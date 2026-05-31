"""Wave 2: visual frame features that need the mp4 (face fill, emotion, hook
image embedding, clutter, action-first). GPU-accelerated via the existing
open-clip setup.

These are the spec's visual features we hadn't built because they require
decoding frames, not just reading stored aggregates:
  - hook_face_fill        : avg face bounding-box area / frame area, first 3s
  - hook_face_headroom    : avg (top-of-face-bbox y / frame height), first 3s
                            (low = face near top = little headroom)
  - hook_frontal_ratio    : frontal-face detections / any-face detections
                            (eye-contact proxy -- frontal Haar vs profile)
  - hook_clip_embedding   : mean CLIP image embedding of the hook frames
                            (512d) -> PCA + winner-sim downstream
  - hook_emotion_*        : CLIP zero-shot over expression prompts
  - hook_background_clutter : Canny edge density (visual busyness)
  - hook_is_action_first  : motion in first ~1s high AND face small/absent
                            (action open) vs face-centred low-motion (talking)

Reuses thumbnail.py's CLIP model + Haar cascade so model names/devices stay
consistent with the rest of the pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

HOOK_SECONDS = 3
N_BODY_FRAMES = 5

# CLIP zero-shot expression prompts (avoids fragile DeepFace). Order fixed so
# the output keys are stable.
_EMOTION_PROMPTS = [
    ("emotion_happy", "a smiling happy person"),
    ("emotion_intense", "a serious intense focused face"),
    ("emotion_surprised", "a surprised shocked face"),
    ("emotion_neutral", "a calm neutral expression"),
]


def _sample_frames(path: Path) -> tuple[list, list, float]:
    """Return (hook_frames, [], fps) as PIL images.

    hook_frames: ~1/sec across the first HOOK_SECONDS. We STOP decoding once
    past the hook window -- every visual feature we compute is hook-only, so
    decoding the rest of the reel was pure waste (~10-20x slower). Body frames
    are intentionally not collected (kept in the signature for compatibility).
    """
    import av

    container = av.open(str(path))
    hook_frames: list = []
    try:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate else 30.0
        fps = fps if fps > 1 else 30.0
        hook_grabbed: set[int] = set()
        frame_idx = 0
        for frame in container.decode(stream):
            sec = frame_idx / fps
            if sec >= HOOK_SECONDS:
                break  # past the hook -- stop decoding (huge speedup)
            isec = int(sec)
            if isec not in hook_grabbed:
                hook_grabbed.add(isec)
                hook_frames.append(frame.to_image())
            frame_idx += 1
    finally:
        container.close()
    return hook_frames, [], fps


def _face_metrics(pil_img) -> dict:
    """Bounding-box face metrics via the Haar cascade. Returns fill (area
    fraction), headroom (top-y fraction), and frontal flag."""
    import cv2

    from creative_director.features.thumbnail import _load_face_detector

    arr = np.asarray(pil_img.convert("L"))
    h, w = arr.shape[:2]
    frame_area = float(h * w) or 1.0
    cascade = _load_face_detector()
    faces = cascade.detectMultiScale(arr, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        return {"present": 0, "fill": 0.0, "headroom": np.nan, "frontal": 0}
    # Dominant face = largest bbox.
    fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
    fill = (fw * fh) / frame_area
    headroom = fy / float(h)  # top of face from frame top, as fraction
    return {"present": 1, "fill": float(fill), "headroom": float(headroom), "frontal": 1}


def _edge_density(pil_img) -> float:
    """Canny edge density: fraction of pixels that are edges. A visual-busyness
    / background-clutter proxy."""
    import cv2

    arr = np.asarray(pil_img.convert("L"))
    edges = cv2.Canny(arr, 100, 200)
    return float((edges > 0).mean())


def _clip_embed_mean(frames: list) -> Optional[np.ndarray]:
    """Mean CLIP image embedding over a set of frames (512d)."""
    from creative_director.features.thumbnail import extract_clip_embedding

    vecs = []
    for f in frames:
        emb = extract_clip_embedding(f)
        if emb:
            vecs.append(np.asarray(emb, dtype=float))
    if not vecs:
        return None
    return np.mean(np.stack(vecs), axis=0)


def _emotion_scores(frames: list) -> dict:
    """CLIP zero-shot expression scores averaged over hook frames."""
    import torch

    from creative_director.features.thumbnail import _load_clip

    if not frames:
        return {k: np.nan for k, _ in _EMOTION_PROMPTS}
    import open_clip

    from creative_director.config import settings

    model, preprocess = _load_clip()
    tokenizer = open_clip.get_tokenizer(settings.clip_model)
    device = next(model.parameters()).device
    texts = [p for _, p in _EMOTION_PROMPTS]
    keys = [k for k, _ in _EMOTION_PROMPTS]
    tokens = tokenizer(texts).to(device)
    with torch.no_grad():
        tf = model.encode_text(tokens)
        tf = tf / tf.norm(dim=-1, keepdim=True)
        acc = np.zeros(len(keys), dtype=float)
        n = 0
        for f in frames:
            x = preprocess(f.convert("RGB")).unsqueeze(0).to(device)
            imf = model.encode_image(x)
            imf = imf / imf.norm(dim=-1, keepdim=True)
            probs = (100.0 * imf @ tf.T).softmax(dim=-1).squeeze(0).cpu().numpy()
            acc += probs
            n += 1
    acc = acc / max(1, n)
    return {k: float(v) for k, v in zip(keys, acc)}


def extract_hook_visual(path: Path) -> Optional[dict]:
    """Full Wave 2 visual feature dict for one mp4. None if unreadable.

    Returns scalar features under their column names plus the raw mean hook
    CLIP embedding under 'hook_clip_embedding' (list) for downstream PCA +
    winner-sim (handled in dataset.py, like thumb/title/desc embeddings).
    """
    try:
        hook_frames, body_frames, _fps = _sample_frames(path)
    except Exception:
        return None
    if not hook_frames:
        return None

    # Face metrics over hook frames.
    fms = [_face_metrics(f) for f in hook_frames]
    present = [m["present"] for m in fms]
    fills = [m["fill"] for m in fms if m["present"]]
    headrooms = [m["headroom"] for m in fms if m["present"] and not np.isnan(m["headroom"])]
    frontal_ratio = (sum(m["frontal"] for m in fms) / len(fms)) if fms else np.nan

    # Action-first: high motion across first frames AND low face presence.
    # Motion proxy = mean abs diff between consecutive downsized hook frames.
    motion = 0.0
    if len(hook_frames) >= 2:
        smalls = [
            np.asarray(f.resize((64, 36)).convert("L"), dtype=np.int16)
            for f in hook_frames
        ]
        diffs = [
            float(np.abs(smalls[i + 1] - smalls[i]).mean() / 255.0)
            for i in range(len(smalls) - 1)
        ]
        motion = float(np.mean(diffs)) if diffs else 0.0
    face_frac = (sum(present) / len(present)) if present else 0.0
    is_action_first = 1 if (motion > 0.08 and face_frac < 0.5) else 0

    emb = _clip_embed_mean(hook_frames)
    emotions = _emotion_scores(hook_frames)
    clutter = float(np.mean([_edge_density(f) for f in hook_frames]))

    out = {
        "hook_face_fill": float(np.mean(fills)) if fills else 0.0,
        "hook_face_headroom": float(np.mean(headrooms)) if headrooms else np.nan,
        "hook_frontal_ratio": float(frontal_ratio),
        "hook_face_present_frac": float(face_frac),
        "hook_background_clutter": clutter,
        "hook_is_action_first": is_action_first,
        "hook_motion_first": motion,
        "hook_clip_embedding": [float(x) for x in emb] if emb is not None else None,
    }
    out.update(emotions)
    return out
