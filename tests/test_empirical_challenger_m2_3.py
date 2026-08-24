"""
tests/test_empirical_challenger_m2_3.py
========================================
Milestone 2 Iteration 2 Hardening Empirical Challenge & Adversarial Stress Suite.
Author: Challenger 3 (critic, specialist)

Target Hardening Verification:
1. Rapid chatter burst suppression (<50ms intervals) under diverse waveforms & pulse counts.
2. Dead-zone interval handling (0.35s to 0.50s) clean re-arming without swallowing or stalling.
3. Boundary timestamps float epsilon precision (0.050s, 0.350s, 0.450s, 0.500s, 0.850s, 1.200s).
4. AudioEngine.feed_virtual_audio seamless streaming, end-to-end DSP-Gesture-Action pipeline, and concurrency.
5. Extensive adversarial edge cases, state machine stress, and DSP dynamic stability.
"""
from __future__ import annotations

import concurrent.futures
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import numpy as np
import pytest

from jarvis.audio.dsp import (
    AudioDSPProcessor,
    DSPBlockResult,
    NoiseFloorTracker,
    SchmittTrigger,
    calculate_rms,
    rms_mono,
)
from jarvis.audio.engine import (
    AudioDeviceInfo,
    AudioEngine,
    AudioEngineMode,
    MicrophoneProbeManager,
)
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionDefinition, ActionResult, PrivilegeLevel, RequesterContext
from jarvis.gesture.detector import GestureDetector, EPS
from jarvis.gesture.models import (
    ClapEvent,
    DetectorState,
    GesturePatternConfig,
    GestureResult,
    GestureType,
)
from jarvis.gesture.patterns import get_default_patterns


# ============================================================================
# 1. RAPID CHATTER BURST EMPIRICAL STRESS TESTS (<50ms)
# ============================================================================

def test_chatter_bursts_various_sub_50ms_intervals():
    """
    Stress-test high-frequency pulse trains at 5ms, 10ms, 15ms, 25ms, 35ms, 45ms, 49.5ms intervals.
    Each pulse train contains 5 to 50 spikes. None should EVER trigger a gesture.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35)

    intervals = [0.005, 0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.045, 0.0495]
    for interval in intervals:
        det.reset()
        t = 1.000
        triggers: List[GestureResult] = []
        for _ in range(30):
            res = det.feed_clap(ClapEvent(timestamp=t, amplitude=0.85))
            if res:
                triggers.append(res)
            t += interval

        # Tick far past disambiguation timeout
        res_tick = det.tick(now=t + 1.5)
        if res_tick:
            triggers.append(res_tick)

        assert len(triggers) == 0, f"Interval {interval*1000:.1f}ms produced false triggers: {triggers}"


def test_chatter_burst_followed_by_legitimate_double_clap():
    """
    Verify that an acoustic chatter burst (e.g. 10 clicks @ 15ms gap from 1.000s to 1.135s):
    Case A: Followed by dead-zone gap (0.42s from t1) at 1.420s -> resets buffer to [1.420s] -> Clap 2 at 1.570s triggers DOUBLE_CLAP.
    Case B: Followed by stale eviction tick at 3.0s -> new double clap at 3.500s and 3.650s triggers DOUBLE_CLAP.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    
    # --- Case A: Dead-zone reset after chatter ---
    # 1. Chatter burst: 10 pulses spaced 15ms apart (1.000s to 1.135s)
    t = 1.000
    for _ in range(10):
        res = det.feed_clap(ClapEvent(timestamp=t, amplitude=0.8))
        assert res is None
        t += 0.015  # Ends at 1.135s

    # 2. Dead-zone clap at 1.420s (gap from 1.000s is 0.420s in dead zone [0.35, 0.50])
    c1 = ClapEvent(timestamp=1.420, amplitude=0.85)
    assert det.feed_clap(c1) is None
    assert len(det._clap_buffer) == 1
    assert math.isclose(det._clap_buffer[0].timestamp, 1.420, abs_tol=1e-4)

    # 3. Legitimate Clap 2 at 1.570s (gap 0.150s from 1.420s)
    c2 = ClapEvent(timestamp=1.570, amplitude=0.85)
    det.feed_clap(c2)

    # 4. Disambiguate
    res = det.tick(now=1.950)
    assert res is not None, "Legitimate double clap after dead-zone reset was not recognized!"
    assert res.gesture_type == GestureType.DOUBLE_CLAP
    assert len(res.claps) == 2
    assert math.isclose(res.claps[0].timestamp, 1.420, abs_tol=1e-4)
    assert math.isclose(res.claps[1].timestamp, 1.570, abs_tol=1e-4)

    # --- Case B: Stale buffer timeout eviction after chatter ---
    det.reset()
    t = 1.000
    for _ in range(10):
        det.feed_clap(ClapEvent(timestamp=t, amplitude=0.8))
        t += 0.015

    # Tick at 3.0s (exceeds pause_max_s + 0.5s = 1.7s) -> evicts stale buffer
    assert det.tick(now=3.000) is None
    assert len(det._clap_buffer) == 0

    # Fresh double clap at 3.500s and 3.650s
    det.feed_clap(ClapEvent(timestamp=3.500, amplitude=0.85))
    det.feed_clap(ClapEvent(timestamp=3.650, amplitude=0.85))
    res_b = det.tick(now=4.050)
    assert res_b is not None and res_b.gesture_type == GestureType.DOUBLE_CLAP
    assert math.isclose(res_b.claps[0].timestamp, 3.500, abs_tol=1e-4)
    assert math.isclose(res_b.claps[1].timestamp, 3.650, abs_tol=1e-4)


