"""
tests/unit/test_system_refinements_and_fixes.py
===============================================
Comprehensive regression tests for Edge TTS PCM decoding, brightness routing,
clipboard dispatch, window maximize, shell argument sanitization, and Spotify media controls.
"""
from __future__ import annotations

import io
import tempfile
import time
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
    app.tts_manager = None
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


def test_youtube_intents_and_video_search():
    """Verify YouTube homepage and specific video searches route to web_open with correct URLs."""
    router = LLMIntentRouter(MagicMock())
    home_queries = [
        "mở youtube",
        "mở xem youtube",
        "xem youtube",
        "bật youtube",
        "vào xem youtube",
        "cho tao vào youtube",
    ]
    for q in home_queries:
        res = router.parse_intent(q, force_llm=False)
        assert res.action_name == "web_open", f"'{q}' should route to web_open"
        assert res.parameters.get("site") == "youtube"

    search_queries = [
        ("mở youtube xem nhạc sơn tùng", "youtube xem nhạc sơn tùng"),
        ("xem video lofi trên youtube", "https://www.youtube.com/results?search_query=lofi"),
        ("bật bài hát em của ngày hôm qua trên youtube", "https://www.youtube.com/results?search_query=em+c%E1%BB%A7a+ng%C3%A0y+h%C3%B4m+qua"),
        ("youtube sơn tùng mtp", "https://www.youtube.com/results?search_query=s%C6%A1n+t%C3%B9ng+mtp"),
        ("tìm nhạc edm trên youtube", "https://www.youtube.com/results?search_query=edm"),
    ]
    for q, expected_target in search_queries:
        res = router.parse_intent(q, force_llm=False)
        assert res.action_name == "web_open", f"'{q}' should route to web_open"
        assert res.parameters.get("target") == expected_target, f"'{q}' expected target {expected_target}, got {res.parameters.get('target')}"


def test_healing_watchdog_heal_action_registration_and_execution():
    """Verify healing_watchdog_heal is registered in ActionDispatcher and executes cleanly."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    assert app.dispatcher.get_action("healing_watchdog_heal") is not None
    res = app.process_text_command("dọn dẹp ram")
    assert res["success"] is True
    assert res["intent"]["action_name"] == "healing_watchdog_heal"
    assert "kiểm tra tiến trình" in res["result"]["message"]
    app.stop()


def test_security_nmap_scan_action_registration_and_execution():
    """Verify security_nmap_scan is registered in ActionDispatcher and handles execution gracefully."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    assert app.dispatcher.get_action("security_nmap_scan") is not None
    res = app.process_text_command("quét mạng nội bộ")
    assert res["intent"]["action_name"] == "security_nmap_scan"
    assert res["result"]["action_name"] == "security_nmap_scan"
    # Even if Nmap is absent on host, it returns structured status instead of ACTION_NOT_FOUND
    assert res["result"]["error_code"] != "ACTION_NOT_FOUND"
    app.stop()


def test_lock_screen_vs_screen_off_routing_distinction():
    """Verify 'khóa màn hình' routes to lock and 'tắt màn hình' routes to screen_off without collision."""
    router = LLMIntentRouter(MagicMock())
    res_lock = router.parse_intent("khóa màn hình", force_llm=False)
    assert res_lock.action_name == "system_power"
    assert res_lock.parameters.get("action") == "lock"

    res_off = router.parse_intent("tắt màn hình", force_llm=False)
    assert res_off.action_name == "system_power"
    assert res_off.parameters.get("action") == "screen_off"


