"""Example Library: for a given finding, return real winning reels that
exemplify the winner-typical value for that feature.

The dashboard's findings tell a creator WHERE they diverge from winners.
This module answers the natural follow-up question -- "OK, but what do
those winning reels actually LOOK like?" -- by returning a few top-tercile
videos in the same niche + tier + archetype whose values for the feature
sit closest to the benchmark median.

These are the videos a creator can click through and watch to internalise
what "winning" means on that dimension, beyond a single benchmark number.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from creative_director.advice.benchmark import REPORTABLE, classify_archetype
from creative_director.advice.tier import tier_for_count
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel


@dataclass
class ExampleVideo:
    video_id: str
    title: str
    channel: str
    value: float
    benchmark_value: float
    duration_seconds: Optional[int]


def _feature_value(video: Video, feature: str) -> Optional[float]:
    """Same source-routing as breakdown / trajectory."""
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


def find_examples(
    session: Session,
    label_scheme: str,
    niche: str,
    feature: str,
    benchmark_value: float,
    tier: Optional[str] = None,
    archetype: Optional[str] = None,
    category: Optional[str] = None,
    n: int = 3,
    exclude_video_id: Optional[str] = None,
) -> list[ExampleVideo]:
    """Return up to ``n`` top-tercile videos closest to the benchmark value
    for ``feature``, filtered by the creator's content category, tier and
    archetype.

    Sparse-fallback policy mirrors the benchmark layer. ``category`` (e.g.
    powerlifting) is the *preferred* dimension: we first look for same-category
    winners, widening tier then archetype within the category; only if that
    can't reach ``n`` do we drop the category filter entirely and fall back to
    the original (tier, archetype) widening. The caller can tell which filters
    survived by inspecting the returned videos.
    """
    if feature not in REPORTABLE:
        return []

    base = (
        select(Video, VideoFeatures, Channel)
        .join(VideoFeatures, VideoFeatures.video_id == Video.id)
        .join(Channel, Channel.id == Video.channel_id)
        .join(
            VideoLabel,
            (VideoLabel.video_id == Video.id)
            & (VideoLabel.label_scheme == label_scheme),
        )
        .where(
            Channel.niche == niche,
            VideoLabel.tercile == 2,
        )
    )
    if exclude_video_id:
        base = base.where(Video.id != exclude_video_id)

    all_rows: list[tuple] = session.execute(base).all()

    def _filter(rows: list[tuple], t: Optional[str], a: Optional[str], c: Optional[str]) -> list[tuple]:
        out = rows
        if c is not None:
            out = [r for r in out if r[0].category == c]
        if t:
            out = [r for r in out if tier_for_count(r[2].subscriber_count) == t]
        if a:
            out = [r for r in out if classify_archetype(r[1].transcript_word_count) == a]
        return out

    # (tier, archetype) widening, most specific to least.
    ta_attempts: list = []
    if tier and archetype:
        ta_attempts.append((tier, archetype))
    if tier:
        ta_attempts.append((tier, None))
    if archetype:
        ta_attempts.append((None, archetype))
    ta_attempts.append((None, None))

    # Prefer same-category winners; fall back to no-category if too sparse.
    cat_prefs: list[Optional[str]] = [category, None] if category else [None]

    rows: list[tuple] = []
    best_fallback: list[tuple] = []
    for use_cat in cat_prefs:
        for use_tier, use_arch in ta_attempts:
            cand = _filter(all_rows, use_tier, use_arch, use_cat)
            if len(cand) > len(best_fallback):
                best_fallback = cand
            if len(cand) >= n:
                rows = cand
                break
        if rows:
            break
    if not rows:
        rows = best_fallback

    # Score by distance-to-benchmark on this feature, drop rows with no value.
    scored: list[tuple[float, Video, VideoFeatures, Channel]] = []
    for video, feat, channel in rows:
        val = _feature_value(video, feature)
        if val is None:
            continue
        scored.append((abs(val - benchmark_value), video, feat, channel))

    scored.sort(key=lambda t: t[0])
    out: list[ExampleVideo] = []
    for _d, video, feat, channel in scored[:n]:
        val = _feature_value(video, feature)
        if val is None:
            continue
        out.append(
            ExampleVideo(
                video_id=video.id,
                title=video.title,
                channel=channel.title,
                value=val,
                benchmark_value=benchmark_value,
                duration_seconds=video.duration_seconds,
            )
        )
    return out
