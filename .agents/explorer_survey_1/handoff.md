# Codebase Survey & Autonomous Superpower Upgrade Blueprint

**Date**: 2026-08-24T02:37:00Z  
**Agent**: `explorer_survey_1`  
**Target Repository**: `d:/Software GitCode/JARVIS`  
**Purpose**: Comprehensive investigation of repository structure, modules, entrypoints, health check, test infrastructure, dependencies, and integration architecture for the Autonomous Agentic Superpower Upgrade (R1–R7).

---

## 1. Observation

### 1.1 Repository Layout & File Organization
A recursive exploration of `d:/Software GitCode/JARVIS` reveals the following structure:
- **Core Package (`jarvis/`)**: Contains 20 specialized sub-packages and 92 total modules:
  1. `jarvis/audio/`: `__init__.py`, `dsp.py` (spectral/RMS filter), `engine.py` (SoundDevice stream, auto-device selection, multi-subscriber audio block dispatching), `wake_word.py` (acoustic energy filter, Vosk/Porcupine integration, cooldown/sensitivity management).
  2. `jarvis/automation/`: `__init__.py`, `control.py` (`ComputerController` with Win32/PyAutoGUI/ctypes window orchestration, mouse/keyboard/clipboard, master volume, screen brightness, bounded file search), `safety_gate.py` (`SafetyGate` 30s token expiration FSM), `shell_assistant.py` (`ShellAssistant` NL-to-shell translator, dev server auto-detector, destructive command interceptor, stdout summarizer), `vm.py` (VMware/VirtualBox), `workspace.py` (IDE workspace launcher).
  3. `jarvis/comms/`: `__init__.py`, `discord.py`, `email_imap.py`, `telegram.py` (Telegram bot command and photo receiver/sender).
  4. `jarvis/core/`: `__init__.py`, `app.py` (`JarvisApp` master lifecycle coordinator, 1345 lines), `config.py` (`ConfigManager` with YAML/JSON hot-reload watcher), `dispatcher.py` (`EventBus` pub/sub and `ActionDispatcher` with RBAC privilege gating and error isolation), `logger.py` (`setup_logging`, structured interaction logger), `models.py` (Data models: `ActionDefinition`, `ActionResult`, `RequesterContext`, `PrivilegeLevel`, `SubscriptionRecord`), `plugin.py` (`PluginRegistry` and `BasePlugin`).
  5. `jarvis/data/`: `__init__.py`, `document.py`, `stats.py`.
  6. `jarvis/gesture/`: `__init__.py`, `detector.py` (`GestureDetector` multi-clap acoustic transient analyzer), `models.py`, `patterns.py`.
  7. `jarvis/hardware/`: `__init__.py`, `monitor.py` (`HardwareMonitor` with CPU/RAM/VRAM/SMART disk probing), `reporter.py` (`HardwareReporter` vocal health summaries).
  8. `jarvis/healing/`: `__init__.py`, `terminator.py`, `watchdog.py` (Hung app terminator and RAM leak killer).
  9. `jarvis/llm/`: `__init__.py`, `client.py` (`LLMClient` multi-provider OpenAI/Gemini/Claude/Ollama), `router.py` (`LLMIntentRouter` two-tier regex/keyword fast path, dynamic tool schema generator, memory prompt injection, Vietnamese rule fallback).
  10. `jarvis/memory/`: `__init__.py`, `manager.py` (`MemoryManager` coordinating session, facts, episodes, habits), `session.py` (`SessionContextManager` 10-turn sliding FIFO queue), `sqlite_store.py` (`SQLiteMemoryStore` in `logs/memory.db` with SQLite WAL mode).
  11. `jarvis/platform/`: `__init__.py`, `autostart.py`, `windows.py` (`WindowsPlatformAPI` ctypes user32/kernel32/winreg platform wrapper).
  12. `jarvis/plugins/`: `__init__.py`, `chrome.py` (`ChromeMultiMonitorPlugin`), `cursor.py` (`CursorPlugin`), `shell.py` (`ShellPlugin`), `spotify.py` (`SpotifyPlugin`), `webhook.py` (`WebhookPlugin`).
  13. `jarvis/proactive/`: `__init__.py`, `engine.py` (`ProactiveEngine` coordinating 5 background sub-engines), `briefing_scheduler.py` (8:00 AM daily briefing), `health_monitor.py` (Hardware threshold alert watchdog), `inactivity.py` (2-hour idle greeting check-in), `pomodoro.py` (Focus mode timer), `reminders.py` (Timed reminder scheduler).
  14. `jarvis/security/`: `__init__.py`, `report.py`, `scanner.py` (Nmap network port scanner and TShark sniffer).
  15. `jarvis/smart_home/`: `__init__.py`, `home_assistant.py` (REST/WS API integration), `mqtt.py` (MQTT client).
  16. `jarvis/stt/`: `__init__.py`, `engine.py` (`STTEngine` with Whisper API, local Whisper, and Web Speech API / SAPI fallback).
  17. `jarvis/tts/`: `__init__.py`, `base.py`, `cache.py` (Local WAV disk cache), `elevenlabs.py`, `engine.py`, `fallback.py` (Windows SAPI5), `manager.py` (`TTSManager` multi-engine routing and fallback).
  18. `jarvis/ui/`: `__init__.py`, `dashboard.py` (`DashboardServer` HTTP & WebSocket real-time server), `overlay.py` (`AlwaysOnOverlay` / `JarvisOverlay` Iron Man Arc Reactor sidebar HUD with 5-turn conversation cards, quick action buttons, memory preview, 5s telemetry bar, 11-bar waveform visualizer), `tray.py` (`SystemTrayController` Windows system tray icon and status menu).
  19. `jarvis/vision/`: `__init__.py`, `biometrics.py`, `dialog_detector.py` (`ErrorDialogDetector` Win32 `#32770` modal scanner), `hands.py`, `ocr.py`, `screen.py` (`ScreenVisionManager` sub-80ms screen capture via MSS/PIL, Gemini/GPT-4o Vision analysis, error dialog explanation, document summarizer).
  20. `jarvis/web/`: `__init__.py`, `cache.py` (`TTLCache` 10-minute thread-safe cache), `finance.py` (`FinanceTracker` crypto/currency rates), `hub.py` (`WebIntelligenceHub` central coordinator), `news.py` (`NewsAggregator` RSS parser), `search.py` (`WebSearcher` DuckDuckGo search), `weather.py` (`WeatherProvider` OpenWeatherMap & wttr.in).

