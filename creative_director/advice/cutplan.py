"""CapCut-style cut/trim guidance.

Compares a reel's actual cut pattern + hook to the winner pacing benchmark
(category winners where data allows, else tier x archetype) and produces:
  - the creator's actual cuts + shot segments
  - over-long holds (shots much longer than winners')
  - first-cut timing vs winners
  - a single suggested intro-trim (the highest-leverage edit)
  - an interactive recompute: given a trim start, which hook checks now pass

HONEST FRAMING: every message is "winners in your category do X" — never
"this will improve your retention." We have no retention data (IG doesn't
expose it); this matches what works, it doesn't promise outcomes.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from creative_director.advice.benchmark import classify_archetype, is_voiceover_led
from creative_director.storage.db import session_scope
from creative_director.storage.models import Video, VideoTimeline

HOOK_SECONDS = 3
_MOTION_FLOOR = 0.10  # per-second motion above this = "something is moving"


def _load(video_id: str):
    with session_scope() as s:
        v = s.get(Video, video_id)
        if v is None or v.features is None:
            return None
        arch = classify_archetype(v.features.transcript_word_count)
        rows = (
            s.execute(select(VideoTimeline).where(VideoTimeline.video_id == video_id))
            .scalars()
            .all()
        )
        tl = [
            {
                "second": r.second,
                "is_cut": bool(r.is_cut),
                "has_face": bool(r.has_face) if r.has_face is not None else False,
                "motion": float(r.motion) if r.motion is not None else 0.0,
            }
            for r in sorted(rows, key=lambda r: r.second)
        ]
        face_frac = (sum(1 for r in tl if r["has_face"]) / len(tl)) if tl else None
        return {
            "archetype": arch,
            "duration": v.duration_seconds or len(tl),
            "tl": tl,
            # Voiceover-led: narration with no presenter (animation/b-roll).
            # Face-timing checks and dead-air trims are unsafe here — the
            # "no face + low motion" seconds usually carry the narration.
            "voiceover_led": is_voiceover_led(arch, face_frac),
        }


def _shot_segments(cuts: list[int], duration: int) -> list[tuple[int, int]]:
    """Segments [start, end) bounded by cuts."""
    bounds = [0] + sorted(cuts) + [duration]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]


def build_cut_plan(video_id: str, benchmark: dict) -> Optional[dict]:
    data = _load(video_id)
    if data is None or not data["tl"]:
        return None
    arch = data["archetype"]
    tl = data["tl"]
    duration = data["duration"]
    arch_bm = (benchmark.get("archetypes") or {}).get(arch, {})

    cuts = [r["second"] for r in tl if r["is_cut"]]
    your_first_cut = min(cuts) if cuts else None
    winner_first_cut = arch_bm.get("first_cut_second_median")
    winner_cuts_per_10s = arch_bm.get("cuts_per_10s_median") or 0.0
    winner_avg_shot = (10.0 / winner_cuts_per_10s) if winner_cuts_per_10s else None
    winner_hook_face = arch_bm.get("hook_face_pct")

    # Over-long holds: shots much longer than winners' average shot.
    long_threshold = max(2.0 * winner_avg_shot, 4.0) if winner_avg_shot else 6.0
    over_long = [
        {"start": a, "end": b, "length": b - a}
        for (a, b) in _shot_segments(cuts, duration)
        if (b - a) >= long_threshold
    ]

    # Hook face presence in the first 3s.
    hook = [r for r in tl if r["second"] < HOOK_SECONDS]
    your_hook_face = (sum(1 for r in hook if r["has_face"]) / len(hook)) if hook else 0.0

    suggestions: list[dict] = []
    # 1. Late / absent first cut.
    if winner_first_cut is not None and winner_cuts_per_10s >= 1.0:
        if your_first_cut is None:
            suggestions.append({
                "second": int(winner_first_cut),
                "type": "first_cut",
                "message": f"Your reel holds one shot the whole way; {arch} winners in your category cut by ~{winner_first_cut:.0f}s. Add a cut early.",
            })
        elif your_first_cut > winner_first_cut + 2:
            suggestions.append({
                "second": int(your_first_cut),
                "type": "first_cut",
                "message": f"Your first cut is at {your_first_cut}s; winners cut by ~{winner_first_cut:.0f}s. The opening shot holds too long.",
            })
    # 2. Over-long holds.
    for seg in over_long[:3]:
        suggestions.append({
            "second": seg["start"],
            "type": "long_hold",
            "message": f"{seg['start']}-{seg['end']}s is one {seg['length']}s shot; winners' shots average ~{winner_avg_shot:.0f}s. Break it up.",
        })

    # Suggested intro trim: if the opening is slow (late first cut, OR static +
    # faceless first 2s), trim to the first 'engaging' second. NEVER for
    # voiceover-led reels — their narration starts at 0 and a trim would cut it.
    suggested_trim_start = None
    static_open = all(r["motion"] < _MOTION_FLOOR for r in tl[:2]) and not any(
        r["has_face"] for r in tl[:2]
    )
    late_open = winner_first_cut is not None and your_first_cut is not None and your_first_cut > winner_first_cut + 2
    if (static_open or late_open) and not data["voiceover_led"]:
        engaging = next(
            (r["second"] for r in tl if r["has_face"] or r["motion"] >= _MOTION_FLOOR),
            None,
        )
        candidate = your_first_cut if late_open else engaging
        if candidate and 0 < candidate <= max(1, len(tl) // 3):
            suggested_trim_start = int(candidate)

    return {
        "video_id": video_id,
        "archetype": arch,
        "duration": duration,
        "category": benchmark.get("category"),
        "benchmark_scope": "category" if benchmark.get("category") else "tier",
        "your_first_cut": your_first_cut,
        "winner_first_cut": winner_first_cut,
        "your_cuts": cuts,
        "your_hook_face_pct": round(your_hook_face, 2),
        "winner_hook_face_pct": round(winner_hook_face, 2) if winner_hook_face is not None else None,
        "winner_avg_shot": round(winner_avg_shot, 1) if winner_avg_shot else None,
        "over_long_holds": over_long,
        "suggestions": suggestions,
        "suggested_trim_start": suggested_trim_start,
    }


def recompute_for_trim(video_id: str, benchmark: dict, trim_start: int) -> dict:
    """Given a proposed trim start, report which hook checks now pass — the
    live aha as the creator drags the trim handle."""
    data = _load(video_id)
    if data is None:
        return {"trim_start": trim_start, "checks": [], "aligned": 0, "total": 0}
    tl = data["tl"]
    arch = data["archetype"]
    arch_bm = (benchmark.get("archetypes") or {}).get(arch, {})
    winner_first_cut = arch_bm.get("first_cut_second_median") or 2.0
    winner_hook_face = arch_bm.get("hook_face_pct") or 0.0

    after = [r for r in tl if r["second"] >= trim_start]
    win = after[:HOOK_SECONDS]
    open_win = after[:2]

    face_by_1s = any(r["has_face"] for r in after[:2])
    movement_open = any(r["motion"] >= _MOTION_FLOOR for r in open_win)
    # first cut within winner median of the NEW start
    rel_cuts = [r["second"] - trim_start for r in after if r["is_cut"]]
    cut_in_window = any(0 < c <= winner_first_cut + 1 for c in rel_cuts)

    checks = []
    # Only assert face-related checks for archetypes/categories where winners
    # actually show a face in the hook — and never for voiceover-led reels
    # (no presenter on screen; there is no face to deploy).
    if winner_hook_face >= 0.4 and not data["voiceover_led"]:
        checks.append({"label": f"Face on screen by 1s (winners {winner_hook_face*100:.0f}%)", "pass": bool(face_by_1s)})
    checks.append({"label": "Opens on movement, not a static hold", "pass": bool(movement_open)})
    checks.append({"label": f"First cut within ~{winner_first_cut:.0f}s of the open", "pass": bool(cut_in_window)})

    aligned = sum(1 for c in checks if c["pass"])
    return {
        "trim_start": trim_start,
        "checks": checks,
        "aligned": aligned,
        "total": len(checks),
    }


# ============================================================================
# Auto "winner cut" — a virtual edit that removes only DEAD AIR.
#
# Honest-by-construction: we cut a second only when it has NO face on screen
# AND essentially no motion. "Nobody's there and nothing's moving" is a fact,
# and removing it can't destroy meaning. Anything that needs judgment about the
# *content* (re-pacing a live single-shot hold, reordering) stays a human
# suggestion in build_cut_plan — we never auto-touch live footage.
# ============================================================================

_DEAD_TAIL_MIN = 3   # trailing dead seconds worth dropping
_DEAD_MID_MIN = 8    # interior dead run worth dropping (hard-gated; rarely fires)


def _is_dead(r: dict) -> bool:
    """A second with no face and no real motion — dead air."""
    return (not r["has_face"]) and r["motion"] < _MOTION_FLOOR


def build_auto_cut(video_id: str, benchmark: dict) -> Optional[dict]:
    """A winner-paced cut of the reel that strips dead air only.

    Returns kept ``segments`` (original-video seconds) plus the ``removed``
    ranges with a plain reason for each, so the UI can play the tightened
    version back virtually and explain every cut.
    """
    data = _load(video_id)
    if data is None or not data["tl"]:
        return None
    arch = data["archetype"]
    tl = data["tl"]
    duration = data["duration"]
    n = len(tl)
    arch_bm = (benchmark.get("archetypes") or {}).get(arch, {})
    winner_first_cut = arch_bm.get("first_cut_second_median")
    winner_cuts_per_10s = arch_bm.get("cuts_per_10s_median") or 0.0
    winner_avg_shot = (10.0 / winner_cuts_per_10s) if winner_cuts_per_10s else None

    removed: list[dict] = []

    # Voiceover-led reels: "dead" (faceless + static) seconds usually carry the
    # narration, which we can't hear per-second — so we never auto-trim them.
    voiceover_led = data["voiceover_led"]

    # --- 1. Slow open: drop a leading run of dead seconds. ------------------
    first_engaging = next((r["second"] for r in tl if not _is_dead(r)), n)
    trim_start = first_engaging if (2 <= first_engaging < n and not voiceover_led) else 0
    if trim_start > 0:
        reason = (
            f"slow open — winning {arch} reels are moving by ~{winner_first_cut:.0f}s"
            if winner_first_cut
            else "slow open — nothing on screen for the first seconds"
        )
        removed.append({"start": 0, "end": trim_start, "reason": reason})

    # --- 2. Dead tail: drop a trailing run of dead seconds. -----------------
    j = n - 1
    while j >= 0 and _is_dead(tl[j]):
        j -= 1
    dead_tail_start = j + 1
    tail_end = duration
    if (
        duration - dead_tail_start >= _DEAD_TAIL_MIN
        and dead_tail_start > trim_start + 1
        and not voiceover_led
    ):
        removed.append(
            {
                "start": dead_tail_start,
                "end": duration,
                "reason": "dead tail — no movement or face to end on",
            }
        )
        tail_end = dead_tail_start

    # --- 3. Interior dead stretch: DEMO reels only, hard-gated. -------------
    # A faceless+static *interior* stretch is only safe to cut when the reel
    # isn't carrying the content in speech. For "talking" reels a static stretch
    # is almost always voiceover-over-a-held-shot (a diagram/text the creator
    # narrates) — cutting it would delete the message we can't hear (no
    # per-second audio). So interior removal is gated to near-silent demos.
    mid: list[tuple[int, int]] = []
    if arch == "demo":
        min_mid = (
            max(2.0 * winner_avg_shot, float(_DEAD_MID_MIN))
            if winner_avg_shot
            else float(_DEAD_MID_MIN)
        )
        body = [r for r in tl if trim_start <= r["second"] < tail_end]
        run_start: Optional[int] = None
        for r in body:
            if _is_dead(r):
                if run_start is None:
                    run_start = r["second"]
            else:
                if run_start is not None:
                    if r["second"] - run_start >= min_mid:
                        mid.append((run_start, r["second"]))
                    run_start = None
        for a, b in mid:
            removed.append(
                {"start": a, "end": b, "reason": f"{b - a}s of dead air — static, no one on screen"}
            )

    # --- Build kept segments = [trim_start, tail_end) minus interior cuts. --
    segments: list[dict] = []
    pos = trim_start
    for a, b in sorted(mid):
        if a > pos:
            segments.append({"start": pos, "end": a})
        pos = b
    if tail_end > pos:
        segments.append({"start": pos, "end": tail_end})
    if not segments:  # safety — never return an empty edit
        segments = [{"start": 0, "end": duration}]
        removed = []

    new_duration = sum(s["end"] - s["start"] for s in segments)
    return {
        "video_id": video_id,
        "archetype": arch,
        "category": benchmark.get("category"),
        "benchmark_scope": "category" if benchmark.get("category") else "tier",
        "original_duration": duration,
        "new_duration": new_duration,
        "removed_seconds": duration - new_duration,
        "changed": new_duration < duration,
        "segments": segments,
        "removed": removed,
        "winner_first_cut": winner_first_cut,
        "winner_avg_shot": round(winner_avg_shot, 1) if winner_avg_shot else None,
    }
