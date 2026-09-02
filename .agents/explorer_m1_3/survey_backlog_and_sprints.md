# Technical Backlog & Phased Sprint Plan Survey (ROADMAP.md Parts B & C)

**Author:** Explorer M1-3 (Technical Backlog & Phased Sprint Architect)  
**Date:** 2026-09-02  
**Target Milestone:** M1 (Roadmap Formulation for v4.6.0 – v5.0.0)  
**Referenced Documents:** `ORIGINAL_REQUEST.md`, `PROJECT.md`, `explorer_survey_1`, `explorer_survey_2`, `spec_miner_survey_3`  
**Workspace:** `d:\Software GitCode\JARVIS`

---

## 1. Executive Summary

This document establishes the comprehensive, prioritized technical backlog (22 granular items across P0 Critical, P1 High, P2 Medium, and P3 Low) and the 4-stage Phased Sprint Plan for JARVIS. It forms the canonical technical blueprint for **Part B (Prioritized Technical Backlog)** and **Part C (Phased Sprint Plan)** of `docs/ROADMAP.md`.

### Prioritization Framework
| Priority | Definition | Scope & Impact |
|---|---|---|
| 🔴 **P0 Critical** | Blocking real-world use | JARVIS cannot start, crashes on missing modules, or fails primary voice routing. |
| 🟠 **P1 High** | UX / Accuracy degradation | System operates but experiences high latency, acoustic false triggers, or audio blocking. |
| 🟡 **P2 Medium** | High-value missing features | Multimodal capabilities: stateful memory, screen vision, live web intelligence, IoT bridge. |
| 🟢 **P3 Low** | Polish & Packaging | Standalone installers, web dashboards, automated benchmarking, and bilingual support. |

---

## 2. Part B: Prioritized Technical Backlog (P0–P3)

