"""Derived features computed at dataset-build time from already-stored data.

These don't need DB storage because they're cheap pure functions over rows
we already load for the existing features. Adding them in dataset.py
avoids another schema migration + backfill round.

Each helper takes the structured inputs (Video, VideoFeatures, list of
VideoTimeline rows, channel publish-time history) and returns a flat dict
of named feature -> numeric value.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import numpy as np


# ----------------------------------------------------------------------------
# Timeline-shape features (per-second VideoTimeline aggregations).
# ----------------------------------------------------------------------------

HOOK_SECONDS = 3
_STATIC_MOTION_THRESHOLD = 0.05  # below this = "no motion"


def _safe_float_list(values) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def _slope(values: list[float]) -> float:
    """OLS slope of a 1D series indexed by position. 0 if too short or flat."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(values):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx
    return float(num / den) if den > 0 else 0.0


def timeline_shape(tl_rows: list) -> dict:
    """Per-second-derived shape features. Empty dict if no timeline rows."""
    if not tl_rows:
        return {
            "tl_hook_motion_std": float("nan"),
            "tl_hook_brightness_var": float("nan"),
            "tl_motion_curve_slope": float("nan"),
            "tl_motion_peak_position": float("nan"),
            "tl_longest_static_stretch": float("nan"),
            "tl_cut_interval_std": float("nan"),
            "tl_cuts_in_first_half_ratio": float("nan"),
            "tl_face_consistency": float("nan"),
            "tl_vibe_transition_count": float("nan"),
        }
    rows = sorted(tl_rows, key=lambda r: r.second)
    duration = len(rows)
    motions = _safe_float_list(r.motion for r in rows)
    brights = _safe_float_list(r.brightness for r in rows)
    cuts = [r.second for r in rows if r.is_cut]
    has_face = [int(bool(r.has_face)) for r in rows if r.has_face is not None]
    vibes = [r.primary_vibe for r in rows]

    # Hook (first 3s) motion + brightness shape.
    hook_motions = motions[:HOOK_SECONDS]
    hook_brights = brights[:HOOK_SECONDS]
    hook_motion_std = float(np.std(hook_motions)) if len(hook_motions) >= 2 else 0.0
    hook_brightness_var = (
        float(np.var(hook_brights)) if len(hook_brights) >= 2 else 0.0
    )

    # Full-reel motion curve: slope + where the peak sits.
    motion_curve_slope = _slope(motions)
    if motions:
        peak_idx = max(range(len(motions)), key=lambda i: motions[i])
        motion_peak_position = peak_idx / max(1, duration - 1)
    else:
        motion_peak_position = 0.5

    # Longest static run (consecutive seconds with motion below threshold).
    run = 0
    longest_static = 0
    for v in motions:
        if v < _STATIC_MOTION_THRESHOLD:
            run += 1
            longest_static = max(longest_static, run)
        else:
            run = 0
    longest_static_stretch = float(longest_static)

    # Cut pacing consistency: std of intervals between consecutive cuts.
    if len(cuts) >= 2:
        intervals = [cuts[i + 1] - cuts[i] for i in range(len(cuts) - 1)]
        cut_interval_std = float(np.std(intervals))
    else:
        cut_interval_std = 0.0

    # Front-loaded edits: ratio of cuts in first half vs total.
    if cuts:
        first_half = sum(1 for c in cuts if c < duration / 2)
        cuts_first_half_ratio = first_half / len(cuts)
    else:
        cuts_first_half_ratio = 0.5

    # Face consistency: fraction of seconds whose face state matches the modal.
    if has_face:
        mode = 1 if sum(has_face) >= len(has_face) / 2 else 0
        face_consistency = sum(1 for f in has_face if f == mode) / len(has_face)
    else:
        face_consistency = float("nan")

    # Visual variability via vibe transitions.
    transitions = sum(
        1 for i in range(1, len(vibes)) if vibes[i] and vibes[i] != vibes[i - 1]
    )
    return {
        "tl_hook_motion_std": hook_motion_std,
        "tl_hook_brightness_var": hook_brightness_var,
        "tl_motion_curve_slope": motion_curve_slope,
        "tl_motion_peak_position": motion_peak_position,
        "tl_longest_static_stretch": longest_static_stretch,
        "tl_cut_interval_std": cut_interval_std,
        "tl_cuts_in_first_half_ratio": cuts_first_half_ratio,
        "tl_face_consistency": face_consistency,
        "tl_vibe_transition_count": float(transitions),
    }


def hook_clip_profile(tl_rows: list) -> tuple[Optional[np.ndarray], list[str]]:
    """Average per-second CLIP zero-shot scores across the first HOOK_SECONDS.

    Returns (vector, prompt_names). prompt_names is the sorted set of keys
    used so the caller can keep dataframe columns aligned. Vector is None
    if no hook rows have clip_scores.
    """
    rows = sorted(tl_rows, key=lambda r: r.second)[:HOOK_SECONDS]
    score_sums: dict[str, float] = {}
    n_scored = 0
    for r in rows:
        scores = r.clip_scores or {}
        if not scores:
            continue
        n_scored += 1
        for k, v in scores.items():
            try:
                score_sums[k] = score_sums.get(k, 0.0) + float(v)
            except (TypeError, ValueError):
                pass
    if not score_sums or n_scored == 0:
        return None, []
    prompts = sorted(score_sums.keys())
    vec = np.array([score_sums[k] / n_scored for k in prompts], dtype=float)
    return vec, prompts


