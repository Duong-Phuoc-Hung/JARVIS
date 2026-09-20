import pytest
from typing import Any
from unittest.mock import MagicMock

from jarvis.comms.telegram import TelegramBotController

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
    res = tg.handle_inbound_message(111, "Hello", 111)
    assert res.get("status") == 200

def test_telegram_mock_http_backward_compatibility():
    class MockHttp:
        def handle_telegram_send_message(self, chat_id, text):
            return {"ok": True, "result": "mock"}
            
    tg = TelegramBotController(bot_token="fake")
    res = tg.send_message(12345, "Hello", mock_http=MockHttp())
    assert res.get("ok")
    assert res.get("result") == "mock"
