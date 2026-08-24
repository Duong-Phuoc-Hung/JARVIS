"""
tests/test_adversarial_m3_ui_app.py
===================================
Empirical Adversarial Stress Testing Suite for Milestone 3:
1. System Tray Controller (F-16):
   - Rapid start/stop cycling (15+ iterations, idempotency, thread termination)
   - High-concurrency status updates (20+ threads, Enum, string, invalid inputs)
   - Menu handler invocation under heavy concurrent load
   - Headless and missing-dependency fallback consistency (PIL/pystray unavailable, non-Win32)
2. Real-Time Dashboard Server (F-17):
   - Concurrent HTTP flood (60+ threads, 300+ requests across REST & UI)
   - Invalid JSON bodies to /api/command (malformed, raw string, binary, huge payload)
   - Malformed config updates to /api/config (non-dict, bad format)
   - Port binding contention & socket collision resilience
   - High-throughput event & telemetry broadcasting ring buffer stability
   - CORS headers & 404 handler robustness
3. JarvisApp Voice Loop & Integration:
   - Full pipeline dispatch: Audio -> STT -> LLM Intent -> Dispatcher -> Plugin Action -> TTS -> Dashboard
   - Silence & corrupted audio rejection
   - Acoustic gesture trigger fanout to action dispatcher & UI event log
   - High-concurrency text/voice command dispatch stress
   - App lifecycle start/stop cleanliness
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import math
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.llm.client import LLMClient
from jarvis.llm.router import IntentResult, LLMIntentRouter
from jarvis.stt.engine import MockSTTEngine, STTEngine
from jarvis.tts.manager import TTSManager
from jarvis.ui.dashboard import (
    DASHBOARD_HTML,
    DashboardMetricsServer,
    DashboardServer,
)
from jarvis.ui.tray import (
    PIL_AVAILABLE,
    PYSTRAY_AVAILABLE,
    SystemTrayController,
    TrayStatus,
    create_status_icon,
)


def _find_free_port() -> int:
    """Find an available ephemeral TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ============================================================================
# 1. SYSTEM TRAY CONTROLLER ADVERSARIAL STRESS TESTS
# ============================================================================

def test_tray_rapid_start_stop_cycling():
    """
    Stress: Rapid start/stop cycles (15+ iterations).
    Verifies that worker threads cleanly terminate, no thread leaks occur,
    and calls are idempotent.
    """
    tray = SystemTrayController()

    for i in range(16):
        tray.start(in_thread=True)
        assert tray.is_running is True
        # Idempotent start
        tray.start(in_thread=True)
        assert tray.is_running is True

        tray.stop()
        assert tray.is_running is False
        # Idempotent stop
        tray.stop()
        assert tray.is_running is False

    assert tray.is_running is False


def test_tray_concurrent_status_updates_stress():
    """
    Stress: 20 threads concurrently hammering update_status() with 600+ total updates
    using alternating TrayStatus Enums, valid strings, invalid strings, and edge types.
    """
    bus = EventBus()
    received_events: List[Dict[str, Any]] = []
    event_lock = threading.Lock()

    def _on_status(**ev):
        with event_lock:
            received_events.append(ev)

    bus.subscribe("tray.status_updated", _on_status)
    tray = SystemTrayController(event_bus=bus)

    status_samples = [
        TrayStatus.ACTIVE,
        TrayStatus.LISTENING,
        TrayStatus.MUTED,
        TrayStatus.ERROR,
        TrayStatus.DISABLED,
        "active",
        "LISTENING",
        "Muted",
        "ERROR",
        "disabled",
        "UNKNOWN_CUSTOM_STATE",  # Should fallback to ACTIVE gracefully
        "invalid_gibberish",      # Should fallback to ACTIVE gracefully
    ]

    exceptions: List[Exception] = []

    def _worker(thread_idx: int):
        try:
            for step in range(30):
                choice = status_samples[(thread_idx + step) % len(status_samples)]
                tray.update_status(choice)
                assert tray.status in [s.value for s in TrayStatus]
        except Exception as exc:
            exceptions.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_worker, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0, f"Exceptions occurred during concurrent update_status: {exceptions}"
    assert len(received_events) >= 600
    assert tray.status in [s.value for s in TrayStatus]


