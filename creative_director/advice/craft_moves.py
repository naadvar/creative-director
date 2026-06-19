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

# Detecting a genuinely WASTED/empty opening from the VLM's prose is a precision
# minefield — every rule below patches a real false positive we observed:
#   * a faceless visual-led reel ("flat-lay of cake, no person present") is NOT
#     wasted — so "no person/subject" is never itself a trigger.
#   * "dark frame" is OUT — it collides with low-key lighting and with "the
#     person's dark frame" (physique sense).
#   * "black frame" alone is NOT enough — "Black frame with two tents at dusk" /
#     "...a woman's face" / "...hands holding pasta" are dark openings with a real
#     subject. The black-frame cue only counts WITH an emptiness confirmer.
#   * "wasted frame" gets misused for FRAMING critiques of content shots
#     ("woman's face ... wasted frame portion") — so it too needs a confirmer.
#     Only "wasted opening/slate" is strong enough to stand alone.
#   * negation + inversion: "no black frame", "non-wasted opening", "wasted frame
#     space minimal" all mean the frame is FINE — see _POSITIVE_FRAME / _NEGATOR_TAIL.

# Tier 1 — unambiguous: the frame itself IS the placeholder. Fires on its own.
_DEAD_STRONG = re.compile(
    r"\bsolid (black|colou?r)\b|"
    r"\b(pure|entirely|completely) (black|blank)\b|"
    r"\b(logo|brand) (bump|reveal|animation|intro)\b|"
    r"\b(empty|blank)( (title|opening))? slate\b|"
    r"\btitle (card|slate) (with no|that is empty|, empty)\b|"
    r"\bnothing (is )?(visible|on ?-?screen|happening)\b|"
    r"\b(colou?r wash|fade-?in placeholder|buffer frame)\b|"
    r"\bwasted (opening|first frame|slate|blank)\b|"
    r"\bnot (yet )?(fully )?loaded\b",
    re.I,
)
# Tier 2 — weak cue: "black/blank/empty frame" or a bare "wasted frame". Counts only
# when an emptiness confirmer co-occurs in the same sentence (or the cue stands almost
# alone, e.g. the whole description is "Black frame").
_DEAD_FRAME = re.compile(
    r"\b(black|blank|empty)( or (very )?dark)? (frame|screen)\b|\bwasted frame\b", re.I
)
_EMPTY_CONFIRM = re.compile(
    r"\bno (visible |discernible )?(subject|content|imagery|scenery|detail|action|object|focal)\b|"
    r"\b(subject|content)s? (is |are )?absent\b|"
    r"\bnothing\b|\btext-?only\b|\btext-on-screen\b|\btext\b|"
    r"\b0\.0s\b|\btimestamp\b|\bwatermark\b|\bleader\b|"
    r"\b(title|text) slate\b|\blogo\b|\bloading\b|"
    r"\bnear-?black\b|\bmonochromatic\b",
    re.I,
)
# The VLM's own POSITIVE / inverted verdicts — if it praised the frame ANYWHERE in
# the description, never flip that into a "wasted opening" complaint. Covers
# "non-wasted", "no/minimal wasted", and the postfix "wasted ... minimal/none".
_POSITIVE_FRAME = re.compile(
    r"\bnon-?wasted\b|"
    r"\b(no|not|minimal(ly)?|little|zero|negligible) (wasted|empty|dead)\b|"
    r"\bwasted [\w ]{0,20}?\b(minimal|negligible|none|little|low)\b|"
    r"\b(clean|tight(ly)?|well[- ]?(composed|framed)|strong|striking|crisp)\b.{0,20}"
    r"\b(frame|composition|shot|open\w*)\b|"
    r"\b(frame|composition|shot)\b.{0,20}\b(clean|crisp|tight|strong|not wasted)\b",
    re.I,
)
# A negator immediately governing a match: "...no <stuff> [black frame]". The window
# before the match must END with a negator followed only by words/commas/slashes (no
# clause break), so "no title slate or black frame" is caught but "Black frame ... no
# visible subject" (black frame comes first, genuinely empty) is not.
_NEGATOR_TAIL = re.compile(
    r"\b(no|not|without|free of|clear of|lacks?|avoids?|absent|non-?|n'?t)\b[\w\s,'/&-]*$", re.I
)
# A concrete subject/object/scene in the opening — even if dim or partial. If one is
# present (and not negated, and not part of a "transitions TO x" later-clause), the
# frame is a SHOT of something, not a blank placeholder, and the weak cue must not fire.
# The audit caught: silhouettes/figures (DBZW), hands (DDDsz), a vehicle headlight
# (C5jt) and seat (CvMq), clothing/feet (DW3pd3), and a desert landscape (DWmI).
_REAL_CONTENT = re.compile(
    r"\b(silhouettes?|figures?|persons?|person'?s|people|hands?|faces?|man|woman|men|"
    r"women|athletes?|presenter|dancers?|crowd|torso|someone|feet|legs?|shoes?|sneakers?|"
    r"clothing|outfit|vehicles?|cars?|headlights?|dashboards?|seats?|motorcycles?|trucks?|"
    r"landscapes?|scenery|foliage|mountains?|buildings?|fields?|terrain|skylines?|"
    r"cityscapes?|seascape|vista|horizon)\b", re.I)
# "transitions/cuts/fades TO x" / "before x appears" — x is LATER content, not in frame 1.
_LATER_CONTENT = re.compile(
    r"\b(transition\w*|fades?|cuts?|gives way|opens? (to|on)|then|before|reveal\w*)\b[\w\s,'-]*$",
    re.I)


def _negated(head: str, m: "re.Match") -> bool:
    return bool(_NEGATOR_TAIL.search(head[: m.start()][-40:]))


def _real_content_present(head: str) -> bool:
    """A real subject/object/scene is IN the opening frame (not negated, not a 'cuts to
    x' later-clause) — so the frame is a shot of something, not a blank placeholder."""
    for m in _REAL_CONTENT.finditer(head):
        if _negated(head, m):
            continue
        if _LATER_CONTENT.search(head[: m.start()][-30:]):
            continue  # "...transitioning to a seascape" — that content comes later
        return True
    return False


def is_dead_opening(shot: Optional[str]) -> bool:
    """True only for a genuinely wasted/empty opening frame — confirmer-gated,
    negation-aware, real-subject-vetoed, and deferring to the VLM's own positive
    verdict. Single source of truth for both the craft note and the (demoted)
    no_dead_opening signal."""
    text = (shot or "").strip()
    if not text or _POSITIVE_FRAME.search(text):
        return False
    head = text.split(". ")[0]  # the opening frame is described in the first sentence
    # a real subject/object/scene IN frame 1 vetoes everything — even the VLM's own
    # "wasted opening" verdict — because the creator's car/feet/landscape is on screen.
    if _real_content_present(head):
        return False
    for m in _DEAD_STRONG.finditer(head):  # tier 1: stands alone
        if not _negated(head, m):
            return True
    has_confirm = bool(_EMPTY_CONFIRM.search(head))
    for m in _DEAD_FRAME.finditer(head):  # tier 2: needs an emptiness confirmer
        if _negated(head, m):
            continue
        if has_confirm:
            return True
        rest = (head[: m.start()] + head[m.end():]).strip(" ,.;:-—")
        if len(rest.split()) <= 3:  # the description is essentially just "Black frame"
            return True
    return False
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
    return not is_dead_opening(shot)


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
    if is_dead_opening(shot):
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
