"""
tests/unit/test_realtime_voice.py
=================================
Unit tests for jarvis/voice/realtime.py:
  - Real-time conversational state transitions (IDLE, LISTENING, THINKING, SPEAKING).
  - Barge-in voice interruption during TTS playback.
  - Streaming STT session integration and partial HUD feedback.
  - Voice biometrics speaker verification gating.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from jarvis.audio.biometrics import VoiceBiometricsManager
from jarvis.stt.streaming import StreamingConfig, StreamingSTTSession
from jarvis.voice.realtime import (
    RealtimeSessionConfig,
    RealtimeVoiceSession,
    RealtimeVoiceState,
)


def _gen_tone(freq: float = 300.0, dur_s: float = 0.1, amp: float = 0.3) -> np.ndarray:
    """Helper to generate a tone chunk."""
    t = np.linspace(0, dur_s, int(16000 * dur_s), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_realtime_session_lifecycle():
    """Verify start, transition, and stop lifecycle states."""
    factory = MagicMock()
    mock_stt_session = MagicMock()
    factory.return_value = mock_stt_session

    session = RealtimeVoiceSession(stt_session_factory=factory)
    assert session.state == RealtimeVoiceState.IDLE

    session.start()
    assert session.state == RealtimeVoiceState.LISTENING
    assert factory.call_count == 1

    session.stop()
    assert session.state == RealtimeVoiceState.IDLE
    assert mock_stt_session.cancel.call_count == 1


def test_realtime_session_barge_in_during_speaking():
    """Verify speaking state triggers barge-in when high-amplitude audio arrives."""
    mock_tts = MagicMock()
    mock_overlay = MagicMock()
    on_barge_in = MagicMock()

    stt_session = MagicMock()
    factory = MagicMock(return_value=stt_session)

    cfg = RealtimeSessionConfig(
        enable_barge_in=True,
        barge_in_threshold=0.020,
        barge_in_confirm_frames=2,
    )

    session = RealtimeVoiceSession(
        stt_session_factory=factory,
        tts_manager=mock_tts,
        overlay=mock_overlay,
        config=cfg,
        on_barge_in=on_barge_in,
    )
    session.start()

    # System begins speaking
    session.set_speaking(True)
    assert session.state == RealtimeVoiceState.SPEAKING

    # Loud speech chunk arrives (barge-in attempt)
    loud_chunk = _gen_tone(freq=300.0, dur_s=0.1, amp=0.40)

    # 1st loud frame -> consecutive = 1 (threshold requires 2)
    session.feed_audio(loud_chunk)
    assert session.state == RealtimeVoiceState.SPEAKING
    assert mock_tts.interrupt.call_count == 0

    # 2nd loud frame -> confirms barge-in!
    session.feed_audio(loud_chunk)
    assert session.state == RealtimeVoiceState.LISTENING
    assert mock_tts.interrupt.call_count == 1
    assert on_barge_in.call_count == 1


def test_realtime_session_biometrics_gating(tmp_path):
    """Verify speaker biometrics gates utterance completion."""
    bio_path = tmp_path / "voiceprints.json"
    bio_mgr = VoiceBiometricsManager(storage_path=bio_path)

    # Enroll Tony
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    tony_voice = (
        (0.35 * np.sin(2 * np.pi * 130 * t) + 0.25 * np.sin(2 * np.pi * 260 * t) + 0.2 * np.sin(2 * np.pi * 700 * t))
        * np.abs(np.sin(2 * np.pi * 3.0 * t))
    ).astype(np.float32)
    bio_mgr.enroll_speaker("Tony", tony_voice)

    on_complete = MagicMock()
    mock_overlay = MagicMock()

    # Capturing session factory callbacks
    stt_callbacks = {}

    def mock_factory(on_partial=None, on_final=None, on_speech_start=None, override_config=None):
        stt_callbacks["on_final"] = on_final
        sess = MagicMock()
        return sess

    session = RealtimeVoiceSession(
        stt_session_factory=mock_factory,
        biometrics_manager=bio_mgr,
        overlay=mock_overlay,
        on_utterance_complete=on_complete,
        config=RealtimeSessionConfig(enable_biometrics=True),
    )
    session.start()

    # Feed unverified intruder voice
    intruder_voice = (
        (0.50 * np.sin(2 * np.pi * 4500 * t) + 0.30 * np.sin(2 * np.pi * 6000 * t))
        * np.abs(np.sin(2 * np.pi * 8.0 * t))
    ).astype(np.float32)
    session.feed_audio(intruder_voice)

    # Simulate STT concluding with "mở két sắt"
    stt_callbacks["on_final"]("mở két sắt")

    # Intruder should be rejected by biometrics!
    assert on_complete.call_count == 0
    assert session.state == RealtimeVoiceState.LISTENING

    # Now feed Tony's genuine voice
    session.feed_audio(tony_voice)
    stt_callbacks["on_final"]("chào JARVIS")

    # Tony should be accepted!
    assert on_complete.call_count == 1
    on_complete.assert_called_with("chào JARVIS")
    assert session.state == RealtimeVoiceState.THINKING
