"""
tests/unit/test_vieneu_tts.py
=============================
Unit tests for VieNeu-TTS neural text-to-speech engine adapter,
voice cloning argument propagation, fail-closed availability,
and TTSManager routing integration.
"""
from __future__ import annotations

import io
import os
import sys
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.tts.base import TTSError
from jarvis.tts.manager import TTSManager
from jarvis.tts.vieneu import VieNeuConfig, VieNeuTTSEngine, VoiceEmbeddingCache


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
    """Verify synthetic generation into raw PCM bytes and WAV container bytes."""
    engine = VieNeuTTSEngine(VieNeuConfig(sample_rate=48000))

    # Mock Vieneu class and model instance
    mock_model_instance = MagicMock()
    # Return 0.5s of sine wave at 48kHz (24000 samples)
    sample_rate = 48000
    t = np.linspace(0, 0.5, int(sample_rate * 0.5), endpoint=False)
    synthetic_audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    mock_model_instance.infer.return_value = synthetic_audio

    mock_vieneu_cls = MagicMock(return_value=mock_model_instance)
    mock_module = types.ModuleType("vieneu")
    mock_module.Vieneu = mock_vieneu_cls  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"vieneu": mock_module}):
        # 1. synthesize_to_bytes returns raw 16-bit PCM bytes (2 bytes per sample)
        pcm_bytes = engine.synthesize_to_bytes("Xin chào JARVIS, chúc bạn một ngày tốt lành.")
        assert len(pcm_bytes) == len(synthetic_audio) * 2
        # Ensure it does not start with RIFF header
        assert not pcm_bytes.startswith(b"RIFF")

        # 2. synthesize_to_wav_bytes returns standard WAV container
        wav_bytes = engine.synthesize_to_wav_bytes("Xin chào JARVIS, chúc bạn một ngày tốt lành.")
        assert wav_bytes.startswith(b"RIFF")

    # Validate WAV properties
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 48000
        assert wf.getnframes() == len(synthetic_audio)


