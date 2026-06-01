"""Add videos.category/category_confirmed (idempotent) and backfill the corpus
with the keyword classifier.

    python -m scripts.backfill_categories
"""
from __future__ import annotations

import sqlite3
from collections import Counter

from sqlalchemy import select

from creative_director.advice.categories import classify, label_for
from creative_director.config import settings
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video


def _migrate() -> None:
    db = str(settings.database_url).replace("sqlite:///", "")
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(videos)")}
    for name, decl in [("category", "TEXT"), ("category_confirmed", "INTEGER")]:
        if name not in cols:
            con.execute(f"ALTER TABLE videos ADD COLUMN {name} {decl}")
            print(f"  + videos.{name} {decl}")
    con.commit()
    con.close()


def main() -> None:
    print("Migrating videos table ...")
    _migrate()

    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Video.title, Video.description, Channel.niche)
            .join(Channel, Channel.id == Video.channel_id)
        ).all()
        counts: Counter = Counter()
        for vid, title, desc, niche in rows:
            # Classify against the *video's own niche* taxonomy.
            best, _ranked = classify(f"{title or ''} {desc or ''}", niche)
            v = s.get(Video, vid)
            # Don't clobber a creator-confirmed category if one exists.
            if v.category_confirmed:
                counts[v.category or "uncategorized"] += 1
                continue
            v.category = best
            v.category_confirmed = 0
            counts[best or "uncategorized"] += 1

    total = sum(counts.values())
    print(f"\nBackfilled categories for {total} reels (all niches):")
    for k, n in counts.most_common():
        print(f"  {label_for(k) if k != 'uncategorized' else 'Uncategorized':<28} {n:>5}  ({100*n/max(1,total):4.1f}%)")


if __name__ == "__main__":
    main()
