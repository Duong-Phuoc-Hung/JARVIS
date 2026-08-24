# Comprehensive Survey Report: JARVIS Core Lifecycle, Gesture Detection, and Voice AI Pipeline

**Author**: Explorer 1  
**Date**: 2026-08-22  
**Scope**: `jarvis/core/app.py`, `jarvis/gesture/detector.py`, `jarvis/gesture/patterns.py`, `jarvis/gesture/models.py`, `jarvis/core/dispatcher.py`, `jarvis/ui/overlay.py`, `jarvis/stt/engine.py`, `jarvis/llm/router.py`, and related test fixtures.

---

## 1. Executive Summary

This investigation analyzed the entire acoustic transient detection, action dispatching, and voice interaction architecture in JARVIS. We traced the lifecycle from raw audio capture in `AudioEngine` through DSP spike filtering, `GestureDetector` rhythmic disambiguation, `JarvisApp` gesture routing, double-clap state management, voice loop execution, and UI overlay presentation.

Key findings:
1. **Double-Dispatch Prevention Architecture**: Cleanly implemented by passing `dispatcher=None` to `GestureDetector` in `JarvisApp.initialize()`, routing all events strictly through `on_gesture=self._on_gesture_event`.
2. **Double-Clap Dual Flow**:
   - 1st double clap successfully triggers the full welcome sequence (`spotify`, `chrome_claude`, `chrome_binance`, `cursor`, `tts_welcome`) once and sets `welcome_executed = True`.
   - 2nd double clap enters the AI Voice Loop (`overlay.show_listening` -> TTS prompt -> STT record -> LLM parse -> action dispatch -> TTS speak -> overlay response).
3. **Identified Critical Bugs & Gaps**:
   - **Clap-Pause-Clap action mismatch**: `app.py:411` hardcodes `toggle_mute` despite `default_config.yaml:65` and requirements specifying `show_overlay`.
   - **`sounddevice.rec()` hard dependency in voice loop**: `_ai_voice_loop` calls `_sd.rec()` directly, which blocks for 5s and crashes in headless/CI test environments.
   - **Static system status**: `_handle_system_status` returns a hardcoded mock message instead of querying real CPU/RAM/temperature metrics via `HardwareReporter`.
   - **Cooldown log visibility**: Suppressed triggers are logged at `log.debug` rather than `log.info`.
   - **Duplicate TTS invocation**: `process_text_command` and `_ai_voice_loop` both attempt to vocalize responses.
   - **Missing startup greeting**: `JarvisApp.start()` lacks the startup intro speech requirement.

---

## 2. Architecture & Module Deep-Dive

### 2.1 `jarvis/core/app.py` — Application Coordinator

`JarvisApp` coordinates all 15 core requirements across audio capture, AI reasoning, plugin execution, and UI presentation.

```
                  ┌──────────────────────┐
                  │     AudioEngine      │
                  │  (SoundDevice/Mock)  │
                  └──────────┬───────────┘
                             │ audio blocks (40ms, 1764 samples)
                             ▼
                  ┌──────────────────────┐
                  │   GestureDetector    │
                  │ (DSP + StateMachine) │
                  └──────────┬───────────┘
                             │ on_gesture(pattern_name, conf)
                             ▼
                  ┌──────────────────────┐
                  │ JarvisApp Lifecycle  │
                  │  _on_gesture_event   │
                  └──────────┬───────────┘
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   [double_clap]       [triple_clap]    [clap_pause_clap]
   (1st vs 2nd)        (system_status)   (show_overlay)
```

#### Lifecycle & Subsystem Initialization Order
1. `ConfigManager`: loads `default_config.yaml`, starts hot-reload file watcher.
2. `EventBus` & `ActionDispatcher`: registers system actions (`tts_welcome`, `system_status`, `toggle_mute`, `show_overlay`).
3. `PluginRegistry`: registers and initializes built-in plugins (`SpotifyPlugin`, `ChromeMultiMonitorPlugin`, `CursorPlugin`, `ShellPlugin`, `WebhookPlugin`).
4. `STTEngine`: multi-provider speech transcriber (Whisper API, Windows SAPI, Mock).
5. `LLMClient` & `LLMIntentRouter`: multi-provider LLM client (OpenAI, Gemini, Claude, Ollama) and fast rule router.
6. `GestureDetector`: initialized with `dispatcher=None` to prevent double-dispatch, hooking `on_gesture=self._on_gesture_event`.
7. `AudioEngine`: captures real-time microphone audio frames and feeds `gesture_detector.feed_audio_block`.
8. `DashboardServer` & `SystemTrayController` & `JarvisOverlay`: UI controllers.

