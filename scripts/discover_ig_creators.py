"""Discover small/mid IG creators in ANY niche via hashtag scraping + profile filter.

Targets sub-100k creators that won't surface via web-search listicles (biased
toward mega-creators). Uses ``apify/instagram-hashtag-scraper`` to pull recent
posts from niche-specific hashtags, dedupes owner usernames, then runs Profile
Scraper to verify follower band + activity.

Niche-generic: pass ``--niche`` + ``--hashtags`` for any vertical (food,
travel, ...). Defaults reproduce the original fitness discovery run.

Hard cost guards at every step:
  - max_total_charge_usd on each actor call (server-side cap)
  - pre/post usage snapshots between phases (abort if delta exceeds budget)
  - candidate ceiling on the profile-verification pass

Output: prints a clean list of new candidates -- nothing is added to the seed
file automatically. The user reviews and merges manually.

    # fitness (defaults)
    python -m scripts.discover_ig_creators

    # food
    python -m scripts.discover_ig_creators --niche ig_food \
        --hashtags easyrecipes,recipereels,highproteinrecipes,mealprepideas \
        --seed-file seed_channels/instagram_food.yaml
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import typer
import yaml
from loguru import logger

from creative_director.apify.client import run_actor
from creative_director.config import settings
from creative_director.ingestion.instagram_apify_pipeline import fetch_profiles_only

app = typer.Typer(add_completion=False)

# Default (fitness) hashtags. Keep specific (not generic #fitness which surfaces
# mega-accounts and brands) and reel-active. Override per-niche with --hashtags.
HASHTAGS = [
    "calisthenicsworkout",
    "mobilityroutine",
    "homefitness",
    "glutetraining",
]

# Per-phase budget guards (USD).
HASHTAG_COST_CAP_PER_CALL = 0.60     # 4 calls -> $2.40 hard ceiling
PROFILE_COST_CAP = 0.60              # ~200 lookups @ $0.003 = $0.60
TOTAL_BUDGET_HARD_LIMIT = 4.00       # abort if cumulative delta exceeds this

# Per-call result caps (also bounds cost on top of the server-side guard).
RESULTS_PER_HASHTAG = 150
MAX_CANDIDATES_TO_VERIFY = 200


def _get_paid_event_total() -> float:
    """Read current cycle's PAID_ACTORS_PER_EVENT USD from the Apify API."""
    token = settings.apify_api_token
    if not token:
        raise RuntimeError("APIFY_API_TOKEN not set")
    url = f"https://api.apify.com/v2/users/me/usage/monthly?token={token}"
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    events = r.json()["data"]["monthlyServiceUsage"].get("PAID_ACTORS_PER_EVENT")
    return float(events["baseAmountUsd"]) if events else 0.0


def _abort_if_overspent(start_usd: float, phase: str, expected_max: float) -> None:
    """Pre-check cost delta and abort if it has exploded."""
    current = _get_paid_event_total()
    spent = current - start_usd
    if spent > expected_max:
        logger.error(
            f"COST GUARD TRIPPED in {phase}: spent ${spent:.4f} exceeds "
            f"expected ${expected_max:.4f}. Aborting."
        )
        raise typer.Exit(code=2)
    logger.info(f"  cost so far this run: ${spent:.4f} (cap {expected_max:.2f}, phase: {phase})")


def _looks_legit(handle: str) -> bool:
    """Drop the most obvious spam handles. Conservative -- prefers false
    positives over missing real small creators."""
    if len(handle) > 35:
        return False
    if handle.count("_") > 4:
        return False
    if handle.count(".") > 2:
        return False
    return True


