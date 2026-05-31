"""End-to-end Instagram reel ingestion (personal-V1 path).

Mirrors ingestion/pipeline.py's ``ingest_channel`` but sources data from
instaloader instead of the YouTube Data API. Writes the same Channel / Video /
VelocitySnapshot rows — IDs are namespaced with an ``ig_`` prefix — and saves
each reel's mp4 + thumbnail under the ``{video_archive_dir}/{id}.mp4``
convention, so the existing feature / timeline / label / model / advice layers
work unchanged.

Feature extraction is NOT run here. After ingesting, run the same scripts as
for the YouTube corpus:
    python -m scripts.extract_features  --niche <niche> --all-labeled
    python -m scripts.extract_timelines --niche <niche>
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger

from creative_director.config import settings
from creative_director.instagram.client import get_instaloader
from creative_director.instagram.profiles import fetch_profile
from creative_director.instagram.reels import iter_reels
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, VelocitySnapshot, Video

REEL_DURATION_LIMIT = 90  # seconds — typical reel ceiling for the analyzer


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)


def _upsert_ig_channel(session, niche: str, profile) -> Channel:
    cid = f"ig_{profile.username}"
    channel = session.get(Channel, cid)
    if channel is None:
        channel = Channel(id=cid)
        session.add(channel)
    channel.title = profile.full_name or profile.username
    channel.handle = profile.username
    channel.niche = niche
    channel.subscriber_count = int(profile.followers or 0)
    channel.video_count = int(profile.mediacount or 0)
    channel.description = profile.biography
    channel.uploads_playlist_id = None
    return channel


def _upsert_ig_video(session, channel_id: str, video_id: str, post) -> Video:
    caption = post.caption or ""
    title = caption.splitlines()[0][:200] if caption.strip() else f"Reel {post.shortcode}"
    duration = int(post.video_duration or 0)

    video = session.get(Video, video_id)
    if video is None:
        video = Video(id=video_id, channel_id=channel_id, published_at=post.date_utc)
        session.add(video)
    video.title = title
    video.description = caption
    try:
        video.tags = list(post.caption_hashtags)
    except Exception:  # noqa: BLE001
        video.tags = []
    video.duration_seconds = duration
    video.is_short = duration <= REEL_DURATION_LIMIT
    video.published_at = post.date_utc
    video.thumbnail_url = post.url
    return video


def _add_ig_velocity(session, video: Video, post) -> None:
    now = datetime.utcnow()
    hours = (now - video.published_at).total_seconds() / 3600.0
    session.add(
        VelocitySnapshot(
            video_id=video.id,
            captured_at=now,
            hours_since_publish=hours,
            view_count=int(post.video_view_count or 0),
            like_count=int(post.likes) if post.likes is not None else None,
            comment_count=int(post.comments) if post.comments is not None else None,
            favorite_count=None,
        )
    )


def ingest_instagram_profile(
    username: str,
    niche: str,
    max_reels: int = 60,
    shorts_only: bool = True,
) -> dict:
    """Ingest up to ``max_reels`` reels for one Instagram creator."""
    loader = get_instaloader()
    profile = fetch_profile(loader, username)

    with session_scope() as s:
        channel = _upsert_ig_channel(s, niche, profile)
        channel_id = channel.id

    archive = settings.video_archive_dir or Path("data/videos")
    processed = skipped = failed = 0

    for post in iter_reels(profile, max_reels=max_reels):
        try:
            duration = int(post.video_duration or 0)
            if shorts_only and duration > REEL_DURATION_LIMIT:
                skipped += 1
                continue

            video_id = f"ig_{post.shortcode}"
            video_url = post.video_url
            thumb_url = post.url

            with session_scope() as s:
                video = _upsert_ig_video(s, channel_id, video_id, post)
                _add_ig_velocity(s, video, post)

            dest = archive / f"{video_id}.mp4"
            if not dest.exists():
                _download(video_url, dest)

            thumb = settings.thumbnail_dir / f"{video_id}.jpg"
            if not thumb.exists() and thumb_url:
                try:
                    _download(thumb_url, thumb)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"{video_id}: thumbnail download failed: {e}")

            with session_scope() as s:
                v = s.get(Video, video_id)
                v.video_file_path = str(dest)
                if thumb.exists():
                    v.thumbnail_path = str(thumb)

            processed += 1
            logger.info(f"[{processed}] {video_id}: {(post.caption or '')[:70]}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"{post.shortcode}: ingestion failed: {e}")

    return {
        "profile": profile.username,
        "channel": channel_id,
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
    }