---

### 2.2 `jarvis/gesture/detector.py` — State Machine & Rhythmic Disambiguation

`GestureDetector` processes acoustic transient spikes detected by `AudioDSPProcessor` (RMS energy + EMA dynamic noise floor tracker + Schmitt trigger hysteresis).

#### Timing Thresholds
| Parameter | Default Value | Purpose |
|---|---|---|
| `min_double_gap_s` | 0.05s (50ms) | Minimum interval between claps (filters acoustic bounce/echo) |
| `max_double_gap_s` | 0.35s (350ms) | Maximum interval between claps for double-clap |
| `cooldown_s` | 0.45s (450ms) | Post-trigger internal debounce cooldown |
| `triple_clap_gap_s` | 0.40s (400ms) | Maximum gap between consecutive claps in triple-clap |
| `pause_min_s` | 0.50s (500ms) | Minimum syncopated pause for clap-pause-clap |
| `pause_max_s` | 1.20s (1200ms) | Maximum syncopated pause for clap-pause-clap |
| `disambiguation_timeout_s`| 0.35s (350ms) | Window to wait after 2nd clap before deciding double-clap |

#### State Machine Flow
- `IDLE`: Initial state.
  * Clap 1 arrives -> buffer = `[c1]`, state = `WAIT_CLAP_2`.
- `WAIT_CLAP_2`:
  * If Clap 2 arrives with `0.50s <= gap1 <= 1.20s`: immediate match -> `CLAP_PAUSE_CLAP`.
  * If Clap 2 arrives with `0.05s <= gap1 <= 0.35s`:
    - If multi-clap patterns (triple clap or syncopation) enabled -> state = `PENDING_DISAMBIGUATION`, deadline = `now + 0.35s`.
    - If only double clap enabled -> immediate match -> `DOUBLE_CLAP`.
  * If `gap1 < 0.05s`: dropped as echo/chatter.
  * If `0.35s < gap1 < 0.50s` (dead-zone) or `gap1 > 1.20s`: resets buffer to `[c2]` and stays in `WAIT_CLAP_2`.
- `PENDING_DISAMBIGUATION`:
  * If Clap 3 arrives:
    - If `0.05s <= gap2 <= 0.40s` and `total_duration <= 0.85s`: matches `TRIPLE_CLAP`.
    - If `0.50s <= gap2 <= 1.20s`: matches 3-clap syncopation `CLAP_PAUSE_CLAP`.
    - If mismatched: resets buffer to `[c3]`, state = `WAIT_CLAP_2`.
  * If clock reaches deadline without 3rd clap (`tick(now)`):
    - Disambiguates to `DOUBLE_CLAP` and triggers.

---

### 2.3 Double-Clap Detailed Flow

```
[User Double Claps] ──► GestureDetector (0.05s <= gap <= 0.35s)
                               │
                               ▼
                    _on_gesture_event("double_clap")
                               │
                Is elapsed < 3.0s cooldown?
                     ├── YES ──► Suppress & Return (log "suppressed")
                     └── NO
                          │
                   Is welcome_executed == False?
                          │
         ┌────────────────┴────────────────┐
         ▼ (1st Time)                      ▼ (Subsequent Times)
   WELCOME SEQUENCE                    AI VOICE LOOP
   - welcome_executed = True           - overlay.show_listening()
   - Spotify playback                  - TTS: "Vâng thưa Ngài, tôi đang lắng nghe."
   - Chrome Claude (Monitor 1)         - tray.update_status(LISTENING)
   - Chrome Binance (Monitor 3)        - Record audio (5s) / Mock STT
   - Cursor IDE launch/focus           - stt_engine.transcribe(audio)
   - TTS Welcome Speech                - overlay.show_thinking(transcript)
                                       - process_text_command(transcript)
                                         * LLMIntentRouter (Tier 1/2/3)
                                         * ActionDispatcher (execute tool)
                                         * TTSManager.speak(response)
                                       - overlay.show_response(transcript, resp)
                                       - tray.update_status(ACTIVE)
```

