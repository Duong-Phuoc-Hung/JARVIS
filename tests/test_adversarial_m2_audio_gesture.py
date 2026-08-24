"""
tests/test_adversarial_m2_audio_gesture.py
===========================================
Empirical Challenger Stress Testing Suite for Milestone 2:
- Audio DSP (RMS, NaN/Inf, multi-channel, pure tones, clipping, extreme SNR)
- EMA Noise Floor Tracker & Schmitt Trigger Hysteresis
- Multi-Pattern Gesture Detector State Machines (boundary precision, rapid spam, syncopations, cooldowns, disambiguation)
- Microphone Auto-Prober & Device Override
- High Concurrency & Thread Safety
"""
import concurrent.futures
import math
import threading
import time
from typing import Any, Dict, List, Optional
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
from jarvis.core.models import RequesterContext
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.models import (
    ClapEvent,
    DetectorState,
    GesturePatternConfig,
    GestureResult,
    GestureType,
)
from jarvis.gesture.patterns import get_default_patterns


# ============================================================================
# 1. ACOUSTIC DSP & RMS CALCULATION EMPIRICAL STRESS TESTS
# ============================================================================

def test_rms_silence_and_empty_inputs():
    """Verify RMS on zero-length, None, and pure digital silence."""
    assert calculate_rms(None) == 0.0
    assert calculate_rms(np.array([], dtype=np.float32)) == 0.0
    assert calculate_rms(np.zeros(0, dtype=np.int16)) == 0.0
    assert calculate_rms(np.zeros(1764, dtype=np.float32)) == 0.0
    assert calculate_rms(np.zeros(1764, dtype=np.float64)) == 0.0
    assert calculate_rms(np.zeros(1764, dtype=np.int16)) == 0.0
    assert rms_mono(np.zeros(1764, dtype=np.float32)) == 0.0


def test_rms_pure_sine_frequencies():
    """Verify pure sine waves across audio spectrum up to 20kHz have RMS equal to Amplitude / sqrt(2)."""
    frequencies = [20.0, 100.0, 440.0, 1000.0, 5000.0, 10000.0, 20000.0]
    sr = 44100
    duration = 0.1  # 100ms
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    amplitude = 0.8
    for freq in frequencies:
        sine_wave = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        rms = calculate_rms(sine_wave)
        expected_rms = amplitude / math.sqrt(2)
        assert math.isclose(rms, expected_rms, rel_tol=0.03), f"Freq {freq}Hz RMS {rms} deviated from expected {expected_rms}"

    # Nyquist (22050Hz): sin is sampled at zero crossings (RMS~0), cos is sampled at alternating peaks (RMS=A)
    nyquist_cos = (amplitude * np.cos(2 * np.pi * 22050.0 * t)).astype(np.float32)
    assert math.isclose(calculate_rms(nyquist_cos), amplitude, rel_tol=0.01)




def test_rms_dc_offset():
    """Verify DC offset produces exact absolute value RMS."""
    for dc_val in [-0.9, -0.5, -0.1, 0.0, 0.25, 0.7, 1.0]:
        block = np.full(1764, dc_val, dtype=np.float32)
        assert math.isclose(calculate_rms(block), abs(dc_val), abs_tol=1e-5)


def test_rms_square_and_triangle_waves():
    """Verify square wave (RMS = A) and triangle wave (RMS = A / sqrt(3))."""
    sr = 44100
    t = np.linspace(0, 0.1, int(sr * 0.1), endpoint=False)
    amp = 0.6
    # Square wave
    sq = (amp * np.sign(np.sin(2 * np.pi * 100 * t))).astype(np.float32)
    assert math.isclose(calculate_rms(sq), amp, rel_tol=0.01)

    # Triangle wave
    tri = (amp * (2.0 * np.abs(2.0 * (t * 100 - np.floor(t * 100 + 0.5))) - 1.0)).astype(np.float32)
    expected_tri_rms = amp / math.sqrt(3)
    assert math.isclose(calculate_rms(tri), expected_tri_rms, rel_tol=0.03)


def test_rms_int16_boundaries_and_saturation():
    """Verify int16 min (-32768) and max (32767) normalization."""
    int16_max = np.full(1000, 32767, dtype=np.int16)
    int16_min = np.full(1000, -32768, dtype=np.int16)
    
    rms_max = calculate_rms(int16_max)
    rms_min = calculate_rms(int16_min)
    
    assert math.isclose(rms_max, 32767.0 / 32768.0, abs_tol=1e-4)
    assert math.isclose(rms_min, 1.0, abs_tol=1e-4)


