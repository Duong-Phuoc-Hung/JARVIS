# Specification Mining Report: JARVIS System Rebuild

**Author**: Spec Miner 3 (Teamwork Specification Mining Agent)  
**Target Workspace**: d:/Software GitCode/JARVIS  
**Authoritative Source**: d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md  
**Reference Codebase**: d:/Software GitCode/JARVIS/jarvis-main/jarvis.py (1052 lines)  
**Date**: 2026-08-22  

---

## 1. Observation

### 1.1 Direct Baseline Codebase Observations (jarvis-main/jarvis.py)
- **Structure**: Single monolithic Python script of 1052 lines with mixed responsibilities (audio capture, Win32 window management, API calls, process spawning, audio caching).
- **Audio & Signal Processing**:
  - Sample rate: SAMPLE_RATE = 44100, BLOCK_MS = 40, CHANNELS = 1 (lines 60-62).
  - Detection parameters: SPIKE_RATIO = 7.0, COOLDOWN_S = 0.45, MIN_DOUBLE_GAP_S = 0.05, MAX_DOUBLE_GAP_S = 0.35, RETRIGGER_RATIO = 0.55, NOISE_FLOOR_ALPHA = 0.992, MIN_RMS = 0.012, QUIET_GATE_MULT = 2.2 (lines 64-71).
  - Device probing: _probe_input_max_rms() and _choose_input_device() scan all input devices if the default device is silent (probe rms < INPUT_SILENT_RMS = 0.001) (lines 72-75, 153-247).
- **TTS Engine**:
  - ElevenLabs integration: say_jarvis_welcome() (lines 328-381) reads ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL_ID (default: eleven_multilingual_v2), ELEVENLABS_OUTPUT_FORMAT (default: pcm_24000), ELEVENLABS_PCM_SAMPLE_RATE.
  - Local caching: _jarvis_welcome_cache_path() hashes phrase|voice_id|model_id|output_format into a SHA-256 digest (.cache/jarvis_welcome/{digest}.wav) to prevent redundant API calls (lines 278-284, 337-343).
