"""
tests/unit/test_phase8_defect_remediations.py
=============================================
TDD Unit test suite for Phase 8: Remediation of 8 High-Priority Audit Defects (D1-D8).
Verifies strict Fail-Closed, Anti-Fabrication, and Ghost-Process elimination per AGENTS.md.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from jarvis.automation.control import ComputerController
from jarvis.audio.engine import AudioEngine
from jarvis.browser.driver import CDPBrowserDriver, BrowserConfig
from jarvis.comms.discord import DiscordBotController
from jarvis.comms.telegram import TelegramBotController
from jarvis.comms.zalo import ZaloBotController, ZaloConfig
from jarvis.security.scanner import PacketCapture


# ==============================================================================
# 1. D1: Zalo send_message Fail-Closed on Missing Token
# ==============================================================================
class TestZaloFailClosedRemediation:
    def test_zalo_send_message_fails_closed_when_token_empty(self):
        config = ZaloConfig(access_token="", oa_id="test_oa")
        bot = ZaloBotController(config=config, is_mock=False)

        res = bot.send_message(user_id="user_123", text="Xin chào")
        assert res.success is False
        assert res.error == "NOT_CONFIGURED"
        assert res.message_id == ""

    def test_zalo_send_message_explicit_mock_mode_succeeds(self):
        config = ZaloConfig(access_token="", oa_id="test_oa")
        bot = ZaloBotController(config=config, is_mock=True)

        res = bot.send_message(user_id="user_123", text="Xin chào")
        assert res.success is True
        assert res.message_id == "mock_msg_id"


# ==============================================================================
# 2. D2: Zalo Anti-Fabrication in Weather & Status
# ==============================================================================
class TestZaloAntiFabricationRemediation:
    def test_zalo_cmd_weather_does_not_fabricate_temperatures(self):
        config = ZaloConfig(access_token="", oa_id="test_oa")
        bot = ZaloBotController(config=config, is_mock=False)

        res = bot._cmd_weather()
        assert "32°C" not in res
        assert "34°C" not in res
        assert "chưa được cấu hình" in res or "chưa khả dụng" in res

    def test_zalo_cmd_status_reports_dynamic_metrics(self):
        config = ZaloConfig(access_token="", oa_id="test_oa")
        bot = ZaloBotController(config=config, is_mock=False)

        res = bot._cmd_status()
        assert "Memory: OK | TTS: OK" not in res
        assert "JARVIS Online" in res
        assert "Zalo Bot: Active" in res or "Zalo Bot: Connected" in res


# ==============================================================================
# 3. D3: Discord _poll_loop Ghost Process Elimination
# ==============================================================================
class TestDiscordGhostProcessElimination:
    def test_discord_start_polling_does_not_spawn_infinite_sleep_thread(self):
        bot = DiscordBotController(bot_token="valid_test_token_123")
        bot.start_polling()

        # Must not spawn an active thread that just sleeps
        assert bot._poll_thread is None or not bot._poll_thread.is_alive()
        assert bot._running is False

    def test_discord_start_polling_without_token_skips(self):
        bot = DiscordBotController(bot_token="")
        bot.start_polling()
        assert bot._poll_thread is None
        assert bot._running is False


# ==============================================================================
# 4. D4: CDPBrowserDriver Interaction Stubs Fail-Closed
# ==============================================================================
class TestCDPBrowserDriverFailClosed:
    def test_cdp_interactions_return_false_when_session_inactive(self):
        from jarvis.browser.models import BrowserDriverType
        cfg = BrowserConfig(driver_type=BrowserDriverType.CDP)
        driver = CDPBrowserDriver(config=cfg)
        driver._is_running = True  # Simulated running flag

        # Even if _is_running is True, DOM actions must return False without active CDP session
        assert driver.click("#submit-btn") is False
        assert driver.type_text("#input-box", "hello") is False
        assert driver.select_option("#dropdown", "opt1") is False
        assert driver.wait_for_selector(".modal") is False


# ==============================================================================
# 5. D5: ComputerController set_volume Fail-Closed on Endpoint Failure
# ==============================================================================
class TestVolumeControlFailClosed:
    """Tests use sys.modules injection so pycaw does NOT need to be installed in CI."""

    @staticmethod
    def _inject_pycaw_mock(monkeypatch, get_speakers_return=None, get_speakers_side_effect=None):
        """Inject a mock pycaw.pycaw into sys.modules so control.py's lazy import resolves."""
        import sys
        mock_audio_utilities = MagicMock()
        if get_speakers_side_effect is not None:
            mock_audio_utilities.GetSpeakers.side_effect = get_speakers_side_effect
        else:
            mock_audio_utilities.GetSpeakers.return_value = get_speakers_return
        mock_pycaw_pycaw = MagicMock(AudioUtilities=mock_audio_utilities)
        mock_pycaw = MagicMock(pycaw=mock_pycaw_pycaw)
        monkeypatch.setitem(sys.modules, "pycaw", mock_pycaw)
        monkeypatch.setitem(sys.modules, "pycaw.pycaw", mock_pycaw_pycaw)
        return mock_audio_utilities

    def test_set_volume_fails_closed_when_speakers_missing(self, monkeypatch):
        """D5: set_volume() returns None when audio endpoint returns None (no speakers)."""
        ctrl = ComputerController()
        ctrl._current_volume = 40

        self._inject_pycaw_mock(monkeypatch, get_speakers_return=None)
        result = ctrl.set_volume(70)
        assert result is None
        # Current volume must not be falsely updated
        assert ctrl._current_volume == 40

    def test_set_volume_fails_closed_when_pycaw_raises_exception(self, monkeypatch):
        """D5: set_volume() returns None when audio endpoint raises (hardware error)."""
        ctrl = ComputerController()
        ctrl._current_volume = 40

        self._inject_pycaw_mock(monkeypatch,
                                get_speakers_side_effect=RuntimeError("Audio hardware disconnected"))
        result = ctrl.set_volume(80)
        assert result is None
        assert ctrl._current_volume == 40


