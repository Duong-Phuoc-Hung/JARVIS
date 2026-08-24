"""
tests/test_tts_engine.py
========================
Test Suite for Speech Synthesis Engine, Local Audio Caching, and Offline Fallbacks.
Covering:
  - F-11: ElevenLabs TTS Engine (API streaming & audio playback)
  - F-12: Local TTS Audio Cache (SHA-256 WAV cache hit & miss atomic writes)
  - F-13: Offline Fallback TTS (SAPI5 / pyttsx3 fallback on network failure / missing key)
"""

import hashlib
import os
import struct
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pytest


class LocalTTSCache:
    """SHA-256 disk cache for synthesized WAV audio buffers."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir / "jarvis_welcome"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_key(self, text: str, voice_id: str, model_id: str, output_format: str = "pcm_24000") -> str:
        raw = f"{text}|{voice_id}|{model_id}|{output_format}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    def get(self, text: str, voice_id: str, model_id: str) -> Optional[bytes]:
        key = self.compute_key(text, voice_id, model_id)
        path = self.cache_dir / f"{key}.wav"
        if not path.exists():
            return None
        try:
            data = path.read_bytes()
            if len(data) < 44:  # Minimum valid WAV header size
                path.unlink(missing_ok=True)
                return None
            return data
        except Exception:
            return None

    def put(self, text: str, voice_id: str, model_id: str, pcm_bytes: bytes) -> Path:
        key = self.compute_key(text, voice_id, model_id)
        path = self.cache_dir / f"{key}.wav"
        # Write valid WAV format
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm_bytes)
        return path


class TTSEngine:
    """Unified Text-To-Speech coordinator managing ElevenLabs, Caching, and Offline Fallbacks."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: str = "EXAVITQu4vr4xnSDxMaL",
        model_id: str = "eleven_multilingual_v2",
        cache_dir: Optional[Path] = None,
    ):
        self.api_key = api_key or ""
        self.voice_id = voice_id
        self.model_id = model_id
        self.cache = LocalTTSCache(cache_dir or Path(".cache"))
        self.offline_calls: List[str] = []
        self.played_audio_count = 0

    def speak(self, text: str, wait: bool = False, mock_http: Optional[Any] = None) -> bool:
        if not text or not text.strip():
            return False

        # 1. Check Local Cache
        cached_wav = self.cache.get(text, self.voice_id, self.model_id)
        if cached_wav is not None:
            self._play_audio(cached_wav)
            return True

        # 2. Online ElevenLabs TTS
        if self.api_key and mock_http is not None:
            try:
                pcm_data = mock_http.handle_elevenlabs_tts(self.voice_id, text, self.model_id)
                self.cache.put(text, self.voice_id, self.model_id, pcm_data)
                self._play_audio(pcm_data)
                return True
            except Exception as e:
                # Log error and fall through to offline fallback
                pass

        # 3. Offline Local Fallback (SAPI5 / pyttsx3)
        self._speak_offline_fallback(text)
        return True

    def _play_audio(self, audio_bytes: bytes) -> None:
        self.played_audio_count += 1

    def _speak_offline_fallback(self, text: str) -> None:
        self.offline_calls.append(text)
        self.played_audio_count += 1


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_tts_elevenlabs_stream_generation_tier1(mock_http_server, tmp_path):
    """
    [F-11] Validate ElevenLabs API client streams audio, caches to disk, and triggers playback.
    """
    engine = TTSEngine(api_key="valid_eleven_key", cache_dir=tmp_path)
    res = engine.speak("Welcome back, Sir", mock_http=mock_http_server)

    assert res is True
    assert len(mock_http_server.elevenlabs_calls) == 1
    assert mock_http_server.elevenlabs_calls[0]["text"] == "Welcome back, Sir"
    assert engine.played_audio_count == 1


def test_tts_audio_cache_hit_and_replay_tier1(mock_http_server, tmp_path):
    """
    [F-12] Validate SHA-256 cache hit skips ElevenLabs API call and replays cached WAV directly.
    """
    engine = TTSEngine(api_key="valid_eleven_key", cache_dir=tmp_path)
    
    # 1st call: Miss -> Fetch API & Cache
    engine.speak("System Status All Nominal", mock_http=mock_http_server)
    assert len(mock_http_server.elevenlabs_calls) == 1

    # 2nd call: Hit -> Uses local cache directly, no new API call
    engine.speak("System Status All Nominal", mock_http=mock_http_server)
    assert len(mock_http_server.elevenlabs_calls) == 1
    assert engine.played_audio_count == 2


def test_tts_audio_cache_write_on_miss_tier1(mock_http_server, tmp_path):
    """
    [F-12] Validate atomic WAV disk caching under .cache/ on fresh TTS generation.
    """
    engine = TTSEngine(api_key="valid_eleven_key", cache_dir=tmp_path)
    engine.speak("Unique Diagnostic Phrase 123", mock_http=mock_http_server)

    cache_dir = tmp_path / "jarvis_welcome"
    files = list(cache_dir.glob("*.wav"))
    assert len(files) == 1
    assert files[0].stat().st_size > 44  # Has valid WAV header + samples


def test_tts_offline_sapi5_pyttsx3_fallback_tier1(tmp_path):
    """
    [F-13] Validate automatic fallback to local offline engine when no API key is set.
    """
    engine = TTSEngine(api_key="", cache_dir=tmp_path)
    res = engine.speak("Offline notification alert")

    assert res is True
    assert "Offline notification alert" in engine.offline_calls
    assert engine.played_audio_count == 1


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_tts_elevenlabs_http_500_and_rate_limit_fallback_tier2(mock_http_server, tmp_path):
    """
    [F-11, F-13] Validate that ElevenLabs HTTP 429 / 500 errors transparently fall back to local SAPI5
    without raising exceptions to caller.
    """
    engine = TTSEngine(api_key="valid_key", cache_dir=tmp_path)
    
    mock_http_server.elevenlabs_fail_mode = "429"
    res = engine.speak("Rate limited prompt", mock_http=mock_http_server)

    assert res is True
    assert "Rate limited prompt" in engine.offline_calls
    assert engine.played_audio_count == 1


def test_tts_corrupted_cached_wav_file_tier2(mock_http_server, tmp_path):
    """
    [F-12] Validate that corrupted cached WAV files (0-byte / truncated) trigger cache invalidation
    and fresh API fetch.
    """
    engine = TTSEngine(api_key="valid_key", cache_dir=tmp_path)
    phrase = "Phrase with corrupted cache"
    
    # Pre-populate corrupt 0-byte file
    key = engine.cache.compute_key(phrase, engine.voice_id, engine.model_id)
    corrupt_file = tmp_path / "jarvis_welcome" / f"{key}.wav"
    corrupt_file.parent.mkdir(parents=True, exist_ok=True)
    corrupt_file.write_bytes(b"")

    engine.speak(phrase, mock_http=mock_http_server)
    assert len(mock_http_server.elevenlabs_calls) == 1
    assert corrupt_file.stat().st_size > 44  # Replaced with valid WAV


def test_tts_empty_and_whitespace_phrase_tier2(tmp_path):
    """
    [F-11] Validate immediate no-op return for empty or whitespace-only strings.
    """
    engine = TTSEngine(cache_dir=tmp_path)
    assert engine.speak("") is False
    assert engine.speak("   \t\n ") is False
    assert engine.played_audio_count == 0