def test_chatter_burst_during_post_trigger_cooldown():
    """
    Verify that chatter arriving during post-trigger cooldown (0.45s) is fully suppressed
    and does NOT corrupt state or cause false triggers when cooldown expires.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, cooldown_s=0.45)

    # Trigger legitimate double clap at 1.0s and 1.2s
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=1.20, amplitude=0.8))
    res = det.tick(now=1.56)  # Disambiguates and triggers at 1.56s (last_trigger_time = 1.56)
    assert res is not None and res.gesture_type == GestureType.DOUBLE_CLAP

    # During cooldown (1.56s to 2.01s), hammer with 20 chatter pulses @ 10ms gap
    t_chatter = 1.60
    for _ in range(20):
        assert det.feed_clap(ClapEvent(timestamp=t_chatter, amplitude=0.8)) is None
        t_chatter += 0.010  # Ends at 1.79s

    # Tick inside cooldown and after cooldown
    assert det.tick(now=1.90) is None
    assert det.tick(now=2.10) is None

    # After cooldown expires (> 1.56 + 0.45 = 2.01s), fire new legitimate double clap
    t_new = 2.10
    det.feed_clap(ClapEvent(timestamp=t_new, amplitude=0.85))
    det.feed_clap(ClapEvent(timestamp=t_new + 0.15, amplitude=0.85))
    res2 = det.tick(now=t_new + 0.55)
    assert res2 is not None and res2.gesture_type == GestureType.DOUBLE_CLAP
    assert res2.claps[0].timestamp == t_new


def test_random_jitter_chatter_bursts():
    """
    Verify random jitter chatter (100 pulses with random intervals in [1ms, 49ms]) produces zero triggers.
    """
    np.random.seed(42)
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35)

    t = 10.0
    triggers = []
    for _ in range(100):
        dt = float(np.random.uniform(0.001, 0.048))
        t += dt
        res = det.feed_clap(ClapEvent(timestamp=t, amplitude=0.9))
        if res:
            triggers.append(res)

    res_tick = det.tick(now=t + 1.0)
    if res_tick:
        triggers.append(res_tick)

    assert len(triggers) == 0, f"Random chatter produced false triggers: {triggers}"


# ============================================================================
# 2. DEAD-ZONE INTERVAL RESILIENCE (0.35s to 0.50s)
# ============================================================================

def test_dead_zone_interval_comprehensive_matrix():
    """
    Test dead-zone gaps across the full range: 0.351s, 0.375s, 0.400s, 0.425s, 0.450s, 0.475s, 0.490s, 0.495s, 0.499s.
    In all cases:
      - Clap 1 -> dead-zone Clap 2 must NOT trigger any gesture.
      - Clap 2 must become the new Clap 1.
      - Subsequent valid Clap 3 must pair with Clap 2 into a DOUBLE_CLAP.
    """
    dead_zone_gaps = [0.351, 0.360, 0.380, 0.400, 0.420, 0.450, 0.470, 0.490, 0.495, 0.499]
    
    for gap in dead_zone_gaps:
        det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
        
        t1 = 10.000
        t2 = t1 + gap
        t3 = t2 + 0.150  # 0.150s gap from t2 (valid double clap)

        # Clap 1
        assert det.feed_clap(ClapEvent(timestamp=t1, amplitude=0.8)) is None
        assert len(det._clap_buffer) == 1

        # Clap 2 (dead zone)
        assert det.feed_clap(ClapEvent(timestamp=t2, amplitude=0.8)) is None
        assert len(det._clap_buffer) == 1, f"Buffer failed to reset for dead-zone gap {gap}s"
        assert math.isclose(det._clap_buffer[0].timestamp, t2, abs_tol=1e-4)

        # Clap 3 (valid interval from Clap 2)
        assert det.feed_clap(ClapEvent(timestamp=t3, amplitude=0.8)) is None
        assert len(det._clap_buffer) == 2

        # Disambiguate
        res = det.tick(now=t3 + 0.40)
        assert res is not None, f"Failed to trigger double clap after dead-zone gap {gap}s"
        assert res.gesture_type == GestureType.DOUBLE_CLAP
        assert math.isclose(res.claps[0].timestamp, t2, abs_tol=1e-4)
        assert math.isclose(res.claps[1].timestamp, t3, abs_tol=1e-4)


def test_dead_zone_followed_by_syncopated_pause():
    """
    Clap 1 -> (0.42s dead zone) -> Clap 2 -> (0.75s pause) -> Clap 3.
    Clap 2 resets buffer to [Clap 2], and Clap 3 triggers CLAP_PAUSE_CLAP with interval 0.75s.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)

    t1 = 1.000
    t2 = t1 + 0.420  # dead zone
    t3 = t2 + 0.750  # valid pause

    det.feed_clap(ClapEvent(timestamp=t1, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=t2, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=t3, amplitude=0.8))

    assert res is not None, "Failed to trigger CLAP_PAUSE_CLAP after dead-zone reset"
    assert res.gesture_type == GestureType.CLAP_PAUSE_CLAP
    assert len(res.claps) == 2
    assert math.isclose(res.claps[0].timestamp, t2, abs_tol=1e-4)
    assert math.isclose(res.claps[1].timestamp, t3, abs_tol=1e-4)


