"""
tests/test_gesture_detector.py
==============================
Test Suite for Multi-Pattern Acoustic Gesture Recognition.
Covering:
  - F-05: Double Clap Detection (0.05s <= gap <= 0.35s, cooldown 0.45s)
  - F-06: Triple Clap Detection (3 consecutive transients, total duration <= 0.85s)
  - F-07: Clap-Pause-Clap Detection (Rhythmic syncopation with 0.50s - 1.20s pause)
"""

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

from tests.test_audio_dsp import AudioDSPProcessor, rms_mono


@dataclass
class GestureEvent:
    pattern_type: str
    timestamp: float
    confidence: float = 1.0


class GestureDetector:
    """State machine for multi-pattern acoustic transient gesture detection."""

    def __init__(
        self,
        min_double_gap_s: float = 0.05,
        max_double_gap_s: float = 0.35,
        cooldown_s: float = 0.45,
        triple_clap_gap_s: float = 0.40,
        pause_min_s: float = 0.50,
        pause_max_s: float = 1.20,
    ):
        self.min_double_gap_s = min_double_gap_s
        self.max_double_gap_s = max_double_gap_s
        self.cooldown_s = cooldown_s
        self.triple_clap_gap_s = triple_clap_gap_s
        self.pause_min_s = pause_min_s
        self.pause_max_s = pause_max_s
        self.dsp = AudioDSPProcessor()

    def process_stream(self, buffer: np.ndarray, block_size: int = 1764) -> List[GestureEvent]:
        # Collect transient spike times
        hit_times = []
        cur_time = 0.0
        dt = block_size / 44100.0

        for i in range(0, len(buffer), block_size):
            chunk = buffer[i : i + block_size]
            if len(chunk) < block_size:
                pad = np.zeros(block_size - len(chunk), dtype=buffer.dtype)
                chunk = np.concatenate([chunk, pad])
            res = self.dsp.process_block(chunk)
            if res["is_transient"]:
                # Filter bounce/echo (< min_double_gap)
                if not hit_times or (cur_time - hit_times[-1]) >= self.min_double_gap_s:
                    hit_times.append(cur_time)
            cur_time += dt

        # Classify collected transient hit times
        events: List[GestureEvent] = []
        i = 0
        while i < len(hit_times):
            # Check Triple Clap (3 hits)
            if i + 2 < len(hit_times):
                t1, t2, t3 = hit_times[i], hit_times[i+1], hit_times[i+2]
                g1, g2 = t2 - t1, t3 - t2
                if (self.min_double_gap_s <= g1 <= self.triple_clap_gap_s) and \
                   (self.min_double_gap_s <= g2 <= self.triple_clap_gap_s) and \
                   (t3 - t1 <= 0.85):
                    events.append(GestureEvent(pattern_type="TRIPLE_CLAP", timestamp=t3))
                    i += 3
                    continue

            # Check Clap-Pause-Clap (2 hits with pause)
            if i + 1 < len(hit_times):
                t1, t2 = hit_times[i], hit_times[i+1]
                gap = t2 - t1
                if self.pause_min_s <= gap <= self.pause_max_s:
                    events.append(GestureEvent(pattern_type="CLAP_PAUSE_CLAP", timestamp=t2))
                    i += 2
                    continue

            # Check Double Clap (2 hits with standard gap)
            if i + 1 < len(hit_times):
                t1, t2 = hit_times[i], hit_times[i+1]
                gap = t2 - t1
                if self.min_double_gap_s <= gap <= self.max_double_gap_s:
                    events.append(GestureEvent(pattern_type="DOUBLE_CLAP", timestamp=t2))
                    i += 2
                    continue

            # Single isolated clap or debounced
            i += 1

        # Apply cooldown filter between recognized events
        filtered: List[GestureEvent] = []
        for ev in events:
            if not filtered or (ev.timestamp - filtered[-1].timestamp) >= self.cooldown_s:
                filtered.append(ev)

        return filtered


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_gesture_detector_double_clap_success_tier1(mock_audio_stream):
    """
    [F-05] Validate detection of 2 transient claps separated by 150ms (within 0.05s-0.35s window).
    """
    detector = GestureDetector()
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15, leading_silence_s=0.1, trailing_silence_s=0.5)
    events = detector.process_stream(pcm)

    assert len(events) == 1
    assert events[0].pattern_type == "DOUBLE_CLAP"


def test_gesture_detector_triple_clap_success_tier1(mock_audio_stream):
    """
    [F-06] Validate detection of 3 consecutive claps within timing thresholds (gaps 0.15s, total <= 0.85s).
    """
    detector = GestureDetector()
    pcm = mock_audio_stream.generate_triple_clap(gap1_s=0.15, gap2_s=0.15, leading_silence_s=0.1)
    events = detector.process_stream(pcm)

    assert len(events) == 1
    assert events[0].pattern_type == "TRIPLE_CLAP"


def test_gesture_detector_clap_pause_clap_success_tier1(mock_audio_stream):
    """
    [F-07] Validate detection of syncopated rhythm pattern (clap-pause-clap) with 750ms pause.
    """
    detector = GestureDetector()
    pcm = mock_audio_stream.generate_clap_pause_clap(gap_s=0.75, leading_silence_s=0.1)
    events = detector.process_stream(pcm)

    assert len(events) == 1
    assert events[0].pattern_type == "CLAP_PAUSE_CLAP"


def test_gesture_detector_debounce_cooldown_tier1(mock_audio_stream):
    """
    [F-05] Validate that 3rd transient occurring within COOLDOWN_S (0.45s) after a double-clap is debounced.
    """
    detector = GestureDetector(cooldown_s=0.45)
    pcm = mock_audio_stream.generate_claps([0.10, 0.25, 0.40], total_s=1.2)
    events = detector.process_stream(pcm)

    # 3 rapid transients form either 1 triple clap or 1 double clap, but not redundant double triggers
    assert len(events) == 1


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_gesture_detector_gap_too_short_echo_rejection_tier2(mock_audio_stream):
    """
    [F-05] Validate rejection of acoustic echo where 2nd hit occurs at 30ms (< MIN_DOUBLE_GAP_S = 0.05s).
    """
    detector = GestureDetector(min_double_gap_s=0.05)
    pcm = mock_audio_stream.generate_claps([0.10, 0.13], total_s=0.8)
    events = detector.process_stream(pcm)

    assert len(events) == 0


def test_gesture_detector_gap_too_long_timeout_tier2(mock_audio_stream):
    """
    [F-05] Validate timing window expiry when 2nd hit occurs at 420ms (> MAX_DOUBLE_GAP_S = 0.35s and < pause min 0.50s).
    """
    detector = GestureDetector(max_double_gap_s=0.35, pause_min_s=0.50)
    pcm = mock_audio_stream.generate_claps([0.10, 0.52], total_s=1.0)
    events = detector.process_stream(pcm)

    assert len(events) == 0


def test_gesture_detector_continuous_clapping_storm_tier2(mock_audio_stream):
    """
    [F-06] Validate that continuous rapid clapping (10 hits in 1s) does not crash or spam un-throttled events.
    """
    detector = GestureDetector(cooldown_s=0.45)
    times = [0.05 * i for i in range(1, 10)]
    pcm = mock_audio_stream.generate_claps(times, total_s=1.5)
    events = detector.process_stream(pcm)

    assert len(events) <= 2
