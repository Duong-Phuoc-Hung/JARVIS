"""
tests/unit/test_screen_context_awaci.py
=======================================
Unit tests for Active Window & Context Injection (AWACI) Engine and Router Integration.
Tests:
  - WindowContext data structure and serialization.
  - App categorization and sub-context extraction.
  - Native AWACI engine telemetry caching and execution latency (< 0.05ms).
  - Context-aware intent disambiguation ("dừng lại", "phóng to", "thu nhỏ", "lưu file", "đóng tab").
  - Seamless router integration with fail-closed safety.
"""
from __future__ import annotations

import time
import pytest

from jarvis.context.screen_context import (
    AWACIEngine,
    WindowContext,
    classify_app_and_subcontext,
    get_active_window_context,
)
from jarvis.llm.client import LLMClient
from jarvis.llm.router import LLMIntentRouter


def test_window_context_data_structure():
    """Verify WindowContext creation, defaults, and dictionary export."""
    ctx = WindowContext(
        hwnd=12345,
        title="Test Window Title",
        process_name="chrome.exe",
        app_category="browser",
        sub_context="web_browsing",
        is_valid=True,
        timestamp=100.0,
    )
    d = ctx.to_dict()
    assert d["hwnd"] == 12345
    assert d["title"] == "Test Window Title"
    assert d["process_name"] == "chrome.exe"
    assert d["app_category"] == "browser"
    assert d["sub_context"] == "web_browsing"
    assert d["is_valid"] is True
    assert d["timestamp"] == 100.0


def test_classify_app_and_subcontext():
    """Verify categorization of known apps into proper semantic domains and sub-contexts."""
    # YouTube video in Chrome
    cat, sub = classify_app_and_subcontext("chrome.exe", "Sơn Tùng M-TP - Lạc Trôi - YouTube - Google Chrome")
    assert cat == "browser"
    assert sub == "youtube_video"

    # Google Docs in Edge
    cat, sub = classify_app_and_subcontext("msedge.exe", "Báo cáo quý 4 - Google Docs - Microsoft Edge")
    assert cat == "browser"
    assert sub == "web_document"

    # GitHub in Firefox
    cat, sub = classify_app_and_subcontext("firefox.exe", "Pull Request #42 · JARVIS/main - GitHub")
    assert cat == "browser"
    assert sub == "code_repo"

    # Spotify
    cat, sub = classify_app_and_subcontext("spotify.exe", "Spotify Premium")
    assert cat == "media_player"
    assert sub == "music_playback"

    # VS Code
    cat, sub = classify_app_and_subcontext("code.exe", "screen_context.py - JARVIS - Visual Studio Code")
    assert cat == "code_editor"
    assert sub == "code_workspace"

    # Windows Terminal
    cat, sub = classify_app_and_subcontext("windowsterminal.exe", "Administrator: Windows PowerShell")
    assert cat == "terminal"
    assert sub == "terminal_shell"

    # Microsoft Word
    cat, sub = classify_app_and_subcontext("winword.exe", "Document1 - Word")
    assert cat == "document_editor"
    assert sub == "document_editing"


