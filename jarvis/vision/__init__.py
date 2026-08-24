"""
jarvis.vision
=============
Computer Vision, Biometrics, and Hand Gesture Tracking subsystem.
"""

from jarvis.vision.biometrics import (
    BiometricPrivilegeGate,
    BiometricsEngine,
    FaceEmbeddingStorage,
)
from jarvis.vision.hands import (
    GestureType,
    HandGestureClassifier,
    HandGestureEngine,
    HandLandmarkTracker,
    NormalizedLandmark,
)

from jarvis.vision.dialog_detector import ErrorDialogDetector
from jarvis.vision.ocr import DesktopOCR
from jarvis.vision.screen import ScreenCaptureResult, ScreenVisionManager
from jarvis.vision.computer_use import (
    BoundingBox,
    CoordinateMapper,
    UIElement,
    UIElementDetector,
    ComputerUseVision,
)
from jarvis.vision.visual_verifier import (
    VisualDiffResult,
    VisualVerifier,
)

__all__ = [
    "BiometricsEngine",
    "BiometricPrivilegeGate",
    "FaceEmbeddingStorage",
    "NormalizedLandmark",
    "GestureType",
    "HandLandmarkTracker",
    "HandGestureClassifier",
    "HandGestureEngine",
    "ScreenVisionManager",
    "ScreenCaptureResult",
    "ErrorDialogDetector",
    "DesktopOCR",
    "BoundingBox",
    "CoordinateMapper",
    "UIElement",
    "UIElementDetector",
    "ComputerUseVision",
    "VisualDiffResult",
    "VisualVerifier",
]


