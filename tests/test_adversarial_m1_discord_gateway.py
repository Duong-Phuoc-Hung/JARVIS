"""
tests/test_adversarial_m1_discord_gateway.py
============================================
Adversarial Challenge & Stress Test Suite for Milestone M1:
Discord Inbound Gateway (jarvis/comms/discord.py).

Empirical verification harness targeting:
1. Malformed message dictionaries (missing author, non-dict payloads, missing IDs, nulls, corrupt content).
2. Author ID types (int vs string in whitelist, type normalization, fail-closed enforcement).
3. Rapid start_polling / stop_polling toggling (concurrency, race conditions, thread cleanup).
4. Out of order snowflakes (monotonic tracking, chronological dispatch, 64-bit ID ordering, invalid snowflake poisoning).
5. Unhandled exception escape verification (resilience of polling loop and handler boundaries).
"""

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jarvis.comms.discord import DiscordBotController, DiscordConfig


# ============================================================================
# 1. MALFORMED MESSAGE DICTIONARIES
# ============================================================================


class TestAdversarialMalformedMessages:
    """Stress tests message ingestion against malformed, corrupt, or unexpected payloads."""

    def test_non_dict_elements_in_raw_messages_handling(self):
        """
        Adversarial Test: Discord API or proxy returns non-dict elements in raw_messages
        e.g. [None], [123], ['invalid_string'].
        Asserts whether poll_once handles or crashes with AttributeError.
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        # Hostile payloads containing non-dict items
        hostile_payloads = [
            [None],
            [12345],
            ["string_instead_of_dict"],
            [None, {"id": "100", "author": {"id": 1001}, "content": "valid"}],
        ]

        for payload in hostile_payloads:
            mock_resp.json.return_value = payload
            mock_http.get.return_value = mock_resp
            # If implementation is resilient, this should NOT raise AttributeError.
            # We assert the empirical behavior.
            try:
                bot.poll_once(channel_id=12345, mock_http=mock_http)
            except AttributeError as exc:
                pytest.fail(f"Unhandled AttributeError escaped poll_once on payload {payload!r}: {exc}")

    def test_empty_and_missing_field_dicts_fail_closed(self):
        """
        Tests message dictionaries missing standard fields (missing author, missing id, missing content).
        Asserts fail-closed: no unauthorized dispatch, no unhandled exceptions.
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        dispatched: list[dict[str, Any]] = []
        bot.register_handler(lambda msg: dispatched.append(msg))

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        malformed_dicts = [
            {},                                      # completely empty
            {"id": None},                            # id is None
            {"id": ""},                              # id is empty string
            {"author": None},                        # author is None
            {"author": "not_a_dict"},                # author is string
            {"author": {}},                          # author has no id
            {"author": {"id": None}},                # author id is None
            {"author": {"id": ""}},                  # author id is empty string
            {"author": {"id": "invalid_number"}},    # author id is non-numeric
            {"id": "501", "content": None},          # content is None
            {"id": "502", "content": 12345},         # content is integer
        ]

        mock_resp.json.return_value = malformed_dicts
        mock_http.get.return_value = mock_resp

        res = bot.poll_once(channel_id=12345, mock_http=mock_http)
        assert res is True
        # None of these malformed entries belong to authorized user 1001, so dispatched must be 0
        assert len(dispatched) == 0

    def test_hostile_content_payloads_do_not_crash_sha256(self):
        """
        Tests malicious or extreme content payloads (null bytes, 100k chars, unicode, emojis).
        Verifies SHA-256 audit hashing handles them safely without exception.
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        hostile_contents = [
            "\x00\x01\x02\x1f\x7f\xff",              # raw binary bytes / null bytes
            "A" * 100_000,                           # 100,000 character buffer overflow probe
            "🚨🔥💥🤖💣⚠️💀" * 500,                   # heavy multi-byte emojis
            "'; DROP TABLE users; --",               # SQL injection probe
            "<script>alert('xss')</script>",         # XSS probe
            "Tiếng Việt có dấu: Ứng dụng điều khiển", # Vietnamese unicode
        ]

        for i, content in enumerate(hostile_contents):
            mock_resp.json.return_value = [
                {
                    "id": f"600{i}",
                    "author": {"id": 9999, "username": "adversary"},
                    "content": content,
                }
            ]
            mock_http.get.return_value = mock_resp
            res = bot.poll_once(channel_id=12345, mock_http=mock_http)
            assert res is True

        # All 6 hostile messages should have been logged in security_violations with valid SHA-256 prefixes
        assert len(bot.security_violations) == len(hostile_contents)
        for v in bot.security_violations:
            assert len(v["payload_sha256_prefix"]) == 12


# ============================================================================
# 2. AUTHOR ID TYPES & WHITELIST REJECTION
# ============================================================================


class TestAdversarialAuthorIdTypes:
    """Stress tests author ID typing, string vs int in whitelist, and fail-closed rules."""

    def test_string_whitelist_vs_int_coercion_behavior(self):
        """
        Adversarial Test: Config provides string whitelist IDs (e.g. ['1001']).
        Discord API returns author.id as string '1001'.
        In poll_once, author_id_int = int(author['id']) -> 1001.
        Does is_user_authorized(1001) match ['1001'] or fail closed?
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=["1001"])
        dispatched: list[dict[str, Any]] = []
        bot.register_handler(lambda msg: dispatched.append(msg))

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "id": "7001",
                "author": {"id": "1001", "username": "alice", "bot": False},
                "content": "hello",
            }
        ]
        mock_http.get.return_value = mock_resp

        res = bot.poll_once(channel_id=12345, mock_http=mock_http)
        assert res is True
        # A robust gateway must handle string whitelist IDs without false security rejections:
        assert len(dispatched) == 1, (
            f"Configuring whitelist_user_ids with string IDs failed to authorize incoming user: "
            f"violations={bot.security_violations}"
        )

    def test_empty_or_none_whitelist_is_strictly_fail_closed(self):
        """
        Verify that None, empty list, or missing whitelist rejects all incoming messages,
        including user_id 0, negative IDs, or admin IDs.
        """
        for empty_val in ([], None):
            bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=empty_val)
            dispatched: list[dict[str, Any]] = []
            bot.register_handler(lambda msg: dispatched.append(msg))

            mock_http = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [
                {"id": "7002", "author": {"id": 1, "username": "superadmin"}, "content": "!admin"},
                {"id": "7003", "author": {"id": 0, "username": "zero"}, "content": "!test"},
            ]
            mock_http.get.return_value = mock_resp

            res = bot.poll_once(channel_id=12345, mock_http=mock_http)
            assert res is True
            assert len(dispatched) == 0, f"Empty whitelist {empty_val!r} allowed message dispatch!"

    def test_author_id_zero_or_negative_rejected(self):
        """Author ID <= 0 is invalid for Discord snowflakes and must never be authorized."""
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[0, -1, 1001])
        assert bot.is_user_authorized(0) is False, "user_id 0 was authorized"
        assert bot.is_user_authorized(-1) is False, "Negative user_id -1 was authorized"
        assert bot.is_user_authorized(1001) is True


