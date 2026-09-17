"""
tests/unit/test_discord_controller.py
=======================================
Unit tests for the full Discord Bot Controller (2-way JARVIS control).
"""
from __future__ import annotations

import time
from typing import Any
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


class TestFailClosed:
    """P0-C: Verify Discord fail-closed behavior when bot_token is absent.

    send_message() MUST return NOT_CONFIGURED error_code, never success=True,
    when bot_token is empty (AGENTS.md Anti-Fabrication Principle, D-08).
    """

    def test_send_message_not_configured_when_token_empty(self, bot_unconfigured):
        """send_message() returns NOT_CONFIGURED when bot_token is empty string."""
        result = bot_unconfigured.send_message(99, "Hello from JARVIS")
        assert result["success"] is False, (
            "FABRICATION: send_message returned success=True without bot_token"
        )
        assert result.get("error_code") == "NOT_CONFIGURED", (
            f"Expected error_code='NOT_CONFIGURED', got: {result.get('error_code')!r}"
        )
        assert "NOT sent" in result.get("description", ""), (
            f"Expected explicit 'NOT sent' in description, got: {result.get('description')!r}"
        )

    def test_send_file_not_configured_when_token_empty(self, bot_unconfigured):
        """send_file() returns NOT_CONFIGURED when bot_token is empty string."""
        result = bot_unconfigured.send_file(99, b"data", "test.png", "caption")
        assert result["success"] is False, (
            "FABRICATION: send_file returned success=True without bot_token"
        )
        assert result.get("error_code") == "NOT_CONFIGURED", (
            f"Expected error_code='NOT_CONFIGURED', got: {result.get('error_code')!r}"
        )

    def test_send_message_logs_message_even_when_not_configured(self, bot_unconfigured):
        """send_message() must append to sent_messages log (audit trail) even when unconfigured."""
        initial_count = len(bot_unconfigured.sent_messages)
        bot_unconfigured.send_message(99, "Audit trail test")
        assert len(bot_unconfigured.sent_messages) == initial_count + 1, (
            "send_message must record to sent_messages audit log regardless of config"
        )


