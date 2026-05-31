"""End-to-end ingestion: API metadata -> DB -> thumbnail download -> transient
video processing -> features. The video file itself is never persisted.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import httpx
from PIL import Image
from loguru import logger
from sqlalchemy.orm import Session

from creative_director.config import settings
from creative_director.features.audio import extract_audio_features
from creative_director.features.text import (
    extract_description_features,
    extract_title_features,
)
from creative_director.features.thumbnail import (
    extract_face_features,
    extract_ocr_features,
    extract_thumbnail_features,
)
from creative_director.features.video import (
    extract_first_seconds_frames,
    extract_video_features,
)
from creative_director.storage.db import session_scope
from creative_director.storage.models import (
    Channel,
    VelocitySnapshot,
    Video,
    VideoFeatures,
)
from creative_director.utils.tempfiles import download_video_to, transient_video
from creative_director.youtube.channels import (
    iter_upload_video_ids,
    resolve_channel,
)
from creative_director.youtube.client import get_youtube_client
from creative_director.youtube.videos import (
    fetch_videos,
    fetch_videos_batch,
    parse_iso_duration,
    parse_published_at,
)


SHORT_DURATION_LIMIT = 60  # YouTube treats <=60s as Shorts


# --- DB upserts ------------------------------------------------------------


def upsert_channel(session: Session, niche: Optional[str], item: dict) -> Channel:
    cid = item["id"]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})

    channel = session.get(Channel, cid)
    if channel is None:
        channel = Channel(id=cid)
        session.add(channel)

    channel.title = snippet.get("title", "")
    channel.handle = snippet.get("customUrl")
    channel.niche = niche
    channel.subscriber_count = (
        int(stats["subscriberCount"]) if "subscriberCount" in stats else None
    )
    channel.video_count = int(stats["videoCount"]) if "videoCount" in stats else None
    channel.view_count = int(stats["viewCount"]) if "viewCount" in stats else None
    channel.description = snippet.get("description")
    channel.country = snippet.get("country")
    channel.uploads_playlist_id = (
        content.get("relatedPlaylists", {}).get("uploads")
    )
    return channel


def upsert_video(session: Session, channel_id: str, item: dict) -> Video:
    vid = item["id"]
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})

    duration = parse_iso_duration(content.get("duration", ""))
    published = parse_published_at(snippet["publishedAt"])

    video = session.get(Video, vid)
    if video is None:
        video = Video(id=vid, channel_id=channel_id, published_at=published)
        session.add(video)

    video.title = snippet.get("title", "")
    video.description = snippet.get("description")
    video.tags = snippet.get("tags") or []
    video.duration_seconds = duration
    video.is_short = duration <= SHORT_DURATION_LIMIT
    video.published_at = published

    thumbs = snippet.get("thumbnails", {})
    best = (
        thumbs.get("maxres")
        or thumbs.get("standard")
        or thumbs.get("high")
        or thumbs.get("medium")
        or thumbs.get("default")
    )
    if best:
        video.thumbnail_url = best.get("url")

    video.default_language = (
        snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
    )
    video.category_id = snippet.get("categoryId")
    return video


def add_velocity_snapshot(session: Session, video: Video, stats: dict) -> None:
    now = datetime.utcnow()
    hours = (now - video.published_at).total_seconds() / 3600.0
    session.add(
        VelocitySnapshot(
            video_id=video.id,
            captured_at=now,
            hours_since_publish=hours,
            view_count=int(stats.get("viewCount", 0)),
            like_count=int(stats["likeCount"]) if "likeCount" in stats else None,
            comment_count=int(stats["commentCount"]) if "commentCount" in stats else None,
            favorite_count=int(stats["favoriteCount"]) if "favoriteCount" in stats else None,
        )
    )


# --- Thumbnails ------------------------------------------------------------


def download_thumbnail(video_id: str, url: str) -> Optional[Path]:
    if not url:
        return None
    settings.thumbnail_dir.mkdir(parents=True, exist_ok=True)
    path = settings.thumbnail_dir / f"{video_id}.jpg"
    if path.exists():
        return path
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            path.write_bytes(r.content)
        return path
    except Exception as e:
        logger.warning(f"Thumbnail download failed for {video_id}: {e}")
        return None


# --- Feature extraction orchestration -------------------------------------


def _map_thumb_features(t: dict) -> dict:
    """Map keys from thumbnail.extract_thumbnail_features into VideoFeatures.thumb_* columns."""
    return {
        "thumb_face_count": t.get("face_count"),
        "thumb_dominant_face_area": t.get("dominant_face_area"),
        "thumb_text_present": t.get("text_present"),
        "thumb_text": t.get("text"),
        "thumb_text_char_count": t.get("text_char_count"),
        "thumb_brightness": t.get("brightness"),
        "thumb_saturation": t.get("saturation"),
        "thumb_contrast": t.get("contrast"),
        "thumb_dominant_colors": t.get("dominant_colors"),
        "thumb_clip_embedding": t.get("clip_embedding"),
    }


def _first3s_visual_signals(path: Path) -> dict:
    """Run face + OCR detection on a few first-3s frames. Stops early if both found."""
    try:
        frames = extract_first_seconds_frames(path, seconds=3.0, n=4)
        if not frames:
            return {"first3s_face_present": None, "first3s_text_present": None}
        face_present = False
        text_present = False
        for f in frames:
            rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            if not face_present:
                face_present = bool((extract_face_features(pil) or {}).get("face_count"))
            if not text_present:
                text_present = bool((extract_ocr_features(pil) or {}).get("text_present"))
            if face_present and text_present:
                break
        return {
            "first3s_face_present": face_present,
            "first3s_text_present": text_present,
        }
    except Exception as e:
        logger.warning(f"first3s visual signals failed: {e}")
        return {}


def _run_video_feature_extraction(path: Path) -> dict:
    out: dict = {}
    out.update(extract_video_features(path))
    out.update(_first3s_visual_signals(path))
    out.update(extract_audio_features(path))
    return out


def extract_all_features(video: Video, thumb_path: Optional[Path]) -> dict:
    """Run all enabled extractors. Three hybrid modes:

    1. Classic transient (``enable_video_download=True``, no ``video_archive_dir``):
       download -> extract -> delete.

    2. Stage 1 local download (``video_archive_dir`` set, ``extract_video_features=False``):
       download video to archive dir, set ``video.video_file_path``, skip heavy
       feature extraction. Stage 2 (Colab) does that later.

    3. Stage 2 Colab extract-from-saved (``enable_video_download=False``,
       ``extract_video_features=True``, ``video.video_file_path`` set):
       read the persisted file, extract features, leave file alone.
    """
    features: dict = {}

    features.update(extract_title_features(video.title))
    features.update(extract_description_features(video.description or ""))

    if thumb_path and thumb_path.exists():
        features.update(_map_thumb_features(extract_thumbnail_features(thumb_path)))

    # Path A: classic transient mode (download + extract + delete in one pass).
    if (
        settings.enable_video_download
        and settings.extract_video_features
        and not settings.video_archive_dir
    ):
        try:
            with transient_video(video.id) as path:
                features.update(_run_video_feature_extraction(path))
        except Exception as e:
            logger.warning(f"Transient video processing failed for {video.id}: {e}")
        return features

    # Path B: stage-1 local download — keep the file, skip heavy extraction.
    if settings.enable_video_download and settings.video_archive_dir:
        try:
            saved = download_video_to(video.id, settings.video_archive_dir)
            video.video_file_path = str(saved)
            if settings.extract_video_features:
                # Caller asked for full local pipeline: also extract on this machine.
                features.update(_run_video_feature_extraction(saved))
        except Exception as e:
            logger.warning(f"Local archive download failed for {video.id}: {e}")
        return features

    # Path C: stage-2 extract-from-saved (no download, file already on disk).
    if (
        not settings.enable_video_download
        and settings.extract_video_features
        and video.video_file_path
    ):
        saved = Path(video.video_file_path)
        if saved.exists():
            try:
                features.update(_run_video_feature_extraction(saved))
            except Exception as e:
                logger.warning(f"Extract-from-saved failed for {video.id}: {e}")
        else:
            logger.warning(f"video_file_path not found on disk for {video.id}: {saved}")
        return features

    # Otherwise: nothing more to do (e.g. thumbnail-only mode).
    return features


def extract_features_from_file(
    video: Video, mp4_path: Optional[Path], thumb_path: Optional[Path]
) -> dict:
    """Compose every extractor for an ALREADY-downloaded local file, with no
    download-mode/config routing. Used by the on-demand creator-reel analyzer
    (OAuth path), where we fetch the mp4 ourselves and just want features.
    """
    features: dict = {}
    features.update(extract_title_features(video.title))
    features.update(extract_description_features(video.description or ""))
    if thumb_path and Path(thumb_path).exists():
        features.update(_map_thumb_features(extract_thumbnail_features(Path(thumb_path))))
    if mp4_path and Path(mp4_path).exists():
        try:
            features.update(_run_video_feature_extraction(Path(mp4_path)))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"video feature extraction failed for {video.id}: {e}")
    return features


def persist_features(session: Session, video_id: str, features: dict) -> None:
    rec = session.get(VideoFeatures, video_id)
    if rec is None:
        rec = VideoFeatures(video_id=video_id)
        session.add(rec)
    for key, val in features.items():
        if hasattr(rec, key):
            setattr(rec, key, val)
    rec.extracted_at = datetime.utcnow()


# --- Top-level entry -------------------------------------------------------


def _iter_video_items(youtube, uploads_pl: str, scan_cap: int):
    """Yield full video detail records in upload order, fetched lazily in
    batches of 50 so a Shorts-count target can stop the scan early."""
    buf: list[str] = []
    for vid in iter_upload_video_ids(youtube, uploads_pl, max_videos=scan_cap):
        buf.append(vid)
        if len(buf) == 50:
            yield from fetch_videos_batch(youtube, buf)
            buf = []
    if buf:
        yield from fetch_videos_batch(youtube, buf)


def ingest_channel(
    channel_ref: str,
    niche: str,
    max_videos: int = 50,
    shorts_only: bool = True,
    run_feature_extraction: bool = True,
    force_reextract: bool = False,
    max_shorts: Optional[int] = None,
    scan_cap: int = 600,
) -> dict:
    """End-to-end: resolve channel -> fetch videos -> store metadata -> features.

    Resumable: by default, videos that already have a VideoFeatures row are skipped
    during feature extraction. Set ``force_reextract=True`` to re-run features
    (e.g., after upgrading an extractor).

    Depth control:
      - ``max_videos``: scan the N most recent uploads (Shorts + long-form).
      - ``max_shorts``: instead, keep scanning uploads until N *Shorts* have
        been ingested (or ``scan_cap`` uploads exhausted). Use this to deepen a
        channel reliably regardless of how much long-form it posts.
    """
    youtube = get_youtube_client()

    channel_item = resolve_channel(youtube, channel_ref)
    if not channel_item:
        raise ValueError(f"Channel not found: {channel_ref}")

    with session_scope() as session:
        channel = upsert_channel(session, niche, channel_item)
        session.flush()
        uploads_pl = channel.uploads_playlist_id
        channel_id = channel.id

    if not uploads_pl:
        raise ValueError(f"No uploads playlist for channel {channel_ref}")

    if max_shorts is not None:
        items = _iter_video_items(youtube, uploads_pl, scan_cap=scan_cap)
        target_desc = f"{max_shorts} shorts (scan cap {scan_cap})"
    else:
        video_ids = list(
            iter_upload_video_ids(youtube, uploads_pl, max_videos=max_videos)
        )
        items = fetch_videos(youtube, video_ids)
        target_desc = f"{len(video_ids)} uploads"
    logger.info(f"Channel {channel_ref}: scanning {target_desc}")

    processed = 0
    skipped = 0

    for item in items:
        if max_shorts is not None and processed >= max_shorts:
            break
        duration = parse_iso_duration(item.get("contentDetails", {}).get("duration", ""))
        if shorts_only and duration > SHORT_DURATION_LIMIT:
            skipped += 1
            continue

        # 1. Metadata + velocity snapshot
        with session_scope() as session:
            video = upsert_video(session, channel_id, item)
            add_velocity_snapshot(session, video, item.get("statistics", {}))
            video_id = video.id
            thumb_url = video.thumbnail_url
            title = video.title

        # 2. Thumbnail (persistent asset)
        thumb_path = download_thumbnail(video_id, thumb_url) if thumb_url else None
        if thumb_path:
            with session_scope() as session:
                v = session.get(Video, video_id)
                v.thumbnail_path = str(thumb_path)

        # 3. Features (skip if already extracted, unless forced)
        if run_feature_extraction:
            with session_scope() as session:
                already = session.get(VideoFeatures, video_id) is not None
            if already and not force_reextract:
                logger.info(f"[{processed + 1}] {video_id}: features cached, skipping extraction")
            else:
                with session_scope() as session:
                    v = session.get(Video, video_id)
                    features = extract_all_features(v, thumb_path)
                    persist_features(session, video_id, features)

        processed += 1
        logger.info(f"[{processed}] {video_id}: {title[:80]}")

        # Duty-cycle thermal cooldown — give the CPU a breather every N videos.
        # Only relevant when heavy feature extraction runs; metadata-only passes
        # do no sustained CPU work and should not pause.
        if (
            run_feature_extraction
            and settings.cooldown_every_n_videos
            and processed % settings.cooldown_every_n_videos == 0
        ):
            logger.info(
                f"Thermal cooldown: pausing {settings.cooldown_seconds}s "
                f"after {processed} videos"
            )
            time.sleep(settings.cooldown_seconds)

    return {"channel": channel_ref, "processed": processed, "skipped": skipped}
