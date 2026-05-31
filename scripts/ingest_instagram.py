"""CLI: ingest Instagram reels for one or more creators (personal-V1 path).

    python -m scripts.ingest_instagram --niche fitness --username @athleanx --max-reels 40
    python -m scripts.ingest_instagram --niche fitness --seed-file seed_channels/instagram_fitness.yaml

Use a BURNER Instagram account — set INSTAGRAM_USER / INSTAGRAM_PASSWORD in
.env — never your main one. Keep --niche distinct from the YouTube niches (or
point DATABASE_URL at a separate DB) so the two corpora don't mix in the model.

After ingesting, extract features exactly as for the YouTube corpus:
    python -m scripts.extract_features  --niche <niche> --all-labeled
    python -m scripts.extract_timelines --niche <niche>
"""
from pathlib import Path
from typing import Optional

import typer
import yaml
from loguru import logger

from creative_director.ingestion.instagram_pipeline import ingest_instagram_profile
from creative_director.storage.db import init_db

app = typer.Typer(add_completion=False)


@app.command()
def main(
    niche: str = typer.Option(
        ..., help="Niche tag — keep distinct from YouTube niches so corpora don't mix"
    ),
    seed_file: Optional[Path] = typer.Option(
        None, help="YAML file with an 'accounts' list of @handles"
    ),
    username: Optional[str] = typer.Option(None, help="Single Instagram @handle"),
    max_reels: int = typer.Option(60, help="Max reels per creator"),
    shorts_only: bool = typer.Option(True, help="Skip videos longer than 90s"),
):
    init_db()

    targets: list[str] = []
    if seed_file:
        with seed_file.open() as f:
            data = yaml.safe_load(f) or {}
        targets.extend(data.get("accounts") or data.get("channels") or [])
    if username:
        targets.append(username)
    if not targets:
        logger.error("Provide --seed-file or --username")
        raise typer.Exit(code=1)

    for i, ref in enumerate(targets, 1):
        handle = str(ref).lstrip("@")
        logger.info(f"--- [{i}/{len(targets)}] Instagram @{handle} (niche={niche}) ---")
        try:
            result = ingest_instagram_profile(
                ref, niche=niche, max_reels=max_reels, shorts_only=shorts_only
            )
            logger.info(f"Done: {result}")
        except Exception:
            logger.exception(f"Failed to ingest {ref}")


if __name__ == "__main__":
    app()
