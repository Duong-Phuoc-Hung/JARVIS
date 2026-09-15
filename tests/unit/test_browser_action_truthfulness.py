"""Fail-closed contracts for composite browser actions and workflows."""

from __future__ import annotations

from unittest.mock import MagicMock

from jarvis.browser.actions import (
    BrowserActionExecutor,
    _merge_download_response_cookies,
)
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.driver import HttpScrapingDriver, MockBrowserDriver
from jarvis.browser.models import BrowserConfig, BrowserDriverType, BrowserResultStatus
from jarvis.browser.scraper import WebScraper
from jarvis.browser.session import BrowserSessionManager


def _mock_agent(tmp_path) -> tuple[BrowserAgent, MockBrowserDriver]:
    config = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        session_storage_dir=str(tmp_path / "sessions"),
    )
    driver = MockBrowserDriver(config)
    sessions = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    return BrowserAgent(config=config, driver=driver, session_manager=sessions), driver


def test_read_page_after_close_reports_disconnected(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    driver.launch()
    driver.set_fixture_html(
        "<html><head><title>Stale</title></head><body>old data</body></html>",
        url="https://stale.invalid/",
        title="Stale",
    )
    driver.close()

    result = agent.actions.read_page()

    assert result.success is False
    assert result.status is BrowserResultStatus.DISCONNECTED
    assert result.error_code == "BROWSER_DISCONNECTED"
    assert result.extracted_data is None


def test_screenshot_action_captures_exactly_once(tmp_path) -> None:
    _agent, driver = _mock_agent(tmp_path)
    driver.launch()
    capture_count = 0
    original_capture = driver.capture_page_screenshot

    def capture_once(full_page: bool = False) -> bytes:
        nonlocal capture_count
        capture_count += 1
        return original_capture(full_page)

    driver.capture_page_screenshot = capture_once  # type: ignore[method-assign]

    result = BrowserActionExecutor(driver).take_screenshot()

    assert result.success is True
    assert result.screenshot_b64 is not None
    assert capture_count == 1


def test_partial_form_fill_is_not_success(tmp_path) -> None:
    _agent, driver = _mock_agent(tmp_path)
    driver.launch()
    original_type = driver.type_text

    def reject_missing(selector: str, text: str, **kwargs) -> bool:
        if "missing" in selector:
            return False
        return original_type(selector, text, **kwargs)

    driver.type_text = reject_missing  # type: ignore[method-assign]
    result = BrowserActionExecutor(driver).fill_and_submit_form(
        fields={"#present": "value", "#missing": "value"},
        submit_selector="#submit",
    )

    assert result.success is False
    assert result.error_code == "BROWSER_FORM_INCOMPLETE"
    assert result.metadata["filled_count"] == 1
    assert result.metadata["target_fields_count"] == 2


def test_failed_form_submission_is_not_success(tmp_path) -> None:
    _agent, driver = _mock_agent(tmp_path)
    driver.launch()
    driver.click = lambda selector, timeout_ms=5000: False  # type: ignore[method-assign]

    result = BrowserActionExecutor(driver).fill_and_submit_form(
        fields={"#name": "Ada"},
        submit_selector="#submit",
    )

    assert result.success is False
    assert result.error_code == "BROWSER_FORM_SUBMIT_FAILED"


def test_form_failure_preserves_disconnected_driver_status(tmp_path) -> None:
    _agent, driver = _mock_agent(tmp_path)
    driver.launch()
    driver.close()

    result = BrowserActionExecutor(driver).fill_and_submit_form(
        fields={"#name": "Ada"},
        submit_selector="#submit",
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.DISCONNECTED
    assert result.error_code == "BROWSER_DISCONNECTED"


def test_clicking_form_container_is_not_treated_as_submission(tmp_path) -> None:
    _agent, driver = _mock_agent(tmp_path)
    driver.launch()
    attempted_selectors: list[str] = []

    def click_only_form(selector: str, timeout_ms: int = 5000) -> bool:
        attempted_selectors.append(selector)
        return selector == "form"

    driver.click = click_only_form  # type: ignore[method-assign]

    result = BrowserActionExecutor(driver).fill_and_submit_form(fields={"#name": "Ada"})

    assert result.success is False
    assert result.error_code == "BROWSER_FORM_SUBMIT_FAILED"
    assert "form" not in attempted_selectors


def test_workflow_stops_when_wait_is_unsupported(tmp_path) -> None:
    config = BrowserConfig(
        driver_type=BrowserDriverType.HTTP_SCRAPER,
        session_storage_dir=str(tmp_path / "sessions"),
    )
    driver = HttpScrapingDriver(config)
    sessions = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    agent = BrowserAgent(config=config, driver=driver, session_manager=sessions)
    try:
        assert agent.start() is True
        result = agent.execute_workflow(
            [{"action": "wait", "selector": "#never", "timeout_ms": 10}]
        )
    finally:
        agent.stop()

    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.error_code == "BROWSER_CAPABILITY_UNAVAILABLE"
    assert result.metadata["executed_steps"][-1]["success"] is False


def test_unknown_workflow_action_fails_closed(tmp_path) -> None:
    agent, _driver = _mock_agent(tmp_path)
    try:
        result = agent.execute_workflow([{"action": "invented-action"}])
    finally:
        agent.stop()

    assert result.success is False
    assert result.error_code == "BROWSER_UNKNOWN_ACTION"


def test_failed_workflow_redacts_prior_scrape_and_eval_payloads(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    driver.set_fixture_html(
        "<html><head><title>TOP_SECRET_TITLE</title></head><body>private</body></html>",
        url="https://example.test/private?token=hidden",
        title="TOP_SECRET_TITLE",
    )
    driver.script_eval_results["window.secret"] = "TOP_SECRET_EVAL"

    try:
        result = agent.execute_workflow(
            [
                {"action": "scrape"},
                {"action": "eval", "script": "window.secret"},
                {"action": "invented-action"},
            ]
        )
    finally:
        agent.stop()

    assert result.success is False
    assert result.error_code == "BROWSER_UNKNOWN_ACTION"
    assert "TOP_SECRET_TITLE" not in repr(result.metadata)
    assert "TOP_SECRET_EVAL" not in repr(result.metadata)
    assert all(
        set(step) <= {"step_index", "action", "success", "error_code"}
        for step in result.metadata["executed_steps"]
    )


def test_empty_workflow_fails_closed(tmp_path) -> None:
    agent, _driver = _mock_agent(tmp_path)
    try:
        result = agent.execute_workflow([])
    finally:
        agent.stop()

    assert result.success is False
    assert result.status is BrowserResultStatus.ERROR
    assert result.error_code == "BROWSER_WORKFLOW_EMPTY"


def test_scroll_rejects_non_integer_distance_before_driver_execution(tmp_path) -> None:
    _agent, driver = _mock_agent(tmp_path)
    driver.launch()
    injected_distance = "0); window.__injected = true; window.scrollBy(0, 1"

    result = BrowserActionExecutor(driver).scroll_page(
        "down",
        injected_distance,  # type: ignore[arg-type]
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.ERROR
    assert result.error_code == "BROWSER_INVALID_SCROLL_DISTANCE"
    assert not any(entry.get("action") == "scroll" for entry in driver.action_log)


def test_search_does_not_return_stale_page_after_navigation_failure(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    driver.launch()
    driver.set_fixture_html(
        "<html><head><title>Old Result</title></head><body>stale result</body></html>",
        url="https://old.invalid/",
        title="Old Result",
    )

    def fail_navigation(url: str, wait_until: str = "domcontentloaded") -> bool:
        driver._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_NAVIGATION_UNAVAILABLE",
            "Browser navigation is unavailable.",
        )
        return False

    driver.navigate = fail_navigation  # type: ignore[method-assign]
    try:
        result = agent.open_and_search("new result")
    finally:
        agent.stop()

    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.title == ""
    assert "stale result" not in result.text_content


def test_price_comparison_skips_stale_page_after_navigation_failure(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    driver.launch()
    driver.set_fixture_html(
        '<div class="title">Old Product</div><div class="price">$99.00</div>',
        url="https://old.invalid/",
        title="Old Product",
    )

    def fail_navigation(url: str, wait_until: str = "domcontentloaded") -> bool:
        driver._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_NAVIGATION_UNAVAILABLE",
            "Browser navigation is unavailable.",
        )
        return False

    driver.navigate = fail_navigation  # type: ignore[method-assign]
    try:
        offers = agent.compare_prices("new product", stores=["TestStore"])
    finally:
        agent.stop()

    assert offers == []


def test_saved_local_storage_is_applied_only_after_navigation(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    assert (
        agent.session_manager.save_session(
            "https://example.test/private",
            [{"name": "sid", "value": "stored", "domain": "example.test"}],
            local_storage={"theme": "dark"},
        )
        is True
    )

    try:
        result = agent.navigate("https://example.test/private")
    finally:
        agent.stop()

    assert result.success is True
    action_names = [entry["action"] for entry in driver.action_log]
    cookie_index = action_names.index("set_cookies")
    navigate_index = action_names.index("navigate")
    storage_index = next(
        index
        for index, entry in enumerate(driver.action_log)
        if entry.get("action") == "evaluate_script"
        and "localStorage.setItem" in entry.get("script", "")
    )
    assert cookie_index < navigate_index < storage_index


def test_unknown_origin_legacy_local_storage_does_not_break_cookie_navigation(
    tmp_path,
) -> None:
    agent, driver = _mock_agent(tmp_path)
    cookie = {
        "name": "legacy-cookie",
        "value": "still-compatible",
        "domain": "example.test",
        "path": "/",
    }
    assert (
        agent.session_manager.save_session(
            "example.test",
            [cookie],
            local_storage={"legacy-secret": "origin-unknown"},
            local_storage_origin="",
        )
        is True
    )

    try:
        result = agent.navigate("https://example.test/private")
        observed_cookies = driver.get_cookies()
    finally:
        agent.stop()

    assert result.success is True
    assert observed_cookies == [cookie]
    assert not any(
        entry.get("action") == "evaluate_script"
        and "localStorage.setItem" in entry.get("script", "")
        for entry in driver.action_log
    )


def test_failed_direct_scrape_redacts_url_and_all_page_evidence(tmp_path) -> None:
    secret = "direct-scrape-secret"
    target = f"https://user:{secret}@example.test/blank?token={secret}#private"
    agent, driver = _mock_agent(tmp_path)
    driver.set_fixture_html("<html></html>", url=target, title="")

    try:
        result = agent.scrape_url(target)
    finally:
        agent.stop()

    assert result.success is False
    assert result.url == "https://example.test"
    assert result.title == ""
    assert result.markdown_content == ""
    assert result.text_content == ""
    assert result.structured_data == {}
    assert result.links == []
    assert result.images == []
    assert result.tables == []
    assert result.metadata == {}
    assert secret not in repr(result)


def test_saved_local_storage_is_not_injected_after_cross_origin_redirect(
    tmp_path,
) -> None:
    agent, driver = _mock_agent(tmp_path)
    assert (
        agent.session_manager.save_session(
            "example.test",
            [],
            local_storage={"private-token": "must-stay-on-original-origin"},
        )
        is True
    )

    def cross_origin_redirect(url: str, wait_until: str = "domcontentloaded") -> bool:
        driver._current_url = "http://example.test:8080/final"
        driver._title = "Redirect complete"
        driver.action_log.append({"action": "navigate", "url": url})
        driver._record_success()
        return True

    driver.navigate = cross_origin_redirect  # type: ignore[method-assign]
    try:
        result = agent.navigate("https://example.test/private")
    finally:
        agent.stop()

    assert result.success is True
    assert not any(
        entry.get("action") == "evaluate_script"
        and "localStorage.setItem" in entry.get("script", "")
        for entry in driver.action_log
    )


def test_saved_local_storage_applies_when_redirect_reaches_its_exact_origin(
    tmp_path,
) -> None:
    agent, driver = _mock_agent(tmp_path)
    assert (
        agent.session_manager.save_session(
            "https://example.test/private",
            [],
            local_storage={"private-token": "exact-origin-value"},
        )
        is True
    )
    driver.script_eval_results["JSON.stringify(window.localStorage);"] = (
        '{"private-token":"exact-origin-value"}'
    )

    def upgrade_redirect(url: str, wait_until: str = "domcontentloaded") -> bool:
        driver._current_url = "https://example.test/final"
        driver._title = "Redirect complete"
        driver._record_success()
        return True

    driver.navigate = upgrade_redirect  # type: ignore[method-assign]
    try:
        result = agent.navigate("http://example.test/start")
    finally:
        agent.stop()

    assert result.success is True
    assert result.metadata["local_storage_applied"] is True
    assert any(
        entry.get("action") == "evaluate_script"
        and "localStorage.setItem" in entry.get("script", "")
        for entry in driver.action_log
    )


def test_local_storage_restore_reloads_page_before_reporting_applied(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    assert (
        agent.session_manager.save_session(
            "https://example.test/private",
            [],
            local_storage={"token": "authenticated"},
        )
        is True
    )
    driver.script_eval_results["JSON.stringify(window.localStorage);"] = '{"token":"authenticated"}'
    navigation_count = 0

    def render_on_navigation(url: str, wait_until: str = "domcontentloaded") -> bool:
        nonlocal navigation_count
        navigation_count += 1
        driver._current_url = "https://example.test/private"
        driver._title = "unauthenticated" if navigation_count == 1 else "authenticated"
        driver._record_success()
        return True

    driver.navigate = render_on_navigation  # type: ignore[method-assign]
    try:
        result = agent.navigate("https://example.test/private")
    finally:
        agent.stop()

    assert navigation_count == 2
    assert result.success is True
    assert result.title == "authenticated"
    assert result.metadata["local_storage_applied"] is True


def test_local_storage_restore_retries_original_target_after_login_redirect(
    tmp_path,
) -> None:
    agent, driver = _mock_agent(tmp_path)
    private_url = "https://example.test/private"
    assert (
        agent.session_manager.save_session(
            private_url,
            [],
            local_storage={"token": "authenticated"},
        )
        is True
    )
    driver.script_eval_results["JSON.stringify(window.localStorage);"] = '{"token":"authenticated"}'
    navigated: list[str] = []

    def login_then_private(url: str, wait_until: str = "domcontentloaded") -> bool:
        navigated.append(url)
        if len(navigated) == 1:
            driver._current_url = "https://example.test/login"
            driver._title = "Login"
        elif url == private_url:
            driver._current_url = private_url
            driver._title = "Authenticated private page"
        else:
            driver._current_url = url
            driver._title = "Login"
        driver._record_success()
        return True

    driver.navigate = login_then_private  # type: ignore[method-assign]
    try:
        result = agent.navigate(private_url)
    finally:
        agent.stop()

    assert navigated == [private_url, private_url]
    assert result.success is True
    assert result.url == private_url
    assert result.title == "Authenticated private page"
    assert result.metadata["local_storage_applied"] is True


def test_capture_on_different_origin_preserves_saved_local_storage(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    assert (
        agent.session_manager.save_session(
            "https://example.test/private",
            [],
            local_storage={"private-token": "preserve-this-origin"},
        )
        is True
    )

    try:
        result = agent.navigate("http://example.test/other-origin")
        stored = agent.session_manager.load_session("https://example.test/private")
    finally:
        agent.stop()

    assert result.success is True
    assert result.metadata["local_storage_applied"] is False
    assert result.metadata["session_captured"] is False
    assert stored is not None
    assert stored["local_storage"] == {
        "private-token": "preserve-this-origin",
    }
    assert stored["local_storage_origin"] == "https://example.test:443"


def test_post_navigation_session_failure_redacts_url_and_title(tmp_path) -> None:
    secret = "private-session-value"
    agent, driver = _mock_agent(tmp_path)
    assert (
        agent.session_manager.save_session(
            "example.test",
            [],
            local_storage={"token": "stored-value"},
            local_storage_origin="https://example.test",
        )
        is True
    )

    def observed_navigation(url: str, wait_until: str = "domcontentloaded") -> bool:
        driver._current_url = f"https://example.test/private?token={secret}"
        driver._title = f"Private account {secret}"
        driver._record_success()
        return True

    apply_count = 0

    def fail_second_apply(*args, **kwargs) -> bool:
        nonlocal apply_count
        apply_count += 1
        if apply_count == 1:
            return True
        driver._record_failure(
            BrowserResultStatus.ERROR,
            "BROWSER_SESSION_APPLY_FAILED",
            "The saved browser session could not be applied.",
        )
        return False

    driver.navigate = observed_navigation  # type: ignore[method-assign]
    agent.session_manager.apply_to_driver = fail_second_apply  # type: ignore[method-assign]
    try:
        result = agent.navigate(f"https://example.test/private?token={secret}")
    finally:
        agent.stop()

    assert result.success is False
    assert result.url == "https://example.test"
    assert result.title == ""
    assert secret not in repr(result)


def test_scrape_start_failure_preserves_not_configured_status(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)

    def fail_launch(config=None) -> bool:
        driver._record_failure(
            BrowserResultStatus.NOT_CONFIGURED,
            "BROWSER_PLAYWRIGHT_NOT_CONFIGURED",
            "The browser runtime is not configured.",
        )
        return False

    driver.launch = fail_launch  # type: ignore[method-assign]
    result = agent.scrape_url("https://example.test/private")

    assert result.success is False
    assert result.status is BrowserResultStatus.NOT_CONFIGURED
    assert result.error_code == "BROWSER_PLAYWRIGHT_NOT_CONFIGURED"
    assert result.driver_type is BrowserDriverType.MOCK


def test_scrape_reports_observed_final_url_after_redirect(tmp_path) -> None:
    agent, driver = _mock_agent(tmp_path)
    final_url = "https://example.test/final"

    def redirect_navigation(url: str, wait_until: str = "domcontentloaded") -> bool:
        driver.navigation_history.append(url)
        driver._current_url = final_url
        driver._title = "Redirect complete"
        driver.html_content = (
            "<html><head><title>Redirect complete</title></head>"
            "<body><main>Observed final document</main></body></html>"
        )
        driver.action_log.append({"action": "navigate", "url": url})
        driver._record_success()
        return True

    driver.navigate = redirect_navigation  # type: ignore[method-assign]
    try:
        result = agent.scrape_url("https://example.test/redirect")
    finally:
        agent.stop()

    assert result.success is True
    assert result.url == final_url
    assert "Observed final document" in result.text_content


def test_malformed_scrape_cannot_contaminate_the_next_conversion() -> None:
    scraper = WebScraper()
    first = scraper.scrape_html(
        "<html><head><title>Malformed</title></head><body><nav>never closed",
        url="https://first.example/",
    )
    second = scraper.scrape_html(
        "<html><head><title>Clean</title></head>"
        "<body><h1>Clean Page</h1><p>Visible second scrape</p></body></html>",
        url="https://second.example/",
    )

    assert first.title == "Malformed"
    assert second.success is True
    assert "Clean Page" in second.markdown_content
    assert "Visible second scrape" in second.markdown_content
    assert "never closed" not in second.markdown_content


def test_download_does_not_forward_unrelated_browser_cookies(
    tmp_path,
    monkeypatch,
) -> None:
    config = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        downloads_dir=str(tmp_path),
    )
    driver = MockBrowserDriver(config)
    assert driver.launch() is True
    driver.cookies = [
        {"name": "host", "value": "allowed", "domain": "files.example.test", "path": "/"},
        {"name": "parent", "value": "allowed", "domain": ".example.test", "path": "/"},
        {
            "name": "host-only-parent",
            "value": "secret",
            "domain": "example.test",
            "path": "/",
        },
        {"name": "wrong-host", "value": "secret", "domain": "attacker.test", "path": "/"},
        {"name": "child", "value": "secret", "domain": "deep.files.example.test", "path": "/"},
        {
            "name": "wrong-path",
            "value": "secret",
            "domain": "files.example.test",
            "path": "/private",
        },
        {
            "name": "wrong-path-boundary",
            "value": "secret",
            "domain": "files.example.test",
            "path": "/public/report",
        },
    ]
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-length": "4"}
    response.iter_content.return_value = [b"data"]
    response.__enter__.return_value = response
    get_request = MagicMock(return_value=response)
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/public/report.bin",
    )

    assert result.success is True
    assert get_request.call_args.kwargs["headers"]["Cookie"] == ("host=allowed; parent=allowed")
    assert "cookies" not in get_request.call_args.kwargs


def test_download_revalidates_cookies_for_each_redirect_target(
    tmp_path,
    monkeypatch,
) -> None:
    config = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        downloads_dir=str(tmp_path),
    )
    driver = MockBrowserDriver(config)
    assert driver.launch() is True
    driver.cookies = [
        {
            "name": "session",
            "value": "must-not-cross-origin",
            "domain": "files.example.test",
            "path": "/",
        }
    ]

    redirect_response = MagicMock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "https://cdn.other.test/report.bin"}
    redirect_response.__enter__.return_value = redirect_response

    final_response = MagicMock()
    final_response.status_code = 200
    final_response.headers = {"content-length": "4"}
    final_response.iter_content.return_value = [b"data"]
    final_response.__enter__.return_value = final_response

    get_request = MagicMock(side_effect=[redirect_response, final_response])
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/start",
    )

    assert result.success is True
    assert get_request.call_count == 2
    first_call, second_call = get_request.call_args_list
    assert first_call.kwargs["allow_redirects"] is False
    assert first_call.kwargs["headers"]["Cookie"] == "session=must-not-cross-origin"
    assert "cookies" not in first_call.kwargs
    assert second_call.args[0] == "https://cdn.other.test/report.bin"
    assert second_call.kwargs["allow_redirects"] is False
    assert "Cookie" not in second_call.kwargs["headers"]
    assert "cookies" not in second_call.kwargs


def test_download_redirect_applies_newly_scoped_response_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    config = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        downloads_dir=str(tmp_path),
    )
    driver = MockBrowserDriver(config)
    assert driver.launch() is True

    nonce = MagicMock()
    nonce.name = "nonce"
    nonce.value = "redirect-proof"
    nonce.domain = "files.example.test"
    nonce.domain_specified = False
    nonce.path = "/final"
    nonce.secure = True
    nonce.expires = None
    nonce._rest = {"HttpOnly": None, "SameSite": "Strict"}

    redirect_response = MagicMock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "https://files.example.test/final/report.bin"}
    redirect_response.cookies = [nonce]
    redirect_response.__enter__.return_value = redirect_response

    final_response = MagicMock()
    final_response.status_code = 200
    final_response.headers = {"content-length": "4"}
    final_response.cookies = []
    final_response.iter_content.return_value = [b"data"]
    final_response.__enter__.return_value = final_response

    get_request = MagicMock(side_effect=[redirect_response, final_response])
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/start",
    )

    assert result.success is True
    assert get_request.call_count == 2
    assert "Cookie" not in get_request.call_args_list[0].kwargs["headers"]
    assert get_request.call_args_list[1].kwargs["headers"]["Cookie"] == ("nonce=redirect-proof")


