"""
tests/unit/test_tts_cache.py
============================
Unit tests for Local TTS Audio Cache (jarvis.tts.cache).
"""
import hashlib
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from jarvis.tts.cache import LocalTTSCache, TTSAudioCache


def test_tts_cache_key_computation():
    """Verify SHA-256 key computation matches {text}|{voice_id}|{model_id}|{output_format}."""
    cache = TTSAudioCache()
    text = "Welcome home sir"
    voice = "test_voice_123"
    model = "eleven_multilingual_v2"
    fmt = "pcm_24000"

    expected = hashlib.sha256(f"{text}|{voice}|{model}|{fmt}".encode("utf-8")).hexdigest()[:24]
    actual = cache.compute_key(text, voice, model, fmt)
    assert actual == expected
    assert len(actual) == 24


def test_tts_cache_put_and_get(tmp_path):
    """Verify putting raw PCM bytes writes valid WAV file and get retrieves it."""
    cache = TTSAudioCache(cache_dir=tmp_path)
    text = "Status check nominal"
    pcm = np.zeros(24000, dtype=np.int16).tobytes()  # 1 second of 24kHz mono audio

    # Cache miss initially
    assert cache.get(text) is None

    # Put PCM
    saved_path = cache.put_pcm(
        text=text,
        voice_id="voice1",
        model_id="model1",
        output_format="pcm_24000",
        pcm_bytes=pcm,
        sample_rate=24000,
    )
    assert saved_path.is_file()
    assert saved_path.stat().st_size > 44

    # Verify WAV header parameters
    with wave.open(str(saved_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 24000

    # Cache hit
    hit_path = cache.get(text, voice_id="voice1", model_id="model1", output_format="pcm_24000")
    assert hit_path == saved_path


def test_tts_cache_corruption_handling(tmp_path):
    """Verify truncated or 0-byte corrupt WAV files are detected and invalidated."""
    cache = TTSAudioCache(cache_dir=tmp_path)
    text = "Corrupted phrase"

    # Write 0-byte corrupted file
    path = cache.get_cache_path(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")

    # Get should detect size < 44, delete corrupt file, and return None
    assert cache.get(text) is None
    assert not path.exists()


def test_local_tts_cache_bytes_interface(tmp_path):
    """Verify LocalTTSCache returns raw bytes on get()."""
    cache = LocalTTSCache(cache_dir=tmp_path)
    text = "Byte interface check"
    pcm = np.full(1000, 100, dtype=np.int16).tobytes()

    cache.put(text, "v1", "m1", pcm)
    wav_bytes = cache.get(text, "v1", "m1")
    assert wav_bytes is not None
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 44


def _write_minimal_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(np.zeros(100, dtype=np.int16).tobytes())


def test_play_wav_mock_audio_bypasses_physical_playback(tmp_path, monkeypatch):
    """
    Verify JARVIS_MOCK_AUDIO=1 makes play_wav() succeed without touching any
    physical playback backend, matching headless CI runners with no audio device.
    """
    monkeypatch.setenv("JARVIS_MOCK_AUDIO", "1")
    cache = TTSAudioCache(cache_dir=tmp_path)
    wav_path = tmp_path / "mock_audio.wav"
    _write_minimal_wav(wav_path)

    with patch("sounddevice.play", side_effect=RuntimeError("no audio device")) as mock_sd_play, \
         patch("winsound.PlaySound", side_effect=RuntimeError("Failed to play sound")) as mock_winsound:
        assert cache.play_wav(wav_path, wait=True) is True

    mock_sd_play.assert_not_called()
    mock_winsound.assert_not_called()


def test_play_wav_without_mock_audio_still_attempts_physical_playback(tmp_path, monkeypatch):
    """
    Verify that without JARVIS_MOCK_AUDIO set, play_wav() still exercises the
    real sounddevice/winsound backends (unchanged real-playback behavior).
    """
    monkeypatch.delenv("JARVIS_MOCK_AUDIO", raising=False)
    cache = TTSAudioCache(cache_dir=tmp_path)
    wav_path = tmp_path / "real_audio.wav"
    _write_minimal_wav(wav_path)

    with patch("sounddevice.play", side_effect=RuntimeError("no audio device")), \
         patch("winsound.PlaySound", side_effect=RuntimeError("Failed to play sound")) as mock_winsound:
        assert cache.play_wav(wav_path, wait=True) is False

    mock_winsound.assert_called_once()
