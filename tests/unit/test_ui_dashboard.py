"""
tests/unit/test_ui_dashboard.py
==============================
Unit tests for JARVIS System Tray and Real-Time Dashboard (F-16 & F-17).
Covers:
  - SystemTrayController status transitions, dynamic PIL icons, and context handlers
  - DashboardServer HTTP server lifecycle, REST API endpoints, and dark UI serving
  - Telemetry and Event broadcasting
  - Command execution and configuration hot-updates
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.ui.dashboard import (
    DASHBOARD_HTML,
    DashboardMetricsServer,
    DashboardServer,
)
from jarvis.ui.tray import (
    PIL_AVAILABLE,
    SystemTrayController,
    TrayStatus,
    create_status_icon,
)

# ============================================================================
# 1. SYSTEM TRAY CONTROLLER TESTS
# ============================================================================

def test_system_tray_status_transitions_and_events():
    """Test SystemTrayController status changes and EventBus publications."""
    bus = EventBus()
    events = []
    bus.subscribe("tray.status_updated", lambda **ev: events.append(ev))

    tray = SystemTrayController(event_bus=bus)
    assert tray.status == "active"

    tray.update_status(TrayStatus.LISTENING)
    assert tray.status == "listening"

    tray.update_status("muted")
    assert tray.status == "muted"

    tray.update_status("error")
    assert tray.status == "error"

    assert len(events) == 3
    assert events[0]["status"] == "listening"
    assert events[1]["status"] == "muted"
    assert events[2]["status"] == "error"


def test_system_tray_icon_generation():
    """Test dynamic PIL arc-reactor icon rendering."""
    if not PIL_AVAILABLE:
        pytest.skip("Pillow not installed")

    img_active = create_status_icon(TrayStatus.ACTIVE, size=(32, 32))
    assert img_active is not None
    assert img_active.size == (32, 32)
    assert img_active.mode == "RGBA"

    img_listening = create_status_icon(TrayStatus.LISTENING, size=(64, 64))
    assert img_listening is not None
    assert img_listening.size == (64, 64)

    img_muted = create_status_icon(TrayStatus.MUTED)
    assert img_muted is not None


def test_system_tray_lifecycle_and_actions():
    """Test start, stop, and context menu actions."""
    app_mock = MagicMock()
    tray = SystemTrayController(app=app_mock)

    tray.start()
    assert tray.is_running is True
    assert "Open Dashboard" in tray.menu_items
    assert "Exit" in tray.menu_items

    # Toggle Mute Action
    tray._on_toggle_mute()
    assert tray._is_mic_muted is True
    assert tray.status == "muted"

    tray._on_toggle_mute()
    assert tray._is_mic_muted is False
    assert tray.status == "active"

    # Toggle Gestures Action
    tray._on_toggle_gestures()
    assert tray._gestures_enabled is False

    tray.stop()
    assert tray.is_running is False


# ============================================================================
# 2. REAL-TIME DASHBOARD SERVER & REST API TESTS
# ============================================================================

def _find_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def test_dashboard_server():
    """Spawns DashboardServer on ephemeral localhost port."""
    port = _find_free_port()
    ws_port = _find_free_port()
    dispatcher = ActionDispatcher()
    dispatcher.register_action("sample_action", lambda: {"status": "ok"}, description="Sample action")

    server = DashboardServer(host="127.0.0.1", port=port, ws_port=ws_port, dispatcher=dispatcher)
    server.start()
    time.sleep(0.05)
    return server


def test_dashboard_http_server_endpoints(test_dashboard_server):
    """Test all REST API endpoints served by DashboardServer."""
    base_url = f"http://127.0.0.1:{test_dashboard_server.port}"

    # 1. GET / (HTML Dark HUD UI)
    with urllib.request.urlopen(f"{base_url}/") as res:
        assert res.status == 200
        html = res.read().decode("utf-8")
        assert "JARVIS SYSTEM CONTROLLER" in html

    # 2. GET /api/status
    with urllib.request.urlopen(f"{base_url}/api/status") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data["status"] == "healthy"

    # 3. GET /api/telemetry
    test_dashboard_server.broadcast_telemetry({"cpu_percent": 24.5, "ram_percent": 50.0})
    with urllib.request.urlopen(f"{base_url}/api/telemetry") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data["cpu_percent"] == 24.5

    # 4. GET /api/actions
    with urllib.request.urlopen(f"{base_url}/api/actions") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "actions" in data
        assert any(a["name"] == "sample_action" for a in data["actions"])

    # 5. GET /api/logs
    with urllib.request.urlopen(f"{base_url}/api/logs") as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "logs" in data

    # 6. POST /api/command (direct action)
    req = urllib.request.Request(
        f"{base_url}/api/command",
        data=json.dumps({"action": "sample_action"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data["success"] is True

    # 7. POST /api/command (text command fallback)
    req_txt = urllib.request.Request(
        f"{base_url}/api/command",
        data=json.dumps({"command": "kiểm tra nhiệt độ cpu"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req_txt) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "response_text" in data


def test_dashboard_event_broadcasting_and_metrics_summary():
    """Test telemetry and event broadcasting history."""
    server = DashboardServer()
    server.broadcast_telemetry({"gpu_percent": 45.0})
    server.broadcast_event({"type": "test_event", "value": 123})

    summary = server.get_status_summary()
    assert summary["status"] == "healthy"
    assert summary["telemetry"]["gpu_percent"] == 45.0
    assert len(server._event_history) == 1


def test_dashboard_metrics_server_alias():
    """Verify DashboardMetricsServer backward compatibility alias."""
    metrics_srv = DashboardMetricsServer()
    assert isinstance(metrics_srv, DashboardServer)
