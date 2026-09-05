"""
tests/unit/test_tiered_stt.py
=============================
TDD Unit test suite for TieredSTTEngine:
Multi-tier Speech-to-Text coordinator with VAD silence gating, SNR estimation,
Whisper local offline vs Cloud fallback, and deadline enforcement.
"""
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock

from jarvis.stt.engine import (
    BaseSTTEngine,
    TranscriptionResult,
    TieredSTTEngine,
)


class TestTieredSTTEngineSlice1:
    """Slice 1: Core TranscriptionResult contract and baseline local Whisper execution."""

    def test_transcription_result_contract(self) -> None:
        res = TranscriptionResult(
            text="xin chào",
            confidence=0.92,
            engine_used="whisper_local",
            latency_ms=120.5,
            snr_db=18.4,
            is_silent=False,
        )
        assert res.text == "xin chào"
        assert res.confidence == 0.92
        assert res.engine_used == "whisper_local"
        assert res.latency_ms == 120.5
        assert res.snr_db == 18.4
        assert res.is_silent is False

        # Must be frozen / immutable
        with pytest.raises(Exception):
            res.text = "thay đổi"  # type: ignore[misc]

    def test_tiered_stt_baseline_local_resolution(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_local.is_available.return_value = True
        mock_local.transcribe.return_value = "bật đèn phòng khách"

        # Synthetic audio: 1 second of 16kHz sine wave (healthy signal)
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        engine = TieredSTTEngine(
            config={"local_confidence_threshold": 0.6},
            local_engine=mock_local,
        )

        result = engine.transcribe(audio)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "bật đèn phòng khách"
        assert result.engine_used == "whisper_local"
        assert result.confidence >= 0.6
        assert result.is_silent is False
        assert result.snr_db > 10.0
        assert result.latency_ms >= 0.0
        mock_local.transcribe.assert_called_once()


class TestTieredSTTEngineSlice2CloudEscalation:
    """Slice 2: Low SNR or low confidence local Whisper triggers escalation to Cloud."""

    def test_low_snr_escalates_to_cloud(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_local.is_available.return_value = True
        mock_local.transcribe.return_value = "bật đèn"  # local noisy attempt

        mock_cloud = MagicMock(spec=BaseSTTEngine)
        mock_cloud.is_available.return_value = True
        mock_cloud.transcribe.return_value = "bật đèn chùm phòng khách"

        # Construct noisy audio: weak signal (amplitude 0.05) + loud Gaussian noise (sigma 0.08)
        np.random.seed(42)
        noise = np.random.normal(0.0, 0.08, 16000).astype(np.float32)
        signal = (0.05 * np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, 16000))).astype(np.float32)
        noisy_audio = signal + noise

        engine = TieredSTTEngine(
            config={"min_snr_threshold_db": 10.0, "local_confidence_threshold": 0.6},
            local_engine=mock_local,
            cloud_engine=mock_cloud,
        )

        result = engine.transcribe(noisy_audio)

        assert isinstance(result, TranscriptionResult)
        assert result.engine_used == "cloud"
        assert result.text == "bật đèn chùm phòng khách"
        assert result.snr_db < 10.0
        mock_cloud.transcribe.assert_called_once()

    def test_low_confidence_local_escalates_to_cloud(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_local.is_available.return_value = True
        # Local engine returns empty or unconfident result
        mock_local.transcribe.return_value = ""

        mock_cloud = MagicMock(spec=BaseSTTEngine)
        mock_cloud.is_available.return_value = True
        mock_cloud.transcribe.return_value = "mở trình duyệt chrome"

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        engine = TieredSTTEngine(
            config={"min_snr_threshold_db": 5.0, "local_confidence_threshold": 0.6},
            local_engine=mock_local,
            cloud_engine=mock_cloud,
        )

        result = engine.transcribe(audio)

        assert result.engine_used == "cloud"
        assert result.text == "mở trình duyệt chrome"
        mock_cloud.transcribe.assert_called_once()


class TestTieredSTTEngineSlice3DeadlineAndEmergencyFallback:
    """Slice 3: Real-time deadline enforcement and emergency SAPI failover."""

    def test_tight_deadline_bypasses_slow_cloud_and_uses_fast_fallback(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_local.is_available.return_value = False

        mock_cloud = MagicMock(spec=BaseSTTEngine)
        mock_cloud.is_available.return_value = True

        mock_fallback = MagicMock(spec=BaseSTTEngine)
        mock_fallback.is_available.return_value = True
        mock_fallback.transcribe.return_value = "dừng lại"
        mock_fallback.engine_name = "sapi_fallback"

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        engine = TieredSTTEngine(
            config={"cloud_expected_latency_ms": 500.0},
            local_engine=mock_local,
            cloud_engine=mock_cloud,
            fallback_engine=mock_fallback,
        )

        # Deadline is 200ms, which is lower than cloud_expected_latency_ms (500ms)
        result = engine.transcribe(audio, deadline_ms=200.0)

        assert result.engine_used == "sapi_fallback"
        assert result.text == "dừng lại"
        mock_cloud.transcribe.assert_not_called()
        mock_fallback.transcribe.assert_called_once()

    def test_cloud_and_local_exceptions_route_to_fallback_zero_crash(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_local.is_available.return_value = True
        mock_local.transcribe.side_effect = RuntimeError("Local CUDA OOM")

        mock_cloud = MagicMock(spec=BaseSTTEngine)
        mock_cloud.is_available.return_value = True
        mock_cloud.transcribe.side_effect = ConnectionError("Cloud network timeout")

        mock_fallback = MagicMock(spec=BaseSTTEngine)
        mock_fallback.is_available.return_value = True
        mock_fallback.transcribe.return_value = "tắt máy tính"
        mock_fallback.engine_name = "sapi_fallback"

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        engine = TieredSTTEngine(
            local_engine=mock_local,
            cloud_engine=mock_cloud,
            fallback_engine=mock_fallback,
        )

        result = engine.transcribe(audio)

        assert result.engine_used == "sapi_fallback"
        assert result.text == "tắt máy tính"
        mock_fallback.transcribe.assert_called_once()


class TestTieredSTTEngineSlice4VADSilence:
    """Slice 4: Integrated VAD silence gating with zero inference overhead on silence."""

    def test_pure_zeros_returns_silent_result_without_invoking_engines(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_cloud = MagicMock(spec=BaseSTTEngine)
        mock_fallback = MagicMock(spec=BaseSTTEngine)

        zeros_audio = np.zeros(16000, dtype=np.float32)

        engine = TieredSTTEngine(
            config={"vad_silence_threshold_rms": 0.002},
            local_engine=mock_local,
            cloud_engine=mock_cloud,
            fallback_engine=mock_fallback,
        )

        res = engine.transcribe(zeros_audio)

        assert isinstance(res, TranscriptionResult)
        assert res.is_silent is True
        assert res.text == ""
        assert res.engine_used == "vad_silence"
        assert res.confidence == 0.0
        assert res.latency_ms < 50.0

        mock_local.transcribe.assert_not_called()
        mock_cloud.transcribe.assert_not_called()
        mock_fallback.transcribe.assert_not_called()

    def test_sub_threshold_ambient_noise_returns_silent(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_cloud = MagicMock(spec=BaseSTTEngine)

        # Ambient noise with very low amplitude (RMS ~ 0.0003 < 0.002)
        np.random.seed(42)
        ambient_noise = np.random.normal(0.0, 0.0003, 16000).astype(np.float32)

        engine = TieredSTTEngine(
            config={"vad_silence_threshold_rms": 0.002},
            local_engine=mock_local,
            cloud_engine=mock_cloud,
        )

        res = engine.transcribe(ambient_noise)

        assert res.is_silent is True
        assert res.text == ""
        assert res.engine_used == "vad_silence"
        mock_local.transcribe.assert_not_called()
        mock_cloud.transcribe.assert_not_called()

    def test_vad_segmenter_bypass_when_no_speech_detected(self) -> None:
        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_vad = MagicMock()
        mock_vad.is_speech.return_value = False  # VAD says no speech

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (0.05 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        engine = TieredSTTEngine(
            local_engine=mock_local,
            vad_segmenter=mock_vad,
        )

        res = engine.transcribe(audio)

        assert res.is_silent is True
        assert res.text == ""
        assert res.engine_used == "vad_silence"
        mock_local.transcribe.assert_not_called()
        mock_vad.is_speech.assert_called_once()


class TestTieredSTTEngineSlice5MasterWiring:
    """Slice 5: Master STTEngine coordinator wiring with provider='tiered' and backward compatibility."""

    def test_stt_engine_initializes_tiered_stt_when_configured(self) -> None:
        from jarvis.stt.engine import STTEngine

        stt = STTEngine(
            config={
                "provider": "tiered",
                "tiered": {
                    "min_snr_threshold_db": 12.0,
                    "cloud_expected_latency_ms": 350.0,
                },
            }
        )

        assert isinstance(stt.primary_engine, TieredSTTEngine)
        assert stt.primary_engine.min_snr_threshold_db == 12.0
        assert stt.primary_engine.cloud_expected_latency_ms == 350.0

    def test_master_stt_transcribe_backward_compatible_str_and_return_result(self) -> None:
        from jarvis.stt.engine import STTEngine

        mock_local = MagicMock(spec=BaseSTTEngine)
        mock_local.is_available.return_value = True
        mock_local.transcribe.return_value = "chào buổi sáng"

        tiered = TieredSTTEngine(
            config={"min_snr_threshold_db": 5.0},
            local_engine=mock_local,
        )

        stt = STTEngine(
            config={"provider": "tiered"},
            primary_engine=tiered,
        )

        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        # Standard caller expects str
        text_res = stt.transcribe(audio)
        assert isinstance(text_res, str)
        assert text_res == "chào buổi sáng"

        # Advanced caller can request full TranscriptionResult
        full_res = stt.transcribe(audio, return_result=True)
        assert isinstance(full_res, TranscriptionResult)
        assert full_res.text == "chào buổi sáng"
        assert full_res.engine_used == "whisper_local"
        assert full_res.is_silent is False


