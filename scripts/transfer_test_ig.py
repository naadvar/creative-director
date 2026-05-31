"""Cross-platform transfer test: does a YouTube-trained model rank IG reels?

Trains the `views_per_sub_aged_v1` regressor on the YouTube fitness corpus
and applies it to IG reels (niche=ig_fitness). Reports Spearman correlation
on IG (rank-preserving, so different label *scales* across platforms do not
hurt).

Feature set is restricted to TRANSFER-SAFE columns:
  - VideoFeatures hand-engineered numerics (thumbnail, title, audio, transcript)
  - Duration / publish hour / weekday
  - Timeline aggregates (hook_face_frac, cuts/10s, etc.)

Dropped:
  - PCA components (fit per-niche in build_dataframe -- different spaces)
  - winner-similarity features (compare to IG winners, not YT winners)
  - per-second deviation summary (label-derived)

Why this is the right test at our scale (2026-05-20: 18 IG videos in cohort,
1432 YT fitness videos): training a model on 18 rows is noise; using 18 rows
only for the test-time rank correlation IS meaningful. Spearman SE ~ +/- 0.2
at n=18 -- directional signal, not definitive.

    python -m scripts.transfer_test_ig
"""
from __future__ import annotations

import numpy as np
import typer
from loguru import logger
from scipy.stats import spearmanr

from creative_director.model.dataset import (
    _DERIVED_COLUMNS,
    _TIMELINE_COLUMNS,
    _VIDEOFEATURE_COLUMNS,
    build_dataframe,
)

app = typer.Typer(add_completion=False)

# Transfer-safe features (see module docstring).
TRANSFER_FEATURES = _VIDEOFEATURE_COLUMNS + _DERIVED_COLUMNS + _TIMELINE_COLUMNS


@app.command()
def main(
    label_scheme: str = typer.Option(
        "views_per_sub_aged_v1",
        help="Label scheme to transfer (only views_per_sub_aged_v1 is honest cross-platform)",
    ),
    train_niche: str = typer.Option("fitness", help="Training niche (YouTube)"),
    test_niche: str = typer.Option("ig_fitness", help="Test niche (Instagram)"),
    n_permutations: int = typer.Option(
        1000, help="Random permutations for the empirical null distribution"
    ),
):
    import lightgbm as lgb

    logger.info(f"Building train df: niche={train_niche}, label={label_scheme}")
    yt = build_dataframe(label_scheme=label_scheme, niche=train_niche)
    logger.info(f"  YT rows: {len(yt)}")

    logger.info(f"Building test df:  niche={test_niche}, label={label_scheme}")
    ig = build_dataframe(label_scheme=label_scheme, niche=test_niche)
    logger.info(f"  IG rows: {len(ig)}")

    if len(yt) < 30 or len(ig) < 5:
        raise typer.Exit(f"Datasets too small: YT={len(yt)}, IG={len(ig)}")

    # Feature matrices. Impute IG NaNs with YT means (consistent transfer);
    # impute YT NaNs with YT means too so training is on a clean matrix.
    X_yt = yt[TRANSFER_FEATURES]
    X_ig = ig[TRANSFER_FEATURES]
    yt_means = X_yt.mean()
    X_yt = X_yt.fillna(yt_means)
    X_ig = X_ig.fillna(yt_means)
    y_yt = yt["score"]
    y_ig = ig["score"]
    logger.info(f"  Features: {len(TRANSFER_FEATURES)} (intrinsic, no PCA, no label-derived)")

    # Train YT regressor (same hyperparameters as model/train.py).
    model = lgb.LGBMRegressor(
        objective="regression_l2",
        n_estimators=200,
        num_leaves=15,
        learning_rate=0.05,
        min_child_samples=15,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_yt, y_yt)
    rho_yt_in, _ = spearmanr(model.predict(X_yt), y_yt)
    logger.info(f"YT in-sample Spearman: {rho_yt_in:.3f} (sanity, not a generalisation number)")

    # Cross-platform inference + Spearman.
    ig_pred = model.predict(X_ig)
    rho_ig, p_ig = spearmanr(ig_pred, y_ig)

    # Empirical null: permute predictions, recompute Spearman, repeat.
    rng = np.random.default_rng(42)
    null_rhos = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        r, _ = spearmanr(rng.permutation(ig_pred), y_ig)
        null_rhos[i] = r
    p_empirical = float(np.mean(np.abs(null_rhos) >= abs(rho_ig)))

    print()
    print("=" * 70)
    print("CROSS-PLATFORM TRANSFER TEST")
    print("=" * 70)
    print(f"Train:    {train_niche}, n={len(yt)}")
    print(f"Test:     {test_niche}, n={len(ig)}")
    print(f"Label:    {label_scheme} (regression target, continuous views/sub)")
    print(f"Features: {len(TRANSFER_FEATURES)} transfer-safe")
    print()
    print(f"Spearman on IG: {rho_ig:+.3f}   (parametric p={p_ig:.4f})")
    print(f"Empirical null (n={n_permutations} perms): "
          f"mean={null_rhos.mean():+.3f}  std={null_rhos.std():.3f}  "
          f"p(|null|>=|obs|)={p_empirical:.3f}")
    print()

    # Per-video table sorted by actual score (rank).
    ig = ig.assign(pred=ig_pred)
    ig["rank_pred"] = ig["pred"].rank().astype(int)
    ig["rank_actual"] = ig["score"].rank().astype(int)
    print("IG videos, sorted by ACTUAL views/sub rank:")
    print(f"  {'video_id':<22} {'channel':<24} {'score':>8} {'pred':>8} {'rank_a':>7} {'rank_p':>7}")
    for _, row in ig.sort_values("score", ascending=False).iterrows():
        print(
            f"  {row['video_id']:<22} "
            f"{str(row['channel'])[:23]:<24} "
            f"{row['score']:>8.3f} {row['pred']:>8.3f} "
            f"{row['rank_actual']:>7d} {row['rank_pred']:>7d}"
        )
    print()

    # Interpretation guide (the only thing the user needs to read first).
    print("INTERPRETATION:")
    if abs(rho_ig) >= 0.3 and p_empirical < 0.10:
        print(f"  Spearman {rho_ig:+.3f} -> SIGNAL. YouTube features transfer to IG.")
        print(f"  -> Scaling IG ingestion next month (~250 reels at fixed cost) is worth it.")
    elif abs(rho_ig) >= 0.15:
        print(f"  Spearman {rho_ig:+.3f} -> WEAK signal at n={len(ig)} (SE ~ +/- 0.2).")
        print(f"  -> Inconclusive. Borderline call -- a larger IG corpus would settle it.")
    else:
        print(f"  Spearman {rho_ig:+.3f} -> NO transfer.")
        print(f"  -> IG looks like its own world at this feature set.")
        print(f"     Drop the IG path OR commit to a paid tier for much more IG data.")


if __name__ == "__main__":
    app()
