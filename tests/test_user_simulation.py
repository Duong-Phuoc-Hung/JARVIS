"""
tests/test_user_simulation.py
=============================
Automated User Simulation Test Suite & Full System Regression for JARVIS (Milestone M4).
Simulates authentic human user interactions with zero cloud / hardware dependencies:

1. Test 1: Synthetic audio double-clap PCM injection into AudioEngine -> GestureDetector -> _on_gesture_event -> welcome sequence.
2. Test 2: Synthetic audio triple-clap PCM injection into AudioEngine -> GestureDetector -> _on_gesture_event -> system_status.
3. Test 3: Synthetic audio clap-pause-clap PCM injection into AudioEngine -> GestureDetector -> _on_gesture_event -> show_overlay.
4. Test 4: First double clap runs welcome sequence once, flips welcome_executed flag, and logs structured interaction.
5. Test 5: Second double clap with welcome_executed=True triggers AI-Voice-Loop (mock STT + LLM router -> action dispatch -> TTS speak -> overlay response).
6. Test 6: Voice loop smart keyword query for smart home ("bật đèn phòng khách") -> dispatches home_assistant_call.
7. Test 7: Voice loop smart keyword query for hardware telemetry ("nhiệt độ hệ thống") -> dispatches system_status / hardware_telemetry_check and speaks CPU/RAM.
8. Test 8: Voice loop silence handling: empty/silent transcript prompts retry ("(không nghe thấy)") without crash, logs STATUS: failed.
9. Test 9: Voice loop exception resilience: STT/LLM error caught cleanly, speaks notification, no unhandled crash.
10. Test 10: Triple clap live hardware status query: _handle_system_status vocalizes CPU/RAM metrics via TTSManager.
11. Test 11: Clap-pause-clap overlay HUD activation: show_overlay action executes overlay.show_listening().
12. Test 12: Zero double-dispatch verification: each gesture trigger executes associated action callbacks strictly 1 time.
13. Test 13: 3.0s debounce cooldown enforcement: rapid re-trigger within 3.0s is suppressed with INFO log "suppressed"; execution re-enabled after 3.0s.
14. Test 14: Overlay FSM transitions (IDLE -> LISTENING -> THINKING -> RESPONSE -> HIDDEN) and 10+ consecutive show/hide cycle stability without leaks or crashes.
15. Test 15: STT & TTS offline fallbacks: missing/invalid API keys cascade gracefully to mock/SAPI5.
16. Test 16: Vietnamese Smart Keyword Router: 7 categories validation ("bật/tắt đèn", "nhiệt độ/CPU/RAM", "mở Spotify/nhạc", "thời tiết", "nhắc nhở", "tắt máy/restart" with safety confirmation, default fallback).
17. Test 17: End-to-end full session simulation with structured [INTERACTION] logging validation in logs/jarvis.log and pipeline completion in < 10.0s.
18. Test 18: CLI health check verification: python -m jarvis health-check returns exit code 0.
"""
from __future__ import annotations

import concurrent.futures
import io
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.cli import main, run_health_check
from jarvis.core.app import JarvisApp
from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.gesture.models import GestureType
from jarvis.llm.client import LLMClient
from jarvis.llm.router import IntentResult, LLMIntentRouter
from jarvis.stt.engine import (
    BaseSTTEngine,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTEngine,
    STTError,
    WindowsSpeechSTT,
)
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import WELCOME_PHRASES, TTSManager
from jarvis.ui.overlay import (
    BREATHING_GRADIENT,
    JarvisOverlay,
    OverlayState,
)
from jarvis.ui.tray import TrayStatus

# ============================================================================
# TEST FIXTURES & ISOLATION HELPERS
# ============================================================================

