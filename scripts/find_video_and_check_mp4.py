"""Find an IG video by title fragment, check its mp4 + thumbnail file existence."""
import sys
from pathlib import Path

from sqlalchemy import select

from creative_director.config import settings
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video


def main(title_fragment: str) -> None:
    archive = settings.video_archive_dir or Path("data/videos")
    with session_scope() as s:
        rows = s.execute(
            select(Video, Channel)
            .join(Channel, Video.channel_id == Channel.id)
            .where(Video.title.like(f"%{title_fragment}%"))
            .limit(5)
        ).all()
        for video, channel in rows:
            mp4 = archive / f"{video.id}.mp4"
            print(f"video_id : {video.id}")
            print(f"  title  : {video.title}")
            print(f"  channel: {channel.title} (niche={channel.niche}, subs={channel.subscriber_count})")
            print(f"  mp4    : {mp4} exists={mp4.exists()} size={mp4.stat().st_size if mp4.exists() else 'n/a'}")
            print(f"  thumbnail_path: {video.thumbnail_path}")
            print(f"  thumbnail_url : {video.thumbnail_url}")
            print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "body will always")