def test_multiple_chained_dead_zone_claps():
    """
    Series of 5 claps each spaced 0.40s apart (all in dead zone).
    Each clap should cleanly replace the previous clap as Clap 1.
    A final 6th clap arriving 0.15s after Clap 5 triggers DOUBLE_CLAP.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)

    t = 1.000
    for i in range(5):
        det.feed_clap(ClapEvent(timestamp=t, amplitude=0.8))
        assert len(det._clap_buffer) == 1
        assert math.isclose(det._clap_buffer[0].timestamp, t, abs_tol=1e-4)
        t += 0.400

    # 6th clap arriving 0.15s after 5th clap
    t6 = (t - 0.400) + 0.150
    det.feed_clap(ClapEvent(timestamp=t6, amplitude=0.8))
    assert len(det._clap_buffer) == 2

    res = det.tick(now=t6 + 0.400)
    assert res is not None
    assert res.gesture_type == GestureType.DOUBLE_CLAP
    assert math.isclose(res.claps[1].timestamp, t6, abs_tol=1e-4)


def test_mismatched_third_clap_in_dead_zone_resets():
    """
    Clap 1 -> (0.15s) -> Clap 2 -> (0.45s dead zone) -> Clap 3.
    Clap 3 does not match Triple Clap (gap 0.45s > 0.40s) nor Pause (gap 0.45s < 0.50s).
    State machine must reset buffer to [Clap 3].
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, triple_clap_gap_s=0.40, pause_min_s=0.50, pause_max_s=1.20)

    t1 = 1.000
    t2 = 1.150
    t3 = 1.150 + 0.450  # 1.600s

    det.feed_clap(ClapEvent(timestamp=t1, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=t2, amplitude=0.8))
    assert len(det._clap_buffer) == 2
    assert det._state == DetectorState.PENDING_DISAMBIGUATION

    res = det.feed_clap(ClapEvent(timestamp=t3, amplitude=0.8))
    assert res is None
    assert len(det._clap_buffer) == 1
    assert math.isclose(det._clap_buffer[0].timestamp, t3, abs_tol=1e-4)


