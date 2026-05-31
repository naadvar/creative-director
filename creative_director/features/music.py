"""Music / audio-track metadata features from the Apify scraper output.

For IG specifically the audit showed:
  - 91.7% of reels have music_info populated
  - 91%+ of those use ORIGINAL audio (creator-made narration)
  - 4214 unique audio_ids across 4739 reels => median 1 reel per id

So the "trending audio detection" play I'd hoped for is weak in fitness:
the top "trending" track is used 11 times in the entire corpus. What IS
clean here is the binary ``uses_original_audio`` -- it cleanly separates
the "I'm an expert with a thing to say" creators (Jeff Nippard, Squat
University, science explainers) from the "I ride trending sounds" set.
We surface that plus a count of how many other reels in the corpus use
the same audio_id (trending-strength proxy at our scale).

YT reels have no Apify music_info -- the model handles this with LightGBM's
missing-value support (NaN passed through).
"""
from __future__ import annotations

from collections import Counter
from typing import Optional


def extract_features(music_info: Optional[dict]) -> dict:
    """Pull the two scalar features from Apify's music_info dict.

    Returns None values when music_info is missing -- the caller writes
    None to the column, which becomes NaN in the model dataframe.
    """
    if not music_info:
        return {
            "music_uses_original": None,
            "music_audio_id": None,
        }
    audio_id_raw = music_info.get("audio_id")
    # Skip the "no audio" placeholder ("0") that Apify uses for muted reels.
    audio_id = (
        str(audio_id_raw) if audio_id_raw not in (None, "", 0, "0") else None
    )
    uses_original_raw = music_info.get("uses_original_audio")
    # Cast to 0/1 -- some rows have bool, some have None.
    if uses_original_raw is None:
        uses_original = None
    else:
        uses_original = 1 if uses_original_raw else 0
    return {
        "music_uses_original": uses_original,
        "music_audio_id": audio_id,
    }


def audio_id_corpus_counts(music_infos: list[Optional[dict]]) -> Counter:
    """Count how many reels in a corpus share each audio_id.

    Build once per niche; each reel's count is then a "how trending is
    this audio across the corpus" proxy.
    """
    c: Counter = Counter()
    for info in music_infos:
        if not info:
            continue
        aid = info.get("audio_id")
        if aid in (None, "", 0, "0"):
            continue
        c[str(aid)] += 1
    return c
