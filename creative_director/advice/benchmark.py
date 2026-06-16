"""Compute the 'what high-performers do' benchmark profile.

The benchmark is the comparison target for per-video breakdowns. A critical
lesson from the v0: high performers are NOT one archetype. They split into
at least two very different formats — silent/music exercise demos and
voiceover/talking-head explainers — that win in completely different ways.
A benchmark therefore has to be computed *per archetype* and a video compared
only against winners of its own archetype, or the advice is nonsense
("stop talking, winners are silent"). This is the retrieval/like-to-like
principle; archetype-splitting is its simplest form.

IMPORTANT: still correlational. ``causal`` tags whether a feature is plausibly
a lever a creator can pull, vs a proxy for something else.
"""
from __future__ import annotations

from typing import Optional

from creative_director.advice.tier import tier_for_count
from creative_director.model.dataset import build_dataframe


ARCHETYPE_TALKING = "talking"
ARCHETYPE_DEMO = "demo"

# Transcript word count above this => voiceover/talking-head; else silent demo.
# The two clusters sit far apart (demo median ~0 words, talking median ~146),
# so the exact threshold barely matters.
_TALKING_WORD_THRESHOLD = 30


REPORTABLE: dict[str, dict] = {
    "duration_seconds": {
        "label": "Video length",
        "unit": "s",
        "source": "video",
        "confidence": "strong",
        "causal": "plausible",
    },
    "hashtag_count": {
        "label": "Hashtags in description",
        "unit": "",
        "source": "features",
        "confidence": "strong",
        "causal": "likely-proxy",
    },
    "transcript_word_count": {
        "label": "Spoken words",
        "unit": "words",
        "source": "features",
        "confidence": "moderate",
        "causal": "plausible",
    },
    "title_emoji_count": {
        "label": "Emoji in title",
        "unit": "",
        "source": "features",
        "confidence": "moderate",
        "causal": "plausible",
    },
    "title_char_count": {
        "label": "Title length",
        "unit": "chars",
        "source": "features",
        "confidence": "moderate",
        "causal": "plausible",
    },
}


def classify_archetype(transcript_word_count: Optional[float]) -> str:
    """Split a video by format: voiceover/talking-head vs silent/music demo."""
    if transcript_word_count is None:
        return ARCHETYPE_DEMO
    return (
        ARCHETYPE_TALKING
        if transcript_word_count > _TALKING_WORD_THRESHOLD
        else ARCHETYPE_DEMO
    )


# Below this fraction of seconds-with-a-face, a "talking" video is treated as
# VOICEOVER-LED (narration over animation/b-roll, no presenter) rather than
# face-to-camera. Median face fraction for true talking reels is ~0.6; the
# voiceover-over-animation failure case sits well under 0.3. Face-timing advice
# and dead-air trims are unsafe for this subformat: there is no face to deploy,
# and its "no face + low motion" seconds usually CARRY the narration.
VOICEOVER_FACE_FRAC = 0.30


def is_voiceover_led(
    archetype: str, face_frac: Optional[float], has_presenter: Optional[bool] = None
) -> bool:
    """True when a transcript-heavy video has no presenter on screen (narration
    over animation / b-roll), so it should read and be benchmarked as voiceover-
    led, not talking-to-camera.

    ``has_presenter`` is the VLM override: a confident False on a word-heavy reel
    makes it voiceover-led regardless of the scalar face fraction (which a reel
    cut between a few face frames and lots of b-roll can push above the
    threshold). This is the broad re-cohort lever — it reframes the read and the
    cohort, not just face advice.
    """
    if archetype != ARCHETYPE_TALKING:
        return False
    if has_presenter is False:
        return True
    return face_frac is not None and face_frac < VOICEOVER_FACE_FRAC


# Below this overall face fraction a DEMO reel is b-roll/product format with no
# presenter at all (food plating, scenery, outfit close-ups shot from the neck
# down). Stricter than the talking threshold: a demo with occasional faces can
# still act on face-timing advice; one with none cannot.
NO_PRESENTER_FACE_FRAC = 0.10


