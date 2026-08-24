# JARVIS Explorer 3 Survey Report: UI Subsystems, UX Requirements (R4), Test Infrastructure, and User Simulation Design

**Author**: Explorer 3 (UI, UX & Test Suite Specialist)  
**Date**: 2026-08-22  
**Target Scope**: UI Overlay (`overlay.py`), System Tray (`tray.py`), Dashboard (`dashboard.py`), Overlay Threading & Stability, UX R4 Polish, Test Suite & Diagnostics (`conftest.py`, `health-check`), and User Simulation Test Suite Specification.

---

## 1. Executive Summary

This investigation covers the user interface, user experience, and automated validation layers of the JARVIS Windows Desktop Assistant.

Key findings:
1. **UI Layer Architecture**:
   - `jarvis/ui/overlay.py`: Tkinter-based Iron Man HUD floating overlay running in a dedicated background daemon thread (`JARVIS-Overlay`). Uses `_schedule(self._root.after(0, fn))` for thread-safe cross-thread execution. State progression: `IDLE` → `LISTENING` → `THINKING` → `RESPONSE` → `HIDDEN`.
   - `jarvis/ui/tray.py`: `SystemTrayController` with dynamic PIL glowing arc-reactor icon rendering and 3-tier fallback (`pystray` → pure Win32 `ctypes` → headless mock). Context menu provides full control (mute, gestures, dashboard, settings, logs, reload, exit).
   - `jarvis/ui/dashboard.py`: Zero-dependency embedded `ThreadingHTTPServer` (and optional WebSocket server) serving a dark-mode HUD UI and comprehensive REST API (`/api/status`, `/api/telemetry`, `/api/actions`, `/api/config`, `/api/logs`, `/api/command`).
2. **Overlay Threading & Stability**:
   - The overlay supports 10+ consecutive show/hide cycles reliably without recreating Tkinter widgets by using `withdraw()` and `deiconify()`.
   - Minor race conditions and state edge cases were identified: calling `show_thinking` when hidden does not deiconify the window; `destroy()` followed by `start()` cannot restart cleanly; dragging event bindings are only on the root frame rather than propagating through child labels/frames.
3. **UX Requirements (R4) Gaps**:
   - **Breathing Dot**: Currently implemented as a binary blink (500ms on/off) rather than a smooth multi-phase breathing pulse.
   - **Typing Animation**: Currently static text `"⟳ Đang xử lý..."` rather than animated cycling dots (`"."`, `".."` , `"..."`).
   - **Randomized Greetings**: Welcome speech currently uses a single hardcoded string rather than a non-repeating randomized pool.
   - **Auto-Hide Tooltip**: Overlay auto-hides after `auto_hide_s` seconds but does not display the hint `"Double clap để hỏi tiếp"`.
   - **Interaction History Logging**: Interactions are logged across general debug logs, but lack a dedicated structured `[INTERACTION]` log entry with timestamp, transcript, intent, action, and response in `logs/jarvis.log`.
   - **Startup Introduction**: No vocal introduction is currently triggered when `app.start()` or `app.initialize()` completes.
4. **Existing Test Infrastructure & Diagnostics**:
   - 50 test files with 518 automated tests passing across DSP, gestures, hardware, biometrics, comms, smart home, and UI.
   - Comprehensive zero-cloud, zero-hardware fixtures in `tests/conftest.py` (`AudioSynthesizer`, `MockAudioStream`, `mock_sounddevice`, `MockHardwareProvider`, `MockWin32Platform`, `MockHttpServer`, `MockCameraFeed`).
   - `python -m jarvis health-check` provides platform, audio device, TTS API, and Win32 diagnostics.
5. **User Simulation Test Suite Specification**:
   - Defined a 13-test user simulation suite in `tests/test_user_simulation.py` covering synthetic clap injections, welcome sequences, AI voice loops, cooldown suppressions, zero double-dispatch validation, overlay state progression, 10+ show/hide cycles, smart keyword routing, and offline fallbacks.

---

## 2. Detailed Investigation of UI Components

