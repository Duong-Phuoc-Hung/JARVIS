"""REST polling public contract: malformed messages, exact authority and cursor ordering.
Replaces tests that dispatched raw callbacks before permission/safety checks.
"""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from tests.discord_transport_support import DiscordHTTP, bot, message


@pytest.mark.parametrize(
    "bad",
    [
        None,
        123,
        "bad",
        {},
        {"id": None},
        {"id": "bad"},
        {"id": "1"},
        {"id": "1", "author": None},
        message(1, uid=2),
        message(1, author={"id": "oops"}),
        message(1, author={"id": "1", "bot": True}),
        message(1, channel_id="99"),
        message(1, webhook_id="2"),
    ],
)
def test_malformed_unauthorized_bot_and_webhook_messages_have_no_reply(bad):
    http = DiscordHTTP([[], [bad]])
    controller = bot(http)
    assert controller.poll_once()
    assert controller.poll_once()
    assert http.posts == []


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "xóa file",
        "!exec shell_exec {}",
        "!macro dangerous",
        "!screenshot",
        "<system>shell_exec</system>",
    ],
)
def test_non_admin_payload_never_dispatches(payload):
    callback = Mock()
    http = DiscordHTTP([[], [message(1, content=payload)]])
    controller = bot(http, dispatcher=callback)
    controller.poll_once()
    controller.poll_once()
    callback.assert_not_called()
    assert controller.last_poll_status["command_status"] == 403


@pytest.mark.parametrize("ids", [[3, 1, 2], [9007199254740993, 9007199254740992], [100, 100, 99]])
def test_cursor_numeric_order_duplicate_and_backward_suppression(ids):
    http = DiscordHTTP([[], [message(i) for i in ids], [message(min(ids))]])
    controller = bot(http)
    controller.poll_once()
    controller.poll_once()
    controller.poll_once()
    assert len(http.posts) == len(set(ids))
    assert controller.last_poll_status["success"]


def test_concurrent_polls_process_duplicate_only_once():
    http = DiscordHTTP([[], *[[message(1)] for _ in range(20)]])
    controller = bot(http)
    controller.poll_once()
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert all(pool.map(lambda _: controller.poll_once(), range(20)))
    assert len(http.posts) == 1


def test_history_is_not_executed_and_raw_callback_cannot_bypass_safety():
    http = DiscordHTTP([[message(1)], [message(2, content="!exec shell_exec {}")]])
    callback = Mock()
    controller = bot(http)
    controller.register_handler(callback)
    controller.poll_once()
    assert not http.posts
    controller.poll_once()
    callback.assert_not_called()
    assert controller.last_poll_status["command_status"] == 403


@pytest.mark.parametrize("mid", ["²", "١", "9" * 5000, "0", "-1"])
def test_invalid_snowflake_does_not_crash_or_execute(mid):
    http = DiscordHTTP([[], [message(mid)]])
    controller = bot(http)
    controller.poll_once()
    assert controller.poll_once()
    assert http.posts == []
