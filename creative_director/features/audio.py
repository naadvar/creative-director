"""Audio feature extraction: Whisper transcript, loudness, tempo, voice ratio."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger

from creative_director.config import settings


_whisper_model = None


def _load_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    from faster_whisper import WhisperModel
    import torch

    if settings.force_cpu:
        device = "cpu"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    _whisper_model = WhisperModel(
        settings.whisper_model,
        device=device,
        compute_type=compute_type,
        cpu_threads=settings.cpu_threads,
    )
    return _whisper_model


def extract_transcript(path: Path) -> dict:
    """Transcript text, word count, and first-3-seconds slice."""
    if not settings.enable_audio_transcript:
        return {
            "transcript": None,
            "transcript_word_count": None,
            "transcript_first_3s": None,
        }
    try:
        model = _load_whisper()
        segments, _info = model.transcribe(str(path), beam_size=1, vad_filter=True)
        full_parts: list[str] = []
        first_3_parts: list[str] = []
        for seg in segments:
            full_parts.append(seg.text.strip())
            if seg.start < 3.0:
                first_3_parts.append(seg.text.strip())
        transcript = " ".join(full_parts).strip()
        first_3 = " ".join(first_3_parts).strip()
        return {
            "transcript": transcript or None,
            "transcript_word_count": len(transcript.split()) if transcript else 0,
            "transcript_first_3s": first_3 or None,
        }
    except Exception as e:
        logger.warning(f"Whisper transcription failed: {e}")
        return {
            "transcript": None,
            "transcript_word_count": None,
            "transcript_first_3s": None,
        }


def extract_audio_stats(path: Path) -> dict:
    """RMS loudness (dB), tempo (BPM), harmonic/total ratio as a voice-presence proxy."""
    try:
        import librosa

        y, sr = librosa.load(str(path), sr=22050, mono=True)
        if y.size == 0:
            return {}

        rms = librosa.feature.rms(y=y)[0]
        rms_db = 20 * np.log10(rms + 1e-8)

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo_val = float(tempo) if np.isscalar(tempo) else float(np.asarray(tempo).flat[0])

        y_h, _y_p = librosa.effects.hpss(y)
        voice_ratio = float(
            np.sum(np.abs(y_h)) / (np.sum(np.abs(y)) + 1e-8)
        )

        return {
            "audio_loudness_mean": float(rms_db.mean()),
            "audio_loudness_max": float(rms_db.max()),
            "audio_tempo_bpm": tempo_val,
            "audio_voice_ratio": voice_ratio,
        }
    except Exception as e:
        logger.warning(f"Audio stats extraction failed: {e}")
        return {}


def extract_audio_features(path: Path) -> dict:
    out: dict = {}
    out.update(extract_audio_stats(path))
    out.update(extract_transcript(path))
    return out
