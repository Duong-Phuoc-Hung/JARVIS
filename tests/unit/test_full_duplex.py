"""
tests/unit/test_full_duplex.py
==============================
Unit Test Suite for Continuous Conversational Full-Duplex & Tri-State Barge-In.
Validates:
  1. Tri-State Barge-In Classifier (ambient ignore, soft backchannel, hard barge-in).
  2. Ducking gain transitions (1.0 -> 0.50 -> 0.125).
  3. Hard barge-in interruption callback and playback termination.
"""
import numpy as np
import pytest

from jarvis.audio.fullduplex import (
    ArgonFullDuplexAudioController,
    BargeInDecision,
    TriStateBargeInClassifier,
)


def test_tristate_classifier_ambient_ignore():
    """Validates that ambient noise or typing without voice is ignored."""
    classifier = TriStateBargeInClassifier(energy_threshold=0.01)

    decision = classifier.classify(
        is_tts_playing=True,
        is_voice_detected=False,
        mic_energy_rms=0.005,
        transcript=None,
    )
    assert decision == BargeInDecision.IGNORE_AMBIENT


def test_tristate_classifier_soft_backchannel():
    """Validates that conversational backchannel words trigger soft ducking."""
    classifier = TriStateBargeInClassifier(energy_threshold=0.01)

    for word in ("dạ", "vâng", "ừ", "uh-huh"):
        decision = classifier.classify(
            is_tts_playing=True,
            is_voice_detected=True,
            mic_energy_rms=0.03,
            transcript=word,
        )
        assert decision == BargeInDecision.SOFT_BACKCHANNEL


def test_tristate_classifier_hard_barge_in():
    """Validates that interrupt commands trigger hard barge-in."""
    classifier = TriStateBargeInClassifier(energy_threshold=0.01)

    for phrase in ("dừng lại đi", "thôi khoan", "stop now", "im lặng"):
        decision = classifier.classify(
            is_tts_playing=True,
            is_voice_detected=True,
            mic_energy_rms=0.04,
            transcript=phrase,
        )
        assert decision == BargeInDecision.HARD_BARGE_IN


def test_argon_fullduplex_controller_ducking_flow():
    """Validates controller gain transitions and callback firing on hard barge-in."""
    callback_fired = []

    def on_interrupt():
        callback_fired.append(True)

    controller = ArgonFullDuplexAudioController(on_hard_barge_in=on_interrupt)

    # Initial state
    assert controller.ducking_gain == 1.0
    assert controller.is_tts_playing is False

    # Start playback
    controller.on_playback_started(session_id="test_speech")
    assert controller.is_tts_playing is True

    # 1. Feed ambient frame (typing)
    ambient_frame = np.ones(512, dtype=np.float32) * 0.005
    d1 = controller.evaluate_incoming_frame(ambient_frame, is_voice_detected=False)
    assert d1 == BargeInDecision.IGNORE_AMBIENT
    assert controller.ducking_gain == 1.0

    # 2. Feed soft backchannel frame ("dạ")
    speech_frame = np.ones(512, dtype=np.float32) * 0.03
    d2 = controller.evaluate_incoming_frame(speech_frame, is_voice_detected=True, transcript="dạ")
    assert d2 == BargeInDecision.SOFT_BACKCHANNEL
    assert controller.ducking_gain == 0.50

    # 3. Feed hard interrupt frame ("dừng lại")
    d3 = controller.evaluate_incoming_frame(speech_frame, is_voice_detected=True, transcript="dừng lại")
    assert d3 == BargeInDecision.HARD_BARGE_IN
    assert controller.ducking_gain == 0.125
    assert controller.is_tts_playing is False
    assert len(callback_fired) == 1
