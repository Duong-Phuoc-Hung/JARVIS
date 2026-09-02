# Survey: JARVIS v4.6.0 Module Status & Dependencies Audit

**Document Version**: 1.0.0  
**Timestamp**: 2026-09-02T06:01:00Z  
**Target Milestone**: M1 (Technical Roadmap & Subsystem Audit — Part A)  
**Author**: Explorer M1-1 (`.agents/explorer_m1_1/`)  

---

## Executive Summary

A comprehensive, automated, and static/dynamic audit of the entire JARVIS repository (`d:\Software GitCode\JARVIS`) was performed across all source directories (`jarvis/`, `tests/`, `docs/`, `scripts/`, `config/`). 

### Core Statistics
- **Total Python Modules in `jarvis/`**: 170 files across 28 functional subsystems / packages.
- **Total Lines of Source Code in `jarvis/`**: ~46,800 lines of Python.
- **Module Status Classification**:
  - `✅ Done` (Fully implemented and operational): **148 files (87.1%)**
  - `🟡 Partial` (Functional but missing optional dependencies, fallback models, or extended rules): **21 files (12.4%)**
  - `❌ Missing/Stub` (Referenced file or stub needing implementation): **1 file (0.5%)** (`jarvis/workers/proactive.py` shim)
- **Test Suite Status**: 116 test files in `tests/`, 0 test failures in unit and adversarial test suites.
- **Stubs & Placeholders**: 1 TODO marker (`skills/skill_synthesizer/__init__.py:100`), 2 NotImplementedError statements (`sandbox/security.py:513,948` in abstract sandbox interface), and 4 interface base classes utilizing standard abstract `pass` definitions (`browser/driver.py`, `stt/engine.py`, `tts/base.py`, `core/plugin.py`).
- **Dependencies Audit**: 12 core libraries are installed (`psutil`, `keyring`, `elevenlabs`, `faster_whisper`, `sounddevice`, `soundfile`, `requests`, `websockets`, `urllib3`, `numpy`, `Pillow`, `PyYAML`). 11 optional libraries are missing (`vosk`, `pvporcupine`, `cv2`, `mediapipe`, `face_recognition`, `winotify`, `playwright`, `pystray`, `keyboard`, `telegram`, `scikit-learn`), with `vosk` representing the only **P0 Critical** dependency blocking production-grade offline wake word detection.

---

## 1. Complete Subsystem & Module Classification Matrix

Below is the exhaustive classification of all 28 packages and 170 modules comprising the JARVIS codebase.

