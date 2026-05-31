"""End-to-end Instagram reel ingestion via Apify (public-data path).

Mirrors instagram_pipeline.py's row shape but sources data from the Apify
``apify/instagram-reel-scraper`` + ``apify/instagram-profile-scraper`` actors
instead of instaloader. Writes the same Channel / Video / VelocitySnapshot
rows (IDs prefixed ``ig_``) and saves each reel's mp4 + thumbnail under the
``{video_archive_dir}/{id}.mp4`` convention, so the existing
feature / timeline / label / model / advice layers reuse unchanged.

Two entry points:
- ``fetch_profiles_only`` — cheap pre-flight (Profile Scraper only,
  ~$0.0016 per creator). Upserts Channel rows with follower counts; no reels.
  Use it to verify handles + see real follower tiers before scaling.
- ``ingest_instagram_profiles_apify`` — full pull: Profile Scraper for the
  Channel rows, then Reel Scraper for the reels, then mp4 + thumbnail
  downloads.

Feature extraction is NOT run here; same as the instaloader path, after
ingest run:
    python -m scripts.extract_features  --niche <niche> --all-labeled
    python -m scripts.extract_timelines --niche <niche>
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
from loguru import logger

from creative_director.apify.client import run_actor
from creative_director.config import settings
from creative_director.storage import media
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, VelocitySnapshot, Video

REEL_DURATION_LIMIT = 90  # seconds — typical reel ceiling for the analyzer


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)


def _parse_ts(s: str) -> datetime:
    # Apify timestamps look like "2024-01-15T10:30:00.000Z".
    # Python 3.11+ fromisoformat handles the "Z" suffix; strip tz to match
    # the rest of the DB (naive UTC).
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _upsert_ig_channel(session, niche: str, profile: dict) -> Channel:
    username = (profile.get("username") or "").lower()
    cid = f"ig_{username}"
    channel = session.get(Channel, cid)
    if channel is None:
        channel = Channel(id=cid)
        session.add(channel)
    channel.title = profile.get("fullName") or username
    channel.handle = username
    channel.niche = niche
    channel.subscriber_count = int(profile.get("followersCount") or 0)
    channel.video_count = int(profile.get("postsCount") or 0)
    channel.description = profile.get("biography")
    channel.uploads_playlist_id = None
    return channel


def _upsert_ig_video(session, channel_id: str, video_id: str, item: dict) -> Video:
    caption = item.get("caption") or ""
    title = caption.splitlines()[0][:200] if caption.strip() else f"Reel {item.get('shortCode')}"
    duration = int(item.get("videoDuration") or 0)
    published_at = _parse_ts(item["timestamp"])

    video = session.get(Video, video_id)
    if video is None:
        video = Video(id=video_id, channel_id=channel_id, published_at=published_at)
        session.add(video)
    video.title = title
    video.description = caption
    video.tags = list(item.get("hashtags") or [])
    video.duration_seconds = duration
    video.is_short = duration <= REEL_DURATION_LIMIT
    video.published_at = published_at
    video.thumbnail_url = item.get("displayUrl")

    # IG-specific metadata that's already in the scraper response at no extra
    # cost. musicInfo is the highest-value one (trending audio is a major reel
    # performance driver). Persist as-is (SQLAlchemy JSON columns handle
    # serialisation); None when the scraper omitted the field.
    video.music_info = item.get("musicInfo")
    video.mentions = item.get("mentions")
    video.tagged_users = item.get("taggedUsers")
    video.dimensions_height = item.get("dimensionsHeight")
    video.dimensions_width = item.get("dimensionsWidth")
    video.comments_disabled = item.get("isCommentsDisabled")
    video.coauthor_producers = item.get("coauthorProducers")
    video.latest_comments = item.get("latestComments")
    return video


def _add_ig_velocity(session, video: Video, item: dict) -> None:
    now = datetime.utcnow()
    hours = (now - video.published_at).total_seconds() / 3600.0
    # videoPlayCount is Meta's canonical Reels metric; videoViewCount is the
    # older unique-views number. Use plays where available.
    view_count = int(item.get("videoPlayCount") or item.get("videoViewCount") or 0)
    likes = item.get("likesCount")
    comments = item.get("commentsCount")
    session.add(
        VelocitySnapshot(
            video_id=video.id,
            captured_at=now,
            hours_since_publish=hours,
            view_count=view_count,
            like_count=int(likes) if likes is not None else None,
            comment_count=int(comments) if comments is not None else None,
            favorite_count=None,
        )
    )


def fetch_profiles_only(usernames: list[str], niche: str) -> dict:
    """Cheap pre-flight: just run Profile Scraper.

    Upserts Channel rows with follower counts (no reels). Use this to
    validate handles + see real follower tiers before scaling the reel pull.
    Cost on the Free tier: ~$0.0016 per creator.
    """
    handles = [u.lstrip("@").strip().lower() for u in usernames]
    items = run_actor(
        settings.apify_instagram_profile_actor,
        run_input={"usernames": handles},
    )
    found: list[dict] = []
    found_handles: set[str] = set()
    with session_scope() as s:
        for p in items:
            username = (p.get("username") or "").lower()
            if not username:
                continue
            _upsert_ig_channel(s, niche, p)
            found.append(
                {
                    "username": username,
                    "followers": int(p.get("followersCount") or 0),
                    "posts": int(p.get("postsCount") or 0),
                    "private": bool(p.get("private")),
                    "verified": bool(p.get("verified")),
                }
            )
            found_handles.add(username)

    missing = [h for h in handles if h not in found_handles]
    return {
        "requested": len(handles),
        "found": len(found),
        "missing": missing,
        "profiles": sorted(found, key=lambda x: x["followers"], reverse=True),
    }


def ingest_instagram_profiles_apify(
    usernames: list[str],
    niche: str,
    max_reels_per_profile: int = 60,
    shorts_only: bool = True,
    max_cost_usd: float | None = None,
) -> dict:
    """Full ingest: Profile Scraper for channels, then Reel Scraper for reels.

    Batches all profiles into one actor run per actor (amortises cold-starts;
    one profile-scraper run + one reel-scraper run for the whole seed list).

    Channels are upserted from the Profile Scraper output; reels whose owner
    didn't come back from the profile run are dropped (without follower count
    the views/follower label is broken — better to skip than corrupt).

    ``max_cost_usd`` caps each actor call's billed spend at the Apify side
    (server-side hard stop). 10% goes to profile scraper, 90% to reel scraper.
    """
    handles = [u.lstrip("@").strip().lower() for u in usernames]
    profile_cap = max_cost_usd * 0.10 if max_cost_usd else None
    reel_cap = max_cost_usd * 0.90 if max_cost_usd else None

    # 1. Profile scraper — channel rows + follower counts.
    profile_items = run_actor(
        settings.apify_instagram_profile_actor,
        run_input={"usernames": handles},
        max_total_charge_usd=profile_cap,
    )
    found_handles: set[str] = set()
    with session_scope() as s:
        for p in profile_items:
            username = (p.get("username") or "").lower()
            if not username:
                continue
            if p.get("private"):
                logger.warning(f"profile @{username} is private — skipping reels")
                continue
            _upsert_ig_channel(s, niche, p)
            found_handles.add(username)

    missing = [h for h in handles if h not in found_handles]
    if missing:
        logger.warning(f"profiles not found / private: {missing}")
    if not found_handles:
        logger.error("no usable profiles — aborting reel pull")
        return {
            "profiles_requested": len(handles),
            "profiles_found": 0,
            "profiles_missing": missing,
            "reels_processed": 0,
        }

    # 2. Reel scraper — only for found, non-private profiles.
    #
    # Gotchas verified the hard way on 2026-05-20 (burned $4.50 of $5 Free
    # quota on 45 reels):
    # - Reel scraper input uses singular "username" (an array) — confusingly
    #   different from profile scraper's plural "usernames".
    # - includeDownloadedVideo=True is a PAID EVENT (~$0.10/reel) for the
    #   reliable 3-day MP4 URL. Keep it OFF; use videoUrl + immediate
    #   _download() instead — works fine, proven on the smoke test (the URL
    #   stays live long enough since we download in the same run).
    # - resultsLimit is GLOBAL across all input profiles, NOT per-profile
    #   (despite the input-schema wording). 26 profiles × resultsLimit=50
    #   yielded 50 reels TOTAL with 10 creators getting zero. Scale by
    #   num_profiles for an upper bound — the actor still distributes
    #   unevenly, so strict per-creator quotas would need one call per
    #   profile (more event overhead).
    reel_items = run_actor(
        settings.apify_instagram_reel_actor,
        run_input={
            "username": sorted(found_handles),
            "resultsLimit": max_reels_per_profile * len(found_handles),
            "skipPinnedPosts": True,
            "includeDownloadedVideo": False,
        },
        # Deep mega-account feeds need more than the 10-min default to finish;
        # max_total_charge_usd is the real spend bound, and run_actor now keeps
        # the partial dataset on timeout/cost-cap anyway.
        timeout_secs=1800,
        max_total_charge_usd=reel_cap,
    )

    archive = settings.video_archive_dir or Path("data/videos")

    # 3. Phase 1: upsert videos + velocity (fast, sequential), collect download
    #    tasks. Only reels owned by a seeded profile (drops scraper bleed-in).
    skipped = failed = 0
    tasks: list[tuple[str, str | None, str | None]] = []
    for item in reel_items:
        shortcode = item.get("shortCode")
        if not shortcode:
            failed += 1
            continue
        try:
            duration = int(item.get("videoDuration") or 0)
            if shorts_only and duration > REEL_DURATION_LIMIT:
                skipped += 1
                continue
            owner = (item.get("ownerUsername") or "").lower()
            if owner not in found_handles:
                failed += 1  # reel scraper recommend-bleed from a non-seed account
                continue

            channel_id = f"ig_{owner}"
            video_id = f"ig_{shortcode}"
            with session_scope() as s:
                video = _upsert_ig_video(s, channel_id, video_id, item)
                _add_ig_velocity(s, video, item)
                # Convention path (valid on the pod after rclone); set in Phase 1
                # so parallel Phase 2 needs no DB writes (no SQLite contention).
                video.video_file_path = str(archive / f"{video_id}.mp4")
                video.thumbnail_path = str(settings.thumbnail_dir / f"{video_id}.jpg")
            tasks.append(
                (
                    video_id,
                    item.get("downloadedVideo") or item.get("videoUrl"),
                    item.get("displayUrl"),
                )
            )
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"{shortcode}: upsert failed: {e}")

    # 4. Phase 2: parallel download + R2 mirror + prune. IG CDN URLs expire in
    #    ~hours, so a thread pool races them where a sequential loop would lose
    #    the back half of a large pull.
    processed = 0
    if tasks:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(t: tuple[str, str | None, str | None]) -> bool:
            video_id, video_url, thumb_url = t
            dest = archive / f"{video_id}.mp4"
            got_video = dest.exists()
            if video_url and not got_video:
                try:
                    _download(video_url, dest)
                    got_video = True
                except Exception:  # noqa: BLE001
                    return False
            thumb = settings.thumbnail_dir / f"{video_id}.jpg"
            if thumb_url and not thumb.exists():
                try:
                    _download(thumb_url, thumb)
                except Exception:  # noqa: BLE001
                    pass
            if settings.r2_enabled:
                try:
                    if dest.exists():
                        media.mirror_video(dest, video_id)
                    if thumb.exists():
                        media.mirror_thumbnail(thumb, video_id)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"{video_id}: R2 upload failed: {e}")
                if settings.r2_prune_local:
                    for p in (dest, thumb):
                        try:
                            if p.exists():
                                p.unlink()
                        except OSError:
                            pass
            return got_video

        logger.info(f"downloading {len(tasks)} reels with 16 workers ...")
        with ThreadPoolExecutor(max_workers=16) as ex:
            futures = [ex.submit(_fetch_one, t) for t in tasks]
            for i, fut in enumerate(as_completed(futures), 1):
                if fut.result():
                    processed += 1
                if i % 200 == 0:
                    logger.info(f"  {i}/{len(tasks)} downloaded (ok={processed})")

    return {
        "profiles_requested": len(handles),
        "profiles_found": len(found_handles),
        "profiles_missing": missing,
        "reels_processed": processed,
        "reels_skipped": skipped,
        "reels_failed": failed,
    }
