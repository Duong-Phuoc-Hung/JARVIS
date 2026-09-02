"""
jarvis/audio/wake_word.py
=========================
Offline Wake Word Detection Engine for JARVIS ("Hey JARVIS" / "JARVIS").
Provides:
  - Multi-tier detection architecture:
      * Tier 1: Offline lightweight keyword matching (Vosk with Vietnamese model, Porcupine, OpenWakeWord).
      * Tier 1.5: Whisper sliding-window STT keyword detector fallback (Faster-Whisper on speech-active windows).
      * Tier 2: Zero-dependency acoustic energy & spectral formant/fricative feature detector fallback (<1s latency).
  - Thread-safe audio block processing accepting 44.1kHz and 16kHz PCM audio frames.
  - Live runtime enable/disable toggle without requiring restart.
  - False positive suppression (silence, white noise, impulse claps, pure tone rejection).
  - Configurable refractory period (default 1.5s cooldown after trigger).
  - Mathematical synthetic wake word signal generator for deterministic testing.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from jarvis.audio.dsp import calculate_rms

logger = logging.getLogger("jarvis.audio.wake_word")

# Optional Tier 1 & Tier 1.5 library imports
try:
    import vosk
    VOSK_AVAILABLE = True
except ImportError:
    vosk = None
    VOSK_AVAILABLE = False

try:
    import openwakeword
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    openwakeword = None
    OPENWAKEWORD_AVAILABLE = False

try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except ImportError:
    pvporcupine = None
    PORCUPINE_AVAILABLE = False

try:
    import faster_whisper
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    faster_whisper = None
    FASTER_WHISPER_AVAILABLE = False


class WakeWordEngineType(str, Enum):
    """Detection engine tier / implementation."""
    VOSK = "vosk"
    OPENWAKEWORD = "openwakeword"
    PORCUPINE = "porcupine"
    WHISPER = "whisper"
    ACOUSTIC_FALLBACK = "acoustic_fallback"
    MOCK = "mock"


@dataclass(frozen=True)
class WakeWordResult:
    """Detection event telemetry."""
    keyword: str
    confidence: float
    timestamp: float = field(default_factory=time.monotonic)
    engine: str = WakeWordEngineType.ACOUSTIC_FALLBACK.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "engine": self.engine,
        }


def resample_audio(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Linear interpolation resampling for 1D audio arrays."""
    if orig_sr == target_sr or len(samples) == 0:
        return samples
    duration = len(samples) / float(orig_sr)
    num_target_samples = int(round(duration * target_sr))
    if num_target_samples == 0:
        return np.empty(0, dtype=samples.dtype)
    orig_indices = np.linspace(0.0, 1.0, len(samples), endpoint=False)
    target_indices = np.linspace(0.0, 1.0, num_target_samples, endpoint=False)
    return np.interp(target_indices, orig_indices, samples).astype(samples.dtype)