| Subsystem / Package | Total Files | Total LOC | Status | Primary Functionality | Missing Deps / Stubs / Limitations |
|---------------------|-------------|-----------|--------|------------------------|-----------------------------------|
| **Root (`jarvis/`)** | 3 | 377 | `✅ Done` | Package entry point, CLI parser, REPL, versioning (`__version__ = "4.5.0"`). | None. Fully functional. |
| **`jarvis.agent`** | 3 | 600 | `✅ Done` | Multi-step agent graph orchestration (`graph.py`), tool runtime isolation (`tool_runtime.py`). | None. Zero external library blockers. |
| **`jarvis.audio`** | 7 | 2,047 | `🟡 Partial` | DSP filters (`dsp.py`), sounddevice capture (`engine.py`), full-duplex AEC (`fullduplex.py`), earcons (`sound_effects.py`), VAD (`vad.py`), multi-tier wake word (`wake_word.py`). | Missing `vosk`, `openwakeword`, `pvporcupine`. Relies on Tier-2 Acoustic spectral detector fallback. |
| **`jarvis.automation`** | 7 | 2,464 | `✅ Done` | OS automation (`control.py`), GUI actor (`gui_actor.py`), destructive command safety gate (`safety_gate.py`), shell assistant (`shell_assistant.py`), VM isolation (`vm.py`), desktop workspaces (`workspace.py`). | `keyboard`/`mouse` optional; ctypes and Win32 fallback implemented. |
| **`jarvis.browser`** | 8 | 3,264 | `🟡 Partial` | Web action execution (`actions.py`), vision browsing agent (`agent.py`), CDP WebSocket controller (`cdp_controller.py`), driver abstraction (`driver.py`), DOM models (`models.py`), scraper (`scraper.py`), cookie session manager (`session.py`). | Missing `playwright`. `cdp_controller.py` provides fallback for Chrome DevTools Protocol. |
| **`jarvis.comms`** | 7 | 1,802 | `🟡 Partial` | Discord bot (`discord.py`), IMAP/SMTP 5-layer email (`email_imap.py`), push notifications (`mobile_bridge.py`), rate limiter (`rate_limiter.py`), Telegram bot (`telegram.py`), Zalo OA (`zalo.py`). | Missing `discord.py` and `python-telegram-bot` in `.venv`. `email_imap.py` and `rate_limiter.py` fully operational. |
| **`jarvis.core`** | 8 | 4,498 | `✅ Done` | Central app orchestrator (`app.py`), configuration manager (`config.py`), ActionDispatcher & EventBus (`dispatcher.py`), logging (`logger.py`), data models (`models.py`), paths (`paths.py`), plugin manager (`plugin.py`). | None. Robust event-driven core architecture. |
| **`jarvis.data`** | 4 | 1,474 | `🟡 Partial` | Telemetry analytics service (`analysis_service.py`), document parser (`document.py`), stats aggregator (`stats.py`). | Missing `matplotlib` (falls back to ASCII text tables in `analysis_service.py`). |
| **`jarvis.gesture`** | 7 | 1,254 | `🟡 Partial` | Camera gesture detector (`detector.py`), hand landmarks (`hand_models.py`), coordinate preprocessor (`hand_preprocess.py`), MediaPipe hand tracker (`hand_tracker.py`), gesture patterns (`patterns.py`). | Missing `cv2` (OpenCV) and `mediapipe`. Video gesture tracking gracefully disabled. |
| **`jarvis.hardware`** | 3 | 934 | `✅ Done` | Real-time psutil hardware monitor (`monitor.py`), voice/HUD telemetry reporter (`reporter.py`). | None. Fully integrated with Windows psutil. |
| **`jarvis.healing`** | 3 | 618 | `✅ Done` | Rogue process terminator (`terminator.py`), health watchdog daemon (`watchdog.py`). | None. Thread-safe background monitoring. |
| **`jarvis.llm`** | 3 | 2,900 | `🟡 Partial` | Multi-provider REST client (`client.py`), two-tier intent router (`router.py`). | Tier-1 rules currently yield 64.8% silent failure rate (target <= 40%). LLM client REST engine is complete. |
| **`jarvis.memory`** | 5 | 1,680 | `🟡 Partial` | Memory manager (`manager.py`), session conversation log (`session.py`), SQLite FTS5 database (`sqlite_store.py`), vector embeddings (`vector_store.py`). | Missing `scikit-learn` (VectorStore falls back to keyword matching). SQLite FTS5 fully operational. |
| **`jarvis.planner`** | 6 | 1,780 | `✅ Done` | Dynamic DAG planner (`dag.py`), execution engine (`engine.py`), models (`models.py`), self-reflection (`reflection.py`), safety interceptor (`safety_interceptor.py`). | None. Fully functional DAG execution engine. |
| **`jarvis.platform`** | 4 | 1,281 | `🟡 Partial` | Registry autostart (`autostart.py`), global hotkeys (`hotkeys.py`), Windows OS subsystem integrations (`windows.py`). | Missing `keyboard` / `pystray`. Ctypes fallback active for Windows audio/power/display controls. |
| **`jarvis.plugins`** | 7 | 652 | `🟡 Partial` | Dynamic plugin loader (`loader.py`), integrations for Chrome (`chrome.py`), Cursor (`cursor.py`), Shell (`shell.py`), Spotify (`spotify.py`), Webhooks (`webhook.py`). | Spotify requires API client credentials. Core loader and plugins functional. |
| **`jarvis.proactive`** | 7 | 1,901 | `✅ Done` | Central ProactiveEngine daemon (`engine.py`), morning/evening briefings (`briefing_scheduler.py`), hardware health alerts (`health_monitor.py`), idle watchdog (`inactivity.py`), Pomodoro timer (`pomodoro.py`), reminder queue (`reminders.py`). | None. Subsystem is fully implemented and tested across Tiers 1–4. |
| **`jarvis.sandbox`** | 5 | 2,578 | `✅ Done` | Artifact manager (`artifacts.py`), Python interpreter (`interpreter.py`), security gatekeeper (`security.py`), forbidden API validator (`validator.py`). | None. AppContainer, Job Object, and AST sandbox isolation active. |
| **`jarvis.security`** | 5 | 1,187 | `✅ Done` | Prompt injection guard (`prompt_guard.py`), security report generator (`report.py`), vulnerability scanner (`scanner.py`), SecretsManager (`secrets.py`). | None. Windows Credential Manager / keyring wired. |
| **`jarvis.skills`** | 24 | 3,814 | `🟡 Partial` | Skills registry (`registry.py`), synthesizer (`synthesizer.py`), telemetry (`telemetry.py`), validation (`validation.py`), plus 18 built-in skill packages (`app_launcher`, `calculator`, `clipboard`, `file_manager`, `git_assistant`, `note_taker`, `pomodoro`, `rag_search`, etc.). | `synthesizer.py:100` contains TODO for dynamic AST generator. All 18 registered skill packages operational. |
| **`jarvis.smart_home`** | 4 | 609 | `🟡 Partial` | Device discovery (`discovery.py`), Home Assistant REST API (`home_assistant.py`), MQTT client (`mqtt.py`). | Missing optional `zeroconf` and `paho-mqtt`. Home Assistant REST API functional. |
| **`jarvis.stt`** | 3 | 1,202 | `✅ Done` | STT Engine abstraction & manager (`engine.py`), local Faster-Whisper CPU/CUDA transcriber (`faster_whisper.py`). | None. `faster-whisper` installed and functioning (with CTranslate2 CUDA/CPU). |
| **`jarvis.tts`** | 8 | 1,087 | `🟡 Partial` | Base TTS interface (`base.py`), disk cache (`cache.py`), ElevenLabs API (`elevenlabs.py`), playback queue (`engine.py`), SAPI5 fallback (`fallback.py`), manager cascade (`manager.py`), Piper TTS (`piper.py`). | `piper` requires external binary download. ElevenLabs and Windows native SAPI5 fallbacks fully functional. |
| **`jarvis.ui`** | 4 | 2,981 | `🟡 Partial` | Telemetry Web Dashboard (`dashboard.py`), HUD desktop overlay (`overlay.py`), System tray icon (`tray.py`). | Missing `pystray` (tray icon). HUD overlay and WebSocket telemetry dashboard fully functional. |
| **`jarvis.utils`** | 2 | 90 | `✅ Done` | Unicode-safe subprocess execution wrapper (`subprocess_utils.py`). | None. Resolves cp1252 Vietnamese encoding errors. |
| **`jarvis.vision`** | 8 | 2,570 | `🟡 Partial` | Biometrics authentication (`biometrics.py`), Claude Computer Use (`computer_use.py`), dialog detector (`dialog_detector.py`), hand tracking bridge (`hands.py`), OCR reader (`ocr.py`), screen capture (`screen.py`), visual verifier (`visual_verifier.py`). | Missing `cv2`, `mediapipe`, `face_recognition`, `pytesseract`. Screen capture (Pillow) and Claude Computer Use operational. |
| **`jarvis.web`** | 7 | 1,591 | `✅ Done` | Web cache (`cache.py`), financial tickers (`finance.py`), central web hub (`hub.py`), news RSS/REST (`news.py`), web search (`search.py`), weather API (`weather.py`). | None. Pure HTTP REST implementations using `requests`. |
| **`jarvis.workers`** | 8 | 2,007 | `🟡 Partial` | Auto-updater (`auto_updater.py`), background worker manager (`manager.py`), task models (`models.py`), Night Shift consolidation (`night_shift.py`), notification dispatcher (`notifications.py`), notification hub (`notification_hub.py`), base worker (`worker.py`). | Missing `winotify` (falls back to overlay). Missing `jarvis/workers/proactive.py` shim (proactive engine lives in `jarvis.proactive`). |