- **Entrypoints**:
  - `jarvis/__main__.py`: Calls `jarvis.cli.main()`.
  - `jarvis/cli.py`: Implements subcommands: `run`, `health-check` (alias `health`), `install-autostart`, `uninstall-autostart`, `autostart-status`.
  - `jarvis/core/app.py`: `JarvisApp.run()` runs the main thread loop, audio engine, tray icon, dashboard server, and proactive watchdog.

- **Configuration**:
  - `config/default_config.yaml`: 229 lines specifying `system`, `logging`, `audio`, `gesture`, `tts`, `stt`, `llm`, `ui`, `hardware`, `healing`, `security`, `vision`, `smart_home`, `comms`, `automation`, `plugins`.

### 1.2 Health Check Diagnostics (`python -m jarvis health-check`)
Direct observation of `jarvis/cli.py:88-201` shows `run_health_check(config)` verifies 11 subsystems:
1. Platform & OS (`sys.platform`, Python version, executable path)
2. Audio Subsystem (`sounddevice` input device enumeration)
3. Wake Word Engine (`WakeWordDetector` keyword='hey jarvis', sensitivity, model state)
4. Persistent Memory Subsystem (`SQLiteMemoryStore` WAL mode, facts count, episodes count)
5. Screen Vision Subsystem (`ScreenVisionManager` capture engine MSS/PIL, dialog detector `#32770`, API key / polite fallback)
6. Web Intelligence Hub (`WebIntelligenceHub` online/offline TTLCache status, weather/news/finance)
7. OS Automation & Dev Shell (`ComputerController` monitor count, `SafetyGate` 30s token FSM, `ShellAssistant`)
8. Proactive Intelligence Engine (`ProactiveEngine` 5 sub-engines: Reminders, Health Watchdog, Pomodoro, 8AM Briefing, Inactivity)
9. Always-On Overlay HUD UI (`AlwaysOnOverlay` sidebar HUD, dynamic waveform spectrum analyzer)
10. Speech & AI Services (`TTSManager` ElevenLabs/SAPI5 status, `STTEngine` Whisper/local fallback)
11. Configuration Status (`ConfigManager` root schema sections, hot-reload watcher)

### 1.3 Test Infrastructure & Test Coverage
- **Mock & Fixture Engine (`tests/conftest.py`)**: 1022 lines providing complete zero-hardware, zero-cloud headless isolation:
  - `AudioSynthesizer`: Mathematical synthesis of PCM audio (silence, Gaussian noise, clap pulses, double claps).
  - `MockAudioStream`: Replaces `sounddevice` input stream.
  - `MockHardwareProvider`: Simulates CPU, RAM, VRAM, GPU, SMART disk telemetry.
  - `MockWin32Platform`: Intercepts `user32`, `kernel32`, `winreg` ctypes calls.
  - `MockHttpServer`: Intercepts Home Assistant REST/WS, ElevenLabs TTS, Telegram bot API, LLMs (Gemini/OpenAI), MQTT.
  - `MockCameraFeed`: Synthetic frames, OpenCV VideoCapture, face recognition encodings, MediaPipe 21 hand landmarks.