### 2.1 Floating Chat Overlay (`jarvis/ui/overlay.py`)

#### Architecture & Lifecycle
- **Window Framework**: Python `tkinter` running on a separate daemon thread (`JARVIS-Overlay`).
- **Styling**: Cyberpunk / Iron Man HUD color scheme (`#0a0e1a` background, `#00f0ff` neon cyan border/title, `#ffa500` amber user text, `#00cc88` green status).
- **Positioning**: Fixed to bottom-right corner of primary display with screen margin calculation:
  ```python
  x = sw - self._width - self._margin_right
  y = sh - self._height - self._margin_bottom
  root.geometry(f"{self._width}x{self._height}+{x}+{y}")
  ```
- **Window Attributes**: `overrideredirect(True)` (frameless), `attributes("-topmost", True)` (always on top), `attributes("-alpha", 0.93)` (subtle transparency).
- **Thread Safety Mechanism**:
  Cross-thread method invocations (e.g., from `app.py` worker threads) are routed through `_schedule(fn)` which uses `self._root.after(0, fn)` to post callbacks into Tkinter's mainloop.

#### State Machine Progression
| State | Method | UI Representation | Status Text | Dot Indicator |
|---|---|---|---|---|
| **IDLE / HIDDEN** | `hide()` / `_do_hide()` | Window withdrawn (`withdraw()`) | `Sẵn sàng` | Static cyan |
| **LISTENING** | `show_listening()` | Window deiconified (`deiconify()`), User: `🎤 Đang lắng nghe...` | `Đang lắng nghe giọng nói` | Blinking amber |
| **THINKING** | `show_thinking(transcript)` | User: `transcript`, JARVIS: `⟳ Đang xử lý...` | `AI đang suy nghĩ` | Purple |
| **RESPONSE** | `show_response(transcript, response)` | User: `transcript`, JARVIS: `response` (truncated to 200 chars) | `Hoàn thành` | Emerald green (Auto-hides in 8-10s) |

#### Component Inspection Table
| Feature | Implementation Location | Current Status | Notes / Gaps |
|---|---|---|---|
| Thread Initialization | `overlay.py:52-58` | Working | Daemon thread `JARVIS-Overlay`, 3s startup timeout |
| Window Dragging | `overlay.py:142-149` | Partial | Bound to `root`, clicks on inner child labels do not drag |
| Auto-Hide Timer | `overlay.py:177, 203-207` | Working | `_root.after(auto_hide_s * 1000, self._do_hide)` with cancellation |
| Dot Animation | `overlay.py:186-196` | Basic Blink | 2-state toggle every 500ms |
| Typing Animation | `overlay.py:161-168` | Static | No animation loop; static string `"⟳ Đang xử lý..."` |
| Tooltip / Hint | `overlay.py:170-178` | Missing | No hint `"Double clap để hỏi tiếp"` displayed |

---

### 2.2 System Tray Controller (`jarvis/ui/tray.py`)

#### Architecture & Fallback Tiering
- **Tier 1 (pystray + PIL)**: Native taskbar notification icon with dynamic RGBA arc-reactor rendering and full context menu.
- **Tier 2 (Win32 ctypes fallback)**: Headless / pure Win32 notification fallback when pystray is unavailable.
- **Tier 3 (Headless Mock)**: Headless fallback for CI/testing environments (`sys.platform != 'win32'`).

#### Dynamic Status Indicators
`TrayStatus` Enum states:
- `ACTIVE` (Neon Cyan / Emerald) — Ready & listening for acoustic claps.
- `LISTENING` (Amber / Gold) — Actively recording voice command.
- `MUTED` (Crimson Red) — Microphone audio stream paused.
- `ERROR` (Orange / Red) — Subsystem degraded or error state.
- `DISABLED` (Slate Gray) — Standby / disabled.

