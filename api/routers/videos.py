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

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from api import schemas
from api.benchmarks import benchmarks, pick_for_tier
from creative_director.advice.benchmark import classify_archetype
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
from creative_director.storage.models import Video

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
    return schemas.PlainSummary.model_validate(plain)


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
        if video is None:
            raise HTTPException(status_code=404, detail=f"unknown video {video_id}")

    # Serve the local file when present (dev); otherwise fall back to the R2
    # corpus (prod / ingest box where local copies are pruned after upload).
    archive = settings.video_archive_dir or Path("data/videos")
    path = archive / f"{video_id}.mp4"
    if path.exists():
        return FileResponse(path, media_type="video/mp4", filename=path.name)
    if settings.r2_enabled:
        return RedirectResponse(media.video_url(video_id))
    raise HTTPException(
        status_code=404,
        detail=f"no mp4 archived for {video_id} (run feature extraction or ingest)",
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
        if video is None:
            raise HTTPException(status_code=404, detail=f"unknown video {video_id}")
        path_str = video.thumbnail_path

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
_MIN_CATEGORY_WINNERS = 5


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
