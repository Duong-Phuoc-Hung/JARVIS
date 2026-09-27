"""Bot API boundary responses are controlled; these are not live Telegram evidence."""

from types import SimpleNamespace

import pytest
import requests

from jarvis.comms.telegram import TelegramBotController, TelegramConfig


class API:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status
        self.sends = []

    def get(self, *a, **kw):
        return SimpleNamespace(status_code=self.status, json=lambda: self.body)

    def post(self, *a, **kw):
        self.sends.append(kw)
        return SimpleNamespace(status_code=self.status, json=lambda: self.body)


def test_http_200_api_failure_is_not_a_send_success(monkeypatch):
    api = API({"ok": False, "error_code": 401, "description": "unsafe echo"})
    monkeypatch.setattr(requests, "Session", lambda: api)
    bot = TelegramBotController(
        config=TelegramConfig(
            bot_token="test-token", whitelist_user_ids={1}, whitelist_chat_ids={1}
        )
    )
    result = bot.send_message(1, "test")
    assert result["ok"] is False
    assert result["error_code"] == "AUTH_FAILED"


def test_duplicate_update_is_not_dispatched_or_replied_twice(monkeypatch):
    update = {
        "update_id": 8,
        "message": {"message_id": 3, "from": {"id": 1}, "chat": {"id": 1}, "text": "/help"},
    }
    api = API({"ok": True, "result": [update, update]})
    monkeypatch.setattr(requests, "Session", lambda: api)
    bot = TelegramBotController(
        config=TelegramConfig(
            bot_token="test-token", whitelist_user_ids={1}, whitelist_chat_ids={1}
        )
    )
    first = bot.poll_once()
    second = bot.poll_once()
    assert len(first) == 1 and second == []
    assert len(api.sends) == 1


def configured():
    return TelegramBotController(
        config=TelegramConfig(
            bot_token="test-token", whitelist_user_ids={1}, whitelist_chat_ids={2}
        )
    )


def test_sender_allowlist_does_not_authorize_other_chats():
    result = configured().handle_inbound_message(1, "/help", 999)
    assert result["status"] == 403


def test_poll_failure_has_truthful_status_and_no_secret_echo(monkeypatch, caplog):
    class Offline:
        def get(self, *a, **kw):
            raise requests.ConnectionError(
                "https://api.telegram.org/bottest-token/getUpdates sensitive"
            )

    monkeypatch.setattr(requests, "Session", Offline)
    bot = configured()
    result = bot.poll_updates()
    assert not result["ok"] and result["error_code"] == "OFFLINE"
    assert "test-token" not in str(result) + caplog.text


def test_send_network_error_is_redacted(monkeypatch):
    class Offline:
        def post(self, *a, **kw):
            raise requests.ConnectionError(
                "https://api.telegram.org/bottest-token/sendMessage sensitive"
            )

    monkeypatch.setattr(requests, "Session", Offline)
    result = configured().send_message(2, "test")
    assert not result["ok"] and result["error_code"] == "OFFLINE"
    assert "test-token" not in str(result) and "sensitive" not in str(result)


def test_send_refuses_recipient_outside_scope_without_http(monkeypatch):
    api = API({"ok": True, "result": {"message_id": 5}})
    monkeypatch.setattr(requests, "Session", lambda: api)
    assert configured().send_message(99, "test")["error_code"] == "CHAT_NOT_ALLOWED"
    assert api.sends == []


@pytest.mark.parametrize(
    "status,body,code",
    [
        (401, {}, "AUTH_FAILED"),
        (429, {"parameters": {"retry_after": 2}}, "RATE_LIMITED"),
        (200, {"ok": True, "result": {}}, "INVALID_RESPONSE"),
        (500, {}, "API_ERROR"),
    ],
)
def test_send_error_contract(monkeypatch, status, body, code):
    monkeypatch.setattr(requests, "Session", lambda: API(body, status))
    result = configured().send_message(2, "private-test-content")
    assert not result["ok"] and result["error_code"] == code and result["http_status"] == status