#### Context Menu Handlers
1. `Mute Microphone` (`_on_toggle_mute`): Toggles `audio_engine.pause_stream()` / `resume_stream()`, updates status to `MUTED` / `ACTIVE`.
2. `Toggle Hand Gestures` (`_on_toggle_gestures`): Enables/disables computer vision gesture processing.
3. `Open Dashboard` (`_on_open_dashboard`): Spawns default browser to `http://127.0.0.1:8080`.
4. `Settings` (`_on_open_settings`): Alias to dashboard.
5. `View Logs` (`_on_view_logs`): Opens `logs/jarvis.log` with default OS viewer or browser.
6. `Reload Config` (`_on_reload_config`): Triggers `config_manager.load()` and `app.config.load()`.
7. `Exit` (`_on_quit`): Stops tray and invokes `app.stop()` in background thread.

#### Stress Testing Verification
Already covered in `tests/test_adversarial_m3_ui_app.py`:
- 16 rapid start/stop cycles (idempotency, thread termination).
- 20 concurrent worker threads executing 600+ status updates.
- Concurrent menu handler executions under load.

---

### 2.3 Real-Time Dashboard Server (`jarvis/ui/dashboard.py`)

#### Architecture
- **Web Server**: Zero-dependency Python standard library `http.server.ThreadingHTTPServer` (`_DashboardHTTPServer`) with request queue backlog 128 and daemon threads.
- **WebSocket Server**: Asyncio WebSocket broadcaster using `websockets` (fallback to HTTP polling if library not present).
- **Embedded UI**: Dark-mode HTML5/CSS3/JavaScript HUD interface with hardware telemetry gauges (CPU, RAM, GPU, Disk S.M.A.R.T.), interactive command console, real-time event stream feed, registered action launcher, and live YAML/JSON config editor.

#### REST API Endpoints
| Endpoint | Method | Payload / Params | Return Type | Description |
|---|---|---|---|---|
| `/` | `GET` | None | `text/html` | Embedded Dark-Mode HUD Dashboard |
| `/api/status` | `GET` | None | `application/json` | System health summary, uptime, audio device, STT/LLM provider |
| `/api/telemetry` | `GET` | None | `application/json` | Latest CPU/RAM/GPU/Disk metrics |
| `/api/actions` | `GET` | None | `application/json` | List of all registered actions and privileges |
| `/api/config` | `GET` | None | `application/json` | Current configuration dictionary |
| `/api/config` | `POST` | `Dict[str, Any]` | `application/json` | Live configuration hot-update |
| `/api/logs` | `GET` | None | `application/json` | Tail of recent log lines from `logs/jarvis.log` |
| `/api/command` | `POST` | `{"command": str}` or `{"action": str}` | `application/json` | Direct text command or action dispatch |

---

## 3. Overlay Threading & Stability Analysis

### 3.1 Threading Model & Concurrency Analysis
Tkinter is not natively thread-safe; its C-level Tcl/Tk interpreter state must be manipulated from the thread that initialized `tk.Tk()`.
- `JarvisOverlay.start()` initializes `tk.Tk()` inside a dedicated thread named `JARVIS-Overlay`.
- All cross-thread updates from `app.py` (e.g. `_ai_voice_loop`, `_welcome`, or pytest test worker threads) call public methods (`show_listening()`, `show_thinking()`, `show_response()`, `hide()`).
- Each public method wraps internal actions with `self._schedule(lambda: self._do_...)`.
- `_schedule` invokes `self._root.after(0, fn)`, placing the callback into Tkinter's internal Windows message pump loop.

### 3.2 10+ Show/Hide Stability Assessment
- In `jarvis/ui/overlay.py`, `_do_hide()` calls `self._root.withdraw()` and `_do_show_listening()` calls `self._root.deiconify()`.
- **Finding**: Because widgets (Labels, Frames, StringVars) are created once during `_build_ui()` and toggled via visibility flags (`withdraw`/`deiconify`), 10+ consecutive show/hide cycles do not cause widget accumulation, memory leaks, or handle exhaustion.
- Timer jobs (`_dot_job`, `_hide_job`) are canceled before scheduling new ones (`_cancel_dot_animation()`, `_cancel_hide()`).

### 3.3 Identified Race Conditions & Edge Cases

