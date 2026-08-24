"""
Gesture detection package for JARVIS.
Provides multi-pattern acoustic transient gesture classification
(Double Clap, Triple Clap, Clap-Pause-Clap) and state machines.
"""
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.models import (
    ClapEvent,
    DetectorState,
    GestureEvent,
    GesturePatternConfig,
    GestureResult,
    GestureType,
)
from jarvis.gesture.patterns import get_default_patterns

__all__ = [
    "GestureDetector",
    "GestureType",
    "DetectorState",
    "ClapEvent",
    "GesturePatternConfig",
    "GestureResult",
    "GestureEvent",
    "get_default_patterns",
]