def generate_wake_word_signal(
    keyword: str = "hey_jarvis",
    duration_s: float = 1.0,
    sample_rate: int = 44100,
    peak_amp: float = 0.80,
    noise_floor_rms: float = 0.002,
) -> np.ndarray:
    """
    Synthesizes a realistic acoustic speech signal matching the phonetic formant
    envelope of 'Hey JARVIS' / 'JARVIS' for deterministic validation and testing.

    Phonetic acoustic structure:
      1. 'Hey' / 'JAR' (/dʒɑːr/): Vowel fundamental (140-180 Hz) + Formants (620 Hz & 1240 Hz),
         duration ~250ms, low ZCR.
      2. Gap / Transition: ~100ms dip.
      3. 'VIS' (/vɪs/): Voiced transition + Sibilant fricative noise burst (4000-6000 Hz),
         duration ~220ms, high ZCR.
    """
    num_samples = int(sample_rate * duration_s)
    signal = np.zeros(num_samples, dtype=np.float32)

    # 1. Syllable 1: "JAR" starting at t=0.15s
    s1_start = int(sample_rate * 0.15)
    s1_dur = int(sample_rate * 0.25)
    if s1_start + s1_dur <= num_samples:
        t_s1 = np.linspace(0.0, 0.25, s1_dur, endpoint=False)
        # Hann envelope
        env_s1 = np.sin(np.pi * t_s1 / 0.25) ** 2
        # Formants
        f0 = 150.0
        f1 = 620.0
        f2 = 1240.0
        vowel = (
            0.50 * np.sin(2 * np.pi * f0 * t_s1)
            + 0.35 * np.sin(2 * np.pi * f1 * t_s1)
            + 0.25 * np.sin(2 * np.pi * f2 * t_s1)
        )
        signal[s1_start : s1_start + s1_dur] += (env_s1 * vowel * peak_amp).astype(np.float32)

    # 2. Syllable 2: "VIS" starting at t=0.45s (approx 200ms after S1 center)
    s2_start = int(sample_rate * 0.45)
    s2_dur = int(sample_rate * 0.22)
    if s2_start + s2_dur <= num_samples:
        t_s2 = np.linspace(0.0, 0.22, s2_dur, endpoint=False)
        env_s2 = np.sin(np.pi * t_s2 / 0.22) ** 2
        # Sibilant fricative: 4800Hz + high frequency filtered noise
        noise_fricative = np.random.normal(0, 1, s2_dur)
        fricative = 0.45 * np.sin(2 * np.pi * 4800.0 * t_s2) + 0.55 * noise_fricative
        signal[s2_start : s2_start + s2_dur] += (env_s2 * fricative * peak_amp * 0.85).astype(np.float32)

    # 3. Add ambient noise floor
    if noise_floor_rms > 0:
        noise = np.random.normal(0.0, 1.0, num_samples).astype(np.float32)
        cur_rms = float(np.sqrt(np.mean(noise**2)))
        if cur_rms > 0:
            noise = noise * (noise_floor_rms / cur_rms)
        signal += noise

    # Clip to valid audio range
    signal = np.clip(signal, -1.0, 1.0)
    return signal.astype(np.float32)


