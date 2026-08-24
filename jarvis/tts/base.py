"""
jarvis/tts/base.py
==================
Abstract Base Class for JARVIS Text-To-Speech (TTS) Engines.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class TTSError(Exception):
    """Base exception for speech synthesis errors."""
    pass


class BaseTTSEngine(ABC):
    """Abstract interface that all TTS engines must implement."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}

    @abstractmethod
    def speak(self, text: str, voice_id: Optional[str] = None, wait: bool = False, **kwargs) -> bool:
        """
        Synthesize text and play audio immediately.

        Args:
            text: Text to vocalize.
            voice_id: Optional voice identifier override.
            wait: If True, blocks until audio playback finishes.

        Returns:
            bool: True if speech synthesis and playback succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def synthesize_to_bytes(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
        """
        Synthesize text into raw PCM or WAV audio bytes without playing.

        Args:
            text: Text to synthesize.
            voice_id: Optional voice identifier override.

        Returns:
            bytes: Audio buffer (16-bit PCM or WAV container).
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the engine is ready and operational (e.g. valid API key or local driver present).
        """
        pass

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return identifier name of the TTS engine."""
        pass

    @property
    def sample_rate(self) -> int:
        """Output sample rate in Hz (default 24000)."""
        return 24000