### 🔴 Priority P0: Critical Subsystems & Blocking Fixes

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                P0 CRITICAL BACKLOG                                │
├───────┬───────────────────────────────────┬───────────────────────────────────────┤
│ ID    │ Feature Name                      │ Primary Affected Files                │
├───────┼───────────────────────────────────┼───────────────────────────────────────┤
│ P0-1  │ Production-Ready Wake Word        │ jarvis/audio/wake_word.py             │
│ P0-2  │ ProactiveEngine Background Daemon │ jarvis/workers/proactive.py, app.py   │
│ P0-3  │ Tier-2 LLM Routing Pipeline       │ jarvis/llm/router.py, client.py       │
│ P0-4  │ Router Tier-1 Coverage Expansion  │ jarvis/llm/router.py                  │
│ P0-5  │ Test Suite Integrity (0 Failures) │ tests/conftest.py, tests/unit/        │
└───────┴───────────────────────────────────┴───────────────────────────────────────┘
```

#### Item P0-1: Production-Ready Offline Wake Word Detection Subsystem
- **Priority:** 🔴 P0 Critical
- **Feature Name:** Offline Wake Word Detection ("Hey JARVIS" / "JARVIS")
- **Technical Description:**  
  Currently, `vosk` is missing from the environment, causing `WakeWordDetector` to drop to `AcousticSpectralDetector` (SFM/ZCR fallback), which exhibits erratic detection in real-world acoustic environments. This item installs `vosk`, wires the offline Vietnamese model (`vosk-model-small-vn-0.4`), implements a sliding-window Faster-Whisper keyword search fallback, eliminates unhandled `ImportError` exceptions, and guarantees $\ge 70\%$ microphone detection accuracy with $< 1.0\text{s}$ latency.
- **Affected Files:**
  - `jarvis/audio/wake_word.py` (L1–L758)
  - `jarvis/audio/engine.py` (L50–L210)
  - `config/default_config.yaml` (L30–L45)
  - `scripts/download_models.py`
- **Concrete Implementation Steps:**
  1. Add `vosk` dependency to virtual environment; create model directory bootstrap in `models/vosk-model-small-vn-0.4`.
  2. In `jarvis/audio/wake_word.py`, implement `VoskKeywordDetector` with constrained grammar search: `["hey jarvis", "jarvis", "chào jarvis", "[unk]"]`.
  3. Implement sliding-window ring buffer with `FasterWhisperSTT` keyword spotting as secondary offline fallback when Vosk model is not downloaded.
  4. Retain `AcousticSpectralDetector` as tertiary zero-dependency fallback for headless/CI test environments.
  5. Provide dynamic thread-safe enable/disable toggle (`set_enabled(bool)`) callable from Windows System Tray without application restart.
- **Test Verification Method:**
  - Unit Test: `pytest tests/unit/test_wake_word.py -k "test_vosk_or_fallback_detection" -q`
  - Integration Test: Feed synthesized 44.1kHz audio buffer containing "hey jarvis" and verify callback fires with `confidence >= 0.70`.
  - Negative Test: Feed 5 seconds of white noise and double clap transients; verify false trigger count is 0.

---

#### Item P0-2: ProactiveEngine Background Worker Daemon Architecture
- **Priority:** 🔴 P0 Critical
- **Feature Name:** Proactive Intelligence Worker (`ProactiveEngine`)
- **Technical Description:**  
  `jarvis/workers/proactive.py` is currently MISSING from the codebase, but is explicitly imported in `jarvis/core/app.py` (causing startup crashes if referenced). This item implements `ProactiveEngine` with background reminder scheduling, hardware threshold watchdogs (CPU > 90%, RAM > 90%, disk < 10GB free, temp > 85°C), Pomodoro focus timer, daily morning briefing, and registers the `proactive_reminder` action with `ActionDispatcher`.
- **Affected Files:**
  - `jarvis/workers/proactive.py` (New File, ~350 lines)
  - `jarvis/workers/__init__.py`
  - `jarvis/core/app.py` (L60–L150, L680–L760)
  - `config/default_config.yaml` (L80–L110)
- **Concrete Implementation Steps:**
  1. Create `jarvis/workers/proactive.py` containing `ProactiveEngine` daemon thread with 1.0-second tick loop.
  2. Implement `ReminderScheduler` supporting relative (`sau 5 phút`) and absolute (`lúc 15:00`) time triggers, storing in `data/reminders.json`.
  3. Implement `HardwareAlertWatchdog` checking `HardwareMonitor` metrics every 10s with 120s debouncing per alert category.
  4. Implement `PomodoroTimer` state machine (25-min work / 5-min break cycles).
  5. Wire `ProactiveEngine` into `JarvisApp.initialize()`, `start()`, and `stop()` lifecycle methods.
  6. Register actions `proactive_reminder`, `focus_mode_start`, and `focus_mode_cancel` into `ActionDispatcher`.
- **Test Verification Method:**
  - `pytest tests/unit/test_proactive_engine.py -q` (>= 3 test cases).
  - Verify `from jarvis.workers.proactive import ProactiveEngine` succeeds without `ModuleNotFoundError`.
  - Simulate RAM utilization at 95% and assert `EventBus.publish("hardware.alert")` triggers TTS voice warning.

---

#### Item P0-3: Tier-2 LLM Semantic Routing Pipeline Verification & Live Wiring
- **Priority:** 🔴 P0 Critical
- **Feature Name:** Tier-2 LLM Intent Routing & Dynamic Tool Calling
- **Technical Description:**  
  Baseline measurements indicate that 64.8% of user utterances miss Tier-1 rules and fall into SILENT_FAILURE. While Tier-2 LLM routing code exists, it must be verified and live-wired so that when `force_llm=False` misses Tier-1 rules, `LLMClient` is invoked with OpenAI/Gemini/Claude schemas, generating valid structured tool calls (`IntentResult(action_name=..., params=...)`) rather than dropping into `generic_llm_response` or `unknown_intent`.
- **Affected Files:**
  - `jarvis/llm/router.py` (L50–L180, L980–L1200)
  - `jarvis/llm/client.py` (L40–L320)
  - `jarvis/core/app.py` (L420–L510)
  - `jarvis/core/dispatcher.py` (L80–L150)
- **Concrete Implementation Steps:**
  1. Verify `generate_tool_schema_from_dispatcher(self.dispatcher)` generates compliant OpenAI/Gemini JSON tool definitions.
  2. Connect `SecretsManager` to wire `OPENAI_API_KEY` / `GEMINI_API_KEY` dynamically into `LLMClient`.
  3. Update `LLMIntentRouter.parse_intent()` to parse LLM function calls into `IntentResult(action_name=tool_name, parameters=tool_args, source="llm")`.
  4. Implement structured diagnostic logging (`logger.info("Tier-2 LLM dispatched tool call: %s -> %s", text, intent.action_name)`).
  5. Ensure graceful fallback to Tier-3 deterministic rule matcher on timeout or HTTP 429 rate limit.
- **Test Verification Method:**
  - `pytest tests/unit/test_llm_router.py -k "test_tier2_tool_calling_mock" -q`
  - Execute `router.parse_intent("đặt hẹn họp lúc 3 giờ chiều", force_llm=False)` with valid mock/live key; assert `intent.action_name == "proactive_reminder"` or valid action (not `unknown_intent` or `generic_llm_response`).

---

#### Item P0-4: Router Tier-1 Fast-Path Coverage Expansion ($\ge 40-60$ Rules)
- **Priority:** 🔴 P0 Critical
- **Feature Name:** Router Fast-Path Rule Expansion & Non-Diacritic Vietnamese Support
- **Technical Description:**  
  Baseline evaluation on `tests/eval/routing_eval_n150.py` yields SILENT_FAILURE of 64.8% (99/152 missed). Root cause analysis reveals 52.5% caused by non-diacritic Whisper outputs (`mo chrome`, `tat may tinh`), 18.2% by English voice shortcuts (`volume up`, `shut down`), and 29.3% by missing high-frequency categories (weather, music, memory, system controls). This item adds $\ge 40-60$ new fast-path regex and static rules in `jarvis/llm/router.py`, reducing SILENT_FAILURE to $\le 40.0\%$ (target $< 15\%$) while strictly maintaining MISROUTED $= 0$.
- **Affected Files:**
  - `jarvis/llm/router.py` (L827–L980, L1200–L1650)
  - `tests/eval/routing_eval_n150.py` (L38–L280)
  - `tests/unit/test_llm_router.py`
- **Concrete Implementation Steps:**
  1. Add non-diacritic app launcher regex (`mo`, `bat`, `chay`, `khoi dong`) covering Chrome, Notepad, Word, Excel, Paint, Calculator, PowerPoint, Settings.
  2. Add non-diacritic website launcher regex (`mo youtube`, `vao facebook`, `mo trang web`).
  3. Add system power rules (`tat may tinh`, `tat nguon`, `shut down`, `stop`, `thoi`, `huy`, `cancel`, `khoi dong lai`).
  4. Add system volume/brightness rules (`tang am luong`, `giam am luong`, `tat tieng`, `mute`, `volume up/down`, `tat man hinh`, `screen off`).
  5. Add generic music playback rules (`mo nhac`, `phat nhac`, `play music`, `bat nhac len`, `spotify`).
  6. Add weather queries (`thoi tiet hom nay`, `du bao thoi tiet`, `troi hom nay`, `weather today`, `bao nhieu do`).
  7. Add news headlines, memory saving, folder search, and hardware status rules.
  8. Retain input length truncation ($\le 512$ chars) and word-boundary anchors for short tokens to prevent ReDoS.
- **Test Verification Method:**
  - `python tests/eval/routing_eval_n150.py` -> verify SILENT_FAILURE $\le 40.0\%$ (target $\le 15.0\%$) and MISROUTED $= 0$.
  - `pytest tests/unit/test_llm_router.py -q` -> 0 failures.

---

#### Item P0-5: Test Suite Integrity & Zero-Failure Baseline Maintenance
- **Priority:** 🔴 P0 Critical
- **Feature Name:** Automated Test Suite Resilience & Regression Protection
- **Technical Description:**  
  Maintain an absolute zero-failure standard across all unit and adversarial test suites (`pytest tests/ -q --ignore=tests/e2e`), eliminating deprecation warnings, resolving missing optional dependency import errors gracefully via `pytest.importorskip`, and securing CI/CD execution.
- **Affected Files:**
  - `tests/conftest.py` (L1–L1022)
  - `tests/unit/test_*.py`
  - `tests/test_adversarial_*.py`
  - `pytest.ini`
- **Concrete Implementation Steps:**
  1. Audit all 51+ test modules for unhandled `ModuleNotFoundError` on optional packages (`cv2`, `mediapipe`, `vosk`, `pvporcupine`).
  2. Wrap optional dependencies in `pytest.importorskip` or `unittest.mock`.
  3. Verify mock fixtures (`MockAudioStream`, `MockHardwareProvider`, `MockWin32Platform`, `MockHttpServer`).
  4. Run full test suite in clean virtual environment.
- **Test Verification Method:**
  - `pytest tests/unit/ -q` (0 failures).
  - `pytest tests/test_adversarial_*.py -q` (0 failures).
  - `pytest tests/ -q --ignore=tests/e2e` (0 failures).

---

### 🟠 Priority P1: High UX, Acoustic & Performance Hardening

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                 P1 HIGH BACKLOG                                   │
├───────┬───────────────────────────────────┬───────────────────────────────────────┤
│ ID    │ Feature Name                      │ Primary Affected Files                │
├───────┼───────────────────────────────────┼───────────────────────────────────────┤
│ P1-6  │ Floating HUD Overlay & Async Loop │ jarvis/ui/overlay.py, app.py          │
│ P1-7  │ System Tray Dynamic Controls      │ jarvis/ui/tray.py, app.py             │
│ P1-8  │ Acoustic Transient Filter & DSP   │ jarvis/audio/dsp.py, detector.py      │
│ P1-9  │ SAPI5 Fallback TTS & COM Safety   │ jarvis/tts/fallback.py, manager.py    │
│ P1-10 │ Faster-Whisper Preload & VAD      │ jarvis/stt/engine.py, vad.py          │
│ P1-11 │ Hardware Telemetry Watchdog       │ jarvis/hardware/monitor.py, reporter.py│
└───────┴───────────────────────────────────┴───────────────────────────────────────┘
```