def test_download_redirect_canonicalizes_url_before_cookie_policy(
    tmp_path,
    monkeypatch,
) -> None:
    config = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        downloads_dir=str(tmp_path),
    )
    driver = MockBrowserDriver(config)
    assert driver.launch() is True
    driver.cookies = [
        {
            "name": "sid",
            "value": "cookie-secret",
            "domain": "localhost",
            "path": "/",
        }
    ]

    redirect_response = MagicMock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "http://127.0.0.1:20000\\@localhost:10000/final.bin"}
    redirect_response.cookies = []

    final_response = MagicMock()
    final_response.status_code = 200
    final_response.headers = {"content-length": "4"}
    final_response.cookies = []
    final_response.iter_content.return_value = [b"data"]
    final_response.__enter__.return_value = final_response

    get_request = MagicMock(side_effect=[redirect_response, final_response])
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "http://localhost:10000/start",
    )

    assert result.success is True
    second_call = get_request.call_args_list[1]
    assert second_call.args[0] == ("http://127.0.0.1:20000/%5C@localhost:10000/final.bin")
    assert "Cookie" not in second_call.kwargs["headers"]


def test_download_redirect_drops_partitioned_response_cookie_without_context(
    tmp_path,
    monkeypatch,
) -> None:
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    chip = MagicMock()
    chip.name = "chip"
    chip.value = "partition-secret"
    chip.domain = "files.example.test"
    chip.domain_specified = False
    chip.path = "/"
    chip.secure = True
    chip.expires = None
    chip._rest = {"Partitioned": None}

    redirect_response = MagicMock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "https://files.example.test/final.bin"}
    redirect_response.cookies = [chip]
    final_response = MagicMock()
    final_response.status_code = 200
    final_response.headers = {"content-length": "4"}
    final_response.cookies = []
    final_response.iter_content.return_value = [b"data"]
    final_response.__enter__.return_value = final_response
    get_request = MagicMock(side_effect=[redirect_response, final_response])
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/start",
    )

    assert result.success is True
    assert "Cookie" not in get_request.call_args_list[1].kwargs["headers"]


