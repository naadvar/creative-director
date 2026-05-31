"""Zero-shot category classification of the corpus, from STORED thumbnail CLIP
embeddings (no video decode, no per-reel CLIP forward pass — just encode the
category prompts once, then cosine over the stored 512d image embeddings).

Step 1 of the categories feature: reveals per-category counts so we can see
which subtopics are thin BEFORE deciding what (if anything) to scrape.

    python -m scripts.classify_categories
"""
from __future__ import annotations

import os

# Safety: this machine's dGPU is damaged. Force CPU before torch imports.
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from collections import Counter, defaultdict

import numpy as np
from sqlalchemy import select

from creative_director.config import settings
from creative_director.features.thumbnail import _load_clip
from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

# Named fitness subtopics with descriptive prompts (CLIP zero-shot does better
# with a short descriptive phrase than a single word). These are CONTENT
# categories, distinct from the talking-vs-demo archetype.
CATEGORIES: dict[str, str] = {
    "Calisthenics / bodyweight": "a calisthenics bodyweight workout with pull-ups, dips, and bar skills",
    "Gym weights / bodybuilding": "a bodybuilding gym workout lifting dumbbells and using weight machines",
    "Mobility / rehab": "a mobility, stretching, and joint rehabilitation exercise",
    "Yoga / pilates": "a yoga or pilates flow on a mat",
    "Functional / HIIT": "a high-intensity functional CrossFit conditioning workout",
    "Powerlifting": "heavy barbell powerlifting with squats, deadlifts and bench press",
    "Running / outdoor": "running and outdoor endurance training",
    "Nutrition / food": "healthy meal prep, nutrition, and food",
}

NICHE = "ig_fitness"


def main() -> None:
    import open_clip
    import torch

    model, _ = _load_clip()
    tokenizer = open_clip.get_tokenizer(settings.clip_model)
    device = next(model.parameters()).device
    keys = list(CATEGORIES)
    with torch.no_grad():
        tokens = tokenizer([CATEGORIES[k] for k in keys]).to(device)
        tf = model.encode_text(tokens)
        tf = tf / tf.norm(dim=-1, keepdim=True)
    cat_feats = tf.cpu().numpy()  # (n_cat, 512)

    with session_scope() as s:
        rows = s.execute(
            select(Video.id, Video.title, VideoFeatures.thumb_clip_embedding)
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == NICHE)
        ).all()

    counts: Counter = Counter()
    samples: dict[str, list] = defaultdict(list)
    margins: list[float] = []
    no_emb = 0

    for vid, title, emb in rows:
        if not emb:
            no_emb += 1
            continue
        v = np.asarray(emb, dtype=float)
        if v.shape != (512,):
            no_emb += 1
            continue
        v = v / (np.linalg.norm(v) + 1e-9)
        scores = cat_feats @ v
        order = np.argsort(scores)[::-1]
        idx = int(order[0])
        cat = keys[idx]
        counts[cat] += 1
        # margin between top-1 and top-2 = how decisive the call is.
        margins.append(float(scores[order[0]] - scores[order[1]]))
        if len(samples[cat]) < 3:
            samples[cat].append((title or "").strip().replace("\n", " ")[:48])

    total = sum(counts[k] for k in keys)
    print(f"\nZero-shot category split of {total} {NICHE} reels "
          f"(of {len(rows)}; {no_emb} had no usable thumbnail embedding)\n")
    print(f"  {'category':<28} {'count':>6}  {'share':>6}")
    print("  " + "-" * 44)
    for k in keys:
        n = counts[k]
        bar = "#" * int(40 * n / max(1, max(counts.values())))
        print(f"  {k:<28} {n:>6}  {100*n/max(1,total):5.1f}%  {bar}")
        for t in samples[k]:
            print(f"       e.g. {t}")
    print()
    if margins:
        print(f"  mean top1-top2 cosine margin: {np.mean(margins):.3f} "
              f"(higher = more decisive; <0.02 = lots of ambiguous calls)")


if __name__ == "__main__":
    main()
