"""Compute topic_cluster_id for every reel in each niche.

Runs once per niche; the result is stable per (niche, k, random_state).
Re-run after adding many new reels to a niche (cluster centroids may shift).
"""
from __future__ import annotations

from creative_director.features.topic_cluster import (
    build_clusters_for_niche,
    summarize_clusters,
)
from creative_director.storage.db import session_scope
from creative_director.storage.models import VideoFeatures


NICHES_AND_K: list[tuple[str, int]] = [
    ("ig_fitness", 8),
    ("fitness", 8),
]


def main() -> None:
    for niche, k in NICHES_AND_K:
        print(f"\n=== Clustering {niche} (k={k}) ===")
        assignments = build_clusters_for_niche(niche, k=k)
        if not assignments:
            print(f"  no reels with both embeddings -- skipped")
            continue
        print(f"  {summarize_clusters(assignments)}")

        written = 0
        with session_scope() as s:
            for vid, cid in assignments.items():
                f = s.get(VideoFeatures, vid)
                if f is None:
                    continue
                f.topic_cluster_id = cid
                written += 1
        print(f"  wrote {written} rows")


if __name__ == "__main__":
    main()
