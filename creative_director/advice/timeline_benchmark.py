"""Frame-level benchmark + breakdown (Phase 2 advice layer).

Turns per-second VideoTimeline rows into:
  1. a per-archetype benchmark of what *winning* videos do in the hook (0-3s)
     and how they pace cuts;
  2. a per-video frame-level breakdown comparing one video's hook + pacing
     against that benchmark.

This is the in-video advice layer: "your hook holds one shot for 8s, winning
demos cut by ~3s" — located in time, not just a video-level aggregate.

Still correlational: winners' patterns, not proven causes. Phrased as
comparisons, not commands.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median, pstdev
from typing import Optional

import numpy as np
from sqlalchemy import select

from creative_director.advice.benchmark import (
    classify_archetype,
    face_advice_applies,
    is_voiceover_led,
    vlm_has_presenter,
)
from creative_director.advice.tier import tier_for_count
from creative_director.storage.db import session_scope
from creative_director.storage.models import (
    Channel,
    Video,
    VideoFeatures,
    VideoLabel,
    VideoTimeline,
)

HOOK_SECONDS = 3


def summarize_timeline(rows: list[VideoTimeline]) -> Optional[dict]:
    """Reduce a video's per-second rows to hook + pacing stats."""
    rows = sorted(rows, key=lambda r: r.second)
    if not rows:
        return None
    n = len(rows)
    hook = rows[:HOOK_SECONDS]
    cuts = [r.second for r in rows if r.is_cut]
    hook_faces = [r.has_face for r in hook if r.has_face is not None]
    hook_vibes = [r.primary_vibe for r in hook if r.primary_vibe]
    all_vibes = [r.primary_vibe for r in rows if r.primary_vibe]
    return {
        "duration": n,
        "hook_face_frac": (
            sum(1 for f in hook_faces if f) / len(hook_faces)
            if hook_faces
            else None
        ),
        "hook_vibe": Counter(hook_vibes).most_common(1)[0][0] if hook_vibes else None,
        "first_cut_second": min(cuts) if cuts else None,
        "cut_count": len(cuts),
        "cuts_per_10s": (len(cuts) / (n / 10.0)) if n else 0.0,
        "distinct_vibes": len(set(all_vibes)),
    }


def compute_timeline_benchmark(
    label_scheme: str = "views_per_sub_aged_v1",
    niche: str = "fitness",
    tier: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """Aggregate hook + pacing stats over *winning* videos, split by archetype.

    ``tier`` (small | mid | large) restricts winners to that follower-count
    band; ``category`` (calisthenics, powerlifting, ...) restricts to that
    content subtopic. Either None = pool across that dimension.
    """
    by_arch: dict[str, list[dict]] = {"talking": [], "demo": []}

    with session_scope() as s:
        winners = s.execute(
            select(Video, VideoFeatures, Channel.subscriber_count)
            .join(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == label_scheme),
            )
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == niche, VideoLabel.tercile == 2)
        ).all()

        for video, feat, sub_count in winners:
            if tier is not None and tier_for_count(sub_count) != tier:
                continue
            if category is not None and video.category != category:
                continue
            tl = (
                s.execute(
                    select(VideoTimeline).where(VideoTimeline.video_id == video.id)
                )
                .scalars()
                .all()
            )
            summ = summarize_timeline(tl)
            if summ is None:
                continue
            arch = classify_archetype(feat.transcript_word_count)
            by_arch[arch].append(summ)

    archetypes: dict[str, dict] = {}
    for arch, summs in by_arch.items():
        if not summs:
            continue
        first_cuts = [x["first_cut_second"] for x in summs if x["first_cut_second"] is not None]
        face_fracs = [x["hook_face_frac"] for x in summs if x["hook_face_frac"] is not None]
        vibe_counts = Counter(x["hook_vibe"] for x in summs if x["hook_vibe"])
        total_vibes = sum(vibe_counts.values()) or 1
        archetypes[arch] = {
            "n_winners": len(summs),
            "hook_face_pct": float(np.mean(face_fracs)) if face_fracs else None,
            "hook_vibe_dist": {
                k: round(v / total_vibes, 3) for k, v in vibe_counts.most_common()
            },
            "first_cut_second_median": float(median(first_cuts)) if first_cuts else None,
            "pct_with_cut_in_hook": round(
                sum(1 for c in first_cuts if c < HOOK_SECONDS) / len(summs), 3
            ),
            "cuts_per_10s_median": float(median(x["cuts_per_10s"] for x in summs)),
            "distinct_vibes_median": float(median(x["distinct_vibes"] for x in summs)),
        }

    return {
        "label_scheme": label_scheme,
        "niche": niche,
        "tier": tier,
        "category": category,
        "archetypes": archetypes,
    }


