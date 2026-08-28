"""
tests/unit/test_offline_stt.py
================================
Unit tests for Faster-Whisper offline STT adapter.
"""
from __future__ import annotations

import struct
import time
from unittest.mock import MagicMock, patch

import pytest

fw_mod = pytest.importorskip("jarvis.stt.faster_whisper", reason="Faster-Whisper STT module not available")

from jarvis.stt.faster_whisper import (
    FasterWhisperConfig,
    FasterWhisperSTTEngine,
    TranscriptionResult,
    TranscriptionSegment,
)


class TestFasterWhisperConfig:
    def test_default_model_size(self):
        cfg = FasterWhisperConfig()
        assert cfg.model_size in ("tiny", "base", "small", "medium", "large")

    def test_default_language_vietnamese(self):
        cfg = FasterWhisperConfig()
        assert cfg.language == "vi"

    def test_default_device_cpu(self):
        cfg = FasterWhisperConfig()
        assert cfg.device == "cpu"

    def test_custom_model_size(self):
        cfg = FasterWhisperConfig(model_size="small", language="en")
        assert cfg.model_size == "small"
        assert cfg.language == "en"


class TestFasterWhisperSTTEngineMock:
    @pytest.fixture
    def engine(self):
        return FasterWhisperSTTEngine(is_mock=True)

    def test_is_available_mock(self, engine):
        assert engine.is_available() is True

    def test_transcribe_returns_result(self, engine):
        silence = b"\x00" * 3200
        result = engine.transcribe(silence)
        assert isinstance(result, TranscriptionResult)

    def test_transcribe_text_is_string(self, engine):
        result = engine.transcribe(b"\x00" * 3200)
        assert isinstance(result.text, str)

    def test_transcribe_language_populated(self, engine):
        result = engine.transcribe(b"\x00" * 3200)
        assert isinstance(result.language, str)
        assert len(result.language) > 0

    def test_transcribe_duration_positive(self, engine):
        result = engine.transcribe(b"\x00" * 3200)
        assert result.duration_ms >= 0

    def test_transcribe_confidence_valid_range(self, engine):
        result = engine.transcribe(b"\x00" * 3200)
        assert 0.0 <= result.confidence <= 1.0

    def test_transcribe_empty_bytes_returns_result(self, engine):
        result = engine.transcribe(b"")
        assert isinstance(result, TranscriptionResult)


class TestTranscriptionResult:
    def test_result_dataclass_fields(self):
        result = TranscriptionResult(
            text="xin chào",
            language="vi",
            confidence=0.95,
            duration_ms=350.0,
        )
        assert result.text == "xin chào"
        assert result.language == "vi"
        assert result.confidence == pytest.approx(0.95)
        assert result.duration_ms == pytest.approx(350.0)
        assert result.segments == []
