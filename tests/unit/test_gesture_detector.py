"""
tests/unit/test_gesture_detector.py
===================================
Unit tests for Multi-Pattern Acoustic Gesture Detector (jarvis.gesture.detector).
"""
import numpy as np
import pytest

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.models import ClapEvent, GestureType


def test_gesture_detector_single_clap_ignored(mock_audio_stream):
    """Verify single isolated clap does not trigger any pattern."""
    detector = GestureDetector()
    pcm = mock_audio_stream.generate_claps([0.10], total_s=0.6)
    events = detector.process_stream(pcm)
    assert len(events) == 0


def test_gesture_detector_double_clap_success(mock_audio_stream):
    """Verify 2 claps separated by 150ms trigger DOUBLE_CLAP."""
    detector = GestureDetector()
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15, leading_silence_s=0.1, trailing_silence_s=0.5)
    events = detector.process_stream(pcm)
    assert len(events) == 1
    assert events[0].pattern_type == "DOUBLE_CLAP"
    assert events[0].gesture_type == GestureType.DOUBLE_CLAP


def test_gesture_detector_triple_clap_success(mock_audio_stream):
    """Verify 3 claps separated by 150ms trigger TRIPLE_CLAP."""
    detector = GestureDetector()
    pcm = mock_audio_stream.generate_triple_clap(gap1_s=0.15, gap2_s=0.15, leading_silence_s=0.1)
    events = detector.process_stream(pcm)
    assert len(events) == 1
    assert events[0].pattern_type == "TRIPLE_CLAP"
    assert events[0].gesture_type == GestureType.TRIPLE_CLAP


def test_gesture_detector_clap_pause_clap_success(mock_audio_stream):
    """Verify syncopated clap-pause-clap with 750ms pause triggers CLAP_PAUSE_CLAP."""
    detector = GestureDetector()
    pcm = mock_audio_stream.generate_clap_pause_clap(gap_s=0.75, leading_silence_s=0.1)
    events = detector.process_stream(pcm)
    assert len(events) == 1
    assert events[0].pattern_type == "CLAP_PAUSE_CLAP"
    assert events[0].gesture_type == GestureType.CLAP_PAUSE_CLAP


def test_gesture_detector_echo_rejection(mock_audio_stream):
    """Verify echo / bounce (< 50ms) is strictly rejected."""
    detector = GestureDetector(min_double_gap_s=0.05)
    pcm = mock_audio_stream.generate_claps([0.10, 0.13], total_s=0.8)
    events = detector.process_stream(pcm)
    assert len(events) == 0


def test_gesture_detector_gap_timeout(mock_audio_stream):
    """Verify gap exceeding max window (420ms > 350ms) does not trigger double clap."""
    detector = GestureDetector(max_double_gap_s=0.35, pause_min_s=0.50)
    pcm = mock_audio_stream.generate_claps([0.10, 0.52], total_s=1.0)
    events = detector.process_stream(pcm)
    assert len(events) == 0


def test_gesture_detector_cooldown_lockout(mock_audio_stream):
    """Verify cooldown period suppresses rapid redundant triggers."""
    detector = GestureDetector(cooldown_s=0.45)
    pcm = mock_audio_stream.generate_claps([0.10, 0.25, 0.40], total_s=1.2)
    events = detector.process_stream(pcm)
    assert len(events) == 1


def test_gesture_detector_event_bus_and_dispatcher_integration():
    """Verify GestureDetector publishes to EventBus and calls ActionDispatcher."""
    bus = EventBus()
    bus_events = []
    bus.subscribe("gesture.detected", lambda gesture_type, result, **kwargs: bus_events.append(gesture_type))

    dispatcher = ActionDispatcher()
    executed_actions = []
    dispatcher.register_action(
        name="spotify",
        handler=lambda **kwargs: executed_actions.append("spotify") or {"status": "ok"},
    )

    detector = GestureDetector(dispatcher=dispatcher, event_bus=bus)

    # Feed claps directly
    clap1 = ClapEvent(timestamp=1.00, amplitude=0.5)
    clap2 = ClapEvent(timestamp=1.15, amplitude=0.5)

    detector.feed_clap(clap1)
    detector.feed_clap(clap2)
    detector.tick(now=1.55)  # Disambiguation timeout

    assert "double_clap" in bus_events
    assert "spotify" in executed_actions
