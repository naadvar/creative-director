"""Per-feature 'how easily can a creator act on this' weights.

This is product judgment, NOT a learned value. It encodes the cost-of-action
the creator would have to incur to move a feature toward winner values:

- HIGH (0.9): change in the editor or copy. No reshoot, no new gear. The
    creator can act on it in the next 10 minutes. Examples: hashtags, title
    text, thumbnail brightness, video length trim.
- MEDIUM (0.6): requires a re-shoot, a re-cut, or a deliberate behavior shift
    on the next video. The creator can act on it within their next upload.
    Examples: hook face presence, cut pacing, transcript length.
- LOW (0.3): structural to the format, gear, or the creator themselves.
    Examples: voice-vs-music ratio (changes the entire video type), face
    count on a thumbnail (different shoot), audio tempo BPM (music choice
    that structures the whole video).

Used to compute Finding.rank_score = gap_score x fixability_weight x
not_already_improving. The 'gap' picks which features differ most from
winners; fixability picks which differences are worth telling the creator
about, because flagging "your face_count is wrong" when face_count is
structural is generic advice that wastes the user's attention budget.

If a feature is not in the map it defaults to MEDIUM (0.6) — safer to
under-promote than over-promote a finding we haven't classified.
"""
from __future__ import annotations

HIGH = 0.9
MEDIUM = 0.6
LOW = 0.3

_DEFAULT = MEDIUM


# Keys match the VideoFeatures column names + derived/timeline column names
# used in benchmark.py REPORTABLE and timeline_benchmark.py findings.
FIXABILITY: dict[str, float] = {
    # --- Title + description (text edit, instant) ---
    "title_char_count": HIGH,
    "title_word_count": HIGH,
    "title_emoji_count": HIGH,
    "title_question_mark": HIGH,
    "title_has_number": HIGH,
    "title_all_caps_ratio": HIGH,
    "description_char_count": HIGH,
    "hashtag_count": HIGH,

    # --- Video length (trim in edit) ---
    "duration_seconds": HIGH,

    # --- Thumbnail (re-edit/re-pick) ---
    "thumb_brightness": HIGH,
    "thumb_saturation": HIGH,
    "thumb_contrast": HIGH,
    "thumb_text_present": HIGH,
    "thumb_text_char_count": HIGH,
    # Face on thumbnail = a different shoot or a different frame pick;
    # the creator CAN re-pick from existing footage but often can't.
    "thumb_face_count": MEDIUM,
    "thumb_dominant_face_area": MEDIUM,

    # --- Hook (first 3 seconds — re-record or re-cut) ---
    "first3s_face_present": MEDIUM,
    "first3s_text_present": HIGH,  # text overlay can be added in editor
    "first3s_motion_intensity": MEDIUM,
    "first3s_cut_count": MEDIUM,

    # --- Pacing / shots (re-cut) ---
    "total_cut_count": MEDIUM,
    "avg_shot_length": MEDIUM,

    # --- Audio ---
    # Loudness normalization is one click in any editor.
    "audio_loudness_mean": HIGH,
    "audio_loudness_max": HIGH,
    # Tempo and voice-ratio are structural to the format choice — changing
    # them changes what KIND of video this is, not how to edit this one.
    "audio_tempo_bpm": LOW,
    "audio_voice_ratio": LOW,

    # --- Transcript (re-shoot with different script) ---
    "transcript_word_count": MEDIUM,

    # --- Timeline aggregates (re-cut or re-record) ---
    "tl_hook_face_frac": MEDIUM,
    "tl_first_cut_second": MEDIUM,
    "tl_cuts_per_10s": MEDIUM,
    "tl_cut_count": MEDIUM,
    "tl_distinct_vibes": MEDIUM,
}


def fixability_weight(feature: str) -> float:
    """Look up a feature's fixability weight; MEDIUM (0.6) if unknown."""
    return FIXABILITY.get(feature, _DEFAULT)


def fixability_label(weight: float) -> str:
    """Human-readable bucket label for a weight value."""
    if weight >= HIGH:
        return "high"
    if weight <= LOW:
        return "low"
    return "medium"
