"""Deterministic 'demo-safe' curation of the craft-read corpus.

The audit found ~17.5% of reads are major fabrications. The full fix (an LLM
grounding-gate) is deferred; this is the CHEAP curation the demo ships on:

  demo_safe = no Layer-0 flag (ocr_miss_suspect / perf_claim_leak)
              AND OCR-consistent (quoted on-screen text has support in the
              independent VLM/caption/transcript channels — catches the one
              fully-deterministic, high-precision failure family: ocr_hallucination)

It does NOT catch the dominant ungrounded_blindspot/speculation family (that needs
the deferred LLM gate), so we ALSO bias the pool toward the safe niches
(food/fashion) and rank richer reads first. Honest residual risk remains; this
just drives the demo-visible major rate down materially and cheaply.

Writes data/tmp/audit/demo_pool.json (ranked video_ids + per-niche counts).

    python -m scripts.curate_demo_pool
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

NICHES = ("ig_fitness", "ig_food", "ig_travel", "ig_fashion")
NICHE_RANK = {"ig_food": 0, "ig_fashion": 1, "ig_travel": 2, "ig_fitness": 3}  # safer first
OUT = Path("data/tmp/audit/demo_pool.json")

_BANNED = re.compile(
    r"\bgo(es|ing|ne)?\s+viral\b|\bmake\s+\w+\s+viral\b"
    r"|\b(more|boost\w*|increas\w*|maximi\w*|driv\w*|gain\w*|get\w*|grow\w*|higher|extra)\s+"
    r"(views|reach|impressions|engagement|followers)\b"
    r"|\bfor\s+the\s+(algorithm|fyp|feed)\b|\bthe\s+algorithm\b"
    r"|\bwatch[-\s]time\b|\bretention\s+rate\b|\bctr\b", re.I)

_STOP = set("the a an and or of to in on at for with is are was were be it this that "
            "your you my we i as by from out up so no not now new how what when".split())
_QUOTE = re.compile(r'"([^"]{3,})"')


def _toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in _STOP and len(t) > 1}


def _perf_text(r: dict) -> str:
    parts = [r.get(k) for k in ("what_it_is", "hook", "payoff", "pacing", "verdict", "biggest_opportunity")]
    parts += (r.get("blind_spots") or []) + (r.get("done_well") or [])
    return " \n ".join(p for p in parts if isinstance(p, str))


def _ocr_inconsistent(r: dict, hay: set[str]) -> bool:
    """True if a MAJORITY of multi-token on-screen-text quotes are unsupported
    by the independent channels — a high-precision ocr_hallucination signal."""
    ost = r.get("on_screen_text_found") or []
    total = bad = 0
    for q in _QUOTE.findall(" ||| ".join(ost)):
        qt = _toks(q)
        if len(qt) < 2:
            continue
        total += 1
        if len(qt & hay) / len(qt) < 0.34:
            bad += 1
    return total >= 2 and bad / total > 0.5


def main() -> None:
    pool, counts = [], {n: {"total": 0, "safe": 0} for n in NICHES}
    reasons = {"ocr_miss_suspect": 0, "perf_claim_leak": 0, "ocr_inconsistent": 0}
    with session_scope() as s:
        for n in NICHES:
            rows = s.execute(
                select(Video.id, Video.title, VideoFeatures.craft_read,
                       VideoFeatures.transcript, VideoFeatures.thumb_text,
                       VideoFeatures.thumb_text_present, VideoFeatures.first3s_text_present,
                       VideoFeatures.vlm_perception)
                .join(Channel, Channel.id == Video.channel_id)
                .join(VideoFeatures, VideoFeatures.video_id == Video.id)
                .where(VideoFeatures.craft_read.isnot(None),
                       Channel.niche == n, Channel.id.notlike("upch_%"))
            ).all()
            for vid, title, read, transcript, thumbt, thumbp, f3s, vp in rows:
                counts[n]["total"] += 1
                r = read or {}
                ost = r.get("on_screen_text_found") or []
                vp = vp if isinstance(vp, dict) else {}
                vp_text = vp.get("on_screen_text") or ""
                # Layer-0 flags
                if not ost and (f3s or thumbp or vp_text.strip()):
                    reasons["ocr_miss_suspect"] += 1
                    continue
                if _BANNED.search(_perf_text(r)):
                    reasons["perf_claim_leak"] += 1
                    continue
                hay = _toks(vp_text) | _toks(title) | _toks(thumbt) | _toks(transcript or "")
                if _ocr_inconsistent(r, hay):
                    reasons["ocr_inconsistent"] += 1
                    continue
                counts[n]["safe"] += 1
                pool.append({"video_id": vid, "niche": n,
                             "n_blind_spots": len(r.get("blind_spots") or []),
                             "n_done_well": len(r.get("done_well") or [])})

    # Rank: safe niches first, then richer reads (more blind_spots + done_well).
    pool.sort(key=lambda x: (NICHE_RANK[x["niche"]],
                             -(x["n_blind_spots"] + x["n_done_well"])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pool": pool, "counts": counts, "excluded": reasons,
                               "pool_size": len(pool)}, indent=1), encoding="utf-8")

    tot = sum(c["total"] for c in counts.values())
    safe = len(pool)
    print(f"demo-safe pool: {safe}/{tot} ({100*safe/tot:.0f}%)  -> {OUT}")
    for n in NICHES:
        c = counts[n]
        print(f"  {n:12s} safe {c['safe']:4d}/{c['total']:4d}")
    print("excluded:", reasons)
    foodfash = sum(1 for p in pool if p["niche"] in ("ig_food", "ig_fashion"))
    print(f"food+fashion in pool: {foodfash}")


if __name__ == "__main__":
    main()
