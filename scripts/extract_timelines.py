"""CLI: extract per-second timelines for archived videos (Phase 2).

Reads videos that have a downloaded file (video_file_path set) and don't yet
have timeline rows, runs the per-second extractor, and persists VideoTimeline
rows. Resumable — re-run after an interruption and it skips done videos.

    python -m scripts.extract_timelines --limit 3       # test on a few
    python -m scripts.extract_timelines                 # all archived videos
    python -m scripts.extract_timelines --scope-niche ig_fitness  # only one niche

``--niche`` controls the CLIP prompt set used during extraction.
``--scope-niche`` filters which videos are processed by Channel.niche
(orthogonal — defaults to None, processing every archived video).
"""
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from sqlalchemy import select, func

from creative_director.config import settings
from creative_director.features.timeline import extract_timeline
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel, Video, VideoTimeline


app = typer.Typer(add_completion=False)


@app.command()
def main(
    limit: int = typer.Option(0, help="Max videos to process (0 = all)"),
    niche: str = typer.Option("fitness", help="Niche for CLIP prompt set"),
    scope_niche: Optional[str] = typer.Option(
        None,
        "--scope-niche",
        help="Only process videos whose channel.niche matches this. None = all.",
    ),
    force: bool = typer.Option(False, help="Re-extract videos that already have a timeline"),
    shard: str = typer.Option(
        "", help="Process only shard i/n of the targets, e.g. 0/6 (for parallel runs)"
    ),
):
    init_db()  # creates the video_timeline table if missing

    # Resolve video files by convention ({video_archive_dir}/{id}.mp4) rather
    # than the stored video_file_path — the DB holds Windows-style paths that
    # do not resolve on a Colab/Linux run.
    archive = settings.video_archive_dir or Path("data/videos")

    with session_scope() as s:
        q = select(Video)
        if scope_niche:
            q = q.join(Channel, Channel.id == Video.channel_id).where(
                Channel.niche == scope_niche
            )
        videos = s.execute(q).scalars().all()
        targets = []
        for v in videos:
            path = archive / f"{v.id}.mp4"
            if not path.exists():
                continue
            has_tl = (
                s.scalar(
                    select(func.count(VideoTimeline.id)).where(
                        VideoTimeline.video_id == v.id
                    )
                )
                > 0
            )
            if has_tl and not force:
                continue
            targets.append((v.id, str(path)))

    targets.sort()  # stable order so parallel shards stay disjoint
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        targets = targets[i::n]
        logger.info(f"shard {i}/{n}: {len(targets)} of the targets")

    if limit:
        targets = targets[:limit]
    logger.info(f"{len(targets)} videos to process")

    done = 0
    for video_id, file_path in targets:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"{video_id}: file missing at {path}, skipping")
            continue
        try:
            timeline = extract_timeline(path, niche=niche)
        except Exception as e:
            logger.warning(f"{video_id}: timeline extraction failed: {e}")
            continue

        with session_scope() as s:
            if force:
                for old in (
                    s.execute(
                        select(VideoTimeline).where(
                            VideoTimeline.video_id == video_id
                        )
                    )
                    .scalars()
                    .all()
                ):
                    s.delete(old)
            for row in timeline:
                s.add(VideoTimeline(video_id=video_id, **row))

        done += 1
        logger.info(f"[{done}/{len(targets)}] {video_id}: {len(timeline)} seconds")

    logger.info(f"Done. {done} videos timelined.")


if __name__ == "__main__":
    app()