def vlm_has_presenter(video_features) -> Optional[bool]:
    """The full-video VLM's read on whether a human presenter is on camera —
    a more reliable presenter signal than the scalar face fraction (which a
    food/product/animation reel can fool). Returns True / False / None
    (None = no VLM run, or the VLM itself returned no determination).

    Confidence is intentionally NOT filtered here: only a False is ever acted on
    (it suppresses face advice), and the harm is asymmetric — wrongly suppressing
    one suggestion on a presenter reel is far cheaper than telling a faceless
    food/product reel to 'show a face.' So we trust a False even at low
    confidence; a True is a no-op for the gate anyway."""
    vp = getattr(video_features, "vlm_perception", None) if video_features else None
    if not isinstance(vp, dict):
        return None
    hp = vp.get("has_presenter")
    return hp if isinstance(hp, bool) else None


def face_advice_applies(
    archetype: str, face_frac: Optional[float], has_presenter: Optional[bool] = None
) -> bool:
    """Should we give 'get a face on screen' style advice at all?

    False for voiceover-led talking reels (narration over animation/b-roll)
    and for demos with essentially no face anywhere — both are formats where
    'show a face sooner' prescribes a different format, not a tweak.

    ``has_presenter`` is the VLM override: a CONFIDENT False (no human on camera)
    suppresses face advice regardless of the scalar face_frac — this is the gate
    that stops faceless food/product reels being told to "show a face." A True or
    None defers to the scalar logic (conservative: the VLM only vetoes, it never
    manufactures face advice the scalar wouldn't already give).
    """
    if has_presenter is False:
        return False
    if is_voiceover_led(archetype, face_frac):
        return False
    if face_frac is not None and face_frac < NO_PRESENTER_FACE_FRAC:
        return False
    return True


def _profile_for(high_df, low_df) -> dict:
    profile: dict[str, dict] = {}
    for feat in REPORTABLE:
        hv = high_df[feat].dropna()
        lv = low_df[feat].dropna()
        if hv.empty:
            continue
        profile[feat] = {
            "high_median": float(hv.median()),
            "high_mean": float(hv.mean()),
            "low_median": float(lv.median()) if not lv.empty else None,
            "n_high": int(hv.shape[0]),
        }
    return profile


def compute_benchmark(
    label_scheme: str = "views_per_sub_aged_v1",
    niche: str = "fitness",
    tier: Optional[str] = None,
) -> dict:
    """Return high-vs-low profiles, split by content archetype.

    ``tier`` (small | mid | large) filters the cohort to creators in that
    follower-count band before computing the winner profile, so a small-tier
    creator is benchmarked against small-tier winners. ``tier=None`` pools
    across all tiers (the historical behavior and the sparse-bucket fallback).
    """
    df = build_dataframe(label_scheme=label_scheme, niche=niche).copy()
    df["archetype"] = df["transcript_word_count"].apply(classify_archetype)

    if tier is not None:
        # Look up each row's channel tier via the loaded Channel column on the df.
        # build_dataframe attaches the channel title only; subscriber_count must
        # be fetched separately for the tier filter.
        from sqlalchemy import select

        from creative_director.storage.db import session_scope
        from creative_director.storage.models import Channel, Video

        video_ids = df["video_id"].tolist()
        with session_scope() as s:
            rows = s.execute(
                select(Video.id, Channel.subscriber_count)
                .join(Channel, Video.channel_id == Channel.id)
                .where(Video.id.in_(video_ids))
            ).all()
        sub_by_id = {vid: sub for vid, sub in rows}
        df["tier"] = df["video_id"].map(
            lambda v: tier_for_count(sub_by_id.get(v))
        )
        df = df[df["tier"] == tier]

    high = df[df["tercile"] == 2]
    low = df[df["tercile"] == 0]

    archetypes: dict[str, dict] = {}
    for arch in (ARCHETYPE_TALKING, ARCHETYPE_DEMO):
        h = high[high["archetype"] == arch]
        lo = low[low["archetype"] == arch]
        archetypes[arch] = {
            "n_high": int(len(h)),
            "n_low": int(len(lo)),
            "profile": _profile_for(h, lo),
        }

    return {
        "label_scheme": label_scheme,
        "niche": niche,
        "tier": tier,
        "n_total": int(len(df)),
        "archetypes": archetypes,
    }
