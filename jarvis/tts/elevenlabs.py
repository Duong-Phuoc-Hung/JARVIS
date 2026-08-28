"""
jarvis/tts/elevenlabs.py
========================
ElevenLabs Cloud Neural TTS Engine with REST fallback and stream assembly.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

from jarvis.tts.base import BaseTTSEngine, TTSError

log = logging.getLogger("jarvis.tts.elevenlabs")


class ElevenLabsTTS(BaseTTSEngine):
    """High-fidelity neural voice synthesis via ElevenLabs API."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        if "api_key" in self.config:
            self.api_key = str(self.config.get("api_key") or "").strip()
        else:
            self.api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        self.voice_id = (
            self.config.get("voice_id")
            or os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
        ).strip()
        self.model_id = (
            self.config.get("model_id")
            or os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
        ).strip()
        self.output_format = (
            self.config.get("output_format")
            or os.environ.get("ELEVENLABS_OUTPUT_FORMAT", "pcm_24000")
        ).strip()
        self._sample_rate = int(
            self.config.get("sample_rate")
            or os.environ.get("ELEVENLABS_PCM_SAMPLE_RATE", 24000)
        )

    @property
    def engine_name(self) -> str:
        return "elevenlabs"

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def is_available(self) -> bool:
        """Available if a non-empty API key is present."""
        return bool(self.api_key)

    def synthesize_to_bytes(
        self,
        text: str,
        voice_id: str | None = None,
        model_id: str | None = None,
        output_format: str | None = None,
        mock_http: Any | None = None,
        **kwargs,
    ) -> bytes:
        """Fetches raw PCM bytes from ElevenLabs API or mock HTTP handler."""
        if not self.is_available() and mock_http is None:
            raise TTSError("ElevenLabs API key is missing or invalid.")

        target_voice = voice_id or self.voice_id
        target_model = model_id or self.model_id
        target_format = output_format or self.output_format

        # 0. Mock HTTP server support for unit tests
        if mock_http is not None:
            if hasattr(mock_http, "handle_elevenlabs_tts"):
                return mock_http.handle_elevenlabs_tts(target_voice, text, target_model)

        # 1. Try official ElevenLabs SDK if installed
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=self.api_key)
            audio_generator = client.text_to_speech.convert(
                voice_id=target_voice,
                text=text,
                model_id=target_model,
                output_format=target_format,
            )
            raw_bytes = b"".join(audio_generator)
            if raw_bytes:
                return raw_bytes
        except ImportError:
            log.debug("elevenlabs package not installed, using REST HTTP client")
        except Exception as e:
            log.warning("ElevenLabs SDK synthesis failed: %s", e)

        # 2. Direct HTTP REST fallback via requests
        try:
            import requests
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice}?output_format={target_format}"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": target_model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200 and resp.content:
                return resp.content
            raise TTSError(f"ElevenLabs HTTP Error {resp.status_code}: {resp.text}")
        except Exception as e:
            raise TTSError(f"ElevenLabs synthesis failed: {e}") from e

    def speak(self, text: str, voice_id: str | None = None, wait: bool = False, **kwargs) -> bool:
        """Synthesize and play immediately using sounddevice."""
        try:
            pcm_bytes = self.synthesize_to_bytes(text, voice_id=voice_id, **kwargs)
            if not pcm_bytes:
                return False
            import sounddevice as sd
            pcm_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
            pcm_f = pcm_i16.astype(np.float32) / 32768.0
            sd.play(pcm_f, samplerate=self.sample_rate)
            if wait:
                sd.wait()
            return True
        except Exception as e:
            log.warning("ElevenLabs speak execution failed: %s", e)
            return False
