"""
jarvis/vision/hands.py
======================
MediaPipe 21-Point Hand Landmark Tracking, Touchless Gesture Recognition & Action Dispatcher.
Covers Features:
  - F-36: 21-Point 3D Hand Landmark Tracking (MediaPipe / Mock fallback)
  - F-37: Gesture Detection (Swipe Left/Right for Virtual Desktops, Fist Clench for Close Window, Open Palm)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

log = logging.getLogger("jarvis.vision.hands")


@dataclass
class NormalizedLandmark:
    x: float
    y: float
    z: float


class GestureType(str, Enum):
    NONE = "none"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    FIST = "fist"
    OPEN_PALM = "open_palm"


class HandLandmarkTracker:
    """Extracts 21 landmarks per hand from camera frames or test feeds."""

    def __init__(self, camera_feed: Any | None = None):
        self.camera = camera_feed
        self.mp_hands = None
        self._init_mediapipe()

    def _init_mediapipe(self) -> None:
        try:
            import mediapipe as mp  # type: ignore
            self.mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.7,
                min_tracking_confidence=0.5,
            )
        except Exception:
            self.mp_hands = None

    def get_landmarks(self, frame: np.ndarray | None = None) -> list[NormalizedLandmark] | None:
        """Retrieves 21 landmarks from camera_feed mock or live frame."""
        if self.camera and hasattr(self.camera, "get_hand_landmarks"):
            return self.camera.get_hand_landmarks()
        if self.mp_hands is not None and frame is not None:
            try:
                results = self.mp_hands.process(frame)
                if results.multi_hand_landmarks:
                    lms = results.multi_hand_landmarks[0].landmark
                    return [NormalizedLandmark(x=p.x, y=p.y, z=p.z) for p in lms]
            except Exception as exc:
                log.error("MediaPipe hand processing error: %s", exc)
        return None


class HandGestureClassifier:
    """Classifies temporal landmark streams into discrete gesture events with debounce."""

    def __init__(self, debounce_cooldown_s: float = 0.8):
        self.debounce_cooldown_s = debounce_cooldown_s
        self.last_gesture: GestureType = GestureType.NONE
        self.last_trigger_time: float = 0.0
        self.position_history: list[tuple[float, float]] = []  # (x, timestamp)

    def classify(self, landmarks: list[NormalizedLandmark] | None) -> GestureType:
        if not landmarks or len(landmarks) < 21:
            self.position_history.clear()
            return GestureType.NONE

        now = time.time()
        wrist = landmarks[0]
        self.position_history.append((wrist.x, now))
        # Keep recent 1.0s window
        self.position_history = [(x, t) for x, t in self.position_history if now - t <= 1.0]

        # 1. Check Fist Clench
        # In a fist: fingertips (8, 12, 16, 20) are close to wrist (0) or MCPs (5, 9, 13, 17)
        fingertip_indices = [8, 12, 16, 20]
        mcp_indices = [5, 9, 13, 17]

        tip_dists = [np.hypot(landmarks[i].x - wrist.x, landmarks[i].y - wrist.y) for i in fingertip_indices]
        mcp_dists = [np.hypot(landmarks[i].x - wrist.x, landmarks[i].y - wrist.y) for i in mcp_indices]
        coords_std = float(np.std([[lm.x, lm.y] for lm in landmarks]))

        is_fist = coords_std < 0.035 or all(td < md * 1.10 for td, md in zip(tip_dists, mcp_dists))

        if is_fist:
            if now - self.last_trigger_time > self.debounce_cooldown_s:
                self.last_trigger_time = now
                self.last_gesture = GestureType.FIST
                return GestureType.FIST
            return GestureType.NONE

        # 2. Check Swipe Left / Right
        if len(self.position_history) >= 2:
            start_x, start_t = self.position_history[0]
            curr_x, curr_t = self.position_history[-1]
            dx = curr_x - start_x
            dt = max(0.01, curr_t - start_t)
            velocity = dx / dt

            # Swipe Left: moving right to left (dx <= -0.15 or velocity <= -0.40)
            if dx <= -0.15 or velocity <= -0.40 or (start_x > 0.60 and curr_x < 0.40):
                if now - self.last_trigger_time > self.debounce_cooldown_s:
                    self.last_trigger_time = now
                    self.position_history.clear()
                    self.last_gesture = GestureType.SWIPE_LEFT
                    return GestureType.SWIPE_LEFT

            # Swipe Right: moving left to right (dx >= 0.15 or velocity >= 0.40)
            elif dx >= 0.15 or velocity >= 0.40 or (start_x < 0.40 and curr_x > 0.60):
                if now - self.last_trigger_time > self.debounce_cooldown_s:
                    self.last_trigger_time = now
                    self.position_history.clear()
                    self.last_gesture = GestureType.SWIPE_RIGHT
                    return GestureType.SWIPE_RIGHT

        # 3. Check Open Palm
        is_open = all(td > md * 1.25 for td, md in zip(tip_dists, mcp_dists))
        if is_open:
            if now - self.last_trigger_time > self.debounce_cooldown_s and self.last_gesture != GestureType.OPEN_PALM:
                self.last_trigger_time = now
                self.last_gesture = GestureType.OPEN_PALM
                return GestureType.OPEN_PALM

        return GestureType.NONE


class HandGestureEngine:
    """Coordinates camera capture, landmark tracking, gesture classification, and Windows desktop actions."""

    def __init__(
        self,
        camera_feed: Any | None = None,
        enabled: bool = True,
        win32_platform: Any | None = None,
    ):
        self.tracker = HandLandmarkTracker(camera_feed)
        self.classifier = HandGestureClassifier()
        self.enabled = enabled
        self.win32 = win32_platform

    def process_frame(self, frame: np.ndarray | None = None) -> GestureType | None:
        """Processes frame, classifies gesture, and invokes configured desktop actions."""
        if not self.enabled:
            return None

        landmarks = self.tracker.get_landmarks(frame)
        gesture = self.classifier.classify(landmarks)

        if gesture == GestureType.SWIPE_LEFT:
            self._on_swipe_left()
        elif gesture == GestureType.SWIPE_RIGHT:
            self._on_swipe_right()
        elif gesture == GestureType.FIST:
            self._on_fist()

        return gesture if gesture != GestureType.NONE else None

    def _on_swipe_left(self) -> None:
        log.info("Hand Gesture Triggered: SWIPE_LEFT -> Virtual Desktop Left")
        if self.win32 and hasattr(self.win32, "send_hotkey"):
            self.win32.send_hotkey("ctrl", "win", "left")
        else:
            try:
                from jarvis.platform.windows import send_hotkey
                send_hotkey("ctrl", "win", "left")
            except Exception as exc:
                log.debug("send_hotkey error: %s", exc)

    def _on_swipe_right(self) -> None:
        log.info("Hand Gesture Triggered: SWIPE_RIGHT -> Virtual Desktop Right")
        if self.win32 and hasattr(self.win32, "send_hotkey"):
            self.win32.send_hotkey("ctrl", "win", "right")
        else:
            try:
                from jarvis.platform.windows import send_hotkey
                send_hotkey("ctrl", "win", "right")
            except Exception as exc:
                log.debug("send_hotkey error: %s", exc)

    def _on_fist(self) -> None:
        log.info("Hand Gesture Triggered: FIST -> Close Active Window")
        if self.win32 and hasattr(self.win32, "get_active_window") and hasattr(self.win32, "close_window"):
            win = self.win32.get_active_window()
            if win:
                hwnd = getattr(win, "hwnd", win)
                self.win32.close_window(hwnd)
        else:
            try:
                from jarvis.platform.windows import close_window, get_active_window
                win = get_active_window()
                if win:
                    close_window(win.hwnd)
            except Exception as exc:
                log.debug("close_window error: %s", exc)
