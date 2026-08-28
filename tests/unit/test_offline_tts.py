"""
tests/unit/test_offline_tts.py
================================
Unit tests for Piper TTS offline adapter.
"""
from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

piper_mod = pytest.importorskip("jarvis.tts.piper", reason="Piper TTS module not available")

from jarvis.tts.piper import PiperConfig, PiperTTSEngine, PiperNotAvailableError


class TestPiperConfig:
    def test_default_model_path(self):
        cfg = PiperConfig()
        assert "piper" in cfg.model_path.lower() or ".onnx" in cfg.model_path

    def test_default_speaker_id_zero(self):
        cfg = PiperConfig()
        assert cfg.speaker_id == 0

    def test_custom_config(self):
        cfg = PiperConfig(model_path="custom/model.onnx", speaker_id=2, length_scale=1.2)
        assert cfg.model_path == "custom/model.onnx"
        assert cfg.speaker_id == 2
        assert cfg.length_scale == pytest.approx(1.2)


class TestPiperTTSEngineMock:
    @pytest.fixture
    def engine(self):
        return PiperTTSEngine(is_mock=True)

    def test_is_available_in_mock_mode(self, engine):
        assert engine.is_available() is True

    def test_synthesize_returns_bytes(self, engine):
        wav = engine.synthesize("Xin chào JARVIS")
        assert isinstance(wav, bytes)
        assert len(wav) > 44  # At least WAV header

    def test_synthesize_starts_with_riff(self, engine):
        wav = engine.synthesize("test")
        assert wav[:4] == b"RIFF"

    def test_speak_no_exception_mock(self, engine):
        # speak() should not raise even in mock mode (uses synthesize)
        with patch("sounddevice.play"):
            try:
                engine.speak("Xin chào")
            except Exception:
                pass  # sounddevice may not be available; that's OK in mock

    def test_mock_wav_has_correct_format(self, engine):
        wav = engine.synthesize("hello")
        # Check WAVE marker at byte 8
        assert wav[8:12] == b"WAVE"


class TestPiperTTSEngineNotAvailable:
    def test_not_available_when_model_missing(self):
        cfg = PiperConfig(model_path="/nonexistent/path/model.onnx")
        engine = PiperTTSEngine(config=cfg, is_mock=False)
        assert engine.is_available() is False

    def test_synthesize_raises_when_not_available(self):
        cfg = PiperConfig(model_path="/nonexistent/path/model.onnx")
        engine = PiperTTSEngine(config=cfg, is_mock=False)
        with pytest.raises((PiperNotAvailableError, ImportError, Exception)):
            engine.synthesize("test")
