"""CLI: download video files for videos that need feature extraction.

Stage 1 of the cloud-extraction plan. Downloading is network-bound and light
on CPU (unlike CLIP/Whisper extraction, which pins this laptop at TjMAX), so it
runs safely on the local machine. The downloaded files are then uploaded to
Drive and featurised on a Colab GPU.

Scope: a niche's videos that carry an age-banded label but have no features and
no downloaded file yet. Idempotent — re-run after an interruption and it skips
files already present.

    python -m scripts.download_videos --niche fitness --limit 3   # smoke test
    python -m scripts.download_videos --niche fitness             # full run
"""
from pathlib import Path

import typer
from loguru import logger
from sqlalchemy import select

from creative_director.config import settings
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel
from creative_director.utils.tempfiles import download_video_to

app = typer.Typer(add_completion=False)

_AGED_SCHEMES = ("views_per_sub_aged_v1", "within_channel_aged_v1")


@app.command()
def main(
    niche: str = typer.Option("fitness", help="Niche to scope the run to"),
    limit: int = typer.Option(0, help="Max videos to download (0 = all targets)"),
    all_labeled: bool = typer.Option(
        False, help="Download every niche video (not just age-banded-labelled ones)"
    ),
):
    init_db()
    dest_dir = settings.video_archive_dir or Path("./data/videos")

    with session_scope() as s:
        q = (
            select(Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .outerjoin(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(
                Channel.niche == niche,
                VideoFeatures.video_id.is_(None),
                Video.video_file_path.is_(None),
            )
        )
        if not all_labeled:
            q = q.join(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme.in_(_AGED_SCHEMES)),
            )
        target_ids = sorted(set(s.execute(q).scalars().all()))

    if limit:
        target_ids = target_ids[:limit]
    logger.info(f"{len(target_ids)} videos to download (niche={niche}) -> {dest_dir}")

    done = 0
    failed = 0
    for video_id in target_ids:
        try:
            path = download_video_to(video_id, dest_dir)
            with session_scope() as s:
                video = s.get(Video, video_id)
                if video is not None:
                    video.video_file_path = str(path)
            done += 1
            logger.info(f"[{done}/{len(target_ids)}] {video_id}: downloaded")
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"{video_id}: download failed: {e}")

    logger.info(f"Done. {done} downloaded, {failed} failed.")


if __name__ == "__main__":
    app()
