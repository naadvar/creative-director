"""CLI: train the preview model and print accuracy + SHAP feature importance.

    python -m scripts.train_model
    python -m scripts.train_model --label-scheme within_channel_aged_v1
    python -m scripts.train_model --task regression --feature-set intrinsic
    python -m scripts.train_model --compare        # full matrix, all schemes

Reports a single time-aware split AND expanding-window time-series CV (the
trustworthy number). feature_set='intrinsic' drops label-derived features for
a leak-free read; 'all' keeps them.
"""
import typer

from creative_director.model.train import time_series_cv, train_preview

app = typer.Typer(add_completion=False)

_SCHEMES = [
    "per_channel_log_residual_v1",
    "log_views_per_sub_v1",
    "views_per_sub_aged_v1",
    "within_channel_aged_v1",
]


def _run_one(label_scheme: str, niche: str, task: str, feature_set: str) -> None:
    r = train_preview(
        label_scheme=label_scheme, niche=niche, task=task, feature_set=feature_set
    )
    cv = time_series_cv(
        label_scheme=label_scheme, niche=niche, task=task, feature_set=feature_set
    )

    print()
    print("=" * 66)
    print(f"scheme={label_scheme}  task={task}  features={feature_set} ({r['n_features']})")
    print("=" * 66)
    print(f"Dataset      : {r['n_total']} videos  ({r['n_train']} train / {r['n_test']} test)")
    print(f"Single split : acc {r['accuracy']:.3f}   (random {r['baseline']:.3f})")
    if r["spearman"] is not None:
        print(f"               spearman {r['spearman']:.3f}   MAE {r['mae']:.3f}")
    if cv["mean_accuracy"] is not None:
        print(
            f"Time-series CV: acc {cv['mean_accuracy']:.3f} +/- {cv['std_accuracy']:.3f}"
            f"   ({cv['n_folds_used']} folds)  folds={[round(a, 2) for a in cv['fold_accuracies']]}"
        )
    if cv["mean_spearman"] is not None:
        print(f"               spearman {cv['mean_spearman']:.3f} (CV mean)")
    print()
    print(r["report"])
    print("Confusion matrix (rows=true, cols=pred), order [low, med, high]:")
    print(r["confusion"])
    print()
    print("Top 15 features by mean |SHAP|:")
    for name, val in r["shap_importance"][:15]:
        print(f"  {name:24} {val:.4f}")


@app.command()
def main(
    label_scheme: str = typer.Option("within_channel_aged_v1", help="VideoLabel scheme"),
    niche: str = typer.Option("fitness", help="Niche to train on"),
    task: str = typer.Option("classification", help="classification | regression"),
    feature_set: str = typer.Option("all", help="all | intrinsic"),
    compare: bool = typer.Option(False, help="Run the full matrix across all schemes"),
):
    if compare:
        for scheme in _SCHEMES:
            for t in ("classification", "regression"):
                for fs in ("all", "intrinsic"):
                    try:
                        _run_one(scheme, niche, t, fs)
                    except Exception as e:  # noqa: BLE001
                        print(f"\n[skip] {scheme} {t} {fs}: {e}")
    else:
        _run_one(label_scheme, niche, task, feature_set)


if __name__ == "__main__":
    app()