#### Item P1-6: Floating HUD Overlay UI & Non-Blocking Async Voice Loop
- **Priority:** 🟠 P1 High
- **Feature Name:** Desktop Floating HUD Overlay & Voice Loop Decoupling
- **Technical Description:**  
  Decouple the Tkinter HUD overlay lifecycle from the voice loop thread. Provide smooth visual state animations (`IDLE` -> `LISTENING` [amber breathing dot] -> `THINKING` [cycling typing dots `.` `..` `...`] -> `SPEAKING` / `RESPONSE`), auto-hide countdown tooltip, and eliminate audio hardware blocking in `_ai_voice_loop`.
- **Affected Files:**
  - `jarvis/ui/overlay.py` (L1–L450)
  - `jarvis/core/app.py` (L330–L420)
  - `jarvis/audio/engine.py` (L100–L180)
- **Concrete Implementation Steps:**
  1. Ensure `JarvisOverlay` runs on a dedicated Tkinter GUI thread with thread-safe queue event dispatcher.
  2. Implement `JarvisApp.record_audio(duration_s, sample_rate)` method to allow non-blocking dummy buffers in headless/CI mode and mock injection.
  3. Route transcribed text through single authority `process_text_command(transcript, requester="voice")`.
  4. Synchronize HUD state transitions with `EventBus` events (`voice.listening`, `voice.thinking`, `voice.response`).
- **Test Verification Method:**
  - `pytest tests/test_m3_ux.py -q`
  - `pytest tests/test_adversarial_m3_ui_app.py -q`

---

#### Item P1-7: Windows System Tray Controller Dynamic Toggle & Telemetry Sync
- **Priority:** 🟠 P1 High
- **Feature Name:** System Tray Dynamic Menu & Real-Time Status Synchronization
- **Technical Description:**  
  Enhance `SystemTrayController` with dynamic context menu options (live toggle for Wake Word detection, gesture detection, and DND/silent mode) without requiring application restart, while syncing system state icon (Idle, Listening, Processing, Error).
- **Affected Files:**
  - `jarvis/ui/tray.py` (L1–L380)
  - `jarvis/core/app.py` (L200–L260)
  - `jarvis/core/events.py`
- **Concrete Implementation Steps:**
  1. Implement `_on_toggle_wakeword` and `_on_toggle_gestures` dynamic menu callbacks in `pystray.Menu`.
  2. Update tray tooltip and icon image dynamically upon receiving `EventBus` state changes (`TrayStatus.IDLE`, `LISTENING`, `PROCESSING`).
  3. Provide graceful fallback for environments lacking GUI / system tray handles (`headless` mode).
- **Test Verification Method:**
  - `pytest tests/unit/test_tray.py -q`
  - Assert programmatic toggle `tray_controller._on_toggle_wakeword()` updates `wake_word_detector.is_enabled`.

---

#### Item P1-8: Acoustic Transient Filter & DSP Dynamic Noise Floor Hardening
- **Priority:** 🟠 P1 High
- **Feature Name:** DSP Acoustic Filtering & False-Positive Suppression
- **Technical Description:**  
  Refine Exponential Moving Average (EMA) noise floor tracking (`alpha = 0.992`) and Schmitt trigger ratio in `AudioDSPProcessor` to suppress false positive claps caused by mechanical keyboard clicks, mouse clicks, and door slams, while maintaining double-clap detection sensitivity.
- **Affected Files:**
  - `jarvis/audio/dsp.py` (L1–L320)
  - `jarvis/gesture/detector.py` (L1–L410)
  - `config/default_config.yaml` (L50–L75)
- **Concrete Implementation Steps:**
  1. Introduce Spectral Flatness Measure (SFM) and Zero Crossing Rate (ZCR) filtering to discard continuous pure tones and broadband white noise from triggering clap transients.
  2. Enforce minimum energy spike threshold relative to rolling RMS baseline.
  3. Ensure configurable refractory period (cooldown 2.5s) suppresses echo loops.
- **Test Verification Method:**
  - `pytest tests/test_audio_dsp.py -q`
  - `pytest tests/test_gesture_detector.py -q`
  - Synthesize clap transient waveforms and verify discrimination against Gaussian noise bursts.

---