class TestDiscordInboundGateway:
    """
    R5 Functional Test Suite for Discord Inbound Polling Gateway.
    """

    def test_start_polling_empty_token_fail_closed(self):
        bot = DiscordBotController(bot_token="", channel_id=12345)
        bot.start_polling()
        assert bot._running is False
        assert bot._poll_thread is None

    def test_start_polling_missing_channel_fail_closed(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=None)
        bot.start_polling()
        assert bot._running is False
        assert bot._poll_thread is None

    def test_start_polling_spawns_thread_when_valid(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, poll_interval_s=0.05)
        with patch.object(bot, "poll_once", return_value=True):
            bot.start_polling()
            assert bot._running is True
            assert bot._poll_thread is not None
            assert bot._poll_thread.is_alive() is True
            bot.stop_polling()
            assert bot._running is False
            assert bot._poll_thread is None

    def test_poll_once_fetches_and_dispatches_message(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        dispatched: list[dict[str, Any]] = []
        bot.register_handler(lambda msg: dispatched.append(msg))

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": "5001",
                "author": {"id": "1001", "username": "alice", "bot": False},
                "content": "!status",
            }
        ]
        mock_http.get.return_value = mock_resp

        res = bot.poll_once(channel_id="12345", mock_http=mock_http)
        assert res is True
        assert len(dispatched) == 1
        assert dispatched[0]["id"] == "5001"
        assert dispatched[0]["content"] == "!status"
        assert bot._last_message_id == "5001"
        assert bot.consecutive_errors == 0

    def test_poll_once_filters_bot_messages(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        dispatched: list[dict[str, Any]] = []
        bot.register_handler(lambda msg: dispatched.append(msg))

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": "5002",
                "author": {"id": "9999", "username": "other_bot", "bot": True},
                "content": "automated announcement",
            }
        ]
        mock_http.get.return_value = mock_resp

        res = bot.poll_once(channel_id="12345", mock_http=mock_http)
        assert res is True
        assert len(dispatched) == 0
        assert bot._last_message_id == "5002"

    def test_poll_once_drops_unauthorized_user_and_records_violation(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        dispatched: list[dict[str, Any]] = []
        bot.register_handler(lambda msg: dispatched.append(msg))

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": "5003",
                "author": {"id": "8888", "username": "intruder", "bot": False},
                "content": "malicious payload",
            }
        ]
        mock_http.get.return_value = mock_resp

        res = bot.poll_once(channel_id="12345", mock_http=mock_http)
        assert res is True
        assert len(dispatched) == 0
        assert len(bot.security_violations) == 1
        violation = bot.security_violations[0]
        assert violation["user_id"] == 8888
        assert violation["username"] == "intruder"
        assert "payload_sha256_prefix" in violation
        assert violation["event"] == "UNAUTHORIZED_DISCORD_ACCESS"
        assert bot._last_message_id == "5003"

    def test_poll_once_tracks_after_snowflake_monotonically(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Messages returned out of order: 5010, 5005, 5020
        mock_resp.json.return_value = [
            {"id": "5010", "author": {"id": "1001", "bot": False}, "content": "msg2"},
            {"id": "5005", "author": {"id": "1001", "bot": False}, "content": "msg1"},
            {"id": "5020", "author": {"id": "1001", "bot": False}, "content": "msg3"},
        ]
        mock_http.get.return_value = mock_resp

        res = bot.poll_once(channel_id="12345", mock_http=mock_http)
        assert res is True
        assert bot._last_message_id == "5020"

        # Second pass: verify 'after=5020' query param is included
        mock_resp.json.return_value = []
        bot.poll_once(channel_id="12345", mock_http=mock_http)
        call_url = mock_http.get.call_args[0][0]
        assert "after=5020" in call_url

    def test_poll_once_fatal_http_error_terminates_loop(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345)
        mock_http = MagicMock()

        for status_code in (401, 403, 404):
            bot._running = True
            mock_resp = MagicMock()
            mock_resp.status_code = status_code
            mock_http.get.return_value = mock_resp

            res = bot.poll_once(channel_id="12345", mock_http=mock_http)
            assert res is False
            assert bot._running is False

    def test_poll_once_consecutive_errors_threshold_terminates_loop(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, consecutive_error_threshold=3)
        bot._running = True

        mock_http = MagicMock()
        mock_http.get.side_effect = ConnectionError("Connection refused by peer")

        # Error 1
        res1 = bot.poll_once(channel_id="12345", mock_http=mock_http)
        assert res1 is True
        assert bot.consecutive_errors == 1
        assert bot._running is True

        # Error 2
        res2 = bot.poll_once(channel_id="12345", mock_http=mock_http)
        assert res2 is True
        assert bot.consecutive_errors == 2
        assert bot._running is True

        # Error 3 (reaches threshold 3) -> terminates
        res3 = bot.poll_once(channel_id="12345", mock_http=mock_http)
        assert res3 is False
        assert bot.consecutive_errors == 3
        assert bot._running is False

    def test_stop_polling_cleans_up_thread(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, poll_interval_s=0.05)
        with patch.object(bot, "poll_once", return_value=True):
            bot.start_polling()
            assert bot._poll_thread is not None
            assert bot._poll_thread.is_alive() is True
            assert bot._running is True

            bot.stop_polling(timeout=1.0)
            assert bot._running is False
            assert bot._stop_event.is_set() is True
            assert bot._poll_thread is None

    def test_poll_once_dispatches_to_handle_message_when_no_handler(self):
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        assert bot.message_handler is None
        with patch.object(bot, "handle_message") as mock_handle:
            mock_http = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [
                {
                    "id": "5050",
                    "author": {"id": "1001", "username": "bob", "bot": False},
                    "content": "hello jarvis",
                }
            ]
            mock_http.get.return_value = mock_resp

            res = bot.poll_once(channel_id="12345", mock_http=mock_http)
            assert res is True
            assert mock_handle.called is True
            args, kwargs = mock_handle.call_args
            assert kwargs.get("user_id") == 1001
            assert kwargs.get("username") == "bob"
            assert kwargs.get("content") == "hello jarvis"


