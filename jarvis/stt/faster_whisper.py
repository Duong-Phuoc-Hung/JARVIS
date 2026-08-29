"""
jarvis/stt/faster_whisper.py
============================
Faster-Whisper Offline STT Adapter — Vietnamese speech recognition on CPU.
Latency: < 200ms for typical utterances using int8 quantized model.

Install: pip install faster-whisper
Models:  tiny, base, small, medium (auto-downloaded on first use)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("jarvis.stt.faster_whisper")


@dataclass
class TranscriptionSegment:
    text: str
    start_s: float
    end_s: float
    confidence: float


@dataclass
class TranscriptionResult:
    text: str
    language: str
    confidence: float
    duration_ms: float
    segments: list[TranscriptionSegment] = field(default_factory=list)
    is_mock: bool = False


@dataclass
class FasterWhisperConfig:
    model_size: str = "base"        # tiny, base, small, medium, large
    device: str = "cpu"
    compute_type: str = "int8"      # int8 fastest on CPU
    language: str = "vi"            # Primary language hint
    beam_size: int = 3
    vad_filter: bool = True         # Built-in VAD to remove silence
    initial_prompt: str | None = "Xin chào JARVIS"


class FasterWhisperSTTEngine:
    """
    Offline STT engine using faster-whisper (CTranslate2 optimized Whisper).
    Lazy-loads model on first call.
    """

    def __init__(
        self,
        config: FasterWhisperConfig | None = None,
        is_mock: bool = False,
    ) -> None:
        self.config = config or FasterWhisperConfig()
        self.is_mock = is_mock
        self._model: Any | None = None
        self._lock = threading.Lock()
        log.info(
            "FasterWhisperSTTEngine initialized (model=%s, device=%s, available=%s)",
            self.config.model_size,
            self.config.device,
            self.is_available(),
        )

    def is_available(self) -> bool:
        """Returns True if faster-whisper is installed."""
        if self.is_mock:
            return True
        try:
            import faster_whisper  # type: ignore[import]  # noqa: F401
            return True
        except ImportError:
            return False

    def _load_model(self) -> Any:
        """Lazy-load the Faster-Whisper model."""
        with self._lock:
            if self._model is None:
                if not self.is_available():
                    raise ImportError(
                        "faster-whisper not installed. Run: pip install faster-whisper"
                    )
                cfg = self.config
                log.info(
                    "Loading Faster-Whisper model '%s' (compute_type=%s)...",
                    cfg.model_size,
                    cfg.compute_type,
                )
                t0 = time.monotonic()
                from faster_whisper import WhisperModel  # type: ignore[import]
                self._model = WhisperModel(
                    cfg.model_size,
                    device=cfg.device,
                    compute_type=cfg.compute_type,
                )
                log.info(
                    "Faster-Whisper model loaded in %.2fs",
                    time.monotonic() - t0,
                )
        return self._model

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe PCM audio bytes to text.

        Args:
            audio_bytes: Raw PCM 16-bit signed mono audio at 16000 Hz
            language: Override language detection (None = auto-detect)

        Returns:
            TranscriptionResult with text, language, confidence, duration_ms
        """
        t0 = time.monotonic()

        if self.is_mock:
            return TranscriptionResult(
                text="[Mock transcription — xin chào JARVIS]",
                language="vi",
                confidence=0.95,
                duration_ms=(time.monotonic() - t0) * 1000,
                is_mock=True,
            )

        if audio_bytes is None or len(audio_bytes) == 0:
            return TranscriptionResult(
                text="",
                language=self.config.language,
                confidence=0.0,
                duration_ms=0.0,
            )

        try:
            import io  # noqa: E401
            import wave

            import numpy as np  # type: ignore[import]

            if isinstance(audio_bytes, np.ndarray):
                audio_float = audio_bytes.astype(np.float32)
            else:
                # Convert PCM bytes to float32 numpy array
                audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
                audio_float = audio_int16.astype(np.float32) / 32768.0

            model = self._load_model()
            cfg = self.config
            lang = language or cfg.language

            segments_gen, info = model.transcribe(
                audio_float,
                language=lang,
                beam_size=cfg.beam_size,
                vad_filter=cfg.vad_filter,
                initial_prompt=cfg.initial_prompt,
            )

            segments: list[TranscriptionSegment] = []
            full_text_parts: list[str] = []

            for seg in segments_gen:
                text_clean = seg.text.strip()
                full_text_parts.append(text_clean)
                avg_logprob = getattr(seg, "avg_logprob", -0.5)
                confidence = min(1.0, max(0.0, 1.0 + avg_logprob))
                segments.append(TranscriptionSegment(
                    text=text_clean,
                    start_s=seg.start,
                    end_s=seg.end,
                    confidence=confidence,
                ))

            full_text = " ".join(full_text_parts).strip()
            avg_conf = (
                sum(s.confidence for s in segments) / len(segments)
                if segments
                else 0.0
            )
            detected_lang = getattr(info, "language", lang) or lang
            duration_ms = (time.monotonic() - t0) * 1000

            log.debug(
                "Transcribed in %.0fms: '%s...' (lang=%s, conf=%.2f)",
                duration_ms,
                full_text[:40],
                detected_lang,
                avg_conf,
            )

            return TranscriptionResult(
                text=full_text,
                language=detected_lang,
                confidence=avg_conf,
                duration_ms=duration_ms,
                segments=segments,
            )

        except ImportError as exc:
            log.error("faster-whisper or numpy missing: %s", exc)
            return TranscriptionResult(
                text="",
                language=self.config.language,
                confidence=0.0,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            log.error("Faster-Whisper transcription error: %s", exc)
            return TranscriptionResult(
                text="",
                language=self.config.language,
                confidence=0.0,
                duration_ms=(time.monotonic() - t0) * 1000,
            )


__all__ = [
    "FasterWhisperSTTEngine",
    "FasterWhisperConfig",
    "TranscriptionResult",
    "TranscriptionSegment",
]