# ============================================================================
# 3. BOUNDARY TIMESTAMPS & FLOAT EPSILON TOLERANCE
# ============================================================================

def test_exact_float_arithmetic_boundaries():
    """
    Test nominal boundaries with float representations that produce IEEE 754 precision residuals.
    For example: 1.000 + 0.350 = 1.350 (gap = 0.3500000000000001)
    All exact boundaries must evaluate predictably without false rejections.
    """
    det = GestureDetector(
        min_double_gap_s=0.050,
        max_double_gap_s=0.350,
        cooldown_s=0.450,
        triple_clap_gap_s=0.400,
        pause_min_s=0.500,
        pause_max_s=1.200,
    )

    # 1. Exact min_double_gap (0.050s)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=1.050, amplitude=0.8))
    res = det.tick(now=1.450)
    assert res is not None and res.gesture_type == GestureType.DOUBLE_CLAP

    # 2. Exact max_double_gap (0.350s)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=1.350, amplitude=0.8))
    res = det.tick(now=1.750)
    assert res is not None and res.gesture_type == GestureType.DOUBLE_CLAP

    # 3. Exact pause_min (0.500s)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=1.500, amplitude=0.8))
    assert res is not None and res.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 4. Exact pause_max (1.200s)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=2.200, amplitude=0.8))
    assert res is not None and res.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 5. Triple Clap with 0.350s + 0.350s (total span 0.700s)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=1.350, amplitude=0.8))
    res_trip = det.feed_clap(ClapEvent(timestamp=1.700, amplitude=0.8))
    assert res_trip is not None and res_trip.gesture_type == GestureType.TRIPLE_CLAP

    # 6. Triple Clap with leg 2 = 0.400s (gap2 = 0.400s <= 0.400s + EPS)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=1.350, amplitude=0.8))
    res_trip2 = det.feed_clap(ClapEvent(timestamp=1.750, amplitude=0.8))
    assert res_trip2 is not None and res_trip2.gesture_type == GestureType.TRIPLE_CLAP


def test_float_epsilon_boundary_rejection_safety():
    """
    Verify that gaps truly OUTSIDE valid windows (beyond EPS) are rejected:
    - 0.050s - 0.002s (0.048s) -> Rejected as echo
    - 0.350s + 0.005s (0.355s) -> Dead-zone reset
    - 0.500s - 0.005s (0.495s) -> Dead-zone reset
    - 1.200s + 0.005s (1.205s) -> Stale rejection
    """
    det = GestureDetector(min_double_gap_s=0.050, max_double_gap_s=0.350, pause_min_s=0.500, pause_max_s=1.200)

    # 0.048s (Echo)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    assert det.feed_clap(ClapEvent(timestamp=1.048, amplitude=0.8)) is None
    assert len(det._clap_buffer) == 1

    # 0.355s (Dead-zone)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    assert det.feed_clap(ClapEvent(timestamp=1.355, amplitude=0.8)) is None
    assert len(det._clap_buffer) == 1
    assert math.isclose(det._clap_buffer[0].timestamp, 1.355, abs_tol=1e-4)

    # 0.495s (Dead-zone)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    assert det.feed_clap(ClapEvent(timestamp=1.495, amplitude=0.8)) is None
    assert len(det._clap_buffer) == 1
    assert math.isclose(det._clap_buffer[0].timestamp, 1.495, abs_tol=1e-4)

    # 1.205s (Beyond pause max)
    det.reset()
    det.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    assert det.feed_clap(ClapEvent(timestamp=2.205, amplitude=0.8)) is None
    assert len(det._clap_buffer) == 1
    assert math.isclose(det._clap_buffer[0].timestamp, 2.205, abs_tol=1e-4)


# ============================================================================
# 4. AUDIO ENGINE FEED_VIRTUAL_AUDIO & FULL PIPELINE TESTS
# ============================================================================

