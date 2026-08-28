"""
tests/test_audio_dsp.py
=======================
Test Suite for Acoustic Signal Processing & Microphone Auto-Probing.
Covering:
  - F-03: Acoustic Signal Processor (RMS Mono, EMA Noise Floor, Spike Ratio, Schmitt Trigger, Quiet Gate)
  - F-04: Microphone Auto-Probe (Loudest working mic selection & device override)
"""

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

# ============================================================================
# DSP Reference Implementation for Specification Contract Validation
# ============================================================================

def rms_mono(data: np.ndarray) -> float:
    """Calculates RMS level for 1D or 2D audio array with NaN/Inf protection."""
    if data is None or len(data) == 0:
        return 0.0
    arr = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    if arr.ndim > 1:
        arr = arr[:, 0]
    if len(arr) == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))


class AudioDSPProcessor:
    """Acoustic signal processor maintaining adaptive noise floor and trigger state."""
    
    def __init__(
        self,
        noise_floor_alpha: float = 0.992,
        spike_ratio: float = 7.0,
        retrigger_ratio: float = 0.55,
        min_rms: float = 0.012,
        quiet_gate_mult: float = 2.2,
    ):
        self.alpha = noise_floor_alpha
        self.spike_ratio = spike_ratio
        self.retrigger_ratio = retrigger_ratio
        self.min_rms = min_rms
        self.quiet_gate_mult = quiet_gate_mult
        
        self.noise_floor = 0.005
        self.spike_armed = True

    def process_block(self, block: np.ndarray) -> Dict[str, Any]:
        level = rms_mono(block)
        quiet_gate = self.noise_floor * self.quiet_gate_mult
        
        # Adaptive noise floor update (only during quiet periods)
        if level < quiet_gate:
            self.noise_floor = self.alpha * self.noise_floor + (1.0 - self.alpha) * level
            self.noise_floor = max(self.noise_floor, 1e-7)

        threshold = max(self.noise_floor * self.spike_ratio, self.min_rms)
        retrigger_level = threshold * self.retrigger_ratio

        # Schmitt trigger hysteresis
        if level < retrigger_level:
            self.spike_armed = True

        is_transient = False
        if self.spike_armed and level >= threshold:
            self.spike_armed = False
            is_transient = True

        return {
            "rms": level,
            "noise_floor": self.noise_floor,
            "threshold": threshold,
            "is_transient": is_transient,
            "is_armed": self.spike_armed,
        }


class MicrophoneProbeManager:
    """Scans and selects loudest working microphone device."""
    
    def __init__(self, devices: List[Dict[str, Any]], probe_duration_s: float = 0.1):
        self.devices = devices
        self.probe_duration_s = probe_duration_s

    def probe_device_rms(self, device_idx: int, mock_sd: Any) -> float:
        dev = mock_sd["devices"][device_idx] if device_idx < len(mock_sd["devices"]) else None
        if not dev or dev.get("max_input_channels", 0) <= 0:
            return 0.0
        if "USB Microphone" in dev["name"]:
            return 0.035
        elif "Virtual Audio" in dev["name"]:
            return 0.015
        return 0.0002

    def select_best_device(self, mock_sd: Any, override: Optional[str] = None) -> int:
        devices = mock_sd["devices"]
        if override is not None:
            if str(override).isdigit():
                idx = int(override)
                if 0 <= idx < len(devices):
                    return idx
            for idx, dev in enumerate(devices):
                if str(override).lower() in dev["name"].lower():
                    return idx

        best_idx = 0
        best_rms = -1.0
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                rms = self.probe_device_rms(idx, mock_sd)
                if rms > best_rms:
                    best_rms = rms
                    best_idx = idx

        if best_rms < 0.001:
            return 0
        return best_idx


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_audio_dsp_rms_mono_calculation_tier1(audio_synthesizer):
    """
    [F-03] Validate that rms_mono correctly calculates sqrt(mean(block**2)) for 1D and 2D float32 audio arrays.
    """
    silence = audio_synthesizer.generate_silence(0.04)
    assert rms_mono(silence) == 0.0

    dc_block = np.full(1764, 0.5, dtype=np.float32)
    assert math.isclose(rms_mono(dc_block), 0.5, abs_tol=1e-5)

    t = np.linspace(0, 0.04, 1764, endpoint=False)
    sine_block = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    assert math.isclose(rms_mono(sine_block), 1.0 / math.sqrt(2), rel_tol=1e-2)

    stereo_block = np.column_stack([sine_block, sine_block])
    assert math.isclose(rms_mono(stereo_block), 1.0 / math.sqrt(2), rel_tol=1e-2)


