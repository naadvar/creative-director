"""Video frame analysis: cut detection, first-3s features, motion intensity.

Uses OpenCV. Decode is incremental — we never load the whole video into memory.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from loguru import logger


def _open_capture(path: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {path}")
    return cap


def _frame_diff(prev: np.ndarray, curr: np.ndarray) -> float:
    """Mean abs diff between two grayscale frames, normalized to 0..1."""
    return float(np.abs(curr.astype(np.int16) - prev.astype(np.int16)).mean() / 255.0)


def detect_cuts(path: Path, threshold: float = 0.35, sample_fps: int = 8) -> list[float]:
    """Timestamps (seconds) of likely scene cuts via frame-diff heuristic."""
    cap = _open_capture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, int(round(fps / sample_fps)))
        cuts: list[float] = []
        prev_gray = None
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                small = cv2.resize(frame, (160, 90))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None and _frame_diff(prev_gray, gray) > threshold:
                    cuts.append(idx / fps)
                prev_gray = gray
            idx += 1
        return cuts
    finally:
        cap.release()


def extract_first_seconds_frames(
    path: Path, seconds: float = 3.0, n: int = 4
) -> list[np.ndarray]:
    """Up to ``n`` evenly-spaced BGR frames from the first ``seconds``."""
    cap = _open_capture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames_target = int(fps * seconds)
        if total_frames_target <= 0:
            return []
        target_indices = sorted({int(i * total_frames_target / n) for i in range(n)})
        frames: list[np.ndarray] = []
        wanted = set(target_indices)
        max_idx = max(target_indices)
        idx = 0
        while idx <= max_idx:
            ok, frame = cap.read()
            if not ok:
                break
            if idx in wanted:
                frames.append(frame)
            idx += 1
        return frames
    finally:
        cap.release()


def motion_intensity(path: Path, seconds: float = 3.0, sample_fps: int = 10) -> float:
    """Average per-frame difference in the first ``seconds``."""
    cap = _open_capture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, int(round(fps / sample_fps)))
        max_frame = int(fps * seconds)
        prev_gray = None
        diffs: list[float] = []
        idx = 0
        while idx <= max_frame:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                small = cv2.resize(frame, (160, 90))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                if prev_gray is not None:
                    diffs.append(_frame_diff(prev_gray, gray))
                prev_gray = gray
            idx += 1
        return float(np.mean(diffs)) if diffs else 0.0
    finally:
        cap.release()


def video_duration_seconds(path: Path) -> float:
    cap = _open_capture(path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        return float(n / fps) if fps else 0.0
    finally:
        cap.release()


def extract_video_features(path: Path) -> dict:
    try:
        cuts = detect_cuts(path)
        first3 = [c for c in cuts if c <= 3.0]
        duration = video_duration_seconds(path)
        mi = motion_intensity(path)
        avg_shot = (duration / len(cuts)) if cuts else duration
        return {
            "first3s_cut_count": len(first3),
            "total_cut_count": len(cuts),
            "avg_shot_length": float(avg_shot),
            "first3s_motion_intensity": mi,
        }
    except Exception as e:
        logger.warning(f"Video feature extraction failed: {e}")
        return {}
