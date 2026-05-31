"""Plain-English synthesis of a video's breakdown — the 'creative-director read'.

Turns the structured aggregate + frame comparisons into:
  - a short plain-English read (2-3 sentences),
  - a prioritised 'worth trying' list (imperative, ranked by gap size),
  - a short 'already working' list.

Template-based: deterministic, no LLM, no API key, cannot overclaim. The framing
stays honest — comparisons to winning videos, never causal guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select

from creative_director.advice.breakdown import VideoBreakdown
from creative_director.advice.timeline_benchmark import summarize_timeline
from creative_director.storage.db import session_scope
from creative_director.storage.models import VideoTimeline

ARCHETYPE_PLAIN = {
    "talking": "talking-to-camera video",
    "demo": "silent exercise demo",
}

_VIBE_PLAIN = {
    "talking_head": "a person talking to camera",
    "exercise_demo": "an exercise demo",
    "muscle_closeup": "a muscle close-up",
    "gym_wide": "a wide gym shot",
    "text_card": "an on-screen text card",
    "food_shot": "a food shot",
    "outdoor": "an outdoor shot",
}


def _plain_vibe(v: Optional[str]) -> str:
    if not v:
        return "an unclear shot"
    return _VIBE_PLAIN.get(v, "a " + v.replace("_", " "))


@dataclass
class Suggestion:
    text: str  # imperative phrasing for the 'worth trying' list
    clause: str  # observational fragment for the read paragraph
    gap: float  # 0-1 ranking weight
    is_proxy: bool = False


@dataclass
class PlainSummary:
    archetype: str
    read: str
    worth_trying: list[Suggestion] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)


def _aggregate_suggestions(b: VideoBreakdown) -> list[Suggestion]:
    arch = ARCHETYPE_PLAIN.get(b.archetype, "video")
    out: list[Suggestion] = []
    for f in b.findings:
        if not f.off_benchmark:
            continue
        # Drop structural/low-fixability findings from the 'worth trying' list:
        # there's nothing the creator can usefully *try* about audio voice
        # ratio or tempo without changing the entire format.
        if f.fixability == "low":
            continue
        yv, bv = f.your_value, f.benchmark_value
        # Use the already-ranked composite (gap_score x fixability) so the
        # 'worth trying' order matches the breakdown table.
        gap = f.rank_score
        if f.causal == "likely-proxy":
            out.append(
                Suggestion(
                    text=(
                        f"{f.label} differs from winners — but treat this as a weak "
                        f"signal, not a lever. Skilled creators just tend not to "
                        f"bother with it; copying the number won't move views."
                    ),
                    clause=f"its {f.label.lower()} differs from winners (a weak signal)",
                    gap=gap * 0.2,
                    is_proxy=True,
                )
            )
            continue
        hi = f.direction == "above"
        feat = f.feature
        if feat == "duration_seconds":
            text = (
                f"Tighten the length — yours runs {yv:.0f}s; winning {arch}s "
                f"average about {bv:.0f}s."
                if hi
                else f"It runs short at {yv:.0f}s vs about {bv:.0f}s for winners."
            )
            clause = (
                f"it runs {yv:.0f}s where winners average about {bv:.0f}s"
                if hi
                else f"it is shorter than winners ({yv:.0f}s vs ~{bv:.0f}s)"
            )
        elif feat == "transcript_word_count":
            text = (
                f"Trim the script — {yv:.0f} spoken words vs about {bv:.0f} for winners."
                if hi
                else f"Sparse narration — {yv:.0f} spoken words vs about {bv:.0f} for winners."
            )
            clause = (
                f"it packs {yv:.0f} spoken words against about {bv:.0f} for winners"
                if hi
                else f"it uses fewer spoken words than winners ({yv:.0f} vs ~{bv:.0f})"
            )
        elif feat == "title_char_count":
            text = (
                f"Shorten the title — {yv:.0f} characters vs about {bv:.0f} for winners."
                if hi
                else f"Your title is brief ({yv:.0f} chars); winners write about {bv:.0f}."
            )
            clause = f"its title runs {'longer' if hi else 'shorter'} than winners'"
        elif feat == "title_emoji_count":
            text = (
                f"Ease off the title emoji — {yv:.0f} vs about {bv:.0f} for winners."
                if hi
                else f"Winners use slightly more title emoji (~{bv:.0f} vs your {yv:.0f})."
            )
            clause = "its title emoji use differs from winners"
        else:
            text = f"{f.label}: yours {yv:.0f}{f.unit}, winners about {bv:.0f}{f.unit}."
            clause = f"its {f.label.lower()} differs from winners"
        out.append(Suggestion(text=text, clause=clause, gap=gap))
    return out


def _frame_suggestions(b: VideoBreakdown, frame_benchmark: dict) -> list[Suggestion]:
    bm = (frame_benchmark.get("archetypes") or {}).get(b.archetype)
    if not bm:
        return []
    with session_scope() as s:
        rows = (
            s.execute(select(VideoTimeline).where(VideoTimeline.video_id == b.video_id))
            .scalars()
            .all()
        )
    summ = summarize_timeline(rows)
    if not summ:
        return []
    arch = ARCHETYPE_PLAIN.get(b.archetype, "video")
    out: list[Suggestion] = []

    yf, bf = summ.get("hook_face_frac"), bm.get("hook_face_pct")
    if yf is not None and bf is not None and yf < bf - 0.2:
        out.append(
            Suggestion(
                text=(
                    f"Get a face on screen sooner — winning {arch}s show a face "
                    f"{bf * 100:.0f}% of the first 3 seconds; yours {yf * 100:.0f}%."
                ),
                clause=(
                    f"a face is on screen only {yf * 100:.0f}% of the hook "
                    f"vs {bf * 100:.0f}% for winners"
                ),
                gap=min(1.0, (bf - yf) * 1.5),
            )
        )

    your_vibe = summ.get("hook_vibe")
    vibe_dist = bm.get("hook_vibe_dist") or {}
    if your_vibe and vibe_dist:
        top_vibe, top_share = next(iter(vibe_dist.items()))
        your_share = vibe_dist.get(your_vibe, 0.0)
        if your_vibe != top_vibe and your_share < 0.15:
            out.append(
                Suggestion(
                    text=(
                        f"Open on {_plain_vibe(top_vibe)} — that's how "
                        f"{top_share * 100:.0f}% of winning {arch}s start; yours "
                        f"opens on {_plain_vibe(your_vibe)}."
                    ),
                    clause=(
                        f"it opens on {_plain_vibe(your_vibe)} rather than "
                        f"{_plain_vibe(top_vibe)}, the common winning opener"
                    ),
                    gap=0.45,
                )
            )
    return out


def build_summary(breakdown: VideoBreakdown, frame_benchmark: dict) -> PlainSummary:
    """Synthesise the structured breakdowns into a plain-English read."""
    arch_plain = ARCHETYPE_PLAIN.get(breakdown.archetype, "video")
    suggestions = _aggregate_suggestions(breakdown) + _frame_suggestions(
        breakdown, frame_benchmark
    )
    suggestions.sort(key=lambda s: -s.gap)
    worth = [s for s in suggestions if s.gap >= 0.1][:3]

    dur = breakdown.duration_seconds
    dur_txt = f"{dur}s " if dur else ""
    if worth:
        clauses = [s.clause for s in worth[:2]]
        gaps = clauses[0] if len(clauses) == 1 else f"{clauses[0]}, and {clauses[1]}"
        read = (
            f"This is a {dur_txt}{arch_plain}. Compared with winning fitness Shorts "
            f"of the same format, {gaps}."
        )
    else:
        read = (
            f"This {dur_txt}{arch_plain} tracks winning fitness Shorts closely on "
            f"every feature measured — no clear gaps stand out."
        )

    strengths = [
        f"{f.label} is in line with winners (~{f.benchmark_value:.0f}{f.unit})."
        for f in breakdown.findings
        if not f.off_benchmark
    ][:3]

    return PlainSummary(
        archetype=breakdown.archetype,
        read=read,
        worth_trying=worth,
        strengths=strengths,
    )
