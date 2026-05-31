"""Discover and verify candidate channels for a niche.

Searches the YouTube Data API for channels matching a set of queries, then
verifies each: subscriber count and how many of its last 30 uploads are
Shorts (<=60s). Prints a ranked table so you can curate a seed list.

Quota: each search costs 100 units; each channel verify ~3 units. A typical
run (6 queries x 15 channels) uses ~900 units of the 10,000/day budget.

Example:
    python -m scripts.discover_channels \\
        --queries "fitness,home workout,calisthenics,gym tips,fitness coach,bodyweight" \\
        --min-shorts 6
"""
from typing import Optional

import typer
from loguru import logger

from creative_director.youtube.channels import iter_upload_video_ids
from creative_director.youtube.client import get_youtube_client
from creative_director.youtube.videos import fetch_videos, parse_iso_duration


app = typer.Typer(add_completion=False)


def search_channel_ids(youtube, query: str, max_results: int = 15) -> list[str]:
    resp = (
        youtube.search()
        .list(part="snippet", q=query, type="channel", maxResults=max_results)
        .execute()
    )
    return [it["snippet"]["channelId"] for it in resp.get("items", [])]


def verify_channel(youtube, channel_id: str) -> Optional[dict]:
    resp = (
        youtube.channels()
        .list(part="snippet,statistics,contentDetails", id=channel_id)
        .execute()
    )
    items = resp.get("items", [])
    if not items:
        return None
    item = items[0]
    uploads = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads:
        return None
    ids = list(iter_upload_video_ids(youtube, uploads, max_videos=30))
    shorts = 0
    for v in fetch_videos(youtube, ids):
        d = parse_iso_duration(v.get("contentDetails", {}).get("duration", ""))
        if 0 < d <= 60:
            shorts += 1
    return {
        "channel_id": channel_id,
        "handle": item["snippet"].get("customUrl"),
        "title": item["snippet"].get("title", ""),
        "subs": int(item["statistics"].get("subscriberCount", 0)),
        "shorts": shorts,
        "checked": len(ids),
    }


def _size_bucket(subs: int) -> str:
    if subs < 50_000:
        return "micro"
    if subs < 500_000:
        return "mid"
    return "large"


@app.command()
def main(
    queries: str = typer.Option(..., help="Comma-separated search queries"),
    min_shorts: int = typer.Option(6, help="Minimum Shorts in last 30 uploads to keep"),
    per_query: int = typer.Option(15, help="Channels pulled per query"),
):
    youtube = get_youtube_client()
    seen: set[str] = set()
    candidates: list[dict] = []

    for q in [x.strip() for x in queries.split(",") if x.strip()]:
        logger.info(f"Searching channels for: {q!r}")
        try:
            cids = search_channel_ids(youtube, q, per_query)
        except Exception as e:
            logger.warning(f"search failed for {q!r}: {e}")
            continue
        for cid in cids:
            if cid in seen:
                continue
            seen.add(cid)
            try:
                info = verify_channel(youtube, cid)
            except Exception as e:
                logger.warning(f"verify failed for {cid}: {e}")
                continue
            if info and info["shorts"] >= min_shorts:
                info["bucket"] = _size_bucket(info["subs"])
                candidates.append(info)
                logger.info(
                    f"  KEEP {info['handle']} | {info['subs']:,} subs "
                    f"| {info['shorts']}/{info['checked']} shorts | {info['bucket']}"
                )

    candidates.sort(key=lambda c: (-c["shorts"], -c["subs"]))
    print()
    print(f"{'handle':<30}{'subs':>13}  {'shorts':>8}  bucket")
    print("-" * 64)
    for c in candidates:
        handle = (c["handle"] or c["channel_id"])
        print(f"{handle:<30}{c['subs']:>13,}  {c['shorts']:>4}/{c['checked']:<3}  {c['bucket']}")
    print()
    by_bucket: dict[str, int] = {}
    for c in candidates:
        by_bucket[c["bucket"]] = by_bucket.get(c["bucket"], 0) + 1
    print(f"{len(candidates)} channels pass (min_shorts>={min_shorts}). By size: {by_bucket}")
    print("\nYAML-ready handles:")
    for c in candidates:
        h = c["handle"] or c["channel_id"]
        print(f'  - "{h}"')


if __name__ == "__main__":
    app()