| # | Edge Case / Race Condition | Severity | Root Cause | Proposed Fix |
|---|---|---|---|---|
| 1 | `show_thinking` called while hidden | Medium | `_do_show_thinking` does not call `self._root.deiconify()`. If called directly without `show_listening`, overlay remains invisible. | Add `self._root.deiconify(); self._visible = True` in `_do_show_thinking` and `_do_show_response`. |
| 2 | Calling `start()` after `destroy()` | Low | `destroy()` quits the Tk mainloop, terminating the thread. A second `start()` call will see `_thread.is_alive() == False` and start a new thread, but `_ready` event was already set from the first run. | Reset `_ready = threading.Event()` and `_root = None` in `destroy()`. |
| 3 | Dragging event propagation | Low | Drag event `<ButtonPress-1>` and `<B1-Motion>` is bound only to `self._root`, not child `outer`, `inner`, `header`, or `Label` widgets. Clicking on labels prevents dragging. | Recursively bind `<ButtonPress-1>` and `<B1-Motion>` to child frames/labels, or bind `<ButtonPress-1>` to `header` frame. |
| 4 | Headless CI execution | Low | On headless environments without display drivers, `tk.Tk()` raises `_tkinter.TclError`. | Currently handled via `try...except` in `_run_tk` setting `_ready.set()`. `_schedule` checks `if self._root:`. Need to ensure `JarvisOverlay` methods no-op cleanly when headless. |

---

## 4. Investigation of UX Requirements (R4)

### 4.1 Breathing Dot Animation in LISTENING State
- **Current Behavior**: `_animate_dot` toggles `self._status_dot` between `COLORS["status_listening"]` (`#ffa500`) and `COLORS["bg"]` (`#0a0e1a`) every 500ms (harsh on/off blink).
- **Requirement**: "Overlay hiển thị animation thở (breathing dot) khi ở trạng thái LISTENING".
- **Proposed Solution**:
  Implement a smooth multi-phase pulsing sequence using a breathing color palette:
  ```python
  BREATHING_COLORS = [
      "#ff8800", "#ff9900", "#ffaa00", "#ffbb33",
      "#ffcc66", "#ffdd99", "#ffcc66", "#ffbb33", "#ffaa00", "#ff9900"
  ]
  ```
  Cycle through these frames with a 150ms `after()` timer tick while `self._visible and self._state == "listening"`.

### 4.2 Typing Animation ("...") in THINKING State
- **Current Behavior**: `_do_show_thinking` sets `self._jarvis_var.set("⟳ Đang xử lý...")` as a static string.
- **Requirement**: "Overlay hiển thị typing animation ('...') khi LLM đang xử lý".
- **Proposed Solution**:
  Add `_start_typing_animation()` and `_animate_typing()`:
  ```python
  def _animate_typing(self):
      if not self._root or not self._visible:
          return
      dots = "." * ((self._typing_step % 3) + 1)
      self._jarvis_var.set(f"Đang suy nghĩ{dots}")
      self._typing_step += 1
      self._typing_job = self._root.after(350, self._animate_typing)
  ```
  Cancel `_typing_job` when transitioning to `show_response` or `hide`.

### 4.3 Randomized Greetings Pool
- **Current Behavior**: `tts/manager.py:143` uses a single static string from `config/default_config.yaml` (`tts.welcome.phrase`: `"Welcome home sir. Congratulations on the new client..."`).
- **Requirement**: "JARVIS nói lời chào ngẫu nhiên từ danh sách (không lặp lại câu mỗi lần)".
- **Proposed Solution**:
  Define a rich pool of Vietnamese and English greetings in `config/default_config.yaml` (`tts.welcome.phrases`):
  ```yaml
  tts:
    welcome:
      enabled: true
      phrases:
        - "Chào mừng Ngài đã trở về. Toàn bộ hệ thống JARVIS đang hoạt động tối ưu."
        - "Rất hân hạnh được phục vụ Ngài. Chúc Ngài một ngày làm việc hiệu quả và thành công."
        - "Hệ thống đã sẵn sàng, thưa Ngài. Tất cả các ứng dụng làm việc đã được mở."
        - "Chào Ngài. Tôi đã chuẩn bị xong môi trường làm việc theo yêu cầu."
        - "Welcome home sir. Systems are online and operating at peak performance."
  ```
  In `TTSManager.speak_welcome()` or `JarvisApp._handle_tts_welcome()`, select a random greeting using a non-repeating algorithm:
  ```python
  available = [p for p in phrases if p != self._last_greeting] or phrases
  selected = random.choice(available)
  self._last_greeting = selected
  ```

