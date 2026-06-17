"""Rich VLM perception over the corpus via the Anthropic Message Batches API
(Haiku 4.5, 50% off). Orchestrated locally: pull mp4 from R2 -> sample a 4-frame
strip -> build a forced-tool-use request -> submit in chunks under the 256MB
batch cap -> poll -> retrieve -> write a resumable JSONL with exact token usage.

  python -m scripts.vlm_demo.batch_backfill 11000          # prep + submit + poll + retrieve
  python -m scripts.vlm_demo.batch_backfill --poll-only    # resume: just poll+retrieve recorded batches
"""
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from creative_director.config import settings
from creative_director.features import vlm_perception as vp
from creative_director.storage import media

MANIFEST = Path("data/tmp/perception_manifest.jsonl")
OUT = Path("data/tmp/vlm_rich_anthropic.jsonl")
BATCHIDS = Path("data/tmp/rich_batch_ids.json")
MODEL = settings.vlm_model or "claude-haiku-4-5"
CHUNK = 2000          # requests per batch (×~60KB image ≈ <150MB, safely under 256MB)
PREP_WORKERS = 24     # R2 download + cv2 sampling is I/O-bound

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _done_ids() -> set:
    if not OUT.exists():
        return set()
    return {json.loads(l)["video_id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}


def _rows(limit):
    out = []
    for l in MANIFEST.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l)
            out.append((r["video_id"], r.get("niche"), r.get("duration_seconds"), r.get("title")))
    return out[:limit] if limit else out


def _build(vid, niche, dur, title):
    """Pull mp4 -> sample -> Anthropic batch Request. Returns (Request, niche) or None."""
    if not media.exists(media.video_key(vid)):
        return None
    try:
        with tempfile.TemporaryDirectory() as td:
            mp4 = Path(td) / "v.mp4"
            media._client().download_file(settings.r2_bucket, media.video_key(vid), str(mp4))
            strips, ts = vp.sample_strips(str(mp4), Path(td) / "s", n_frames=4)
            ctx = vp._context_text(niche, (title or "")[:200], dur, ts)
            content = [{"type": "text", "text": ctx}] + [vp._img_block(p) for p in strips]
        params = MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=1500, system=vp._SYSTEM,
            tools=[vp._PERCEPTION_TOOL], tool_choice={"type": "tool", "name": "report_perception"},
            messages=[{"role": "user", "content": content}],
        )
        return Request(custom_id=vid, params=params), niche
    except Exception as e:  # noqa: BLE001
        print(f"  build failed {vid}: {type(e).__name__}: {str(e)[:120]}", flush=True)
        return None


def _submit_chunks(targets):
    """Prep concurrently and submit in CHUNK-sized batches. Returns list of batch ids."""
    batch_ids = json.loads(BATCHIDS.read_text()) if BATCHIDS.exists() else []
    for start in range(0, len(targets), CHUNK):
        chunk = targets[start:start + CHUNK]
        reqs, skip = [], 0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=PREP_WORKERS) as ex:
            for fut in as_completed([ex.submit(_build, *r) for r in chunk]):
                res = fut.result()
                if res:
                    reqs.append(res[0])
                else:
                    skip += 1
        if not reqs:
            print(f"chunk {start}: no requests (all skipped)", flush=True)
            continue
        batch = client.messages.batches.create(requests=reqs)
        batch_ids.append(batch.id)
        BATCHIDS.write_text(json.dumps(batch_ids))
        print(f"chunk {start}: prepped {len(reqs)} (skip {skip}) in {time.time()-t0:.0f}s -> batch {batch.id}", flush=True)
    return batch_ids


def _poll_and_retrieve(batch_ids):
    # poll
    while True:
        statuses = [client.messages.batches.retrieve(b).processing_status for b in batch_ids]
        ended = sum(s == "ended" for s in statuses)
        print(f"  batches ended {ended}/{len(batch_ids)}  statuses={dict(zip(batch_ids, statuses))}", flush=True)
        if ended == len(batch_ids):
            break
        time.sleep(60)
    # retrieve
    ok = err = 0
    tin = tout = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for b in batch_ids:
            for result in client.messages.batches.results(b):
                if result.result.type == "succeeded":
                    msg = result.result.message
                    perc = next((dict(x.input) for x in msg.content if x.type == "tool_use"), None)
                    if perc:
                        perc["schema_version"] = vp.SCHEMA_VERSION
                        tin += msg.usage.input_tokens
                        tout += msg.usage.output_tokens
                        ok += 1
                    fh.write(json.dumps({"video_id": result.custom_id, "vlm_perception": perc,
                                         "in_tok": msg.usage.input_tokens, "out_tok": msg.usage.output_tokens},
                                        ensure_ascii=False) + "\n")
                    fh.flush()
                else:
                    err += 1
    batch_cost = (tin * 1.0 + tout * 5.0) / 1e6 * 0.5
    print(f"\nDONE  ok={ok}  err={err}  tokens in={tin} out={tout}  batch cost=${batch_cost:.2f} -> {OUT}", flush=True)


def main():
    poll_only = "--poll-only" in sys.argv
    if poll_only:
        ids = json.loads(BATCHIDS.read_text())
        print(f"poll-only: {len(ids)} batches", flush=True)
        _poll_and_retrieve(ids)
        return
    limit = next((int(a) for a in sys.argv[1:] if a.isdigit()), 11000)
    done = _done_ids()
    targets = [r for r in _rows(limit) if r[0] not in done]
    print(f"model={MODEL}  limit={limit}  already_done={len(done)}  to_submit={len(targets)}  chunk={CHUNK}", flush=True)
    ids = _submit_chunks(targets)
    print(f"submitted {len(ids)} batches; polling...", flush=True)
    _poll_and_retrieve(ids)


if __name__ == "__main__":
    main()
