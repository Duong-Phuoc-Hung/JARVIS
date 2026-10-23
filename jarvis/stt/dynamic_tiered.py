"""
jarvis/stt/dynamic_tiered.py
============================
Dynamic Tiered ASR Engine & Adaptive Model Routing Subsystem (Milestone 1, Requirement R1).

Provides intelligent acoustic routing between Whisper model tiers on local GPU (e.g. GTX 1650 4GB):
- Fast tier (default): faster-whisper-small (or tiny for short audio < 1.0s) on CUDA (int8_float16).
  Empirical latency target <= 880ms on GPU, maintaining resident VRAM <= 1.2GB (~786MB total system VRAM).
- Acoustic uncertainty escalation: monitors token average log-probability (avg_logprob < -0.65),
  no-speech probability (no_speech_prob > 0.50), or speech energy with empty transcript.
- Ephemeral escalation tier: loads faster-whisper-large-v3 on-demand, transcribes, and immediately
  unloads via explicit garbage collection and CUDA cache clearing (del large; gc.collect(); torch.cuda.empty_cache()),
  strictly preventing CUDA out-of-memory errors on 4GB GPUs.
- Fail-closed architecture: on missing model weights or CUDA exceptions, cascades to CPU small or
  returns an immutable TranscriptionResult with error metadata.
"""
from __future__ import annotations

import gc
import io
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from jarvis.audio.dsp import calculate_rms
from jarvis.stt.engine import (
    FASTER_WHISPER_AVAILABLE,
    STT_SAMPLE_RATE,
    BaseSTTEngine,
    FasterWhisperSTT,
    STTError,
    prepare_stt_audio,
)

log = logging.getLogger("jarvis.stt.dynamic_tiered")


@dataclass(frozen=True)
class TranscriptionResult:
    """
    Immutable transcription result contract per PROJECT.md interface specifications.

    Attributes:
        text: Transcribed speech text (empty string on silence or fatal error).
        avg_logprob: Token average log-probability from Whisper segments (higher is more confident).
        no_speech_prob: Probability that the audio segment contains no intelligible speech.
        model_tier: The Whisper model tier used for final output ('tiny', 'small', 'large-v3', etc.).
        escalated: True if acoustic uncertainty triggered escalation to large-v3.
        duration_ms: Total end-to-end transcription latency in milliseconds.
        error: Optional error description if a tier failed or fallback was triggered.
    """
    text: str
    avg_logprob: float
    no_speech_prob: float
    model_tier: str
    escalated: bool
    duration_ms: float
    error: str | None = None

    @property
    def confidence(self) -> float:
        """
        Normalized acoustic confidence score in [0.0, 1.0] derived from avg_logprob.
        Formula: clamp(1.0 + avg_logprob, 0.0, 1.0).
        """
        return float(min(1.0, max(0.0, 1.0 + self.avg_logprob)))

    @property
    def is_success(self) -> bool:
        """Returns True if speech was successfully transcribed without fatal error."""
        return bool(self.text.strip()) and (self.error is None)


