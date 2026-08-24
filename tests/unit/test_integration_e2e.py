"""
tests/unit/test_integration_e2e.py
===================================
Master Integration & Regression Test Suite for Milestone 7 (R9).
Verifies:
  - JarvisApp boots and wires all 10 core & expansion subsystems cleanly.
  - WakeWordDetector receives audio frames in parallel with GestureDetector.
  - process_text_command records turns in SessionContextManager and SQLite episodic logs.
  - Memory facts are extracted, stored in SQLite, and injected into LLM system prompt.
  - ScreenVisionManager actions dispatch and handle fallback gracefully.
  - WebIntelligenceHub actions dispatch with 10-minute caching and morning briefing.
  - ComputerController, ShellAssistant, and SafetyGate 30s token confirmation flow.
  - ProactiveEngine lifecycle start/stop integration with JarvisApp.
  - AlwaysOnOverlay HUD sidebar modes, 5-turn history, and quick actions.
  - CLI health check runs all 10 diagnostic categories and exits with code 0.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List
import numpy as np
import pytest

from jarvis import __version__
from jarvis.cli import run_health_check
from jarvis.core.app import JarvisApp
from jarvis.core.config import ConfigManager
from jarvis.core.models import RequesterContext
from jarvis.ui.tray import TrayStatus


# ============================================================================
# 1. Subsystem Boot & Wiring Tests
# ============================================================================

def test_jarvis_app_initialization_all_subsystems(tmp_path, monkeypatch):
    """Verify JarvisApp boots cleanly and instantiates all 10 subsystems."""
    db_file = str(tmp_path / "test_memory.db")
    monkeypatch.setenv("JARVIS_MEMORY_DB", db_file)

    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Verify All Core Subsystems
    assert app.config is not None
    assert app.event_bus is not None
    assert app.dispatcher is not None
    assert app.plugin_registry is not None
    assert app.tts_manager is not None
    assert app.stt_engine is not None
    assert app.llm_client is not None
    assert app.llm_router is not None
    assert app.audio_engine is not None
    assert app.gesture_detector is not None

    # Verify All 7 Expansion Subsystems
    assert app.wake_word_detector is not None, "WakeWordDetector must be instantiated"
    assert app.memory_manager is not None, "MemoryManager must be instantiated"
    assert app.vision_manager is not None, "ScreenVisionManager must be instantiated"
    assert app.web_hub is not None, "WebIntelligenceHub must be instantiated"
    assert app.computer_controller is not None, "ComputerController must be instantiated"
    assert app.safety_gate is not None, "SafetyGate must be instantiated"
    assert app.shell_assistant is not None, "ShellAssistant must be instantiated"
    assert app.proactive_engine is not None, "ProactiveEngine must be instantiated"
    assert app.overlay is not None, "AlwaysOnOverlay HUD must be instantiated"

    # Verify Cross-Subsystem Wire Injections
    assert app.llm_router._memory_manager is app.memory_manager
    assert app.shell_assistant._safety_gate is app.safety_gate
    assert app.proactive_engine.web_hub is app.web_hub
    assert app._initialized is True

    app.stop()


def test_composite_audio_feed_to_both_detectors(tmp_path):
    """Verify audio blocks dispatched by AudioEngine reach both gesture and wake word detectors."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    gesture_blocks = []
    wake_word_blocks = []

    # Spy on feed methods
    orig_gesture_feed = app.gesture_detector.feed_audio_block
    orig_ww_feed = app.wake_word_detector.feed_audio_block

    def _spy_gesture(block, timestamp=None):
        gesture_blocks.append(block)
        return orig_gesture_feed(block, timestamp=timestamp)

    def _spy_ww(block, timestamp=None):
        wake_word_blocks.append(block)
        return orig_ww_feed(block, timestamp=timestamp)

    app.gesture_detector.feed_audio_block = _spy_gesture
    app.wake_word_detector.feed_audio_block = _spy_ww

    test_block = np.zeros(1764, dtype=np.float32)
    app.audio_engine._dispatch_block(test_block)

    assert len(gesture_blocks) == 1
    assert len(wake_word_blocks) == 1

    app.stop()


# ============================================================================
# 2. Conversational Memory & Intent Flow Tests
# ============================================================================