- **Current Test Suites**:
  - `tests/unit/`: 20 unit test files (`test_wake_word.py`, `test_memory_system.py`, `test_screen_vision.py`, `test_web_intelligence.py`, `test_computer_control.py`, `test_shell_assistant.py`, `test_proactive_engine.py`, `test_always_on_overlay.py`, `test_llm_engine.py`, `test_stt_engine.py`, `test_tts_cache.py`, `test_tts_engines.py`, `test_ui_dashboard.py`, `test_audio_engine.py`, `test_dsp.py`, `test_gesture_detector.py`, `test_app_integration.py`, `test_plugins_m2.py`, etc.).
  - `tests/e2e/test_tiers_1_to_4.py`: 93 comprehensive E2E tests (Tier 1: 40 feature tests, Tier 2: 40 boundary/corner cases, Tier 3: 8 cross-feature integration pipelines, Tier 4: 5 realistic real-world workflow scenarios).
  - Adversarial & empirical suites: 921+ baseline tests passing.

---

## 2. Logic Chain: Analysis & Upgrade Architecture (R1–R7)

### Step 2.1: ReAct Planner & Multi-Step Task Engine (R1)
- **Current State**: `LLMIntentRouter` (`jarvis/llm/router.py`) performs 1-turn intent classification and routes to a single action. `JarvisApp.process_text_command` executes one action and returns.
- **Inference**: For complex, abstract user requests (e.g., "Kiểm tra giá BTC trên Binance, lưu vào bảng Excel và gửi báo cáo qua Telegram"), a single action dispatcher cannot handle sequential dependencies, intermediate variable passing, or dynamic self-correction.
- **Design & Integration**:
  - Create `jarvis/planner/` package:
    * `jarvis/planner/models.py`: `TaskStep`, `TaskGraph` (DAG), `StepStatus` (PENDING, RUNNING, COMPLETED, FAILED, RETRYING, SKIPPED), `ReActState` (Thought, Action, Observation, Reflection).
    * `jarvis/planner/react_engine.py`: `AutonomousReActPlanner` implementing ReAct loop with max iterations (e.g. 10), Step decomposition, LLM reflection on errors, alternative strategy synthesis, and variable store passing results between DAG nodes.
    * `jarvis/planner/safety_interceptor.py`: Integrates with `SafetyGate` (`jarvis/automation/safety_gate.py`) to classify step risk level (`READ_ONLY`, `LOW`, `MEDIUM`, `HIGH_DESTRUCTIVE`, `FINANCIAL`) and prompt for user confirmation when risk >= HIGH.
  - Wire into `jarvis/core/app.py` and register action `planner_execute_task`.

### Step 2.2: Dynamic Skill Synthesis & Sandboxed Self-Coding (R2)
- **Current State**: `jarvis/automation/shell_assistant.py` executes dev commands via `subprocess`, and `jarvis/plugins/` has static plugins. There is no isolated Python code interpreter or dynamic skill persistence.
- **Inference**: User requests requiring custom computation, data wrangling (pandas/csv/json/openpyxl), or format conversion need an on-demand code generator that runs safely in a sandbox and can package reusable tools into `jarvis/skills/`.
- **Design & Integration**:
  - Create `jarvis/sandbox/` package:
    * `jarvis/sandbox/interpreter.py`: `CodeInterpreterSandbox` executing Python / PowerShell scripts with timeout bounds, memory/process limits, output capture (stdout/stderr/generated artifacts), and restricted execution environment.
  - Create `jarvis/skills/` package & manager:
    * `jarvis/skills/manager.py`: `SkillManager` that takes successful code from the sandbox, adds standard docstring/schema metadata, generates a standalone Python module in `jarvis/skills/<skill_name>.py`, indexes it in SQLite (`logs/memory.db` table `synthesized_skills`), and dynamically registers it into `ActionDispatcher` via `plugin_registry.register_action`.
  - Register actions: `sandbox_execute_code`, `skill_synthesize`, `skill_list`, `skill_invoke`.

