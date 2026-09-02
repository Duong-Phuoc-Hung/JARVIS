# JARVIS Codebase Survey & Roadmap Technical Audit Report

**Date**: 2026-09-02  
**Auditor**: Explorer 1 (`explorer_survey_1`)  
**Workspace**: `d:\Software GitCode\JARVIS`  
**Target Version**: v4.5.0 → v4.6.0  

---

## Executive Summary

A comprehensive, zero-assumption audit was conducted across the entire JARVIS repository (`jarvis/`, `tests/`, `docs/`, `scripts/`, `config/`, and root files). 

Key findings:
1. **Module Architecture**: 28 sub-packages and 170+ Python files are mapped. 23 sub-packages are fully implemented (`✅ Done`), while 5 sub-packages (`audio`, `browser`, `gesture`, `llm`, `vision`) operate in `🟡 Partial` status due to missing optional C/ML dependencies or incomplete rule coverage.
2. **Missing Dependencies Impact**:
   - `vosk` / `pvporcupine`: Absent. Forces `WakeWordDetector` into `AcousticSpectralDetector` (Tier 2 acoustic fallback), which is sensitive to room acoustics.
   - `cv2` / `mediapipe` / `face_recognition`: Absent. Vision biometrics and hand gesture camera tracking cleanly degrade to mock/unvailable states without crashing.
   - `playwright`: Absent. Browser agent falls back to HTTP scraper and mock driver.
   - `faster-whisper (1.2.1)`, `ctranslate2 (4.7.2)`, `elevenlabs (2.64.0)`, `psutil (6.1.1)`, `pywin32 (312)`, `keyring`, `sounddevice`, `pystray`, `keyboard`, `google-generativeai`, `openai` are **INSTALLED** and functional.
3. **Intent Routing State**:
   - Baseline measured by `tests/eval/routing_eval_n150.py`: **CORRECT: 28.8%**, **SILENT_FAILURE: 64.8%**, **MISROUTED: 0.0%**.
   - The high silent failure rate is driven by missing Tier-1 keyword patterns for common Vietnamese phrases.
4. **ProactiveEngine Status**:
   - `jarvis/proactive/engine.py` is fully implemented and tested (1,064 lines of unit tests in `tests/unit/test_proactive_engine.py` with 100% pass rate). A compatibility shim at `jarvis/workers/proactive.py` is recommended to prevent legacy import divergence.
5. **Codebase Cleanliness**:
   - Exactly 1 `# TODO` in the entire repository (in `jarvis/skills/skill_synthesizer/__init__.py:100` inside a dynamic code generation template).
   - Zero `FIXME`.
   - `NotImplementedError` is only used as a non-Windows OS guard in `jarvis/sandbox/security.py`.

---

## Part A: Codebase Inventory & Status Classification

### 1. Sub-Package & Module Status Matrix

