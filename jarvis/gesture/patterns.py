"""
jarvis/gesture/patterns.py
==========================
Default gesture patterns and definitions.
"""
from __future__ import annotations

from jarvis.gesture.models import GesturePatternConfig, GestureType


def get_default_patterns(
    min_double_gap_s: float = 0.05,
    max_double_gap_s: float = 0.35,
    cooldown_s: float = 0.45,
    triple_clap_gap_s: float = 0.40,
    pause_min_s: float = 0.50,
    pause_max_s: float = 1.20,
) -> dict[GestureType, GesturePatternConfig]:
    """Build default gesture patterns matching system configuration."""
    return {
        GestureType.DOUBLE_CLAP: GesturePatternConfig(
            name="double_clap",
            gesture_type=GestureType.DOUBLE_CLAP,
            enabled=True,
            min_gap_s=min_double_gap_s,
            max_gap_s=max_double_gap_s,
            cooldown_s=cooldown_s,
            actions=["spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"],
        ),
        GestureType.TRIPLE_CLAP: GesturePatternConfig(
            name="triple_clap",
            gesture_type=GestureType.TRIPLE_CLAP,
            enabled=True,
            min_gap_s=min_double_gap_s,
            max_gap_s=triple_clap_gap_s,
            cooldown_s=cooldown_s,
            actions=["system_status"],
        ),
        GestureType.CLAP_PAUSE_CLAP: GesturePatternConfig(
            name="clap_pause_clap",
            gesture_type=GestureType.CLAP_PAUSE_CLAP,
            enabled=True,
            min_gap_s=min_double_gap_s,
            max_gap_s=max_double_gap_s,
            pause_min_s=pause_min_s,
            pause_max_s=pause_max_s,
            cooldown_s=cooldown_s,
            actions=["show_overlay"],
        ),
    }
