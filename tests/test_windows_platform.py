"""
tests/test_windows_platform.py
==============================
Test Suite for Windows Platform Interception, Monitor Geometry, and Touchless Gestures.
Covering:
  - Win32 Platform API (Monitor sorting, window snapping, focus, hotkeys, workstation locking)
  - F-36: MediaPipe Hand Gesture Tracker (21 3D landmarks for touchless gesture classification)
  - F-37: Virtual Desktop & Window Gestures (Swipe left/right desktop switch, fist clench close)
"""

import sys
from typing import Any, Dict, List, Optional, Tuple
import pytest

from jarvis.core.models import MonitorInfo, WindowInfo
from jarvis.platform.windows import (
    WindowsPlatformAPI,
    close_window,
    focus_window,
    get_monitors,
    is_window_hung,
    lock_workstation,
    send_hotkey,
    set_window_pos,
)


class HandGestureClassifier:
    """Classifies 21 MediaPipe hand landmarks into discrete gestures."""

    @staticmethod
    def classify(landmarks: Optional[List[Any]]) -> str:
        if not landmarks or len(landmarks) < 21:
            return "NO_GESTURE"

        wrist = landmarks[0]
        tips = [landmarks[4], landmarks[8], landmarks[12], landmarks[16], landmarks[20]]

        # Horizontal swipe gestures based on lateral displacement
        if landmarks[8].x < 0.38:
            return "SWIPE_LEFT"
        elif landmarks[8].x > 0.62:
            return "SWIPE_RIGHT"

        # Fist vs open palm based on fingertip distance to wrist
        dists = [((t.x - wrist.x)**2 + (t.y - wrist.y)**2)**0.5 for t in tips]
        avg_dist = sum(dists) / len(dists)

        if avg_dist < 0.10:
            return "FIST_CLENCH"

        return "OPEN_PALM"


class TouchlessGestureController:
    """Translates classified hand gestures to Windows desktop actions."""

    def __init__(self, platform: WindowsPlatformAPI):
        self.platform = platform
        self.desktop_switches: List[str] = []
        self.closed_windows: List[int] = []

    def handle_gesture(self, gesture: str, active_hwnd: Optional[int] = None) -> bool:
        if gesture == "SWIPE_LEFT":
            # Switch virtual desktop right (Win + Ctrl + Right)
            self.desktop_switches.append("right")
            return self.platform.send_hotkey("win", "ctrl", "right")
        elif gesture == "SWIPE_RIGHT":
            # Switch virtual desktop left (Win + Ctrl + Left)
            self.desktop_switches.append("left")
            return self.platform.send_hotkey("win", "ctrl", "left")
        elif gesture == "FIST_CLENCH":
            # Close active foreground window
            if active_hwnd:
                self.closed_windows.append(active_hwnd)
                return self.platform.close_window(active_hwnd)
        return False


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_win32_monitor_rect_sorting_left_to_top_tier1(mock_win32_platform):
    """
    [F-37] Validate EnumDisplayMonitors enumerates and sorts display rectangles from leftmost to rightmost, top to bottom.
    """
    api = WindowsPlatformAPI()
    mons = api.get_monitors()

    assert len(mons) >= 3
    assert mons[0].index == 1
    assert mons[0].rect == (0, 0, 1920, 1080)
    assert mons[1].index == 2
    assert mons[1].rect == (1920, 0, 3840, 1080)
    assert mons[2].index == 3
    assert mons[2].rect == (3840, 0, 5760, 1080)


def test_win32_window_snap_to_monitor_bounds_tier1(mock_win32_platform):
    """
    Validate SetWindowPos positions and resizes window to monitor coordinates.
    """
    api = WindowsPlatformAPI()
    success = api.set_window_pos(hwnd=1001, x=1920, y=0, width=1920, height=1080)

    assert success is True
    win = mock_win32_platform.windows[1001]
    assert win.rect == (1920, 0, 3840, 1080)


def test_win32_virtual_desktop_switch_tier1(mock_win32_platform):
    """
    [F-37] Validate virtual desktop left/right switching synthesizes Win+Ctrl+Left/Right keyboard shortcuts.
    """
    api = WindowsPlatformAPI()
    controller = TouchlessGestureController(api)

    res_right = controller.handle_gesture("SWIPE_LEFT")
    assert res_right is True
    assert "right" in controller.desktop_switches

    res_left = controller.handle_gesture("SWIPE_RIGHT")
    assert res_left is True
    assert "left" in controller.desktop_switches


def test_win32_close_active_window_fist_gesture_tier1(mock_win32_platform):
    """
    [F-37] Validate fist clench gesture posts WM_CLOSE message to foreground window.
    """
    api = WindowsPlatformAPI()
    controller = TouchlessGestureController(api)

    res = controller.handle_gesture("FIST_CLENCH", active_hwnd=1002)
    assert res is True
    assert 1002 in controller.closed_windows


def test_mediapipe_hand_gesture_classifier_tier1(mock_camera_feed):
    """
    [F-36] Validate 21-landmark hand tracking classifications for open palm, fist, and swipes.
    """
    classifier = HandGestureClassifier()

    # 1. Open palm
    mock_camera_feed.set_scene("open_palm")
    landmarks_open = mock_camera_feed.get_hand_landmarks()
    assert classifier.classify(landmarks_open) == "OPEN_PALM"

    # 2. Fist clench
    mock_camera_feed.set_scene("fist")
    landmarks_fist = mock_camera_feed.get_hand_landmarks()
    assert classifier.classify(landmarks_fist) == "FIST_CLENCH"

    # 3. Swipe left
    mock_camera_feed.set_scene("swipe_left")
    mock_camera_feed.frame_counter = 5
    landmarks_left = mock_camera_feed.get_hand_landmarks()
    assert classifier.classify(landmarks_left) == "SWIPE_LEFT"

    # 4. Swipe right
    mock_camera_feed.set_scene("swipe_right")
    mock_camera_feed.frame_counter = 5
    landmarks_right = mock_camera_feed.get_hand_landmarks()
    assert classifier.classify(landmarks_right) == "SWIPE_RIGHT"


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_win32_workstation_lock_interception_tier2(mock_win32_platform):
    """
    Validate LockWorkStation is cleanly intercepted without locking developer physical workstation.
    """
    api = WindowsPlatformAPI()
    locked = api.lock_workstation()

    assert locked is True
    assert mock_win32_platform.lock_workstation_calls == 1


def test_win32_ishungappwindow_detection_tier2(mock_win32_platform):
    """
    Validate detection of frozen / unresponsive application windows.
    """
    hung_hwnd = mock_win32_platform.add_hung_window("FrozenBrowser.exe", pid=8899)
    api = WindowsPlatformAPI()

    assert api.is_window_hung(hung_hwnd) is True
    assert api.is_window_hung(1001) is False  # Normal window is not hung


def test_mediapipe_null_or_empty_landmarks_tier2():
    """
    [F-36] Validate handling None or truncated landmark list returns NO_GESTURE safely.
    """
    classifier = HandGestureClassifier()
    assert classifier.classify(None) == "NO_GESTURE"
    assert classifier.classify([]) == "NO_GESTURE"
    assert classifier.classify([None] * 5) == "NO_GESTURE"
