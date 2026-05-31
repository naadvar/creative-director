"""Do timeline seconds align with the archived mp4? (EDL cuts depend on it.)

    python -m scripts.diag_durations

For a few reels prints: DB duration_seconds, timeline row count + max second,
and the actual mp4 container duration. If timeline-rows ~= mp4-seconds, the
EDL segment seconds map straight onto the player. A big gap = misaligned cuts.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import func, select

from creative_director.config import settings
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoTimeline

IDS = ["ig_DXH-HlTkRBJ", "ig_DYFn0yeuZAw", "ig_DWPHyPBDvBM", "ig_DUypLNrgfza"]


def _mp4_seconds(video_id: str) -> str:
    archive = settings.video_archive_dir or Path("data/videos")
    path = Path(archive) / f"{video_id}.mp4"
    if not path.exists():
        return "no-file"
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=20,
        )
        return f"{float(out.stdout.strip()):.1f}" if out.stdout.strip() else f"err:{out.stderr.strip()[:40]}"
    except FileNotFoundError:
        return "no-ffprobe"
    except Exception as e:  # noqa: BLE001
        return f"err:{e}"


def main() -> None:
    with session_scope() as s:
        for vid in IDS:
            v = s.get(Video, vid)
            if v is None:
                print(f"{vid}: not in DB")
                continue
            cnt, mn, mx = s.execute(
                select(func.count(VideoTimeline.second),
                       func.min(VideoTimeline.second),
                       func.max(VideoTimeline.second))
                .where(VideoTimeline.video_id == vid)
            ).one()
            print(
                f"{vid}: duration_seconds={v.duration_seconds}  "
                f"timeline rows={cnt} (min={mn} max={mx})  mp4={_mp4_seconds(vid)}s"
            )


if __name__ == "__main__":
    main()
