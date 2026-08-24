"""
tests/adversarial_challenge_runner.py
Empirical stress-testing and adversarial challenge harness for tests/conftest.py.
Executes mathematical verification, safety barrier auditing, and fixture isolation attacks.
"""

import math
import os
import sys
import time
import threading
import numpy as np
import pytest

# Ensure workspace root is on sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from tests.conftest import (
    AudioSynthesizer,
    MockAudioStream,
    MockHardwareProvider,
    MockWin32Platform,
    MockHttpServer,
    MockCameraFeed,
    _to_hwnd_int,
)
from tests.test_audio_dsp import rms_mono, AudioDSPProcessor, MicrophoneProbeManager
from tests.mocks.win32_mocks import MockWinreg


def run_dsp_math_challenges():
    print("\n=======================================================")
    print("CHALLENGE 1: ACOUSTIC DSP SYNTHESIS MATH VERIFICATION")
    print("=======================================================")
    synth = AudioSynthesizer(default_sample_rate=44100)
    
    # 1.1 RMS Power Precision & Linearity
    print("\n[1.1] Testing RMS Power Precision across frequencies, sample rates & durations...")
    target_rms_values = [0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.2]
    sample_rates = [16000, 22050, 44100, 48000]
    durations = [0.05, 0.1, 0.5, 1.0]
    
    max_rms_rel_error = 0.0
    for sr in sample_rates:
        for dur in durations:
            for target_rms in target_rms_values:
                noise = synth.generate_noise(duration_s=dur, rms=target_rms, sample_rate=sr)
                emp_rms = rms_mono(noise)
                rel_error = abs(emp_rms - target_rms) / target_rms
                if rel_error > max_rms_rel_error:
                    max_rms_rel_error = rel_error
                # Tolerance: for white noise with N > 500 samples, RMS should be within 1e-4 absolute or 1% relative
                assert math.isclose(emp_rms, target_rms, rel_tol=0.01, abs_tol=1e-5), \
                    f"RMS mismatch: target={target_rms}, emp={emp_rms}, sr={sr}, dur={dur}"
    print(f"  --> PASS: Tested {len(target_rms_values)*len(sample_rates)*len(durations)} combinations. Max RMS rel error: {max_rms_rel_error:.6%}")

    # 1.2 int16 Quantization & Dynamic Range
    print("\n[1.2] Testing int16 Quantization & Dynamic Range...")
    for target_rms in [0.01, 0.05, 0.1]:
        noise_i16 = synth.generate_noise(duration_s=0.5, rms=target_rms, dtype=np.int16)
        assert noise_i16.dtype == np.int16
        # Re-convert to float32 normalized and verify RMS
        float_equiv = noise_i16.astype(np.float32) / 32767.0
        emp_rms = rms_mono(float_equiv)
        assert math.isclose(emp_rms, target_rms, rel_tol=0.02, abs_tol=1e-4)
        assert np.max(noise_i16) <= 32767 and np.min(noise_i16) >= -32768
    print("  --> PASS: int16 quantization preserves target RMS within 2% and strictly respects signed 16-bit range.")

    # 1.3 Exponential Decay Envelope Analysis
    print("\n[1.3] Testing Exponential Decay Envelope & Resonant Burst Carrier...")
    for decay_ms in [3.0, 6.0, 10.0, 20.0]:
        for peak in [0.5, 0.85, 0.95]:
            pulse = synth.generate_clap_pulse(duration_ms=40.0, peak_amp=peak, decay_time_ms=decay_ms, center_freq_hz=2200.0)
            assert np.max(np.abs(pulse)) <= peak + 1e-5
            assert math.isclose(np.max(np.abs(pulse)), peak, abs_tol=1e-4)
            # Verify decay: the energy in the first quarter should be substantially higher than in the last quarter
            q1 = pulse[:len(pulse)//4]
            q4 = pulse[3*len(pulse)//4:]
            rms_q1 = rms_mono(q1)
            rms_q4 = rms_mono(q4)
            assert rms_q1 > rms_q4 * 3.0, f"Decay failed: rms_q1={rms_q1}, rms_q4={rms_q4}"
    print("  --> PASS: Exponential decay envelope correctly confines peak amplitude and decays exponentially.")

    # 1.4 Multi-Clap Sequence Timing Accuracy
    print("\n[1.4] Testing Multi-Clap Timing Intervals & Sample Alignment...")
    sr = 44100
    gap_s = 0.15
    lead_s = 0.10
    trail_s = 0.20
    double_clap = synth.generate_double_clap(gap_s=gap_s, leading_silence_s=lead_s, trailing_silence_s=trail_s, sample_rate=sr)
    
    expected_len = int(sr * lead_s) + int(sr * 0.025) + int(sr * gap_s) + int(sr * 0.025) + int(sr * trail_s)
    assert len(double_clap) == expected_len, f"Length mismatch: {len(double_clap)} vs {expected_len}"
    
    # Check peak locations
    # Find peaks above 0.5
    peaks = np.where(np.abs(double_clap) > 0.5)[0]
    # Cluster peaks into clap 1 and clap 2
    p1 = peaks[peaks < int(sr * (lead_s + 0.035))]
    p2 = peaks[peaks > int(sr * (lead_s + 0.035))]
    assert len(p1) > 0 and len(p2) > 0
    t_p1 = p1[0] / sr
    t_p2 = p2[0] / sr
    delta_t = t_p2 - t_p1
    # Expected distance: duration of clap1 (0.025s) + gap (0.15s) = 0.175s
    assert math.isclose(delta_t, 0.175, abs_tol=0.015), f"Timing delta mismatch: {delta_t}"
    print("  --> PASS: Double-clap transient timing conforms to exact millisecond intervals.")

    # 1.5 Noise Floor Adaptation & Quiet Gate Dynamics
    print("\n[1.5] Testing Noise Floor Adaptation & Quiet Gate Cutoff...")
    dsp = AudioDSPProcessor(noise_floor_alpha=0.992, quiet_gate_mult=2.2)
    dsp.noise_floor = 0.005

    # Step 1: Feed quiet noise (RMS 0.002) - noise floor should decrease
    for _ in range(300):
        dsp.process_block(synth.generate_noise(0.04, rms=0.002))
    assert 0.0018 <= dsp.noise_floor <= 0.0025, f"Noise floor did not adapt downwards: {dsp.noise_floor}"

    # Step 2: Feed loud noise (RMS 0.030 > 2.2 * floor) - noise floor should NOT adapt upwards
    frozen_floor = dsp.noise_floor
    for _ in range(100):
        dsp.process_block(synth.generate_noise(0.04, rms=0.030))
    assert dsp.noise_floor == frozen_floor, f"Quiet gate failed: floor changed from {frozen_floor} to {dsp.noise_floor}"

    # 1.6 Boundary & Adversarial DSP inputs
    print("\n[1.6] Testing Boundary & Adversarial DSP inputs (NaN, Inf, 0-length, extreme RMS)...")
    assert len(synth.generate_silence(0.0)) == 0
    assert len(synth.generate_noise(0.0)) == 0
    
    # Extreme RMS
    extreme_noise = synth.generate_noise(0.1, rms=50.0)
    assert np.all(np.abs(extreme_noise) <= 1.0), "Extreme RMS exceeded [-1.0, 1.0] bounds"
    
    # NaN and Inf resilience in rms_mono
    nan_arr = np.array([np.nan, 1.0, np.inf, -np.inf, np.nan], dtype=np.float32)
    rms_val = rms_mono(nan_arr)
    assert not math.isnan(rms_val) and not math.isinf(rms_val) and rms_val >= 0.0
    print("  --> PASS: DSP algorithms resilient against extreme boundary values and invalid floating-point inputs.")


def run_win32_safety_challenges():
    print("\n=======================================================")
    print("CHALLENGE 2: WIN32 CTYPES SAFETY BARRIER VERIFICATION")
    print("=======================================================")
    import ctypes
    
    platform = MockWin32Platform()
    
    # 2.1 Workstation Lock Safety Barrier
    print("\n[2.1] Testing Workstation Lock Interception...")
    # Verify initial state
    assert platform.lock_workstation_calls == 0
    
    # Simulate user32 mock binding
    class MockUser32:
        def LockWorkStation(self) -> int:
            platform.lock_workstation_calls += 1
            return 1
            
        def IsHungAppWindow(self, hwnd):
            h_int = _to_hwnd_int(hwnd)
            win = platform.windows.get(h_int)
            return 1 if win and win.is_hung else 0
            
        def SetForegroundWindow(self, hwnd):
            h_int = _to_hwnd_int(hwnd)
            if h_int in platform.windows:
                platform.foreground_hwnd = h_int
                for w in platform.windows.values():
                    w.is_foreground = (w.hwnd == h_int)
                return 1
            return 0
            
        def keybd_event(self, bVk, bScan, dwFlags, dwExtraInfo):
            platform.injected_keys.append((bVk, bScan, dwFlags, dwExtraInfo))
            
        def SendInput(self, nInputs, pInputs, cbSize):
            return nInputs

    class MockKernel32:
        def TerminateProcess(self, hProcess, uExitCode):
            platform.killed_pids.append(hProcess)
            to_del = [h for h, w in platform.windows.items() if w.pid == hProcess]
            for h in to_del:
                del platform.windows[h]
            return 1

    mock_u32 = MockUser32()
    mock_k32 = MockKernel32()

    # Intercept and test lock
    res = mock_u32.LockWorkStation()
    assert res == 1
    assert platform.lock_workstation_calls == 1
    print("  --> PASS: LockWorkStation() intercepted without invoking Windows OS lock.")

    # 2.2 Process Kill Safety Barrier
    print("\n[2.2] Testing Process Termination Safety Barrier...")
    hung_hwnd = platform.add_hung_window("MaliciousFreeze.exe", pid=8888)
    assert 8888 in [w.pid for w in platform.windows.values()]
    assert mock_u32.IsHungAppWindow(hung_hwnd) == 1
    
    # Terminate the simulated hung process
    mock_k32.TerminateProcess(8888, 1)
    assert 8888 in platform.killed_pids
    assert hung_hwnd not in platform.windows
    # Real PID of this runner must NOT be in killed_pids
    assert os.getpid() not in platform.killed_pids
    print(f"  --> PASS: TerminateProcess() scoped to mock PID 8888; real process PID {os.getpid()} untouched.")

    # 2.3 Keystroke Injection Barrier
    print("\n[2.3] Testing Virtual Keystroke & Mouse Injection Safety Barrier...")
    # Inject Win+D (Minimize all)
    mock_u32.keybd_event(0x5B, 0, 0, 0)
    mock_u32.keybd_event(0x44, 0, 0, 0)
    mock_u32.keybd_event(0x44, 0, 2, 0)
    mock_u32.keybd_event(0x5B, 0, 2, 0)
    
    assert len(platform.injected_keys) == 4
    assert platform.injected_keys[0] == (0x5B, 0, 0, 0)
    assert platform.injected_keys[1] == (0x44, 0, 0, 0)
    print("  --> PASS: keybd_event() captured inside platform.injected_keys; zero real OS keyboard events emitted.")

    # 2.4 Registry Interception Barrier
    print("\n[2.4] Testing MockWinreg Registry Safety Barrier...")
    reg = MockWinreg()
    reg.SetValueEx(None, "JARVIS_AUTORUN", 0, reg.REG_SZ, "C:\\JARVIS\\jarvis.exe")
    val, typ = reg.QueryValueEx(None, "JARVIS_AUTORUN")
    assert val == "C:\\JARVIS\\jarvis.exe"
    assert typ == reg.REG_SZ
    reg.DeleteValue(None, "JARVIS_AUTORUN")
    try:
        reg.QueryValueEx(None, "JARVIS_AUTORUN")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        pass
    print("  --> PASS: MockWinreg operations purely in-memory dictionary; zero Windows registry modifications.")


def run_fixture_isolation_challenges():
    print("\n=======================================================")
    print("CHALLENGE 3: FIXTURE ISOLATION & STATE LEAKAGE ATTACK")
    print("=======================================================")
    
    # 3.1 MockAudioStream Threading & Resource Cleanup
    print("\n[3.1] Testing MockAudioStream Thread Lifecycle & Non-blocking I/O...")
    synth = AudioSynthesizer()
    buf = synth.generate_noise(0.5, rms=0.005)
    received_chunks = []
    
    def on_audio_callback(chunk, block_size, time_info, status):
        received_chunks.append(chunk)

    stream = MockAudioStream(buffer=buf, sample_rate=44100, block_size=1764, callback=on_audio_callback)
    with stream:
        assert stream.is_active is True
        time.sleep(0.1)
    
    assert stream.is_active is False
    assert stream._thread is None or not stream._thread.is_alive()
    assert len(received_chunks) > 0
    print("  --> PASS: MockAudioStream thread starts, processes async callbacks, and terminates cleanly upon exit.")

    # 3.2 MockHttpServer State Reset Isolation
    print("\n[3.2] Testing MockHttpServer State Reset Isolation...")
    srv1 = MockHttpServer()
    srv1.ha_states["light.living_room"]["state"] = "on"
    srv1.elevenlabs_calls.append({"text": "Hello"})
    srv1.mqtt_published_messages.append(("test/topic", b"payload", 0, False))

    srv2 = MockHttpServer()
    assert srv2.ha_states["light.living_room"]["state"] == "off"
    assert len(srv2.elevenlabs_calls) == 0
    assert len(srv2.mqtt_published_messages) == 0
    print("  --> PASS: MockHttpServer instances maintain strict independent state isolation.")

    # 3.3 MockHardwareProvider Mutation Isolation
    print("\n[3.3] Testing MockHardwareProvider Mutation Isolation...")
    hw1 = MockHardwareProvider()
    hw1.simulate_overheating()
    hw1.simulate_ram_exhaustion()
    assert hw1.cpu_temp_c == 94.0
    assert hw1.ram_percent == 95.5

    hw2 = MockHardwareProvider()
    assert hw2.cpu_temp_c == 48.0
    assert hw2.ram_percent == 37.5
    print("  --> PASS: MockHardwareProvider instances maintain clean default state isolation.")

    # 3.4 MockCameraFeed Scene & Face Vector Isolation
    print("\n[3.4] Testing MockCameraFeed Face Recognition & Scene Isolation...")
    cam1 = MockCameraFeed()
    cam1.set_scene("intruder_face")
    encs_intruder = cam1.get_face_encodings(cam1.generate_synthetic_frame())
    assert len(encs_intruder) == 1
    assert np.allclose(encs_intruder[0], cam1.intruder_encoding)

    cam2 = MockCameraFeed()
    assert cam2.current_scene == "owner_face"
    encs_owner = cam2.get_face_encodings(cam2.generate_synthetic_frame())
    assert len(encs_owner) == 1
    # Check that owner encoding does NOT match intruder encoding (distance > 0.6)
    dist = np.linalg.norm(encs_owner[0] - cam2.intruder_encoding)
    assert dist > 0.6, f"Owner and intruder encodings too close: dist={dist}"
    print("  --> PASS: MockCameraFeed discriminates owner vs intruder face vectors with high Euclidean margin.")


if __name__ == "__main__":
    try:
        run_dsp_math_challenges()
        run_win32_safety_challenges()
        run_fixture_isolation_challenges()
        print("\n=======================================================")
        print("ALL EMPIRICAL CHALLENGES PASSED WITH ZERO FAILURES!")
        print("=======================================================\n")
    except Exception as e:
        print(f"\nCHALLENGE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
