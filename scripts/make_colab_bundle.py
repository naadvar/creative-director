"""CLI: build the zip bundle to upload to Drive for Colab feature extraction.

Bundles: the project code, a copy of the DB, the colab_processor notebook, and
the video files + thumbnails for videos that still need feature extraction.
Only the target media is included, so the upload stays small.

    python -m scripts.make_colab_bundle --niche fitness

Then upload data/colab_bundle.zip to Drive and unzip to
/content/drive/MyDrive/creative-director.
"""
import zipfile
from pathlib import Path

import typer
from loguru import logger
from sqlalchemy import select

from creative_director.config import settings
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel

app = typer.Typer(add_completion=False)

_AGED_SCHEMES = ("views_per_sub_aged_v1", "within_channel_aged_v1")


@app.command()
def main(
    niche: str = typer.Option("fitness", help="Niche to scope the bundle to"),
    out: Path = typer.Option(Path("data/colab_bundle.zip"), help="Output zip path"),
    all_labeled: bool = typer.Option(
        False, help="Include every niche video lacking features (not just age-banded)"
    ),
):
    root = Path(".")
    videos_dir = settings.video_archive_dir or Path("data/videos")
    thumbs_dir = settings.thumbnail_dir
    db_path = Path("data/creative_director.db")

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
    logger.info(f"{len(target_ids)} videos need extraction (niche={niche})")

    out.parent.mkdir(parents=True, exist_ok=True)
    n_code = n_vid = n_thumb = missing_vid = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        # Project code.
        for sub in ("creative_director", "scripts", "notebooks", "colab_bridge"):
            for p in (root / sub).rglob("*.py"):
                if "__pycache__" in p.parts:
                    continue
                z.write(p, str(p.relative_to(root)))
                n_code += 1
        for extra in ("notebooks/colab_processor.ipynb", "requirements.txt"):
            p = root / extra
            if p.exists():
                z.write(p, extra)

        # DB.
        if not db_path.exists():
            raise FileNotFoundError(f"DB not found: {db_path}")
        z.write(db_path, "data/creative_director.db")

        # Media for the target videos only.
        for vid in target_ids:
            mp4 = videos_dir / f"{vid}.mp4"
            if mp4.exists():
                z.write(mp4, f"data/videos/{vid}.mp4")
                n_vid += 1
            else:
                missing_vid += 1
            jpg = thumbs_dir / f"{vid}.jpg"
            if jpg.exists():
                z.write(jpg, f"data/thumbnails/{vid}.jpg")
                n_thumb += 1

    size_mb = out.stat().st_size / 1e6
    logger.info(
        f"Bundle written: {out}  ({size_mb:.0f} MB)  "
        f"{n_code} code files, {n_vid} videos, {n_thumb} thumbnails"
    )
    if missing_vid:
        logger.warning(
            f"{missing_vid} target videos have no downloaded file yet — "
            f"run scripts.download_videos first, or they will be skipped on Colab."
        )


if __name__ == "__main__":
    app()
