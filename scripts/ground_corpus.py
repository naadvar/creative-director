"""Apply the grounding gate to the existing v3 craft reads (no re-reading the videos
— reuses the stored read + vlm_perception + transcript). Stamps grounded=true/false,
suppresses materially-fabricated reads, fixes redundant biggest_opportunity.

    python -m scripts.ground_corpus [limit] [workers] [ig_fitness]

Resumable: only reels whose read lacks a `grounded` field are selected, so a
stop/restart skips everything already gated. One cheap text-only Qwen call per reel.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from creative_director.advice.craft_xray import SCHEMA_VERSION, ground_and_gate
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures


def pick(niche: str, limit: int) -> list[tuple]:
    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Video.title, VideoFeatures.craft_read,
                   VideoFeatures.vlm_perception, VideoFeatures.transcript,
                   VideoFeatures.thumb_text)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            # No schema_version filter: the untreated niches are schema_version=1 and
            # still need gating. `grounded IS NULL` is the resumability + only-untreated
            # key (already-gated fitness reads have grounded set, so they are skipped).
            .where(Channel.niche == niche, Channel.id.notlike("upch_%"),
                   VideoFeatures.craft_read.isnot(None),
                   func.json_extract(VideoFeatures.craft_read, "$.grounded").is_(None))
            .limit(limit)
        ).all()
    return [(vid, title, dict(read), vp, tr, thumb) for vid, title, read, vp, tr, thumb in rows]


def work(t: tuple):
    vid, title, read, vp, tr, thumb = t
    try:
        return vid, ground_and_gate(read, vp, tr, title, thumb)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{vid}: {type(e).__name__}: {str(e)[:100]}")
        return vid, None


def store(vid: str, gated: dict) -> None:
    for attempt in range(4):
        try:
            with session_scope() as s:
                row = s.query(VideoFeatures).filter(VideoFeatures.video_id == vid).first()
                if row is not None:
                    row.craft_read = gated
            return
        except OperationalError:
            time.sleep(0.5 * (attempt + 1))


def main(limit: int, workers: int, niche: str) -> None:
    targets = pick(niche, limit)
    logger.info(f"grounding gate: {len(targets)} {niche} reels (workers={workers})")
    t0 = time.time()
    done = ok = fail = suppressed = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, t) for t in targets]
        for fu in as_completed(futs):
            vid, gated = fu.result()
            done += 1
            if gated is not None:
                store(vid, gated)
                ok += 1
                if gated.get("grounded") is False:
                    suppressed += 1
            else:
                fail += 1
            if done % 25 == 0 or done == len(targets):
                el = time.time() - t0
                eta = (len(targets) - done) / (done / el) if done else 0
                logger.info(f"  {done}/{len(targets)} ok={ok} fail={fail} suppressed={suppressed} "
                            f"({done/el*60:.0f}/min, eta {eta/60:.0f}m)")
    logger.info(f"DONE ok={ok} fail={fail} suppressed={suppressed} "
                f"({100*suppressed/max(ok,1):.1f}%) in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [int(a) for a in args if a.isdigit()]
    niche = next((a for a in args if a.startswith("ig_")), "ig_fitness")
    limit = nums[0] if nums else 60
    workers = nums[1] if len(nums) > 1 else 12
    main(limit, workers, niche)