#### Item P1-9: SAPI5 Local TTS Fallback Thread Safety & COM Initialization
- **Priority:** 🟠 P1 High
- **Feature Name:** SAPI5 Local TTS Engine & COM Apartment Safety
- **Technical Description:**  
  Guarantee rock-solid offline speech synthesis when ElevenLabs API is unreachable, rate-limited (HTTP 429), or missing API key. Fix COM threading apartment issues (`pythoncom.CoInitialize()`) when invoking `SAPI.SpVoice` from background worker threads, and provide PowerShell Base64 fallback.
- **Affected Files:**
  - `jarvis/tts/fallback.py` (L1–L280)
  - `jarvis/tts/manager.py` (L1–L390)
  - `jarvis/tts/elevenlabs.py` (L1–L210)
- **Concrete Implementation Steps:**
  1. Wrap SAPI5 initialization in `try ... pythoncom.CoInitialize()` and `pythoncom.CoUninitialize()` in thread teardown.
  2. Provide Base64-encoded PowerShell script execution fallback for systems without `win32com`.
  3. Implement non-repeating polite welcome phrase pool in `TTSManager`.
  4. Ensure SHA-256 disk cache (`.cache/jarvis_welcome/`) avoids redundant synthesis of static phrases.
- **Test Verification Method:**
  - `pytest tests/test_tts_engine.py -q`
  - `pytest tests/unit/test_tts_cache.py -q`
  - `pytest tests/unit/test_tts_engines.py -q`

---

#### Item P1-10: Faster-Whisper Local STT Model Preloading & VAD Optimization
- **Priority:** 🟠 P1 High
- **Feature Name:** Faster-Whisper Model Preloading & VAD Optimization
- **Technical Description:**  
  Optimize local CT2 `faster-whisper` STT pipeline for sub-second transcription. Implement lazy-loading or background preloading of `small` / `base` model, integrate Silero VAD / WebRTC VAD segmenter to prune pre-speech and trailing silence, and support CPU INT8 / GPU FP16 execution.
- **Affected Files:**
  - `jarvis/stt/engine.py` (L1–L450)
  - `jarvis/audio/vad.py` (L1–L250)
  - `config/default_config.yaml` (L20–L35)
- **Concrete Implementation Steps:**
  1. Add model warming routine on startup in a background daemon thread.
  2. Implement `VADSegmenter` ring buffer to cut audio frame at silence boundary (0.8s silence window) rather than waiting for full 5.0s timeout.
  3. Auto-detect CUDA availability (`torch.cuda.is_available()`) to configure `device="cuda"`, `compute_type="float16"` or fallback to `device="cpu"`, `compute_type="int8"`.
- **Test Verification Method:**
  - `pytest tests/unit/test_stt_engine.py -q`
  - Benchmark transcription latency on 3s speech sample ($\le 800\text{ms}$ on GPU, $\le 1.8\text{s}$ on CPU).

---

#### Item P1-11: Persistent Hardware Telemetry Watchdog & S.M.A.R.T. Disk Health
- **Priority:** 🟠 P1 High
- **Feature Name:** Hardware Telemetry Watchdog & S.M.A.R.T. Reporting
- **Technical Description:**  
  Extend `HardwareMonitor` and `HardwareReporter` to query live CPU load, RAM usage, GPU telemetry, battery charge status, and disk S.M.A.R.T. health using pure ctypes Win32 API and CIM/WMI fallback (no mandatory pywin32).
- **Affected Files:**
  - `jarvis/hardware/monitor.py` (L1–L380)
  - `jarvis/hardware/reporter.py` (L1–L220)
  - `jarvis/core/app.py` (L230–L245)
- **Concrete Implementation Steps:**
  1. Implement `GlobalMemoryStatusEx` and `GetSystemTimes` ctypes calls for CPU/RAM telemetry.
  2. Implement `GetSystemPowerStatus` for battery percentage and AC power detection.
  3. Implement `format_voice_summary(lang="vi")` returning concise spoken telemetry for triple-clap and `system_status` actions.
  4. Wire `HardwareReporter` into `JarvisApp._handle_system_status()`.
- **Test Verification Method:**
  - `pytest tests/test_hardware_monitor.py -q`
  - Verify `_handle_system_status` returns live CPU % and RAM % instead of hardcoded mock string.

---

### 🟡 Priority P2: Medium Multimodal Intelligence & Integrations

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                P2 MEDIUM BACKLOG                                  │
├───────┬───────────────────────────────────┬───────────────────────────────────────┤
│ ID    │ Feature Name                      │ Primary Affected Files                │
├───────┼───────────────────────────────────┼───────────────────────────────────────┤
│ P2-12 │ Two-Layer Memory System (SQLite)  │ jarvis/memory/manager.py, session.py  │
│ P2-13 │ Screen Vision & Dialog Inspection │ jarvis/vision/screen.py, dialog.py    │
│ P2-14 │ Real-Time Web Intelligence Hub    │ jarvis/web/search.py, weather.py      │
│ P2-15 │ Browser Automation Worker         │ jarvis/browser/controller.py          │
│ P2-16 │ Telegram Communication Bot        │ jarvis/comms/telegram_bot.py          │
│ P2-17 │ Smart Home (Home Assistant) Bridge│ jarvis/iot/home_assistant.py          │
└───────┴───────────────────────────────────┴───────────────────────────────────────┘
```

#### Item P2-12: Two-Layer Stateful Memory System (Session Sliding Window & SQLite Store)
- **Priority:** 🟡 P2 Medium
- **Feature Name:** Stateful Conversational Memory & Persistent Fact Store
- **Technical Description:**  
  Implement stateful conversational memory: a 10-turn sliding FIFO buffer (`SessionContextManager`) for multi-turn dialogue, and a persistent SQLite database (`logs/memory.db` with WAL mode) for user facts, profile preferences, episodic telemetry logs, and daily activity summaries.
- **Affected Files:**
  - `jarvis/memory/manager.py` (New File, ~400 lines)
  - `jarvis/memory/session.py` (New File, ~200 lines)
  - `jarvis/memory/schema.sql` (New File, ~60 lines)
  - `jarvis/llm/router.py` (L600–L750)
  - `jarvis/core/app.py`
- **Concrete Implementation Steps:**
  1. Create database schema `logs/memory.db` with `facts`, `episodes`, and `user_habits` tables.
  2. Implement `MemoryManager` with thread-safe CRUD methods (`save_fact`, `get_fact`, `record_episode`, `summarize_day`).
  3. Implement `SessionContextManager` with 10-turn sliding window.
  4. Inject relevant facts and recent dialogue history into `build_jarvis_system_prompt()`.
  5. Register actions `memory_save_fact`, `memory_query_fact`, and `memory_summarize_daily` into `ActionDispatcher`.
- **Test Verification Method:**
  - `pytest tests/unit/test_memory_system.py -q`
  - Multi-threaded stress test (30 concurrent threads read/write without `database is locked` error).

---

#### Item P2-13: Screen Vision & Win32 Modal Dialog Visual Inspection
- **Priority:** 🟡 P2 Medium
- **Feature Name:** Screen Capture, OCR & Multimodal Vision Intelligence
- **Technical Description:**  
  Provide visual screen understanding (<100ms capture, <3.0s end-to-end inference) using `mss` / `PIL.ImageGrab`, unified Vision LLM integration (Gemini 1.5 Flash / GPT-4o Vision), dual-tier OCR, and native Win32 `#32770` error dialog detection.
