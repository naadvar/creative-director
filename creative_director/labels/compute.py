"""Compute labels for all videos and persist them as VideoLabel rows.

A label is a (score, tercile) pair under a named scheme:

- ``per_channel_log_residual_v1``: compares each video to its channel's mean.
  Cohort = channel. Skips channels with fewer than ``min_cohort_size`` videos
  (default 3 — terciles aren't meaningful below that).

- ``log_views_per_sub_v1``: views / subscribers. Single global cohort.
  Tercile is computed across all videos in the niche.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import numpy as np
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from creative_director.labels.schemes import (
    VideoMetrics,
    log_views_per_subscriber,
    per_channel_log_residual,
)
from creative_director.storage.models import Video, VideoLabel


def build_metrics(session: Session, niche: Optional[str] = None) -> list[VideoMetrics]:
    """Pull the data needed to compute labels.

    Uses the *latest* velocity snapshot per video as the view count. This is biased
    toward older videos (more time to accumulate views) — fine for v1, but a future
    revision should normalize to a fixed age (e.g., views at 24h, 7d).
    """
    q = select(Video)
    if niche is not None:
        from creative_director.storage.models import Channel
        q = q.join(Channel).where(Channel.niche == niche)

    out: list[VideoMetrics] = []
    for v in session.execute(q).scalars():
        if not v.velocity_snapshots:
            continue
        latest = max(v.velocity_snapshots, key=lambda s: s.captured_at)
        age = max(0.0, (datetime.utcnow() - v.published_at).total_seconds() / 86400.0)
        out.append(
            VideoMetrics(
                video_id=v.id,
                channel_id=v.channel_id,
                niche=v.channel.niche,
                subscriber_count=v.channel.subscriber_count,
                latest_view_count=latest.view_count,
                age_days=age,
            )
        )
    return out


def _tercile_index(score: float, q33: float, q67: float) -> int:
    if score < q33:
        return 0
    if score < q67:
        return 1
    return 2


def _upsert_label(
    session: Session,
    video_id: str,
    label_scheme: str,
    score: float,
    tercile: int,
    cohort_id: str,
    cohort_size: int,
) -> None:
    existing = session.execute(
        select(VideoLabel).where(
            VideoLabel.video_id == video_id,
            VideoLabel.label_scheme == label_scheme,
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = VideoLabel(video_id=video_id, label_scheme=label_scheme)
        session.add(existing)
    existing.score = float(score)
    existing.tercile = int(tercile)
    existing.cohort_id = cohort_id
    existing.cohort_size = int(cohort_size)
    existing.computed_at = datetime.utcnow()


def compute_per_channel_labels(
    session: Session,
    scheme_name: str = "per_channel_log_residual_v1",
    min_cohort_size: int = 3,
    niche: Optional[str] = None,
) -> dict:
    """For each channel, score its videos as log-residuals and bucket into terciles.

    Skips channels with fewer than ``min_cohort_size`` videos.
    """
    metrics = build_metrics(session, niche=niche)
    by_channel: dict[str, list[VideoMetrics]] = defaultdict(list)
    for m in metrics:
        by_channel[m.channel_id].append(m)

    stats = {
        "scheme": scheme_name,
        "channels_labeled": 0,
        "channels_skipped": 0,
        "videos_labeled": 0,
        "videos_skipped_small_cohort": 0,
    }

    for cid, vids in by_channel.items():
        if len(vids) < min_cohort_size:
            stats["channels_skipped"] += 1
            stats["videos_skipped_small_cohort"] += len(vids)
            logger.info(f"channel {cid}: skipping ({len(vids)} videos < min {min_cohort_size})")
            continue
        scores = [per_channel_log_residual(m, vids) for m in vids]
        q33, q67 = np.quantile(scores, [1 / 3, 2 / 3])
        for m, s in zip(vids, scores):
            _upsert_label(
                session,
                video_id=m.video_id,
                label_scheme=scheme_name,
                score=s,
                tercile=_tercile_index(s, q33, q67),
                cohort_id=cid,
                cohort_size=len(vids),
            )
            stats["videos_labeled"] += 1
        stats["channels_labeled"] += 1

    return stats


def compute_global_views_per_sub_labels(
    session: Session,
    scheme_name: str = "log_views_per_sub_v1",
    niche: Optional[str] = None,
) -> dict:
    """Score each video by log(views/subs); bucket into niche-wide terciles."""
    metrics = build_metrics(session, niche=niche)
    if not metrics:
        return {"scheme": scheme_name, "videos_labeled": 0}

    scores = [log_views_per_subscriber(m) for m in metrics]
    q33, q67 = np.quantile(scores, [1 / 3, 2 / 3])
    cohort_id = f"niche:{niche}" if niche else "global"

    for m, s in zip(metrics, scores):
        _upsert_label(
            session,
            video_id=m.video_id,
            label_scheme=scheme_name,
            score=s,
            tercile=_tercile_index(s, q33, q67),
            cohort_id=cohort_id,
            cohort_size=len(metrics),
        )

    return {
        "scheme": scheme_name,
        "videos_labeled": len(metrics),
        "cohort_size": len(metrics),
        "q33": float(q33),
        "q67": float(q67),
    }


def compute_age_banded_views_per_sub_labels(
    session: Session,
    scheme_name: str = "views_per_sub_aged_v1",
    niche: Optional[str] = None,
    min_age_days: float = 30.0,
    max_age_days: float = 180.0,
) -> dict:
    """log(views/subs), but only for videos whose view snapshot was taken
    within an age band.

    Restricting to an age band removes the dominant confound in single-snapshot
    labels: a 6-month-old video has had far longer to accumulate views than a
    week-old one. Within a band, views/subs is a much cleaner proxy for how
    well the content actually performed. Terciles are computed within the band.
    """
    metrics = [
        m
        for m in build_metrics(session, niche=niche)
        if min_age_days <= m.age_days <= max_age_days
    ]
    if not metrics:
        return {"scheme": scheme_name, "videos_labeled": 0}

    scores = [log_views_per_subscriber(m) for m in metrics]
    q33, q67 = np.quantile(scores, [1 / 3, 2 / 3])
    cohort_id = f"niche:{niche}|age:{min_age_days:.0f}-{max_age_days:.0f}d"

    for m, s in zip(metrics, scores):
        _upsert_label(
            session,
            video_id=m.video_id,
            label_scheme=scheme_name,
            score=s,
            tercile=_tercile_index(s, q33, q67),
            cohort_id=cohort_id,
            cohort_size=len(metrics),
        )

    return {
        "scheme": scheme_name,
        "videos_labeled": len(metrics),
        "cohort_size": len(metrics),
        "age_band_days": [min_age_days, max_age_days],
        "q33": float(q33),
        "q67": float(q67),
    }


def compute_within_channel_aged_labels(
    session: Session,
    scheme_name: str = "within_channel_aged_v1",
    niche: Optional[str] = None,
    min_age_days: float = 30.0,
    max_age_days: float = 180.0,
    min_cohort_size: int = 4,
) -> dict:
    """Per-channel log-residual, restricted to an age band, terciled globally.

    Combines the two corrections we already use separately:
      - per-channel residual removes the creator-skill confound (a big channel's
        worst video can still out-view a small channel's best);
      - the age band removes the accumulation confound.

    The residual is channel-relative, so residuals *are* comparable across
    channels — terciles are therefore computed once over the whole niche, not
    per channel (per-channel terciles on ~4-10 videos would be noise). This is
    the most product-relevant label: "did this video beat what this specific
    creator usually does, holding age constant".
    """
    metrics = [
        m
        for m in build_metrics(session, niche=niche)
        if min_age_days <= m.age_days <= max_age_days
    ]
    by_channel: dict[str, list[VideoMetrics]] = defaultdict(list)
    for m in metrics:
        by_channel[m.channel_id].append(m)

    scored: list[tuple[VideoMetrics, float]] = []
    channels_skipped = 0
    for cid, vids in by_channel.items():
        if len(vids) < min_cohort_size:
            channels_skipped += 1
            continue
        for m in vids:
            scored.append((m, per_channel_log_residual(m, vids)))

    if not scored:
        return {"scheme": scheme_name, "videos_labeled": 0, "channels_skipped": channels_skipped}

    scores = [s for _, s in scored]
    q33, q67 = np.quantile(scores, [1 / 3, 2 / 3])
    for m, s in scored:
        _upsert_label(
            session,
            video_id=m.video_id,
            label_scheme=scheme_name,
            score=s,
            tercile=_tercile_index(s, q33, q67),
            cohort_id=f"channel:{m.channel_id}",
            cohort_size=len(by_channel[m.channel_id]),
        )

    return {
        "scheme": scheme_name,
        "videos_labeled": len(scored),
        "channels_labeled": len({m.channel_id for m, _ in scored}),
        "channels_skipped": channels_skipped,
        "age_band_days": [min_age_days, max_age_days],
        "q33": float(q33),
        "q67": float(q67),
    }


def compute_all_labels(session: Session, niche: Optional[str] = None) -> dict:
    """Compute every label scheme we have. Convenience wrapper."""
    return {
        "per_channel_log_residual_v1": compute_per_channel_labels(session, niche=niche),
        "log_views_per_sub_v1": compute_global_views_per_sub_labels(session, niche=niche),
        "views_per_sub_aged_v1": compute_age_banded_views_per_sub_labels(
            session, niche=niche
        ),
        "within_channel_aged_v1": compute_within_channel_aged_labels(
            session, niche=niche
        ),
    }