def test_rms_nan_inf_injection_matrix():
    """Verify NaN, +Inf, -Inf in various positions are sanitized to 0.0 without errors."""
    # 1. All NaNs
    all_nan = np.full(1000, np.nan, dtype=np.float32)
    assert calculate_rms(all_nan) == 0.0

    # 2. All Infs
    all_inf = np.full(1000, np.inf, dtype=np.float32)
    assert calculate_rms(all_inf) == 0.0

    all_neginf = np.full(1000, -np.inf, dtype=np.float32)
    assert calculate_rms(all_neginf) == 0.0

    # 3. Interleaved corruptions with real signals
    mixed = np.array([np.nan, 0.4, np.inf, 0.4, -np.inf, 0.4, np.nan, 0.4], dtype=np.float32)
    rms_mixed = calculate_rms(mixed)
    # 4 samples of 0.4, 4 samples of 0.0 -> mean_sq = (4 * 0.16) / 8 = 0.08 -> sqrt(0.08) ~= 0.2828
    assert math.isclose(rms_mixed, math.sqrt(0.08), rel_tol=1e-3)


def test_rms_multichannel_downmix_dimensions():
    """Verify 2D multi-channel arrays: stereo (N, 2), quad (N, 4), 5.1 surround (N, 6)."""
    n_samples = 1764
    mono_signal = np.full(n_samples, 0.5, dtype=np.float32)

    # 2-channel stereo
    stereo = np.column_stack([mono_signal, mono_signal])
    assert math.isclose(calculate_rms(stereo), 0.5, abs_tol=1e-5)

    # 6-channel 5.1 surround
    surround = np.column_stack([mono_signal] * 6)
    assert math.isclose(calculate_rms(surround), 0.5, abs_tol=1e-5)

    # Out-of-phase stereo [A, -A] -> downmix mean is 0 -> RMS is 0
    out_of_phase = np.column_stack([mono_signal, -mono_signal])
    assert calculate_rms(out_of_phase) == 0.0

    # Empty 2D array
    empty_2d = np.zeros((0, 2), dtype=np.float32)
    assert calculate_rms(empty_2d) == 0.0


# ============================================================================
# 2. NOISE FLOOR TRACKER & SCHMITT TRIGGER HYSTERESIS STRESS TESTS
# ============================================================================

def test_noise_floor_slow_adaptation_and_convergence():
    """Test noise floor smoothly converges to new quiet background level."""
    tracker = NoiseFloorTracker(alpha=0.992, initial_floor=0.020)
    target_noise = 0.003

    # Simulate 1000 blocks (~40s) of steady background noise
    for _ in range(1000):
        floor, gated = tracker.update(target_noise)
        assert not gated

    assert math.isclose(tracker.noise_floor, target_noise, abs_tol=1e-4)


def test_noise_floor_quiet_gate_boundary_precision():
    """Verify quiet gate threshold freezing: RMS < floor * 2.2 adapts, RMS >= floor * 2.2 freezes."""
    tracker = NoiseFloorTracker(alpha=0.992, quiet_gate_mult=2.2, initial_floor=0.010)

    # Just below quiet gate: 0.010 * 2.19 = 0.0219 -> adapts
    floor_sub, gated_sub = tracker.update(0.0219)
    assert not gated_sub
    assert floor_sub > 0.010  # floor increased slightly

    # Reset
    tracker.reset(initial_floor=0.010)

    # Just above quiet gate: 0.010 * 2.21 = 0.0221 -> frozen
    floor_sup, gated_sup = tracker.update(0.0221)
    assert gated_sup
    assert floor_sup == 0.010  # floor did not change


def test_noise_floor_clamps_min_max():
    """Verify noise floor is strictly clamped within [min_floor, max_floor]."""
    tracker = NoiseFloorTracker(alpha=0.9, min_floor=1e-6, max_floor=0.5, initial_floor=0.01)

    # Drive to 0
    for _ in range(100):
        tracker.update(0.0)
    assert tracker.noise_floor >= 1e-6

    # Drive to 1.0 with quiet gate disabled for testing
    tracker_no_gate = NoiseFloorTracker(alpha=0.9, quiet_gate_mult=100.0, max_floor=0.5, initial_floor=0.01)
    for _ in range(100):
        tracker_no_gate.update(1.0)
    assert tracker_no_gate.noise_floor <= 0.5


