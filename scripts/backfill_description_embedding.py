"""Backfill description_embedding (SentenceTransformer 384d) for every row.

GPU guard: this machine's RTX 2060 is thermally damaged. Force CUDA invisible
BEFORE any torch import so SentenceTransformer can only run on CPU. Running it
on the GPU crashes the box with a dxgkrnl fault.
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = ""

import sys
import time

from sqlalchemy import select

from creative_director.features.hook_text import batch_embed, load_embedder
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoFeatures


BATCH = 256


def _log(msg: str) -> None:
    print(msg, flush=True)
    sys.stdout.flush()


def main() -> None:
    _log("Loading SentenceTransformer ...")
    model = load_embedder()

    with session_scope() as s:
        # Resume-safe: only fetch rows that don't already have an embedding.
        ids = [
            r[0]
            for r in s.execute(
                select(VideoFeatures.video_id).where(
                    VideoFeatures.description_embedding.is_(None)
                )
            ).all()
        ]
    _log(f"Backfilling description_embedding for {len(ids)} rows (resuming)")

    written = 0
    start = time.monotonic()
    for i in range(0, len(ids), BATCH):
        chunk_ids = ids[i : i + BATCH]
        with session_scope() as s:
            rows = s.execute(
                select(Video.id, Video.description, VideoFeatures)
                .join(VideoFeatures, VideoFeatures.video_id == Video.id)
                .where(Video.id.in_(chunk_ids))
            ).all()
            texts = [row[1] for row in rows]
            embs = batch_embed(model, texts)
            for (vid, _desc, feat), emb in zip(rows, embs):
                feat.description_embedding = emb
                written += 1
        elapsed = time.monotonic() - start
        rate = written / max(elapsed, 1e-6)
        _log(f"  ...{written}/{len(ids)}  {rate:.1f}/s")
    _log(f"Done. wrote={written}")


if __name__ == "__main__":
    main()
