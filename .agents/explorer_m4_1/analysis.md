# Analysis Report: Automated User Simulation Test Suite & Full Regression (Milestone M4)

## 1. Executive Summary

This investigation designs the comprehensive automated user simulation test suite (`tests/test_user_simulation.py`) for Milestone M4 of the JARVIS desktop assistant. The test suite verifies realistic user interactions with zero cloud/hardware dependencies, testing the full lifecycle across acoustic gesture injection, state machine transitions, AI voice loop processing, action dispatching, zero double-dispatch guarantees, and cooldown debounce enforcement.

### Key Findings Summary:
1. **Audio Injection Path**: `mock_audio_stream` in `tests/conftest.py` generates deterministic PCM buffers for `double_clap`, `triple_clap`, and `clap_pause_clap`. These buffers are fed into `app.audio_engine.feed_audio(pcm, virtual_time=True)`, processed via `AudioDSPProcessor` and `GestureDetector.feed_audio_block()`, and dispatched via `app._on_gesture_event()`.
2. **First vs. Second Double Clap**: `app.welcome_executed` starts `False`. The first double clap triggers the welcome sequence thread (`spotify`, `chrome_claude`, `chrome_binance`, `tts_welcome`, `cursor`) and sets `app.welcome_executed = True`. Subsequent double claps spawn the `AI-Voice-Loop` thread.
3. **AI Voice Loop Pipeline**: Subsequent double claps invoke `overlay.show_listening()` -> `tts.speak("Vâng thưa Ngài...")` -> `app.record_audio()` -> `stt_engine.transcribe()` -> `overlay.show_thinking()` -> `llm_router.parse_intent()` -> `dispatcher.dispatch_action()` -> `tts.speak(response)` -> `overlay.show_response()` -> `log_interaction()`.
4. **Triple Clap & Clap-Pause-Clap**: Triple clap triggers `system_status` (`_handle_system_status`), fetching live CPU/RAM metrics and vocalizing them. Clap-pause-clap triggers `show_overlay` (`_handle_show_overlay`), opening the HUD overlay.
5. **Zero Double-Dispatch Architecture**: In `app.py:181-186`, `GestureDetector` is initialized with `dispatcher=None`, ensuring action dispatching is handled solely by `JarvisApp._on_gesture_event()`, eliminating double execution.
6. **3.0s Debounce Cooldown**: In `app.py:98-101, 383-398`, `_action_fanout_cooldown_s = 3.0` suppresses any re-trigger within 3.0 seconds, logging `"Gesture [%s] suppressed — cooldown %.1fs remaining."`.

---

## 2. Component Analysis & Call Chains

### 2.1 Synthetic Audio Clap Injection & Routing
- **Entry point**: `app.audio_engine.feed_audio(pcm, virtual_time=True)` (`jarvis/audio/engine.py:431-446`)
- **Block slicing**: Slices PCM into chunks of `block_size` (1764 samples at 44.1kHz = 40ms) and calls `_dispatch_block(chunk, timestamp)`.
- **DSP & Transient Detection**: `gesture_detector.feed_audio_block(block, timestamp)` (`jarvis/gesture/detector.py:152-177`) runs `dsp.process_block(block)`. When `is_transient == True`, creates a `ClapEvent` and calls `feed_clap(clap)`.
- **Temporal Disambiguation**:
  - Double clap transient 1 sets state to `WAIT_CLAP_2`.
  - Double clap transient 2 (gap 0.05s-0.35s) enters `PENDING_DISAMBIGUATION` with deadline `t + 0.35s` (since triple clap is enabled).
  - Trailing silence causes `tick(now)` to expire the disambiguation deadline and call `_emit_trigger(GestureType.DOUBLE_CLAP)`.
- **Routing**: `_dispatch_result()` invokes `self.on_gesture("double_clap", 1.0)` -> `JarvisApp._on_gesture_event("double_clap", 1.0)` (`jarvis/core/app.py:374`).

### 2.2 First Double Clap vs. Second Double Clap Mechanics
- **Flag**: `self.welcome_executed = False` (`jarvis/core/app.py:96`).
- **First trigger** (`jarvis/core/app.py:412-435`):
  ```python
  if pattern_name == "double_clap":
      if not self.welcome_executed:
          self.welcome_executed = True
          self.log_interaction(...)
          threading.Thread(target=_welcome, daemon=True, name="Welcome-Sequence").start()
  ```
  Actions dispatched: `["spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"]`.
