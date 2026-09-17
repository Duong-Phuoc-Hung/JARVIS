"""
tests/test_adversarial_m1_discord_error_recovery.py
===================================================
Adversarial test suite targeting DiscordBotController error recovery,
failure modes, and loop termination in Milestone M1 (Discord Inbound Gateway).

Verified scopes:
1. Consecutive error counter: verify exactly 5 consecutive network exceptions terminate polling loop.
2. HTTP 401, 403, 404: verify immediate loop termination without retry.
3. Empty bot token and empty channel ID: verify immediate non-spawning return.
4. Edge cases: error counter reset on success, live background thread termination,
   double start_polling thread deduplication, and non-401/403/404 HTTP errors.
"""
from __future__ import annotations

import socket
import ssl
import time
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from jarvis.comms.discord import DiscordBotController, DiscordConfig


class TestConsecutiveNetworkExceptionTermination:
    """
    Challenge Dimension 1: Consecutive Error Counter.
    Verify that exactly 5 consecutive network exceptions terminate the polling loop,
    and any intervening success resets the counter.
    """

    def test_exactly_five_consecutive_network_exceptions_terminate_poll_once(self):
        """
        Adversarially probe consecutive_errors step-by-step:
        Attempts 1 to 4 must return True (loop continues), with counter incrementing 1..4.
        Attempt 5 must return False (loop terminates), with counter reaching 5 and _running set to False.
        """
        bot = DiscordBotController(bot_token="test_bot_token_secret", channel_id=987654321)
        bot._running = True
        assert bot.consecutive_errors == 0
        assert bot.consecutive_error_threshold == 5

        mock_http = MagicMock()
        mock_http.get.side_effect = ConnectionResetError("Connection reset by peer [WSAECONNRESET]")

        # Iterations 1 through 4: must survive and keep polling
        for i in range(1, 5):
            continue_polling = bot.poll_once(channel_id=987654321, mock_http=mock_http)
            assert continue_polling is True, f"Failed at iteration {i}: loop terminated prematurely before threshold"
            assert bot.consecutive_errors == i, f"Expected consecutive_errors={i}, got {bot.consecutive_errors}"
            assert bot._running is True, f"bot._running must remain True at error {i}"

        # Iteration 5: exactly hits threshold 5 -> must terminate loop
        terminate_polling = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert terminate_polling is False, "Loop must terminate (return False) on exactly 5th consecutive error"
        assert bot.consecutive_errors == 5, f"Expected consecutive_errors=5, got {bot.consecutive_errors}"
        assert bot._running is False, "bot._running must be set to False on 5th error"

        # Subsequent call must immediately fail
        subsequent = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert subsequent is False

    def test_error_counter_resets_to_zero_on_successful_poll(self):
        """
        Adversarially probe counter reset:
        4 failures occur -> counter is 4.
        1 success occurs -> counter must reset to 0.
        4 more failures occur -> counter is 4, loop STILL running.
        5th failure in second streak -> terminates.
        """
        bot = DiscordBotController(bot_token="test_bot_token_secret", channel_id=987654321)
        bot._running = True

        mock_http = MagicMock()
        mock_http.get.side_effect = TimeoutError("Gateway request timed out")

        # 4 consecutive errors
        for i in range(1, 5):
            res = bot.poll_once(channel_id=987654321, mock_http=mock_http)
            assert res is True
            assert bot.consecutive_errors == i

        # 1 successful poll
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = []
        mock_http.get.side_effect = None
        mock_http.get.return_value = success_resp

        res_success = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res_success is True
        assert bot.consecutive_errors == 0, "consecutive_errors must be reset to 0 upon HTTP 200 success"
        assert bot._running is True

        # Second streak: 4 more errors
        mock_http.get.side_effect = TimeoutError("Second streak timeout")
        for i in range(1, 5):
            res = bot.poll_once(channel_id=987654321, mock_http=mock_http)
            assert res is True
            assert bot.consecutive_errors == i
            assert bot._running is True

        # 5th error in second streak terminates
        res_term = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res_term is False
        assert bot.consecutive_errors == 5
        assert bot._running is False

    def test_mixed_network_exceptions_streak(self):
        """
        Adversarially stress varied real-world network and socket exceptions.
        All network exceptions must increment the consecutive error counter.
        """
        exceptions = [
            socket.timeout("Socket recv timed out"),
            urllib.error.URLError("getaddrinfo failed: Temporary failure in name resolution"),
            ssl.SSLError("SSL: CERTIFICATE_VERIFY_FAILED"),
            ConnectionRefusedError("No connection could be made because target machine actively refused it"),
            OSError("Network is unreachable"),
        ]

        bot = DiscordBotController(bot_token="test_bot_token_secret", channel_id=987654321)
        bot._running = True
        mock_http = MagicMock()

        for idx, exc in enumerate(exceptions[:4], start=1):
            mock_http.get.side_effect = exc
            res = bot.poll_once(channel_id=987654321, mock_http=mock_http)
            assert res is True, f"Premature termination on exception {type(exc)}"
            assert bot.consecutive_errors == idx

        # 5th exception hits threshold
        mock_http.get.side_effect = exceptions[4]
        res_term = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res_term is False
        assert bot.consecutive_errors == 5
        assert bot._running is False

    def test_live_background_thread_terminates_after_five_errors(self):
        """
        Adversarially test the real worker thread execution:
        When start_polling() is invoked with continuous network failures,
        the background thread must automatically terminate after 5 consecutive errors
        without hanging or requiring external intervention.
        """
        mock_http = MagicMock()
        mock_http.get.side_effect = ConnectionError("Persistent network outage")

        bot = DiscordBotController(
            bot_token="test_bot_token_secret",
            channel_id=987654321,
            poll_interval_s=0.01,  # Fast interval for test speed
            consecutive_error_threshold=5,
            http_client=mock_http,
        )

        bot.start_polling()
        assert bot._running is True
        assert bot._poll_thread is not None
        assert bot._poll_thread.is_alive() is True

        # Wait for thread to encounter 5 errors and cleanly terminate
        bot._poll_thread.join(timeout=2.0)

        assert bot._poll_thread.is_alive() is False, "Thread must terminate when error threshold is exceeded"
        assert bot._running is False, "bot._running must be False after loop termination"
        assert bot.consecutive_errors == 5

    def test_custom_consecutive_error_threshold(self):
        """
        Adversarially probe configurable threshold (e.g. threshold = 2).
        Loop must terminate on exactly 2 consecutive errors.
        """
        bot = DiscordBotController(
            bot_token="test_bot_token_secret",
            channel_id=987654321,
            consecutive_error_threshold=2,
        )
        bot._running = True
        mock_http = MagicMock()
        mock_http.get.side_effect = ConnectionAbortedError("Aborted")

        res1 = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res1 is True
        assert bot.consecutive_errors == 1

        res2 = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res2 is False
        assert bot.consecutive_errors == 2
        assert bot._running is False


