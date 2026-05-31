"""Train a preview model and explain it with SHAP.

This is a PREVIEW model. With a few hundred rows its absolute accuracy is not
the point — the point is whether there is real, generalising signal.

Three things this module does beyond the original 3-class single-split:

  - REGRESSION target. The label score is continuous; bucketing it into 3
    terciles before training throws away ordering information and makes two
    near-identical videos either side of a cutoff look maximally different.
    Regressing the raw score and reporting Spearman correlation is the more
    honest read. A tercile accuracy is still derived (bin predictions by the
    train set's tercile cutoffs) so it stays comparable to the classifier.

  - TIME-SERIES CV. A single 80/20 time split tests on ~40 videos — one lucky
    or unlucky tail dominates. Expanding-window CV evaluates on several
    successive tails and reports mean +/- std, which is the trustworthy number.

  - FEATURE SET switch. Some features are label-derived (see dataset.py
    LABEL_DERIVED_FEATURES). feature_set="intrinsic" drops them for a
    leak-free number; "all" keeps them (mild optimistic bias).
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from creative_director.model.dataset import (
    FEATURE_NAMES,
    INTRINSIC_FEATURES,
    LABEL_DERIVED_FEATURES,
    build_dataframe,
)


def _feature_list(feature_set: str) -> list[str]:
    if feature_set == "intrinsic":
        return INTRINSIC_FEATURES
    if feature_set == "all":
        return FEATURE_NAMES
    raise ValueError(f"feature_set must be 'all' or 'intrinsic', got {feature_set!r}")


def _terciles_from(scores: np.ndarray, q33: float, q67: float) -> np.ndarray:
    """Bucket continuous scores into 0/1/2 by fixed cutoffs."""
    out = np.ones(len(scores), dtype=int)
    out[scores < q33] = 0
    out[scores >= q67] = 2
    return out


def train_preview(
    label_scheme: str = "per_channel_log_residual_v1",
    niche: str = "fitness",
    test_frac: float = 0.2,
    task: str = "classification",
    feature_set: str = "all",
) -> dict:
    """Single time-aware split. task = 'classification' | 'regression'."""
    import lightgbm as lgb

    features = _feature_list(feature_set)
    df = build_dataframe(label_scheme=label_scheme, niche=niche)
    if len(df) < 30:
        raise RuntimeError(f"Only {len(df)} labeled videos — too few to train.")

    # Time-aware split: train on older videos, test on the most recent.
    df = df.sort_values("published_at").reset_index(drop=True)
    split = int(len(df) * (1 - test_frac))
    train_df, test_df = df.iloc[:split], df.iloc[split:]

    X_train, X_test = train_df[features], test_df[features]

    if task == "regression":
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
        model.fit(X_train, train_df["score"])
        pred_score = model.predict(X_test)

        from scipy.stats import spearmanr

        rho, _ = spearmanr(pred_score, test_df["score"])
        # Derive a tercile accuracy using the TRAIN score distribution's cutoffs.
        q33, q67 = np.quantile(train_df["score"], [1 / 3, 2 / 3])
        preds = _terciles_from(np.asarray(pred_score), q33, q67)
        y_test = test_df["tercile"].to_numpy()
        acc = float(accuracy_score(y_test, preds))
        report = classification_report(
            y_test, preds, target_names=["low", "med", "high"], zero_division=0
        )
        cm = confusion_matrix(y_test, preds, labels=[0, 1, 2])
        mae = float(np.mean(np.abs(pred_score - test_df["score"].to_numpy())))
    else:
        model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            n_estimators=150,
            num_leaves=15,
            learning_rate=0.05,
            min_child_samples=15,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, train_df["tercile"])
        preds = model.predict(X_test)
        y_test = test_df["tercile"].to_numpy()
        acc = float(accuracy_score(y_test, preds))
        report = classification_report(
            y_test, preds, target_names=["low", "med", "high"], zero_division=0
        )
        cm = confusion_matrix(y_test, preds, labels=[0, 1, 2])
        rho, mae = None, None

    # --- SHAP feature importance (mean |SHAP| aggregated over classes) ---
    import shap

    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(X_test)
    if isinstance(sv, list):  # older shap: list of (n, features) per class
        mean_abs = np.mean([np.abs(a).mean(axis=0) for a in sv], axis=0)
    else:
        arr = np.abs(np.asarray(sv))
        if arr.ndim == 3:  # (n, features, classes)
            mean_abs = arr.mean(axis=(0, 2))
        else:  # (n, features)
            mean_abs = arr.mean(axis=0)
    shap_importance = sorted(zip(features, mean_abs.tolist()), key=lambda x: -x[1])

    return {
        "task": task,
        "feature_set": feature_set,
        "n_features": len(features),
        "n_total": len(df),
        "n_train": len(train_df),
        "n_test": len(test_df),
        "accuracy": acc,
        "baseline": 1.0 / 3.0,
        "spearman": rho,
        "mae": mae,
        "report": report,
        "confusion": cm,
        "shap_importance": shap_importance,
        "model": model,
    }


def time_series_cv(
    label_scheme: str = "per_channel_log_residual_v1",
    niche: str = "fitness",
    n_folds: int = 5,
    task: str = "classification",
    feature_set: str = "all",
) -> dict:
    """Expanding-window cross-validation over time-ordered videos.

    The corpus is cut into n_folds+1 contiguous chunks by publish date. Fold i
    trains on chunks 0..i and tests on chunk i+1, so every test set is strictly
    in the future relative to its training data. Reports mean +/- std accuracy
    — far more trustworthy than one 80/20 tail.
    """
    import lightgbm as lgb
    from scipy.stats import spearmanr

    features = _feature_list(feature_set)
    df = build_dataframe(label_scheme=label_scheme, niche=niche)
    if len(df) < 60:
        raise RuntimeError(f"Only {len(df)} labeled videos — too few for {n_folds}-fold CV.")

    df = df.sort_values("published_at").reset_index(drop=True)
    bounds = np.linspace(0, len(df), n_folds + 2, dtype=int)

    fold_acc: list[float] = []
    fold_rho: list[float] = []
    for i in range(n_folds):
        tr = df.iloc[: bounds[i + 1]]
        te = df.iloc[bounds[i + 1] : bounds[i + 2]]
        if len(te) < 5 or tr["tercile"].nunique() < 2:
            continue
        X_tr, X_te = tr[features], te[features]
        y_te = te["tercile"].to_numpy()

        if task == "regression":
            m = lgb.LGBMRegressor(
                objective="regression_l2", n_estimators=200, num_leaves=15,
                learning_rate=0.05, min_child_samples=15, subsample=0.8,
                colsample_bytree=0.8, reg_lambda=1.0, random_state=42, verbose=-1,
            )
            m.fit(X_tr, tr["score"])
            pred_score = m.predict(X_te)
            q33, q67 = np.quantile(tr["score"], [1 / 3, 2 / 3])
            preds = _terciles_from(np.asarray(pred_score), q33, q67)
            if len(set(te["score"])) > 1:
                rho, _ = spearmanr(pred_score, te["score"])
                fold_rho.append(float(rho))
        else:
            m = lgb.LGBMClassifier(
                objective="multiclass", num_class=3, n_estimators=150,
                num_leaves=15, learning_rate=0.05, min_child_samples=15,
                subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
                random_state=42, verbose=-1,
            )
            m.fit(X_tr, tr["tercile"])
            preds = m.predict(X_te)
        fold_acc.append(float(accuracy_score(y_te, preds)))

    return {
        "task": task,
        "feature_set": feature_set,
        "n_features": len(features),
        "n_total": len(df),
        "n_folds_used": len(fold_acc),
        "fold_accuracies": fold_acc,
        "mean_accuracy": float(np.mean(fold_acc)) if fold_acc else None,
        "std_accuracy": float(np.std(fold_acc)) if fold_acc else None,
        "mean_spearman": float(np.mean(fold_rho)) if fold_rho else None,
        "baseline": 1.0 / 3.0,
    }
