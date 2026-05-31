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
from creative_director.storage.models import Video, VideoLabel


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
        # niche (data-derived winner-patterns) — the honest "matches winners" %.
        breakdown.pattern_match = predictive_pattern_match(
            video, video.channel.niche if video.channel else None
        )

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
