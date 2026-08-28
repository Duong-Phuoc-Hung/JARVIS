"""
tests/test_adversarial_harness.py
Comprehensive empirical stress-testing and adversarial challenge suite for tests/conftest.py.
Executes mathematical verification, safety barrier auditing, boundary tests, and fixture isolation attacks.
"""

import ctypes
import math
import os
import sys
import threading
import time

import numpy as np
import pytest

from tests.conftest import (
    AudioSynthesizer,
    MockAudioStream,
    MockCameraFeed,
    MockHardwareProvider,
    MockHttpServer,
    MockWin32Platform,
    _to_hwnd_int,
)
from tests.mocks.win32_mocks import MockWinreg
from tests.test_audio_dsp import AudioDSPProcessor, MicrophoneProbeManager, rms_mono

# ============================================================================
# CHALLENGE 1: ACOUSTIC DSP SYNTHESIS MATH VERIFICATION
# ============================================================================

def test_dsp_rms_power_precision_and_linearity(audio_synthesizer):
    """
    [DSP-ADV-01] Adversarially stress-test RMS power calculation across frequencies,
    sample rates (16kHz-48kHz), durations (50ms-1s), and RMS levels (0.0005 to 0.2).
    """
    target_rms_values = [0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.2]
    sample_rates = [16000, 22050, 44100, 48000]
    durations = [0.05, 0.1, 0.5, 1.0]

    for sr in sample_rates:
        for dur in durations:
            for target_rms in target_rms_values:
                noise = audio_synthesizer.generate_noise(duration_s=dur, rms=target_rms, sample_rate=sr)
                emp_rms = rms_mono(noise)
                assert math.isclose(emp_rms, target_rms, rel_tol=0.01, abs_tol=1e-5), \
                    f"RMS mismatch: target={target_rms}, emp={emp_rms}, sr={sr}, dur={dur}"


def test_dsp_int16_quantization_and_dynamic_range(audio_synthesizer):
    """
    [DSP-ADV-02] Adversarially test int16 PCM quantization dynamic range and signed 16-bit boundaries.
    """
    for target_rms in [0.01, 0.05, 0.1]:
        noise_i16 = audio_synthesizer.generate_noise(duration_s=0.5, rms=target_rms, dtype=np.int16)
        assert noise_i16.dtype == np.int16
        float_equiv = noise_i16.astype(np.float32) / 32767.0
        emp_rms = rms_mono(float_equiv)
        assert math.isclose(emp_rms, target_rms, rel_tol=0.02, abs_tol=1e-4)
        assert np.max(noise_i16) <= 32767 and np.min(noise_i16) >= -32768


