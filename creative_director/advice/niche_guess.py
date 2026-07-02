"""Niche consistency guess — did the creator pick the right niche for this reel?

The selected niche drives the COMPARISON layers (DNA wording, corpus stats, category
menus), so a mispick makes personalized claims quietly wrong — an honesty problem.
This is a deterministic keyword check over what the read actually SAW (what_it_is,
verdict, caption, transcript). Deliberately CONSERVATIVE: we only suspect a mismatch
when another niche scores clearly and the selected niche barely registers, so
crossover reels ("what I eat as a lifter") never get flagged. We never silently
switch — the read page shows a chip and the CREATOR decides (same explicit-action
rule as the revision loop).
"""
from __future__ import annotations

import re
from typing import Optional

_LEXICON: dict[str, list[str]] = {
    "ig_fitness": [
        "workout", "gym", "exercise", "rep", "reps", "sets", "muscle", "lift", "lifting",
        "deadlift", "squat", "bench", "protein", "trainer", "abs", "cardio", "stretch",
        "yoga", "dumbbell", "barbell", "physique", "warm-up", "warmup", "form", "hypertrophy",
        "calisthenics", "pilates", "treadmill", "fitness",
    ],
    "ig_food": [
        "recipe", "cook", "cooking", "kitchen", "ingredient", "ingredients", "bake", "baking",
        "meal", "sauce", "oven", "restaurant", "dish", "chef", "flavor", "tasty", "delicious",
        "pasta", "chicken", "dessert", "snack", "breakfast", "dinner", "lunch", "fridge",
        "grill", "marinade", "dough", "plating", "taste test",
    ],
    "ig_travel": [
        "travel", "hotel", "flight", "beach", "destination", "resort", "trip", "tour",
        "island", "airport", "itinerary", "passport", "sunset sail", "vacation", "airbnb",
        "hostel", "backpacking", "landmark", "sightseeing", "wanderlust", "coastline",
        "villa", "road trip", "hidden gem",
    ],
    "ig_fashion": [
        "outfit", "style", "styling", "wear", "dress", "fabric", "wardrobe", "sneaker",
        "sneakers", "jeans", "fit check", "thrift", "accessories", "blazer", "runway",
        "lookbook", "capsule", "streetwear", "heels", "handbag", "vintage", "denim",
        "tailored", "aesthetic outfit", "ootd",
    ],
}


def _score(text: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for niche, words in _LEXICON.items():
        n = 0
        for w in words:
            if re.search(r"\b" + re.escape(w) + r"\b", text):
                n += 1
        scores[niche] = n
    return scores


def guess_mismatched_niche(
    selected: Optional[str],
    *texts: Optional[str],
) -> Optional[str]:
    """Return the suspected REAL niche when the reel's content clearly belongs to a
    different niche than the one selected — else None. Conservative by design:
    requires the other niche to hit >= 3 distinct terms while the selected niche
    hits <= 1, and a clear margin."""
    if selected not in _LEXICON:
        return None
    text = " ".join(t for t in texts if t)[:4000].lower()
    if len(text) < 40:
        return None  # not enough signal to second-guess the creator
    scores = _score(text)
    sel = scores.get(selected, 0)
    best_other, best_score = None, 0
    for niche, s in scores.items():
        if niche != selected and s > best_score:
            best_other, best_score = niche, s
    if best_other and best_score >= 3 and sel <= 1 and best_score >= sel + 3:
        return best_other
    return None