| Sub-Package / Module | Status | Files / LOC (approx) | Core Functionality | Missing Dependencies / Degradation |
|---|:---:|---|---|---|
| **Root** (`__init__.py`, `__main__.py`, `cli.py`) | `✅ Done` | 3 files / ~600 LOC | Entrypoints, CLI arg parsing, version exposure (`v4.5.0`) | None |
| **`jarvis/agent/`** | `✅ Done` | 3 files / ~800 LOC | ReAct Autonomous Loop (`Think→Act→Observe→Reflect`), `ToolExecutionResult`, Sandbox integration | `langgraph` optional (has built-in ReAct fallback) |
| **`jarvis/audio/`** | `🟡 Partial` | 7 files / ~2,800 LOC | Full-duplex audio stream, AEC, RMS/spectral DSP, VAD, multi-tier wake word | `vosk`, `openwakeword`, `pvporcupine` missing (runs in Tier 2 Acoustic Fallback) |
| **`jarvis/automation/`** | `✅ Done` | 7 files / ~2,200 LOC | OS input simulation, GUI actor, SafetyGate approval, Shell assistant, VM manager, workspace presets | None (`CREATE_NO_WINDOW` enforced) |
| **`jarvis/browser/`** | `🟡 Partial` | 8 files / ~2,400 LOC | Multi-tier browser agent, CDP controller, session manager, price aggregator | `playwright` missing (runs in HTTP scraper / Mock driver fallback) |
| **`jarvis/comms/`** | `✅ Done` | 7 files / ~1,800 LOC | Telegram bot, IMAP 5-layer secure email, Discord bot, Zalo webhooks, rate limiting | Env tokens required for external services |
| **`jarvis/core/`** | `✅ Done` | 8 files / ~3,800 LOC | `JARVIS` app coordinator, voice interaction loop, `ActionDispatcher`, rotating logger, paths | None (Echo fix E9 & SecretsManager wired) |
| **`jarvis/data/`** | `✅ Done` | 4 files / ~900 LOC | Document parsing (PDF, DOCX, TXT, MD), dataframe statistics | None |
| **`jarvis/gesture/`** | `🟡 Partial` | 7 files / ~1,600 LOC | Acoustic clap gesture detector, geometric landmark tracking | `cv2`, `mediapipe` missing for real camera; acoustic clap is `✅ Done` |
| **`jarvis/hardware/`** | `✅ Done` | 3 files / ~1,100 LOC | Real-time CPU, RAM, GPU, Temp, Disk telemetry polling via `psutil` / WMI | None |
| **`jarvis/healing/`** | `✅ Done` | 2 files / ~800 LOC | Self-healing process restarter, RAM threshold purger, zombie thread cleaner | None |
| **`jarvis/llm/`** | `🟡 Partial` | 3 files / ~3,200 LOC | Two-tier intent router, regex engine, dynamic tool schema generator, multi-provider client | Tier-1 rule coverage is low (28.8%); Tier-2 live LLM call needs verification |
| **`jarvis/memory/`** | `✅ Done` | 2 files / ~1,400 LOC | SQLite persistent memory, daily summary, fact recall, TF-IDF vector retrieval | None |
| **`jarvis/planner/`** | `✅ Done` | 6 files / ~1,900 LOC | DAG dependency planner, execution engine, safety interceptor, reflection | None |
| **`jarvis/platform/`** | `✅ Done` | 4 files / ~1,200 LOC | Win32 API helpers, DPI awareness, autostart registry, global hotkeys | None |
| **`jarvis/plugins/`** | `✅ Done` | 7 files / ~900 LOC | Dynamic plugin loader (Spotify, Cursor, Chrome, Shell, Webhooks) | None |
| **`jarvis/proactive/`** | `✅ Done` | 7 files / ~2,100 LOC | Reminders, Pomodoro timer, hardware health alerts, daily briefing, inactivity greeting | None (fully covered by unit tests) |
| **`jarvis/sandbox/`** | `✅ Done` | 5 files / ~2,800 LOC | Windows Job Objects, AppContainer, Low Integrity Level, AST validator, artifacts | None |
| **`jarvis/security/`** | `✅ Done` | 5 files / ~1,700 LOC | Prompt injection detector, security scanner, SecretsManager (`keyring` / Windows Credential Manager) | None |
| **`jarvis/skills/`** | `✅ Done` | 25 files / ~4,500 LOC | 19 built-in skills + dynamic Self-Coding Skill Synthesizer | None |
| **`jarvis/smart_home/`** | `✅ Done` | 4 files / ~800 LOC | Home Assistant REST/WS API client, MQTT client, mDNS discovery | None |
| **`jarvis/stt/`** | `✅ Done` | 3 files / ~1,500 LOC | Local faster-whisper (CUDA/CPU), OpenAI Whisper API, Windows SAPI, VAD buffer | None (`faster-whisper` installed) |
| **`jarvis/tts/`** | `✅ Done` | 8 files / ~1,400 LOC | ElevenLabs cloud TTS, SAPI5 fallback, local disk cache, voice manager | None (`elevenlabs` installed) |
| **`jarvis/ui/`** | `✅ Done` | 4 files / ~2,400 LOC | Web dashboard (FastAPI/WS), HUD overlay (Tkinter/Win32), Pystray tray | None |
| **`jarvis/utils/`** | `✅ Done` | 2 files / ~200 LOC | `run_safe()` wrapper with `CREATE_NO_WINDOW` enforcement | None |
| **`jarvis/vision/`** | `🟡 Partial` | 8 files / ~2,500 LOC | Screen capture, Computer Use Vision, OCR, visual verification | `cv2`, `face_recognition`, `mediapipe` missing (camera biometrics degraded) |
| **`jarvis/web/`** | `✅ Done` | 7 files / ~1,900 LOC | Multi-source search, financial data, morning briefing hub, weather API | None |
| **`jarvis/workers/`** | `✅ Done` | 8 files / ~2,100 LOC | Worker pool, Night Shift scheduled maintenance, NotificationHub | None |

