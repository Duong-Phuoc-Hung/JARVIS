"""
Text-To-Speech (TTS) subsystem for JARVIS.
Provides high-fidelity ElevenLabs neural speech, offline Windows SAPI5 / pyttsx3 fallback,
SHA-256 local audio disk caching, and asynchronous speech queue coordination.
"""
from jarvis.tts.base import BaseTTSEngine, TTSError
from jarvis.tts.cache import LocalTTSCache, TTSAudioCache
from jarvis.tts.elevenlabs import ElevenLabsTTS
from jarvis.tts.engine import TTSEngine
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager

__all__ = [
    "BaseTTSEngine",
    "TTSError",
    "TTSAudioCache",
    "LocalTTSCache",
    "ElevenLabsTTS",
    "SAPI5FallbackTTS",
    "TTSManager",
    "TTSEngine",
]
