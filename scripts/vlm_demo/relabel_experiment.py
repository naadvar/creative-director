"""Does label engineering raise 0.55 ON CURRENT DATA? Two levers, measured.

Method: a FIXED, time-held-out ig_fitness test set. Every arm is evaluated on
the SAME test videos against the SAME target; only the TRAINING set changes. So
any Spearman difference is purely "did more/other training data help."

LEVER 1 (pool niches): target = existing aged quality label.
  A  baseline   : train ig_fitness aged only          (~1.3k)
  C  pooled     : train all-4-niches aged + niche flag (~4.8k)

LEVER 2 (recover the ~3.5k discarded ig_fitness videos): target = age-residualized
log(views/sub) (a quality signal valid at ALL ages, not just the 30-180d band).
  A' band-only  : train only the in-age-band ig_fitness videos
  B' recovered  : train ALL ig_fitness videos + age feature
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

NICHES = ["ig_fitness", "ig_food", "ig_travel", "ig_fashion"]
FEATS = _feature_list("intrinsic")
SEEDS = (1, 2, 3)


def fit_predict(train, test, feats, seeds=SEEDS):
    """Mean held-out Spearman over seeds (target column = 'y')."""
    rhos = []
    for sd in seeds:
        m = lgb.LGBMRegressor(
            objective="regression_l2", n_estimators=300, num_leaves=15,
            learning_rate=0.05, min_child_samples=20, subsample=0.8,
            colsample_bytree=0.8, reg_lambda=1.0, random_state=sd, verbose=-1,
        )
        m.fit(train[feats], train["y"])
        rho, _ = spearmanr(m.predict(test[feats]), test["y"])
        if not np.isnan(rho):
            rhos.append(float(rho))
    return float(np.mean(rhos)), float(np.std(rhos))


print("=== loading aged-label corpus (4 niches) ===")
aged = build_dataframe(label_scheme="views_per_sub_aged_v1", niche=NICHES)
aged["y"] = aged["score"]
for nm in NICHES:
    aged[f"niche_{nm}"] = (aged["niche"] == nm).astype(float)
NICHE_COLS = [f"niche_{nm}" for nm in NICHES]
print(f"  aged rows: {len(aged)}  per niche: {aged['niche'].value_counts().to_dict()}")

# Fixed time-held-out ig_fitness test = most-recent 25% of aged ig_fitness.
fit_aged = aged[aged["niche"] == "ig_fitness"].sort_values("published_at")
cut = int(len(fit_aged) * 0.75)
TEST_IDS = set(fit_aged.iloc[cut:]["video_id"])
test_aged = aged[aged["video_id"].isin(TEST_IDS)]
print(f"  ig_fitness aged: {len(fit_aged)}  -> held-out test: {len(TEST_IDS)}")

print("\n=== LEVER 1: POOL NICHES (target = aged quality label) ===")
trainA = aged[(aged["niche"] == "ig_fitness") & (~aged["video_id"].isin(TEST_IDS))]
mA, sA = fit_predict(trainA, test_aged, FEATS)
print(f"  A baseline (ig_fitness only, n={len(trainA)}):        Spearman={mA:.3f} (+/-{sA:.3f})")
trainC = aged[~aged["video_id"].isin(TEST_IDS)]
mC, sC = fit_predict(trainC, test_aged, FEATS + NICHE_COLS)
print(f"  C pooled (all 4 niches+flag, n={len(trainC)}):       Spearman={mC:.3f} (+/-{sC:.3f})")
print(f"  --> pooling niches: {mC-mA:+.3f}")

print("\n=== LEVER 2: RECOVER DISCARDED ig_fitness (target = age-residualized) ===")
logfit = build_dataframe(label_scheme="log_views_per_sub_v1", niche="ig_fitness")
print(f"  full ig_fitness (all ages): {len(logfit)}")
with session_scope() as s:
    snap = dict(
        s.execute(
            select(VelocitySnapshot.video_id, func.max(VelocitySnapshot.captured_at))
            .where(VelocitySnapshot.video_id.in_(logfit["video_id"].tolist()))
            .group_by(VelocitySnapshot.video_id)
        ).all()
    )
logfit["cap"] = logfit["video_id"].map(snap)
logfit = logfit[logfit["cap"].notna()].copy()
logfit["age_days"] = (pd.to_datetime(logfit["cap"]) - pd.to_datetime(logfit["published_at"])).dt.days.clip(lower=0)
# age-residualized target: over/under-performance vs same-age peers
logfit["age_bucket"] = pd.qcut(logfit["age_days"], 8, labels=False, duplicates="drop")
logfit["y"] = logfit["score"] - logfit.groupby("age_bucket")["score"].transform("median")

# sanity: is the residual a faithful stand-in for the canonical aged label?
ov = logfit.merge(fit_aged[["video_id", "score"]].rename(columns={"score": "aged_score"}), on="video_id")
if len(ov) > 10:
    r, _ = spearmanr(ov["y"], ov["aged_score"])
    print(f"  sanity: corr(residual target, canonical aged label) on {len(ov)} overlap = {r:.3f}")

aged_ids = set(fit_aged["video_id"])  # the in-band videos
test_log = logfit[logfit["video_id"].isin(TEST_IDS)]
trainAp = logfit[logfit["video_id"].isin(aged_ids) & ~logfit["video_id"].isin(TEST_IDS)]
mAp, sAp = fit_predict(trainAp, test_log, FEATS)
print(f"  A' band-only (n={len(trainAp)}):                     Spearman={mAp:.3f} (+/-{sAp:.3f})")
trainBp = logfit[~logfit["video_id"].isin(TEST_IDS)]
mBp, sBp = fit_predict(trainBp, test_log, FEATS + ["age_days"])
print(f"  B' recovered (all ages+age feat, n={len(trainBp)}):   Spearman={mBp:.3f} (+/-{sBp:.3f})")
print(f"  --> recovering discarded videos: {mBp-mAp:+.3f}")

print("\n=== COMBINED: pool niches + all ages (residual target, all niches) ===")
# rebuild residual target across all niches/ages would need full corpus; approximate
# with the strongest single arm already measured. (Full 15k build is the next step.)
print(f"  best single-lever lift vs its baseline: pool={mC-mA:+.3f}  recover={mBp-mAp:+.3f}")
