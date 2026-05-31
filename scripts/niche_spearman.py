"""CLI: does niche-specific training beat a pooled model on held-out Spearman?

The decision experiment for the new IG niches. Reports time-series-CV Spearman on
the leak-free intrinsic feature set and the channel-normalized
within_channel_aged_v1 label (the most honest read):

  1. Per-niche CV Spearman -- the existing expanding-window time_series_cv, trained
     and tested within each niche. Tells us whether the model finds real within-niche
     signal at all (fitness sits ~0.5 today).

  2. Pooled vs niche -- on a SINGLE feature build over the target niches (shared PCA
     basis) with a fixed per-niche time-tail test set: train on the pooled
     target-niche corpus vs train on that niche alone, compare Spearman on the same
     test set. Isolates the value of niche-specificity from the value of more data.

    python -m scripts.niche_spearman
    python -m scripts.niche_spearman --label-scheme views_per_sub_aged_v1
    python -m scripts.niche_spearman --niches ig_food,ig_travel
"""
from __future__ import annotations

import numpy as np
import typer
from scipy.stats import spearmanr

from creative_director.model.dataset import INTRINSIC_FEATURES, build_dataframe
from creative_director.model.train import time_series_cv

app = typer.Typer(add_completion=False)

_DEFAULT_NICHES = "ig_food,ig_travel,ig_fashion"


def _fit_predict(train_df, test_df, features) -> np.ndarray:
    import lightgbm as lgb

    m = lgb.LGBMRegressor(
        objective="regression_l2", n_estimators=200, num_leaves=15,
        learning_rate=0.05, min_child_samples=15, subsample=0.8,
        colsample_bytree=0.8, reg_lambda=1.0, random_state=42, verbose=-1,
    )
    m.fit(train_df[features], train_df["score"])
    return np.asarray(m.predict(test_df[features]))


@app.command()
def main(
    label_scheme: str = typer.Option("within_channel_aged_v1", help="VideoLabel scheme"),
    niches: str = typer.Option(_DEFAULT_NICHES, help="Comma-separated target niches"),
    test_frac: float = typer.Option(0.2, help="Held-out tail fraction per niche"),
) -> None:
    target = [n.strip() for n in niches.split(",") if n.strip()]
    features = INTRINSIC_FEATURES
    print(f"label_scheme={label_scheme}  features=intrinsic ({len(features)})  niches={target}")

    # --- 1. Per-niche CV Spearman (trusted expanding-window harness) ---
    print("\n=== 1. Per-niche time-series CV Spearman (regression, intrinsic) ===")
    print(f"{'niche':14}{'n':>7}{'folds':>7}{'CV-spearman':>14}")
    for n in target + ["fitness"]:
        try:
            cv = time_series_cv(
                label_scheme=label_scheme, niche=n,
                task="regression", feature_set="intrinsic",
            )
            rho = cv["mean_spearman"]
            rho_s = f"{rho:+.3f}" if rho is not None else "n/a"
            print(f"{n:14}{cv['n_total']:>7}{cv['n_folds_used']:>7}{rho_s:>14}")
        except Exception as e:  # noqa: BLE001
            print(f"{n:14}  skip: {e}")

    # --- 2. Pooled vs niche on a shared feature build over the target niches ---
    print("\n=== 2. Pooled-vs-niche (shared features, fixed per-niche test tail) ===")
    df = build_dataframe(label_scheme=label_scheme, niche=target)
    if df.empty or "niche" not in df.columns:
        print("  (no rows / missing niche column)")
        raise typer.Exit()
    df = df.sort_values("published_at").reset_index(drop=True)
    print(f"  pooled rows={len(df)}  counts={df['niche'].value_counts().to_dict()}")
    print(f"{'niche':14}{'n_test':>8}{'pooled':>10}{'niche':>10}{'delta':>10}")
    for n in target:
        sub = df[df["niche"] == n].sort_values("published_at")
        if len(sub) < 40:
            print(f"{n:14}  too few ({len(sub)})")
            continue
        split = int(len(sub) * (1 - test_frac))
        cutoff = sub.iloc[split]["published_at"]
        test_ids = set(sub.iloc[split:]["video_id"])
        test_df = df[df["video_id"].isin(test_ids)]
        if len(test_df) < 5 or test_df["score"].nunique() < 2:
            print(f"{n:14}  test too small")
            continue
        # Strictly-past training rows (time-aware), excluding the test tail.
        pooled_train = df[(df["published_at"] < cutoff) & (~df["video_id"].isin(test_ids))]
        niche_train = pooled_train[pooled_train["niche"] == n]
        if len(niche_train) < 30 or len(pooled_train) < 30:
            print(f"{n:14}  train too small (pooled={len(pooled_train)}, niche={len(niche_train)})")
            continue
        rho_pool = spearmanr(_fit_predict(pooled_train, test_df, features), test_df["score"])[0]
        rho_niche = spearmanr(_fit_predict(niche_train, test_df, features), test_df["score"])[0]
        print(
            f"{n:14}{len(test_df):>8}{rho_pool:>+10.3f}{rho_niche:>+10.3f}"
            f"{rho_niche - rho_pool:>+10.3f}"
        )

    print("\nRead: delta>0 => niche-specific training helps; <=0 => pooling (more data) wins.")


if __name__ == "__main__":
    app()