- **Second trigger** (`jarvis/core/app.py:436-499`):
  ```python
  else:
      log.info("AI voice interaction triggered.")
      threading.Thread(target=_ai_voice_loop, daemon=True, name="AI-Voice-Loop").start()
  ```

### 2.3 AI Voice Loop Execution Chain
1. `overlay.show_listening()` -> State `OverlayState.LISTENING`, breathing dot animation.
2. `tts_manager.speak("Vâng thưa Ngài, tôi đang lắng nghe.", wait=True)` -> Spoken audio queue.
3. `tray_controller.update_status(TrayStatus.LISTENING)` -> Tray icon update.
4. `audio_flat = self.record_audio()` -> Decoupled microphone capture or headless silent buffer.
5. `transcript = self.stt_engine.transcribe(audio_flat)` -> STT transcription (or MockSTTEngine).
6. Silence Check:
   - If empty: `overlay.show_response("(không nghe thấy)", ...)`, `tts_manager.speak(...)`, `log_interaction(status="failed")`, return.
7. `overlay.show_thinking(transcript)` -> State `OverlayState.THINKING`, typing dots animation (`.`, `..`, `...`).
8. `result = self.process_text_command(transcript, requester="voice")`:
   - `intent_result = self.llm_router.parse_intent(transcript)` (Fast regex / Smart keyword / LLM).
   - `action_result = self.dispatcher.dispatch_action(intent_result.action_name, payload=...)`.
   - `response_text` formatted from action result or natural Vietnamese template.
   - `tts_manager.speak(response_text, wait=False)`.
9. `overlay.show_response(transcript, response_text)` -> State `OverlayState.RESPONSE`, hint `"💡 Double clap để hỏi tiếp"`, auto-hide timer.
10. `tray_controller.update_status(TrayStatus.ACTIVE)`.
11. `log_interaction(trigger="VOICE", ...)` -> Appends formatted single line to `logs/jarvis.log`.

### 2.4 Triple Clap System Status Action
- Dispatches `system_status` (`jarvis/core/app.py:504-518`).
- Handler `_handle_system_status` (`jarvis/core/app.py:273-328`):
  - Fetches metrics from `HardwareReporter` (or `MockHardwareProvider`).
  - Calls `hardware_reporter.format_voice_summary(metrics, lang="vi")`.
  - Speaks voice summary via `tts_manager.speak(msg, wait=False)`.
  - Returns `{"status": "healthy", "message": msg, "metrics": metrics_dict}`.
  - Logs interaction with `trigger="GESTURE:triple_clap"`.

### 2.5 Clap-Pause-Clap Overlay HUD Action
- Dispatches `show_overlay` (`jarvis/core/app.py:523-537`).
- Handler `_handle_show_overlay` (`jarvis/core/app.py:336-341`):
  - Invokes `self.overlay.show_listening()`.
  - Returns `{"status": "overlay_shown"}`.
  - Logs interaction with `trigger="GESTURE:clap_pause_clap"`.

### 2.6 Zero Double-Dispatch Safeguard
- **Root cause of duplicate dispatch**: In early builds, `GestureDetector` directly dispatched actions to `ActionDispatcher` AND fired `on_gesture` callback to `JarvisApp`, which also dispatched actions.
- **Fix in `app.py:183`**:
  ```python
  self.gesture_detector = GestureDetector(
      config=gesture_cfg,
      dispatcher=None,          # Prevent double-dispatch
      event_bus=self.event_bus,
      on_gesture=self._on_gesture_event,
  )
  ```
- **Verification method**: Hook spy callback on `dispatcher.dispatch_action` and count invocations per trigger. Count must strictly equal 1 per configured action.

### 2.7 3.0s Debounce Cooldown Guard
- **Configuration**: `self._action_fanout_cooldown_s: float = 3.0` (`jarvis/core/app.py:101`).
- **Mechanism** (`jarvis/core/app.py:385-398`):
  ```python
  now = _time.monotonic()
  last = self._pattern_last_fired.get(pattern_name, 0.0)
  elapsed = now - last

  cooldown = self._action_fanout_cooldown_s
  if elapsed < cooldown:
      log.info(
          "Gesture [%s] suppressed — cooldown %.1fs remaining.",
          pattern_name, cooldown - elapsed,
      )
      return
  self._pattern_last_fired[pattern_name] = now
  ```

