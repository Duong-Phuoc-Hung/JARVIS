"""
jarvis/stt/streaming.py
=======================
Real-Time Chunked Streaming Speech-to-Text (STT) Subsystem for JARVIS.
Provides:
  - Low-latency sliding-window chunk ingestion (100ms - 200ms blocks).
  - Continuous speech activity tracking and trailing silence completion.
  - Non-blocking partial hypothesis emission (`on_partial`) for real-time HUD feedback.
  - Final transcript finalization (`on_final`) upon natural silence boundary.
  - Fail-closed exception containment and backward compatibility with FasterWhisperSTTEngine.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from jarvis.audio.dsp import calculate_rms, speech_bandpass_filter
from jarvis.stt.engine import STT_SAMPLE_RATE, audio_to_float32, prepare_stt_audio

logger = logging.getLogger("jarvis.stt.streaming")


@dataclass
class StreamingConfig:
    """Configuration parameters for real-time streaming STT."""
    sample_rate: int = STT_SAMPLE_RATE
    chunk_size_samples: int = 1600         # 100ms at 16kHz
    window_size_s: float = 3.0             # Sliding context window duration (seconds)
    step_interval_s: float = 0.25          # Hypothesis refresh interval (seconds)
    silence_cutoff_s: float = 0.75         # Silence duration to conclude an utterance (seconds)
    min_speech_s: float = 0.25             # Minimum speech required before transcribing (seconds)
    speech_threshold: float = 0.012        # Minimum RMS energy to register voice activity
    language: str = "vi"                   # Transcription target language
    beam_size: int = 1                     # Greedy beam size for low latency partials


@dataclass
class StreamingHypothesis:
    """Represents a partial or final streaming transcription event."""
    text: str
    is_final: bool
    confidence: float = 1.0
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    speculative_candidate: Any | None = None
    speculative_hit: bool = False


class StreamingSTTSession:
    """
    Stateful real-time streaming STT session.
    Accumulates incoming audio chunks, tracks voice activity, and emits partial & final transcripts.
    """

    def __init__(
        self,
        transcriber_fn: Callable[[np.ndarray, str], str],
        config: StreamingConfig | None = None,
        on_partial: Callable[[str], None] | None = None,
        on_final: Callable[[str], None] | None = None,
        on_speech_start: Callable[[], None] | None = None,
        speculative_router: Any | None = None,
    ) -> None:
        self.transcriber_fn = transcriber_fn
        self.config = config or StreamingConfig()
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_speech_start = on_speech_start
        self.speculative_router = speculative_router

        self._lock = threading.RLock()
        self._is_active = True
        self._speech_active = False

        # Ring buffer for sliding window transcription context
        self._max_window_samples = int(self.config.sample_rate * self.config.window_size_s)
        self._min_speech_samples = int(self.config.sample_rate * self.config.min_speech_s)
        self._silence_cutoff_samples = int(self.config.sample_rate * self.config.silence_cutoff_s)

        # Buffer containing active utterance audio samples
        self._utterance_samples: list[float] = []
        # Pre-speech circular buffer (300ms) to avoid clipping leading consonants
        self._pre_speech_len = int(self.config.sample_rate * 0.3)
        self._pre_speech_buffer: deque[float] = deque(maxlen=self._pre_speech_len)

        self._consecutive_silence_samples = 0
        self._total_speech_samples = 0
        self._last_hypothesis = ""
        self._last_transcribe_time = 0.0

    @property
    def is_speech_active(self) -> bool:
        """Returns True if the user is currently speaking."""
        with self._lock:
            return self._speech_active

    def feed(self, chunk: np.ndarray | bytes) -> StreamingHypothesis | None:
        """
        Feeds an incoming audio chunk into the streaming session.

        Args:
            chunk: 1D NumPy array or raw PCM bytes.

        Returns:
            StreamingHypothesis if a partial or final transcript was produced, else None.
        """
        with self._lock:
            if not self._is_active:
                return None

            arr = audio_to_float32(chunk, sample_rate=self.config.sample_rate)
            if arr.size == 0:
                return None

            # Apply speech bandpass filter to suppress rumble and fan noise
            filtered = speech_bandpass_filter(
                arr,
                sample_rate=self.config.sample_rate,
                lowcut=80.0,
                highcut=7500.0,
            )
            rms = calculate_rms(filtered)
            has_voice = rms >= self.config.speech_threshold

            if not self._speech_active:
                if has_voice:
                    # Transition to active speech!
                    self._speech_active = True
                    self._consecutive_silence_samples = 0
                    # Prepend pre-speech buffer
                    self._utterance_samples = list(self._pre_speech_buffer) + filtered.tolist()
                    self._total_speech_samples = len(self._utterance_samples)
                    self._last_transcribe_time = time.monotonic()
                    if self.on_speech_start:
                        try:
                            self.on_speech_start()
                        except Exception as e:
                            logger.error("Error in on_speech_start callback: %s", e)
                else:
                    # Idle ambient buffer
                    self._pre_speech_buffer.extend(filtered.tolist())
                    return None
            else:
                # Speech already active: accumulate audio
                self._utterance_samples.extend(filtered.tolist())
                self._total_speech_samples += filtered.size

                if has_voice:
                    self._consecutive_silence_samples = 0
                else:
                    self._consecutive_silence_samples += filtered.size

                # Check if natural silence boundary is reached -> finalize utterance
                if self._consecutive_silence_samples >= self._silence_cutoff_samples:
                    return self._finalize_utterance()

                # Check if it's time to generate an intermediate partial hypothesis
                now = time.monotonic()
                if (now - self._last_transcribe_time) >= self.config.step_interval_s:
                    self._last_transcribe_time = now
                    return self._generate_partial_hypothesis()

            return None

    def _generate_partial_hypothesis(self) -> StreamingHypothesis | None:
        """Transcribes the recent active audio window and emits partial text."""
        if len(self._utterance_samples) < self._min_speech_samples:
            return None

        # Take sliding window from end of current utterance
        window_samples = np.array(self._utterance_samples[-self._max_window_samples:], dtype=np.float32)
        try:
            t0 = time.monotonic()
            text = self.transcriber_fn(window_samples, self.config.language)
            dur_ms = (time.monotonic() - t0) * 1000.0
            clean_text = text.strip()

            if clean_text and clean_text != self._last_hypothesis:
                self._last_hypothesis = clean_text
                spec_cand = None
                if getattr(self, "speculative_router", None):
                    try:
                        spec_cand = self.speculative_router.on_partial_hypothesis(clean_text)
                    except Exception as e:
                        logger.debug("Speculative router partial error: %s", e)
                if self.on_partial:
                    try:
                        self.on_partial(clean_text)
                    except Exception as e:
                        logger.error("Error in on_partial callback: %s", e)
                return StreamingHypothesis(
                    text=clean_text,
                    is_final=False,
                    confidence=0.85,
                    duration_ms=dur_ms,
                    speculative_candidate=spec_cand,
                )
        except Exception as e:
            logger.warning("Streaming partial transcription error: %s", e)

        return None

    def _finalize_utterance(self) -> StreamingHypothesis:
        """Concludes the current utterance and emits the final transcript."""
        final_samples = np.array(self._utterance_samples, dtype=np.float32)
        final_text = ""
        dur_ms = 0.0

        if final_samples.size >= self._min_speech_samples:
            try:
                t0 = time.monotonic()
                text = self.transcriber_fn(final_samples, self.config.language)
                dur_ms = (time.monotonic() - t0) * 1000.0
                final_text = text.strip()
            except Exception as e:
                logger.error("Streaming final transcription error: %s", e)
                final_text = self._last_hypothesis

        # Speculative resolution
        spec_intent = None
        is_hit = False
        if getattr(self, "speculative_router", None) and final_text:
            try:
                spec_intent, is_hit = self.speculative_router.on_final_hypothesis(final_text)
            except Exception as e:
                logger.debug("Speculative router final error: %s", e)

        # Reset session state for next speech utterance
        self._speech_active = False
        self._consecutive_silence_samples = 0
        self._utterance_samples.clear()
        self._pre_speech_buffer.clear()
        self._last_hypothesis = ""

        if self.on_final:
            try:
                self.on_final(final_text)
            except Exception as e:
                logger.error("Error in on_final callback: %s", e)

        return StreamingHypothesis(
            text=final_text,
            is_final=True,
            confidence=0.95 if final_text else 0.0,
            duration_ms=dur_ms,
            speculative_candidate=spec_intent,
            speculative_hit=is_hit,
        )

    def finish(self) -> str:
        """
        Manually concludes the session and forces final transcription of remaining audio.

        Returns:
            str: Final transcribed text.
        """
        with self._lock:
            if not self._is_active:
                return ""
            hyp = self._finalize_utterance()
            self._is_active = False
            return hyp.text

    def cancel(self) -> None:
        """Aborts the streaming session without emitting final transcript."""
        with self._lock:
            self._is_active = False
            self._speech_active = False
            self._utterance_samples.clear()
            self._pre_speech_buffer.clear()


class StreamingSTTEngine:
    """
    Manager and factory for real-time streaming STT sessions.
    Wraps existing FasterWhisper or custom STT engines for low-latency chunk processing.
    """

    def __init__(
        self,
        base_engine: Any | None = None,
        config: StreamingConfig | None = None,
        speculative_router: Any | None = None,
    ) -> None:
        self.base_engine = base_engine
        self.config = config or StreamingConfig()
        self.speculative_router = speculative_router

    def _default_transcribe(self, audio: np.ndarray, language: str) -> str:
        """Dispatches transcription to underlying base engine or mock."""
        if self.base_engine is None:
            # Fallback mock transcription for unit testing and offline development
            return "xin chào JARVIS"

        # Check for FasterWhisperSTTEngine interface
        if hasattr(self.base_engine, "transcribe"):
            res = self.base_engine.transcribe(audio, language=language)
            if hasattr(res, "text"):
                return str(res.text)
            return str(res)

        return ""

    def create_session(
        self,
        on_partial: Callable[[str], None] | None = None,
        on_final: Callable[[str], None] | None = None,
        on_speech_start: Callable[[], None] | None = None,
        override_config: StreamingConfig | None = None,
        speculative_router: Any | None = None,
    ) -> StreamingSTTSession:
        """Creates a new active StreamingSTTSession."""
        cfg = override_config or self.config
        spec_router = speculative_router if speculative_router is not None else self.speculative_router
        return StreamingSTTSession(
            transcriber_fn=self._default_transcribe,
            config=cfg,
            on_partial=on_partial,
            on_final=on_final,
            on_speech_start=on_speech_start,
            speculative_router=spec_router,
        )

