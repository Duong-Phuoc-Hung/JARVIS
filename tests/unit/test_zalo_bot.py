"""
tests/unit/test_zalo_bot.py
==============================
Unit tests for ZaloBotController (mock mode).
"""
from __future__ import annotations

import pytest

from jarvis.comms.zalo import ZaloBotController, ZaloConfig, ZaloMessage, ZaloSendResult


@pytest.fixture
def bot():
    cfg = ZaloConfig(whitelist_user_ids=["u1", "user_001", "user_002"], webhook_secret="test_secret_123")
    return ZaloBotController(config=cfg, is_mock=True)


@pytest.fixture
def bot_unconfigured():
    return ZaloBotController(config=ZaloConfig(), is_mock=False)


@pytest.fixture
def bot_whitelist():
    cfg = ZaloConfig(whitelist_user_ids=["user_001", "user_002"])
    return ZaloBotController(config=cfg, is_mock=True)


class TestAuthorization:
    def test_unconfigured_whitelist_blocks_all(self, bot_unconfigured):
        """Verify Fail-Close: If whitelist is not configured, all access is denied."""
        assert bot_unconfigured.is_user_authorized("anyone") is False
        assert bot_unconfigured.is_user_authorized("") is False

    def test_whitelist_allows_member(self, bot_whitelist):
        assert bot_whitelist.is_user_authorized("user_001") is True

    def test_whitelist_blocks_stranger(self, bot_whitelist):
        assert bot_whitelist.is_user_authorized("stranger_xyz") is False

    def test_mock_webhook_signature_always_valid(self, bot):
        assert bot.verify_webhook_signature(b"payload", "signature") is True

    def test_real_webhook_signature_fails_when_secret_empty(self, bot_unconfigured):
        """Verify Fail-Close: Missing secret rejects all webhooks."""
        assert bot_unconfigured.verify_webhook_signature(b"payload", "sig") is False

    def test_real_webhook_signature_validates_correctly(self):
        import hashlib, hmac
        secret = "super_secret_key"
        cfg = ZaloConfig(webhook_secret=secret, whitelist_user_ids=["u1"])
        controller = ZaloBotController(config=cfg, is_mock=False)
        payload = b'{"event":"test"}'
        valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        assert controller.verify_webhook_signature(payload, valid_sig) is True
        assert controller.verify_webhook_signature(payload, "invalid_signature_hex") is False


class TestCommandDispatch:
    def test_help_command(self, bot):
        result = bot.handle_message("u1", "Tester", "/help")
        assert result["status"] == 200
        assert "lệnh" in result["text"].lower() or "help" in result["text"].lower()

    def test_status_command(self, bot):
        result = bot.handle_message("u1", "Tester", "/status")
        assert result["status"] == 200
        assert "JARVIS" in result["text"]

    def test_note_command(self, bot):
        result = bot.handle_message("u1", "Tester", "/note nhớ họp lúc 3h")
        assert result["status"] == 200
        assert result["text"] != ""

    def test_unauthorized_user_blocked(self, bot_whitelist):
        result = bot_whitelist.handle_message("stranger", "Unknown", "/status")
        assert result["status"] == 403
        assert len(bot_whitelist.security_violations) == 1

    def test_natural_language_handled(self, bot):
        result = bot.handle_message("u1", "Tester", "JARVIS ơi làm ơn")
        assert result["status"] == 200


class TestSendMessage:
    def test_mock_send_returns_success(self, bot):
        result = bot.send_message("user_001", "Xin chào!")
        assert isinstance(result, ZaloSendResult)
        assert result.success is True
        assert result.message_id == "mock_msg_id"

    def test_sent_messages_logged(self, bot):
        bot.send_message("user_001", "Test 1")
        bot.send_message("user_001", "Test 2")
        assert len(bot.sent_messages) == 2

    def test_mock_send_image_returns_success(self, bot):
        result = bot.send_image("user_001", "path/to/img.png", caption="Test caption")
        assert isinstance(result, ZaloSendResult)
        assert result.success is True
        assert result.message_id == "mock_img_id"
        assert len(bot.sent_messages) == 1
        assert bot.sent_messages[0]["image"] == "path/to/img.png"

    def test_broadcast_sends_to_all(self, bot_whitelist):
        results = bot_whitelist.broadcast("Thông báo chung")
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_broadcast_no_users_returns_empty(self, bot_unconfigured):
        results = bot_unconfigured.broadcast("Test")
        assert results == []


