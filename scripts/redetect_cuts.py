"""Backfill is_cut on existing VideoTimeline rows using PySceneDetect.

Faster than re-running the full timeline extraction: only re-detects scene
cuts (no CLIP), then updates the is_cut flag on existing per-second rows.

    python -m scripts.redetect_cuts --limit 3   # test
    python -m scripts.redetect_cuts             # all timelined videos
"""
from pathlib import Path

import typer
from loguru import logger
from sqlalchemy import select

from creative_director.features.timeline import detect_cut_seconds
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoTimeline


app = typer.Typer(add_completion=False)


@app.command()
def main(limit: int = typer.Option(0, help="Max videos to process (0 = all)")):
    with session_scope() as s:
        video_ids = (
            s.execute(
                select(VideoTimeline.video_id).distinct()
            )
            .scalars()
            .all()
        )
        paths = {
            v.id: v.video_file_path
            for v in s.execute(
                select(Video).where(Video.id.in_(video_ids))
            ).scalars()
        }

    targets = [(vid, paths.get(vid)) for vid in video_ids if paths.get(vid)]
    if limit:
        targets = targets[:limit]
    logger.info(f"Re-detecting cuts for {len(targets)} videos")

    done = 0
    for vid, fp in targets:
        path = Path(fp)
        if not path.exists():
            logger.warning(f"{vid}: file missing, skipping")
            continue
        cuts = detect_cut_seconds(path)
        with session_scope() as s:
            rows = (
                s.execute(select(VideoTimeline).where(VideoTimeline.video_id == vid))
                .scalars()
                .all()
            )
            for r in rows:
                r.is_cut = r.second in cuts
        done += 1
        if done % 25 == 0:
            logger.info(f"[{done}/{len(targets)}] ...")
    logger.info(f"Done. Re-detected cuts for {done} videos.")


if __name__ == "__main__":
    app()
