"""Installed-application routing contracts; no OS discovery or launches."""

from unittest.mock import Mock

import pytest

from jarvis.llm.client import LLMResponse, ToolCall
from jarvis.llm.router import LLMIntentRouter


@pytest.mark.parametrize("phrase, name", [
    ("mở ứng dụng Calculator", "Calculator"),
    ("mở ứng dụng Notepad", "Notepad"),
    ("mở ứng dụng Spotify", "Spotify"),
    ("mở ứng dụng Settings", "Settings"),
    ("mở ứng dụng Example Editor", "Example Editor"),
    ("mo ung dung Calculator", "Calculator"),
    ("open application Notepad", "Notepad"),
    ("Jarvis, mở app Tiếng Việt Editor", "Tiếng Việt Editor"),
    ("bật ứng dụng Calculator", "Calculator"),
])
def test_explicit_app_request_uses_catalog_before_legacy_aliases(phrase, name):
    result = LLMIntentRouter(llm_client=None).parse_intent(phrase)

    assert result.action_name == "app_open"
    assert result.parameters == {"app_name": name, "installed_only": True}
    assert result.raw_text == phrase


@pytest.mark.parametrize("phrase, name", [
    ("mở Example Editor", "Example Editor"),
    ("mo Example Editor", "Example Editor"),
    ("open Example Editor", "Example Editor"),
    ("Jarvis, mở Tiếng Việt Editor", "Tiếng Việt Editor"),
    ("mở Calculator Pro", "Calculator Pro"),
    ("mở Notepad++", "Notepad++"),
])
def test_unknown_short_app_name_routes_without_legacy_prefix_match(phrase, name):
    result = LLMIntentRouter(llm_client=None).parse_intent(phrase)

    assert result.action_name == "app_open"
    assert result.parameters == {"app_name": name, "installed_only": True}


@pytest.mark.parametrize("phrase, name", [
    ("mở Notepad", "notepad"),
    ("mở Calculator", "calculator"),
    ("mo calculator", "calculator"),
    ("open notepad", "notepad"),
    ("mở chrome", "chrome"),
    ("bật terminal", "terminal"),
    ("khởi động word", "word"),
    ("quản lý tác vụ", "taskmgr"),
])
def test_known_desktop_app_aliases_use_verified_catalog_launch(phrase, name):
    result = LLMIntentRouter(llm_client=None).parse_intent(phrase)

    assert result.action_name == "app_open"
    assert result.parameters["app_name"] == name
    assert result.parameters.get("installed_only") is True


@pytest.mark.parametrize("phrase", [
    "mở ứng dụng",
    "mở ứng dụng Calculator và Notepad",
    "mở ứng dụng Calculator; mở Notepad",
    "mở ứng dụng Calculator\nmở Notepad",
    "mở ứng dụng " + "A" * 121,
    "mở Calculator và Notepad",
    "mở Example Editor hoặc Notepad",
    "mở Notepad; mở Calculator",
    "mở Notepad\nmở Calculator",
    "Jarvis," + " " * 480 + "mở ứng dụng Calculator" + " " * 100 + "và Notepad",
    "mở" + " " * 502 + "Notepad" + " và Calculator",
])
def test_malformed_or_compound_app_request_asks_for_one_complete_name(phrase):
    result = LLMIntentRouter(llm_client=None).parse_intent(phrase)

    assert result.action_name == "unknown_intent"
    assert result.parameters.get("clarify") is True
    assert result.response_text


@pytest.mark.parametrize("phrase", [
    "tôi không muốn mở ứng dụng Calculator",
    "toi khong muon mo ung dung chrome",
    "đừng mở ứng dụng cài đặt",
    "do not open application Notepad",
    "tôi không muốn mở Notepad",
    "don't open Calculator",
    "đừng mở Example Editor",
    "Example Editor là gì",
])
def test_negation_and_noncommands_never_become_app_launches(phrase):
    result = LLMIntentRouter(llm_client=None).parse_intent(phrase)

    assert result.action_name == "unknown_intent"


