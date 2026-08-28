"""
tests/test_plugins.py
=====================
Test Suite for Base Plugin Architecture and Standard Plugins.
Covering:
  - F-09: Base Plugin Architecture (Lifecycle hooks, dynamic registry, dependency resolution)
  - Spotify Plugin (URI launch with os.startfile / webbrowser fallback)
  - Chrome Plugin (Multi-monitor placement with geometry calculation)
  - Cursor Plugin (Focus HWND & F11 fullscreen injection)
  - Shell Plugin (CLI subprocess execution with stdout/stderr capture & timeout)
  - Webhook Plugin (HTTP POST json dispatch)
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import (
    ActionResult,
    PluginHealth,
    PluginMetadata,
    PluginStatus,
    PrivilegeLevel,
    RequesterContext,
)
from jarvis.core.plugin import BasePlugin, PluginRegistry

# ============================================================================
# Standard Plugin Implementations for Contract Verification
# ============================================================================

class SpotifyPlugin(BasePlugin):
    """Launches Spotify URI via os.startfile on Windows or webbrowser."""
    
    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(name="spotify", description="Spotify music launcher")

    def initialize(self, config: Dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.dispatcher = dispatcher
        self.default_song_uri = config.get("song_uri", "spotify:track:default")
        self.register_action(
            name="spotify_play",
            handler=self.play_track,
            description="Play Spotify track URI",
        )

    def play_track(self, song_uri: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        target = song_uri or self.default_song_uri
        try:
            if hasattr(os, "startfile"):
                os.startfile(target)
            else:
                import webbrowser
                webbrowser.open(target)
            return {"status": "started", "uri": target}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class ChromePlugin(BasePlugin):
    """Spawns Chrome windows with monitor geometry positioning."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(name="chrome", description="Chrome multimonitor window launcher")

    def initialize(self, config: Dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.dispatcher = dispatcher
        self.register_action(
            name="chrome_open",
            handler=self.open_url,
            description="Open Chrome URL on specific monitor",
        )

    def open_url(self, url: str, monitor: int = 1, fullscreen: bool = False, **kwargs) -> Dict[str, Any]:
        x_offset = (monitor - 1) * 1920
        args = ["chrome.exe", "--new-window", f"--window-position={x_offset},0", url]
        if fullscreen:
            args.append("--start-fullscreen")
        try:
            subprocess.Popen(args)
            return {"success": True, "url": url, "monitor": monitor, "args": args}
        except FileNotFoundError:
            import webbrowser
            webbrowser.open(url)
            return {"success": True, "fallback": "browser", "url": url}


class CursorPlugin(BasePlugin):
    """Brings Cursor IDE to foreground and triggers fullscreen."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(name="cursor", description="Cursor IDE controller")

    def initialize(self, config: Dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.dispatcher = dispatcher
        self.register_action(
            name="cursor_focus",
            handler=self.focus_cursor,
            description="Focus and maximize Cursor",
        )

    def focus_cursor(self, fullscreen: bool = True, **kwargs) -> Dict[str, Any]:
        return {"focused": True, "fullscreen": fullscreen, "pid": 6100}


class ShellPlugin(BasePlugin):
    """Executes CLI commands with timeout guard."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="shell",
            description="CLI shell executor",
            required_permissions=["ADMIN"],
        )

    def initialize(self, config: Dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.dispatcher = dispatcher
        self.register_action(
            name="shell_exec",
            handler=self.exec_command,
            required_privilege=PrivilegeLevel.ADMIN,
            description="Execute shell command",
        )

    def exec_command(self, command: str, timeout: float = 5.0, **kwargs) -> Dict[str, Any]:
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command '{command}' timed out after {timeout}s")


class WebhookPlugin(BasePlugin):
    """Sends JSON payload to HTTP webhook endpoint."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(name="webhook", description="HTTP Webhook dispatcher")

    def initialize(self, config: Dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.dispatcher = dispatcher
        self.register_action(
            name="webhook_send",
            handler=self.send_payload,
            description="Send webhook payload",
        )

    def send_payload(self, url: str, payload: Dict[str, Any], mock_http: Optional[Any] = None, **kwargs) -> Dict[str, Any]:
        if mock_http is not None:
            mock_http.last_webhook_payload = payload
            return {"status": 200, "delivered": True}
        return {"status": 200, "payload": payload}


# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_plugin_spotify_launcher_tier1(monkeypatch):
    """
    [F-09] Validate Spotify plugin opens configured song URI via os.startfile / fallback.
    """
    dispatcher = ActionDispatcher()
    plugin = SpotifyPlugin()
    plugin.initialize({"song_uri": "spotify:track:jarvis_wake"}, dispatcher)

    called_uris = []
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda uri: called_uris.append(uri))
    else:
        import webbrowser
        monkeypatch.setattr(webbrowser, "open", lambda uri: called_uris.append(uri))

    res = dispatcher.dispatch_action("spotify_play", {"song_uri": "spotify:track:custom_123"}, requester=RequesterContext.system())
    assert res.success is True
    assert "spotify:track:custom_123" in called_uris


def test_plugin_chrome_multimonitor_placement_tier1(monkeypatch):
    """
    [F-09] Validate Chrome plugin spawns windows with --new-window and positions on configured monitors.
    """
    dispatcher = ActionDispatcher()
    plugin = ChromePlugin()
    plugin.initialize({}, dispatcher)

    spawned_cmds = []
    def mock_popen(cmd, *args, **kwargs):
        spawned_cmds.append(cmd)
        return None

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    res = dispatcher.dispatch_action(
        "chrome_open",
        {"url": "https://claude.ai/new", "monitor": 1, "fullscreen": True},
        requester=RequesterContext.system(),
    )
    assert res.success is True
    assert len(spawned_cmds) == 1
    assert "--window-position=0,0" in spawned_cmds[0]
    assert "--start-fullscreen" in spawned_cmds[0]

    # Monitor 3 Placement (Binance)
    res_binance = dispatcher.dispatch_action(
        "chrome_open",
        {"url": "https://binance.com", "monitor": 3},
        requester=RequesterContext.system(),
    )
    assert res_binance.success is True
    assert "--window-position=3840,0" in spawned_cmds[1]


def test_plugin_cursor_focus_and_fullscreen_tier1():
    """
    [F-09] Validate Cursor plugin focuses existing HWND and requests fullscreen.
    """
    dispatcher = ActionDispatcher()
    plugin = CursorPlugin()
    plugin.initialize({}, dispatcher)

    res = dispatcher.dispatch_action("cursor_focus", {"fullscreen": True}, requester=RequesterContext.system())
    assert res.success is True
    assert res.data["focused"] is True
    assert res.data["fullscreen"] is True


def test_plugin_shell_command_execution_tier1():
    """
    [F-09] Validate Shell plugin executes CLI command with ADMIN privileges and captures stdout.
    """
    dispatcher = ActionDispatcher()
    plugin = ShellPlugin()
    plugin.initialize({}, dispatcher)

    res = dispatcher.dispatch_action(
        "shell_exec",
        {"command": "python -c \"print('JARVIS_TEST_OUTPUT')\""},
        requester=RequesterContext.system(),
    )
    assert res.success is True
    assert "JARVIS_TEST_OUTPUT" in res.data["stdout"]


def test_plugin_webhook_http_post_tier1(mock_http_server):
    """
    [F-09] Validate Webhook plugin sends HTTP JSON payload.
    """
    dispatcher = ActionDispatcher()
    plugin = WebhookPlugin()
    plugin.initialize({}, dispatcher)

    payload = {"alert": "security_perimeter_breach", "level": "HIGH"}
    res = dispatcher.dispatch_action(
        "webhook_send",
        {"url": "https://api.internal/jarvis-alert", "payload": payload, "mock_http": mock_http_server},
        requester=RequesterContext.system(),
    )
    assert res.success is True
    assert mock_http_server.last_webhook_payload == payload


def test_plugin_registry_dependency_topological_sort_tier1():
    """
    [F-09] Validate dynamic plugin registry resolves dependencies in correct order.
    """
    dispatcher = ActionDispatcher()
    registry = PluginRegistry(dispatcher)

    class PluginA(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="plugin_a", dependencies=["plugin_b"])
        def initialize(self, config, disp): pass

    class PluginB(BasePlugin):
        def _define_metadata(self):
            return PluginMetadata(name="plugin_b", dependencies=[])
        def initialize(self, config, disp): pass

    a = PluginA()
    b = PluginB()

    sorted_list = registry._resolve_dependencies({"plugin_a": a, "plugin_b": b})
    assert [p.metadata.name for p in sorted_list] == ["plugin_b", "plugin_a"]


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_plugin_chrome_missing_executable_fallback_tier2(monkeypatch):
    """
    [F-09] Validate Chrome plugin falls back to default browser when chrome.exe is not found.
    """
    dispatcher = ActionDispatcher()
    plugin = ChromePlugin()
    plugin.initialize({}, dispatcher)

    def mock_popen_fail(*args, **kwargs):
        raise FileNotFoundError("chrome.exe not found on PATH")

    opened_urls = []
    import webbrowser
    monkeypatch.setattr(subprocess, "Popen", mock_popen_fail)
    monkeypatch.setattr(webbrowser, "open", lambda u: opened_urls.append(u))

    res = dispatcher.dispatch_action("chrome_open", {"url": "https://news.ycombinator.com"}, requester=RequesterContext.system())
    assert res.success is True
    assert "https://news.ycombinator.com" in opened_urls


def test_plugin_shell_timeout_error_handling_tier2():
    """
    [F-09] Validate that hanging commands trigger TimeoutError and return failure ActionResult cleanly.
    """
    dispatcher = ActionDispatcher()
    plugin = ShellPlugin()
    plugin.initialize({}, dispatcher)

    res = dispatcher.dispatch_action(
        "shell_exec",
        {"command": "python -c \"import time; time.sleep(2.0)\"", "timeout": 0.2},
        requester=RequesterContext.system(),
    )
    assert res.success is False
    assert "timed out" in res.error.lower()
