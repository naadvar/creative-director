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

from sqlalchemy import select
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
# "other" = an honest catch-all for reels outside the four corpus niches: the read
# runs on the frames as normal, but nothing niche-keyed (corpus comparison, DNA
# "you're a X creator", population stats) is asserted for it.
ALLOWED_NICHES = {"ig_fitness", "ig_food", "ig_travel", "ig_fashion", "other"}

MAX_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_DURATION_S = 180  # 3 minutes — short-form only
UPLOADS_PER_DAY = 10  # per client IP
# Deduped re-uploads don't consume the read quota (they cost no LLM call), but the
# path still streams the file and writes an Event row, so it gets its own generous
# ceiling against scripted replay of one file at wire speed.
DEDUPES_PER_DAY = 100  # per client IP
JOB_TTL_S = 6 * 3600  # _JOBS entries outlive any real poll (client gives up at 9 min)
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
    idea_id: Optional[str] = None  # set when this upload shoots a generated DNA idea
    transcoded: bool = False  # set when _ensure_decodable had to re-encode (HEVC etc.)
    file_hash: Optional[str] = None  # sha256 of the ORIGINAL uploaded bytes (pre-transcode)


_JOBS: dict[str, _Job] = {}
_UPLOADS_BY_IP: dict[str, list[float]] = {}
_DEDUPES_BY_IP: dict[str, list[float]] = {}


def _evict_stale_jobs() -> None:
    """Drop finished/abandoned job records so the module-global dict can't grow
    without bound across a long-lived process (pre-existing leak; the cheap
    dedupe path made it cheaply reachable)."""
    cutoff = time.time() - JOB_TTL_S
    for jid in [j for j, job in _JOBS.items() if job.created < cutoff]:
        _JOBS.pop(jid, None)


def _dedupe_limited(ip: str) -> bool:
    now = time.time()
    window = [t for t in _DEDUPES_BY_IP.get(ip, []) if now - t < 86_400]
    _DEDUPES_BY_IP[ip] = window
    return len(window) >= DEDUPES_PER_DAY


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
            if container.streams.video:  # guard: audio-only files have no video[0]
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


def _source_rotation(mp4: Path) -> int:
    """Display rotation (0/90/180/270) the container declares, read via OpenCV's
    CAP_PROP_ORIENTATION_META — which comes from the container header, so it's
    decoder-independent and works for HEVC even where frame DECODE fails on the lean
    host. iPhone portrait video carries this; if we re-encode without baking it into
    the pixels the output plays sideways and the read reasons about a sideways clip.
    (Normal landscape H.264 uploads never reach the transcode — cv2 decodes them
    directly, auto-orienting via the same metadata — so rotation only matters here.)"""
    try:
        import cv2

        cap = cv2.VideoCapture(str(mp4))
        try:
            meta = cap.get(cv2.CAP_PROP_ORIENTATION_META) or 0
        finally:
            cap.release()
        return int(round(float(meta))) % 360
    except Exception:  # noqa: BLE001 — any failure -> treat as unrotated (no regression)
        return 0


