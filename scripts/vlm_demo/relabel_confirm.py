"""Confirm the 'recover discarded videos' lift under expanding-window CV
(multiple honest future test periods), so the headline isn't a single-split fluke.

Every fold TESTS on in-band ig_fitness videos (the canonical quality examples).
  A' band-only : trains only on in-band videos published BEFORE the test period.
  B' recovered : trains on ALL ig_fitness videos (all ages) published before it.
Same folds, same target (age-residualized). Delta = pure effect of recovering data.
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sqlalchemy import func, select

import lightgbm as lgb
from creative_director.model.dataset import build_dataframe
from creative_director.model.train import _feature_list
from creative_director.storage.db import session_scope
from creative_director.storage.models import VelocitySnapshot

FEATS = _feature_list("intrinsic")


def fit_eval(train, test, feats, seeds=(1, 2, 3)):
    rhos = []
    for sd in seeds:
        m = lgb.LGBMRegressor(
            objective="regression_l2", n_estimators=300, num_leaves=15,
            learning_rate=0.05, min_child_samples=20, subsample=0.8,
            colsample_bytree=0.8, reg_lambda=1.0, random_state=sd, verbose=-1,
        )
        m.fit(train[feats], train["y"])
        r, _ = spearmanr(m.predict(test[feats]), test["y"])
        if not np.isnan(r):
            rhos.append(r)
    return float(np.mean(rhos)) if rhos else np.nan


logfit = build_dataframe(label_scheme="log_views_per_sub_v1", niche="ig_fitness")
with session_scope() as s:
    snap = dict(s.execute(
        select(VelocitySnapshot.video_id, func.max(VelocitySnapshot.captured_at))
        .where(VelocitySnapshot.video_id.in_(logfit["video_id"].tolist()))
        .group_by(VelocitySnapshot.video_id)).all())
logfit["cap"] = logfit["video_id"].map(snap)
logfit = logfit[logfit["cap"].notna()].copy()
logfit["age_days"] = (pd.to_datetime(logfit["cap"]) - pd.to_datetime(logfit["published_at"])).dt.days.clip(lower=0)
logfit["age_bucket"] = pd.qcut(logfit["age_days"], 8, labels=False, duplicates="drop")
logfit["y"] = logfit["score"] - logfit.groupby("age_bucket")["score"].transform("median")
logfit["pub"] = pd.to_datetime(logfit["published_at"])
logfit = logfit.sort_values("pub").reset_index(drop=True)

aged = build_dataframe(label_scheme="views_per_sub_aged_v1", niche="ig_fitness")
inband = set(aged["video_id"])
logfit["inband"] = logfit["video_id"].isin(inband)

# Expanding-window folds defined over the IN-BAND (canonical) videos by date.
inband_df = logfit[logfit["inband"]].sort_values("pub").reset_index(drop=True)
N_FOLDS = 5
bounds = np.linspace(0, len(inband_df), N_FOLDS + 2, dtype=int)

aprime, bprime, sizes = [], [], []
for i in range(N_FOLDS):
    test_ids = set(inband_df.iloc[bounds[i + 1]:bounds[i + 2]]["video_id"])
    if len(test_ids) < 20:
        continue
    test = logfit[logfit["video_id"].isin(test_ids)]
    t0 = logfit[logfit["video_id"].isin(test_ids)]["pub"].min()
    before = logfit[logfit["pub"] < t0]
    trA = before[before["inband"]]
    trB = before
    if len(trA) < 80 or trA["y"].nunique() < 5:
        continue
    rA = fit_eval(trA, test, FEATS)
    rB = fit_eval(trB, test, FEATS + ["age_days"])
    aprime.append(rA); bprime.append(rB); sizes.append((len(trA), len(trB), len(test)))
    print(f"  fold {i}: test={len(test_ids):>3}  A'(band n={len(trA):>4})={rA:.3f}   B'(all n={len(trB):>4})={rB:.3f}   delta={rB-rA:+.3f}")

print()
print(f"  A' band-only   mean Spearman = {np.mean(aprime):.3f}")
print(f"  B' recovered   mean Spearman = {np.mean(bprime):.3f}")
print(f"  RECOVER-DISCARDED LIFT (expanding-window CV) = {np.mean(bprime)-np.mean(aprime):+.3f}")