---

## 2. Inventory of Stubs, Placeholders, and Incomplete Code

Static AST analysis of the repository identified the following markers:

### A. `# TODO` / `# FIXME` Markers
| Location | Line | Code Snippet | Analysis & Required Action |
|----------|------|--------------|----------------------------|
| `jarvis/skills/synthesizer.py` | 100 | `# TODO: integrate with dynamic AST code generator` | The dynamic skill synthesizer currently uses template substitution. Integrating AST node creation is a P2 enhancement. |

### B. `NotImplementedError` Statements
| Location | Line | Code Snippet | Analysis & Required Action |
|----------|------|--------------|----------------------------|
| `jarvis/sandbox/security.py` | 513 | `raise NotImplementedError("Platform-specific JobObject enforcement not implemented on POSIX")` | Intentional OS guard: Windows Job Object resource limiting is enforced on Windows; POSIX raises not implemented. |
| `jarvis/sandbox/security.py` | 948 | `raise NotImplementedError("AppContainer isolation requires Windows 8+")` | Intentional OS guard: Windows AppContainer network isolation check. |

### C. Abstract Base Class Interface Definitions (`pass`)
| Module | Classes & Methods | Purpose |
|--------|-------------------|---------|
| `jarvis/browser/driver.py` | `BrowserDriverBase`: `launch`, `close`, `navigate`, `click`, `type_text`, `select_option`, `wait_for_selector`, `evaluate_script`, `get_html`, `get_text`, `capture_page_screenshot`, `get_cookies`, `set_cookies`, `get_current_url`, `get_title`, `find_elements`, `scroll` | Formal abstract contract implemented by Playwright and CDP driver classes. |
| `jarvis/stt/engine.py` | `STTEngineBase`: `transcribe`, `is_available`, `engine_name` | Formal abstract contract implemented by `FasterWhisperEngine`, `CloudSTTEngine`, `MockSTTEngine`. |
| `jarvis/tts/base.py` | `TTSEngineBase`: `speak`, `synthesize_to_bytes`, `is_available`, `engine_name` | Formal abstract contract implemented by `ElevenLabsTTS`, `PiperTTS`, `SAPI5FallbackTTS`. |
| `jarvis/core/plugin.py` | `PluginBase`: `_define_metadata` | Hook for plugin subclasses. |
| `jarvis/comms/zalo.py` | `ZaloClient`: `log_message` | Optional logging hook. |
| `jarvis/core/logger.py` | `LogContext`: `__exit__` | Standard context manager exit. |
| `jarvis/memory/sqlite_store.py` | `SQLiteMemoryStore`: `close` | No-op connection closure. |

