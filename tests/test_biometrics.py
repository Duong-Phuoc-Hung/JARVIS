"""
tests/test_biometrics.py
========================
Test Suite for Biometric Authentication, Privilege Gating, Intruder Auto-Lock, and Hand Tracking.
Covering:
  - F-33: Face Enrollment & Verification (128D face embedding comparison)
  - F-34: Biometric Privilege Gate (Authorization barrier for sensitive commands)
  - F-35: Intruder Detection & Auto-Lock (Stranger face -> Win32 LockWorkStation + Telegram alert)
  - F-36: 21-Point 3D Hand Landmark Tracking
  - F-37: Virtual Desktop & Window Gestures (Swipe left/right, Fist clench)
"""

from typing import Any, Dict, List, Optional
import numpy as np
import pytest

from jarvis.core.models import PrivilegeLevel, RequesterContext
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


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_biometrics_face_enrollment_and_verification_tier1(mock_camera_feed):
    """
    [F-33] Validate owner face enrollment and live frame matching with face encodings.
    """
    engine = BiometricsEngine(mock_camera_feed)
    owner_frame = mock_camera_feed.get_owner_frame()
    assert engine.verify_frame(owner_frame) is True


def test_biometrics_privilege_gate_unlocks_on_auth_tier1(mock_camera_feed):
    """
    [F-34] Validate privilege gate permits high-privilege execution after biometric auth.
    """
    engine = BiometricsEngine(mock_camera_feed)
    gate = BiometricPrivilegeGate(engine)

    # 1. Without auth -> Denied
    assert gate.is_allowed("execute_nmap_scan", None) is False

    # 2. With valid owner face -> Authorized
    context = gate.authenticate(mock_camera_feed.get_owner_frame())
    assert context is not None
    assert context.is_authenticated is True
    assert gate.is_allowed("execute_nmap_scan", context) is True


def test_biometrics_intruder_detection_and_lockworkstation_tier1(mock_camera_feed, mock_win32_platform, mock_http_server):
    """
    [F-35] Validate stranger face detection invokes user32.LockWorkStation and dispatches Telegram alert.
    """
    engine = BiometricsEngine(mock_camera_feed)
    stranger_frame = mock_camera_feed.get_stranger_frame()

    res = engine.process_surveillance_frame(stranger_frame, mock_win32_platform, mock_http_server)
    assert res["locked"] is True
    assert mock_win32_platform.lock_workstation_calls == 1
    assert len(mock_http_server.telegram_sent_photos) == 1
    assert "CẢNH BÁO" in mock_http_server.telegram_sent_photos[0]["caption"]


def test_biometrics_hand_gestures_swipe_and_fist_tier1(mock_camera_feed, mock_win32_platform):
    """
    [F-36, F-37] Validate 21-point hand tracking classifies swipe and fist gestures.
    """
    gesture_engine = HandGestureEngine(camera_feed=mock_camera_feed, win32_platform=mock_win32_platform)

    # 1. Swipe Left
    mock_camera_feed.set_scene("swipe_left")
    mock_camera_feed.frame_counter = 1
    gesture_engine.process_frame(mock_camera_feed.generate_synthetic_frame())
    mock_camera_feed.frame_counter = 6
    g1 = gesture_engine.process_frame(mock_camera_feed.generate_synthetic_frame())
    assert g1 == GestureType.SWIPE_LEFT

    # 2. Fist Clench
    gesture_engine.classifier.last_trigger_time = 0.0  # Reset debounce for test
    mock_camera_feed.set_scene("fist")
    g2 = gesture_engine.process_frame(mock_camera_feed.generate_synthetic_frame())
    assert g2 == GestureType.FIST


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_biometrics_bypass_mode_tier2(mock_camera_feed):
    """
    [F-33, F-34] Validate software bypass mode allows headless CI operation safely.
    """
    engine = BiometricsEngine(mock_camera_feed, bypass_mode=True)
    gate = BiometricPrivilegeGate(engine)

    # Frame is None (no camera)
    context = gate.authenticate(None)
    assert context is not None
    assert gate.is_allowed("any_action", context) is True


def test_biometrics_dark_or_occluded_frame_handling_tier2(mock_camera_feed):
    """
    [F-33] Validate pitch black or occluded video frame returns False without triggering false-positive lock.
    """
    engine = BiometricsEngine(mock_camera_feed)
    black_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    assert engine.verify_frame(black_frame) is False
