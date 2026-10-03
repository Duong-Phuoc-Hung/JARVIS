"""
tests/unit/test_system_refinements_and_fixes.py
===============================================
Comprehensive regression tests for Edge TTS PCM decoding, brightness routing,
clipboard dispatch, window maximize, shell argument sanitization, and Spotify media controls.
"""
from __future__ import annotations

import io
import tempfile
import wave
from unittest.mock import MagicMock, patch

import pytest

from jarvis.automation.shell_assistant import ShellAssistant
from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.llm.router import LLMIntentRouter
from jarvis.plugins.spotify import SpotifyPlugin
from jarvis.tts.edge import EdgeTTS, _mp3_to_pcm
from jarvis.tts.manager import TTSManager


def test_edge_tts_synthesize_pcm_contract():
    """Verify EdgeTTS synthesize_to_bytes returns decoded 16-bit PCM bytes."""
    edge = EdgeTTS()
    assert edge.engine_name == "edge_tts"
    assert edge.sample_rate == 24000
    assert edge.voice_id == "vi-VN-HoaiMyNeural"

    # Test _mp3_to_pcm with mock MP3 or live synthesis if available
    def _mock_run(coro):
        coro.close()
        return b"FAKE_MP3_DATA"

    fake_pcm = b"\x00\x01" * 12000  # 1 second of 16-bit mono 12000 samples
    with patch("jarvis.tts.edge.EdgeTTS.is_available", return_value=True), \
         patch("jarvis.tts.edge._run_async", side_effect=_mock_run), \
         patch("jarvis.tts.edge._mp3_to_pcm", return_value=fake_pcm):
        pcm = edge.synthesize_to_bytes("Xin chào")
        assert pcm == fake_pcm
        assert len(pcm) % 2 == 0


