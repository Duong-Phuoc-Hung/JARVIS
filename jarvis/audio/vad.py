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
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.audio.vad")


def _find_silero_vad_path() -> Path | None:
    """Locate Silero VAD v6 ONNX model file on disk."""
    try:
        import faster_whisper
        p = Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"
        if p.exists():
            return p
    except Exception:
        pass
    try:
        import openwakeword
        p = Path(openwakeword.__file__).parent / "resources" / "models" / "silero_vad.onnx"
        if p.exists():
            return p
    except Exception:
        pass
    return None


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
    backend: str = "auto"              # "auto" | "silero" | "webrtcvad" | "energy"
    silero_threshold: float = 0.50


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
    Voice Activity Detection with Silero VAD v6 ONNX, webrtcvad, and energy fallback.
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
        self._silero_session: Any | None = None
        self._silero_h: Any | None = None
        self._silero_c: Any | None = None
        if not is_mock:
            self._init_backend()
        backend_name = "energy"
        if self._silero_session is not None:
            backend_name = "silero_vad_v6"
        elif self._vad_backend is not None:
            backend_name = "webrtcvad"
        log.info(
            "VoiceActivityDetector initialized (backend=%s, sr=%d, energy_threshold=%.4f)",
            backend_name,
            self.config.sample_rate,
            self.config.silence_threshold,
        )

    def _init_backend(self) -> None:
        if self.config.backend in ("auto", "silero"):
            try:
                import onnxruntime as ort
                import numpy as np
                model_path = _find_silero_vad_path()
                if model_path is not None:
                    opts = ort.SessionOptions()
                    opts.intra_op_num_threads = 1
                    opts.inter_op_num_threads = 1
                    self._silero_session = ort.InferenceSession(
                        str(model_path), opts, providers=["CPUExecutionProvider"]
                    )
                    self._silero_h = np.zeros((1, 1, 128), dtype=np.float32)
                    self._silero_c = np.zeros((1, 1, 128), dtype=np.float32)
                    log.info("Silero VAD v6 ONNX loaded from %s (threshold=%.2f)", model_path, self.config.silero_threshold)
                    return
            except Exception as e:
                log.debug("Silero VAD init skipped: %s", e)

        if self.config.backend in ("auto", "webrtcvad"):
            try:
                import webrtcvad  # type: ignore[import]
                self._vad_backend = webrtcvad.Vad(self.config.aggressiveness)
                log.info("webrtcvad loaded (aggressiveness=%d)", self.config.aggressiveness)
                return
            except ImportError:
                log.info("webrtcvad not installed — using energy-based VAD")
            except Exception as exc:
                log.warning("webrtcvad init failed (%s) — using energy fallback", exc)

    def is_speech(self, audio_chunk: bytes, sample_rate: int | None = None) -> bool:
        """Returns True if audio_chunk contains speech (PCM 16-bit signed mono)."""
        if self.is_mock or not audio_chunk:
            return False
        sr = sample_rate or self.config.sample_rate

        # 1. Silero VAD neural check if enabled
        if self._silero_session is not None and self.config.backend != "energy":
            try:
                import numpy as np
                count = len(audio_chunk) // 2
                if count >= 32:
                    shorts = np.frombuffer(audio_chunk[: count * 2], dtype=np.int16)
                    f32 = (shorts.astype(np.float32) / 32768.0).reshape(1, -1)
                    if f32.shape[1] < 576:
                        pad = np.zeros((1, 576 - f32.shape[1]), dtype=np.float32)
                        f32 = np.concatenate([f32, pad], axis=1)
                    elif f32.shape[1] > 576:
                        f32 = f32[:, :576]

                    feeds = {"input": f32, "h": self._silero_h, "c": self._silero_c}
                    out, self._silero_h, self._silero_c = self._silero_session.run(None, feeds)
                    prob = float(out[0][0])
                    if prob >= self.config.silero_threshold:
                        return True
            except Exception as s_exc:
                log.debug("Silero VAD inference error: %s", s_exc)

        # 2. webrtcvad check if available
        if self._vad_backend is not None and self.config.backend != "energy":
            try:
                frame_ms = self.config.frame_duration_ms
                expected = int(sr * frame_ms / 1000) * 2
                chunk = (audio_chunk + b"\x00" * expected)[:expected]
                return bool(self._vad_backend.is_speech(chunk, sr))
            except Exception as exc:
                log.debug("webrtcvad error: %s", exc)

        # 3. Energy fallback
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
