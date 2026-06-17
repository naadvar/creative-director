"""Anthropic rich-perception calibration: run N corpus reels through Claude
(Haiku 4.5) with the full perception tool, capture EXACT token usage, and
project the cost for the whole corpus at sync + batch (50% off) rates.

    python -m scripts.vlm_demo.calibrate_anthropic 30
"""
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic

from creative_director.config import settings
from creative_director.features import vlm_perception as vp
from creative_director.storage import media

MANIFEST = Path("data/tmp/perception_manifest.jsonl")
OUT = Path("data/tmp/calib_anthropic.jsonl")
MODEL = settings.vlm_model or "claude-haiku-4-5"
CORPUS_TOTAL = 14929

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _rows(n):
    rows = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows.append((r["video_id"], r.get("niche"), r.get("duration_seconds"), r.get("title")))
    return rows[:n]


def _one(vid, niche, dur, title):
    if not media.exists(media.video_key(vid)):
        return {"video_id": vid, "skip": "no_mp4"}
    try:
        with tempfile.TemporaryDirectory() as td:
            mp4 = Path(td) / "v.mp4"
            media._client().download_file(settings.r2_bucket, media.video_key(vid), str(mp4))
            strips, ts = vp.sample_strips(str(mp4), Path(td) / "s", n_frames=4)
            ctx = vp._context_text(niche, (title or "")[:200], dur, ts)
            content = [{"type": "text", "text": ctx}] + [vp._img_block(p) for p in strips]
            resp = _client.messages.create(
                model=MODEL, max_tokens=1500, system=vp._SYSTEM,
                tools=[vp._PERCEPTION_TOOL], tool_choice={"type": "tool", "name": "report_perception"},
                messages=[{"role": "user", "content": content}],
            )
        perc = next((dict(b.input) for b in resp.content if b.type == "tool_use"), None)
        return {"video_id": vid, "niche": niche, "perception": perc,
                "in_tok": resp.usage.input_tokens, "out_tok": resp.usage.output_tokens}
    except Exception as e:  # noqa: BLE001
        return {"video_id": vid, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    rows = _rows(n)
    print(f"model={MODEL}  reels={len(rows)}")
    recs, t0 = [], time.time()
    with OUT.open("w", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=6) as ex:
        for fut in as_completed([ex.submit(_one, *r) for r in rows]):
            rec = fut.result()
            recs.append(rec)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    dt = time.time() - t0

    ok = [r for r in recs if r.get("perception")]
    skip = [r for r in recs if r.get("skip")]
    err = [r for r in recs if r.get("error")]
    print(f"\n[{dt:.0f}s]  ok={len(ok)}  skip(no_mp4)={len(skip)}  err={len(err)}")
    if err:
        print("  sample errors:", [e["error"] for e in err[:3]])

    if ok:
        ain = sum(r["in_tok"] for r in ok) / len(ok)
        aout = sum(r["out_tok"] for r in ok) / len(ok)
        print(f"  avg tokens/reel: in={ain:.0f}  out={aout:.0f}")
        # Haiku 4.5: $1/M in, $5/M out. Batch = 50% off.
        def cost(reels, disc):
            return reels * (ain * 1.0 + aout * 5.0) / 1e6 * disc
        for reels in (50, 500, 2000, CORPUS_TOTAL):
            print(f"  {reels:>6} reels:  sync ${cost(reels,1.0):.2f}   batch(50% off) ${cost(reels,0.5):.2f}")

    print("\n--- sample perceptions ---")
    for r in ok[:5]:
        p = r["perception"]
        print(f"\n[{r['niche']}] {r['video_id']}")
        print(f"  genre={p.get('genre')}  has_presenter={p.get('has_presenter')}  conf={p.get('confidence')}")
        print(f"  opening_shot: {p.get('opening_shot')}")
        if p.get("on_screen_text"):
            print(f"  on_screen_text: {p.get('on_screen_text')}")
        for o in (p.get("observed") or [])[:3]:
            print(f"    observed[{o.get('frame_ts')}s/{o.get('kind')}]: {o.get('text')}")


if __name__ == "__main__":
    main()