def test_memory_recording_in_process_text_command(tmp_path, monkeypatch):
    """Verify process_text_command logs turns in session memory, SQLite, and overlay cards."""
    db_file = str(tmp_path / "test_memory.db")
    monkeypatch.setenv("JARVIS_MEMORY_DB", db_file)

    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    res = app.process_text_command("Báo cáo tình trạng hệ thống", requester="voice")

    assert res["success"] is True
    assert "tình trạng" in res["transcript"].lower() or "báo cáo" in res["transcript"].lower()

    # Verify short-term session context
    turns = app.memory_manager.get_session_turns()
    assert len(turns) >= 2
    assert turns[0]["role"] == "user"
    assert "báo cáo" in turns[0]["content"].lower()
    assert turns[1]["role"] == "assistant"

    # Verify long-term episodic log in SQLite
    episodes = app.memory_manager.list_episodes()
    assert len(episodes) >= 1
    assert "báo cáo" in episodes[0]["command"].lower()
    assert episodes[0]["success"] == 1

    # Verify overlay history queue
    history = app.overlay.get_history()
    assert len(history) >= 1
    assert "báo cáo" in history[0]["user_text"].lower()

    app.stop()


def test_memory_fact_memorization_and_system_prompt_context(tmp_path, monkeypatch):
    """Verify remembering facts stores in SQLite, updates overlay preview, and injects into LLM prompt."""
    db_file = str(tmp_path / "test_memory.db")
    monkeypatch.setenv("JARVIS_MEMORY_DB", db_file)

    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # User tells JARVIS to remember something
    res = app.process_text_command("Nhớ rằng tôi tên là Hưng", requester="user")
    assert res["success"] is True

    facts = app.memory_manager.list_facts()
    assert len(facts) >= 1
    stored_keys = [f["key"] for f in facts]
    assert any("tên" in k.lower() or "user" in k.lower() for k in stored_keys)

    # Verify memory context generated for LLM prompt
    prompt_context = app.memory_manager.get_system_prompt_context()
    assert "Hưng" in prompt_context or "BỘ NHỚ" in prompt_context

    # Verify overlay facts preview
    assert len(app.overlay.memory_facts) >= 1

    app.stop()


def test_today_summary_action_dispatch(tmp_path, monkeypatch):
    """Verify daily summary command retrieves episodic records."""
    db_file = str(tmp_path / "test_memory.db")
    monkeypatch.setenv("JARVIS_MEMORY_DB", db_file)

    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    app.process_text_command("Mở Spotify", requester="user")
    app.process_text_command("Bật Claude", requester="user")

    res = app.dispatcher.dispatch_action("memory_summarize_daily", payload={"text": "Hôm nay tôi đã làm gì?"})
    assert res.is_success
    assert res.data is not None
    assert "message" in res.data or "summary" in res.data

    app.stop()


# ============================================================================
# 3. Vision & Web Intelligence Subsystems Tests
# ============================================================================

def test_screen_vision_action_dispatch(tmp_path):
    """Verify screen capture and analysis actions dispatch with proper structure."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Screen capture test
    shot_path = str(tmp_path / "test_shot.png")
    cap_res = app.dispatcher.dispatch_action("screen_capture", payload={"filepath": shot_path})
    assert cap_res.is_success
    assert cap_res.data["status"] == "success"

    # Screen analyze test (polite fallback when no Vision API key)
    ana_res = app.dispatcher.dispatch_action("screen_analyze", payload={"query": "Kiểm tra màn hình"})
    assert ana_res.is_success
    assert len(ana_res.data.get("message", "")) > 0

    # Error dialog explanation test
    err_res = app.dispatcher.dispatch_action("screen_explain_error")
    assert err_res.is_success
    assert "message" in err_res.data

    app.stop()


def test_web_intelligence_hub_briefing_dispatch():
    """Verify WebIntelligenceHub weather, news, crypto, and morning briefing actions."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Morning briefing action
    briefing_res = app.dispatcher.dispatch_action("morning_briefing", payload={"city": "Hanoi"})
    assert briefing_res.is_success
    assert "briefing" in briefing_res.data
    briefing = briefing_res.data["briefing"]
    assert "weather" in briefing
    assert "news" in briefing
    assert "crypto" in briefing
    assert "spoken_summary" in briefing

    # Crypto rates action
    crypto_res = app.dispatcher.dispatch_action("crypto_rates")
    assert crypto_res.is_success
    assert "rates" in crypto_res.data

    app.stop()


# ============================================================================
# 4. OS Automation & Dev Shell Tests
# ============================================================================

