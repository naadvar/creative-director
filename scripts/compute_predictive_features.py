"""Measure which interpretable features actually predict performance, per niche.

The Scorecard "pattern match" currently counts a fixed 5-feature REPORTABLE set
equally, so it's noise vs actual performance. This computes, per niche, the
Spearman correlation of every interpretable (non-PCA) intrinsic feature with the
views-per-sub performance score, and persists the predictive ones
(|rho| >= threshold, p < 0.05) to creative_director/advice/predictive_features.json.

breakdown.py can then gate / weight the match% by these, so "pattern match"
reflects features that actually relate to performance in that niche.

    python -m scripts.compute_predictive_features
"""
from __future__ import annotations

import json

from scipy.stats import spearmanr

from creative_director.model.dataset import (
    _VIDEOFEATURE_COLUMNS,
    build_dataframe,
)

SCHEME = "views_per_sub_aged_v1"
NICHES = ["ig_fitness", "ig_travel", "ig_food", "ig_fashion", "fitness"]
RHO_MIN = 0.08
P_MAX = 0.05
# Only features the analyzer can read straight off a video at serve time
# (stored VideoFeatures columns + duration). Excludes derived/PCA features that
# only exist at dataset-build time, so breakdown.py can actually use these.
CANDIDATES = list(_VIDEOFEATURE_COLUMNS) + ["duration_seconds"]
OUT = "creative_director/advice/predictive_features.json"


def main() -> None:
    print(f"candidates={len(CANDIDATES)}  scheme={SCHEME}")
    out: dict[str, dict] = {}
    for niche in NICHES:
        df = build_dataframe(label_scheme=SCHEME, niche=niche)
        if df.empty or "score" not in df:
            print(f"\n{niche}: no data")
            continue
        sc = df["score"].to_numpy()
        scored = []
        for f in CANDIDATES:
            if f not in df.columns:
                continue
            v = df[f].to_numpy()
            try:
                rho, p = spearmanr(v, sc, nan_policy="omit")
            except Exception:  # noqa: BLE001
                continue
            if rho == rho:  # not NaN (constant feature -> NaN)
                scored.append((f, float(rho), float(p)))
        scored.sort(key=lambda x: -abs(x[1]))
        hi = df[df["tercile"] == 2]  # winners — their median is the "what winners do" target
        keep = {}
        for f, r, p in scored:
            if abs(r) >= RHO_MIN and p < P_MAX:
                wm = hi[f].dropna()
                keep[f] = {
                    "rho": round(r, 4),
                    "niche_median": round(float(df[f].median()), 4),
                    "winner_median": round(float(wm.median()), 4) if not wm.empty else None,
                    "source": "video" if f == "duration_seconds" else "features",
                }
        out[niche] = keep
        print(f"\n=== {niche} (n={len(df)})  predictive={len(keep)} of {len(scored)} ===")
        for f, r, p in scored[:12]:
            mark = "*" if (abs(r) >= RHO_MIN and p < P_MAX) else " "
            print(f"  {mark} {f:30} rho={r:+.3f}  p={p:.1e}")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"scheme": SCHEME, "rho_min": RHO_MIN, "p_max": P_MAX, "niches": out}, fh, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
