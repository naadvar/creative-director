"""CLI: ingest Instagram reels via Apify (public-data path, no IG login needed).

Cheap pre-flight (Profile Scraper only, ~$0.03 for 20 creators) -- recommended
before any reel pull. Validates handles, surfaces follower counts so you can
re-tier the seed before scaling.
    python -m scripts.ingest_instagram_apify --niche ig_fitness \
        --seed-file seed_channels/instagram_fitness.yaml --profiles-only

Smoke test (1 creator, 5 reels, ~$0.005):
    python -m scripts.ingest_instagram_apify --niche ig_fitness \
        --username @jeffnippard --max-reels 5

Full ingest (20 creators x 60 reels, ~$1.20):
    python -m scripts.ingest_instagram_apify --niche ig_fitness \
        --seed-file seed_channels/instagram_fitness.yaml --max-reels 60

Requires APIFY_API_TOKEN in .env.

After ingest, extract features the same way as the YouTube corpus:
    python -m scripts.extract_features  --niche <niche> --all-labeled
    python -m scripts.extract_timelines --niche <niche>
"""
from pathlib import Path
from typing import Optional

import typer
import yaml
from loguru import logger

from creative_director.ingestion.instagram_apify_pipeline import (
    fetch_profiles_only,
    ingest_instagram_profiles_apify,
)
from creative_director.storage.db import init_db

app = typer.Typer(add_completion=False)


def _load_targets(seed_file: Optional[Path], username: Optional[str]) -> list[str]:
    targets: list[str] = []
    if seed_file:
        with seed_file.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        targets.extend(data.get("accounts") or data.get("channels") or [])
    if username:
        targets.append(username)
    return [str(t).strip() for t in targets if t]


def _print_profiles_table(result: dict) -> None:
    """Print fetch_profiles_only result as a sorted-by-followers table so the
    user can eyeball the real tier spread vs. the seed-file guess."""
    profiles = result.get("profiles", [])
    if profiles:
        typer.echo("")
        typer.echo(f"{'@handle':<30} {'followers':>12} {'posts':>8}  flags")
        typer.echo("-" * 66)
        for p in profiles:
            flags = []
            if p.get("private"):
                flags.append("private")
            if p.get("verified"):
                flags.append("verified")
            followers = f"{p['followers']:,}" if p["followers"] else "0"
            typer.echo(
                f"@{p['username']:<29} {followers:>12} {p['posts']:>8}  "
                f"{' '.join(flags)}"
            )
        typer.echo("")
    missing = result.get("missing", [])
    if missing:
        typer.echo(f"MISSING ({len(missing)}): {', '.join('@' + m for m in missing)}")


@app.command()
def main(
    niche: str = typer.Option(
        ..., help="Niche tag -- keep distinct from YouTube niches (e.g. ig_fitness)"
    ),
    seed_file: Optional[Path] = typer.Option(
        None, help="YAML file with an 'accounts' (or 'channels') list of @handles"
    ),
    username: Optional[str] = typer.Option(None, help="Single Instagram @handle"),
    max_reels: int = typer.Option(
        60, help="Max reels per creator (passed as resultsLimit to Reel Scraper)"
    ),
    shorts_only: bool = typer.Option(True, help="Skip videos longer than 90s"),
    profiles_only: bool = typer.Option(
        False,
        help="Just run Profile Scraper (cheap pre-flight; no reel pull, no media downloads)",
    ),
    max_cost_usd: float = typer.Option(
        0.0,
        "--max-cost-usd",
        help="Hard cost cap (USD) on each actor call. 0 = no cap.",
    ),
):
    init_db()
    targets = _load_targets(seed_file, username)
    if not targets:
        logger.error("Provide --seed-file or --username")
        raise typer.Exit(code=1)

    handles = [t.lstrip("@") for t in targets]
    mode = "profiles-only pre-flight" if profiles_only else "full ingest"
    logger.info(f"--- Apify IG {mode}: {len(handles)} creator(s), niche={niche} ---")

    if profiles_only:
        result = fetch_profiles_only(handles, niche=niche)
        _print_profiles_table(result)
        logger.info(
            f"Done: requested={result['requested']} found={result['found']} "
            f"missing={len(result.get('missing', []))}"
        )
    else:
        result = ingest_instagram_profiles_apify(
            handles,
            niche=niche,
            max_reels_per_profile=max_reels,
            shorts_only=shorts_only,
            max_cost_usd=max_cost_usd if max_cost_usd > 0 else None,
        )
        logger.info(f"Done: {result}")


if __name__ == "__main__":
    app()
