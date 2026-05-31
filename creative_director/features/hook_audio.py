"""Hook-audio fingerprint: what the FIRST 1-2s of a reel sounds like.

Audio is a primary driver of swipe-or-stay in the 1-2s decision window
that IG/TikTok feeds reward. Our existing audio features summarise the
whole reel (loudness_mean, tempo_bpm, voice_ratio), which loses the
opening punch -- a reel that ramps in loud is structurally different
from one that fades up softly, even if their full-reel means match.

We extract three opening-window descriptors from the archived mp4:

  - hook_audio_peak_loudness   : max RMS in the first 2s (the "punch")
  - hook_audio_mean_loudness   : mean RMS in the first 2s
  - hook_audio_attack_rate     : difference between first 0.2s and the
                                  next 0.8-1.8s window (positive = builds
                                  in fast; negative = starts hot then sags)
  - hook_audio_is_voice        : binary -- did Whisper transcribe anything
                                  in seconds 0-1? (uses our existing
                                  transcript_first_3s field, no re-decode)

Reads the mp4 with librosa at 22050 Hz mono, restricted to a 2s slice so
even a 50s reel processes in <1s.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np


HOOK_WINDOW_SECONDS = 2.0
SAMPLE_RATE = 22050


def _safe_audio_load(path: Path) -> Optional[np.ndarray]:
    """Load just the first 2s of audio from an mp4. Returns mono float32 at 22050 Hz."""
    import librosa  # heavy import, kept local

    try:
        y, _sr = librosa.load(
            str(path),
            sr=SAMPLE_RATE,
            mono=True,
            offset=0.0,
            duration=HOOK_WINDOW_SECONDS,
        )
    except Exception:
        return None
    if y is None or len(y) == 0:
        return None
    return y


def _rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def extract_hook_audio(
    mp4_path: Path, hook_transcript_text: Optional[str] = None
) -> Optional[dict]:
    """Read the first 2s of audio and return the hook-audio feature dict.

    ``hook_transcript_text`` is the stored transcript_first_3s -- we use it
    to derive ``hook_audio_is_voice`` without redoing Whisper.
    """
    y = _safe_audio_load(mp4_path)
    if y is None:
        return None

    # Peak + mean loudness over the full 2s window.
    peak = float(np.max(np.abs(y)))
    mean_rms = _rms(y)

    # Attack rate: compare the first 200ms to the 800-1800ms region.
    # A positive attack means the reel BUILDS (e.g., quiet text card -> drop).
    # A negative attack means it FRONT-LOADS (loud hook then sustained body).
    open_window = y[: int(0.2 * SAMPLE_RATE)]
    later_window = y[int(0.8 * SAMPLE_RATE) : int(1.8 * SAMPLE_RATE)]
    open_rms = _rms(open_window)
    later_rms = _rms(later_window)
    # Normalise by mean RMS so the scale is relative, not absolute.
    denom = mean_rms + 1e-6
    attack_rate = float((later_rms - open_rms) / denom)

    is_voice = 1 if (hook_transcript_text or "").strip() else 0

    return {
        "hook_audio_peak_loudness": peak,
        "hook_audio_mean_loudness": mean_rms,
        "hook_audio_attack_rate": attack_rate,
        "hook_audio_is_voice": is_voice,
    }
