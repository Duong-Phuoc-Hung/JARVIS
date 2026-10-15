"""
tests/unit/test_streaming_stt.py
================================
Unit tests for jarvis/stt/streaming.py:
  - Real-time chunked audio ingestion (100ms - 200ms blocks).
  - Voice Activity Detection (VAD) transition and pre-speech buffer accumulation.
  - Partial transcription hypothesis emission (`on_partial`).
  - Trailing silence detection and final transcript emission (`on_final`).
  - Session lifecycle: finish(), cancel(), reset.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from jarvis.stt.streaming import (
    StreamingConfig,
    StreamingHypothesis,
    StreamingSTTEngine,
    StreamingSTTSession,
)


def _generate_synthetic_chunk(
    frequency: float = 300.0,
    duration_s: float = 0.1,  # 100ms
    sample_rate: int = 16000,
    amplitude: float = 0.25,
) -> np.ndarray:
    """Helper to generate a 1D float32 audio chunk with a sinusoidal tone."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    # Sine wave with high amplitude to trigger VAD threshold
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def _generate_silent_chunk(duration_s: float = 0.1, sample_rate: int = 16000) -> np.ndarray:
    """Helper to generate a silent audio chunk."""
    return np.zeros(int(sample_rate * duration_s), dtype=np.float32)


def test_streaming_config_defaults():
    """Verify default parameters for real-time streaming STT."""
    cfg = StreamingConfig()
    assert cfg.sample_rate == 16000
    assert cfg.chunk_size_samples == 1600
    assert cfg.window_size_s == 3.0
    assert cfg.step_interval_s == 0.25
    assert cfg.silence_cutoff_s == 0.75
    assert cfg.speech_threshold == 0.012
    assert cfg.language == "vi"


def test_streaming_session_silence_remains_idle():
    """Verify feeding continuous silence does not trigger speech start or partials."""
    mock_transcriber = MagicMock(return_value="test")
    on_partial = MagicMock()
    on_final = MagicMock()
    on_speech_start = MagicMock()

    cfg = StreamingConfig(speech_threshold=0.012)
    session = StreamingSTTSession(
        transcriber_fn=mock_transcriber,
        config=cfg,
        on_partial=on_partial,
        on_final=on_final,
        on_speech_start=on_speech_start,
    )

    silent_chunk = _generate_silent_chunk(duration_s=0.1)
    for _ in range(5):
        hyp = session.feed(silent_chunk)
        assert hyp is None

    assert session.is_speech_active is False
    assert on_speech_start.call_count == 0
    assert on_partial.call_count == 0
    assert on_final.call_count == 0
    assert mock_transcriber.call_count == 0


def test_streaming_session_speech_activation_and_partial():
    """Verify feeding speech triggers on_speech_start and periodic on_partial."""
    transcribed_words = ["xin", "xin chào", "xin chào JARVIS"]
    call_idx = 0

    def mock_transcriber(audio: np.ndarray, lang: str) -> str:
        nonlocal call_idx
        idx = min(call_idx, len(transcribed_words) - 1)
        call_idx += 1
        return transcribed_words[idx]

    on_partial = MagicMock()
    on_final = MagicMock()
    on_speech_start = MagicMock()

    # Step interval 0.15s for quick test cadence
    cfg = StreamingConfig(
        step_interval_s=0.15,
        min_speech_s=0.20,
        silence_cutoff_s=0.50,
        speech_threshold=0.010,
    )
    session = StreamingSTTSession(
        transcriber_fn=mock_transcriber,
        config=cfg,
        on_partial=on_partial,
        on_final=on_final,
        on_speech_start=on_speech_start,
    )

    speech_chunk = _generate_synthetic_chunk(frequency=400.0, duration_s=0.1, amplitude=0.3)

    # Feed 1st chunk (100ms) -> speech detected
    session.feed(speech_chunk)
    assert session.is_speech_active is True
    assert on_speech_start.call_count == 1

    # Feed 2nd & 3rd chunks (total 300ms speech) with small delay to cross step_interval_s
    session.feed(speech_chunk)
    time.sleep(0.16)
    session.feed(speech_chunk)

    # on_partial should have been emitted
    assert on_partial.call_count >= 1
    assert on_final.call_count == 0


def test_streaming_session_silence_cutoff_finalizes():
    """Verify that trailing silence triggers on_final and resets session to idle."""
    mock_transcriber = MagicMock(return_value="bật đèn phòng khách")
    on_partial = MagicMock()
    on_final = MagicMock()

    cfg = StreamingConfig(
        step_interval_s=0.2,
        min_speech_s=0.2,
        silence_cutoff_s=0.3,  # 300ms silence ends turn
        speech_threshold=0.010,
    )
    session = StreamingSTTSession(
        transcriber_fn=mock_transcriber,
        config=cfg,
        on_partial=on_partial,
        on_final=on_final,
    )

    speech_chunk = _generate_synthetic_chunk(duration_s=0.1, amplitude=0.35)
    silent_chunk = _generate_silent_chunk(duration_s=0.1)

    # 300ms active speech
    session.feed(speech_chunk)
    session.feed(speech_chunk)
    session.feed(speech_chunk)
    assert session.is_speech_active is True

    # Feed 300ms of silence (3 x 100ms)
    session.feed(silent_chunk)
    session.feed(silent_chunk)
    hyp = session.feed(silent_chunk)

    assert hyp is not None
    assert hyp.is_final is True
    assert hyp.text == "bật đèn phòng khách"
    assert on_final.call_count == 1
    on_final.assert_called_with("bật đèn phòng khách")
    # Session reset
    assert session.is_speech_active is False


def test_streaming_session_manual_finish():
    """Verify manual finish forces final transcription and closes session."""
    mock_transcriber = MagicMock(return_value="mở trình duyệt")
    on_final = MagicMock()

    cfg = StreamingConfig(min_speech_s=0.2, speech_threshold=0.010)
    session = StreamingSTTSession(
        transcriber_fn=mock_transcriber,
        config=cfg,
        on_final=on_final,
    )

    speech_chunk = _generate_synthetic_chunk(duration_s=0.1, amplitude=0.3)
    session.feed(speech_chunk)
    session.feed(speech_chunk)
    session.feed(speech_chunk)

    result = session.finish()
    assert result == "mở trình duyệt"
    assert on_final.call_count == 1


def test_streaming_session_cancel():
    """Verify cancel cleanly aborts session without calling on_final."""
    mock_transcriber = MagicMock(return_value="hủy thao tác")
    on_final = MagicMock()

    session = StreamingSTTSession(
        transcriber_fn=mock_transcriber,
        on_final=on_final,
    )

    speech_chunk = _generate_synthetic_chunk(duration_s=0.1, amplitude=0.3)
    session.feed(speech_chunk)
    session.cancel()

    assert session.is_speech_active is False
    assert on_final.call_count == 0


def test_streaming_stt_engine_factory():
    """Verify StreamingSTTEngine wraps underlying base engine."""
    class DummyEngine:
        def transcribe(self, audio, language="vi"):
            return "giọng nói thử nghiệm"

    engine = StreamingSTTEngine(base_engine=DummyEngine())
    on_final = MagicMock()
    session = engine.create_session(on_final=on_final)

    speech_chunk = _generate_synthetic_chunk(duration_s=0.1, amplitude=0.35)
    for _ in range(3):
        session.feed(speech_chunk)

    res = session.finish()
    assert res == "giọng nói thử nghiệm"
    on_final.assert_called_with("giọng nói thử nghiệm")