@pytest.mark.parametrize("phrase, action, expected", [
    ("mở cài đặt windows", "app_open", {"app_name": "Settings", "app": "ms-settings:"}),
    ("mở spotify", "spotify", None),
    ("mở claude ai", "web_open", {"site": "claude"}),
    ("mở youtube", "web_open", {"site": "youtube"}),
    ("mở https://example.com/Case?Token=AbC", "web_open", {"site": "https://example.com/Case?Token=AbC"}),
    ("mo thu muc", "folder_open", None),
    ("mo du an jarvis", "workspace_prepare", None),
])
def test_existing_specific_routes_precede_short_app_fallback(phrase, action, expected):
    result = LLMIntentRouter(llm_client=None).parse_intent(phrase)

    assert result.action_name == action
    for key, value in (expected or {}).items():
        assert result.parameters[key] == value
    assert "installed_only" not in result.parameters


@pytest.mark.parametrize("phrase, name", [
    ("mở ứng dụng Calculator", "Calculator"),
    ("mở Example Editor", "Example Editor"),
])
def test_llm_failure_uses_same_installed_app_routing(phrase, name):
    class UnavailableLLM:
        def generate(self, **kwargs):
            raise ConnectionError("offline")

    result = LLMIntentRouter(llm_client=UnavailableLLM()).parse_intent(phrase, force_llm=True)

    assert result.action_name == "app_open"
    assert result.parameters == {"app_name": name, "installed_only": True}
    assert result.confidence == 0.85


@pytest.mark.parametrize("force_llm", [False, True])
@pytest.mark.parametrize("action_name", ["app_open", "open_app"])
@pytest.mark.parametrize("phrase", [
    "tôi không muốn mở ứng dụng Calculator",
    "toi khong muon mo ung dung chrome",
    "đừng mở ứng dụng cài đặt",
    "don't open Notepad",
])
def test_successful_llm_cannot_override_negated_app_request(force_llm, action_name, phrase):
    llm = Mock()
    llm.generate.return_value = LLMResponse(tool_calls=[
        ToolCall(id="negated", name=action_name, arguments={"app_name": "Calculator"}),
    ])

    result = LLMIntentRouter(llm_client=llm).parse_intent(phrase, force_llm=force_llm)

    assert result.action_name == "unknown_intent"
    assert result.confidence == 0.0
    assert result.raw_text == phrase


@pytest.mark.parametrize("action_name", ["app_open", "open_app"])
@pytest.mark.parametrize("parameters", [
    {"app_name": "Calculator"},
    {"app_name": "Calculator", "installed_only": False},
    {"name": "Notepad"},
    {"app": "Chrome"},
])
def test_successful_llm_desktop_launch_requires_catalog(action_name, parameters):
    llm = Mock()
    llm.generate.return_value = LLMResponse(tool_calls=[
        ToolCall(id="affirmative", name=action_name, arguments=parameters),
    ])

    result = LLMIntentRouter(llm_client=llm).parse_intent("mở ứng dụng giúp tôi", force_llm=True)

    assert result.action_name == action_name
    assert result.parameters["installed_only"] is True
    assert result.parameters == {**parameters, "installed_only": True}


def test_llm_settings_target_retains_specialized_route():
    llm = Mock()
    llm.generate.return_value = LLMResponse(tool_calls=[
        ToolCall(id="settings", name="app_open", arguments={"app_name": "Settings", "app": "ms-settings:"}),
    ])

    result = LLMIntentRouter(llm_client=llm).parse_intent("mở cài đặt", force_llm=True)

    assert result.parameters == {"app_name": "Settings", "app": "ms-settings:"}


def test_app_negation_does_not_block_unrelated_llm_action():
    llm = Mock()
    llm.generate.return_value = LLMResponse(tool_calls=[
        ToolCall(id="reminder", name="reminder", arguments={"message": "nghỉ mắt", "delay_s": 60}),
    ])

    result = LLMIntentRouter(llm_client=llm).parse_intent(
        "tôi không muốn mở Calculator, hãy nhắc tôi nghỉ mắt sau một phút", force_llm=True,
    )

    assert result.action_name == "reminder"
    assert result.parameters == {"message": "nghỉ mắt", "delay_s": 60}