@app.command()
def main(
    niche: str = typer.Option(
        "ig_fitness", help="Niche tag for verified candidates (e.g. ig_food)"
    ),
    hashtags: str = typer.Option(
        "", help="Comma-separated hashtags (omit #). Empty = fitness defaults."
    ),
    seed_file: Path = typer.Option(
        Path("seed_channels/instagram_fitness.yaml"),
        help="Existing seed YAML to dedupe against (skipped if it doesn't exist)",
    ),
    min_followers: int = typer.Option(5_000, help="Lower follower bound for target tier"),
    max_followers: int = typer.Option(100_000, help="Upper follower bound for target tier"),
    min_posts: int = typer.Option(50, help="Minimum posts to count as an active creator"),
    max_cost: float = typer.Option(
        TOTAL_BUDGET_HARD_LIMIT, help="Hard total-cost ceiling (USD) for the whole run"
    ),
    max_candidates: int = typer.Option(
        MAX_CANDIDATES_TO_VERIFY, help="Max candidates to profile-verify (more = more creators)"
    ),
):
    start_total = _get_paid_event_total()
    logger.info(f"Pre-run PAID_ACTORS_PER_EVENT: ${start_total:.4f}")
    logger.info(f"Hard total-cost budget: ${max_cost:.2f}")

    # Load existing seed to skip duplicates (a fresh niche may have no seed yet).
    if seed_file.exists():
        seed_data = yaml.safe_load(seed_file.read_text(encoding="utf-8")) or {}
        existing = {a.lstrip("@").lower() for a in seed_data.get("accounts", [])}
    else:
        existing = set()
        logger.info(f"Seed file {seed_file} not found — no dedupe set")
    logger.info(f"Existing seed: {len(existing)} accounts (will skip duplicates)")

    # --- Phase 1: hashtag discovery ---
    hashtags_list = [t.strip().lstrip("#") for t in hashtags.split(",") if t.strip()]
    tags = hashtags_list or HASHTAGS
    all_usernames: set[str] = set()
    sample_by_user: dict[str, dict] = {}

    for tag in tags:
        logger.info(f"Scraping #{tag} (resultsLimit={RESULTS_PER_HASHTAG}, "
                    f"cost_cap=${HASHTAG_COST_CAP_PER_CALL})")
        try:
            items = run_actor(
                "apify/instagram-hashtag-scraper",
                run_input={
                    "hashtags": [tag],
                    "resultsType": "posts",
                    "resultsLimit": RESULTS_PER_HASHTAG,
                },
                max_total_charge_usd=HASHTAG_COST_CAP_PER_CALL,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"#{tag}: scrape failed: {e}")
            continue

        for it in items:
            u = (it.get("ownerUsername") or "").lower()
            if u and u not in sample_by_user:
                sample_by_user[u] = it
            if u:
                all_usernames.add(u)

        _abort_if_overspent(start_total, f"hashtag #{tag}", max_cost)

    logger.info(f"Phase 1 done: {len(all_usernames)} unique candidate usernames")

    # --- Filter: dedupe vs existing seed + spam heuristic ---
    candidates = sorted(
        u for u in (all_usernames - existing) if _looks_legit(u)
    )
    logger.info(f"After dedupe + spam filter: {len(candidates)} candidates")

    n_before_cap = len(candidates)
    candidates = candidates[:max_candidates]
    if len(candidates) < n_before_cap:
        logger.warning(f"Capped candidate list at {max_candidates} to bound cost")

    if not candidates:
        logger.info("No new candidates to verify. Exiting.")
        return

    # --- Phase 2: profile verification (follower band + activity) ---
    logger.info(f"Profile-scraping {len(candidates)} candidates "
                f"(cost_cap=${PROFILE_COST_CAP})")
    pre_profile_total = _get_paid_event_total()
    result = fetch_profiles_only(candidates, niche=f"{niche}_candidates")
    post_profile_total = _get_paid_event_total()
    logger.info(f"Profile pass spent: ${post_profile_total - pre_profile_total:.4f}")

    _abort_if_overspent(start_total, "profile verification", max_cost)

    # --- Phase 3: filter by tier + activity ---
    def is_in_target_tier(p: dict) -> bool:
        followers = p["followers"]
        if not (min_followers <= followers <= max_followers):
            return False
        if p["posts"] < min_posts:
            return False
        if p["private"]:
            return False
        return True

    survivors = [p for p in result["profiles"] if is_in_target_tier(p)]
    too_small = [p for p in result["profiles"] if p["followers"] < min_followers]
    too_big = [p for p in result["profiles"] if p["followers"] > max_followers]
    inactive = [p for p in result["profiles"]
                if min_followers <= p["followers"] <= max_followers and p["posts"] < min_posts]

    print()
    print("=" * 72)
    print("DISCOVERY RESULTS")
    print("=" * 72)
    print(f"Niche: {niche}   Hashtags scraped: {', '.join('#'+t for t in tags)}")
    print(f"Unique usernames found: {len(all_usernames)}")
    print(f"After dedup+filter: {len(candidates)} candidates profile-verified")
    print(f"Out of band: too small ({len(too_small)}), too big ({len(too_big)}), "
          f"inactive ({len(inactive)})")
    print(f"Missing/404: {len(result.get('missing', []))}")
    print()
    print(f"NEW CANDIDATES ({min_followers:,}-{max_followers:,} followers, "
          f"posts>={min_posts}, public)")
    print("=" * 72)
    if survivors:
        print(f"  {'@handle':<30} {'followers':>10} {'posts':>7}  flags")
        print(f"  {'-' * 30} {'-' * 10} {'-' * 7}  -----")
        for p in sorted(survivors, key=lambda x: x["followers"], reverse=True):
            v = "verified" if p.get("verified") else ""
            print(f"  @{p['username']:<29} {p['followers']:>10,} "
                  f"{p['posts']:>7,}  {v}")
    else:
        print("  (none -- consider broadening hashtags or follower band)")

    print()
    final_total = _get_paid_event_total()
    print(f"Total discovery spend: ${final_total - start_total:.4f}")
    print(f"PAID_ACTORS_PER_EVENT now: ${final_total:.4f}")


if __name__ == "__main__":
    app()
