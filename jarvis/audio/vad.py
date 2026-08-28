"""
jarvis/audio/vad.py
===================
Voice Activity Detection (VAD) Engine.
Detects speech vs silence using energy-based RMS detection (always available)
with optional webrtcvad integration for higher accuracy.

Features:
  - Energy-based RMS threshold detection (no external deps)
  - Optional webrtcvad backend for improved accuracy
  - listen_for_speech(): captures complete utterance with silence detection
  - Thread-safe, headless/CI mock mode
"""
from __future__ import annotations

import logging
import math
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("jarvis.audio.vad")


@dataclass
class VoiceActivityConfig:
    sample_rate: int = 16000
    frame_duration_ms: int = 30
    aggressiveness: int = 2            # webrtcvad 0-3
    silence_threshold: float = 0.01   # RMS energy threshold
    min_speech_duration_ms: int = 200
    min_silence_duration_ms: int = 600
    max_utterance_ms: int = 15000
    pre_speech_padding_ms: int = 200


@dataclass
class SpeechSegment:
    audio_bytes: bytes
    duration_ms: float
    confidence: float
    start_time: float = field(default_factory=time.time)

    def __bool__(self) -> bool:
        return len(self.audio_bytes) > 0


class VoiceActivityDetector:
    """
    Voice Activity Detection with energy-based fallback and optional webrtcvad.
    """

    def __init__(
        self,
        config: VoiceActivityConfig | None = None,
        is_mock: bool = False,
    ) -> None:
        self.config = config or VoiceActivityConfig()
        self.is_mock = is_mock
        self._lock = threading.Lock()
        self._vad_backend: Any | None = None
        if not is_mock:
            self._init_backend()
        log.info(
            "VoiceActivityDetector initialized (backend=%s, sr=%d, energy_threshold=%.4f)",
            "webrtcvad" if self._vad_backend else "energy",
            self.config.sample_rate,
            self.config.silence_threshold,
        )

    def _init_backend(self) -> None:
        try:
            import webrtcvad  # type: ignore[import]
            self._vad_backend = webrtcvad.Vad(self.config.aggressiveness)
            log.info("webrtcvad loaded (aggressiveness=%d)", self.config.aggressiveness)
        except ImportError:
            log.info("webrtcvad not installed — using energy-based VAD")
        except Exception as exc:
            log.warning("webrtcvad init failed (%s) — using energy fallback", exc)

    def is_speech(self, audio_chunk: bytes, sample_rate: int | None = None) -> bool:
        """Returns True if audio_chunk contains speech (PCM 16-bit signed mono)."""
        if self.is_mock:
            return False
        sr = sample_rate or self.config.sample_rate
        if self._vad_backend is not None:
            try:
                frame_ms = self.config.frame_duration_ms
                expected = int(sr * frame_ms / 1000) * 2
                chunk = (audio_chunk + b"\x00" * expected)[:expected]
                return bool(self._vad_backend.is_speech(chunk, sr))
            except Exception as exc:
                log.debug("webrtcvad error: %s", exc)
        return self._energy_is_speech(audio_chunk)

    def _energy_is_speech(self, audio_chunk: bytes) -> bool:
        if not audio_chunk:
            return False
        try:
            count = len(audio_chunk) // 2
            if count == 0:
                return False
            shorts = struct.unpack(f"<{count}h", audio_chunk[: count * 2])
            rms = math.sqrt(sum(s * s for s in shorts) / count) / 32768.0
            return rms > self.config.silence_threshold
        except Exception:
            return False

    def listen_for_speech(
        self,
        stream: Any,
        timeout_s: float = 10.0,
        frame_size: int | None = None,
    ) -> SpeechSegment | None:
        """
        Reads from audio stream until a complete utterance is detected.
        Returns SpeechSegment or None on timeout.
        """
        if self.is_mock:
            time.sleep(0.05)
            return SpeechSegment(audio_bytes=b"\x00" * 960, duration_ms=30.0, confidence=0.8)

        cfg = self.config
        sr = cfg.sample_rate
        chunk_size = frame_size or (int(sr * cfg.frame_duration_ms / 1000) * 2)
        pre_frames = max(1, cfg.pre_speech_padding_ms // cfg.frame_duration_ms)
        sil_thr_fr = cfg.min_silence_duration_ms // cfg.frame_duration_ms
        min_sp_fr = cfg.min_speech_duration_ms // cfg.frame_duration_ms
        max_fr = cfg.max_utterance_ms // cfg.frame_duration_ms

        pre_buffer: list[bytes] = []
        speech_buffer: list[bytes] = []
        in_speech = False
        silence_frames = speech_frames = 0
        deadline = time.monotonic() + timeout_s
        start_t = time.monotonic()

        try:
            while time.monotonic() < deadline:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                is_sp = self.is_speech(chunk, sr)
                if not in_speech:
                    pre_buffer.append(chunk)
                    if len(pre_buffer) > pre_frames:
                        pre_buffer.pop(0)
                    if is_sp:
                        in_speech = True
                        speech_frames = 1
                        silence_frames = 0
                        speech_buffer = list(pre_buffer)
                else:
                    speech_buffer.append(chunk)
                    speech_frames += 1
                    if is_sp:
                        silence_frames = 0
                    else:
                        silence_frames += 1
                        if silence_frames >= sil_thr_fr:
                            if speech_frames >= min_sp_fr:
                                break
                            in_speech = False
                            speech_buffer.clear()
                    if speech_frames >= max_fr:
                        break
        except Exception as exc:
            log.warning("listen_for_speech stream error: %s", exc)
            return None

        if not speech_buffer or speech_frames < min_sp_fr:
            return None

        audio = b"".join(speech_buffer)
        dur = (len(audio) // 2) / sr * 1000
        conf = min(1.0, speech_frames / max(1, speech_frames + silence_frames))
        return SpeechSegment(audio_bytes=audio, duration_ms=dur, confidence=conf, start_time=start_t)


__all__ = ["VoiceActivityDetector", "VoiceActivityConfig", "SpeechSegment"]
