"""ML-tuning moves run on a reliable box (Runpod), not the thermally-failed laptop.

Three subcommands, all using expanding-window time-series CV on the regression
target (Spearman is the metric we care about for ranking):

    python -m scripts.ml_moves sweep      --niche ig_fitness --label-scheme views_per_sub_aged_v1
    python -m scripts.ml_moves multiseed  --niche ig_fitness --label-scheme views_per_sub_aged_v1
    python -m scripts.ml_moves family     --niche ig_fitness --label-scheme views_per_sub_aged_v1

sweep     : grid over LightGBM hyperparameters, report best by CV Spearman.
multiseed : repeat CV across N random seeds, report mean +/- std (tightens the
            estimate so we know if 0.51 vs 0.55 is real or noise).
family    : LightGBM vs XGBoost vs CatBoost on the same features/folds.
"""
from __future__ import annotations

import itertools
from typing import Callable, Optional

import numpy as np
import typer
from scipy.stats import spearmanr

from creative_director.model.dataset import (
    FEATURE_NAMES,
    INTRINSIC_FEATURES,
    build_dataframe,
)

app = typer.Typer(add_completion=False)


def _features(feature_set: str) -> list[str]:
    return INTRINSIC_FEATURES if feature_set == "intrinsic" else FEATURE_NAMES


def _expanding_cv_spearman(
    df,
    features: list[str],
    model_factory: Callable,
    n_folds: int = 5,
) -> tuple[float, list[float]]:
    """Expanding-window CV. Returns (mean_spearman, per_fold). Mirrors
    model/train.py time_series_cv but model-agnostic via a factory."""
    df = df.sort_values("published_at").reset_index(drop=True)
    bounds = np.linspace(0, len(df), n_folds + 2, dtype=int)
    fold_rho: list[float] = []
    for i in range(n_folds):
        tr = df.iloc[: bounds[i + 1]]
        te = df.iloc[bounds[i + 1] : bounds[i + 2]]
        if len(te) < 5:
            continue
        X_tr, X_te = tr[features], te[features]
        y_tr, y_te = tr["score"], te["score"]
        model = model_factory()
        model.fit(X_tr, y_tr)
        pred = model.predict(X_te)
        if len(set(te["score"])) > 1:
            rho, _ = spearmanr(pred, y_te)
            if not np.isnan(rho):
                fold_rho.append(float(rho))
    return (float(np.mean(fold_rho)) if fold_rho else 0.0), fold_rho


@app.command()
def sweep(
    niche: str = typer.Option("ig_fitness"),
    label_scheme: str = typer.Option("views_per_sub_aged_v1"),
    feature_set: str = typer.Option("intrinsic", help="all | intrinsic"),
) -> None:
    """Grid search LightGBM hyperparameters by CV Spearman."""
    import lightgbm as lgb

    feats = _features(feature_set)
    print(f"Building dataframe ({niche}, {label_scheme}) ...")
    df = build_dataframe(label_scheme=label_scheme, niche=niche)
    print(f"  rows={len(df)}  features={len(feats)}")

    grid = {
        "n_estimators": [200, 400, 700],
        "num_leaves": [7, 15, 31],
        "learning_rate": [0.02, 0.05],
        "min_child_samples": [10, 25, 50],
    }
    keys = list(grid)
    combos = list(itertools.product(*[grid[k] for k in keys]))
    print(f"Sweeping {len(combos)} configs x 5 folds ...")

    results = []
    for combo in combos:
        params = dict(zip(keys, combo))

        def factory(p=params):
            return lgb.LGBMRegressor(
                objective="regression_l2",
                subsample=0.8,
                colsample_bytree=0.8,
                reg_lambda=1.0,
                random_state=42,
                verbose=-1,
                **p,
            )

        mean_rho, folds = _expanding_cv_spearman(df, feats, factory)
        results.append((mean_rho, params, folds))

    results.sort(key=lambda r: -r[0])
    print("\n=== TOP 10 CONFIGS BY CV SPEARMAN ===")
    for mean_rho, params, folds in results[:10]:
        fold_str = "[" + ", ".join(f"{f:.2f}" for f in folds) + "]"
        print(f"  {mean_rho:.4f}  {params}  folds={fold_str}")
    print(f"\nBEST: {results[0][0]:.4f}  {results[0][1]}")
    print(f"(baseline default config CV was ~0.507 on this label)")


@app.command()
def multiseed(
    niche: str = typer.Option("ig_fitness"),
    label_scheme: str = typer.Option("views_per_sub_aged_v1"),
    feature_set: str = typer.Option("intrinsic"),
    n_seeds: int = typer.Option(8),
) -> None:
    """Repeat CV across N seeds; report mean +/- std Spearman."""
    import lightgbm as lgb

    feats = _features(feature_set)
    df = build_dataframe(label_scheme=label_scheme, niche=niche)
    print(f"rows={len(df)} features={len(feats)}  seeds={n_seeds}")

    seed_means = []
    for seed in range(n_seeds):
        def factory(s=seed):
            return lgb.LGBMRegressor(
                objective="regression_l2",
                n_estimators=400,
                num_leaves=15,
                learning_rate=0.05,
                min_child_samples=25,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_lambda=1.0,
                random_state=s,
                verbose=-1,
            )

        mean_rho, _ = _expanding_cv_spearman(df, feats, factory)
        seed_means.append(mean_rho)
        print(f"  seed {seed}: {mean_rho:.4f}")

    arr = np.array(seed_means)
    print(f"\nMEAN Spearman across {n_seeds} seeds: {arr.mean():.4f} +/- {arr.std():.4f}")
    print(f"  range [{arr.min():.4f}, {arr.max():.4f}]")