- **Affected Files:**
  - `jarvis/vision/screen.py` (New File, ~300 lines)
  - `jarvis/vision/vision_client.py` (New File, ~250 lines)
  - `jarvis/vision/dialog_detector.py` (New File, ~200 lines)
  - `config/default_config.yaml`
- **Concrete Implementation Steps:**
  1. Implement `ScreenCaptureManager` capturing primary monitor or active window ROI, compressing to JPEG (quality 80, $\le 1920\times 1080$).
  2. Implement `VisionLLMClient` with Gemini `inlineData` Base64 and OpenAI `image_url` formats.
  3. Implement `Win32DialogDetector` using `EnumWindows` to detect `#32770` dialogs and extract error text.
  4. Register actions `screen_inspect`, `screen_explain_error`, `screen_summarize_doc` into `ActionDispatcher`.
  5. Provide graceful offline / missing-API-key fallback response.
- **Test Verification Method:**
  - `pytest tests/unit/test_screen_vision.py -q`
  - Assert captured screenshot payload conforms to Gemini/OpenAI vision schemas.

---

#### Item P2-14: Real-Time Web Intelligence, Search & Financial Rates Hub
- **Priority:** 🟡 P2 Medium
- **Feature Name:** Live Web Search, Weather, News & Financial Rates
- **Technical Description:**  
  Build real-time external information hub with DuckDuckGo search, OpenWeatherMap / wttr.in weather queries, XML RSS news aggregator (VnExpress, TechCrunch), live crypto/currency exchange rates (Binance, CoinGecko, USD/VND), thread-safe 10-minute TTL caching layer, and morning briefing composer.
- **Affected Files:**
  - `jarvis/web/search.py` (New File, ~220 lines)
  - `jarvis/web/weather.py` (New File, ~200 lines)
  - `jarvis/web/news.py` (New File, ~180 lines)
  - `jarvis/web/finance.py` (New File, ~220 lines)
  - `jarvis/web/cache.py` (New File, ~150 lines)
  - `config/default_config.yaml`
- **Concrete Implementation Steps:**
  1. Implement `TTLCache` (TTL = 600s, thread-safe `threading.RLock`, SHA-256 keying).
  2. Implement DuckDuckGo free search and LLM multi-source summarizer.
  3. Implement weather client with OpenWeatherMap and `wttr.in` fallback.
  4. Implement RSS feed parser using stdlib `xml.etree.ElementTree`.
  5. Implement crypto (BTC/ETH), forex (USD/VND), and stock tickers.
  6. Register actions `web_search`, `web_weather`, `web_news_briefing`, `web_crypto_rate`, `web_currency_rate`, `web_morning_briefing`.
  7. Add lightweight DNS socket probe for offline detection.
- **Test Verification Method:**
  - `pytest tests/unit/test_web_intelligence.py -q`
  - Test cache hit within 10 minutes and verify polite fallback on network timeout.

---

#### Item P2-15: Browser Automation & Web Action Dispatching
- **Priority:** 🟡 P2 Medium
- **Feature Name:** Headless Browser Automation (Playwright / Selenium)
- **Technical Description:**  
  Integrate Playwright / Selenium browser automation worker enabling JARVIS to execute complex web workflows (e.g. searching Google, navigating to specific portals, extracting tabular data, and taking web page screenshots) upon voice command.
- **Affected Files:**
  - `jarvis/browser/controller.py` (New File, ~320 lines)
  - `jarvis/browser/actions.py` (New File, ~200 lines)
  - `config/default_config.yaml`
- **Concrete Implementation Steps:**
  1. Create `BrowserController` managing headless/headful Chromium instance.
  2. Implement navigation, click, type, and screenshot primitives with safety guards.
  3. Register actions `browser_navigate`, `browser_search_and_extract`, `browser_fill_form`.
  4. Enforce strict URL domain allowlisting/sandboxing.
- **Test Verification Method:**
  - `pytest tests/unit/test_browser_automation.py -q`

---

#### Item P2-16: Telegram & External Communication Bot Integration
- **Priority:** 🟡 P2 Medium
- **Feature Name:** Telegram Bot Notification & Remote Command Channel
- **Technical Description:**  
  Connect JARVIS to Telegram Bot API enabling remote voice/text notifications (e.g., proactive hardware alerts, completed background tasks, reminder pings) and remote command execution with authorized user ID authentication.
- **Affected Files:**
  - `jarvis/comms/telegram_bot.py` (New File, ~280 lines)
  - `jarvis/comms/notifier.py` (New File, ~150 lines)
  - `config/default_config.yaml`
- **Concrete Implementation Steps:**
  1. Implement `TelegramNotifier` sending markdown messages and audio notes via HTTP REST API.
  2. Implement long-polling / webhook worker for inbound command reception.
  3. Enforce strict `allowed_user_ids` whitelist in configuration.
  4. Wire proactive engine alerts to dispatch remote Telegram pings.
- **Test Verification Method:**
  - `pytest tests/unit/test_telegram_bot.py -q` (with mocked Telegram HTTP endpoint).

---