---

## 3. Test Suite Architecture for `tests/test_user_simulation.py`

### Proposed Test Inventory (14 Test Cases):

| # | Test Function Name | Tested Scenario | Assertions / Validations |
|---|-------------------|-----------------|--------------------------|
| 1 | `test_sim_audio_engine_double_clap_injection` | Inject double-clap PCM into `AudioEngine` | `GestureDetector` recognizes double clap, routes to `_on_gesture_event`, welcome actions triggered |
| 2 | `test_sim_audio_engine_triple_clap_injection` | Inject triple-clap PCM into `AudioEngine` | `GestureDetector` recognizes triple clap, routes to `_on_gesture_event`, `system_status` triggered |
| 3 | `test_sim_audio_engine_clap_pause_clap_injection` | Inject clap-pause-clap PCM into `AudioEngine` | `GestureDetector` recognizes clap-pause-clap, routes to `_on_gesture_event`, `show_overlay` triggered |
| 4 | `test_sim_first_double_clap_welcome_sequence_once` | First double-clap activation | `welcome_executed` transitions `False` -> `True`, all 5 welcome actions run, interaction logged |
| 5 | `test_sim_second_double_clap_triggers_ai_voice_loop` | Second double-clap with `welcome_executed=True` | `AI-Voice-Loop` spawns, STT + LLM run, TTS speaks response, overlay transitions |
| 6 | `test_sim_voice_loop_smart_keyword_home_assistant` | Voice loop with transcript "bật đèn phòng khách" | Keyword router triggers `home_assistant_call`, speaks Vietnamese response |
| 7 | `test_sim_voice_loop_smart_keyword_hardware_status` | Voice loop with transcript "nhiệt độ hệ thống" | Keyword router triggers `hardware_status_query`, speaks CPU/RAM telemetry |
| 8 | `test_sim_voice_loop_silence_rejection` | Voice loop with empty/silent recording | Graceful rejection, overlay shows "(không nghe thấy)", TTS speaks retry prompt |
| 9 | `test_sim_voice_loop_error_recovery` | Voice loop where STT/LLM raises exception | Graceful error catch, TTS speaks error, no crash |
| 10 | `test_sim_triple_clap_system_status_live_telemetry` | Triple-clap system status query | `_handle_system_status` executes, queries hardware metrics, speaks CPU/RAM summary |
| 11 | `test_sim_clap_pause_clap_shows_overlay` | Clap-pause-clap gesture HUD activation | `show_overlay` action executes, `overlay.show_listening()` invoked |
| 12 | `test_sim_zero_double_dispatch_verification` | Zero double-dispatch across all gestures | Each action executed strictly 1 time per gesture trigger |
| 13 | `test_sim_3s_debounce_cooldown_enforcement` | Cooldown enforcement within 3.0s | Trigger at $t_0$ runs; trigger at $t_0+1.0\text{s}$ suppressed with log; trigger at $t_0+3.1\text{s}$ runs |
| 14 | `test_sim_full_user_session_e2e` | End-to-end multi-step synthetic user session | Full session: Startup intro -> Double clap 1 (welcome) -> Double clap 2 (voice query) -> Triple clap -> Clap-pause-clap -> complete log file verification |

---

## 4. Concrete Code Implementation Design for `tests/test_user_simulation.py`

