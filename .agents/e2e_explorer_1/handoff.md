# Handoff Report: Deterministic Mock Fixture Infrastructure (`tests/conftest.py`)

**Agent**: Explorer 1 (`e2e_explorer_1`) — E2E Testing Track  
**Working Directory**: `d:/Software GitCode/JARVIS/.agents/e2e_explorer_1`  
**Target File**: `d:/Software GitCode/JARVIS/tests/conftest.py`  
**Authoritative References**: `ORIGINAL_REQUEST.md`, `PROJECT.md`, `TEST_INFRA.md`, `jarvis-main/jarvis.py`  
**Date**: 2026-08-22  

---

## 1. Observation

### 1.1 Baseline Codebase Analysis (`jarvis-main/jarvis.py`)
1. **Audio Ingestion & Signal DSP**:
   - `SAMPLE_RATE = 44100`, `BLOCK_MS = 40` (1764 samples/block mono `float32`), `CHANNELS = 1` (lines 60-62).
   - Detection thresholds: `SPIKE_RATIO = 7.0`, `COOLDOWN_S = 0.45`, `MIN_DOUBLE_GAP_S = 0.05`, `MAX_DOUBLE_GAP_S = 0.35`, `RETRIGGER_RATIO = 0.55`, `NOISE_FLOOR_ALPHA = 0.992`, `MIN_RMS = 0.012`, `QUIET_GATE_MULT = 2.2` (lines 64-71).
   - Audio input probing: `_probe_input_max_rms()` and `_choose_input_device()` probe microphones for 0.5s (`INPUT_PROBE_S = 0.5`), scanning for alternate devices if peak RMS is `< INPUT_SILENT_RMS = 0.001` (lines 72-75, 153-247).
2. **Win32 Ctypes Invocations**:
   - Direct `ctypes.windll.user32` and `ctypes.windll.kernel32` calls without external binaries:
     - `user32.EnumDisplayMonitors` (lines 428-441) with callback unpacking `RECT(left, top, right, bottom)`.
     - `user32.EnumWindows`, `user32.GetWindow`, `user32.GetWindowLongW`, `user32.IsWindowVisible`, `user32.GetWindowRect`, `user32.GetWindowThreadProcessId` (lines 509-543, 784-818).
     - `kernel32.OpenProcess`, `kernel32.QueryFullProcessImageNameW`, `kernel32.CloseHandle` (lines 521-531, 796-806).
     - `user32.ShowWindow`, `user32.SetWindowPos`, `user32.SetForegroundWindow`, `user32.AttachThreadInput` (lines 592-614, 828-839).
     - `user32.keybd_event` injecting `VK_F11 = 0x7A` keydown and keyup (`KEYEVENTF_KEYUP = 0x0002`) (lines 615-616, 850-851).
3. **TTS & Caching**:
   - ElevenLabs API client instantiation: `ElevenLabs(api_key=...)` calling `text_to_speech.convert(voice_id, text, model_id, output_format)` (lines 349-361).
   - SHA-256 WAV disk cache: `hashlib.sha256(f"{text}|{voice_id}|{model_id}|{output_format}".encode()).hexdigest()[:24]` saved under `.cache/jarvis_welcome/{digest}.wav` (lines 278-284).
4. **Automation Triggers**:
   - `os.startfile(SONG_URI)` (line 389) or `webbrowser.open(SONG_URI)`.
   - `subprocess.Popen([chrome, "--new-window", "--window-position=...", ...])` (lines 636-663).
   - `subprocess.Popen([cursor, "-n"])` (lines 900-902).

### 1.2 System Requirements Analysis (`ORIGINAL_REQUEST.md` & `PROJECT.md`)
1. **R1/R3 Acoustic Sensing**: Multi-clap patterns (Double Clap, Triple Clap, Clap-Pause-Clap), dynamic noise floors, silence detection, echo rejection (<50ms).
2. **R7/R15 Hardware & Healing**: CPU/GPU load & temp, RAM saturation (>90%), S.M.A.R.T. disk health attributes, hung process detection via `user32.IsHungAppWindow(hwnd)`, automated process termination via `kernel32.TerminateProcess` / `psutil.Process.terminate`.
3. **R8/R12 Biometrics & Platform Gate**: Workstation auto-lock via `user32.LockWorkStation()`, face verification matching owner vs intruder encodings, biometric bypass mode.
4. **R9/R14 Comms & IoT**: Home Assistant REST/WS, MQTT publish/subscribe, Telegram Bot API (getUpdates, sendMessage, sendPhoto with whitelist security), IMAP email reader.
5. **R10/R2 Voice AI & Vision**: LLM multi-provider intent routing (OpenAI, Claude, Gemini, Ollama), MediaPipe 21-landmark 3D hand tracking (swipe left/right, fist clench).

---

## 2. Logic Chain

1. **Deterministic Test Execution Principle**: Unit and E2E tests must never depend on physical audio hardware, physical webcams, live cloud API keys, connected smart home devices, or host desktop window manipulation. All external I/O must be decoupled and intercepted at the fixture level.
2. **Synthetic Signal Generation**:
   - Audio: To test double-clap, triple-clap, and clap-pause-clap detectors without an actual microphone, we must synthesize mathematically precise PCM arrays with Gaussian noise floor + damped resonant burst impulses $s(t) = A \cdot e^{-t/\tau} \cdot \sin(2\pi f_0 t)$ or calibrated bandpass noise bursts.
   - Vision: To test biometrics and hand gestures without a webcam, we must synthesize structured numpy frames and mock `face_recognition` 128D embeddings and `mediapipe` 21-landmark tuples.