def test_download_cookie_max_age_precedes_expired_expires(
    tmp_path,
    monkeypatch,
) -> None:
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    driver.cookies = [
        {
            "name": "sid",
            "value": "still-valid",
            "domain": "files.example.test",
            "path": "/",
        }
    ]
    redirect_response = MagicMock()
    redirect_response.status_code = 302
    redirect_response.headers = {
        "location": "https://files.example.test/final.bin",
        "set-cookie": (
            "sid=still-valid; Max-Age=3600; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/"
        ),
    }
    redirect_response.cookies = []
    final_response = MagicMock()
    final_response.status_code = 200
    final_response.headers = {"content-length": "4"}
    final_response.cookies = []
    final_response.iter_content.return_value = [b"data"]
    final_response.__enter__.return_value = final_response
    get_request = MagicMock(side_effect=[redirect_response, final_response])
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/start",
    )

    assert result.success is True
    assert get_request.call_args_list[1].kwargs["headers"]["Cookie"] == "sid=still-valid"


def test_download_redirect_withholds_strict_cookie_from_cross_site_chain(
    tmp_path,
    monkeypatch,
) -> None:
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    driver.cookies = [
        {
            "name": "bank-session",
            "value": "must-not-cross-site",
            "domain": "bank.test",
            "path": "/",
            "secure": True,
            "sameSite": "Strict",
        }
    ]
    redirect_response = MagicMock()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "https://bank.test/report.bin"}
    redirect_response.cookies = []
    final_response = MagicMock()
    final_response.status_code = 200
    final_response.headers = {"content-length": "4"}
    final_response.cookies = []
    final_response.iter_content.return_value = [b"data"]
    final_response.__enter__.return_value = final_response
    get_request = MagicMock(side_effect=[redirect_response, final_response])
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://evil.test/start",
    )

    assert result.success is True
    assert "Cookie" not in get_request.call_args_list[1].kwargs["headers"]


