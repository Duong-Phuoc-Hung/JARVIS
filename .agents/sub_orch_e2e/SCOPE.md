# Scope: E2E Testing Track

## Architecture
The E2E Testing Track is responsible for designing, implementing, and validating an opaque-box, requirement-driven test suite covering all 43 features (F-01 to F-43) across Requirements R1 to R15.
Tests operate in a completely headless CI-friendly environment using high-fidelity mock fixtures without requiring physical microphones, webcams, smart lights, or live Nmap binaries.

```
E2E Test Architecture
========================================================================================
+------------------------------------------------------------------------------------+
|                         PYTEST RUNNER (python -m pytest tests/)                    |
+------------------------------------------------------------------------------------+
                                           │
         ┌─────────────────────────────────┴─────────────────────────────────┐
         ▼                                                                   ▼
+───────────────────────────────────+             +───────────────────────────────────+
|      HEADLESS MOCK FIXTURES       |             |         TEST SUITE TIERS          |
|  - MockAudioStream (PCM spikes)   |             |  - Tier 1: Feature Coverage       |
|  - MockHardwareProvider (CIM/WMI) |             |  - Tier 2: Boundary & Corner      |
|  - MockWin32Platform (ctypes)     |             |  - Tier 3: Cross-Feature Flows    |
|  - MockHttpServer (HA/REST/LLM)   |             |  - Tier 4: Real-World Workflows   |
|  - MockCameraFeed (OpenCV/MediaP) |             +───────────────────────────────────+
+───────────────────────────────────+                               │
                                                                    ▼
                                                  +───────────────────────────────────+
                                                  |           TEST MODULES            |
                                                  | - test_config.py                  |
                                                  | - test_audio_dsp.py               |
                                                  | - test_gesture_detector.py        |
                                                  | - test_tts_engine.py              |
                                                  | - test_plugins.py                 |
                                                  | - test_dispatcher.py              |
                                                  | - test_windows_platform.py        |
                                                  | - test_llm_router.py              |
                                                  | - test_hardware_monitor.py        |
                                                  | - test_self_healing.py            |
                                                  | - test_security_scanner.py        |
                                                  | - test_biometrics.py              |
                                                  | - test_smart_home.py              |
                                                  | - test_data_analytics.py          |
                                                  | - test_comms_hub.py               |
                                                  | - test_e2e_scenarios.py           |
                                                  +───────────────────────────────────+
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F-01 | Modular Package Structure | Package refactoring & public API type hints | E2E-M1, E2E-M2 | R1 |
| F-02 | Monolith Legacy Compatibility | Backward compatibility with `.env` variables | E2E-M2 | R1, R3 |
| F-03 | Acoustic Signal Processor | RMS audio calculation & spike ratio detection | E2E-M2 | R1, R3 |
| F-04 | Microphone Auto-Probe | Scans and selects loudest working microphone | E2E-M2 | R1, R3 |
| F-05 | Double Clap Detection | Detects 2 transients in 0.05-0.35s with cooldown | E2E-M2 | R3 |
| F-06 | Triple Clap Detection | Detects 3 consecutive claps within timing thresholds | E2E-M2 | R3 |
| F-07 | Clap-Pause-Clap Detection | Detects syncopated rhythm pattern | E2E-M2 | R3 |
| F-08 | Dynamic Action Dispatcher | Central event bus routing triggers to plugins | E2E-M2 | R1, R4 |
| F-09 | Base Plugin Architecture | Standardized plugin interface (`execute`, `validate`) | E2E-M2 | R4 |
| F-10 | Config Hot-Reload Watcher | File watcher reloads YAML/JSON configs within 5s | E2E-M2 | R4 |
| F-11 | ElevenLabs TTS Engine | High-fidelity TTS generation via ElevenLabs API | E2E-M2 | R1, R2 |
| F-12 | Local TTS Audio Cache | SHA-256 caching of generated TTS WAV files | E2E-M2 | R1, R2 |
| F-13 | Offline Fallback TTS | Local SAPI5 / pyttsx3 speech synthesis fallback | E2E-M2 | R2 |
| F-14 | Speech-to-Text (STT) Engine | Local/Cloud STT converting microphone audio to text | E2E-M2 | R2 |
| F-15 | LLM Semantic Intent Engine | Multi-provider LLM client with tool-calling | E2E-M2 | R2 |
| F-16 | System Tray Controller | Windows taskbar icon with status indicators | E2E-M2 | R5 |
| F-17 | Real-Time Dashboard | Embedded Web/WS dashboard showing real-time metrics | E2E-M2 | R5 |
| F-18 | Structured File Logging | Rotating log handler recording timestamped results | E2E-M2 | R6 |
| F-19 | Windows Auto-Start Installer | Single CLI command configuring Windows Registry | E2E-M2 | R6 |
| F-20 | Hardware Telemetry Collector | Gathers CPU, GPU, RAM, VRAM metrics via CIM/psutil | E2E-M2 | R7 |
| F-21 | S.M.A.R.T. Disk Health Prober | Analyzes hard drive health attributes & free space | E2E-M2 | R7 |
| F-22 | Hardware Voice Alerts & Query | Vocal alert when thresholds breached; answers query | E2E-M2 | R7 |
| F-23 | Network Scanner Wrapper (Nmap) | CLI wrapper executing subnet discovery & audits | E2E-M2 | R8 |
| F-24 | Packet Capture Wrapper (TShark) | CLI wrapper executing live packet capture | E2E-M2 | R8 |
| F-25 | Security Risk Report Generator | Compiles scan results into Markdown/PDF report | E2E-M2 | R8 |
| F-26 | Home Assistant REST/WS Client | Integrates with HA API for device state & calls | E2E-M2 | R9 |
| F-27 | MQTT Protocol Adapter | Publishes/subscribes to MQTT topics for IoT | E2E-M2 | R9 |
| F-28 | Data Ingestion & Stats Engine | Ingests CSV/XLSX, computes descriptive statistics | E2E-M2 | R10 |
| F-29 | Monte Carlo Simulation Module | Runs probabilistic simulations over parameters | E2E-M2 | R10 |
| F-30 | Multi-Format Document Exporter | Generates formatted DOCX, PDF, PPTX files | E2E-M2 | R10 |
| F-31 | Workspace VM Orchestrator | CLI wrapper for VMware and VirtualBox | E2E-M2 | R11 |
| F-32 | IDE & Terminal Workspace Prep | Spawns/focuses Cursor/VS Code + Windows Terminal | E2E-M2 | R11 |
| F-33 | Face Enrollment & Verification | Enrolls owner face encodings & matches frames | E2E-M2 | R12 |
| F-34 | Biometric Privilege Gate | Intercepts high-privilege actions until verified | E2E-M2 | R12 |
| F-35 | Intruder Detection & Auto-Lock | Locks Windows workstation, snaps photo & alerts | E2E-M2 | R12 |
| F-36 | MediaPipe Hand Gesture Tracker | 21-landmark 3D hand tracking for gestures | E2E-M2 | R13 |
| F-37 | Virtual Desktop & Window Gestures | Swipe left/right virtual desktop; fist closes window | E2E-M2 | R13 |
| F-38 | Telegram Bot Remote Controller | Two-way Telegram bot with whitelist user ID | E2E-M2 | R14 |
| F-39 | IMAP Email Reader & Summarizer | Polls IMAP mailboxes, summarizes priority emails | E2E-M2 | R14 |
| F-40 | Discord Bot Integration | Discord bot monitoring channels & summaries | E2E-M2 | R14 |
| F-41 | Process & Resource Watchdog | Polling watchdog monitoring RAM & CPU saturation | E2E-M2 | R15 |
| F-42 | Unresponsive App Detector | Win32 `IsHungAppWindow()` probe for frozen apps | E2E-M2 | R15 |
| F-43 | Autonomous Healing Protocol | Terminates hung processes, reclaims memory | E2E-M2 | R15 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E-M1 | Test Fixtures & Harness | `tests/conftest.py` with `MockAudioStream`, `MockHardwareProvider`, `MockWin32Platform`, `MockHttpServer`, `MockCameraFeed` | none | DONE |
| E2E-M2 | Tier 1 Feature Coverage Suites | Core, Audio, TTS, Plugins, Dispatcher, Win32, LLM, Hardware, Healing, Security, Biometrics, Smart Home, Data, Comms unit test suites | E2E-M1 | DONE |
| E2E-M3 | Tier 2 Boundary & Robustness Suites | Error conditions, timeouts, malformed configs, offline fallbacks, unauthenticated gating | E2E-M1, E2E-M2 | DONE |
| E2E-M4 | Tier 3 & Tier 4 Scenarios | Cross-feature interactions and real-world multi-step workflows (`test_e2e_scenarios.py`) | E2E-M1, E2E-M2, E2E-M3 | DONE |
| E2E-M5 | Suite Validation & TEST_READY | Complete pytest verification, coverage reporting, and publish `TEST_READY.md` | E2E-M1..E2E-M4 | DONE |
