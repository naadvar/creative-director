"""Niche-specific CLIP zero-shot prompts for per-second video classification.

Each prompt is a (key, text) pair: the text is what CLIP scores a frame
against; the key is the short label stored in VideoTimeline.primary_vibe /
clip_scores.

Prompts are deliberately niche-specific — what matters in a fitness Short
("exercise demo", "physique") is nothing like what matters in a food, travel,
or fashion reel. The candidate label set is chosen at *extraction* time, so a
frame can only ever be tagged with a concept that lives in its niche's list.
Add a niche by adding an entry here, then re-run timeline extraction for that
niche's videos so primary_vibe is recomputed against the new prompts.

The niche key is normalised via categories._base, so ig_food /
ig_food_candidates / cooking all resolve to the "food" prompt list.
"""
from __future__ import annotations

from creative_director.advice.categories import _base as _niche_base

# Shared concepts reused across niches (same key -> same display string).
_TALKING = ("talking_head", "a person talking directly to the camera")
_TEXT = ("text_overlay", "a screen showing large text overlay")

NICHE_PROMPTS: dict[str, list[tuple[str, str]]] = {
    "fitness": [
        _TALKING,
        ("exercise_demo", "a person demonstrating a workout exercise"),
        ("muscle_closeup", "a close-up of a muscle or body part"),
        _TEXT,
        ("gym_setting", "the inside of a gym with workout equipment"),
        ("physique_reveal", "a person showing off their muscular physique"),
        ("food_or_meal", "a plate of food or a meal being prepared"),
        ("action_movement", "fast dynamic athletic movement"),
    ],
    "food": [
        _TALKING,
        ("plated_dish", "a finished plated dish of food"),
        ("ingredients", "raw ingredients laid out on a counter"),
        ("cooking_action", "food being cooked in a pan, on a stove, or on a grill"),
        ("hands_prep", "a close-up of hands chopping or preparing food"),
        ("eating", "a person taking a bite of food"),
        ("restaurant", "the interior of a restaurant or cafe"),
        _TEXT,
    ],
    "travel": [
        _TALKING,
        ("landscape", "a scenic natural landscape, mountains, or forest"),
        ("landmark", "a famous landmark or tourist attraction"),
        ("cityscape", "a city street or urban skyline"),
        ("beach_water", "a beach, ocean, lake, or swimming pool"),
        ("hotel_resort", "a hotel room, resort, or pool area"),
        ("person_scenic", "a person posing in front of scenery"),
        _TEXT,
    ],
    "fashion": [
        _TALKING,
        ("full_outfit", "a person showing a full-body outfit"),
        ("mirror_selfie", "a person filming their outfit in a mirror"),
        ("clothing_closeup", "a close-up of clothing fabric or detail"),
        ("getting_dressed", "a person trying on or changing clothes"),
        ("accessories", "a close-up of shoes, bags, or jewelry"),
        ("makeup_hair", "a person applying makeup or styling their hair"),
        _TEXT,
    ],
}

# Used when a niche has no specific prompt list (unknown / legacy niches).
DEFAULT_NICHE = "fitness"


def get_prompts(niche: str | None = None) -> list[tuple[str, str]]:
    """Return the (key, text) prompt list for a niche, falling back to default.

    The niche is normalised first (ig_food / ig_food_candidates / cooking ->
    "food"), so the raw stored channel niche can be passed straight in.
    """
    base = _niche_base(niche)  # food | travel | fashion | fitness | None
    return NICHE_PROMPTS.get(base or DEFAULT_NICHE, NICHE_PROMPTS[DEFAULT_NICHE])
