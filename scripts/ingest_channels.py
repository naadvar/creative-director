"""CLI: ingest channels from a seed-list YAML, by ID/handle, or from the DB.

Examples
--------
    python -m scripts.ingest_channels --niche fitness --seed-file seed_channels/fitness.yaml
    python -m scripts.ingest_channels --niche travel --channel @LostLeBlanc --max-videos 30
    # Deepen every channel already in the DB (all niches), metadata only:
    python -m scripts.ingest_channels --from-db --max-shorts 600 --no-features
    # Daily discovery pass — catch new uploads on known channels:
    python -m scripts.ingest_channels --from-db --max-videos 30 --no-features
"""
from pathlib import Path
from typing import Optional

import typer
import yaml
from loguru import logger
from sqlalchemy import select

from creative_director.ingestion.pipeline import ingest_channel
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel

app = typer.Typer(add_completion=False)


@app.command()
def main(
    niche: Optional[str] = typer.Option(
        None, help="Niche tag. Required for --seed-file/--channel; filters --from-db."
    ),
    seed_file: Optional[Path] = typer.Option(None, help="YAML file with a 'channels' list"),
    channel: Optional[str] = typer.Option(None, help="Single channel ID (UC...) or @handle"),
    from_db: bool = typer.Option(
        False, help="Ingest every channel already in the DB (optionally filtered by --niche)"
    ),
    max_videos: int = typer.Option(50, help="Max recent uploads to scan per channel"),
    max_shorts: Optional[int] = typer.Option(
        None, help="Deepen until N Shorts ingested per channel (overrides --max-videos)"
    ),
    scan_cap: int = typer.Option(600, help="Hard cap on uploads scanned when --max-shorts is set"),
    shorts_only: bool = typer.Option(True, help="Skip videos longer than 60s"),
    no_features: bool = typer.Option(
        False, help="Skip feature extraction (metadata + thumbnails only)"
    ),
    force_reextract: bool = typer.Option(
        False, help="Re-run feature extraction even for videos already featurized"
    ),
):
    init_db()

    # (channel_ref, niche) pairs to ingest.
    targets: list[tuple[str, str]] = []

    if from_db:
        with session_scope() as s:
            # Exclude Instagram channels -- this is the YouTube Data API
            # ingest path; ig_* IDs always 404 here. (The IG corpus is
            # ingested via scripts/ingest_instagram_apify.py and shouldn't
            # be touched by the daily YouTube discover task.)
            q = select(Channel).where(~Channel.id.like("ig_%"))
            if niche:
                q = q.where(Channel.niche == niche)
            for ch in s.execute(q).scalars():
                targets.append((ch.id, ch.niche or niche or "unknown"))
        logger.info(f"--from-db: {len(targets)} channels selected (ig_* excluded)")

    if seed_file:
        if not niche:
            logger.error("--niche is required with --seed-file")
            raise typer.Exit(code=1)
        with seed_file.open() as f:
            data = yaml.safe_load(f) or {}
        targets.extend((ref, niche) for ref in data.get("channels", []))

    if channel:
        if not niche:
            logger.error("--niche is required with --channel")
            raise typer.Exit(code=1)
        targets.append((channel, niche))

    if not targets:
        logger.error("Provide --from-db, --seed-file, or --channel")
        raise typer.Exit(code=1)

    for i, (ref, ch_niche) in enumerate(targets, 1):
        logger.info(f"--- [{i}/{len(targets)}] Ingesting {ref} (niche={ch_niche}) ---")
        try:
            result = ingest_channel(
                channel_ref=ref,
                niche=ch_niche,
                max_videos=max_videos,
                max_shorts=max_shorts,
                scan_cap=scan_cap,
                shorts_only=shorts_only,
                run_feature_extraction=not no_features,
                force_reextract=force_reextract,
            )
            logger.info(f"Done: {result}")
        except Exception:
            logger.exception(f"Failed to ingest {ref}")


if __name__ == "__main__":
    app()