def test_download_cookie_deletion_updates_driver_store(
    tmp_path,
    monkeypatch,
) -> None:
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    driver.cookies = [
        {
            "name": "sid",
            "value": "logged-in",
            "domain": "files.example.test",
            "path": "/",
        }
    ]
    response = MagicMock()
    response.status_code = 200
    response.headers = {
        "content-length": "4",
        "set-cookie": "sid=; Max-Age=0; Path=/",
    }
    response.cookies = []
    response.iter_content.return_value = [b"data"]
    response.__enter__.return_value = response
    monkeypatch.setattr("requests.get", MagicMock(return_value=response))

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/logout.bin",
    )

    assert result.success is True
    assert driver.get_cookies() == []


def test_download_cookie_sync_preserves_concurrent_browser_cookie(
    tmp_path,
    monkeypatch,
) -> None:
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    driver.cookies = [
        {
            "name": "sid",
            "value": "initial-session",
            "domain": "files.example.test",
            "path": "/",
        }
    ]

    nonce = MagicMock()
    nonce.name = "nonce"
    nonce.value = "download-response"
    nonce.domain = "files.example.test"
    nonce.domain_specified = False
    nonce.path = "/"
    nonce.secure = True
    nonce.expires = None
    nonce._rest = {"HttpOnly": None, "SameSite": "Lax"}

    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-length": "4"}
    response.cookies = [nonce]
    response.iter_content.return_value = [b"data"]
    response.__enter__.return_value = response

    def request_with_concurrent_cookie(*args, **kwargs):
        driver.cookies.append(
            {
                "name": "live-tab",
                "value": "must-survive-download-sync",
                "domain": "files.example.test",
                "path": "/",
            }
        )
        return response

    monkeypatch.setattr("requests.get", request_with_concurrent_cookie)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/report.bin",
    )

    assert result.success is True
    assert {(cookie["name"], cookie["value"]) for cookie in driver.get_cookies()} == {
        ("sid", "initial-session"),
        ("live-tab", "must-survive-download-sync"),
        ("nonce", "download-response"),
    }