def test_audio_engine_feed_virtual_audio_chunking_and_padding():
    """
    Verify feed_virtual_audio correctly splits arbitrary length buffers into block_size chunks
    and zero-pads partial final chunks.
    """
    dispatched_blocks = []
    sample_rate = 44100
    block_ms = 40  # block_size = 1764

    engine = AudioEngine(
        sample_rate=sample_rate,
        block_ms=block_ms,
        mode=AudioEngineMode.MOCK,
        on_audio_block=lambda blk: dispatched_blocks.append(blk.copy()),
    )
    engine.start_stream()

    # Feed buffer of 4000 samples (2 full blocks of 1764 = 3528, plus partial block of 472 samples)
    buffer = np.ones(4000, dtype=np.float32) * 0.75
    engine.feed_virtual_audio(buffer)

    assert len(dispatched_blocks) == 3
    # First 2 blocks should be full 0.75
    assert len(dispatched_blocks[0]) == 1764
    assert np.allclose(dispatched_blocks[0], 0.75)
    assert len(dispatched_blocks[1]) == 1764
    assert np.allclose(dispatched_blocks[1], 0.75)

    # 3rd block has 472 samples of 0.75, remainder padded with 0.0
    assert len(dispatched_blocks[2]) == 1764
    assert np.allclose(dispatched_blocks[2][:472], 0.75)
    assert np.allclose(dispatched_blocks[2][472:], 0.0)

    engine.stop_stream()


def test_audio_engine_end_to_end_virtual_audio_to_dispatcher():
    """
    End-to-end integration:
    AudioEngine -> feed_virtual_audio -> DSP -> GestureDetector -> ActionDispatcher.
    Synthesize an audio PCM buffer with 2 loud acoustic claps spaced 200ms apart.
    Verify action is dispatched.
    """
    sample_rate = 44100
    block_ms = 40
    block_size = int(sample_rate * (block_ms / 1000.0))  # 1764

    # 1. Setup ActionDispatcher
    dispatcher = ActionDispatcher()
    dispatched_events = []

    def mock_action(**payload: Any) -> Dict[str, Any]:
        dispatched_events.append(payload)
        return {"status": "ok"}

    dispatcher.register_action(
        name="test_virtual_action",
        handler=mock_action,
        required_privilege=PrivilegeLevel.NORMAL,
        description="Test virtual action",
    )

    # 2. Setup GestureDetector
    dsp = AudioDSPProcessor()
    detector = GestureDetector(
        dsp=dsp,
        dispatcher=dispatcher,
        min_double_gap_s=0.05,
        max_double_gap_s=0.35,
    )
    detector._patterns[GestureType.DOUBLE_CLAP].actions = ["test_virtual_action"]

    # 3. Setup AudioEngine
    engine = AudioEngine(
        sample_rate=sample_rate,
        block_ms=block_ms,
        mode=AudioEngineMode.MOCK,
    )
    engine.register_callback(lambda blk, timestamp=None: detector.feed_audio_block(blk, timestamp=timestamp))
    engine.start_stream()

    # 4. Generate synthetic PCM stream with 2 claps
    total_samples = int(1.5 * sample_rate)
    pcm = np.full(total_samples, 0.001, dtype=np.float32)

    # Clap 1 at 0.30s (duration 40ms)
    c1_start = int(0.30 * sample_rate)
    c1_end = c1_start + int(0.04 * sample_rate)
    pcm[c1_start:c1_end] = 0.85

    # Clap 2 at 0.50s (gap = 0.20s from c1)
    c2_start = int(0.50 * sample_rate)
    c2_end = c2_start + int(0.04 * sample_rate)
    pcm[c2_start:c2_end] = 0.85

    # Feed virtual audio stream
    engine.feed_virtual_audio(pcm, virtual_time=True)

    # Trigger clock tick at end of buffer
    detector.tick(now=1.6)

    engine.stop_stream()

    # Verify action execution
    assert len(dispatched_events) == 1, f"Expected 1 dispatched event, got {len(dispatched_events)}"
    assert dispatched_events[0]["gesture"]["gesture_type"] == "double_clap"


