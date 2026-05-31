"""What does Apify's music_info actually look like? Sample a few + see field coverage."""
import json
from collections import Counter

from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures


def main() -> None:
    with session_scope() as s:
        # 1. Show a few sample music_info dicts so we see the shape.
        sample = s.execute(
            select(Video.id, Video.music_info)
            .join(Channel, Channel.id == Video.channel_id)
            .where(
                (Channel.niche == "ig_fitness")
                & (Video.music_info.isnot(None))
            )
            .limit(5)
        ).all()
        print("=== Sample music_info dicts ===")
        for vid, info in sample:
            print(f"\n--- {vid} ---")
            print(json.dumps(info, indent=2, default=str)[:600])

        # 2. Count field presence across IG fitness reels.
        rows = s.execute(
            select(Video.music_info)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == "ig_fitness")
        ).all()
        n_total = len(rows)
        n_nonnull = sum(1 for r in rows if r[0])
        keys = Counter()
        for (info,) in rows:
            if not info:
                continue
            keys.update(info.keys())
        print(f"\n=== Field coverage across {n_nonnull}/{n_total} IG fitness reels ===")
        for k, c in keys.most_common():
            print(f"  {k:<30} {c:>5}  ({100*c/n_nonnull:5.1f}% of non-null)")

        # 3. Specifically: how many unique audio_track_id-like values?
        ids: list[str] = []
        for (info,) in rows:
            if not info:
                continue
            for k in ("audio_id", "audio_track_id", "id", "originalAudioId", "musicId"):
                if k in info and info[k]:
                    ids.append(str(info[k]))
                    break
        print(f"\nUnique audio IDs extracted (first key match): {len(set(ids))} from {len(ids)} reels")
        top = Counter(ids).most_common(10)
        print("Top 10 most-used audio IDs:")
        for aid, n in top:
            print(f"  {aid:<32}  {n}")


if __name__ == "__main__":
    main()
