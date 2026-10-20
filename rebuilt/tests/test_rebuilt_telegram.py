"""
tests/test_rebuilt_telegram.py
==============================
Behavioral tests for rebuilt/telegram_controller.py.
Verifies rules TG-01 through TG-09 (TTEST-01 to TTEST-09).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REBUILT_DIR = Path(__file__).resolve().parent.parent
if str(REBUILT_DIR) not in sys.path:
    sys.path.insert(0, str(REBUILT_DIR))

from telegram_controller import (
    RateLimitConfig,
    TelegramController,
)


def test_ttest_01_unauthorized_user_rejection():
    """TTEST-01: Unauthorized user receives 403 forbidden with rejected=True."""
    controller = TelegramController(allowed_user_ids={1001, 1002}, bot_token="valid_token")
    res = controller.handle_inbound_message(user_id=9999, text="/help")

    assert res.get("status") == 403
    assert res.get("rejected") is True
    assert 9999 in controller.security_violations


def test_ttest_02_authorized_user_help_command():
    """TTEST-02: Authorized user receives 200 and standard help text."""
    controller = TelegramController(allowed_user_ids={1001}, bot_token="valid_token")
    res = controller.handle_inbound_message(user_id=1001, text="/help")

    assert res.get("status") == 200
    assert "JARVIS Telegram Commands" in res.get("text", "")


def test_ttest_03_rate_limiting_exceeded():
    """TTEST-03: Exceeding token bucket rate limit triggers 429 too many requests."""
    config = RateLimitConfig(requests_per_minute=60, burst_limit=2)
    controller = TelegramController(
        allowed_user_ids={1001},
        bot_token="valid_token",
        rate_limit_config=config,
    )

    # First 2 requests within burst capacity
    res1 = controller.handle_inbound_message(user_id=1001, text="/help")
    res2 = controller.handle_inbound_message(user_id=1001, text="/help")
    assert res1.get("status") == 200
    assert res2.get("status") == 200

    # Third immediate request should exceed bucket
    res3 = controller.handle_inbound_message(user_id=1001, text="/help")
    assert res3.get("status") == 429
    assert res3.get("rejected") is True
    assert "retry_after_s" in res3


def test_ttest_04_voice_stt_none_fail_closed():
    """TTEST-04: When stt_engine is None, voice handling returns STT_UNAVAILABLE."""
    controller = TelegramController(
        allowed_user_ids={1001},
        bot_token="valid_token",
        stt_engine=None,
    )
    res = controller.handle_inbound_voice(user_id=1001, voice_bytes=b"sample_audio")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_ttest_05_voice_stt_exception_fail_closed():
    """TTEST-05: When stt_engine.transcribe throws, fail-closed with STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.side_effect = RuntimeError("Whisper model failure")

    controller = TelegramController(
        allowed_user_ids={1001},
        bot_token="valid_token",
        stt_engine=mock_stt,
    )
    res = controller.handle_inbound_voice(user_id=1001, voice_bytes=b"sample_audio")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_ttest_06_voice_stt_empty_transcription():
    """TTEST-06: Empty transcription returns EMPTY_TRANSCRIPTION."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "   "

    controller = TelegramController(
        allowed_user_ids={1001},
        bot_token="valid_token",
        stt_engine=mock_stt,
    )
    res = controller.handle_inbound_voice(user_id=1001, voice_bytes=b"sample_audio")

    assert res.get("ok") is False
    assert res.get("error_code") == "EMPTY_TRANSCRIPTION"


def test_ttest_07_voice_stt_success_routes_to_message():
    """TTEST-07: Successful voice transcription routes to command handler."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "/help"

    controller = TelegramController(
        allowed_user_ids={1001},
        bot_token="valid_token",
        stt_engine=mock_stt,
    )
    res = controller.handle_inbound_voice(user_id=1001, voice_bytes=b"sample_audio")

    assert res.get("status") == 200
    assert "JARVIS Telegram Commands" in res.get("text", "")


def test_ttest_08_status_anti_fabrication_on_psutil_error():
    """TTEST-08: /status with psutil error returns honest 'không xác định' (never fabricated OK)."""
    controller = TelegramController(allowed_user_ids={1001}, bot_token="valid_token")

    with patch.dict("sys.modules", {"psutil": None}):
        res = controller.handle_inbound_message(user_id=1001, text="/status")

    assert res.get("status") == 200
    status_text = res.get("text", "")
    assert "không xác định" in status_text
    assert "hoạt động bình thường" not in status_text


def test_ttest_09_send_message_missing_token_guard():
    """TTEST-09: send_message with empty token returns NOT_CONFIGURED without network call."""
    controller = TelegramController(allowed_user_ids={1001}, bot_token="")
    res = controller.send_message(chat_id=1001, text="Ping")

    assert res.get("ok") is False
    assert res.get("error_code") == "NOT_CONFIGURED"
