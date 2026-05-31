"""Transient video file handling.

The pipeline never persists video files. ``transient_video`` downloads a video
via yt-dlp, yields the local path to feature extractors, and deletes the file
on context exit (success or failure).
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import yt_dlp
from loguru import logger

from creative_director.config import settings


YOUTUBE_VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"


@contextmanager
def transient_video(video_id: str, max_height: Optional[int] = None) -> Iterator[Path]:
    """Download a video to a temp path, yield the path, then delete it."""
    max_height = max_height or settings.max_video_height
    settings.temp_video_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(
        settings.temp_video_dir / f"{video_id}_{uuid.uuid4().hex}.%(ext)s"
    )

    ydl_opts = {
        "format": (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best"
        ),
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "merge_output_format": "mp4",
        "retries": 2,
    }
    if settings.ytdlp_proxy:
        # Residential proxy (e.g. Decodo) avoids "Sign in to confirm you're not a bot"
        # errors when running yt-dlp from a datacenter IP like Colab.
        ydl_opts["proxy"] = settings.ytdlp_proxy

    path: Optional[Path] = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                YOUTUBE_VIDEO_URL.format(video_id=video_id), download=True
            )
            path = Path(ydl.prepare_filename(info))
            if not path.exists():
                alt = path.with_suffix(".mp4")
                if alt.exists():
                    path = alt
        if not path or not path.exists():
            raise FileNotFoundError(f"yt-dlp did not produce a file for {video_id}")
        yield path
    finally:
        if path and path.exists():
            try:
                os.remove(path)
            except OSError as e:
                logger.warning(f"Failed to delete temp video {path}: {e}")


def download_video_to(video_id: str, dest_dir: Path, max_height: Optional[int] = None) -> Path:
    """Download a video to ``dest_dir/<video_id>.mp4`` and return its path.

    Unlike ``transient_video``, this does NOT delete the file. Used by stage-1
    of the hybrid pipeline: download locally, sync to Drive, process on Colab.

    Returns the existing file if already downloaded (idempotent).
    """
    max_height = max_height or settings.max_video_height
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    final_path = dest_dir / f"{video_id}.mp4"
    if final_path.exists():
        return final_path

    out_template = str(dest_dir / f"{video_id}.%(ext)s")
    ydl_opts = {
        "format": (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best"
        ),
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "merge_output_format": "mp4",
        "retries": 2,
    }
    if settings.ytdlp_proxy:
        ydl_opts["proxy"] = settings.ytdlp_proxy

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(YOUTUBE_VIDEO_URL.format(video_id=video_id), download=True)
        written = Path(ydl.prepare_filename(info))
        if written.suffix != ".mp4":
            mp4 = written.with_suffix(".mp4")
            if mp4.exists():
                written = mp4

    # Normalize to <video_id>.mp4
    if written != final_path:
        try:
            written.rename(final_path)
        except OSError:
            # Fall back to copy + delete if rename fails (cross-volume etc.)
            import shutil

            shutil.copy2(written, final_path)
            try:
                written.unlink()
            except OSError:
                pass
    if not final_path.exists():
        raise FileNotFoundError(f"yt-dlp did not produce a file for {video_id}")
    return final_path