def _wait_for_condition(predicate, timeout: float = 3.0, interval: float = 0.02) -> bool:
    """Helper polling until a predicate returns True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def sim_app(tmp_path, monkeypatch):
    """
    Creates an isolated, headless JarvisApp instance configured for simulation testing.
    Intercepts TTS speech and provides headless overlay for state inspection.
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
            lambda txt, wait=False, **kw: spoken_phrases.append({"text": str(txt), "wait": wait}) or True,
        )

    app.spoken_phrases = spoken_phrases
    app.log_file_path = log_file

    yield app

    if app.overlay:
        app.overlay.destroy()
    app.stop()


# ============================================================================
# TEST 1: SYNTHETIC AUDIO DOUBLE-CLAP PCM INJECTION
# ============================================================================

def test_sim_01_audio_engine_double_clap_injection(sim_app, mock_audio_stream):
    """
    [Test 1] Ingest synthetic double-clap PCM buffer into AudioEngine ->
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
    pcm = mock_audio_stream.generate_double_clap(
        gap_s=0.15, leading_silence_s=0.10, trailing_silence_s=0.60
    )
    sim_app.audio_engine.feed_audio(pcm, virtual_time=True)

    # Wait for welcome sequence thread
    assert _wait_for_condition(lambda: sim_app.welcome_executed is True, timeout=2.0)
    assert _wait_for_condition(lambda: len(executed_actions) >= 5, timeout=2.0)

    assert "spotify" in executed_actions
    assert "chrome_claude" in executed_actions
    assert "tts_welcome" in executed_actions


# ============================================================================
# TEST 2: SYNTHETIC AUDIO TRIPLE-CLAP PCM INJECTION
# ============================================================================

def test_sim_02_audio_engine_triple_clap_injection(sim_app, mock_audio_stream):
    """
    [Test 2] Ingest synthetic triple-clap PCM buffer into AudioEngine ->
    verifies detection and dispatch of system_status action.
    """
    status_executed: List[bool] = []
    sim_app.dispatcher.register_action(
        name="system_status",
        handler=lambda **kw: status_executed.append(True) or {"status": "healthy"},
    )

    pcm = mock_audio_stream.generate_triple_clap(
        gap1_s=0.15, gap2_s=0.15, leading_silence_s=0.10, trailing_silence_s=0.50
    )
    sim_app.audio_engine.feed_audio(pcm, virtual_time=True)

    assert _wait_for_condition(lambda: len(status_executed) == 1, timeout=2.0)


# ============================================================================
# TEST 3: SYNTHETIC AUDIO CLAP-PAUSE-CLAP PCM INJECTION
# ============================================================================

def test_sim_03_audio_engine_clap_pause_clap_injection(sim_app, mock_audio_stream):
    """
    [Test 3] Ingest synthetic clap-pause-clap PCM buffer (750ms pause) into AudioEngine ->
    verifies detection and dispatch of show_overlay action.
    """
    overlay_executed: List[bool] = []
    sim_app.dispatcher.register_action(
        name="show_overlay",
        handler=lambda **kw: overlay_executed.append(True) or {"status": "shown"},
    )

    pcm = mock_audio_stream.generate_clap_pause_clap(
        gap_s=0.75, leading_silence_s=0.10, trailing_silence_s=0.50
    )
    sim_app.audio_engine.feed_audio(pcm, virtual_time=True)

    assert _wait_for_condition(lambda: len(overlay_executed) == 1, timeout=2.0)


# ============================================================================
# TEST 4: FIRST DOUBLE CLAP RUNS WELCOME SEQUENCE ONCE
# ============================================================================

def test_sim_04_first_double_clap_welcome_sequence_once(sim_app):
    """
    [Test 4] Verify first double clap runs welcome sequence exactly 1 time,
    flips welcome_executed flag, and logs structured interaction.
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
    assert "STATUS: success" in log_content


# ============================================================================
# TEST 5: SECOND DOUBLE CLAP TRIGGERS AI-VOICE-LOOP
# ============================================================================

