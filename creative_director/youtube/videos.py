import re
from datetime import datetime, timezone
from typing import Iterator

from googleapiclient.discovery import Resource


_ISO_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_iso_duration(s: str) -> int:
    """Parse YouTube's ISO 8601 duration (PT#H#M#S) into total seconds."""
    if not s:
        return 0
    m = _ISO_DURATION.fullmatch(s)
    if not m:
        return 0
    h, mi, se = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mi * 60 + se


def parse_published_at(s: str) -> datetime:
    """RFC3339 ('2024-08-12T14:23:45Z') -> naive UTC datetime."""
    return (
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )


def fetch_videos_batch(youtube: Resource, video_ids: list[str]) -> list[dict]:
    if not video_ids:
        return []
    if len(video_ids) > 50:
        raise ValueError("videos.list accepts at most 50 IDs per call")
    resp = (
        youtube.videos()
        .list(
            part="snippet,statistics,contentDetails,status",
            id=",".join(video_ids),
            maxResults=50,
        )
        .execute()
    )
    return resp.get("items", [])


def fetch_videos(youtube: Resource, video_ids: list[str]) -> Iterator[dict]:
    """Iterate over video records, batching at the API's 50-id limit."""
    for i in range(0, len(video_ids), 50):
        yield from fetch_videos_batch(youtube, video_ids[i : i + 50])