---

## Part B: Stubs, Placeholders, and Anti-Patterns Scan

### 1. Literal Search Results
- `TODO`: **1 occurrence**
  - `jarvis/skills/skill_synthesizer/__init__.py:100` → inside string template for newly synthesized skills: `# TODO: Implement skill logic here`.
- `FIXME`: **0 occurrences**.
- `NotImplementedError`: **2 occurrences**
  - `jarvis/sandbox/security.py:513` → Non-Windows OS guard for Low Integrity processes.
  - `jarvis/sandbox/security.py:948` → Non-Windows OS guard for AppContainer isolation.
- `pass` statements:
  - Total: ~180 occurrences across 170 files.
  - Distribution:
    - ~30 abstract method definitions (`BaseBrowserDriver`, `BaseWorker`, `BaseSTTEngine`).
    - ~110 exception handling blocks (`except Exception: pass` for optional dependency probing, socket cleanup, or window enumeration).
    - ~40 safe no-op branches (e.g. keyboard event releases, audio silence chunks).

---

## Part C: Dependency Audit & Architectural Impact

### 1. Installed Dependencies (`.venv`)
- **Audio / STT / TTS**: `sounddevice 0.5.6`, `soundfile 0.14.0`, `faster-whisper 1.2.1`, `ctranslate2 4.7.2`, `elevenlabs 2.64.0`, `numpy 2.4.6`, `scipy 1.18.1`.
- **LLM / APIs**: `google-generativeai 0.8.6`, `openai 2.38.0`, `anthropic 0.97.0`, `groq 1.4.0`, `litellm 1.88.0`.
- **Windows / OS**: `pywin32 312`, `keyring 24.3.1` (with `pywin32-ctypes`), `psutil 6.1.1`, `keyboard 0.13.5`, `pyperclip 1.11.0`, `pystray 0.19.5`.
- **UI / Web**: `PyQt6 6.11.0`, `fastapi 0.136.3`, `uvicorn 0.46.0`, `websockets 15.0.1`, `requests 2.33.1`, `beautifulsoup4 4.14.3`, `pillow 11.3.0`.
- **Testing & Dev**: `pytest 8.4.2`, `pytest-subtests 0.15.0`, `pytest-timeout 2.4.0`, `ruff 0.16.5`.

### 2. Missing Dependencies & Architectural Impact

| Dependency | Category | Impact when Missing | Fallback Mechanism in Code | Mitigation Priority |
|---|---|---|---|:---:|
| **`vosk`** | Audio / Wake Word | Cannot run offline Kaldi wake word model | Falls back to `AcousticSpectralDetector` (Tier 2 acoustic fallback) | 🔴 **P0** |
| **`pvporcupine`** | Audio / Wake Word | Porcupine Picovoice wake word unavailable | Falls back to Vosk / Acoustic detector | 🟡 **P2** |
| **`playwright`** | Browser Automation | Cannot execute headless Chromium for dynamic SPAs | Falls back to `MockBrowserDriver` and `WebScraper` (requests/BS4) | 🟠 **P1** |
| **`opencv-python` (`cv2`)** | Vision / Gestures | Cannot capture real webcam stream | Unit tests skip via `pytest.importorskip("cv2")`; landmark math runs standalone | 🟡 **P2** |
| **`mediapipe`** | Gesture Tracking | Camera hand landmark detection disabled | Geometric tracker reports `HandTrackerState.UNAVAILABLE` | 🟡 **P2** |
| **`face_recognition`** | Vision / Biometrics | Face ID user recognition disabled | Degrades gracefully; biometrics returns mock or unavailable | 🟡 **P2** |
| **`winotify`** | Notifications | Windows Action Center toast notifications disabled | Uses Pystray balloon notifications and overlay HUD | 🟠 **P1** |
| **`matplotlib`** | Data / Charts | Cannot render visual trend graphs | Generates text/ASCII tables or raw data points | 🟢 **P3** |

---

## Part D: Technical Backlog (P0 to P3) for `docs/ROADMAP.md`

### 🔴 Priority 0 (P0 Critical) — Immediate Blockers & Core Stability