def test_sim_05_second_double_clap_triggers_ai_voice_loop(sim_app, monkeypatch):
    """
    [Test 5] Verify second double clap with welcome_executed=True triggers AI-Voice-Loop:
    Overlay -> LISTENING -> STT transcribe -> Overlay -> THINKING -> LLM Intent -> Dispatch -> TTS speak -> Overlay -> RESPONSE.
    """
    sim_app.welcome_executed = True
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0  # Cooldown cleared

    # Mock STT to return a specific command
    sim_app.stt_engine.primary_engine = MockSTTEngine(default_transcript="bật đèn phòng khách")
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

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


# ============================================================================
# TEST 6: VOICE LOOP SMART KEYWORD QUERY FOR SMART HOME
# ============================================================================

def test_sim_06_voice_loop_smart_keyword_home_assistant(sim_app, monkeypatch):
    """
    [Test 6] Voice loop smart keyword query for smart home ("bật đèn phòng khách") ->
    dispatches home_assistant_call with proper entity and parameters.
    """
    sim_app.welcome_executed = True
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0

    sim_app.stt_engine.primary_engine = MockSTTEngine(default_transcript="bật đèn phòng khách")
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

    received_payloads: List[Dict[str, Any]] = []
    sim_app.dispatcher.register_action(
        name="home_assistant_call",
        handler=lambda payload=None, **kw: received_payloads.append(payload or {}) or {"status": "ok"},
    )

    sim_app._on_gesture_event("double_clap")

    assert _wait_for_condition(lambda: len(received_payloads) == 1, timeout=3.0)
    payload = received_payloads[0]
    assert payload.get("domain") == "light"
    assert payload.get("service") == "turn_on"
    assert "living_room" in payload.get("entity_id", "")


# ============================================================================
# TEST 7: VOICE LOOP SMART KEYWORD QUERY FOR HARDWARE TELEMETRY
# ============================================================================

def test_sim_07_voice_loop_smart_keyword_hardware_telemetry(sim_app, monkeypatch):
    """
    [Test 7] Voice loop smart keyword query for hardware telemetry ("nhiệt độ hệ thống") ->
    dispatches system_status / hardware_telemetry_check and speaks CPU/RAM.
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
    sim_app.dispatcher.register_action(
        name="hardware_status_query",
        handler=lambda **kw: status_calls.append(kw) or {"status": "healthy", "message": "CPU 25%, RAM 40%"},
    )
    sim_app.dispatcher.register_action(
        name="hardware_telemetry_check",
        handler=lambda **kw: status_calls.append(kw) or {"status": "healthy", "message": "CPU 25%, RAM 40%"},
    )

    sim_app._on_gesture_event("double_clap")

    assert _wait_for_condition(lambda: len(status_calls) >= 1 or any("CPU" in p["text"] or "hệ thống" in p["text"] for p in sim_app.spoken_phrases), timeout=3.0)
    assert sim_app.overlay.state == OverlayState.RESPONSE


# ============================================================================
# TEST 8: VOICE LOOP SILENCE HANDLING
# ============================================================================

def test_sim_08_voice_loop_silence_handling(sim_app, monkeypatch):
    """
    [Test 8] Voice loop silence handling: empty/silent transcript prompts retry ("(không nghe thấy)")
    without crash, logs STATUS: failed.
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


# ============================================================================
# TEST 9: VOICE LOOP EXCEPTION RESILIENCE
# ============================================================================

def test_sim_09_voice_loop_exception_resilience(sim_app, monkeypatch):
    """
    [Test 9] Voice loop exception resilience: STT/LLM error caught cleanly, speaks notification,
    no unhandled crash.
    """
    sim_app.welcome_executed = True
    sim_app._pattern_last_fired["double_clap"] = time.monotonic() - 5.0

    def _failing_transcribe(*args, **kwargs):
        raise RuntimeError("Audio hardware stream disconnected")

    sim_app.stt_engine.transcribe = _failing_transcribe
    monkeypatch.setattr(sim_app, "record_audio", lambda **kw: np.zeros(1600, dtype=np.float32))

    sim_app._on_gesture_event("double_clap")

    # Gracefully falls back to silence rejection message
    assert _wait_for_condition(lambda: any("không nghe thấy" in p["text"] for p in sim_app.spoken_phrases), timeout=3.0)
    assert sim_app.overlay.state == OverlayState.RESPONSE


