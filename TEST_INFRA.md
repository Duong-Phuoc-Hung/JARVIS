# JARVIS Testing Infrastructure & Architecture Guide

## 1. Overview
The JARVIS test infrastructure provides deterministic, isolated, and hardware-independent quality verification for the entire AI voice assistant subsystem. All unit and integration suites run in headless environments (CI/CD, local development, Windows/Linux/macOS) with zero cloud dependencies and zero live audio device requirements.

---

## 2. Multi-Tier Test Hierarchy

```
┌────────────────────────────────────────────────────────────────────────┐
│                        JARVIS Quality Gates                            │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Unit Tests (tests/unit/)                                       │
│   - Pure logic isolation, deterministic DSP, mock STA COM, fast (<0.1s) │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Integration Tests (tests/integration/, tests/test_*.py)        │
│   - Multi-module wiring (Audio <-> TTS <-> STT <-> Router <-> UI)      │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Adversarial & Stress Harness (tests/test_adversarial_*.py)     │
│   - Buffer overflows, malformed payloads, regex DoS, race conditions   │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 4: E2E Workflows (tests/e2e/)                                     │
│   - Full voice turnaround, task execution, tool calling pipelines      │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 5: Intent Benchmark Evaluation (tests/eval/routing_eval_n150.py)  │
│   - 150-utterance Vietnamese intent classification accuracy eval       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mock & Deterministic Synthesis Infrastructure

### 3.1 Acoustic DSP & Signal Generation
- **Mathematical Formant Synthesizer (`jarvis.audio.wake_word.generate_wake_word_signal`)**:
  Synthesizes realistic dual-syllable acoustic waveforms matching the phonetic formant envelope of *"Hey JARVIS"* (S1: 150/620/1240 Hz Hann envelope, S2: 4800 Hz fricative noise burst).
- **Audio Synthesizer Fixture (`tests/conftest.py:AudioSynthesizer`)**:
  Generates precise Gaussian white noise, single/double/triple claps, impulse transients, and digital silence buffers at 16kHz and 44.1kHz.

### 3.2 Windows COM Apartment Concurrency Safety
- **COM Apartment Interception (`pythoncom`, `win32com.client`)**:
  Simulates Windows Single-Threaded Apartment (STA) lifecycle on daemon background threads. Mocks `pythoncom.CoInitialize()` and `pythoncom.CoUninitialize()`, intercepting `pywintypes.com_error (-2147221008)` to verify fault recovery and PowerShell fallback.

### 3.3 Neural Speech-to-Text (Faster-Whisper)
- **CTranslate2 WhisperModel Mocking**:
  Enables validation of eager background preloading threads, `vad_filter=True` parameter propagation, silence trimming, and transcription latency budgets ($\le 1.5\text{s}$) without requiring gigabyte model downloads.

### 3.4 Hardware Telemetry & Win32 Platform
- **Hardware Telemetry Provider (`jarvis.hardware.monitor.HardwareMetrics`)**:
  Injects synthetic CPU load, CPU temperature, RAM usage, GPU load, VRAM, and S.M.A.R.T. disk statuses to test natural language speech generation.

### 3.5 System Tray & UI Headless Mode
- **Pystray & Tkinter Headless Degradation**:
  Provides dynamic RGBA icon generation and thread isolation verification without opening OS desktop windows.

---

## 4. Sprint 2 (v4.7.0) Test Suite Inventory

| Test File | Target Requirement | Scope | Test Count |
|---|---|---|:---:|
| `tests/unit/test_acoustic_hardening.py` | R1 (P1-8 DSP Acoustic Hardening) | VAD silent frame discard, speech pass-through, 2.5s post-TTS mic suppression, ring buffer clearing, SFM bounds [0.03, 0.65], ZCR threshold $\ge 0.10$, clap rejection | 9 |
| `tests/unit/test_tts_com_safety.py` | R2 (P1-9 SAPI5 COM Safety) | `pythoncom` STA lifecycle, 10 consecutive TTS calls in daemon thread, SAPI5 fallback error handling, finally block cleanup | 5 |
| `tests/unit/test_stt_preload.py` | R3 (P1-10 Faster-Whisper Preload) | Background eager model preload, `vad_filter=True`, latency budget $\le 1.5\text{s}$, concurrent transcribe thread safety | 5 |
| `tests/unit/test_tray_menu.py` | R4 (P1-7 System Tray & Status) | Tray menu items $\ge 4$, "Status" item telemetry (version 4.7.0, TTS, STT, RAM%), safe `Path` import in `_on_view_logs` | 5 |
| `tests/unit/test_router_hardware.py` | R5 (P1-11 Hardware Voice & Routing) | 5 hardware queries routing (CPU, RAM, temp, pin, speed), unaccented variants, Vietnamese voice summary formatting | 13 |

---

## 5. Execution Commands

### Run All Sprint 2 Unit Tests
```powershell
pytest tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py tests/unit/test_stt_preload.py tests/unit/test_tray_menu.py tests/unit/test_router_hardware.py -v
```

### Run Full Unit Test Suite
```powershell
pytest tests/unit/ -q
```

### Run Intent Routing Benchmark (N=150)
```powershell
python tests/eval/routing_eval_n150.py
```

### Run Complete Regression & Adversarial Suite
```powershell
pytest tests/unit/ tests/test_adversarial_*.py -q
```