def _transcode_h264(mp4: Path) -> None:
    """Transcode to H.264/yuv420p mp4 in place via PyAV (bundled FFmpeg — no system
    ffmpeg needed). Video is re-encoded (capped at 1280px, veryfast/crf23 so a 30s
    reel takes ~seconds on the small CPU); audio is stream-COPIED when present
    (iPhone .mov audio is AAC, mp4-compatible) so the transcript keeps its source.
    Container rotation is BAKED into the pixels (iPhone portrait is a landscape frame
    + a 90° display flag) so every downstream consumer — player, thumbnail, cv2 frame
    sampling — sees it upright."""
    import av
    import cv2

    rot = _source_rotation(mp4)
    # OpenCV-consistent mapping (matches the auto-orient that already handles H.264
    # uploads), so baking is consistent with the rest of the pipeline.
    cv_rot = {
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }.get(rot)
    swap = rot in (90, 270)

    tmp = mp4.with_name(mp4.stem + "_h264.mp4")
    try:
        with av.open(str(mp4)) as inp, av.open(str(tmp), mode="w") as out:
            if not inp.streams.video:  # audio-only upload: no frames to read
                raise ValueError(f"no video stream in {mp4.name}")
            vin = inp.streams.video[0]
            rate = vin.average_rate or 30
            w = vin.codec_context.width or 720
            h = vin.codec_context.height or 1280
            # Display dimensions AFTER rotation (swapped for 90/270), then scale-capped.
            dw, dh = (h, w) if swap else (w, h)
            scale = min(1.0, 1280 / max(dw, dh))
            vw, vh = max(2, (int(dw * scale) // 2) * 2), max(2, (int(dh * scale) // 2) * 2)
            vout = out.add_stream("libx264", rate=rate)
            vout.width, vout.height = vw, vh
            vout.pix_fmt = "yuv420p"
            vout.options = {"crf": "23", "preset": "veryfast"}
            ain = next(iter(inp.streams.audio), None)
            aout = None
            if ain is not None:
                try:
                    aout = out.add_stream(template=ain)  # packet copy, no re-encode
                except Exception:  # noqa: BLE001 — exotic audio codec: keep video, drop audio
                    logger.warning(f"transcode: audio stream copy unsupported for {mp4.name}; dropping audio")
            streams = [s for s in (vin, ain) if s is not None]
            for packet in inp.demux(streams):
                if packet.dts is None:
                    continue
                if packet.stream is vin:
                    for frame in packet.decode():
                        if cv_rot is not None:
                            # rotate pixels (bgr ndarray) then resize to the target
                            arr = cv2.rotate(frame.to_ndarray(format="bgr24"), cv_rot)
                            if (arr.shape[1], arr.shape[0]) != (vw, vh):
                                arr = cv2.resize(arr, (vw, vh))
                            nf = av.VideoFrame.from_ndarray(arr, format="bgr24").reformat(format="yuv420p")
                            for p in vout.encode(nf):
                                out.mux(p)
                        else:
                            f2 = frame.reformat(width=vw, height=vh, format="yuv420p")
                            for p in vout.encode(f2):
                                out.mux(p)
                elif aout is not None and packet.stream is ain:
                    packet.stream = aout
                    out.mux(packet)
            for p in vout.encode():  # flush the encoder
                out.mux(p)
        tmp.replace(mp4)
    finally:
        # On success replace() consumed tmp; on any exception it must not leak onto
        # the persistent volume.
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _ensure_decodable(mp4: Path, job: _Job) -> None:
    """iPhones record .mov in HEVC by default — including the in-app camera — and
    the lean host's OpenCV can't decode HEVC. Everything downstream (thumbnail,
    frame sampling for the read, browser playback) assumes a cv2-decodable file,
    so if cv2 can't read a first frame, transcode ONCE to H.264 and replace the
    stored file. No-op for normal H.264 uploads. Raises on a failed transcode
    (the job can't produce a read from an undecodable file anyway)."""
    try:
        import cv2

        cap = cv2.VideoCapture(str(mp4))
        try:
            ok, _ = cap.read()
        finally:
            cap.release()
        if ok:
            return
    except Exception as e:  # noqa: BLE001 — cv2 itself failing -> still try the transcode
        logger.warning(f"cv2 decode check failed for {mp4.name}: {type(e).__name__}")
    job.message = "converting your video…"
    job.transcoded = True
    logger.info(f"{mp4.name}: not cv2-decodable (likely HEVC .mov) — transcoding to H.264")
    _transcode_h264(mp4)


def _find_existing_read(user_id: int, file_hash: str, niche: str, caption: str) -> Optional[str]:
    """Same-file memoization: the newest of the creator's OWN uploads with the same
    content hash AND the same read inputs (niche, caption) whose stored read is
    grounded and was produced by the CURRENT read engine. A byte-identical re-upload
    is answered with that read — same reel, same answer, instantly — instead of a
    fresh roll of the non-deterministic pipeline (temp-0 runs on identical frames
    still differ, so re-uploads were visibly flaky). Only SUCCESS is memoized:
    suppressed (grounded=False) and ungated (grounded=None) reads never match, so
    the suppression retry keeps its fresh rolls; deleted uploads have no row and
    engine upgrades (READ_ENGINE_VERSION bump) retire every cached read at once."""
    from creative_director.advice.craft_xray import READ_ENGINE_VERSION
    from creative_director.storage.db import session_scope
    from creative_director.storage.models import Upload

    with session_scope() as s:
        rows = s.execute(
            select(Upload.video_id, Upload.caption, Upload.craft_read)
            .where(Upload.user_id == user_id, Upload.file_hash == file_hash)
            .order_by(Upload.created_at.desc())
            .limit(20)
        ).all()
    for vid, prev_caption, read in rows:
        if not isinstance(read, dict) or read.get("grounded") is not True:
            continue
        if read.get("engine_version") != READ_ENGINE_VERSION:
            continue
        # niche + caption both shape the read (niche-as-hint prompts, caption notes,
        # caption-as-remedy) — any changed input deserves a fresh read. The niche is
        # compared against the read's GENERATION-time stamp, not Upload.niche, which
        # the mismatch-chip PATCH rewrites in place without regenerating the read.
        if read.get("engine_niche") != niche or (prev_caption or "").strip() != caption:
            continue
        return vid
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

        # 0. Normalize the container/codec: iPhone .mov (HEVC) — incl. in-app camera
        # recordings — must become H.264 before anything downstream touches it.
        job.message = "reading your video…"
        _ensure_decodable(mp4, job)

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

            # Niche consistency: the selected niche drives the DNA wording + corpus
            # comparisons, so a mispick makes personalized claims quietly wrong. A
            # conservative keyword check over what the read actually SAW stamps
            # suspected_niche — the read page then offers a one-tap switch. Never
            # silent, never blocking (best-effort).
            if read is not None and read.get("grounded") is not False:
                try:
                    from creative_director.advice.niche_guess import guess_mismatched_niche

                    sus = guess_mismatched_niche(
                        job.niche,
                        read.get("what_it_is"), read.get("verdict"), caption, transcript,
                    )
                    if sus:
                        read["suspected_niche"] = sus
                        logger.info(
                            f"niche mismatch suspected for {vid}: selected={job.niche} looks like {sus}"
                        )
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"niche check failed for {vid}: {type(e).__name__}: {e}")

            # Caption-as-remedy (v1.2): when the read itself implicates the caption,
            # attach ONE voice-matched suggestion (their past captions = the voice
            # reference). Honest absence on any failure. Best-effort.
            if read is not None and read.get("grounded") is not False:
                try:
                    from creative_director.advice.captions import (
                        caption_implicated,
                        suggest_caption,
                    )

                    # Two remedy cases: the read flagged the caption, or none was
                    # provided at all (the purest deficiency). A fine caption is
                    # never rewritten (suggest_caption re-checks this too).
                    if caption_implicated(read) or not (caption or "").strip():
                        with session_scope() as s:
                            v = s.get(Video, vid)
                            owner = v.uploaded_by_user_id if v is not None else None
                            past = []
                            if owner:
                                past = [
                                    c
                                    for (c,) in s.execute(
                                        select(Upload.caption)
                                        .where(
                                            Upload.user_id == owner,
                                            Upload.caption.isnot(None),
                                            Upload.caption != "",
                                            Upload.video_id != vid,
                                        )
                                        .order_by(Upload.created_at.desc())
                                        .limit(5)
                                    ).all()
                                ]
                        job.message = "drafting your caption…"
                        sug = suggest_caption(
                            read,
                            transcript=transcript,
                            current_caption=caption,
                            past_captions=past,
                        )
                        if sug:
                            read["caption_suggestion"] = sug
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"caption suggestion failed for {vid}: {type(e).__name__}")

            if read is not None:
                # Stamp the engine + the niche the read was actually GENERATED under —
                # the same-file memoization only reuses current-engine reads whose
                # generation inputs match. engine_niche is deliberately separate from
                # Upload.niche: the mismatch-chip PATCH rewrites Upload.niche in place
                # on an existing read, and that switched read must never be served as
                # a fresh same-inputs hit for the new niche.
                from creative_director.advice.craft_xray import READ_ENGINE_VERSION

                read["engine_version"] = READ_ENGINE_VERSION
                read["engine_niche"] = job.niche
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
                    # If the prior reel was deleted, its frames are gone — don't feed
                    # a stale path to the two-version verifier (it would sample a
                    # nonexistent file). Null it so the verifier returns None and the
                    # verdict is an honest "cant_verify", not a fabricated compare.
                    if prior_mp4 and not Path(prior_mp4).exists():
                        prior_mp4 = None
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
                    up.idea_id = job.idea_id
                    up.file_hash = job.file_hash
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

        # 6. Telemetry — the launch-KPI signal (grounded/suppressed/revision funnel).
        try:
            from creative_director.storage.telemetry import log_event

            with session_scope() as s:
                up = s.get(Upload, vid)
            read = up.craft_read if (up is not None and isinstance(up.craft_read, dict)) else None
            log_event(
                "read_completed",
                user_id=up.user_id if up is not None else None,
                video_id=vid,
                niche=job.niche,
                grounded=bool(read) and read.get("grounded") is not False,
                suppressed=bool(read) and read.get("grounded") is False,
                # gated=False means perception failed so the fact-check gate never
                # ran — the silent-degradation mode that hid for 4 days in July.
                gated=bool(read) and read.get("grounded") is not None,
                no_read=read is None,
                transcoded=job.transcoded or None,
                revision_state=(revision_verdict or {}).get("state"),
                idea_linked=bool(job.idea_id) or None,
            )
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        logger.exception("upload job failed")
        job.status = "error"
        job.error = str(e)
        try:
            from creative_director.storage.telemetry import log_event

            log_event("read_failed", video_id=job.video_id, error=type(e).__name__)
        except Exception:  # noqa: BLE001
            pass