# ==============================================================================
# 6. D6: Telegram Dispatcher Fail-Closed for /exec, /note, /healing
# ==============================================================================
class TestTelegramDispatcherFailClosed:
    def test_telegram_exec_fails_closed_when_no_dispatcher(self):
        bot = TelegramBotController(allowed_user_ids={999}, dispatcher=None)
        res = bot.handle_inbound_message(user_id=999, text="/exec notepad.exe")

        assert res["status"] == 503
        assert "chưa được cấu hình" in res["text"]
        assert "Đã thực thi lệnh" not in res["text"]

    def test_telegram_note_fails_closed_when_no_dispatcher(self):
        bot = TelegramBotController(allowed_user_ids={999}, dispatcher=None)
        res = bot.handle_inbound_message(user_id=999, text="/note mua sữa")

        assert res["status"] == 503
        assert "chưa được cấu hình" in res["text"]

    def test_telegram_healing_fails_closed_when_no_dispatcher(self):
        bot = TelegramBotController(allowed_user_ids={999}, dispatcher=None)
        res = bot.handle_inbound_message(user_id=999, text="/healing")

        assert res["status"] == 503
        assert "chưa được cấu hình" in res["text"]


# ==============================================================================
# 7. D7: PacketCapture Fallback Count Bug
# ==============================================================================
class TestPacketCaptureCountTruthfulness:
    def test_packet_capture_returns_zero_count_on_unparseable_output(self):
        capture = PacketCapture()
        unparseable_output = "tshark: The capture session could not be initiated on interface 'eth0'\n"

        res = capture._build_capture_result(
            interface="eth0",
            count=100,
            duration=5.0,
            raw_stdout=unparseable_output,
        )

        assert res.status == "NO_PROTOCOLS_PARSED"
        assert res.protocols == {}
        # Must be 0, NOT 100
        assert res.packet_count == 0


# ==============================================================================
# 8. D8: AudioEngine Device Fabrication Elimination
# ==============================================================================
class TestAudioEngineDeviceAntiFabrication:
    def test_probe_devices_returns_empty_when_sounddevice_unavailable(self, monkeypatch):
        import jarvis.audio.engine as eng_mod
        monkeypatch.setattr(eng_mod, "SOUNDDEVICE_AVAILABLE", False)

        engine = AudioEngine()
        devices = engine.probe_devices()

        assert devices == []
        assert not any("Headless Mock Audio Device" in d.name for d in devices)