### D. Missing / Relocated Modules
| Module Path | Referenced In | Actual State & Resolution |
|-------------|---------------|---------------------------|
| `jarvis/workers/proactive.py` | `ORIGINAL_REQUEST.md`, `PROJECT.md` | **Missing file in `jarvis/workers/`**. The complete proactive intelligence subsystem was implemented under `jarvis/proactive/` (`engine.py`, `reminders.py`, `health_monitor.py`, `pomodoro.py`, `briefing_scheduler.py`, `inactivity.py`). **Fix**: Add `jarvis/workers/proactive.py` as a backward-compatible shim re-exporting `ProactiveEngine`. |

---

## 3. Missing Dependencies Audit & Exact Functional Impact

### Dependency Status Summary
```
Installed in .venv (12):
  psutil (7.2.2), keyring (25.7.0), elevenlabs (2.64.0), faster_whisper (1.2.1), 
  sounddevice (0.5.6), soundfile (0.14.0), requests (2.34.2), websockets (17.0.1), 
  urllib3 (2.7.0), numpy (2.5.2), Pillow (12.3.0), PyYAML (6.0.3)

Missing in .venv (11):
  vosk, pvporcupine, cv2, mediapipe, face_recognition, winotify, 
  playwright, pystray, keyboard, python-telegram-bot, scikit-learn
```