class WhisperSlidingWindowDetector:
    """
    Tier 1.5: Lightweight speech-to-text keyword detector running Faster-Whisper
    on voice-active sliding windows as a robust local STT fallback.
    """

    def __init__(
        self,
        model_size: str = "tiny",
        sample_rate: int = 16000,
        min_rms: float = 0.010,
        model: Any | None = None,
        check_interval_s: float = 0.3,
        keywords: list[str] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.min_rms = min_rms
        self.check_interval_s = check_interval_s
        self._last_check_time: float = 0.0
        self.keywords = keywords or [
            "jarvis",
            "hey jarvis",
            "chào jarvis",
            "ê jarvis",
            "ơi jarvis",
            "hi jarvis",
            "ok jarvis",
            "hello jarvis",
        ]
        self.model = model
        self._model_size = model_size
        self._lock = threading.Lock()

    def _get_model(self) -> Any:
        if self.model is None and FASTER_WHISPER_AVAILABLE:
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            except Exception as e:
                logger.warning("Failed to initialize Faster-Whisper model: %s", e)
                self.model = False
        return self.model if self.model is not False else None

    def analyze_window(
        self,
        buffer: np.ndarray,
        sensitivity: float = 0.5,
        timestamp: float | None = None,
    ) -> tuple[bool, str, float]:
        """
        Transcribes the sliding window if speech energy exceeds min_rms and check_interval
        has elapsed.

        Returns:
            Tuple[bool, str, float]: (detected, keyword, confidence)
        """
        if len(buffer) == 0:
            return False, "", 0.0

        now = timestamp if timestamp is not None else time.monotonic()
        if (now - self._last_check_time) < self.check_interval_s:
            return False, "", 0.0

        rms = calculate_rms(buffer)
        threshold_rms = max(0.003, self.min_rms * (1.0 - 0.5 * sensitivity))
        if rms < threshold_rms:
            return False, "", 0.0

        model = self._get_model()
        if not model:
            return False, "", 0.0

        self._last_check_time = now

        try:
            audio_arr = buffer.astype(np.float32) if buffer.dtype != np.float32 else buffer
            with self._lock:
                segments, _ = model.transcribe(
                    audio_arr,
                    language="vi",
                    beam_size=1,
                    temperature=0.0,
                    initial_prompt="JARVIS, hey JARVIS, chào JARVIS",
                    vad_filter=False,
                )
                text = " ".join([getattr(s, "text", "") for s in segments]).lower().strip()

            if not text:
                return False, "", 0.0

            for kw in self.keywords:
                if kw in text:
                    return True, "hey_jarvis", 0.92
        except Exception as e:
            logger.debug("WhisperSlidingWindowDetector transcribe error: %s", e)

        return False, "", 0.0

    def reset(self) -> None:
        """Reset internal rate limit / state."""
        self._last_check_time = 0.0


class AcousticSpectralDetector:
    """
    Tier 2: Zero-dependency acoustic energy & spectral feature detector fallback.
    Performs fast (<5ms) multi-band STFT spectrum extraction and temporal syllable
    sequence matching to classify 'Hey JARVIS' / 'JARVIS' speech patterns.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_size: int = 512,
        hop_size: int = 256,
        min_rms: float = 0.005,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.hop_size = hop_size
        self.min_rms = min_rms

        # Frequency bin calculations (16000 / 512 = 31.25 Hz/bin)
        self.bin_hz = sample_rate / float(frame_size)
        self.low_bins = (max(1, int(80 / self.bin_hz)), max(2, int(350 / self.bin_hz)))       # 80-350 Hz
        self.mid_bins = (int(400 / self.bin_hz), int(2500 / self.bin_hz))                     # 400-2500 Hz (Formants)
        self.high_bins = (int(2800 / self.bin_hz), int(7200 / self.bin_hz))                   # 2800-7200 Hz (Fricatives)
        self._window = np.hanning(self.frame_size).astype(np.float32)

    def analyze_window(self, buffer: np.ndarray, sensitivity: float = 0.5) -> tuple[bool, str, float]:
        """
        Analyzes a 1.0-1.5s audio buffer for the 'Hey JARVIS' / 'JARVIS' acoustic signature.

        Returns:
            Tuple[bool, str, float]: (detected, keyword, confidence)
        """
        if len(buffer) < self.frame_size * 4:
            return False, "", 0.0

        rms = calculate_rms(buffer)
        if rms < self.min_rms:
            return False, "", 0.0

        # Check for harsh digital clipping or flat saturation
        if np.max(np.abs(buffer)) > 0.999 and np.mean(np.abs(buffer)) > 0.70:
            return False, "", 0.0

        num_frames = (len(buffer) - self.frame_size) // self.hop_size + 1
        if num_frames < 8:
            return False, "", 0.0

        mid_energies = np.zeros(num_frames, dtype=np.float32)
        high_energies = np.zeros(num_frames, dtype=np.float32)
        zcrs = np.zeros(num_frames, dtype=np.float32)
        flatness_list: list[float] = []

        for i in range(num_frames):
            start = i * self.hop_size
            frame = buffer[start : start + self.frame_size]
            if len(frame) < self.frame_size:
                break

            frame_rms = calculate_rms(frame)
            if frame_rms < self.min_rms:
                continue

            # Zero-Crossing Rate
            zcr = float(np.mean(np.abs(np.diff(np.signbit(frame)))))
            zcrs[i] = zcr

            # Windowed FFT magnitude
            w_frame = frame * self._window
            spec = np.abs(np.fft.rfft(w_frame))
            spec_sum = float(np.sum(spec)) + 1e-9

            # Band energy ratios weighted by frame RMS power
            mid_ratio = float(np.sum(spec[self.mid_bins[0] : self.mid_bins[1]])) / spec_sum
            high_ratio = float(np.sum(spec[self.high_bins[0] : self.high_bins[1]])) / spec_sum
            weight = frame_rms / max(0.005, rms)

            mid_energies[i] = mid_ratio * weight
            high_energies[i] = high_ratio * weight

            # Spectral Flatness Measure (SFM)
            geom_mean = np.exp(np.mean(np.log(spec + 1e-9)))
            arith_mean = np.mean(spec) + 1e-9
            flatness_list.append(float(geom_mean / arith_mean))

        avg_flatness = float(np.mean(flatness_list)) if flatness_list else 0.0
        # White noise rejection: pure white noise has high flatness across the active frames
        if avg_flatness > 0.65:
            return False, "", 0.0
        # Pure tone / narrow-band noise rejection: pure sine waves have flatness near 0
        # (single dominant spectral spike). Speech flatness is typically 0.05–0.30.
        # This blocks false positives on system beeps, fan noise, pure tones (e.g. 3kHz).
        if avg_flatness < 0.03:
            return False, "", 0.0

        max_mid = float(np.max(mid_energies))
        max_high = float(np.max(high_energies))

        if max_mid < 0.15 or max_high < 0.12:
            return False, "", 0.0

        peak_mid_idx = int(np.argmax(mid_energies))
        peak_high_idx = int(np.argmax(high_energies))

        # Check temporal order: Syllable 1 (mid) must precede Syllable 2 (high)
        time_diff_s = (peak_high_idx - peak_mid_idx) * (self.hop_size / float(self.sample_rate))

        # Expected gap between "JAR" and "VIS" peaks is ~0.08s to 0.65s
        if not (0.07 <= time_diff_s <= 0.65):
            return False, "", 0.0

        # Clap impulse rejection: Claps peak simultaneously across all bands
        if abs(time_diff_s) < 0.05:
            return False, "", 0.0

        # ZCR check during S2
        zcr_s2 = zcrs[peak_high_idx]
        if zcr_s2 < 0.10:
            return False, "", 0.0

        # Calculate confidence score
        score_mid = min(1.0, max_mid / 0.50)
        score_high = min(1.0, max_high / 0.45)
        score_zcr = min(1.0, zcr_s2 / 0.20)
        score_timing = max(0.0, min(1.0, 1.0 - abs(time_diff_s - 0.28) / 0.35))
        score_contrast = max(0.0, min(1.0, 1.0 - avg_flatness))

        confidence = float(
            0.25 * score_mid + 0.25 * score_high + 0.20 * score_zcr + 0.15 * score_timing + 0.15 * score_contrast
        )
        confidence = max(0.0, min(1.0, confidence))

        # Sensitivity scaling (robust threshold to prevent ambient noise false positives)
        threshold = max(0.40, 0.75 - (sensitivity * 0.35))

        if confidence >= threshold:
            return True, "hey_jarvis", confidence

        return False, "", 0.0


class _PorcupineFrameBuffer:
    """
    Adapts arbitrary-sized incoming audio blocks to Porcupine's fixed-frame
    contract: ``porcupine.process()`` requires exactly ``frame_length`` int16
    samples per call and advances the engine's internal detection state on
    every call, so partial frames must be carried over (never dropped or
    duplicated) and every complete frame must be processed in order.
    """

    def __init__(self, engine: Any, frame_length: int, sample_rate: int) -> None:
        self.engine = engine
        self.frame_length = int(frame_length)
        self.sample_rate = int(sample_rate)
        self._pending: np.ndarray = np.empty(0, dtype=np.int16)

    def process(self, pcm_int16: np.ndarray) -> int:
        """
        Buffers new int16 PCM samples and runs every complete frame through
        Porcupine in order. Returns the first detected keyword index observed
        in this call, or -1 if none of the processed frames matched.
        """
        if pcm_int16.size:
            self._pending = np.concatenate([self._pending, pcm_int16])

        detected_index = -1
        while len(self._pending) >= self.frame_length:
            frame = self._pending[: self.frame_length]
            self._pending = self._pending[self.frame_length :]
            idx = self.engine.process(frame.tolist())
            if idx >= 0 and detected_index < 0:
                detected_index = idx

        return detected_index

    def reset(self) -> None:
        """Drop any buffered partial frame (used on detector reset())."""
        self._pending = np.empty(0, dtype=np.int16)


class WakeWordDetector:
    """
    Real-time, multi-tier Wake Word Detector for JARVIS.

    Features:
      - Multi-tier detection cascade:
          * Tier 1: Vosk (Vietnamese model auto-discovery), OpenWakeWord, Porcupine.
          * Tier 1.5: Faster-Whisper sliding window STT keyword fallback.
          * Tier 2: Spectral DSP Acoustic Formant/Fricative Detector.
      - Live enable/disable toggle without restart (`set_enabled`, `is_enabled`, `toggle_enabled`).
      - Cooldown & refractory period (1.5s default).
      - Accepts audio blocks in 44.1kHz or 16kHz, mono or stereo.
      - Full thread-safety for multi-subscriber audio architectures.
    """

    def __init__(
        self,
        callback: Callable[[], None] | None = None,
        sensitivity: float = 0.5,
        enabled: bool = True,
        sample_rate: int = 44100,
        target_sample_rate: int = 16000,
        window_duration_s: float = 1.2,
        cooldown_s: float = 1.5,
        on_wake_word: Callable[[str, float], None] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.callback = callback
        self.sensitivity = max(0.0, min(1.0, float(sensitivity)))
        self._enabled = bool(enabled)
        self.sample_rate = int(sample_rate)
        self.target_sample_rate = int(target_sample_rate)
        self.window_duration_s = float(window_duration_s)
        self.cooldown_s = float(cooldown_s)
        self.on_wake_word = on_wake_word
        self.config = config or {}

        self._lock = threading.RLock()
        self._last_trigger_time: float = 0.0
        self._trigger_count: int = 0

        # Ring buffer for sliding window in target sample rate (16kHz)
        self._buffer_len = int(self.target_sample_rate * self.window_duration_s)
        self._ring_buffer: np.ndarray = np.zeros(self._buffer_len, dtype=np.float32)

        # Initialize engines
        self._spectral_detector = AcousticSpectralDetector(
            sample_rate=self.target_sample_rate,
            min_rms=float(self.config.get("min_rms", 0.005)),
        )
        self._whisper_detector = WhisperSlidingWindowDetector(
            model_size=self.config.get("whisper_model_size", "tiny"),
            sample_rate=self.target_sample_rate,
            min_rms=float(self.config.get("whisper_min_rms", 0.010)),
            check_interval_s=float(self.config.get("whisper_check_interval_s", 0.3)),
        )
        self._tier1_engine: Any | None = None
        self._porcupine_frame_buffer: _PorcupineFrameBuffer | None = None
        self._engine_type: WakeWordEngineType = self._init_tier1()

        logger.info(
            "WakeWordDetector initialized (engine=%s, sensitivity=%.2f, cooldown=%.1fs, enabled=%s)",
            self._engine_type.value,
            self.sensitivity,
            self.cooldown_s,
            self._enabled,
        )

    def _init_tier1(self) -> WakeWordEngineType:
        """Attempt to initialize Tier 1 local model if available."""
        # Check explicit engine override in config
        forced_engine = self.config.get("engine") or self.config.get("engine_type")
        if forced_engine == "whisper" and FASTER_WHISPER_AVAILABLE:
            return WakeWordEngineType.WHISPER
        if forced_engine == "mock":
            return WakeWordEngineType.MOCK

        # 1. Vosk
        if VOSK_AVAILABLE:
            candidate_paths = [
                self.config.get("vosk_model_path"),
                os.environ.get("JARVIS_VOSK_MODEL"),
                os.environ.get("VOSK_MODEL_PATH"),
                os.path.join(os.getcwd(), "models", "vosk-model-small-vn-0.4"),
                os.path.join(os.getcwd(), "models", "vosk-model-vn"),
                os.path.join(os.getcwd(), "models", "vosk-model-small-en-us-0.15"),
                os.path.expanduser("~/.cache/vosk/vosk-model-small-vn-0.4"),
                os.path.expanduser("~/.vosk/vosk-model-small-vn-0.4"),
                os.path.expanduser("~/.cache/vosk/vosk-model-vn"),
                os.path.expanduser("~/.vosk/vosk-model-vn"),
            ]
            model_path = None
            for path in candidate_paths:
                if path and os.path.isdir(path):
                    model_path = path
                    break

            vosk_model = None
            if model_path:
                try:
                    vosk_model = vosk.Model(model_path)
                except Exception as e:
                    logger.warning("Vosk init failed for path '%s': %s", model_path, e)

            # Auto-download if explicitly configured
            if vosk_model is None and self.config.get("auto_download_vosk", False):
                try:
                    lang = self.config.get("vosk_lang", "vn")
                    vosk_model = vosk.Model(lang=lang)
                except Exception as e:
                    logger.debug("Vosk auto-download failed for lang='%s': %s", self.config.get("vosk_lang", "vn"), e)

            if vosk_model is not None:
                try:
                    rec = vosk.KaldiRecognizer(
                        vosk_model,
                        self.target_sample_rate,
                        '["hey jarvis", "jarvis", "chào jarvis", "ê jarvis", "ơi jarvis", "[unk]"]',
                    )
                    self._tier1_engine = rec
                    return WakeWordEngineType.VOSK
                except Exception as e:
                    logger.warning("Vosk KaldiRecognizer init failed: %s; falling back to Tier 2.", e)

        # 2. OpenWakeWord
        if OPENWAKEWORD_AVAILABLE:
            try:
                if hasattr(openwakeword, "Model"):
                    self._tier1_engine = openwakeword.Model()
                    return WakeWordEngineType.OPENWAKEWORD
            except Exception as e:
                logger.warning("OpenWakeWord init failed: %s; falling back to Tier 2.", e)

        # 3. Porcupine
        if PORCUPINE_AVAILABLE:
            access_key = self.config.get("porcupine_access_key", os.environ.get("PORCUPINE_ACCESS_KEY"))
            if access_key:
                porcupine_engine = None
                try:
                    porcupine_engine = pvporcupine.create(
                        access_key=access_key,
                        keywords=["jarvis"],
                        sensitivities=[self.sensitivity],
                    )
                    frame_buffer = _PorcupineFrameBuffer(
                        porcupine_engine,
                        frame_length=porcupine_engine.frame_length,
                        sample_rate=porcupine_engine.sample_rate,
                    )
                    self._tier1_engine = porcupine_engine
                    self._porcupine_frame_buffer = frame_buffer
                    return WakeWordEngineType.PORCUPINE
                except Exception as e:
                    logger.warning("Porcupine init failed: %s; falling back to Tier 2.", e)
                    if porcupine_engine is not None:
                        try:
                            porcupine_engine.delete()
                        except Exception as delete_err:
                            logger.debug(
                                "Porcupine delete() failed while cleaning up a partial init: %s",
                                delete_err,
                            )

        # 4. Faster-Whisper (if explicitly requested in config)
        if (
            self.config.get("use_whisper", False)
            or self.config.get("whisper_enabled", False)
        ) and FASTER_WHISPER_AVAILABLE:
            return WakeWordEngineType.WHISPER

        return WakeWordEngineType.ACOUSTIC_FALLBACK

    # -----------------------------------------------------------------------
    # State & Control
    # -----------------------------------------------------------------------
    def _reset_stream_state_locked(self) -> None:
        """
        Clear the caller-owned streaming buffers (the sliding ring
        buffer and any pending partial Porcupine frame) on an enable/disable
        transition, so caller-side PCM from before the transition is never
        concatenated with caller-side PCM from after it.
        """
        self._ring_buffer.fill(0.0)
        if self._porcupine_frame_buffer is not None:
            self._porcupine_frame_buffer.reset()
        if hasattr(self, "_whisper_detector") and self._whisper_detector:
            self._whisper_detector.reset()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable wake word detection live without restart."""
        with self._lock:
            new_value = bool(enabled)
            changed = new_value != self._enabled
            self._enabled = new_value
            if changed:
                self._reset_stream_state_locked()
            logger.info("WakeWordDetector enabled set to: %s", self._enabled)

    def is_enabled(self) -> bool:
        """Return current enabled status."""
        with self._lock:
            return self._enabled

    def toggle_enabled(self) -> bool:
        """
        Thread-safe flip of the enabled state (True<->False) without restart.
        Returns the resulting enabled state.
        """
        with self._lock:
            self._enabled = not self._enabled
            self._reset_stream_state_locked()
            logger.info("WakeWordDetector enabled toggled to: %s", self._enabled)
            return self._enabled

    @property
    def enabled(self) -> bool:
        """Property alias for enabled status."""
        with self._lock:
            return self._enabled

    @property
    def trigger_count(self) -> int:
        """Total number of successful wake word triggers."""
        with self._lock:
            return self._trigger_count

    def reset(self) -> None:
        """Reset internal buffers and timers."""
        with self._lock:
            self._reset_stream_state_locked()
            self._last_trigger_time = 0.0
            if hasattr(self, "_whisper_detector") and self._whisper_detector:
                self._whisper_detector.reset()
            if self._tier1_engine and hasattr(self._tier1_engine, "Reset"):
                try:
                    self._tier1_engine.Reset()
                except Exception:
                    pass

    def _release_porcupine_native(self) -> None:
        """Release the native Porcupine engine exactly once, if attached."""
        with self._lock:
            engine = self._tier1_engine
            self._tier1_engine = None
            self._porcupine_frame_buffer = None
            if engine is not None:
                try:
                    engine.delete()
                except Exception as e:
                    logger.debug("Porcupine delete() failed during release: %s", e)

    def shutdown(self) -> None:
        """Release native Tier 1 backend resources (Porcupine)."""
        with self._lock:
            if self._engine_type == WakeWordEngineType.PORCUPINE:
                self._release_porcupine_native()

    # -----------------------------------------------------------------------
    # Porcupine backend helpers
    # -----------------------------------------------------------------------
    def _degrade_porcupine_to_acoustic_fallback(self, error: Exception) -> None:
        """Permanently switch this detector off the native Porcupine backend."""
        logger.warning(
            "Porcupine process() failed: %s; permanently switching this detector "
            "to the Tier 2 acoustic fallback.",
            error,
        )
        self._release_porcupine_native()
        self._engine_type = WakeWordEngineType.ACOUSTIC_FALLBACK

    def _process_porcupine_tier(self, resampled: np.ndarray, arr: np.ndarray, in_sr: int) -> bool:
        """Feed audio through the Porcupine frame buffer."""
        if not self._tier1_engine or self._porcupine_frame_buffer is None:
            return False
        try:
            porcupine_sr = self._porcupine_frame_buffer.sample_rate
            if porcupine_sr == self.target_sample_rate:
                pcm_source = resampled
            else:
                pcm_source = resample_audio(arr, in_sr, porcupine_sr)
            int16_pcm = (np.clip(pcm_source, -1.0, 1.0) * 32767.0).astype(np.int16)
            keyword_index = self._porcupine_frame_buffer.process(int16_pcm)
            return keyword_index >= 0
        except Exception as e:
            self._degrade_porcupine_to_acoustic_fallback(e)
            return False

    # -----------------------------------------------------------------------
    # Audio Ingestion & Processing
    # -----------------------------------------------------------------------
    def process_audio_block(self, audio_data: np.ndarray | None) -> bool:
        """
        Processes an incoming audio block (44.1kHz or 16kHz, float32 or int16).
        Returns True if a wake word was detected in this block, False otherwise.
        """
        result = self.feed_audio_block(audio_data)
        return result is not None

    def feed_audio_block(
        self,
        block: np.ndarray | None,
        timestamp: float | None = None,
    ) -> WakeWordResult | None:
        """
        Ingests an audio block into the sliding buffer, classifies wake words,
        enforces refractory cooldowns, and dispatches callbacks.
        """
        if block is None or getattr(block, "size", 0) == 0:
            return None

        with self._lock:
            if not self._enabled:
                return None

        # Sanitize and convert format.
        arr = np.nan_to_num(block, nan=0.0, posinf=0.0, neginf=0.0)

        if np.issubdtype(arr.dtype, np.integer):
            arr = arr.astype(np.float32) / 32768.0
        elif arr.dtype != np.float32:
            arr = arr.astype(np.float32)

        if arr.ndim > 1:
            arr = np.mean(arr, axis=1)

        in_sr = self.sample_rate
        resampled = resample_audio(arr, in_sr, self.target_sample_rate)
        if len(resampled) == 0:
            return None

        with self._lock:
            if not self._enabled:
                return None

            # Push into sliding ring buffer
            n = min(len(resampled), self._buffer_len)
            self._ring_buffer = np.roll(self._ring_buffer, -n)
            self._ring_buffer[-n:] = resampled[-n:]

            now = timestamp if timestamp is not None else time.monotonic()
            in_cooldown = (now - self._last_trigger_time) < self.cooldown_s

            # Porcupine must keep streaming through cooldown
            porcupine_hit = False
            if self._engine_type == WakeWordEngineType.PORCUPINE:
                porcupine_hit = self._process_porcupine_tier(resampled, arr, in_sr)

            # Refractory period / cooldown guard
            if in_cooldown:
                return None

            # Run Tier 1 if present
            detected = False
            keyword = ""
            confidence = 0.0
            engine_name = self._engine_type.value

            if porcupine_hit:
                detected = True
                keyword = "hey_jarvis"
                confidence = 1.0
                engine_name = WakeWordEngineType.PORCUPINE.value
            elif self._engine_type == WakeWordEngineType.VOSK and self._tier1_engine:
                try:
                    int16_pcm = (resampled * 32767.0).astype(np.int16).tobytes()
                    text = ""
                    if self._tier1_engine.AcceptWaveform(int16_pcm):
                        raw_res = self._tier1_engine.Result()
                        if isinstance(raw_res, str):
                            try:
                                res_json = json.loads(raw_res)
                                text = res_json.get("text", "").lower()
                            except json.JSONDecodeError:
                                text = raw_res.lower()
                        elif isinstance(raw_res, dict):
                            text = raw_res.get("text", "").lower()
                    else:
                        if hasattr(self._tier1_engine, "PartialResult"):
                            raw_partial = self._tier1_engine.PartialResult()
                            if isinstance(raw_partial, str):
                                try:
                                    partial_json = json.loads(raw_partial)
                                    text = partial_json.get("partial", "").lower()
                                except json.JSONDecodeError:
                                    text = raw_partial.lower()
                            elif isinstance(raw_partial, dict):
                                text = raw_partial.get("partial", "").lower()

                    keywords = ["jarvis", "hey jarvis", "chào jarvis", "ê jarvis", "ơi jarvis", "hi jarvis", "ok jarvis"]
                    if any(kw in text for kw in keywords):
                        detected = True
                        keyword = "hey_jarvis"
                        confidence = 0.95
                        if hasattr(self._tier1_engine, "Reset"):
                            try:
                                self._tier1_engine.Reset()
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug("Vosk recognition error: %s", e)

            elif self._engine_type == WakeWordEngineType.WHISPER:
                detected, keyword, confidence = self._whisper_detector.analyze_window(
                    self._ring_buffer,
                    sensitivity=self.sensitivity,
                    timestamp=now,
                )
                if detected:
                    engine_name = WakeWordEngineType.WHISPER.value

            # Intermediate fallback: Whisper sliding window if configured as fallback
            if not detected and self.config.get("whisper_fallback", False) and FASTER_WHISPER_AVAILABLE:
                w_detected, w_kw, w_conf = self._whisper_detector.analyze_window(
                    self._ring_buffer,
                    sensitivity=self.sensitivity,
                    timestamp=now,
                )
                if w_detected:
                    detected = True
                    keyword = w_kw
                    confidence = w_conf
                    engine_name = WakeWordEngineType.WHISPER.value

            # Fallback to Tier 2 Acoustic Spectral Detector
            if not detected:
                detected, keyword, confidence = self._spectral_detector.analyze_window(
                    self._ring_buffer,
                    sensitivity=self.sensitivity,
                )
                engine_name = WakeWordEngineType.ACOUSTIC_FALLBACK.value

            if detected:
                self._last_trigger_time = now
                self._trigger_count += 1
                result = WakeWordResult(
                    keyword=keyword or "hey_jarvis",
                    confidence=confidence,
                    timestamp=now,
                    engine=engine_name,
                )

                logger.info(
                    "Wake word detected: [%s] (confidence=%.2f, engine=%s)",
                    result.keyword,
                    result.confidence,
                    result.engine,
                )

                # Dispatch callbacks
                self._dispatch_callbacks(result)
                return result

        return None

    def _dispatch_callbacks(self, result: WakeWordResult) -> None:
        """Invoke registered callbacks in a safe manner."""
        if self.callback:
            try:
                self.callback()
            except Exception as e:
                logger.error("WakeWord callback error: %s", e, exc_info=True)

        if self.on_wake_word:
            try:
                self.on_wake_word(result.keyword, result.confidence)
            except Exception as e:
                logger.error("WakeWord on_wake_word error: %s", e, exc_info=True)