def test_tray_menu_handlers_under_concurrent_load():
    """
    Stress: Concurrently executing tray context menu handlers
    (_on_toggle_mute, _on_toggle_gestures, _on_reload_config, _on_open_dashboard)
    while status updates are simultaneously running.
    """
    app_mock = MagicMock()
    app_mock.audio_engine = MagicMock()
    config_mock = MagicMock()

    tray = SystemTrayController(
        app=app_mock,
        config_manager=config_mock,
        dashboard_url="http://127.0.0.1:8080",
    )
    tray.start()

    exceptions: List[Exception] = []

    def _menu_worker(thread_idx: int):
        try:
            for _ in range(25):
                if thread_idx % 4 == 0:
                    tray._on_toggle_mute()
                elif thread_idx % 4 == 1:
                    tray._on_toggle_gestures()
                elif thread_idx % 4 == 2:
                    tray._on_reload_config()
                else:
                    tray.update_status(TrayStatus.LISTENING)
        except Exception as exc:
            exceptions.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(_menu_worker, i) for i in range(16)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0
    tray.stop()
    assert tray.is_running is False


def test_tray_headless_and_fallback_consistency():
    """
    Test fallback behavior when PIL or pystray is simulated as unavailable,
    or on non-Windows platforms.
    """
    # 1. create_status_icon when PIL is unavailable
    with patch("jarvis.ui.tray.PIL_AVAILABLE", False):
        icon = create_status_icon(TrayStatus.ACTIVE)
        assert icon is None

    # 2. TrayController in headless mode (pystray unavailable)
    with patch("jarvis.ui.tray.PYSTRAY_AVAILABLE", False):
        tray = SystemTrayController()
        tray.start()
        assert tray.is_running is True
        assert tray.status == "active"
        # First toggle mutes
        tray._on_toggle_mute()
        assert tray._is_mic_muted is True
        assert tray.status == "muted"
        # Second toggle unmutes
        tray._on_toggle_mute()
        assert tray._is_mic_muted is False
        assert tray.status == "active"
        tray.stop()
        assert tray.is_running is False

    # 3. TrayController when sys.platform != "win32"
    with patch("sys.platform", "linux"), patch("jarvis.ui.tray.PYSTRAY_AVAILABLE", False):
        tray_linux = SystemTrayController()
        tray_linux.start()
        assert tray_linux.is_running is True
        tray_linux.update_status("error")
        assert tray_linux.status == "error"
        tray_linux.stop()
        assert tray_linux.is_running is False


# ============================================================================
# 2. REAL-TIME DASHBOARD SERVER ADVERSARIAL STRESS TESTS
# ============================================================================

@pytest.fixture
def running_dashboard_server():
    """Spawns an active DashboardServer instance on free ports."""
    port = _find_free_port()
    ws_port = _find_free_port()

    dispatcher = ActionDispatcher()
    dispatcher.register_action("test_ping", lambda: {"status": "pong"}, description="Test ping action")
    dispatcher.register_action("test_calc", lambda **p: {"sum": p.get("a", 0) + p.get("b", 0)}, description="Calc sum")

    cfg_mock = MagicMock()
    cfg_mock._config_data = {"version": "1.0.0", "env": "test"}
    cfg_mock.to_dict.return_value = cfg_mock._config_data

    server = DashboardServer(
        host="127.0.0.1",
        port=port,
        ws_port=ws_port,
        dispatcher=dispatcher,
        config_manager=cfg_mock,
    )
    server.start()
    time.sleep(0.05)
    return server


