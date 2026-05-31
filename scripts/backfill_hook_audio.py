"""Backfill hook-audio features for every reel that has an archived mp4."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import select

from creative_director.config import settings
from creative_director.features.hook_audio import extract_hook_audio
from creative_director.storage.db import session_scope
from creative_director.storage.models import VideoFeatures


BATCH = 50


def _log(msg: str) -> None:
    print(msg, flush=True)
    sys.stdout.flush()


def main() -> None:
    archive = settings.video_archive_dir or Path("data/videos")
    with session_scope() as s:
        # Only reels with an archived mp4 are reachable; pre-filter by file
        # existence so we don't waste time on the metadata-only niches.
        all_ids = [r[0] for r in s.execute(select(VideoFeatures.video_id)).all()]
    ids = [vid for vid in all_ids if (archive / f"{vid}.mp4").exists()]
    _log(f"Backfilling hook-audio features for {len(ids)} reels with mp4 (of {len(all_ids)} total)")

    written = 0
    skipped = 0
    start = time.monotonic()
    for i in range(0, len(ids), BATCH):
        chunk_ids = ids[i : i + BATCH]
        with session_scope() as s:
            feats = (
                s.execute(
                    select(VideoFeatures).where(VideoFeatures.video_id.in_(chunk_ids))
                )
                .scalars()
                .all()
            )
            for feat in feats:
                mp4 = archive / f"{feat.video_id}.mp4"
                if not mp4.exists():
                    skipped += 1
                    continue
                d = extract_hook_audio(mp4, feat.transcript_first_3s)
                if d is None:
                    skipped += 1
                    continue
                feat.hook_audio_peak_loudness = d["hook_audio_peak_loudness"]
                feat.hook_audio_mean_loudness = d["hook_audio_mean_loudness"]
                feat.hook_audio_attack_rate = d["hook_audio_attack_rate"]
                feat.hook_audio_is_voice = d["hook_audio_is_voice"]
                written += 1
        elapsed = time.monotonic() - start
        rate = (written + skipped) / max(elapsed, 1e-6)
        eta = (len(ids) - (written + skipped)) / max(rate, 1e-6)
        _log(
            f"  ...{written + skipped}/{len(ids)}  wrote={written} skipped={skipped}  "
            f"{rate:.1f}/s  ETA {eta/60:.1f}m"
        )
    _log(f"Done. wrote={written}, skipped={skipped}")


if __name__ == "__main__":
    main()
