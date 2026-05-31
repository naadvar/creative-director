"""Creator-tier classification by subscriber/follower count.

Tiers match the seed-file batches we already curate for:
- SMALL: <100K followers (the primary target user for the product)
- MID:   100K-1M ("heart of the target band")
- LARGE: 1M+

For both YT (subscribers) and IG (followers), the platform-specific count is
stored on Channel.subscriber_count, refreshed when the channel is re-polled.
The daily CreativeDirector-DiscoverNewUploads task keeps this current. No
separate channel-level time-series exists, so we read the column directly.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from creative_director.storage.models import Channel, Video


TIER_SMALL = "small"
TIER_MID = "mid"
TIER_LARGE = "large"

TIERS = (TIER_SMALL, TIER_MID, TIER_LARGE)

# Tier boundaries by subscriber/follower count (inclusive lower).
_MID_THRESHOLD = 100_000
_LARGE_THRESHOLD = 1_000_000


def tier_for_count(count: Optional[int]) -> Optional[str]:
    """Tier for a given subscriber/follower count, or None if count is missing.

    Callers should treat None as 'tier unknown' and fall back to
    non-tier-stratified benchmarks rather than guessing.
    """
    if count is None or count < 0:
        return None
    if count >= _LARGE_THRESHOLD:
        return TIER_LARGE
    if count >= _MID_THRESHOLD:
        return TIER_MID
    return TIER_SMALL


def tier_for_channel(channel: Channel) -> Optional[str]:
    """Tier for a Channel row, using its current subscriber_count."""
    return tier_for_count(channel.subscriber_count)


def tier_for_video(session: Session, video_id: str) -> Optional[str]:
    """Tier of the channel that owns the given video. None if missing."""
    row = session.execute(
        select(Channel.subscriber_count)
        .join(Video, Video.channel_id == Channel.id)
        .where(Video.id == video_id)
    ).first()
    if not row:
        return None
    return tier_for_count(row[0])


def tier_distribution(session: Session, niche: Optional[str] = None) -> dict[str, int]:
    """Count of analyzable videos per tier (and 'unknown'). For sanity checks."""
    q = (
        select(Channel.subscriber_count)
        .join(Video, Video.channel_id == Channel.id)
    )
    if niche:
        q = q.where(Channel.niche == niche)
    counts: dict[str, int] = {t: 0 for t in TIERS}
    counts["unknown"] = 0
    for (sub,) in session.execute(q).all():
        bucket = tier_for_count(sub) or "unknown"
        counts[bucket] += 1
    return counts
