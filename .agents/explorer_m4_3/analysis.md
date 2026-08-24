# Analysis Report: Milestone M4 (Automated User Simulation & Full Regression)

**Explorer**: Explorer 3 (M4)  
**Date**: 2026-08-22  
**Target Subsystems**: `tests/test_user_simulation.py`, `tests/conftest.py`, `jarvis/core/app.py`, `jarvis/core/logger.py`, `jarvis/cli.py`

---

## 1. Executive Summary

Milestone M4 establishes the **Automated User Simulation Test Suite** (`tests/test_user_simulation.py`) and executes full regression across the $\ge 518$ test base. This analysis provides an exhaustive breakdown of:
1. **Fixture Architecture & Isolation Strategy**: How to leverage existing fixtures (`audio_synthesizer`, `mock_audio_stream`, `mock_hardware_provider`, `mock_win32_platform`, `mock_http_server`) and construct dedicated deterministic test fixtures for `JarvisApp`.
2. **Structured `[INTERACTION]` Logging Verification**: The exact format, atomic file append mechanism, multiline sanitization, and how to assert on interaction log entries.
3. **CLI Health-Check Diagnostic Audit**: Step-by-step validation of `python -m jarvis health-check` ensuring all 5 diagnostic checks pass cleanly with exit code 0.
4. **Complete Architecture for `tests/test_user_simulation.py`**: A robust, non-flaky test suite containing 14 user simulation test scenarios covering all voice loop states, acoustic gestures, zero double-dispatch guarantees, cooldown suppression, smart keyword routing, and offline fallbacks.

---

## 2. Deep Dive: Existing Pytest Fixtures & App Initialization

### 2.1 Fixture Inventory in `tests/conftest.py`

| Fixture Name | Type | Scope | Capabilities & Usage |
|---|---|---|---|
| `audio_synthesizer` | `AudioSynthesizer` | Function | Mathematical PCM generator: `generate_silence`, `generate_noise`, `generate_clap_pulse`, `generate_double_clap`, `generate_triple_clap`, `generate_clap_pause_clap`. |
| `mock_audio_stream` | `MockAudioStream` | Function | Simulates `sounddevice.InputStream` with fixed block size (1764) and sample rate (44.1 kHz). Includes helper methods `feed_buffer` and `read`. |
| `mock_sounddevice` | `Dict[str, Any]` | Function | Monkeypatches `sounddevice.query_devices`, `sounddevice.play`, `sounddevice.wait`, `sounddevice.InputStream`. Records played audio chunks in `played_audio_chunks`. |
| `mock_hardware_provider` | `MockHardwareProvider` | Function | Simulates host sensors: CPU load/temp, RAM/VRAM saturation, GPU metrics, disk S.M.A.R.T. status. Monkeypatches `psutil`. |
| `mock_win32_platform` | `MockWin32Platform` | Function | Simulates Win32 desktop environment (monitors, windows, foreground hwnd, `LockWorkStation`, `IsHungAppWindow`, `TerminateProcess`). Monkeypatches `ctypes.windll.user32` & `kernel32`. |
| `mock_http_server` | `MockHttpServer` | Function | In-memory REST/WS interceptor for Home Assistant, ElevenLabs TTS, Telegram Bot API, MQTT brokers. |
| `mock_camera_feed` | `MockCameraFeed` | Function | Synthetic frame generator and OpenCV/MediaPipe/face_recognition interceptor. |

### 2.2 `JarvisApp` Initialization Patterns

In `jarvis/core/app.py`:
- Constructor: `JarvisApp(config_path=None, headless=False, no_hot_reload=False)`
- Bootstrapping: `app.initialize()` initializes in strict deterministic order:
  1. `ConfigManager` (loaded in memory)
  2. `TTSManager` & core action registration (`tts_welcome`, `system_status`, `toggle_mute`, `show_overlay`)
  3. Action Plugins (`SpotifyPlugin`, `ChromeMultiMonitorPlugin`, `CursorPlugin`, `ShellPlugin`, `WebhookPlugin`)
  4. `STTEngine` (multi-provider with mock/whisper fallback)
  5. `LLMClient` & `LLMIntentRouter` (hybrid 3-tier router with 7 Vietnamese keyword categories)
  6. `GestureDetector` (configured with `dispatcher=None` to eliminate double-dispatch, routing solely via `on_gesture=self._on_gesture_event`)
  7. `AudioEngine` (receives audio blocks and feeds `gesture_detector.feed_audio_block`)
  8. `DashboardServer` & `SystemTrayController` (skipped or mocked when `headless=True`)
  9. `HardwareReporter` (tied to `HardwareMonitor`)

### 2.3 Headless Testing Best Practices for `JarvisApp`

