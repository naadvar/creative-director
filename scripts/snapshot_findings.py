"""Snapshot the current /analyze findings + Scorecard match% for a sample of
corpus videos — a BEFORE baseline to diff against once we change which features
count toward "pattern match" (option 3). Read-only; hits the running API.

    python -m scripts.snapshot_findings    # -> data/findings_baseline_<ts>.json

Re-run after the change and compare the same video_ids to see how match%
shifts (and that high-performers stop looking like low pattern-match).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

import httpx
from sqlalchemy import desc, select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoLabel

API = "http://127.0.0.1:8000"
SCHEME = "views_per_sub_aged_v1"
NICHES = ["ig_fitness", "ig_travel", "ig_food", "ig_fashion", "fitness"]
PER_TERCILE = 3


def main() -> None:
    with session_scope() as s:
        samples: list[tuple[str, str, int, float]] = []  # niche, vid, tercile, score
        for niche in NICHES:
            for terc in (2, 1, 0):
                rows = s.execute(
                    select(VideoLabel.video_id, VideoLabel.score)
                    .join(Video, Video.id == VideoLabel.video_id)
                    .join(Channel, Channel.id == Video.channel_id)
                    .where(
                        Channel.niche == niche,
                        VideoLabel.label_scheme == SCHEME,
                        VideoLabel.tercile == terc,
                    )
                    .order_by(desc(VideoLabel.score))
                    .limit(PER_TERCILE)
                ).all()
                samples += [(niche, vid, terc, float(sc)) for vid, sc in rows]

    snap = {"created": datetime.utcnow().isoformat() + "Z", "scheme": SCHEME, "videos": []}
    with httpx.Client(timeout=120) as c:
        for niche, vid, terc, score in samples:
            try:
                a = c.get(f"{API}/videos/{vid}/analyze").json()
            except Exception as e:  # noqa: BLE001
                print(f"{vid}: ERR {e}")
                continue
            f = a.get("findings") or []
            total = len(f)
            aligned = sum(1 for x in f if not x.get("off_benchmark"))
            pm = a.get("pattern_match") or {}
            snap["videos"].append({
                "video_id": vid, "niche": niche, "tercile": terc, "score": round(score, 3),
                "archetype": a.get("archetype"), "tier": a.get("tier"),
                "benchmark_scope": a.get("benchmark_scope"),
                "total_findings": total, "aligned": aligned,
                "match_pct": round(100 * aligned / total) if total else None,
                "pm_pct": pm.get("pct"), "pm_aligned": pm.get("aligned"), "pm_total": pm.get("total"),
                "findings": [
                    {k: x.get(k) for k in
                     ("feature", "off_benchmark", "direction", "causal", "rank_score", "fixability")}
                    for x in f
                ],
            })

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = f"data/findings_baseline_{ts}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2)

    old_by, new_by = defaultdict(list), defaultdict(list)
    for v in snap["videos"]:
        if v["match_pct"] is not None:
            old_by[v["tercile"]].append(v["match_pct"])
        if v.get("pm_pct") is not None:
            new_by[v["tercile"]].append(v["pm_pct"])
    print(f"wrote {path}  ({len(snap['videos'])} videos)")
    print("avg match% by performance tercile (NEW should track performance: High > Mid > Low):")
    print(f"  {'tercile':12}{'OLD (generic 5)':>18}{'NEW (predictive)':>20}")
    for terc in (2, 1, 0):
        name = "High Mid Low".split()[2 - terc]
        o, n = old_by[terc], new_by[terc]
        os_ = f"{sum(o)/len(o):.0f} (n={len(o)})" if o else "-"
        ns_ = f"{sum(n)/len(n):.0f} (n={len(n)})" if n else "-"
        print(f"  {terc} {name:9}{os_:>18}{ns_:>20}")


if __name__ == "__main__":
    main()
