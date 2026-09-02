"""
tests/unit/test_stt_preload.py
==============================
Unit tests for Faster-Whisper background model pre-loading and VAD trimming (Sprint 2 R3).
Covers:
  - Background daemon thread spawning on FasterWhisperSTT initialization.
  - Thread-safe lazy/eager model loading synchronization.
  - VAD filtering parameter passing to WhisperModel.transcribe (vad_filter=True, min_silence_duration_ms=500).
  - Configurable preload toggle and custom VAD overrides.
  - Model loaded state detection.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.stt.engine import FasterWhisperSTT, STTError


def test_faster_whisper_preload_spawns_daemon_thread():
    """Verify FasterWhisperSTT.__init__ spawns a daemon thread when preload=True."""
    with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
        with patch.object(FasterWhisperSTT, "_get_model") as mock_get_model:
            stt = FasterWhisperSTT({"preload": True, "model_size": "tiny"})
            assert stt._preload_thread is not None
            assert stt._preload_thread.is_alive() or mock_get_model.called
            assert stt._preload_thread.daemon is True
            assert "Preload" in stt._preload_thread.name


def test_faster_whisper_preload_disabled_when_config_false():
    """Verify FasterWhisperSTT does not spawn preload thread when preload=False."""
    with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
        stt = FasterWhisperSTT({"preload": False, "model_size": "tiny"})
        assert stt._preload_thread is None
        assert stt.is_model_loaded is False


def test_faster_whisper_thread_safe_get_model_synchronization():
    """Verify concurrent access to _get_model loads the model once and returns same instance."""
    mock_model_instance = MagicMock()

    with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
        with patch("jarvis.stt.engine.WhisperModel", return_value=mock_model_instance) as mock_wm:
            stt = FasterWhisperSTT({"preload": False, "model_size": "tiny"})
            assert stt.is_model_loaded is False

            results = []
            def worker():
                m = stt._get_model()
                results.append(m)

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(results) == 10
            for r in results:
                assert r is mock_model_instance
            # WhisperModel constructor must be called exactly once
            assert mock_wm.call_count == 1
            assert stt.is_model_loaded is True


def test_faster_whisper_vad_filter_and_parameters_passed_to_transcribe():
    """Verify vad_filter=True and min_silence_duration_ms=500 are passed to WhisperModel.transcribe."""
    mock_model_instance = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "xin chào jarvis"
    mock_info = MagicMock()
    mock_model_instance.transcribe.return_value = ([mock_segment], mock_info)

    with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
        with patch("jarvis.stt.engine.WhisperModel", return_value=mock_model_instance):
            stt = FasterWhisperSTT({"preload": False, "model_size": "tiny"})
            # Audio array with speech energy
            audio = np.sin(np.linspace(0, 2 * np.pi * 440, 16000)).astype(np.float32) * 0.5

            result = stt.transcribe(audio, language="vi")
            assert result == "xin chào jarvis"

            mock_model_instance.transcribe.assert_called_once()
            _, kwargs = mock_model_instance.transcribe.call_args
            assert kwargs.get("vad_filter") is True
            assert kwargs.get("vad_parameters") == {"min_silence_duration_ms": 500}
            assert kwargs.get("condition_on_previous_text") is False


def test_faster_whisper_vad_override_parameters():
    """Verify custom VAD settings via transcribe kwargs or config are respected."""
    mock_model_instance = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "tắt đèn"
    mock_model_instance.transcribe.return_value = ([mock_segment], MagicMock())

    with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True):
        with patch("jarvis.stt.engine.WhisperModel", return_value=mock_model_instance):
            stt = FasterWhisperSTT({"preload": False})
            audio = np.sin(np.linspace(0, 2 * np.pi * 440, 16000)).astype(np.float32) * 0.5

            stt.transcribe(
                audio,
                vad_filter=False,
                vad_parameters={"min_silence_duration_ms": 300},
            )

            _, kwargs = mock_model_instance.transcribe.call_args
            assert kwargs.get("vad_filter") is False
            assert kwargs.get("vad_parameters") == {"min_silence_duration_ms": 300}