#### Item P2-17: Smart Home & IoT Automation Bridge (Home Assistant Connector)
- **Priority:** 🟡 P2 Medium
- **Feature Name:** Home Assistant IoT Integration & Voice Device Control
- **Technical Description:**  
  Provide bidirectional integration with Home Assistant via REST API and WebSocket events, enabling control over smart lights, air conditioning, smart switches, and scene activation via Vietnamese voice commands.
- **Affected Files:**
  - `jarvis/iot/home_assistant.py` (New File, ~300 lines)
  - `jarvis/llm/router.py`
  - `config/default_config.yaml`
- **Concrete Implementation Steps:**
  1. Implement `HomeAssistantClient` querying entity states and posting service calls (`light.turn_on`, `climate.set_temperature`, `switch.toggle`).
  2. Add entity name normalization in intent router (mapping "đèn phòng khách" -> `light.living_room`).
  3. Register actions `iot_light_control`, `iot_climate_control`, `iot_switch_control`.
- **Test Verification Method:**
  - `pytest tests/unit/test_home_assistant.py -q` (using `MockHttpServer`).

---

### 🟢 Priority P3: Low Polish, Packaging & Enterprise Tooling

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                 P3 LOW BACKLOG                                    │
├───────┬───────────────────────────────────┬───────────────────────────────────────┤
│ ID    │ Feature Name                      │ Primary Affected Files                │
├───────┼───────────────────────────────────┼───────────────────────────────────────┤
│ P3-18 │ Windows One-Click Installer       │ scripts/install.ps1, build.ps1        │
│ P3-19 │ Interactive Web Dashboard         │ jarvis/web/dashboard.py, static/      │
│ P3-20 │ Automated Benchmark Harness       │ tests/eval/routing_eval_n150.py       │
│ P3-21 │ CLI Pre-Flight Diagnostics        │ jarvis/cli.py, system_diagnostic.ps1  │
│ P3-22 │ Bilingual Code-Switching Engine   │ jarvis/utils/vietnamese.py, router.py │
└───────┴───────────────────────────────────┴───────────────────────────────────────┘
```

#### Item P3-18: Windows One-Click Installer & Autostart Registry Automation
- **Priority:** 🟢 P3 Low
- **Feature Name:** Windows One-Click Installer & Registry Autostart Setup
- **Technical Description:**  
  Create an automated PowerShell installer script (`scripts/install.ps1`) and MSI/EXE build recipe (via PyInstaller / InnoSetup) that configures virtual environment, downloads offline models, and manages Windows Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` autostart.
- **Affected Files:**
  - `scripts/install.ps1`
  - `scripts/build_standalone.ps1`
  - `jarvis/cli.py` (L140–L190)
- **Concrete Implementation Steps:**
  1. Author `scripts/install.ps1` checking Python 3.10+, Visual C++ Redistributable, PortAudio, and downloading Vosk/Whisper models.
  2. Implement CLI subcommands `install-autostart`, `uninstall-autostart`, and `autostart-status` modifying Win32 registry.
  3. Create desktop and start menu shortcuts with custom JARVIS icon.
- **Test Verification Method:**
  - `pytest tests/test_cli.py -k "autostart" -q`
  - PowerShell syntax validation on `install.ps1`.

---

#### Item P3-19: Interactive Web Dashboard & Realtime Telemetry WebSocket
- **Priority:** 🟢 P3 Low
- **Feature Name:** Real-Time Web Telemetry Dashboard & Audio Visualizer
- **Technical Description:**  
  Enhance FastAPI / WebSocket dashboard server (`jarvis/web/dashboard.py`) to stream real-time audio input waveforms, CPU/RAM telemetry graphs, recent intent routing logs, and active plugin statuses to a modern HTML5/Vue web UI.
- **Affected Files:**
  - `jarvis/web/dashboard.py` (L1–L250)
  - `jarvis/web/static/index.html`
  - `jarvis/web/static/app.js`
- **Concrete Implementation Steps:**
  1. Implement WebSocket `/ws/telemetry` broadcasting 10Hz hardware metrics and audio RMS.
  2. Implement REST `/api/status`, `/api/logs`, `/api/command` endpoints.
  3. Build responsive single-page dashboard with dark Iron Man HUD theme.
- **Test Verification Method:**
  - `pytest tests/unit/test_dashboard_server.py -q`

---

#### Item P3-20: Automated Benchmark & Acoustic Evaluation Suite
- **Priority:** 🟢 P3 Low
- **Feature Name:** Continuous Benchmark Harness & Acoustic Metrics
- **Technical Description:**  
  Formulate automated benchmarking scripts to continuously measure STT transcription accuracy (Word Error Rate / Character Error Rate across clean and noisy acoustic corpora), intent routing Wilson 95% Confidence Intervals, and end-to-end pipeline latency.
- **Affected Files:**
  - `tests/eval/routing_eval_n150.py` (L1–L318)
  - `tests/eval/stt_intent_eval.py`
  - `docs/benchmark_results.md`
- **Concrete Implementation Steps:**
  1. Maintain `routing_eval_n150.py` tracking CORRECT %, SILENT %, MISROUTED % with Wilson CI calculation.
  2. Build acoustic evaluation runner iterating over `tests/eval/audio/*.wav` corpus.
  3. Automatically generate markdown benchmark summary reports in `docs/benchmark_results.md`.
- **Test Verification Method:**
  - `python tests/eval/routing_eval_n150.py --dry-run`

---

#### Item P3-21: CLI System Pre-Flight Diagnostics & Diagnostic Health Check
- **Priority:** 🟢 P3 Low
- **Feature Name:** CLI System Diagnostic Health Probes
- **Technical Description:**  
  Enhance `jarvis health` (`run_health_check` in `jarvis/cli.py`) to validate audio input/output devices, Vosk/Whisper model integrity, SQLite memory permissions, screen capture capabilities, and API key configurations with colorized console output.
- **Affected Files:**
  - `jarvis/cli.py` (L88–L137)
  - `tests/test_cli.py`
  - `scripts/system_diagnostic.ps1`
- **Concrete Implementation Steps:**
  1. Add probe routines for Wake Word detector model files, memory SQLite DB write access, Win32 display metrics, and LLM API connectivity.
  2. Return structured JSON report with `--json` flag or formatted ANSI table.
  3. Return non-zero exit code if critical prerequisites (audio input, config) fail.
