"""
tests/unit/test_discord_controller.py
=======================================
Unit tests for the full Discord Bot Controller (2-way JARVIS control).
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from jarvis.comms.discord import DiscordBotController, DiscordConfig, DiscordEmbed


@pytest.fixture
def bot():
    return DiscordBotController(
        bot_token="",
        whitelist_user_ids=[],   # Empty = allow all
    )


@pytest.fixture
def bot_whitelist():
    return DiscordBotController(
        bot_token="",
        whitelist_user_ids=[12345, 99999],
    )


class TestAuthorization:
    def test_empty_whitelist_allows_all(self, bot):
        assert bot.is_user_authorized(111) is True
        assert bot.is_user_authorized(999999) is True

    def test_whitelist_allows_only_listed_users(self, bot_whitelist):
        assert bot_whitelist.is_user_authorized(12345) is True
        assert bot_whitelist.is_user_authorized(99999) is True
        assert bot_whitelist.is_user_authorized(77777) is False

    def test_unauthorized_message_returns_403(self, bot_whitelist):
        result = bot_whitelist.handle_message(77777, "stranger", "!status", 0)
        assert result["status"] == 403
        assert "không có quyền" in result["text"].lower() or "⛔" in result["text"]


class TestCommandDispatch:
    def test_help_command(self, bot):
        result = bot.handle_message(1, "user", "!help", 0)
        assert result["status"] == 200
        assert result["embed"] is not None

    def test_status_command(self, bot):
        result = bot.handle_message(1, "user", "!status", 0)
        assert result["status"] == 200
        assert "jarvis" in result["text"].lower() or "online" in result["text"].lower() or "✅" in result["text"]

    def test_note_command_empty_text(self, bot):
        result = bot.handle_message(1, "user", "!note", 0)
        assert result["status"] in (400, 200)

    def test_note_command_with_text(self, bot):
        result = bot.handle_message(1, "user", "!note ghi chú thử nghiệm", 0)
        assert result["status"] == 200

    def test_unknown_command_returns_200(self, bot):
        result = bot.handle_message(1, "user", "xin chào JARVIS", 0)
        assert result["status"] == 200

    def test_help_embed_has_fields(self, bot):
        result = bot.handle_message(1, "user", "!help", 0)
        embed = result.get("embed", {})
        assert isinstance(embed, dict)
        assert "fields" in embed
        assert len(embed["fields"]) > 0


class TestSendMessage:
    def test_send_message_records_to_sent_list(self, bot):
        initial = len(bot.sent_messages)
        bot.send_message(channel_id=123, content="test message")
        assert len(bot.sent_messages) == initial + 1

    def test_send_message_stores_channel_id(self, bot):
        bot.send_message(channel_id=456, content="hello")
        last = bot.sent_messages[-1]
        assert last["channel_id"] == 456
        assert last["content"] == "hello"


class TestDiscordEmbed:
    def test_embed_add_field(self):
        embed = DiscordEmbed(title="Test", description="desc")
        embed.add_field("Field 1", "Value 1")
        assert len(embed.fields) == 1
        assert embed.fields[0]["name"] == "Field 1"

    def test_embed_to_dict(self):
        embed = DiscordEmbed(title="JARVIS", description="Bot")
        d = embed.to_dict()
        assert d["title"] == "JARVIS"
        assert "fields" in d
        assert "color" in d
