"""Normalization formulas used to convert raw view counts into comparable scores.

Each scheme answers a different question:

- ``log_views_per_subscriber``: "How many views did this get relative to the
  channel's audience?" Simplest. Has known biases (older videos accumulate
  more views; channels with algorithm love get higher ratios consistently).

- ``per_channel_log_residual``: "Did this video over- or under-perform what
  this channel typically gets?" This is the most useful signal for prescriptive
  advice ("you usually do X; this one did 0.4x that"). Requires >=3 videos per
  channel for a meaningful baseline.

- ``per_niche_log_residual``: Same idea but baseline is the niche cohort. For
  cross-creator comparisons. Less precise per creator but useful for
  benchmarking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class VideoMetrics:
    """Snapshot of one video used for label computation."""

    video_id: str
    channel_id: str
    niche: Optional[str]
    subscriber_count: Optional[int]
    latest_view_count: int
    age_days: float


def _safe_log(x: float) -> float:
    return math.log(max(1.0, float(x)))


def log_views_per_subscriber(m: VideoMetrics) -> float:
    """log(views / max(1, subscribers)). High = video punched above channel weight."""
    subs = max(1, m.subscriber_count or 1)
    return _safe_log(m.latest_view_count) - _safe_log(subs)


def per_channel_log_residual(m: VideoMetrics, channel_videos: Iterable[VideoMetrics]) -> float:
    """log(this video views) - mean(log(views)) over all videos in this channel.

    Positive = over-performed the channel's baseline. Negative = under-performed.
    """
    log_views = [_safe_log(v.latest_view_count) for v in channel_videos]
    if not log_views:
        return 0.0
    baseline = sum(log_views) / len(log_views)
    return _safe_log(m.latest_view_count) - baseline


def per_niche_log_residual(m: VideoMetrics, niche_videos: Iterable[VideoMetrics]) -> float:
    """log(this video views) - mean(log(views)) over all videos in this niche.

    Cross-creator comparison. Use only when channel has too few videos for a
    per-channel baseline.
    """
    log_views = [_safe_log(v.latest_view_count) for v in niche_videos]
    if not log_views:
        return 0.0
    baseline = sum(log_views) / len(log_views)
    return _safe_log(m.latest_view_count) - baseline