@dataclass
class FrameBreakdown:
    video_id: str
    title: str
    archetype: str
    duration: int
    findings: list[str] = field(default_factory=list)


def analyze_timeline(video_id: str, benchmark: Optional[dict] = None) -> FrameBreakdown:
    """Compare one video's hook + pacing to the winner benchmark of its archetype."""
    if benchmark is None:
        benchmark = compute_timeline_benchmark()

    with session_scope() as s:
        video = s.get(Video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")
        feat = video.features
        tl = (
            s.execute(select(VideoTimeline).where(VideoTimeline.video_id == video_id))
            .scalars()
            .all()
        )
        summ = summarize_timeline(tl)
        title = video.title
        arch = classify_archetype(feat.transcript_word_count if feat else None)
        has_presenter = vlm_has_presenter(feat)

    fb = FrameBreakdown(
        video_id=video_id,
        title=title,
        archetype=arch,
        duration=summ["duration"] if summ else 0,
    )
    if summ is None:
        fb.findings.append("No timeline data — run extract_timelines for this video.")
        return fb

    bm = benchmark["archetypes"].get(arch)
    if not bm:
        fb.findings.append(f"No winner benchmark available for archetype '{arch}'.")
        return fb

    noun = "Reels" if video_id.startswith(("ig_", "up_")) else "Shorts"
    faces = [r.has_face for r in tl if r.has_face is not None]
    face_frac = (sum(faces) / len(faces)) if faces else None
    voiceover_led = is_voiceover_led(arch, face_frac, has_presenter)

    # --- Hook: face presence ---
    if voiceover_led:
        fb.findings.append(
            "FORMAT: voiceover-led — narration with no presenter on screen "
            "(animation / b-roll). Face-timing benchmarks don't apply to this format."
        )
    elif not face_advice_applies(arch, face_frac, has_presenter):
        fb.findings.append(
            "FORMAT: no presenter on screen (b-roll / product format) — "
            "face-timing benchmarks don't apply to this format."
        )
    elif summ["hook_face_frac"] is not None and bm["hook_face_pct"] is not None:
        yours = summ["hook_face_frac"]
        winners = bm["hook_face_pct"]
        if yours < winners - 0.25:
            fb.findings.append(
                f"HOOK FACE: your first 3s show a face {yours*100:.0f}% of the time; "
                f"winning {arch} {noun} average {winners*100:.0f}%. "
                f"Consider getting a face on screen sooner."
            )
        else:
            fb.findings.append(
                f"HOOK FACE: aligned ({yours*100:.0f}% vs winners {winners*100:.0f}%)."
            )

    # --- Hook: opening vibe ---
    if summ["hook_vibe"] and bm["hook_vibe_dist"]:
        top_vibe, top_share = next(iter(bm["hook_vibe_dist"].items()))
        yours = summ["hook_vibe"]
        your_share = bm["hook_vibe_dist"].get(yours, 0.0)
        if yours == top_vibe:
            fb.findings.append(
                f"HOOK OPENING: you open on '{yours}', the most common winning "
                f"opener ({top_share*100:.0f}% of {arch} winners). Aligned."
            )
        elif your_share >= 0.15:
            # Your opener is itself a common winning opener — nagging someone
            # to switch from a 27%-of-winners open to a 30% one is noise.
            fb.findings.append(
                f"HOOK OPENING: you open on '{yours}' — a common winning opener "
                f"({your_share*100:.0f}% of {arch} winners). Aligned."
            )
        else:
            fb.findings.append(
                f"HOOK OPENING: you open on '{yours}' "
                f"({your_share*100:.0f}% of winners open this way); the most common "
                f"winning opener is '{top_vibe}' ({top_share*100:.0f}%)."
            )

    # --- Shot variety (CLIP-vibe based — robust, doesn't depend on cut detection) ---
    yours_vibes = summ["distinct_vibes"]
    bm_vibes = bm["distinct_vibes_median"]
    if yours_vibes < bm_vibes - 1:
        fb.findings.append(
            f"SHOT VARIETY: your video shows {yours_vibes} distinct on-screen "
            f"'vibes'; winning {arch} {noun} show ~{bm_vibes:.0f}. More visual "
            f"variety (different shots/angles/framing) may help hold attention."
        )
    elif yours_vibes > bm_vibes + 1:
        fb.findings.append(
            f"SHOT VARIETY: {yours_vibes} distinct on-screen vibes — more "
            f"variety than typical winners (~{bm_vibes:.0f}). No gap here."
        )
    else:
        fb.findings.append(
            f"SHOT VARIETY: {yours_vibes} distinct on-screen vibes, "
            f"in line with winners (~{bm_vibes:.0f})."
        )

    # --- Cuts / pacing (PySceneDetect content-aware detection) ---
    # Only give pacing advice when cutting is actually the norm for the archetype.
    # If winners of an archetype are genuinely single-shot, advising "cut sooner"
    # would be wrong — so the else-branch just describes, doesn't prescribe.
    cut_heavy = (bm["cuts_per_10s_median"] or 0.0) >= 1.0
    if cut_heavy:
        fc = summ["first_cut_second"]
        bm_fc = bm["first_cut_second_median"]
        # First-cut pacing
        if fc is None:
            fb.findings.append(
                f"PACING: your video holds one shot the whole way through; "
                f"winning {arch} {noun} cut by ~second {bm_fc:.0f} "
                f"({bm['pct_with_cut_in_hook']*100:.0f}% cut within the first 3s). "
                f"A static hold tends to lose viewers in this archetype."
            )
        elif bm_fc is not None and fc > bm_fc + 2:
            fb.findings.append(
                f"PACING: your first cut is at second {fc}; winning {arch} {noun} "
                f"cut by ~second {bm_fc:.0f}. The opening shot may hold too long."
            )
        else:
            fb.findings.append(
                f"PACING: first cut at second {fc}, in line with winners "
                f"(~{bm_fc:.0f})."
            )
        # Overall cut rhythm
        yours_rate = summ["cuts_per_10s"]
        bm_rate = bm["cuts_per_10s_median"]
        if yours_rate < bm_rate * 0.5:
            fb.findings.append(
                f"CUT RHYTHM: {yours_rate:.1f} cuts/10s vs winners ~{bm_rate:.1f}. "
                f"Your video is cut noticeably slower than winning {arch} {noun}."
            )
        elif yours_rate > bm_rate * 2.0:
            fb.findings.append(
                f"CUT RHYTHM: {yours_rate:.1f} cuts/10s vs winners ~{bm_rate:.1f}. "
                f"Cut much faster than typical winners — not necessarily wrong, "
                f"but worth a look."
            )
        else:
            fb.findings.append(
                f"CUT RHYTHM: {yours_rate:.1f} cuts/10s, in line with winners "
                f"(~{bm_rate:.1f})."
            )
    else:
        fb.findings.append(
            f"CUTS: {summ['cut_count']} hard cut(s) detected. Winning {arch} "
            f"{noun} of this archetype are mostly single-shot, so this is in line "
            f"with what works."
        )

    return fb


def format_frame_breakdown(fb: FrameBreakdown) -> str:
    lines = [
        f"FRAME-LEVEL BREAKDOWN — {fb.title}",
        f"Archetype: {fb.archetype}  |  Duration: {fb.duration}s",
        "",
    ]
    for f in fb.findings:
        lines.append(f"  - {f}")
    return "\n".join(lines)


# ============================================================================
# Per-second deviation scoring — drives the CapCut-style timeline markers.
#
# For each second of a video, how far it diverges from what winning videos of
# the same archetype do at that point. The hook (first few seconds) is compared
# by ABSOLUTE second; the body by RELATIVE position (so a 20s and a 55s video
# are still comparable).
#
# This is a PREDICTED divergence-from-what-works signal, NOT measured audience
# retention (retention is creator-private — YouTube Analytics + OAuth only).
# ============================================================================

PS_HOOK_LEN = 5  # first N seconds compared by absolute position
PS_BODY_BINS = 10  # body compared by relative-position bin

_PS_W_FACE = 0.45
_PS_W_VIBE = 0.35
_PS_W_MOTION = 0.20


def _ps_aggregate(samples: list[tuple]) -> dict:
    """samples = list of (has_face, primary_vibe, motion) -> aggregate profile."""
    faces = [s[0] for s in samples if s[0] is not None]
    vibes = [s[1] for s in samples if s[1]]
    motions = [s[2] for s in samples if s[2] is not None]
    vc = Counter(vibes)
    total = sum(vc.values()) or 1
    return {
        "n": len(samples),
        "face_pct": (sum(1 for f in faces if f) / len(faces)) if faces else None,
        "vibe_dist": {k: v / total for k, v in vc.items()},
        "motion_mean": (sum(motions) / len(motions)) if motions else None,
        "motion_std": (pstdev(motions) if len(motions) > 1 else 0.0),
    }


def compute_per_second_benchmark(
    label_scheme: str = "views_per_sub_aged_v1",
    niche: str = "fitness",
    tier: Optional[str] = None,
) -> dict:
    """Per-archetype winner profile at each hook-second and body-position bin.

    ``tier`` restricts winners to that follower-count band; ``tier=None``
    pools across all tiers.
    """
    hook: dict = {}
    body: dict = {}

    with session_scope() as s:
        winners = s.execute(
            select(Video, VideoFeatures, Channel.subscriber_count)
            .join(
                VideoLabel,
                (VideoLabel.video_id == Video.id)
                & (VideoLabel.label_scheme == label_scheme),
            )
            .join(VideoFeatures, VideoFeatures.video_id == Video.id)
            .join(Channel, Channel.id == Video.channel_id)
            .where(Channel.niche == niche, VideoLabel.tercile == 2)
        ).all()

        for video, feat, sub_count in winners:
            if tier is not None and tier_for_count(sub_count) != tier:
                continue
            arch = classify_archetype(feat.transcript_word_count)
            tl = (
                s.execute(
                    select(VideoTimeline)
                    .where(VideoTimeline.video_id == video.id)
                    .order_by(VideoTimeline.second)
                )
                .scalars()
                .all()
            )
            if not tl:
                continue
            duration = len(tl)
            for r in tl:
                sample = (r.has_face, r.primary_vibe, r.motion)
                if r.second < PS_HOOK_LEN:
                    hook.setdefault(arch, {}).setdefault(r.second, []).append(sample)
                else:
                    rel = r.second / max(1, duration)
                    b = min(PS_BODY_BINS - 1, int(rel * PS_BODY_BINS))
                    body.setdefault(arch, {}).setdefault(b, []).append(sample)

    archetypes: dict = {}
    for arch in set(list(hook) + list(body)):
        archetypes[arch] = {
            "hook": {sec: _ps_aggregate(v) for sec, v in hook.get(arch, {}).items()},
            "body": {b: _ps_aggregate(v) for b, v in body.get(arch, {}).items()},
        }
    return {
        "label_scheme": label_scheme,
        "niche": niche,
        "tier": tier,
        "archetypes": archetypes,
    }


def _ps_reference(arch_bm: dict, second: int, duration: int) -> Optional[dict]:
    """Winner profile to compare a given second against."""
    if second < PS_HOOK_LEN and second in arch_bm["hook"]:
        return arch_bm["hook"][second]
    rel = second / max(1, duration)
    b = min(PS_BODY_BINS - 1, int(rel * PS_BODY_BINS))
    return arch_bm["body"].get(b)


def deviation_from_rows(
    arch: str, tl: list[VideoTimeline], benchmark: dict
) -> list[dict]:
    """Pure per-second deviation given an archetype, ordered timeline rows and a
    precomputed benchmark. No DB access — safe to call in a tight loop."""
    arch_bm = benchmark["archetypes"].get(arch)
    duration = len(tl)
    out: list[dict] = []

    for r in tl:
        ref = _ps_reference(arch_bm, r.second, duration) if arch_bm else None
        if not ref:
            out.append(
                {"second": r.second, "deviation": None, "reason": None, "parts": {}}
            )
            continue

        # face: weighted by how decisive winners are at this second
        dev_face = 0.0
        if ref["face_pct"] is not None and r.has_face is not None:
            consensus = abs(ref["face_pct"] - 0.5) * 2.0
            expected = 1 if ref["face_pct"] > 0.5 else 0
            dev_face = consensus * abs(int(r.has_face) - expected)

        # vibe: how rare this shot type is among winners RELATIVE to the most
        # common winning vibe at this point. Showing the top winning vibe -> 0;
        # showing a vibe far rarer than the top -> high. (Measuring against the
        # distribution, not against 100%, since winners spread across ~8 vibes.)
        dev_vibe = 0.0
        if r.primary_vibe and ref["vibe_dist"]:
            top_share = max(ref["vibe_dist"].values())
            your_share = ref["vibe_dist"].get(r.primary_vibe, 0.0)
            dev_vibe = min(1.0, max(0.0, (top_share - your_share) / max(top_share, 0.1)))

        # motion: clamped distance from the winner mean
        dev_motion = 0.0
        if ref["motion_mean"] is not None and r.motion is not None:
            sd = (ref["motion_std"] or 0.0) + 0.02
            dev_motion = min(1.0, abs(r.motion - ref["motion_mean"]) / (sd * 3.0))

        parts = {
            "face": _PS_W_FACE * dev_face,
            "shot": _PS_W_VIBE * dev_vibe,
            "energy": _PS_W_MOTION * dev_motion,
        }
        deviation = sum(parts.values())
        dom = max(parts, key=parts.get)
        reason = {
            "face": (
                "no one on screen — winning Shorts have a face here"
                if (ref["face_pct"] or 0) > 0.5
                else "a face is held on screen where winners have cut away"
            ),
            "shot": "the shot here is a style winning Shorts rarely use at this point",
            "energy": "the on-screen energy is unlike winning Shorts at this point",
        }[dom]

        out.append(
            {
                "second": r.second,
                "deviation": round(deviation, 3),
                # Only annotate genuine outlier seconds; the rest still carry a
                # continuous score for the timeline heatmap.
                "reason": reason if deviation > 0.40 else None,
                "parts": {k: round(v, 3) for k, v in parts.items()},
            }
        )
    return out


def summarize_deviation(dev: list[dict]) -> Optional[dict]:
    """Reduce a per-second deviation curve to tabular model features.

    Captures the shape a sequence model would otherwise read directly: overall
    divergence, the single worst moment and where it sits, and whether the
    video is front-loaded weak (bad hook) vs back-loaded weak (sags later).
    """
    vals = [(d["second"], d["deviation"]) for d in dev if d["deviation"] is not None]
    if not vals:
        return None
    n = len(vals)
    scores = [v for _s, v in vals]
    hook = [v for s, v in vals if s < PS_HOOK_LEN]
    body = [v for s, v in vals if s >= PS_HOOK_LEN]
    hook_mean = sum(hook) / len(hook) if hook else 0.0
    body_mean = sum(body) / len(body) if body else 0.0
    worst_second = max(vals, key=lambda sv: sv[1])[0]
    return {
        "dev_mean": sum(scores) / n,
        "dev_max": max(scores),
        "dev_worst_rel": worst_second / max(1, n),
        "dev_hook_mean": hook_mean,
        "dev_body_mean": body_mean,
        "dev_front_back": hook_mean - body_mean,
        "dev_flagged_frac": sum(1 for v in scores if v > 0.40) / n,
    }


def per_second_deviation(video_id: str, benchmark: Optional[dict] = None) -> list[dict]:
    """Per-second divergence of a video from its archetype's winner profile.

    Returns one dict per second: {second, deviation (0-1 or None), reason, parts}.
    deviation ~0 = on-pattern, ~1 = far off. reason names the dominant cause.
    This is what the CapCut-style timeline UI colours/marks each second with.
    """
    if benchmark is None:
        benchmark = compute_per_second_benchmark()

    with session_scope() as s:
        video = s.get(Video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} not found")
        feat = video.features
        arch = classify_archetype(feat.transcript_word_count if feat else None)
        tl = (
            s.execute(
                select(VideoTimeline)
                .where(VideoTimeline.video_id == video_id)
                .order_by(VideoTimeline.second)
            )
            .scalars()
            .all()
        )

    return deviation_from_rows(arch, tl, benchmark)