### 4.4 Auto-Hide Overlay + Tooltip "Double clap để hỏi tiếp"
- **Current Behavior**: `_do_show_response` displays the response text and schedules `_do_hide` after `auto_hide_s` (8.0s), but displays no tooltip or hint.
- **Requirement**: "Sau khi response, overlay tự ẩn và hiển thị tooltip nhỏ 'Double clap để hỏi tiếp'".
- **Proposed Solution**:
  Add a dedicated hint label in `_build_ui()`:
  ```python
  self._hint_var = tk.StringVar(value="")
  self._hint_label = tk.Label(
      inner, textvariable=self._hint_var,
      font=tkfont.Font(family=FONT_FAMILY, size=8, slant="italic"),
      fg="#557788", bg=COLORS["bg"], anchor="e"
  )
  self._hint_label.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))
  ```
  In `_do_show_response`:
  `self._hint_var.set("💡 Double clap để hỏi tiếp")`
  In `_do_hide` and `_do_show_listening`:
  `self._hint_var.set("")`

### 4.5 Interaction History Logging to `logs/jarvis.log`
- **Current Behavior**: General module logs exist, but there is no standardized `[INTERACTION]` record for user queries and system responses.
- **Requirement**: "Log file ghi timestamp + transcript + response cho mỗi interaction" / "Log file tại logs/jarvis.log ghi interaction history với timestamp".
- **Proposed Solution**:
  In `jarvis/core/logger.py`, add `log_interaction(transcript: str, response: str, action: str = "", duration_ms: float = 0.0)`:
  ```python
  def log_interaction(self, transcript: str, response: str, action: str = "none", duration_ms: float = 0.0) -> None:
      self.info("[INTERACTION] Transcript='%s' | Response='%s' | Action='%s' | Duration=%.1fms",
                transcript, response, action, duration_ms)
  ```
  Call `log_interaction` in `JarvisApp.process_text_command` and `_ai_voice_loop`.

### 4.6 Startup Introduction Speech
- **Current Behavior**: `JarvisApp.start()` boots subsystems but makes no verbal announcement.
- **Requirement**: "JARVIS tự giới thiệu khi khởi động: 'Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.'"
- **Proposed Solution**:
  In `JarvisApp.start()`, after initializing audio, TTS, and UI components:
  ```python
  if self.tts_manager and not self.headless:
      startup_intro = self.config.get("system.startup_intro", "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.")
      self.tts_manager.speak(startup_intro, wait=False)
  ```

---

## 5. Existing Test Suite & Diagnostics Analysis

### 5.1 Test Suite Inventory
- Total test files: **50 files** (located in `tests/` and `tests/unit/`).
- Total passing tests: **518 tests**.
- Categorized test modules:
  - Audio & DSP: `test_audio_dsp.py`, `unit/test_dsp.py`, `unit/test_audio_engine.py`, `test_adversarial_m2_audio_gesture.py`.
  - Gesture Detection: `test_gesture_detector.py`, `unit/test_gesture_detector.py`.
  - Speech & AI: `test_tts_engine.py`, `unit/test_tts_cache.py`, `unit/test_tts_engines.py`, `unit/test_stt_engine.py`, `unit/test_llm_engine.py`, `test_llm_router.py`, `test_adversarial_m3_stt_llm.py`.
  - UI & App Integration: `unit/test_ui_dashboard.py`, `test_adversarial_m3_ui_app.py`, `unit/test_app_integration.py`.
  - Plugins & Extensions: `test_plugins.py`, `unit/test_plugins_m2.py`.
  - System Infrastructure: `test_config.py`, `test_dispatcher.py`, `test_logger.py`, `test_cli.py`, `test_windows_platform.py`.
  - Advanced Subsystems: `test_hardware_monitor.py`, `test_self_healing.py`, `test_security_scanner.py`, `test_biometrics.py`, `test_smart_home.py`, `test_comms_hub.py`, `test_data_analytics.py`.
  - Adversarial Stress & E2E Suites: `test_adversarial_harness.py`, `test_adversarial_m1.py` through `m5`, `test_e2e_scenarios.py`, `test_tier5_adversarial_core_audio_sys.py`.

