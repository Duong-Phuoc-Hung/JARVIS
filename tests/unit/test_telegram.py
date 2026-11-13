"""
tests/unit/test_telegram.py
===========================
Unit tests for jarvis.comms.telegram TelegramBotController.
Verifies fail-closed semantics, STT voice handling, rate limiting, and authorization.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from jarvis.comms.telegram import TelegramBotController, TelegramConfig


def test_telegram_send_message_missing_token():
    tg = TelegramBotController(bot_token="")
    res = tg.send_message(12345, "Hello")
    assert not res.get("ok")
    assert res.get("error_code") == "NOT_CONFIGURED"


def test_telegram_send_photo_missing_token():
    tg = TelegramBotController(bot_token="")
    res = tg.send_photo(12345, b"photo", "caption")
    assert not res.get("ok")
    assert res.get("error_code") == "NOT_CONFIGURED"


def test_telegram_poll_missing_token():
    tg = TelegramBotController(bot_token="")
    res = tg.poll_once()
    assert res == []


def test_telegram_unauthorized_user():
    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111})
    res = tg.handle_inbound_message(999, "Hello", 999)
    assert res.get("status") == 403
    assert res.get("rejected") is True


def test_telegram_authorized_user():
    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111})
    res = tg.handle_inbound_message(111, "/help", 111)
    assert res.get("status") == 200
    assert "JARVIS Telegram Commands" in res.get("text", "")

def test_telegram_mock_http_backward_compatibility():
    class MockHttp:
        def handle_telegram_send_message(self, chat_id, text):
            return {"ok": True, "result": "mock"}

    tg = TelegramBotController(bot_token="fake")
    res = tg.send_message(12345, "Hello", mock_http=MockHttp())
    assert res.get("ok")
    assert res.get("result") == "mock"


# ============================================================================
# Fail-Closed STT & Voice Handling Tests (Milestone 1 Remediation)
# ============================================================================

def test_telegram_voice_unauthorized_user():
    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111})
    res = tg.handle_inbound_voice(user_id=999, voice_bytes=b"audio_bytes")
    assert res.get("status") == 403
    assert res.get("rejected") is True
    assert 999 in tg.security_violations


def test_telegram_voice_stt_none_fail_closed():
    """When stt_engine is None, handle_inbound_voice must fail-closed with STT_UNAVAILABLE."""
    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111}, stt_engine=None)
    res = tg.handle_inbound_voice(user_id=111, voice_bytes=b"audio_bytes")
    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"
    assert "offline or not configured" in res.get("message", "")


def test_telegram_voice_stt_missing_transcribe_method_fail_closed():
    """When stt_engine does not have transcribe method, fail-closed with STT_UNAVAILABLE."""
    class DummyEngine:
        pass

    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111}, stt_engine=DummyEngine())
    res = tg.handle_inbound_voice(user_id=111, voice_bytes=b"audio_bytes")
    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_telegram_voice_stt_exception_fail_closed():
    """When stt_engine.transcribe raises an exception, must fail-closed with STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.side_effect = RuntimeError("Whisper CUDA OOM or network error")

    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=111, voice_bytes=b"audio_bytes")
    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"
    assert "offline or not configured" in res.get("message", "")


def test_telegram_voice_stt_empty_result_fail_closed():
    """When stt_engine.transcribe returns empty string, must fail-closed with STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = ""

    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=111, voice_bytes=b"audio_bytes")
    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_telegram_voice_stt_success_routes_to_message():
    """When stt_engine.transcribe succeeds, transcribed text is routed to handle_inbound_message."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "/help"

    tg = TelegramBotController(bot_token="fake", allowed_user_ids={111}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=111, voice_bytes=b"audio_bytes", chat_id=111)
    assert res.get("status") == 200
    assert "JARVIS Telegram Commands" in res.get("text", "")


def test_telegram_send_voice_fail_closed_and_mock():
    # 1. Unconfigured bot token -> fail-closed NOT_CONFIGURED
    bot_unconfigured = TelegramBotController(bot_token="")
    res_unconfigured = bot_unconfigured.send_voice(12345, b"OGG_HEADER_DATA")
    assert res_unconfigured["ok"] is False
    assert res_unconfigured["error_code"] == "NOT_CONFIGURED"

    # 2. Configured bot with mock HTTP handler
    mock_http = MagicMock()
    mock_http.handle_telegram_send_voice.return_value = {"ok": True, "result": {"message_id": 999}}
    bot = TelegramBotController(bot_token="test_token_123")
    res_mock = bot.send_voice(12345, b"OGG_VOICE_SAMPLE", caption="Hello voice note", mock_http=mock_http)
    assert res_mock["ok"] is True
    assert res_mock["result"]["message_id"] == 999
    mock_http.handle_telegram_send_voice.assert_called_once_with(12345, b"OGG_VOICE_SAMPLE", "Hello voice note")
