"""Authenticated creator endpoints: list their own Reels (and, later, analyze
them). Uses the stored Instagram token to call the Graph API on their behalf —
authorized data, no scraping."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy import select

from api.auth import get_current_user
from api.config import api_settings
from creative_director.config import settings
from creative_director.ingestion.pipeline import (
    extract_features_from_file,
    persist_features,
)
from creative_director.features.timeline import extract_timeline
from creative_director.storage.db import session_scope
from creative_director.storage.models import (
    Channel,
    ConnectedAccount,
    Video,
    VideoFeatures,
    VideoLabel,
    VideoTimeline,
)

router = APIRouter(prefix="/me", tags=["creator"])

_GRAPH = "https://graph.instagram.com"


@router.get("/fingerprint")
def my_fingerprint(user: dict = Depends(get_current_user)) -> dict:
    """The creator's style fingerprint, built from their OWN uploaded reels.
    Descriptive only; accumulates as they upload more."""
    from creative_director.profile.fingerprint import compute_fingerprint

    return compute_fingerprint(user["id"])
_DEMO_TOKEN = "DEMO"  # marks the dev demo account; served from the corpus


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)


def _parse_ts(s: Optional[str]) -> datetime:
    if not s:
        return datetime.utcnow()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return datetime.utcnow()


def _ig_account(user_id: int) -> ConnectedAccount:
    """Return the user's Instagram ConnectedAccount or 400 if not connected."""
    with session_scope() as s:
        acct = (
            s.execute(
                select(ConnectedAccount).where(
                    (ConnectedAccount.user_id == user_id)
                    & (ConnectedAccount.platform == "instagram")
                )
            )
            .scalars()
            .first()
        )
        if acct is None or not acct.access_token:
            raise HTTPException(status_code=400, detail="No Instagram account connected.")
        # Detach the fields we need (session closes after this scope).
        return {  # type: ignore[return-value]
            "token": acct.access_token,
            "username": acct.username,
        }


@router.get("/reels")
def my_reels(
    request: Request,
    user: dict = Depends(get_current_user),
    limit: int = 24,
) -> dict:
    """List the creator's own Reels via the Instagram Graph API.

    Returns lightweight reel cards (id, thumbnail, caption, timestamp,
    permalink, basic counts). media_url (the mp4) is fetched on-demand at
    analyze time because IG CDN URLs expire quickly.
    """
    acct = _ig_account(user["id"])

    # Demo account: serve already-analyzable reels from the corpus so the authed
    # app can be previewed without OAuth. video_id is set, so the gallery links
    # straight to the existing /video/{id} dashboard (no extraction needed).
    if acct["token"] == _DEMO_TOKEN:
        scheme = api_settings.label_scheme
        with session_scope() as s:
            rows = s.execute(
                select(
                    Video.id,
                    Video.title,
                    Video.published_at,
                    VideoLabel.tercile,
                    VideoLabel.score,
                )
                .join(VideoFeatures, VideoFeatures.video_id == Video.id)
                .join(Channel, Channel.id == Video.channel_id)
                # Inner-join the label so demo tiles always carry a grade — newer
                # scraped reels are unlabeled (labels are a periodic snapshot), so
                # an outer join would surface ungraded reels first.
                .join(
                    VideoLabel,
                    (VideoLabel.video_id == Video.id)
                    & (VideoLabel.label_scheme == scheme),
                )
                .where(Channel.niche == "ig_fitness")
                .order_by(Video.published_at.desc())
                .limit(limit)
            ).all()
        reels = [
            {
                "id": vid,
                "video_id": vid,
                "thumbnail_url": f"/api/videos/{vid}/thumbnail",
                "permalink": None,
                "caption": (title or "")[:280],
                "timestamp": pa.isoformat() if pa else None,
                "like_count": None,
                "comments_count": None,
                "tercile": terc,
                "score": score,
            }
            for vid, title, pa, terc, score in rows
        ]
        return {"username": "demo_creator", "count": len(reels), "reels": reels}

    fields = (
        "id,media_type,media_product_type,thumbnail_url,permalink,"
        "caption,timestamp,like_count,comments_count"
    )
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{_GRAPH}/{api_settings.instagram_graph_version}/me/media",
            params={"fields": fields, "limit": limit, "access_token": acct["token"]},
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Instagram API error ({resp.status_code}). Token may be expired — reconnect.",
        )
    data = resp.json().get("data", [])
    reels = [
        {
            "id": m.get("id"),
            "video_id": None,  # not ingested yet -> gallery shows "Analyze"
            "thumbnail_url": m.get("thumbnail_url"),
            "permalink": m.get("permalink"),
            "caption": (m.get("caption") or "")[:280],
            "timestamp": m.get("timestamp"),
            "like_count": m.get("like_count"),
            "comments_count": m.get("comments_count"),
            "tercile": None,  # not analyzed yet
            "score": None,
        }
        for m in data
        if m.get("media_product_type") == "REELS"
    ]
    return {"username": acct["username"], "count": len(reels), "reels": reels}