---

## 3. Cooldown Logic & Double-Dispatch Prevention

### 3.1 Cooldown Enforcement
In `JarvisApp._on_gesture_event` (`app.py:260-275`):
- Tracks `self._pattern_last_fired[pattern_name]`.
- Checks `elapsed = now - last`.
- If `elapsed < self._action_fanout_cooldown_s` (3.0s), the gesture is suppressed.
- **Identified Defect**: The suppression is logged via `log.debug(...)`. In standard production runs where log level is `INFO`, suppression events will not appear in `logs/jarvis.log`. This should be upgraded to `log.info(...)` to satisfy Acceptance Criteria.

### 3.2 Double-Dispatch Prevention
In `GestureDetector._dispatch_result` (`detector.py:355-395`):
- It can trigger via:
  1. `on_gesture` callback
  2. `event_bus.publish("gesture.detected", ...)`
  3. `self.dispatcher.dispatch_action(...)` (if dispatcher is passed to detector)
- In `JarvisApp.initialize` (`app.py:148-153`), `dispatcher=None` is explicitly passed to `GestureDetector`.
- This ensures that only `JarvisApp._on_gesture_event` performs action dispatching, eliminating any possibility of double-firing.

---

## 4. Synthetic Audio Clap Injection for User Simulation Tests

We have verified 3 distinct injection tiers that can be utilized in the user simulation test suite:

### Tier 1: Discrete Event Injection (State Machine Unit Tests)
```python
detector = GestureDetector()
c1 = ClapEvent(timestamp=1.00, amplitude=0.85)
c2 = ClapEvent(timestamp=1.15, amplitude=0.85)  # gap = 150ms
detector.feed_clap(c1)
detector.feed_clap(c2)
result = detector.tick(now=1.50)  # past disambiguation timeout
assert result.gesture_type == GestureType.DOUBLE_CLAP
```

### Tier 2: Continuous PCM Synthesis (DSP + Pattern Recognition)
Using `AudioSynthesizer` from `tests/conftest.py`:
```python
synth = AudioSynthesizer(default_sample_rate=44100)
# Generate double-clap PCM buffer (150ms gap)
pcm_double = synth.generate_double_clap(gap_s=0.15, leading_silence_s=0.1, trailing_silence_s=0.5)

detector = GestureDetector()
events = detector.process_stream(pcm_double)
assert len(events) == 1
assert events[0].pattern_type == "DOUBLE_CLAP"
```

### Tier 3: Full End-to-End Application Simulation
```python
app = JarvisApp(headless=True, no_hot_reload=True)
app.initialize()

# Mock STT to return specific test commands
app.stt_engine.primary_engine = MockSTTEngine(default_transcript="kiểm tra nhiệt độ cpu")

# 1. First Double-Clap Simulation -> Welcome Sequence
app._on_gesture_event("double_clap")
time.sleep(0.1)
assert app.welcome_executed is True

# 2. Rapid Trigger Simulation -> Cooldown Suppression
app._on_gesture_event("double_clap")  # elapsed < 3.0s -> suppressed!

# 3. Second Double-Clap Simulation (>3.0s later) -> AI Voice Loop
time.sleep(3.1)
app._on_gesture_event("double_clap")
# Verify AI Voice Loop execution and overlay state transitions

# 4. Triple Clap Simulation -> System Status
app._on_gesture_event("triple_clap")
```

---

## 5. Comprehensive Bug, Race Condition, Edge Case & Gap Inventory