### Step 2.3: Full Browser Automation Agent (R3)
- **Current State**: `jarvis/web/` performs HTTP requests (DuckDuckGo, RSS, OpenWeatherMap, CoinGecko) and `jarvis/plugins/chrome.py` launches Chrome URLs via OS shell. It cannot interact with dynamic SPAs, fill complex forms, click DOM elements, or download files.
- **Inference**: Web automation requires a dedicated browser driver capable of headless/headed navigation, selector/text queries, form submission, SPA waiting, and artifact downloading.
- **Design & Integration**:
  - Create `jarvis/browser/` package:
    * `jarvis/browser/agent.py`: `BrowserAgent` utilizing Playwright / Chromium DevTools Protocol (with headless fallback mock for testing).
    * Provides: `navigate(url)`, `click(selector_or_text)`, `type_text(selector, text)`, `extract_content(selector_or_all)`, `take_page_screenshot()`, `download_file(url_or_click)`, `extract_table_data(selector)`.
    * Session management with cookie persistence and timeout resilience.
  - Register actions: `browser_navigate`, `browser_extract`, `browser_fill_form`, `browser_download`.

### Step 2.4: Computer-Use Vision & Desktop GUI Interaction (R4)
- **Current State**: `jarvis/vision/screen.py` captures screenshots (<80ms) and queries Gemini/GPT-4o for natural language description. `jarvis/automation/control.py` performs blind mouse clicks and keystrokes. They are not linked in a closed visual-feedback loop.
- **Inference**: Autonomous desktop control requires Vision AI to identify pixel coordinates/bounding boxes of buttons, inputs, and icons in any software, send accurate mouse/keyboard events, and take a follow-up screenshot to visually verify state change.
- **Design & Integration**:
  - Create `jarvis/vision/computer_use.py`:
    * `ComputerUseVision`: Implements coordinate detection from screenshot via Vision LLM (e.g. prompting Gemini/GPT-4o with bounding box format `[ymin, xmin, ymax, xmax]` or `{x, y}` normalized to screen resolution).
    * `click_ui_element(query_or_label)`: Captures screen -> locates coordinates -> dispatches `ComputerController.mouse_click(x, y)` -> waits 200ms -> captures verification screenshot -> checks UI state transition.
    * `type_into_ui_element(query_or_label, text)`: Locates element -> clicks center -> dispatches `ComputerController.type_text(text)` -> verifies typed text.
  - Register actions: `vision_click_ui`, `vision_type_ui`, `vision_verify_state`.

### Step 2.5: Autonomous Background Workers & Sub-Agent Pool (R5)
- **Current State**: `JarvisApp` runs synchronous command dispatching on worker threads (e.g. `_voice_loop`), while `ProactiveEngine` has timers. There is no multi-agent delegation pool for long-running autonomous workflows.
- **Inference**: Tasks taking tens of seconds or minutes (e.g. monitoring price spikes, crawling multiple sites, heavy batch jobs) must run in isolated background worker threads/tasks, publishing real-time telemetry to the `EventBus` without blocking voice or UI responsiveness.
- **Design & Integration**:
  - Create `jarvis/agents/` package:
    * `jarvis/agents/worker_pool.py`: `SubAgentWorkerPool` managing concurrent autonomous worker instances (`BackgroundSubAgent`).
    * Lifecycle management: `spawn_agent(task_id, goal, planner)`, `cancel_agent(task_id)`, `list_active_agents()`, `get_agent_status(task_id)`.
    * Telemetry publishing: Publishes `agent.task_started`, `agent.step_progress`, `agent.task_completed`, `agent.task_failed` to `EventBus`.
    * Notification: On completion, triggers TTS voice announcement and sends summary message (and attached files) via Telegram/Discord.
  - Register actions: `subagent_spawn`, `subagent_status`, `subagent_cancel`.

### Step 2.6: Unified Multi-Modal Integration & HUD Telemetry (R6)
- **Current State**: `AlwaysOnOverlay` in `jarvis/ui/overlay.py` displays 5-turn history cards, quick actions, 3 memory facts, 5s telemetry bar, and audio waveform.
- **Inference**: The HUD needs to render autonomous execution telemetry: real-time Task DAG cards, active step status indicators, running code output logs, and sub-agent status badges.
- **Design & Integration**:
  - Extend `AlwaysOnOverlay` (`jarvis/ui/overlay.py`):
    * Add `TaskGraphWidget` / `AgentStatusCard`: Displays current active Task DAG, highlighting current running step (animated dots / cyan glow), completed steps (green check), and failed/recovering steps (amber pulse).
    * Add code log viewer / telemetry card for sandbox code output.
    * Subscribe overlay to `EventBus` topics: `agent.step_progress`, `agent.code_executed`, `planner.reflection_triggered`.
  - Extend `SQLiteMemoryStore` (`jarvis/memory/sqlite_store.py`):
    * Add tables `autonomous_tasks` (task_id, goal, dag_json, status, created_at, finished_at) and `synthesized_skills` (name, description, code, parameters_schema, usage_count).
    * Add memory methods: `save_task_run`, `get_task_history`, `store_synthesized_skill`, `list_synthesized_skills`.