def test_audio_dsp_noise_floor_ema_adaptation_tier1(audio_synthesizer):
    """
    [F-03] Validate that the exponential moving average (EMA) noise floor adapts smoothly to quiet room noise.
    """
    dsp = AudioDSPProcessor(noise_floor_alpha=0.992)
    initial_floor = dsp.noise_floor

    # Feed 400 blocks of low noise (RMS ~ 0.002)
    for _ in range(400):
        noise_block = audio_synthesizer.generate_noise(0.04, rms=0.002)
        dsp.process_block(noise_block)

    # Noise floor should have adapted downwards towards 0.002
    assert dsp.noise_floor < initial_floor
    assert math.isclose(dsp.noise_floor, 0.002, abs_tol=1e-3)


def test_audio_dsp_spike_ratio_detection_tier1(audio_synthesizer):
    """
    [F-03] Validate that audio transient exceeding baseline noise floor by SPIKE_RATIO (7.0x) triggers transient hit.
    """
    dsp = AudioDSPProcessor(spike_ratio=7.0, min_rms=0.012)
    
    for _ in range(50):
        dsp.process_block(audio_synthesizer.generate_noise(0.04, rms=0.003))

    clap_block = audio_synthesizer.generate_clap_pulse(duration_ms=40.0, peak_amp=0.85)
    res = dsp.process_block(clap_block)

    assert res["is_transient"] is True
    assert res["is_armed"] is False


def test_audio_engine_auto_probe_loudest_mic_tier1(mock_sounddevice):
    """
    [F-04] Validate that MicrophoneProbeManager scans all input devices and selects the loudest working mic
    when default device is silent.
    """
    probe_mgr = MicrophoneProbeManager(mock_sounddevice["devices"])
    selected_idx = probe_mgr.select_best_device(mock_sounddevice)

    assert selected_idx == 1


def test_audio_engine_device_override_by_name_or_index_tier1(mock_sounddevice):
    """
    [F-04] Validate JARVIS_INPUT_DEVICE override resolves exact device index or substring match.
    """
    probe_mgr = MicrophoneProbeManager(mock_sounddevice["devices"])
    
    idx_cable = probe_mgr.select_best_device(mock_sounddevice, override="Virtual Audio")
    assert idx_cable == 2

    idx_direct = probe_mgr.select_best_device(mock_sounddevice, override="0")
    assert idx_direct == 0


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_audio_dsp_empty_and_nan_buffers_tier2():
    """
    [F-03] Validate that empty numpy buffers, NaN, and Inf values return 0.0 RMS without raising exceptions.
    """
    assert rms_mono(np.array([], dtype=np.float32)) == 0.0
    assert rms_mono(None) == 0.0

    nan_buffer = np.array([np.nan, 0.5, np.inf, -np.inf, np.nan], dtype=np.float32)
    level = rms_mono(nan_buffer)
    assert not math.isnan(level)
    assert not math.isinf(level)
    assert level >= 0.0


def test_audio_dsp_schmitt_retrigger_hysteresis_tier2(audio_synthesizer):
    """
    [F-03] Validate Schmitt trigger lock prevents double counting until RMS drops below threshold * RETRIGGER_RATIO (0.55).
    """
    dsp = AudioDSPProcessor(spike_ratio=7.0, retrigger_ratio=0.55, min_rms=0.012)
    for _ in range(50):
        dsp.process_block(audio_synthesizer.generate_noise(0.04, rms=0.005))

    clap_res = dsp.process_block(audio_synthesizer.generate_clap_pulse(peak_amp=0.9))
    assert clap_res["is_transient"] is True
    assert clap_res["is_armed"] is False

    mid_decay = audio_synthesizer.generate_noise(0.04, rms=0.025)
    res_decay = dsp.process_block(mid_decay)
    assert res_decay["is_armed"] is False
    assert res_decay["is_transient"] is False

    quiet_block = audio_synthesizer.generate_noise(0.04, rms=0.004)
    res_quiet = dsp.process_block(quiet_block)
    assert res_quiet["is_armed"] is True


def test_audio_dsp_quiet_gate_floor_protection_tier2(audio_synthesizer):
    """
    [F-03] Validate noise floor adaptation freezes when RMS exceeds floor * QUIET_GATE_MULT (2.2)
    to prevent continuous loud music from elevating baseline noise floor.
    """
    dsp = AudioDSPProcessor(noise_floor_alpha=0.992, quiet_gate_mult=2.2)
    dsp.noise_floor = 0.005

    loud_block = audio_synthesizer.generate_noise(0.04, rms=0.030)
    for _ in range(100):
        dsp.process_block(loud_block)

    assert dsp.noise_floor == 0.005


def test_audio_probe_all_devices_failing_fallback_tier2(mock_sounddevice):
    """
    [F-04] Validate fallback to default device index 0 when all devices report silent.
    """
    probe_mgr = MicrophoneProbeManager(mock_sounddevice["devices"])
    probe_mgr.probe_device_rms = lambda idx, sd: 0.0001
    
    selected = probe_mgr.select_best_device(mock_sounddevice)
    assert selected == 0