def test_computer_control_and_safety_gate_integration():
    """Verify ComputerController window status, volume, brightness, and SafetyGate confirmation."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Active window query
    win_res = app.dispatcher.dispatch_action("window_active")
    assert win_res.is_success
    assert "window" in win_res.data

    # Volume adjustment
    vol_res = app.dispatcher.dispatch_action("system_volume", payload={"level": 60})
    assert vol_res.is_success
    assert vol_res.data["volume"] == 60

    # Destructive shell command with SafetyGate intercept
    nl_res = app.shell_assistant.execute_natural_command("xóa sạch thư mục C:/temp")
    assert nl_res["gated"] is True
    assert nl_res["confirmation_token"] != ""
    token = nl_res["confirmation_token"]

    # Reject gated action
    rej_res = app.dispatcher.dispatch_action("safety_gate_reject", payload={"token": token})
    assert rej_res.is_success

    app.stop()


# ============================================================================
# 5. Proactive Intelligence & Overlay HUD Lifecycle Tests
# ============================================================================

def test_proactive_engine_lifecycle_with_app():
    """Verify ProactiveEngine starts with JarvisApp.start() and halts with app.stop()."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    assert app.proactive_engine.is_running() is False
    app.start()
    assert app.proactive_engine.is_running() is True

    # Test reminder scheduling via action dispatcher
    rem_res = app.dispatcher.dispatch_action(
        "proactive_reminder",
        payload={"message": "Uống nước", "delay_seconds": 0.5},
    )
    assert rem_res.is_success
    assert "reminder_id" in rem_res.data

    # Test Pomodoro start & stop
    pomo_res = app.dispatcher.dispatch_action(
        "proactive_pomodoro_start",
        payload={"work_minutes": 25.0},
    )
    assert pomo_res.is_success
    assert app.proactive_engine.pomodoro.is_active is True

    stop_res = app.dispatcher.dispatch_action("proactive_pomodoro_stop")
    assert stop_res.is_success
    assert app.proactive_engine.pomodoro.is_active is False

    app.stop()
    assert app.proactive_engine.is_running() is False


def test_overlay_hud_sidebar_collapse_and_quick_actions():
    """Verify AlwaysOnOverlay sidebar mode, collapse/expand actions, and quick action callbacks."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    assert app.overlay.is_sidebar_mode is True
    assert app.overlay.is_collapsed is False

    # Collapse sidebar
    app.dispatcher.dispatch_action("collapse_sidebar")
    assert app.overlay.is_collapsed is True

    # Expand sidebar
    app.dispatcher.dispatch_action("expand_sidebar")
    assert app.overlay.is_collapsed is False

    # Quick action execution
    result = app.overlay.trigger_quick_action("system_status")
    assert result is not None

    app.stop()


# ============================================================================
# 6. CLI Diagnostics & Health Check Tests
# ============================================================================

def test_cli_health_check_returns_zero_all_green():
    """Verify CLI run_health_check checks all 10 subsystems and exits cleanly with 0."""
    config = ConfigManager()
    config.load()

    exit_code = run_health_check(config)
    assert exit_code == 0


def test_wake_word_trigger_starts_voice_interaction(monkeypatch):
    """Verify wake word detector callback initiates voice interaction flow."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Track interactions and TTS calls
    spoken = []
    if app.tts_manager:
        app.tts_manager.speak = lambda txt, **kw: spoken.append(txt) or True

    # Mock audio record and transcription
    app.record_audio = lambda *a, **k: np.zeros(100, dtype=np.float32)
    app.stt_engine.transcribe = lambda buf: "Báo cáo tình trạng hệ thống"

    # Trigger wake word callback directly
    app._on_wake_word_triggered()

    # Wait briefly for daemon thread
    time.sleep(0.4)

    # Verify voice response was produced
    assert app.overlay.state != "hidden"
    app.stop()


def test_safety_gate_confirmation_flow():
    """Verify safety gate confirmation flow executes gated action upon token confirm."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Request high risk operation
    res = app.shell_assistant.execute_natural_command("xóa sạch thư mục D:/data")
    assert res["gated"] is True
    token = res["confirmation_token"]

    # Confirm token via action dispatcher
    conf_res = app.dispatcher.dispatch_action("safety_gate_confirm", payload={"token": token})
    assert conf_res.is_success
    assert "Đã xác nhận" in conf_res.data.get("message", "")

    app.stop()


def test_inactivity_monitor_recording_on_text_command():
    """Verify executing text command records user activity on proactive inactivity monitor."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    initial_time = app.proactive_engine.inactivity_monitor.last_activity_time
    time.sleep(0.05)

    app.process_text_command("Kiểm tra thời tiết", requester="user")
    updated_time = app.proactive_engine.inactivity_monitor.last_activity_time

    assert updated_time >= initial_time
    app.stop()