@router.post("/upload", response_model=UploadJobStatus)
async def upload_reel(
    request: Request,
    file: UploadFile = File(...),
    niche: str = Form(...),
    caption: str = Form(""),
    followers: Optional[int] = Form(None),
    prior_video_id: Optional[str] = Form(None),  # set when re-checking a prior reel's fix
    idea_id: Optional[str] = Form(None),  # set when shooting a generated DNA idea
    force_fresh: Optional[str] = Form(None),  # owner-only: skip same-file memoization
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
    # Fresh reads and deduped replays have separate windows (a dedupe costs no LLM
    # call so it doesn't consume the read quota), but BOTH gate before the body is
    # streamed — an over-cap client shouldn't cost 200 MB of write I/O per retry.
    if _rate_limited(ip) or _dedupe_limited(ip):
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

    # Stream the upload to disk with a hard size cap, hashing as it flows (the
    # hash keys the same-file memoization below).
    import hashlib

    size = 0
    hasher = hashlib.sha256()
    try:
        with mp4.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "File too large (max 200 MB).")
                hasher.update(chunk)
                out.write(chunk)
    except HTTPException:
        mp4.unlink(missing_ok=True)
        raise
    if size == 0:
        mp4.unlink(missing_ok=True)
        raise HTTPException(422, "Empty upload.")
    file_hash = hasher.hexdigest()

    caption = (caption or "").strip()
    # Only honor links that look like our own ids (sanity, not auth — the ownership
    # check happens in _run_job against the new upload's user). Validated BEFORE the
    # memoization gate so junk values can't skip it.
    prior = prior_video_id if (prior_video_id or "").startswith("up_") else None
    idea = idea_id if (idea_id or "").startswith("cdi_") else None

    # SAME-FILE MEMOIZATION — a byte-identical re-upload with identical inputs gets
    # the read the creator already has (a coach gives the same answer to the same
    # video), instead of a fresh non-deterministic roll. Skipped for explicit
    # re-checks (prior — the revision verifier must run) and idea shoots (idea —
    # the flywheel link must be recorded). force_fresh is an owner-only escape
    # hatch for testing, honored only with the tools key. The whole block is
    # best-effort: any failure inside it degrades to a normal fresh upload.
    if not prior and not idea:
        existing = None
        try:
            from api.config import api_settings

            forced = bool(force_fresh) and bool(api_settings.tools_key) and (
                request.headers.get("x-tools-key") == api_settings.tools_key
            )
            if not forced:
                existing = _find_existing_read(user["id"], file_hash, niche, caption)
        except Exception as e:  # noqa: BLE001 — memoization must never block an upload
            logger.warning(f"dedupe lookup failed: {type(e).__name__}: {e}")
            existing = None
        if existing:
            mp4.unlink(missing_ok=True)  # keep the original upload's stored copy
            _DEDUPES_BY_IP.setdefault(ip, []).append(time.time())
            _evict_stale_jobs()
            job = _Job(
                id=uuid.uuid4().hex[:12], video_id=existing, niche=niche,
                status="done", message="You've already read this reel. Taking you to your read.",
            )
            _JOBS[job.id] = job
            from creative_director.storage.telemetry import log_event

            log_event("read_deduped", user_id=user["id"], video_id=existing, niche=niche)
            logger.info(f"upload deduped to {existing} (same file+inputs, user {user['id']})")
            return _status(job)

    try:
        duration = _probe_duration(mp4)
        if duration is None:
            raise HTTPException(422, "Couldn't read that file as a video — try an mp4 or mov.")
        if duration > MAX_DURATION_S:
            raise HTTPException(
                422, f"Video is {duration:.0f}s — max {MAX_DURATION_S}s (short-form only)."
            )
    except Exception:
        # Any pre-job failure (expected or not) must not orphan the streamed mp4
        # on the persistent volume.
        mp4.unlink(missing_ok=True)
        raise

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
    _evict_stale_jobs()
    job = _Job(
        id=uuid.uuid4().hex[:12], video_id=video_id, niche=niche,
        prior_video_id=prior, idea_id=idea, file_hash=file_hash,
    )

    from creative_director.storage.telemetry import log_event

    log_event(
        "upload_started", user_id=user["id"], video_id=video_id, niche=niche,
        revision=bool(prior) or None, idea=bool(idea) or None,
        size_mb=round(size / 1e6, 1),
    )
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