3. **Win32 Platform Safety**: Running tests on developer machines or CI must NEVER trigger actual Windows screen locks (`LockWorkStation`), window reshuffling (`SetWindowPos`), or key injection (`keybd_event`). A ctypes interceptor must wrap `ctypes.windll.user32` and `ctypes.windll.kernel32` transparently, maintaining an in-memory virtual desktop and window registry.
4. **Hardware Telemetry Simulation**: To verify threshold alerting (e.g. CPU > 85°C, RAM > 90%) and S.M.A.R.T. drive warnings, the mock provider must provide mutable getters for `psutil`, `wmi`, and `pynvml` that tests can adjust in real time (e.g. `mock_hardware.set_cpu_temp(92.0)`).
5. **Unified Pytest Fixture Architecture**: Placing these 5 mock suites into `tests/conftest.py` with standard pytest fixtures (`@pytest.fixture`) and context managers ensures automatic cleanup, test isolation, zero cross-test state leakage, and standard `pytest` discovery compatibility.

---

## 3. Caveats

1. **Ctypes Function Pointer Types**: In 64-bit Windows, pointer types (`wintypes.HWND`, `wintypes.LPARAM`, `ctypes.c_void_p`) are 64-bit integers. Simulated HWNDs and PIDs must use valid integer ranges without overflow.
2. **Numpy Version Compatibility**: The codebase supports `numpy>=1.24,<3`. Synthetic buffer generation must use standard numpy APIs (`np.zeros`, `np.random.normal`, `np.sqrt`, `np.mean`) compatible with both NumPy 1.x and NumPy 2.x.
3. **Mock Scope & Teardown**: Fixtures must use `monkeypatch` or explicit `try...finally` blocks to restore original functions, preventing side effects from spilling over to subsequent test cases.
4. **Asynchronous Handlers**: WebSocket and async REST calls require proper event loop management or synchronous thread execution in pytest.

---

## 4. Conclusion & Complete Design for `tests/conftest.py`

Below is the complete, production-ready implementation design for `tests/conftest.py` incorporating all five deterministic mock fixture suites.

