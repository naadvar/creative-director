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

from creative_director.advice.benchmark import face_advice_applies, is_voiceover_led
from creative_director.advice.breakdown import VideoBreakdown
from creative_director.advice.categories import _base as _niche_base
from creative_director.advice.timeline_benchmark import summarize_timeline
from creative_director.storage.db import session_scope
from creative_director.storage.models import VideoTimeline

# How to describe the *subject* video's format (niche-neutral). The demo
# phrase avoids claiming "silent" — demo just means little-to-no talking, and
# a read that says "silent ... packs 19 spoken words" contradicts itself.
ARCHETYPE_PLAIN = {
    "talking": "talking-to-camera video",
    "demo": "visual-led video (little to no talking)",
}


def _cohort(niche: Optional[str], video_id: str) -> str:
    """How to refer to the winning set in prose — niche- and platform-aware.

    e.g. ``ig_food`` -> "food Reels", a YouTube fitness id -> "fitness Shorts",
    an unknown niche -> just "Reels"/"Shorts". Uploaded reels (``up_`` ids)
    are short-form verticals benchmarked against IG niches -> "Reels".
    """
    platform = "Reels" if (video_id or "").startswith(("ig_", "up_")) else "Shorts"
    word = _niche_base(niche)  # 'food' | 'travel' | 'fashion' | 'fitness' | None
    return f"{word} {platform}" if word else platform

