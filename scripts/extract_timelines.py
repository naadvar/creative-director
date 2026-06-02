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

import httpx
import typer
from loguru import logger
from sqlalchemy import select, func, delete

from creative_director.config import settings
from creative_director.features.timeline import extract_timeline
from creative_director.storage import media
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel, Video, VideoTimeline


app = typer.Typer(add_completion=False)


@app.command()
def main(
    limit: int = typer.Option(0, help="Max videos to process (0 = all)"),
    niche: Optional[str] = typer.Option(
        None,
        "--niche",
        help="Override the CLIP prompt set for ALL videos. Default (None): use "
        "each video's own channel niche, so a mixed run stays correct.",
    ),
    scope_niche: Optional[str] = typer.Option(
        None,
        "--scope-niche",
        help="Only process videos whose channel.niche matches this. None = all.",
    ),
    force: bool = typer.Option(False, help="Re-extract videos that already have a timeline"),
    shard: str = typer.Option(
        "", help="Process only shard i/n of the targets, e.g. 0/6 (for parallel runs)"
    ),
    fetch_missing: bool = typer.Option(
        True,
        "--fetch-missing/--no-fetch-missing",
        help="If the local mp4 is absent, pull it from R2 just for this run and "
        "delete it afterwards (keeps pod disk low). --no-fetch-missing = local only.",
    ),
):
    init_db()  # creates the video_timeline table if missing

    # Resolve video files by convention ({video_archive_dir}/{id}.mp4) rather
    # than the stored video_file_path — the DB holds Windows-style paths that
    # do not resolve on a Colab/Linux run.
    archive = settings.video_archive_dir or Path("data/videos")

    with session_scope() as s:
        # Always carry each video's channel niche so we can pick the right CLIP
        # prompt set per video (the niche option only overrides this).
        q = select(Video, Channel.niche).join(Channel, Channel.id == Video.channel_id)
        if scope_niche:
            q = q.where(Channel.niche == scope_niche)
        rows = s.execute(q).all()
        targets = []
        for v, vniche in rows:
            path = archive / f"{v.id}.mp4"
            if not fetch_missing and not path.exists():
                continue  # local-only mode: nothing on disk to extract
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
            targets.append((v.id, str(path), vniche))

    targets.sort(key=lambda t: t[0])  # stable order so parallel shards stay disjoint
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        targets = targets[i::n]
        logger.info(f"shard {i}/{n}: {len(targets)} of the targets")

    if limit:
        targets = targets[:limit]
    logger.info(f"{len(targets)} videos to process")

    done = 0
    for video_id, file_path, vniche in targets:
        path = Path(file_path)
        fetched = False
        if not path.exists():
            if not fetch_missing:
                logger.warning(f"{video_id}: file missing at {path}, skipping")
                continue
            url = media.video_url(video_id)
            if not url:
                logger.warning(f"{video_id}: not in R2 (no url), skipping")
                continue
            try:
                with httpx.Client(timeout=180, follow_redirects=True) as c:
                    r = c.get(url)
                    r.raise_for_status()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(r.content)
                fetched = True
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{video_id}: R2 fetch failed: {e}")
                continue
        use_niche = niche or vniche  # explicit override, else the video's own niche
        try:
            timeline = extract_timeline(path, niche=use_niche)
            with session_scope() as s:
                if force:
                    # Delete-then-insert in one txn: flush the deletes FIRST so the
                    # new rows can't collide with the old ones on (video_id, second).
                    s.execute(
                        delete(VideoTimeline).where(
                            VideoTimeline.video_id == video_id
                        )
                    )
                    s.flush()
                for row in timeline:
                    s.add(VideoTimeline(video_id=video_id, **row))
        except Exception as e:  # noqa: BLE001 — never let one reel abort a long run
            logger.warning(f"{video_id}: failed: {e}")
            continue
        finally:
            if fetched:
                path.unlink(missing_ok=True)  # keep pod disk low

        done += 1
        logger.info(f"[{done}/{len(targets)}] {video_id}: {len(timeline)} seconds")

    logger.info(f"Done. {done} videos timelined.")


if __name__ == "__main__":
    app()
