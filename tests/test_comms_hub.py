"""
tests/test_comms_hub.py
=======================
Test Suite for Multi-Channel Communications: Telegram, IMAP Email, and Discord.
Covering:
  - F-38: Telegram Bot Remote Controller (Whitelist user ID security, /status, /lock, /exec)
  - F-39: IMAP Priority Email Reader & LLM Summarizer (Unread email filter, HTML strip, voice formatting)
  - F-40: Discord Bot Integration (Channel reader & activity summary)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import pytest

from jarvis.comms.discord import DiscordBotClient, DiscordBotIntegration
from jarvis.comms.email_imap import EmailMessage, IMAPEmailReader
from jarvis.comms.telegram import TelegramBotController

# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

def test_comms_telegram_authorized_user_command_tier1(mock_win32_platform):
    """
    [F-38] Validate Telegram bot processes commands from whitelisted User ID and executes actions.
    """
    bot = TelegramBotController(allowed_user_ids={12345}, win32_platform=mock_win32_platform)

    # 1. /status command
    status_reply = bot.handle_inbound_message(user_id=12345, text="/status")
    assert status_reply["status"] == 200
    assert "Hệ thống hoạt động bình thường" in status_reply["text"]

    # 2. /lock command
    lock_reply = bot.handle_inbound_message(user_id=12345, text="/lock")
    assert lock_reply["status"] == 200
    assert mock_win32_platform.lock_workstation_calls == 1


def test_comms_telegram_photo_dispatch_tier1(mock_http_server):
    """
    [F-38] Validate Telegram bot photo dispatch sending snapshots.
    """
    bot = TelegramBotController(allowed_user_ids={12345}, http_client=mock_http_server)
    res = bot.send_photo(chat_id=12345, photo_bytes=b"intruder_jpeg", caption="Cảnh báo", mock_http=mock_http_server)
    assert res["ok"] is True
    assert len(mock_http_server.telegram_sent_photos) == 1


def test_comms_imap_email_fetch_and_llm_summary_tier1():
    """
    [F-39] Validate IMAP reader fetches unread high-priority emails and formats concise voice summary.
    """
    reader = IMAPEmailReader(priority_senders=["boss@corp.com", "security@cloud.io"])
    emails = [
        EmailMessage(sender="boss@corp.com", subject="Q3 Review", body_text="Cuộc họp dời sang 3h chiều."),
        EmailMessage(sender="marketing@spam.com", subject="Discount 50%", body_text="Buy now!"),
    ]

    res = reader.fetch_and_summarize(emails)
    assert res["priority_count"] == 1
    assert "boss@corp.com" in res["voice_summary"]
    assert "Q3 Review" in res["voice_summary"]


def test_comms_discord_bot_channel_reader_tier1():
    """
    [F-40] Validate Discord bot channel monitoring and activity summarization.
    """
    bot = DiscordBotIntegration()
    summary = bot.summarize_channel("dev-chat", ["Fix commit ready", "Tests all passing"])
    assert "dev-chat" in summary
    assert "2 tin nhắn mới" in summary


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_comms_telegram_unauthorized_user_whitelist_rejection_tier2():
    """
    [F-38] Validate that non-whitelisted Telegram User IDs are rejected with 403 Forbidden.
    """
    bot = TelegramBotController(allowed_user_ids={12345})
    unauth_reply = bot.handle_inbound_message(user_id=999999, text="/status")

    assert unauth_reply["status"] == 403
    assert unauth_reply["rejected"] is True
    assert 999999 in bot.security_violations