@router.post("/reels/{media_id}/analyze")
def analyze_my_reel(
    media_id: str, request: Request, user: dict = Depends(get_current_user)
) -> dict:
    """Ingest the creator's own Reel (authorized data, no scraping) and run the
    existing analysis pipeline, so the result renders in the standard /video/{id}
    dashboard (Scorecard, findings, timeline, examples).

    NOTE: this runs live feature extraction (CLIP + Whisper + PyAV, ~60-90s on
    CPU). Fine on a real deployment box; on the dev laptop, use sparingly (the
    sustained CLIP/Whisper load is what overheats it).
    """
    acct = _ig_account(user["id"])
    token, username = acct["token"], acct["username"]
    ver = api_settings.instagram_graph_version

    with httpx.Client(timeout=60) as client:
        m = client.get(
            f"{_GRAPH}/{ver}/{media_id}",
            params={
                "fields": "id,media_type,media_product_type,media_url,thumbnail_url,caption,timestamp",
                "access_token": token,
            },
        )
        if m.status_code != 200:
            raise HTTPException(status_code=502, detail="Couldn't fetch this Reel from Instagram.")
        media = m.json()
        prof = client.get(
            f"{_GRAPH}/{ver}/me",
            params={"fields": "followers_count", "access_token": token},
        )
        followers = (
            prof.json().get("followers_count") if prof.status_code == 200 else None
        )

    media_url = media.get("media_url")
    if not media_url:
        raise HTTPException(
            status_code=400,
            detail="This Reel has no downloadable media (IG CDN URL may have expired — retry).",
        )

    video_id = f"ig_{media_id}"
    channel_id = f"ig_{username or user['id']}"
    caption = media.get("caption") or ""
    published_at = _parse_ts(media.get("timestamp"))

    # Upsert Channel + Video (ig_fitness so it uses the IG benchmarks).
    with session_scope() as s:
        ch = s.get(Channel, channel_id)
        if ch is None:
            ch = Channel(id=channel_id)
            s.add(ch)
        ch.title = username or channel_id
        ch.niche = "ig_fitness"
        if followers is not None:
            ch.subscriber_count = int(followers)

        v = s.get(Video, video_id)
        if v is None:
            v = Video(id=video_id, channel_id=channel_id)
            s.add(v)
        v.channel_id = channel_id
        v.title = (caption[:200] or "Reel").strip()
        v.description = caption
        v.published_at = published_at
        v.is_short = True

    archive = settings.video_archive_dir or Path("data/videos")
    mp4_path = archive / f"{video_id}.mp4"
    thumb_path = Path("data/thumbnails") / f"{video_id}.jpg"
    try:
        _download(media_url, mp4_path)
        if media.get("thumbnail_url"):
            _download(media["thumbnail_url"], thumb_path)
    except Exception as e:  # noqa: BLE001
        logger.error(f"reel download failed for {video_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to download the Reel media.")

    # Extract features + per-second timeline from the saved file.
    with session_scope() as s:
        v = s.get(Video, video_id)
        v.video_file_path = str(mp4_path)
        v.thumbnail_path = str(thumb_path) if thumb_path.exists() else None
        features = extract_features_from_file(
            v, mp4_path, thumb_path if thumb_path.exists() else None
        )
        persist_features(s, video_id, features)

        try:
            tl = extract_timeline(mp4_path, niche="ig_fitness")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"timeline extraction failed for {video_id}: {e}")
            tl = []
        if tl:
            v.duration_seconds = len(tl)
            s.query(VideoTimeline).filter(VideoTimeline.video_id == video_id).delete()
            for row in tl:
                s.add(
                    VideoTimeline(
                        video_id=video_id,
                        second=row["second"],
                        primary_vibe=row.get("primary_vibe"),
                        clip_scores=row.get("clip_scores"),
                        motion=row.get("motion"),
                        brightness=row.get("brightness"),
                        has_face=row.get("has_face"),
                        is_cut=row.get("is_cut"),
                        on_beat=row.get("on_beat"),
                    )
                )

    logger.info(f"Analyzed own reel {video_id} for user {user['id']}")
    return {"video_id": video_id}