#### P0-A: Wake Word Production-Ready (Vosk / Keyword Spotting)
- **Problem**: `vosk` is not installed; `WakeWordDetector` relies on `AcousticSpectralDetector` which can be unreliable across different microphone hardware and background noise profiles.
- **Affected Files**: `jarvis/audio/wake_word.py`, `pyproject.toml`, `requirements.txt`.
- **Implementation Plan**:
  1. Add `vosk` to dependencies.
  2. Implement automatic discovery for local model directory (`models/vosk-model-small-vn-0.4` or `%LOCALAPPDATA%/JARVIS/models/vosk`).
  3. Wire keyword spotting sliding-window fallback via `faster-whisper` for "jarvis" detection when Vosk model is not present.
- **Verification**: `WakeWordDetector` initializes with `WakeWordEngineType.VOSK`; tests pass with simulated and real PCM frames.

#### P0-B: Proactive Engine Backward Compatibility & App Binding
- **Problem**: `jarvis/proactive/engine.py` is implemented, but legacy references or external callers might expect `jarvis/workers/proactive.py`.
- **Affected Files**: `jarvis/workers/proactive.py` (create compatibility shim), `jarvis/core/app.py`.
- **Implementation Plan**:
  1. Create `jarvis/workers/proactive.py` that re-exports `ProactiveEngine`, `ProactiveConfig`, and models from `jarvis.proactive`.
  2. Ensure `app.py` registers `proactive_reminder`, `proactive_pomodoro_start`, `proactive_pomodoro_stop`.
  3. Verify hardware alert listener fires vocal alert when RAM > 90% or CPU > 90%.
- **Verification**: `pytest tests/unit/test_proactive_engine.py` (all tests pass), `python -c "import jarvis.workers.proactive"` succeeds.

#### P0-C: Tier-2 LLM Intent Routing Pipeline Validation
- **Problem**: 64.8% of user utterances miss Tier 1 and require Tier 2 LLM routing. The Tier 2 pipeline must be validated end-to-end with dynamic tool calling schemas.
- **Affected Files**: `jarvis/llm/router.py`, `jarvis/llm/client.py`.
- **Implementation Plan**:
  1. Verify `force_llm=False` flow: after Tier-1 miss, generate tool call schema from `ActionDispatcher` and invoke LLM.
  2. Ensure OpenAI / Gemini provider parses tool call arguments and maps them to registered actions.
  3. Add robust timeout and error handling falling back to Tier 3 without raising uncaught exceptions.
- **Verification**: `router.parse_intent("đặt hẹn họp lúc 3 giờ chiều", force_llm=False)` resolves to valid action (not `unknown_intent` or empty).

#### P0-D: Tier-1 Router Rule Coverage Expansion (SILENT <= 40%)
- **Problem**: `tests/eval/routing_eval_n150.py` reports 64.8% `SILENT_FAILURE` because Tier-1 rules lack coverage for common Vietnamese voice command variations.
- **Affected Files**: `jarvis/llm/router.py`, `tests/eval/routing_eval_n150.py`.
- **Implementation Plan**:
  1. Analyze miss patterns in the 150-utterance test corpus.
  2. Add ~50-60 new regex and dictionary rules covering:
     - Memory: `nho cho toi`, `save this`, `tom tat hom nay`, `ghi chú`.
     - App Launch: `mo ung dung chrome`, `open file explorer`, `mo calculator`, `mo powerpoint`.
     - Web/Search: `tim kiem google`, `search chrome`, `tim kiem youtube`, `tim file word`.
     - Music: `mo nhac`, `phat nhac`, `play music`, `mo spotify`.
     - Weather: `thoi tiet hom nay`, `thoi tiet ngay mai`, `bao nhieu do`.
     - System/Power: `khoi dong lai may`, `restart may tinh`, `tang do sang`, `giam do sang`.
     - Projects & Git: `tao project moi`, `liet ke project`, `git status`, `git commit`.
- **Verification**: Run `python tests/eval/routing_eval_n150.py` → `SILENT_FAILURE <= 40.0%`, `MISROUTED = 0`.

---

### 🟠 Priority 1 (P1 High) — UX & Real-World Reliability

#### P1-1: STT Acoustic Evaluation Under Ambient Noise (N=90)
- **Problem**: STT model accuracy in real room environments (echo, fan noise, low-quality mic) needs empirical calibration between `small` and `large-v3`.
- **Affected Files**: `tests/eval/stt_acoustic_eval.py`, `jarvis/stt/engine.py`.
- **Verification**: Benchmark report with latency (<1000ms) and accuracy metrics.