def test_audio_engine_concurrent_feed_virtual_audio():
    """
    Stress-test concurrent feed_virtual_audio from 8 threads hammering AudioEngine simultaneously.
    Must execute safely without race conditions or deadlocks.
    """
    received_blocks = []
    lock = threading.Lock()

    def collector(blk: np.ndarray, timestamp: Optional[float] = None) -> None:
        with lock:
            received_blocks.append(blk)

    engine = AudioEngine(
        sample_rate=44100,
        block_ms=40,
        mode=AudioEngineMode.MOCK,
        on_audio_block=collector,
    )
    engine.start_stream()

    def worker(tid: int):
        buf = np.full(1764 * 5, float(tid) * 0.1, dtype=np.float32)
        for _ in range(10):
            engine.feed_virtual_audio(buf, virtual_time=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(8)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    engine.stop_stream()
    # 8 threads * 10 iterations * 5 blocks = 400 blocks
    assert len(received_blocks) == 400


# ============================================================================
# 5. STATE MACHINE & DSP ADVERSARIAL EDGE CASE TESTS
# ============================================================================

def test_detector_reset_during_pending_disambiguation():
    """
    Verify calling reset() while state is PENDING_DISAMBIGUATION cleanly purges state,
    cancels pending triggers, and returns to IDLE.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35)
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=1.15, amplitude=0.8))
    assert det._state == DetectorState.PENDING_DISAMBIGUATION
    assert len(det._clap_buffer) == 2

    # Reset
    det.reset()
    assert det._state == DetectorState.IDLE
    assert len(det._clap_buffer) == 0
    assert det._last_raw_clap_time == -100.0

    # Ticking past previous deadline should produce nothing
    assert det.tick(now=1.60) is None


def test_detector_eager_mode_when_triple_and_pause_disabled():
    """
    When TRIPLE_CLAP and CLAP_PAUSE_CLAP are disabled in config,
    DOUBLE_CLAP should trigger IMMEDIATELY on the 2nd clap without waiting for disambiguation timeout.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35)
    det._patterns[GestureType.TRIPLE_CLAP].enabled = False
    det._patterns[GestureType.CLAP_PAUSE_CLAP].enabled = False

    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=1.20, amplitude=0.8))

    assert res is not None, "Eager mode failed to trigger double clap immediately on 2nd clap!"
    assert res.gesture_type == GestureType.DOUBLE_CLAP
    assert det._state == DetectorState.COOLDOWN


def test_dsp_processor_continuous_sine_wave_no_chatter():
    """
    Feeding a continuous 1kHz sine wave for 50 blocks.
    The SchmittTrigger should trigger once on initial attack and remain disarmed (no repetitive triggering)
    as long as signal stays high without dipping below retrigger threshold.
    """
    dsp = AudioDSPProcessor()
    sr = 44100
    block_size = 1764
    duration = block_size / sr
    t = np.linspace(0, duration, block_size, endpoint=False)
    sine_block = (0.8 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)

    transients = []
    for i in range(50):
        res = dsp.process_block(sine_block)
        if res.get("is_transient"):
            transients.append(i)

    # Must fire only once on block 0 or 1, and never re-trigger while constant high tone continues
    assert len(transients) == 1
    assert transients[0] in [0, 1]


def test_dsp_processor_adaptation_step_response():
    """
    Verify DSP gracefully handles sudden 100x noise floor jumps and drops.
    """
    dsp = AudioDSPProcessor()
    # 1. 20 blocks quiet (0.001)
    for _ in range(20):
        dsp.process_block(np.full(1764, 0.001, dtype=np.float32))

    # 2. 20 blocks moderate noise (0.010)
    for _ in range(20):
        dsp.process_block(np.full(1764, 0.010, dtype=np.float32))

    # 3. Transient spike (0.8)
    res_spike = dsp.process_block(np.full(1764, 0.8, dtype=np.float32))
    assert res_spike.get("is_transient") is True


def test_audio_engine_pause_resume_lifecycle_with_feed_virtual_audio():
    """
    Verify pause_stream() suppresses dispatching of fed virtual audio blocks,
    and resume_stream() restores dispatching cleanly.
    """
    dispatched = []
    engine = AudioEngine(
        sample_rate=44100,
        block_ms=40,
        mode=AudioEngineMode.MOCK,
        on_audio_block=lambda blk: dispatched.append(blk),
    )
    engine.start_stream()

    # Active stream: feed 2 blocks -> received
    engine.feed_virtual_audio(np.ones(1764 * 2, dtype=np.float32) * 0.5)
    assert len(dispatched) == 2

    # Pause stream: feed 2 blocks -> suppressed
    engine.pause_stream()
    engine.feed_virtual_audio(np.ones(1764 * 2, dtype=np.float32) * 0.5)
    assert len(dispatched) == 2  # No new blocks dispatched!

    # Resume stream: feed 2 blocks -> received
    engine.resume_stream()
    engine.feed_virtual_audio(np.ones(1764 * 2, dtype=np.float32) * 0.5)
    assert len(dispatched) == 4

    engine.stop_stream()