class TestWebhook:
    def test_start_stop_mock_webhook(self, bot):
        bot.start_webhook()
        assert bot._running is True
        bot.stop_webhook()
        assert bot._running is False


class TestFailClosed:
    """P0-B: Verify Zalo fail-closed behavior when access_token is absent.

    Guards against fabrication: send_message MUST NOT return success=True
    without credentials (AGENTS.md Anti-Fabrication Principle).
    """

    def test_send_message_not_configured_when_token_empty(self, bot_unconfigured):
        """send_message() must return NOT_CONFIGURED error when access_token is empty."""
        result = bot_unconfigured.send_message("user_123", "Hello JARVIS")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION: send_message returned success=True without access_token"
        )
        assert "NOT_CONFIGURED" in result.error, (
            f"Expected 'NOT_CONFIGURED' in error, got: {result.error!r}"
        )

    def test_send_image_not_configured_when_token_empty(self, bot_unconfigured):
        """send_image() must return NOT_CONFIGURED error when access_token is empty."""
        result = bot_unconfigured.send_image("user_123", "path/to/image.jpg")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION: send_image returned success=True without access_token"
        )
        assert "NOT_CONFIGURED" in result.error, (
            f"Expected 'NOT_CONFIGURED' in error, got: {result.error!r}"
        )

    def test_send_message_no_fabricated_success_on_network_error(self):
        """send_message() must fail-closed on network error, never return success=True."""
        from unittest.mock import patch
        from urllib.error import URLError

        cfg = ZaloConfig(
            access_token="fake_token_for_test",
            whitelist_user_ids=["u1"],
        )
        bot = ZaloBotController(config=cfg, is_mock=False)

        with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
            result = bot.send_message("u1", "Test message")

        assert result.success is False, (
            "FABRICATION: send_message returned success=True despite network URLError"
        )

    def test_broadcast_empty_when_no_whitelist(self, bot_unconfigured):
        """broadcast() with empty whitelist must return [], not fabricate sends."""
        results = bot_unconfigured.broadcast("Test broadcast")
        assert results == [], (
            f"Expected empty list when no users configured, got: {results}"
        )

    def test_send_message_not_configured_when_token_whitespace(self):
        """send_message() must return NOT_CONFIGURED error when access_token is whitespace."""
        bot = ZaloBotController(config=ZaloConfig(access_token="   \t\n  "), is_mock=False)
        result = bot.send_message("user_123", "Hello JARVIS")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION: send_message returned success=True on whitespace token"
        )
        assert result.error == "NOT_CONFIGURED", (
            f"Expected error='NOT_CONFIGURED', got: {result.error!r}"
        )

    def test_send_image_not_configured_when_token_whitespace(self):
        """send_image() must return NOT_CONFIGURED error when access_token is whitespace."""
        bot = ZaloBotController(config=ZaloConfig(access_token="   \t\n  "), is_mock=False)
        result = bot.send_image("user_123", "path/to/image.jpg")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION: send_image returned success=True on whitespace token"
        )
        assert result.error == "NOT_CONFIGURED", (
            f"Expected error='NOT_CONFIGURED', got: {result.error!r}"
        )

    def test_send_image_not_implemented_when_token_provided(self):
        """send_image() must fail-closed with IMAGE_SEND_NOT_IMPLEMENTED when token is configured (no ghost success)."""
        bot = ZaloBotController(config=ZaloConfig(access_token="valid_test_token_123"), is_mock=False)
        result = bot.send_image("user_123", "path/to/image.jpg", caption="Test image")
        assert isinstance(result, ZaloSendResult), "Expected ZaloSendResult dataclass"
        assert result.success is False, (
            "FABRICATION/GHOST SUCCESS: send_image returned success=True without upload implementation"
        )
        assert result.error == "IMAGE_SEND_NOT_IMPLEMENTED", (
            f"Expected error='IMAGE_SEND_NOT_IMPLEMENTED', got: {result.error!r}"
        )

    def test_webhook_secret_whitespace_fails_closed(self):
        """verify_webhook_signature must fail-closed when webhook_secret is only whitespace."""
        bot = ZaloBotController(config=ZaloConfig(webhook_secret="   \t\n "), is_mock=False)
        assert bot.verify_webhook_signature(b"payload", "any_signature") is False