def test_timeout_reconnect_and_redacted_evidence(monkeypatch):
    class Recovering:
        calls = 0

        def get(self, *a, **kw):
            self.calls += 1
            if self.calls == 1:
                raise requests.Timeout("test-token")
            return SimpleNamespace(status_code=200, json=lambda: {"ok": True, "result": []})

    api = Recovering()
    monkeypatch.setattr(requests, "Session", lambda: api)
    bot = configured()
    assert bot.poll_updates()["error_code"] == "TIMEOUT"
    assert bot.poll_updates()["ok"] is True
    assert "test-token" not in str(bot.evidence)
    assert [e["http_status"] for e in bot.evidence] == [None, 200]


def test_checkpoint_prevents_restart_replay(monkeypatch, tmp_path):
    update = {
        "update_id": 12,
        "message": {"message_id": 4, "from": {"id": 1}, "chat": {"id": 2}, "text": "/help"},
    }
    api = API({"ok": True, "result": [update]})
    monkeypatch.setattr(requests, "Session", lambda: api)
    config = TelegramConfig(bot_token="test-token", whitelist_user_ids={1}, whitelist_chat_ids={2})
    config.checkpoint_path = str(tmp_path / "offset.json")
    assert len(TelegramBotController(config=config).poll_once()) == 1
    assert TelegramBotController(config=config).poll_once() == []
    assert "test-token" not in (tmp_path / "offset.json").read_text()


def test_dispatcher_denial_cannot_be_reported_as_command_success():
    from jarvis.core.dispatcher import ActionDispatcher

    dispatcher = ActionDispatcher()
    dispatcher.register_action("shell_exec", lambda: pytest.fail("must be gated"))
    bot = configured()
    bot.dispatcher = dispatcher
    result = bot.handle_inbound_message(1, "/exec shell_exec", 2)
    assert result["status"] != 200 and result["error_code"] == "CONFIRMATION_REQUIRED"


def test_safe_calc_uses_public_dispatcher_payload():
    from jarvis.core.dispatcher import ActionDispatcher

    dispatcher = ActionDispatcher()
    dispatcher.register_action(
        "skill_calculator",
        lambda expression: (
            {"success": True, "output": "4"} if expression == "2+2" else {"success": False}
        ),
    )
    bot = configured()
    bot.dispatcher = dispatcher
    result = bot.handle_inbound_message(1, "/calc 2+2", 2)
    assert result["status"] == 200 and "4" in result["text"]


def test_missing_resources_do_not_start_ghost_polling():
    bot = TelegramBotController()
    try:
        assert bot.start() is False
    finally:
        bot.stop()


def test_rate_limit_is_enforced_before_reconnecting(monkeypatch):
    calls = []

    class Limited:
        def get(self, *a, **kw):
            calls.append(1)
            return SimpleNamespace(
                status_code=429, json=lambda: {"ok": False, "parameters": {"retry_after": 60}}
            )

    monkeypatch.setattr(requests, "Session", Limited)
    bot = configured()
    assert bot.poll_updates()["error_code"] == "RATE_LIMITED"
    assert bot.poll_updates()["error_code"] == "RATE_LIMITED"
    assert len(calls) == 1


def test_failed_windows_lock_is_not_reported_as_success(monkeypatch):
    import jarvis.platform.windows as windows

    monkeypatch.setattr(windows, "lock_workstation", lambda: False, raising=False)
    result = configured().handle_inbound_message(1, "/lock", 2)
    assert result["status"] != 200


def test_missing_dispatcher_cannot_fabricate_available_skills():
    outcome = configured().handle_inbound_message(1, "/skills", 2)
    assert outcome["status"] == 503
    assert outcome["error_code"] == "DISPATCHER_UNAVAILABLE"
