"""
tests/test_adversarial_beta_m1_comms_failclosed.py
==================================================
Adversarial challenge test suite for Milestone M1:
Verifies fail-closed semantics across Zalo OA, Comms adapters (Telegram, Discord, IMAP),
and Hardware controllers (Volume, Brightness).
"""
import pytest
from unittest.mock import MagicMock

from jarvis.comms.zalo import ZaloBotController, ZaloConfig, ZaloSendResult
from jarvis.comms.telegram import TelegramBotController
from jarvis.comms.discord import DiscordBotController
from jarvis.comms.email_imap import IMAPEmailReader, IMAPNotConfiguredError
from jarvis.core.app import JarvisApp


class TestZaloSendImageFailClosed:
    """Adversarial challenge on ZaloBotController.send_image() fail-closed semantics."""

    def test_zalo_send_image_missing_token(self):
        """Unconfigured token must return success=False and error='NOT_CONFIGURED'."""
        bot = ZaloBotController(config=ZaloConfig(), is_mock=False)
        result = bot.send_image(user_id="user_123", image_path="test.png", caption="Test")
        assert isinstance(result, ZaloSendResult)
        assert result.success is False, f"Expected success=False on unconfigured token, got: {result}"
        assert result.error == "NOT_CONFIGURED", f"Expected error='NOT_CONFIGURED', got: {result.error}"

    def test_zalo_send_image_empty_token(self):
        """Empty string token must return success=False and error='NOT_CONFIGURED'."""
        bot = ZaloBotController(config=ZaloConfig(access_token=""), is_mock=False)
        result = bot.send_image(user_id="user_123", image_path="test.png", caption="Test")
        assert isinstance(result, ZaloSendResult)
        assert result.success is False, f"Expected success=False on empty token, got: {result}"
        assert result.error == "NOT_CONFIGURED", f"Expected error='NOT_CONFIGURED', got: {result.error}"

    def test_zalo_send_image_whitespace_token(self):
        """Whitespace token '   ' must return success=False and error='NOT_CONFIGURED'."""
        bot = ZaloBotController(config=ZaloConfig(access_token="   "), is_mock=False)
        result = bot.send_image(user_id="user_123", image_path="test.png", caption="Test")
        assert isinstance(result, ZaloSendResult)
        assert result.success is False, f"FABRICATION/GHOST SUCCESS: send_image returned success=True on whitespace token! result={result}"
        assert result.error == "NOT_CONFIGURED", f"Expected error='NOT_CONFIGURED', got: {result.error}"

    def test_zalo_send_image_tab_newline_whitespace(self):
        """Whitespace token '\\t\\n  ' must return success=False and error='NOT_CONFIGURED'."""
        bot = ZaloBotController(config=ZaloConfig(access_token="\t\n  "), is_mock=False)
        result = bot.send_image(user_id="user_123", image_path="test.png", caption="Test")
        assert isinstance(result, ZaloSendResult)
        assert result.success is False, f"FABRICATION/GHOST SUCCESS: send_image returned success=True on tab/newline token! result={result}"
        assert result.error == "NOT_CONFIGURED", f"Expected error='NOT_CONFIGURED', got: {result.error}"

    def test_zalo_send_image_mock_mode(self):
        """is_mock=True must return success=True and valid mock message_id."""
        bot = ZaloBotController(config=ZaloConfig(), is_mock=True)
        result = bot.send_image(user_id="user_123", image_path="test.png", caption="Test")
        assert isinstance(result, ZaloSendResult)
        assert result.success is True
        assert result.message_id == "mock_img_id"

    def test_zalo_send_image_configured_token_not_implemented(self):
        """Configured token under is_mock=False must return success=False and error='IMAGE_SEND_NOT_IMPLEMENTED' (no ghost success)."""
        bot = ZaloBotController(config=ZaloConfig(access_token="configured_token_123"), is_mock=False)
        result = bot.send_image(user_id="user_123", image_path="test.png", caption="Test")
        assert isinstance(result, ZaloSendResult)
        assert result.success is False, (
            f"FABRICATION/GHOST SUCCESS: send_image returned success=True on configured token! result={result}"
        )
        assert result.error == "IMAGE_SEND_NOT_IMPLEMENTED", (
            f"Expected error='IMAGE_SEND_NOT_IMPLEMENTED', got: {result.error}"
        )