- **Test Verification Method:**
  - `pytest tests/test_cli.py -k "test_run_health_check" -q`
  - `jarvis health --json` validation.

---

#### Item P3-22: Multi-Language & Code-Switching Vietnamese-English Engine
- **Priority:** 🟢 P3 Low
- **Feature Name:** Bilingual Code-Switching & Vietnamese Diacritic Normalizer
- **Technical Description:**  
  Enhance STT post-processing and intent router to seamlessly support Vietnamese-English code-switching (e.g. "open Chrome", "search Google bài hát mới", "restart máy tính", "git push origin main") and handle accented vs non-accented text seamlessly.
- **Affected Files:**
  - `jarvis/stt/engine.py`
  - `jarvis/llm/router.py`
  - `jarvis/utils/vietnamese.py` (New File, ~150 lines)
- **Concrete Implementation Steps:**
  1. Implement diacritic stripper / normalizer in `jarvis/utils/vietnamese.py` (`remove_vietnamese_accents`).
  2. Support dual-language regex evaluation for mixed tech keywords.
  3. Benchmark code-switching intent routing on bilingual corpus.
- **Test Verification Method:**
  - `pytest tests/unit/test_vietnamese_utils.py -q`
  - `pytest tests/unit/test_llm_router.py -k "code_switching" -q`

---

## 3. Part C: Phased Sprint Plan

```
Timeline Overview:
Sprint 1 (Weeks 1–2)  ──> v4.6.0: P0 Criticals, Tier-1 Expansion & 0 Test Failures
Sprint 2 (Weeks 3–6)  ──> v4.7.0: Acoustic Hardening, HUD Overlay & Sub-Second Latency
Sprint 3 (Months 2–3) ──> v4.8.0: Multimodal Memory, Screen Vision, Web & IoT Hub
Sprint 4 (Month 4+)   ──> v5.0.0: Windows Installer, Web Dashboard & Production CI/CD
```

### 🏁 Sprint 1 (Weeks 1–2 / v4.6.0): P0 Criticals & Stabilization
- **Theme:** Zero-Crash Baseline & Critical Bug Eradication
- **Duration:** 1–2 Weeks
- **Target Release:** v4.6.0
- **Scope & Backlog Items:**
  - **P0-1:** Wake word production-ready (Vosk + Faster-Whisper sliding window fallback).
  - **P0-2:** `jarvis/workers/proactive.py` implemented (`ProactiveEngine`, reminders, hardware alerts, Pomodoro).
  - **P0-3:** Tier-2 LLM routing pipeline wired with OpenAI API key and dynamic tool schemas.
  - **P0-4:** Tier-1 fast-path router rules expanded ($\ge 40-60$ rules, SILENT $\le 40\%$, MISROUTED $= 0$).
  - **P0-5:** Test suite integrity maintained (0 failures across all unit and adversarial suites).
- **Deliverables:**
  1. `docs/ROADMAP.md` (comprehensive audit, 22 backlog items, 4 sprints).
  2. `jarvis/workers/proactive.py` created and integrated with `app.py`.
  3. `jarvis/audio/wake_word.py` resilient to missing models with clean fallbacks.
  4. `jarvis/llm/router.py` expanded with 60+ new fast-path regex rules.
  5. `CHANGELOG.md` entry for v4.6.0 with updated package version in `jarvis/__init__.py`.
- **Sprint Acceptance Gate:**
  - `pytest tests/ -q --ignore=tests/e2e` passes with 0 failures.
  - `python tests/eval/routing_eval_n150.py` achieves SILENT $\le 40.0\%$ and MISROUTED $= 0$.
  - `python -c "import jarvis.core.app; import jarvis.workers.proactive"` executes without error.

---

### 🚀 Sprint 2 (Weeks 3–6 / v4.7.0): Accuracy & Acoustic UX Hardening
- **Theme:** Acoustic Robustness, UI Feedback & Latency Optimization
- **Duration:** 2–4 Weeks
- **Target Release:** v4.7.0
- **Scope & Backlog Items:**
  - **P1-6:** Floating HUD overlay Tkinter decoupling and non-blocking recording buffer in `JarvisApp`.
  - **P1-7:** Windows System Tray dynamic menu toggles for Wake Word and gestures without restart.
  - **P1-8:** DSP dynamic noise floor adaptation (EMA tracking, SFM/ZCR spectral filtering) and 2.5s cooldown.
  - **P1-9:** SAPI5 fallback TTS thread safety with `pythoncom.CoInitialize()` and PowerShell execution.
  - **P1-10:** Faster-Whisper local STT preloading, VAD segmenter, and GPU/CPU auto-tuning.
  - **P1-11:** Hardware telemetry watchdog integration for live CPU/RAM metrics on voice query.
  - Router coverage expanded to $\ge 60-70\%$ Tier-1 hit rate.
- **Deliverables:**
  1. End-to-end voice roundtrip latency $< 1.5\text{s}$ (STT + Routing + TTS).
  2. Smooth HUD breathing animations synchronized with audio pipeline states.
  3. Zero audio device lock contention between acoustic stream and recording.
- **Sprint Acceptance Gate:**
  - Live microphone wake word detection $\ge 70\%$ across 30 real acoustic trials.
  - False positive clap trigger rate $< 1$ per 2 hours of ambient office noise.
  - 100% pass on UX and UI integration test suites (`test_m3_ux.py`, `test_adversarial_m3_ui_app.py`).

---

### 🌟 Sprint 3 (Months 2–3 / v4.8.0): Multimodal Feature Completion
- **Theme:** Memory, Vision, Live Web Awareness & External Ecosystem
- **Duration:** 1–2 Months
- **Target Release:** v4.8.0
- **Scope & Backlog Items:**
  - **P2-12:** Two-layer stateful memory system (`SessionContextManager` + SQLite `logs/memory.db`).
  - **P2-13:** Screen Vision engine with `mss` capture, Gemini 1.5 Flash / GPT-4o Vision, and `#32770` dialog detection.
  - **P2-14:** Real-time Web Intelligence Hub (DuckDuckGo search, OpenWeatherMap, RSS news, crypto/forex rates, 10m TTL cache).
  - **P2-15:** Browser automation controller (Playwright / Selenium).
  - **P2-16:** Telegram bot remote notification and command channel.
  - **P2-17:** Smart Home Home Assistant IoT integration.
