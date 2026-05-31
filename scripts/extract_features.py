"""CLI: extract VideoFeatures for already-ingested videos that lack them.

Scoped feature-extraction pass for the deepened corpus. Metadata-only ingest
leaves videos without a VideoFeatures row (and without a downloaded file);
this script downloads + featurises a targeted subset.

Default scope: a niche's videos that carry an age-banded label
(views_per_sub_aged_v1 / within_channel_aged_v1) but have no features yet —
i.e. exactly the videos that would expand the model's training set.

Resumable: videos that already have a VideoFeatures row are skipped.
Honours the duty-cycle thermal cooldown from settings.

    python -m scripts.extract_features --niche fitness --limit 3   # smoke test
    python -m scripts.extract_features --niche fitness             # full scoped run
"""
import os

# Cap BLAS/OpenMP thread pools BEFORE numpy/torch are imported (they read these
# at import time). Keeps peak CPU power draw down so the chip stays off TjMAX.
# A launcher env var still wins via setdefault.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "4")

import time
from pathlib import Path

import typer
from loguru import logger
from sqlalchemy import select

from creative_director.config import settings
from creative_director.ingestion.pipeline import extract_all_features, persist_features
from creative_director.storage.db import init_db, session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel

app = typer.Typer(add_completion=False)

_AGED_SCHEMES = ("views_per_sub_aged_v1", "within_channel_aged_v1")


@app.command()
def main(
    niche: str = typer.Option("fitness", help="Niche to scope the run to"),
    limit: int = typer.Option(0, help="Max videos to process (0 = all targets)"),
    all_labeled: bool = typer.Option(
        False, help="Process every niche video (not just age-banded-labelled ones)"
    ),
    threads: int = typer.Option(
        4, help="Cap CPU threads for ML inference (0 = uncapped, for GPU/cloud)"
    ),
    shard: str = typer.Option(
        "", help="Process only shard i/n of the targets, e.g. 0/6 (for parallel runs)"
    ),
):
    init_db()

    # Cap ML inference threads so the CPU stays off TjMAX. The BLAS pools were
    # already capped at import time; this covers torch and Whisper. threads<=0
    # leaves everything uncapped — correct for a Colab GPU run.
    if threads > 0:
        settings.cpu_threads = threads
        import torch

        torch.set_num_threads(threads)
        logger.info(f"CPU threads capped at {threads} (torch + Whisper + BLAS pools)")
    else:
        settings.cpu_threads = 0
        logger.info("CPU threads uncapped (GPU/cloud mode)")

    with session_scope() as s:
        q = (
            select(Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .outerjoin(VideoFeatures, VideoFeatures.video_id == Video.id)
            .where(Channel.niche == niche, VideoFeatures.video_id.is_(None))
        )
        if not all_labeled:
            q = q.join(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme.in_(_AGED_SCHEMES)),
            )
        target_ids = sorted(set(s.execute(q).scalars().all()))

    # Shard the (deterministically sorted) target list across parallel workers:
    # worker i of n takes every n-th id -> disjoint, evenly distributed.
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        target_ids = target_ids[i::n]
        logger.info(f"shard {i}/{n}: {len(target_ids)} of the targets")

    if limit:
        target_ids = target_ids[:limit]
    logger.info(f"{len(target_ids)} videos to featurise (niche={niche})")

    done = 0
    failed = 0
    for video_id in target_ids:
        try:
            with session_scope() as s:
                video = s.get(Video, video_id)
                if video is None:
                    continue
                # Resolve the thumbnail by convention ({thumbnail_dir}/{id}.jpg)
                # rather than the stored path — the DB holds Windows paths that
                # do not resolve on a Colab/Linux run.
                thumb_path = settings.thumbnail_dir / f"{video_id}.jpg"
                if not thumb_path.exists():
                    thumb_path = None
                features = extract_all_features(video, thumb_path)
                persist_features(s, video_id, features)
            done += 1
            logger.info(f"[{done}/{len(target_ids)}] {video_id}: featurised")
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"{video_id}: feature extraction failed: {e}")

        # Duty-cycle thermal cooldown — let the CPU settle.
        if (
            settings.cooldown_every_n_videos
            and (done + failed) % settings.cooldown_every_n_videos == 0
        ):
            logger.info(
                f"Thermal cooldown: pausing {settings.cooldown_seconds}s "
                f"after {done + failed} videos"
            )
            time.sleep(settings.cooldown_seconds)

    logger.info(f"Done. {done} featurised, {failed} failed.")


if __name__ == "__main__":
    app()
