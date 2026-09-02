# Survey: Stubs, Placeholders, and NotImplementedError Inventory

**Target Milestone**: M1 (R1: Codebase Audit & `docs/ROADMAP.md` Part A)  
**Investigator**: Explorer M1-2  
**Date**: 2026-09-02  
**Repository**: `d:\Software GitCode\JARVIS` (JARVIS Voice AI Assistant v4.5.0 → v4.6.0)

---

## 1. Executive Summary

A comprehensive static AST (Abstract Syntax Tree) and regex inspection across the entire JARVIS repository was performed to identify all stubs, `# TODO`, `# FIXME`, `# STUB`, `raise NotImplementedError`, dummy `pass` functions, empty classes, and mock implementations.

### Summary Metrics
| Category | Occurrences in `jarvis/` | Occurrences in `tests/` & `scripts/` | Overall Codebase |
|---|---|---|---|
| **`# TODO` Markers** | 1 | 0 | 1 |
| **`# FIXME` Markers** | 0 | 0 | 0 |
| **`# STUB` / `# XXX` Markers** | 0 | 0 | 0 |
| **`raise NotImplementedError`** | 2 | 0 | 2 |
| **Abstract `@abstractmethod` Methods** | 25 | 0 | 25 |
| **Non-Abstract Dummy `pass` Functions** | 3 | 52 | 55 |
| **Empty Classes (`class Foo: pass`)** | 13 | 12 | 25 |
| **Missing Module Files** | 1 (`jarvis/workers/proactive.py`) | 0 | 1 |
| **Missing Optional Dependencies** | 5 (`vosk`, `porcupine`, `cv2`, `mediapipe`, `face_recognition`) | — | 5 |
| **In-Production Mock Classes** | 2 (`MockBrowserDriver`, `MockSTTEngine`) | 53 | 55 |

The core business logic of JARVIS is exceptionally mature and contains **zero fake facades or trivial return stubs** in production pathways. All detected placeholders fall into well-defined architectural categories: OS platform guards, template generation strings, abstract interface definitions, exception hierarchies, and deterministic CI/CD test doubles.

---

## 2. Detailed Item-by-Item Inventory

### 2.1 `# TODO` Comments

| # | File Path | Line | Surrounding Function / Class | Current Behavior | Required Fix / Production Resolution |
|---|---|---|---|---|---|
| 1 | `jarvis/skills/skill_synthesizer/__init__.py` | L100 | `SkillSynthesizer._generate_skill_code` | Embedded comment in fallback generic Python template string for dynamically synthesized skills. | Replace placeholder comment with a robust default action body (e.g. structured JSON logging, event bus notification, or LLM fallback execution). |

**Code Snippet (`jarvis/skills/skill_synthesizer/__init__.py:98–101`):**
```python
    else:
        logic = textwrap.dedent("""\
            # TODO: Implement skill logic here
            text = f'Skill [{skill_name}] đã nhận lệnh: {action} với tham số: {query or str(kwargs)}'""")
```

---

### 2.2 `# FIXME`, `# STUB`, `# XXX` Comments
- **Total Count**: **0**
- No active `# FIXME`, `# STUB`, or `# XXX` markers exist anywhere in the codebase.

---

### 2.3 `raise NotImplementedError` Statements

| # | File Path | Line | Surrounding Function / Class | Current Behavior | Required Fix / Production Resolution |
|---|---|---|---|---|---|
| 1 | `jarvis/sandbox/security.py` | L513 | `run_in_restricted_token_with_job(args, ...)` | Raises `NotImplementedError("Low Integrity processes are only supported on Windows.")` if `sys.platform != "win32"`. | Production guard for Windows Integrity Mechanism (MIC) token creation. For cross-platform POSIX support in future phases, implement a POSIX `setrlimit` / unshare isolation runner. |
| 2 | `jarvis/sandbox/security.py` | L948 | `run_in_appcontainer_with_job(args, appcontainer_name, ...)` | Raises `NotImplementedError("AppContainer process isolation is only supported on Windows.")` if `sys.platform != "win32"`. | Production guard for Windows NT AppContainer SID isolation with zero network capabilities. For POSIX platforms, document requirement or implement Docker / seccomp container runner. |

**Code Snippets (`jarvis/sandbox/security.py`):**
```python
# Line 512-513:
if sys.platform != "win32":
    raise NotImplementedError("Low Integrity processes are only supported on Windows.")

# Line 947-948:
if sys.platform != "win32":
    raise NotImplementedError("AppContainer process isolation is only supported on Windows.")
```

---

### 2.4 Non-Abstract Dummy `pass` Functions in Production

