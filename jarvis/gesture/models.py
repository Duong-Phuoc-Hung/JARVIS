"""
jarvis/gesture/models.py
========================
Data structures, enums, and event models for acoustic gesture recognition.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GestureType(str, Enum):
    """Supported acoustic gesture types."""
    DOUBLE_CLAP = "double_clap"
    TRIPLE_CLAP = "triple_clap"
    CLAP_PAUSE_CLAP = "clap_pause_clap"
    SINGLE_CLAP = "single_clap"
    CUSTOM = "custom"


class DetectorState(str, Enum):
    """Internal state machine states."""
    IDLE = "idle"
    WAIT_CLAP_2 = "wait_clap_2"
    PENDING_DISAMBIGUATION = "pending_disambiguation"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class ClapEvent:
    """Acoustic transient event detected by DSP frontend."""
    timestamp: float                    # Monotonic time in seconds (time.monotonic())
    amplitude: float                    # Normalized RMS or peak amplitude [0.0, 1.0]
    duration: float = 0.04              # Transient duration in seconds (~block size)
    noise_floor: float = 0.0            # Baseline noise floor at trigger moment
    threshold: float = 0.0              # Spike detection threshold
    snr_ratio: float = 0.0              # Signal-to-noise ratio (amplitude / noise_floor)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "amplitude": self.amplitude,
            "duration": self.duration,
            "noise_floor": self.noise_floor,
            "threshold": self.threshold,
            "snr_ratio": self.snr_ratio,
        }


@dataclass
class GesturePatternConfig:
    """Configuration and timing thresholds for a specific gesture pattern."""
    name: str
    gesture_type: GestureType
    enabled: bool = True
    actions: list[str] = field(default_factory=list)
    min_gap_s: float = 0.05             # Minimum interval between claps (debounce)
    max_gap_s: float = 0.35             # Maximum interval between claps
    pause_min_s: float = 0.50           # Minimum pause duration (for syncopation)
    pause_max_s: float = 1.20           # Maximum pause duration
    cooldown_s: float = 0.45            # Post-trigger debounce cooldown
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "gesture_type": self.gesture_type.value,
            "enabled": self.enabled,
            "actions": list(self.actions),
            "min_gap_s": self.min_gap_s,
            "max_gap_s": self.max_gap_s,
            "pause_min_s": self.pause_min_s,
            "pause_max_s": self.pause_max_s,
            "cooldown_s": self.cooldown_s,
            "metadata": dict(self.metadata),
        }


@dataclass
class GestureResult:
    """Structured detection outcome emitted when a gesture pattern is recognized."""
    gesture_type: GestureType
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    claps: list[ClapEvent] = field(default_factory=list)
    intervals: list[float] = field(default_factory=list)
    actions_triggered: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def pattern_type(self) -> str:
        """Alias for compatibility with uppercase test strings (DOUBLE_CLAP, TRIPLE_CLAP, etc.)."""
        return self.gesture_type.value.upper()

    def to_dict(self) -> dict[str, Any]:
        return {
            "gesture_type": self.gesture_type.value,
            "pattern_type": self.pattern_type,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "claps": [c.to_dict() for c in self.claps],
            "intervals": list(self.intervals),
            "actions_triggered": list(self.actions_triggered),
            "metadata": dict(self.metadata),
        }


# Direct alias for compatibility with test suites expecting GestureEvent
GestureEvent = GestureResult
