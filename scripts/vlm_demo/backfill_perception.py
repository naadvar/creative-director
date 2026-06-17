"""Corpus VLM-perception backfill — orchestrated LOCALLY, GPU work on the pod.

Runs on your laptop: for each IG corpus reel it pulls the mp4 from R2, samples
12 timestamped frames (light cv2 I/O), and POSTs them to a VLM endpoint (your
RunPod vLLM serving Qwen3-VL). The heavy inference is entirely on the pod. Writes
a resumable JSONL; load it into VideoFeatures.vlm_perception afterwards.

Setup (one command on the pod):
    vllm serve Qwen/Qwen3-VL-32B-Instruct --port 8000 --limit-mm-per-prompt image=3
Then in .env:
    vlm_provider=openai_compatible
    vlm_base_url=https://<pod-id>-8000.proxy.runpod.net/v1
    vlm_model=Qwen/Qwen3-VL-32B-Instruct

Run:
    python -m scripts.vlm_demo.backfill_perception --niche ig_fitness --workers 6
    python -m scripts.vlm_demo.backfill_perception --all          # all 4 IG niches
"""
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import typer
from loguru import logger

from creative_director.config import settings
from creative_director.features import vlm_perception as vp
from creative_director.storage import media

app = typer.Typer(add_completion=False)
OUT = Path("data/tmp/vlm_perception_backfill.jsonl")
IG_NICHES = ["ig_fitness", "ig_food", "ig_travel", "ig_fashion"]


def _done_ids() -> set[str]:
    if not OUT.exists():
        return set()
    return {json.loads(l)["video_id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}


def _targets_from_manifest(path, limit):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows.append((r["video_id"], r.get("niche"), r.get("duration_seconds"), r.get("title")))
    return rows[:limit] if limit else rows


def _targets_from_db(niches, limit):
    # lazy import: the pod (manifest mode) never needs the DB
    from sqlalchemy import select
    from creative_director.storage.db import session_scope
    from creative_director.storage.models import Channel, Video, VideoFeatures

    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Channel.niche, Video.duration_seconds, Video.title)
            .join(Channel, Channel.id == Video.channel_id)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(Channel.niche.in_(niches)).order_by(Video.id)
        ).all()
    return rows[:limit] if limit else rows


RICH = False  # set by --rich: full schema (opening_shot/observed/on_screen_text) + 12 dense frames


def _process(vid, niche, dur, title) -> dict:
    """Pull mp4 from R2 -> sample frames -> VLM. Returns a JSONL record."""
    if not media.exists(media.video_key(vid)):
        return {"video_id": vid, "niche": niche, "vlm_perception": None, "skip": "no_mp4_on_r2"}
    try:
        with tempfile.TemporaryDirectory() as td:
            mp4 = Path(td) / "v.mp4"
            media._client().download_file(settings.r2_bucket, media.video_key(vid), str(mp4))
            strips, ts = vp.sample_strips(str(mp4), Path(td) / "strips", n_frames=4)
            tags = vp.perceive_from_strips(
                strips, niche=niche, caption=(title or "")[:200], duration_s=dur,
                timestamps=ts, lean=not RICH,  # rich = full schema; else structural-only fast pass
            )
        return {"video_id": vid, "niche": niche, "vlm_perception": tags}
    except Exception as e:  # noqa: BLE001
        return {"video_id": vid, "niche": niche, "vlm_perception": None, "error": str(e)[:160]}


@app.command()
def main(
    manifest: str = typer.Option(None, help="pod mode: read the work-list from this JSONL (no DB needed)"),
    rich: bool = typer.Option(False, "--rich", help="full schema (opening_shot/observed/text) + 12 dense frames"),
    niche: str = typer.Option(None, help="single niche, e.g. ig_fitness"),
    all: bool = typer.Option(False, "--all", help="all 4 IG niches"),
    limit: int = typer.Option(0, help="cap (0=all)"),
    workers: int = typer.Option(6, help="concurrent reels (pod batches them)"),
) -> None:
    global RICH
    RICH = rich
    if settings.vlm_provider != "openai_compatible" or not settings.vlm_base_url:
        logger.warning("Set vlm_provider=openai_compatible + vlm_base_url in .env (the RunPod vLLM endpoint) first.")
        raise typer.Exit(1)
    logger.info(f"mode: {'RICH (full schema, 12 frames)' if rich else 'lean'}")
    if manifest:
        rows = _targets_from_manifest(manifest, limit)
    else:
        niches = IG_NICHES if all else [niche] if niche else IG_NICHES
        rows = _targets_from_db(niches, limit)
    done = _done_ids()
    todo = [r for r in rows if r[0] not in done]
    logger.info(f"backfill: {len(rows)} reels in scope, {len(done)} already done, {len(todo)} to do "
                f"| endpoint={settings.vlm_base_url} model={settings.vlm_model}")
    n_ok = n_skip = n_err = 0
    with OUT.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_process, *r): r[0] for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if rec.get("vlm_perception"):
                n_ok += 1
            elif rec.get("skip"):
                n_skip += 1
            else:
                n_err += 1
            if i % 100 == 0:
                logger.info(f"[{i}/{len(todo)}] ok={n_ok} skip={n_skip} err={n_err}")
    logger.info(f"DONE ok={n_ok} skip(no_mp4)={n_skip} err={n_err} -> {OUT}")


if __name__ == "__main__":
    app()
