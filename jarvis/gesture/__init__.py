"""
Gesture detection package for JARVIS.
Provides multi-pattern acoustic transient gesture classification
(Double Clap, Triple Clap, Clap-Pause-Clap) and state machines, plus a
separate, independent MediaPipe-style hand-landmark gesture pipeline
(OPEN_PALM, FIST, SWIPE_LEFT, SWIPE_RIGHT). The two subsystems share no
types; the acoustic detector is unmodified by the hand-gesture addition.
"""
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.hand_models import (
    HandGestureBackend,
    HandGestureResult,
    HandGestureType,
    HandLandmarkIndex,
    HandLandmarkPoint,
    HandLandmarks,
    HandTrackerState,
)
from jarvis.gesture.hand_preprocess import (
    classify_dynamic_gesture,
    classify_static_shape,
    landmarks_to_feature_vector,
    normalize_landmarks,
)
from jarvis.gesture.hand_tracker import HandGestureTracker, get_available_backend
from jarvis.gesture.models import (
    ClapEvent,
    DetectorState,
    GestureEvent,
    GesturePatternConfig,
    GestureResult,
    GestureType,
)
from jarvis.gesture.patterns import get_default_patterns

__all__ = [
    "GestureDetector",
    "GestureType",
    "DetectorState",
    "ClapEvent",
    "GesturePatternConfig",
    "GestureResult",
    "GestureEvent",
    "get_default_patterns",
    "HandGestureTracker",
    "HandGestureType",
    "HandGestureBackend",
    "HandGestureResult",
    "HandTrackerState",
    "HandLandmarks",
    "HandLandmarkPoint",
    "HandLandmarkIndex",
    "normalize_landmarks",
    "classify_static_shape",
    "classify_dynamic_gesture",
    "landmarks_to_feature_vector",
    "get_available_backend",
]