def test_schmitt_trigger_hysteresis_exact_threshold_boundaries():
    """Verify exact transient firing and re-arming boundary math."""
    spike_ratio = 7.0
    retrigger_ratio = 0.55
    min_rms = 0.012
    trigger = SchmittTrigger(spike_ratio=spike_ratio, retrigger_ratio=retrigger_ratio, min_rms=min_rms)

    noise_floor = 0.005
    expected_th = max(noise_floor * spike_ratio, min_rms)  # 0.035
    expected_retrigger = expected_th * retrigger_ratio     # 0.01925

    # 1. Below threshold by epsilon: no transient
    tr, armed, th, retrig = trigger.evaluate(expected_th - 1e-5, noise_floor)
    assert not tr
    assert armed is True
    assert math.isclose(th, expected_th)
    assert math.isclose(retrig, expected_retrigger)

    # 2. At / Above threshold: triggers transient and disarms
    tr, armed, _, _ = trigger.evaluate(expected_th + 1e-5, noise_floor)
    assert tr is True
    assert armed is False

    # 3. In hysteresis deadband (between retrigger and threshold): no rearm
    tr, armed, _, _ = trigger.evaluate(expected_retrigger + 1e-5, noise_floor)
    assert not tr
    assert armed is False

    # 4. Another loud spike while disarmed: ignored!
    tr, armed, _, _ = trigger.evaluate(expected_th * 2.0, noise_floor)
    assert not tr
    assert armed is False

    # 5. Drop below retrigger level: re-arms trigger
    tr, armed, _, _ = trigger.evaluate(expected_retrigger - 1e-5, noise_floor)
    assert not tr
    assert armed is True

    # 6. Now loud spike can trigger again!
    tr, armed, _, _ = trigger.evaluate(expected_th + 1e-5, noise_floor)
    assert tr is True
    assert armed is False


def test_dsp_processor_snr_safety_under_extreme_dynamics():
    """Verify AudioDSPProcessor never raises exceptions or produces NaN/Inf SNR."""
    dsp = AudioDSPProcessor()

    # Extreme input sequence: 0.0 -> 100.0 -> NaN -> -Inf -> 0.0001
    for val in [0.0, 100.0, float('nan'), float('inf'), float('-inf'), 1e-8, 1.0]:
        block = np.full(1764, val, dtype=np.float32)
        res = dsp.process_block_detailed(block)
        assert isinstance(res, DSPBlockResult)
        assert not math.isnan(res.rms)
        assert not math.isinf(res.rms)
        assert not math.isnan(res.noise_floor)
        assert not math.isinf(res.noise_floor)
        assert not math.isnan(res.snr_ratio)
        assert not math.isinf(res.snr_ratio)
        assert not math.isnan(res.snr_db)
        assert not math.isinf(res.snr_db)


# ============================================================================
# 3. GESTURE DETECTOR TIMING BOUNDARY & SYNCOPATION EMPIRICAL STRESS TESTS
# ============================================================================

def test_double_clap_exact_timing_boundaries():
    """
    Timing boundaries for double clap:
    min_gap = 0.050s, max_gap = 0.350s.
    - 0.049s: rejected as acoustic echo (< 0.050s)
    - 0.050s: accepted (== min_gap)
    - 0.051s: accepted (> min_gap)
    - 0.349s: accepted (< max_gap)
    """
    # A. 0.049s (Echo rejection)
    det_echo = GestureDetector(min_double_gap_s=0.050, max_double_gap_s=0.350)
    c1 = ClapEvent(timestamp=1.000, amplitude=0.8)
    c2 = ClapEvent(timestamp=1.049, amplitude=0.8)
    assert det_echo.feed_clap(c1) is None
    assert det_echo.feed_clap(c2) is None  # Echo filtered!
    assert len(det_echo._clap_buffer) == 1  # 2nd clap was dropped

    # B. 0.050s (Exact min gap boundary)
    det_min = GestureDetector(min_double_gap_s=0.050, max_double_gap_s=0.350)
    c1 = ClapEvent(timestamp=1.000, amplitude=0.8)
    c2 = ClapEvent(timestamp=1.050, amplitude=0.8)
    det_min.feed_clap(c1)
    det_min.feed_clap(c2)
    res_min = det_min.tick(now=1.450)  # Disambiguation timeout
    assert res_min is not None
    assert res_min.gesture_type == GestureType.DOUBLE_CLAP

    # C. 0.051s (Just above min gap)
    det_min_plus = GestureDetector(min_double_gap_s=0.050, max_double_gap_s=0.350)
    det_min_plus.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    det_min_plus.feed_clap(ClapEvent(timestamp=1.051, amplitude=0.8))
    res_min_plus = det_min_plus.tick(now=1.450)
    assert res_min_plus is not None
    assert res_min_plus.gesture_type == GestureType.DOUBLE_CLAP

    # D. 0.349s (Just below max gap)
    det_max_minus = GestureDetector(min_double_gap_s=0.050, max_double_gap_s=0.350)
    det_max_minus.feed_clap(ClapEvent(timestamp=1.000, amplitude=0.8))
    det_max_minus.feed_clap(ClapEvent(timestamp=1.349, amplitude=0.8))
    res_max_minus = det_max_minus.tick(now=1.750)
    assert res_max_minus is not None
    assert res_max_minus.gesture_type == GestureType.DOUBLE_CLAP


