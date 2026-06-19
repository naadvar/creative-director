"""Consistent backup of the local SQLite DB to R2.

Why this exists: the corpus extraction + craft-reads live ONLY in the local
SQLite file. This makes a transactionally-consistent snapshot (VACUUM INTO,
WAL-safe even with the demo backend attached), verifies its integrity and the
craft-read count BEFORE touching R2, uploads it to a dated key, then points the
canonical pull location (db/creative_director.db) at it via a server-side copy.

    python -m scripts.backup_db_to_r2

The previous canonical backup is never blindly destroyed: the new upload lands on
its own dated key first; only after that succeeds is the canonical pointer moved.
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
import tempfile
from pathlib import Path

from loguru import logger
from sqlalchemy.engine import make_url

from creative_director.config import settings
from creative_director.storage import media

CANONICAL_KEY = "db/creative_director.db"


def _db_path() -> Path:
    p = make_url(settings.database_url).database
    if not p:
        raise SystemExit(f"could not parse a file path from database_url")
    return Path(p).resolve()


def main() -> None:
    src = _db_path()
    if not src.exists():
        raise SystemExit(f"local DB not found: {src}")
    size_mb = src.stat().st_size / 1e6
    logger.info(f"source DB: {src} ({size_mb:.1f} MB)")

    snap = Path(tempfile.gettempdir()) / "ccd_db_snapshot.db"
    snap.unlink(missing_ok=True)

    # 1. Consistent snapshot — VACUUM INTO reads a point-in-time view of the live
    #    DB (WAL-safe) and writes a clean, defragmented single file.
    logger.info("VACUUM INTO snapshot ...")
    conn = sqlite3.connect(str(src), timeout=60)
    try:
        conn.execute("PRAGMA busy_timeout=60000")
        conn.execute(f"VACUUM INTO '{snap.as_posix()}'")
    finally:
        conn.close()
    logger.info(f"snapshot: {snap} ({snap.stat().st_size/1e6:.1f} MB)")

    # 2. Verify the snapshot BEFORE it goes anywhere near R2.
    v = sqlite3.connect(str(snap))
    try:
        integ = v.execute("PRAGMA integrity_check").fetchone()[0]
        craft = v.execute(
            "SELECT COUNT(*) FROM video_features WHERE craft_read IS NOT NULL"
        ).fetchone()[0]
        vids = v.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    finally:
        v.close()
    logger.info(f"integrity_check={integ!r}  videos={vids}  craft_reads={craft}")
    if integ != "ok":
        raise SystemExit(f"ABORT: integrity_check failed: {integ!r}")
    if craft < 3000:
        raise SystemExit(f"ABORT: only {craft} craft_reads (<3000) — snapshot looks wrong")

    # 3. Upload to a dated key first (purely additive — destroys nothing).
    today = _dt.date.today().isoformat()
    dated_key = f"db/creative_director_{today}.db"
    logger.info(f"uploading -> r2://{settings.r2_bucket}/{dated_key} ...")
    media.upload(snap, dated_key, "application/x-sqlite3")

    # 4. Move the canonical pointer via a cheap server-side copy (no re-upload).
    c = media._client()
    logger.info(f"server-side copy -> {CANONICAL_KEY} ...")
    c.copy_object(
        Bucket=settings.r2_bucket,
        CopySource={"Bucket": settings.r2_bucket, "Key": dated_key},
        Key=CANONICAL_KEY,
        ContentType="application/x-sqlite3",
        MetadataDirective="REPLACE",
    )

    # 5. Confirm.
    for k in (dated_key, CANONICAL_KEY):
        h = c.head_object(Bucket=settings.r2_bucket, Key=k)
        logger.info(f"  R2 {k}: {h['ContentLength']/1e6:.1f} MB  {h['LastModified']}")
    snap.unlink(missing_ok=True)
    logger.info(f"DONE — backed up {craft} craft_reads / {vids} videos to R2")


if __name__ == "__main__":
    main()