def test_vieneu_cache_defensive_unpacking(tmp_path: Path) -> None:
    """Verify TTSAudioCache.save_wav_atomic defensively strips WAV header if passed a full container."""
    from jarvis.tts.cache import TTSAudioCache

    cache = TTSAudioCache(cache_dir=tmp_path)
    # Generate a real WAV container
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        wf.writeframes(np.zeros(1000, dtype=np.int16).tobytes())
    wav_container = buf.getvalue()

    # Pass full WAV container into save_wav_atomic
    saved = cache.save_wav_atomic(tmp_path / "test_defensive.wav", wav_container, sample_rate=48000)
    assert saved.is_file()

    # Inspect resulting file: must NOT contain nested RIFF in audio frames
    with wave.open(str(saved), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        assert not frames.startswith(b"RIFF")
        assert len(frames) == 2000


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
    """Verify speak() triggers high-fidelity sounddevice or winsound fallback."""
    engine = VieNeuTTSEngine()
    dummy_pcm = np.zeros(1000, dtype=np.int16).tobytes()

    with patch.object(engine, "synthesize_to_bytes", return_value=dummy_pcm):
        # 1. Primary sounddevice path
        mock_sd = MagicMock()
        with patch.dict(sys.modules, {"sounddevice": mock_sd}):
            ok = engine.speak("Testing speak function via sounddevice", wait=True)
            assert ok is True
            mock_sd.play.assert_called_once()
            mock_sd.wait.assert_called_once()

        # 2. Winsound fallback path when sounddevice fails
        with patch.dict(sys.modules, {"sounddevice": None}):
            with patch("sys.platform", "win32"):
                with patch("winsound.PlaySound") as mock_play:
                    ok2 = engine.speak("Testing speak function via winsound", wait=False)
                    assert ok2 is True
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


def test_voice_embedding_cache_in_memory() -> None:
    """Verify in-memory operations of VoiceEmbeddingCache."""
    cache = VoiceEmbeddingCache()
    assert len(cache) == 0
    assert cache.keys() == []

    emb1 = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    cache.set("voice_vi_01", emb1, persist=False)
    assert len(cache) == 1
    assert cache.has("voice_vi_01") is True
    assert cache.has("voice_vi_02") is False

    retrieved = cache.get("voice_vi_01")
    assert retrieved is not None
    np.testing.assert_array_almost_equal(retrieved, emb1)

    # Delete
    assert cache.delete("voice_vi_01", persist=False) is True
    assert cache.delete("voice_vi_01", persist=False) is False
    assert len(cache) == 0

    # Clear
    cache.set("a", np.array([1.0]), persist=False)
    cache.set("b", np.array([2.0]), persist=False)
    assert len(cache) == 2
    cache.clear(persist=False)
    assert len(cache) == 0


def test_voice_embedding_cache_atomic_persistence(tmp_path: Path) -> None:
    """Verify Windows atomic persistence of VoiceEmbeddingCache via .npz."""
    npz_path = tmp_path / "voice_embeddings.npz"
    cache = VoiceEmbeddingCache(persist_path=npz_path)

    emb_friday = np.array([0.42, 0.88, -0.15], dtype=np.float32)
    cache.set("friday", emb_friday)
    assert npz_path.is_file()

    # Create fresh instance pointing to same file
    cache2 = VoiceEmbeddingCache(persist_path=npz_path)
    assert len(cache2) == 1
    assert cache2.has("friday") is True
    retrieved = cache2.get("friday")
    assert retrieved is not None
    np.testing.assert_array_almost_equal(retrieved, emb_friday)


def test_voice_embedding_cache_windows_retry_resilience(tmp_path: Path) -> None:
    """Verify retry loop handles temporary file locking (WinError 5 / PermissionError)."""
    npz_path = tmp_path / "test_retry.npz"
    cache = VoiceEmbeddingCache(persist_path=npz_path)

    attempts = 0
    orig_replace = os.replace

    def mock_replace(src: Any, dst: Any) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("WinError 5: Access is denied")
        orig_replace(src, dst)

    with patch("os.replace", side_effect=mock_replace):
        cache.set("jarvis_warm", np.array([1.0, 2.0, 3.0], dtype=np.float32))

    assert attempts == 3
    assert npz_path.is_file()


def test_vieneu_engine_uses_voice_embedding_cache() -> None:
    """Verify synthesize_to_bytes leverages cached speaker embedding."""
    cache = VoiceEmbeddingCache()
    emb = np.array([0.5, 0.5, 0.5], dtype=np.float32)
    cache.set("cached_speaker", emb, persist=False)

    engine = VieNeuTTSEngine(embedding_cache=cache)

    mock_model_instance = MagicMock()
    mock_model_instance.infer.return_value = np.zeros(2400, dtype=np.float32)
    mock_vieneu_cls = MagicMock(return_value=mock_model_instance)
    mock_module = types.ModuleType("vieneu")
    mock_module.Vieneu = mock_vieneu_cls  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"vieneu": mock_module}):
        engine.synthesize_to_bytes("Xin chào Việt Nam", voice_id="cached_speaker")

        assert mock_model_instance.infer.called
        kwargs = mock_model_instance.infer.call_args[1]
        assert "speaker_embedding" in kwargs
        np.testing.assert_array_almost_equal(kwargs["speaker_embedding"], emb)


def test_voice_embedding_cache_fingerprint_mismatch_invalidation(tmp_path: Path) -> None:
    """Verify cache is invalidated if loaded under different model architecture."""
    npz_path = tmp_path / "fingerprint_test.npz"
    cache1 = VoiceEmbeddingCache(persist_path=npz_path, model_fingerprint="v1_0.3B_48k")
    cache1.set("speaker_a", np.array([1.0, 2.0], dtype=np.float32))
    assert npz_path.is_file()

    # Load with mismatched fingerprint (e.g. model upgraded to v2_0.5B_48k)
    cache2 = VoiceEmbeddingCache(persist_path=npz_path, model_fingerprint="v2_0.5B_48k")
    assert len(cache2) == 0  # Invalidation protects against corrupted audio


def test_voice_embedding_cache_lru_eviction() -> None:
    """Verify LRU capacity bounds in-memory RAM usage."""
    cache = VoiceEmbeddingCache(max_cached_voices=2)
    cache.set("voice_1", np.array([1.0]), persist=False)
    cache.set("voice_2", np.array([2.0]), persist=False)
    assert len(cache) == 2

    # Adding 3rd voice should evict oldest ("voice_1")
    cache.set("voice_3", np.array([3.0]), persist=False)
    assert len(cache) == 2
    assert cache.has("voice_1") is False
    assert cache.has("voice_2") is True
    assert cache.has("voice_3") is True