### 5.2 Test Fixtures & Mock Infrastructure (`tests/conftest.py`)
`tests/conftest.py` is an exceptionally rich 1,022-line fixture library providing zero-cloud, zero-hardware isolation:
1. `AudioSynthesizer`: Mathematical PCM generation for silence, Gaussian noise, clap pulses, double claps (`generate_double_clap`), triple claps (`generate_triple_clap`), clap-pause-claps (`generate_clap_pause_clap`), and noise steps.
2. `MockAudioStream`: Emulates `sounddevice.InputStream` with synchronous `read(frames)` or asynchronous callback threads.
3. `mock_sounddevice`: Monkeypatches `sounddevice` device queries, playback, wait, and input streams.
4. `MockHardwareProvider`: Simulates CPU load, GPU metrics, thermals, fans, RAM, VRAM, and S.M.A.R.T. storage telemetry.
5. `MockWin32Platform`: Intercepts `ctypes.windll.user32` and `kernel32` (monitors, windows, PIDs, process termination, input injection, workstation lock).
6. `MockHttpServer`: In-memory mock for Home Assistant, ElevenLabs TTS, Telegram Bot API, OpenAI/Gemini/Claude LLMs, MQTT, and Webhooks.
7. `MockCameraFeed`: Synthetic OpenCV frames, face recognition encodings (owner vs. intruder), and MediaPipe 21-landmark hand gestures.

### 5.3 Health Check Diagnostics (`python -m jarvis health-check`)
Implemented in `jarvis/cli.py` (`run_health_check`):
1. Platform & OS environment check (`sys.platform`, Python version, executable).
2. Audio subsystem query via `sounddevice.query_devices()` (identifies input devices and default microphone).
3. TTS engine key detection (verifies ElevenLabs key or confirms SAPI5 fallback).
4. Windows Win32 API capability check (`user32.GetSystemMetrics(SM_CMONITORS)`).
5. Configuration verification (root sections count).
6. Covered by unit tests in `tests/test_cli.py:44` (`test_run_health_check_execution`).

---

## 6. Specification for User Simulation Test Suite (`tests/test_user_simulation.py`)

To fulfill Requirement R1 and R5 (adding $\ge 10$ new user simulation tests without regressing the existing 518 tests), `tests/test_user_simulation.py` should be structured as follows:

```
tests/test_user_simulation.py
├── test_user_sim_double_clap_first_trigger_welcome_sequence
├── test_user_sim_double_clap_second_trigger_ai_voice_loop
├── test_user_sim_triple_clap_system_status
├── test_user_sim_clap_pause_clap_show_overlay
├── test_user_sim_cooldown_suppression
├── test_user_sim_zero_double_dispatch
├── test_user_sim_overlay_state_transitions
├── test_user_sim_overlay_10_show_hide_cycles
├── test_user_sim_voice_pipeline_smart_keyword_router
├── test_user_sim_tts_fallback_when_elevenlabs_invalid
├── test_user_sim_stt_fallback_without_api_key
├── test_user_sim_interaction_history_logging
└── test_user_sim_startup_introduction_speech
```

### Detailed Test Specifications

#### Test 1: First Double Clap → Welcome Sequence
- **Intent**: User performs a double clap on a fresh session.
- **Verification**:
  - `welcome_executed` becomes `True`.
  - `spotify`, `chrome_claude`, `chrome_binance`, `cursor`, and `tts_welcome` actions are dispatched.
  - Welcome sequence runs exactly once.