To ensure **zero flakiness** and avoid real hardware / display bindings:
1. Initialize with `JarvisApp(headless=True, no_hot_reload=True)`.
2. For testing UI Overlay FSM during app workflows, instantiate `overlay = JarvisOverlay(headless=True)` and set `app.overlay = overlay`.
3. For testing vocalizations without real sound output, spy or mock `app.tts_manager.speak` via `monkeypatch.setattr(app.tts_manager, "speak", lambda txt, **kw: spoken_list.append((txt, kw.get("wait", False))) or True)`.
4. For testing audio recording in `_ai_voice_loop`, override `app.record_audio = lambda duration_s=None, sample_rate=None: synthetic_pcm_buffer`.
5. For testing STT transcription, assign `app.stt_engine.primary_engine = MockSTTEngine(default_transcript="...")` or monkeypatch `app.stt_engine.transcribe`.
6. For testing log isolation, configure `app.config.set("logging.file", str(tmp_path / "jarvis.log"))`.

---

## 3. Structured `[INTERACTION]` Logging Verification

### 3.1 Specification & Implementation (`jarvis/core/logger.py` & `app.py`)

Every interaction (voice command, text input, gesture trigger, or silence rejection) is recorded in `logs/jarvis.log` (or the configured log file).

#### Schema Layout:
```text
[INTERACTION] <YYYY-MM-DD HH:MM:SS> | TRIGGER: <trigger_type> | INPUT: <clean_input> | ACTION: <clean_action> | RESPONSE: <clean_response> | STATUS: <success|failed>
```

#### Key Implementation Details:
1. **Timestamping**: `datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")`.
2. **Multiline Sanitization**: Newlines and carriage returns in `input_text` and `response` are sanitized using `" ".join(str(text).split())`, guaranteeing strictly one line per interaction.
3. **Atomic File Append**: File writing is guarded by `_INTERACTION_LOCK = threading.Lock()` and uses direct append mode (`with open(target_path, "a", encoding="utf-8") as f: f.write(entry + "\n")`).
4. **Dual Output**: The entry is also emitted to `logging.getLogger("jarvis.interaction")` at `INFO` level.

### 3.2 Verification Strategy in Tests:
```python
def test_verify_interaction_logging(tmp_path):
    log_file = tmp_path / "test_jarvis.log"
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    app.config.set("logging.file", str(log_file))

    # Execute interactions
    app.process_text_command("bật đèn phòng khách", requester="user")
    app._on_gesture_event("double_clap")
    app._on_gesture_event("triple_clap")

    assert log_file.exists()
    lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if "[INTERACTION]" in l]
    assert len(lines) >= 3

    for line in lines:
        assert line.startswith("[INTERACTION]")
        assert " | TRIGGER: " in line
        assert " | INPUT: " in line
        assert " | ACTION: " in line
        assert " | RESPONSE: " in line
        assert " | STATUS: " in line
```

---

## 4. Health-Check CLI Diagnostics Verification

### 4.1 CLI Health-Check Implementation (`jarvis/cli.py:run_health_check`)

The health-check command (`python -m jarvis health-check` or `python -m jarvis health`) evaluates 5 core diagnostic areas:
1. **Platform & OS**: Prints OS platform (`win32`/`linux`) and Python version.
2. **Audio Subsystem**: Queries `sounddevice.query_devices()` and checks for input channels and default input index.
3. **TTS Engine**: Checks `tts.elevenlabs.api_key` or `ELEVENLABS_API_KEY` in environment; informs whether ElevenLabs or Windows SAPI5 fallback will be used.
4. **Windows Win32 Platform**: Checks `sys.platform == "win32"` and probes `user32.GetSystemMetrics(80)` (SM_CMONITORS).
5. **Configuration**: Verifies `ConfigManager` loads root sections.
6. **Return Code**: Returns integer `0` on success.

### 4.2 Verification Strategy in Tests:
```python
def test_cli_health_check_passes_cleanly(monkeypatch):
    from jarvis.cli import main, run_health_check
    from jarvis.core.config import ConfigManager
    import io

    cfg = ConfigManager()
    cfg.load()

    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        exit_code = run_health_check(cfg)
        output = mock_stdout.getvalue()

    assert exit_code == 0
    assert "JARVIS System Health Diagnostics" in output
    assert "Operating System:" in output
    assert "Audio Subsystem:" in output
    assert "TTS Engine:" in output
    assert "Configuration:" in output
    assert "Diagnostics completed successfully." in output
```

---

## 5. Architecture & Matrix for `tests/test_user_simulation.py`

To satisfy Requirement R1, R5, and Feature #15, the test suite must contain $\ge 13$ deterministic test cases structured without timing race conditions.

### 5.1 Test Scenarios Matrix

