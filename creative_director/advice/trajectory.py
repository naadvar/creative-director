"""Per-creator feature trajectory over the last K uploads.

Given a video and one of its feature dimensions, look at the creator's K
previous reels and ask: are they trending TOWARD the winner-tier benchmark
(improving), AWAY from it (declining), or holding steady (stable)?

This feeds the dashboard's ranking score as a down-weight: if a creator is
already improving on a dimension, the advisor shouldn't keep yelling about
it -- their next experiment should be elsewhere. The ranking math is:

    rank_score = gap_score x fixability_weight x (1 if not improving else 0.5)

Output is also surfaced visually as a small arrow next to each finding so
the creator can see at a glance which way they're moving.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from creative_director.advice.benchmark import REPORTABLE
from creative_director.storage.models import Video, VideoFeatures


# Direction labels surfaced to the UI.
IMPROVING = "improving"
STABLE = "stable"
DECLINING = "declining"

# Minimum relative slope (per video step) to call a direction non-stable.
# Empirical pick: 5% of the distance from benchmark per video step. Lower
# than this looks like noise across K=5 small-N estimates.
_SLOPE_THRESHOLD = 0.05

# Down-weight applied to rank_score when the creator is already improving.
ALREADY_IMPROVING_WEIGHT = 0.5


def _feature_value(video: Video, feature: str) -> Optional[float]:
    """Pull a feature value from a Video or its features row, matching
    benchmark.REPORTABLE.source. Returns None when missing."""
    meta = REPORTABLE.get(feature)
    src = meta["source"] if meta else "features"
    if src == "video":
        v = getattr(video, feature, None)
    else:
        v = getattr(video.features, feature, None) if video.features else None
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _slope(distances: list[float]) -> float:
    """Linear-fit slope of a 1D series, expressed per index step.

    Positive slope means distance is GROWING (declining trajectory); negative
    means SHRINKING (improving). Uses the closed-form covariance form rather
    than a heavy regression so this stays cheap.
    """
    n = len(distances)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(distances) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(distances):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx
    if den == 0:
        return 0.0
    return num / den


def compute_trajectory(
    session: Session,
    channel_id: str,
    current_published_at,
    feature: str,
    benchmark_value: float,
    k: int = 5,
) -> Optional[str]:
    """Look at the creator's last ``k`` reels before the current one and
    report direction toward the benchmark.

    Returns None if there isn't enough history (fewer than 3 prior videos
    with a non-null value for this feature) -- the UI shows no arrow in that
    case rather than a misleading one.
    """
    rows = session.execute(
        select(Video)
        .where(
            (Video.channel_id == channel_id)
            & (Video.published_at < current_published_at)
        )
        .order_by(Video.published_at.desc())
        .limit(k)
    ).scalars().all()
    if len(rows) < 3:
        return None

    # Chronological order (oldest -> newest) so a NEGATIVE slope = improving.
    ordered = list(reversed(rows))
    values = [_feature_value(v, feature) for v in ordered]
    pairs = [v for v in values if v is not None]
    if len(pairs) < 3:
        return None
    distances = [abs(v - benchmark_value) for v in pairs]

    # Normalise slope by the mean distance so the threshold is scale-free.
    mean_dist = sum(distances) / len(distances)
    if mean_dist <= 1e-9:
        # Already at the benchmark -- arrow points nowhere meaningful.
        return STABLE
    slope = _slope(distances)
    normalised = slope / mean_dist
    if normalised < -_SLOPE_THRESHOLD:
        return IMPROVING
    if normalised > _SLOPE_THRESHOLD:
        return DECLINING
    return STABLE


def trajectory_weight(trajectory: Optional[str]) -> float:
    """Down-weight applied to rank_score when a creator is already improving
    on that dimension. ``stable`` and ``declining`` use full weight (still
    worth attention); only ``improving`` is muted."""
    if trajectory == IMPROVING:
        return ALREADY_IMPROVING_WEIGHT
    return 1.0
