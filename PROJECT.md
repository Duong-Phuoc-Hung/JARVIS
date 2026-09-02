# Project: JARVIS Sprint 2 (v4.7.0) - P1 Accuracy, Acoustic & UX Hardening

## Architecture
JARVIS is a modular AI voice assistant for Windows 11.
- **Audio & Acoustic Engine (`jarvis/audio/`, `jarvis/core/app.py`)**: Real-time microphone capture via SoundDevice, multi-tier wake word detection (Vosk, Faster-Whisper sliding window, Acoustic spectral detector), energy/WebRTC VAD pre-filter gate, 2.5s post-TTS microphone suppression window.
- **TTS Engine (`jarvis/tts/`)**: TTS Manager with ElevenLabs cloud synthesis and SAPI5 offline fallback. Background worker thread with Windows Single-Threaded Apartment COM lifecycle discipline (`pythoncom.CoInitialize()` and `pythoncom.CoUninitialize()`).
- **STT Engine (`jarvis/stt/`)**: Faster-Whisper CTranslate2 STT with eager background thread model preloading on initialization and built-in VAD silence trimming (`vad_filter=True`).
- **UI & HUD Overlay (`jarvis/ui/`)**: AlwaysOnOverlay Tkinter interface running in a dedicated background daemon thread with all mutations marshaled via `_schedule()` / `root.after(0, fn)`. SystemTrayController with dynamic status generator (version, TTS status, STT model readiness, RAM usage) and safe path resolution.
- **Hardware Telemetry & Intent Routing (`jarvis/hardware/`, `jarvis/llm/router.py`)**: HardwareReporter formatting natural Vietnamese voice summary with CPU%, RAM%, GPU temp, SMART storage. LLMIntentRouter with fast regex and dictionary rules routing hardware inquiries (CPU, RAM, GPU, battery/pin, temperature) directly to `system_status` / `hardware_telemetry_check`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F-01 | VAD Filter Gate | Pre-filter raw audio blocks before wake word ring buffer | M1 | ORIGINAL_REQUEST §R1 |
| F-02 | 2.5s Echo Lockout | Suppress/ignore microphone frames during and 2.5s after TTS | M1 | ORIGINAL_REQUEST §R1 |
| F-03 | SFM/ZCR Thresholds | Verify/maintain spectral flatness [0.03, 0.65] and ZCR >= 0.10 | M1 | ORIGINAL_REQUEST §R1 |
| F-04 | TTS Worker COM Safety | pythoncom.CoInitialize/CoUninitialize in TTSManager worker thread | M2 | ORIGINAL_REQUEST §R2 |
| F-05 | SAPI5 COM Lifecycle | Ensure CoUninitialize in finally block in fallback.py | M2 | ORIGINAL_REQUEST §R2 |
| F-06 | FasterWhisper Preload | Background eager model loading on FasterWhisperSTT.__init__() | M3 | ORIGINAL_REQUEST §R3 |
| F-07 | STT VAD Silence Trim | Configure vad_filter=True & min_silence_duration_ms=500 in transcribe() | M3 | ORIGINAL_REQUEST §R3 |
| F-08 | HUD Thread Isolation | Confirm AlwaysOnOverlay uses _schedule(fn) -> root.after(0, fn) | M4 | ORIGINAL_REQUEST §R4 |
| F-09 | System Tray Status Item | Add "Status" item (v4.7.0, TTS, STT, RAM%) and fix Path import | M4 | ORIGINAL_REQUEST §R4 |
| F-10 | Hardware Voice Summary | Format Vietnamese voice summary with CPU%, RAM%, GPU temp | M5 | ORIGINAL_REQUEST §R5 |
| F-11 | Hardware Intent Routing | Route 5 hardware queries (cpu, ram, temp, pin, speed) with MISROUTED=0 | M5 | ORIGINAL_REQUEST §R5 |
| F-12 | Adversarial Test Fixes | Fix dialog detector severity, 50KB regex speed, and alert debounce | M5 | Survey Handoff |
| F-13 | E2E & Unit Test Suites | Create unit/E2E test suites for R1-R5 (acoustic, com, preload, tray, hw) | Test Track | ORIGINAL_REQUEST §R6 |
| F-14 | Routing Benchmark Eval | routing_eval_n150.py with SILENT <= 5% and MISROUTED = 0 | M6 | ORIGINAL_REQUEST §R6 |
| F-15 | Version Bump & Release | Bump to v4.7.0, update CHANGELOG.md, commit & push to origin main | M6 | ORIGINAL_REQUEST §R6 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Design & write test suites (Tiers 1-4) across R1–R5, publish TEST_READY.md | none | IN_PROGRESS |
| M1 | DSP Acoustic Hardening | VAD pre-filter gate, 2.5s post-TTS mic suppression, SFM/ZCR bounds | none | PLANNED |
| M2 | SAPI5 TTS COM Safety | CoInitialize/CoUninitialize on daemon thread & SAPI5 fallback | none | PLANNED |
| M3 | Faster-Whisper Preload & VAD | Background preload thread, vad_filter=True, cold-start latency | none | PLANNED |
| M4 | HUD Isolation & Tray Status | AlwaysOnOverlay thread safety, Tray Status menu item, Path import fix | none | PLANNED |
| M5 | Hardware Voice & Router Rules | GPU temp voice summary, 5 hardware query rules, adversarial fixes | none | PLANNED |
| M6 | Final Verification & Release | Pytest 0 failures, routing eval benchmark, version bump, CHANGELOG, git push | M1, M2, M3, M4, M5, E2E | PLANNED |