def test_system_power_screen_off_execution():
    """Verify system_power screen_off executes successfully and non-blocking."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    res = app.process_text_command("tắt màn hình")
    assert res["success"] is True
    assert res["result"]["action_name"] == "system_power"
    assert "tắt màn hình" in res["result"]["message"].lower()
    app.stop()


def test_skill_registry_accepts_skill_metadata_objects():
    """Verify SkillRegistry methods accept SkillMetadata objects without unhashable type errors."""
    from jarvis.skills.registry import SkillRegistry
    sr = SkillRegistry()
    skills = sr.list_skills()
    assert len(skills) > 0
    meta = skills[0]
    assert sr.is_skill_registered(meta) is True
    skill_def = sr.get_skill(meta)
    assert skill_def is not None
    assert skill_def.metadata.name == meta.name


def test_system_power_abort_and_suspend_opt_in():
    """Verify system_power abort execution and hardware suspend opt-in."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # 1. Abort shutdown executes without requiring confirmation and reports status
    fake_win32 = MagicMock()
    fake_win32.abort_shutdown.return_value = True
    app.computer_controller.win32 = fake_win32

    res_abort = app.process_text_command("hủy tắt máy")
    assert res_abort["success"] is True
    assert res_abort["result"]["action_name"] == "system_power"
    assert "hủy lệnh tắt máy" in res_abort["result"]["message"]
    fake_win32.abort_shutdown.assert_called_once()

    # 2. Suspend/Sleep with allow_hardware_power_actions opt-in
    app.config.set("power.allow_hardware_power_actions", True)
    fake_win32.suspend_system.return_value = True
    res_sleep = app._handle_system_power(action="sleep")
    assert res_sleep["success"] is True
    assert "chế độ ngủ" in res_sleep["message"]
    fake_win32.suspend_system.assert_called_with(hibernate=False)
    app.stop()


def test_battery_probing_and_voice_formatting():
    """Verify battery telemetry probing and voice summary in HardwareReporter."""
    from jarvis.hardware.monitor import HardwareMetrics, HardwareMonitor
    from jarvis.hardware.reporter import HardwareReporter

    metrics = HardwareMetrics(
        cpu_percent=15.0,
        cpu_temp_c=45.0,
        gpu_percent=None,
        gpu_temp_c=None,
        ram_percent=50.0,
        vram_used_gb=None,
        smart_status="PASSED",
        battery_percent=85.0,
        battery_power_plugged=True,
        battery_secsleft=7200,
    )
    d = metrics.to_dict()
    assert d["battery_percent"] == 85.0
    assert d["battery_power_plugged"] is True

    mon = HardwareMonitor()
    reporter = HardwareReporter(mon)

    summary_vi = reporter.format_component_summary("pin", metrics=metrics, lang="vi")
    assert "85 phần trăm" in summary_vi
    assert "đang cắm sạc" in summary_vi

    summary_en = reporter.format_component_summary("battery", metrics=metrics, lang="en")
    assert "85 percent" in summary_en
    assert "plugged in" in summary_en


def test_skill_synthesizer_live_registration_and_cleanup(tmp_path):
    """Verify skill synthesizer live loads into SkillRegistry and unregisters cleanly."""
    from jarvis.skills.registry import SkillRegistry
    from jarvis.skills.skill_synthesizer import execute as synth_execute

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    sr = SkillRegistry(skills_dir=skills_dir, auto_discover=False)

    # Monkeypatch root
    import jarvis.skills.skill_synthesizer as synth_mod
    orig_root = synth_mod._SKILLS_ROOT
    synth_mod._SKILLS_ROOT = skills_dir

    try:
        res_create = synth_execute(
            action="create",
            skill_name="test_temp_calc",
            description="Kỹ năng tính toán tạm thời",
            registry=sr,
        )
        assert res_create["data"]["success"] is True
        assert sr.is_skill_registered("test_temp_calc") is True
        assert "kích hoạt kỹ năng" in res_create["data"]["text"]

        res_delete = synth_execute(
            action="delete",
            skill_name="test_temp_calc",
            registry=sr,
        )
        assert res_delete["data"]["success"] is True
        assert sr.is_skill_registered("test_temp_calc") is False
    finally:
        synth_mod._SKILLS_ROOT = orig_root


def test_router_battery_and_abort_intents():
    """Verify router maps battery and abort intents accurately."""
    router = LLMIntentRouter(MagicMock())

    for q in ["kiểm tra pin", "pin còn bao nhiêu", "tình trạng pin", "xem pin", "check battery"]:
        res = router.parse_intent(q, force_llm=False)
        assert res.action_name == "hardware_telemetry_check", f"'{q}' should route to hardware_telemetry_check"
        assert res.parameters.get("component") == "battery"

    for q in ["hủy tắt máy", "hủy shutdown", "hủy khởi động lại", "cancel shutdown", "abort shutdown"]:
        res = router.parse_intent(q, force_llm=False)
        assert res.action_name == "system_power", f"'{q}' should route to system_power"
        assert res.parameters.get("action") == "abort"


