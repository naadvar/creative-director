"""Caption-based category classification, two methods, side by side, so we can
see if the captions separate categories more cleanly than the thumbnail did.

  A) Keyword rules over the caption text (high precision, leaves no-keyword
     reels 'unclassified' -> coverage tells us how often it fires).
  B) Caption-embedding zero-shot: cosine the stored title/caption embedding
     (SentenceTransformer 384d) to category-description embeddings.

Prints per-method counts + sample titles + a quality metric.

    python -m scripts.classify_categories_v2
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = ""  # safety: damaged dGPU

import re
from collections import Counter, defaultdict

import numpy as np
from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Channel, Video, VideoFeatures

NICHE = "ig_fitness"

# Descriptive prompts for the embedding method.
CATEGORIES: dict[str, str] = {
    "Calisthenics / bodyweight": "calisthenics bodyweight training, pull-ups, dips, muscle-ups and bar skills",
    "Gym weights / bodybuilding": "bodybuilding hypertrophy gym training with dumbbells, machines and isolation work",
    "Mobility / rehab": "mobility, stretching, flexibility and injury rehab or prehab",
    "Yoga / pilates": "yoga and pilates flow practice",
    "Functional / HIIT": "high-intensity functional CrossFit conditioning and circuits",
    "Powerlifting": "powerlifting strength training: squat, deadlift and bench press, one-rep maxes",
    "Running / outdoor": "running and outdoor endurance cardio training",
    "Nutrition / food": "nutrition, diet, recipes, meal prep and macros",
}

# Keyword rules (case-insensitive). Word-boundaried where ambiguous.
KEYWORDS: dict[str, list[str]] = {
    "Calisthenics / bodyweight": [
        r"calisthenic", r"pull[- ]?up", r"chin[- ]?up", r"\bdips?\b", r"muscle[- ]?up",
        r"push[- ]?up", r"handstand", r"planche", r"front lever", r"\bbar(s)?\b",
        r"bodyweight", r"street workout",
    ],
    "Gym weights / bodybuilding": [
        r"bodybuild", r"hypertroph", r"dumbbell", r"bicep", r"tricep", r"chest day",
        r"back day", r"leg day", r"isolation", r"\bmachine", r"\bcable", r"physique",
        r"\bbulk", r"\bcut(ting)?\b", r"delts?", r"quads?",
    ],
    "Mobility / rehab": [
        r"mobility", r"stretch", r"\brehab", r"prehab", r"flexibilit", r"hip flexor",
        r"range of motion", r"\brom\b", r"posture", r"sciatic", r"knee pain",
        r"shoulder pain", r"warm[- ]?up", r"\bpain\b",
    ],
    "Yoga / pilates": [r"\byoga", r"pilates", r"vinyasa", r"namaste", r"asana", r"breathwork"],
    "Functional / HIIT": [
        r"\bhiit\b", r"crossfit", r"conditioning", r"functional", r"circuit",
        r"\bamrap\b", r"\bemom\b", r"\bwod\b", r"kettlebell", r"burpee", r"metcon",
    ],
    "Powerlifting": [
        r"powerlift", r"\bsquat", r"deadlift", r"bench press", r"\b1rm\b", r"\bpr\b",
        r"one rep max", r"big 3", r"\bsumo\b", r"lockout", r"barbell",
    ],
    "Running / outdoor": [
        r"\brun(ning|ner)?\b", r"\b5k\b", r"\b10k\b", r"marathon", r"sprint",
        r"\bjog", r"\bpace\b", r"mileage", r"\btrail",
    ],
    "Nutrition / food": [
        r"recipe", r"meal prep", r"nutrition", r"protein", r"calorie", r"macro",
        r"\bdiet", r"\beat(ing)?\b", r"\bfood\b", r"smoothie", r"supplement", r"snack",
    ],
}
_COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in pats] for k, pats in KEYWORDS.items()}
KEYS = list(CATEGORIES)


def _report(name: str, counts: Counter, samples: dict, extra: str) -> None:
    total = sum(counts[k] for k in KEYS)
    print(f"\n=== {name} ===  ({total} classified; {extra})")
    print(f"  {'category':<28} {'count':>6} {'share':>7}")
    for k in KEYS:
        n = counts[k]
        print(f"  {k:<28} {n:>6} {100*n/max(1,total):6.1f}%")
        for t in samples[k][:2]:
            print(f"       e.g. {t}")


def main() -> None:
    from creative_director.features.hook_text import load_embedder

    model = load_embedder()  # SentenceTransformer, CPU
    cat_feats = model.encode(
        [CATEGORIES[k] for k in KEYS], convert_to_numpy=True, normalize_embeddings=True
    )

    with session_scope() as s:
        rows = s.execute(
            select(
                Video.id, Video.title, Video.description, VideoFeatures.title_embedding
            )
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == NICHE)
        ).all()

    kw_counts: Counter = Counter()
    kw_samples = defaultdict(list)
    kw_unclassified = 0

    emb_counts: Counter = Counter()
    emb_samples = defaultdict(list)
    emb_margins: list[float] = []
    emb_missing = 0

    for vid, title, desc, temb in rows:
        text = f"{title or ''} {desc or ''}"
        short = (title or "").strip().replace("\n", " ")[:48]

        # --- Method A: keyword rules ---
        hits = {k: sum(1 for rx in _COMPILED[k] if rx.search(text)) for k in KEYS}
        best = max(hits, key=hits.get)
        if hits[best] == 0:
            kw_unclassified += 1
        else:
            kw_counts[best] += 1
            if len(kw_samples[best]) < 2:
                kw_samples[best].append(short)

        # --- Method B: caption embedding zero-shot ---
        if temb:
            v = np.asarray(temb, dtype=float)
            if v.shape == (384,):
                v = v / (np.linalg.norm(v) + 1e-9)
                scores = cat_feats @ v
                order = np.argsort(scores)[::-1]
                emb_counts[KEYS[int(order[0])]] += 1
                emb_margins.append(float(scores[order[0]] - scores[order[1]]))
                if len(emb_samples[KEYS[int(order[0])]]) < 2:
                    emb_samples[KEYS[int(order[0])]].append(short)
            else:
                emb_missing += 1
        else:
            emb_missing += 1

    _report(
        "METHOD A — caption keyword rules",
        kw_counts, kw_samples,
        f"{kw_unclassified} unclassified (no keyword) = {100*kw_unclassified/max(1,len(rows)):.0f}% coverage gap",
    )
    _report(
        "METHOD B — caption embedding zero-shot",
        emb_counts, emb_samples,
        f"{emb_missing} missing embedding; mean top1-top2 margin "
        f"{np.mean(emb_margins):.3f}" if emb_margins else "no embeddings",
    )


if __name__ == "__main__":
    main()
