"""
tests/unit/test_tts_engines.py
==============================
Unit tests for TTS Engines and Coordinator (ElevenLabs, SAPI5, TTSManager).
"""
import time

import pytest

from jarvis.tts.base import BaseTTSEngine, TTSError
from jarvis.tts.cache import TTSAudioCache
from jarvis.tts.elevenlabs import ElevenLabsTTS
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager


def test_elevenlabs_engine_availability():
    """Verify ElevenLabs availability check based on API key presence."""
    engine_no_key = ElevenLabsTTS({"api_key": ""})
    assert engine_no_key.is_available() is False

    engine_with_key = ElevenLabsTTS({"api_key": "sk_test_12345"})
    assert engine_with_key.is_available() is True


def test_elevenlabs_synthesize_mock_http(mock_http_server):
    """Verify ElevenLabs synthesis via mock HTTP server fixture."""
    engine = ElevenLabsTTS({"api_key": "valid_key", "voice_id": "test_voice"})
    pcm_data = engine.synthesize_to_bytes("Hello from ElevenLabs", mock_http=mock_http_server)
    assert pcm_data is not None
    assert len(pcm_data) > 0
    assert len(mock_http_server.elevenlabs_calls) == 1


def test_sapi5_fallback_tts():
    """Verify SAPI5 fallback synthesis records spoken history."""
    engine = SAPI5FallbackTTS()
    assert engine.is_available() is True
    res = engine.speak("Offline fallback alert")
    assert res is True
    assert "Offline fallback alert" in engine.spoken_history


def test_tts_manager_cache_and_fallback_routing(mock_http_server, tmp_path):
    """Verify TTSManager coordinates cache hits, online API, and fallback."""
    mgr = TTSManager(
        config={
            "cache": {"enabled": True, "dir": str(tmp_path)},
            "elevenlabs": {"api_key": "valid_key"},
        }
    )

    # 1. First call: Cache miss -> calls ElevenLabs via mock_http
    res1 = mgr.speak("Phrase Alpha", wait=True, mock_http=mock_http_server)
    assert res1 is True
    assert len(mock_http_server.elevenlabs_calls) == 1

    # 2. Second call: Cache hit -> does NOT call ElevenLabs again
    res2 = mgr.speak("Phrase Alpha", wait=True, mock_http=mock_http_server)
    assert res2 is True
    assert len(mock_http_server.elevenlabs_calls) == 1

    # 3. Third call: Error in ElevenLabs -> falls back to SAPI5
    mock_http_server.elevenlabs_fail_mode = "500"
    res3 = mgr.speak("Phrase Beta", wait=True, mock_http=mock_http_server)
    assert res3 is True
    assert "Phrase Beta" in mgr.fallback_engine.spoken_history

    mgr.stop()