@app.command()
def baselines(
    niche: str = typer.Option("ig_fitness"),
    label_scheme: str = typer.Option("views_per_sub_aged_v1"),
    feature_set: str = typer.Option("intrinsic"),
) -> None:
    """How much does the full model beat naive baselines?

    Reports, on identical expanding-window test folds:
      - predict-mean (the floor: no ranking power)
      - the best SINGLE feature as a ranker (the best one-line rule a creator
        could apply: 'shorter is better', etc.)
      - a LightGBM trained on ONLY that best single feature
      - the full model (all features)
    The gap (full - best_single) is what the ML earns over common sense.
    """
    import lightgbm as lgb

    feats = _features(feature_set)
    df = build_dataframe(label_scheme=label_scheme, niche=niche)
    df = df.sort_values("published_at").reset_index(drop=True)
    n_folds = 5
    bounds = np.linspace(0, len(df), n_folds + 2, dtype=int)
    print(f"rows={len(df)} features={len(feats)} folds={n_folds}")

    # 1. Univariate: per-feature mean test-fold Spearman (signed).
    uni: list[tuple[str, float]] = []
    for f in feats:
        rhos = []
        for i in range(n_folds):
            te = df.iloc[bounds[i + 1] : bounds[i + 2]]
            if len(te) < 5:
                continue
            sub = te[[f, "score"]].dropna()
            if len(sub) < 5 or sub[f].nunique() < 2:
                continue
            r, _ = spearmanr(sub[f], sub["score"])
            if not np.isnan(r):
                rhos.append(float(r))
        if rhos:
            uni.append((f, float(np.mean(rhos))))
    uni.sort(key=lambda t: -abs(t[1]))

    print("\n=== TOP 12 SINGLE FEATURES (mean test-fold Spearman) ===")
    for name, rho in uni[:12]:
        print(f"  {name:28} {rho:+.4f}  (|{abs(rho):.4f}|)")

    best_feat, best_rho = uni[0] if uni else ("<none>", 0.0)

    # 2. LightGBM trained on ONLY the best single feature.
    def _cv_with(features_subset: list[str]) -> float:
        rhos = []
        for i in range(n_folds):
            tr = df.iloc[: bounds[i + 1]]
            te = df.iloc[bounds[i + 1] : bounds[i + 2]]
            if len(te) < 5:
                continue
            m = lgb.LGBMRegressor(
                objective="regression_l2", n_estimators=400, num_leaves=15,
                learning_rate=0.05, min_child_samples=25, subsample=0.8,
                colsample_bytree=0.8, reg_lambda=1.0, random_state=42, verbose=-1,
            )
            m.fit(tr[features_subset], tr["score"])
            pred = m.predict(te[features_subset])
            if len(set(te["score"])) > 1:
                r, _ = spearmanr(pred, te["score"])
                if not np.isnan(r):
                    rhos.append(float(r))
        return float(np.mean(rhos)) if rhos else 0.0

    one_feat_model = _cv_with([best_feat]) if uni else 0.0
    full_model = _cv_with(feats)

    print("\n=== BASELINE LADDER (CV Spearman) ===")
    print(f"  predict-mean (no ranking)          : 0.000  (floor)")
    print(f"  best single feature univariate     : {abs(best_rho):.4f}  [{best_feat}]")
    print(f"  LightGBM on best single feature    : {one_feat_model:+.4f}")
    print(f"  FULL MODEL (all {len(feats)} features)     : {full_model:+.4f}")
    print(f"\n  ML value-add over best one-line rule: {full_model - abs(best_rho):+.4f}")


@app.command()
def family(
    niche: str = typer.Option("ig_fitness"),
    label_scheme: str = typer.Option("views_per_sub_aged_v1"),
    feature_set: str = typer.Option("intrinsic"),
) -> None:
    """LightGBM vs XGBoost vs CatBoost on identical features/folds."""
    feats = _features(feature_set)
    df = build_dataframe(label_scheme=label_scheme, niche=niche)
    print(f"rows={len(df)} features={len(feats)}")

    # Impute NaNs with column means for XGBoost/CatBoost parity (LightGBM
    # handles NaN natively, but we feed all three the same matrix).
    df_imputed = df.copy()
    df_imputed[feats] = df_imputed[feats].fillna(df_imputed[feats].mean())

    factories: dict[str, Callable] = {}

    import lightgbm as lgb

    factories["LightGBM"] = lambda: lgb.LGBMRegressor(
        objective="regression_l2", n_estimators=400, num_leaves=15,
        learning_rate=0.05, min_child_samples=25, subsample=0.8,
        colsample_bytree=0.8, reg_lambda=1.0, random_state=42, verbose=-1,
    )

    try:
        import xgboost as xgb

        factories["XGBoost"] = lambda: xgb.XGBRegressor(
            n_estimators=400, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
            random_state=42, verbosity=0,
        )
    except ImportError:
        print("  (xgboost not installed -- skipping)")

    try:
        from catboost import CatBoostRegressor

        factories["CatBoost"] = lambda: CatBoostRegressor(
            iterations=400, depth=4, learning_rate=0.05,
            l2_leaf_reg=3.0, random_seed=42, verbose=0,
        )
    except ImportError:
        print("  (catboost not installed -- skipping)")

    print("\n=== MODEL FAMILY COMPARISON (CV Spearman) ===")
    for name, factory in factories.items():
        use_df = df if name == "LightGBM" else df_imputed
        mean_rho, folds = _expanding_cv_spearman(use_df, feats, factory)
        fold_str = "[" + ", ".join(f"{f:.2f}" for f in folds) + "]"
        print(f"  {name:<10} {mean_rho:.4f}  folds={fold_str}")


if __name__ == "__main__":
    app()
