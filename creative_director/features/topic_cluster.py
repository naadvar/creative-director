"""Offline topic subclustering within a niche.

A "fitness" reel could be a mobility flow, a hypertrophy explainer, a
calisthenics demo, a women's-strength piece, or pure aesthetic gym
content. Winners cluster very differently across these subtopics; lumping
them under one "fitness winners" benchmark dilutes the signal -- a
mobility creator gets compared against the median across all subtopics,
which makes their hashtag use look wrong when it might be fine for their
subtopic.

We k-means cluster reels in a niche by their stored thumb CLIP embedding
+ title text embedding (PCA-reduced & concatenated), assign each reel a
``topic_cluster_id``, and use that as both a model feature and (later) a
benchmark stratification dimension.

K (cluster count) is set per niche. For ig_fitness with ~5k reels, K=8
keeps each cluster at ~600 reels -- enough for stable winner medians.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures


def _coerce_embedding(raw, dim: int):
    if not raw:
        return None
    try:
        vec = np.asarray(raw, dtype=float)
    except (TypeError, ValueError):
        return None
    if vec.shape != (dim,):
        return None
    return vec


def build_clusters_for_niche(
    niche: str, k: int = 8, random_state: int = 42
) -> dict[str, int]:
    """Return {video_id: cluster_id} for every reel in ``niche`` that has
    both a thumb and title embedding. Reels missing either get no entry."""
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA

    with session_scope() as s:
        rows = s.execute(
            select(Video.id, VideoFeatures.thumb_clip_embedding, VideoFeatures.title_embedding)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == niche)
        ).all()

    valid: list[tuple[str, np.ndarray, np.ndarray]] = []
    for vid, thumb_raw, title_raw in rows:
        thumb_v = _coerce_embedding(thumb_raw, 512)
        title_v = _coerce_embedding(title_raw, 384)
        if thumb_v is None or title_v is None:
            continue
        valid.append((vid, thumb_v, title_v))

    if not valid:
        return {}

    # PCA-reduce each embedding family separately, then concatenate. The
    # numbers below are dataset-size-conscious: small enough not to overfit
    # k-means in a few-thousand-row corpus, big enough to preserve topical
    # structure.
    thumb_mat = np.stack([v[1] for v in valid])
    title_mat = np.stack([v[2] for v in valid])
    thumb_pca = PCA(n_components=16, random_state=random_state).fit_transform(thumb_mat)
    title_pca = PCA(n_components=12, random_state=random_state).fit_transform(title_mat)
    # Standardise so neither embedding family dominates by raw scale.
    thumb_pca = (thumb_pca - thumb_pca.mean(0)) / (thumb_pca.std(0) + 1e-9)
    title_pca = (title_pca - title_pca.mean(0)) / (title_pca.std(0) + 1e-9)
    feats = np.concatenate([thumb_pca, title_pca], axis=1)

    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labels = km.fit_predict(feats)
    return {valid[i][0]: int(labels[i]) for i in range(len(valid))}


def summarize_clusters(assignments: dict[str, int]) -> str:
    c = Counter(assignments.values())
    parts = [f"{cid}={n}" for cid, n in sorted(c.items())]
    return f"k={len(c)}  " + "  ".join(parts)
