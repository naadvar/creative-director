"""Per-video analysis endpoints — the advice layer, one pipeline function per route.

All four reuse the cached corpus benchmarks, so each request is just one video's
DB lookup plus the comparison — no corpus-wide recompute. Benchmarks are
TIER-STRATIFIED: each route resolves the creator's follower-count tier and
picks a same-tier benchmark when the (tier, archetype) bucket is thick enough,
falling back to the pooled benchmark when it isn't.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel

from api import schemas
from api.auth import get_optional_user
from api.benchmarks import benchmarks, pick_for_tier
from creative_director.advice.benchmark import REPORTABLE, classify_archetype
from creative_director.advice.breakdown import analyze_video
from creative_director.advice.categories import (
    CATEGORIES,
    classify,
    dropdown_options,
    label_for,
)
from creative_director.advice.cutplan import (
    build_auto_cut,
    build_cut_plan,
    recompute_for_trim,
)
from creative_director.advice.examples import find_examples
from creative_director.advice.summary import build_summary
from creative_director.advice.tier import tier_for_video
from creative_director.advice.timeline_benchmark import (
    analyze_timeline,
    per_second_deviation,
    summarize_deviation,
)
from api.config import api_settings
from creative_director.config import settings
from creative_director.storage import media
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, NoteFeedback, Upload, Video, VideoFeatures

router = APIRouter(prefix="/videos", tags=["analysis"])


def _video_context(
    video_id: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (niche, creator_tier, archetype) for picking the right benchmark.

    Niche comes from the video's channel so a YT creator is compared against
    YT winners and an IG creator against IG winners. All three can be None if
    the video is unknown or has no features -- callers treat None niche/tier
    as 'use cache default / pooled'.
    """
    with session_scope() as s:
        video = s.get(Video, video_id)
        if video is None:
            return None, None, None
        niche = video.channel.niche if video.channel else None
        tier = tier_for_video(s, video_id)
        archetype = (
            classify_archetype(video.features.transcript_word_count)
            if video.features
            else None
        )
        return niche, tier, archetype


