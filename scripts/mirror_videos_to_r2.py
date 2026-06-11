"""Mirror the local video archive to R2 (videos/{id}.mp4), resumably.

Skips objects already in R2 (HEAD check), so re-running after an interruption
only uploads what's missing. Excludes up_* (private uploads stay local-only).

    python -m scripts.mirror_videos_to_r2            # mirror everything missing
    python -m scripts.mirror_videos_to_r2 --limit 5  # smoke test
    python -m scripts.mirror_videos_to_r2 --verify   # report-only, no uploads
"""
from __future__ import annotations

import concurrent.futures as cf
import glob
import os
import threading
from pathlib import Path

import typer
from loguru import logger

from creative_director.config import settings
from creative_director.storage import media

app = typer.Typer(add_completion=False)

_lock = threading.Lock()
_done = {"uploaded": 0, "skipped": 0, "failed": 0, "bytes": 0}


def _exists(client, key: str) -> bool:
    import botocore

    try:
        client.head_object(Bucket=settings.r2_bucket, Key=key)
        return True
    except botocore.exceptions.ClientError:
        return False


def _mirror_one(path: Path, verify_only: bool) -> None:
    client = media._client()  # boto3 clients are thread-safe
    key = f"videos/{path.name}"
    try:
        if _exists(client, key):
            with _lock:
                _done["skipped"] += 1
            return
        if verify_only:
            with _lock:
                _done["failed"] += 1  # counts as "missing" in verify mode
            return
        client.upload_file(
            str(path), settings.r2_bucket, key, ExtraArgs={"ContentType": "video/mp4"}
        )
        with _lock:
            _done["uploaded"] += 1
            _done["bytes"] += os.path.getsize(path)
            n = _done["uploaded"]
        if n % 100 == 0:
            logger.info(f"{n} uploaded ({_done['bytes']/1e9:.1f} GB so far)")
    except Exception as e:  # noqa: BLE001
        with _lock:
            _done["failed"] += 1
        logger.warning(f"{path.name}: {e}")


@app.command()
def main(
    limit: int = typer.Option(0, help="Max files to process (0 = all)"),
    workers: int = typer.Option(6, help="Parallel upload threads"),
    verify: bool = typer.Option(False, "--verify", help="Report-only: count present/missing"),
) -> None:
    archive = settings.video_archive_dir or Path("data/videos")
    files = sorted(
        Path(f)
        for f in glob.glob(str(archive / "*.mp4"))
        if not Path(f).name.startswith("up_")
    )
    if limit:
        files = files[:limit]
    total_gb = sum(os.path.getsize(f) for f in files) / 1e9
    logger.info(f"{len(files)} local mp4s ({total_gb:.1f} GB) -> r2://{settings.r2_bucket}/videos/")

    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda p: _mirror_one(p, verify), files))

    label = "missing" if verify else "failed"
    logger.info(
        f"DONE. uploaded={_done['uploaded']} already-present={_done['skipped']} "
        f"{label}={_done['failed']} ({_done['bytes']/1e9:.1f} GB sent)"
    )
    print(
        f"MIRROR_RESULT uploaded={_done['uploaded']} present={_done['skipped']} {label}={_done['failed']}"
    )


if __name__ == "__main__":
    app()