def test_process_stream_boundary_precision():
    """
    Verify process_stream handles whole continuous PCM buffers with precise double,
    triple, and syncopated pause clap patterns.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    sr = 44100
    block_size = 1764

    # Synthesize PCM with:
    # 1. Double clap: Clap at 0.20s, Clap at 0.38s (gap = 0.18s)
    # 2. Quiet gap of 1.0s
    # 3. Triple clap: Clap at 1.80s, 2.00s, 2.20s (gaps = 0.20s, 0.20s, span = 0.40s)
    # 4. Quiet gap of 1.0s
    # 5. Syncopated clap: Clap at 3.60s, Clap at 4.30s (gap = 0.70s)
    total_len = int(5.5 * sr)
    pcm = np.zeros(total_len, dtype=np.float32)

    def inject_clap(t_sec: float):
        start = int(t_sec * sr)
        end = start + int(0.03 * sr)
        pcm[start:end] = 0.85

    # 1. Double clap
    inject_clap(0.20)
    inject_clap(0.38)

    # 2. Triple clap
    inject_clap(1.80)
    inject_clap(2.00)
    inject_clap(2.20)

    # 3. Syncopated pause
    inject_clap(3.60)
    inject_clap(4.30)

    results = det.process_stream(pcm, block_size=block_size)
    assert len(results) == 3, f"Expected 3 recognized gestures, got {len(results)}: {results}"
    assert results[0].gesture_type == GestureType.DOUBLE_CLAP
    assert results[1].gesture_type == GestureType.TRIPLE_CLAP
    assert results[2].gesture_type == GestureType.CLAP_PAUSE_CLAP


def test_dynamic_reconfiguration_during_stream():
    """
    Verify configure_from_dict updates timing windows and thresholds on-the-fly.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35)

    # Reconfigure max_double_gap_s to 0.60s and pause_min_s to 0.70s
    det.configure_from_dict({
        "dsp": {"max_double_gap_s": 0.60, "cooldown_s": 0.30},
        "patterns": {
            "double_clap": {"max_gap_s": 0.60},
            "clap_pause_clap": {"pause_min_s": 0.70},
        }
    })

    assert math.isclose(det.max_double_gap_s, 0.60)
    assert math.isclose(det.cooldown_s, 0.30)
    assert math.isclose(det._patterns[GestureType.DOUBLE_CLAP].max_gap_s, 0.60)
    assert math.isclose(det._patterns[GestureType.CLAP_PAUSE_CLAP].pause_min_s, 0.70)

    # Now a clap pair with 0.55s gap is accepted as double clap!
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=1.55, amplitude=0.8))
    res = det.tick(now=2.20)
    assert res is not None and res.gesture_type == GestureType.DOUBLE_CLAP


def test_extreme_stress_randomized_synthetic_events():
    """
    Generate 5,000 randomized events across simulated 100 seconds:
    - High-density noise bursts
    - Cooldown attacks
    - Random dead-zone pulses
    Verify zero crashes, zero unhandled exceptions, zero deadlocks.
    """
    np.random.seed(12345)
    det = GestureDetector()
    t = 0.0

    for _ in range(5000):
        action = np.random.choice(["clap", "tick", "reset", "reconfig"])
        dt = float(np.random.uniform(0.005, 0.080))
        t += dt

        if action == "clap":
            amp = float(np.random.uniform(0.1, 0.95))
            det.feed_clap(ClapEvent(timestamp=t, amplitude=amp))
        elif action == "tick":
            det.tick(now=t)
        elif action == "reset":
            det.reset()
        elif action == "reconfig":
            det.configure_from_dict({"dsp": {"cooldown_s": float(np.random.uniform(0.2, 0.6))}})

    # Final cleanup tick
    det.tick(now=t + 2.0)
    assert True

