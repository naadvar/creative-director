"""Read-flywheel report: aggregate the one-tap craft-read feedback into a signal
you can act on. Every row is a frame-grounded labeled example.

    python -m scripts.feedback_report [days]

How each label feeds back into the engine:
  • not_in_reel  → the read FABRICATED something the creator says isn't there. This
                   is a hallucination label — the exact failure the grounding gate
                   exists to suppress. Feed these reels' (read, transcript, frames)
                   into the gate's eval set (scripts/tmp/retest_gate.py) to measure
                   + tighten fabrication suppression. A note dismissed 'not_in_reel'
                   a lot is a gate miss.
  • not_useful   → the read was accurate but boilerplate / low-leverage. A usefulness
                   label — tune the lever + blind-spot prompts, and demote note
                   shapes (by dimension) that get dismissed a lot.
  • helpful      → the lever landed. Positive label — these are the lever shapes to
                   KEEP; over-rotate the prompt toward what earns 👍.

The store is the WRITABLE userdata.db (survives corpus redeploys), so this signal
accumulates with real usage.
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console emoji-safe
except Exception:  # noqa: BLE001
    pass

from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import NoteFeedback


def main(days: int | None) -> None:
    since = datetime.utcnow() - timedelta(days=days) if days else None
    with session_scope() as s:
        q = select(NoteFeedback)
        if since is not None:
            q = q.where(NoteFeedback.created_at >= since)
        rows = s.execute(q).scalars().all()

    if not rows:
        print("No feedback yet. (The 👍/👎 + dismissals land here as users read.)")
        return

    by_reason = Counter(r.reason or "dismissed" for r in rows)
    window = f"last {days}d" if days else "all time"
    print(f"=== Craft-read feedback ({window}) — {len(rows)} signals ===")
    for reason in ("helpful", "not_useful", "not_in_reel", "dismissed"):
        n = by_reason.get(reason, 0)
        if n:
            print(f"  {reason:12} {n:4}  ({100*n/len(rows):.0f}%)")

    # The actionable lists.
    fab = [r for r in rows if r.reason == "not_in_reel"]
    if fab:
        print(f"\n--- {len(fab)} FABRICATION flags (not_in_reel) → grounding-gate eval ---")
        top = Counter((r.video_id, (r.note or "")[:80]) for r in fab).most_common(10)
        for (vid, note), c in top:
            print(f"  [{vid}] ×{c}: {note}")

    nu = [r for r in rows if r.reason == "not_useful"]
    if nu:
        print(f"\n--- {len(nu)} NOT-USEFUL flags → lever/blind-spot prompt tuning ---")
        for note, c in Counter((r.note or "")[:90] for r in nu).most_common(10):
            print(f"  ×{c}: {note}")

    helpful = [r for r in rows if r.reason == "helpful"]
    if helpful:
        print(f"\n--- {len(helpful)} HELPFUL 👍 (lever shapes to keep) ---")
        for note, c in Counter((r.note or "")[:90] for r in helpful).most_common(5):
            print(f"  ×{c}: {note}")


if __name__ == "__main__":
    arg = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    main(arg)
