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
            select(Video.id, Video.title, Video.description)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == "ig_fitness")
        ).all()
        counts: Counter = Counter()
        for vid, title, desc in rows:
            best, _ranked = classify(f"{title or ''} {desc or ''}")
            v = s.get(Video, vid)
            # Don't clobber a creator-confirmed category if one exists.
            if v.category_confirmed:
                counts[v.category or "uncategorized"] += 1
                continue
            v.category = best
            v.category_confirmed = 0
            counts[best or "uncategorized"] += 1

    total = sum(counts.values())
    print(f"\nBackfilled categories for {total} ig_fitness reels:")
    for k, n in counts.most_common():
        print(f"  {label_for(k) if k != 'uncategorized' else 'Uncategorized':<28} {n:>5}  ({100*n/max(1,total):4.1f}%)")


if __name__ == "__main__":
    main()