def test_download_set_cookie_extensions_cannot_fabricate_cookies(
    tmp_path,
    monkeypatch,
) -> None:
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    accepted = MagicMock()
    accepted.name = "sid"
    accepted.value = "accepted-session"
    accepted.domain = "files.example.test"
    accepted.domain_specified = False
    accepted.path = "/secure"
    accepted.secure = True
    accepted.expires = None
    accepted._rest = {"HttpOnly": None, "SameSite": "Lax"}

    raw_headers = MagicMock()
    raw_headers.getlist.return_value = [
        "sid=accepted-session; Path=/secure; Secure; HttpOnly; "
        "SameSite=Lax; Priority=High; SameParty"
    ]
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-length": "4"}
    response.raw.headers = raw_headers
    response.cookies = [accepted]
    response.iter_content.return_value = [b"data"]
    response.__enter__.return_value = response
    monkeypatch.setattr("requests.get", MagicMock(return_value=response))

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/secure/report.bin",
    )

    assert result.success is True
    assert driver.get_cookies() == [
        {
            "name": "sid",
            "value": "accepted-session",
            "domain": "files.example.test",
            "path": "/secure",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    ]


def test_download_ordered_delete_then_set_cookie_keeps_last_value() -> None:
    cookies = [
        {
            "name": "sid",
            "value": "old",
            "domain": "files.example.test",
            "path": "/",
        }
    ]
    accepted = MagicMock()
    accepted.name = "sid"
    accepted.value = "new"
    accepted.domain = "files.example.test"
    accepted.domain_specified = False
    accepted.path = "/"
    accepted.secure = True
    accepted.expires = None
    accepted._rest = {}
    raw_headers = MagicMock()
    raw_headers.getlist.return_value = [
        "sid=; Max-Age=0; Path=/; Secure",
        "sid=new; Path=/; Secure",
    ]
    response = MagicMock()
    response.raw.headers = raw_headers
    response.headers = {}
    response.cookies = [accepted]

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "https://files.example.test/start",
    )

    assert deletions == []
    assert [(cookie["name"], cookie["value"]) for cookie in upserts] == [("sid", "new")]
    assert [(cookie["name"], cookie["value"]) for cookie in cookies] == [("sid", "new")]