# Display strings for the CLIP vibe keys (see advice/clip_prompts.py). Keys not
# listed here fall back to a generic "a <key>" in _plain_vibe.
_VIBE_PLAIN = {
    # shared
    "talking_head": "a person talking to camera",
    "text_overlay": "an on-screen text card",
    # fitness
    "exercise_demo": "an exercise demo",
    "muscle_closeup": "a muscle close-up",
    "gym_setting": "a gym shot",
    "physique_reveal": "a physique reveal",
    "food_or_meal": "a food shot",
    "action_movement": "fast, dynamic movement",
    # food
    "plated_dish": "a plated dish",
    "ingredients": "raw ingredients laid out",
    "cooking_action": "food being cooked",
    "hands_prep": "a close-up of food prep",
    "eating": "someone tasting the food",
    "restaurant": "a restaurant interior",
    # travel
    "landscape": "a scenic landscape",
    "landmark": "a landmark",
    "cityscape": "a city street",
    "beach_water": "a beach or water shot",
    "hotel_resort": "a hotel or resort shot",
    "person_scenic": "a person in front of scenery",
    # fashion
    "full_outfit": "a full-body outfit shot",
    "mirror_selfie": "a mirror outfit clip",
    "clothing_closeup": "a clothing close-up",
    "getting_dressed": "a getting-dressed shot",
    "accessories": "an accessories close-up",
    "makeup_hair": "a hair or makeup shot",
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


def _aggregate_suggestions(b: VideoBreakdown, cohort: str) -> list[Suggestion]:
    out: list[Suggestion] = []
    # IG/uploads have captions, not titles — the title features there are the
    # caption's opening line, and creators read "title" as a YouTube-ism.
    t_word = "caption opening" if b.video_id.startswith(("ig_", "up_")) else "title"
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
                f"Tighten the length — yours runs {yv:.0f}s; winning {cohort} "
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
            # Word counts need a real gap — "3 spoken words vs about 1" or
            # "0 vs ~1" is noise, not advice.
            if yv is None or abs(yv - bv) < 15:
                continue
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
            # Needs a real gap — "43 chars vs about 33" is noise.
            if yv is None or abs(yv - bv) < 12:
                continue
            text = (
                f"Shorten the {t_word} — {yv:.0f} characters vs about {bv:.0f} for winners."
                if hi
                else f"Your {t_word} is brief ({yv:.0f} chars); winners write about {bv:.0f}."
            )
            clause = f"its {t_word} runs {'longer' if hi else 'shorter'} than winners'"
        elif feat == "title_emoji_count":
            # Emoji counts are tiny integers — a 1-vs-0 "gap" is noise, and
            # surfacing it as advice reads as pedantic. Require a real delta.
            if yv is None or abs(yv - bv) < 2:
                continue
            text = (
                f"Ease off the {t_word} emoji — {yv:.0f} vs about {bv:.0f} for winners."
                if hi
                else f"Winners use slightly more {t_word} emoji (~{bv:.0f} vs your {yv:.0f})."
            )
            clause = f"its {t_word} emoji use differs from winners"
        else:
            text = f"{f.label}: yours {yv:.0f}{f.unit}, winners about {bv:.0f}{f.unit}."
            clause = f"its {f.label.lower()} differs from winners"
        out.append(Suggestion(text=text, clause=clause, gap=gap))
    return out


def _frame_suggestions(
    b: VideoBreakdown, frame_benchmark: dict, cohort: str
) -> tuple[list[Suggestion], Optional[float]]:
    """Returns (suggestions, overall_face_frac) — the face fraction lets the
    caller reword the read for voiceover-led reels."""
    bm = (frame_benchmark.get("archetypes") or {}).get(b.archetype)
    with session_scope() as s:
        rows = (
            s.execute(select(VideoTimeline).where(VideoTimeline.video_id == b.video_id))
            .scalars()
            .all()
        )
    faces = [r.has_face for r in rows if r.has_face is not None]
    face_frac = (sum(faces) / len(faces)) if faces else None
    if not bm:
        return [], face_frac
    summ = summarize_timeline(rows)
    if not summ:
        return [], face_frac
    out: list[Suggestion] = []
    presenter_ok = face_advice_applies(b.archetype, face_frac)

    yf, bf = summ.get("hook_face_frac"), bm.get("hook_face_pct")
    # "Get a face on screen" only when the format HAS a presenter to deploy —
    # never for voiceover-over-animation reels or faceless b-roll demos.
    if yf is not None and bf is not None and yf < bf - 0.2 and presenter_ok:
        out.append(
            Suggestion(
                text=(
                    f"Get a face on screen sooner — winning {cohort} show a face "
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
        # Never suggest "open on a person talking to camera" to formats that
        # can't act on it: no-presenter reels (nobody to film) and silent demos
        # (opening on someone talking prescribes adding speech). Pick the most
        # common winning opener they can actually shoot instead.
        if presenter_ok and b.archetype != "demo":
            top_vibe, top_share = next(iter(vibe_dist.items()))
        else:
            non_face = [(k, v) for k, v in vibe_dist.items() if k != "talking_head"]
            if not non_face:
                return out, face_frac
            top_vibe, top_share = non_face[0]
        your_share = vibe_dist.get(your_vibe, 0.0)
        if your_vibe != top_vibe and your_share < 0.15:
            out.append(
                Suggestion(
                    text=(
                        f"Open on {_plain_vibe(top_vibe)} — that's how "
                        f"{top_share * 100:.0f}% of winning {cohort} start; yours "
                        f"opens on {_plain_vibe(your_vibe)}."
                    ),
                    clause=(
                        f"it opens on {_plain_vibe(your_vibe)} rather than "
                        f"{_plain_vibe(top_vibe)}, the common winning opener"
                    ),
                    gap=0.45,
                )
            )
    return out, face_frac


def build_summary(
    breakdown: VideoBreakdown, frame_benchmark: dict, niche: Optional[str] = None
) -> PlainSummary:
    """Synthesise the structured breakdowns into a plain-English read."""
    cohort = _cohort(niche, breakdown.video_id)
    frame_sugs, face_frac = _frame_suggestions(breakdown, frame_benchmark, cohort)
    # A transcript-heavy reel with (almost) no presenter is voiceover-led
    # (animation / b-roll) — calling it "talking-to-camera" reads as wrong.
    if is_voiceover_led(breakdown.archetype, face_frac):
        arch_plain = "voiceover-led video (no presenter on screen)"
    else:
        arch_plain = ARCHETYPE_PLAIN.get(breakdown.archetype, "video")
    suggestions = _aggregate_suggestions(breakdown, cohort) + frame_sugs
    suggestions.sort(key=lambda s: -s.gap)
    # Proxy findings self-describe as "not a lever — don't act on this"; they
    # have no business occupying a "Worth trying" slot. (They stay visible in
    # the findings table with their honest framing.)
    worth = [s for s in suggestions if s.gap >= 0.1 and not s.is_proxy][:3]

    dur = breakdown.duration_seconds
    dur_txt = f"{dur}s " if dur else ""
    if worth:
        clauses = [s.clause for s in worth[:2]]
        gaps = clauses[0] if len(clauses) == 1 else f"{clauses[0]}, and {clauses[1]}"
        read = (
            f"This is a {dur_txt}{arch_plain}. Compared with winning {cohort} "
            f"of the same format, {gaps}."
        )
    else:
        read = (
            f"This {dur_txt}{arch_plain} tracks winning {cohort} closely on "
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
