"""Thumbnail feature extraction: faces, OCR text, color stats, CLIP embedding.

All extractors accept a PIL Image so they can be reused on video frames.
``extract_thumbnail_features`` is the top-level entry point.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from loguru import logger

from creative_director.config import settings


_clip_model = None
_clip_preprocess = None
_face_cascade = None
_tesseract_configured = False


def _configure_tesseract() -> None:
    global _tesseract_configured
    if _tesseract_configured:
        return
    import pytesseract

    if settings.tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_path
    elif shutil.which("tesseract") is None:
        # Common Windows install location
        win_default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if win_default.exists():
            pytesseract.pytesseract.tesseract_cmd = str(win_default)
    _tesseract_configured = True


def _load_clip():
    global _clip_model, _clip_preprocess
    if _clip_model is not None:
        return _clip_model, _clip_preprocess
    import open_clip
    import torch

    device = "cpu" if settings.force_cpu else ("cuda" if torch.cuda.is_available() else "cpu")
    _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
        settings.clip_model, pretrained=settings.clip_pretrained, device=device
    )
    _clip_model.eval()
    return _clip_model, _clip_preprocess


def _load_face_detector():
    """Lazy-loaded OpenCV Haar cascade for face detection.

    Switched from mediapipe on 2026-05-15: mediapipe's Python 3.12 wheels
    dropped the `mp.solutions` namespace in favor of `mediapipe.tasks`,
    which needs separately-downloaded model files. OpenCV's built-in
    cascade ships with the wheel and is accurate enough for thumbnail
    analysis (faces tend to be large, frontal, and deliberate).
    """
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade
    import cv2

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    _face_cascade = cv2.CascadeClassifier(cascade_path)
    if _face_cascade.empty():
        raise RuntimeError(f"Failed to load Haar cascade from {cascade_path}")
    return _face_cascade


def extract_face_features(image: Image.Image) -> dict:
    if not settings.enable_face_detection:
        return {"face_count": None, "dominant_face_area": None}
    try:
        import cv2

        cascade = _load_face_detector()
        rgb = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape
        min_dim = max(8, int(min(h, w) * 0.05))
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(min_dim, min_dim),
        )
        if len(faces) == 0:
            return {"face_count": 0, "dominant_face_area": 0.0}
        image_area = h * w
        largest_area = max(int(fw) * int(fh) for (_, _, fw, fh) in faces)
        largest_frac = largest_area / image_area if image_area else 0.0
        return {
            "face_count": int(len(faces)),
            "dominant_face_area": float(largest_frac),
        }
    except Exception as e:
        logger.warning(f"Face detection failed: {e}")
        return {"face_count": None, "dominant_face_area": None}


def extract_ocr_features(image: Image.Image) -> dict:
    if not settings.enable_ocr:
        return {"text_present": None, "text": None, "text_char_count": None}
    try:
        _configure_tesseract()
        import pytesseract

        text = pytesseract.image_to_string(image).strip()
        return {
            "text_present": bool(text),
            "text": text or None,
            "text_char_count": len(text),
        }
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return {"text_present": None, "text": None, "text_char_count": None}


def extract_color_features(image: Image.Image, k: int = 5) -> dict:
    rgb = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
    hsv = np.array(image.convert("HSV"), dtype=np.float32) / 255.0

    brightness = float(rgb.mean())
    saturation = float(hsv[..., 1].mean())
    luminance = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    contrast = float(luminance.std())

    dominant: list[list[int]] = []
    try:
        from sklearn.cluster import KMeans

        flat = (rgb.reshape(-1, 3) * 255).astype(np.uint8)
        if flat.shape[0] > 10000:
            rng = np.random.default_rng(42)
            idx = rng.choice(flat.shape[0], 10000, replace=False)
            flat = flat[idx]
        km = KMeans(n_clusters=k, n_init=3, random_state=42).fit(flat)
        centers = km.cluster_centers_.astype(int).tolist()
        counts = np.bincount(km.labels_, minlength=k)
        order = np.argsort(-counts)
        dominant = [centers[i] for i in order]
    except Exception as e:
        logger.warning(f"k-means dominant colors failed: {e}")

    return {
        "brightness": brightness,
        "saturation": saturation,
        "contrast": contrast,
        "dominant_colors": dominant,
    }


def extract_clip_embedding(image: Image.Image) -> Optional[list[float]]:
    if not settings.enable_clip_embeddings:
        return None
    try:
        import torch

        model, preprocess = _load_clip()
        device = next(model.parameters()).device
        x = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
        with torch.no_grad():
            emb = model.encode_image(x)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb.squeeze(0).cpu().tolist()
    except Exception as e:
        logger.warning(f"CLIP embedding failed: {e}")
        return None


def extract_thumbnail_features(thumbnail_path: Path) -> dict:
    """All-in-one. Returns a flat dict the orchestrator maps to `thumb_*` columns."""
    img = Image.open(thumbnail_path)
    out: dict = {}
    out.update(extract_face_features(img))
    out.update(extract_ocr_features(img))
    out.update(extract_color_features(img))
    out["clip_embedding"] = extract_clip_embedding(img)
    return out
