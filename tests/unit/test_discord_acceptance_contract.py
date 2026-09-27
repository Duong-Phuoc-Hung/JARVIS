from unittest.mock import Mock

import pytest

from jarvis.comms.discord import DiscordBotController
from jarvis.core.dispatcher import ActionDispatcher


def test_whitelist_does_not_implicitly_grant_admin():
    bot = DiscordBotController(whitelist_user_ids=[1])
    assert not bot.is_admin(1)


def test_discord_dangerous_action_reaches_real_safety_gate_without_effect(tmp_path):
    canary = tmp_path / "effect"
    d = ActionDispatcher()
    d.register_action("shell_exec", lambda **kwargs: canary.write_text("bad"))
    bot = DiscordBotController(whitelist_user_ids=[1], admin_user_ids=[1], dispatcher=d)
    result = bot.handle_message(1, "tester", '!exec shell_exec {"command":"echo test"}')
    assert result["status"] == 409
    assert result["error_code"] == "CONFIRMATION_REQUIRED"
    assert len(d.safety_interceptor.safety_gate.list_pending()) == 1
    assert not canary.exists()


@pytest.mark.parametrize(
    "content", ["!exec shell_exec {}", "!macro test", "!screenshot", "xóa file"]
)
def test_non_admin_cannot_reach_any_action_path(content):
    callback = Mock()
    bot = DiscordBotController(whitelist_user_ids=[1], admin_user_ids=[2], dispatcher=callback)
    assert bot.handle_message(1, "user", content)["status"] == 403
    callback.assert_not_called()


from unittest.mock import patch

import requests


def response(code, data):
    r = Mock(status_code=code)
    r.json.return_value = data
    return r


def configured(client):
    return DiscordBotController(
        bot_token="test-token",
        guild_id=20,
        channel_id=30,
        whitelist_user_ids=[1],
        admin_user_ids=[1],
        http_client=client,
    )


def channel_response():
    return response(200, {"id": "30", "guild_id": "20"})


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_send_reports_provider_failure_without_content_or_token(status):
    client = Mock()
    client.request.side_effect = [
        channel_response(),
        response(status, {"retry_after": 10, "message": "private-canary"}),
    ]
    bot = configured(client)
    result = bot.send_message(30, "private-canary")
    assert result["success"] is False
    assert result["http_status"] == status
    assert "private-canary" not in str(result) + str(bot.sent_messages)
    assert "test-token" not in str(result)


def test_outbound_requires_message_id_and_channel_binding():
    client = Mock()
    client.request.side_effect = [channel_response(), response(200, {})]
    bot = configured(client)
    result = bot.send_message(30, "test")
    assert result["success"] is False
    assert result["error_code"] == "INVALID_RESPONSE"
    assert bot.send_message(999, "test")["error_code"] == "CHANNEL_NOT_ALLOWED"


def test_poll_command_reply_and_duplicate_suppression():
    client = Mock()
    msg = {"id": "100", "channel_id": "30", "author": {"id": "1"}, "content": "!help"}
    client.request.side_effect = [
        channel_response(),
        response(200, []),
        response(200, [msg]),
        response(200, {"id": "101", "channel_id": "30"}),
        response(200, [msg]),
    ]
    bot = configured(client)
    assert bot.poll_once()  # bootstrap ignores existing channel history
    assert bot.poll_once()
    assert bot.poll_once()
    posts = [c for c in client.request.call_args_list if c.args[0] == "POST"]
    assert len(posts) == 1
    assert bot.sent_messages[-1]["message_id"] == "101"


def test_rate_limit_cooldown_does_not_retry_send():
    client = Mock()
    client.request.side_effect = [channel_response(), response(429, {"retry_after": 30})]
    bot = configured(client)
    bot.send_message(30, "one")
    bot.send_message(30, "two")
    assert client.request.call_count == 2


def test_transport_failure_redacted_and_reconnect(caplog):
    client = Mock()
    client.request.side_effect = [
        channel_response(),
        requests.Timeout("test-token private-canary"),
        response(200, []),
    ]
    bot = configured(client)
    assert bot.poll_once()
    assert bot.last_poll_status["error_code"] == "TIMEOUT"
    assert bot.poll_once()
    assert bot.last_poll_status["success"] is True
    assert "private-canary" not in caplog.text


def test_provider_cooldown_does_not_exhaust_error_budget():
    client = Mock()
    client.request.side_effect = [
        channel_response(),
        response(429, {"retry_after": 30}),
        response(200, []),
    ]
    controller = configured(client)
    with patch("jarvis.comms.discord.time.monotonic", return_value=10):
        assert controller.poll_once()
        assert all(controller.poll_once() for _ in range(10))
    assert client.request.call_count == 2
    with patch("jarvis.comms.discord.time.monotonic", return_value=41):
        assert controller.poll_once()
    assert controller.last_poll_status["success"]


def test_disabled_config_never_starts_or_sends():
    from jarvis.comms.discord import DiscordConfig

    client = Mock()
    controller = DiscordBotController(
        config=DiscordConfig(bot_token="dummy", guild_id=20, default_channel_id=30, enabled=False),
        http_client=client,
    )
    assert controller.start_polling()["error_code"] == "DISABLED"
    assert controller.send_message(30, "private-canary")["error_code"] == "DISABLED"
    client.request.assert_not_called()