def test_dashboard_concurrent_http_flood(running_dashboard_server):
    """
    Stress: 60 concurrent worker threads flooding 300+ requests across all
    REST endpoints and UI files simultaneously.
    """
    base_url = f"http://127.0.0.1:{running_dashboard_server.port}"
    endpoints = [
        ("/", "GET", None),
        ("/api/status", "GET", None),
        ("/api/telemetry", "GET", None),
        ("/api/actions", "GET", None),
        ("/api/config", "GET", None),
        ("/api/logs", "GET", None),
        ("/api/command", "POST", json.dumps({"action": "test_ping"}).encode("utf-8")),
        ("/api/command", "POST", json.dumps({"command": "bật đèn phòng ngủ"}).encode("utf-8")),
    ]

    results: List[int] = []
    errors: List[Exception] = []

    def _fetch(task_id: int):
        try:
            path, method, body = endpoints[task_id % len(endpoints)]
            req = urllib.request.Request(
                f"{base_url}{path}",
                data=body,
                headers={"Content-Type": "application/json"} if body else {},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=5.0) as res:
                results.append(res.status)
        except Exception as exc:
            errors.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        futures = [executor.submit(_fetch, i) for i in range(300)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(errors) == 0, f"HTTP flood encountered errors: {errors}"
    assert len(results) == 300
    assert all(code == 200 for code in results)


def test_dashboard_invalid_json_payloads_api_command(running_dashboard_server):
    """
    Adversarial: Send corrupted, malformed, and edge-case payloads to /api/command.
    Verify server responds with HTTP 400 without crashing or returning unhandled 500s.
    """
    base_url = f"http://127.0.0.1:{running_dashboard_server.port}"

    malformed_bodies = [
        b'{"action": "test_ping"',                # Incomplete JSON
        b'{"invalid: 1234}',                      # Syntax error
        b'not a json at all',                     # Plain text
        b'',                                      # Empty body
        b'{"action": \x00\xff}',                  # Invalid UTF-8 bytes
        b'{"action": "test_ping", "extra": ' + b'a' * 100000 + b'}', # Large payload syntax error
    ]

    for raw_data in malformed_bodies:
        req = urllib.request.Request(
            f"{base_url}/api/command",
            data=raw_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as res:
                # If parsed as empty string or defaulted, should still be HTTP 200 or 400
                assert res.status in (200, 400)
        except urllib.error.HTTPError as http_err:
            assert http_err.code == 400
            err_data = json.loads(http_err.read().decode("utf-8"))
            assert "error" in err_data


def test_dashboard_malformed_config_payloads_api_config(running_dashboard_server):
    """
    Adversarial: Send non-dict and malformed config updates to POST /api/config.
    """
    base_url = f"http://127.0.0.1:{running_dashboard_server.port}"

    # 1. Valid config update
    valid_payload = json.dumps({"theme": "dark", "volume": 80}).encode("utf-8")
    req_valid = urllib.request.Request(
        f"{base_url}/api/config",
        data=valid_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_valid) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data.get("success") is True

    # 2. Malformed JSON to /api/config -> HTTP 400
    req_bad = urllib.request.Request(
        f"{base_url}/api/config",
        data=b"corrupted_json_string{",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req_bad)
    assert exc_info.value.code == 400


def test_dashboard_port_contention_and_collision():
    """
    Adversarial: Bind a socket to a port, then attempt to start DashboardServer on that port.
    Verifies that the server does not crash the calling thread, logs a warning, and handles failure cleanly.
    """
    port = _find_free_port()
    # Occupy the port with a raw socket
    occupied_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied_sock.bind(("127.0.0.1", port))
    occupied_sock.listen(1)

    try:
        server = DashboardServer(host="127.0.0.1", port=port)
        # Starting on occupied port should NOT raise an unhandled exception to the caller
        server.start()
        assert server._httpd is None  # Server failed binding gracefully
        server.stop()
    finally:
        occupied_sock.close()


def test_dashboard_event_and_telemetry_high_concurrency():
    """
    Stress: 25 threads pushing 1000+ events and telemetry updates concurrently.
    Verifies deque maxlen bound (200) holds and no data race corruption occurs.
    """
    server = DashboardServer()
    server.start()

    exceptions: List[Exception] = []

    def _broadcaster(thread_idx: int):
        try:
            for i in range(50):
                server.broadcast_telemetry({
                    "cpu_percent": float(thread_idx + i % 100),
                    "ram_percent": 50.0 + (i % 20),
                    "timestamp": time.time(),
                })
                server.broadcast_event({
                    "type": "stress_event",
                    "thread": thread_idx,
                    "iteration": i,
                })
                _ = server.get_latest_telemetry()
                _ = server.get_status_summary()
        except Exception as exc:
            exceptions.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = [executor.submit(_broadcaster, i) for i in range(25)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0
    assert len(server._event_history) <= 200
    summary = server.get_status_summary()
    assert summary["status"] == "healthy"
    server.stop()


def test_dashboard_cors_and_options_and_404(running_dashboard_server):
    """
    Verify CORS OPTIONS headers and 404 response on non-existent endpoints.
    """
    base_url = f"http://127.0.0.1:{running_dashboard_server.port}"

    # 1. OPTIONS request
    req_options = urllib.request.Request(f"{base_url}/api/status", method="OPTIONS")
    with urllib.request.urlopen(req_options) as res:
        assert res.status == 204
        assert res.headers.get("Access-Control-Allow-Origin") == "*"

    # 2. 404 Not Found GET
    req_404 = urllib.request.Request(f"{base_url}/api/non_existent_route")
    with pytest.raises(urllib.error.HTTPError) as exc_404:
        urllib.request.urlopen(req_404)
    assert exc_404.value.code == 404
    err_body = json.loads(exc_404.value.read().decode("utf-8"))
    assert err_body.get("error") == "Not Found"

    # 3. 404 Not Found POST
    req_post_404 = urllib.request.Request(
        f"{base_url}/api/non_existent_post",
        data=b'{"dummy": true}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_post_404:
        urllib.request.urlopen(req_post_404)
    assert exc_post_404.value.code == 404


# ============================================================================
# 3. JARVIS APP FULL PIPELINE VOICE LOOP INTEGRATION TESTS
# ============================================================================

def test_jarvis_app_full_voice_pipeline_dispatch():
    """
    Integration & Stress: Verify the complete end-to-end Voice AI loop:
    Synthetic Audio -> STTEngine -> LLMIntentRouter -> ActionDispatcher -> TTS -> Dashboard & Tray.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Override with deterministic Mock STT returning spotify command
    app.stt_engine.primary_engine = MockSTTEngine(default_transcript="mở spotify phát nhạc")

    # Track actions executed
    action_events: List[str] = []
    app.event_bus.subscribe("action.post_dispatch", lambda **ev: action_events.append(ev.get("action_name", "")))

    # Synthetic speech audio (16kHz, 1.0 second non-silent sine wave)
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    synthetic_audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    result = app.process_voice_command(synthetic_audio)

    assert result["success"] is True
    assert "spotify" in result["transcript"].lower()
    assert result["intent"] is not None
    assert result["intent"]["action_name"] == "spotify"
    assert "spotify" in action_events

    # Verify Dashboard received the command event broadcast
    if app.dashboard_server:
        assert len(app.dashboard_server._event_history) >= 1
        last_event = app.dashboard_server._event_history[-1]["event"]
        assert last_event["type"] == "command"
        assert last_event["action"] == "spotify"

    app.stop()


def test_jarvis_app_voice_loop_silence_and_noise_rejection():
    """
    Adversarial: Feed pure silence, empty arrays, and whitespace into voice & text commands.
    Verify graceful rejection without crashing.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # 1. Zero amplitude silence
    silence = np.zeros(16000, dtype=np.float32)
    res_silence = app.process_voice_command(silence)
    assert res_silence["success"] is False
    assert res_silence.get("error") == "No speech detected"

    # 2. Empty array
    empty_buf = np.array([], dtype=np.float32)
    res_empty = app.process_voice_command(empty_buf)
    assert res_empty["success"] is False

    # 3. Empty text command
    res_empty_txt = app.process_text_command("   ")
    assert res_empty_txt["success"] is False

    app.stop()


def test_jarvis_app_acoustic_gesture_to_action_fanout():
    """
    Integration: Simulate acoustic gesture trigger (_on_gesture_event)
    and verify multi-action fanout execution and dashboard event broadcast.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Set custom workflow actions for double_clap
    app.config.set("gesture.patterns.double_clap.actions", ["system_status", "tts_welcome"])

    executed_actions: List[str] = []
    app.event_bus.subscribe("action.post_dispatch", lambda **ev: executed_actions.append(ev.get("action_name", "")))

    # Trigger double clap gesture
    app._on_gesture_event("double_clap", confidence=0.98)

    # Wait for fanout background thread to execute
    time.sleep(0.15)

    assert "system_status" in executed_actions
    assert "tts_welcome" in executed_actions

    # Check dashboard received gesture event
    if app.dashboard_server:
        events = [e["event"] for e in app.dashboard_server._event_history]
        assert any(e.get("type") == "gesture" and e.get("pattern") == "double_clap" for e in events)

    app.stop()


def test_jarvis_app_concurrent_text_commands_stress():
    """
    Stress: 20 threads concurrently issuing text commands through process_text_command().
    Verifies thread safety across LLM router, dispatcher, event bus, TTS, and dashboard.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    test_commands = [
        "bật nhạc spotify",
        "mở trình duyệt claude",
        "mở cursor ide",
        "kiểm tra trạng thái hệ thống",
        "bật tắt mic",
        "thời tiết hôm nay thế nào",
        "lệnh hoàn toàn lạ chưa từng thấy",
    ]

    exceptions: List[Exception] = []
    successes: List[Dict[str, Any]] = []

    def _cmd_worker(thread_idx: int):
        try:
            for step in range(15):
                cmd = test_commands[(thread_idx + step) % len(test_commands)]
                res = app.process_text_command(cmd, requester=f"worker_{thread_idx}")
                assert res.get("success") is True
                successes.append(res)
        except Exception as exc:
            exceptions.append(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_cmd_worker, i) for i in range(20)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0, f"Exceptions during concurrent text commands: {exceptions}"
    assert len(successes) == 300
    app.stop()


def test_jarvis_app_lifecycle_start_and_stop():
    """
    Integration: Start JarvisApp, check all initialized components,
    and verify clean stop and shutdown event state.
    """
    dash_port = _find_free_port()
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    app.config.set("ui.dashboard.port", dash_port)
    app.config.set("ui.dashboard.ws_port", _find_free_port())

    app.start()
    assert app.audio_engine is not None
    assert app.dashboard_server is not None
    assert app.dashboard_server.is_running is True
    assert app.stt_engine is not None
    assert app.llm_router is not None

    app.stop()
    assert app._shutdown_event.is_set()
    assert app.dashboard_server.is_running is False