| # | File Path | Line | Surrounding Class & Function | Current Behavior | Assessment & Recommendation |
|---|---|---|---|---|---|
| 1 | `jarvis/comms/zalo.py` | L407 | `ZaloBotController.ZaloWebhookHandler.log_message(self, format, *args)` | Implements `pass` to suppress default `BaseHTTPRequestHandler` standard error logging. | Valid suppression hook. Recommend routing to `logger.debug(...)` for enhanced telemetry during webhook diagnostics. |
| 2 | `jarvis/core/logger.py` | L301 | `LogContext.__exit__(self, exc_type, exc_val, exc_tb)` | Implements `pass` in context manager exit hook. | Standard context manager exit no-op. No modification needed. |
| 3 | `jarvis/memory/sqlite_store.py` | L779 | `SQLiteMemoryStore.close(self)` | Implements `pass` with docstring: *"No-op for connection-per-call architecture, provided for lifecycle symmetry."* | Standard lifecycle symmetry hook. If connection pooling is introduced, wire pool cleanup here. |

---

### 2.5 Abstract Base Class Interfaces (`@abstractmethod` with `pass`)

These define the formal interface contracts across JARVIS subsystems and are fully implemented by their corresponding concrete providers:

| Subsystem | Abstract Base Class | File Path | Method Name | Line | Concrete Implementations |
|---|---|---|---|---|---|
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `launch` | L46 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `close` | L51 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `navigate` | L56 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `click` | L61 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `type_text` | L66 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `select_option` | L77 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `wait_for_selector` | L82 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `evaluate_script` | L92 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `get_html` | L97 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `get_text` | L102 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `capture_page_screenshot` | L107 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `get_cookies` | L112 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `set_cookies` | L117 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `get_current_url` | L122 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `get_title` | L127 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `find_elements` | L132 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Browser** | `BaseBrowserDriver` | `jarvis/browser/driver.py` | `scroll` | L137 | `CDPBrowserDriver`, `PlaywrightBrowserDriver`, `MockBrowserDriver` |
| **Plugins** | `BasePlugin` | `jarvis/core/plugin.py` | `_define_metadata` | L53 | All plugin implementations in `jarvis/plugins/` |
| **STT** | `BaseSTTEngine` | `jarvis/stt/engine.py` | `transcribe` | L332 | `WhisperAPISTT`, `WindowsSpeechSTT`, `FasterWhisperSTT`, `MockSTTEngine` |
| **STT** | `BaseSTTEngine` | `jarvis/stt/engine.py` | `is_available` | L351 | `WhisperAPISTT`, `WindowsSpeechSTT`, `FasterWhisperSTT`, `MockSTTEngine` |
| **STT** | `BaseSTTEngine` | `jarvis/stt/engine.py` | `engine_name` | L357 | `WhisperAPISTT`, `WindowsSpeechSTT`, `FasterWhisperSTT`, `MockSTTEngine` |
| **TTS** | `BaseTTSEngine` | `jarvis/tts/base.py` | `speak` | L24 | `SAPI5Engine`, `PiperTTSEngine`, `ElevenLabsTTSEngine`, `FallbackTTSEngine` |
| **TTS** | `BaseTTSEngine` | `jarvis/tts/base.py` | `synthesize_to_bytes` | L39 | `SAPI5Engine`, `PiperTTSEngine`, `ElevenLabsTTSEngine`, `FallbackTTSEngine` |
| **TTS** | `BaseTTSEngine` | `jarvis/tts/base.py` | `is_available` | L53 | `SAPI5Engine`, `PiperTTSEngine`, `ElevenLabsTTSEngine`, `FallbackTTSEngine` |
| **TTS** | `BaseTTSEngine` | `jarvis/tts/base.py` | `engine_name` | L61 | `SAPI5Engine`, `PiperTTSEngine`, `ElevenLabsTTSEngine`, `FallbackTTSEngine` |

---

### 2.6 Empty Exception Hierarchy Classes (`class X(Exception): pass`)

