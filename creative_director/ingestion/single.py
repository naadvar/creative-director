"""Ingest one video by ID — the on-demand path for the frontend.

``ingest_channel`` walks a whole channel; the frontend needs to analyze a single
pasted URL. This reuses the same upsert / feature / timeline steps for one video.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from loguru import logger
from sqlalchemy import select

from creative_director.ingestion.pipeline import (
    SHORT_DURATION_LIMIT,
    add_velocity_snapshot,
    download_thumbnail,
    extract_all_features,
    persist_features,
    upsert_channel,
    upsert_video,
)
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoFeatures, VideoTimeline
from creative_director.youtube.channels import fetch_channel
from creative_director.youtube.client import get_youtube_client
from creative_director.youtube.videos import fetch_videos, parse_iso_duration


def video_exists(video_id: str) -> bool:
    """True if this video is already ingested with features extracted."""
    with session_scope() as s:
        return s.get(VideoFeatures, video_id) is not None


def ingest_single_video(
    video_id: str,
    niche: str = "fitness",
    run_timeline: bool = True,
    force: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Fetch, featurize, and timeline one video so the advice layer can analyze it.

    Idempotent: if the video already has features (and a timeline), returns early
    unless ``force`` is set. ``progress`` is an optional status callback for UIs.
    """
    say = progress or (lambda _msg: None)

    if not force and video_exists(video_id):
        has_tl = True
        if run_timeline:
            with session_scope() as s:
                has_tl = (
                    s.scalar(
                        select(VideoTimeline.id).where(
                            VideoTimeline.video_id == video_id
                        )
                    )
                    is not None
                )
        if has_tl:
            say("Already ingested — using cached analysis.")
            return {"video_id": video_id, "cached": True}

    say("Fetching video metadata from YouTube...")
    youtube = get_youtube_client()
    items = list(fetch_videos(youtube, [video_id]))
    if not items:
        raise ValueError(
            f"Video {video_id} not found via the YouTube Data API "
            "(it may be private, deleted, or the ID is wrong)."
        )
    item = items[0]

    duration = parse_iso_duration(item.get("contentDetails", {}).get("duration", ""))
    if duration > SHORT_DURATION_LIMIT:
        raise ValueError(
            f"Video is {duration}s long — this tool analyzes Shorts "
            f"(<={SHORT_DURATION_LIMIT}s) only."
        )

    channel_id = item["snippet"]["channelId"]
    say("Fetching channel metadata...")
    channel_item = fetch_channel(youtube, channel_id)
    if not channel_item:
        raise ValueError(f"Channel {channel_id} could not be fetched.")

    with session_scope() as session:
        upsert_channel(session, niche, channel_item)
        session.flush()
        video = upsert_video(session, channel_id, item)
        add_velocity_snapshot(session, video, item.get("statistics", {}))
        thumb_url = video.thumbnail_url

    say("Downloading thumbnail...")
    thumb_path = download_thumbnail(video_id, thumb_url) if thumb_url else None
    if thumb_path:
        with session_scope() as session:
            v = session.get(Video, video_id)
            v.thumbnail_path = str(thumb_path)

    say("Downloading video and extracting features (this is the slow step)...")
    with session_scope() as session:
        v = session.get(Video, video_id)
        features = extract_all_features(v, thumb_path)
        persist_features(session, video_id, features)
        file_path = v.video_file_path

    if run_timeline:
        if file_path and Path(file_path).exists():
            say("Extracting per-second timeline...")
            from creative_director.features.timeline import extract_timeline

            timeline = extract_timeline(Path(file_path), niche=niche)
            with session_scope() as session:
                for old in (
                    session.execute(
                        select(VideoTimeline).where(
                            VideoTimeline.video_id == video_id
                        )
                    )
                    .scalars()
                    .all()
                ):
                    session.delete(old)
                for row in timeline:
                    session.add(VideoTimeline(video_id=video_id, **row))
        else:
            logger.warning(
                f"{video_id}: no video file on disk, skipping timeline extraction"
            )

    say("Done.")
    return {"video_id": video_id, "cached": False, "duration": duration}