- **Automation & Windows Integration**:
  - Spotify / Media launch via os.startfile(SONG_URI) (lines 383-394).
  - Google Chrome multi-window / multi-monitor positioning: _open_url_in_chrome(), _win32_sorted_monitor_rects(), _wait_new_chrome_hwnd_win32(), _chrome_snap_window_to_monitor_win32() supporting CLAUDE_CHROME_MONITOR = 1, BINANCE_CHROME_MONITOR = 3, --new-window, --window-position, --window-size, and F11 fullscreen (lines 396-756).
  - Cursor IDE window handling: _cursor_largest_main_hwnd_win32(), _focus_existing_cursor_window_win32(), _cursor_send_f11_fullscreen_win32(), and subprocess.Popen([exe, " -n\]) for new instances (lines 758-913).
- **Execution Lifecycle**:
 - main() runs a single-threaded blocking audio loop (sd.InputStream), launching action workflows in daemon threads (
un_double_clap_actions()) (lines 865-876, 915-1048).
 - Runs once per process (welcome_sequence_done = True) unless restarted.

### 1.2 Authoritative Request Observations (ORIGINAL_REQUEST.md)
- Defines a transformation from the single-file script into an autonomous, modular, production-ready AI desktop assistant.
- 15 Core Requirements (R1 to R15) spanning 7 core domains:
 1. *Architecture & Plugins*: R1 (Modular Package), R4 (Dynamic Plugins & Hot-reload), R6 (Logging & Autostart).
 2. *Voice, AI & Acoustic Sensing*: R2 (Voice STT + LLM + TTS), R3 (Multi-Pattern Acoustic Gestures).
 3. *UI & Diagnostics*: R5 (System Tray & Dashboard), R7 (Hardware Diagnostics & S.M.A.R.T.).
 4. *Security & Biometrics*: R8 (Security Scanning Tools Wrapper), R12 (Biometrics & Access Gate).
 5. *Computer Vision*: R13 (MediaPipe Hand Gestures & Virtual Desktop Control).
 6. *Automation & Workspaces*: R9 (Home Assistant / Smart Home), R11 (Autonomous Workspace / VM Orchestration).
 7. *Multi-channel & Healing*: R10 (Data Processing & Slide/Doc Reports), R14 (Telegram / Discord / IMAP Hub), R15 (Self-Healing Watchdog & Process Killer).

---

## 2. Logic Chain

1. **Monolith Deconstruction**: The monolithic script jarvis.py tightly couples audio signal processing, Win32 API calls, TTS playback, and workflow orchestration. Refactoring into dedicated modules (jarvis.audio, jarvis.gesture, jarvis.actions, jarvis.tts, etc.) is essential for testability, maintainability, and clean separation of concerns (R1).
2. **Backwards Compatibility Invariant**: Existing .env variables and default workflow behaviors (double-clap -> Spotify -> Claude on Monitor 1 -> Binance on Monitor 3 -> ElevenLabs TTS -> Cursor fullscreen) must remain fully functional as default out-of-the-box configuration.
3. **Extensibility via Plugin Architecture**: Implementing an open plugin architecture with JSON/YAML schema definitions (R4) decouples action execution from trigger detection, enabling acoustic gestures (R3), voice commands (R2), vision gestures (R13), remote Telegram messages (R14), and scheduled automations to trigger identical or composite action chains.
4. **Security & Privilege Stratification**: High-privilege operations such as Nmap vulnerability scans (R8), elevated shell execution, and administrative workspace tasks must be gated behind Biometric Face Authentication (R12), with a headless bypass fallback for development/non-camera setups.
5. **Observability & Diagnostics**: Moving from stdout logging to structured rotating file logs (R6), accompanied by real-time hardware diagnostics (R7), self-healing process watchdogs (R15), system tray controls, and dashboard visualizers (R5), transitions JARVIS from an experimental script into a resilient, production-grade assistant.
6. **Milestone Phasing Strategy**:
   - *Phase 1 (Foundation & Core Preservation)*: R1, R3, R4, R6.
   - *Phase 2 (Intelligence & User Interface)*: R2, R5, R7.
   - *Phase 3 (Vision, Biometrics & Security)*: R12, R13, R8.
   - *Phase 4 (Automation, IoT & Workspaces)*: R9, R11, R10.
   - *Phase 5 (Multi-Channel Comms & Autonomous Healing)*: R14, R15.
   - *Phase 6 (Hardening & 4-Tier E2E Testing)*: Comprehensive test verification.

---

## 3. Caveats

1. **Hardware & Environment Specificity**:
   - Win32 API window positioning, monitor enumeration, and virtual desktop switching (pyautogui/Win32 events) require active Windows desktop sessions.
   - Hardware diagnostics (CPU/GPU temperature, fan speeds) rely on host sensor availability (WMI, LibreHardwareMonitor, pynvml); headless or VM environments may report partial metrics.
   - Webcam presence is mandatory for live face recognition (R12) and hand gestures (R13); a software bypass mode is mandatory for CI/CD and non-camera workstations.
2. **External API Dependencies**:
   - ElevenLabs TTS, OpenAI/Gemini/Claude LLMs, Telegram Bot API, and Home Assistant REST/WebSocket require valid network connectivity and API keys. The system must support mock/offline fallback modes (e.g. pyttsx3 local TTS, mock LLM responses, local rule-based intent parsing) during automated testing.
3. **Third-Party CLI Utilities**:
   - Nmap, TShark (Wireshark), VMware (vmrun), VirtualBox (VBoxManage), and Smartctl must be pre-installed on the host for R8 and R11. JARVIS acts strictly as an orchestrator and wrapper, handling missing CLI tools gracefully with clear diagnostics.

---

## 4. Conclusion & Specification Mining Deliverables

### 4.1 Exhaustive Requirements Breakdown (R1 to R15)

#### [R1] Modular Architecture & Production Readiness
- **Core Intent**: Deconstruct monolithic jarvis.py into a robust, object-oriented, multi-package Python library with CLI entry points (python -m jarvis).
- **Detailed Sub-features**:
  - jarvis.audio: Audio stream capture (sounddevice), real-time RMS processing, noise floor adaptation, multi-device probing.
  - jarvis.gesture: Acoustic gesture detector engine with extensible pattern matching.
  - jarvis.core: Dispatcher, event bus, context manager, error handler, lifecycle controller.
  - jarvis.plugins: Base plugin interfaces, plugin registry, dynamic loader.
  - jarvis.config: Unified settings manager supporting .env, YAML, and JSON with pydantic models.
  - jarvis.tts: TTS manager supporting ElevenLabs, local caching, and offline TTS fallback (pyttsx3/SAPI5).
  - jarvis.llm: LLM client abstraction supporting OpenAI, Gemini, Claude, and local providers.
  - jarvis.vision: Face recognition (face_recognition/OpenCV) and hand tracking (mediapipe).
  - jarvis.comms: Telegram bot, Discord bot, IMAP mail processor.
  - jarvis.hardware: Hardware telemetry (CPU/GPU temps, RAM/VRAM, S.M.A.R.T. health).
  - jarvis.security: Nmap, TShark/Wireshark CLI wrappers and risk report generator.
  - jarvis.automation: Home Assistant client, VM controller (vmrun/VBoxManage), Workspace orchestrator.
  - jarvis.healing: Resource monitor, hung process detector (IsHungAppWindow), auto-terminator.
  - jarvis.data: Data analytics (pandas), Monte Carlo simulator, DOCX/PDF/PPTX export.
  - jarvis.ui: Windows System Tray (pystray) and Real-time Dashboard.
- **Acceptance Criteria**:
  - python -m jarvis starts cleanly without crashing.
  - Complete type hints on all public interfaces (mypy compliant).
  - At least 15+ automated unit tests pass.
  - Full backwards compatibility with all existing .env configuration keys.

#### [R2] Voice Command Recognition & AI Semantic Response
- **Core Intent**: Transition from trigger-only execution to natural voice interactions powered by Speech-to-Text, LLM intent extraction, and voice feedback.
- **Detailed Sub-features**:
  - Activation channels: Wake-up via acoustic gesture, wake word (" Jarvis\), or UI/hotkey.
 - Speech-To-Text (STT): Multi-backend STT (Faster-Whisper / local Whisper / cloud STT / Windows Speech API) with Voice Activity Detection (VAD).
 - Semantic Reasoning & Tool Calling: LLM agent parses natural language, decides appropriate actions, maps parameters, and synthesizes conversational responses.
 - Voice Response Synthesis: Generates dynamic ElevenLabs speech or local fallback TTS.
- **Acceptance Criteria**:
 - Acoustic gesture triggers active voice capture session.
 - Transcribed voice correctly parsed by LLM and dispatched to appropriate plugin/action.
 - Spoken response rendered via TTS within < 2.5s on cached/fast models.

#### [R3] Multi-Pattern Acoustic Gesture Detection
- **Core Intent**: Expand single double-clap detection into a multi-pattern acoustic gesture recognition engine.
- **Detailed Sub-features**:
 - Double Clap: Two transients within 0.05s - 0.35s, cooldown 0.45s.
 - Triple Clap: Three consecutive transients within calibrated windows.
 - Clap-Pause-Clap: Distinct rhythmic syncopated pattern (clap, 0.5s-1.0s silence, clap).
 - Custom Pattern Definition: JSON/YAML configurable transient sequences, timing thresholds, spike ratios, and noise floor parameters.
 - Real-time Mic Level Probing: Automatic selection of loudest operational microphone if Windows default is silent.
- **Acceptance Criteria**:
 - Support at least 3 distinct acoustic gesture patterns out of the box.
 - Each pattern independently bindable to different actions/workflows via config.
 - Accurate discrimination between patterns without cross-triggering.

#### [R4] Dynamic Plugin System & Hot-Reload Configuration
- **Core Intent**: Decouple actions into isolated plugins and provide runtime configuration hot-reloading without process restarts.
- **Detailed Sub-features**:
 - Plugin Interface: Abstract BasePlugin defining execute(context), validate(), schema(), metadata().
 - Built-in Plugins: Spotify/Media, Chrome Multi-Monitor, Cursor/IDE Focus & Fullscreen, System Command, TTS, Webhook, App Launcher.
 - Configuration Hot-Reload: File watcher (watchdog / timer polling) monitors config.yaml / actions.json and reloads plugins/bindings within 5 seconds without restarting.
 - Plugin State Management: Enable, disable, reorder, or update plugin parameters on-the-fly.
- **Acceptance Criteria**:
 - New plugins can be added by placing a Python file or configuring an action without modifying core engine code.
 - Modifying config.yaml takes effect in under 5 seconds while JARVIS is actively running.
 - Syntax errors in configuration files log warnings and retain working memory state without crashing.

#### [R5] User Interface — System Tray & Dashboard
- **Core Intent**: Provide unobtrusive Windows background execution via System Tray and rich interactive telemetry via Dashboard.
- **Detailed Sub-features**:
 - System Tray Icon (pystray / Qt):
 - Real-time status indicator (Active, Muted, Listening, Error).
 - Right-click menu: Status Overview, Mute/Unmute Mic, Toggle Hand Gestures, Open Dashboard, Settings, View Logs, Reload Config, Exit.
 - Windows Balloon / Toast Notifications for system alerts.
 - Real-Time Dashboard (Web UI / GUI):
 - Live hardware telemetry gauges (CPU, GPU, RAM, VRAM, Disk).
 - Trigger & Action Execution History log.
 - Visual Configuration Editor & Plugin Marketplace / Toggle bench.
 - Live audio mic level visualizer.
- **Acceptance Criteria**:
 - Tray icon persists in Windows taskbar; context menu actions function reliably.
 - Dashboard renders real-time status and logs without freezing the main audio loop.

#### [R6] Structured Logging, Windows Auto-Start & Utilities
- **Core Intent**: Robust operational infrastructure with structured logging, auto-start installer, and automated verification suite.
- **Detailed Sub-features**:
 - Rotating File Logging: Standardized format [Timestamp] [Level] [Module] [Gesture/Trigger] [Action] [Result].
 - Auto-Start Manager CLI:
 - CLI commands: python -m jarvis install-autostart, uninstall-autostart, autostart-status.
 - Supports Windows Registry Run key (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run) or Task Scheduler.
 - Automated Unit Testing Suite: Comprehensive test suite with >=15 unit test passes covering audio processing, config, dispatcher, plugins, and TTS caching.
- **Acceptance Criteria**:
 - Running python -m jarvis install-autostart configures startup entry verified via registry query.
 - Log rotation preserves disk space and formats logs consistently.
 - Pytest suite executes >=15 unit tests successfully.

#### [R7] Infrastructure Management & Deep Hardware Diagnostics
- **Core Intent**: Deep hardware monitoring, threshold-based voice alerting, and natural voice health reporting.
- **Detailed Sub-features**:
 - Telemetry Collection: CPU/GPU utilization, CPU/GPU temperature, fan speeds, RAM/VRAM allocation, storage partition capacities.
 - Storage Health: S.M.A.R.T. disk attribute analysis (reallocated sectors, temperature, wear-out indicator).
 - Autonomous Voice Alerting: Configurable threshold rules (e.g. CPU > 85°C, RAM > 90%) trigger synthesized voice warnings.
 - Interactive Query: Voice request \Jarvis tình trạng hệ thống?\ returns synthesized spoken summary of hardware status.
- **Acceptance Criteria**:
 - Real-time sensor polling operates with < 2% CPU overhead.
 - Exceeding configured temperature/RAM thresholds triggers vocal warning.
 - Voice query generates accurate, concise spoken status report.

#### [R8] Network Security Intelligence & Tool Orchestration
- **Core Intent**: Wrapper and orchestrator for local security tooling (Nmap, Wireshark/TShark) producing actionable risk intelligence.
- **Detailed Sub-features**:
  - Nmap Scanner Wrapper: Subnet discovery, open port scanning, service version detection, vulnerability scanning (--script vuln).
  - Packet Capture Wrapper: TShark/Wireshark capture orchestration, protocol summary, anomaly detection.
  - Security Risk Report Generator: Aggregates scan findings into Markdown/HTML/PDF vulnerability assessments.
  - Biometric Gate Integration: Enforces mandatory R12 authentication before permitting any security scan execution.
  - Voice Briefing: Speaks high-level security posture summary after scan completion.
- **Acceptance Criteria**:
  - Graceful handling when Nmap/TShark are not installed in PATH.
  - Gated by biometric authorization; unauthorized attempts trigger security alert.
  - Generates comprehensive file report and delivers spoken summary.

#### [R9] Smart Home & IoT Automation
- **Core Intent**: Voice and automated control of smart home environments via Home Assistant and MQTT protocols.
- **Detailed Sub-features**:
  - Home Assistant Integration: REST API and WebSocket clients for device state querying and service execution (light.turn_on, climate.set_temperature, switch.toggle).
  - MQTT Client: Publish/Subscribe support for custom smart home microcontrollers and IoT devices.
  - Entity Alias Mapping: YAML/JSON dictionary mapping natural language aliases (" living room light\, \đèn phòng khách\) to entity IDs (light.living_room_ceiling).
 - Voice Command Handlers: Processes lighting, temperature, and scene activations.
- **Acceptance Criteria**:
 - Executes at least 1 Home Assistant service (e.g. toggle light) via voice command.
 - Device additions and alias updates supported entirely through config file without code changes.

#### [R10] Data Processing, Statistics & Automated Simulation Reports
- **Core Intent**: Voice-driven data ingestion, statistical analysis, Monte Carlo simulation, and automated multi-format report generation.
- **Detailed Sub-features**:
 - Ingestion Engine: Parsing CSV and Excel (.xlsx) files with automatic schema/column detection.
 - Statistical & Simulation Engine: Descriptive statistics (mean, median, variance, correlations), percentile distribution, Monte Carlo probabilistic simulations.
 - Document & Slide Generation:
 - Word (.docx) structured analytical reports (python-docx).
 - Presentation slides (.pptx) with formatted summary charts and key takeaways (python-pptx, matplotlib).
 - Formatted PDF export.
 - Voice Executive Summary: Synthesizes key numerical findings into a spoken summary.
- **Acceptance Criteria**:
 - Ingests CSV file and outputs structured DOCX/PDF or PPTX presentation.
 - Speaks concise statistical summary upon generation.

#### [R11] Autonomous Workspace Automation
- **Core Intent**: One-shot orchestration of complete development environments (VMs, IDEs, Terminals, Browsers) via voice/gesture.
- **Detailed Sub-features**:
 - VM Orchestration: CLI integration with VMware Workstation (vmrun) and VirtualBox (VBoxManage) for headless/GUI VM boot and state management.
 - IDE Workspace Launcher: Spawns or focuses Cursor/VS Code on specific project directories, applying window placement and F11 fullscreen.
 - Terminal Session Setup: Spawns Windows Terminal tabs with working directories and startup scripts.
 - Workflow Engine: YAML-defined workspace recipes specifying execution sequence, delays, and voice completion report.
- **Acceptance Criteria**:
 - Voice command (\Jarvis chuẩn bị môi trường làm việc\) triggers configured VM, IDE, and terminal launch sequence.
 - Delivers voice confirmation upon workspace readiness.

#### [R12] Biometric Recognition & Role-Based Privilege Gating
- **Core Intent**: Facial biometric authentication using OpenCV + face_recognition to secure high-privilege commands and detect unauthorized users.
- **Detailed Sub-features**:
 - Owner Face Enrollment & Recognition: Extracts facial encodings and matches against live webcam feed.
 - Privilege Access Interceptor: Gates high-risk actions (R8 security scans, system admin commands, sensitive file access).
 - Intruder Detection & Auto-Lock: Automatically triggers Windows Workstation Lock (LockWorkStation), captures intruder photo, and dispatches Telegram alert upon unknown face detection.
 - Headless / No-Webcam Bypass Mode: Configurable bypass flag (BIOMETRIC_BYPASS=true or passphrase) for non-camera environments.
- **Acceptance Criteria**:
 - Correctly verifies owner face via webcam to unlock privileged features.
 - Unidentified face triggers Windows lock and dispatches Telegram photo alert.
 - Bypass mode functional when webcam is absent.

#### [R13] Computer Vision Hand Gesture Control
- **Core Intent**: Touchless OS control using MediaPipe Hands and webcam video stream.
- **Detailed Sub-features**:
 - Hand Landmark Tracking: MediaPipe Hands tracking 21 3D hand landmarks in real time.
 - Gesture Classifiers:
 - Swipe Left / Swipe Right: Triggers Windows Virtual Desktop switch (Win+Ctrl+Left/Right).
 - Fist Clench: Closes active window (Alt+F4 or WM_CLOSE).
 - Custom Hand Poses (Open Palm, Peace Sign, Thumbs Up) mapped to custom actions via config.
 - UI Toggle: Quick enable/disable via System Tray to prevent accidental triggers and conserve CPU/GPU.
- **Acceptance Criteria**:
 - Detects at least 2 distinct hand gestures and executes corresponding OS actions.
 - Hand tracking toggleable instantly via System Tray menu.

#### [R14] Multi-Channel Communication Hub
- **Core Intent**: Unified messaging integration connecting Telegram Bot, Discord Bot, and IMAP Email for alerts, summaries, and remote control.
- **Detailed Sub-features**:
 - Telegram Bot: Two-way control with User ID whitelist authentication; executes remote commands, forwards alerts, and sends intruder snapshots.
 - Discord Bot: Monitors specified channels and provides AI summaries of long discussions.
 - IMAP Email Interceptor: Background email polling, filters priority senders/unread emails, extracts text, generates AI summaries, and reads them aloud via TTS.
- **Acceptance Criteria**:
 - Telegram bot executes commands only from whitelisted user IDs.
 - JARVIS reads aloud email summaries when requested by voice or notification trigger.

#### [R15] Self-Healing Protocol & System Resource Watchdog
- **Core Intent**: Proactive system stability watchdog that detects frozen apps and extreme memory pressure, executing automated remediation and voice reporting.
- **Detailed Sub-features**:
 - Memory Watchdog: Continuously monitors RAM usage; triggers healing when RAM exceeds configurable threshold (e.g. 90%).
 - Unresponsive App Detector: Probes Windows top-level windows using Win32 IsHungAppWindow() API to detect frozen processes (Chrome, VMware, IDEs).
 - Remediation Action: Terminates offending hung/memory-hog processes cleanly or forcefully with OS critical process whitelisting.
 - Spoken Healing Report: Announces action taken and updated resource metrics (\Hệ thống bị quá tải. Đã xử lý: [tên tiến trình]. RAM hiện tại: X%\).
 - Mode Switching: Supports Autonomous Mode (auto-kill) and Advisory Mode (voice warning only).
- **Acceptance Criteria**:
 - Detects hung Windows application and terminates process according to configured policy.
 - Synthesizes and plays voice healing report upon completion.

---

### 4.2 Comprehensive Feature Inventory

| Feature ID | Feature Name | Description | Source Req | Category | Verification Channel | Minimum Acceptance Threshold |
|---|---|---|---|---|---|---|
| **F-01** | Modular Package Structure | Package refactoring with python -m jarvis entry point & public API type hints | R1 | Core Architecture | Pytest / CLI invocation | Clean boot, 0 import errors, full type coverage |
| **F-02** | Monolith Legacy Compatibility | Backwards compatibility with .env variables and legacy double-clap actions | R1, R3 | Core Architecture | E2E Regression Test | 100% legacy env variables respected, default actions work |
| **F-03** | Acoustic Signal Processor | RMS audio calculation, noise floor adaptation, spike ratio detection | R1, R3 | Audio Engine | Unit Test / Synthetic Audio | Accurate transient detection across variable noise floors |
| **F-04** | Microphone Auto-Probe | Scans and selects loudest working microphone if default is silent | R1, R3 | Audio Engine | Unit Test / Device Mock | Auto-selects active input device without crashing |
| **F-05** | Double Clap Detection | Detects 2 transients in 0.05-0.35s with 0.45s cooldown | R3 | Acoustic Gestures | Synthetic Audio / Mic Test | >=95% detection on valid claps; <=1% false positives |
| **F-06** | Triple Clap Detection | Detects 3 consecutive claps within timing thresholds | R3 | Acoustic Gestures | Synthetic Audio / Mic Test | Accurate pattern recognition without double-clap collision |
| **F-07** | Clap-Pause-Clap Detection | Detects syncopated rhythm pattern (clap-pause-clap) | R3 | Acoustic Gestures | Synthetic Audio / Mic Test | Distinguishes pause timing from continuous claps |
| **F-08** | Dynamic Action Dispatcher | Central event bus routing triggers to synchronous/asynchronous plugins | R1, R4 | Core Engine | Pytest / Event Bus Mock | Reliable trigger-to-action routing with error isolation |
| **F-09** | Base Plugin Architecture | Standardized plugin interface (execute, validate, schema, metadata) | R4 | Plugin System | Unit Test / Mock Plugin | Plugins load dynamically from directory/config |
| **F-10** | Config Hot-Reload Watcher | File watcher reloads YAML/JSON configs within 5s without restart | R4 | Configuration | File Modification Test | Config change effective within <= 5s, invalid syntax ignored |
| **F-11** | ElevenLabs TTS Engine | High-fidelity TTS generation via ElevenLabs API | R1, R2 | TTS & Speech | Integration Test / Mock API | Plays audio stream with configured voice & model |
| **F-12** | Local TTS Audio Cache | SHA-256 caching of generated TTS WAV files under .cache/ | R1, R2 | TTS & Speech | Unit Test / Cache Inspection | Zero redundant API calls for matching phrase/voice keys |
| **F-13** | Offline Fallback TTS | Local SAPI5 / pyttsx3 speech synthesis when offline or API unavailable | R2 | TTS & Speech | Integration Test / Offline Mock | Speaks fallback audio when ElevenLabs is unreachable |
| **F-14** | Speech-to-Text (STT) Engine | Local/Cloud STT converting microphone audio to text after trigger | R2 | Voice & AI | Audio Stream Test | Accurate text transcription of voice commands |
| **F-15** | LLM Semantic Intent Engine | Multi-provider LLM client (OpenAI, Gemini, Claude) with tool-calling | R2 | Voice & AI | Mock LLM / API Test | Parses user prompt into structured action parameters |
| **F-16** | System Tray Controller | Windows taskbar icon with status indicators and context menu | R5 | User Interface | GUI Interaction Test | Context menu responds: Mute, Dashboard, Config, Quit |
| **F-17** | Real-Time Dashboard | Web/GUI dashboard showing real-time metrics, logs, and config editor | R5 | User Interface | Browser / GUI Test | Renders live CPU/RAM/VRAM and event history without lag |
| **F-18** | Structured File Logging | Rotating log handler recording timestamped trigger and execution results | R6 | System Utilities | Log File Verification | Writes formatted logs to logs/jarvis.log with auto-rotation |
| **F-19** | Windows Auto-Start Installer | Single CLI command configuring Windows Registry / Task Scheduler | R6 | System Utilities | Windows Registry Query | Registry Run key or Task created/removed via CLI |
| **F-20** | Hardware Telemetry Collector | Gathers CPU, GPU, RAM, VRAM metrics and temperatures via WMI/psutil | R7 | Hardware & Infra | Sensor Reading Test | Polls sensor metrics with < 2% CPU overhead |
| **F-21** | S.M.A.R.T. Disk Health Prober | Analyzes hard drive health attributes and remaining free space | R7 | Hardware & Infra | Diagnostic Test | Extracts S.M.A.R.T. health data and disk partition stats |
| **F-22** | Hardware Voice Alerts & Query | Vocal alert when thresholds breached; answers " tình trạng hệ thống?\ | R7 | Hardware & Infra | Integration Test / Voice Mock | Vocalizes warnings and responds to voice status query |
| **F-23** | Network Scanner Wrapper (Nmap) | CLI wrapper executing subnet discovery and vulnerability audits | R8 | Security & Intel | CLI Wrapper Test | Runs Nmap, parses scan XML/JSON into structured data |
| **F-24** | Packet Capture Wrapper (TShark) | CLI wrapper executing live packet capture and anomaly analysis | R8 | Security & Intel | CLI Wrapper Test | Captures packets and extracts protocol distribution |
| **F-25** | Security Risk Report Generator | Compiles scan results into Markdown/PDF report + voice summary | R8 | Security & Intel | Output Inspection | Generates formatted report file and speaks brief summary |
| **F-26** | Home Assistant REST/WS Client | Integrates with HA API for device state queries and service calls | R9 | Smart Home & IoT | API Mock / Live HA Test | Toggles smart device state via voice or automation |
| **F-27** | MQTT Protocol Adapter | Publishes and subscribes to MQTT topics for IoT actuators/sensors | R9 | Smart Home & IoT | MQTT Broker Test | Publishes command payload to configured MQTT broker |
| **F-28** | Data Ingestion & Stats Engine | Ingests CSV/XLSX, computes descriptive statistics and distributions | R10 | Data & Analytics | Unit Test / Pandas Test | Accurately processes datasets and computes metrics |
| **F-29** | Monte Carlo Simulation Module | Runs probabilistic simulations over parameterized data models | R10 | Data & Analytics | Math/Stats Verification | Executes N iterations and computes confidence intervals |
| **F-30** | Multi-Format Document Exporter | Generates formatted DOCX, PDF reports and PPTX presentation slides | R10 | Data & Analytics | File Generation Test | Creates valid DOCX, PDF, and PPTX files with charts |
| **F-31** | Workspace VM Orchestrator | CLI wrapper for VMware (vmrun) and VirtualBox (VBoxManage) | R11 | Workspace Auto | VM Command Mock | Boots/suspends configured virtual machines |
| **F-32** | IDE & Terminal Workspace Prep | Spawns/focuses Cursor/VS Code on path + Windows Terminal instances | R11 | Workspace Auto | Win32 Window Test | Focuses/launches IDE + Terminal on target directories |
| **F-33** | Face Enrollment & Verification | Enrolls owner face encodings and matches live webcam frames | R12 | Biometrics | OpenCV / Video Mock | Accurately verifies enrolled owner vs stranger |
| **F-34** | Biometric Privilege Gate | Intercepts high-privilege actions until biometrically authorized | R12 | Biometrics | Security Gate Test | Blocks R8/admin actions when unauthenticated |
| **F-35** | Intruder Detection & Auto-Lock | Locks Windows workstation, snaps photo, and alerts via Telegram | R12 | Biometrics | Security Event Test | Calls LockWorkStation() and sends alert on stranger |
| **F-36** | MediaPipe Hand Gesture Tracker | 21-landmark 3D hand tracking for touchless gesture classification | R13 | Computer Vision | Video Stream Test | Tracks hand landmarks at >= 15 FPS with low jitter |
| **F-37** | Virtual Desktop & Window Gestures | Swipe left/right switches virtual desktops; fist clenches closes window | R13 | Computer Vision | Win32 Key Event Test | Sends correct hotkeys on recognized hand gestures |
| **F-38** | Telegram Bot Remote Controller | Two-way Telegram bot with whitelist user ID security filtering | R14 | Multi-Channel Hub | Telegram API Mock | Executes commands only from authorized user IDs |
| **F-39** | IMAP Email Reader & Summarizer | Polls IMAP mailboxes, summarizes priority unread emails via LLM | R14 | Multi-Channel Hub | IMAP Mock / Mail Test | Fetches unread emails, summarizes, and reads via TTS |
| **F-40** | Discord Bot Integration | Discord bot monitoring channels and generating topic summaries | R14 | Multi-Channel Hub | Discord API Mock | Summarizes channel messages using LLM |
| **F-41** | Process & Resource Watchdog | Polling watchdog monitoring RAM pressure and CPU saturation | R15 | Self-Healing | System Resource Test | Detects RAM > 90% and excessive memory consumption |
| **F-42** | Unresponsive App Detector | Win32 IsHungAppWindow() probe identifying frozen desktop apps | R15 | Self-Healing | Hung Window Mock | Correctly flags hung GUI applications |
| **F-43** | Autonomous Healing Protocol | Terminates hung processes, reclaims memory, speaks status report | R15 | Self-Healing | Process Kill Test | Kills non-critical hung process and announces via TTS |

---

### 4.3 Proposed Milestone Architecture & Module Decomposition

`
================================================================================
                    PROPOSED MILESTONE ROADMAP (M1 - M6)
================================================================================
`
+-----------------------------------------------------------------------------+
| MILESTONE 1: Foundation & Legacy Preservation                                |
| Modules: jarvis.audio, jarvis.gesture, jarvis.core, jarvis.tts,              |
|          jarvis.config, jarvis.plugins                                      |
| Requirements: R1, R3, R4, R6 (Partial)                                      |
| Deliverables: Modular architecture, multi-pattern acoustic gestures,         |
|               plugin system with hot-reload, legacy .env parity, 15+ tests  |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| MILESTONE 2: Conversational Intelligence & System UI                         |
| Modules: jarvis.llm, jarvis.stt, jarvis.ui (Tray & Dashboard),             |
|          jarvis.hardware                                                    |
| Requirements: R2, R5, R6 (Full), R7                                         |
| Deliverables: STT + Multi-LLM provider integration, System Tray + Web/GUI   |
|               Dashboard, Auto-start CLI installer, Hardware diagnostics     |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| MILESTONE 3: Vision, Biometrics & Security Intelligence                      |
| Modules: jarvis.vision, jarvis.biometrics, jarvis.security                  |
| Requirements: R8, R12, R13                                                  |
| Deliverables: MediaPipe Hand tracking for Virtual Desktops, OpenCV Face     |
|               Biometrics & Intruder Lock, Nmap & TShark wrappers with gating|
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| MILESTONE 4: Autonomous Automation, IoT & Analytics                          |
| Modules: jarvis.automation (HA, VM, Workspace), jarvis.data                 |
| Requirements: R9, R10, R11                                                  |
| Deliverables: Home Assistant & MQTT clients, Workspace & VM orchestrator,   |
|               Pandas analytics, Monte Carlo simulation & DOCX/PPTX generator |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| MILESTONE 5: Multi-Channel Comms Hub & Self-Healing Engine                   |
| Modules: jarvis.comms (Telegram, Discord, IMAP), jarvis.healing             |
| Requirements: R14, R15                                                      |
| Deliverables: Telegram Bot (whitelist remote control), IMAP Email summarizer,|
|               Discord listener, IsHungAppWindow detector & auto-killer       |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| MILESTONE 6: System Hardening & 4-Tier E2E Verification                     |
| Focus: Full integration, performance profiling, complete E2E test matrix    |
| Requirements: All Acceptance Criteria (Core, Voice, Config, Hardware, etc.) |
| Deliverables: Production package distribution, Tier 1-4 automated test suite |
+-----------------------------------------------------------------------------+
`

---

### 4.4 Four-Tier End-to-End Testing Framework

`
================================================================================
                    4-TIER E2E TESTING FRAMEWORK SPECIFICATION
================================================================================
`

#### Tier 1: Feature Coverage (>= 5 Tests per Feature across F-01 to F-43)
- **Objective**: Exhaustive unit-level and functional validation verifying each feature works according to specification under nominal conditions.
- **Requirement**: Each of the 43 features in the inventory must have at least 5 distinct test cases (Total >= 215 tests).
- **Representative Test Categories**:
  - *Audio & Gestures*: Double-clap timing boundaries, triple-clap sequence, clap-pause-clap recognition, mic device enumeration, RMS calculations.
  - *Config & Plugins*: YAML loading, JSON schema validation, dynamic plugin registration, action chain execution, hot-reload file modification detection.
  - *TTS & Speech*: ElevenLabs API request generation, SHA-256 cache read/write, cache hit bypassing API call, sample rate conversion, pyttsx3 fallback initialization.
  - *Voice & LLM*: Wake word trigger, STT audio decoding, LLM tool calling schema parsing, multi-turn context preservation, prompt templating.
  - *Hardware & Healing*: CPU/RAM metric parsing, WMI temperature extraction, S.M.A.R.T. output parsing, IsHungAppWindow detection mock, safe process termination.
  - *Biometrics & Vision*: Face encoding generation, owner match thresholding, intruder detection event, MediaPipe landmark 21-point tracking, swipe direction calculation.
  - *Security, Comms & Data*: Nmap command assembly, TShark filter construction, Home Assistant REST payload structure, Telegram whitelist validation, Pandas statistics calculations, DOCX/PPTX export generation.

#### Tier 2: Boundary & Edge Cases (>= 5 Tests per Feature across F-01 to F-43)
- **Objective**: Rigorous stress and fault injection testing covering negative paths, boundary extremes, missing dependencies, and corrupted inputs.
- **Requirement**: Minimum 5 boundary/edge case test cases per feature (Total >= 215 tests).
- **Representative Test Matrix**:

| Feature Category | Edge Case Scenario | Test Input / Condition | Expected Resilient Behavior |
|---|---|---|---|
| **Acoustic Gestures** | Extreme Ambient Noise | Audio stream with 85dB continuous white noise | Noise floor adapts dynamically; avoids false positive triggers |
| **Acoustic Gestures** | Rapid Sub-Threshold Clicks | Rapid keyboard typing / pen clicking (< MIN_RMS) | Gated out by MIN_RMS and QUIET_GATE_MULT without spike arming |
| **Acoustic Gestures** | Single Isolated Clap | Single loud transient without second clap | Arms transient, times out after MAX_DOUBLE_GAP_S, resets cleanly |
| **Configuration** | Corrupted Config File | config.yaml containing invalid syntax / partial writes | Log parse error, maintain active in-memory configuration without crash |
| **Plugin System** | Defective Plugin Execution | Plugin raising uncaught ZeroDivisionError / RuntimeError | Exception isolated, logged with traceback; main event loop unaffected |
| **TTS Engine** | Missing / Invalid API Key | ELEVENLABS_API_KEY=" invalid_key\ or empty | Log warning, seamlessly switch to offline local TTS engine (pyttsx3) |
| **TTS Cache** | Corrupt Cached WAV File | 0-byte or truncated .wav file in .cache/jarvis_welcome/ | Detect invalid header/size, invalidate cache, refetch fresh audio |
| **LLM Engine** | Upstream API Timeout | LLM endpoint times out after 10s | Trigger fallback timeout response and alert user via voice |
| **Hardware Telemetry** | Non-Admin / No GPU Sensor | System lacking NVIDIA GPU or non-admin WMI access | Gracefully report None/N/A for missing sensors without crash |
| **Security Scanning** | Missing CLI Binaries | Nmap / TShark not installed in system PATH | Log clear error (\Nmap executable not found in PATH\), skip scan |
| **Security Scanning** | Unauthenticated Security Trigger| Security scan triggered without prior Biometric verification | Block execution immediately, log security violation, notify user |
| **Smart Home** | Home Assistant Offline | Target IP unreachable / HTTP 500 returned | Return voice error (\Home Assistant unreachable\), retry later |
| **Data Processing** | Empty / Malformed CSV File | 0-byte CSV or corrupted binary file passed to analyzer | Catch pandas parsing error, return structured error report |
| **Biometrics** | Webcam Disconnected | Webcam device index unavailable or busy | Fallback to bypass mode / password prompt, log warning |
| **Biometrics** | Extreme Low-Light Webcam Feed | Pitch black camera frame (< 5 average pixel intensity) | Prompt user for better lighting, avoid false positive intruder alert |
| **Vision Gestures** | Multiple Hands in Frame | 3 hands simultaneously in camera frame | Track primary dominant hand, ignore secondary background hands |
| **Multi-Channel** | Unauthorized Telegram User | Command sent from non-whitelisted Telegram User ID | Silently drop command, log security warning with user ID |
| **Self-Healing** | OS Protected Process Hung | explorer.exe or csrss.exe flagged as hung | Whitelist protection prevents killing critical OS processes |

#### Tier 3: Cross-Feature Interactions
- **Objective**: Verify end-to-end integration and concurrency across multiple subsystems operating simultaneously.
- **Key Cross-Feature Workflows to Validate**:
 1. **Acoustic Trigger -> Multi-Monitor Window Management -> TTS Playback**:
 - Double-clap triggers Spotify URL, launches Chrome on Monitor 1 & 3, focuses Cursor IDE, and streams ElevenLabs TTS concurrently without thread blocking or audio stutter.
 2. **Voice Command -> LLM Tool Call -> Home Assistant Actuation -> Voice Feedback**:
 - User speaks \Bật đèn phòng khách\; STT transcribes; LLM identifies home_assistant.turn_on action with entity light.living_room; executes REST call; TTS synthesizes \Đã bật đèn phòng khách\.
 3. **Biometric Security Gating -> Security Audit -> Report Delivery**:
 - User requests network scan; system activates webcam and verifies owner face; upon successful match, runs Nmap vulnerability scan; generates PDF report; sends summary to Telegram.
 4. **Hardware Watchdog -> Memory Threshold Breach -> Self-Healing -> Notification**:
 - System RAM exceeds 90% due to hung Chrome instance; Self-Healing module detects hung window, kills PID, frees RAM, sends Telegram notification, and announces status aloud.
 5. **Intruder Detection -> Workstation Lock -> Telegram Photo Dispatch**:
 - Camera detects unknown face; instantly calls Win32 LockWorkStation(); captures snapshot; uploads photo to whitelisted Telegram chat with timestamp.
 6. **Configuration Hot-Reload during Active Audio Capture**:
 - User modifies config.yaml to change gesture bindings while audio listener loop is running; file watcher triggers reload; new pattern bindings activate immediately without restarting audio stream.

#### Tier 4: Real-World Long-Running Workflows & Stress Runs
- **Objective**: Validate real-world stability, resource leakage prevention, and autonomous recovery under prolonged continuous operation.
- **Key Real-World Scenarios**:
 1. **24-Hour Continuous Ambient Monitoring Run**:
 - Run JARVIS background daemon for 24 hours in a simulated office environment with background conversation, music, keyboard clicks, and periodic claps.
 - *Pass Criteria*: Memory leak < 50MB RSS growth over 24 hours; zero process crashes; audio stream remains synchronized.
 2. **Burst Load & Rapid Gesture Stress**:
 - Rapid sequence of 50 acoustic clap patterns and 50 voice commands issued in rapid succession.
 - *Pass Criteria*: Dispatcher queue handles all events gracefully without thread pool exhaustion or dropped state.
 3. **Network Disruption & Auto-Recovery**:
 - Abruptly disconnect internet connectivity during active TTS, LLM, and Telegram polling; reconnect after 5 minutes.
 - *Pass Criteria*: Local features continue operating; network clients automatically re-establish connections upon restoration.
 4. **Multi-Application Developer Workspace Launch**:
 - Execute \Jarvis chuẩn bị môi trường làm việc\ with heavy workload (VMware VM boot, 2 VS Code workspaces, 4 Terminal tabs, 2 Chrome windows).
 - *Pass Criteria*: Sequence completes within configured timeout, windows positioned accurately, voice completion report plays.

---

## 5. Verification Method

To independently verify this specification mining report and validate future implementations against it:

1. **Requirement & Feature Inventory Verification**:
 - Inspect d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md to verify all 15 requirements (R1 through R15) and acceptance criteria are completely mapped into F-01 through F-43.
 - Inspect d:/Software GitCode/JARVIS/jarvis-main/jarvis.py to confirm legacy constant parity (lines 60-106).
2. **Automated Unit & Integration Test Execution**:
 - Run pytest suite covering Core Architecture and Legacy Compatibility:
 `bash
 pytest tests/ -v --tb=short
 `
 - Verify minimum test count requirement:
 `bash
 pytest tests/ --collect-only | grep \collected.*items\
 `
 *(Must exceed >= 15 tests for baseline; >= 215 tests for full Tier 1 coverage).*
3. **Configuration Hot-Reload Validation**:
 - Launch JARVIS: python -m jarvis
 - Modify config.yaml during runtime (e.g. toggle plugin or change threshold).
 - Verify via logs/jarvis.log that reload occurs within <= 5 seconds.
4. **Invalidation Conditions**:
 - Any omission of requirements R1-R15 or failure to support legacy .env keys invalidates specification compliance.
 - Failure to implement biometric gating (R12) before security tools (R8) invalidates the security architecture.