| Test # | Test Name | Trigger / Input | Target Behavior & Assertions |
|---|---|---|---|
| 1 | `test_user_sim_01_first_double_clap_welcome_sequence` | 1st `double_clap` | `welcome_executed` becomes `True`, welcome actions (`spotify`, `chrome_claude`, `chrome_binance`, `tts_welcome`, `cursor`) dispatched, `[INTERACTION]` logged. |
| 2 | `test_user_sim_02_second_double_clap_ai_voice_loop` | 2nd `double_clap` (with cooldown > 3s) | Triggers `_ai_voice_loop`, overlay transitions to `LISTENING` -> `THINKING` -> `RESPONSE`, spoken response generated, `[INTERACTION]` logged. |
| 3 | `test_user_sim_03_triple_clap_system_status_hardware_metrics` | `triple_clap` | Dispatches `system_status`, queries live CPU/RAM via `HardwareReporter`, speaks status in Vietnamese, `[INTERACTION]` logged. |
| 4 | `test_user_sim_04_clap_pause_clap_overlay_hud_activation` | `clap_pause_clap` | Dispatches `show_overlay`, overlay window transitions to `LISTENING`, `[INTERACTION]` logged. |
| 5 | `test_user_sim_05_zero_double_dispatch_guarantee` | Any gesture / clap stream | Asserts `GestureDetector.dispatcher is None` inside `JarvisApp`. Verifies all actions are dispatched exactly 1 time (zero double dispatch). |
| 6 | `test_user_sim_06_cooldown_debounce_suppression_and_log` | 2nd gesture at $t < 3.0s$ vs $t > 3.0s$ | First trigger executes; second trigger within 3s is suppressed and logs `"suppressed — cooldown ... remaining"`; third trigger at $t > 3.0s$ succeeds. |
| 7 | `test_user_sim_07_voice_pipeline_smart_home_lighting` | Voice: `"bật đèn phòng khách"` | Intent mapped to `home_assistant_call`, natural response `"Đang bật đèn phòng khách cho Ngài."` returned and spoken, overlay updated. |
| 8 | `test_user_sim_08_voice_pipeline_hardware_telemetry_cpu_ram` | Voice: `"nhiệt độ CPU"` / `"RAM"` | Intent mapped to `hardware_telemetry_check`, natural response with temperature / RAM returned and spoken, overlay updated. |
| 9 | `test_user_sim_09_voice_pipeline_spotify_music_control` | Voice: `"bật nhạc"` / `"mở spotify bài Nơi này có anh"` | Intent mapped to `spotify`, search query extracted, natural response returned and spoken. |
| 10 | `test_user_sim_10_voice_loop_silence_graceful_rejection` | Audio: Pure silence / empty STT | Gracefully handled without crash: speaks `"Tôi không nghe thấy gì cả. Vui lòng thử lại."`, overlay displays `"(không nghe thấy)"`, log records `STATUS: failed`. |
| 11 | `test_user_sim_11_overlay_fsm_transitions_and_rapid_cycling` | 15x state transitions | Verifies `IDLE` -> `LISTENING` -> `THINKING` -> `RESPONSE` -> `HIDDEN`. Confirms breathing gradient and typing dot timers clean up on hide. |
| 12 | `test_user_sim_12_stt_and_tts_offline_fallbacks` | Missing / Invalid API keys | STT falls back gracefully without crashing; TTS cascades to Windows SAPI5 when ElevenLabs API key is missing or invalid. |
| 13 | `test_user_sim_13_startup_greeting_and_interaction_logging_e2e` | `app.start()` + multi-turn interactions | Startup intro vocalized (`"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`), all multi-turn interactions appended atomically to log. |
| 14 | `test_user_sim_14_cli_health_check_all_green` | `python -m jarvis health-check` | Diagnostics run cleanly across OS, Audio, TTS, Win32, Config; returns exit code 0. |

---

## 6. Avoiding Flakiness: Anti-Patterns & Best Practices

1. **Anti-Pattern: Uncontrolled `time.sleep` in async threads**
   - *Fix*: In tests invoking background threads (`_welcome` or `_ai_voice_loop`), use `threading.Event` synchronization or a helper `_wait_for_condition(predicate, timeout=2.0)` rather than hard-coded arbitrary sleeps.
2. **Anti-Pattern: Shared monotonic clock across tests causing cooldown suppression**
   - *Fix*: Create a fresh `JarvisApp` instance per test using pytest fixture. When testing cooldown explicitly, mock `time.monotonic` with deterministic timestamps: `mock_time = [100.0]; monkeypatch.setattr(time, "monotonic", lambda: mock_time[0])`.
3. **Anti-Pattern: Blocking `sounddevice.rec` in headless environments**
   - *Fix*: `JarvisApp.record_audio()` automatically returns a silent float32 array in `headless=True` mode, or can be overridden via `app.record_audio = lambda ...: synthetic_buffer`.
4. **Anti-Pattern: Tkinter GUI window creation failing in headless CI**
   - *Fix*: Use `JarvisOverlay(headless=True)`, which executes the complete state machine FSM and animation gradient logic without calling Tkinter window geometry.
5. **Anti-Pattern: Shared log file lock contention**
   - *Fix*: Use `tmp_path` fixture for each test and point `app.config.set("logging.file", str(tmp_path / "jarvis.log"))`.
