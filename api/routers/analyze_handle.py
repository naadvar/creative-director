"""POST /analyze-handle — paste an Instagram handle, scrape the creator's recent
reels via Apify, featurise them, so the /videos/{id}/* endpoints can analyze them.

This is the HEAVY product path: Apify scrape + mp4 download + CLIP/Whisper feature
extraction takes minutes, so the work runs in a background thread and the client
polls GET /analyze-handle/{job_id} until status == 'done'. The job registry is
in-memory (fine for a single backend instance; a real queue is the eventual
upgrade).

Gated with the rest of the ingest family via ENABLE_INGEST — available on the
full / worker deploy, not the light serve-only one (it needs the torch stack).
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

router = APIRouter(tags=["analyze-handle"])


def parse_handle(text: str) -> Optional[str]:
    """Pull an Instagram username out of a handle or a profile URL."""
    text = (text or "").strip()
    if not text:
        return None
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", text)
    if m:
        return m.group(1).lower()
    t = text.lstrip("@").rstrip("/")
    if re.fullmatch(r"[A-Za-z0-9._]{1,30}", t):
        return t.lower()
    return None


@dataclass
class _Job:
    id: str
    handle: str
    niche: str
    max_reels: int
    status: str = "running"  # running | done | error
    message: str = ""
    video_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None
    created: float = field(default_factory=time.time)


_JOBS: dict[str, _Job] = {}


class AnalyzeHandleRequest(BaseModel):
    handle: str
    niche: str = "ig_fitness"
    max_reels: int = 6


class JobStatus(BaseModel):
    job_id: str
    status: str
    message: str
    handle: str
    niche: str
    video_ids: list[str]
    error: Optional[str] = None


def _status(job: _Job) -> JobStatus:
    return JobStatus(
        job_id=job.id,
        status=job.status,
        message=job.message,
        handle=job.handle,
        niche=job.niche,
        video_ids=job.video_ids,
        error=job.error,
    )


def _run_job(job: _Job) -> None:
    """Scrape the handle's reels (Apify) then featurise them. Heavy imports are
    deferred to here so the router stays light at module load."""
    try:
        from pathlib import Path

        import httpx
        from sqlalchemy import desc, select

        from creative_director.config import settings
        from creative_director.ingestion.instagram_apify_pipeline import (
            ingest_instagram_profiles_apify,
        )
        from creative_director.ingestion.pipeline import (
            extract_all_features,
            persist_features,
        )
        from creative_director.storage import media
        from creative_director.storage.db import session_scope
        from creative_director.storage.models import Video, VideoFeatures

        # 1. Scrape + store + R2-mirror the creator's recent reels.
        job.message = f"scraping @{job.handle} via Apify…"
        cap = round(0.02 + 0.02 * job.max_reels, 2)  # server-side spend guard
        res = ingest_instagram_profiles_apify(
            [job.handle],
            niche=job.niche,
            max_reels_per_profile=job.max_reels,
            max_cost_usd=cap,
        )
        if not res.get("profiles_found"):
            job.status = "error"
            job.error = f"@{job.handle} not found, private, or returned no reels."
            return

        # 2. The creator's newest reels.
        cid = f"ig_{job.handle}"
        with session_scope() as s:
            video_ids = (
                s.execute(
                    select(Video.id)
                    .where(Video.channel_id == cid)
                    .order_by(desc(Video.published_at))
                    .limit(job.max_reels)
                )
                .scalars()
                .all()
            )
        if not video_ids:
            job.status = "error"
            job.error = "scrape returned no reels for this handle."
            return

        # 3. Featurise each: pull the mp4 from R2 -> extract -> persist -> clean up.
        #    (The ingest pipeline prunes the local mp4 after mirroring to R2, so we
        #    re-fetch it here for the extractor, which reads from local disk.)
        archive = settings.video_archive_dir or Path("data/videos")
        archive.mkdir(parents=True, exist_ok=True)
        done: list[str] = []
        for i, vid in enumerate(video_ids, 1):
            job.message = f"analyzing reel {i}/{len(video_ids)}…"
            try:
                with session_scope() as s:
                    if s.get(VideoFeatures, vid) is not None:
                        done.append(vid)
                        continue
                mp4 = archive / f"{vid}.mp4"
                if not mp4.exists():
                    url = media.video_url(vid)
                    if url:
                        with httpx.Client(timeout=120, follow_redirects=True) as c:
                            r = c.get(url)
                            r.raise_for_status()
                            mp4.write_bytes(r.content)
                with session_scope() as s:
                    v = s.get(Video, vid)
                    if v is None:
                        continue
                    thumb = settings.thumbnail_dir / f"{vid}.jpg"
                    feats = extract_all_features(v, thumb if thumb.exists() else None)
                    persist_features(s, vid, feats)
                done.append(vid)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{vid}: featurise failed: {e}")
            finally:
                try:
                    (archive / f"{vid}.mp4").unlink(missing_ok=True)
                except OSError:
                    pass

        job.video_ids = done
        job.status = "done"
        job.message = f"ready — {len(done)} of {len(video_ids)} reels analyzed."
    except Exception as e:  # noqa: BLE001
        logger.exception("analyze-handle job failed")
        job.status = "error"
        job.error = str(e)


@router.post("/analyze-handle", response_model=JobStatus)
def analyze_handle(req: AnalyzeHandleRequest) -> JobStatus:
    """Kick off scraping + featurising a creator's recent reels in the background.
    Poll GET /analyze-handle/{job_id} until status is 'done' (then read the
    /videos/{id}/* endpoints for each returned video_id)."""
    handle = parse_handle(req.handle)
    if not handle:
        raise HTTPException(422, "Could not parse an Instagram handle from that input.")
    max_reels = max(1, min(int(req.max_reels or 6), 15))
    job = _Job(id=uuid.uuid4().hex[:12], handle=handle, niche=req.niche, max_reels=max_reels)
    _JOBS[job.id] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    logger.info(f"analyze-handle job {job.id} started for @{handle} (niche={req.niche})")
    return _status(job)


@router.get("/analyze-handle/{job_id}", response_model=JobStatus)
def analyze_handle_status(job_id: str) -> JobStatus:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job id (it may have expired on a restart).")
    return _status(job)