# ============================================================================
# TEST 10: TRIPLE CLAP LIVE HARDWARE STATUS QUERY
# ============================================================================

def test_sim_10_triple_clap_live_hardware_status(sim_app, mock_hardware_provider):
    """
    [Test 10] Triple clap live hardware status query: _handle_system_status vocalizes
    CPU/RAM metrics via TTSManager.
    """
    mock_hardware_provider.set_cpu(32.5)
    mock_hardware_provider.set_ram(45.0)

    res = sim_app._handle_system_status()
    assert res["status"] == "healthy"
    assert "Tình trạng hệ thống" in res["message"] or "CPU" in res["message"] or "JARVIS" in res["message"]

    sim_app._on_gesture_event("triple_clap")

    assert _wait_for_condition(lambda: len(sim_app.spoken_phrases) >= 1, timeout=2.0)
    last_spoken = sim_app.spoken_phrases[-1]["text"]
    assert "Tình trạng hệ thống" in last_spoken or "CPU" in last_spoken or "RAM" in last_spoken or "JARVIS" in last_spoken

    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    assert "TRIGGER: GESTURE:triple_clap" in log_content
    assert "ACTION: system_status" in log_content


# ============================================================================
# TEST 11: CLAP-PAUSE-CLAP OVERLAY HUD ACTIVATION
# ============================================================================

def test_sim_11_clap_pause_clap_overlay_hud_activation(sim_app):
    """
    [Test 11] Clap-pause-clap overlay HUD activation: show_overlay action executes
    overlay.show_listening().
    """
    sim_app._on_gesture_event("clap_pause_clap")

    assert sim_app.overlay.state == OverlayState.LISTENING
    assert sim_app.overlay.is_visible is True

    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    assert "TRIGGER: GESTURE:clap_pause_clap" in log_content
    assert "ACTION: show_overlay" in log_content


# ============================================================================
# TEST 12: ZERO DOUBLE-DISPATCH VERIFICATION
# ============================================================================

def test_sim_12_zero_double_dispatch_verification(sim_app):
    """
    [Test 12] Zero double-dispatch verification: each gesture trigger executes associated
    action callbacks strictly 1 time.
    """
    # 1. Assert architecture contract: GestureDetector dispatcher must be None
    assert sim_app.gesture_detector.dispatcher is None

    call_counts: Dict[str, int] = {"welcome_act": 0, "status_act": 0, "overlay_act": 0}

    sim_app.dispatcher.register_action("welcome_act", lambda **kw: call_counts.__setitem__("welcome_act", call_counts["welcome_act"] + 1) or {})
    sim_app.dispatcher.register_action("status_act", lambda **kw: call_counts.__setitem__("status_act", call_counts["status_act"] + 1) or {})
    sim_app.dispatcher.register_action("overlay_act", lambda **kw: call_counts.__setitem__("overlay_act", call_counts["overlay_act"] + 1) or {})

    sim_app.config.set("gesture.patterns.double_clap.actions", ["welcome_act"])
    sim_app.config.set("gesture.patterns.triple_clap.actions", ["status_act"])
    sim_app.config.set("gesture.patterns.clap_pause_clap.actions", ["overlay_act"])

    # Double clap
    sim_app._on_gesture_event("double_clap")
    time.sleep(0.05)
    assert call_counts["welcome_act"] == 1

    # Triple clap
    sim_app._on_gesture_event("triple_clap")
    time.sleep(0.05)
    assert call_counts["status_act"] == 1

    # Clap-pause-clap
    sim_app._on_gesture_event("clap_pause_clap")
    time.sleep(0.05)
    assert call_counts["overlay_act"] == 1


