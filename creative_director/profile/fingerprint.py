"""Per-creator style fingerprint — built from the creator's OWN uploads (no
scraping, no OAuth, fully owned data). It accumulates as they use the product,
which doubles as the retention hook. Purely DESCRIPTIVE (style, never performance
— within-creator performance is noise, per the project's findings).

A fingerprint is a cheap deterministic aggregate over the craft reads of the
reels a user has uploaded: their dominant format, their recurring craft notes,
and a one-line summary. No LLM call, so no hallucination surface.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Upload

# change_type enum -> a friendly, creator-facing phrase (style, not a verdict).
_CHANGE_FRIENDLY = {
    "hook_unclear": "hooks that don't say what the reel is up front",
    "dead_opening": "slow openings",
    "no_onscreen_text": "reels with no on-screen text",
    "text_illegible": "on-screen text that's hard to read at reel size",
    "payoff_backloaded": "payoffs that land late",
    "payoff_missing": "an unclear payoff",
    "dead_time": "dead stretches",
    "weak_framing": "framing that hides the key action",
    "wasted_ending": "endings that trail off",
    "pacing_slow": "slow pacing",
}
_FORMAT_LABEL = {
    "talking_head": "talking-head",
    "visual_led": "visual-led",
    "mixed": "mixed-format",
}


def compute_fingerprint(user_id: int) -> dict:
    """Aggregate the user's own uploaded reels' craft reads into a style summary.
    Returns {ready: False} until they've uploaded at least one analyzed reel."""
    with session_scope() as s:
        rows = s.execute(
            select(Upload.craft_read, Upload.niche)
            .where(Upload.user_id == user_id, Upload.craft_read.isnot(None))
        ).all()

    # Style only from reads we'd actually show (a suppressed/ungrounded read is noise).
    rows = [(r, niche) for r, niche in rows
            if isinstance(r, dict) and r.get("grounded") is not False]
    reads = [r for r, _ in rows]
    n = len(reads)
    if n == 0:
        return {"ready": False, "n_reels": 0,
                "summary": "Upload a reel to start building your creator fingerprint."}

    niches = Counter(niche for _, niche in rows if niche)
    fmts = Counter(r.get("format_class") for r in reads if r.get("format_class"))
    changes = Counter(
        c for r in reads for c in (r.get("change_types") or []) if c and c != "other"
    )

    niche = niches.most_common(1)[0][0] if niches else None
    # Only name a niche the creator is actually filed under a corpus niche for —
    # "other" / unknown must NOT become "You're a other creator".
    _CORPUS = {"ig_fitness", "ig_food", "ig_travel", "ig_fashion"}
    niche_word = niche.replace("ig_", "") if (niche in _CORPUS) else None
    fmt = fmts.most_common(1)[0][0] if fmts else None
    fmt_label = _FORMAT_LABEL.get(fmt)

    recurring = [
        {"type": c, "label": _CHANGE_FRIENDLY[c], "count": cnt}
        for c, cnt in changes.most_common(3) if c in _CHANGE_FRIENDLY
    ]

    summary = f"You're a {niche_word} creator" if niche_word else "You're a creator"
    if fmt_label:
        summary += f" who mostly makes {fmt_label} reels"
    summary += "."
    # Only assert a "recurring" pattern once it's actually shown up more than once.
    top = recurring[0] if recurring else None
    if top and top["count"] >= 2:
        summary += f" Across your last {n} reels, the note that recurs most is {top['label']}."
    elif n < 3:
        summary += f" Upload a few more and we'll spot your recurring patterns ({n} so far)."

    return {
        "ready": True,
        "n_reels": n,
        "niche": niche,
        "format": fmt,
        "format_label": fmt_label,
        "recurring": recurring if (top and top["count"] >= 2) else [],
        "summary": summary,
    }
