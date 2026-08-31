"""
jarvis/gesture/hand_tracker.py
================================
Thread-safe lifecycle wrapper around the pure hand-gesture classification
functions in jarvis.gesture.hand_preprocess. Emits semantic
HandGestureResult events only — no direct OS actions, no wiring into
ActionDispatcher/core in this phase.

OpenCV and MediaPipe are optional, lazily-imported dependencies. When
either is absent, or no webcam can be opened, the tracker cleanly reports
HandTrackerState.UNAVAILABLE instead of raising — mirroring the graceful
degradation pattern used by jarvis.audio.wake_word.WakeWordDetector.

`ingest_landmarks()` is the deterministic, hardware-free entry point used by
both real camera capture (internally) and unit tests (directly) — it never
touches cv2/mediapipe itself.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from jarvis.gesture.hand_models import (
    HandGestureBackend,
    HandGestureResult,
    HandGestureType,
    HandLandmarks,
    HandTrackerState,
)
from jarvis.gesture.hand_preprocess import classify_dynamic_gesture, classify_static_shape

logger = logging.getLogger("jarvis.gesture.hand_tracker")

try:
    import cv2  # type: ignore[import-untyped]
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    CV2_AVAILABLE = False

try:
    import mediapipe as mp  # type: ignore[import-untyped]
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    mp = None  # type: ignore[assignment]
    MEDIAPIPE_AVAILABLE = False


def get_available_backend() -> HandGestureBackend:
    """Report which real camera/landmark backend, if any, is importable right now."""
    if CV2_AVAILABLE and MEDIAPIPE_AVAILABLE:
        return HandGestureBackend.MEDIAPIPE
    return HandGestureBackend.UNAVAILABLE


class HandGestureTracker:
    """
    Static-shape (OPEN_PALM/FIST) + dynamic-swipe (SWIPE_LEFT/SWIPE_RIGHT)
    hand gesture classifier with confidence thresholding, temporal
    stabilization/debounce for static shapes, and a post-trigger cooldown.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        stabilization_frames: int = 3,
        cooldown_s: float = 0.75,
        history_maxlen: int = 8,
        min_swipe_displacement: float = 0.15,
        on_gesture: Callable[[HandGestureResult], None] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.confidence_threshold = float(confidence_threshold)
        self.stabilization_frames = max(1, int(stabilization_frames))
        self.cooldown_s = float(cooldown_s)
        self.min_swipe_displacement = float(min_swipe_displacement)
        self.on_gesture = on_gesture

        self._point_history: deque[tuple[float, float]] = deque(maxlen=max(2, history_maxlen))
        self._recent_static: deque[HandGestureType] = deque(maxlen=self.stabilization_frames)
        self._last_emit_time: float = float("-inf")
        self._callbacks: list[Callable[[HandGestureResult], None]] = []

        self._state: HandTrackerState = HandTrackerState.IDLE
        self._cap: Any = None
        self._mp_hands: Any = None
        self._capture_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def state(self) -> HandTrackerState:
        with self._lock:
            return self._state

    def add_callback(self, cb: Callable[[HandGestureResult], None]) -> None:
        with self._lock:
            if cb not in self._callbacks:
                self._callbacks.append(cb)

    def reset(self) -> None:
        """Clear buffers/state to IDLE. Does not affect an active camera capture."""
        with self._lock:
            self._point_history.clear()
            self._recent_static.clear()
            self._last_emit_time = float("-inf")

    def is_backend_available(self) -> bool:
        return get_available_backend() == HandGestureBackend.MEDIAPIPE

    def ingest_landmarks(
        self,
        landmarks: HandLandmarks,
        timestamp: float | None = None,
        handedness: str | None = None,
    ) -> HandGestureResult | None:
        """
        Deterministic classification entry point. Feed one hand's landmarks
        for one frame; returns a HandGestureResult only when a gesture is
        confidently, stably recognized and not currently in cooldown.
        """
        with self._lock:
            now = timestamp if timestamp is not None else time.monotonic()

            wrist = landmarks.point(0)
            self._point_history.append((wrist.x, wrist.y))

            dynamic_type, dynamic_conf = classify_dynamic_gesture(
                list(self._point_history), min_displacement=self.min_swipe_displacement
            )

            candidate_type: HandGestureType
            candidate_conf: float
            if dynamic_type != HandGestureType.UNKNOWN and dynamic_conf >= self.confidence_threshold:
                candidate_type, candidate_conf = dynamic_type, dynamic_conf
                is_dynamic = True
            else:
                candidate_type, candidate_conf = classify_static_shape(landmarks)
                is_dynamic = False

            if candidate_type == HandGestureType.UNKNOWN or candidate_conf < self.confidence_threshold:
                self._recent_static.clear()
                return None

            if is_dynamic:
                stable = True
            else:
                self._recent_static.append(candidate_type)
                stable = (
                    len(self._recent_static) == self.stabilization_frames
                    and all(g == candidate_type for g in self._recent_static)
                )

            if not stable:
                return None

            if now - self._last_emit_time < self.cooldown_s:
                return None

            self._last_emit_time = now
            if is_dynamic:
                self._point_history.clear()
            self._recent_static.clear()

            result = HandGestureResult(
                gesture_type=candidate_type,
                confidence=candidate_conf,
                timestamp=now,
                handedness=handedness,
            )
            self._dispatch(result)
            return result

    def _dispatch(self, result: HandGestureResult) -> None:
        if self.on_gesture:
            try:
                self.on_gesture(result)
            except Exception as exc:
                logger.error("Error in on_gesture callback: %s", exc)
        for cb in list(self._callbacks):
            try:
                cb(result)
            except Exception as exc:
                logger.error("Error in hand gesture callback: %s", exc)

    # -- Optional real camera/MediaPipe lifecycle -----------------------
    # Not exercised by unit tests (no webcam requirement); guarded so a
    # missing dependency or camera never raises, only reports UNAVAILABLE.

    def start(self, camera_index: int = 0) -> bool:
        """Attempt to start real webcam + MediaPipe Hands capture. Returns success."""
        with self._lock:
            if self._state == HandTrackerState.RUNNING:
                return True
            if not self.is_backend_available():
                logger.info("Hand gesture backend unavailable (cv2/mediapipe not installed).")
                self._state = HandTrackerState.UNAVAILABLE
                return False

            try:
                cap = cv2.VideoCapture(camera_index)
                if not cap.isOpened():
                    cap.release()
                    self._state = HandTrackerState.UNAVAILABLE
                    return False
                self._cap = cap
                self._mp_hands = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=1,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            except Exception as exc:
                logger.warning("Failed to initialize hand gesture backend: %s", exc)
                self._release_backend_locked()
                self._state = HandTrackerState.UNAVAILABLE
                return False

            # A fresh (re)start must not classify motion spanning the gap between this
            # start() and any prior stop() — clear stale point-history/stabilization/
            # cooldown state so the first post-restart frame can't combine with a
            # leftover pre-stop landmark into a spurious gesture.
            self._point_history.clear()
            self._recent_static.clear()
            self._last_emit_time = float("-inf")

            self._stop_event.clear()
            self._state = HandTrackerState.RUNNING
            self._capture_thread = threading.Thread(
                target=self._capture_loop, name="HandGestureCapture", daemon=True
            )
            self._capture_thread.start()
            return True

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                cap = self._cap
                hands = self._mp_hands
            if cap is None or hands is None:
                return
            try:
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_result = hands.process(rgb)
                if mp_result and getattr(mp_result, "multi_hand_landmarks", None):
                    raw = mp_result.multi_hand_landmarks[0]
                    coords = [(lm.x, lm.y, lm.z) for lm in raw.landmark]
                    landmarks = HandLandmarks.from_iterable(coords)
                    self.ingest_landmarks(landmarks)
            except Exception as exc:
                logger.error("Hand gesture capture loop error: %s", exc)
                # A worker exception must not leave the tracker reporting RUNNING
                # while nothing is actually running — release resources and drop
                # back to UNAVAILABLE so a later start() will genuinely restart it.
                with self._lock:
                    self._release_backend_locked()
                    self._capture_thread = None
                    self._state = HandTrackerState.UNAVAILABLE
                return

    def _release_backend_locked(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        if self._mp_hands is not None:
            try:
                self._mp_hands.close()
            except Exception:
                pass
            self._mp_hands = None

    def stop(self) -> None:
        """Stop capture (if running) and release camera/MediaPipe resources. Idempotent."""
        thread_to_join: threading.Thread | None = None
        with self._lock:
            self._stop_event.set()
            thread_to_join = self._capture_thread
            self._capture_thread = None

        if thread_to_join is not None and thread_to_join.is_alive():
            thread_to_join.join(timeout=2.0)

        with self._lock:
            self._release_backend_locked()
            if self._state == HandTrackerState.RUNNING:
                self._state = HandTrackerState.STOPPED

    def shutdown(self) -> None:
        """Alias for stop(), for lifecycle-naming consistency with other detectors."""
        self.stop()
