"""
Speech-to-Text (STT) Subsystem for JARVIS.
Provides multi-provider speech transcription (OpenAI Whisper REST, Local Faster-Whisper, Windows SAPI, Mock),
real-time Voice Activity Detection (VAD) buffer segmentation, and zero-crash fallback cascading.
"""
from __future__ import annotations

from jarvis.stt.engine import (
    BaseSTTEngine,
    FasterWhisperSTT,
    LocalWhisperSTT,
    MockSTTEngine,
    OpenAIWhisperAPI,
    OpenAIWhisperSTT,
    STTEngine,
    STTError,
    VADSegmenter,
    WindowsSpeechSTT,
    audio_to_float32,
    audio_to_wav_bytes,
    float32_to_pcm16_wav_bytes,
    resample_audio,
)

__all__ = [
    "BaseSTTEngine",
    "STTError",
    "STTEngine",
    "OpenAIWhisperSTT",
    "OpenAIWhisperAPI",
    "FasterWhisperSTT",
    "LocalWhisperSTT",
    "WindowsSpeechSTT",
    "MockSTTEngine",
    "VADSegmenter",
    "audio_to_float32",
    "audio_to_wav_bytes",
    "float32_to_pcm16_wav_bytes",
    "resample_audio",
]
