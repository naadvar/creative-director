"""KPI aggregation — the numbers every launch decision depends on.

Sources: Event rows (behavioral, from telemetry.py — only counts from when
telemetry shipped) UNION Upload rows (historical — uploads have always been
stored, so upload-based activity/retention works retroactively), plus
NoteFeedback (helpful%) and Upload.craft_read/revision_verdict (quality).

Used by both scripts/telemetry_report.py (local/offline) and the key-gated
GET /tools/kpis endpoint (live prod numbers from a phone)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from creative_director.storage.db import session_scope
from creative_director.storage.models import Event, NoteFeedback, Upload, User


def _day(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def compute_kpis(now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    d7 = now - timedelta(days=7)
    d28 = now - timedelta(days=28)

    with session_scope() as s:
        users = s.execute(select(User.id, User.created_at, User.email)).all()
        uploads = s.execute(
            select(Upload.video_id, Upload.user_id, Upload.created_at, Upload.craft_read,
                   Upload.prior_video_id, Upload.revision_verdict, Upload.niche)
        ).all()
        events = s.execute(select(Event.name, Event.user_id, Event.created_at, Event.props)).all()
        feedback = s.execute(select(NoteFeedback.reason, NoteFeedback.created_at)).all()

    # ---- activity map: user -> set of active days (events + uploads) ----
    active_days: dict[int, set[str]] = defaultdict(set)
    for _, uid, created, *_ in uploads:
        if uid is not None and created:
            active_days[uid].add(_day(created))
    for _, uid, created, _ in events:
        if uid is not None and created:
            active_days[uid].add(_day(created))

    def active_since(cutoff: datetime) -> int:
        cut = _day(cutoff)
        return sum(1 for days in active_days.values() if any(d >= cut for d in days))

    # ---- retention: weekly signup cohorts, D1 / D7 (activity after day 0) ----
    first_seen = {uid: created for uid, created, _ in users if created}
    cohorts: dict[str, dict] = {}
    for uid, seen in first_seen.items():
        if seen is None:
            continue
        week = (seen - timedelta(days=seen.weekday())).strftime("%Y-%m-%d")
        c = cohorts.setdefault(week, {"size": 0, "d1": 0, "d7": 0})
        c["size"] += 1
        days = active_days.get(uid, set())
        day0 = _day(seen)
        d1_lo, d1_hi = _day(seen + timedelta(days=1)), _day(seen + timedelta(days=2))
        d7_hi = _day(seen + timedelta(days=8))
        if any(d1_lo <= d < d1_hi for d in days if d != day0):
            c["d1"] += 1
        if any(day0 < d < d7_hi for d in days):
            c["d7"] += 1

    # ---- uploads funnel + read quality ----
    n_up = len(uploads)
    n_up_7d = sum(1 for u in uploads if u[2] and u[2] >= d7)
    grounded = suppressed = no_read = ungated = 0
    revisions = {"fixed": 0, "still_there": 0, "cant_verify": 0}
    n_rechecks = 0
    for u in uploads:
        read = u[3]
        if not isinstance(read, dict):
            no_read += 1
        elif read.get("grounded") is False:
            suppressed += 1
        else:
            grounded += 1
            # grounded=None (vs True) = the fact-check gate never RAN (perception
            # failure) — the July silent-degradation mode. Scoped to the last 7d so
            # the historical outage doesn't pin the alarm forever; must stay 0.
            if read.get("grounded") is None and u[2] and u[2] >= d7:
                ungated += 1
        if u[4]:  # prior_video_id
            n_rechecks += 1
            state = (u[5] or {}).get("state") if isinstance(u[5], dict) else None
            if state in revisions:
                revisions[state] += 1

    # ---- feedback (helpful%) ----
    fb = defaultdict(int)
    for reason, _created in feedback:
        fb[reason or "unknown"] += 1
    fb_total = sum(fb.values())
    helpful_pct = round(100 * fb.get("helpful", 0) / fb_total) if fb_total else None

    # ---- event counts (7d) ----
    ev7 = defaultdict(int)
    for name, _uid, created, _props in events:
        if created and created >= d7:
            ev7[name] += 1

    return {
        "generated_at": now.isoformat(),
        "users": {
            "total": len(users),
            "new_7d": sum(1 for _, c, _e in users if c and c >= d7),
            "new_28d": sum(1 for _, c, _e in users if c and c >= d28),
        },
        "activity": {
            "wau": active_since(d7),
            "mau_28d": active_since(d28),
            "note": "activity = events + uploads; event-based activity only exists from 2026-07-04",
        },
        "uploads": {
            "total": n_up,
            "last_7d": n_up_7d,
            "grounded": grounded,
            "suppressed": suppressed,
            "no_read": no_read,
            "ungated": ungated,  # gate never ran (perception failure) — alarm if > 0
            "suppression_pct": round(100 * suppressed / max(1, grounded + suppressed)),
        },
        "revision_loop": {"rechecks": n_rechecks, **revisions},
        "feedback": {"total": fb_total, "helpful_pct": helpful_pct, "by_reason": dict(fb)},
        "events_7d": dict(sorted(ev7.items(), key=lambda kv: -kv[1])),
        "cohorts_weekly": {
            wk: {
                "size": c["size"],
                "d1_pct": round(100 * c["d1"] / c["size"]) if c["size"] else 0,
                "d7_pct": round(100 * c["d7"] / c["size"]) if c["size"] else 0,
            }
            for wk, c in sorted(cohorts.items())[-8:]
        },
    }


def render_text(k: dict) -> str:
    L = []
    L.append(f"KPIs @ {k['generated_at']}")
    u, a, up = k["users"], k["activity"], k["uploads"]
    L.append(f"users: {u['total']} total | +{u['new_7d']} this week | +{u['new_28d']} this month")
    L.append(f"active: WAU {a['wau']} | MAU(28d) {a['mau_28d']}")
    L.append(
        f"uploads: {up['total']} total ({up['last_7d']} this week) | grounded {up['grounded']} "
        f"| suppressed {up['suppressed']} ({up['suppression_pct']}%)"
        + (f" | !! UNGATED {up['ungated']} (fact-check gate not running)" if up.get("ungated") else "")
    )
    r = k["revision_loop"]
    L.append(
        f"revision loop: {r['rechecks']} re-checks -> fixed {r['fixed']} / still {r['still_there']} "
        f"/ cant_verify {r['cant_verify']}"
    )
    f = k["feedback"]
    L.append(f"feedback: {f['total']} taps | helpful {f['helpful_pct']}% | {f['by_reason']}")
    if k["events_7d"]:
        L.append("events (7d): " + ", ".join(f"{n}={c}" for n, c in k["events_7d"].items()))
    L.append("weekly cohorts (size / D1% / D7%):")
    for wk, c in k["cohorts_weekly"].items():
        L.append(f"  {wk}: {c['size']:>4} / {c['d1_pct']:>3}% / {c['d7_pct']:>3}%")
    return "\n".join(L)
