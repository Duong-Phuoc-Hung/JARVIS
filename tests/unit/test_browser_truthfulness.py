"""Truthfulness contracts for the canonical browser result models."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from jarvis.browser.actions import BrowserActionExecutor, BrowserActions
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.driver import (
    CDPBrowserDriver,
    DriverFactory,
    HttpScrapingDriver,
    MockBrowserDriver,
    PlaywrightBrowserDriver,
)
from jarvis.browser.models import (
    BrowserActionResult,
    BrowserConfig,
    BrowserDriverType,
    BrowserResultStatus,
    ScrapeResult,
)
from jarvis.browser.session import BrowserSessionManager
from tests.browser_test_site import LocalBrowserTestSite


def test_empty_scrape_result_fails_closed() -> None:
    result = ScrapeResult(
        url="http://127.0.0.1:1/unreachable",
        title="Error",
        markdown_content="",
        text_content="",
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.ERROR
    assert result.error_code == "BROWSER_EMPTY_DOCUMENT"
    assert result.error


def test_explicit_success_cannot_override_missing_scrape_evidence() -> None:
    result = ScrapeResult(
        url="https://example.test/error",
        title="Error",
        markdown_content="",
        text_content="",
        status=BrowserResultStatus.SUCCESS,
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.ERROR
    assert result.error_code == "BROWSER_EMPTY_DOCUMENT"


def test_action_failure_status_cannot_report_success() -> None:
    result = BrowserActionResult(
        success=True,
        action="navigate",
        status=BrowserResultStatus.TIMEOUT,
        error_code="BROWSER_TIMEOUT",
        error_message="The browser action timed out.",
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.TIMEOUT
    assert result.error_code == "BROWSER_TIMEOUT"


def test_explicit_failure_cannot_be_overridden_by_success_status() -> None:
    result = BrowserActionResult(
        success=False,
        action="navigate",
        status=BrowserResultStatus.SUCCESS,
    )

    assert result.success is False
    assert result.status is BrowserResultStatus.ERROR
    assert result.error_code == "BROWSER_ERROR"


def test_successful_result_cannot_keep_stale_error_fields() -> None:
    action = BrowserActionResult(
        success=True,
        action="navigate",
        status=BrowserResultStatus.SUCCESS,
        error_code="SECRET_ERROR",
        error_message="stale secret diagnostic",
    )
    scrape = ScrapeResult(
        url="https://example.test/",
        title="Observed page",
        markdown_content="Observed content",
        text_content="Observed content",
        status=BrowserResultStatus.SUCCESS,
        error_code="SECRET_ERROR",
        error_message="stale secret diagnostic",
    )

    assert action.error_code is None
    assert action.error_message is None
    assert scrape.error_code is None
    assert scrape.error_message is None


def test_custom_session_storage_dirs_do_not_share_sqlite_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "global-app-data"))
    config_a = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        session_storage_dir=str(tmp_path / "profile-a"),
    )
    config_b = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        session_storage_dir=str(tmp_path / "profile-b"),
    )
    agent_a = BrowserAgent(config=config_a, driver=MockBrowserDriver(config_a))
    agent_b = BrowserAgent(config=config_b, driver=MockBrowserDriver(config_b))
    cookie = {
        "name": "profile-secret",
        "value": "must-not-cross-profile-boundary",
        "domain": "example.test",
        "path": "/",
    }

    assert (
        agent_a.session_manager.save_session(
            "https://example.test/private",
            [cookie],
        )
        is True
    )

    assert agent_b.session_manager.load_session("https://example.test/private") is None
    assert Path(str(agent_a.session_manager.db_path)).parent == tmp_path / "profile-a"
    assert Path(str(agent_b.session_manager.db_path)).parent == tmp_path / "profile-b"


def test_http_fallback_reports_actual_driver_and_rejects_click() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    try:
        result = BrowserActions(driver).click_element("#submit")
    finally:
        driver.close()

    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.error_code == "BROWSER_CAPABILITY_UNAVAILABLE"
    assert result.driver_type is BrowserDriverType.HTTP_SCRAPER


def test_http_session_capture_does_not_poison_followup_page_read(tmp_path) -> None:
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
        with LocalBrowserTestSite() as site:
            navigation = agent.navigate(f"{site.base_url}/")
            page = agent.actions.read_page()
    finally:
        agent.stop()

    assert navigation.success is True
    assert navigation.metadata["session_captured"] is True
    assert page.success is True
    assert page.status is BrowserResultStatus.SUCCESS
    assert "Deterministic Browser Page" in page.extracted_data["text"]


def test_http_fallback_preserves_saved_local_storage_without_applying_it(tmp_path) -> None:
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
        with LocalBrowserTestSite() as site:
            assert (
                sessions.save_session(
                    site.base_url,
                    cookies=[],
                    local_storage={"opaque-state": "preserve-for-real-browser"},
                )
                is True
            )
            navigation = agent.navigate(f"{site.base_url}/")
            stored = sessions.load_session(site.base_url)
    finally:
        agent.stop()

    assert navigation.success is True
    assert navigation.metadata["local_storage_applied"] is False
    assert stored is not None
    assert stored["local_storage"] == {
        "opaque-state": "preserve-for-real-browser",
    }


def test_http_session_apply_fails_closed_for_requested_local_storage(tmp_path) -> None:
    config = BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER)
    driver = HttpScrapingDriver(config)
    manager = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path="",
    )
    assert (
        manager.save_session(
            "https://example.test/private",
            [],
            local_storage={"private-token": "requires-javascript"},
        )
        is True
    )
    assert driver.launch() is True
    driver._current_url = "https://example.test/private"

    try:
        assert (
            manager.apply_to_driver(
                driver,
                "https://example.test/private",
            )
            is False
        )
    finally:
        driver.close()


def test_http_redirects_recompute_secure_expiry_and_host_cookie_scope() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    driver.set_cookies(
        [
            {
                "name": "host-only",
                "value": "exact-host",
                "domain": "example.test",
                "path": "/",
            },
            {
                "name": "domain-wide",
                "value": "subdomain-ok",
                "domain": ".example.test",
                "path": "/",
            },
            {
                "name": "secure-only",
                "value": "never-over-http",
                "domain": ".example.test",
                "path": "/",
                "secure": True,
            },
            {
                "name": "expired",
                "value": "never-send",
                "domain": ".example.test",
                "path": "/",
                "expires": int(time.time()) - 60,
            },
        ]
    )

    class FakeResponse:
        def __init__(self, status_code, url, *, location=None, text=""):
            self.status_code = status_code
            self.url = url
            self.text = text
            self.headers = {"location": location} if location else {}

        def close(self) -> None:
            return None

    assert driver._session is not None
    request_get = MagicMock(
        side_effect=[
            FakeResponse(
                302,
                "http://example.test/start",
                location="http://sub.example.test/final",
            ),
            FakeResponse(
                200,
                "http://sub.example.test/final",
                text="<html><head><title>Done</title></head></html>",
            ),
        ]
    )
    driver._session.get = request_get

    try:
        assert driver.navigate("http://example.test/start") is True
    finally:
        driver.close()

    assert request_get.call_count == 2
    first_cookies = request_get.call_args_list[0].kwargs["headers"]["Cookie"]
    second_cookies = request_get.call_args_list[1].kwargs["headers"]["Cookie"]
    assert first_cookies == "host-only=exact-host; domain-wide=subdomain-ok"
    assert second_cookies == "domain-wide=subdomain-ok"


def test_http_redirect_strips_configured_headers_on_origin_change() -> None:
    driver = HttpScrapingDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.HTTP_SCRAPER,
            extra_headers={
                "Authorization": "Bearer private-token",
                "Proxy-Authorization": "Basic private-proxy-token",
                "Cookie": "manual-cookie=must-not-bypass-cookie-policy",
                "X-API-Key": "private-api-key",
            },
        )
    )
    assert driver.launch() is True

    class FakeResponse:
        def __init__(self, status_code, url, *, location=None, text=""):
            self.status_code = status_code
            self.url = url
            self.text = text
            self.headers = {"location": location} if location else {}

        def close(self) -> None:
            return None

    assert driver._session is not None
    request_get = MagicMock(
        side_effect=[
            FakeResponse(
                302,
                "https://example.test/start",
                location="https://evil.test/final",
            ),
            FakeResponse(
                200,
                "https://evil.test/final",
                text="<html><head><title>Done</title></head></html>",
            ),
        ]
    )
    driver._session.get = request_get

    try:
        assert driver.navigate("https://example.test/start") is True
    finally:
        driver.close()

    first_headers = request_get.call_args_list[0].kwargs["headers"]
    second_headers = request_get.call_args_list[1].kwargs["headers"]
    assert first_headers["Authorization"] == "Bearer private-token"
    assert first_headers["X-API-Key"] == "private-api-key"
    assert not any(name.lower() == "cookie" for name in first_headers)
    assert second_headers == {}


def test_http_invalid_origins_never_receive_configured_headers() -> None:
    driver = HttpScrapingDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.HTTP_SCRAPER,
            extra_headers={"Authorization": "Bearer private-token"},
        )
    )

    assert (
        driver._headers_for_url(
            "https://example.test./start",
            "https://attacker.test./collect",
        )
        == {}
    )


def test_http_redirect_never_readds_headers_after_cross_origin_bounce() -> None:
    driver = HttpScrapingDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.HTTP_SCRAPER,
            extra_headers={"Authorization": "Bearer private-token"},
        )
    )
    assert driver.launch() is True

    class FakeResponse:
        def __init__(self, status_code, url, *, location=None, text=""):
            self.status_code = status_code
            self.url = url
            self.text = text
            self.headers = {"location": location} if location else {}

        def close(self) -> None:
            return None

    assert driver._session is not None
    request_get = MagicMock(
        side_effect=[
            FakeResponse(
                302,
                "https://trusted.test/start",
                location="https://other.test/bounce",
            ),
            FakeResponse(
                302,
                "https://other.test/bounce",
                location="https://trusted.test/final",
            ),
            FakeResponse(
                200,
                "https://trusted.test/final",
                text="<html><head><title>Done</title></head></html>",
            ),
        ]
    )
    driver._session.get = request_get

    try:
        assert driver.navigate("https://trusted.test/start") is True
    finally:
        driver.close()

    assert request_get.call_args_list[0].kwargs["headers"] == {
        "Authorization": "Bearer private-token"
    }
    assert request_get.call_args_list[1].kwargs["headers"] == {}
    assert request_get.call_args_list[2].kwargs["headers"] == {}


def test_http_redirect_real_sessions_do_not_send_secrets_to_new_origin() -> None:
    observed: dict[str, dict[str, str]] = {}

    class FinalHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            observed["final"] = dict(self.headers.items())
            body = b"<html><head><title>Done</title></head></html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    final_server = ThreadingHTTPServer(("127.0.0.1", 0), FinalHandler)
    final_thread = threading.Thread(target=final_server.serve_forever, daemon=True)
    final_thread.start()

    class RedirectHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            observed["initial"] = dict(self.headers.items())
            ambiguous_url = (
                f"http://127.0.0.1:{final_server.server_port}"
                f"\\@localhost:{self.server.server_port}/final"
            )
            self.send_response(302)
            self.send_header("Location", ambiguous_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

    redirect_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = threading.Thread(
        target=redirect_server.serve_forever,
        daemon=True,
    )
    redirect_thread.start()
    start_url = f"http://localhost:{redirect_server.server_port}/start"

    driver = HttpScrapingDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.HTTP_SCRAPER,
            extra_headers={
                "Authorization": "Bearer private-token",
                "X-API-Key": "private-api-key",
            },
        )
    )
    try:
        assert driver.launch() is True
        driver.set_cookies(
            [
                {
                    "name": "sid",
                    "value": "cookie-secret",
                    "domain": "localhost",
                    "path": "/",
                }
            ]
        )
        assert driver.navigate(start_url) is True
    finally:
        driver.close()
        redirect_server.shutdown()
        redirect_server.server_close()
        final_server.shutdown()
        final_server.server_close()
        redirect_thread.join(timeout=2.0)
        final_thread.join(timeout=2.0)

    assert observed["initial"]["Authorization"] == "Bearer private-token"
    assert observed["initial"]["X-API-Key"] == "private-api-key"
    assert observed["initial"]["Cookie"] == "sid=cookie-secret"
    assert "Authorization" not in observed["final"]
    assert "X-API-Key" not in observed["final"]
    assert "Cookie" not in observed["final"]


def test_playwright_page_headers_are_scoped_to_navigation_origin() -> None:
    driver = PlaywrightBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.PLAYWRIGHT,
            extra_headers={
                "Authorization": "Bearer private-token",
                "X-API-Key": "private-api-key",
                "Cookie": "must-not-override-browser-cookie-store",
            },
        )
    )
    driver._navigation_header_origin = ("https", "example.test", 443)
    driver._committed_header_origin = ("https", "example.test", 443)
    driver._committed_header_authorized = True
    driver._main_frame_id = "main-frame"
    session = MagicMock()
    driver._header_cdp_session = session

    driver._on_request_paused(
        {
            "requestId": "same-origin",
            "frameId": "main-frame",
            "resourceType": "Fetch",
            "request": {
                "url": "https://example.test/api",
                "headers": {"Accept": "application/json"},
            },
        }
    )
    same_payload = session.send.call_args_list[-1].args[1]
    same_headers = {entry["name"]: entry["value"] for entry in same_payload["headers"]}
    assert same_headers["Authorization"] == "Bearer private-token"
    assert same_headers["X-API-Key"] == "private-api-key"
    assert not any(name.lower() == "cookie" for name in same_headers)

    driver._on_request_paused(
        {
            "requestId": "cross-origin",
            "frameId": "main-frame",
            "resourceType": "Document",
            "request": {
                "url": "https://attacker.test/collect",
                "headers": {
                    "Accept": "application/json",
                    "Authorization": "Bearer private-token",
                    "X-API-Key": "private-api-key",
                },
            },
        }
    )
    cross_payload = session.send.call_args_list[-1].args[1]
    cross_headers = {entry["name"]: entry["value"] for entry in cross_payload["headers"]}
    assert "Authorization" not in cross_headers
    assert "X-API-Key" not in cross_headers

    driver._committed_header_origin = ("https", "attacker.test", 443)
    driver._on_request_paused(
        {
            "requestId": "attacker-triggered-return",
            "frameId": "main-frame",
            "resourceType": "Image",
            "request": {
                "url": "https://example.test/private-side-effect",
                "headers": {},
            },
        }
    )
    return_payload = session.send.call_args_list[-1].args[1]
    return_headers = {entry["name"]: entry["value"] for entry in return_payload["headers"]}
    assert "Authorization" not in return_headers
    assert "X-API-Key" not in return_headers


def test_playwright_subresource_redirect_chain_never_readds_headers() -> None:
    driver = PlaywrightBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.PLAYWRIGHT,
            extra_headers={"Authorization": "Bearer private-token"},
        )
    )
    driver._navigation_header_origin = ("https", "example.test", 443)
    driver._committed_header_origin = ("https", "example.test", 443)
    driver._committed_header_authorized = True
    driver._main_frame_id = "main-frame"
    session = MagicMock()
    driver._header_cdp_session = session

    for request_id, url in (
        ("interception-job-1.0", "https://example.test/asset-start"),
        ("interception-job-1.1", "https://attacker.test/bounce"),
        ("interception-job-1.2", "https://example.test/private"),
    ):
        driver._on_request_paused(
            {
                "requestId": request_id,
                "networkId": "network-chain-1",
                "frameId": "main-frame",
                "resourceType": "Image",
                "request": {"url": url, "headers": {}},
            }
        )

    observed = []
    for call in session.send.call_args_list:
        payload = call.args[1]
        observed.append({entry["name"]: entry["value"] for entry in payload["headers"]})
    assert observed[0]["Authorization"] == "Bearer private-token"
    assert "Authorization" not in observed[1]
    assert "Authorization" not in observed[2]


def test_playwright_cookie_delta_validates_before_mutation() -> None:
    original = {
        "name": "sid",
        "value": "original-session",
        "domain": "example.test",
        "path": "/",
        "sameSite": "Strict",
    }

    class StrictCookieContext:
        def __init__(self) -> None:
            self.jar = [dict(original)]

        def cookies(self) -> list[dict[str, object]]:
            return [dict(cookie) for cookie in self.jar]

        def add_cookies(self, cookies) -> None:
            self.jar.extend(dict(cookie) for cookie in cookies)

    context = StrictCookieContext()
    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._is_running = True
    session = MagicMock()
    driver._header_cdp_session = session

    driver.apply_cookie_delta(
        [
            {
                "name": "invalid",
                "value": "must-not-wipe-existing-state",
                "domain": "example.test",
                "path": "/",
                "expires": None,
                "sameSite": "strict",
            }
        ],
        [],
    )

    assert context.jar == [original]
    session.send.assert_not_called()
    assert driver.last_error_status is BrowserResultStatus.ERROR


def test_playwright_cookie_delta_rolls_back_partial_deletion_failure() -> None:
    original = [
        {"name": "one", "value": "first", "domain": "example.test", "path": "/"},
        {"name": "two", "value": "second", "domain": "example.test", "path": "/"},
        {
            "name": "unrelated",
            "value": "must-survive",
            "domain": "example.test",
            "path": "/other",
        },
    ]

    class DeltaContext:
        def __init__(self) -> None:
            self.jar = [dict(cookie) for cookie in original]

        def cookies(self) -> list[dict[str, object]]:
            return [dict(cookie) for cookie in self.jar]

        def add_cookies(self, cookies) -> None:
            for cookie in cookies:
                identity = (cookie["name"], cookie["domain"], cookie["path"])
                self.jar = [
                    existing
                    for existing in self.jar
                    if (
                        existing["name"],
                        existing["domain"],
                        existing["path"],
                    )
                    != identity
                ]
                self.jar.append(dict(cookie))

    context = DeltaContext()
    delete_calls = 0

    def send(method: str, params=None):
        nonlocal delete_calls
        if method != "Network.deleteCookies":
            return {}
        delete_calls += 1
        if delete_calls == 2:
            raise RuntimeError("synthetic second-delete failure")
        identity = (params["name"], params["domain"], params["path"])
        context.jar = [
            cookie
            for cookie in context.jar
            if (cookie["name"], cookie["domain"], cookie["path"]) != identity
        ]
        return {}

    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._is_running = True
    driver._header_cdp_session = SimpleNamespace(send=send)

    driver.apply_cookie_delta(
        [],
        [
            ("one", "example.test", "/", None),
            ("two", "example.test", "/", None),
        ],
    )

    assert sorted(context.jar, key=lambda cookie: cookie["name"]) == sorted(
        original,
        key=lambda cookie: cookie["name"],
    )
    assert driver.last_error_status is BrowserResultStatus.ERROR


def test_http_set_cookies_rejects_entire_invalid_batch() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    original = {
        "name": "sid",
        "value": "preserved",
        "domain": "example.test",
        "path": "/",
    }
    driver.set_cookies([original])

    driver.set_cookies(
        [
            {
                "name": "new",
                "value": "must-not-partially-apply",
                "domain": "example.test",
                "path": "/",
            },
            {},
        ]
    )

    assert driver.last_error_code == "BROWSER_INVALID_COOKIE"
    assert driver.get_cookies() == [original]
    driver.set_cookies([{}])
    assert driver.last_error_code == "BROWSER_INVALID_COOKIE"
    driver.close()


def test_http_response_cookie_extensions_do_not_create_fake_cookies() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    accepted = MagicMock()
    accepted.name = "sid"
    accepted.value = "accepted-session"
    accepted.domain = "example.test"
    accepted.domain_specified = False
    accepted.path = "/secure"
    accepted.secure = True
    accepted.expires = None
    accepted._rest = {"HttpOnly": None, "SameSite": "Lax"}
    assert driver._session is not None
    driver._session.cookies = [accepted]
    raw_headers = MagicMock()
    raw_headers.getlist.return_value = [
        "sid=accepted-session; Path=/secure; Secure; HttpOnly; "
        "SameSite=Lax; Priority=High; SameParty"
    ]
    response = MagicMock()
    response.raw.headers = raw_headers
    response.headers = {}

    driver._merge_session_cookies(response, "https://example.test/secure")

    assert driver.get_cookies() == [
        {
            "name": "sid",
            "value": "accepted-session",
            "domain": "example.test",
            "path": "/secure",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }
    ]
    driver.close()


def test_http_response_rejects_parent_domain_and_insecure_secure_cookie() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    assert driver._session is not None

    parent_cookie = MagicMock()
    parent_cookie.name = "parent"
    parent_cookie.value = "must-not-cross-sites"
    parent_cookie.domain = ".co.uk"
    parent_cookie.domain_specified = True
    parent_cookie.path = "/"
    parent_cookie.secure = True
    parent_cookie.expires = None
    parent_cookie._rest = {}
    driver._session.cookies = [parent_cookie]
    parent_response = MagicMock()
    parent_response.headers = {
        "set-cookie": "parent=must-not-cross-sites; Domain=co.uk; Path=/; Secure"
    }
    parent_response.raw = None

    driver._merge_session_cookies(
        parent_response,
        "https://shop.example.co.uk/account",
    )

    insecure_secure_cookie = MagicMock()
    insecure_secure_cookie.name = "secure-session"
    insecure_secure_cookie.value = "must-not-be-fixed"
    insecure_secure_cookie.domain = "shop.example.test"
    insecure_secure_cookie.domain_specified = False
    insecure_secure_cookie.path = "/"
    insecure_secure_cookie.secure = True
    insecure_secure_cookie.expires = None
    insecure_secure_cookie._rest = {}
    driver._session.cookies = [insecure_secure_cookie]
    insecure_response = MagicMock()
    insecure_response.headers = {"set-cookie": "secure-session=must-not-be-fixed; Path=/; Secure"}
    insecure_response.raw = None

    driver._merge_session_cookies(
        insecure_response,
        "http://shop.example.test/account",
    )

    assert driver.get_cookies() == []
    driver.close()


def test_http_response_cookie_deletion_removes_persisted_cookie() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "private-session",
                "domain": "example.test",
                "path": "/",
            }
        ]
    )

    class FakeResponse:
        def __init__(self, url, *, headers=None):
            self.status_code = 200
            self.url = url
            self.text = "<html><head><title>Done</title></head></html>"
            self.headers = headers or {}

        def close(self) -> None:
            return None

    assert driver._session is not None
    request_get = MagicMock(
        side_effect=[
            FakeResponse(
                "https://example.test/logout",
                headers={"set-cookie": "sid=; Max-Age=0; Path=/"},
            ),
            FakeResponse("https://example.test/echo"),
        ]
    )
    driver._session.get = request_get

    try:
        assert driver.navigate("https://example.test/logout") is True
        assert driver.get_cookies() == []
        assert driver.navigate("https://example.test/echo") is True
    finally:
        driver.close()

    assert request_get.call_args_list[0].kwargs["headers"]["Cookie"] == ("sid=private-session")
    assert "Cookie" not in request_get.call_args_list[1].kwargs["headers"]


def test_http_cookie_max_age_takes_precedence_over_expired_expires() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "still-valid",
                "domain": "example.test",
                "path": "/",
            }
        ]
    )

    class FakeResponse:
        status_code = 200
        url = "https://example.test/account"
        text = "<html><head><title>Account</title></head></html>"
        headers = {
            "set-cookie": (
                "sid=still-valid; Max-Age=3600; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/"
            )
        }

    assert driver._session is not None
    driver._session.get = MagicMock(return_value=FakeResponse())

    try:
        assert driver.navigate("https://example.test/account") is True
        assert driver.get_cookies()[0]["value"] == "still-valid"
    finally:
        driver.close()


def test_http_redirect_withholds_strict_cookie_from_cross_site_chain() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    driver.set_cookies(
        [
            {
                "name": "bank-session",
                "value": "must-not-cross-site",
                "domain": "bank.test",
                "path": "/",
                "secure": True,
                "sameSite": "Strict",
            }
        ]
    )

    class FakeResponse:
        def __init__(self, status_code, url, *, location=None):
            self.status_code = status_code
            self.url = url
            self.text = "<html><head><title>Done</title></head></html>"
            self.headers = {"location": location} if location else {}

        def close(self) -> None:
            return None

    assert driver._session is not None
    request_get = MagicMock(
        side_effect=[
            FakeResponse(
                302,
                "https://evil.test/start",
                location="https://bank.test/account",
            ),
            FakeResponse(200, "https://bank.test/account"),
        ]
    )
    driver._session.get = request_get

    try:
        assert driver.navigate("https://evil.test/start") is True
    finally:
        driver.close()

    assert "Cookie" not in request_get.call_args_list[1].kwargs["headers"]


def test_http_cookie_security_attributes_survive_session_capture(tmp_path) -> None:
    config = BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER)
    driver = HttpScrapingDriver(config)
    manager = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    assert driver.launch() is True
    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "private-session",
                "domain": "example.test",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "strict",
            }
        ]
    )

    try:
        assert (
            manager.capture_from_driver(
                driver,
                "https://example.test/account",
            )
            is True
        )
    finally:
        driver.close()

    stored = manager.load_session("https://example.test/account")
    assert stored is not None
    assert stored["cookies"] == [
        {
            "name": "sid",
            "value": "private-session",
            "domain": "example.test",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Strict",
        }
    ]


def test_http_partitioned_cookie_is_preserved_but_never_transmitted(tmp_path) -> None:
    config = BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER)
    driver = HttpScrapingDriver(config)
    manager = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path="",
    )
    assert driver.launch() is True
    driver.set_cookies(
        [
            {
                "name": "partitioned-auth",
                "value": "private-session",
                "domain": "example.test",
                "path": "/",
                "secure": True,
                "partitionKey": "https://top-level.test",
            }
        ]
    )

    class FakeResponse:
        status_code = 200
        url = "https://example.test/account"
        text = "<html><head><title>Account</title></head></html>"
        headers: dict[str, str] = {}

    assert driver._session is not None
    get_request = MagicMock(return_value=FakeResponse())
    driver._session.get = get_request

    try:
        assert driver.navigate("https://example.test/account") is True
        assert "Cookie" not in get_request.call_args.kwargs["headers"]
        assert (
            manager.capture_from_driver(
                driver,
                "https://example.test/account",
            )
            is True
        )
    finally:
        driver.close()

    stored = manager.load_session("https://example.test/account")
    assert stored is not None
    assert stored["cookies"][0]["partitionKey"] == "https://top-level.test"


def test_http_response_cookie_shape_is_playwright_compatible() -> None:
    class CookieHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            body = b"<html><head><title>Cookie</title></head></html>"
            self.send_response(200)
            self.send_header(
                "Set-Cookie",
                "sid=private-session; Path=/; HttpOnly=false; SameSite=strict",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), CookieHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/cookie"
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))

    try:
        assert driver.launch() is True
        assert driver.navigate(url) is True
        observed = driver.get_cookies()
    finally:
        driver.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)

    assert len(observed) == 1
    assert observed[0]["httpOnly"] is True
    assert observed[0]["sameSite"] == "Strict"
    assert "expires" not in observed[0]


def test_http_fallback_rejects_type() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    try:
        result = BrowserActions(driver).fill_text("#secret", "do-not-store")
    finally:
        driver.close()

    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.error_code == "BROWSER_CAPABILITY_UNAVAILABLE"


def test_http_fallback_rejects_scroll() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    try:
        result = BrowserActions(driver).scroll_page("down", 500)
    finally:
        driver.close()

    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.error_code == "BROWSER_CAPABILITY_UNAVAILABLE"


def test_http_fallback_does_not_return_placeholder_screenshot() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    try:
        result = BrowserActions(driver).take_screenshot()
    finally:
        driver.close()

    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.error_code == "BROWSER_CAPABILITY_UNAVAILABLE"
    assert result.screenshot_b64 is None


def test_canonical_executor_reports_http_wait_as_unavailable() -> None:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    try:
        result = BrowserActionExecutor(driver).wait_for_selector("#delayed", timeout_ms=10)
    finally:
        driver.close()

    assert BrowserActions is BrowserActionExecutor
    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.error_code == "BROWSER_CAPABILITY_UNAVAILABLE"


def test_price_scrape_failure_does_not_create_synthetic_offer(tmp_path) -> None:
    config = BrowserConfig(
        driver_type=BrowserDriverType.MOCK,
        session_storage_dir=str(tmp_path / "sessions"),
    )
    driver = MockBrowserDriver(config)
    sessions = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    agent = BrowserAgent(config=config, driver=driver, session_manager=sessions)
    try:
        offers = agent.compare_prices(product_name="missing-product", stores=["TestStore"])
    finally:
        agent.stop()

    assert offers == []


def test_failed_navigation_cannot_relabel_stale_scrape_content(tmp_path) -> None:
    config = BrowserConfig(
        driver_type=BrowserDriverType.HTTP_SCRAPER,
        timeout_ms=200,
        session_storage_dir=str(tmp_path / "sessions"),
    )
    driver = HttpScrapingDriver(config)
    sessions = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    agent = BrowserAgent(config=config, driver=driver, session_manager=sessions)
    try:
        with LocalBrowserTestSite() as site:
            first = agent.scrape_url(f"{site.base_url}/")
        failed = agent.scrape_url("http://127.0.0.1:1/unreachable")
    finally:
        agent.stop()

    assert first.success is True
    assert failed.success is False
    assert failed.status is BrowserResultStatus.UNAVAILABLE
    assert failed.error_code == "BROWSER_NAVIGATION_UNAVAILABLE"
    assert failed.title == ""
    assert "Deterministic Browser Page" not in failed.text_content


def test_factory_fallback_reports_the_actual_http_driver(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "missing-browsers"))
    config = BrowserConfig(
        driver_type=BrowserDriverType.PLAYWRIGHT,
        cdp_endpoint="http://127.0.0.1:1",
        session_storage_dir=str(tmp_path / "sessions"),
    )
    driver = DriverFactory.create_driver(config=config)
    sessions = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    agent = BrowserAgent(config=config, driver=driver, session_manager=sessions)
    try:
        assert isinstance(driver, HttpScrapingDriver)
        assert agent.get_active_driver_type() is BrowserDriverType.HTTP_SCRAPER
    finally:
        agent.stop()


def test_detect_best_driver_validates_playwright_runtime_before_reporting_it(
    monkeypatch,
) -> None:
    monkeypatch.setattr(PlaywrightBrowserDriver, "launch", lambda self, config=None: False)
    monkeypatch.setattr(CDPBrowserDriver, "launch", lambda self, config=None: False)
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: type("Response", (), {"status_code": 200})(),
    )

    assert DriverFactory.detect_best_driver() is BrowserDriverType.HTTP_SCRAPER


def test_factory_launch_logs_do_not_echo_exception_secrets(monkeypatch, caplog) -> None:
    secret = "proxy-password-do-not-log"

    def fail_with_secret(self, config=None):
        raise RuntimeError(secret)

    monkeypatch.setattr(PlaywrightBrowserDriver, "launch", fail_with_secret)
    monkeypatch.setattr(CDPBrowserDriver, "launch", fail_with_secret)
    monkeypatch.setattr(HttpScrapingDriver, "launch", lambda self, config=None: True)

    driver = DriverFactory.create_driver(driver_type=BrowserDriverType.PLAYWRIGHT)

    assert isinstance(driver, HttpScrapingDriver)
    assert secret not in caplog.text


def test_playwright_driver_rejects_scroll_script_injection_before_evaluation() -> None:
    evaluated: list[str] = []

    class FakePage:
        def evaluate(self, script: str) -> None:
            evaluated.append(script)

    driver = PlaywrightBrowserDriver()
    driver._is_running = True
    driver._browser = object()
    driver._page = FakePage()
    driver.is_running = lambda: True  # type: ignore[method-assign]

    result = driver.scroll(
        "down",
        "0); window.__injected = true; window.scrollBy(0, 1",  # type: ignore[arg-type]
    )

    assert result is False
    assert driver.last_error_code == "BROWSER_INVALID_SCROLL_DISTANCE"
    assert evaluated == []


def test_http_navigation_preserves_not_configured_launch_failure() -> None:
    driver = HttpScrapingDriver()

    def fail_launch(config=None) -> bool:
        driver._record_failure(
            BrowserResultStatus.NOT_CONFIGURED,
            "BROWSER_HTTP_NOT_CONFIGURED",
            "The HTTP scraper is not configured.",
        )
        return False

    driver.launch = fail_launch  # type: ignore[method-assign]

    assert driver.navigate("https://example.test") is False
    assert driver.last_error_status is BrowserResultStatus.NOT_CONFIGURED
    assert driver.last_error_code == "BROWSER_HTTP_NOT_CONFIGURED"
