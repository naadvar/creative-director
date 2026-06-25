"""Craft progress over a creator's own reads — the 'am I improving?' signal, the
retention payoff. Built from the durable Upload rows (the prioritized fix dimension
of each read), ordered in time.

HONEST BY DESIGN: it never claims "you fixed X" (causal, unverifiable). It states
factual patterns about the READS — "pacing was your most common note early on and
hasn't come up in your last 3" — and lets the creator draw the conclusion. Same
ethos as the craft read itself: observations, not claims.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Upload

DIM_LABEL = {
    "hook": "the hook",
    "pacing": "pacing",
    "cut": "cut rhythm",
    "framing": "framing",
    "payoff": "the payoff",
    "structure": "structure & order",
    "text": "on-screen text",
    "clarity": "message clarity",
    "audio": "audio",
    "energy": "energy & delivery",
}


def _label(d: str) -> str:
    return DIM_LABEL.get(d, d)


def compute_progress(user_id: int) -> dict:
    """Per-creator craft trend. Returns the reads timeline (newest first) plus the
    dimensions that RECUR vs the ones that recurred early but have dropped out of
    recent reads ('moving past')."""
    with session_scope() as s:
        rows = (
            s.execute(
                select(Upload.video_id, Upload.title, Upload.created_at, Upload.craft_read)
                .where(Upload.user_id == user_id, Upload.craft_read.isnot(None))
                .order_by(Upload.created_at.asc())  # oldest -> newest
            )
            .all()
        )

    timeline = []  # oldest -> newest
    for vid, title, created, read in rows:
        if not isinstance(read, dict) or read.get("grounded") is False:
            continue
        dim = read.get("opportunity_dimension") or ""
        if dim == "none":
            dim = ""
        timeline.append(
            {
                "video_id": vid,
                "title": (title or "Your reel")[:80],
                "date": created.isoformat() if created else None,
                "dimension": dim,
                "dimension_label": _label(dim) if dim else None,
            }
        )

    n = len(timeline)
    if n == 0:
        return {"ready": False, "n": 0, "reads": [], "improving": [], "recurring": [],
                "headline": "Read a reel and your craft trend starts here."}

    dims = [t["dimension"] for t in timeline if t["dimension"]]
    newest_first = list(reversed(timeline))

    if n < 3 or len(dims) < 3:
        return {
            "ready": True, "n": n, "reads": newest_first, "improving": [], "recurring": [],
            "headline": f"{n} read{'s' if n != 1 else ''} so far — read a couple more and your "
                        f"recurring-vs-improving trend shows up here.",
        }

    # Split into a recent window and the earlier reads. A dimension that recurred
    # earlier but is absent from recent reads is one the creator has moved past;
    # one that's still in recent reads (and repeated overall) is persistent.
    recent_k = min(n - 1, max(2, n // 3))
    recent = {d for d in dims[-recent_k:]}
    earlier = dims[:-recent_k]
    earlier_counts = Counter(earlier)
    total = Counter(dims)

    improving = [
        {"dimension": d, "label": _label(d), "past_count": c}
        for d, c in earlier_counts.most_common()
        if c >= 2 and d not in recent
    ]
    recurring = [
        {"dimension": d, "label": _label(d), "count": c}
        for d, c in total.most_common()
        if c >= 2 and d in recent
    ][:3]

    if improving:
        top = improving[0]
        headline = (f"{top['label'].capitalize()} was a recurring note early on "
                    f"({top['past_count']}×) and hasn't come up in your last {recent_k} reads.")
    elif recurring:
        top = recurring[0]
        headline = (f"{top['label'].capitalize()} is your most persistent note — "
                    f"{top['count']} of your {n} reads.")
    else:
        headline = "No single note dominates your reads — you're working with range."

    return {
        "ready": True, "n": n, "reads": newest_first,
        "improving": improving[:3], "recurring": recurring, "headline": headline,
    }
