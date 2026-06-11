"""Per-video creative-director breakdown (v0 — aggregate features, archetype-aware).

Compares one video against the high-performer benchmark *of its own archetype*
(talking-head vs silent demo) and produces a structured list of findings.
Phase 2 will add per-second / frame-level findings on top of this aggregate layer.

Output is comparative, not prescriptive: each finding says "winners of your
archetype tend to X, your video does Y" with confidence + causal tags so the
narrative layer can stay honest about levers vs proxies.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from creative_director.advice.benchmark import (
    REPORTABLE,
    classify_archetype,
    compute_benchmark,
)
from creative_director.advice.fixability import fixability_label, fixability_weight
from creative_director.advice.tier import tier_for_video
from creative_director.advice.trajectory import (
    compute_trajectory,
    trajectory_weight,
)
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoLabel, VideoTimeline


# Minimum (tier x archetype) winner count below which we fall back to the
# non-tier-stratified pooled benchmark. Five is a soft floor for medians;
# tighter than that and the per-tier comparison is noisier than the pool.
_MIN_TIER_WINNERS = 5


@lru_cache(maxsize=1)
def _predictive_map() -> dict:
    """Per-niche map of features that actually predict performance, from
    scripts.compute_predictive_features -> {niche: {feature: {rho, niche_median, source}}}."""
    path = Path(__file__).with_name("predictive_features.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("niches", {})
    except (OSError, ValueError):
        return {}


def predictive_pattern_match(video, niche: Optional[str]) -> Optional[dict]:
    """How well a video matches what actually WINS in its niche.

    Uses the data-derived predictive features (not the generic REPORTABLE set):
    the |rho|-weighted fraction sitting on the winner-favorable side of the niche
    median. Returns {aligned, total, pct} or None when the niche has no
    predictive map yet / the video lacks features.
    """
    feats = _predictive_map().get(niche or "")
    if not feats or video.features is None:
        return None
    tot_w = al_w = 0.0
    total = aligned = 0
    for feat, meta in feats.items():
        rho = meta.get("rho") or 0.0
        med = meta.get("niche_median")
        if med is None or rho == 0:
            continue
        val = (
            video.duration_seconds
            if meta.get("source") == "video"
            else getattr(video.features, feat, None)
        )
        if val is None:
            continue
        w = abs(rho)
        tot_w += w
        total += 1
        if (float(val) - med) * rho > 0:  # on the side that correlates with winning
            al_w += w
            aligned += 1
    if tot_w == 0:
        return None
    return {"aligned": aligned, "total": total, "pct": round(100 * al_w / tot_w)}


# (label, directive when winners have a HIGHER value, directive when LOWER).
# Drives the "do what winners do" recommendations from the predictive features.
_FEATURE_META: dict[str, tuple[str, str, str]] = {
    "duration_seconds": ("length", "Make it longer", "Make it shorter / tighter"),
    "avg_shot_length": ("shot pacing", "Hold shots longer", "Cut faster"),
    "total_cut_count": ("cuts", "Add more cuts", "Use fewer cuts"),
    "first3s_cut_count": ("opening cuts", "Cut more in the first 3s", "Cut less in the first 3s"),
    "first3s_motion_intensity": ("opening motion", "More motion in the first 3s", "Calmer opening"),
    "first3s_face_present": ("a face up front", "Show a face in the first 3s", "Skip the face up front"),
    "first3s_text_present": ("opening text", "Put on-screen text in the first 3s", "Drop the opening text"),
    "audio_voice_ratio": ("voiceover", "Add more voiceover / talking", "Talk less — let visuals lead"),
    "audio_loudness_mean": ("loudness", "Mix it louder", "Mix it quieter"),
    "audio_loudness_max": ("peak loudness", "Punchier audio peaks", "Softer audio peaks"),
    "transcript_word_count": ("spoken words", "Say more", "Say less"),
    "hook_word_count": ("hook length", "A longer spoken hook", "A shorter spoken hook"),
    "hook_uses_you": ("“you” in the hook", "Address the viewer (“you…”) in the hook", "Drop “you” from the hook"),
    "title_emoji_count": ("title emojis", "Add emojis to the title", "Use fewer title emojis"),
    "title_char_count": ("title length", "A longer title", "A shorter title"),
    "title_word_count": ("title words", "More words in the title", "Fewer words in the title"),
    "title_question_mark": ("a title question", "Ask a question in the title", "Drop the title question"),
    "title_all_caps_ratio": ("ALL-CAPS", "More ALL-CAPS in the title", "Less ALL-CAPS in the title"),
    "hashtag_count": ("hashtags", "Add more hashtags", "Use fewer hashtags"),
    "description_char_count": ("caption length", "A longer caption", "A shorter caption"),
    "description_word_count": ("caption length", "A longer caption", "A shorter caption"),
    "thumb_contrast": ("thumbnail contrast", "A higher-contrast thumbnail", "A softer / lower-contrast thumbnail"),
    "thumb_brightness": ("thumbnail brightness", "A brighter thumbnail", "A darker thumbnail"),
    "thumb_saturation": ("thumbnail color", "More vivid thumbnail color", "More muted thumbnail color"),
    "thumb_dominant_face_area": ("face size in thumbnail", "A bigger face in the thumbnail", "A smaller face in the thumbnail"),
    "thumb_text_present": ("thumbnail text", "Add text to the thumbnail", "Drop the thumbnail text"),
    "thumb_text_char_count": ("thumbnail text", "More text on the thumbnail", "Less text on the thumbnail"),
    "engagement_has_tag_prompt": ("a tag-a-friend prompt", "Add a “tag a friend” prompt", "Drop the tag prompt"),
    "engagement_prompt_count": ("calls-to-action", "Add a clear call-to-action", "Fewer calls-to-action"),
}

# Minimum |your_value - winner_median| before a recommendation is worth showing.
# Tiny-integer / ratio features otherwise produce "1 emoji vs ~0"-grade nags.
_MIN_ACTIONABLE_DELTA: dict[str, float] = {
    "title_emoji_count": 2,
    "description_emoji_count": 2,
    "hashtag_count": 2,
    "title_word_count": 3,
    "title_char_count": 12,
    "title_all_caps_ratio": 0.2,
    "engagement_prompt_count": 1,
    "hook_word_count": 3,
    "transcript_word_count": 15,
    "description_char_count": 40,
    "description_word_count": 10,
    # Continuous features where small deltas are perceptually meaningless:
    "thumb_contrast": 0.1,
    "thumb_brightness": 0.1,
    "thumb_saturation": 0.1,
    "audio_loudness_mean": 4,   # dB — under ~4dB nobody can act on "mix it louder"
    "audio_loudness_max": 4,
    "audio_voice_ratio": 0.15,
    "first3s_motion_intensity": 0.02,
    "avg_shot_length": 3,
}


# Speech-tuning advice ("say more", "add voiceover") only makes sense for
# reels that already lead with speech; telling a silent demo channel to add a
# voiceover prescribes a different format, not a tweak.
_SPEECH_FEATS = {
    "transcript_word_count",
    "hook_word_count",
    "hook_uses_you",
    "audio_voice_ratio",
}
_FACE_FEATS = {"first3s_face_present"}


def _overall_face_frac(video) -> Optional[float]:
    """Whole-video face fraction from the timeline (None if no rows/session)."""
    from sqlalchemy import select
    from sqlalchemy.orm import object_session

    s = object_session(video)
    if s is None:
        return None
    rows = s.execute(
        select(VideoTimeline.has_face).where(VideoTimeline.video_id == video.id)
    ).all()
    vals = [r[0] for r in rows if r[0] is not None]
    return (sum(vals) / len(vals)) if vals else None


def winner_recommendations(video, niche: Optional[str], limit: int = 6) -> list[dict]:
    """Top data-derived 'do what winners do' moves.

    The predictive features (for this niche) where the reel is on the WRONG side
    of the winner-favorable direction, phrased as directives and ranked by |rho|
    (how strongly the feature predicts performance). This is the moat: specific,
    category-tuned advice grounded in what actually correlates with winning.
    """
    from creative_director.advice.benchmark import classify_archetype, face_advice_applies

    feats = _predictive_map().get(niche or "")
    if not feats or video.features is None:
        return []
    archetype = classify_archetype(video.features.transcript_word_count)
    face_frac = _overall_face_frac(video)
    recs: list[dict] = []
    for feat, meta in feats.items():
        # The read owns length advice (tier+archetype cohort); carrying duration
        # here too lets two benchmarks argue on one page ("runs short" vs
        # "make it shorter").
        if meta.get("source") == "video":
            continue
        if feat in _SPEECH_FEATS and archetype != "talking":
            continue
        if feat in _FACE_FEATS and not face_advice_applies(archetype, face_frac):
            continue
        rho = meta.get("rho") or 0.0
        med = meta.get("niche_median")
        if med is None or rho == 0:
            continue
        val = (
            video.duration_seconds
            if meta.get("source") == "video"
            else getattr(video.features, feat, None)
        )
        if val is None:
            continue
        wm = meta.get("winner_median")
        if wm is None or round(float(val), 2) == round(float(wm), 2):
            continue  # no winner target, or no visible gap to act on
        # Recommend only when the reel is on the WORSE side of the winner median,
        # so the directive ("do more/less") and the target we show stay consistent.
        if (float(wm) - float(val)) * rho <= 0:
            continue
        # Tiny-magnitude features need a REAL absolute delta — "1 emoji vs ~0"
        # or "0.06 ALL-CAPS vs 0" read as pedantic noise, not advice.
        if abs(float(val) - float(wm)) < _MIN_ACTIONABLE_DELTA.get(feat, 0.0):
            continue
        # "Hold shots longer (≈15s)" on a 4s reel: the target can't exceed the
        # reel itself. Skip shot-length advice when the winner target doesn't
        # comfortably fit inside the video.
        if (
            feat == "avg_shot_length"
            and rho > 0
            and video.duration_seconds
            and float(wm) > 0.8 * float(video.duration_seconds)
        ):
            continue
        pretty = feat.replace("_", " ")
        label, hi_dir, lo_dir = _FEATURE_META.get(
            feat, (pretty, f"More {pretty}", f"Less {pretty}")
        )
        wm = meta.get("winner_median")
        recs.append({
            "feature": feat,
            "label": label,
            "advice": hi_dir if rho > 0 else lo_dir,
            "your_value": round(float(val), 2),
            "winner_value": round(float(wm), 2) if wm is not None else None,
            "weight": round(abs(rho), 3),
        })
    recs.sort(key=lambda r: -r["weight"])
    return recs[:limit]


@dataclass
class Finding:
    feature: str
    label: str
    your_value: Optional[float]
    benchmark_value: float
    unit: str
    direction: str  # "above" | "below" | "aligned"
    gap_ratio: float
    confidence: str
    causal: str
    off_benchmark: bool
    # Per-feature how-easily-can-the-creator-act-on-this weight (see fixability.py).
    fixability: str = "medium"
    # 0..1 composite rank for which findings to surface first.
    # rank_score = gap_score x fixability_weight x trajectory_weight.
    rank_score: float = 0.0
    # Direction of the creator's recent uploads on this feature:
    # "improving" (moving toward benchmark) | "stable" | "declining" | None
    # (when history is too thin to call). Surfaced as an arrow in the UI and
    # fed back into rank_score to mute findings the creator is already
    # working on.
    trajectory: Optional[str] = None


@dataclass
class VideoBreakdown:
    video_id: str
    title: str
    channel: str
    duration_seconds: Optional[int]
    archetype: str
    archetype_n: int  # how many high performers of this archetype back the benchmark
    label_scheme: Optional[str]
    tercile: Optional[int]
    score: Optional[float]
    # Creator's tier (small/mid/large/None). None = unknown.
    tier: Optional[str] = None
    # Whether the benchmark used was tier-stratified or pooled fallback.
    benchmark_scope: str = "pooled"  # "tier" | "pooled"
    findings: list[Finding] = field(default_factory=list)
    # Data-derived "matches winners" score over the niche's predictive features
    # ({aligned, total, pct}). The honest Scorecard headline, vs the old generic
    # all-findings match%. None when the niche has no predictive map.
    pattern_match: Optional[dict] = None
    # Top "do what winners do" moves: predictive features the reel is on the
    # wrong side of, phrased as directives, ranked by predictive importance.
    recommendations: list[dict] = field(default_factory=list)


def _gap_score(gap_ratio: float) -> float:
    """Symmetric 0..1 deviation magnitude from the benchmark ratio.

    log2(gap_ratio) is 0 at parity, +1 at 2x above, -1 at 2x below. We take
    the absolute value and clip to 1.0 so a 4x outlier doesn't dominate the
    ranking against several 1.5-2x findings.
    """
    if gap_ratio <= 0 or not math.isfinite(gap_ratio):
        return 1.0
    return min(abs(math.log2(gap_ratio)), 1.0)


_TERCILE_NAME = {0: "low", 1: "medium", 2: "high"}


def _video_feature_value(video: Video, feature: str) -> Optional[float]:
    src = REPORTABLE[feature]["source"]
    if src == "video":
        v = getattr(video, feature, None)
    else:
        v = getattr(video.features, feature, None) if video.features else None
    return None if v is None else float(v)


def analyze_video(
    video_id: str,
    benchmark: Optional[dict] = None,
    benchmarks_by_tier: Optional[dict[str, dict]] = None,
) -> VideoBreakdown:
    """Build the structured breakdown for one video, archetype- and tier-aware.

    Caller passes EITHER:
      - ``benchmark`` (legacy: a single, non-tier-stratified profile), OR
      - ``benchmarks_by_tier`` mapping {tier: benchmark, "pooled": benchmark}
        so the analyzer can pick the right tier benchmark for this video
        and fall back to "pooled" when the (tier, archetype) bucket is thin.
    """
    with session_scope() as s:
        video = s.get(Video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")
        if video.features is None:
            raise ValueError(f"Video {video_id} has no extracted features")

        archetype = classify_archetype(video.features.transcript_word_count)

        # Pick the benchmark to compare against.
        creator_tier: Optional[str] = None
        benchmark_scope = "pooled"
        if benchmarks_by_tier is not None:
            creator_tier = tier_for_video(s, video_id)
            chosen = None
            if creator_tier and creator_tier in benchmarks_by_tier:
                tier_bm = benchmarks_by_tier[creator_tier]
                tier_n = (
                    tier_bm.get("archetypes", {})
                    .get(archetype, {})
                    .get("n_high", 0)
                )
                if tier_n >= _MIN_TIER_WINNERS:
                    chosen = tier_bm
                    benchmark_scope = "tier"
            if chosen is None:
                chosen = benchmarks_by_tier.get("pooled")
            if chosen is None:
                raise ValueError("benchmarks_by_tier missing 'pooled' fallback")
            benchmark = chosen
        elif benchmark is None:
            benchmark = compute_benchmark()

        arch_data = benchmark["archetypes"].get(archetype, {})
        profile = arch_data.get("profile", {})

        label = s.execute(
            VideoLabel.__table__.select().where(
                (VideoLabel.video_id == video_id)
                & (VideoLabel.label_scheme == benchmark["label_scheme"])
            )
        ).first()

        breakdown = VideoBreakdown(
            video_id=video.id,
            title=video.title,
            channel=video.channel.title if video.channel else "?",
            duration_seconds=video.duration_seconds,
            archetype=archetype,
            archetype_n=arch_data.get("n_high", 0),
            label_scheme=benchmark["label_scheme"],
            tercile=label.tercile if label else None,
            score=label.score if label else None,
            tier=creator_tier,
            benchmark_scope=benchmark_scope,
        )

        for feat, meta in REPORTABLE.items():
            if feat not in profile:
                continue
            bm = profile[feat]["high_median"]
            val = _video_feature_value(video, feat)
            if val is None:
                continue

            if bm > 0:
                gap_ratio = val / bm
            else:
                gap_ratio = 1.0 if val == bm else 2.0
            off = abs(gap_ratio - 1.0) > 0.25
            direction = "aligned" if not off else ("above" if val > bm else "below")

            fix_w = fixability_weight(feat)
            # Trajectory only matters for off-benchmark items (no point
            # tracking direction on something the creator is already nailing).
            trajectory = (
                compute_trajectory(
                    s, video.channel_id, video.published_at, feat, bm
                )
                if off
                else None
            )
            traj_w = trajectory_weight(trajectory)
            # rank_score: prioritise findings the creator can both ACT on AND
            # that diverge most AND isn't already improving. Aligned findings
            # get rank_score=0 so they naturally sort to the bottom.
            gap_s = _gap_score(gap_ratio) if off else 0.0
            rank_score = gap_s * fix_w * traj_w

            breakdown.findings.append(
                Finding(
                    feature=feat,
                    label=meta["label"],
                    your_value=val,
                    benchmark_value=bm,
                    unit=meta["unit"],
                    direction=direction,
                    gap_ratio=gap_ratio,
                    confidence=meta["confidence"],
                    causal=meta["causal"],
                    off_benchmark=off,
                    fixability=fixability_label(fix_w),
                    rank_score=rank_score,
                    trajectory=trajectory,
                )
            )

        # How well this reel matches what actually predicts performance in its
        # niche (data-derived winner-patterns) — the honest "matches winners" %,
        # plus the specific moves to close the gap.
        _niche = video.channel.niche if video.channel else None
        breakdown.pattern_match = predictive_pattern_match(video, _niche)
        breakdown.recommendations = winner_recommendations(video, _niche)

    # Off-benchmark findings first (by rank_score desc); aligned at the tail.
    conf_rank = {"strong": 0, "moderate": 1}
    breakdown.findings.sort(
        key=lambda f: (
            not f.off_benchmark,
            -f.rank_score,
            conf_rank.get(f.confidence, 2),
        )
    )
    return breakdown


def format_breakdown(b: VideoBreakdown) -> str:
    lines: list[str] = []
    lines.append(f"VIDEO: {b.title}")
    lines.append(f"Channel: {b.channel}  |  Duration: {b.duration_seconds}s")
    lines.append(
        f"Archetype: {b.archetype}  "
        f"(compared against {b.archetype_n} high-performing {b.archetype} videos)"
    )
    if b.tercile is not None:
        lines.append(
            f"Benchmark label: {_TERCILE_NAME.get(b.tercile, '?')} performer "
            f"(score {b.score:+.2f})"
        )
    lines.append("")
    lines.append(f"FINDINGS vs high-performing {b.archetype} fitness Shorts:")
    for f in b.findings:
        val = f"{f.your_value:.1f}{f.unit}" if f.your_value is not None else "n/a"
        bm = f"{f.benchmark_value:.1f}{f.unit}"
        tag = "OK" if f.direction == "aligned" else f"OFF ({f.direction})"
        proxy = (
            "  [likely a proxy, not a direct lever]"
            if f.causal == "likely-proxy"
            else ""
        )
        lines.append(
            f"  - {f.label:24} you={val:<11} winners~{bm:<11} {tag} "
            f"[{f.confidence}]{proxy}"
        )
    return "\n".join(lines)
