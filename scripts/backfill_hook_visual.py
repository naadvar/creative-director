"""Wave 2 backfill: extract visual frame features from mp4s (GPU pod).

Reads each IG reel's archived mp4, runs creative_director.features.hook_visual
.extract_hook_visual (face fill/headroom/frontal, CLIP image embedding, CLIP
emotion, edge-density clutter, action-first), and writes the results to the
new video_features columns. Run AFTER migrate adds the columns and the mp4s
are present on the pod.

    PYTHONPATH=. python3 -u scripts/backfill_hook_visual.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from sqlalchemy import select

from creative_director.config import settings
from creative_director.features.hook_visual import extract_hook_visual
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

# extract_hook_visual key -> VideoFeatures column.
_SCALAR_MAP = {
    "hook_face_fill": "hook_face_fill",
    "hook_face_headroom": "hook_face_headroom",
    "hook_frontal_ratio": "hook_frontal_ratio",
    "hook_face_present_frac": "hook_face_present_frac",
    "hook_background_clutter": "hook_background_clutter",
    "hook_is_action_first": "hook_is_action_first",
    "hook_motion_first": "hook_motion_first",
    "emotion_happy": "hook_emotion_happy",
    "emotion_intense": "hook_emotion_intense",
    "emotion_surprised": "hook_emotion_surprised",
    "emotion_neutral": "hook_emotion_neutral",
}


def _log(m: str) -> None:
    print(m, flush=True)
    sys.stdout.flush()


def main() -> None:
    archive = settings.video_archive_dir or Path("data/videos")
    # Only IG reels (the cohort we have mp4s for); only those still missing the
    # visual features (resume-safe).
    with session_scope() as s:
        ids = [
            r[0]
            for r in s.execute(
                select(VideoFeatures.video_id)
                .join(Video, Video.id == VideoFeatures.video_id)
                .join(Channel, Channel.id == Video.channel_id)
                .where(
                    (Channel.niche == "ig_fitness")
                    & (VideoFeatures.hook_face_present_frac.is_(None))
                )
            ).all()
        ]
    _log(f"Wave-2 visual backfill: {len(ids)} reels to process (archive: {archive})")

    written = 0
    skipped = 0
    start = time.monotonic()
    for i, vid in enumerate(ids):
        mp4 = archive / f"{vid}.mp4"
        if not mp4.exists():
            skipped += 1
            continue
        d = extract_hook_visual(mp4)
        if d is None:
            skipped += 1
            continue
        with session_scope() as s:
            f = s.get(VideoFeatures, vid)
            if f is None:
                continue
            for src_key, col in _SCALAR_MAP.items():
                if src_key in d and d[src_key] is not None:
                    setattr(f, col, float(d[src_key]))
            if d.get("hook_clip_embedding"):
                f.hook_clip_image_embedding = d["hook_clip_embedding"]
            written += 1
        if (i + 1) % 100 == 0:
            elapsed = time.monotonic() - start
            rate = (i + 1) / max(elapsed, 1e-6)
            eta = (len(ids) - (i + 1)) / max(rate, 1e-6)
            _log(f"  ...{i+1}/{len(ids)} wrote={written} skip={skipped} {rate:.1f}/s ETA {eta/60:.1f}m")
    _log(f"Done. wrote={written} skipped={skipped}")


if __name__ == "__main__":
    main()