def test_syncopated_clap_pause_clap_2_clap_permutations():
    """
    2-clap syncopation: Clap 1 -> Pause (0.50s to 1.20s) -> Clap 2.
    - 0.49s: rejected (too short for pause)
    - 0.50s: accepted (== pause_min_s) -> immediate CLAP_PAUSE_CLAP trigger
    - 0.75s: accepted
    - 1.19s: accepted (< pause_max_s)
    - 1.25s: rejected (exceeds pause_max_s)
    """
    # 0.49s
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    assert det.feed_clap(ClapEvent(timestamp=1.49, amplitude=0.8)) is None
    assert det.tick(now=2.00) is None

    # 0.50s (exact min pause)
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=1.50, amplitude=0.8))
    assert res is not None
    assert res.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 0.75s (nominal syncopation)
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=1.75, amplitude=0.8))
    assert res is not None
    assert res.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 1.19s (< max pause)
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=2.19, amplitude=0.8))
    assert res is not None
    assert res.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 1.25s (exceeds max pause)
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    det.feed_clap(ClapEvent(timestamp=1.00, amplitude=0.8))
    res = det.feed_clap(ClapEvent(timestamp=2.25, amplitude=0.8))
    assert res is None


def test_rapid_multi_clap_chatter_suppression_hardened():
    """
    Hardened verification: Rapid 20ms chatter transients (<50ms apart)
    must NOT alias into false gestures because every raw pulse updates _last_raw_clap_time.
    """
    det = GestureDetector(min_double_gap_s=0.05)
    t = 1.0
    triggers = []
    for i in range(20):
        res = det.feed_clap(ClapEvent(timestamp=t, amplitude=0.8))
        if res is not None:
            triggers.append(res)
        t += 0.02  # 20ms continuous chatter

    # After chatter stops, tick past timeout
    res_tick = det.tick(now=t + 1.0)
    if res_tick is not None:
        triggers.append(res_tick)

    assert len(triggers) == 0, f"Expected 0 triggers from chatter spam, got {len(triggers)}: {triggers}"