@router.get("/{video_id}/analyze", response_model=schemas.VideoBreakdown)
def analyze(video_id: str) -> schemas.VideoBreakdown:
    """Aggregate, archetype-aware breakdown of one video vs winning Shorts.

    Uses the full tier map for the video's niche; analyze_video picks the
    right tier benchmark and records both the creator's tier and which scope
    ('tier' vs 'pooled') was used, so the UI can label the comparison honestly.
    """
    niche, _tier, _arch = _video_context(video_id)
    try:
        breakdown = analyze_video(
            video_id, benchmarks_by_tier=benchmarks.aggregate(niche)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return schemas.VideoBreakdown.model_validate(breakdown)


def _watch_winners(breakdown, niche, tier, archetype, video_id):
    """Block 4: up to 3 winning reels for the creator to WATCH — exemplifying
    their top actionable gap, or representative cohort winners when there's no
    clear gap (already a top performer / on-benchmark). Returns (examples, label)."""
    if niche is None:
        return [], None
    # Don't frame winners as a "gap to fix" for a proven top-tercile performer —
    # the read doesn't lecture them, so show representative peers instead.
    top = None
    if breakdown.tercile != 2:
        cands = sorted(
            [
                f for f in breakdown.findings
                if getattr(f, "off_benchmark", False)
                and getattr(f, "fixability", None) != "low"
                and getattr(f, "causal", None) != "likely-proxy"
                and getattr(f, "benchmark_value", None) is not None
                and getattr(f, "rank_score", 0.0) >= 0.1  # same bar as worth_trying
                and f.feature in REPORTABLE
            ],
            key=lambda f: -getattr(f, "rank_score", 0.0),
        )
        top = cands[0] if cands else None
    # Honest label: descriptive, never "winners that nail <feature>" — we proved
    # no observable craft feature predicts winning, so don't imply one does. We
    # still SELECT winners near the top gap (or duration) for relevance.
    _NW = {"ig_fitness": "fitness", "ig_food": "food", "ig_travel": "travel", "ig_fashion": "fashion"}
    nw = _NW.get(niche)
    label = f"Top {nw} performers your size — watch how they open" if nw else "Top performers your size"
    if top is not None:
        feature, bench_val = top.feature, float(top.benchmark_value)
    else:
        feature, bench_val = "duration_seconds", None
    with session_scope() as s:
        video = s.get(Video, video_id)
        category = video.category if video else None
        if bench_val is None:
            bm, _ = pick_for_tier(benchmarks.aggregate(niche), tier, archetype)
            prof = (
                (bm.get("archetypes", {}).get(archetype, {}) if archetype else {})
                .get("profile", {})
                .get(feature)
            )
            if not prof:
                return [], None
            bench_val = float(prof["high_median"])
        results = find_examples(
            s,
            label_scheme=api_settings.label_scheme,
            niche=niche,
            feature=feature,
            benchmark_value=bench_val,
            tier=tier,
            archetype=archetype,
            category=category,
            n=3,
            exclude_video_id=video_id,
        )
    return results, (label if results else None)


@router.get("/{video_id}/summary", response_model=schemas.PlainSummary)
def summary(video_id: str) -> schemas.PlainSummary:
    """Plain-English 'creative-director read' — drives the WHOOP-style scorecard."""
    niche, tier, archetype = _video_context(video_id)
    try:
        breakdown = analyze_video(
            video_id, benchmarks_by_tier=benchmarks.aggregate(niche)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    timeline_bm, _ = pick_for_tier(benchmarks.timeline(niche), tier, archetype)
    plain = build_summary(breakdown, timeline_bm, niche)
    resp = schemas.PlainSummary.model_validate(plain)
    # Block 4: winning reels to watch (best-effort — never break the core read).
    try:
        winners, label = _watch_winners(breakdown, niche, tier, archetype, video_id)
        resp.watch_winners = [schemas.ExampleVideo.model_validate(e) for e in winners]
        resp.watch_winners_label = label
    except Exception:  # noqa: BLE001
        pass
    return resp


def _my_note_feedback(video_id: str, user_id: int, read: dict) -> dict:
    """The signed-in creator's own feedback on THIS read: which notes they dismissed
    ('not useful' / 'not in my reel') and whether they rated the headline lever. Lets
    the UI restore those dismissals across reloads/devices instead of losing them the
    moment the optimistic local state is gone. Notes are stored verbatim (truncated at
    2000 chars), so an exact-text match reidentifies the dismissed spot on the client."""
    lever = read.get("biggest_opportunity") if isinstance(read, dict) else None
    with session_scope() as s:
        rows = [
            (r.note, r.reason)
            for r in (
                s.query(NoteFeedback)
                .filter(
                    (NoteFeedback.video_id == video_id)
                    & (NoteFeedback.user_id == user_id)
                )
                .order_by(NoteFeedback.created_at.asc())
                .all()
            )
        ]
    dismissed = [note for note, reason in rows if reason in ("not_useful", "not_in_reel")]
    lever_fb = None
    if lever:
        # Most-recent feedback row whose note is the headline lever (rows are asc,
        # so the last match wins) → the 👍/👎 on "Fix this first".
        for note, reason in rows:
            if note == lever and reason in ("helpful", "not_useful"):
                lever_fb = reason
    return {"dismissed": dismissed, "lever": lever_fb}


@router.get("/{video_id}/craft-read")
def craft_read(video_id: str, request: Request) -> dict:
    """The Craft X-ray — the grounded craft critic read (advice/craft_xray.py).
    Served from cache (VideoFeatures.craft_read); returns {available: false} when it
    hasn't been generated yet, so the frontend can show the card only when present.
    Carries lightweight video meta (title/duration/channel) so the read page needs
    only this one call — the old scalar breakdown is no longer on the page.
    Uploads are served from the durable userdata Upload row (survives corpus
    redeploys); corpus videos from VideoFeatures."""
    revision_verdict = None
    with session_scope() as s:
        up = s.get(Upload, video_id)
        if up is not None:
            read = up.craft_read
            revision_verdict = up.revision_verdict  # "did my fix land?" — None unless a re-check
            meta = {
                "video_id": video_id,
                "title": up.title or "Your reel",
                "channel": "Your upload",
                "duration_seconds": up.duration_seconds,
                "is_upload": True,
                "niche": up.niche,  # so the mismatch chip can say "fitness vs food"
            }
        else:
            f = s.query(VideoFeatures).filter(VideoFeatures.video_id == video_id).first()
            read = getattr(f, "craft_read", None) if f else None
            v = s.get(Video, video_id)
            meta = None
            if v is not None:
                ch = s.get(Channel, v.channel_id) if v.channel_id else None
                meta = {
                    "video_id": v.id,
                    "title": v.title or "Reel",
                    "channel": (ch.title if ch and ch.title else None),
                    "duration_seconds": v.duration_seconds,
                    "is_upload": bool(v.channel_id and v.channel_id.startswith("upch_")),
                }
    user = get_optional_user(request)
    # Telemetry: a read page was actually opened (uploads = the retention signal;
    # corpus views = Examples browsing). Anonymous-safe.
    try:
        from creative_director.storage.telemetry import log_event

        log_event(
            "read_viewed",
            user_id=user["id"] if user else None,
            video_id=video_id,
            is_upload=bool(meta and meta.get("is_upload")) or None,
        )
    except Exception:  # noqa: BLE001
        pass

    if not read:
        return {"available": False, "meta": meta, "revision_verdict": revision_verdict}
    # The grounding gate stamps grounded=false on a materially-fabricated read.
    # We'd rather say nothing than serve a hallucinated critique of the creator's
    # own footage — so a suppressed read is reported as not-available.
    if isinstance(read, dict) and read.get("grounded") is False:
        # Suppressed: we won't assert the (ungrounded) critique, but the positive
        # observations (done_well) are low-risk encouragement — surface them so the
        # creator isn't left with a dead-end instead of nothing.
        strengths = [s for s in (read.get("done_well") or []) if isinstance(s, str)][:3]
        return {
            "available": False,
            "suppressed": True,
            "strengths": strengths,
            "meta": meta,
            "revision_verdict": revision_verdict,
        }
    out = {
        "available": True,
        "read": _dedupe_promoted_spot(read),
        "meta": meta,
        "revision_verdict": revision_verdict,
    }
    # Signed-in only: the creator's own dismissals/lever rating, so the UI restores
    # them across reloads. Cheap (one indexed query); omitted for anonymous viewers.
    if user is not None and isinstance(read, dict):
        out["my_feedback"] = _my_note_feedback(video_id, user["id"], read)
    return out


def _dedupe_promoted_spot(read: dict) -> dict:
    """The lever (FIX THIS FIRST) is synthesized FROM the read's top blind spot —
    grounded by construction — but the promoted spot then repeats verbatim-ish in
    "Worth a second look". Serve the spot list with the promoted one removed:
    best token-overlap match, with a lower bar when the timestamps agree. Works on
    a COPY (never mutate the stored read) and drops at most one spot."""
    if not isinstance(read, dict):
        return read
    opp = str(read.get("biggest_opportunity") or "")
    spots = read.get("blind_spots") or []
    if not opp or not spots:
        return read
    import re as _re

    def toks(s: str) -> set:
        return {w for w in _re.findall(r"[a-z']+", s.lower()) if len(w) > 3}

    ot = toks(opp)
    if not ot:
        return read
    # search, not match: levers often bury the timestamp mid-sentence
    # ("Increase the font size ... — at 0:02, the text is too small").
    m = _re.search(r"(\d{1,2}:\d{2})", opp)
    lever_ts = str(read.get("lever_timestamp") or "") or (m.group(1) if m else "")
    best_i, best_j = None, 0.0
    for i, s in enumerate(spots):
        st = toks(str(s))
        if not st:
            continue
        j = len(ot & st) / max(1, len(ot | st))
        ts_m = _re.match(r"\s*(\d{1,2}:\d{2})", str(s))
        same_ts = bool(lever_ts and ts_m and ts_m.group(1) == lever_ts)
        if ((same_ts and j >= 0.25) or j >= 0.45) and j > best_j:
            best_i, best_j = i, j
    if best_i is None:
        return read
    out = dict(read)
    out["blind_spots"] = [s for i, s in enumerate(spots) if i != best_i]
    return out


class NoteFeedbackBody(BaseModel):
    note: str
    reason: Optional[str] = None  # "not_useful" | "not_in_reel"


@router.post("/{video_id}/note-feedback")
def note_feedback(video_id: str, body: NoteFeedbackBody, request: Request) -> dict:
    """One-tap dismissal of a craft-read note. Records it for trust (the creator
    overrides a note they disagree with) + as labeled training data. Captures the
    user when signed in; works anonymously otherwise."""
    user = get_optional_user(request)
    with session_scope() as s:
        s.add(NoteFeedback(
            video_id=video_id,
            user_id=user["id"] if user else None,
            note=(body.note or "")[:2000],
            reason=(body.reason or "dismissed")[:32],
        ))
    return {"ok": True}


@router.get("/{video_id}/frame", response_model=schemas.FrameBreakdown)
def frame(video_id: str) -> schemas.FrameBreakdown:
    """Hook + pacing breakdown derived from the per-second timeline."""
    niche, tier, archetype = _video_context(video_id)
    bm, _ = pick_for_tier(benchmarks.timeline(niche), tier, archetype)
    try:
        fb = analyze_timeline(video_id, benchmark=bm)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return schemas.FrameBreakdown.model_validate(fb)


@router.get("/{video_id}/file")
def video_file(video_id: str) -> Response:
    """Stream the archived mp4 for in-browser playback.

    Resolves the file by ``{video_archive_dir}/{video_id}.mp4`` convention so
    it works across YouTube IDs and Apify-ingested ``ig_*`` IDs. Starlette's
    FileResponse supports HTTP Range requests, so the HTML5 video element can
    seek (scrub) without re-downloading from the start.
    """
    with session_scope() as s:
        video = s.get(Video, video_id)
        # Uploads live in the durable userdata store; the corpus Video row may be
        # gone after a redeploy, but the mp4 persists on the volume.
        up = s.get(Upload, video_id) if video is None else None
        if video is None and up is None:
            raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
        up_path = up.video_file_path if up is not None else None

    # Serve the local file when present (dev + uploads on the volume); otherwise
    # fall back to the R2 corpus (prod / ingest box where local copies are pruned).
    archive = settings.video_archive_dir or Path("data/videos")
    path = archive / f"{video_id}.mp4"
    if not path.exists() and up_path:
        cand = Path(up_path)
        if cand.exists():
            path = cand
    if path.exists():
        return FileResponse(path, media_type="video/mp4", filename=path.name)
    if settings.r2_enabled:
        return RedirectResponse(media.video_url(video_id))
    raise HTTPException(
        status_code=404,
        detail=f"no mp4 archived for {video_id} (run feature extraction or ingest)",
    )


def _resolve_local_mp4(video_id: str) -> Optional[Path]:
    """The on-disk mp4 for a video, or None. Same resolution as /file (archive-dir
    convention first, then the upload's stored path), but LOCAL ONLY — never the R2
    redirect, since frame extraction needs bytes in hand (cv2 can't seek a redirect)."""
    with session_scope() as s:
        video = s.get(Video, video_id)
        up = s.get(Upload, video_id) if video is None else None
        if video is None and up is None:
            return None
        up_path = up.video_file_path if up is not None else None
    archive = settings.video_archive_dir or Path("data/videos")
    path = archive / f"{video_id}.mp4"
    if not path.exists() and up_path:
        cand = Path(up_path)
        if cand.exists():
            path = cand
    return path if path.exists() else None


@router.get("/{video_id}/frame-at")
def frame_at(video_id: str, t: float = Query(0.0, ge=0.0)) -> Response:
    """A single downscaled JPEG frame at ``t`` seconds — the "frame receipt" that
    lets a craft note show the exact moment it's about. Local mp4 only (uploads +
    corpus copies on the volume); cv2 seeks by msec, so no whole-file decode. 404
    when the file or that frame isn't available, so a corpus read with no local copy
    degrades gracefully (the client hides the thumbnail). Cached a day at the edge."""
    path = _resolve_local_mp4(video_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no mp4 archived for {video_id}")

    import cv2  # host-provided; kept local so the import cost is per-request, not per-boot

    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise HTTPException(status_code=404, detail="could not open video")
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        # Clamp t into [0, duration]; a note past the end lands on the last frame
        # instead of failing. Fall back to a fixed cap when metadata is missing.
        duration = (n_frames / fps) if fps > 0 and n_frames > 0 else None
        ts = max(0.0, float(t))
        if duration is not None:
            ts = min(ts, max(0.0, duration - 0.05))
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000.0)
        read_ok, frame = cap.read()
        if not read_ok or frame is None:
            raise HTTPException(status_code=404, detail="no frame at that time")
        # Downscale to <=480px on the long side (receipts are small thumbnails).
        h, w = frame.shape[:2]
        long_side = max(h, w)
        if long_side > 480:
            scale = 480.0 / long_side
            frame = cv2.resize(
                frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA,
            )
        enc_ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not enc_ok:
            raise HTTPException(status_code=404, detail="could not encode frame")
    finally:
        cap.release()
    return Response(
        content=buf.tobytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{video_id}/thumbnail")
def video_thumbnail(video_id: str) -> Response:
    """Serve the cached thumbnail jpg for any video (YT or IG).

    For IG reels the original IG CDN URL has expiring tokens, and YouTube's
    `i.ytimg.com/vi/{id}/hqdefault.jpg` returns a generic gray placeholder
    (not a 404) for non-YouTube IDs, so the browser thinks the image loaded.
    Both paths need a local source. Serve the locally cached file when present;
    otherwise fall back to the R2 corpus.
    """
    with session_scope() as s:
        video = s.get(Video, video_id)
        if video is not None:
            path_str = video.thumbnail_path
        else:
            up = s.get(Upload, video_id)  # durable upload record
            if up is None:
                raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
            path_str = up.thumbnail_path

    if path_str:
        path = Path(path_str)
        if not path.is_absolute():
            # Stored relative to project root; resolve against CWD where uvicorn runs.
            path = Path.cwd() / path
        if path.exists():
            return FileResponse(path, media_type="image/jpeg", filename=path.name)
    if settings.r2_enabled:
        return RedirectResponse(media.thumbnail_url(video_id))
    raise HTTPException(status_code=404, detail=f"no thumbnail cached for {video_id}")


@router.get("/{video_id}/examples/{feature}", response_model=schemas.ExampleList)
def examples(video_id: str, feature: str) -> schemas.ExampleList:
    """Up to 3 winning reels in the same niche/tier/archetype whose value
    for ``feature`` sits closest to the winner median. The Example Library
    -- the dashboard's answer to 'OK, so what does winning look like here?'

    Sparse-fallback: if the strict (tier, archetype) bucket has too few
    examples, the underlying ``find_examples`` widens the filter (drops tier
    first, then archetype) until at least 3 candidates are found.
    """
    niche, tier, archetype = _video_context(video_id)
    if niche is None:
        raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
    bm_map = benchmarks.aggregate(niche)
    bm, _scope = pick_for_tier(bm_map, tier, archetype)
    arch_data = bm.get("archetypes", {}).get(archetype, {}) if archetype else {}
    feat_profile = arch_data.get("profile", {}).get(feature)
    if not feat_profile:
        # Fall back to the pooled benchmark profile so the response still
        # carries a target value (rare; happens for feature names that the
        # benchmark didn't have data for at all).
        pooled_arch = bm_map["pooled"].get("archetypes", {}).get(archetype, {})
        feat_profile = pooled_arch.get("profile", {}).get(feature)
    if not feat_profile:
        raise HTTPException(
            status_code=404,
            detail=f"no benchmark for feature '{feature}' in this niche/archetype",
        )
    benchmark_value = float(feat_profile["high_median"])

    with session_scope() as s:
        video = s.get(Video, video_id)
        category = video.category if video else None
        results = find_examples(
            s,
            label_scheme=api_settings.label_scheme,
            niche=niche,
            feature=feature,
            benchmark_value=benchmark_value,
            tier=tier,
            archetype=archetype,
            category=category,
            n=3,
            exclude_video_id=video_id,
        )
    return schemas.ExampleList(
        feature=feature,
        benchmark_value=benchmark_value,
        examples=[schemas.ExampleVideo.model_validate(e) for e in results],
    )


@router.get("/{video_id}/timeline", response_model=schemas.Timeline)
def timeline(video_id: str) -> schemas.Timeline:
    """Per-second deviation from the archetype's winner profile — the CapCut-style
    timeline data. A prediction from niche patterns, NOT measured audience retention.

    A video with no extracted timeline returns 200 with an empty ``seconds`` list.
    """
    niche, tier, archetype = _video_context(video_id)
    bm, _ = pick_for_tier(benchmarks.per_second(niche), tier, archetype)
    try:
        dev = per_second_deviation(video_id, benchmark=bm)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    summ = summarize_deviation(dev)
    return schemas.Timeline(
        video_id=video_id,
        seconds=[schemas.TimelineSecond(**d) for d in dev],
        summary=schemas.TimelineSummary(**summ) if summ else None,
    )


# Minimum same-category winners (for this archetype) before we trust a
# category-specific pacing benchmark over the broader tier benchmark. Mirrors
# benchmarks._MIN_TIER_WINNERS so the fallback logic is consistent across routes.
# Below this many winners, a category cohort's medians are noise (a first-cut
# median from 6 videos can swing seconds on one outlier) — fall back to the
# much thicker tier x archetype benchmark instead.
_MIN_CATEGORY_WINNERS = 12


def _cutplan_benchmark(niche: str, tier: Optional[str], archetype: Optional[str], category: Optional[str]) -> dict:
    """Pick the pacing benchmark for the cut plan.

    Prefers the creator's own content category (e.g. 'calisthenics' winners)
    when that bucket is thick enough; otherwise falls back to the tier x
    archetype benchmark. The chosen dict carries its own ``category`` field, so
    build_cut_plan reports the scope ('category' vs 'tier') honestly.
    """
    if category:
        cat_bm = benchmarks.timeline_category(niche, tier, category)
        n = (cat_bm.get("archetypes") or {}).get(archetype, {}).get("n_winners") or 0
        if n >= _MIN_CATEGORY_WINNERS:
            return cat_bm
    bm, _scope = pick_for_tier(benchmarks.timeline(niche), tier, archetype)
    return bm


@router.get("/{video_id}/cutplan")
def cutplan(video_id: str, trim_start: Optional[int] = None) -> dict:
    """CapCut-style cut/trim guidance vs winners in the creator's category.

    Default (no ``trim_start``): the full cut plan — actual cuts, over-long
    holds, first-cut timing vs winners, and a single suggested intro trim.

    With ``?trim_start=N``: the live recompute — which hook checks (face by 1s,
    opens on movement, first cut within the winner window) now pass if the reel
    were trimmed to start at second N. This drives the interactive trim handle.
    """
    niche, tier, archetype = _video_context(video_id)
    if niche is None:
        raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
    with session_scope() as s:
        video = s.get(Video, video_id)
        category = video.category if video else None

    bm = _cutplan_benchmark(niche, tier, archetype, category)

    if trim_start is not None:
        return recompute_for_trim(video_id, bm, trim_start)

    plan = build_cut_plan(video_id, bm)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"no timeline extracted for {video_id} — can't build a cut plan",
        )
    # The plan carries the raw category key; attach a human label so the UI can
    # say "vs Powerlifting winners" without duplicating the label map.
    plan["category_label"] = label_for(plan.get("category"))
    return plan


@router.get("/{video_id}/autocut")
def autocut(video_id: str) -> dict:
    """A virtual 'winner cut' that strips dead air only (no re-encoding).

    Returns kept ``segments`` the browser can play back to preview the
    tightened reel, plus the ``removed`` ranges with a plain reason for each.
    Honest by construction: only footage with no face AND no motion is cut.
    """
    niche, tier, archetype = _video_context(video_id)
    if niche is None:
        raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
    with session_scope() as s:
        video = s.get(Video, video_id)
        category = video.category if video else None

    bm = _cutplan_benchmark(niche, tier, archetype, category)
    cut = build_auto_cut(video_id, bm)
    if cut is None:
        raise HTTPException(
            status_code=404,
            detail=f"no timeline extracted for {video_id} — can't build a winner cut",
        )
    cut["category_label"] = label_for(cut.get("category"))
    return cut


@router.get("/{video_id}/category", response_model=schemas.CategoryInfo)
def get_category(video_id: str) -> schemas.CategoryInfo:
    """Current content category + override options for the dropdown.

    ``current`` is the creator-confirmed pick if one exists, else the keyword
    classifier's guess. ``options`` are sorted by classifier likelihood so the
    most-probable categories sit at the top of the dropdown.
    """
    with session_scope() as s:
        video = s.get(Video, video_id)
        if video is None:
            raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
        current = video.category
        confirmed = bool(video.category_confirmed)
        text = f"{video.title or ''} {video.description or ''}"
        niche = video.channel.niche if video.channel else None

    guess, ranked = classify(text, niche)
    # Sort the dropdown by classifier likelihood (keys with keyword hits first,
    # in rank order; the rest keep their declared order).
    rank_index = {key: i for i, (key, _hits) in enumerate(ranked)}
    options = sorted(
        dropdown_options(niche), key=lambda o: rank_index.get(o["key"], len(rank_index))
    )
    return schemas.CategoryInfo(
        video_id=video_id,
        current=current,
        current_label=label_for(current),
        confirmed=confirmed,
        guess=guess,
        options=[schemas.CategoryOption(**o) for o in options],
    )


@router.post("/{video_id}/category", response_model=schemas.CategoryInfo)
def set_category(video_id: str, body: schemas.CategoryUpdate) -> schemas.CategoryInfo:
    """Creator override: set (or clear) the content category and mark it confirmed.

    A confirmed pick is authoritative — the backfill classifier won't clobber it,
    and every downstream comparison (cut plan, examples) re-benchmarks against the
    chosen category. Each correction is also a free training label for later.
    """
    key = body.category
    if key is not None and key not in CATEGORIES:
        raise HTTPException(status_code=422, detail=f"unknown category '{key}'")
    with session_scope() as s:
        video = s.get(Video, video_id)
        if video is None:
            raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
        video.category = key
        video.category_confirmed = 1
        niche = video.channel.niche if video.channel else None
        guess, ranked = classify(f"{video.title or ''} {video.description or ''}", niche)

    rank_index = {k: i for i, (k, _h) in enumerate(ranked)}
    options = sorted(
        dropdown_options(niche), key=lambda o: rank_index.get(o["key"], len(rank_index))
    )
    return schemas.CategoryInfo(
        video_id=video_id,
        current=key,
        current_label=label_for(key),
        confirmed=True,
        guess=guess,
        options=[schemas.CategoryOption(**o) for o in options],
    )
