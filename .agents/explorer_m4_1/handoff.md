# Handoff Report: Automated User Simulation Test Suite & Full Regression (Milestone M4)

## 1. Observation

Direct code observations from inspecting the codebase:

1. **Gesture Routing Architecture (`jarvis/core/app.py:176-187`)**:
   ```python
   # NOTE: dispatcher is intentionally NOT passed here — all routing goes through
   # on_gesture callback in _on_gesture_event to avoid double-dispatch.
   dsp_cfg = self.config.get("gesture.dsp", {})
   gesture_cfg = self.config.get("gesture", {})
   self.gesture_detector = GestureDetector(
       config=gesture_cfg,
       dispatcher=None,          # Prevent double-dispatch
       event_bus=self.event_bus,
       on_gesture=self._on_gesture_event,
   )
   ```

2. **Acoustic Audio Feed Path (`jarvis/core/app.py:189-199`)**:
   `AudioEngine` is wired with `on_audio_block=self.gesture_detector.feed_audio_block`. In `jarvis/audio/engine.py:431-446`, `feed_audio(buffer, virtual_time=True)` streams audio blocks into `feed_audio_block()`, which performs DSP transient detection and routes recognised patterns to `app._on_gesture_event()`.

3. **First vs. Second Double Clap Logic (`jarvis/core/app.py:411-499`)**:
   - `self.welcome_executed = False` on startup (`jarvis/core/app.py:96`).
   - First double clap checks `if not self.welcome_executed:`, sets `self.welcome_executed = True`, logs interaction (`trigger="GESTURE:double_clap"`, `action="welcome_sequence"`), and spawns `Welcome-Sequence` thread executing `["spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"]`.
   - Second double clap triggers `else:` branch, spawning `AI-Voice-Loop` thread: `overlay.show_listening()` -> `tts.speak("Vâng thưa Ngài, tôi đang lắng nghe.")` -> `record_audio()` -> `stt_engine.transcribe()` -> `overlay.show_thinking()` -> `process_text_command()` (LLM router + action dispatch + TTS response) -> `overlay.show_response()`.

4. **Triple Clap & Clap-Pause-Clap Routing (`jarvis/core/app.py:504-538`)**:
   - Triple clap (`pattern_name == "triple_clap"`) dispatches `system_status` action, vocalizing live CPU/RAM metrics via `HardwareReporter` (`jarvis/core/app.py:273-328`).
   - Clap-pause-clap (`pattern_name == "clap_pause_clap"`) dispatches `show_overlay` action, invoking `overlay.show_listening()` (`jarvis/core/app.py:336-341`).

5. **3.0s Debounce Cooldown (`jarvis/core/app.py:98-101, 383-398`)**:
   `self._action_fanout_cooldown_s: float = 3.0`. When `_on_gesture_event` is called, `elapsed = now - last`. If `elapsed < cooldown`, it logs `"Gesture [%s] suppressed — cooldown %.1fs remaining."` and returns immediately.

6. **Overlay HUD States (`jarvis/ui/overlay.py:25-32, 189-221`)**:
   `OverlayState` has 5 states: `IDLE`, `LISTENING`, `THINKING`, `RESPONSE`, `HIDDEN`. `JarvisOverlay` supports headless mode (`headless=True`) with full state tracking and transitions.

7. **Deterministic Testing Fixtures (`tests/conftest.py:39-370`)**:
   `mock_audio_stream` provides `generate_double_clap()`, `generate_triple_clap()`, and `generate_clap_pause_clap()`. `MockHardwareProvider` provides controllable CPU, RAM, GPU, and disk metrics.

---

## 2. Logic Chain

