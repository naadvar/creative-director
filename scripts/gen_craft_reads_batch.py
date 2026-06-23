"""Concurrent craft-read backfill — pulls mp4s from R2, runs the configured craft-read
model (Qwen via DeepInfra if .env CRAFT_READ_* is set), caches to VideoFeatures.craft_read.

    python -m scripts.gen_craft_reads_batch <total_limit> [workers]

Stratified across the 4 IG niches, skips reels that already have a craft_read (resumable),
retries transient failures once. Workers only do R2-download + VLM call; DB writes happen
on the main thread (SQLite is single-writer), so there's no write contention.
"""
from __future__ import annotations

import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError

from creative_director.advice.craft_xray import SCHEMA_VERSION, extract_craft_read
from creative_director.config import settings
from creative_director.storage import media
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

NICHES = ("ig_fitness", "ig_food", "ig_travel", "ig_fashion")


def pick_targets(total: int, niches: tuple = NICHES, force: bool = False) -> list[tuple]:
    """force=True re-selects reels that ALREADY have a craft_read (to regenerate
    them in place on a new engine), instead of only the ones still missing one."""
    per = max(1, total // len(niches))
    out = []
    with session_scope() as s:
        for n in niches:
            q = (select(Video.id, Video.duration_seconds, Video.title)
                 .join(Channel, Channel.id == Video.channel_id)
                 .join(VideoFeatures, VideoFeatures.video_id == Video.id)
                 .where(VideoFeatures.vlm_perception.isnot(None),
                        Channel.niche == n, Channel.id.notlike("upch_%")))
            if force:
                # Resumable regen: reels missing a read OR not yet on the current
                # engine schema. Reels already regenerated (schema_version==current)
                # are skipped, so the run can stop/resume freely.
                q = q.where(or_(
                    VideoFeatures.craft_read.is_(None),
                    func.json_extract(VideoFeatures.craft_read, "$.schema_version")
                    != SCHEMA_VERSION,
                ))
            else:
                q = q.where(VideoFeatures.craft_read.is_(None))
            rows = s.execute(q.limit(per)).all()
            out += [(vid, n, dur, title) for vid, dur, title in rows]
    return out


def work(t: tuple):
    vid, niche, dur, title = t
    tmp = Path(tempfile.gettempdir()) / f"cb_{vid}.mp4"
    try:
        media._client().download_file(settings.r2_bucket, media.video_key(vid), str(tmp))
        read = extract_craft_read(str(tmp), niche=niche, caption=title, duration_s=dur)
        if read is None:  # one retry for a transient VLM/rate-limit hiccup
            time.sleep(3)
            read = extract_craft_read(str(tmp), niche=niche, caption=title, duration_s=dur)
        return vid, read
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{vid}: {type(e).__name__}: {str(e)[:120]}")
        return vid, None
    finally:
        tmp.unlink(missing_ok=True)


def store(vid: str, read: dict) -> None:
    for attempt in range(4):  # SQLite 'database is locked' retry
        try:
            with session_scope() as s:
                row = s.query(VideoFeatures).filter(VideoFeatures.video_id == vid).first()
                row.craft_read = read
            return
        except OperationalError:
            time.sleep(0.5 * (attempt + 1))
    logger.warning(f"{vid}: DB write failed after retries")


def main(total: int, workers: int, niches: tuple = NICHES, force: bool = False) -> None:
    targets = pick_targets(total, niches, force)
    logger.info(f"targets: {len(targets)} reels (niches={niches}, force={force}, workers={workers}, "
                f"openai={bool(settings.craft_read_base_url)} model={settings.craft_read_model})")
    t0 = time.time()
    ok = fail = done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, t) for t in targets]
        for f in as_completed(futs):
            vid, read = f.result()
            done += 1
            if read:
                store(vid, read)
                ok += 1
            else:
                fail += 1
            if done % 10 == 0 or done == len(targets):
                el = time.time() - t0
                rate = done / el * 60 if el else 0
                eta = (len(targets) - done) / (done / el) if done else 0
                logger.info(f"  {done}/{len(targets)} ok={ok} fail={fail} "
                            f"{el:.0f}s ({rate:.0f}/min, eta {eta/60:.0f}m)")
    logger.info(f"DONE ok={ok} fail={fail} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [int(a) for a in args if a.isdigit()]
    niche_args = tuple(a for a in args if a.startswith("ig_"))
    total = nums[0] if nums else 24
    workers = nums[1] if len(nums) > 1 else 8
    force = "force" in args  # regenerate reels that already have a read (new engine)
    # Single-niche run: pass e.g. `ig_fitness` to pull ALL remaining reels of that
    # niche (per = total, so set total >= the remaining count). Add `force` to redo
    # reels that already have a craft_read.
    main(total, workers, niche_args or NICHES, force)