| File Path | Line | Class Name | Superclasses | Docstring Summary |
|---|---|---|---|---|
| `jarvis/core/plugin.py` | L141 | `CircularDependencyError` | `Exception` | Raised when plugin dependency graph contains a cycle. |
| `jarvis/llm/client.py` | L39 | `LLMError` | `Exception` | Base exception for all LLM client failures. |
| `jarvis/llm/client.py` | L44 | `LLMAuthenticationError` | `LLMError, PermissionError` | Raised on invalid API key or 401/403 HTTP status. |
| `jarvis/llm/client.py` | L49 | `LLMRateLimitError` | `LLMError` | Raised when LLM provider rate limits (HTTP 429). |
| `jarvis/llm/client.py` | L54 | `LLMTimeoutError` | `LLMError, TimeoutError` | Raised when LLM provider connection times out. |
| `jarvis/llm/client.py` | L59 | `LLMProviderError` | `LLMError` | Raised on provider internal server error (HTTP 5xx). |
| `jarvis/llm/client.py` | L64 | `LLMResponseParsingError` | `LLMError` | Raised when response format cannot be decoded. |
| `jarvis/planner/dag.py` | L18 | `TaskDAGException` | `Exception` | Base exception for DAG execution failures. |
| `jarvis/planner/dag.py` | L23 | `CycleDetectedException` | `TaskDAGException` | Raised when a cycle is detected in task graph. |
| `jarvis/planner/dag.py` | L28 | `NodeNotFoundException` | `TaskDAGException` | Raised when dependency node ID is missing from graph. |
| `jarvis/stt/engine.py` | L76 | `STTError` | `Exception` | Base exception for speech transcription errors. |
| `jarvis/tts/base.py` | L12 | `TTSError` | `Exception` | Base exception for text-to-speech synthesis failures. |
| `jarvis/workers/worker.py` | L23 | `WorkerCancelledException` | `Exception` | Raised internally when a background task is cancelled. |

---

### 2.7 Missing Subsystem Modules & Worker Unification

| Subsystem / Module | Expected Location | Current State | Impact | Required Resolution (P0-B) |
|---|---|---|---|---|
| **Proactive Worker Bridge** | `jarvis/workers/proactive.py` | **MISSING** (File does not exist under `jarvis/workers/`) | `app.py` or modular worker loaders attempting to import `jarvis.workers.proactive.ProactiveEngine` fail unless importing from `jarvis.proactive.engine`. | Create `jarvis/workers/proactive.py` that implements/re-exports `ProactiveEngine`, integrating reminder scheduling, hardware watchdog alerts (CPU/RAM/Temp), Pomodoro focus timer, and `proactive_reminder` action. |

---

### 2.8 Missing Optional Dependencies & Fallback Behavior

| Dependency | Category | Installed in `.venv` | Configured in `pyproject.toml` | Modules Affected | Fallback Behavior When Missing |
|---|---|---|---|---|---|
| `vosk` | Audio / Wake Word | ❌ No | ❌ No | `jarvis/audio/wake_word.py` | Falls back to `AcousticSpectralDetector` (SFM/ZCR spectral analysis), which is sensitive to room noise. |
| `pvporcupine` | Audio / Wake Word | ❌ No | ✅ Yes (`[project.optional-dependencies.wakeword]`) | `jarvis/audio/wake_word.py` | Skips Porcupine engine, tries Vosk / OpenWakeWord / Acoustic fallback. |
| `opencv-python` (`cv2`) | Computer Vision / Gestures | ❌ No | ✅ Yes (`[project.optional-dependencies.gestures]`) | `jarvis/gesture/hand_tracker.py`, `jarvis/vision/biometrics.py` | Gracefully catches `ImportError`, sets `CV2_AVAILABLE=False`, disables webcam capture. |
| `mediapipe` | Computer Vision / Gestures | ❌ No | ✅ Yes (`[project.optional-dependencies.gestures]`) | `jarvis/gesture/hand_tracker.py` | Gracefully catches `ImportError`, sets `MEDIAPIPE_AVAILABLE=False`, disables hand landmark detection. |
| `face_recognition` | Biometrics / Security | ❌ No | ❌ No | `jarvis/vision/biometrics.py` | Gracefully catches `ImportError`, sets `FACE_RECOGNITION_AVAILABLE=False`, biometric unlock disabled. |
| `playwright` | Automation / Browser | ❌ No | ✅ Yes (`[project.optional-dependencies.browser]`) | `jarvis/browser/driver.py`, `jarvis/browser/cdp_controller.py` | Falls back to native Chrome DevTools Protocol (CDP) WebSocket driver (`CDPBrowserDriver`) or `MockBrowserDriver`. |
| `winotify` | Notifications | ❌ No | ✅ Yes (`[project.optional-dependencies.notifications]`) | `jarvis/workers/notification_hub.py` | Falls back to PowerShell `BurntToast` script or Windows balloon tooltip. |
| `matplotlib` | Data Analysis | ❌ No | ✅ Yes (`[project.optional-dependencies.charts]`) | `jarvis/data/analysis_service.py` | Gracefully skips chart generation; returns tabular/text summary. |
| `paho-mqtt` | Smart Home IoT | ❌ No | ❌ No | `jarvis/smart_home/mqtt.py` | Catches `ImportError`; MQTT discovery returns empty node list. |
| `onnxruntime` | Offline TTS | ❌ No | ❌ No | `jarvis/tts/piper.py` | Catches `ImportError`; Piper offline TTS engine marked unavailable; falls back to SAPI5. |

---

### 2.9 In-Production Mock Implementations

