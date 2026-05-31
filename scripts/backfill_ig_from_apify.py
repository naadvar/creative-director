"""Backfill IG video rows from an existing Apify Reel Scraper run's dataset.

Useful when:
  - the ingest was killed mid-process (some reels never made it to the DB)
  - new metadata columns were added to the schema after the original ingest
    (need to repopulate music_info, mentions, tagged_users, etc. without
    re-running the actor)

Free (dataset reads are ~$4e-7 each). mp4 downloads are best-effort -- the
``videoUrl`` Instagram CDN URLs expire in hours, so older runs may yield
metadata-only rows. Within Apify's 7-day dataset retention, the dataset
itself is still readable.

    python -m scripts.backfill_ig_from_apify --run-id e6X7ZIUbsCIOEIRKj
    python -m scripts.backfill_ig_from_apify --run-id <id> --no-download
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from sqlalchemy import select

from creative_director.apify.client import get_client
from creative_director.config import settings
from creative_director.ingestion.instagram_apify_pipeline import (
    REEL_DURATION_LIMIT,
    _add_ig_velocity,
    _download,
    _upsert_ig_video,
)
from creative_director.storage import media
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel, Video

app = typer.Typer(add_completion=False)


@app.command()
def main(
    run_id: str = typer.Option(..., help="Apify actor run ID to re-fetch dataset from"),
    niche: Optional[str] = typer.Option(
        None,
        help="Only ingest reels whose owner already has a Channel in this niche "
        "(filters the actor's bleed-in from non-seed accounts).",
    ),
    download: bool = typer.Option(
        True, help="Best-effort mp4/thumbnail download for missing files"
    ),
    shorts_only: bool = typer.Option(True, help="Skip videos longer than 90s"),
):
    init_db()
    client = get_client()
    run = client.run(run_id).get()
    dataset_id = run["defaultDatasetId"]
    logger.info(f"Reading dataset {dataset_id} from run {run_id}")

    # When a niche is given, restrict to owners that are already seeded channels
    # in that niche (the profile-scraper step ran before the reel pull, so the
    # legit creators exist). Drops the reel scraper's recommend-bleed.
    valid_owners: Optional[set[str]] = None
    if niche:
        with session_scope() as s:
            handles = s.execute(
                select(Channel.handle).where(Channel.niche == niche)
            ).scalars().all()
        valid_owners = {(h or "").lower() for h in handles if h}
        logger.info(f"niche={niche}: {len(valid_owners)} seeded owners to keep")

    items = list(client.dataset(dataset_id).iterate_items())
    logger.info(f"Dataset has {len(items)} items")

    archive = settings.video_archive_dir or Path("data/videos")
    new_reels = 0
    updated_reels = 0
    skipped = 0

    # --- Phase 1: upsert metadata (fast, sequential) + collect download tasks ---
    tasks: list[tuple[str, Optional[str], Optional[str]]] = []
    for item in items:
        shortcode = item.get("shortCode")
        if not shortcode:
            skipped += 1
            continue
        owner = (item.get("ownerUsername") or "").lower()
        if not owner:
            skipped += 1
            continue
        if valid_owners is not None and owner not in valid_owners:
            skipped += 1  # reel scraper bleed-in from a non-seed account
            continue
        duration = int(item.get("videoDuration") or 0)
        if shorts_only and duration > REEL_DURATION_LIMIT:
            skipped += 1
            continue

        channel_id = f"ig_{owner}"
        video_id = f"ig_{shortcode}"
        try:
            with session_scope() as s:
                existing = s.get(Video, video_id)
                video = _upsert_ig_video(s, channel_id, video_id, item)
                if existing is None:
                    _add_ig_velocity(s, video, item)
                    new_reels += 1
                else:
                    updated_reels += 1
                # Path follows the {archive}/{id}.mp4 convention (valid on the
                # pod after rclone). Set in Phase 1 so the parallel Phase 2 needs
                # no DB writes -> avoids SQLite write contention under threads.
                video.video_file_path = str(archive / f"{video_id}.mp4")
                video.thumbnail_path = str(settings.thumbnail_dir / f"{video_id}.jpg")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{shortcode}: upsert failed: {e}")
            continue

        if download:
            video_url = item.get("downloadedVideo") or item.get("videoUrl")
            tasks.append((video_id, video_url, item.get("displayUrl")))

    logger.info(f"Phase 1 done: new={new_reels} updated={updated_reels} skipped={skipped}")

    # --- Phase 2: parallel download + R2 mirror. IG CDN URLs expire within
    #     ~hours, so we race them with a thread pool instead of a multi-hour
    #     sequential loop that would lose the back half of the dataset. ---
    download_ok = 0
    download_fail = 0
    if download and tasks:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_one(t: tuple[str, Optional[str], Optional[str]]) -> bool:
            video_id, video_url, thumb_url = t
            dest = archive / f"{video_id}.mp4"
            got_video = dest.exists()
            if video_url and not got_video:
                try:
                    _download(video_url, dest)
                    got_video = True
                except Exception:  # noqa: BLE001
                    return False  # URL likely expired
            thumb = settings.thumbnail_dir / f"{video_id}.jpg"
            if thumb_url and not thumb.exists():
                try:
                    _download(thumb_url, thumb)
                except Exception:  # noqa: BLE001
                    pass
            if settings.r2_enabled:
                try:
                    if dest.exists():
                        media.mirror_video(dest, video_id)
                    if thumb.exists():
                        media.mirror_thumbnail(thumb, video_id)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"{video_id}: R2 upload failed: {e}")
                if settings.r2_prune_local:
                    for p in (dest, thumb):
                        try:
                            if p.exists():
                                p.unlink()
                        except OSError:
                            pass
            return got_video

        logger.info(f"Phase 2: downloading {len(tasks)} reels with 16 workers ...")
        with ThreadPoolExecutor(max_workers=16) as ex:
            futures = [ex.submit(_fetch_one, t) for t in tasks]
            for i, fut in enumerate(as_completed(futures), 1):
                if fut.result():
                    download_ok += 1
                else:
                    download_fail += 1
                if i % 200 == 0:
                    logger.info(f"  {i}/{len(tasks)} (ok={download_ok}, fail={download_fail})")

    print()
    print("=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"Dataset items:        {len(items)}")
    print(f"New reels in DB:      {new_reels}")
    print(f"Updated existing:     {updated_reels} (metadata refreshed)")
    print(f"Skipped:              {skipped}")
    if download:
        print(f"mp4 downloads OK:     {download_ok}")
        print(f"mp4 downloads failed: {download_fail} (URL expired)")


if __name__ == "__main__":
    app()
