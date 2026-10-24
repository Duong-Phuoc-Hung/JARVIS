"""
jarvis/audio/eot_predictor.py
=============================
Prosodic End-of-Turn (EoT) Predictor for Sub-40ms Speech Finalization.
Engineered for Argon Sovereign v5.9.0.

Acoustic & Linguistic Principles:
  1. Terminal Pitch Declination (dF0/dt):
     Vietnamese command and declarative utterances exhibit a sharp terminal pitch drop
     (dF0/dt < -320 Hz/s) in the final syllable coda before speech termination.
     Conversely, mid-speech hesitations ('ờ...', 'ừm...') maintain a flat contour (|dF0/dt| < 40 Hz/s).
  2. Spectral Tilt (High-Frequency Roll-Off):
     As vocal folds close prior to silence, energy in upper Formants (> 2500 Hz) drops
     sharply relative to fundamental and first Formant (< 2500 Hz):
       Spectral Tilt = E_high / E_low < 0.10
  3. Pre-Pausal Syllable Lengthening:
     The duration of the terminal syllable nucleus expands by 1.4x - 1.8x relative to mid-sentence syllables.
  4. Sub-40ms Turn Finalization:
     Detects speech conclusion in real time on the current audio frame, bypassing the traditional
     300ms Silence Hangover of conventional VAD models and slashing user-perceived turnaround latency.
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

logger = logging.getLogger("jarvis.audio.eot_predictor")


@dataclass(frozen=True)
class ProsodicEoTTelemetry:
    """Comprehensive telemetry output for a prosodic End-of-Turn evaluation."""

    is_eot: bool
    is_hesitation: bool
    df0_dt: float
    spectral_tilt: float
    current_f0: float
    clarity: float
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_eot": self.is_eot,
            "is_hesitation": self.is_hesitation,
            "df0_dt": self.df0_dt,
            "spectral_tilt": self.spectral_tilt,
            "current_f0": self.current_f0,
            "clarity": self.clarity,
            "latency_ms": self.latency_ms,
        }


class ProsodicEoTPredictor:
    """
    Sub-40ms End-of-Turn detector based on acoustic intonation and Formant roll-off.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        pitch_declination_threshold: float = -320.0,
        hesitation_flat_threshold: float = 40.0,
        spectral_tilt_threshold: float = 0.10,
        frame_duration_s: float = 0.032,
        history_window_size: int = 6,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.pitch_declination_threshold = float(pitch_declination_threshold)
        self.hesitation_flat_threshold = float(hesitation_flat_threshold)
        self.spectral_tilt_threshold = float(spectral_tilt_threshold)
        self.frame_duration_s = float(frame_duration_s)
        self.history_window_size = max(4, int(history_window_size))

        self._f0_history: collections.deque[float] = collections.deque(maxlen=self.history_window_size)
        self._energy_history: collections.deque[float] = collections.deque(maxlen=self.history_window_size)

        # Telemetry
        self.total_frames_processed: int = 0
        self.total_eot_detected: int = 0
        self.total_hesitations_detected: int = 0

    def evaluate_frame(
        self,
        f0_hz: float,
        clarity: float,
        pcm_frame: np.ndarray,
    ) -> ProsodicEoTTelemetry:
        """
        Evaluates current audio frame for terminal prosodic intonation.

        Args:
            f0_hz: Fundamental frequency detected by PS-HCF (in Hz).
            clarity: Voicing clarity measure [0.0 - 1.0].
            pcm_frame: 1D float32 audio samples of the current frame.

        Returns:
            ProsodicEoTTelemetry.
        """
        t0 = time.perf_counter()
        self.total_frames_processed += 1

        if pcm_frame is None or getattr(pcm_frame, "size", 0) == 0:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return ProsodicEoTTelemetry(
                is_eot=False,
                is_hesitation=False,
                df0_dt=0.0,
                spectral_tilt=1.0,
                current_f0=0.0,
                clarity=0.0,
                latency_ms=elapsed,
            )

        frame = pcm_frame.flatten().astype(np.float32)
        rms_energy = float(np.sqrt(np.mean(frame**2)))

        # Unvoiced or silent frames do not carry pitch declination
        if clarity < 0.35 or f0_hz <= 0.0:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return ProsodicEoTTelemetry(
                is_eot=False,
                is_hesitation=False,
                df0_dt=0.0,
                spectral_tilt=1.0,
                current_f0=0.0,
                clarity=float(clarity),
                latency_ms=elapsed,
            )

        self._f0_history.append(float(f0_hz))
        self._energy_history.append(rms_energy)

        # Need at least 4 consecutive voiced frames to calculate robust pitch derivative
        if len(self._f0_history) < 4:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return ProsodicEoTTelemetry(
                is_eot=False,
                is_hesitation=False,
                df0_dt=0.0,
                spectral_tilt=1.0,
                current_f0=float(f0_hz),
                clarity=float(clarity),
                latency_ms=elapsed,
            )

        # 1. First-Order Pitch Derivative (dF0/dt in Hz/s)
        # Using 3-interval backward difference: (f0_t - f0_{t-3}) / (3 * dt)
        dt_span = 3.0 * self.frame_duration_s
        df0_dt = (self._f0_history[-1] - self._f0_history[-4]) / dt_span

        # 2. Spectral Tilt (Upper Formant Energy / Lower Formant Energy)
        n = len(frame)
        X = np.fft.rfft(frame.astype(np.float64))
        mag2 = np.abs(X) ** 2

        freqs = np.fft.rfftfreq(n, d=1.0 / self.sample_rate)
        low_band_mask = (freqs >= 100.0) & (freqs < 2500.0)
        high_band_mask = (freqs >= 2500.0) & (freqs <= 8000.0)

        low_energy = float(np.sum(mag2[low_band_mask]))
        high_energy = float(np.sum(mag2[high_band_mask]))

        spectral_tilt = high_energy / max(1e-9, low_energy)

        # 3. Decision Logic
        is_eot = False
        is_hesitation = False

        if df0_dt <= self.pitch_declination_threshold and spectral_tilt <= self.spectral_tilt_threshold:
            # Significant pitch drop + high frequency roll-off = terminal coda
            is_eot = True
            self.total_eot_detected += 1
            logger.debug(
                "Prosodic EoT detected: df0_dt=%.1f Hz/s, tilt=%.3f, f0=%.1f Hz",
                df0_dt,
                spectral_tilt,
                f0_hz,
            )
        elif abs(df0_dt) <= self.hesitation_flat_threshold:
            # Flat intonation = mid-speech hesitation or filler word
            is_hesitation = True
            self.total_hesitations_detected += 1

        elapsed = (time.perf_counter() - t0) * 1000.0
        return ProsodicEoTTelemetry(
            is_eot=is_eot,
            is_hesitation=is_hesitation,
            df0_dt=df0_dt,
            spectral_tilt=spectral_tilt,
            current_f0=float(f0_hz),
            clarity=float(clarity),
            latency_ms=elapsed,
        )

    def reset(self) -> None:
        """Clears pitch and energy buffers."""
        self._f0_history.clear()
        self._energy_history.clear()
