"""Fast vibe-only re-extraction.

Re-scores VideoTimeline.primary_vibe + clip_scores with the niche-aware CLIP
prompts WITHOUT re-running the expensive parts of full timeline extraction
(scene detection, audio/beat analysis, full-video decode). For each video it
seeks ~1 frame per existing timeline-second, runs CLIP, and UPDATEs only the
two vibe columns — leaving cuts / motion / beats / faces untouched.

This exists because the only thing that changed is the CLIP prompt taxonomy
(advice/clip_prompts.py): food / travel / fashion frames were previously
scored against the fitness prompt set. Full re-extraction is ~120s/video
(mostly decode); this is ~10x faster since it only samples the frames CLIP
needs.

    python -m scripts.reextract_vibes --scope-niche ig_food
    python -m scripts.reextract_vibes --scope-niche ig_food --limit 5     # test
    python -m scripts.reextract_vibes --scope-niche ig_travel --shard 0/12

The CLIP prompt set is the video's own channel niche (overridable with
--niche). Missing mp4s are pulled from R2 and deleted after (--fetch-missing).
"""
from pathlib import Path
from typing import Optional

import av
import httpx
import typer
from loguru import logger
from sqlalchemy import func, select, update

from creative_director.config import settings
from creative_director.features.timeline import _clip_scores
from creative_director.storage import media
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel, Video, VideoTimeline

app = typer.Typer(add_completion=False)


def _sample_frames(path: Path, seconds: list[int]) -> dict[int, "object"]:
    """Seek to each second and grab one frame (keyframe-aligned, ~1 decode/sec)."""
    out: dict[int, object] = {}
    container = av.open(str(path))
    try:
        vs = container.streams.video[0]
        vs.thread_count = 1  # keep per-process threads bounded (many shards)
        tb = vs.time_base
        for sec in seconds:
            try:
                container.seek(int(sec / tb), stream=vs, backward=True, any_frame=False)
                for frame in container.decode(vs):
                    out[sec] = frame.to_image()
                    break
            except Exception:  # noqa: BLE001 — skip unseekable seconds
                continue
    finally:
        container.close()
    return out


@app.command()
def main(
    scope_niche: str = typer.Option(..., "--scope-niche", help="Channel.niche to process"),
    niche: Optional[str] = typer.Option(
        None, "--niche", help="Override CLIP prompt set (default: video's own niche)"
    ),
    limit: int = typer.Option(0, help="Max videos (0 = all)"),
    shard: str = typer.Option("", help="Process shard i/n of the targets, e.g. 0/12"),
    fetch_missing: bool = typer.Option(
        True, "--fetch-missing/--no-fetch-missing", help="Pull missing mp4s from R2"
    ),
):
    init_db()
    archive = settings.video_archive_dir or Path("data/videos")

    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Channel.niche)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == scope_niche)
        ).all()
        targets = [
            (vid, vn)
            for vid, vn in rows
            if s.scalar(
                select(func.count(VideoTimeline.id)).where(
                    VideoTimeline.video_id == vid
                )
            )
            > 0
        ]

    targets.sort(key=lambda t: t[0])
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        targets = targets[i::n]
        logger.info(f"shard {i}/{n}: {len(targets)} targets")
    if limit:
        targets = targets[:limit]
    logger.info(f"{len(targets)} videos to re-vibe")

    done = 0
    for video_id, vniche in targets:
        path = archive / f"{video_id}.mp4"
        fetched = False
        try:
            if not path.exists():
                if not fetch_missing:
                    continue
                url = media.video_url(video_id)
                if not url:
                    logger.warning(f"{video_id}: not in R2, skipping")
                    continue
                with httpx.Client(timeout=180, follow_redirects=True) as c:
                    r = c.get(url)
                    r.raise_for_status()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(r.content)
                fetched = True

            with session_scope() as s:
                secs = [
                    row[0]
                    for row in s.execute(
                        select(VideoTimeline.second).where(
                            VideoTimeline.video_id == video_id
                        )
                    ).all()
                ]
            if not secs:
                continue
            frames = _sample_frames(path, secs)
            use_niche = niche or vniche
            with session_scope() as s:
                for sec, img in frames.items():
                    scores = _clip_scores(img, use_niche)
                    vibe = max(scores, key=scores.get)
                    s.execute(
                        update(VideoTimeline)
                        .where(
                            VideoTimeline.video_id == video_id,
                            VideoTimeline.second == sec,
                        )
                        .values(primary_vibe=vibe, clip_scores=scores)
                    )
        except Exception as e:  # noqa: BLE001 — never let one reel abort the run
            logger.warning(f"{video_id}: failed: {e}")
            continue
        finally:
            if fetched:
                path.unlink(missing_ok=True)

        done += 1
        if done % 25 == 0 or done == len(targets):
            logger.info(f"[{done}/{len(targets)}] {video_id}: re-vibed {len(frames)} secs")

    logger.info(f"Done. {done} videos re-vibed.")


if __name__ == "__main__":
    app()