#### P1-2: Playwright Headless Browser Agent Integration
- **Problem**: Complex web automation (e-commerce price comparison, multi-step web scraping) requires real DOM execution.
- **Affected Files**: `jarvis/browser/driver.py`, `pyproject.toml`.
- **Verification**: `PlaywrightDriver` launches Chromium headless and executes search/extract actions.

#### P1-3: Windows Native Toast Notifications (`winotify`)
- **Problem**: HUD overlay can be intrusive during full-screen apps; native Windows toasts provide cleaner background alerts.
- **Affected Files**: `jarvis/workers/notification_hub.py`, `pyproject.toml`.
- **Verification**: Notifications appear in Windows 10/11 Action Center.

#### P1-4: SecretsManager Migration Wizard
- **Problem**: Users may have plaintext API keys in `.env`; need smooth migration into Windows Credential Manager.
- **Affected Files**: `jarvis/security/secrets.py`, `jarvis/cli.py`.
- **Verification**: CLI command `jarvis secrets migrate` securely transfers keys.

---

### 🟡 Priority 2 (P2 Medium) — High-Value Non-Blocking Features

#### P2-1: Computer Vision & MediaPipe Webcam Gesture Control
- **Problem**: Touchless gestures (wave to mute, open palm to pause) require camera tracking.
- **Affected Files**: `jarvis/gesture/hand_tracker.py`, `jarvis/vision/hands.py`.

#### P2-2: Biometric Face Authentication
- **Problem**: Automatic profile loading based on user facial recognition.
- **Affected Files**: `jarvis/vision/biometrics.py`.

#### P2-3: Smart Home Auto-Discovery via mDNS/SSDP
- **Problem**: Manual IP configuration for Home Assistant / Philips Hue.
- **Affected Files**: `jarvis/smart_home/discovery.py`.

#### P2-4: Discord Bot Full Voice Channel Bridge
- **Problem**: Voice chat integration inside Discord servers.
- **Affected Files**: `jarvis/comms/discord.py`.

---

### 🟢 Priority 3 (P3 Low) — Polish & Distribution

#### P3-1: One-Click Windows Installer Packaging
- **Problem**: Deployment requires Python/Git environment.
- **Affected Files**: `installer/`, `JARVIS.spec`.

#### P3-2: Dashboard Visual Metrics Graphs
- **Problem**: Real-time chart telemetry on the web dashboard.
- **Affected Files**: `jarvis/ui/dashboard.py`.

#### P3-3: Code Signing Workflow
- **Problem**: Windows SmartScreen warning on unverified executables.
- **Affected Files**: `scripts/sign_binary.ps1`.

---

## Part E: Diagnostic, Changelog, and Methodology Audit

### 1. `scripts/system_diagnostic.ps1`
- **Structure**: 9 comprehensive sections:
  1. Windows / Hardware (OS, CPU, RAM, Disk)
  2. GPU / CUDA (nvidia-smi, CTranslate2 CUDA device count)
  3. Python environment, version, pip, critical package list
  4. JARVIS import check, STT availability, SecretsManager presence, py_compile check
  5. Git state (branch, commit, status, remote)
  6. Environment variables presence (Process, User, Machine scopes)
  7. Error log scanner (`logs/jarvis.log`, filtering INTERACTION failed noise)
  8. Optional pytest execution
  9. Quick diagnosis (Python, Git, GPU, venv, RAM)
- **Status**: Production-ready.

### 2. `CHANGELOG.md`
- **History**: Detailed records from v4.2.0 to v4.5.0.
- **Key Milestones**:
  - v4.5.0: E9 Echo loop fix (cooldown 1.0s → 2.5s), SecretsManager wired into 6 modules, test suite stabilized to 0 failures.
  - v4.4.0: E6 subprocess `CREATE_NO_WINDOW`, E7 `parse_intent(None)` crash fix, E8 pure tone SFM rejection.
- **Next Version**: v4.6.0 (incorporating P0 roadmap fixes).

### 3. `AUDIT_METHODOLOGY.md`
- **Rules**: 7 mandatory criteria for declaring completion, 3-tier classification (Tier 1 Verified Real, Tier 2 Mock/Small N, Tier 3 Unaudited), 14 anti-pattern methodology traps.
- **Application**: All classifications in this report strictly adhere to these criteria.
