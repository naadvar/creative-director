"""Generate + cache Craft X-ray reads for given video_ids (pulls the mp4 from R2).

    python -m scripts.gen_craft_reads <video_id> [<video_id> ...]

Idempotent: adds the video_features.craft_read column if missing, skips reels that
already have a read unless --force.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from loguru import logger
from sqlalchemy import text

from creative_director.advice.craft_xray import extract_craft_read
from creative_director.config import settings
from creative_director.storage import media
from creative_director.storage.db import engine, session_scope
from creative_director.storage.models import Video, VideoFeatures


def ensure_column() -> None:
    with engine.begin() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(video_features)"))]
        if "craft_read" not in cols:
            conn.execute(text("ALTER TABLE video_features ADD COLUMN craft_read JSON"))
            logger.info("added video_features.craft_read column")


def gen(video_ids: list[str], force: bool = False) -> None:
    ensure_column()
    for vid in video_ids:
        with session_scope() as s:
            v = s.get(Video, vid)
            f = s.query(VideoFeatures).filter(VideoFeatures.video_id == vid).first()
            if not v or not f:
                logger.warning(f"{vid}: no video/features row, skip")
                continue
            if f.craft_read and not force:
                logger.info(f"{vid}: already has craft_read, skip")
                continue
            niche = v.channel.niche if v.channel else None
            dur = v.duration_seconds
            caption = getattr(f, "caption_text", None) or v.title
        tmp = Path(tempfile.gettempdir()) / f"craftgen_{vid}.mp4"
        try:
            media._client().download_file(settings.r2_bucket, media.video_key(vid), str(tmp))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{vid}: R2 download failed: {type(e).__name__}: {str(e)[:120]}")
            continue
        read = extract_craft_read(str(tmp), niche=niche, caption=caption, duration_s=dur)
        tmp.unlink(missing_ok=True)
        if not read:
            logger.warning(f"{vid}: craft read returned None")
            continue
        with session_scope() as s:
            f = s.query(VideoFeatures).filter(VideoFeatures.video_id == vid).first()
            f.craft_read = read
        logger.info(f"{vid}: cached craft_read ({len(read.get('blind_spots', []))} blind spots)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    gen(args, force="--force" in sys.argv)
