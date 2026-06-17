"""Honest craft notes — specific, grounded observations from the rich VLM read.

We PROVED (craft_moves_profile) that no observable craft move predicts winning,
so these notes make NO performance claim ("do X to win" / "winners avoid this").
They surface only SELF-EVIDENT craft observations a creator would go "oh, good
catch" at — things they likely didn't intend — grounded in their own frames:

  1. a wasted / near-empty opening frame (a blank first frame helps no one)
  2. a caption-vs-visual gap (the caption sets up a payoff the opening doesn't show)

Each note is an OBSERVATION + a neutral craft reason, scrubbed of any lift claim.
Pair with the descriptive winner exemplars (build_summary.watch_winners) — "here's
how top performers in your niche open; compare" — never "they win because of it".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from creative_director.advice.craft_moves import _CAPTION_GAP, _DEAD_OPEN


@dataclass
class CraftNote:
    kind: str            # stable id (wasted_opening | caption_visual_gap)
    note: str            # creator-facing observation (no performance claim)
    evidence: str        # the grounded frame detail it's drawn from


# Belt-and-suspenders: a craft note must never imply a performance outcome.
_BANNED = re.compile(r"\b(viral|views|reach|algorithm|engagement|retention|perform|"
                     r"boost|more likely to|will (get|win|rank)|drives?|hook works)\b", re.I)


def _first_sentence(text: str, limit: int = 26) -> str:
    s = (text or "").split(". ")[0].strip().rstrip(".")
    w = s.split()
    return (" ".join(w[:limit]) + "…") if len(w) > limit else s


def craft_notes(perception: Optional[dict]) -> list[CraftNote]:
    """Up to 2 honest, grounded craft observations (or [] if none apply / no rich read)."""
    if not isinstance(perception, dict):
        return []
    notes: list[CraftNote] = []

    shot = (perception.get("opening_shot") or "").strip()
    head = shot.split(". ")[0]  # dead openings are described in the first sentence
    head_l = head.lower()
    if head and "no wasted" not in head_l and "not wasted" not in head_l and _DEAD_OPEN.search(head):
        notes.append(CraftNote(
            kind="wasted_opening",
            note="Your reel opens on a near-empty first frame — the very first thing "
                 "on screen is blank/placeholder, before anything happens.",
            evidence=_first_sentence(shot),
        ))

    # caption-visual gap: the VLM's hypothesis flagged a promise the opening doesn't show
    for h in (perception.get("hypothesis") or []):
        ht = (h.get("text") if isinstance(h, dict) else "") or ""
        if _CAPTION_GAP.search(ht):
            notes.append(CraftNote(
                kind="caption_visual_gap",
                note="Your caption sets up something the opening frames don't show yet — "
                     "the payoff isn't visible in the first seconds.",
                evidence=_first_sentence(ht, 34),
            ))
            break

    # final safety: drop any note whose text slipped a performance/lift word
    return [n for n in notes if not _BANNED.search(n.note)]