### Step 2.7: Comprehensive Regression & Integration Test Suite (R7)
- **Current State**: 921+ tests passing across `tests/unit/`, `tests/e2e/test_tiers_1_to_4.py`, `tests/test_adversarial_*.py`, `tests/test_empirical_*.py`.
- **Inference**: All 921+ baseline tests must continue to pass with 0 regressions. A new comprehensive test suite (`tests/unit/test_autonomous_agent.py`, `tests/unit/test_code_sandbox.py`, `tests/unit/test_browser_agent.py`, `tests/unit/test_computer_use_vision.py`, `tests/e2e/test_autonomous_workflows.py`) with >= 30 new tests will bring the total test suite to >= 951 tests.
- Diagnostics: Update `jarvis/cli.py:run_health_check` to verify:
  - Autonomous ReAct Planner (`AutonomousReActPlanner` READY)
  - Code Interpreter Sandbox (`CodeInterpreterSandbox` READY)
  - Persistent Skill Library (`SkillManager` READY)
  - Browser Automation Agent (`BrowserAgent` READY)
  - Computer-Use Vision Coordinator (`ComputerUseVision` READY)
  - Sub-Agent Worker Pool (`SubAgentWorkerPool` READY)

---

## 3. Caveats

1. **Hardware & Cloud Headless Testing**: All tests must use deterministic mocks (simulated browser CDP, sandbox execution limits, synthetic screenshots, virtualized mouse/keyboard events) so tests run reliably in headless CI without requiring active display servers, real physical mice/keyboards, or paid external LLM/Vision API keys.
2. **Windows Platform Compatibility**: `ComputerController` and `WindowsPlatformAPI` rely on Windows ctypes (`user32.dll`, `kernel32.dll`, `winreg`). All new modules must gracefully handle non-Windows / virtualized environments using platform checks and fallback paths.
3. **Safety Isolation**: Code execution in `CodeInterpreterSandbox` must have hard timeouts (e.g. 15s default) and process isolation (`subprocess` in isolated temp directories) to prevent runaway execution or memory exhaustion.

---

## 4. Conclusion

The JARVIS codebase is exceptionally well-structured, modular, and extensible:
1. The **`EventBus`** and **`ActionDispatcher`** in `jarvis/core/dispatcher.py` provide a clean, decoupled mechanism for registering and routing any new autonomous actions and background events.
2. The **`MemoryManager`** and **`SQLiteMemoryStore`** in `jarvis/memory/` offer a high-performance, WAL-enabled SQLite foundation ready to store task DAGs, execution episodes, and synthesized skills.
3. The **`AlwaysOnOverlay`** in `jarvis/ui/overlay.py` provides a thread-safe UI rendering engine ready to display real-time DAG telemetry and code logs.
4. The **`tests/conftest.py`** mock architecture enables 100% test isolation, allowing comprehensive new unit, integration, and E2E test suites to be written with zero hardware or live API dependencies.

---

## 5. Verification Method

To independently verify this codebase survey:
1. **Module & Directory Structure**:
   - Inspect `jarvis/`: Verify all 20 subdirectories exist (`audio`, `automation`, `comms`, `core`, `data`, `gesture`, `hardware`, `healing`, `llm`, `memory`, `platform`, `plugins`, `proactive`, `security`, `smart_home`, `stt`, `tts`, `ui`, `vision`, `web`).
2. **CLI & Health Check**:
   - Inspect `jarvis/cli.py` and `jarvis/__main__.py`: Verify `build_parser()`, `main()`, and `run_health_check(config)` function signatures and diagnostic logic.
3. **Core App & Subsystem Wiring**:
   - Inspect `jarvis/core/app.py`: Verify `JarvisApp.initialize()` (lines 151-348), `_register_core_actions()` (lines 350-513), and `process_text_command()` (lines 1102-1200).
4. **Test Suite Baseline**:
   - Inspect `tests/conftest.py`: Verify `AudioSynthesizer`, `MockAudioStream`, `MockHardwareProvider`, `MockWin32Platform`, `MockHttpServer`, and `MockCameraFeed`.
   - Inspect `tests/e2e/test_tiers_1_to_4.py`: Verify 93 E2E test cases across Tiers 1–4.
   - Inspect `tests/unit/`: Verify 20 unit test files.