class TestImmediateTerminationOnFatalStatusCodes:
    """
    Challenge Dimension 2: HTTP 401, 403, 404 Fatal Errors.
    Verify immediate polling loop termination without retry for authentication,
    authorization, and not-found failures.
    """

    @pytest.mark.parametrize("status_code", [401, 403, 404])
    def test_fatal_http_status_codes_terminate_immediately_via_response(self, status_code: int):
        """
        Verify that HTTP 401, 403, 404 responses immediately return False
        on attempt #1 without incrementing consecutive_errors to 5.
        """
        bot = DiscordBotController(bot_token="test_bot_token_secret", channel_id=987654321)
        bot._running = True

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = f"Fatal Error {status_code}"
        mock_http.get.return_value = mock_resp

        res = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res is False, f"HTTP {status_code} must cause immediate termination on attempt 1"
        assert bot._running is False, f"bot._running must be False immediately on HTTP {status_code}"
        # consecutive_errors must NOT be incremented to threshold
        assert bot.consecutive_errors == 0, f"HTTP {status_code} should not count as transient network error"

    @pytest.mark.parametrize("status_code", [401, 403, 404])
    def test_fatal_http_status_codes_terminate_immediately_via_http_error_exception(self, status_code: int):
        """
        Verify that urllib.error.HTTPError with code 401, 403, 404
        immediately terminates polling loop without retry.
        """
        bot = DiscordBotController(bot_token="test_bot_token_secret", channel_id=987654321)
        bot._running = True

        mock_http = MagicMock()
        mock_http.get.side_effect = urllib.error.HTTPError(
            url="https://discord.com/api/v10/channels/987654321/messages",
            code=status_code,
            msg=f"HTTP Error {status_code}",
            hdrs={},
            fp=None,
        )

        res = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res is False, f"HTTPError {status_code} exception must cause immediate termination"
        assert bot._running is False
        assert bot.consecutive_errors == 0

    @pytest.mark.parametrize("status_code", [401, 403, 404])
    def test_fatal_status_code_in_live_background_thread_stops_immediately(self, status_code: int):
        """
        Verify that a background polling thread terminates on the first cycle
        when encountering 401, 403, or 404, without retrying 5 times.
        """
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_http.get.return_value = mock_resp

        bot = DiscordBotController(
            bot_token="test_bot_token_secret",
            channel_id=987654321,
            poll_interval_s=0.01,
            http_client=mock_http,
        )

        bot.start_polling()
        assert bot._poll_thread is not None

        # Thread must exit immediately after 1 call
        bot._poll_thread.join(timeout=1.0)
        assert bot._poll_thread.is_alive() is False
        assert bot._running is False
        # Ensure it was called at most once or twice, definitely not 5 retries
        assert mock_http.get.call_count == 1

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_server_errors_are_retryable_unlike_401_403_404(self, status_code: int):
        """
        Adversarial comparison: Unlike 401/403/404 which terminate immediately,
        server 5xx errors (500, 502, 503, 504) are treated as transient failures
        and only terminate when consecutive_error_threshold (5) is reached.
        """
        bot = DiscordBotController(bot_token="test_bot_token_secret", channel_id=987654321)
        bot._running = True

        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = f"Server Error {status_code}"
        mock_http.get.return_value = mock_resp

        # First call: raises RuntimeError, increments counter to 1, continues polling
        res1 = bot.poll_once(channel_id=987654321, mock_http=mock_http)
        assert res1 is True, f"HTTP {status_code} should be retryable on first failure"
        assert bot.consecutive_errors == 1
        assert bot._running is True


