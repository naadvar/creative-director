"""Backfill a prioritized, broad-vocabulary biggest_opportunity onto the SILENT gated
reads (currently 'well-executed as is') — synthesized from each read's blind_spots +
evidence, no video re-read. One cheap Qwen text call per reel.

    python -m scripts.synth_opportunity_corpus [limit] [workers] [ig_fitness] [dump=PATH]

dump=PATH  -> dry run: write before/after + evidence to a JSON file, DO NOT touch the DB
             (used for the pre-rollout adversarial confirmation).
Resumable: selects silent reads with no opportunity_dimension stamp yet.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from creative_director.advice.craft_xray import SCHEMA_VERSION, synthesize_opportunity
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures


def _vp_compact(vp):
    if not isinstance(vp, dict):
        return {}
    obs = [f"{o.get('frame_ts')}s [{o.get('kind')}]: {(o.get('text') or '')[:90]}"
           for o in (vp.get("observed") or [])[:5] if isinstance(o, dict)]
    return {"genre": vp.get("genre"), "format": vp.get("format"),
            "opening_shot": (vp.get("opening_shot") or "")[:200],
            "on_screen_text": (vp.get("on_screen_text") or "")[:200], "observed": obs}


def pick(niche: str, limit: int) -> list[tuple]:
    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Video.title, VideoFeatures.craft_read,
                   VideoFeatures.vlm_perception, VideoFeatures.transcript, VideoFeatures.thumb_text)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(Channel.niche == niche, Channel.id.notlike("upch_%"),
                   func.json_extract(VideoFeatures.craft_read, "$.schema_version") == SCHEMA_VERSION,
                   func.coalesce(func.json_extract(VideoFeatures.craft_read, "$.grounded"), 1) != 0,
                   func.json_extract(VideoFeatures.craft_read, "$.biggest_opportunity").like("%well-executed as is%"),
                   func.json_extract(VideoFeatures.craft_read, "$.opportunity_dimension").is_(None))
            .limit(limit)
        ).all()
    return [(vid, title, dict(read), vp, tr, thumb) for vid, title, read, vp, tr, thumb in rows]


def work(t: tuple, dump: bool):
    vid, title, read, vp, tr, thumb = t
    old_bo = read.get("biggest_opportunity") or ""
    try:
        new = synthesize_opportunity(read, vp, tr, title, thumb)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{vid}: {type(e).__name__}: {str(e)[:100]}")
        return None
    rec = None
    if dump:
        rec = {"video_id": vid, "caption": (title or "")[:200],
               "old_lever": old_bo, "new_lever": new.get("biggest_opportunity") or "",
               "vocabulary": new.get("opportunity_dimension") or "",
               "read": {k: new.get(k) for k in ("what_it_is", "hook", "payoff", "pacing",
                        "blind_spots", "done_well", "on_screen_text_found")},
               "evidence": {"transcript": (tr or "")[:600], "thumb_text": (thumb or "")[:160],
                            "vlm_perception": _vp_compact(vp)}}
    return vid, new, rec


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


def main(limit: int, workers: int, niche: str, dump_path: str | None) -> None:
    targets = pick(niche, limit)
    dump = dump_path is not None
    logger.info(f"opportunity synthesis: {len(targets)} silent {niche} reels "
                f"(workers={workers}, mode={'DUMP' if dump else 'WRITE-DB'})")
    t0 = time.time()
    done = ok = fail = changed = stayed = 0
    records = []
    vocab: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, t, dump) for t in targets]
        for fu in as_completed(futs):
            r = fu.result()
            done += 1
            if r is None:
                fail += 1
                continue
            vid, new, rec = r
            ok += 1
            dim = new.get("opportunity_dimension") or "none"
            vocab[dim] = vocab.get(dim, 0) + 1
            if dim and dim != "none":
                changed += 1
            else:
                stayed += 1
            if dump:
                records.append(rec)
            else:
                store(vid, new)
            if done % 20 == 0 or done == len(targets):
                el = time.time() - t0
                logger.info(f"  {done}/{len(targets)} ok={ok} fail={fail} changed={changed} "
                            f"stayed-silent={stayed} ({done/el*60:.0f}/min)")
    if dump:
        Path(dump_path).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        logger.info(f"wrote {len(records)} records -> {dump_path}")
    logger.info(f"DONE ok={ok} fail={fail} changed={changed} stayed-silent={stayed} "
                f"vocab={vocab} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    args = sys.argv[1:]
    nums = [int(a) for a in args if a.isdigit()]
    niche = next((a for a in args if a.startswith("ig_")), "ig_fitness")
    dump_path = next((a.split("=", 1)[1] for a in args if a.startswith("dump=")), None)
    limit = nums[0] if nums else 80
    workers = nums[1] if len(nums) > 1 else 16
    main(limit, workers, niche, dump_path)
