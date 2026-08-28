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
    return ZaloBotController(is_mock=True)


@pytest.fixture
def bot_whitelist():
    cfg = ZaloConfig(whitelist_user_ids=["user_001", "user_002"])
    return ZaloBotController(config=cfg, is_mock=True)


class TestAuthorization:
    def test_no_whitelist_allows_all(self, bot):
        assert bot.is_user_authorized("anyone") is True

    def test_whitelist_allows_member(self, bot_whitelist):
        assert bot_whitelist.is_user_authorized("user_001") is True

    def test_whitelist_blocks_stranger(self, bot_whitelist):
        assert bot_whitelist.is_user_authorized("stranger_xyz") is False

    def test_mock_webhook_signature_always_valid(self, bot):
        assert bot.verify_webhook_signature(b"payload", "signature") is True


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

    def test_broadcast_sends_to_all(self, bot_whitelist):
        results = bot_whitelist.broadcast("Thông báo chung")
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_broadcast_no_users_returns_empty(self, bot):
        results = bot.broadcast("Test")
        assert results == []


class TestWebhook:
    def test_start_stop_mock_webhook(self, bot):
        bot.start_webhook()
        assert bot._running is True
        bot.stop_webhook()
        assert bot._running is False