#### Test 2: Second Double Clap → AI Voice Interaction Loop
- **Intent**: User performs a double clap after welcome sequence has completed.
- **Verification**:
  - Welcome sequence does NOT repeat.
  - Overlay enters `show_listening()`.
  - JARVIS announces listening prompt (`"Vâng thưa Ngài, tôi đang lắng nghe."`).
  - Synthetic voice audio is recorded and transcribed via STT.
  - Overlay transitions to `show_thinking()`.
  - LLM parses intent, action executes, overlay transitions to `show_response()`.
  - Response is spoken via TTS.

#### Test 3: Triple Clap → System Status Report
- **Intent**: User claps 3 times in rapid succession.
- **Verification**:
  - `GestureDetector` recognizes `triple_clap`.
  - `system_status` action executes.
  - Status summary message containing CPU/RAM health is vocalized.

#### Test 4: Clap-Pause-Clap → Show Overlay Interaction
- **Intent**: User performs clap-pause-clap rhythm.
- **Verification**:
  - `GestureDetector` recognizes `clap_pause_clap`.
  - `show_overlay` action executes.
  - Overlay is shown in listening state.

#### Test 5: Cooldown Enforcement & Rapid Trigger Suppression
- **Intent**: User accidentally claps again within 1.0s of a previous trigger.
- **Verification**:
  - Second acoustic trigger within `< 3.0s` cooldown is suppressed.
  - Debug log records `"suppressed — cooldown ... remaining"`.
  - No redundant actions are dispatched.

#### Test 6: Zero Double-Dispatch Across Gesture-to-Action Routing
- **Intent**: Verify architectural fix ensuring `GestureDetector` never dispatches directly while `JarvisApp._on_gesture_event` also dispatches.
- **Verification**:
  - Count of dispatches for any single gesture event is strictly equal to 1 per registered action.

#### Test 7: Overlay State Machine Progression
- **Intent**: Trace full visual state transitions of `JarvisOverlay`.
- **Verification**:
  - `_visible == False` (IDLE).
  - `show_listening()` → `_visible == True`, status `"Đang lắng nghe giọng nói"`, breathing dot active.
  - `show_thinking("mở spotify")` → user text updated, typing animation active.
  - `show_response("mở spotify", "Đã mở Spotify")` → status `"Hoàn thành"`, hint `"💡 Double clap để hỏi tiếp"`, auto-hide timer scheduled.

#### Test 8: Overlay 10+ Show/Hide Cycling Stability
- **Intent**: Rapidly cycle `show_listening()` and `hide()` 15 times consecutively.
- **Verification**:
  - No Tkinter widget errors, thread deadlocks, or uncaught exceptions.
  - Final state matches expected visibility.

#### Test 9: Voice Pipeline Smart Keyword Router (Offline / No Key Mode)
- **Intent**: Provide transcripts for $\ge 5$ distinct categories without LLM API key.
- **Test Matrix**:
  1. `"bật đèn phòng khách"` → `home_assistant_call` / Vietnamese confirmation.
  2. `"nhiệt độ CPU hiện tại"` → `hardware_telemetry_check` / telemetry reply.
  3. `"mở nhạc spotify"` → `spotify` action.
  4. `"thời tiết hôm nay"` → weather info response.
  5. `"nhắc nhở công việc"` → reminder response.
  6. `"tắt máy tính"` → system shutdown confirmation.
  7. `"câu hỏi lạ chưa biết"` → fallback: `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`.

#### Test 10: TTS Fallback on Invalid ElevenLabs Key
- **Intent**: Simulate ElevenLabs HTTP 401 Unauthorized or connection timeout.
- **Verification**:
  - Primary engine raises exception.
  - `TTSManager` catches exception, switches to `SAPI5FallbackTTS`.
  - Speech succeeds without crashing the application.

#### Test 11: STT Fallback on Missing Whisper API Key
- **Intent**: Simulate missing `OPENAI_API_KEY`.
- **Verification**:
  - Primary `OpenAIWhisperSTT` fails gracefully.
  - `STTEngine` falls back to `WindowsSpeechSTT` / `MockSTTEngine`.
  - Non-silent audio returns valid transcript or graceful empty string without unhandled exceptions.

