"""
tests/unit/test_hand_gesture.py
================================
Unit tests for the hand-landmark gesture pipeline (jarvis.gesture.hand_*).

Fully deterministic and hardware-free: synthetic 21-point landmark sets are
constructed by hand, no MediaPipe/OpenCV/webcam is used or required.
"""
import time

import numpy as np
import pytest

from jarvis.gesture.hand_models import (
    NUM_HAND_LANDMARKS,
    HandGestureBackend,
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


def _base_coords() -> list[list[float]]:
    """21 arbitrary-but-valid coordinates (wrist at index 0)."""
    coords = [[0.5, 0.5, 0.0]]  # WRIST
    for i in range(1, NUM_HAND_LANDMARKS):
        coords.append([0.5, 0.5 - i * 0.01, 0.0])
    return coords


def _make_open_palm_landmarks() -> HandLandmarks:
    """All 5 fingertips far from the wrist relative to their pip/ip joint -> OPEN_PALM."""
    coords = _base_coords()
    wrist = (0.5, 0.5)
    ref_joints = {
        HandLandmarkIndex.THUMB_IP: (0.45, 0.45),
        HandLandmarkIndex.INDEX_PIP: (0.55, 0.45),
        HandLandmarkIndex.MIDDLE_PIP: (0.5, 0.4),
        HandLandmarkIndex.RING_PIP: (0.45, 0.42),
        HandLandmarkIndex.PINKY_PIP: (0.4, 0.45),
    }
    tips = {
        HandLandmarkIndex.THUMB_TIP: (0.35, 0.35),
        HandLandmarkIndex.INDEX_TIP: (0.65, 0.25),
        HandLandmarkIndex.MIDDLE_TIP: (0.5, 0.15),
        HandLandmarkIndex.RING_TIP: (0.35, 0.25),
        HandLandmarkIndex.PINKY_TIP: (0.25, 0.35),
    }
    for idx, (x, y) in ref_joints.items():
        coords[int(idx)] = [x, y, 0.0]
    for idx, (x, y) in tips.items():
        coords[int(idx)] = [x, y, 0.0]
    coords[0] = [wrist[0], wrist[1], 0.0]
    return HandLandmarks.from_iterable(coords)


def _make_fist_landmarks() -> HandLandmarks:
    """All 5 fingertips curled close to the wrist, closer than their pip/ip joint -> FIST."""
    coords = _base_coords()
    wrist = (0.5, 0.5)
    ref_joints = {
        HandLandmarkIndex.THUMB_IP: (0.48, 0.48),
        HandLandmarkIndex.INDEX_PIP: (0.52, 0.48),
        HandLandmarkIndex.MIDDLE_PIP: (0.5, 0.47),
        HandLandmarkIndex.RING_PIP: (0.48, 0.47),
        HandLandmarkIndex.PINKY_PIP: (0.47, 0.48),
    }
    tips = {
        HandLandmarkIndex.THUMB_TIP: (0.495, 0.495),
        HandLandmarkIndex.INDEX_TIP: (0.505, 0.495),
        HandLandmarkIndex.MIDDLE_TIP: (0.5, 0.49),
        HandLandmarkIndex.RING_TIP: (0.495, 0.49),
        HandLandmarkIndex.PINKY_TIP: (0.49, 0.495),
    }
    for idx, (x, y) in ref_joints.items():
        coords[int(idx)] = [x, y, 0.0]
    for idx, (x, y) in tips.items():
        coords[int(idx)] = [x, y, 0.0]
    coords[0] = [wrist[0], wrist[1], 0.0]
    return HandLandmarks.from_iterable(coords)


# --- HandLandmarks model -------------------------------------------------

def test_hand_landmarks_requires_exactly_21_points():
    with pytest.raises(ValueError):
        HandLandmarks.from_iterable([[0.0, 0.0, 0.0]] * 20)


def test_hand_landmarks_from_array_and_as_array_roundtrip():
    arr = np.array(_base_coords(), dtype=np.float64)
    landmarks = HandLandmarks.from_array(arr)
    out = landmarks.as_array()
    assert out.shape == (NUM_HAND_LANDMARKS, 3)
    assert np.allclose(out, arr)


def test_hand_landmarks_is_immutable():
    landmarks = HandLandmarks.from_iterable(_base_coords())
    with pytest.raises(AttributeError):
        landmarks.points = ()  # type: ignore[misc]


def test_hand_landmark_point_as_tuple():
    p = HandLandmarkPoint(0.1, 0.2, 0.3)
    assert p.as_tuple() == (0.1, 0.2, 0.3)


# --- Preprocessing: normalization ----------------------------------------

def test_normalize_landmarks_translates_wrist_to_origin():
    landmarks = _make_open_palm_landmarks()
    normalized = normalize_landmarks(landmarks)
    wrist = normalized.point(HandLandmarkIndex.WRIST)
    assert wrist.x == pytest.approx(0.0, abs=1e-9)
    assert wrist.y == pytest.approx(0.0, abs=1e-9)


def test_normalize_landmarks_is_scale_invariant():
    landmarks = _make_open_palm_landmarks()
    arr = landmarks.as_array()
    scaled_arr = arr.copy()
    wrist = scaled_arr[0].copy()
    scaled_arr = wrist + (scaled_arr - wrist) * 2.0  # uniformly scale 2x around wrist
    scaled_landmarks = HandLandmarks.from_array(scaled_arr)

    n1 = normalize_landmarks(landmarks).as_array()
    n2 = normalize_landmarks(scaled_landmarks).as_array()
    assert np.allclose(n1, n2, atol=1e-6)


def test_landmarks_to_feature_vector_shape():
    landmarks = _make_open_palm_landmarks()
    vec = landmarks_to_feature_vector(landmarks)
    assert vec.shape == (NUM_HAND_LANDMARKS * 3,)


# --- Preprocessing: static shape classification --------------------------

def test_classify_static_shape_open_palm():
    gesture, confidence = classify_static_shape(_make_open_palm_landmarks())
    assert gesture == HandGestureType.OPEN_PALM
    assert confidence >= 0.6


def test_classify_static_shape_fist():
    gesture, confidence = classify_static_shape(_make_fist_landmarks())
    assert gesture == HandGestureType.FIST
    assert confidence >= 0.6


# --- Preprocessing: dynamic swipe classification -------------------------

def test_classify_dynamic_gesture_swipe_right():
    history = [(0.1, 0.5), (0.2, 0.5), (0.3, 0.5), (0.4, 0.5)]
    gesture, confidence = classify_dynamic_gesture(history, min_displacement=0.15)
    assert gesture == HandGestureType.SWIPE_RIGHT
    assert confidence > 0.0


def test_classify_dynamic_gesture_swipe_left():
    history = [(0.4, 0.5), (0.3, 0.5), (0.2, 0.5), (0.1, 0.5)]
    gesture, confidence = classify_dynamic_gesture(history, min_displacement=0.15)
    assert gesture == HandGestureType.SWIPE_LEFT
    assert confidence > 0.0


def test_classify_dynamic_gesture_too_short_history_is_unknown():
    gesture, confidence = classify_dynamic_gesture([(0.1, 0.5), (0.2, 0.5)], min_frames=4)
    assert gesture == HandGestureType.UNKNOWN
    assert confidence == 0.0


def test_classify_dynamic_gesture_vertical_motion_is_unknown():
    history = [(0.5, 0.1), (0.5, 0.2), (0.5, 0.3), (0.5, 0.4)]
    gesture, confidence = classify_dynamic_gesture(history, min_displacement=0.15)
    assert gesture == HandGestureType.UNKNOWN


def test_classify_dynamic_gesture_below_min_displacement_is_unknown():
    history = [(0.50, 0.5), (0.51, 0.5), (0.52, 0.5), (0.53, 0.5)]
    gesture, confidence = classify_dynamic_gesture(history, min_displacement=0.15)
    assert gesture == HandGestureType.UNKNOWN


# --- HandGestureTracker: static gesture debounce/cooldown ----------------

def test_tracker_requires_stabilization_frames_before_emitting():
    tracker = HandGestureTracker(stabilization_frames=3, confidence_threshold=0.6, cooldown_s=0.0)
    open_palm = _make_open_palm_landmarks()

    r1 = tracker.ingest_landmarks(open_palm, timestamp=0.0)
    r2 = tracker.ingest_landmarks(open_palm, timestamp=0.1)
    r3 = tracker.ingest_landmarks(open_palm, timestamp=0.2)

    assert r1 is None
    assert r2 is None
    assert r3 is not None
    assert r3.gesture_type == HandGestureType.OPEN_PALM


def test_tracker_enforces_cooldown_between_emissions():
    # stabilization_frames=1 isolates cooldown as the only gating factor.
    tracker = HandGestureTracker(stabilization_frames=1, confidence_threshold=0.6, cooldown_s=1.0)
    open_palm = _make_open_palm_landmarks()

    first = tracker.ingest_landmarks(open_palm, timestamp=0.0)
    assert first is not None

    # Within cooldown window -> must not re-emit.
    second = tracker.ingest_landmarks(open_palm, timestamp=0.5)
    assert second is None

    # After cooldown elapses -> emits again.
    third = tracker.ingest_landmarks(open_palm, timestamp=1.1)
    assert third is not None


def _make_partial_open_palm_landmarks() -> HandLandmarks:
    """4 of 5 fingertips extended (pinky curled) -> OPEN_PALM at confidence 0.8."""
    landmarks = _make_open_palm_landmarks()
    coords = [list(p.as_tuple()) for p in landmarks.points]
    # Curl the pinky back near its pip joint (ref joint set at (0.4, 0.45) in _make_open_palm_landmarks).
    coords[int(HandLandmarkIndex.PINKY_TIP)] = [0.41, 0.46, 0.0]
    return HandLandmarks.from_iterable(coords)


def test_tracker_low_confidence_never_emits():
    tracker = HandGestureTracker(stabilization_frames=1, confidence_threshold=0.99, cooldown_s=0.0)
    partial_palm = _make_partial_open_palm_landmarks()
    gesture, confidence = classify_static_shape(partial_palm)
    assert gesture == HandGestureType.OPEN_PALM
    assert confidence < 0.99  # sanity: fixture actually produces a sub-threshold confidence

    result = tracker.ingest_landmarks(partial_palm, timestamp=0.0)
    assert result is None


def test_tracker_swipe_emits_without_waiting_for_static_stabilization():
    tracker = HandGestureTracker(
        stabilization_frames=5, confidence_threshold=0.5, cooldown_s=0.0, min_swipe_displacement=0.1
    )
    base = _base_coords()

    def landmarks_at(x: float) -> HandLandmarks:
        coords = [list(c) for c in base]
        coords[0] = [x, 0.5, 0.0]
        return HandLandmarks.from_iterable(coords)

    results = []
    for i, x in enumerate([0.1, 0.2, 0.3, 0.4]):
        results.append(tracker.ingest_landmarks(landmarks_at(x), timestamp=float(i)))

    assert any(r is not None and r.gesture_type == HandGestureType.SWIPE_RIGHT for r in results)


def test_tracker_reset_clears_buffers():
    tracker = HandGestureTracker(stabilization_frames=2, cooldown_s=0.0)
    open_palm = _make_open_palm_landmarks()
    tracker.ingest_landmarks(open_palm, timestamp=0.0)
    tracker.reset()
    # After reset, a single frame is not enough to emit (stabilization restarts).
    result = tracker.ingest_landmarks(open_palm, timestamp=0.1)
    assert result is None


def test_tracker_add_callback_invoked_on_emission():
    tracker = HandGestureTracker(stabilization_frames=1, cooldown_s=0.0)
    received = []
    tracker.add_callback(received.append)
    tracker.ingest_landmarks(_make_open_palm_landmarks(), timestamp=0.0)
    assert len(received) == 1
    assert received[0].gesture_type == HandGestureType.OPEN_PALM


def test_tracker_callback_exception_does_not_propagate():
    tracker = HandGestureTracker(stabilization_frames=1, cooldown_s=0.0)

    def bad_callback(_result):
        raise RuntimeError("boom")

    tracker.add_callback(bad_callback)
    result = tracker.ingest_landmarks(_make_open_palm_landmarks(), timestamp=0.0)
    assert result is not None  # exception in callback must not break ingestion


# --- Graceful UNAVAILABLE state (no mediapipe/cv2/webcam required) -------

def test_get_available_backend_reports_unavailable_without_deps(monkeypatch):
    import jarvis.gesture.hand_tracker as ht

    monkeypatch.setattr(ht, "CV2_AVAILABLE", False)
    monkeypatch.setattr(ht, "MEDIAPIPE_AVAILABLE", False)
    assert ht.get_available_backend() == HandGestureBackend.UNAVAILABLE


def test_tracker_start_returns_false_and_sets_unavailable_without_deps(monkeypatch):
    import jarvis.gesture.hand_tracker as ht

    monkeypatch.setattr(ht, "CV2_AVAILABLE", False)
    monkeypatch.setattr(ht, "MEDIAPIPE_AVAILABLE", False)

    tracker = HandGestureTracker()
    started = tracker.start()
    assert started is False
    assert tracker.state == HandTrackerState.UNAVAILABLE


def test_tracker_stop_is_safe_noop_when_never_started():
    tracker = HandGestureTracker()
    tracker.stop()  # must not raise
    tracker.shutdown()  # must not raise, idempotent


# --- Lifecycle correctness: worker exception / restart state reset ------

def test_capture_loop_exception_releases_resources_and_updates_state():
    """A worker exception must not leave the tracker reporting RUNNING with dead resources."""

    class FailingCap:
        def __init__(self):
            self.released = False

        def read(self):
            raise RuntimeError("simulated camera failure")

        def release(self):
            self.released = True

    class DummyHands:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    tracker = HandGestureTracker()
    failing_cap = FailingCap()
    dummy_hands = DummyHands()
    tracker._cap = failing_cap
    tracker._mp_hands = dummy_hands
    tracker._state = HandTrackerState.RUNNING
    tracker._capture_thread = object()  # placeholder; loop run synchronously below

    tracker._capture_loop()  # cap.read() raises immediately -> exception path runs once

    assert tracker.state == HandTrackerState.UNAVAILABLE
    assert tracker._cap is None
    assert tracker._mp_hands is None
    assert tracker._capture_thread is None
    assert failing_cap.released is True
    assert dummy_hands.closed is True


def test_start_after_worker_exception_actually_restarts(monkeypatch):
    """
    End-to-end: a real capture-thread crash must self-heal out of RUNNING, and a
    subsequent start() must then actually spin up a new thread rather than
    no-op'ing because state was left stuck at RUNNING.
    """
    import jarvis.gesture.hand_tracker as ht

    class CrashingCap:
        def isOpened(self):
            return True

        def read(self):
            raise RuntimeError("simulated camera failure")

        def release(self):
            pass

    class WorkingCap:
        def isOpened(self):
            return True

        def read(self):
            return False, None

        def release(self):
            pass

    class FakeHands:
        def close(self):
            pass

    call_count = {"n": 0}

    class FakeCv2:
        @staticmethod
        def VideoCapture(_index):
            call_count["n"] += 1
            return CrashingCap() if call_count["n"] == 1 else WorkingCap()

    class FakeHandsNamespace:
        @staticmethod
        def Hands(**_kwargs):
            return FakeHands()

    class FakeSolutions:
        hands = FakeHandsNamespace()

    class FakeMediapipe:
        solutions = FakeSolutions()

    monkeypatch.setattr(ht, "CV2_AVAILABLE", True)
    monkeypatch.setattr(ht, "MEDIAPIPE_AVAILABLE", True)
    monkeypatch.setattr(ht, "cv2", FakeCv2())
    monkeypatch.setattr(ht, "mp", FakeMediapipe())

    tracker = HandGestureTracker()

    assert tracker.start() is True  # spawns the thread whose first read() raises

    deadline = time.monotonic() + 2.0
    while tracker.state == HandTrackerState.RUNNING and time.monotonic() < deadline:
        time.sleep(0.01)
    assert tracker.state == HandTrackerState.UNAVAILABLE  # self-healed after the crash

    started_again = tracker.start()
    assert started_again is True
    assert tracker.state == HandTrackerState.RUNNING
    assert tracker._capture_thread is not None

    tracker.stop()


def test_start_clears_stale_classification_state_from_before_restart(monkeypatch):
    """A restart must not let pre-stop landmark history leak into post-restart classification."""
    import jarvis.gesture.hand_tracker as ht

    class FakeCap:
        def isOpened(self):
            return True

        def read(self):
            time.sleep(0.005)
            return False, None

        def release(self):
            pass

    class FakeHands:
        def close(self):
            pass

    class FakeCv2:
        @staticmethod
        def VideoCapture(_index):
            return FakeCap()

    class FakeHandsNamespace:
        @staticmethod
        def Hands(**_kwargs):
            return FakeHands()

    class FakeSolutions:
        hands = FakeHandsNamespace()

    class FakeMediapipe:
        solutions = FakeSolutions()

    monkeypatch.setattr(ht, "CV2_AVAILABLE", True)
    monkeypatch.setattr(ht, "MEDIAPIPE_AVAILABLE", True)
    monkeypatch.setattr(ht, "cv2", FakeCv2())
    monkeypatch.setattr(ht, "mp", FakeMediapipe())

    tracker = HandGestureTracker()
    # Seed stale state as if a gesture were mid-flight right before a stop().
    tracker._point_history.extend([(0.1, 0.5), (0.9, 0.5)])
    tracker._recent_static.append(HandGestureType.OPEN_PALM)
    tracker._last_emit_time = 123.0

    started = tracker.start()
    assert started is True
    assert len(tracker._point_history) == 0
    assert len(tracker._recent_static) == 0
    assert tracker._last_emit_time == float("-inf")

    tracker.stop()
