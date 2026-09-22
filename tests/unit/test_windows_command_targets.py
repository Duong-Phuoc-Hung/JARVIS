"""Windows launch contracts; OS boundaries mocked, not live runtime evidence."""
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from jarvis.automation.control import ComputerController
from jarvis.core.app import JarvisApp
from jarvis.core.runaway_guard import launch_dedupe_guard
from jarvis.llm.router import LLMIntentRouter


@pytest.fixture
def controller():
    launch_dedupe_guard.reset()
    yield ComputerController(win32=MagicMock())
    launch_dedupe_guard.reset()


@pytest.mark.parametrize("target", [
    "mở https://example.com/CaseSensitive?Token=AbC#Section",
    "example.com/CaseSensitive?Token=AbC#Section",
])
def test_url_preserves_exact_path_and_query(controller, monkeypatch, target):
    browser = MagicMock(return_value=True)
    monkeypatch.setattr("webbrowser.open", browser)
    result = controller.open_website(target)
    assert result["success"]
    browser.assert_called_once_with("https://example.com/CaseSensitive?Token=AbC#Section")


def test_bare_domain_with_port_preserves_target(controller, monkeypatch):
    browser = MagicMock(return_value=True)
    monkeypatch.setattr("webbrowser.open", browser)
    result = controller.open_website("example.com:8443/Case?Token=AbC")
    assert result["success"]
    browser.assert_called_once_with("https://example.com:8443/Case?Token=AbC")


@pytest.mark.parametrize("prefix,key", [("search ", "q"), ("youtube ", "search_query")])
def test_search_query_is_encoded_without_changing_text(controller, monkeypatch, prefix, key):
    browser = MagicMock(return_value=True)
    monkeypatch.setattr("webbrowser.open", browser)
    result = controller.open_website(prefix + "C++ & Tiếng Việt")
    assert parse_qs(urlsplit(result["url"]).query)[key] == ["C++ & Tiếng Việt"]


def test_browser_refusal_is_not_success(controller, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda url: False)
    result = controller.open_website("github")
    assert result["success"] is False
    assert result["error_code"] == "BROWSER_OPEN_FAILED"


def test_browser_exception_does_not_fall_back_to_shell(controller, monkeypatch):
    monkeypatch.setattr("webbrowser.open", MagicMock(side_effect=OSError("unavailable")))
    process = MagicMock()
    startfile = MagicMock()
    monkeypatch.setattr("subprocess.Popen", process)
    monkeypatch.setattr("os.startfile", startfile, raising=False)
    assert controller.open_website("github")["success"] is False
    process.assert_not_called()
    startfile.assert_not_called()


def test_unknown_app_does_not_launch_a_substring_match(controller, monkeypatch):
    requested = []
    def which(name):
        requested.append(name)
        return None
    monkeypatch.setattr("shutil.which", which)
    monkeypatch.setattr("os.path.exists", lambda path: False)
    monkeypatch.setattr("os.path.isdir", lambda path: False)
    result = controller.open_app("notepad_missing")
    assert result["success"] is False
    assert "notepad.exe" not in requested


@pytest.mark.parametrize("target", ["javascript:alert(1)", "file:///C:/secret", "https://", "https://user:password@example.com"])
def test_invalid_url_never_reaches_browser(controller, monkeypatch, target):
    browser = MagicMock()
    monkeypatch.setattr("webbrowser.open", browser)
    assert controller.open_website(target)["success"] is False
    browser.assert_not_called()


@pytest.mark.parametrize("method,target", [("_handle_app_open", {"app_name": "missing"}), ("_handle_web_open", {"target": "github"})])
def test_handler_preserves_failure_without_success_message(method, target):
    app = object.__new__(JarvisApp)
    app.computer_controller = MagicMock()
    failure = {"success": False, "error": "Cannot launch", "error_code": "LAUNCH_FAILED"}
    app.computer_controller.open_app.return_value = failure
    app.computer_controller.open_installed_app.return_value = failure
    app.computer_controller.open_website.return_value = failure
    result = getattr(app, method)(**target)
    assert result["message"] == "Cannot launch"
    assert result["error_code"] == "LAUNCH_FAILED"


@pytest.mark.parametrize("command,expected", [
    ("mở https://example.com/Case?Token=AbC", "https://example.com/Case?Token=AbC"),
    ("tìm kiếm C++ & Tiếng Việt", None),
    ("google C++ & Tiếng Việt", None),
])
def test_command_to_handler_keeps_exact_target(controller, monkeypatch, command, expected):
    browser = MagicMock(return_value=True)
    monkeypatch.setattr("webbrowser.open", browser)
    router = LLMIntentRouter(llm_client=None, dispatcher=None, fast_path_enabled=True)
    intent = router.parse_intent(command)
    assert intent.action_name == "web_open"
    app = object.__new__(JarvisApp)
    app.computer_controller = controller
    result = app._handle_web_open(**intent.parameters)
    assert result["status"] == "success"
    actual = browser.call_args.args[0]
    if expected:
        assert actual == expected
    else:
        assert parse_qs(urlsplit(actual).query)["q"] == ["C++ & Tiếng Việt"]