def test_dead_zone_interval_resets_buffer_cleanly():
    """
    Verify dead-zone gap (e.g. 0.420s between max_double 0.35s and pause_min 0.50s)
    cleanly resets the gesture buffer and treats Clap 2 as Clap 1 of a new sequence.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)

    # Clap 1 at 1.000s
    c1 = ClapEvent(timestamp=1.000, amplitude=0.8)
    assert det.feed_clap(c1) is None
    assert len(det._clap_buffer) == 1

    # Clap 2 at 1.420s (gap = 0.420s: dead-zone)
    c2 = ClapEvent(timestamp=1.420, amplitude=0.8)
    assert det.feed_clap(c2) is None
    # Buffer MUST now hold only Clap 2 (not Clap 1, and not empty)
    assert len(det._clap_buffer) == 1
    assert det._clap_buffer[0].timestamp == 1.420

    # Clap 3 at 1.570s (gap = 0.150s from Clap 2)
    c3 = ClapEvent(timestamp=1.570, amplitude=0.8)
    assert det.feed_clap(c3) is None
    assert len(det._clap_buffer) == 2

    # Disambiguation timeout at 1.950s
    res = det.tick(now=1.950)
    assert res is not None
    assert res.gesture_type == GestureType.DOUBLE_CLAP
    assert res.claps[0].timestamp == 1.420
    assert res.claps[1].timestamp == 1.570


def test_float_epsilon_tolerance_exact_boundaries():
    """
    Verify exact timing boundaries withstand IEEE 754 float subtraction residuals.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)

    # 1. Exact Double Clap max boundary: 1.000 + 0.350 = 1.350
    t1 = 1.000
    t2 = t1 + 0.350
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t1, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=t2, amplitude=0.8))
    res = det.tick(now=t2 + 0.40)
    assert res is not None
    assert res.gesture_type == GestureType.DOUBLE_CLAP

    # 2. Exact Syncopated Pause max boundary: 1.000 + 1.200 = 2.200
    t3 = 1.000
    t4 = t3 + 1.200
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t3, amplitude=0.8))
    res_pause_max = det.feed_clap(ClapEvent(timestamp=t4, amplitude=0.8))
    assert res_pause_max is not None
    assert res_pause_max.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 3. Exact Syncopated Pause min boundary: 1.000 + 0.500 = 1.500
    t5 = 1.000
    t6 = t5 + 0.500
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t5, amplitude=0.8))
    res_pause_min = det.feed_clap(ClapEvent(timestamp=t6, amplitude=0.8))
    assert res_pause_min is not None
    assert res_pause_min.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 4. Exact Double Clap min boundary: 1.000 + 0.050 = 1.050
    t7 = 1.000
    t8 = t7 + 0.050
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t7, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=t8, amplitude=0.8))
    res_double_min = det.tick(now=t8 + 0.40)
    assert res_double_min is not None
    assert res_double_min.gesture_type == GestureType.DOUBLE_CLAP



def test_concurrent_clap_feeding_and_tick_thread_safety():
    """
    Thread safety stress: 10 threads concurrently feeding claps, ticking, and resetting.
    Must execute without deadlocks, exceptions, or race conditions.
    """
    det = GestureDetector()
    exceptions = []

    def worker(thread_id: int):
        try:
            base_time = 10.0 * thread_id
            for step in range(50):
                now = base_time + step * 0.1
                if step % 5 == 0:
                    det.reset()
                elif step % 3 == 0:
                    det.tick(now=now)
                else:
                    det.feed_clap(ClapEvent(timestamp=now, amplitude=0.6))
        except Exception as e:
            exceptions.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(10)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0


# ============================================================================
# 4. MICROPHONE AUTO-PROBER & DEVICE OVERRIDE TESTS
# ============================================================================

def test_probe_manager_empty_and_silent_devices():
    """Verify behavior with empty device list and all-silent microphones."""
    probe_mgr = MicrophoneProbeManager(devices=[])
    assert probe_mgr.get_input_devices() == []
    assert probe_mgr.select_best_device() == 0


def test_probe_manager_override_substring_and_integer():
    """Verify override by exact index and substring (case-insensitive)."""
    mock_devs = [
        {"index": 0, "name": "Realtek Audio In", "max_input_channels": 2},
        {"index": 1, "name": "Yeti USB Microphone", "max_input_channels": 1},
        {"index": 2, "name": "Virtual Audio Cable", "max_input_channels": 2},
    ]
    probe_mgr = MicrophoneProbeManager(devices=mock_devs)

    # Exact index as string
    assert probe_mgr.select_best_device(override="2") == 2
    assert probe_mgr.select_best_device(override="0") == 0

    # Substring match
    assert probe_mgr.select_best_device(override="yeti") == 1
    assert probe_mgr.select_best_device(override="REALTEK") == 0
    assert probe_mgr.select_best_device(override="cable") == 2


def test_audio_engine_feed_virtual_audio_alias():
    """
    Verify AudioEngine.feed_virtual_audio exists and dispatches audio blocks.
    """
    bus_blocks = []
    engine = AudioEngine(
        sample_rate=44100,
        block_ms=40,
        mode=AudioEngineMode.MOCK,
        on_audio_block=lambda blk: bus_blocks.append(blk),
    )
    engine.start_stream()

    test_audio = np.full(3528, 0.42, dtype=np.float32)
    assert hasattr(engine, "feed_virtual_audio")
    engine.feed_virtual_audio(test_audio)

    engine.stop_stream()
    assert len(bus_blocks) == 2
    assert np.allclose(bus_blocks[0], 0.42)