| ID | Component | Location | Issue Description | Impact | Recommended Fix |
|---|---|---|---|---|---|
| **BUG-01** | App Gesture Routing | `jarvis/core/app.py:411` | `clap_pause_clap` hardcoded to `toggle_mute` | Config specifies `show_overlay`. `toggle_mute` is wrong action. | Read actions from `config.get("gesture.patterns.clap_pause_clap.actions")` or dispatch `show_overlay`. |
| **BUG-02** | Default Pattern Config | `jarvis/gesture/patterns.py:50` | `CLAP_PAUSE_CLAP` default action is `["toggle_mute"]` | Default pattern conflicts with `default_config.yaml` (`show_overlay`). | Update default pattern action to `["show_overlay"]`. |
| **BUG-03** | AI Voice Loop | `jarvis/core/app.py:340-353` | Direct `sounddevice.rec()` in `_ai_voice_loop` | Blocks for 5s, crashes in CI / mock / headless environments. | Wrap audio recording with mock/headless fallback support. |
| **BUG-04** | AI Voice Loop | `jarvis/core/app.py:388-390` | Inconsistent / duplicate TTS speak logic | `process_text_command` already speaks, `_ai_voice_loop` has dead/confusing duplicate condition. | Remove redundant TTS speak check from `_ai_voice_loop`. |
| **BUG-05** | Core Actions | `jarvis/core/app.py:230-235` | `_handle_system_status` returns hardcoded static string | Triple-clap does not read actual CPU/RAM/temperature metrics. | Connect `HardwareReporter().format_voice_summary(lang="vi")` into handler. |
| **BUG-06** | Cooldown Logging | `jarvis/core/app.py:269` | `log.debug` used for cooldown suppression | Suppression not visible under default `INFO` logging level. | Change `log.debug` to `log.info`. |
| **BUG-07** | Startup UX | `jarvis/core/app.py:513-549` | Startup welcome greeting not vocalized on `app.start()` | Fails requirement R4 (startup self-introduction). | Call `tts_manager.speak` with greeting on startup. |
| **BUG-08** | TTS Welcome | `jarvis/tts/manager.py:141-155` | Static single welcome phrase | Fails requirement R4 (random non-repeating greetings). | Add randomized greeting phrase list support. |
| **BUG-09** | Mic Mute Action | `jarvis/core/app.py:237` | `_handle_toggle_mute` only updates tray boolean | Does not pause/resume `AudioEngine` stream. | Call `audio_engine.pause_stream()` / `resume_stream()` on mute toggle. |
| **BUG-10** | Overlay UX | `jarvis/ui/overlay.py` | Missing breathing animation and typing dots | Fails requirement R4 visual feedback requirements. | Add animated breathing dot in LISTENING and typing dots in THINKING. |
| **BUG-11** | STT Provider Resolution | `jarvis/stt/engine.py:645-665` | `"web_speech"` config provider not explicitly handled | Falls back to generic mock without clear warning. | Add explicit `"web_speech"` resolution mapping to Windows Speech STT. |
| **BUG-12** | Keyword Router | `jarvis/llm/router.py:188-262` | Rule engine missing "thời tiết", "nhắc nhở", "tắt máy" | Offline keyword fallback incomplete for R3 requirements. | Expand `rule_engine` with all 7 keyword categories in Vietnamese. |

---

## 6. Implementation Plan for Workers & Reviewers

1. **Fix `app.py` & `patterns.py` Gesture Routing**:
   - Change `clap_pause_clap` dispatch to `show_overlay`.
   - Upgrade cooldown log to `log.info`.
   - Connect `_handle_system_status` to `HardwareReporter`.
   - Update `_handle_toggle_mute` to pause/resume `audio_engine`.
   - Add startup greeting vocalization to `JarvisApp.start()`.
2. **Harden Voice AI Loop**:
   - Refactor audio recording in `_ai_voice_loop` to support mock / synthetic buffers cleanly.
   - Clean up TTS speaking deduplication.
3. **Upgrade LLM Keyword Router & STT Fallback**:
   - Add all 7 Vietnamese keyword categories in `jarvis/llm/router.py`.
   - Explicitly handle `"web_speech"` provider in `jarvis/stt/engine.py`.
4. **Enhance Overlay UX**:
   - Implement breathing dot animation during LISTENING.
   - Implement typing indicator during THINKING.
5. **Add User Simulation Test Suite**:
   - Create `tests/test_user_simulation_voice_pipeline.py` with ≥ 10 deterministic tests covering synthetic clap injection, double-clap 1st vs 2nd flow, cooldown enforcement, triple-clap system status, and overlay transitions.
