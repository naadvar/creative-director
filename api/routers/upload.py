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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from loguru import logger
from pydantic import BaseModel

from api.auth import get_current_user

router = APIRouter(tags=["upload"])

# The niches with extracted benchmark corpora. Uploads must map to one so the
# winner comparisons / vibe prompts / cohort wording all resolve.
ALLOWED_NICHES = {"ig_fitness", "ig_food", "ig_travel", "ig_fashion"}

MAX_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_DURATION_S = 180  # 3 minutes — short-form only
UPLOADS_PER_DAY = 10  # per client IP
# The read pipeline is non-deterministic; a noisy single sample can falsely trip the
# grounding gate. Regenerate a suppressed read up to this many times, keeping the first
# grounded one (genuinely un-groundable reels suppress on every attempt).
MAX_READ_ATTEMPTS = 2


@dataclass
class _Job:
    id: str
    video_id: str
    niche: str
    status: str = "running"  # running | done | error
    message: str = "queued…"
    error: Optional[str] = None
    created: float = field(default_factory=time.time)
    prior_video_id: Optional[str] = None  # set when this upload re-checks a prior reel's fix


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
    """Container duration in seconds (None if unreadable). PyAV when available (accurate),
    else OpenCV — which is always present on the lean serve host (PyAV is not)."""
    try:
        import av

        with av.open(str(path)) as container:
            if container.duration is not None:
                return float(container.duration) / av.time_base
            vs = container.streams.video[0]
            if vs.duration is not None and vs.time_base is not None:
                return float(vs.duration * vs.time_base)
    except Exception as e:  # noqa: BLE001 — av is absent on lean hosts; fall back to OpenCV
        logger.warning(f"PyAV duration probe unavailable for {path} ({type(e).__name__}); trying OpenCV")
    try:
        import cv2

        cap = cv2.VideoCapture(str(path))
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if fps > 0 and frames > 0:
                return float(frames) / float(fps)
        finally:
            cap.release()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"OpenCV duration probe failed for {path}: {e}")
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
        from creative_director.storage.models import Upload, Video, VideoFeatures, VideoTimeline

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
            try:
                feats = extract_features_from_file(v, mp4, thumb if has_thumb else None)
                persist_features(s, vid, feats)
            except Exception as e:  # noqa: BLE001 — the heavy scalar stack can be absent on a lean serve host
                logger.warning(
                    f"feature extraction failed for {vid}, falling back to transcript only: "
                    f"{type(e).__name__}: {str(e)[:120]}"
                )
                from creative_director.features.audio import extract_transcript

                persist_features(s, vid, extract_transcript(mp4))

        # 2b+2c. Perception + craft read, WITH RETRY. The read pipeline is
        # non-deterministic, so a single noisy perception/read sample can trip the
        # grounding gate and falsely suppress a perfectly critique-able reel (creators
        # found that simply re-uploading the same reel often produced a read). So when a
        # read comes back suppressed, regenerate it — fresh perception + read — up to
        # MAX_READ_ATTEMPTS times and keep the first grounded one. A genuinely
        # un-groundable reel suppresses on every attempt, so this recovers false
        # suppressions without ever forcing a hallucinated read through the gate.
        # Defensive throughout — a read failure never fails the job (scorecard fallback).
        read = None
        perception = None
        try:
            from creative_director.advice.craft_xray import (
                extract_craft_read,
                ground_and_gate,
                synthesize_opportunity,
            )
            from creative_director.features.vlm_perception import extract_vlm_perception

            # Stable across attempts — read the transcript / thumb-text once.
            transcript = thumb_text = None
            with session_scope() as s:
                f = s.get(VideoFeatures, vid)
                transcript = getattr(f, "transcript", None) if f else None
                thumb_text = getattr(f, "thumb_text", None) if f else None

            for attempt in range(MAX_READ_ATTEMPTS):
                retry = attempt > 0
                # Independent perception pass — the gate's evidence.
                a_perception = None
                if settings.enable_vlm_perception:
                    try:
                        job.message = "re-reading the frames…" if retry else "reading the frames…"
                        a_perception = extract_vlm_perception(
                            str(mp4), niche=job.niche, caption=caption, duration_s=duration_s
                        )
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"vlm perception failed for {vid} (try {attempt + 1}): {e}")
                # The craft read itself.
                try:
                    job.message = (
                        "taking another pass at your read…" if retry else "writing your craft read…"
                    )
                    a_read = extract_craft_read(
                        str(mp4), niche=job.niche, caption=caption, duration_s=duration_s
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"craft read failed for {vid} (try {attempt + 1}): {e}")
                    a_read = None
                if a_read is None:
                    continue
                # Grounding gate — only fires with a perception pass to contrast against.
                if a_perception is not None:
                    try:
                        job.message = "fact-checking the read against your footage…"
                        a_read = ground_and_gate(a_read, a_perception, transcript, caption, thumb_text)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"grounding gate failed for {vid} (try {attempt + 1}): {e}")
                read, perception = a_read, a_perception
                if a_read.get("grounded") is not False:
                    break  # grounded — keep this one
                logger.info(
                    f"craft read suppressed for {vid} (try {attempt + 1}/{MAX_READ_ATTEMPTS}): "
                    f"{a_read.get('grounding_reason', '')[:120]}"
                )

            # Prioritized opportunity — promote the read's top blind_spot into the
            # headline lever (grounded by construction). Kept (grounded) reads only.
            if read is not None and read.get("grounded") is not False:
                try:
                    read = synthesize_opportunity(read, perception, transcript, caption, thumb_text)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"opportunity synthesis failed for {vid}: {e}")

            if read is not None:
                with session_scope() as s:
                    f = s.get(VideoFeatures, vid)
                    if f is not None:
                        if perception is not None:
                            f.vlm_perception = perception
                        f.craft_read = read
            else:
                logger.info(f"craft read skipped (no read produced) for {vid}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"craft read pipeline failed for {vid}: {type(e).__name__}: {e}")

        # 3. Per-second timeline (cuts, vibes, faces, beats) for the strip + cut plan.
        # Best-effort: the craft read is the product, so a timeline failure (its heavy
        # stack may be absent on a lean serve host) must never error a good read.
        job.message = "building the per-second timeline (1-2 min)…"
        try:
            timeline = extract_timeline(mp4, niche=job.niche)
            with session_scope() as s:
                for row in timeline:
                    s.add(VideoTimeline(video_id=vid, **row))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"timeline extraction skipped/failed for {vid}: {type(e).__name__}: {str(e)[:120]}"
            )

        # 3.5 REVISION VERDICT — only when this upload explicitly re-checks a prior reel
        # (the creator tapped "Re-check this fix"). A frames-only verifier judges whether the
        # prior issue was fixed in THESE new frames; it never sees the new read's text, so the
        # noisy read can't fabricate a "you fixed it". Self-contained (snapshots prior title)
        # + best-effort (a verdict failure never fails the job, never suppresses the read).
        revision_verdict = None
        if job.prior_video_id and read is not None and read.get("grounded") is not False:
            try:
                from creative_director.advice.craft_xray import (
                    _lever_timestamp,
                    compare_revision,
                    verify_fix_addressed,
                )

                with session_scope() as s:
                    prior = s.get(Upload, job.prior_video_id)
                    cur = s.get(Video, vid)
                    new_user = cur.uploaded_by_user_id if cur is not None else None
                    # Only re-check against the creator's OWN prior reel.
                    own = (
                        prior is not None
                        and prior.user_id is not None
                        and prior.user_id == new_user
                    )
                    prior_read = prior.craft_read if (own and isinstance(prior.craft_read, dict)) else None
                    prior_title = prior.title if own else None
                    prior_mp4 = prior.video_file_path if own else None
                # Only re-check when the prior read named a REAL issue — skip a clean
                # ("well-executed as is", opportunity_dimension == "none") prior read,
                # which has nothing to verify a fix against.
                if (
                    isinstance(prior_read, dict)
                    and prior_read.get("biggest_opportunity")
                    and prior_read.get("opportunity_dimension") != "none"
                ):
                    job.message = "checking whether your fix landed…"
                    verifier = verify_fix_addressed(
                        str(mp4),
                        prior_read.get("biggest_opportunity") or "",
                        _lever_timestamp(prior_read),
                        old_mp4=prior_mp4,  # compare OLD vs NEW — needed to ground a real change
                        niche=job.niche, caption=caption, duration_s=duration_s,
                    )
                    revision_verdict = compare_revision(prior_read, read, verifier)
                    revision_verdict["prior_video_id"] = job.prior_video_id
                    revision_verdict["prior_title"] = prior_title
                    revision_verdict["checked_at"] = datetime.utcnow().isoformat()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"revision verdict failed for {vid}: {type(e).__name__}: {e}")

        # 4. DURABLE record → userdata.db (separate writable store). Mirrors the
        # finished upload + its read so it survives corpus redeploys (which overwrite
        # the corpus videos/video_features rows). The mp4/thumbnail on the persistent
        # volume survive too; their paths are captured here.
        try:
            with session_scope() as s:
                v = s.get(Video, vid)
                f = s.get(VideoFeatures, vid)
                if v is not None:
                    up = s.get(Upload, vid) or Upload(video_id=vid)
                    up.user_id = v.uploaded_by_user_id
                    up.niche = job.niche
                    up.title = v.title
                    up.caption = v.description
                    up.duration_seconds = v.duration_seconds
                    up.craft_read = f.craft_read if f is not None else None
                    up.video_file_path = v.video_file_path
                    up.thumbnail_path = v.thumbnail_path
                    up.prior_video_id = job.prior_video_id
                    up.revision_verdict = revision_verdict
                    s.add(up)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"durable upload record failed for {vid}: {type(e).__name__}: {e}")

        # 5. Re-engagement nudge: email the read link. Inert without a provider key,
        # best-effort (a notification problem must never fail a finished upload).
        try:
            from creative_director.notify.email import send_read_ready
            from creative_director.storage.models import User

            with session_scope() as s:
                up = s.get(Upload, vid)
                read = up.craft_read if up is not None else None
                grounded = isinstance(read, dict) and read.get("grounded") is not False
                if up is not None and up.user_id and grounded:
                    user = s.get(User, up.user_id)
                    if user is not None and user.email:
                        send_read_ready(user.email, up.title or "your reel", vid)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"email nudge skipped for {vid}: {type(e).__name__}: {e}")

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
    prior_video_id: Optional[str] = Form(None),  # set when re-checking a prior reel's fix
    user: dict = Depends(get_current_user),
) -> UploadJobStatus:
    """Accept a reel upload and start the analysis job. Requires a session
    (the passwordless email gate) — uploading is the conversion point, so we
    capture the email before spending the extraction compute.

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
                uploaded_by_user_id=user["id"],  # link upload → creator for the fingerprint
            )
        )

    _UPLOADS_BY_IP.setdefault(ip, []).append(time.time())
    # Only honor a prior link that looks like our own upload id (sanity, not auth — the
    # ownership check happens in _run_job against the new upload's user).
    prior = prior_video_id if (prior_video_id or "").startswith("up_") else None
    job = _Job(id=uuid.uuid4().hex[:12], video_id=video_id, niche=niche, prior_video_id=prior)
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