def test_download_unpartitioned_cookie_does_not_replace_partitioned_peer() -> None:
    cookies = [
        {
            "name": "sid",
            "value": "partitioned-session",
            "domain": "files.example.test",
            "path": "/",
            "secure": True,
            "partitionKey": "https://top-level.test",
        }
    ]
    accepted = MagicMock()
    accepted.name = "sid"
    accepted.value = "unpartitioned-session"
    accepted.domain = "files.example.test"
    accepted.domain_specified = False
    accepted.path = "/"
    accepted.secure = True
    accepted.expires = None
    accepted._rest = {}
    response = MagicMock()
    response.headers = {"set-cookie": "sid=unpartitioned-session; Path=/; Secure"}
    response.raw = None
    response.cookies = [accepted]

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "https://files.example.test/start",
    )

    assert deletions == []
    assert [cookie["value"] for cookie in upserts] == ["unpartitioned-session"]
    assert {cookie["value"] for cookie in cookies} == {
        "partitioned-session",
        "unpartitioned-session",
    }


def test_download_rejects_public_suffix_and_insecure_secure_cookie() -> None:
    def accepted_cookie(*, domain: str, secure: bool) -> MagicMock:
        cookie = MagicMock()
        cookie.name = "sid"
        cookie.value = "must-not-be-stored"
        cookie.domain = domain
        cookie.domain_specified = True
        cookie.path = "/"
        cookie.secure = secure
        cookie.expires = None
        cookie._rest = {}
        return cookie

    public_suffix_response = MagicMock()
    public_suffix_response.headers = {
        "set-cookie": "sid=must-not-be-stored; Domain=co.uk; Path=/; Secure"
    }
    public_suffix_response.cookies = [accepted_cookie(domain=".co.uk", secure=True)]
    insecure_response = MagicMock()
    insecure_response.headers = {"set-cookie": "sid=must-not-be-stored; Path=/; Secure"}
    insecure_response.cookies = [accepted_cookie(domain="shop.example.test", secure=True)]

    public_cookies: list[dict[str, object]] = []
    insecure_cookies: list[dict[str, object]] = []
    public_upserts, _ = _merge_download_response_cookies(
        public_cookies,
        public_suffix_response,
        "https://shop.example.co.uk/file",
    )
    insecure_upserts, _ = _merge_download_response_cookies(
        insecure_cookies,
        insecure_response,
        "http://shop.example.test/file",
    )

    assert public_upserts == []
    assert public_cookies == []
    assert insecure_upserts == []
    assert insecure_cookies == []


