"""Niche-specific CLIP zero-shot prompts for per-second video classification.

Each prompt is a (key, text) pair: the text is what CLIP scores a frame
against; the key is the short label stored in VideoTimeline.clip_scores.

Prompts are deliberately niche-specific — what matters in a fitness Short
("exercise demo", "physique") is different from travel or cooking. Add a
niche by adding an entry here.
"""
from __future__ import annotations


NICHE_PROMPTS: dict[str, list[tuple[str, str]]] = {
    "fitness": [
        ("talking_head", "a person talking directly to the camera"),
        ("exercise_demo", "a person demonstrating a workout exercise"),
        ("muscle_closeup", "a close-up of a muscle or body part"),
        ("text_overlay", "a screen showing large text overlay"),
        ("gym_setting", "the inside of a gym with workout equipment"),
        ("physique_reveal", "a person showing off their muscular physique"),
        ("food_or_meal", "a plate of food or a meal being prepared"),
        ("action_movement", "fast dynamic athletic movement"),
    ],
}

# Used when a niche has no specific prompt list.
DEFAULT_NICHE = "fitness"


def get_prompts(niche: str | None = None) -> list[tuple[str, str]]:
    """Return the (key, text) prompt list for a niche, falling back to default."""
    return NICHE_PROMPTS.get(niche or DEFAULT_NICHE, NICHE_PROMPTS[DEFAULT_NICHE])
