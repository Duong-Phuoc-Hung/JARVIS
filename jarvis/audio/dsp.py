"""
jarvis/audio/dsp.py
===================
Acoustic Signal Processing (DSP) Module for JARVIS.
Provides:
  - Exact RMS energy calculation over float32 and int16 buffers with NaN/Inf sanitization.
  - Dynamic Exponential Moving Average (EMA) noise floor tracking with Quiet Gate protection.
  - Dual-threshold Schmitt trigger for clap transient detection with hysteresis lock.
  - Signal-to-Noise Ratio (SNR) computation in linear and decibel scales.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np


def calculate_rms(block: Optional[np.ndarray]) -> float:
    """
    Calculates Root Mean Square (RMS) energy level for 1D or 2D audio arrays.

    Features:
      - Sanitizes NaN, +Inf, and -Inf values to 0.0.
      - Supports float32/float64 in [-1.0, 1.0] and int16 in [-32768, 32767].
      - Normalizes integer buffers to [0.0, 1.0] range.
      - Handles 1D mono and 2D multi-channel buffers via downmixing.
      - Guarantees non-negative output without numeric overflow.

    Args:
        block: NumPy array of audio samples, or None.

    Returns:
        float: Normalized RMS level in range [0.0, 1.0].
    """
    if block is None:
        return 0.0

    if getattr(block, "size", 0) == 0:
        return 0.0

    # Sanitize NaN / Inf
    arr = np.nan_to_num(block, nan=0.0, posinf=0.0, neginf=0.0)
    if arr.size == 0:
        return 0.0

    # Multi-channel downmixing
    if arr.ndim > 1:
        arr = np.mean(arr, axis=1)

    # Normalize integer formats (e.g. int16)
    if np.issubdtype(arr.dtype, np.integer):
        arr = arr.astype(np.float64) / 32768.0
    elif arr.dtype != np.float64:
        arr = arr.astype(np.float64)

    mean_sq = float(np.mean(arr ** 2))
    return float(np.sqrt(max(0.0, mean_sq)))


# Backward compatibility alias
rms_mono = calculate_rms


@dataclass(frozen=True)
class DSPBlockResult:
    """Structured telemetry output for a processed audio block."""
    rms: float
    noise_floor: float
    threshold: float
    retrigger_level: float
    snr_ratio: float
    snr_db: float
    is_transient: bool
    is_armed: bool
    is_quiet_gated: bool
    timestamp: float = field(default_factory=time.monotonic)

    def to_dict(self) -> Dict[str, Any]:
        """Convert telemetry to standard dictionary matching test expectations."""
        return {
            "rms": self.rms,
            "noise_floor": self.noise_floor,
            "threshold": self.threshold,
            "retrigger_level": self.retrigger_level,
            "snr_ratio": self.snr_ratio,
            "snr_db": self.snr_db,
            "is_transient": self.is_transient,
            "is_armed": self.is_armed,
            "is_quiet_gated": self.is_quiet_gated,
            "timestamp": self.timestamp,
        }


class NoiseFloorTracker:
    """
    Adaptive Exponential Moving Average (EMA) noise floor estimator.

    Features:
      - Dual-rate adaptation (optional asymmetric attack vs decay).
      - Quiet Gate protection freezing floor during loud transients.
      - Non-zero clamping preventing divide-by-zero or threshold collapse.
    """

    def __init__(
        self,
        alpha: float = 0.992,
        alpha_rise: Optional[float] = None,
        alpha_fall: Optional[float] = None,
        quiet_gate_mult: float = 2.2,
        min_floor: float = 1e-7,
        max_floor: float = 1.0,
        initial_floor: float = 0.005,
    ) -> None:
        self.alpha = float(alpha)
        self.alpha_rise = float(alpha_rise) if alpha_rise is not None else self.alpha
        self.alpha_fall = float(alpha_fall) if alpha_fall is not None else self.alpha
        self.quiet_gate_mult = float(quiet_gate_mult)
        self.min_floor = float(min_floor)
        self.max_floor = float(max_floor)
        self.noise_floor = max(self.min_floor, min(float(initial_floor), self.max_floor))

    def update(self, rms_level: float) -> Tuple[float, bool]:
        """
        Updates the estimated noise floor with a new RMS measurement.

        Args:
            rms_level: Current audio block RMS.

        Returns:
            Tuple[float, bool]: (updated_noise_floor, is_quiet_gated)
        """
        quiet_gate = self.noise_floor * self.quiet_gate_mult
        if rms_level < quiet_gate:
            # Active adaptation
            eff_alpha = self.alpha_rise if rms_level > self.noise_floor else self.alpha_fall
            self.noise_floor = eff_alpha * self.noise_floor + (1.0 - eff_alpha) * rms_level
            self.noise_floor = max(self.min_floor, min(self.noise_floor, self.max_floor))
            return self.noise_floor, False
        else:
            # Loud burst: freeze adaptation
            return self.noise_floor, True

    def reset(self, initial_floor: float = 0.005) -> None:
        """Reset noise floor to baseline."""
        self.noise_floor = max(self.min_floor, min(float(initial_floor), self.max_floor))


class SchmittTrigger:
    """
    Dual-threshold Schmitt trigger state machine with hysteresis.

    Prevents transient bounce and chatter by requiring audio energy to fall
    below `retrigger_level` before re-arming for the next clap.
    """

    def __init__(
        self,
        spike_ratio: float = 7.0,
        retrigger_ratio: float = 0.55,
        min_rms: float = 0.012,
    ) -> None:
        self.spike_ratio = float(spike_ratio)
        self.retrigger_ratio = float(retrigger_ratio)
        self.min_rms = float(min_rms)
        self.is_armed: bool = True

    def evaluate(self, rms_level: float, noise_floor: float) -> Tuple[bool, bool, float, float]:
        """
        Evaluates current RMS level against dynamic Schmitt thresholds.

        Args:
            rms_level: Measured RMS level.
            noise_floor: Current adaptive noise floor.

        Returns:
            Tuple[bool, bool, float, float]: (is_transient, is_armed, threshold, retrigger_level)
        """
        threshold = max(noise_floor * self.spike_ratio, self.min_rms)
        retrigger_level = threshold * self.retrigger_ratio

        # Hysteresis reset
        if rms_level < retrigger_level:
            self.is_armed = True

        # Trigger evaluation
        is_transient = False
        if self.is_armed and rms_level >= threshold:
            self.is_armed = False
            is_transient = True

        return is_transient, self.is_armed, threshold, retrigger_level

    def reset(self) -> None:
        """Reset trigger to armed state."""
        self.is_armed = True


class AudioDSPProcessor:
    """
    Unified acoustic signal processor combining RMS calculation,
    adaptive noise floor tracking, and Schmitt trigger transient detection.
    """

    def __init__(
        self,
        noise_floor_alpha: float = 0.992,
        spike_ratio: float = 7.0,
        retrigger_ratio: float = 0.55,
        min_rms: float = 0.012,
        quiet_gate_mult: float = 2.2,
        initial_floor: float = 0.005,
    ) -> None:
        self.tracker = NoiseFloorTracker(
            alpha=noise_floor_alpha,
            quiet_gate_mult=quiet_gate_mult,
            initial_floor=initial_floor,
        )
        self.trigger = SchmittTrigger(
            spike_ratio=spike_ratio,
            retrigger_ratio=retrigger_ratio,
            min_rms=min_rms,
        )

    @property
    def noise_floor(self) -> float:
        return self.tracker.noise_floor

    @noise_floor.setter
    def noise_floor(self, value: float) -> None:
        self.tracker.noise_floor = max(self.tracker.min_floor, min(float(value), self.tracker.max_floor))

    @property
    def spike_armed(self) -> bool:
        return self.trigger.is_armed

    @spike_armed.setter
    def spike_armed(self, value: bool) -> None:
        self.trigger.is_armed = bool(value)

    @property
    def alpha(self) -> float:
        return self.tracker.alpha

    @property
    def spike_ratio(self) -> float:
        return self.trigger.spike_ratio

    @property
    def retrigger_ratio(self) -> float:
        return self.trigger.retrigger_ratio

    @property
    def min_rms(self) -> float:
        return self.trigger.min_rms

    @property
    def quiet_gate_mult(self) -> float:
        return self.tracker.quiet_gate_mult

    def process_block(self, block: np.ndarray) -> Dict[str, Any]:
        """
        Process a single audio buffer and return dictionary of metrics.
        Matches exact contract expected by test suite and legacy callers.
        """
        res = self.process_block_detailed(block)
        return res.to_dict()

    def process_block_detailed(self, block: np.ndarray) -> DSPBlockResult:
        """Process audio block and return immutable DSPBlockResult dataclass."""
        level = calculate_rms(block)
        floor, is_gated = self.tracker.update(level)
        is_transient, is_armed, threshold, retrigger = self.trigger.evaluate(level, floor)

        snr_ratio = level / max(floor, 1e-7)
        snr_db = 20.0 * math.log10(max(snr_ratio, 1e-7))

        return DSPBlockResult(
            rms=level,
            noise_floor=floor,
            threshold=threshold,
            retrigger_level=retrigger,
            snr_ratio=snr_ratio,
            snr_db=snr_db,
            is_transient=is_transient,
            is_armed=is_armed,
            is_quiet_gated=is_gated,
        )

    def reset(self, initial_floor: float = 0.005) -> None:
        """Reset internal tracker and trigger states."""
        self.tracker.reset(initial_floor)
        self.trigger.reset()