class TestCommsAdaptersFailClosed:
    """Check Telegram, Discord, and IMAP fail-closed behavior when credentials are missing."""

    def test_telegram_send_message_unconfigured(self):
        bot = TelegramBotController()
        res = bot.send_message(chat_id=12345, text="Hello")
        assert res.get("ok") is False
        assert res.get("error_code") == "NOT_CONFIGURED"

    def test_telegram_send_photo_unconfigured(self):
        bot = TelegramBotController()
        res = bot.send_photo(chat_id=12345, photo_bytes=b"fake_bytes")
        assert res.get("ok") is False
        assert res.get("error_code") == "NOT_CONFIGURED"

    def test_discord_send_message_unconfigured(self):
        bot = DiscordBotController()
        res = bot.send_message(channel_id=12345, content="Hello")
        assert res.get("success") is False
        assert res.get("error_code") == "NOT_CONFIGURED"

    def test_discord_send_file_unconfigured(self):
        bot = DiscordBotController()
        res = bot.send_file(channel_id=12345, file_bytes=b"data", filename="test.txt")
        assert res.get("success") is False
        assert res.get("error_code") == "NOT_CONFIGURED"

    def test_discord_send_embed_unconfigured(self):
        bot = DiscordBotController()
        res = bot.send_embed(channel_id=12345, title="Alert", description="Test")
        assert res.get("success") is False
        assert res.get("error_code") == "NOT_CONFIGURED"

    def test_imap_connect_unconfigured(self):
        reader = IMAPEmailReader(host="", username="", password="")
        with pytest.raises(IMAPNotConfiguredError) as exc_info:
            reader.connect()
        assert "NOT_CONFIGURED" in str(exc_info.value)

    def test_imap_fetch_and_summarize_unconfigured(self):
        reader = IMAPEmailReader(host="", username="", password="")
        with pytest.raises(IMAPNotConfiguredError) as exc_info:
            reader.fetch_and_summarize()
        assert "NOT_CONFIGURED" in str(exc_info.value)


class TestHardwareFailClosed:
    """Verify hardware fail-closed: _handle_system_volume and _handle_system_brightness."""

    def test_volume_set_controller_returns_none(self):
        """
        H-08 review correction: "error" holds the clear Vietnamese
        human-readable message (what reaches the user via
        process_text_command()'s failure-text precedence), "error_code"
        holds the short machine constant -- not the reverse.
        """
        app = JarvisApp.__new__(JarvisApp)
        app.computer_controller = MagicMock()
        app.computer_controller.set_volume.return_value = None

        res = app._handle_system_volume(level=80)
        assert res["status"] == "failed"
        assert res["success"] is False
        assert res["error_code"] == "VOLUME_SET_FAILED"
        assert "Không thể" in res["error"]

    def test_volume_change_controller_returns_none(self):
        app = JarvisApp.__new__(JarvisApp)
        app.computer_controller = MagicMock()
        app.computer_controller.change_volume.return_value = None

        res = app._handle_system_volume(delta=10)
        assert res["status"] == "failed"
        assert res["success"] is False
        assert res["error_code"] == "VOLUME_CHANGE_FAILED"
        assert "Không thể" in res["error"]

    def test_brightness_set_controller_returns_none(self):
        app = JarvisApp.__new__(JarvisApp)
        app.computer_controller = MagicMock()
        app.computer_controller.set_brightness.return_value = None

        res = app._handle_system_brightness(level=70)
        assert res["status"] == "failed"
        assert res["success"] is False
        assert res["error"] == "BRIGHTNESS_SET_FAILED"

    def test_brightness_change_controller_returns_none(self):
        app = JarvisApp.__new__(JarvisApp)
        app.computer_controller = MagicMock()
        app.computer_controller.change_brightness.return_value = None

        res = app._handle_system_brightness(delta=-10)
        assert res["status"] == "failed"
        assert res["success"] is False
        assert res["error"] == "BRIGHTNESS_CHANGE_FAILED"

    def test_volume_and_brightness_controller_none(self):
        app = JarvisApp.__new__(JarvisApp)
        app.computer_controller = None

        res_vol = app._handle_system_volume(level=80)
        assert res_vol["status"] == "failed"
        assert res_vol["success"] is False

        res_bri = app._handle_system_brightness(level=70)
        assert res_bri["status"] == "failed"
        assert res_bri["success"] is False