def test_dsp_exponential_decay_envelope_fidelity(audio_synthesizer):
    """
    [DSP-ADV-03] Adversarially test exponential decay envelope: e^(-t/tau) monotonic energy decay
    and peak amplitude constraint.
    """
    for decay_ms in [3.0, 6.0, 10.0, 20.0]:
        for peak in [0.5, 0.85, 0.95]:
            pulse = audio_synthesizer.generate_clap_pulse(
                duration_ms=40.0, peak_amp=peak, decay_time_ms=decay_ms, center_freq_hz=2200.0
            )
            assert np.max(np.abs(pulse)) <= peak + 1e-5
            assert math.isclose(np.max(np.abs(pulse)), peak, abs_tol=1e-4)
            q1 = pulse[:len(pulse)//4]
            q4 = pulse[3*len(pulse)//4:]
            rms_q1 = rms_mono(q1)
            rms_q4 = rms_mono(q4)
            assert rms_q1 > rms_q4 * 3.0, f"Decay failed: rms_q1={rms_q1}, rms_q4={rms_q4}"


def test_dsp_multi_clap_sequence_timing_accuracy(audio_synthesizer):
    """
    [DSP-ADV-04] Adversarially verify multi-clap gap timing and sample-accurate transient offsets.
    """
    sr = 44100
    gap_s = 0.15
    lead_s = 0.10
    trail_s = 0.20
    double_clap = audio_synthesizer.generate_double_clap(
        gap_s=gap_s, leading_silence_s=lead_s, trailing_silence_s=trail_s, sample_rate=sr
    )

    expected_len = int(sr * lead_s) + int(sr * 0.025) + int(sr * gap_s) + int(sr * 0.025) + int(sr * trail_s)
    assert len(double_clap) == expected_len

    peaks = np.where(np.abs(double_clap) > 0.5)[0]
    p1 = peaks[peaks < int(sr * (lead_s + 0.035))]
    p2 = peaks[peaks > int(sr * (lead_s + 0.035))]
    assert len(p1) > 0 and len(p2) > 0
    t_p1 = p1[0] / sr
    t_p2 = p2[0] / sr
    delta_t = t_p2 - t_p1
    assert math.isclose(delta_t, 0.175, abs_tol=0.015)


def test_dsp_triple_clap_and_clap_pause_clap(audio_synthesizer):
    """
    [DSP-ADV-05] Adversarially verify triple-clap and clap-pause-clap transient sequences.
    """
    sr = 44100
    triple = audio_synthesizer.generate_triple_clap(
        gap1_s=0.12, gap2_s=0.18, leading_silence_s=0.05, trailing_silence_s=0.1, sample_rate=sr
    )
    assert len(triple) > int(sr * 0.4)
    assert np.max(np.abs(triple)) > 0.80

    pause_clap = audio_synthesizer.generate_clap_pause_clap(
        gap_s=0.80, leading_silence_s=0.05, trailing_silence_s=0.1, sample_rate=sr
    )
    assert len(pause_clap) > int(sr * 0.95)


def test_dsp_noise_floor_ema_step_adaptation(audio_synthesizer):
    """
    [DSP-ADV-06] Adversarially verify EMA noise floor adaptation and quiet gate freeze.
    """
    dsp = AudioDSPProcessor(noise_floor_alpha=0.992, quiet_gate_mult=2.2)
    dsp.noise_floor = 0.005

    for _ in range(300):
        dsp.process_block(audio_synthesizer.generate_noise(0.04, rms=0.002))
    assert 0.0018 <= dsp.noise_floor <= 0.0025

    frozen_floor = dsp.noise_floor
    for _ in range(100):
        dsp.process_block(audio_synthesizer.generate_noise(0.04, rms=0.030))
    assert dsp.noise_floor == frozen_floor


def test_dsp_chunk_stream_slicing(audio_synthesizer):
    """
    [DSP-ADV-07] Adversarially verify chunk_stream zero-padding and total sample reconstruction.
    """
    buf = audio_synthesizer.generate_noise(0.123, rms=0.01, sample_rate=44100)
    block_size = 512
    chunks = list(audio_synthesizer.chunk_stream(buf, block_size=block_size))
    for c in chunks:
        assert len(c) == block_size
    reconstructed = np.concatenate(chunks)
    assert len(reconstructed) >= len(buf)
    assert np.allclose(reconstructed[:len(buf)], buf)


def test_dsp_adversarial_boundary_inputs(audio_synthesizer):
    """
    [DSP-ADV-08] Boundary cases: zero durations, NaN, Inf, extreme RMS amplitude.
    """
    # Zero duration returns empty arrays
    assert len(audio_synthesizer.generate_silence(0.0)) == 0
    assert len(audio_synthesizer.generate_noise(0.0)) == 0

    # Negative duration handling: generate_noise guards with num_samples <= 0 returning empty array
    assert len(audio_synthesizer.generate_noise(-0.5)) == 0

    # Extreme RMS is clipped within [-1.0, 1.0] bounds
    extreme_noise = audio_synthesizer.generate_noise(0.1, rms=50.0)
    assert np.all(np.abs(extreme_noise) <= 1.0)

    # NaN and Inf resilience in rms_mono
    nan_arr = np.array([np.nan, 1.0, np.inf, -np.inf, np.nan], dtype=np.float32)
    rms_val = rms_mono(nan_arr)
    assert not math.isnan(rms_val) and not math.isinf(rms_val) and rms_val >= 0.0


# ============================================================================
# CHALLENGE 2: WIN32 CTYPES SAFETY BARRIER VERIFICATION
# ============================================================================

def test_win32_workstation_lock_safety(mock_win32_platform):
    """
    [WIN32-ADV-01] Verify LockWorkStation() is intercepted by mock fixture,
    recording call telemetry without triggering real OS workstation lock.
    """
    assert mock_win32_platform.lock_workstation_calls == 0
    res = ctypes.windll.user32.LockWorkStation()
    assert res == 1
    assert mock_win32_platform.lock_workstation_calls == 1


def test_win32_process_termination_safety(mock_win32_platform):
    """
    [WIN32-ADV-02] Verify TerminateProcess() and OpenProcess() are trapped inside mock registry,
    preventing real OS process disruption.
    """
    hung_hwnd = mock_win32_platform.add_hung_window("FrozenMockApp.exe", pid=7777)
    assert 7777 in [w.pid for w in mock_win32_platform.windows.values()]

    h_proc = ctypes.windll.kernel32.OpenProcess(0x0001, 0, 7777)
    assert h_proc == 7777

    ctypes.windll.kernel32.TerminateProcess(h_proc, 1)
    assert 7777 in mock_win32_platform.killed_pids
    assert hung_hwnd not in mock_win32_platform.windows
    assert os.getpid() not in mock_win32_platform.killed_pids


def test_win32_keystroke_and_input_interception(mock_win32_platform):
    """
    [WIN32-ADV-03] Verify keybd_event() and SendInput() are strictly captured in memory
    and do not generate physical Windows input events.
    """
    ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)
    ctypes.windll.user32.keybd_event(0x44, 2, 0, 0)
    ctypes.windll.user32.keybd_event(0x5B, 2, 0, 0)

    assert len(mock_win32_platform.injected_keys) == 4
    assert mock_win32_platform.injected_keys[0] == (0x5B, 0, 0, 0)
    assert mock_win32_platform.injected_keys[1] == (0x44, 0, 0, 0)

    input_res = ctypes.windll.user32.SendInput(5, None, 40)
    assert input_res == 5


def test_win32_window_management_interception(mock_win32_platform):
    """
    [WIN32-ADV-04] Verify SetWindowPos, ShowWindow, SetForegroundWindow, EnumWindows
    operate exclusively on simulated window registry.
    """
    u32 = ctypes.windll.user32
    assert u32.IsWindow(1001) == 1
    assert u32.IsWindow(99999) == 0

    u32.SetForegroundWindow(1002)
    assert mock_win32_platform.foreground_hwnd == 1002
    assert mock_win32_platform.windows[1002].is_foreground is True
    assert mock_win32_platform.windows[1001].is_foreground is False

    u32.SetWindowPos(1001, 0, 10, 20, 800, 600, 0)
    assert mock_win32_platform.windows[1001].rect == (10, 20, 810, 620)

    u32.ShowWindow(1001, 3) # SW_MAXIMIZE
    assert mock_win32_platform.windows[1001].show_state == 3

    enumerated = []
    def enum_cb(hwnd, lparam):
        enumerated.append(hwnd)
        return True
    u32.EnumWindows(enum_cb, 0)
    assert 1001 in enumerated and 1002 in enumerated


def test_win32_mock_winreg_isolation():
    """
    [WIN32-ADV-05] Verify MockWinreg writes only to in-memory dictionary and does not touch the registry.
    """
    reg = MockWinreg()
    reg.SetValueEx(None, "TEST_KEY", 0, reg.REG_SZ, "test_val")
    val, typ = reg.QueryValueEx(None, "TEST_KEY")
    assert val == "test_val"
    assert typ == reg.REG_SZ
    reg.DeleteValue(None, "TEST_KEY")
    with pytest.raises(FileNotFoundError):
        reg.QueryValueEx(None, "TEST_KEY")


# ============================================================================
# CHALLENGE 3: FIXTURE ISOLATION & RESOURCE CLEANUP
# ============================================================================

def test_fixture_isolation_mock_audio_stream_lifecycle(audio_synthesizer):
    """
    [ISO-ADV-01] Verify MockAudioStream cleanly joins daemon threads upon context exit.
    """
    buf = audio_synthesizer.generate_noise(0.3, rms=0.005)
    received = []

    def cb(chunk, block_size, time_info, status):
        received.append(chunk)

    stream = MockAudioStream(buffer=buf, sample_rate=44100, block_size=1764, callback=cb)
    with stream:
        assert stream.is_active is True
        time.sleep(0.08)

    assert stream.is_active is False
    assert stream._thread is None or not stream._thread.is_alive()
    assert len(received) > 0


def test_fixture_isolation_mock_audio_stream_sync_read(mock_audio_stream):
    """
    [ISO-ADV-02] Verify synchronous reading with boundary frames and exhaustion.
    """
    mock_audio_stream.feed_buffer(np.ones(1000, dtype=np.float32))
    chunk1, _ = mock_audio_stream.read(400)
    assert len(chunk1) == 400
    chunk2, _ = mock_audio_stream.read(800)
    assert len(chunk2) == 800
    # Remaining was 600, padded with 200 zeros
    assert np.all(chunk2[:600] == 1.0)
    assert np.all(chunk2[600:] == 0.0)

    # Exhausted read returns zeros
    chunk3, _ = mock_audio_stream.read(100)
    assert len(chunk3) == 100
    assert np.all(chunk3 == 0.0)


def test_fixture_isolation_http_server_reset(mock_http_server):
    """
    [ISO-ADV-03] Verify mock_http_server starts with pristine state across test boundaries.
    """
    assert mock_http_server.ha_states["light.living_room"]["state"] == "off"
    assert len(mock_http_server.elevenlabs_calls) == 0
    assert len(mock_http_server.mqtt_published_messages) == 0

    mock_http_server.ha_states["light.living_room"]["state"] = "on"
    mock_http_server.elevenlabs_calls.append({"text": "Test"})
    mock_http_server.mqtt_published_messages.append(("topic", b"msg", 0, False))


def test_fixture_isolation_hardware_provider_reset(mock_hardware_provider):
    """
    [ISO-ADV-04] Verify mock_hardware_provider resets to baseline CPU/RAM/GPU telemetry.
    """
    assert mock_hardware_provider.cpu_temp_c == 48.0
    assert mock_hardware_provider.ram_percent == 37.5

    mock_hardware_provider.simulate_overheating()
    mock_hardware_provider.simulate_ram_exhaustion()
    assert mock_hardware_provider.cpu_temp_c == 94.0
    assert mock_hardware_provider.ram_percent == 95.5


def test_fixture_isolation_camera_feed_reset(mock_camera_feed):
    """
    [ISO-ADV-05] Verify mock_camera_feed resets to default owner_face scene and discriminates intruders.
    """
    assert mock_camera_feed.current_scene == "owner_face"
    encs_owner = mock_camera_feed.get_face_encodings(mock_camera_feed.generate_synthetic_frame())
    assert len(encs_owner) == 1
    dist = np.linalg.norm(encs_owner[0] - mock_camera_feed.intruder_encoding)
    assert dist > 0.6
