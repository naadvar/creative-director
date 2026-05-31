"""How many tercile-2 winners exist per category (for the API's label scheme)?

    python -m scripts.diag_category_winners

Tells us whether category-aware examples can actually prefer same-category
winners, or whether categories are too sparse and it correctly falls back.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from api.config import api_settings
from creative_director.advice.benchmark import classify_archetype
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures, VideoLabel


def main() -> None:
    print(f"label_scheme = {api_settings.label_scheme!r}  niche = {api_settings.niche!r}")
    with session_scope() as s:
        rows = s.execute(
            select(Video.category, VideoFeatures.transcript_word_count)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .join(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == api_settings.label_scheme),
            )
            .where(Channel.niche == "ig_fitness", VideoLabel.tercile == 2)
        ).all()

    by_cat: Counter = Counter()
    by_cat_arch: Counter = Counter()
    for cat, wc in rows:
        key = cat or "(uncategorized)"
        by_cat[key] += 1
        by_cat_arch[(key, classify_archetype(wc))] += 1

    print(f"\nTotal tercile-2 winners: {sum(by_cat.values())}")
    print("\nBy category:")
    for k, n in by_cat.most_common():
        print(f"  {k:<18} {n:>4}")
    print("\nBy (category, archetype) — buckets >=3 can drive same-category examples:")
    for (k, a), n in sorted(by_cat_arch.items(), key=lambda kv: -kv[1]):
        flag = "" if n >= 3 else "   (sparse)"
        print(f"  {k:<18} {a:<8} {n:>4}{flag}")


if __name__ == "__main__":
    main()