def test_tts_manager_edge_tts_cache_integration():
    """Verify TTSManager with edge_tts writes a valid PCM WAV cache entry."""
    fake_pcm = b"\x00\x02" * 24000  # 1 sec of 24kHz 16-bit mono PCM
    with tempfile.TemporaryDirectory() as tmp_dir:
        with patch.object(EdgeTTS, "is_available", return_value=True), \
             patch.object(EdgeTTS, "synthesize_to_bytes", return_value=fake_pcm):
            mgr = TTSManager({"provider": "edge_tts", "cache": {"enabled": True, "dir": tmp_dir}})
            with patch("sounddevice.play"), patch("sounddevice.wait"):
                ok = mgr.speak("Chào buổi sáng", wait=True)
                assert ok is True

            cached = mgr.cache.get("Chào buổi sáng", voice_id=mgr.primary_engine.voice_id,
                                   model_id=mgr.primary_engine.model_id,
                                   output_format=mgr.primary_engine.output_format)
            assert cached is not None and cached.is_file()
            with wave.open(str(cached), "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 24000
            mgr.stop()


def test_router_brightness_mappings():
    """Verify brightness commands route to system_brightness, not system_volume."""
    router = LLMIntentRouter(MagicMock())
    test_cases = [
        ("do sang man hinh", "system_brightness", {"query": True}),
        ("độ sáng màn hình", "system_brightness", {"query": True}),
        ("tang do sang", "system_brightness", {"delta": 10}),
        ("giam do sang", "system_brightness", {"delta": -10}),
        ("tăng độ sáng", "system_brightness", {"delta": 10}),
        ("giảm độ sáng", "system_brightness", {"delta": -10}),
    ]
    for utterance, expected_action, expected_params in test_cases:
        res = router.parse_intent(utterance, force_llm=False)
        assert res.action_name == expected_action, f"'{utterance}' misrouted to {res.action_name}"
        for k, v in expected_params.items():
            assert res.parameters.get(k) == v, f"'{utterance}' expected {k}={v}, got {res.parameters.get(k)}"


def test_router_clipboard_diacritics():
    """Verify both 'cắt' (with diacritic) and 'cat' route to skill_clipboard cut."""
    router = LLMIntentRouter(MagicMock())
    for phrase in ["cắt", "cat"]:
        res = router.parse_intent(phrase, force_llm=False)
        assert res.action_name == "skill_clipboard"
        assert res.parameters.get("action") == "cut"

    res_clear = router.parse_intent("xóa clipboard", force_llm=False)
    assert res_clear.action_name == "skill_clipboard"
    assert res_clear.parameters.get("action") == "clear"


def test_app_clipboard_actions():
    """Verify ActionDispatcher handles skill_clipboard and clipboard actions."""
    app = JarvisApp.__new__(JarvisApp)
    app.dispatcher = ActionDispatcher()
    app._register_core_actions()
    app.computer_controller = MagicMock()
    app.computer_controller.send_hotkey.return_value = True
    app.computer_controller.set_clipboard_text.return_value = True
    app.computer_controller.paste_text.return_value = True
    app.computer_controller.copy_selection.return_value = "HELLO_CLIP"
    app.computer_controller.get_clipboard_text.return_value = "READ_CLIP"

    # Cut
    r_cut = app.dispatcher.dispatch_action("skill_clipboard", {"action": "cut"})
    assert r_cut.success is True
    app.computer_controller.send_hotkey.assert_called_with("ctrl", "x")

    # Copy
    r_copy = app.dispatcher.dispatch_action("skill_clipboard", {"action": "copy"})
    assert r_copy.success is True
    assert r_copy.data["text"] == "HELLO_CLIP"

    # Paste
    r_paste = app.dispatcher.dispatch_action("skill_clipboard", {"action": "paste", "text": "paste_val"})
    assert r_paste.success is True
    app.computer_controller.paste_text.assert_called_with("paste_val")

    # Read
    r_read = app.dispatcher.dispatch_action("clipboard", {"action": "read"})
    assert r_read.success is True
    assert r_read.data["text"] == "READ_CLIP"


def test_app_brightness_query():
    """Verify _handle_system_brightness supports query=True truthfully."""
    app = JarvisApp.__new__(JarvisApp)
    app.dispatcher = ActionDispatcher()
    app._register_core_actions()
    app.computer_controller = MagicMock()
    app.computer_controller.get_brightness.return_value = 80

    res = app.dispatcher.dispatch_action("system_brightness", {"query": True})
    assert res.success is True
    assert res.data["brightness"] == 80
    assert "80%" in res.data["message"]
    app.computer_controller.change_brightness.assert_not_called()
    app.computer_controller.set_brightness.assert_not_called()


def test_window_maximize_native():
    """Verify window_active maximize calls win32.maximize_window on active hwnd."""
    app = JarvisApp.__new__(JarvisApp)
    app.dispatcher = ActionDispatcher()
    app._register_core_actions()
    app.computer_controller = MagicMock()
    app.computer_controller.get_active_window.return_value = {"hwnd": 9999, "title": "Target Window"}
    app.computer_controller.win32 = MagicMock()
    app.computer_controller.win32.maximize_window.return_value = True

    res = app.dispatcher.dispatch_action("window_active", {"action": "maximize"})
    assert res.success is True
    assert "Target Window" in res.data["message"]
    app.computer_controller.win32.maximize_window.assert_called_with(9999)


def test_file_search_clarify_on_create():
    """Verify file_search with action=create requests clarification without sweeping drive."""
    app = JarvisApp.__new__(JarvisApp)
    app.dispatcher = ActionDispatcher()
    app._register_core_actions()
    app.computer_controller = MagicMock()

    res = app.dispatcher.dispatch_action("file_search", {"action": "create", "clarify": True})
    assert res.success is True
    assert res.data.get("clarification_required") is True
    app.computer_controller.search_files.assert_not_called()


def test_shell_assistant_time_and_date_fast_path():
    """Verify date/time queries return instant formatted responses without subprocesses."""
    sa = ShellAssistant()
    res_time = sa.execute_natural_command("mấy giờ rồi")
    assert res_time["success"] is True
    assert "giờ" in res_time["message"]

    res_date = sa.execute_natural_command("hôm nay thứ mấy")
    assert res_date["success"] is True
    assert "Thứ" in res_date["message"] or "Chủ Nhật" in res_date["message"]


def test_shell_assistant_windows_quote_stripping():
    """Verify custom command tokens on Windows have enclosing quotes stripped."""
    sa = ShellAssistant()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="OUTPUT_OK", stderr="")
        res = sa.execute_natural_command("powershell -c \"Write-Output 'HELLO'\"")
        assert res["success"] is True
        call_tokens = mock_run.call_args[0][0]
        # Must not contain literal outer double quotes in the script argument
        assert '"Write-Output \'HELLO\'"' not in call_tokens
        assert "Write-Output 'HELLO'" in call_tokens


def test_spotify_media_controls():
    """Verify SpotifyPlugin sends media keys for previous, next, pause."""
    plugin = SpotifyPlugin()
    plugin.initialize({}, MagicMock())

    with patch("jarvis.platform.windows.WindowsPlatformAPI.send_hotkey", return_value=True) as mock_hk:
        res_prev = plugin.play_track(action="previous")
        assert res_prev["status"] == "success"
        mock_hk.assert_called_with("media_prev")

        res_next = plugin.play_track(action="next")
        assert res_next["status"] == "success"
        mock_hk.assert_called_with("media_next")

        res_pause = plugin.play_track(action="pause")
        assert res_pause["status"] == "success"
        mock_hk.assert_called_with("media_play_pause")
