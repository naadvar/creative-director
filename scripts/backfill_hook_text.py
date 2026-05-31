"""Backfill hook-text features for every reel that has a transcript_first_3s.

Embedding step uses a single SentenceTransformer load -- much faster than
re-instantiating the model per row.
"""
from __future__ import annotations

from sqlalchemy import select

from creative_director.features.hook_text import (
    batch_embed,
    extract_flags,
    load_embedder,
)
from creative_director.storage.db import session_scope
from creative_director.storage.models import VideoFeatures


BATCH = 256


def main() -> None:
    print("Loading SentenceTransformer (~2s)...")
    model = load_embedder()
    print("Model loaded.")

    with session_scope() as s:
        ids = [r[0] for r in s.execute(select(VideoFeatures.video_id)).all()]
    print(f"Backfilling hook-text features for {len(ids)} rows ...")

    written = 0
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
            texts = [f.transcript_first_3s for f in feats]
            embs = batch_embed(model, texts)
            for feat, emb in zip(feats, embs):
                flags = extract_flags(feat.transcript_first_3s)
                feat.hook_starts_with_question = flags["hook_starts_with_question"]
                feat.hook_uses_you = flags["hook_uses_you"]
                feat.hook_uses_number = flags["hook_uses_number"]
                feat.hook_has_negation = flags["hook_has_negation"]
                feat.hook_word_count = flags["hook_word_count"]
                feat.hook_text_embedding = emb
                written += 1
        print(f"  ...{written}/{len(ids)}")
    print(f"Done. wrote={written}")


if __name__ == "__main__":
    main()
