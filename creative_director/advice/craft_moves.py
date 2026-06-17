"""Craft moves — binary, frame-checkable craft choices derived DETERMINISTICALLY
from the rich VLM perception we already have (no new model / no new LLM pass).

Each move is a yes/no question about the reel's craft that a creator can act on
("does a subject appear in the opening frame?", "is there an on-screen text hook?").
We compute which moves WINNERS in a niche have far more often than non-winners
(the discriminativeness gate, in craft_moves_profile.py) and keep only those.

These power: the Craft-Gap advice cards (the move you're missing + winners who do
it) and the read-consistent "craft match" headline (how many winner-moves you have).

A predicate returns True / False / None:
  True  = the move is present
  False = the move is absent (a candidate gap)
  None  = can't tell from this reel's perception (excluded from rates + advice)
"""
from __future__ import annotations

import re
from typing import Callable, Optional

# A genuinely WASTED/empty opening — the first frame IS a placeholder (black/blank
# frame, a logo bump, an empty slate, or the VLM says no subject is visible).
# Tight on purpose: must NOT match "...no wasted frame" (the VLM's POSITIVE note),
# and "black/blank" must qualify "frame/screen" (so "black jacket" never fires).
_DEAD_OPEN = re.compile(
    r"\b(solid|pure|near-?|mostly )?\s*(black|blank|empty|dark) (frame|screen)\b|"
    r"\bsolid (black|colou?r)\b|"
    r"\blogo (bump|reveal|animation|intro)\b|\bbrand bump\b|"
    r"empty (title )?slate|title (card|slate) (with no|that is empty|, empty)|"
    r"\bno (visible )?(subject|content|person|action|focal point)\b|"
    r"\bnothing (is )?(visible|on ?-?screen|happening)\b|"
    r"not (yet )?(fully )?loaded",
    re.I,
)
# A caption-vs-visual GAP — must be the explicit "caption promises X BUT the opening
# does NOT show it" shape: a caption/text + a promise verb + a contrast + an explicit
# not-shown clause. Tight so the VLM's ordinary "...but..." hedging doesn't fire.
_CAPTION_GAP = re.compile(
    r"(caption|title|hook|on-?screen text)[^.]{0,60}"
    r"\b(promis\w*|claim\w*|says|sets? up|implies|frames? (it|this) as|teases?|suggests?)\b"
    r"[^.]{0,90}\b(but|yet|however|whereas)\b[^.]{0,90}"
    r"\b(not (yet )?(shown|visible|present|delivered)|does ?n'?t (show|appear|deliver|match)|"
    r"isn'?t (shown|visible|present)|never (shows?|appears?|delivers?)|absent|missing|buried|"
    r"no .{0,25}(visible|shown|on screen))\b",
    re.I,
)


def _move_no_dead_opening(p: dict) -> Optional[bool]:
    shot = (p.get("opening_shot") or "").strip()
    if not shot:
        return None
    return not bool(_DEAD_OPEN.search(shot))


def _move_onscreen_text_hook(p: dict) -> Optional[bool]:
    # on_screen_text is the verbatim first-frames text the VLM read (null when none).
    t = p.get("on_screen_text")
    if t is None:
        # fall back to an observed on_screen_text item early in the clip
        for o in (p.get("observed") or []):
            if isinstance(o, dict) and o.get("kind") == "on_screen_text" and (o.get("frame_ts") or 99) <= 2.0:
                return True
        return None
    return bool(str(t).strip())


def _move_subject_at_open(p: dict) -> Optional[bool]:
    """A person/subject is on screen at the open — not a text card or empty frame."""
    if p.get("has_presenter") is True:
        return True
    for o in (p.get("observed") or []):
        if isinstance(o, dict) and o.get("kind") in ("presence_of_person", "object_on_screen") and (o.get("frame_ts") or 99) <= 2.0:
            return True
    shot = (p.get("opening_shot") or "").strip()
    if not shot:
        return None
    if _DEAD_OPEN.search(shot):
        return False
    return None  # a concrete scene with no clear subject cue — don't assert either way


def _move_caption_delivers(p: dict) -> Optional[bool]:
    hyps = " ".join(h.get("text", "") for h in (p.get("hypothesis") or [])).strip()
    if not hyps:
        return None
    return not bool(_CAPTION_GAP.search(hyps))


# id -> (creator-facing label, predicate). Order = display priority.
MOVES: list[tuple[str, str, Callable[[dict], Optional[bool]]]] = [
    ("subject_at_open", "a subject on screen in the opening shot", _move_subject_at_open),
    ("no_dead_opening", "no wasted/blank opening frame", _move_no_dead_opening),
    ("onscreen_text_hook", "an on-screen text hook in the first seconds", _move_onscreen_text_hook),
    ("caption_delivers", "an opening that delivers what the caption promises", _move_caption_delivers),
]

MOVE_LABEL = {mid: label for mid, label, _ in MOVES}


def moves_for(perception: Optional[dict]) -> dict[str, Optional[bool]]:
    """Map each move id -> True/False/None for one reel's rich perception."""
    if not isinstance(perception, dict):
        return {mid: None for mid, _, _ in MOVES}
    return {mid: fn(perception) for mid, _, fn in MOVES}