# ============================================================================
# 3. RAPID START / STOP POLLING TOGGLING (RACE CONDITIONS)
# ============================================================================


class TestAdversarialPollingConcurrency:
    """Stress tests start_polling and stop_polling under rapid toggling and concurrent pressure."""

    def test_rapid_start_stop_sequence_no_deadlock(self):
        """Sequential 50 start/stop cycles with fast intervals to assert no thread hangs."""
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, poll_interval_s=0.005)
        bot.poll_once = MagicMock(return_value=True)

        for _ in range(30):
            bot.start_polling()
            assert bot._running is True
            bot.stop_polling(timeout=0.2)
            assert bot._running is False
            assert bot._poll_thread is None

    def test_concurrent_start_stop_pounding(self):
        """
        Multiple worker threads pounding start_polling and stop_polling concurrently.
        Asserts no unhandled exceptions and that all spawned threads terminate.
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, poll_interval_s=0.01)
        bot.poll_once = MagicMock(return_value=True)

        errors: list[Exception] = []

        def worker_start():
            try:
                for _ in range(25):
                    bot.start_polling()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def worker_stop():
            try:
                for _ in range(25):
                    bot.stop_polling(timeout=0.05)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker_start),
            threading.Thread(target=worker_stop),
            threading.Thread(target=worker_start),
            threading.Thread(target=worker_stop),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        # Cleanup
        bot.stop_polling(timeout=0.5)

        assert len(errors) == 0, f"Concurrent start/stop raised exceptions: {errors}"
        assert bot._running is False
        assert bot._poll_thread is None

    def test_missing_credentials_start_polling_is_strictly_fail_closed(self):
        """Ensure invalid/empty token or channel never starts any background thread."""
        cases = [
            ("", 12345),
            ("valid_token", None),
            (None, None),
            ("", None),
        ]
        for token, channel in cases:
            bot = DiscordBotController(bot_token=token, channel_id=channel)
            bot.start_polling()
            assert bot._running is False
            assert bot._poll_thread is None


# ============================================================================
# 4. OUT OF ORDER SNOWFLAKES & MONOTONIC TRACKING
# ============================================================================


class TestAdversarialSnowflakeTracking:
    """Stress tests snowflake ordering, monotonicity, and query construction."""

    def test_out_of_order_snowflakes_dispatched_in_numeric_order(self):
        """
        Discord messages arriving out of order must be dispatched in ascending
        chronological order (by numeric snowflake ID).
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        dispatched_ids: list[str] = []
        bot.register_handler(lambda msg: dispatched_ids.append(msg["id"]))

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        # Out of order IDs
        mock_resp.json.return_value = [
            {"id": "5030", "author": {"id": 1001}, "content": "3"},
            {"id": "5010", "author": {"id": 1001}, "content": "1"},
            {"id": "5050", "author": {"id": 1001}, "content": "4"},
            {"id": "5020", "author": {"id": 1001}, "content": "2"},
        ]
        mock_http.get.return_value = mock_resp

        bot.poll_once(channel_id=12345, mock_http=mock_http)

        assert dispatched_ids == ["5010", "5020", "5030", "5050"]
        assert bot._last_message_id == "5050"

    def test_monotonic_tracking_rejects_backwards_snowflakes(self):
        """
        If a subsequent poll receives an older snowflake (clock skew or network retransmit),
        _last_message_id must NOT regress backwards.
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        # Poll 1: Advances to 9000
        mock_resp.json.return_value = [{"id": "9000", "author": {"id": 1001}, "content": "newest"}]
        mock_http.get.return_value = mock_resp
        bot.poll_once(channel_id=12345, mock_http=mock_http)
        assert bot._last_message_id == "9000"

        # Poll 2: Receives older message 8500
        mock_resp.json.return_value = [{"id": "8500", "author": {"id": 1001}, "content": "older"}]
        bot.poll_once(channel_id=12345, mock_http=mock_http)
        assert bot._last_message_id == "9000", "Snowflake regressed backwards!"

    def test_64bit_snowflakes_differ_from_lexicographical_order(self):
        """
        Verify numeric comparison of 64-bit snowflakes where string length differs.
        Lexicographically '99' > '100', but numerically 100 > 99.
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        dispatched_ids: list[str] = []
        bot.register_handler(lambda msg: dispatched_ids.append(msg["id"]))

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "100000000000000000", "author": {"id": 1001}, "content": "b"},
            {"id": "99999999999999999", "author": {"id": 1001}, "content": "a"},
        ]
        mock_http.get.return_value = mock_resp

        bot.poll_once(channel_id=12345, mock_http=mock_http)

        assert dispatched_ids == ["99999999999999999", "100000000000000000"]
        assert bot._last_message_id == "100000000000000000"

    def test_non_numeric_snowflake_poisoning(self):
        """
        Adversarial Test: What happens when an invalid snowflake like 'invalid' or '' arrives?
        Does it corrupt _last_message_id to 'invalid', causing Discord API 400 Bad Request?
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "invalid", "author": {"id": 1001}, "content": "corrupted id"}
        ]
        mock_http.get.return_value = mock_resp

        bot.poll_once(channel_id=12345, mock_http=mock_http)

        # In a hardened gateway, non-numeric snowflake IDs must not poison _last_message_id:
        assert bot._last_message_id is None or bot._last_message_id.isdigit(), (
            f"_last_message_id was poisoned with non-digit value {bot._last_message_id!r}, "
            f"which will cause HTTP 400 Bad Request on Discord REST endpoint"
        )


# ============================================================================
# 5. UNHANDLED EXCEPTION ESCAPES & THREAD RESILIENCE
# ============================================================================


class TestAdversarialExceptionResilience:
    """Stress tests exception containment in polling loop and message dispatch."""

    def test_handle_message_exception_escapes_poll_once(self):
        """
        Adversarial Test: When message_handler is None, poll_once delegates to handle_message.
        If handle_message raises an unexpected exception (e.g. database error, skill crash),
        does poll_once catch it or let it escape unhandled?
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])
        assert bot.message_handler is None

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "9999", "author": {"id": 1001, "username": "alice"}, "content": "crash_me"}
        ]
        mock_http.get.return_value = mock_resp

        with patch.object(bot, "handle_message", side_effect=RuntimeError("Simulated DB lock failure")):
            # If implementation is robust, an error inside handle_message should be logged
            # and NOT escape unhandled out of poll_once to kill the polling thread.
            try:
                bot.poll_once(channel_id=12345, mock_http=mock_http)
            except RuntimeError as exc:
                pytest.fail(f"Unhandled RuntimeError escaped poll_once: {exc}")

    def test_custom_message_handler_exception_is_contained(self):
        """
        Verify that an exception in custom message_handler is properly caught and logged,
        never crashing the polling loop.
        """
        bot = DiscordBotController(bot_token="test_token", channel_id=12345, whitelist_user_ids=[1001])

        def failing_handler(msg):
            raise ValueError("Custom handler blew up")

        bot.register_handler(failing_handler)

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "9998", "author": {"id": 1001, "username": "alice"}, "content": "test"}
        ]
        mock_http.get.return_value = mock_resp

        # Must not raise
        res = bot.poll_once(channel_id=12345, mock_http=mock_http)
        assert res is True
