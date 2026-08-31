"""
jarvis/gesture/hand_models.py
==============================
Immutable, typed data structures for the MediaPipe-style 21-point hand
landmark pipeline. Independent of jarvis.gesture.models (acoustic clap
gesture detector) — no shared types, deliberately, to avoid confusing the
two subsystems.
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any

import numpy as np

NUM_HAND_LANDMARKS = 21


class HandLandmarkIndex(IntEnum):
    """MediaPipe Hands 21-point landmark topology."""
    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_MCP = 5
    INDEX_PIP = 6
    INDEX_DIP = 7
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_PIP = 10
    MIDDLE_DIP = 11
    MIDDLE_TIP = 12
    RING_MCP = 13
    RING_PIP = 14
    RING_DIP = 15
    RING_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


class HandGestureType(str, Enum):
    """Supported semantic hand-gesture classifications."""
    OPEN_PALM = "open_palm"
    FIST = "fist"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    UNKNOWN = "unknown"


class HandGestureBackend(str, Enum):
    """Which optical backend (if any) is available to source real landmarks."""
    MEDIAPIPE = "mediapipe"
    UNAVAILABLE = "unavailable"


class HandTrackerState(str, Enum):
    """Lifecycle state of HandGestureTracker."""
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class HandLandmarkPoint:
    """A single normalized 3D landmark coordinate (MediaPipe convention: x/y in [0,1], z relative depth)."""
    x: float
    y: float
    z: float = 0.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class HandLandmarks:
    """
    Immutable snapshot of exactly 21 hand landmark points for one detected hand.
    """
    points: tuple[HandLandmarkPoint, ...]

    def __post_init__(self) -> None:
        if len(self.points) != NUM_HAND_LANDMARKS:
            raise ValueError(
                f"HandLandmarks requires exactly {NUM_HAND_LANDMARKS} points, got {len(self.points)}"
            )

    @classmethod
    def from_iterable(cls, coords: Iterable[Sequence[float]]) -> HandLandmarks:
        """Build from an iterable of (x, y[, z]) sequences."""
        pts = []
        for c in coords:
            if len(c) == 2:
                pts.append(HandLandmarkPoint(float(c[0]), float(c[1]), 0.0))
            else:
                pts.append(HandLandmarkPoint(float(c[0]), float(c[1]), float(c[2])))
        return cls(points=tuple(pts))

    @classmethod
    def from_array(cls, arr: np.ndarray) -> HandLandmarks:
        """Build from an (21, 2) or (21, 3) numpy array."""
        if arr.shape[0] != NUM_HAND_LANDMARKS:
            raise ValueError(f"Expected {NUM_HAND_LANDMARKS} rows, got {arr.shape[0]}")
        return cls.from_iterable(arr.tolist())

    def point(self, index: HandLandmarkIndex | int) -> HandLandmarkPoint:
        return self.points[int(index)]

    def as_array(self) -> np.ndarray:
        """Return an (21, 3) float64 ndarray view of this landmark set."""
        return np.array([p.as_tuple() for p in self.points], dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        return {"points": [p.as_tuple() for p in self.points]}


@dataclass(frozen=True)
class HandGestureResult:
    """Structured, semantic outcome emitted when a hand gesture is recognized."""
    gesture_type: HandGestureType
    confidence: float
    timestamp: float = field(default_factory=time.time)
    handedness: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gesture_type": self.gesture_type.value,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "handedness": self.handedness,
            "metadata": dict(self.metadata),
        }
