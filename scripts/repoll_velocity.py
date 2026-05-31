"""Re-poll stats for recently published videos to build velocity curves.

Run periodically (e.g., daily via Windows Task Scheduler / cron). Appends a
VelocitySnapshot row for each in-window video. The label generator later turns
these into growth-curve features.
"""
from datetime import datetime, timedelta

import typer
from loguru import logger
from sqlalchemy import select

from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import VelocitySnapshot, Video
from creative_director.youtube.client import get_youtube_client
from creative_director.youtube.videos import fetch_videos


app = typer.Typer(add_completion=False)


@app.command()
def main(
    max_age_days: int = typer.Option(45, help="Only re-poll videos published within this window"),
):
    init_db()
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    with session_scope() as session:
        # Exclude Instagram videos -- this is the YouTube Data API repoll;
        # ig_* IDs aren't valid YouTube IDs. (IG velocity would need its own
        # Apify re-poll, not built yet.)
        videos = (
            session.execute(
                select(Video)
                .where(Video.published_at >= cutoff)
                .where(~Video.id.like("ig_%"))
            )
            .scalars()
            .all()
        )
        ids = [v.id for v in videos]
        published_lookup = {v.id: v.published_at for v in videos}

    logger.info(f"Re-polling stats for {len(ids)} videos")
    if not ids:
        return

    youtube = get_youtube_client()

    for item in fetch_videos(youtube, ids):
        vid = item["id"]
        stats = item.get("statistics", {})
        published = published_lookup.get(vid)
        if not published:
            continue
        hours = (datetime.utcnow() - published).total_seconds() / 3600.0
        with session_scope() as session:
            session.add(
                VelocitySnapshot(
                    video_id=vid,
                    captured_at=datetime.utcnow(),
                    hours_since_publish=hours,
                    view_count=int(stats.get("viewCount", 0)),
                    like_count=int(stats["likeCount"]) if "likeCount" in stats else None,
                    comment_count=int(stats["commentCount"]) if "commentCount" in stats else None,
                    favorite_count=int(stats["favoriteCount"]) if "favoriteCount" in stats else None,
                )
            )


if __name__ == "__main__":
    app()
