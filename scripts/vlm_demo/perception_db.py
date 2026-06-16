"""Local DB ops for the VLM-perception backfill (run on the laptop, not the pod):

    python -m scripts.vlm_demo.perception_db migrate          # add the column
    python -m scripts.vlm_demo.perception_db export-manifest  # work-list for the pod
    python -m scripts.vlm_demo.perception_db load             # apply pod results -> DB

The pod never needs the DB: it gets the manifest (a small JSONL of video ids +
metadata), pulls mp4s from R2, runs the VLM, and writes a perception JSONL that
this `load` command applies back into VideoFeatures.vlm_perception.
"""
import json
from pathlib import Path

import typer
from loguru import logger
from sqlalchemy import select, text

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

app = typer.Typer(add_completion=False)
IG_NICHES = ["ig_fitness", "ig_food", "ig_travel", "ig_fashion"]
MANIFEST = Path("data/tmp/perception_manifest.jsonl")
RESULTS = Path("data/tmp/vlm_perception_backfill.jsonl")


@app.command()
def migrate() -> None:
    """Add VideoFeatures.vlm_perception if missing (SQLite ALTER TABLE)."""
    with session_scope() as s:
        cols = [r[1] for r in s.execute(text("PRAGMA table_info(video_features)")).all()]
        if "vlm_perception" in cols:
            logger.info("vlm_perception column already present.")
            return
        s.execute(text("ALTER TABLE video_features ADD COLUMN vlm_perception JSON"))
        logger.info("Added video_features.vlm_perception column.")


@app.command("export-manifest")
def export_manifest(niche: str = typer.Option(None), all: bool = typer.Option(True, "--all/--one")) -> None:
    """Write the pod work-list: one JSON line per featurized IG reel."""
    niches = IG_NICHES if (all and not niche) else [niche]
    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Channel.niche, Video.duration_seconds, Video.title)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(Channel.niche.in_(niches)).order_by(Video.id)
        ).all()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8") as fh:
        for vid, nm, dur, title in rows:
            fh.write(json.dumps({"video_id": vid, "niche": nm, "duration_seconds": dur,
                                 "title": (title or "")[:200]}, ensure_ascii=False) + "\n")
    logger.info(f"wrote {len(rows)} reels -> {MANIFEST}")


@app.command()
def load(path: str = typer.Option(str(RESULTS), help="perception JSONL from the pod")) -> None:
    """Apply the pod's perception JSONL into VideoFeatures.vlm_perception."""
    p = Path(path)
    if not p.exists():
        logger.error(f"{p} not found"); raise typer.Exit(1)
    n_set = n_null = n_miss = 0
    with session_scope() as s:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            tags = rec.get("vlm_perception")
            vf = s.get(VideoFeatures, rec["video_id"])
            if vf is None:
                n_miss += 1
                continue
            vf.vlm_perception = tags
            n_set += 1 if tags else 0
            n_null += 0 if tags else 1
    logger.info(f"loaded: {n_set} with tags, {n_null} null/skipped, {n_miss} video_id not found")


if __name__ == "__main__":
    app()
