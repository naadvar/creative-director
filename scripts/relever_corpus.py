"""Richer levers via VLM re-read: re-watch each target reel's frames (fetched from R2)
and replace a SILENT or legibility-only biggest_opportunity with one grounded, high-
leverage craft lever (hook / pacing / structure / framing / payoff). Vision-grounded, so
it does not confabulate like the text-only synthesis.

    python -m scripts.relever_corpus [limit] [workers] [ig_fitness] [dump=PATH]

Targets reads whose lever is silent OR text-legibility, and that have not been re-read yet
(lever_source != 'reread'). Resumable. dump=PATH = dry run (write before/after to JSON, no
DB write). One Qwen-VL call + one R2 fetch + frame extraction per reel (~$0.0016 + egress).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError

from creative_director.advice.craft_xray import (SCHEMA_VERSION, _is_silent,
                                                 extract_craft_lever)
from creative_director.config import settings
from creative_director.storage import media
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

_GROUNDED = func.coalesce(func.json_extract(VideoFeatures.craft_read, "$.grounded"), 1)
_BO = func.json_extract(VideoFeatures.craft_read, "$.biggest_opportunity")
_DIM = func.json_extract(VideoFeatures.craft_read, "$.opportunity_dimension")
_SRC = func.json_extract(VideoFeatures.craft_read, "$.lever_source")


def pick(niche: str, limit: int, all_reads: bool = False) -> list[tuple]:
    """Select reels to re-lever. Default (fitness-treatment) mode targets SILENT or
    text-legibility levers on the current schema. `all_reads=True` (untreated-niche
    backfill) targets EVERY grounded, not-yet-relevered read regardless of schema or
    dimension — used to replace the original boilerplate/intent-fighting levers on
    travel/food/fashion with grounded, reveal-respecting ones."""
    conds = [Channel.niche == niche, Channel.id.notlike("upch_%"),
             VideoFeatures.craft_read.isnot(None), _GROUNDED != 0, _SRC.is_(None)]
    if not all_reads:
        conds += [func.json_extract(VideoFeatures.craft_read, "$.schema_version") == SCHEMA_VERSION,
                  or_(_BO.like("%well-executed as is%"), _DIM == "text")]
    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Video.title, Video.duration_seconds, VideoFeatures.craft_read)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(*conds)
            .order_by(Video.id)  # ig ids are hash-like -> mixes creators, stable for resume
            .limit(limit)
        ).all()
    return [(vid, title, dur, dict(read)) for vid, title, dur, read in rows]


def _fetch(vid: str, dest_dir: str) -> Path:
    p = Path(dest_dir) / f"{vid}.mp4"
    media._client().download_file(settings.r2_bucket, media.video_key(vid), str(p))
    return p


def work(t: tuple, dump: bool, niche: str = "ig_fitness"):
    vid, title, dur, read = t
    old_bo = read.get("biggest_opportunity") or ""
    old_dim = read.get("opportunity_dimension") or ""
    try:
        with tempfile.TemporaryDirectory() as td:
            mp4 = _fetch(vid, td)
            lev = extract_craft_lever(str(mp4), niche=niche, caption=title, duration_s=dur,
                                      payoff=read.get("payoff"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{vid}: {type(e).__name__}: {str(e)[:90]}")
        return None
    applied = False
    if (lev and lev.get("lever") and not _is_silent(lev["lever"])
            and (lev.get("confidence") or "").lower() in ("high", "medium")):
        read["biggest_opportunity"] = lev["lever"]
        read["opportunity_dimension"] = lev.get("vocabulary") or ""
        if lev.get("timestamp"):
            read["lever_timestamp"] = lev["timestamp"]
        applied = True
    read["lever_source"] = "reread"  # mark processed either way (resumable)
    rec = None
    if dump:
        rec = {"video_id": vid, "caption": (title or "")[:160], "duration_s": dur,
               "old_lever": old_bo, "old_dimension": old_dim,
               "new_lever": read.get("biggest_opportunity") or "",
               "new_dimension": read.get("opportunity_dimension") or "",
               "timestamp": read.get("lever_timestamp") or "", "applied": applied,
               "confidence": (lev or {}).get("confidence") or ""}
    return vid, read, applied, (read.get("opportunity_dimension") or "none"), rec


def store(vid: str, read: dict) -> None:
    for attempt in range(4):
        try:
            with session_scope() as s:
                row = s.query(VideoFeatures).filter(VideoFeatures.video_id == vid).first()
                if row is not None:
                    row.craft_read = read
            return
        except OperationalError:
            time.sleep(0.5 * (attempt + 1))


def main(limit: int, workers: int, niche: str, dump_path: str | None,
         all_reads: bool = False) -> None:
    targets = pick(niche, limit, all_reads=all_reads)
    dump = dump_path is not None
    logger.info(f"re-lever: {len(targets)} {'ALL-kept' if all_reads else 'silent/legibility'} "
                f"{niche} reels (workers={workers}, mode={'DUMP' if dump else 'WRITE-DB'})")
    t0 = time.time()
    done = ok = fail = upgraded = 0
    records, vocab = [], {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, t, dump, niche) for t in targets]
        for fu in as_completed(futs):
            r = fu.result()
            done += 1
            if r is None:
                fail += 1
                continue
            vid, read, applied, dim, rec = r
            ok += 1
            if applied:
                upgraded += 1
                vocab[dim] = vocab.get(dim, 0) + 1
            if dump:
                records.append(rec)
            else:
                store(vid, read)
            if done % 10 == 0 or done == len(targets):
                el = time.time() - t0
                logger.info(f"  {done}/{len(targets)} ok={ok} fail={fail} upgraded={upgraded} "
                            f"({done/el*60:.0f}/min)")
    if dump:
        Path(dump_path).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        logger.info(f"wrote {len(records)} records -> {dump_path}")
    logger.info(f"DONE ok={ok} fail={fail} upgraded={upgraded} vocab={vocab} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [int(a) for a in args if a.isdigit()]
    niche = next((a for a in args if a.startswith("ig_")), "ig_fitness")
    dump_path = next((a.split("=", 1)[1] for a in args if a.startswith("dump=")), None)
    all_reads = "all" in args  # untreated-niche backfill: re-lever EVERY kept read
    limit = nums[0] if nums else 20
    workers = nums[1] if len(nums) > 1 else 6
    main(limit, workers, niche, dump_path, all_reads=all_reads)