### Detailed Impact Matrix
| Dependency | Affected Subsystems / Files | Fallback Mechanism | Impact Severity | Functional Consequences When Missing |
|------------|----------------------------|--------------------|-----------------|--------------------------------------|
| `vosk` | `jarvis/audio/wake_word.py` | `AcousticSpectralDetector` (ZCR / SFM DSP heuristics) | 🔴 **P0 Critical** | Cannot perform offline phonetic keyword matching for "Hey JARVIS" / "JARVIS". DSP fallback is vulnerable to ambient false triggers and missed wake words. |
| `pvporcupine` | `jarvis/audio/wake_word.py` | Vosk or Acoustic fallback | 🟢 **P3 Low** | Commercial alternative wake word engine; not needed if Vosk Vietnamese model is present. |
| `opencv-python` (`cv2`) | `jarvis/gesture/detector.py`, `jarvis/gesture/hand_tracker.py`, `jarvis/vision/biometrics.py` | Subsystems disabled with warning logs | 🟡 **P2 Medium** | Webcam video capture, video gesture recognition, and camera facial recognition are unavailable. Screen analysis is unaffected (uses Pillow). |
| `mediapipe` | `jarvis/gesture/hand_models.py`, `jarvis/gesture/hand_tracker.py`, `jarvis/vision/hands.py` | Gesture detection loop disabled | 🟡 **P2 Medium** | Real-time 21-point hand tracking and hand gesture controls (clap, swipe, peace sign) cannot run. |
| `face_recognition` | `jarvis/vision/biometrics.py` | Falls back to Windows PIN / password | 🟢 **P3 Low** | Automatic biometric facial recognition for user identification is disabled. |
| `winotify` | `jarvis/workers/notification_hub.py` | HUD desktop overlay & log alerts | 🟢 **P3 Low** | System notifications are displayed via the custom HUD overlay rather than Windows 10/11 native Action Center toasts. |
| `playwright` | `jarvis/browser/driver.py`, `jarvis/browser/cdp_controller.py` | Direct Chrome DevTools Protocol (CDP) WebSocket | 🟡 **P2 Medium** | Headless browser automation relies on direct CDP communication. Complex browser orchestration is constrained. |
| `pystray` | `jarvis/ui/tray.py` | Headless console mode / HUD overlay | 🟠 **P1 High** | No Windows taskbar notification area (System Tray) icon or right-click context menu. |
| `keyboard` & `mouse` | `jarvis/automation/control.py`, `jarvis/platform/hotkeys.py` | Windows ctypes `user32.dll` SendInput | 🟡 **P2 Medium** | Global hotkey hooks require active Windows message pump or ctypes polling. |
| `python-telegram-bot` & `discord.py` | `jarvis/comms/telegram.py`, `jarvis/comms/discord.py` | Remote bridge gateways disabled | 🟡 **P2 Medium** | Remote voice/text command routing via Telegram and Discord bots is inactive. |
| `scikit-learn` & `matplotlib` | `jarvis/memory/vector_store.py`, `jarvis/data/analysis_service.py` | Keyword search fallback; ASCII tables | 🟢 **P3 Low** | VectorStore relies on string token matching rather than cosine similarity; analytics generates text tables instead of graphical charts. |

---

## 4. Other Repository Directories Audit (`tests/`, `docs/`, `scripts/`, `config/`)

### `tests/` Directory
- **Files**: 116 test modules (~528 files including cache/bytecode).
- **Structure**:
  - `tests/unit/`: Subsystem unit tests covering audio, core, llm, memory, proactive, vision, web, workers.
  - `tests/eval/`: Benchmark evaluation scripts (`routing_eval_n150.py`, `stt_acoustic_eval.py`).
  - `tests/e2e/`: Opaque-box End-to-End test suite (`test_v460_e2e.py` covering Tiers 1–4).
  - `tests/test_adversarial_*.py`: Stress and security regression tests (M1–M5, Challenger suites).
- **Status**: `✅ Done`. All unit and adversarial tests pass with 0 failures (`pytest tests/unit/ -q`, `pytest tests/test_adversarial_*.py -q`).

### `docs/` Directory
- **Files**: `PROJECT_STATE.md`, `SECURITY_ARCHITECTURE.md`, `TECHNICAL_AUDIT_REPORT.md`, `benchmark_results.md`, `night_shift_audit.md`, `eval/`.
- **Status**: `🟡 Partial`. Missing `docs/ROADMAP.md` (scheduled for release in v4.6.0 via Milestone M1).

### `scripts/` Directory
- **Files**: `benchmark_hardware.py`, `benchmark_stt_cuda.py`, `build_exe.py`, `build_installer.py`, `create_shortcuts.py`, `health_check_report.py`, `system_diagnostic.ps1`.
- **Status**: `✅ Done`. All diagnostic, benchmark, and packaging scripts are fully implemented.

### `config/` Directory
- **Files**: `default_config.yaml` (582 lines).
- **Status**: `✅ Done`. Comprehensive configuration covering audio, stt, tts, llm, memory, proactive, vision, browser, comms, and security.

---

## 5. Formatted Markdown Output for `docs/ROADMAP.md` Section A

The following tables and summaries are formatted specifically for inclusion into `docs/ROADMAP.md` Part A:

