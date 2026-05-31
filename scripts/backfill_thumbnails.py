"""Backfill grid thumbnails for niches whose JPGs aren't in R2.

The new IG niches were metadata-ingested + GPU-extracted for features, but the
thumbnail JPGs were never saved (and their Instagram CDN URLs have since
expired -> 403). This grabs an early frame from each video's mp4 (already in R2
at videos/{id}.mp4) and uploads it to thumbnails/{id}.jpg, so the corpus browser
shows real previews and /videos/{id}/thumbnail resolves.

Resumable (skips ids already in R2), tolerant (logs + counts failures), threaded.

    python -m scripts.backfill_thumbnails                       # all 3 new niches
    python -m scripts.backfill_thumbnails --limit 3             # smoke test
    python -m scripts.backfill_thumbnails --niches ig_food
"""
from __future__ import annotations

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import typer
from loguru import logger
from sqlalchemy import select

from creative_director.config import settings
from creative_director.storage import media
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video

app = typer.Typer(add_completion=False)


def _make_thumb(video_id: str) -> str:
    """Grab an early frame from the R2 mp4 -> upload as thumbnails/{id}.jpg.

    Returns a short status token: skip | ok | no_open | no_frame | error.
    """
    tkey = media.thumb_key(video_id)
    if media.exists(tkey):
        return "skip"
    url = media.url_for(media.video_key(video_id))  # presigned GET
    cap = cv2.VideoCapture(url)
    try:
        if not cap.isOpened():
            return "no_open"
        # Read ~15 frames and keep the last decoded one — cheaply skips a black
        # intro frame without seeking (seeking a streamed URL is unreliable).
        frame = None
        for _ in range(15):
            ok, f = cap.read()
            if not ok:
                break
            frame = f
        if frame is None:
            return "no_frame"
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            media.upload(Path(path), tkey, "image/jpeg")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        return "ok"
    finally:
        cap.release()


@app.command()
def main(
    niches: str = typer.Option("ig_food,ig_travel,ig_fashion", help="Comma-separated niches"),
    workers: int = typer.Option(12, help="Parallel download/decode workers"),
    limit: int = typer.Option(0, help="Max videos (0 = all; use a few for a smoke test)"),
) -> None:
    if not settings.r2_enabled:
        raise RuntimeError("R2 not configured (need write creds in .env)")
    targets = [n.strip() for n in niches.split(",") if n.strip()]

    with session_scope() as s:
        ids = sorted(
            set(
                s.execute(
                    select(Video.id)
                    .join(Channel, Channel.id == Video.channel_id)
                    .where(Channel.niche.in_(targets))
                )
                .scalars()
                .all()
            )
        )
    if limit:
        ids = ids[:limit]
    logger.info(f"{len(ids)} videos across {targets} (workers={workers})")

    counts: dict[str, int] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_make_thumb, vid): vid for vid in ids}
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001
                r = "error"
                logger.warning(f"{futs[fut]}: {e}")
            counts[r] = counts.get(r, 0) + 1
            done += 1
            if done % 200 == 0:
                logger.info(f"[{done}/{len(ids)}] {counts}")

    logger.info(f"DONE {counts}")


if __name__ == "__main__":
    app()