- **Deliverables:**
  1. `jarvis/memory/` package with SQLite WAL persistence and daily summary generation.
  2. `jarvis/vision/` package for low-latency desktop screen understanding.
  3. `jarvis/web/` intelligence hub with 10-minute caching.
  4. `jarvis/comms/` and `jarvis/iot/` connectors.
- **Sprint Acceptance Gate:**
  - All 12 new actions registered and dispatchable via `ActionDispatcher`.
  - Multi-threaded SQLite stress test passes with 0 lock errors across 30 concurrent threads.
  - All external network operations gracefully handle offline status and timeouts within 2.0s.

---

### 💎 Sprint 4 (Month 4+ / Ongoing / v5.0.0): Production Polish & Enterprise Distribution
- **Theme:** One-Click Distribution, Standalone Installer, Benchmarks & CI/CD
- **Duration:** Ongoing / Continuous
- **Target Release:** v5.0.0
- **Scope & Backlog Items:**
  - **P3-18:** Windows one-click installer (`scripts/install.ps1`) and PyInstaller standalone build recipe.
  - **P3-19:** Interactive web dashboard with real-time audio waveform and WebSocket telemetry.
  - **P3-20:** Automated continuous benchmark harness reporting to `docs/benchmark_results.md`.
  - **P3-21:** CLI system diagnostic pre-flight tool (`jarvis health --json`).
  - **P3-22:** Multi-language Vietnamese-English code-switching and diacritic normalizer.
- **Deliverables:**
  1. `scripts/install.ps1` automated setup script.
  2. Standalone Windows EXE/MSI distribution artifact.
  3. Web-based real-time dashboard.
  4. Full CI/CD test automation and release pipeline.
- **Sprint Acceptance Gate:**
  - Clean installation on fresh Windows 11 machine via `install.ps1`.
  - Autostart registry persistence verified across system reboots.
  - Zero test regressions across $> 600$ automated test cases.

---

## 4. Backlog Traceability & Cross-Reference Matrix

| Backlog ID | Requirement Source | Target Sprint | Primary Module | Verification Test |
|---|---|---|---|---|
| **P0-1** | ORIGINAL_REQUEST §R2 (P0-A) | Sprint 1 | `jarvis/audio/wake_word.py` | `pytest tests/unit/test_wake_word.py` |
| **P0-2** | ORIGINAL_REQUEST §R2 (P0-B) | Sprint 1 | `jarvis/workers/proactive.py` | `pytest tests/unit/test_proactive_engine.py` |
| **P0-3** | ORIGINAL_REQUEST §R2 (P0-C) | Sprint 1 | `jarvis/llm/router.py` | `pytest tests/unit/test_llm_router.py` |
| **P0-4** | ORIGINAL_REQUEST §R2 (P0-D) | Sprint 1 | `jarvis/llm/router.py` | `python tests/eval/routing_eval_n150.py` |
| **P0-5** | ORIGINAL_REQUEST §R3 | Sprint 1 | `tests/` | `pytest tests/ -q --ignore=tests/e2e` |
| **P1-6** | PROJECT.md Interface Contracts | Sprint 2 | `jarvis/ui/overlay.py` | `pytest tests/test_m3_ux.py` |
| **P1-7** | PROJECT.md UI Subsystem | Sprint 2 | `jarvis/ui/tray.py` | `pytest tests/unit/test_tray.py` |
| **P1-8** | AUDIT_METHODOLOGY Acoustic | Sprint 2 | `jarvis/audio/dsp.py` | `pytest tests/test_audio_dsp.py` |
| **P1-9** | AUDIT_METHODOLOGY Voice | Sprint 2 | `jarvis/tts/fallback.py` | `pytest tests/test_tts_engine.py` |
| **P1-10**| AUDIT_METHODOLOGY STT | Sprint 2 | `jarvis/stt/engine.py` | `pytest tests/unit/test_stt_engine.py` |
| **P1-11**| PROJECT.md Hardware Subsystem | Sprint 2 | `jarvis/hardware/monitor.py` | `pytest tests/test_hardware_monitor.py` |
| **P2-12**| Survey Report 2 (§Section 2) | Sprint 3 | `jarvis/memory/manager.py` | `pytest tests/unit/test_memory_system.py` |
| **P2-13**| Survey Report 2 (§Section 3) | Sprint 3 | `jarvis/vision/screen.py` | `pytest tests/unit/test_screen_vision.py` |
| **P2-14**| Survey Report 2 (§Section 4) | Sprint 3 | `jarvis/web/search.py` | `pytest tests/unit/test_web_intelligence.py`|
| **P2-15**| PROJECT.md Automation | Sprint 3 | `jarvis/browser/controller.py`| `pytest tests/unit/test_browser_automation.py`|
| **P2-16**| ORIGINAL_REQUEST Comms | Sprint 3 | `jarvis/comms/telegram_bot.py`| `pytest tests/unit/test_telegram_bot.py` |
| **P2-17**| Survey Report 1 IoT | Sprint 3 | `jarvis/iot/home_assistant.py`| `pytest tests/unit/test_home_assistant.py` |
| **P3-18**| ORIGINAL_REQUEST Installer | Sprint 4 | `scripts/install.ps1` | `pytest tests/test_cli.py` |
| **P3-19**| PROJECT.md Web Dashboard | Sprint 4 | `jarvis/web/dashboard.py` | `pytest tests/unit/test_dashboard_server.py`|
| **P3-20**| ORIGINAL_REQUEST §R3 Benchmark| Sprint 4 | `tests/eval/` | `python tests/eval/routing_eval_n150.py` |
| **P3-21**| ORIGINAL_REQUEST Diagnostic | Sprint 4 | `jarvis/cli.py` | `pytest tests/test_cli.py` |
| **P3-22**| AUDIT_METHODOLOGY Multi-Lang | Sprint 4 | `jarvis/utils/vietnamese.py` | `pytest tests/unit/test_vietnamese_utils.py`|

---
*Document formulated by Explorer M1-3 for Milestone M1 of the JARVIS Personal AI Expansion Project.*
