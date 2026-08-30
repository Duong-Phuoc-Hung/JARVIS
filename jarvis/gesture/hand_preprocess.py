"""
jarvis/gesture/hand_preprocess.py
===================================
Pure, deterministic preprocessing and classification functions for the hand
landmark pipeline. None of these functions touch MediaPipe, OpenCV, or a
camera — they operate only on HandLandmarks/plain sequences, so they are
fully unit-testable without any optional dependency or hardware.

Classification approach is a simple, transparent geometric heuristic
(landmark-to-wrist distance ratios for static shapes; net displacement of a
tracked point for dynamic swipes) — deliberately NOT a port of any trained
model or classifier code from any upstream reference project.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from jarvis.gesture.hand_models import HandGestureType, HandLandmarkIndex, HandLandmarks

# Static-shape classification: (tip, reference-joint) pairs per digit.
# A digit counts as "extended" when its tip is farther from the wrist than
# its reference joint by at least EXTENSION_RATIO.
_DIGIT_JOINTS: tuple[tuple[HandLandmarkIndex, HandLandmarkIndex], ...] = (
    (HandLandmarkIndex.THUMB_TIP, HandLandmarkIndex.THUMB_IP),
    (HandLandmarkIndex.INDEX_TIP, HandLandmarkIndex.INDEX_PIP),
    (HandLandmarkIndex.MIDDLE_TIP, HandLandmarkIndex.MIDDLE_PIP),
    (HandLandmarkIndex.RING_TIP, HandLandmarkIndex.RING_PIP),
    (HandLandmarkIndex.PINKY_TIP, HandLandmarkIndex.PINKY_PIP),
)
EXTENSION_RATIO = 1.1
OPEN_PALM_MIN_EXTENDED = 4
FIST_MAX_EXTENDED = 1


def normalize_landmarks(landmarks: HandLandmarks) -> HandLandmarks:
    """
    Translate landmarks so the wrist is the origin, then scale so the
    largest wrist-to-landmark planar distance is 1.0. Makes classification
    invariant to hand position in frame and distance from the camera.
    """
    arr = landmarks.as_array()
    origin = arr[HandLandmarkIndex.WRIST].copy()
    translated = arr - origin

    planar_dists = np.linalg.norm(translated[:, :2], axis=1)
    scale = float(np.max(planar_dists))
    if scale < 1e-9:
        scale = 1.0

    normalized = translated / scale
    return HandLandmarks.from_array(normalized)


def landmarks_to_feature_vector(landmarks: HandLandmarks) -> np.ndarray:
    """Flatten normalized landmarks into a deterministic 63-dim feature vector."""
    return normalize_landmarks(landmarks).as_array().flatten()


def classify_static_shape(landmarks: HandLandmarks) -> tuple[HandGestureType, float]:
    """
    Classify a single hand pose as OPEN_PALM, FIST, or UNKNOWN using
    wrist-relative digit extension ratios. Returns (gesture_type, confidence).
    """
    normalized = normalize_landmarks(landmarks)
    arr = normalized.as_array()
    wrist_xy = arr[HandLandmarkIndex.WRIST][:2]

    extended_flags = []
    for tip_idx, ref_idx in _DIGIT_JOINTS:
        d_tip = float(np.linalg.norm(arr[tip_idx][:2] - wrist_xy))
        d_ref = float(np.linalg.norm(arr[ref_idx][:2] - wrist_xy))
        extended_flags.append(d_tip > d_ref * EXTENSION_RATIO)

    extended_count = sum(extended_flags)
    total = len(_DIGIT_JOINTS)

    if extended_count >= OPEN_PALM_MIN_EXTENDED:
        return HandGestureType.OPEN_PALM, extended_count / total
    if extended_count <= FIST_MAX_EXTENDED:
        return HandGestureType.FIST, (total - extended_count) / total
    return HandGestureType.UNKNOWN, 0.0


def classify_dynamic_gesture(
    point_history: Sequence[tuple[float, float]],
    min_displacement: float = 0.15,
    min_frames: int = 4,
) -> tuple[HandGestureType, float]:
    """
    Classify a horizontal swipe from a short history of a tracked point
    (e.g. wrist position in normalized image coordinates, x increasing
    rightward). Returns (gesture_type, confidence); UNKNOWN/0.0 when the
    history is too short or the motion isn't a clean horizontal swipe.
    """
    if len(point_history) < min_frames:
        return HandGestureType.UNKNOWN, 0.0

    start = point_history[0]
    end = point_history[-1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    if abs(dx) < min_displacement:
        return HandGestureType.UNKNOWN, 0.0
    if abs(dy) >= abs(dx):
        # Motion is not predominantly horizontal.
        return HandGestureType.UNKNOWN, 0.0

    gesture = HandGestureType.SWIPE_RIGHT if dx > 0 else HandGestureType.SWIPE_LEFT
    confidence = min(1.0, abs(dx) / (min_displacement * 2.0))
    return gesture, confidence
