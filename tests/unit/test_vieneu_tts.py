"""
tests/unit/test_vieneu_tts.py
=============================
Unit tests for VieNeu-TTS neural text-to-speech engine adapter,
voice cloning argument propagation, fail-closed availability,
and TTSManager routing integration.
"""
from __future__ import annotations

import io
import sys
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.tts.base import TTSError
from jarvis.tts.manager import TTSManager
from jarvis.tts.vieneu import VieNeuConfig, VieNeuTTSEngine


def test_vieneu_config_defaults() -> None:
    """Verify default parameters of VieNeuConfig."""
    cfg = VieNeuConfig()
    assert cfg.model_name == "pnnbao-ump/VieNeu-TTS-0.3B"
    assert cfg.codec_repo == "neuphonic/distill-neucodec"
    assert cfg.device == "cpu"
    assert cfg.emotion == "natural"
    assert cfg.reference_audio == ""
    assert cfg.sample_rate == 48000
    assert cfg.speed == 1.0
    assert cfg.enabled is True


def test_vieneu_engine_initialization() -> None:
    """Verify engine initialization with config dictionary and dataclass."""
    # From dict
    dict_engine = VieNeuTTSEngine({
        "model_name": "custom/model",
        "sample_rate": 24000,
        "device": "cpu",
        "emotion": "storytelling",
    })
    assert dict_engine.engine_name == "vieneu"
    assert dict_engine.sample_rate == 24000
    assert dict_engine.cfg.model_name == "custom/model"
    assert dict_engine.cfg.emotion == "storytelling"

    # From VieNeuConfig
    cfg = VieNeuConfig(sample_rate=48000, device="cpu")
    obj_engine = VieNeuTTSEngine(cfg)
    assert obj_engine.sample_rate == 48000
    assert obj_engine.cfg.device == "cpu"


def test_vieneu_availability_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify fail-closed behavior when vieneu is disabled or not installed."""
    # 1. Disabled in config -> False
    disabled_engine = VieNeuTTSEngine(VieNeuConfig(enabled=False))
    assert disabled_engine.is_available() is False

    # 2. Module not installed -> False
    engine = VieNeuTTSEngine(VieNeuConfig(enabled=True))
    with patch.dict(sys.modules, {"vieneu": None}):
        assert engine.is_available() is False

    # 3. Module present -> True
    mock_module = types.ModuleType("vieneu")
    mock_module.Vieneu = MagicMock()  # type: ignore[attr-defined]
    with patch.dict(sys.modules, {"vieneu": mock_module}):
        assert engine.is_available() is True


def test_vieneu_empty_text_raises_error() -> None:
    """Verify synthesizing empty string raises TTSError immediately."""
    engine = VieNeuTTSEngine()
    with pytest.raises(TTSError, match="Cannot synthesize empty text"):
        engine.synthesize_to_bytes("")

    with pytest.raises(TTSError, match="Cannot synthesize empty text"):
        engine.synthesize_to_bytes("    ")


def test_vieneu_synthesis_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify synthetic generation into standard 48kHz WAV bytes."""
    engine = VieNeuTTSEngine(VieNeuConfig(sample_rate=48000))

    # Mock Vieneu class and model instance
    mock_model_instance = MagicMock()
    # Return 0.5s of sine wave at 48kHz
    sample_rate = 48000
    t = np.linspace(0, 0.5, int(sample_rate * 0.5), endpoint=False)
    synthetic_audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    mock_model_instance.infer.return_value = synthetic_audio

    mock_vieneu_cls = MagicMock(return_value=mock_model_instance)
    mock_module = types.ModuleType("vieneu")
    mock_module.Vieneu = mock_vieneu_cls  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"vieneu": mock_module}):
        wav_bytes = engine.synthesize_to_bytes("Xin chào JARVIS, chúc bạn một ngày tốt lành.")

    assert wav_bytes.startswith(b"RIFF")
    mock_model_instance.infer.assert_called_once()
    assert mock_model_instance.infer.call_args[1]["text"] == "Xin chào JARVIS, chúc bạn một ngày tốt lành."

    # Validate WAV properties
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 48000
        assert wf.getnframes() > 0


def test_vieneu_voice_cloning_reference_propagation(tmp_path: Path) -> None:
    """Verify voice cloning reference audio path propagates correctly to infer."""
    ref_audio_file = tmp_path / "jarvis_voice_sample.wav"
    ref_audio_file.write_bytes(b"RIFF....WAVEfmt ....data....")

    engine = VieNeuTTSEngine(VieNeuConfig(sample_rate=48000, reference_audio=str(ref_audio_file)))

    mock_model_instance = MagicMock()
    mock_model_instance.infer.return_value = np.zeros(2400, dtype=np.float32)
    mock_vieneu_cls = MagicMock(return_value=mock_model_instance)
    mock_module = types.ModuleType("vieneu")
    mock_module.Vieneu = mock_vieneu_cls  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"vieneu": mock_module}):
        # 1. Uses config reference audio
        engine.synthesize_to_bytes("Cloning voice from config")
        assert mock_model_instance.infer.call_args[1]["ref_audio"] == str(ref_audio_file)

        # 2. Overrides with explicit ref_audio argument
        alt_ref = tmp_path / "alt_speaker.wav"
        alt_ref.write_bytes(b"RIFF....WAVEfmt ....data....")
        engine.synthesize_to_bytes("Cloning voice from argument", ref_audio=str(alt_ref))
        assert mock_model_instance.infer.call_args[1]["ref_audio"] == str(alt_ref)


def test_vieneu_speak_playback_windows() -> None:
    """Verify speak() triggers platform audio playback correctly."""
    engine = VieNeuTTSEngine()
    dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"

    with patch.object(engine, "synthesize_to_bytes", return_value=dummy_wav):
        with patch("sys.platform", "win32"):
            with patch("winsound.PlaySound") as mock_play:
                ok = engine.speak("Testing speak function", wait=False)
                assert ok is True
                mock_play.assert_called_once()


def test_tts_manager_vieneu_provider_wiring(tmp_path: Path) -> None:
    """Verify TTSManager instantiates VieNeuTTSEngine when provider is 'vieneu'."""
    mgr = TTSManager(
        config={
            "provider": "vieneu",
            "vieneu": {
                "model_name": "pnnbao-ump/VieNeu-TTS-0.3B",
                "sample_rate": 48000,
                "emotion": "natural",
            },
            "cache": {"enabled": False},
        }
    )
    try:
        assert isinstance(mgr.primary_engine, VieNeuTTSEngine)
        assert mgr.primary_engine.cfg.model_name == "pnnbao-ump/VieNeu-TTS-0.3B"
        assert mgr.primary_engine.cfg.sample_rate == 48000
    finally:
        mgr.stop()
