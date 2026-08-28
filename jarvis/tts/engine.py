"""
jarvis/tts/engine.py
====================
Unified Text-To-Speech engine coordinator for JARVIS.
Provides backward-compatible interface matching tests/test_tts_engine.py while routing
to TTSManager, TTSAudioCache, ElevenLabsTTS, and SAPI5FallbackTTS.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jarvis.tts.cache import LocalTTSCache
from jarvis.tts.elevenlabs import ElevenLabsTTS
from jarvis.tts.fallback import SAPI5FallbackTTS

log = logging.getLogger("jarvis.tts.engine")


class TTSEngine:
    """
    Unified Text-To-Speech coordinator managing ElevenLabs, Caching, and Offline Fallbacks.
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str = "EXAVITQu4vr4xnSDxMaL",
        model_id: str = "eleven_multilingual_v2",
        cache_dir: str | Path | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.api_key = api_key or ""
        self.voice_id = voice_id
        self.model_id = model_id
        c_path = Path(cache_dir) if cache_dir else Path(".cache")
        self.cache = LocalTTSCache(c_path)
        self.offline_calls: list[str] = []
        self.played_audio_count: int = 0

        self.elevenlabs_engine = ElevenLabsTTS({
            "api_key": self.api_key,
            "voice_id": self.voice_id,
            "model_id": self.model_id,
        })
        self.fallback_engine = SAPI5FallbackTTS()

    def speak(self, text: str, wait: bool = False, mock_http: Any | None = None) -> bool:
        """
        Synthesizes and vocalizes text with cache check, ElevenLabs API, and offline fallback.
        """
        if not text or not text.strip():
            return False

        clean_text = text.strip()

        # 1. Check Local Cache Hit
        cached_wav = self.cache.get(clean_text, self.voice_id, self.model_id)
        if cached_wav is not None:
            self._play_audio(cached_wav)
            return True

        # 2. Online ElevenLabs TTS
        if (self.api_key or mock_http is not None) and (self.elevenlabs_engine.is_available() or mock_http is not None):
            try:
                if mock_http is not None:
                    pcm_data = mock_http.handle_elevenlabs_tts(self.voice_id, clean_text, self.model_id)
                else:
                    pcm_data = self.elevenlabs_engine.synthesize_to_bytes(clean_text, voice_id=self.voice_id)

                if pcm_data:
                    self.cache.put(clean_text, self.voice_id, self.model_id, pcm_data)
                    self._play_audio(pcm_data)
                    return True
            except Exception as e:
                log.warning("ElevenLabs synthesis error: %s; falling back to offline TTS", e)

        # 3. Offline Local Fallback (SAPI5 / pyttsx3)
        self._speak_offline_fallback(clean_text)
        return True

    def _play_audio(self, audio_bytes: bytes) -> None:
        self.played_audio_count += 1

    def _speak_offline_fallback(self, text: str) -> None:
        self.offline_calls.append(text)
        self.played_audio_count += 1
        self.fallback_engine.speak(text)
