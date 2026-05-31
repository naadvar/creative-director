"""Backfill music metadata for every reel that has Apify music_info.

Computes ``music_audio_id_corpus_uses`` per niche (so a Jeff Nippard
audio_id usage count is computed against the IG corpus, not the YT corpus).
"""
from __future__ import annotations

from sqlalchemy import select

from creative_director.features.music import audio_id_corpus_counts, extract_features
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures


def main() -> None:
    # Iterate one niche at a time so the corpus-uses count is niche-local.
    with session_scope() as s:
        niches = [r[0] for r in s.execute(select(Channel.niche).distinct()).all() if r[0]]
    print(f"Niches: {niches}")

    for niche in niches:
        with session_scope() as s:
            rows = s.execute(
                select(Video.id, Video.music_info)
                .join(Channel, Channel.id == Video.channel_id)
                .where(Channel.niche == niche)
            ).all()
        n = len(rows)
        if n == 0:
            continue
        print(f"\n=== {niche}: {n} videos ===")

        infos = [info for _vid, info in rows]
        counts = audio_id_corpus_counts(infos)
        if counts:
            print(
                f"  unique audio_ids={len(counts)}; "
                f"max_uses={max(counts.values())}; "
                f">=5_uses={sum(1 for v in counts.values() if v >= 5)}"
            )

        written = 0
        with session_scope() as s:
            for vid, info in rows:
                d = extract_features(info)
                f = s.get(VideoFeatures, vid)
                if f is None:
                    continue
                f.music_uses_original = d["music_uses_original"]
                f.music_audio_id = d["music_audio_id"]
                if d["music_audio_id"] and counts.get(d["music_audio_id"]):
                    f.music_audio_id_corpus_uses = counts[d["music_audio_id"]]
                else:
                    f.music_audio_id_corpus_uses = None
                written += 1
        print(f"  wrote {written} rows")


if __name__ == "__main__":
    main()
