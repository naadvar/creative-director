"""Honest craft notes — specific, grounded observations from the rich VLM read.

We PROVED (craft_moves_profile) that no observable craft move predicts winning,
so these notes make NO performance claim ("do X to win" / "winners avoid this").
They surface only SELF-EVIDENT craft observations a creator would go "oh, good
catch" at — things they likely didn't intend — grounded in their own frames:

  1. a wasted / near-empty opening frame (a blank first frame helps no one)
  2. (DISABLED) a caption-vs-visual gap — an adversarial audit found it ~46% unsound
     because its source is the VLM's speculative `hypothesis[]`, not grounded fact;
     gated off behind _ENABLE_CAPTION_GAP pending a rebuild on a grounded source.

Each note is an OBSERVATION + a neutral craft reason, scrubbed of any lift claim.
Pair with the descriptive winner exemplars (build_summary.watch_winners) — "here's
how top performers in your niche open; compare" — never "they win because of it".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from creative_director.advice.craft_moves import _CAPTION_GAP, is_dead_opening


@dataclass
class CraftNote:
    kind: str            # stable id (wasted_opening | caption_visual_gap)
    note: str            # creator-facing observation (no performance claim)
    evidence: str        # the grounded frame detail it's drawn from


# caption_visual_gap is OFF — see the long comment at its call site. Flip to True only
# after rebuilding it on a grounded (non-speculative) source and re-running the audit.
_ENABLE_CAPTION_GAP = False

# Belt-and-suspenders: a craft note must never imply a performance outcome.
_BANNED = re.compile(r"\b(viral|views|reach|algorithm|engagement|retention|perform|"
                     r"boost|more likely to|will (get|win|rank)|drives?|hook works)\b", re.I)


def _clean_opening(shot: str) -> str:
    """First grounded clause of the opening-shot description, clipped at its natural
    boundary (period / semicolon / em-dash / parenthetical) so it reads as a complete
    phrase — never a mid-word '…' truncation."""
    s = (shot or "").strip()
    # clip at period / semicolon / em-dash — but NOT at "(": an early parenthetical
    # like "Opening frame (0.0s) is entirely black" would otherwise strip the substance.
    cut = re.search(r"\.\s|;|\s*—", s)
    if cut:
        s = s[:cut.start()]
    s = s.strip().strip("—-,;: ").rstrip(".")
    return (s + ".") if s else ""


# Where to END the quote past the match: at hard punctuation, OR at the editorial
# tail the VLM tacks on after stating the gap ("...may leave viewers unclear",
# "...so the payoff relies on voiceover", "—jump cuts move..."). This completes the
# 'no visible <object>' phrase without dragging in speculative commentary.
_TAIL_STOP = re.compile(
    r"[.;]|—|\s-\s|"
    r"\b(may |might |could |would |which |so (the|that|a|it) |because |creating |"
    r"leaving |reducing |without (demonstrating|showing)|potential mismatch)\b",
    re.I,
)


def _gap_clause(text: str, m: "re.Match") -> str:
    """Quote the ACTUAL matched gap ('hook promises X, but X not shown') as a clean,
    self-contained sentence — never the unrelated preamble before it, never a trailing
    editorial paragraph after it. The _CAPTION_GAP match spans from the caption/hook
    keyword to the not-shown keyword; when the phrasing is 'no visible <object>' the
    object falls just past the match end, so we extend to the editorial-tail boundary
    to complete it, then end cleanly with a period (no truncation ellipsis)."""
    tail = text[m.end():]
    stop = _TAIL_STOP.search(tail)
    end = m.end() + (stop.start() if stop else len(tail))
    span = text[m.start():end].strip().strip("—-,;: ").rstrip(".")
    words = span.split()
    if len(words) > 44:  # safety backstop — end at a word boundary, still no ellipsis
        span = " ".join(words[:44]).strip(",;:— ")
    return (span[:1].upper() + span[1:] + ".") if span else ""


def craft_notes(perception: Optional[dict]) -> list[CraftNote]:
    """Up to 2 honest, grounded craft observations (or [] if none apply / no rich read)."""
    if not isinstance(perception, dict):
        return []
    notes: list[CraftNote] = []

    shot = (perception.get("opening_shot") or "").strip()
    # is_dead_opening is negation-aware, defers to the VLM's own positive verdict, and
    # vetoes dark/low-light shots that still contain a real subject (so "flat-lay of
    # cake, no person present", "...clean, not wasted", and "...silhouettes of figures
    # in low light" never fire).
    if is_dead_opening(shot):
        notes.append(CraftNote(
            kind="wasted_opening",
            note="Your opening frame is a placeholder, not your subject — a blank/black "
                 "or text-only leader before the real footage starts.",
            evidence=_clean_opening(shot),
        ))

    # caption-visual gap: DISABLED. A 14-agent adversarial audit found ~46% of these
    # fires were unsound — the source (the VLM's `hypothesis[]`) is speculative
    # interpretation, not grounded observation: it over-reads vibe/service/joke captions
    # into "promises", demands visual payoff for verbal/audio/nutrition claims, hedges
    # ("potential mismatch", "may", "if"), and judges from sampled frames only. No regex
    # gate separates the sound from the unsound reliably. Kept behind a flag (not deleted)
    # so it can be rebuilt on a GROUNDED source — e.g. literal caption text vs OCR'd
    # on-screen text — rather than the VLM's guesses.
    if _ENABLE_CAPTION_GAP:
        for h in (perception.get("hypothesis") or []):
            ht = (h.get("text") if isinstance(h, dict) else "") or ""
            m = _CAPTION_GAP.search(ht)
            if m:
                notes.append(CraftNote(
                    kind="caption_visual_gap",
                    note="Your caption or hook sets up a payoff the reel doesn't clearly "
                         "deliver on screen.",
                    evidence=_gap_clause(ht, m),
                ))
                break

    # final safety: drop a note if its note OR evidence slipped a performance/lift
    # word — evidence is now a raw VLM clause, so it must be scrubbed too.
    return [n for n in notes
            if not _BANNED.search(n.note) and not _BANNED.search(n.evidence)]
