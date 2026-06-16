"""What would it take to raise 0.55 ON CURRENT DATA? Three empirical probes:

1. LEARNING CURVE — train on random subsamples of growing size, honest
   expanding-window CV, Spearman vs n. Rising at full n => data-limited (more of
   the same data would help). Flat => noise/feature-limited (it won't).
2. LABEL-NOISE / DENOISE POTENTIAL — how many velocity snapshots per video?
   A real time series => we can fit a settled-views label (denoise the target,
   which raises achievable Spearman). One snapshot => that lever is unavailable.
3. UNLABELED HEADROOM — how many already-scraped videos lack features/labels
   (i.e. n we could grow with ZERO new scraping).
"""
import numpy as np
from scipy.stats import spearmanr
from sqlalchemy import func, select

import lightgbm as lgb
from creative_director.model.train import _feature_list, build_dataframe
from creative_director.storage.db import session_scope
from creative_director.storage.models import (
    Channel, Video, VideoFeatures, VideoLabel, VelocitySnapshot,
)

NICHE = "ig_fitness"
LABEL = "views_per_sub_aged_v1"
FEATS = _feature_list("intrinsic")


def cv_spearman(df, n_folds=5, seed=42):
    """Expanding-window regression CV -> mean test Spearman (replicates harness)."""
    df = df.sort_values("published_at").reset_index(drop=True)
    bounds = np.linspace(0, len(df), n_folds + 2, dtype=int)
    rhos = []
    for i in range(n_folds):
        tr = df.iloc[: bounds[i + 1]]
        te = df.iloc[bounds[i + 1] : bounds[i + 2]]
        if len(te) < 5 or len(set(te["score"])) < 2:
            continue
        m = lgb.LGBMRegressor(
            objective="regression_l2", n_estimators=200, num_leaves=15,
            learning_rate=0.05, min_child_samples=15, subsample=0.8,
            colsample_bytree=0.8, reg_lambda=1.0, random_state=seed, verbose=-1,
        )
        m.fit(tr[FEATS], tr["score"])
        rho, _ = spearmanr(m.predict(te[FEATS]), te["score"])
        if not np.isnan(rho):
            rhos.append(float(rho))
    return float(np.mean(rhos)) if rhos else None


print(f"=== building dataframe ({NICHE}, {LABEL}, intrinsic features) ===")
full = build_dataframe(label_scheme=LABEL, niche=NICHE)
print(f"trainable n = {len(full)}, n_features = {len(FEATS)}")

print("\n=== 1. LEARNING CURVE (random subsample x 4 seeds, expanding-window CV) ===")
sizes = [250, 450, 700, 1000, 1300, len(full)]
for N in sizes:
    if N > len(full):
        continue
    vals = []
    for seed in (1, 2, 3, 4):
        sub = full.sample(n=N, random_state=seed) if N < len(full) else full
        r = cv_spearman(sub, seed=seed)
        if r is not None:
            vals.append(r)
    if vals:
        print(f"  n={N:>5}:  Spearman = {np.mean(vals):.3f}  (+/-{np.std(vals):.3f})")

print("\n=== 2. LABEL-NOISE / DENOISE POTENTIAL (velocity snapshots per video) ===")
with session_scope() as s:
    sub = (
        select(VelocitySnapshot.video_id, func.count().label("k"))
        .join(Video, Video.id == VelocitySnapshot.video_id)
        .join(Channel, Channel.id == Video.channel_id)
        .where(Channel.niche == NICHE)
        .group_by(VelocitySnapshot.video_id)
        .subquery()
    )
    rows = s.execute(select(sub.c.k)).all()
    counts = [r[0] for r in rows]
    if counts:
        import collections
        dist = collections.Counter(counts)
        print(f"  videos with velocity snapshots: {len(counts)}")
        print(f"  snapshots/video: min={min(counts)} median={int(np.median(counts))} max={max(counts)}")
        print(f"  distribution (k snapshots -> #videos): {dict(sorted(dist.items())[:8])}")
        multi = sum(1 for c in counts if c >= 3)
        print(f"  videos with >=3 snapshots (fittable growth curve): {multi} ({100*multi/len(counts):.0f}%)")
    else:
        print("  no velocity snapshots for this niche")

print("\n=== 3. UNLABELED HEADROOM (already-scraped, not yet featurized/labeled) ===")
with session_scope() as s:
    for nm in [NICHE, "ig_food", "ig_travel", "ig_fashion"]:
        total = s.execute(select(func.count()).select_from(Video).join(Channel, Channel.id == Video.channel_id).where(Channel.niche == nm)).scalar()
        feat = s.execute(select(func.count()).select_from(Video).join(Channel, Channel.id == Video.channel_id).join(VideoFeatures, VideoFeatures.video_id == Video.id).where(Channel.niche == nm)).scalar()
        lab = s.execute(select(func.count(func.distinct(Video.id))).select_from(Video).join(Channel, Channel.id == Video.channel_id).join(VideoLabel, VideoLabel.video_id == Video.id).where(Channel.niche == nm, VideoLabel.label_scheme == LABEL)).scalar()
        print(f"  {nm:>11}: scraped={total:>5}  featurized={feat:>5}  labeled({LABEL})={lab:>5}  -> unfeaturized headroom={total-feat}")