class DynamicTieredASREngine(BaseSTTEngine):
    """
    Intelligent Dynamic Tiered ASR Engine coordinating multi-tier Whisper models
    with VRAM budget constraints and acoustic uncertainty routing.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        small_engine: BaseSTTEngine | None = None,
        tiny_engine: BaseSTTEngine | None = None,
        large_engine_factory: Callable[[], BaseSTTEngine] | None = None,
        cleanup_callback: Callable[[], None] | None = None,
        contextual_biaser: Any | None = None,
    ) -> None:
        """
        Initialize DynamicTieredASREngine.

        Args:
            config: Configuration dictionary for models, thresholds, and execution devices.
            small_engine: Optional pre-constructed small tier engine (for dependency injection).
            tiny_engine: Optional pre-constructed tiny tier engine (for dependency injection).
            large_engine_factory: Optional factory callable to produce ephemeral large engine.
            cleanup_callback: Optional post-cleanup hook invoked after large model VRAM eviction.
        """
        super().__init__(config)

        # ── Device & Compute Resolution ─────────────────────────────────────────
        self.requested_device = str(self.config.get("device", "cuda"))
        self.device = FasterWhisperSTT._resolve_device(self.requested_device)
        default_compute = "int8_float16" if self.device == "cuda" else "int8"
        self.compute_type = str(self.config.get("compute_type", default_compute))
        if self.device == "cpu" and self.compute_type in ("float16", "int8_float16", "bfloat16"):
            self.compute_type = "int8"

        # ── Model Cache Directory ────────────────────────────────────────────────
        _raw_root = self.config.get("download_root", "") or ""
        if not _raw_root:
            _appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            _base = Path(_appdata) / "JARVIS" if _appdata else Path.home() / ".jarvis"
            _raw_root = str(_base / "cache" / "whisper")
        self.download_root = _raw_root

        # ── Model Names & Thresholds ────────────────────────────────────────────
        self.tiny_model_size: str = str(self.config.get("tiny_model_size", "tiny"))
        self.small_model_size: str = str(self.config.get("small_model_size", "small"))
        self.large_model_size: str = str(self.config.get("large_model_size", "large-v3"))

        self.short_duration_threshold_s: float = float(
            self.config.get("short_duration_threshold_s", 1.0)
        )
        self.logprob_escalation_threshold: float = float(
            self.config.get("logprob_escalation_threshold", -0.65)
        )
        self.no_speech_escalation_threshold: float = float(
            self.config.get("no_speech_escalation_threshold", 0.50)
        )
        self.allow_escalation: bool = bool(self.config.get("allow_escalation", True))

        # ── Engines & Factories ─────────────────────────────────────────────────
        self._small_engine: BaseSTTEngine | None = small_engine
        self._tiny_engine: BaseSTTEngine | None = tiny_engine
        self._large_engine_factory: Callable[[], BaseSTTEngine] | None = large_engine_factory
        self._cleanup_callback: Callable[[], None] | None = cleanup_callback
        self._lock = threading.RLock()
        self._large_v3_lock = threading.Lock()

        if contextual_biaser is None:
            try:
                from jarvis.stt.contextual_biaser import ContextualPromptBiaser
                contextual_biaser = ContextualPromptBiaser()
            except Exception as _e_bias:
                contextual_biaser = None
        self.contextual_biaser = contextual_biaser

        log.info(
            "DynamicTieredASREngine initialized (device=%s, compute=%s, small=%s, tiny=%s, large=%s)",
            self.device,
            self.compute_type,
            self.small_model_size,
            self.tiny_model_size,
            self.large_model_size,
        )

    @property
    def engine_name(self) -> str:
        """Identifier name of the dynamic tiered ASR engine."""
        return "dynamic_tiered_asr"

    def is_available(self) -> bool:
        """Check if faster-whisper or injected engine is available."""
        if self._small_engine is not None:
            return self._small_engine.is_available()
        return FASTER_WHISPER_AVAILABLE

    def _get_small_engine(self) -> BaseSTTEngine:
        """Lazy-construct and cache the resident small tier engine."""
        if self._small_engine is None:
            with self._lock:
                if self._small_engine is None:
                    self._small_engine = FasterWhisperSTT({
                        "model_size": self.small_model_size,
                        "device": self.device,
                        "compute_type": self.compute_type,
                        "download_root": self.download_root,
                    })
        return self._small_engine

    def _get_tiny_engine(self) -> BaseSTTEngine:
        """Lazy-construct and cache the resident tiny tier engine for ultra-short audio."""
        if self._tiny_engine is None:
            with self._lock:
                if self._tiny_engine is None:
                    self._tiny_engine = FasterWhisperSTT({
                        "model_size": self.tiny_model_size,
                        "device": self.device,
                        "compute_type": self.compute_type,
                        "download_root": self.download_root,
                    })
        return self._tiny_engine

    def _create_large_engine(self) -> BaseSTTEngine:
        """Instantiate an ephemeral large model engine for escalation."""
        if self._large_engine_factory is not None:
            return self._large_engine_factory()

        return FasterWhisperSTT({
            "model_size": self.large_model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "download_root": self.download_root,
        })

    def _unload_large_engine(self, engine: Any | None) -> None:
        """
        Immediately unload ephemeral large model and clean GPU VRAM cache to prevent OOM.
        """
        if engine is not None:
            try:
                # Destroy CTranslate2 WhisperModel inside FasterWhisperSTT if present
                if hasattr(engine, "_model") and engine._model is not None:
                    del engine._model
                    engine._model = None
            except Exception as exc:
                log.debug("Error releasing large engine internal model reference: %s", exc)
            del engine

        gc.collect()
        self._clean_gpu_memory()

        if self._cleanup_callback is not None:
            try:
                self._cleanup_callback()
            except Exception as cb_exc:
                log.debug("Error in cleanup callback: %s", cb_exc)

    @staticmethod
    def _clean_gpu_memory() -> None:
        """Evicts unreferenced memory buffers from CUDA memory allocator if PyTorch is loaded."""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, Exception):
            pass

    def _fallback_cpu_small(
        self,
        arr: np.ndarray,
        language: str,
        t0: float,
        error: str,
    ) -> TranscriptionResult:
        """Fail-closed CPU fallback when GPU inference encounters an unrecoverable exception."""
        log.warning("Initiating emergency CPU fallback for small Whisper model...")
        try:
            cpu_engine = FasterWhisperSTT({
                "model_size": self.small_model_size,
                "device": "cpu",
                "compute_type": "int8",
                "download_root": self.download_root,
            })
            metrics = cpu_engine.transcribe_with_metrics(arr, language=language)
            dur = (time.perf_counter() - t0) * 1000.0
            return TranscriptionResult(
                text=metrics.text,
                avg_logprob=metrics.avg_logprob,
                no_speech_prob=metrics.no_speech_prob,
                model_tier=f"{self.small_model_size}-cpu-fallback",
                escalated=False,
                duration_ms=dur,
                error=f"CUDA failure: {error}",
            )
        except Exception as cpu_exc:
            dur = (time.perf_counter() - t0) * 1000.0
            log.error("Emergency CPU fallback failed: %s", cpu_exc)
            return TranscriptionResult(
                text="",
                avg_logprob=-99.0,
                no_speech_prob=1.0,
                model_tier="failed",
                escalated=False,
                duration_ms=dur,
                error=f"CUDA error: {error}; CPU fallback failed: {cpu_exc}",
            )

    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str = "vi",
        **kwargs: Any,
    ) -> TranscriptionResult:
        """
        Transcribe input speech audio using adaptive dynamic model routing.

        Flow:
        1. Resample and normalize audio to 16kHz float32.
        2. Filter zero-energy / pure-silence frames immediately.
        3. Route to 'tiny' tier if audio duration < 1.0s, else 'small' tier on GPU.
        4. Inspect acoustic uncertainty metrics (avg_logprob and no_speech_prob).
        5. If uncertainty exceeds thresholds or speech energy exists with empty text,
           escalate to 'large-v3' on-demand and immediately reclaim VRAM.

        Args:
            audio: Audio buffer, numpy array, raw PCM bytes, or file path.
            language: Target language hint (default: 'vi').
            **kwargs: Extra parameters passed to model.transcribe (e.g. beam_size).

        Returns:
            TranscriptionResult with text, metrics, model_tier, and latency.
        """
        t0 = time.perf_counter()

        # 1. Normalize audio to float32 16kHz mono array
        try:
            arr = prepare_stt_audio(audio, kwargs.pop("source_sample_rate", STT_SAMPLE_RATE))
        except Exception as prep_exc:
            dur = (time.perf_counter() - t0) * 1000.0
            return TranscriptionResult(
                text="",
                avg_logprob=-99.0,
                no_speech_prob=1.0,
                model_tier="none",
                escalated=False,
                duration_ms=dur,
                error=f"Audio preparation failed: {prep_exc}",
            )

        # 2. Silence / empty buffer gate
        if arr.size == 0:
            dur = (time.perf_counter() - t0) * 1000.0
            return TranscriptionResult(
                text="",
                avg_logprob=0.0,
                no_speech_prob=1.0,
                model_tier="none",
                escalated=False,
                duration_ms=dur,
            )

        audio_rms = float(calculate_rms(arr))
        audio_duration_s = len(arr) / float(STT_SAMPLE_RATE)

        if audio_rms < 0.001:
            dur = (time.perf_counter() - t0) * 1000.0
            return TranscriptionResult(
                text="",
                avg_logprob=0.0,
                no_speech_prob=1.0,
                model_tier="none",
                escalated=False,
                duration_ms=dur,
            )

        # 3. Select Initial Fast Tier (tiny for ultra-short commands, small for normal)
        if audio_duration_s < self.short_duration_threshold_s:
            initial_tier = self.tiny_model_size
            initial_engine = self._get_tiny_engine()
        else:
            initial_tier = self.small_model_size
            initial_engine = self._get_small_engine()

        # 4. Contextual Biasing & Initial Tier Execution
        if "initial_prompt" not in kwargs or kwargs.get("initial_prompt") is None:
            if getattr(self, "contextual_biaser", None) is not None:
                bias_prompt = self.contextual_biaser.get_bias_prompt()
                if bias_prompt:
                    kwargs["initial_prompt"] = bias_prompt
        if kwargs.get("initial_prompt"):
            from jarvis.stt.contextual_biaser import cap_prompt_tokens
            kwargs["initial_prompt"] = cap_prompt_tokens(str(kwargs["initial_prompt"]), 15)

        try:
            initial_metrics = initial_engine.transcribe_with_metrics(arr, language=language, **kwargs)
        except Exception as tier_exc:
            log.warning("Initial tier '%s' failed on %s: %s", initial_tier, self.device, tier_exc)
            is_cuda_issue = bool(
                self.requested_device == "cuda"
                or self.device == "cuda"
                or "cuda" in str(tier_exc).lower()
            )
            if is_cuda_issue:
                return self._fallback_cpu_small(arr, language=language, t0=t0, error=str(tier_exc))
            dur = (time.perf_counter() - t0) * 1000.0
            return TranscriptionResult(
                text="",
                avg_logprob=-99.0,
                no_speech_prob=1.0,
                model_tier="failed",
                escalated=False,
                duration_ms=dur,
                error=str(tier_exc),
            )

        # 5. Acoustic Uncertainty Evaluation
        # Conditions for escalation:
        # a) avg_logprob < threshold (e.g. -0.65)
        # b) no_speech_prob > threshold (e.g. 0.50)
        # c) Audio has significant voice energy (RMS >= 0.003) but produced an empty transcript
        has_voice_energy = bool(audio_rms >= 0.003)
        has_empty_text = bool(len(initial_metrics.text.strip()) == 0)
        is_low_logprob = bool(initial_metrics.avg_logprob < self.logprob_escalation_threshold)
        is_high_no_speech = bool(initial_metrics.no_speech_prob > self.no_speech_escalation_threshold)
        is_voice_missing = bool(has_voice_energy and has_empty_text)

        should_escalate = self.allow_escalation and (
            is_low_logprob or is_high_no_speech or is_voice_missing
        )

        if not should_escalate:
            dur = (time.perf_counter() - t0) * 1000.0
            return TranscriptionResult(
                text=initial_metrics.text,
                avg_logprob=initial_metrics.avg_logprob,
                no_speech_prob=initial_metrics.no_speech_prob,
                model_tier=initial_tier,
                escalated=False,
                duration_ms=dur,
            )

        # 6. Ephemeral Escalation to Large-v3
        log.info(
            "Acoustic uncertainty triggered escalation from '%s' to '%s' "
            "(avg_logprob=%.2f, no_speech_prob=%.2f, voice_missing=%s)",
            initial_tier,
            self.large_model_size,
            initial_metrics.avg_logprob,
            initial_metrics.no_speech_prob,
            is_voice_missing,
        )

        with self._large_v3_lock:
            large_engine: BaseSTTEngine | None = None
            try:
                large_engine = self._create_large_engine()
                large_metrics = large_engine.transcribe_with_metrics(arr, language=language, **kwargs)
                dur = (time.perf_counter() - t0) * 1000.0

                # Preserve initial text if large returned empty on noisy utterance
                use_large = bool(large_metrics.text.strip()) or not bool(initial_metrics.text.strip())
                final_text = large_metrics.text if use_large else initial_metrics.text
                final_lp = large_metrics.avg_logprob if use_large else initial_metrics.avg_logprob
                final_nsp = large_metrics.no_speech_prob if use_large else initial_metrics.no_speech_prob

                return TranscriptionResult(
                    text=final_text,
                    avg_logprob=final_lp,
                    no_speech_prob=final_nsp,
                    model_tier=self.large_model_size,
                    escalated=True,
                    duration_ms=dur,
                )
            except Exception as esc_exc:
                dur = (time.perf_counter() - t0) * 1000.0
                log.warning("Escalation to '%s' failed: %s; falling back to initial tier", self.large_model_size, esc_exc)
                return TranscriptionResult(
                    text=initial_metrics.text,
                    avg_logprob=initial_metrics.avg_logprob,
                    no_speech_prob=initial_metrics.no_speech_prob,
                    model_tier=initial_tier,
                    escalated=False,
                    duration_ms=dur,
                    error=f"Escalation failed: {esc_exc}",
                )
            finally:
                # Strictly unload ephemeral model and reclaim VRAM
                self._unload_large_engine(large_engine)

    def get_vram_telemetry(self) -> dict[str, Any]:
        """
        Query current GPU VRAM allocation telemetry for monitoring compliance with 2.0GB budget.
        """
        telemetry: dict[str, Any] = {
            "device": self.device,
            "compute_type": self.compute_type,
            "is_cuda": self.device == "cuda",
            "allocated_mb": 0.0,
            "reserved_mb": 0.0,
        }
        try:
            import torch
            if torch.cuda.is_available():
                telemetry["allocated_mb"] = float(torch.cuda.memory_allocated() / (1024 * 1024))
                telemetry["reserved_mb"] = float(torch.cuda.memory_reserved() / (1024 * 1024))
        except (ImportError, Exception):
            pass
        return telemetry


# Backward compatibility alias
DynamicTieredASR = DynamicTieredASREngine