# ============================================================================
# TEST 13: 3.0S DEBOUNCE COOLDOWN ENFORCEMENT
# ============================================================================

def test_sim_13_3s_debounce_cooldown_enforcement(sim_app, caplog):
    """
    [Test 13] 3.0s debounce cooldown enforcement: rapid re-trigger within 3.0s is suppressed
    with INFO log 'suppressed'; execution re-enabled after 3.0s.
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

        # Trigger 2: Rapid re-trigger within 3.0s -> Suppressed
        sim_app._on_gesture_event("custom_pat")
        assert executed_count == 1  # Blocked!
        assert any("suppressed" in rec.message for rec in caplog.records)

        # Advance pattern last fired timestamp past 3.0s
        sim_app._pattern_last_fired["custom_pat"] = time.monotonic() - 3.5

        # Trigger 3: After cooldown expired
        sim_app._on_gesture_event("custom_pat")
        assert executed_count == 2  # Executed!


# ============================================================================
# TEST 14: OVERLAY FSM TRANSITIONS & CYCLE STABILITY
# ============================================================================

def test_sim_14_overlay_fsm_transitions_and_cycle_stability():
    """
    [Test 14] Overlay FSM transitions (IDLE -> LISTENING -> THINKING -> RESPONSE -> HIDDEN)
    and 10+ consecutive show/hide cycle stability without leaks or crashes.
    """
    overlay = JarvisOverlay(headless=True, auto_hide_s=5.0)
    overlay.start()

    # 1. State machine cycle
    assert overlay.state == OverlayState.IDLE
    assert overlay.is_visible is False

    overlay.show_listening("🎤 Đang lắng nghe...")
    assert overlay.state == OverlayState.LISTENING
    assert overlay.is_visible is True
    assert overlay.user_text == "🎤 Đang lắng nghe..."

    overlay.show_thinking("bật đèn phòng khách")
    assert overlay.state == OverlayState.THINKING
    assert overlay.user_text == "bật đèn phòng khách"

    overlay.show_response("bật đèn phòng khách", "Đang bật đèn cho Ngài.", hint="💡 Double clap để hỏi tiếp")
    assert overlay.state == OverlayState.RESPONSE
    assert overlay.jarvis_text == "Đang bật đèn cho Ngài."
    assert overlay.hint_text == "💡 Double clap để hỏi tiếp"

    overlay.hide()
    assert overlay.state == OverlayState.HIDDEN
    assert overlay.is_visible is False

    # 2. 15 consecutive show/hide stability cycles
    for i in range(15):
        overlay.show_listening(f"Prompt {i}")
        assert overlay.state == OverlayState.LISTENING
        overlay.show_thinking(f"Transcript {i}")
        assert overlay.state == OverlayState.THINKING
        overlay.show_response(f"Transcript {i}", f"Response {i}")
        assert overlay.state == OverlayState.RESPONSE
        overlay.hide()
        assert overlay.state == OverlayState.HIDDEN

    # 3. Multithreaded concurrency stress test
    exceptions: List[Exception] = []

    def _worker(thread_id: int):
        try:
            for i in range(10):
                overlay.show_listening(f"T{thread_id}-{i}")
                overlay.show_thinking(f"Q{thread_id}-{i}")
                overlay.show_response(f"Q{thread_id}-{i}", f"R{thread_id}-{i}")
                overlay.hide()
        except Exception as e:
            exceptions.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_worker, t) for t in range(8)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0
    overlay.destroy()


# ============================================================================
# TEST 15: STT & TTS OFFLINE FALLBACKS
# ============================================================================

def test_sim_15_stt_and_tts_offline_fallbacks(tmp_path, audio_synthesizer):
    """
    [Test 15] STT & TTS offline fallbacks: missing/invalid API keys cascade gracefully to mock/SAPI5.
    """
    # 1. STT Fallback on missing/invalid key
    invalid_whisper = OpenAIWhisperSTT(config={"api_key": ""})
    assert invalid_whisper.is_available() is False

    mock_stt = MockSTTEngine(default_transcript="bật đèn phòng khách")
    stt_engine = STTEngine(
        primary_engine=invalid_whisper,
        fallback_engine=mock_stt,
    )
    noise_audio = audio_synthesizer.generate_noise(duration_s=0.5, rms=0.05)
    assert stt_engine.transcribe(noise_audio) == "bật đèn phòng khách"

    # STT silence gating
    silence = audio_synthesizer.generate_silence(duration_s=0.5)
    assert stt_engine.transcribe(silence) == ""

    # 2. TTS Cascading to SAPI5 Fallback on invalid ElevenLabs key
    tts_config = {
        "elevenlabs": {"api_key": "invalid_eleven_key_123"},
        "fallback": {"voice_name": "Microsoft David Desktop"},
        "cache": {"enabled": False, "dir": str(tmp_path)},
    }
    tts_mgr = TTSManager(config=tts_config, cache_dir=tmp_path)
    success = tts_mgr.speak("Xin chào Ngài, tôi là JARVIS.", wait=True)
    assert success is True
    assert len(tts_mgr.fallback_engine.spoken_history) >= 1
    assert "Xin chào Ngài, tôi là JARVIS." in tts_mgr.fallback_engine.spoken_history

    # 3. Non-repeating randomized greeting pool
    greetings = [tts_mgr.get_welcome_phrase() for _ in range(25)]
    for i in range(len(greetings) - 1):
        assert greetings[i] != greetings[i + 1]

    tts_mgr.stop()


# ============================================================================
# TEST 16: VIETNAMESE SMART KEYWORD ROUTER: 7 CATEGORIES VALIDATION
# ============================================================================

@pytest.mark.parametrize(
    "query, expected_action, expected_param_key, expected_param_val, expected_text_sub",
    [
        # Category 1: Smart Home
        ("bật đèn phòng khách", "home_assistant_call", "domain", "light", "Đang bật đèn"),
        ("tắt quạt phòng khách", "home_assistant_call", "domain", "fan", "Đang tắt quạt"),
        ("bật điều hòa", "home_assistant_call", "domain", "climate", "Đang bật điều hòa"),
        
        # Category 2: Hardware Telemetry / CPU / RAM
        ("kiểm tra nhiệt độ CPU", "hardware_telemetry_check", "component", "cpu", "Nhiệt độ CPU"),
        ("kiểm tra dung lượng RAM", "hardware_telemetry_check", "component", "ram", "Bộ nhớ RAM"),
        ("tình trạng hệ thống", "hardware_status_query", None, None, "Tình trạng hệ thống"),
        
        # Category 3: Spotify / Music
        ("mở Spotify", "spotify", None, None, "Đang mở Spotify"),
        ("bật nhạc bài Nơi Này Có Anh", "spotify", None, None, "Nơi Này Có Anh"),
        ("dừng nhạc", "spotify", "command", "pause", "Đã tạm dừng"),
        
        # Category 4: Weather
        ("thời tiết hôm nay", "shell_exec", "topic", "weather", "thời tiết hôm nay"),
        ("dự báo thời tiết Hà Nội", "shell_exec", "topic", "weather", "thời tiết tại Hà Nội"),
        
        # Category 5: Reminder
        ("nhắc nhở uống nước sau 15 phút", "reminder", None, None, "Đã ghi nhận lời nhắc"),
        
        # Category 6: System Power (Lock screen - low risk)
        ("khóa màn hình", "system_power", "action", "lock", "Đã khóa màn hình"),
        
        # Category 7: Default Fallback
        ("câu hỏi hoàn toàn ngẫu nhiên xyz 123", "unknown_intent", None, None, "Tôi chưa hiểu lệnh này"),
    ]
)
def test_sim_16_vietnamese_smart_keyword_router_7_categories(
    query: str,
    expected_action: str,
    expected_param_key: Optional[str],
    expected_param_val: Optional[str],
    expected_text_sub: str,
):
    """
    [Test 16] Vietnamese Smart Keyword Router: 7 categories validation.
    """
    client = LLMClient(provider="openai", api_key="")
    router = LLMIntentRouter(client)

    intent = router.parse_intent(query)
    assert intent.action_name == expected_action
    assert expected_text_sub.lower() in intent.response_text.lower()

    if expected_param_key:
        assert intent.parameters.get(expected_param_key) == expected_param_val


def test_sim_16_system_power_safety_confirmation_flags():
    """
    [Test 16-B] System power safety flags: Destructive operations require confirmation.
    """
    client = LLMClient(provider="openai", api_key="")
    router = LLMIntentRouter(client)

    # 1. Shutdown command (Critical)
    intent_shutdown = router.parse_intent("tắt máy tính")
    assert intent_shutdown.action_name == "system_power"
    assert intent_shutdown.parameters.get("action") == "shutdown"
    assert intent_shutdown.requires_confirmation is True
    assert intent_shutdown.danger_level == "CRITICAL"
    assert intent_shutdown.confirmation_prompt is not None

    # 2. Restart command (Critical)
    intent_restart = router.parse_intent("khởi động lại máy")
    assert intent_restart.action_name == "system_power"
    assert intent_restart.parameters.get("action") == "restart"
    assert intent_restart.requires_confirmation is True
    assert intent_restart.danger_level == "CRITICAL"


# ============================================================================
# TEST 17: END-TO-END FULL SESSION SIMULATION & PERFORMANCE (< 10.0S)
# ============================================================================

def test_sim_17_e2e_full_session_simulation_and_performance(sim_app, monkeypatch, audio_synthesizer):
    """
    [Test 17] End-to-end full session simulation with structured [INTERACTION] logging validation
    in logs/jarvis.log and pipeline completion in < 10.0s.
    """
    t_start = time.perf_counter()

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
    time.sleep(0.05)

    # 5. Clap-pause-clap
    sim_app._pattern_last_fired["clap_pause_clap"] = time.monotonic() - 5.0
    sim_app._on_gesture_event("clap_pause_clap")
    time.sleep(0.05)
    assert sim_app.overlay.state == OverlayState.LISTENING

    # 6. Direct process_voice_command latency benchmark
    audio_buffer = audio_synthesizer.generate_noise(duration_s=0.5, rms=0.04)
    v_res = sim_app.process_voice_command(audio_buffer)
    assert v_res["success"] is True

    elapsed_total = time.perf_counter() - t_start
    assert elapsed_total < 10.0, f"Full session took {elapsed_total:.2f}s, exceeding 10.0s threshold!"

    # 7. Validate complete interaction log
    log_content = sim_app.log_file_path.read_text(encoding="utf-8")
    lines = [l for l in log_content.splitlines() if "[INTERACTION]" in l]
    assert len(lines) >= 4

    assert any("GESTURE:double_clap" in l for l in lines)
    assert any("VOICE" in l for l in lines)
    assert any("GESTURE:triple_clap" in l for l in lines)
    assert any("GESTURE:clap_pause_clap" in l for l in lines)


# ============================================================================
# TEST 18: CLI HEALTH CHECK VERIFICATION
# ============================================================================

def test_sim_18_cli_health_check_verification(monkeypatch):
    """
    [Test 18] CLI health check verification: python -m jarvis health-check returns exit code 0.
    """
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

    # Also verify through CLI main entrypoint
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout_main:
        main_exit_code = main(["health-check"])
        main_output = mock_stdout_main.getvalue()

    assert main_exit_code == 0
    assert "Diagnostics completed successfully." in main_output