def test_window_advanced_snap_and_switch():
    """Verify window snap (left/right) and switch hotkey operations."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    fake_win32 = MagicMock()
    fake_win32.send_hotkey.return_value = True
    fake_win32.close_window.return_value = True
    app.computer_controller.win32 = fake_win32

    # Snap Left
    res_left = app._handle_window_active(action="snap_left")
    assert res_left["success"] is True
    fake_win32.send_hotkey.assert_called_with("win", "left")

    # Snap Right
    res_right = app._handle_window_active(action="snap_right")
    assert res_right["success"] is True
    fake_win32.send_hotkey.assert_called_with("win", "right")

    # Switch
    res_switch = app._handle_window_active(action="switch")
    assert res_switch["success"] is True
    fake_win32.send_hotkey.assert_called_with("alt", "tab")

    # Close
    res_close = app._handle_window_active(action="close")
    assert res_close["status"] == "success"

    app.stop()


@patch("jarvis.web.finance.FinanceTracker._fetch_exchange_rate", return_value=25000.0)
def test_forex_currency_rate_query(_fetch):
    """Verify Forex exchange rate retrieval and formatting for USD and EUR."""
    from jarvis.web.finance import FinanceTracker
    ft = FinanceTracker()
    usd_rate = ft.get_exchange_rate("USD", "VND")
    assert usd_rate > 20000.0

    summary_usd = ft.get_forex_summary("USD")
    assert "Đô la Mỹ" in summary_usd
    assert "Việt Nam Đồng" in summary_usd

    summary_eur = ft.get_forex_summary("EUR")
    assert "Euro" in summary_eur
    assert "Việt Nam Đồng" in summary_eur

    # Test via JarvisApp handler
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    res = app._handle_crypto_rates(currency="USD")
    assert res["success"] is True
    assert res["currency"] == "USD"
    assert "Đô la Mỹ" in res["message"]
    app.stop()


def test_voice_note_taking_and_desktop_sync(tmp_path, monkeypatch):
    """Verify personal voice note addition, desktop sync, and listing."""
    fake_home = tmp_path / "user"
    fake_desktop = fake_home / "Desktop"
    fake_desktop.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    monkeypatch.setenv("LOCALAPPDATA", str(fake_home / "LocalAppData"))

    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Add Note
    res_add = app._handle_note_add(content="Kiểm tra hệ thống JARVIS v5.2")
    assert res_add["success"] is True
    assert "Kiểm tra hệ thống JARVIS v5.2" in res_add["message"]

    # Verify Desktop file created
    notes_file = fake_desktop / "JARVIS_Notes.md"
    assert notes_file.exists()
    assert "Kiểm tra hệ thống JARVIS v5.2" in notes_file.read_text(encoding="utf-8")

    # List Notes
    res_list = app._handle_note_list()
    assert res_list["success"] is True
    assert "Kiểm tra hệ thống JARVIS v5.2" in res_list["message"]

    app.stop()


def test_router_window_and_note_intents():
    """Verify router captures window snap, close, and voice notes."""
    router = LLMIntentRouter(MagicMock())

    # Window Snap
    res_snap = router.parse_intent("chia màn hình sang trái", force_llm=False)
    assert res_snap.action_name == "window_active"
    assert res_snap.parameters.get("action") == "snap_left"

    res_close = router.parse_intent("đóng cửa sổ", force_llm=False)
    assert res_close.action_name == "window_active"
    assert res_close.parameters.get("action") == "close"

    # Forex
    res_usd = router.parse_intent("tỷ giá usd", force_llm=False)
    assert res_usd.action_name == "crypto_rates"
    assert res_usd.parameters.get("currency") == "USD"

    # Notes
    res_note = router.parse_intent("ghi chú họp nhóm vào lúc 10h", force_llm=False)
    assert res_note.action_name == "note_add"
    assert res_note.parameters.get("content") == "họp nhóm vào lúc 10h"

    res_read = router.parse_intent("xem ghi chú", force_llm=False)
    assert res_read.action_name == "note_list"


def test_routine_engine_scheduling_and_recurring():
    """Verify routine scheduling, immediate dispatch, and recurring tick."""
    from jarvis.proactive.reminders import ReminderScheduler

    dispatched = []
    rs = ReminderScheduler(enabled=True)
    r_id = rs.schedule_routine(
        text="Dọn RAM tự động",
        delay_seconds=0.1,
        action_name="healing_watchdog_heal",
        repeat_interval_s=10.0,
        callback=lambda r: dispatched.append(r.action_name),
    )
    assert r_id is not None
    assert len(rs.get_pending_reminders()) == 1

    # Tick at trigger time
    due = rs.tick(now=time.time() + 0.2)
    assert len(due) == 1
    assert "healing_watchdog_heal" in dispatched
    # Recurring routine must be rescheduled
    pending = rs.get_pending_reminders()
    assert len(pending) == 1
    assert pending[0]["repeat_interval_s"] == 10.0


def test_deep_research_synthesis_and_desktop_export(tmp_path, monkeypatch):
    """Verify deep web research synthesis and executive markdown export."""
    from jarvis.web.hub import WebIntelligenceHub
    from jarvis.web.search import SearchResultItem

    fake_home = tmp_path / "research_user"
    fake_desktop = fake_home / "Desktop"
    fake_desktop.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    mock_searcher = MagicMock()
    mock_searcher.search.return_value = [
        SearchResultItem(title="Quantum AI 2026", url="https://example.com/quantum", snippet="Bước đột phá máy tính lượng tử trong trí tuệ nhân tạo."),
        SearchResultItem(title="QPU Scalability", url="https://example.com/qpu", snippet="Khả năng mở rộng chip lượng tử cho mô hình ngôn ngữ lớn."),
    ]

    hub = WebIntelligenceHub(search_engine=mock_searcher)
    res = hub.conduct_deep_research("quantum computing ai")
    assert res["success"] is True
    assert res["sources_count"] == 2
    assert "báo cáo nghiên cứu về quantum computing ai" in res["spoken_summary"]

    # Verify Desktop file
    report_file = list(fake_desktop.glob("JARVIS_Research_*.md"))
    assert len(report_file) == 1
    content = report_file[0].read_text(encoding="utf-8")
    assert "Báo Cáo Nghiên Cứu Chuyên Sâu: quantum computing ai" in content
    assert "Quantum AI 2026" in content


def test_error_dialog_dismissal_logic():
    """Verify error dialog detector dismissal mechanism."""
    from jarvis.vision.dialog_detector import ErrorDialogDetector
    detector = ErrorDialogDetector()
    assert detector is not None

    # Test with mock dialogs
    mock_dialogs = [
        {"hwnd": 1234, "title": "Application Error", "text": "Out of memory crash", "is_error": True},
    ]
    with patch.object(detector, "scan_for_dialogs", return_value=mock_dialogs):
        with patch.object(detector, "dismiss_dialog", return_value=True):
            resolved = detector.resolve_error_dialogs(auto_dismiss=True)
            assert len(resolved) == 1
            assert resolved[0]["dismissed"] is True
            assert resolved[0]["action_taken"] == "ok"


def test_ollama_offline_cascade_fallback():
    """Verify LLMClient cascades gracefully to Ollama when cloud provider fails."""
    from jarvis.llm.client import LLMClient, LLMProvider, ChatMessage, LLMResponse

    client = LLMClient(
        provider=LLMProvider.GEMINI,
        api_key="",
        fallback_to_ollama=True,
    )

    mock_ollama_resp = LLMResponse(content="Xin chào từ Ollama offline!", model="llama3.2")
    with patch.object(client, "_call_ollama", return_value=mock_ollama_resp):
        resp = client.chat([ChatMessage(role="user", content="hello")])
        assert resp.content == "Xin chào từ Ollama offline!"
        assert resp.provider == "ollama"


def test_router_routine_and_research_intents():
    """Verify router matches routine scheduling, deep research, and dialog resolve intents."""
    router = LLMIntentRouter(MagicMock())

    # Deep Research
    res_res = router.parse_intent("nghiên cứu về trí tuệ nhân tạo", force_llm=False)
    assert res_res.action_name == "deep_research"
    assert res_res.parameters.get("topic") == "trí tuệ nhân tạo"

    # Routine
    res_rou = router.parse_intent("mỗi 2 tiếng dọn dẹp ram", force_llm=False)
    assert res_rou.action_name == "routine_schedule"
    assert res_rou.parameters.get("action") == "healing_watchdog_heal"
    assert res_rou.parameters.get("interval_seconds") == 7200.0

    # Dialog resolve
    res_dlg = router.parse_intent("xử lý lỗi màn hình", force_llm=False)
    assert res_dlg.action_name == "dialog_resolve"
    assert res_dlg.parameters.get("auto_dismiss") is True


def test_vietnamese_verbal_math_evaluation():
    """Verify calculator handles verbal Vietnamese math expressions."""
    from jarvis.skills.calculator import evaluate_expression, execute as calc_execute

    assert evaluate_expression("15 cộng 35") == 50.0
    assert evaluate_expression("100 trừ 45") == 55.0
    assert evaluate_expression("25 nhân 4") == 100.0
    assert evaluate_expression("100 chia 5") == 20.0
    assert evaluate_expression("2 mũ 3") == 8.0

    res = calc_execute(expression="50 cộng 50")
    assert res["data"]["success"] is True
    assert res["data"]["result"] == 100.0


def test_conversational_llm_fallback():
    """Verify that unrecognized commands trigger natural conversational reply via LLM."""
    from jarvis.llm.client import LLMResponse
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    mock_llm = MagicMock()
    mock_llm.chat.return_value = LLMResponse(content="Hôm nay trời rất đẹp để lập trình, thưa Ngài.", model="gemini-1.5-flash")
    app.llm_client = mock_llm

    res = app.process_text_command("Hôm nay nên làm gì?")
    assert res["success"] is True
    assert "Hôm nay trời rất đẹp" in res["response_text"]
    mock_llm.chat.assert_called_once()
    app.stop()


def test_conversational_filler_word_stripping():
    """Verify that speech vocatives and conversational fillers are cleanly stripped before routing."""
    router = LLMIntentRouter(MagicMock())

    queries = [
        ("jarvis ơi mở google", "web_open"),
        ("ê jarvis kiểm tra pin", "hardware_telemetry_check"),
        ("này jarvis chụp màn hình", "screen_capture"),
        ("hãy giúp tôi dọn dẹp ram", "healing_watchdog_heal"),
        ("làm ơn đóng cửa sổ", "window_active"),
    ]
    for q, expected_act in queries:
        res = router.parse_intent(q, force_llm=False)
        assert res.action_name == expected_act, f"Query '{q}' failed to route to '{expected_act}' (got '{res.action_name}')"


def test_workflow_presets_work_relax_clean():
    """Verify productivity workflow presets (work, relax, clean)."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Work mode
    res_work = app._handle_workflow_preset(preset="work")
    assert res_work["success"] is True
    assert "làm việc tập trung" in res_work["message"]

    # Relax mode
    res_relax = app._handle_workflow_preset(preset="relax")
    assert res_relax["success"] is True
    assert "nghỉ ngơi" in res_relax["message"]

    # Clean mode
    res_clean = app._handle_workflow_preset(preset="clean")
    assert res_clean["success"] is True
    assert "kiểm tra tiến trình" in res_clean["message"]

    app.stop()