| # | Class Name | File Path | Line | Intended Purpose & Architecture Design |
|---|---|---|---|---|
| 1 | `MockBrowserDriver` | `jarvis/browser/driver.py` | L855 | Tier 4 Browser Driver designed for zero-network, headless CI/CD execution and unit test isolation with simulated DOM, synthetic screenshots, and in-memory cookie stores. |
| 2 | `MockSTTEngine` | `jarvis/stt/engine.py` | L726 | Tier 4 Speech-to-Text Driver for deterministic automated testing and offline unit test suites without requiring microphone hardware or external speech APIs. |

---

## 3. Formatted Stubs & Placeholders Table for `docs/ROADMAP.md` Part A

The following markdown table is formatted specifically for inclusion into `docs/ROADMAP.md` under **Phần A — Phân loại trạng thái hiện tại (Stubs & Placeholders Inventory)**:

```markdown
### Stubs & Placeholders Inventory

| # | Type | File Location | Identifier | Current Behavior | Production Target / Fix |
|---|---|---|---|---|---|
| 1 | `# TODO` | `jarvis/skills/skill_synthesizer/__init__.py:100` | `SkillSynthesizer._generate_skill_code` | Placeholder comment in dynamic code synthesis template string. | Replace with structured default execution handler and logging. |
| 2 | `NotImplementedError` | `jarvis/sandbox/security.py:513` | `run_in_restricted_token_with_job` | Platform guard raising on non-Windows OS (MIC Token isolation). | Windows 11 native feature; document constraint or add POSIX runner. |
| 3 | `NotImplementedError` | `jarvis/sandbox/security.py:948` | `run_in_appcontainer_with_job` | Platform guard raising on non-Windows OS (AppContainer isolation). | Windows 11 native feature; document constraint or add seccomp runner. |
| 4 | Dummy `pass` Hook | `jarvis/comms/zalo.py:407` | `ZaloWebhookHandler.log_message` | Suppresses `BaseHTTPRequestHandler` standard error output. | Forward to `logger.debug` for webhook observability. |
| 5 | Dummy `pass` Hook | `jarvis/core/logger.py:301` | `LogContext.__exit__` | No-op context manager exit hook. | Retain as standard context manager lifecycle no-op. |
| 6 | Dummy `pass` Hook | `jarvis/memory/sqlite_store.py:779` | `SQLiteMemoryStore.close` | No-op connection-per-call lifecycle symmetry hook. | Retain as standard lifecycle symmetry no-op. |
| 7 | Missing Module | `jarvis/workers/proactive.py` | `ProactiveEngine` | File missing under `jarvis/workers/` (lives in `jarvis/proactive/`). | Implement `jarvis/workers/proactive.py` worker bridge (P0-B). |
| 8 | Missing Dep Stub | `jarvis/audio/wake_word.py:37` | `import vosk` fallback | Falls back to unreliable `AcousticSpectralDetector`. | Install `vosk` + Vietnamese model `vosk-model-small-vn-0.4` (P0-A). |
| 9 | Missing Dep Stub | `jarvis/gesture/hand_tracker.py:41` | `import cv2, mediapipe` | Disables hand tracking and camera biometrics gracefully. | Optional dependency in `[gestures]`; keep graceful degradation. |
| 10 | Missing Dep Stub | `jarvis/vision/biometrics.py:39` | `import face_recognition` | Disables face unlock verification gracefully. | Optional biometric feature; keep graceful degradation. |
| 11 | In-Code Mock | `jarvis/browser/driver.py:855` | `MockBrowserDriver` | In-memory simulated browser driver for offline test isolation. | Retain as Tier 4 test double; real driver uses CDP/Playwright. |
| 12 | In-Code Mock | `jarvis/stt/engine.py:726` | `MockSTTEngine` | Deterministic offline STT engine for automated test suites. | Retain as Tier 4 test double; real STT uses Whisper/Windows/Vosk. |
```

---

## 4. Verification & Audit Methodology

This inventory was generated and verified using deterministic multi-pass static analysis:
1. **AST Node Traverser**: Scanned all `.py` files in `jarvis/`, `tests/`, and `scripts/` using Python's `ast` standard library to locate `ast.Pass`, `ast.Raise(NotImplementedError)`, `ast.ClassDef`, and `ast.FunctionDef`.
2. **Regex Line Scanner**: Scanned for pattern matching `#\s*(TODO|FIXME|STUB|XXX)\b`.
3. **Import Fallback Categorizer**: Tracked every `try: ... except ImportError:` block across all subpackages.
4. **Reproducibility**:
   ```powershell
   # Search for TODOs across codebase
   git grep -n "TODO" jarvis/
   # Search for NotImplementedError
   git grep -n "NotImplementedError" jarvis/
   # Search for empty pass functions
   python .agents/explorer_m1_2/scan_code.py
   ```