def test_awaci_engine_latency_and_caching():
    """Verify that cached window telemetry executes well under 0.05ms."""
    engine = AWACIEngine(cache_ttl_s=0.1)

    # Initial call
    ctx1 = engine.get_current_window_context()
    assert isinstance(ctx1, WindowContext)

    # Benchmarking cached calls
    times = []
    for _ in range(100):
        t0 = time.perf_counter()
        _ = engine.get_current_window_context()
        times.append((time.perf_counter() - t0) * 1000.0)

    p50 = float(sorted(times)[len(times) // 2])
    # Cached call must be ultra-fast (sub-0.05ms)
    assert p50 < 0.05, f"Cached AWACI latency {p50:.4f}ms exceeds 0.05ms target"


def test_disambiguate_stop_command():
    """Verify context-dependent resolution of 'dừng lại' across media, browser, and terminal."""
    engine = AWACIEngine()

    # Case A: YouTube in Chrome
    ctx_yt = WindowContext(
        hwnd=1,
        title="MixiGaming - Live Stream - YouTube - Google Chrome",
        process_name="chrome.exe",
        app_category="browser",
        sub_context="youtube_video",
        is_valid=True,
    )
    res_yt = engine.disambiguate_intent("dừng lại", "unknown", context=ctx_yt)
    assert res_yt is not None
    action, params, text, conf = res_yt
    assert action == "media_control"
    assert params["command"] == "pause"
    assert params["target"] == "youtube"
    assert conf >= 0.95

    # Case B: Spotify
    ctx_spot = WindowContext(
        hwnd=2,
        title="Spotify Free",
        process_name="spotify.exe",
        app_category="media_player",
        sub_context="music_playback",
        is_valid=True,
    )
    res_spot = engine.disambiguate_intent("dừng lại", "unknown", context=ctx_spot)
    assert res_spot is not None
    action, params, text, conf = res_spot
    assert action == "media_control"
    assert params["command"] == "pause"
    assert params["target"] == "media_player"

    # Case C: Terminal
    ctx_term = WindowContext(
        hwnd=3,
        title="Command Prompt",
        process_name="cmd.exe",
        app_category="terminal",
        sub_context="terminal_shell",
        is_valid=True,
    )
    res_term = engine.disambiguate_intent("dừng lại", "unknown", context=ctx_term)
    assert res_term is not None
    action, params, text, conf = res_term
    assert action == "terminal_control"
    assert params["action"] == "interrupt"


def test_disambiguate_zoom_and_save():
    """Verify context-dependent resolution of 'phóng to', 'thu nhỏ', and 'lưu file'."""
    engine = AWACIEngine()
    ctx_code = WindowContext(
        hwnd=10,
        title="main.py - Visual Studio Code",
        process_name="code.exe",
        app_category="code_editor",
        sub_context="code_workspace",
        is_valid=True,
    )

    # Zoom in
    res_zoom = engine.disambiguate_intent("phóng to", "unknown", context=ctx_code)
    assert res_zoom is not None
    action, params, text, conf = res_zoom
    assert action == "window_control"
    assert params["action"] == "zoom_in"

    # Zoom out
    res_out = engine.disambiguate_intent("thu nhỏ", "unknown", context=ctx_code)
    assert res_out is not None
    action, params, text, conf = res_out
    assert action == "window_control"
    assert params["action"] == "zoom_out"

    # Save file
    res_save = engine.disambiguate_intent("lưu file", "unknown", context=ctx_code)
    assert res_save is not None
    action, params, text, conf = res_save
    assert action == "file_save"
    assert params["action"] == "save_active"


def test_router_awaci_integration():
    """Verify that LLMIntentRouter properly uses AWACI context in Tier 1 fast path."""
    mock_llm = LLMClient.__new__(LLMClient)
    router = LLMIntentRouter(llm_client=mock_llm, fast_path_enabled=True, awaci_enabled=True)

    # Explicit WindowContext passed in route
    ctx_yt = WindowContext(
        hwnd=99,
        title="Taylor Swift - Blank Space - YouTube - Google Chrome",
        process_name="chrome.exe",
        app_category="browser",
        sub_context="youtube_video",
        is_valid=True,
    )

    res = router.route("dừng lại", window_context=ctx_yt)
    assert res.action_name == "media_control"
    assert res.parameters.get("command") == "pause"
    assert res.parameters.get("target") == "youtube"
    assert res.source == "awaci_context"
    assert res.confidence >= 0.95

    # Context passed via dictionary in context={"window_context": ...}
    ctx_code_dict = {
        "hwnd": 101,
        "title": "script.py - Visual Studio Code",
        "process_name": "code.exe",
        "app_category": "code_editor",
        "sub_context": "code_workspace",
        "is_valid": True,
    }
    res_save = router.route("lưu lại", context={"window_context": ctx_code_dict})
    assert res_save.action_name == "file_save"
    assert res_save.parameters.get("action") == "save_active"
    assert res_save.source == "awaci_context"

    # Close tab
    res_close_tab = router.route("đóng tab", context={"window_context": ctx_code_dict})
    assert res_close_tab.action_name == "tab_control"
    assert res_close_tab.parameters.get("action") == "close_tab"
    assert res_close_tab.source == "awaci_context"


def test_awaci_fail_closed_on_invalid_context():
    """Verify fail-closed behavior when window context is invalid or empty."""
    mock_llm = LLMClient.__new__(LLMClient)
    router = LLMIntentRouter(llm_client=mock_llm, fast_path_enabled=True, awaci_enabled=True)

    invalid_ctx = WindowContext(is_valid=False)
    # When context is invalid and query has no static rule, router does not invent false positive
    res = router.route("dừng lại", window_context=invalid_ctx)
    # Notice without context, "dừng lại" has no AWACI match, falls through to normal pipeline
    assert res.source != "awaci_context"


def test_awaci_new_tab_and_streaming_domains():
    """Verify AWACI supports multimedia streaming domains, new tab, and Vietnamese synonyms."""
    engine = AWACIEngine()

    # Twitch in Chrome
    cat, sub = classify_app_and_subcontext("chrome.exe", "Twitch - Live Stream - Google Chrome")
    assert cat == "browser"
    assert sub == "youtube_video"

    # Netflix in Edge
    cat, sub = classify_app_and_subcontext("msedge.exe", "Stranger Things - Netflix - Microsoft Edge")
    assert cat == "browser"
    assert sub == "youtube_video"

    ctx_stream = WindowContext(
        hwnd=50,
        title="Live Stream - Twitch - Google Chrome",
        process_name="chrome.exe",
        app_category="browser",
        sub_context="youtube_video",
        is_valid=True,
    )

    # "dừng video"
    res_pause = engine.disambiguate_intent("dừng video", "unknown", context=ctx_stream)
    assert res_pause is not None
    assert res_pause[0] == "media_control"
    assert res_pause[1]["command"] == "pause"

    # "phát video"
    res_play = engine.disambiguate_intent("phát video", "unknown", context=ctx_stream)
    assert res_play is not None
    assert res_play[0] == "media_control"
    assert res_play[1]["command"] == "play"

    # "mở tab mới"
    res_new_tab = engine.disambiguate_intent("mở tab mới", "unknown", context=ctx_stream)
    assert res_new_tab is not None
    assert res_new_tab[0] == "tab_control"
    assert res_new_tab[1]["action"] == "new_tab"

    # "đóng thẻ"
    res_close_the = engine.disambiguate_intent("đóng thẻ", "unknown", context=ctx_stream)
    assert res_close_the is not None
    assert res_close_the[0] == "tab_control"
    assert res_close_the[1]["action"] == "close_tab"


def test_jarvis_app_awaci_actions_registered():
    """Verify that file_save, tab_control, window_control, terminal_control, browser_control are all registered in JarvisApp."""
    from jarvis.core.dispatcher import ActionDispatcher
    from jarvis.core.handlers.system_handlers import SystemHandlersMixin
    from unittest.mock import MagicMock

    class MockApp(SystemHandlersMixin):
        def __init__(self):
            self.computer_controller = MagicMock()
            self.tts_manager = None
            self.dispatcher = ActionDispatcher()

    app = MockApp()
    # Register actions
    app.dispatcher.register_action("file_save", app._handle_file_save)
    app.dispatcher.register_action("tab_control", app._handle_tab_control)
    app.dispatcher.register_action("window_control", app._handle_window_control)
    app.dispatcher.register_action("terminal_control", app._handle_terminal_control)
    app.dispatcher.register_action("browser_control", app._handle_browser_control)

    # 1. file_save
    app.computer_controller.send_hotkey.return_value = True
    res_save = app.dispatcher.dispatch_action("file_save", {})
    assert res_save.success is True
    app.computer_controller.send_hotkey.assert_called_with("ctrl", "s")

    # 2. tab_control (new_tab)
    app.computer_controller.send_hotkey.return_value = True
    res_new_tab = app.dispatcher.dispatch_action("tab_control", {"action": "new_tab"})
    assert res_new_tab.success is True
    app.computer_controller.send_hotkey.assert_called_with("ctrl", "t")

    # 3. tab_control (close_tab)
    app.computer_controller.close_tab.return_value = True
    res_close_tab = app.dispatcher.dispatch_action("tab_control", {"action": "close_tab"})
    assert res_close_tab.success is True
    app.computer_controller.close_tab.assert_called_once()

    # 4. window_control (zoom_in)
    app.computer_controller.send_hotkey.return_value = True
    res_zoom = app.dispatcher.dispatch_action("window_control", {"action": "zoom_in"})
    assert res_zoom.success is True

    # 5. terminal_control (interrupt)
    res_term = app.dispatcher.dispatch_action("terminal_control", {"action": "interrupt"})
    assert res_term.success is True
    app.computer_controller.send_hotkey.assert_called_with("ctrl", "c")

    # 6. browser_control (reload)
    app.computer_controller.refresh_page.return_value = True
    res_reload = app.dispatcher.dispatch_action("browser_control", {"action": "reload"})
    assert res_reload.success is True
    app.computer_controller.refresh_page.assert_called_once()