```markdown
## Part A — Current Subsystem & Module Classification

### 1. Subsystem Health Matrix
| Subsystem | Modules / Files | Total LOC | Status | Stubs / Placeholders | Missing Optional Dependencies |
|---|---|---|---|---|---|
| `jarvis.core` | 8 | 4,498 | ✅ Done | 0 | None |
| `jarvis.proactive` | 7 | 1,901 | ✅ Done | 0 | None |
| `jarvis.stt` | 3 | 1,202 | ✅ Done | 0 | None (`faster-whisper` installed) |
| `jarvis.audio` | 7 | 2,047 | 🟡 Partial | 0 | `vosk`, `porcupine` (runs on Tier-2 DSP fallback) |
| `jarvis.llm` | 3 | 2,900 | 🟡 Partial | 0 | None (REST-based; Tier-1 coverage at 35.2%) |
| `jarvis.tts` | 8 | 1,087 | 🟡 Partial | 0 | `piper` (falls back to ElevenLabs / SAPI5) |
| `jarvis.memory` | 5 | 1,680 | 🟡 Partial | 0 | `scikit-learn` (falls back to SQLite FTS5) |
| `jarvis.automation` | 7 | 2,464 | ✅ Done | 0 | `keyboard`, `mouse` (ctypes fallback) |
| `jarvis.browser` | 8 | 3,264 | 🟡 Partial | 0 | `playwright` (CDP controller fallback) |
| `jarvis.vision` | 8 | 2,570 | 🟡 Partial | 0 | `cv2`, `mediapipe`, `face_recognition`, `pytesseract` |
| `jarvis.gesture` | 7 | 1,254 | 🟡 Partial | 0 | `cv2`, `mediapipe` (camera gestures disabled) |
| `jarvis.comms` | 7 | 1,802 | 🟡 Partial | 0 | `discord.py`, `python-telegram-bot` |
| `jarvis.ui` | 4 | 2,981 | 🟡 Partial | 0 | `pystray` (HUD overlay & WebSocket active) |
| `jarvis.workers` | 8 | 2,007 | 🟡 Partial | 1 (`proactive.py`) | `winotify` |
| `jarvis.skills` | 24 | 3,814 | 🟡 Partial | 1 (`synthesizer.py:100`) | None |
| `jarvis.sandbox` | 5 | 2,578 | ✅ Done | 0 | None |
| `jarvis.security` | 5 | 1,187 | ✅ Done | 0 | None |
| `jarvis.planner` | 6 | 1,780 | ✅ Done | 0 | None |
| `jarvis.agent` | 3 | 600 | ✅ Done | 0 | None |
| `jarvis.hardware` | 3 | 934 | ✅ Done | 0 | None |
| `jarvis.healing` | 3 | 618 | ✅ Done | 0 | None |
| `jarvis.web` | 7 | 1,591 | ✅ Done | 0 | None |
| `jarvis.smart_home` | 4 | 609 | 🟡 Partial | 0 | `zeroconf`, `paho-mqtt` |
| `jarvis.platform` | 4 | 1,281 | 🟡 Partial | 0 | `keyboard`, `pystray` |
| `jarvis.data` | 4 | 1,474 | 🟡 Partial | 0 | `matplotlib` |
| `jarvis.utils` | 2 | 90 | ✅ Done | 0 | None |
| `jarvis/` (root) | 3 | 377 | ✅ Done | 0 | None |

### 2. Missing Optional Dependencies & System Impact
| Dependency | Affected Modules | Fallback Strategy | Severity | Operational Impact |
|---|---|---|---|---|
| `vosk` | `jarvis.audio.wake_word` | Acoustic DSP Flatness/ZCR | 🔴 P0 Critical | Offline wake word detection vulnerable to noise & false triggers |
| `pystray` | `jarvis.ui.tray` | Headless mode / HUD overlay | 🟠 P1 High | No system tray icon in Windows taskbar |
| `playwright` | `jarvis.browser.driver` | Chrome DevTools Protocol (CDP) | 🟡 P2 Medium | Constrains complex multi-tab browser automation |
| `cv2` & `mediapipe` | `jarvis.gesture`, `jarvis.vision` | Graceful disable | 🟡 P2 Medium | Camera gestures and facial biometrics inactive |
| `telegram` & `discord` | `jarvis.comms` | Bridges disabled | 🟡 P2 Medium | Remote chat bot command routing inactive |
| `scikit-learn` | `jarvis.memory.vector_store` | SQLite FTS5 keyword match | 🟢 P3 Low | Reduced semantic ranking for memory retrieval |
| `winotify` | `jarvis.workers.notification_hub`| Desktop HUD overlay | 🟢 P3 Low | Toasts appear on HUD instead of Windows Action Center |
```