def body_clip_profile(tl_rows: list) -> tuple[Optional[np.ndarray], list[str]]:
    """Same as hook_clip_profile but for seconds >= HOOK_SECONDS."""
    rows = sorted(tl_rows, key=lambda r: r.second)[HOOK_SECONDS:]
    score_sums: dict[str, float] = {}
    n_scored = 0
    for r in rows:
        scores = r.clip_scores or {}
        if not scores:
            continue
        n_scored += 1
        for k, v in scores.items():
            try:
                score_sums[k] = score_sums.get(k, 0.0) + float(v)
            except (TypeError, ValueError):
                pass
    if not score_sums or n_scored == 0:
        return None, []
    prompts = sorted(score_sums.keys())
    vec = np.array([score_sums[k] / n_scored for k in prompts], dtype=float)
    return vec, prompts


def cosine(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    if a is None or b is None or len(a) != len(b):
        return float("nan")
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return float("nan")
    return float(np.dot(a, b) / (na * nb))


# ----------------------------------------------------------------------------
# Text-derived features (caption, transcript, title beyond simple counts).
# ----------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+|www\.\S+|\b\w+\.(com|co|io|app|me|tv)\b", re.IGNORECASE)
_PROMO_RE = re.compile(
    r"\b(link in bio|dm me|use code|coupon|promo|discount|10% off|"
    r"sponsor(ed)?|paid partnership|swipe up|click below|join my|sign up)\b",
    re.IGNORECASE,
)
_IMPERATIVE_OPENERS = (
    "stop", "try", "do", "don't", "watch", "look", "listen", "see",
    "learn", "remember", "use", "follow", "tag", "save", "subscribe",
    "comment", "imagine", "consider", "stop scrolling", "wait",
)
_YOU_RE = re.compile(r"\byou\b|\byour\b|\byou'?re\b|\byou'?ve\b|\byourself\b", re.IGNORECASE)


def title_text_features(title: Optional[str]) -> dict:
    text = (title or "").strip()
    starts_imperative = 0
    if text:
        first_word = text.split()[0].lower().rstrip(",.?!:")
        starts_imperative = 1 if first_word in _IMPERATIVE_OPENERS else 0
    return {"title_starts_imperative": starts_imperative}


def description_text_features(description: Optional[str]) -> dict:
    text = (description or "")
    if not text.strip():
        return {
            "description_first_line_chars": 0,
            "description_word_count": 0,
            "description_link_count": 0,
            "description_has_promo": 0,
        }
    first_line = text.split("\n", 1)[0]
    return {
        "description_first_line_chars": len(first_line),
        "description_word_count": len(text.split()),
        "description_link_count": len(_URL_RE.findall(text)),
        "description_has_promo": 1 if _PROMO_RE.search(text) else 0,
    }


def transcript_text_features(transcript: Optional[str]) -> dict:
    text = (transcript or "")
    if not text.strip():
        return {
            "transcript_question_count": 0,
            "transcript_uses_you_count": 0,
        }
    return {
        "transcript_question_count": text.count("?"),
        "transcript_uses_you_count": len(_YOU_RE.findall(text)),
    }


def speech_pace_wpm(
    transcript_word_count: Optional[float],
    audio_voice_ratio: Optional[float],
    duration_seconds: Optional[float],
) -> float:
    """Words per minute over the spoken portion of the reel.

    Uses audio_voice_ratio (fraction of time with voice) and total duration
    to estimate the speaking time. Returns 0 if the reel has no speech.
    """
    if not transcript_word_count or not duration_seconds:
        return 0.0
    voice_ratio = audio_voice_ratio if audio_voice_ratio is not None else 1.0
    speaking_seconds = max(0.0, float(duration_seconds) * float(voice_ratio))
    if speaking_seconds < 1.0:
        return 0.0
    return float(transcript_word_count) / speaking_seconds * 60.0


def audio_dynamic_range(
    loudness_max: Optional[float], loudness_mean: Optional[float]
) -> float:
    if loudness_max is None or loudness_mean is None:
        return float("nan")
    return float(loudness_max) - float(loudness_mean)


def music_artist_is_known(music_info: Optional[dict]) -> int:
    """1 if the artist_name is a real-looking artist (not 'Original audio')."""
    if not music_info:
        return 0
    name = (music_info.get("artist_name") or "").strip().lower()
    if not name or name in ("original audio", ""):
        return 0
    # Heuristic: an Instagram handle (no spaces, starts with letter) is
    # often the creator's own; a "real artist" tends to have spaces or a
    # well-known label. We mark "any non-empty non-default name" as known
    # since even creator handles uploading their own music count as named.
    return 1


# ----------------------------------------------------------------------------
# Channel temporal features (creator-level history at publish time).
# ----------------------------------------------------------------------------


def channel_temporal_features(
    channel_publish_times: list[datetime],
    current_published_at: datetime,
) -> dict:
    """Given a sorted-by-asc list of the creator's publish times (excluding
    the current video) and the current video's publish time, compute simple
    cadence features.
    """
    earlier = [t for t in channel_publish_times if t < current_published_at]
    if not earlier:
        return {
            "creator_days_since_last_post": float("nan"),
            "creator_posting_rate_30d": 0.0,
            "creator_total_reels_at_publish": 0.0,
            "creator_is_first_10_reels": 1.0,
        }
    last_t = max(earlier)
    days_since = (current_published_at - last_t).total_seconds() / 86400.0
    window_start = current_published_at - timedelta(days=30)
    in_window = sum(1 for t in earlier if t >= window_start)
    return {
        "creator_days_since_last_post": float(days_since),
        "creator_posting_rate_30d": float(in_window) / 30.0,
        "creator_total_reels_at_publish": float(len(earlier)),
        "creator_is_first_10_reels": 1.0 if len(earlier) < 10 else 0.0,
    }
