"""Discord REST lifecycle at the HTTP boundary; no network/provider success inferred."""

import threading
import time

import pytest
import requests

from jarvis.comms.discord import DiscordBotController
from tests.discord_transport_support import DiscordHTTP, bot


@pytest.mark.parametrize("status", [401, 403, 404])
def test_fatal_http_stops_immediately(status):
    controller = bot(DiscordHTTP([(status, {})]))
    assert not controller.poll_once()
    assert controller.last_poll_status["error_code"] == f"HTTP_{status}"


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_retry_to_threshold(status):
    controller = bot(DiscordHTTP([(status, {})] * 5))
    assert [controller.poll_once() for _ in range(5)] == [True, True, True, True, False]


@pytest.mark.parametrize(
    "error",
    [
        requests.Timeout("private-canary"),
        requests.ConnectionError("private-canary"),
        OSError("private-canary"),
    ],
)
def test_error_counter_resets_and_terminates(error, caplog):
    controller = bot(DiscordHTTP([error] * 4 + [[]] + [error] * 5))
    assert all(controller.poll_once() for _ in range(5))
    assert controller.consecutive_errors == 0
    assert [controller.poll_once() for _ in range(5)] == [True, True, True, True, False]
    assert "private-canary" not in caplog.text


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"bot_token": "dummy"},
        {"bot_token": "dummy", "channel_id": 30},
        {"bot_token": "dummy", "guild_id": 20},
    ],
)
def test_missing_config_never_starts(kwargs):
    controller = DiscordBotController(**kwargs)
    assert not controller.start_polling()["success"]
    assert controller.stop_polling()["success"]


def test_start_stop_restart_and_duplicate_start():
    controller = bot(DiscordHTTP())
    for _ in range(10):
        assert controller.start_polling()["success"]
        assert controller.start_polling()["error_code"] == "ALREADY_RUNNING"
        assert controller.stop_polling()["success"]


def test_stop_timeout_retains_worker_prevents_duplicate_restart():
    entered = threading.Event()
    release = threading.Event()

    class Blocking(DiscordHTTP):
        def request(self, method, url, **kwargs):
            if "/messages?" in url:
                entered.set()
                release.wait(2)
            return super().request(method, url, **kwargs)

    controller = bot(Blocking())
    try:
        assert controller.start_polling()["success"]
        assert entered.wait(1)
        assert controller.stop_polling(timeout=0.001)["error_code"] == "STOP_TIMEOUT"
        assert controller.start_polling()["error_code"] == "STOPPING"
    finally:
        release.set()
        assert controller.stop_polling()["success"]


def test_background_worker_stops_on_fatal_http():
    controller = bot(DiscordHTTP([(403, {})]))
    assert controller.start_polling()["success"]
    deadline = time.monotonic() + 2
    while (
        controller.last_poll_status.get("error_code") != "HTTP_403" and time.monotonic() < deadline
    ):
        threading.Event().wait(0.01)
    assert controller.last_poll_status["error_code"] == "HTTP_403"
    assert controller.stop_polling()["success"]