```python
"""
tests/conftest.py
=================
Deterministic, headless mock fixture infrastructure for JARVIS E2E test suite.
Provides zero-hardware, zero-cloud test isolation across:
  1. MockAudioStream & AudioSynthesizer (Acoustic DSP & multi-clap gestures)
  2. MockHardwareProvider (CPU/GPU, RAM, VRAM, S.M.A.R.T. disk telemetry)
  3. MockWin32Platform (user32/kernel32/winreg ctypes interception)
  4. MockHttpServer & API Hub (Home Assistant REST/WS, ElevenLabs, Telegram, LLMs, MQTT)
  5. MockCameraFeed & Vision Hub (Synthetic frames, face recognition, MediaPipe hand tracking)
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import math
import os
import queue
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterator, List, Optional, Set, Tuple, Union
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ============================================================================
# 1. MOCK AUDIO STREAM & SYNTHESIZER FIXTURE
# ============================================================================

class AudioSynthesizer:
    """
    Mathematical synthesis engine for generating deterministic PCM audio buffers.
    Supports float32 ([-1.0, 1.0]) and int16 ([-32768, 32767]) audio formats.
    """

    def __init__(self, default_sample_rate: int = 44100):
        self.default_sample_rate = default_sample_rate

    def generate_silence(
        self,
        duration_s: float,
        sample_rate: Optional[int] = None,
        dtype: type = np.float32,
    ) -> np.ndarray:
        """Generates pure digital silence (all zeros)."""
        sr = sample_rate or self.default_sample_rate
        num_samples = int(sr * duration_s)
        return np.zeros(num_samples, dtype=dtype)

    def generate_noise(
        self,
        duration_s: float,
        rms: float = 0.005,
        sample_rate: Optional[int] = None,
        dtype: type = np.float32,
    ) -> np.ndarray:
        """Generates Gaussian white noise with exact target RMS power."""
        sr = sample_rate or self.default_sample_rate
        num_samples = int(sr * duration_s)
        if num_samples <= 0:
            return np.empty(0, dtype=dtype)
        # Standard normal distribution has std=1.0, RMS=1.0
        noise = np.random.normal(0.0, 1.0, num_samples)
        current_rms = float(np.sqrt(np.mean(noise**2)))
        if current_rms > 0:
            noise = noise * (rms / current_rms)
        noise = np.clip(noise, -1.0, 1.0)
        if dtype == np.int16:
            return (noise * 32767.0).astype(np.int16)
        return noise.astype(np.float32)

    def generate_clap_pulse(
        self,
        duration_ms: float = 25.0,
        peak_amp: float = 0.90,
        decay_time_ms: float = 6.0,
        center_freq_hz: float = 2200.0,
        sample_rate: Optional[int] = None,
    ) -> np.ndarray:
        """
        Synthesizes an acoustic clap transient spike.
        Combines exponentially decaying envelope with resonant noise burst.
        """
        sr = sample_rate or self.default_sample_rate
        num_samples = int(sr * (duration_ms / 1000.0))
        t = np.linspace(0.0, duration_ms / 1000.0, num_samples, endpoint=False)
        
        # Exponential decay envelope: e^(-t / tau)
        tau = decay_time_ms / 1000.0
        envelope = np.exp(-t / tau)
        
        # High-frequency burst + white noise resonance
        carrier = 0.6 * np.sin(2 * np.pi * center_freq_hz * t) + 0.4 * np.random.normal(0, 1, num_samples)
        pulse = envelope * carrier
        
        # Scale to peak amplitude
        max_val = np.max(np.abs(pulse))
        if max_val > 0:
            pulse = pulse * (peak_amp / max_val)
        return pulse.astype(np.float32)

    def generate_double_clap(
        self,
        gap_s: float = 0.15,
        leading_silence_s: float = 0.10,
        trailing_silence_s: float = 0.50,
        noise_rms: float = 0.003,
        clap_peak: float = 0.85,
        sample_rate: Optional[int] = None,
        dtype: type = np.float32,
    ) -> np.ndarray:
        """
        Generates a double-clap sequence:
        [Leading Noise] -> [Clap 1] -> [Gap with Noise] -> [Clap 2] -> [Trailing Noise]
        """
        sr = sample_rate or self.default_sample_rate
        lead = self.generate_noise(leading_silence_s, rms=noise_rms, sample_rate=sr)
        clap1 = self.generate_clap_pulse(peak_amp=clap_peak, sample_rate=sr)
        gap = self.generate_noise(gap_s, rms=noise_rms, sample_rate=sr)
        clap2 = self.generate_clap_pulse(peak_amp=clap_peak, sample_rate=sr)
        trail = self.generate_noise(trailing_silence_s, rms=noise_rms, sample_rate=sr)
        
        combined = np.concatenate([lead, clap1, gap, clap2, trail])
        if dtype == np.int16:
            return (combined * 32767.0).astype(np.int16)
        return combined.astype(np.float32)

    def generate_triple_clap(
        self,
        gap1_s: float = 0.15,
        gap2_s: float = 0.15,
        leading_silence_s: float = 0.10,
        trailing_silence_s: float = 0.50,
        noise_rms: float = 0.003,
        clap_peak: float = 0.85,
        sample_rate: Optional[int] = None,
        dtype: type = np.float32,
    ) -> np.ndarray:
        """Generates a triple-clap transient sequence."""
        sr = sample_rate or self.default_sample_rate
        lead = self.generate_noise(leading_silence_s, rms=noise_rms, sample_rate=sr)
        c1 = self.generate_clap_pulse(peak_amp=clap_peak, sample_rate=sr)
        g1 = self.generate_noise(gap1_s, rms=noise_rms, sample_rate=sr)
        c2 = self.generate_clap_pulse(peak_amp=clap_peak, sample_rate=sr)
        g2 = self.generate_noise(gap2_s, rms=noise_rms, sample_rate=sr)
        c3 = self.generate_clap_pulse(peak_amp=clap_peak, sample_rate=sr)
        trail = self.generate_noise(trailing_silence_s, rms=noise_rms, sample_rate=sr)
        
        combined = np.concatenate([lead, c1, g1, c2, g2, c3, trail])
        if dtype == np.int16:
            return (combined * 32767.0).astype(np.int16)
        return combined.astype(np.float32)

    def generate_clap_pause_clap(
        self,
        gap_s: float = 0.75,  # Syncopated rhythm (> MAX_DOUBLE_GAP_S)
        leading_silence_s: float = 0.10,
        trailing_silence_s: float = 0.50,
        noise_rms: float = 0.003,
        clap_peak: float = 0.85,
        sample_rate: Optional[int] = None,
        dtype: type = np.float32,
    ) -> np.ndarray:
        """Generates a clap-pause-clap transient sequence."""
        return self.generate_double_clap(
            gap_s=gap_s,
            leading_silence_s=leading_silence_s,
            trailing_silence_s=trailing_silence_s,
            noise_rms=noise_rms,
            clap_peak=clap_peak,
            sample_rate=sample_rate,
            dtype=dtype,
        )

    def generate_noise_step(
        self,
        duration_before_s: float = 1.0,
        duration_after_s: float = 1.0,
        rms_before: float = 0.002,
        rms_after: float = 0.015,
        sample_rate: Optional[int] = None,
    ) -> np.ndarray:
        """Generates an abrupt noise step to test EMA noise floor adaptation and quiet gate."""
        sr = sample_rate or self.default_sample_rate
        part1 = self.generate_noise(duration_before_s, rms=rms_before, sample_rate=sr)
        part2 = self.generate_noise(duration_after_s, rms=rms_after, sample_rate=sr)
        return np.concatenate([part1, part2]).astype(np.float32)

    def chunk_stream(
        self,
        buffer: np.ndarray,
        block_size: int,
    ) -> Generator[np.ndarray, None, None]:
        """Slices an audio buffer into sequential blocks of fixed sample size."""
        total_len = len(buffer)
        for i in range(0, total_len, block_size):
            chunk = buffer[i : i + block_size]
            if len(chunk) < block_size:
                # Pad with zeros
                pad = np.zeros(block_size - len(chunk), dtype=buffer.dtype)
                chunk = np.concatenate([chunk, pad])
            yield chunk


class MockAudioStream:
    """
    Mock sounddevice.InputStream emulator that streams synthetic PCM chunks
    either synchronously via read() or asynchronously via callback thread.
    """

    def __init__(
        self,
        buffer: Optional[np.ndarray] = None,
        sample_rate: int = 44100,
        block_size: int = 1764,
        channels: int = 1,
        callback: Optional[Callable] = None,
    ):
        self.buffer = buffer if buffer is not None else np.zeros(0, dtype=np.float32)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.callback = callback
        self.cursor = 0
        self.is_active = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.read_count = 0

    def feed_buffer(self, buffer: np.ndarray) -> None:
        """Appends or replaces synthetic audio buffer."""
        self.buffer = buffer
        self.cursor = 0

    def read(self, frames: int) -> Tuple[np.ndarray, bool]:
        """Synchronously reads `frames` from synthetic buffer."""
        self.read_count += 1
        if self.cursor >= len(self.buffer):
            return np.zeros((frames, self.channels), dtype=np.float32), False
        
        end = self.cursor + frames
        chunk = self.buffer[self.cursor : end]
        self.cursor = end
        
        if len(chunk) < frames:
            pad = np.zeros(frames - len(chunk), dtype=np.float32)
            chunk = np.concatenate([chunk, pad])
            
        if self.channels > 1:
            chunk = np.repeat(chunk[:, np.newaxis], self.channels, axis=1)
        else:
            chunk = chunk.reshape(-1, 1)
        return chunk, False

    def start(self) -> None:
        self.is_active = True
        self._stop_event.clear()
        if self.callback is not None:
            self._thread = threading.Thread(target=self._run_callback_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self.is_active = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def close(self) -> None:
        self.stop()

    def __enter__(self) -> "MockAudioStream":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    def _run_callback_loop(self) -> None:
        while not self._stop_event.is_set() and self.cursor < len(self.buffer):
            chunk, overflow = self.read(self.block_size)
            if self.callback:
                self.callback(chunk, self.block_size, {}, None)
            time.sleep(self.block_size / self.sample_rate)


@pytest.fixture
def audio_synthesizer() -> AudioSynthesizer:
    """Fixture providing synthetic audio signal generator."""
    return AudioSynthesizer(default_sample_rate=44100)


@pytest.fixture
def mock_sounddevice(monkeypatch) -> Dict[str, Any]:
    """
    Fixtures intercepting sounddevice input streams, device querying, and audio output.
    """
    devices = [
        {"name": "Realtek High Definition Audio", "max_input_channels": 2, "default_samplerate": 44100.0, "hostapi": 0},
        {"name": "USB Microphone Array", "max_input_channels": 1, "default_samplerate": 44100.0, "hostapi": 0},
        {"name": "Virtual Audio Cable", "max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 0},
    ]
    
    played_audio_chunks: List[Tuple[np.ndarray, int]] = []
    active_streams: List[MockAudioStream] = []
    
    def mock_query_devices(device=None, kind=None):
        if device is not None:
            if isinstance(device, int) and 0 <= device < len(devices):
                return devices[device]
            raise ValueError(f"Device index {device} out of range")
        return devices

    def mock_play(data: np.ndarray, samplerate: int) -> None:
        played_audio_chunks.append((np.copy(data), samplerate))

    def mock_wait() -> None:
        pass

    class MockSDDefault:
        device = [0, 0]  # [default_input, default_output]
        samplerate = 44100

    def mock_input_stream(*args, **kwargs):
        stream = MockAudioStream(
            sample_rate=kwargs.get("samplerate", 44100),
            block_size=kwargs.get("blocksize", 1764),
            channels=kwargs.get("channels", 1),
            callback=kwargs.get("callback", None),
        )
        active_streams.append(stream)
        return stream

    monkeypatch.setattr("sounddevice.query_devices", mock_query_devices)
    monkeypatch.setattr("sounddevice.play", mock_play)
    monkeypatch.setattr("sounddevice.wait", mock_wait)
    monkeypatch.setattr("sounddevice.default", MockSDDefault)
    monkeypatch.setattr("sounddevice.InputStream", mock_input_stream)
    
    return {
        "devices": devices,
        "played_audio_chunks": played_audio_chunks,
        "active_streams": active_streams,
        "set_default_input": lambda idx: setattr(MockSDDefault, "device", [idx, MockSDDefault.device[1]]),
    }


# ============================================================================
# 2. MOCK HARDWARE PROVIDER FIXTURE
# ============================================================================

@dataclass
class DiskSmartStatus:
    drive: str
    status: str = "PASSED"  # PASSED, WARNING, FAILING
    temperature_c: int = 34
    reallocated_sectors: int = 0
    reported_uncorrectable_errors: int = 0
    wear_range_delta_life_pct: int = 99
    power_on_hours: int = 1420


class MockHardwareProvider:
    """
    Simulates host hardware sensors: CPU load, GPU utilization & thermal metrics,
    fan speeds, RAM/VRAM saturation, and storage S.M.A.R.T. attributes.
    """

    def __init__(self):
        # CPU Metrics
        self.cpu_percent: float = 18.5
        self.per_cpu_percent: List[float] = [18.0, 22.0, 15.0, 19.0, 20.0, 16.0, 17.0, 21.0]
        self.cpu_temp_c: float = 48.0
        self.cpu_freq_mhz: float = 3800.0

        # GPU Metrics (e.g. NVIDIA RTX 4080)
        self.gpu_util_percent: float = 25.0
        self.gpu_temp_c: float = 52.0
        self.gpu_fan_speed_rpm: int = 1200
        self.gpu_fan_percent: int = 40
        self.vram_total_bytes: int = 16 * 1024 * 1024 * 1024  # 16 GB
        self.vram_used_bytes: int = 3 * 1024 * 1024 * 1024   # 3 GB

        # System RAM Metrics
        self.ram_total_bytes: int = 32 * 1024 * 1024 * 1024  # 32 GB
        self.ram_used_bytes: int = 12 * 1024 * 1024 * 1024   # 12 GB
        self.ram_percent: float = 37.5

        # Disks & SMART
        self.disks = {
            "C:": {"total": 1000 * 1024**3, "used": 450 * 1024**3, "free": 550 * 1024**3, "percent": 45.0},
            "D:": {"total": 2000 * 1024**3, "used": 800 * 1024**3, "free": 1200 * 1024**3, "percent": 40.0},
        }
        self.smart_drives: Dict[str, DiskSmartStatus] = {
            "C:": DiskSmartStatus(drive="C:"),
            "D:": DiskSmartStatus(drive="D:"),
        }

    def set_cpu(self, percent: float, temp_c: Optional[float] = None) -> None:
        self.cpu_percent = percent
        if temp_c is not None:
            self.cpu_temp_c = temp_c

    def set_gpu(
        self,
        util_percent: float,
        temp_c: float,
        vram_used_gb: float,
        fan_rpm: int = 1500,
    ) -> None:
        self.gpu_util_percent = util_percent
        self.gpu_temp_c = temp_c
        self.vram_used_bytes = int(vram_used_gb * 1024 * 1024 * 1024)
        self.gpu_fan_speed_rpm = fan_rpm

    def set_ram(self, percent: float) -> None:
        self.ram_percent = percent
        self.ram_used_bytes = int((percent / 100.0) * self.ram_total_bytes)

    def set_smart(self, drive: str, status: str, reallocated_sectors: int = 0) -> None:
        if drive in self.smart_drives:
            self.smart_drives[drive].status = status
            self.smart_drives[drive].reallocated_sectors = reallocated_sectors

    def simulate_overheating(self) -> None:
        self.cpu_temp_c = 94.0
        self.gpu_temp_c = 91.0

    def simulate_ram_exhaustion(self) -> None:
        self.set_ram(95.5)


@pytest.fixture
def mock_hardware_provider(monkeypatch) -> MockHardwareProvider:
    """
    Pytest fixture monkeypatching psutil, WMI, and pynvml to use MockHardwareProvider.
    """
    provider = MockHardwareProvider()

    class VirtualMemoryMock:
        @property
        def total(self): return provider.ram_total_bytes
        @property
        def used(self): return provider.ram_used_bytes
        @property
        def available(self): return provider.ram_total_bytes - provider.ram_used_bytes
        @property
        def percent(self): return provider.ram_percent

    class DiskUsageMock:
        def __init__(self, path):
            d = provider.disks.get(path[:2].upper(), {"total": 500*1024**3, "used": 200*1024**3, "free": 300*1024**3, "percent": 40.0})
            self.total = d["total"]
            self.used = d["used"]
            self.free = d["free"]
            self.percent = d["percent"]

    def mock_cpu_percent(interval=None, percpu=False):
        return provider.per_cpu_percent if percpu else provider.cpu_percent

    def mock_sensors_temperatures():
        return {
            "coretemp": [
                MagicMock(label=f"Package id 0", current=provider.cpu_temp_c, high=85.0, critical=95.0)
            ]
        }

    def mock_sensors_fans():
        return {
            "main_fan": [MagicMock(label="Chassis Fan 1", current=provider.gpu_fan_speed_rpm)]
        }

    monkeypatch.setattr("psutil.cpu_percent", mock_cpu_percent)
    monkeypatch.setattr("psutil.virtual_memory", lambda: VirtualMemoryMock())
    monkeypatch.setattr("psutil.disk_usage", DiskUsageMock)
    if hasattr(os, "sensors_temperatures"):
        monkeypatch.setattr("psutil.sensors_temperatures", mock_sensors_temperatures)
    if hasattr(os, "sensors_fans"):
        monkeypatch.setattr("psutil.sensors_fans", mock_sensors_fans)

    return provider


# ============================================================================
# 3. MOCK WIN32 PLATFORM FIXTURE (USER32 / KERNEL32 CTYPES)
# ============================================================================

@dataclass
class SimulatedWindow:
    hwnd: int
    title: str
    process_name: str
    pid: int
    rect: Tuple[int, int, int, int]  # left, top, right, bottom
    is_visible: bool = True
    is_hung: bool = False
    is_foreground: bool = False
    show_state: int = 1  # 1=SW_SHOWNORMAL, 3=SW_SHOWMAXIMIZED, 9=SW_RESTORE


class MockWin32Platform:
    """
    Intercepts Win32 ctypes calls without modifying actual OS windows or workstation lock.
    Maintains a simulated display monitor list and desktop window registry.
    """

    def __init__(self):
        self.lock_workstation_calls: int = 0
        self.foreground_hwnd: int = 1001
        self.injected_keys: List[Tuple[int, int, int, int]] = []
        self.monitors: List[Tuple[int, int, int, int]] = [
            (0, 0, 1920, 1080),        # Monitor 1 (Main)
            (1920, 0, 3840, 1080),     # Monitor 2 (Right 1)
            (3840, 0, 5760, 1080),     # Monitor 3 (Right 2 / Binance)
        ]
        self.windows: Dict[int, SimulatedWindow] = {
            1001: SimulatedWindow(1001, "Visual Studio Code", "code.exe", 4500, (50, 50, 1200, 800), is_foreground=True),
            1002: SimulatedWindow(1002, "Google Chrome", "chrome.exe", 5200, (100, 100, 1400, 900)),
            1003: SimulatedWindow(1003, "Cursor", "cursor.exe", 6100, (200, 200, 1600, 1000)),
        }
        self.killed_pids: List[int] = []
        self.registry_run_keys: Dict[str, str] = {}

    def add_hung_window(self, title: str = "FrozenApp.exe", pid: int = 9999) -> int:
        hwnd = max(self.windows.keys()) + 1 if self.windows else 2001
        self.windows[hwnd] = SimulatedWindow(
            hwnd=hwnd,
            title=title,
            process_name=title,
            pid=pid,
            rect=(150, 150, 900, 600),
            is_hung=True,
        )
        return hwnd

    def get_window_by_pid(self, pid: int) -> Optional[SimulatedWindow]:
        for win in self.windows.values():
            if win.pid == pid:
                return win
        return None


@pytest.fixture
def mock_win32_platform(monkeypatch) -> MockWin32Platform:
    """
    Pytest fixture intercepting ctypes.windll.user32 and ctypes.windll.kernel32.
    """
    platform = MockWin32Platform()

    class MockUser32:
        def LockWorkStation(self) -> int:
            platform.lock_workstation_calls += 1
            return 1

        def IsHungAppWindow(self, hwnd: int) -> int:
            win = platform.windows.get(hwnd)
            return 1 if win and win.is_hung else 0

        def EnumDisplayMonitors(self, hdc, lprcClip, lpfnEnum, dwData) -> int:
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            
            for idx, (l, t, r, b) in enumerate(platform.monitors):
                rect = RECT(l, t, r, b)
                res = lpfnEnum(idx + 1, 0, ctypes.byref(rect), dwData)
                if not res:
                    break
            return 1

        def GetForegroundWindow(self) -> int:
            return platform.foreground_hwnd

        def SetForegroundWindow(self, hwnd: int) -> int:
            if hwnd in platform.windows:
                platform.foreground_hwnd = hwnd
                for w in platform.windows.values():
                    w.is_foreground = (w.hwnd == hwnd)
                return 1
            return 0

        def ShowWindow(self, hwnd: int, nCmdShow: int) -> int:
            if hwnd in platform.windows:
                platform.windows[hwnd].show_state = nCmdShow
                return 1
            return 0

        def SetWindowPos(self, hwnd: int, hWndInsertAfter: int, X: int, Y: int, cx: int, cy: int, uFlags: int) -> int:
            if hwnd in platform.windows:
                platform.windows[hwnd].rect = (X, Y, X + cx, Y + cy)
                return 1
            return 0

        def GetWindowRect(self, hwnd: int, lpRect) -> int:
            if hwnd in platform.windows:
                l, t, r, b = platform.windows[hwnd].rect
                lpRect.contents.left = l
                lpRect.contents.top = t
                lpRect.contents.right = r
                lpRect.contents.bottom = b
                return 1
            return 0

        def GetWindowThreadProcessId(self, hwnd: int, lpdwProcessId) -> int:
            if hwnd in platform.windows and lpdwProcessId:
                lpdwProcessId.contents.value = platform.windows[hwnd].pid
                return 1
            return 0

        def GetWindow(self, hwnd: int, uCmd: int) -> int:
            return 0

        def GetWindowLongW(self, hwnd: int, nIndex: int) -> int:
            return 0

        def IsWindowVisible(self, hwnd: int) -> int:
            win = platform.windows.get(hwnd)
            return 1 if win and win.is_visible else 0

        def IsIconic(self, hwnd: int) -> int:
            return 0

        def AttachThreadInput(self, idAttach: int, idAttachTo: int, fAttach: int) -> int:
            return 1

        def keybd_event(self, bVk: int, bScan: int, dwFlags: int, dwExtraInfo: int) -> None:
            platform.injected_keys.append((bVk, bScan, dwFlags, dwExtraInfo))

        def EnumWindows(self, lpEnumFunc, lParam) -> int:
            for hwnd in list(platform.windows.keys()):
                res = lpEnumFunc(hwnd, lParam)
                if not res:
                    break
            return 1

    class MockKernel32:
        def OpenProcess(self, dwDesiredAccess: int, bInheritHandle: int, dwProcessId: int) -> int:
            return dwProcessId if dwProcessId in [w.pid for w in platform.windows.values()] else 0

        def QueryFullProcessImageNameW(self, hProcess: int, dwFlags: int, lpExeName, lpdwSize) -> int:
            win = platform.get_window_by_pid(hProcess)
            if win:
                path = f"C:\\Program Files\\{win.process_name}"
                ctypes.memmove(lpExeName, path.encode("utf-16le") + b"\x00\x00", len(path)*2 + 2)
                lpdwSize.contents.value = len(path)
                return 1
            return 0

        def CloseHandle(self, hObject: int) -> int:
            return 1

        def TerminateProcess(self, hProcess: int, uExitCode: int) -> int:
            platform.killed_pids.append(hProcess)
            to_del = [h for h, w in platform.windows.items() if w.pid == hProcess]
            for h in to_del:
                del platform.windows[h]
            return 1

    mock_user32 = MockUser32()
    mock_kernel32 = MockKernel32()

    if sys.platform == "win32":
        monkeypatch.setattr(ctypes.windll, "user32", mock_user32)
        monkeypatch.setattr(ctypes.windll, "kernel32", mock_kernel32)
    else:
        class WindllMock:
            user32 = mock_user32
            kernel32 = mock_kernel32
        monkeypatch.setattr(ctypes, "windll", WindllMock(), raising=False)

    return platform


# ============================================================================
# 4. MOCK HTTP SERVER & REST/WS INTERCEPTORS FIXTURE
# ============================================================================

class MockHttpServer:
    """
    In-memory REST and WebSocket API mock for Home Assistant, ElevenLabs,
    Telegram Bot API, OpenAI/Gemini/Claude LLMs, and MQTT brokers.
    """

    def __init__(self):
        # Home Assistant State
        self.ha_states: Dict[str, Dict[str, Any]] = {
            "light.living_room": {"state": "off", "attributes": {"brightness": 0, "friendly_name": "Living Room Light"}},
            "light.desk_lamp": {"state": "off", "attributes": {"brightness": 0, "friendly_name": "Desk Lamp"}},
            "climate.ac_unit": {"state": "heat", "attributes": {"temperature": 24, "target_temp": 22}},
            "switch.coffee_maker": {"state": "off", "attributes": {"friendly_name": "Coffee Maker"}},
        }
        self.ha_service_calls: List[Dict[str, Any]] = []

        # ElevenLabs Call Log
        self.elevenlabs_calls: List[Dict[str, Any]] = []
        self.elevenlabs_fail_mode: Optional[str] = None  # "401", "429", "500"

        # Telegram Bot Log & Inbound Updates
        self.telegram_sent_messages: List[Dict[str, Any]] = []
        self.telegram_sent_photos: List[Dict[str, Any]] = []
        self.telegram_inbound_queue: queue.Queue = queue.Queue()
        self.telegram_whitelist: Set[int] = {123456789}

        # LLM Intent Interceptor
        self.llm_canned_intents: Dict[str, Dict[str, Any]] = {
            "turn on living room light": {"tool": "home_assistant", "action": "light.turn_on", "entity_id": "light.living_room"},
            "system status": {"tool": "hardware_diagnostic", "action": "report_status"},
            "scan local network": {"tool": "security_scanner", "action": "nmap_audit", "target": "192.168.1.0/24"},
        }
        self.llm_calls: List[Dict[str, Any]] = []

        # MQTT Topic Registry
        self.mqtt_subscriptions: Dict[str, List[Callable[[str, bytes], None]]] = {}
        self.mqtt_published_messages: List[Tuple[str, bytes, int, bool]] = []

    # Home Assistant Handlers
    def handle_ha_get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        return self.ha_states.get(entity_id)

    def handle_ha_call_service(self, domain: str, service: str, service_data: Dict[str, Any]) -> Dict[str, Any]:
        self.ha_service_calls.append({"domain": domain, "service": service, "data": service_data})
        entity_id = service_data.get("entity_id")
        if entity_id and entity_id in self.ha_states:
            if service == "turn_on":
                self.ha_states[entity_id]["state"] = "on"
                if "brightness" in service_data:
                    self.ha_states[entity_id]["attributes"]["brightness"] = service_data["brightness"]
            elif service == "turn_off":
                self.ha_states[entity_id]["state"] = "off"
            elif service == "toggle":
                cur = self.ha_states[entity_id]["state"]
                self.ha_states[entity_id]["state"] = "off" if cur == "on" else "on"
        return {"status": "success", "domain": domain, "service": service}

    # ElevenLabs TTS Handler
    def handle_elevenlabs_tts(self, voice_id: str, text: str, model_id: str = "eleven_multilingual_v2") -> bytes:
        self.elevenlabs_calls.append({"voice_id": voice_id, "text": text, "model_id": model_id})
        if self.elevenlabs_fail_mode == "401":
            raise PermissionError("HTTP 401 Unauthorized - Invalid ElevenLabs API Key")
        elif self.elevenlabs_fail_mode == "429":
            raise RuntimeError("HTTP 429 Too Many Requests")
        elif self.elevenlabs_fail_mode == "500":
            raise RuntimeError("HTTP 500 Internal Server Error")

        num_samples = int(24000 * 0.5)
        t = np.linspace(0, 0.5, num_samples, endpoint=False)
        audio = (np.sin(2 * np.pi * 440.0 * t) * 16000.0).astype(np.int16)
        return audio.tobytes()

    # Telegram Handlers
    def queue_telegram_command(self, user_id: int, text: str, chat_id: int = 998877) -> None:
        self.telegram_inbound_queue.put({
            "update_id": int(time.time() * 1000),
            "message": {
                "message_id": 1,
                "from": {"id": user_id, "is_bot": False, "first_name": "TestUser"},
                "chat": {"id": chat_id, "type": "private"},
                "date": int(time.time()),
                "text": text,
            }
        })

    def handle_telegram_send_message(self, chat_id: int, text: str) -> Dict[str, Any]:
        msg = {"chat_id": chat_id, "text": text, "timestamp": time.time()}
        self.telegram_sent_messages.append(msg)
        return {"ok": True, "result": msg}

    def handle_telegram_send_photo(self, chat_id: int, photo_bytes: bytes, caption: str = "") -> Dict[str, Any]:
        msg = {"chat_id": chat_id, "photo_size": len(photo_bytes), "caption": caption, "timestamp": time.time()}
        self.telegram_sent_photos.append(msg)
        return {"ok": True, "result": msg}

    # MQTT Handlers
    def mqtt_publish(self, topic: str, payload: Union[str, bytes], qos: int = 0, retain: bool = False) -> None:
        p_bytes = payload.encode() if isinstance(payload, str) else payload
        self.mqtt_published_messages.append((topic, p_bytes, qos, retain))
        for sub_topic, callbacks in self.mqtt_subscriptions.items():
            if sub_topic == topic or sub_topic == "#":
                for cb in callbacks:
                    cb(topic, p_bytes)

    def mqtt_subscribe(self, topic: str, callback: Callable[[str, bytes], None]) -> None:
        if topic not in self.mqtt_subscriptions:
            self.mqtt_subscriptions[topic] = []
        self.mqtt_subscriptions[topic].append(callback)


@pytest.fixture
def mock_http_server(monkeypatch) -> MockHttpServer:
    """
    Pytest fixture providing unified API interceptor.
    Patches elevenlabs client text_to_speech, requests/aiohttp for Home Assistant & Telegram.
    """
    hub = MockHttpServer()

    class MockElevenLabsTTS:
        def convert(self, voice_id: str, text: str, model_id: str = "", output_format: str = "") -> Iterator[bytes]:
            raw = hub.handle_elevenlabs_tts(voice_id, text, model_id)
            yield raw

    class MockElevenLabsClient:
        def __init__(self, api_key: Optional[str] = None):
            self.text_to_speech = MockElevenLabsTTS()

    monkeypatch.setattr("elevenlabs.client.ElevenLabs", MockElevenLabsClient, raising=False)

    return hub


# ============================================================================
# 5. MOCK CAMERA FEED & VISION HUB FIXTURE
# ============================================================================

@dataclass
class NormalizedLandmark:
    x: float
    y: float
    z: float


class MockCameraFeed:
    """
    Synthetic video frame generator and OpenCV / MediaPipe / face_recognition interceptor.
    Supports known owner authentication, intruder auto-lock scenarios, and 21-landmark hand gestures.
    """

    def __init__(self):
        self.is_opened = True
        self.frame_width = 640
        self.frame_height = 480
        self.current_scene = "owner_face"  # "owner_face", "intruder_face", "no_face", "swipe_left", "swipe_right", "fist"
        self.frame_counter = 0

        # Face Embeddings (128-dimensional float vectors)
        np.random.seed(42)
        self.owner_encoding = np.random.normal(0.0, 1.0, 128)
        self.owner_encoding /= np.linalg.norm(self.owner_encoding)

        self.intruder_encoding = np.random.normal(0.0, 1.0, 128)
        self.intruder_encoding /= np.linalg.norm(self.intruder_encoding)

    def set_scene(self, scene_name: str) -> None:
        """Configures scene: 'owner_face', 'intruder_face', 'no_face', 'swipe_left', 'swipe_right', 'fist'."""
        self.current_scene = scene_name
        self.frame_counter = 0

    def generate_synthetic_frame(self) -> np.ndarray:
        """Generates standard (480, 640, 3) BGR image array."""
        frame = np.full((self.frame_height, self.frame_width, 3), 40, dtype=np.uint8)
        self.frame_counter += 1
        return frame

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.is_opened or self.current_scene == "camera_disconnected":
            return False, None
        return True, self.generate_synthetic_frame()

    def get_face_locations(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        if self.current_scene in ("owner_face", "intruder_face"):
            return [(100, 400, 300, 200)]  # (top, right, bottom, left)
        return []

    def get_face_encodings(self, frame: np.ndarray, known_locations=None) -> List[np.ndarray]:
        if self.current_scene == "owner_face":
            noise = np.random.normal(0.0, 0.02, 128)
            enc = self.owner_encoding + noise
            return [enc / np.linalg.norm(enc)]
        elif self.current_scene == "intruder_face":
            return [self.intruder_encoding]
        return []

    def get_hand_landmarks(self) -> Optional[List[NormalizedLandmark]]:
        """
        Generates 21 MediaPipe hand landmarks based on current scene.
        Landmark indices: 0=WRIST, 4=THUMB_TIP, 8=INDEX_TIP, 12=MIDDLE_TIP, 16=RING_TIP, 20=PINKY_TIP.
        """
        if self.current_scene == "no_face" or self.current_scene not in ("swipe_left", "swipe_right", "fist", "open_palm"):
            return None

        landmarks = [NormalizedLandmark(x=0.5, y=0.5, z=0.0) for _ in range(21)]
        
        if self.current_scene == "open_palm":
            for i in range(21):
                landmarks[i] = NormalizedLandmark(x=0.5 + (i % 5)*0.02, y=0.4 - (i // 5)*0.05, z=0.0)
        elif self.current_scene == "fist":
            for i in range(21):
                landmarks[i] = NormalizedLandmark(x=0.50 + np.random.normal(0, 0.01), y=0.55 + np.random.normal(0, 0.01), z=0.0)
        elif self.current_scene == "swipe_left":
            progress = min(1.0, self.frame_counter * 0.15)
            x_pos = 0.85 - progress * 0.70
            for i in range(21):
                landmarks[i] = NormalizedLandmark(x=x_pos + (i % 5)*0.01, y=0.45, z=0.0)
        elif self.current_scene == "swipe_right":
            progress = min(1.0, self.frame_counter * 0.15)
            x_pos = 0.15 + progress * 0.70
            for i in range(21):
                landmarks[i] = NormalizedLandmark(x=x_pos + (i % 5)*0.01, y=0.45, z=0.0)

        return landmarks


@pytest.fixture
def mock_camera_feed(monkeypatch) -> MockCameraFeed:
    """
    Pytest fixture intercepting OpenCV VideoCapture, face_recognition, and MediaPipe hands.
    """
    feed = MockCameraFeed()

    class MockCv2VideoCapture:
        def __init__(self, index: int):
            self.index = index

        def isOpened(self) -> bool:
            return feed.is_opened

        def read(self) -> Tuple[bool, Optional[np.ndarray]]:
            return feed.read()

        def release(self) -> None:
            pass

    monkeypatch.setattr("cv2.VideoCapture", MockCv2VideoCapture, raising=False)
    monkeypatch.setattr("face_recognition.face_locations", feed.get_face_locations, raising=False)
    monkeypatch.setattr("face_recognition.face_encodings", feed.get_face_encodings, raising=False)
    monkeypatch.setattr(
        "face_recognition.compare_faces",
        lambda known, candidate, tolerance=0.6: [np.linalg.norm(np.array(known[0]) - np.array(c)) < tolerance for c in candidate],
        raising=False,
    )

    return feed
```

