"""
tests/unit/test_plugins_m2.py
=============================
Unit tests for Milestone 2 plugins (Spotify, Chrome Multi-Monitor, Cursor IDE).
"""
import os
import subprocess

import pytest

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import RequesterContext
from jarvis.plugins.chrome import ChromeMultiMonitorPlugin
from jarvis.plugins.cursor import CursorPlugin
from jarvis.plugins.spotify import SpotifyPlugin


def test_spotify_plugin_execution(monkeypatch):
    """Verify Spotify plugin invokes startfile/webbrowser with configured URI."""
    dispatcher = ActionDispatcher()
    plugin = SpotifyPlugin()
    plugin.initialize({"song_uri": "spotify:track:default_track"}, dispatcher)

    opened = []
    if hasattr(os, "startfile"):
        monkeypatch.setattr(os, "startfile", lambda uri: opened.append(uri))
    else:
        import webbrowser
        monkeypatch.setattr(webbrowser, "open", lambda uri: opened.append(uri))

    res = dispatcher.dispatch_action("spotify_play", {"song_uri": "spotify:track:custom_456"}, requester=RequesterContext.system())
    assert res.success is True
    assert "spotify:track:custom_456" in opened


def test_chrome_multimonitor_plugin_placement(monkeypatch):
    """Verify Chrome plugin constructs correct window coordinates for Monitor 1 and Monitor 3."""
    dispatcher = ActionDispatcher()
    plugin = ChromeMultiMonitorPlugin()
    plugin.initialize(
        {
            "claude_url": "https://claude.ai/new",
            "binance_url": "https://binance.com/en/trade/BTC_USDT",
            "claude_monitor": 1,
            "binance_monitor": 3,
        },
        dispatcher,
    )

    spawned = []
    def mock_popen(args, *p_args, **kwargs):
        spawned.append(args)
        return None

    monkeypatch.setattr(subprocess, "Popen", mock_popen)

    # Launch Claude on Monitor 1
    res1 = dispatcher.dispatch_action("chrome_claude", requester=RequesterContext.system())
    assert res1.success is True
    assert len(spawned) == 1
    assert "--window-position=0,0" in spawned[0]
    assert "https://claude.ai/new" in spawned[0]

    # Launch Binance on Monitor 3
    res2 = dispatcher.dispatch_action("chrome_binance", requester=RequesterContext.system())
    assert res2.success is True
    assert len(spawned) == 2
    assert "--window-position=3840,0" in spawned[1]
    assert "https://binance.com/en/trade/BTC_USDT" in spawned[1]


def test_cursor_plugin_focus_and_fullscreen():
    """Verify Cursor plugin executes focus action and returns status."""
    dispatcher = ActionDispatcher()
    plugin = CursorPlugin()
    plugin.initialize({"fullscreen": True}, dispatcher)

    res = dispatcher.dispatch_action("cursor_focus", {"fullscreen": True}, requester=RequesterContext.system())
    assert res.success is True
    assert res.data["focused"] is True
    assert res.data["fullscreen"] is True