def test_failed_download_progress_redacts_url_credentials(
    tmp_path,
    monkeypatch,
) -> None:
    secret = "private-download-token"
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    monkeypatch.setattr(
        "requests.get",
        MagicMock(side_effect=RuntimeError("synthetic failure")),
    )
    progress = []

    result = BrowserActionExecutor(driver).download_file(
        f"https://user:{secret}@example.test/file?token={secret}#fragment",
        on_progress=progress.append,
    )

    assert result.success is False
    assert progress[-1].status == "failed"
    assert progress[-1].url == "https://example.test"
    assert secret not in repr(progress[-1])


def test_download_fails_closed_when_browser_cookie_read_disconnects(
    tmp_path,
    monkeypatch,
) -> None:
    driver = MockBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True

    def disconnected_cookies() -> list[dict[str, object]]:
        driver._record_failure(
            BrowserResultStatus.DISCONNECTED,
            "BROWSER_DISCONNECTED",
            "The browser session is disconnected.",
        )
        return []

    driver.get_cookies = disconnected_cookies  # type: ignore[method-assign]
    get_request = MagicMock()
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/report.bin",
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.DISCONNECTED
    assert result.error_code == "BROWSER_DISCONNECTED"
    get_request.assert_not_called()


def test_http_download_after_driver_close_fails_closed(tmp_path, monkeypatch) -> None:
    driver = HttpScrapingDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.HTTP_SCRAPER,
            downloads_dir=str(tmp_path),
        )
    )
    assert driver.launch() is True
    assert driver.close() is True
    get_request = MagicMock()
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/report.bin",
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.DISCONNECTED
    assert result.error_code == "BROWSER_DISCONNECTED"
    get_request.assert_not_called()


def test_failed_action_and_workflow_do_not_expose_prior_page_title(tmp_path) -> None:
    secret_title = "Private account for secret@example.test"
    agent, driver = _mock_agent(tmp_path)
    driver.launch()
    driver.set_fixture_html(
        f"<html><head><title>{secret_title}</title></head><body>private</body></html>",
        url="https://example.test/private",
        title=secret_title,
    )

    def fail_click(selector: str, timeout_ms: int = 5000) -> bool:
        driver._record_failure(
            BrowserResultStatus.TIMEOUT,
            "BROWSER_TIMEOUT",
            "The browser action timed out.",
        )
        return False

    driver.click = fail_click  # type: ignore[method-assign]
    try:
        action = agent.actions.click_element("#missing")
        workflow = agent.execute_workflow([{"action": "unknown-action"}])
    finally:
        agent.stop()

    assert action.success is False
    assert action.title == ""
    assert workflow.success is False
    assert workflow.title == ""
    assert secret_title not in repr(action)
    assert secret_title not in repr(workflow)
