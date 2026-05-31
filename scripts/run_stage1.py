"""Stage 1 stratified IG ingest: LARGE / MID / SMALL batches sequentially.

Cost-monitored: snapshots Apify usage before each batch, aborts if the
per-batch delta exceeds 1.5x expected OR if cumulative spend exceeds the
hard total budget. Each batch is its own subprocess so a partial failure
doesn't kill the wrapper itself.

    python -m scripts.run_stage1
"""
from __future__ import annotations

import subprocess
import sys
from typing import NamedTuple

import httpx
import typer
from loguru import logger

from creative_director.config import settings

app = typer.Typer(add_completion=False)


class Batch(NamedTuple):
    tier: str
    seed_file: str
    max_reels: int
    expected_cap_usd: float
    n_creators: int


# Per-reel cost measured 2026-05-20 (Stage 0): $0.00258 without
# includeDownloadedVideo. expected_cap_usd = num_creators * max_reels * 0.003
# (slight buffer over measured rate).
BATCHES = [
    Batch("LARGE", "seed_channels/instagram_fitness_large.yaml", 15, 0.60, 12),
    Batch("MID",   "seed_channels/instagram_fitness_mid.yaml",   80, 2.75, 11),
    Batch("SMALL", "seed_channels/instagram_fitness_small.yaml", 50, 4.20, 27),
]

# Hard total-cost ceiling. Stage 1 expected total ~$6.50; abort if cumulative
# session spend exceeds this (catches an unexpected pricing shift).
HARD_TOTAL_CEILING_USD = 12.00

# Per-batch spike threshold (multiple of expected_cap_usd).
SPIKE_THRESHOLD = 1.5


def _get_paid_event_total() -> float:
    token = settings.apify_api_token
    if not token:
        raise RuntimeError("APIFY_API_TOKEN not set")
    r = httpx.get(
        f"https://api.apify.com/v2/users/me/usage/monthly?token={token}",
        timeout=30,
    )
    r.raise_for_status()
    events = r.json()["data"]["monthlyServiceUsage"].get("PAID_ACTORS_PER_EVENT")
    return float(events["baseAmountUsd"]) if events else 0.0


@app.command()
def main():
    start = _get_paid_event_total()
    logger.info(f"Stage 1 starting: pre-snapshot ${start:.4f}")
    logger.info(f"Hard ceiling: cumulative spend > ${HARD_TOTAL_CEILING_USD:.2f} -> abort")

    for batch in BATCHES:
        pre = _get_paid_event_total()
        logger.info("")
        logger.info("=" * 64)
        logger.info(
            f"[{batch.tier}] {batch.n_creators} creators x max-reels {batch.max_reels} "
            f"(resultsLimit={batch.n_creators * batch.max_reels})"
        )
        logger.info(f"[{batch.tier}] pre: ${pre:.4f}, expected cap ${batch.expected_cap_usd:.2f}")
        logger.info("=" * 64)

        rc = subprocess.run(
            [
                sys.executable, "-m", "scripts.ingest_instagram_apify",
                "--niche", "ig_fitness",
                "--seed-file", batch.seed_file,
                "--max-reels", str(batch.max_reels),
            ],
        ).returncode

        post = _get_paid_event_total()
        delta = post - pre
        cumulative = post - start
        logger.info("")
        logger.info(
            f"[{batch.tier}] post: ${post:.4f}  delta ${delta:.4f}  "
            f"cumulative ${cumulative:.4f}  exit={rc}"
        )

        if delta > batch.expected_cap_usd * SPIKE_THRESHOLD:
            logger.error(
                f"COST SPIKE in {batch.tier}: delta ${delta:.4f} > "
                f"{SPIKE_THRESHOLD}x expected ${batch.expected_cap_usd:.2f}. Aborting."
            )
            raise typer.Exit(code=2)
        if cumulative > HARD_TOTAL_CEILING_USD:
            logger.error(
                f"TOTAL OVER HARD CEILING: cumulative ${cumulative:.4f} > "
                f"${HARD_TOTAL_CEILING_USD:.2f}. Aborting."
            )
            raise typer.Exit(code=3)
        if rc != 0:
            logger.warning(
                f"{batch.tier} subprocess exited with {rc} -- continuing to next batch"
            )

    final = _get_paid_event_total()
    print()
    print("=" * 64)
    print("STAGE 1 STRATIFIED INGEST COMPLETE")
    print("=" * 64)
    print(f"Started:    ${start:.4f}")
    print(f"Finished:   ${final:.4f}")
    print(f"Total cost: ${final - start:.4f}")


if __name__ == "__main__":
    app()
