"""POST /upload — upload your own reel, get the full analysis.

The compliant product path: the creator provides the video (no scraping, no
OAuth), picks their niche, and the full pipeline runs on it — features +
per-second timeline — so every /videos/{id}/* endpoint works on the result,
exactly like a corpus video. Uploaded videos live under synthetic ``up_``
channels that are EXCLUDED from the public corpus browse.

Heavy work (Whisper/CLIP/scene detection) runs in a background thread; the
client polls GET /upload/{job_id} until status == 'done', then navigates to
/video/{video_id}. Gated by ENABLE_UPLOAD (default on) — needs the full
extraction stack, so serve-only deploys without torch should disable it.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from loguru import logger
from pydantic import BaseModel

router = APIRouter(tags=["upload"])

# The niches with extracted benchmark corpora. Uploads must map to one so the
# winner comparisons / vibe prompts / cohort wording all resolve.
ALLOWED_NICHES = {"ig_fitness", "ig_food", "ig_travel", "ig_fashion"}

MAX_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_DURATION_S = 180  # 3 minutes — short-form only
UPLOADS_PER_DAY = 10  # per client IP


@dataclass
class _Job:
    id: str
    video_id: str
    niche: str
    status: str = "running"  # running | done | error
    message: str = "queued…"
    error: Optional[str] = None
    created: float = field(default_factory=time.time)


_JOBS: dict[str, _Job] = {}
_UPLOADS_BY_IP: dict[str, list[float]] = {}


class UploadJobStatus(BaseModel):
    job_id: str
    status: str
    message: str
    video_id: str
    niche: str
    error: Optional[str] = None


def _status(job: _Job) -> UploadJobStatus:
    return UploadJobStatus(
        job_id=job.id,
        status=job.status,
        message=job.message,
        video_id=job.video_id,
        niche=job.niche,
        error=job.error,
    )


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.time()
    window = [t for t in _UPLOADS_BY_IP.get(ip, []) if now - t < 86_400]
    _UPLOADS_BY_IP[ip] = window
    return len(window) >= UPLOADS_PER_DAY


def _probe_duration(path: Path) -> Optional[float]:
    """Container duration in seconds via PyAV (None if unreadable)."""
    import av

    try:
        with av.open(str(path)) as container:
            if container.duration is not None:
                return float(container.duration) / av.time_base
            vs = container.streams.video[0]
            if vs.duration is not None and vs.time_base is not None:
                return float(vs.duration * vs.time_base)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"duration probe failed for {path}: {e}")
    return None


def _first_frame_thumbnail(mp4: Path, out_jpg: Path) -> bool:
    """Grab a representative early frame (~0.5s in) as the thumbnail."""
    import cv2

    cap = cv2.VideoCapture(str(mp4))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, 500)
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_MSEC, 0)
            ok, frame = cap.read()
        if not ok:
            return False
        out_jpg.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_jpg), frame)
        return True
    finally:
        cap.release()


def _run_job(job: _Job, mp4: Path) -> None:
    """Featurise + timeline an uploaded reel. Heavy imports stay in here."""
    try:
        from creative_director.config import settings
        from creative_director.features.timeline import extract_timeline
        from creative_director.ingestion.pipeline import (
            extract_features_from_file,
            persist_features,
        )
        from creative_director.storage.db import session_scope
        from creative_director.storage.models import Video, VideoFeatures, VideoTimeline

        vid = job.video_id

        # 1. Thumbnail from the opening frame (so the header/player poster work).
        job.message = "reading your video…"
        thumb = settings.thumbnail_dir / f"{vid}.jpg"
        has_thumb = _first_frame_thumbnail(mp4, thumb)
        if has_thumb:
            with session_scope() as s:
                v = s.get(Video, vid)
                if v is not None:
                    v.thumbnail_path = str(thumb)

        # 2. Full feature extraction (transcript, hook, audio, visual).
        job.message = "analyzing — transcribing audio + reading frames (1-3 min)…"
        caption = None
        duration_s = None
        with session_scope() as s:
            v = s.get(Video, vid)
            if v is None:
                raise RuntimeError("video row vanished")
            caption = v.description
            duration_s = v.duration_seconds
            feats = extract_features_from_file(v, mp4, thumb if has_thumb else None)
            persist_features(s, vid, feats)

        # 2b. VLM rich-perception layer (grounded read + presenter gate). Opt-in
        # via ENABLE_VLM_PERCEPTION; defensive — a failure never fails the job.
        if settings.enable_vlm_perception:
            try:
                from creative_director.features.vlm_perception import (
                    extract_vlm_perception,
                )

                job.message = "reading the frames…"
                perception = extract_vlm_perception(
                    str(mp4),
                    niche=job.niche,
                    caption=caption,
                    duration_s=duration_s,
                )
                if perception is not None:
                    with session_scope() as s:
                        f = s.get(VideoFeatures, vid)
                        if f is not None:
                            f.vlm_perception = perception
                else:
                    logger.info(f"vlm perception skipped/empty for {vid}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"vlm perception failed for {vid}: {e}")

        # 3. Per-second timeline (cuts, vibes, faces, beats) for the strip + cut plan.
        job.message = "building the per-second timeline (1-2 min)…"
        timeline = extract_timeline(mp4, niche=job.niche)
        with session_scope() as s:
            for row in timeline:
                s.add(VideoTimeline(video_id=vid, **row))

        job.status = "done"
        job.message = "ready"
    except Exception as e:  # noqa: BLE001
        logger.exception("upload job failed")
        job.status = "error"
        job.error = str(e)


@router.post("/upload", response_model=UploadJobStatus)
async def upload_reel(
    request: Request,
    file: UploadFile = File(...),
    niche: str = Form(...),
    caption: str = Form(""),
    followers: Optional[int] = Form(None),
) -> UploadJobStatus:
    """Accept a reel upload and start the analysis job.

    ``caption`` feeds the title/description features (emoji count, hashtags…)
    so paste the real caption for a truer read. ``followers`` (optional) sets
    the creator tier so the comparison set is size-appropriate.
    """
    if niche not in ALLOWED_NICHES:
        raise HTTPException(422, f"niche must be one of {sorted(ALLOWED_NICHES)}")

    ip = _client_ip(request)
    if _rate_limited(ip):
        raise HTTPException(429, "Daily upload limit reached — try again tomorrow.")

    from creative_director.advice.categories import classify
    from creative_director.config import settings
    from creative_director.storage.db import session_scope
    from creative_director.storage.models import Channel, Video

    uid = uuid.uuid4().hex[:12]
    video_id = f"up_{uid}"
    archive = settings.video_archive_dir or Path("data/videos")
    archive.mkdir(parents=True, exist_ok=True)
    mp4 = archive / f"{video_id}.mp4"

    # Stream the upload to disk with a hard size cap.
    size = 0
    try:
        with mp4.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "File too large (max 200 MB).")
                out.write(chunk)
    except HTTPException:
        mp4.unlink(missing_ok=True)
        raise
    if size == 0:
        mp4.unlink(missing_ok=True)
        raise HTTPException(422, "Empty upload.")

    duration = _probe_duration(mp4)
    if duration is None:
        mp4.unlink(missing_ok=True)
        raise HTTPException(422, "Could not read that file as a video — upload an mp4.")
    if duration > MAX_DURATION_S:
        mp4.unlink(missing_ok=True)
        raise HTTPException(422, f"Video is {duration:.0f}s — max {MAX_DURATION_S}s (short-form only).")

    caption = (caption or "").strip()
    title = caption.splitlines()[0][:120] if caption else (file.filename or "Uploaded reel")
    guess, _ranked = classify(caption, niche)

    with session_scope() as s:
        s.add(
            Channel(
                id=f"upch_{uid}",
                title="Your upload",
                niche=niche,
                subscriber_count=followers,
            )
        )
        s.add(
            Video(
                id=video_id,
                channel_id=f"upch_{uid}",
                title=title,
                description=caption or None,
                duration_seconds=int(duration),
                is_short=True,
                published_at=datetime.utcnow(),
                video_file_path=str(mp4),
                category=guess,
                category_confirmed=0,
            )
        )

    _UPLOADS_BY_IP.setdefault(ip, []).append(time.time())
    job = _Job(id=uuid.uuid4().hex[:12], video_id=video_id, niche=niche)
    _JOBS[job.id] = job
    threading.Thread(target=_run_job, args=(job, mp4), daemon=True).start()
    logger.info(f"upload job {job.id} started ({video_id}, niche={niche}, {size/1e6:.1f}MB, {duration:.0f}s)")
    return _status(job)


@router.get("/upload/{job_id}", response_model=UploadJobStatus)
def upload_status(job_id: str) -> UploadJobStatus:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job id (it may have expired on a restart).")
    return _status(job)