#### Test 12: Interaction History Logging
- **Intent**: Execute text and voice commands through `JarvisApp`.
- **Verification**:
  - `logs/jarvis.log` contains structured records with timestamp, transcript, and response.

#### Test 13: Startup Introduction Speech
- **Intent**: Initialize and start `JarvisApp`.
- **Verification**:
  - TTS speaks `"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`.

---

## 7. Potential Regression Risks & Mitigation Guidelines

| Risk Area | Risk Description | Severity | Mitigation Strategy |
|---|---|---|---|
| **Cooldown Timing** | Increasing `_action_fanout_cooldown_s` to 3.0s might suppress fast multi-step test assertions if tests do not advance time or sleep. | High | In tests, use explicit time advancing (`time.monotonic()` patching) or allow sufficient inter-test intervals. |
| **Tkinter Headless Execution** | In Linux or CI runners without X11/Win32 display, `tk.Tk()` raises `TclError`. | Medium | Ensure `JarvisOverlay` has headless detection (`headless=True` or `TclError` catch) and all overlay methods gracefully no-op when `_root is None`. |
| **STT / LLM Latency** | Pipeline taking $> 10$ seconds will violate acceptance criteria. | Medium | Use synchronous mock STT/LLM during automated tests with instantaneous response time ($< 0.05$s). |
| **Existing Test Regressions** | Modifying `LLMIntentRouter`, `TTSManager`, or `JarvisApp` signatures could break existing unit tests in `tests/`. | High | Maintain strict backward compatibility with existing method signatures, keyword arguments, and return types (e.g. `DashboardMetricsServer = DashboardServer`, `audio_to_wav_bytes = float32_to_pcm16_wav_bytes`). |
| **Double Dispatch Bug Re-introduction** | Passing `dispatcher` into `GestureDetector` constructor will cause double-fire because `JarvisApp._on_gesture_event` already dispatches actions. | Critical | Keep `dispatcher=None` when `JarvisApp` instantiates `GestureDetector`. All routing must flow through `_on_gesture_event`. |

---

## 8. Summary of Recommendations for Implementation Team

1. **For Worker 1 (UI & UX Polish - R4)**:
   - Upgrade `jarvis/ui/overlay.py`:
     - Implement multi-phase breathing pulse in `_animate_dot`.
     - Implement dynamic `_animate_typing` (`"."`, `".."` , `"..."`) in `_do_show_thinking`.
     - Add `"💡 Double clap để hỏi tiếp"` hint label in `_do_show_response`.
     - Ensure `show_thinking` and `show_response` deiconify the window if it was hidden.
   - Upgrade `jarvis/tts/manager.py` & `config/default_config.yaml`:
     - Add non-repeating randomized greeting pool (`tts.welcome.phrases`).
   - Upgrade `jarvis/core/app.py`:
     - Add startup vocal greeting in `app.start()`: `"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`.
     - Add structured `log_interaction` logging in `process_text_command` and `_ai_voice_loop`.
     - Fix `clap_pause_clap` routing to dispatch `show_overlay` instead of hardcoded `toggle_mute`.

2. **For Worker 2 (Smart Keyword Router & Fallbacks - R2, R3)**:
   - Upgrade `jarvis/llm/router.py`:
     - Expand `rule_engine` and `_regex_rules` to cover all Vietnamese smart home, system status, music, weather, reminder, and power management phrases with natural Vietnamese text responses.
     - Set default fallback response to `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`.
   - Ensure STT and TTS offline fallbacks seamlessly engage when API keys are absent.

3. **For Worker 3 / Challenger (User Simulation Suite - R1, R5)**:
   - Implement the complete 13-test user simulation suite in `tests/test_user_simulation.py` following the specification above.
   - Verify `python -m pytest tests/ -x -q` reaches $\ge 531$ passing tests ($518 + 13$).
   - Run `python -m jarvis health-check` and ensure clean exit code 0.