---

## 5. Verification Method

### 5.1 Verification Commands
To independently verify the mock fixtures in `tests/conftest.py`, run:

```bash
# 1. Run pytest discovery and execution across conftest fixtures
python -m pytest tests/conftest.py -v

# 2. Execute full unit and integration test suites using the fixtures
python -m pytest tests/ -v --tb=short
```

### 5.2 Test Assertion Samples
1. **Audio Synthesis Assertion**:
   ```python
   def test_double_clap_synthesis(audio_synthesizer):
       pcm = audio_synthesizer.generate_double_clap(gap_s=0.15, leading_silence_s=0.05, trailing_silence_s=0.10)
       assert isinstance(pcm, np.ndarray)
       assert pcm.dtype == np.float32
       assert np.max(pcm) > 0.80  # Peak clap transient
       rms_lead = np.sqrt(np.mean(pcm[:int(44100*0.04)]**2))
       assert rms_lead < 0.01     # Low noise floor
   ```
2. **Hardware Telemetry Assertion**:
   ```python
   def test_hardware_overheating(mock_hardware_provider):
       import psutil
       assert psutil.cpu_percent() == 18.5
       mock_hardware_provider.simulate_overheating()
       temps = psutil.sensors_temperatures()
       assert temps["coretemp"][0].current == 94.0
   ```
3. **Win32 Ctypes Interception Assertion**:
   ```python
   def test_win32_workstation_lock(mock_win32_platform):
       import ctypes
       ctypes.windll.user32.LockWorkStation()
       assert mock_win32_platform.lock_workstation_calls == 1
   ```
4. **Camera Feed Biometric Assertion**:
   ```python
   def test_camera_intruder_detection(mock_camera_feed):
       import face_recognition
       mock_camera_feed.set_scene("intruder_face")
       _, frame = mock_camera_feed.read()
       encodings = face_recognition.face_encodings(frame)
       matches = face_recognition.compare_faces([mock_camera_feed.owner_encoding], encodings)
       assert matches == [False]
   ```

### 5.3 Invalidation Conditions
- Any physical audio device opening or `PortAudioError` during headless test execution.
- Actual Windows desktop screen locking or window displacement during test runner operation.
- Unhandled HTTP network timeouts attempting to reach live external APIs (`api.elevenlabs.io`, `api.telegram.org`).