1. From **Observation 2**, synthetic audio can be injected into `app.audio_engine.feed_audio(pcm)` or `app.gesture_detector.feed_clap(clap)`. The DSP and state machine recognize the patterns and invoke `app._on_gesture_event`.
2. From **Observation 1 & 3**, when `_on_gesture_event("double_clap")` is invoked for the first time, `app.welcome_executed` is `False`, triggering the welcome sequence exactly once and flipping `welcome_executed` to `True`. Subsequent double claps enter the `AI-Voice-Loop`.
3. From **Observation 3 & 7**, by mocking `app.stt_engine.primary_engine` with `MockSTTEngine` and providing a headless `JarvisOverlay`, the entire AI voice loop (STT -> LLM Intent Router -> Dispatcher -> TTS -> Overlay) can be tested deterministically in headless CI with zero real microphone or cloud API requirements.
4. From **Observation 4**, triple clap and clap-pause-clap are wired to `system_status` and `show_overlay` actions respectively. Their execution, live telemetry formatting, TTS speech, and interaction logging can be tested synchronously or with brief thread synchronization.
5. From **Observation 1**, passing `dispatcher=None` to `GestureDetector` guarantees that `GestureDetector` does not dispatch actions directly; only `JarvisApp._on_gesture_event` dispatches them, ensuring zero double-dispatch.
6. From **Observation 5**, firing two events within 3.0 seconds causes the second event to be suppressed with an INFO log. Advancing the simulated timestamp past 3.0s re-enables execution.
7. Therefore, a comprehensive 14-test suite (`tests/test_user_simulation.py`) completely covers all requirements of Milestone M4 (R1 and R5).

---

## 3. Caveats

1. **Threading Synchronization**: `Welcome-Sequence` and `AI-Voice-Loop` execute in background daemon threads (`threading.Thread`). Simulation tests must use polling predicate helpers (`_wait_for_condition`) with timeouts (e.g. 2.0-3.0s) rather than fixed sleeps to avoid flaky tests under heavy CI load.
2. **Virtual Time in AudioEngine vs. Monotonic Time in JarvisApp**: `AudioEngine.feed_audio` uses virtual time for DSP block ticks, but `JarvisApp._on_gesture_event` checks `time.monotonic()`. When feeding multiple gestures in the same test function, `sim_app._pattern_last_fired` timestamps must be cleared or set back by > 3.0s to avoid triggering the debounce cooldown.
3. **Headless Overlay**: In headless testing environments (CI/Linux/virtual machines), `JarvisOverlay(headless=True)` is used to track state properties (`overlay.state`, `overlay.user_text`, `overlay.jarvis_text`) without requiring an active Tkinter X11/Win32 display server.

---

## 4. Conclusion

The architecture of JARVIS is ready for the Milestone M4 user simulation test suite.
A complete, production-grade test suite consisting of 14 deterministic tests has been designed and specified in `d:/Software GitCode/JARVIS/.agents/explorer_m4_1/analysis.md`.
The test file to be created is `tests/test_user_simulation.py`.

### Test Suite Structure:
- **Audio Gesture Injection**: `test_sim_audio_engine_double_clap_injection`, `test_sim_audio_engine_triple_clap_injection`, `test_sim_audio_engine_clap_pause_clap_injection`.
- **First vs. Second Double Clap**: `test_sim_first_double_clap_welcome_sequence_once`, `test_sim_second_double_clap_triggers_ai_voice_loop`.
- **Voice AI Loop Scenarios**: `test_sim_voice_loop_smart_keyword_home_assistant`, `test_sim_voice_loop_smart_keyword_hardware_status`, `test_sim_voice_loop_silence_rejection`, `test_sim_voice_loop_error_recovery`.
- **Gesture Action Dispatch**: `test_sim_triple_clap_system_status_live_telemetry`, `test_sim_clap_pause_clap_shows_overlay`.
- **Safety & Cooldown**: `test_sim_zero_double_dispatch_verification`, `test_sim_3s_debounce_cooldown_enforcement`.
- **Overlay & E2E Session**: `test_sim_overlay_full_state_lifecycle`, `test_sim_full_user_session_e2e`.

---

## 5. Verification Method

Once Worker implements `tests/test_user_simulation.py`:

1. **Run the simulation test suite**:
   ```bash
   python -m pytest tests/test_user_simulation.py -v
   ```
   **Expected**: 14/14 passed in < 15 seconds.

2. **Run full regression test suite**:
   ```bash
   python -m pytest tests/ -x -q
   ```
   **Expected**: $\ge 532$ tests passed (518 existing + 14 simulation tests).

3. **Run CLI health check**:
   ```bash
   python -m jarvis health-check
   ```
   **Expected**: All subsystem checks green.