```python
"""
tests/test_user_simulation.py
=============================
Automated User Simulation Test Suite & Full Pipeline Regression for JARVIS (Milestone M4).
Simulates realistic end-user interactions:
1. Synthetic audio clap events injected into AudioEngine / GestureDetector and routed to JarvisApp.
2. First double clap -> runs welcome sequence exactly 1 time (welcome_executed flag set).
3. Second double clap -> triggers AI voice loop (with mock STT + LLM).
4. Triple clap -> triggers system_status action (_handle_system_status).
5. Clap-pause-clap -> triggers show_overlay action.
6. Zero double-dispatch verification (ensuring single callback execution per gesture pattern).
7. 3.0s debounce cooldown enforcement (second trigger within 3.0s is suppressed and logged).
8. Overlay HUD state transitions: IDLE -> LISTENING -> THINKING -> RESPONSE -> HIDDEN.
9. End-to-end synthetic user session simulation with structured interaction logging.
"""
from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import RequesterContext
from jarvis.gesture.models import GestureType
from jarvis.stt.engine import MockSTTEngine
from jarvis.ui.overlay import JarvisOverlay, OverlayState
from jarvis.ui.tray import TrayStatus


# ============================================================================
# HELPER FIXTURES & UTILITIES
# ============================================================================

@pytest.fixture
def sim_app(tmp_path, monkeypatch):
    """
    Creates an isolated, headless JarvisApp instance configured for simulation testing.
    Intercepts TTS speech and overlay rendering to avoid external audio/display dependencies.
    """
    log_file = tmp_path / "sim_jarvis.log"
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    app.config.set("logging.file", str(log_file))

    # Provide headless overlay for state inspection
    app.overlay = JarvisOverlay(headless=True)
    app.overlay.start()

    # Track spoken TTS phrases
    spoken_phrases: List[Dict[str, Any]] = []
    if app.tts_manager:
        monkeypatch.setattr(
            app.tts_manager,
            "speak",
            lambda txt, wait=False, **kw: spoken_phrases.append({"text": txt, "wait": wait}) or True,
        )

    setattr(app, "spoken_phrases", spoken_phrases)
    setattr(app, "log_file_path", log_file)

    yield app

    if app.overlay:
        app.overlay.destroy()
    app.stop()


def _wait_for_condition(predicate, timeout: float = 3.0, interval: float = 0.05) -> bool:
    """Helper polling until a predicate returns True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ============================================================================
# 1. SYNTHETIC AUDIO CLAP INJECTION & ROUTING TESTS
# ============================================================================

def test_sim_audio_engine_double_clap_injection(sim_app, mock_audio_stream):
    """
    [Sim 1] Ingest synthetic double-clap PCM buffer into AudioEngine ->
    verifies DSP transient detection, GestureDetector state disambiguation,
    and JarvisApp._on_gesture_event routing to welcome sequence.
    """
    executed_actions: List[str] = []
    for act in ["spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"]:
        sim_app.dispatcher.register_action(
            name=act,
            handler=lambda name=act, **kw: executed_actions.append(name) or {"status": "ok"},
        )

    assert sim_app.welcome_executed is False

    # Generate synthetic double clap PCM (150ms gap, 0.1s lead, 0.6s trailing silence for disambiguation tick)
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15, leading_silence_s=0.10, trailing_silence_s=0.60)
    sim_app.audio_engine.feed_audio(pcm, virtual_time=True)

    # Wait for welcome sequence thread
    assert _wait_for_condition(lambda: sim_app.welcome_executed is True, timeout=2.0)
    assert _wait_for_condition(lambda: len(executed_actions) >= 5, timeout=2.0)

    assert "spotify" in executed_actions
    assert "chrome_claude" in executed_actions
    assert "tts_welcome" in executed_actions


def test_sim_audio_engine_triple_clap_injection(sim_app, mock_audio_stream):
    """
    [Sim 2] Ingest synthetic triple-clap PCM buffer into AudioEngine ->
    verifies detection and dispatch of system_status action.
    """
    status_executed: List[bool] = []
    sim_app.dispatcher.register_action(
        name="system_status",
        handler=lambda **kw: status_executed.append(True) or {"status": "healthy"},
    )

    pcm = mock_audio_stream.generate_triple_clap(gap1_s=0.15, gap2_s=0.15, leading_silence_s=0.10, trailing_silence_s=0.50)
    sim_app.audio_engine.feed_audio(pcm, virtual_time=True)

    assert _wait_for_condition(lambda: len(status_executed) == 1, timeout=2.0)


def test_sim_audio_engine_clap_pause_clap_injection(sim_app, mock_audio_stream):
    """
    [Sim 3] Ingest synthetic clap-pause-clap PCM buffer (750ms pause) into AudioEngine ->
    verifies detection and dispatch of show_overlay action.
    """
    overlay_executed: List[bool] = []
    sim_app.dispatcher.register_action(
        name="show_overlay",
        handler=lambda **kw: overlay_executed.append(True) or {"status": "shown"},
    )

    pcm = mock_audio_stream.generate_clap_pause_clap(gap_s=0.75, leading_silence_s=0.10, trailing_silence_s=0.50)
    sim_app.audio_engine.feed_audio(pcm, virtual_time=True)

    assert _wait_for_condition(lambda: len(overlay_executed) == 1, timeout=2.0)


# ============================================================================
# 2. FIRST VS. SECOND DOUBLE CLAP STATE TRANSITIONS
# ============================================================================

def test_sim_first_double_clap_welcome_sequence_once(sim_app):
    """
    [Sim 4] Verify first double clap runs welcome sequence exactly 1 time,
    sets welcome_executed flag, and logs structured interaction.
    """
    executed: List[str] = []
    for act in ["spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"]:
        sim_app.dispatcher.register_action(
            name=act,
            handler=lambda name=act, **kw: executed.append(name) or {"status": "ok"},
        )

    assert sim_app.welcome_executed is False

    sim_app._on_gesture_event("double_clap")

    assert sim_app.welcome_executed is True
    assert _wait_for_condition(lambda: len(executed) == 5, timeout=2.0)

    # Verify structured interaction log file
    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    assert "[INTERACTION]" in log_content
    assert "TRIGGER: GESTURE:double_clap" in log_content
    assert "ACTION: welcome_sequence" in log_content


def test_sim_second_double_clap_triggers_ai_voice_loop(sim_app, monkeypatch):
    """
    [Sim 5] Verify second double clap triggers AI voice loop:
    Overlay -> LISTENING -> STT transcribe -> Overlay -> THINKING -> LLM Intent -> Dispatch -> TTS speak -> Overlay -> RESPONSE.
    """
    # Simulate that welcome sequence has already completed
    sim_app.welcome_executed = True
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0  # Cooldown cleared

    # Mock STT to return a specific command
    sim_app.stt_engine.primary_engine = MockSTTEngine(default_transcript="bật đèn phòng khách")
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

    # Track home_assistant_call action execution
    ha_calls: List[Dict[str, Any]] = []
    sim_app.dispatcher.register_action(
        name="home_assistant_call",
        handler=lambda **kw: ha_calls.append(kw) or {"status": "success", "message": "Đã bật đèn phòng khách"},
    )

    sim_app._on_gesture_event("double_clap")

    # Wait for AI-Voice-Loop thread to complete
    assert _wait_for_condition(lambda: len(ha_calls) == 1, timeout=3.0)
    assert _wait_for_condition(lambda: len(sim_app.spoken_phrases) >= 2, timeout=3.0)

    # Verify TTS spoken sequence
    listening_prompt = next((p for p in sim_app.spoken_phrases if "đang lắng nghe" in p["text"]), None)
    assert listening_prompt is not None

    # Verify overlay reached RESPONSE state
    assert sim_app.overlay.state == OverlayState.RESPONSE
    assert "bật đèn phòng khách" in sim_app.overlay.user_text

    # Verify interaction log
    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    assert "TRIGGER: VOICE" in log_content
    assert "INPUT: bật đèn phòng khách" in log_content


def test_sim_voice_loop_smart_keyword_hardware_status(sim_app, monkeypatch):
    """
    [Sim 6] Voice loop simulation with Vietnamese keyword query: "nhiệt độ hệ thống" ->
    routes to hardware_status_query / system_status and vocalizes live telemetry.
    """
    sim_app.welcome_executed = True
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0

    sim_app.stt_engine.primary_engine = MockSTTEngine(default_transcript="nhiệt độ hệ thống")
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

    status_calls: List[Dict[str, Any]] = []
    sim_app.dispatcher.register_action(
        name="system_status",
        handler=lambda **kw: status_calls.append(kw) or {"status": "healthy", "message": "CPU 25%, RAM 40%"},
    )

    sim_app._on_gesture_event("double_clap")

    assert _wait_for_condition(lambda: len(status_calls) == 1, timeout=3.0)
    assert _wait_for_condition(lambda: any("CPU" in p["text"] or "hệ thống" in p["text"] for p in sim_app.spoken_phrases), timeout=3.0)


def test_sim_voice_loop_silence_rejection(sim_app, monkeypatch):
    """
    [Sim 7] Voice loop simulation when user speaks nothing / STT returns empty string:
    Overlay shows "(không nghe thấy)" and TTS prompts user to retry without crashing.
    """
    sim_app.welcome_executed = True
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0

    sim_app.stt_engine.primary_engine = MockSTTEngine(default_transcript="")
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

    sim_app._on_gesture_event("double_clap")

    assert _wait_for_condition(lambda: any("không nghe thấy" in p["text"] for p in sim_app.spoken_phrases), timeout=3.0)
    assert sim_app.overlay.state == OverlayState.RESPONSE
    assert "(không nghe thấy)" in sim_app.overlay.user_text

    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    assert "STATUS: failed" in log_content


def test_sim_voice_loop_error_recovery(sim_app, monkeypatch):
    """
    [Sim 8] Voice loop simulation when STT/LLM throws an unexpected exception:
    Ensures error is cleanly caught, vocalized to user, and overlay updated.
    """
    sim_app.welcome_executed = True
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0

    def _failing_transcribe(*args, **kwargs):
        raise RuntimeError("Microphone hardware disconnected")

    sim_app.stt_engine.transcribe = _failing_transcribe
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

    sim_app._on_gesture_event("double_clap")

    assert _wait_for_condition(lambda: any("không nghe thấy" in p["text"] for p in sim_app.spoken_phrases), timeout=3.0)


# ============================================================================
# 3. TRIPLE CLAP & CLAP-PAUSE-CLAP ACTION DISPATCH
# ============================================================================

def test_sim_triple_clap_system_status_live_telemetry(sim_app, mock_hardware_provider):
    """
    [Sim 9] Triple clap gesture -> invokes _handle_system_status ->
    vocalizes CPU & RAM status summary via TTS and logs interaction.
    """
    mock_hardware_provider.set_cpu(32.5)
    mock_hardware_provider.set_ram(45.0)

    sim_app._on_gesture_event("triple_clap")

    assert _wait_for_condition(lambda: len(sim_app.spoken_phrases) >= 1, timeout=2.0)
    last_spoken = sim_app.spoken_phrases[-1]["text"]
    assert "Tình trạng hệ thống" in last_spoken or "CPU" in last_spoken or "RAM" in last_spoken

    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    assert "TRIGGER: GESTURE:triple_clap" in log_content
    assert "ACTION: system_status" in log_content


def test_sim_clap_pause_clap_shows_overlay(sim_app):
    """
    [Sim 10] Clap-pause-clap gesture -> invokes show_overlay ->
    activates overlay LISTENING HUD state and logs interaction.
    """
    sim_app._on_gesture_event("clap_pause_clap")

    assert sim_app.overlay.state == OverlayState.LISTENING
    assert sim_app.overlay.is_visible is True

    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    assert "TRIGGER: GESTURE:clap_pause_clap" in log_content
    assert "ACTION: show_overlay" in log_content


# ============================================================================
# 4. ZERO DOUBLE-DISPATCH & 3.0S DEBOUNCE COOLDOWN ENFORCEMENT
# ============================================================================

def test_sim_zero_double_dispatch_verification(sim_app):
    """
    [Sim 11] Verify zero double-dispatch: Each gesture event triggers its
    associated actions EXACTLY once (call_count == 1).
    """
    call_counts: Dict[str, int] = {"welcome_act": 0, "status_act": 0, "overlay_act": 0}

    sim_app.dispatcher.register_action("welcome_act", lambda **kw: call_counts.__setitem__("welcome_act", call_counts["welcome_act"] + 1) or {})
    sim_app.dispatcher.register_action("status_act", lambda **kw: call_counts.__setitem__("status_act", call_counts["status_act"] + 1) or {})
    sim_app.dispatcher.register_action("overlay_act", lambda **kw: call_counts.__setitem__("overlay_act", call_counts["overlay_act"] + 1) or {})

    sim_app.config.set("gesture.patterns.double_clap.actions", ["welcome_act"])
    sim_app.config.set("gesture.patterns.triple_clap.actions", ["status_act"])
    sim_app.config.set("gesture.patterns.clap_pause_clap.actions", ["overlay_act"])

    # 1. Double clap
    sim_app._on_gesture_event("double_clap")
    time.sleep(0.1)
    assert call_counts["welcome_act"] == 1

    # 2. Triple clap
    sim_app._on_gesture_event("triple_clap")
    time.sleep(0.1)
    assert call_counts["status_act"] == 1

    # 3. Clap pause clap
    sim_app._on_gesture_event("clap_pause_clap")
    time.sleep(0.1)
    assert call_counts["overlay_act"] == 1


def test_sim_3s_debounce_cooldown_enforcement(sim_app, caplog):
    """
    [Sim 12] Verify 3.0s debounce cooldown:
    Trigger 1 at t0 -> executes.
    Trigger 2 at t0 + 1.0s -> suppressed, logs 'suppressed' / 'cooldown'.
    Trigger 3 after cooldown expires -> executes.
    """
    executed_count = 0

    def _handler(**kw):
        nonlocal executed_count
        executed_count += 1
        return {"status": "ok"}

    sim_app.dispatcher.register_action("custom_action", _handler)
    sim_app.config.set("gesture.patterns.custom_pat.actions", ["custom_action"])

    with caplog.at_level(logging.INFO):
        # Trigger 1: Initial activation
        sim_app._on_gesture_event("custom_pat")
        assert executed_count == 1

        # Trigger 2: Rapid re-trigger within 3.0s (e.g. 0.2s later)
        sim_app._on_gesture_event("custom_pat")
        assert executed_count == 1  # Blocked!
        assert any("suppressed" in rec.message for rec in caplog.records)

        # Advance pattern last fired timestamp past 3.0s
        sim_app._pattern_last_fired["custom_pat"] = time.monotonic() - 3.5

        # Trigger 3: After cooldown expired
        sim_app._on_gesture_event("custom_pat")
        assert executed_count == 2  # Executed!


# ============================================================================
# 5. OVERLAY STATE LIFECYCLE & FULL USER SESSION SIMULATION
# ============================================================================

def test_sim_overlay_full_state_lifecycle():
    """
    [Sim 13] Verify Overlay HUD state machine:
    IDLE -> LISTENING -> THINKING -> RESPONSE -> HIDDEN.
    """
    overlay = JarvisOverlay(headless=True)
    overlay.start()

    assert overlay.state == OverlayState.IDLE

    overlay.show_listening("🎤 Đang lắng nghe...")
    assert overlay.state == OverlayState.LISTENING
    assert overlay.is_visible is True

    overlay.show_thinking("Tôi muốn bật đèn")
    assert overlay.state == OverlayState.THINKING
    assert overlay.user_text == "Tôi muốn bật đèn"

    overlay.show_response("Tôi muốn bật đèn", "Đã bật đèn cho Ngài.", duration_s=0.2)
    assert overlay.state == OverlayState.RESPONSE
    assert overlay.jarvis_text == "Đã bật đèn cho Ngài."

    overlay.hide()
    assert overlay.state == OverlayState.HIDDEN
    assert overlay.is_visible is False

    overlay.destroy()


def test_sim_full_user_session_e2e(sim_app, monkeypatch):
    """
    [Sim 14] End-to-End simulation of a realistic complete user session:
    1. Startup introduction spoken.
    2. User double claps -> Welcome sequence launches.
    3. User double claps again -> Voice query "nhiệt độ hệ thống" -> Live CPU/RAM response.
    4. User triple claps -> System status reported.
    5. User clap-pause-claps -> Overlay HUD opens.
    6. Complete structured interaction log validated.
    """
    # 1. Startup intro
    sim_app.start()
    assert any("Hệ thống đã sẵn sàng" in p["text"] for p in sim_app.spoken_phrases)

    # 2. First double clap (Welcome sequence)
    sim_app._on_gesture_event("double_clap")
    assert sim_app.welcome_executed is True

    # 3. Second double clap (Voice AI Loop)
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0
    sim_app.stt_engine.primary_engine = MockSTTEngine(default_transcript="nhiệt độ hệ thống")
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

    sim_app._on_gesture_event("double_clap")
    assert _wait_for_condition(lambda: sim_app.overlay.state == OverlayState.RESPONSE, timeout=3.0)

    # 4. Triple clap
    sim_app._pattern_last_fired["triple_clap"] = time.monotonic() - 5.0
    sim_app._on_gesture_event("triple_clap")
    time.sleep(0.1)

    # 5. Clap-pause-clap
    sim_app._pattern_last_fired["clap_pause_clap"] = time.monotonic() - 5.0
    sim_app._on_gesture_event("clap_pause_clap")
    time.sleep(0.1)
    assert sim_app.overlay.state == OverlayState.LISTENING

    # 6. Validate complete interaction log
    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    lines = [l for l in log_content.splitlines() if "[INTERACTION]" in l]
    assert len(lines) >= 4

    assert any("GESTURE:double_clap" in l for l in lines)
    assert any("VOICE" in l for l in lines)
    assert any("GESTURE:triple_clap" in l for l in lines)
    assert any("GESTURE:clap_pause_clap" in l for l in lines)
```
