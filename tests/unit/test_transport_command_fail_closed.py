"""Command boundaries use synthetic dependencies; never provider runtime evidence."""
from types import SimpleNamespace

import pytest

from jarvis.comms.telegram import TelegramBotController
from jarvis.comms.zalo import ZaloBotController, ZaloConfig
from jarvis.core.dispatcher import ActionDispatcher

CANARY = "synthetic-private-canary"


def fail(*args, **kwargs):
    raise RuntimeError(CANARY)


@pytest.mark.parametrize("user, chat", [(2, None), (1, 9)])
def test_telegram_unauthorized_voice_never_reaches_stt(user, chat):
    calls = []
    bot = TelegramBotController(allowed_user_ids={1}, stt_engine=SimpleNamespace(transcribe=lambda value: calls.append(value)))
    assert bot.handle_inbound_voice(user, b"test", chat_id=chat)["status"] == 403
    assert calls == []


@pytest.mark.parametrize("engine", [None, SimpleNamespace(transcribe=fail)])
def test_telegram_voice_failure_is_redacted_not_acknowledged(engine, caplog):
    bot = TelegramBotController(allowed_user_ids={1}, stt_engine=engine)
    result = bot.handle_inbound_voice(1, b"test")
    assert result["status"] == 503
    assert result["error_code"] == "TRANSCRIPTION_UNAVAILABLE"
    assert CANARY not in str(result) + caplog.text


@pytest.mark.parametrize("command, action, payload", [
    ("/note test", "skill_note_taker", {"action": "add", "text": "test"}),
    ("/screenshot", "skill_system_control", {"action": "screenshot"}),
])
def test_zalo_sensitive_commands_use_confirmation(command, action, payload):
    effects = []
    dispatcher = ActionDispatcher()
    dispatcher.register_action(action, lambda **kw: effects.append(kw) or {"success": True})
    bot = ZaloBotController(ZaloConfig(whitelist_user_ids=["tester"]), dispatcher=dispatcher)
    result = bot.handle_message("tester", "test", command)
    assert result["status"] == 409
    assert result["error_code"] == "CONFIRMATION_REQUIRED"
    assert effects == []
    pending = dispatcher.safety_interceptor.safety_gate.get_latest_pending()
    assert pending.payload["action_name"] == action
    assert pending.payload["parameters"] == payload
    assert dispatcher.safety_interceptor.confirm(pending.token)
    confirmed = dispatcher.dispatch_action(action, payload, confirmation_token=pending.token)
    assert confirmed.success and effects == [payload]


@pytest.mark.parametrize("command", ["/note test", "/screenshot", "/calc 1+1", "/briefing"])
def test_zalo_unconfigured_command_dispatch_fails_closed(command):
    bot = ZaloBotController(ZaloConfig(whitelist_user_ids=["tester"]))
    result = bot.handle_message("tester", "test", command)
    assert result["status"] == 503
    assert result["error_code"] == "DISPATCHER_UNAVAILABLE"


def test_zalo_dependency_error_has_no_secret_echo(caplog):
    dispatcher = SimpleNamespace(dispatch_action=fail)
    bot = ZaloBotController(ZaloConfig(whitelist_user_ids=["tester"]), dispatcher=dispatcher)
    result = bot.handle_message("tester", "test", "/calc 1+1")
    assert result["status"] == 503
    assert CANARY not in str(result) + caplog.text


def test_zalo_missing_llm_does_not_claim_handled(monkeypatch, caplog):
    from jarvis.llm.client import LLMClient
    monkeypatch.setattr(LLMClient, "generate", fail)
    bot = ZaloBotController(ZaloConfig(whitelist_user_ids=["tester"]))
    result = bot.handle_message("tester", "test", "test question")
    assert result["status"] == 503
    assert result["error_code"] == "LLM_UNAVAILABLE"
    assert CANARY not in str(result) + caplog.text


@pytest.mark.parametrize("action, payload", [
    ("skill_note_taker", {"action": "add", "text": "test"}),
    ("skill_system_control", {"action": "screenshot"}),
])
def test_sensitive_skill_alias_cannot_bypass_dispatcher_gate(action, payload):
    effects = []
    dispatcher = ActionDispatcher()
    dispatcher.register_action(action, lambda **kw: effects.append(kw))
    result = dispatcher.dispatch_action(action, payload)
    assert not result.success and result.error_code == "CONFIRMATION_REQUIRED"
    assert effects == []


def test_zalo_authorized_calculator_remains_usable():
    from jarvis.skills.calculator import execute
    dispatcher = ActionDispatcher()
    dispatcher.register_action("skill_calculator", execute)
    bot = ZaloBotController(ZaloConfig(whitelist_user_ids=["tester"]), dispatcher=dispatcher)
    result = bot.handle_message("tester", "test", "/calc 1+1")
    assert result["status"] == 200 and "2" in result["text"]


def test_telegram_authorized_voice_remains_usable():
    bot = TelegramBotController(allowed_user_ids={1}, stt_engine=SimpleNamespace(transcribe=lambda value: "/help"))
    result = bot.handle_inbound_voice(1, b"test", chat_id=1)
    assert result["status"] == 200 and "Telegram Commands" in result["text"]


def test_zalo_llm_failed_response_cannot_claim_success(monkeypatch):
    from jarvis.llm.client import LLMClient, LLMResponse
    monkeypatch.setattr(LLMClient, "generate", lambda *a, **kw: LLMResponse(content="unverified", success=False))
    bot = ZaloBotController(ZaloConfig(whitelist_user_ids=["tester"]))
    result = bot.handle_message("tester", "test", "test question")
    assert result["status"] == 503 and result["error_code"] == "LLM_UNAVAILABLE"
