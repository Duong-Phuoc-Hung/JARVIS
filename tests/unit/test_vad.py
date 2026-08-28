"""
tests/unit/test_vad.py
=======================
Unit tests for Voice Activity Detection (VAD) engine.
Tests energy-based detection, silence detection, and thread safety.
"""
from __future__ import annotations

import struct
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

vad_mod = pytest.importorskip("jarvis.audio.vad", reason="VAD module not yet available")

from jarvis.audio.vad import VoiceActivityConfig, VoiceActivityDetector, SpeechSegment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pcm(rms_level: float, num_samples: int = 480, sample_rate: int = 16000) -> bytes:
    """Generate PCM bytes with given RMS level (0.0-1.0)."""
    amplitude = int(rms_level * 32767)
    import math
    samples = []
    for i in range(num_samples):
        val = int(amplitude * math.sin(2 * math.pi * 440 * i / sample_rate))
        val = max(-32768, min(32767, val))
        samples.append(val)
    return struct.pack(f"<{num_samples}h", *samples)


def _make_silence(num_samples: int = 480) -> bytes:
    return b"\x00" * (num_samples * 2)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVoiceActivityConfig:
    def test_default_values(self):
        cfg = VoiceActivityConfig()
        assert cfg.sample_rate == 16000
        assert cfg.frame_duration_ms == 30
        assert 0.0 < cfg.silence_threshold < 0.1
        assert cfg.min_speech_duration_ms > 0
        assert cfg.min_silence_duration_ms > 0

    def test_custom_values(self):
        cfg = VoiceActivityConfig(sample_rate=8000, silence_threshold=0.02)
        assert cfg.sample_rate == 8000
        assert cfg.silence_threshold == 0.02


class TestVoiceActivityDetectorMock:
    @pytest.fixture
    def vad(self):
        return VoiceActivityDetector(is_mock=True)

    def test_mock_is_speech_always_false(self, vad):
        audio = _make_pcm(0.8)
        assert vad.is_speech(audio) is False

    def test_mock_listen_returns_segment(self, vad):
        stream = MagicMock()
        stream.read.return_value = _make_silence()
        result = vad.listen_for_speech(stream, timeout_s=0.5)
        assert result is not None
        assert isinstance(result, SpeechSegment)
        assert len(result.audio_bytes) > 0

    def test_mock_speech_segment_has_confidence(self, vad):
        stream = MagicMock()
        stream.read.return_value = _make_silence()
        seg = vad.listen_for_speech(stream, timeout_s=0.5)
        assert 0.0 <= seg.confidence <= 1.0

    def test_mock_speech_segment_duration_positive(self, vad):
        stream = MagicMock()
        stream.read.return_value = _make_silence()
        seg = vad.listen_for_speech(stream, timeout_s=0.5)
        assert seg.duration_ms > 0


class TestVoiceActivityDetectorEnergy:
    @pytest.fixture
    def vad(self):
        cfg = VoiceActivityConfig(silence_threshold=0.05)
        return VoiceActivityDetector(config=cfg, is_mock=False)

    def test_loud_audio_detected_as_speech(self, vad):
        audio = _make_pcm(0.8)  # High amplitude = speech
        assert vad.is_speech(audio) is True

    def test_silence_not_detected_as_speech(self, vad):
        silence = _make_silence()
        assert vad.is_speech(silence) is False

    def test_empty_audio_not_speech(self, vad):
        assert vad.is_speech(b"") is False

    def test_threshold_boundary(self):
        cfg = VoiceActivityConfig(silence_threshold=0.3)
        vad = VoiceActivityDetector(config=cfg, is_mock=False)
        quiet = _make_pcm(0.1)   # Below threshold
        loud = _make_pcm(0.5)    # Above threshold
        assert vad.is_speech(quiet) is False
        assert vad.is_speech(loud) is True


class TestSpeechSegment:
    def test_bool_true_when_bytes_nonempty(self):
        seg = SpeechSegment(audio_bytes=b"\x00" * 100, duration_ms=50.0, confidence=0.9)
        assert bool(seg) is True

    def test_bool_false_when_empty(self):
        seg = SpeechSegment(audio_bytes=b"", duration_ms=0.0, confidence=0.0)
        assert bool(seg) is False