def test_dashboard_open_intent():
    """Verify intent router correctly maps dashboard open query."""
    router = LLMIntentRouter(MagicMock())
    res = router.parse_intent("mở dashboard", force_llm=False)
    assert res.action_name == "web_open"
    assert res.parameters.get("target") == "http://127.0.0.1:8080"


def test_tab_close_page_scroll_and_refresh():
    """Verify close tab, scroll page, and refresh page hotkey dispatches."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    fake_win32 = MagicMock()
    fake_win32.send_hotkey.return_value = True
    app.computer_controller.win32 = fake_win32

    # Close Tab
    res_tab = app._handle_close_tab()
    assert res_tab["success"] is True
    fake_win32.send_hotkey.assert_called_with("ctrl", "w")

    # Scroll Down
    res_down = app._handle_page_scroll(direction="down")
    assert res_down["success"] is True
    fake_win32.send_hotkey.assert_called_with("pagedown")

    # Scroll Up
    res_up = app._handle_page_scroll(direction="up")
    assert res_up["success"] is True
    fake_win32.send_hotkey.assert_called_with("pageup")

    # Refresh
    res_f5 = app._handle_page_refresh()
    assert res_f5["success"] is True
    fake_win32.send_hotkey.assert_called_with("f5")

    app.stop()
