"""Per-second video timeline extraction (Phase 2 — frame-level analysis).

Decodes a video with PyAV, samples ~1 frame/second, and for each second
records:
  - CLIP zero-shot vibe (which niche prompt the frame matches best)
  - motion intensity, brightness, face presence
  - whether a scene cut happened in that second
  - whether an audio beat landed in that second

This per-second representation is what makes "your hook at 0-3s is the
problem" advice possible, versus only video-level aggregates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger

from creative_director.advice.clip_prompts import get_prompts
from creative_director.config import settings


_clip_tokenizer = None
# niche -> (keys, text_features tensor)
_text_features_cache: dict = {}


def detect_cut_seconds(path: Path, threshold: float = 27.0) -> set[int]:
    """Return the set of integer seconds where a hard scene cut occurs.

    Uses PySceneDetect's content-aware ContentDetector (HSV content delta) —
    far more reliable than a raw frame-diff threshold, which misses cuts
    between visually similar shots.
    """
    try:
        from scenedetect import ContentDetector, detect

        scenes = detect(str(path), ContentDetector(threshold=threshold))
        # Each scene boundary after the first is a cut point.
        return {int(start.get_seconds()) for start, _end in scenes[1:]}
    except Exception as e:
        logger.warning(f"scene detection failed for {path}: {e}")
        return set()


def _load_clip_bits():
    """Reuse thumbnail.py's CLIP model + preprocess; add the text tokenizer."""
    global _clip_tokenizer
    from creative_director.features.thumbnail import _load_clip

    model, preprocess = _load_clip()
    if _clip_tokenizer is None:
        import open_clip

        _clip_tokenizer = open_clip.get_tokenizer(settings.clip_model)
    return model, preprocess, _clip_tokenizer


def _encode_prompts(niche: str):
    if niche in _text_features_cache:
        return _text_features_cache[niche]
    import torch

    model, _, tokenizer = _load_clip_bits()
    keys, texts = zip(*get_prompts(niche))
    device = next(model.parameters()).device
    tokens = tokenizer(list(texts)).to(device)
    with torch.no_grad():
        tf = model.encode_text(tokens)
        tf = tf / tf.norm(dim=-1, keepdim=True)
    _text_features_cache[niche] = (list(keys), tf)
    return list(keys), tf


def _clip_scores(pil_img, niche: str) -> dict:
    """Zero-shot probabilities over the niche prompts for one frame."""
    import torch

    model, preprocess, _ = _load_clip_bits()
    keys, text_features = _encode_prompts(niche)
    device = next(model.parameters()).device
    x = preprocess(pil_img.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        img_f = model.encode_image(x)
        img_f = img_f / img_f.norm(dim=-1, keepdim=True)
        probs = (100.0 * img_f @ text_features.T).softmax(dim=-1)
    return {k: round(float(p), 4) for k, p in zip(keys, probs.squeeze(0).cpu().tolist())}


def _detect_beats(path: Path) -> list[float]:
    """Audio onset timestamps (seconds) via librosa."""
    try:
        import librosa

        y, sr = librosa.load(str(path), sr=22050, mono=True)
        if y.size == 0:
            return []
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onsets = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sr, units="time"
        )
        return [float(t) for t in onsets]
    except Exception as e:
        logger.warning(f"beat detection failed: {e}")
        return []


def extract_timeline(path: Path, niche: str = "fitness") -> list[dict]:
    """Return a list of per-second dicts for the video at ``path``."""
    import av
    from PIL import Image

    from creative_director.features.thumbnail import extract_face_features

    beat_times = _detect_beats(path)
    cut_seconds = detect_cut_seconds(path)

    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate else 30.0
        fps = fps if fps > 1 else 30.0

        motion_every = max(1, int(round(fps / 6)))  # ~6 motion samples/sec
        clip_every = max(1, int(round(fps)))  # ~1 CLIP sample/sec

        # per-second accumulators
        sec_data: dict[int, dict] = {}
        prev_small: Optional[np.ndarray] = None
        frame_idx = 0
        last_sec = 0

        for frame in container.decode(stream):
            sec = int(frame_idx / fps)
            last_sec = sec
            row = sec_data.setdefault(sec, {})

            if frame_idx % motion_every == 0:
                img = frame.to_image()
                small = np.asarray(
                    img.resize((64, 36)).convert("L"), dtype=np.int16
                )
                if prev_small is not None:
                    diff = float(np.abs(small - prev_small).mean() / 255.0)
                    row.setdefault("motion_sum", 0.0)
                    row["motion_sum"] += diff
                    row["motion_n"] = row.get("motion_n", 0) + 1
                prev_small = small

            if frame_idx % clip_every == 0 and "clip" not in row:
                pil = frame.to_image()
                row["clip"] = _clip_scores(pil, niche)
                row["brightness"] = float(
                    np.asarray(pil.convert("L")).mean() / 255.0
                )
                try:
                    row["has_face"] = bool(
                        (extract_face_features(pil) or {}).get("face_count")
                    )
                except Exception:
                    row["has_face"] = None

            frame_idx += 1
    finally:
        container.close()

    out: list[dict] = []
    for sec in range(last_sec + 1):
        row = sec_data.get(sec, {})
        clip = row.get("clip")
        motion = (
            row["motion_sum"] / row["motion_n"]
            if row.get("motion_n")
            else None
        )
        out.append(
            {
                "second": sec,
                "clip_scores": clip,
                "primary_vibe": (max(clip, key=clip.get) if clip else None),
                "motion": motion,
                "brightness": row.get("brightness"),
                "has_face": row.get("has_face"),
                "is_cut": sec in cut_seconds,
                "on_beat": any(sec <= b < sec + 1 for b in beat_times),
            }
        )
    return out