## Interface Contracts
### Audio & TTS Interaction (`jarvis/audio/` ↔ `jarvis/tts/manager.py`)
- `TTSManager.is_in_echo_window(current_time: float | None = None, cooldown_s: float = 2.5) -> bool`: returns True if TTS is actively playing or finished < 2.5s ago.
- `WakeWordDetector.suppress_until(timestamp: float) -> None`: clears ring buffer and resets sliding window detectors.
- `WakeWordDetector.feed_audio_block(block, timestamp)`: drops frames when VAD detects silence or when in echo window.

### TTS COM Safety Contract (`jarvis/tts/manager.py`, `jarvis/tts/fallback.py`)
- `TTSManager._process_queue()`: wraps worker thread lifecycle with `pythoncom.CoInitialize()` and `pythoncom.CoUninitialize()` in `finally:`.
- `SAPI5FallbackTTS.speak()`: wraps COM speech calls in `try: pythoncom.CoInitialize() ... finally: pythoncom.CoUninitialize()`.

### STT Preloading Contract (`jarvis/stt/engine.py`)
- `FasterWhisperSTT.__init__(config=None, preload=True)`: starts background daemon thread for `_get_model()`.
- `FasterWhisperSTT.transcribe(audio, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}, ...)`: trims silence and transcribes within 1.5s.

### System Tray Status Contract (`jarvis/ui/tray.py`)
- `SystemTrayController.menu_items`: contains `"Status"` item that dynamically generates version, TTS state, STT state, and RAM%.
- `_on_view_logs`: safely references `Path` from `pathlib`.

### Hardware Reporter & Router Contract (`jarvis/hardware/reporter.py`, `jarvis/llm/router.py`)
- `HardwareReporter.format_voice_summary(metrics, lang="vi") -> str`: includes CPU%, RAM%, and GPU temp when available.
- `LLMIntentRouter.parse_intent(text, force_llm=False)`: parses `"cpu mấy phần trăm"`, `"ram còn bao nhiêu"`, `"nhiệt độ máy"`, `"pin còn bao nhiêu"`, `"tốc độ cpu"` into `action_name="system_status"` (or `hardware_telemetry_check`) with confidence >= 0.95.

## Code Layout
- `jarvis/audio/wake_word.py`: Wake word detector, VAD filter gate, ring buffer, spectral detector.
- `jarvis/audio/dsp.py`: DSP utilities, RMS calculation, spectral analysis.
- `jarvis/core/app.py`: Main JarvisApp loop, audio block dispatch, 2.5s mic suppression window.
- `jarvis/tts/manager.py`: TTSManager, daemon queue worker thread, COM lifecycle, echo window tracking.
- `jarvis/tts/fallback.py`: SAPI5FallbackTTS COM wrapper.
- `jarvis/stt/engine.py`: FasterWhisperSTT, background preload thread, VAD silence trimming.
- `jarvis/ui/overlay.py`: AlwaysOnOverlay, Tkinter event scheduling via `_schedule()`.
- `jarvis/ui/tray.py`: SystemTrayController, pystray menu, "Status" item.
- `jarvis/hardware/reporter.py`: HardwareReporter, `format_voice_summary()`.
- `jarvis/hardware/monitor.py`: HardwareMonitor, telemetry probe, emergency alert debounce logic.
- `jarvis/llm/router.py`: LLMIntentRouter, Tier-1 regex/dictionary rules for hardware queries.
- `jarvis/vision/dialog_detector.py`: DialogDetector severity precedence.
- `jarvis/__init__.py`: Package metadata, `__version__ = "4.7.0"`.
- `tests/unit/test_acoustic_hardening.py`: Unit tests for VAD filter and 2.5s echo suppression.
- `tests/unit/test_tts_com_safety.py`: Unit tests for SAPI5 COM apartment thread safety.
- `tests/unit/test_stt_preload.py`: Unit tests for Faster-Whisper background preload and VAD trim.
- `tests/unit/test_tray_menu.py`: Unit tests for tray status menu and Path import safety.
- `tests/unit/test_router_hardware.py`: Unit tests for 5 hardware query intent rules.
- `CHANGELOG.md`: Release notes for v4.7.0.
