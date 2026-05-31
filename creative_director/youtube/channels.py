from typing import Iterator, Optional

from googleapiclient.discovery import Resource


def fetch_channel(youtube: Resource, channel_id: str) -> Optional[dict]:
    resp = (
        youtube.channels()
        .list(part="snippet,statistics,contentDetails", id=channel_id)
        .execute()
    )
    items = resp.get("items", [])
    return items[0] if items else None


def fetch_channel_by_handle(youtube: Resource, handle: str) -> Optional[dict]:
    handle = handle.lstrip("@")
    resp = (
        youtube.channels()
        .list(part="snippet,statistics,contentDetails", forHandle=handle)
        .execute()
    )
    items = resp.get("items", [])
    return items[0] if items else None


def resolve_channel(youtube: Resource, ref: str) -> Optional[dict]:
    """Accept either a channel ID (UC...) or an @handle and return the channel record."""
    if ref.startswith("@") or not ref.startswith("UC"):
        return fetch_channel_by_handle(youtube, ref)
    return fetch_channel(youtube, ref)


def iter_upload_video_ids(
    youtube: Resource, uploads_playlist_id: str, max_videos: int = 50
) -> Iterator[str]:
    """Yield up to ``max_videos`` recent video IDs from a channel's uploads playlist."""
    page_token: Optional[str] = None
    fetched = 0
    while fetched < max_videos:
        page_size = min(50, max_videos - fetched)
        resp = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=page_size,
                pageToken=page_token,
            )
            .execute()
        )
        for item in resp.get("items", []):
            yield item["contentDetails"]["videoId"]
            fetched += 1
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
