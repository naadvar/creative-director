"""Content-category classification for fitness reels.

Categories are CONTENT subtopics (calisthenics, powerlifting, mobility...),
distinct from the talking-vs-demo archetype. We classify from the caption via
keyword rules: high precision where they fire, and where they don't the UI
falls back to a "pick your category" dropdown (so the creator's correction
becomes a free training label).

Method comparison that led here (see scripts/classify_categories*.py):
  - thumbnail CLIP zero-shot: full coverage but ~noise (random-frame thumbs)
  - caption-embedding zero-shot: ~noise (casual/promo captions)
  - caption keyword rules: best precision, ~57% coverage  <-- this
The 43% no-keyword gap is fundamental (many captions are personal/promo, not
descriptive) — handled by the override dropdown, not by more keywords/data.
"""
from __future__ import annotations

import re
from typing import Optional

# category key -> (display label, descriptive blurb for UI/benchmark prompts)
CATEGORIES: dict[str, str] = {
    "calisthenics": "Calisthenics / bodyweight",
    "weights": "Gym weights / bodybuilding",
    "mobility": "Mobility / rehab",
    "yoga": "Yoga / pilates",
    "functional": "Functional / HIIT",
    "powerlifting": "Powerlifting",
    "running": "Running / outdoor",
    "nutrition": "Nutrition / food",
}

CATEGORY_KEYS = list(CATEGORIES)


_KEYWORDS: dict[str, list[str]] = {
    "calisthenics": [
        r"calisthenic", r"pull[- ]?up", r"chin[- ]?up", r"\bdips?\b", r"muscle[- ]?up",
        r"push[- ]?up", r"handstand", r"planche", r"front lever", r"\bbar(s)?\b",
        r"bodyweight", r"street workout",
    ],
    "weights": [
        r"bodybuild", r"hypertroph", r"dumbbell", r"bicep", r"tricep", r"chest day",
        r"back day", r"leg day", r"isolation", r"\bmachine", r"\bcable", r"physique",
        r"\bbulk", r"\bcut(ting)?\b", r"delts?", r"quads?", r"hip thrust", r"glute",
    ],
    "mobility": [
        r"mobility", r"stretch", r"\brehab", r"prehab", r"flexibilit", r"hip flexor",
        r"range of motion", r"\brom\b", r"posture", r"sciatic", r"knee pain",
        r"shoulder pain", r"warm[- ]?up", r"\bpain\b",
    ],
    "yoga": [r"\byoga", r"pilates", r"vinyasa", r"namaste", r"asana", r"breathwork"],
    "functional": [
        r"\bhiit\b", r"crossfit", r"conditioning", r"functional", r"circuit",
        r"\bamrap\b", r"\bemom\b", r"\bwod\b", r"kettlebell", r"burpee", r"metcon",
    ],
    "powerlifting": [
        r"powerlift", r"\bsquat", r"deadlift", r"bench press", r"\b1rm\b", r"\bpr\b",
        r"one rep max", r"big 3", r"\bsumo\b", r"lockout", r"barbell",
    ],
    "running": [
        r"\brun(ning|ner)?\b", r"\b5k\b", r"\b10k\b", r"marathon", r"sprint",
        r"\bjog", r"\bpace\b", r"mileage", r"\btrail",
    ],
    "nutrition": [
        r"recipe", r"meal prep", r"nutrition", r"protein", r"calorie", r"macro",
        r"\bdiet", r"\beat(ing)?\b", r"\bfood\b", r"smoothie", r"supplement", r"snack",
    ],
}
_COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in pats] for k, pats in _KEYWORDS.items()}


def classify(text: Optional[str]) -> tuple[Optional[str], list[tuple[str, int]]]:
    """Return (best_category_key | None, ranked [(key, hit_count), ...]).

    best is None when no keyword fires (the UI shows the dropdown). The ranked
    list lets the UI pre-sort the dropdown by likelihood.
    """
    blob = text or ""
    scores = {k: sum(1 for rx in _COMPILED[k] if rx.search(blob)) for k in CATEGORY_KEYS}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    return best, ranked


def label_for(key: Optional[str]) -> str:
    """Human display label for a category key (or 'Uncategorized')."""
    return CATEGORIES.get(key or "", "Uncategorized")


def dropdown_options() -> list[dict]:
    """Category options for the override dropdown."""
    return [{"key": k, "label": v} for k, v in CATEGORIES.items()]