class TestEmptyTokenAndEmptyChannelFailClosed:
    """
    Challenge Dimension 3: Empty Bot Token and Empty Channel ID.
    Verify immediate non-spawning return and fail-closed defense.
    """

    def test_start_polling_empty_token_immediate_non_spawning_return(self):
        """Empty string token must immediately return without spawning thread."""
        bot = DiscordBotController(bot_token="", channel_id=123456789)
        bot.start_polling()
        assert bot._running is False
        assert bot._poll_thread is None

    def test_start_polling_none_token_immediate_non_spawning_return(self):
        """None token must immediately return without spawning thread."""
        bot = DiscordBotController(bot_token=None, channel_id=123456789)
        bot.start_polling()
        assert bot._running is False
        assert bot._poll_thread is None

    def test_start_polling_empty_channel_immediate_non_spawning_return(self):
        """Empty string channel_id must immediately return without spawning thread."""
        bot = DiscordBotController(bot_token="valid_token_123", channel_id="")
        bot.start_polling()
        assert bot._running is False
        assert bot._poll_thread is None

    def test_start_polling_none_channel_immediate_non_spawning_return(self):
        """None channel_id must immediately return without spawning thread."""
        bot = DiscordBotController(bot_token="valid_token_123", channel_id=None)
        bot.start_polling()
        assert bot._running is False
        assert bot._poll_thread is None

    def test_start_polling_both_empty_immediate_non_spawning_return(self):
        """Both empty token and empty channel must immediately return without spawning thread."""
        bot = DiscordBotController(bot_token="", channel_id="")
        bot.start_polling()
        assert bot._running is False
        assert bot._poll_thread is None

    def test_poll_once_with_empty_token_returns_false_without_network_calls(self):
        """Direct call to poll_once with empty bot_token returns False and makes no HTTP requests."""
        mock_http = MagicMock()
        bot = DiscordBotController(bot_token="", channel_id=123456789, http_client=mock_http)
        res = bot.poll_once(channel_id=123456789)
        assert res is False
        assert mock_http.get.call_count == 0

    def test_poll_once_with_empty_channel_returns_false_without_network_calls(self):
        """Direct call to poll_once with empty channel_id returns False and makes no HTTP requests."""
        mock_http = MagicMock()
        bot = DiscordBotController(bot_token="valid_token_123", channel_id="", http_client=mock_http)
        res = bot.poll_once(channel_id="")
        assert res is False
        assert mock_http.get.call_count == 0


class TestConcurrencyAndThreadLifecycle:
    """
    Challenge Dimension 4: Concurrency, Duplicate Spawns, and Graceful Teardown.
    """

    def test_duplicate_start_polling_call_does_not_spawn_duplicate_threads(self):
        """
        Adversarially invoke start_polling() twice.
        The second call must detect self._running is True and not create a second thread.
        """
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_http.get.return_value = mock_resp

        bot = DiscordBotController(
            bot_token="test_bot_token_secret",
            channel_id=987654321,
            poll_interval_s=0.1,
            http_client=mock_http,
        )

        bot.start_polling()
        first_thread = bot._poll_thread
        assert first_thread is not None
        assert first_thread.is_alive() is True

        # Second call
        bot.start_polling()
        assert bot._poll_thread is first_thread, "Second start_polling() must not overwrite or recreate thread"

        bot.stop_polling(timeout=1.0)
        assert bot._poll_thread is None
        assert bot._running is False

    def test_stop_polling_when_not_started_is_safe_noop(self):
        """Calling stop_polling on an unstarted controller must be a safe no-op."""
        bot = DiscordBotController(bot_token="test_bot_token_secret", channel_id=987654321)
        assert bot._running is False
        assert bot._poll_thread is None
        bot.stop_polling()
        assert bot._running is False
        assert bot._poll_thread is None
