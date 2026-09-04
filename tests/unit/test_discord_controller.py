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
        bot_token="mock_token",
        whitelist_user_ids=[1, 12345, 99999],
    )


@pytest.fixture
def bot_unconfigured():
    return DiscordBotController(
        bot_token="",
        whitelist_user_ids=[],
    )


@pytest.fixture
def bot_whitelist():
    return DiscordBotController(
        bot_token="",
        whitelist_user_ids=[12345, 99999],
    )


class TestAuthorization:
    def test_empty_whitelist_blocks_all(self, bot_unconfigured):
        """Verify Fail-Close: If whitelist is not configured, all access is denied."""
        assert bot_unconfigured.is_user_authorized(111) is False
        assert bot_unconfigured.is_user_authorized(999999) is False
        assert bot_unconfigured.is_user_authorized(0) is False

    def test_whitelist_allows_only_listed_users(self, bot_whitelist):
        assert bot_whitelist.is_user_authorized(12345) is True
        assert bot_whitelist.is_user_authorized(99999) is True
        assert bot_whitelist.is_user_authorized(77777) is False

    def test_unauthorized_message_returns_403_and_redacts_log(self, bot_whitelist):
        result = bot_whitelist.handle_message(77777, "stranger", "!status secret_password_123", 0)
        assert result["status"] == 403
        assert "không có quyền" in result["text"].lower() or "⛔" in result["text"]
        assert len(bot_whitelist.security_violations) == 1
        violation = bot_whitelist.security_violations[0]
        assert violation["user_id"] == 77777
        assert "payload_sha256_prefix" in violation
        assert "secret_password_123" not in str(violation)


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


class TestDiscordSlashCommandsAndRichEmbeds:
    """
    R6 Functional Test Suite for Discord Slash Commands and Rich Embed Generators.
    """

    def test_slash_command_status_rich_embed(self, bot):
        """
        Test 1: Validate /status slash command generates 200 OK and Rich Embed
        with JARVIS status details and proper color coding (0x00FF88).
        """
        response = bot.handle_message(
            user_id=1,
            username="test_admin",
            content="/status",
            channel_id=1001,
        )
        assert response["status"] == 200
        assert "text" in response
        assert "embed" in response
        embed = response["embed"]
        assert isinstance(embed, dict)
        assert embed["title"] == "🟢 JARVIS System Status"
        assert embed["color"] == 0x00FF88
        assert "JARVIS Online" in embed["description"]

    def test_slash_command_help_rich_embed_fields(self, bot):
        """
        Test 2: Validate /help slash command returns structured Rich Embed
        containing command reference fields with inline flags.
        """
        response = bot.handle_message(
            user_id=1,
            username="test_admin",
            content="/help",
            channel_id=1001,
        )
        assert response["status"] == 200
        embed = response["embed"]
        assert embed is not None
        assert embed["title"] == "🤖 JARVIS Discord Controller"
        assert len(embed["fields"]) >= 6

        # Verify key command fields exist
        field_names = [f["name"] for f in embed["fields"]]
        assert any("status" in name for name in field_names)
        assert any("skills" in name for name in field_names)
        assert any("calc" in name for name in field_names)
        assert all("value" in f and "inline" in f for f in embed["fields"])

    def test_slash_command_calc_execution(self, bot):
        """
        Test 3: Validate /calc slash command evaluates arithmetic expressions
        and returns formatted response.
        """
        response = bot.handle_message(
            user_id=1,
            username="test_admin",
            content="/calc 25 * 4 + 50",
            channel_id=1001,
        )
        assert response["status"] == 200
        assert "150" in response["text"] or "🔢" in response["text"]

    def test_slash_command_skills_listing(self, bot):
        """
        Test 4: Validate /skills slash command lists available skill modules.
        """
        response = bot.handle_message(
            user_id=1,
            username="test_admin",
            content="/skills",
            channel_id=1001,
        )
        assert response["status"] == 200
        assert "🧰" in response["text"] or "kỹ năng" in response["text"].lower() or "skills" in response["text"].lower()

    def test_slash_command_briefing_and_note(self, bot):
        """
        Test 5: Validate /briefing and /note slash commands.
        """
        res_brief = bot.handle_message(1, "user", "/briefing", 1001)
        assert res_brief["status"] == 200
        assert "📰" in res_brief["text"] or "briefing" in res_brief["text"].lower()

        res_note = bot.handle_message(1, "user", "/note Họp nhóm lúc 3h chiều", 1001)
        assert res_note["status"] == 200
        assert "Họp nhóm lúc 3h chiều" in res_note["text"]

    def test_send_embed_custom_dispatch(self, bot):
        """
        Test 6: Validate programmatic send_embed method records structured embed
        and sends to designated Discord channel.
        """
        channel_id = 999888
        title = "🚀 System Alert"
        description = "High CPU load detected on Worker Pool"
        fields = [
            {"name": "CPU Usage", "value": "98.5%", "inline": True},
            {"name": "Action", "value": "Throttling background tasks", "inline": True},
        ]

        result = bot.send_embed(
            channel_id=channel_id,
            title=title,
            description=description,
            fields=fields,
        )
        # A3 fix (2026-09-04): send_embed is fail-closed — success=False when no bot_token.
        # The record is still appended to sent_messages (local queue) for auditability.
        assert result["success"] is False
        assert result.get("error_code") == "NOT_CONFIGURED"
        assert len(bot.sent_messages) > 0
        last_msg = bot.sent_messages[-1]
        assert last_msg["channel_id"] == channel_id
        assert title in last_msg["content"]
        assert "embed" in last_msg
        assert last_msg["embed"]["title"] == title
        assert last_msg["embed"]["fields"] == fields


    def test_rate_limiter_throttles_excess_requests(self):
        """
        Test 7: Validate RateLimiter integration blocks excessive requests with HTTP 429.
        """
        mock_limiter = MagicMock()
        mock_limiter.acquire.side_effect = [(True, 0.0), (True, 0.0), (False, 2.5)]

        bot = DiscordBotController(
            bot_token="mock_token",
            whitelist_user_ids=[1],
            rate_limiter=mock_limiter,
        )

        res1 = bot.handle_message(1, "user", "/status", 100)
        assert res1["status"] == 200

        res2 = bot.handle_message(1, "user", "/help", 100)
        assert res2["status"] == 200

        res3 = bot.handle_message(1, "user", "/calc 1+1", 100)
        assert res3["status"] == 429
        assert "429" in str(res3["status"]) or "quá nhiều yêu cầu" in res3["text"].lower() or "⏳" in res3["text"]
        assert res3.get("retry_after") == 2.5

