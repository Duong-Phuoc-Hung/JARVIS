"""Security regressions for browser cookie ingestion and request emission."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jarvis.browser.actions import (
    BrowserActionExecutor,
    _merge_download_response_cookies,
)
from jarvis.browser.driver import (
    HttpScrapingDriver,
    MockBrowserDriver,
    PlaywrightBrowserDriver,
)
from jarvis.browser.models import (
    BrowserConfig,
    BrowserDriverType,
    BrowserResultStatus,
)
from jarvis.browser.session import BrowserSessionManager


def _accepted_cookie(
    name: str,
    value: str,
    *,
    domain: str,
    path: str = "/",
    domain_specified: bool = False,
    secure: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        value=value,
        domain=domain,
        domain_specified=domain_specified,
        path=path,
        secure=secure,
        expires=None,
        _rest={},
    )


def _response_with_set_cookie(
    headers: list[str],
    accepted_cookies: list[SimpleNamespace] | None = None,
) -> MagicMock:
    raw_headers = MagicMock()
    raw_headers.getlist.return_value = headers
    response = MagicMock()
    response.raw.headers = raw_headers
    response.headers = {}
    response.cookies = accepted_cookies or []
    return response


def _http_driver() -> HttpScrapingDriver:
    driver = HttpScrapingDriver(BrowserConfig(driver_type=BrowserDriverType.HTTP_SCRAPER))
    assert driver.launch() is True
    return driver


class _InMemoryPlaywrightCookieContext:
    """Minimal browser-boundary fake that exposes Playwright's cookie seam."""

    def __init__(self, cookies: list[dict[str, object]] | None = None) -> None:
        self.jar = [dict(cookie) for cookie in cookies or []]

    def cookies(self) -> list[dict[str, object]]:
        return [dict(cookie) for cookie in self.jar]

    def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        entries = [dict(cookie) for cookie in cookies]
        self.jar.extend(entries)


def _playwright_cookie_driver(
    context: _InMemoryPlaywrightCookieContext,
) -> PlaywrightBrowserDriver:
    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._header_cdp_session = MagicMock()
    driver._is_running = True
    driver._has_started = True
    return driver


def test_download_set_then_delete_wins_over_stale_requests_cookie_jar() -> None:
    cookies = [
        {
            "name": "sid",
            "value": "old",
            "domain": "files.example.test",
            "path": "/",
        }
    ]
    response = _response_with_set_cookie(
        [
            "sid=new; Path=/; Secure",
            "sid=; Max-Age=0; Path=/; Secure",
        ],
        [
            _accepted_cookie(
                "sid",
                "new",
                domain="files.example.test",
                secure=True,
            )
        ],
    )

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "https://files.example.test/logout",
    )

    assert cookies == []
    assert upserts == []
    assert deletions == [("sid", "files.example.test", "/", None)]


def test_http_set_then_delete_wins_over_stale_requests_cookie_jar() -> None:
    driver = _http_driver()
    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "old",
                "domain": "files.example.test",
                "path": "/",
            }
        ]
    )
    response = _response_with_set_cookie(
        [
            "sid=new; Path=/; Secure",
            "sid=; Max-Age=0; Path=/; Secure",
        ]
    )
    assert driver._session is not None
    driver._session.cookies = [
        _accepted_cookie(
            "sid",
            "new",
            domain="files.example.test",
            secure=True,
        )
    ]

    try:
        driver._merge_session_cookies(
            response,
            "https://files.example.test/logout",
        )
        assert driver.get_cookies() == []
    finally:
        driver.close()


def test_download_invalid_path_deletion_uses_rfc_default_path() -> None:
    cookies = [
        {
            "name": "sid",
            "value": "private",
            "domain": "files.example.test",
            "path": "/account",
        }
    ]
    response = _response_with_set_cookie(["sid=; Max-Age=0; Path=bogus; Secure"])

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "https://files.example.test/account/logout",
    )

    assert cookies == []
    assert upserts == []
    assert deletions == [("sid", "files.example.test", "/account", None)]


def test_http_invalid_path_deletion_uses_rfc_default_path() -> None:
    driver = _http_driver()
    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "private",
                "domain": "files.example.test",
                "path": "/account",
            }
        ]
    )
    response = _response_with_set_cookie(["sid=; Max-Age=0; Path=bogus; Secure"])
    assert driver._session is not None
    driver._session.cookies = []

    try:
        driver._merge_session_cookies(
            response,
            "https://files.example.test/account/logout",
        )
        assert driver.get_cookies() == []
    finally:
        driver.close()


def test_download_parent_domain_may_delete_and_create_valid_cookie() -> None:
    cookies = [
        {
            "name": "sid",
            "value": "parent-session",
            "domain": ".example.test",
            "path": "/",
        }
    ]
    deletion = _response_with_set_cookie(["sid=; Max-Age=0; Domain=example.test; Path=/; Secure"])

    _upserts, deletions = _merge_download_response_cookies(
        cookies,
        deletion,
        "https://shop.example.test/logout",
    )

    assert cookies == []
    assert deletions == [("sid", ".example.test", "/", None)]

    parent_upsert = _response_with_set_cookie(
        ["sid=must-not-broaden; Domain=example.test; Path=/; Secure"],
        [
            _accepted_cookie(
                "sid",
                "must-not-broaden",
                domain=".example.test",
                domain_specified=True,
                secure=True,
            )
        ],
    )
    upserts, _deletions = _merge_download_response_cookies(
        cookies,
        parent_upsert,
        "https://shop.example.test/account",
    )

    assert upserts == [
        {
            "name": "sid",
            "value": "must-not-broaden",
            "domain": ".example.test",
            "path": "/",
            "secure": True,
        }
    ]
    assert cookies == upserts


def test_http_parent_domain_may_delete_and_create_valid_cookie() -> None:
    driver = _http_driver()
    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "parent-session",
                "domain": ".example.test",
                "path": "/",
            }
        ]
    )
    deletion = _response_with_set_cookie(["sid=; Max-Age=0; Domain=example.test; Path=/; Secure"])
    assert driver._session is not None
    driver._session.cookies = []

    try:
        driver._merge_session_cookies(
            deletion,
            "https://shop.example.test/logout",
        )
        assert driver.get_cookies() == []

        parent_upsert = _response_with_set_cookie(
            ["sid=must-not-broaden; Domain=example.test; Path=/; Secure"]
        )
        driver._session.cookies = [
            _accepted_cookie(
                "sid",
                "must-not-broaden",
                domain=".example.test",
                domain_specified=True,
                secure=True,
            )
        ]
        driver._merge_session_cookies(
            parent_upsert,
            "https://shop.example.test/account",
        )
        assert driver.get_cookies() == [
            {
                "name": "sid",
                "value": "must-not-broaden",
                "domain": ".example.test",
                "path": "/",
                "secure": True,
            }
        ]
    finally:
        driver.close()


def test_download_rejects_invalid_secure_and_host_cookie_prefixes() -> None:
    response = _response_with_set_cookie(
        [
            "__Secure-sid=missing-flag; Path=/",
            "__Host-sid=has-domain; Domain=files.example.test; Path=/; Secure",
        ],
        [
            _accepted_cookie(
                "__Secure-sid",
                "missing-flag",
                domain="files.example.test",
            ),
            _accepted_cookie(
                "__Host-sid",
                "has-domain",
                domain=".files.example.test",
                domain_specified=True,
                secure=True,
            ),
        ],
    )
    cookies: list[dict[str, object]] = []

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "https://files.example.test/account",
    )

    assert upserts == []
    assert deletions == []
    assert cookies == []


def test_http_rejects_invalid_secure_and_host_cookie_prefixes() -> None:
    driver = _http_driver()
    response = _response_with_set_cookie(
        [
            "__Secure-sid=missing-flag; Path=/",
            "__Host-sid=has-domain; Domain=files.example.test; Path=/; Secure",
        ]
    )
    assert driver._session is not None
    driver._session.cookies = [
        _accepted_cookie(
            "__Secure-sid",
            "missing-flag",
            domain="files.example.test",
        ),
        _accepted_cookie(
            "__Host-sid",
            "has-domain",
            domain=".files.example.test",
            domain_specified=True,
            secure=True,
        ),
    ]

    try:
        driver._merge_session_cookies(
            response,
            "https://files.example.test/account",
        )
        assert driver.get_cookies() == []
    finally:
        driver.close()


def test_download_domain_localhost_is_never_stored_as_domain_cookie() -> None:
    response = _response_with_set_cookie(
        ["sid=value; Domain=localhost; Path=/; Secure"],
        [
            _accepted_cookie(
                "sid",
                "value",
                domain=".localhost",
                domain_specified=True,
                secure=True,
            )
        ],
    )
    cookies: list[dict[str, object]] = []

    upserts, _deletions = _merge_download_response_cookies(
        cookies,
        response,
        "https://localhost/account",
    )

    expected = {
        "name": "sid",
        "value": "value",
        "domain": "localhost",
        "path": "/",
        "secure": True,
    }
    assert upserts == [expected]
    assert cookies == [expected]


def test_http_domain_localhost_is_never_stored_as_domain_cookie() -> None:
    driver = _http_driver()
    response = _response_with_set_cookie(["sid=value; Domain=localhost; Path=/; Secure"])
    assert driver._session is not None
    driver._session.cookies = [
        _accepted_cookie(
            "sid",
            "value",
            domain=".localhost",
            domain_specified=True,
            secure=True,
        )
    ]

    try:
        driver._merge_session_cookies(response, "https://localhost/account")
        assert driver.get_cookies() == [
            {
                "name": "sid",
                "value": "value",
                "domain": "localhost",
                "path": "/",
                "secure": True,
            }
        ]
    finally:
        driver.close()


def test_download_emits_duplicate_cookie_names_specific_path_first(
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
            "value": "narrow",
            "domain": "files.example.test",
            "path": "/private",
        },
        {
            "name": "sid",
            "value": "broad",
            "domain": "files.example.test",
            "path": "/",
        },
    ]
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-length": "4"}
    response.raw = None
    response.cookies = []
    response.iter_content.return_value = [b"data"]
    response.__enter__.return_value = response
    get_request = MagicMock(return_value=response)
    monkeypatch.setattr("requests.get", get_request)

    result = BrowserActionExecutor(driver).download_file(
        "https://files.example.test/private/report.bin",
    )

    assert result.success is True
    request_kwargs = get_request.call_args.kwargs
    assert request_kwargs["headers"]["Cookie"] == "sid=narrow; sid=broad"
    assert "cookies" not in request_kwargs


def test_http_emits_duplicate_cookie_names_specific_path_first() -> None:
    driver = _http_driver()
    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "narrow",
                "domain": "files.example.test",
                "path": "/private",
            },
            {
                "name": "sid",
                "value": "broad",
                "domain": "files.example.test",
                "path": "/",
            },
        ]
    )

    class FakeResponse:
        status_code = 200
        url = "https://files.example.test/private/account"
        text = "<html><head><title>Account</title></head></html>"
        headers: dict[str, str] = {}
        raw = None
        cookies: list[object] = []

    assert driver._session is not None
    get_request = MagicMock(return_value=FakeResponse())
    driver._session.get = get_request

    try:
        assert driver.navigate("https://files.example.test/private/account") is True
    finally:
        driver.close()

    request_kwargs = get_request.call_args.kwargs
    assert request_kwargs["headers"]["Cookie"] == "sid=narrow; sid=broad"
    assert "cookies" not in request_kwargs


def test_download_exact_host_domain_deletion_preserves_host_only_peer() -> None:
    host_only = {
        "name": "sid",
        "value": "host-only",
        "domain": "foo.localhost",
        "path": "/",
    }
    domain_cookie = {
        "name": "sid",
        "value": "domain-cookie",
        "domain": ".foo.localhost",
        "path": "/",
    }
    cookies = [dict(host_only), dict(domain_cookie)]
    response = _response_with_set_cookie(["sid=; Max-Age=0; Domain=foo.localhost; Path=/; Secure"])

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "https://foo.localhost/logout",
    )

    assert cookies == [host_only]
    assert upserts == []
    assert deletions == [("sid", ".foo.localhost", "/", None)]


def test_http_exact_host_domain_deletion_preserves_host_only_peer() -> None:
    driver = _http_driver()
    host_only = {
        "name": "sid",
        "value": "host-only",
        "domain": "foo.localhost",
        "path": "/",
    }
    driver.set_cookies(
        [
            host_only,
            {
                "name": "sid",
                "value": "domain-cookie",
                "domain": ".foo.localhost",
                "path": "/",
            },
        ]
    )
    response = _response_with_set_cookie(["sid=; Max-Age=0; Domain=foo.localhost; Path=/; Secure"])
    assert driver._session is not None
    driver._session.cookies = []

    try:
        driver._merge_session_cookies(response, "https://foo.localhost/logout")
        assert driver.get_cookies() == [host_only]
    finally:
        driver.close()


def test_download_insecure_set_cannot_overlay_secure_cookie() -> None:
    original = {
        "name": "sid",
        "value": "secure-original",
        "domain": "files.example.test",
        "path": "/account",
        "secure": True,
    }
    cookies = [dict(original)]
    response = _response_with_set_cookie(["sid=insecure; Path=/account"])

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "http://files.example.test/account/login",
    )

    assert cookies == [original]
    assert upserts == []
    assert deletions == []


def test_download_insecure_deletion_cannot_remove_secure_cookie() -> None:
    original = {
        "name": "sid",
        "value": "secure-original",
        "domain": "files.example.test",
        "path": "/account",
        "secure": True,
    }
    cookies = [dict(original)]
    response = _response_with_set_cookie(["sid=; Max-Age=0; Path=/account"])

    upserts, deletions = _merge_download_response_cookies(
        cookies,
        response,
        "http://files.example.test/account/logout",
    )

    assert cookies == [original]
    assert upserts == []
    assert deletions == []


def test_http_insecure_set_cannot_overlay_secure_cookie() -> None:
    driver = _http_driver()
    original = {
        "name": "sid",
        "value": "secure-original",
        "domain": "files.example.test",
        "path": "/account",
        "secure": True,
    }
    driver.set_cookies([original])
    response = _response_with_set_cookie(["sid=insecure; Path=/account"])
    assert driver._session is not None
    driver._session.cookies = []

    try:
        driver._merge_session_cookies(
            response,
            "http://files.example.test/account/login",
        )
        assert driver.get_cookies() == [original]
    finally:
        driver.close()


def test_http_insecure_deletion_cannot_remove_secure_cookie() -> None:
    driver = _http_driver()
    original = {
        "name": "sid",
        "value": "secure-original",
        "domain": "files.example.test",
        "path": "/account",
        "secure": True,
    }
    driver.set_cookies([original])
    response = _response_with_set_cookie(["sid=; Max-Age=0; Path=/account"])
    assert driver._session is not None
    driver._session.cookies = []

    try:
        driver._merge_session_cookies(
            response,
            "http://files.example.test/account/logout",
        )
        assert driver.get_cookies() == [original]
    finally:
        driver.close()


def test_playwright_rejects_samesite_none_cookie_without_secure() -> None:
    context = MagicMock()
    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._is_running = True
    driver._has_started = True

    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "must-not-apply",
                "domain": "example.test",
                "path": "/",
                "sameSite": "None",
                "secure": False,
            }
        ]
    )

    context.add_cookies.assert_not_called()
    assert driver.last_error_status is BrowserResultStatus.ERROR
    assert driver.last_error_code == "BROWSER_INVALID_COOKIE"


def test_http_rejects_samesite_none_cookie_without_secure() -> None:
    driver = _http_driver()
    original = {
        "name": "preserved",
        "value": "original",
        "domain": "example.test",
        "path": "/",
    }
    driver.set_cookies([original])

    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "must-not-apply",
                "domain": "example.test",
                "path": "/",
                "sameSite": "None",
                "secure": False,
            }
        ]
    )

    try:
        assert driver.last_error_status is BrowserResultStatus.ERROR
        assert driver.last_error_code == "BROWSER_INVALID_COOKIE"
        assert driver.get_cookies() == [original]
    finally:
        driver.close()


def test_playwright_partition_delete_uses_observed_cross_site_bit() -> None:
    cookie = {
        "name": "partitioned",
        "value": "private",
        "domain": "third.example",
        "path": "/",
        "secure": True,
        "partitionKey": "https://top.example",
        "_crHasCrossSiteAncestor": True,
    }

    class PartitionContext:
        def __init__(self) -> None:
            self.jar = [dict(cookie)]

        def cookies(self) -> list[dict[str, object]]:
            return [dict(item) for item in self.jar]

        def add_cookies(self, cookies) -> None:
            self.jar.extend(dict(item) for item in cookies)

    context = PartitionContext()
    delete_params: list[dict[str, object]] = []

    def send(method: str, params=None):
        if method == "Network.deleteCookies":
            delete_params.append(dict(params))
            partition = params.get("partitionKey") or {}
            context.jar = [
                item
                for item in context.jar
                if not (
                    item["name"] == params["name"]
                    and item["domain"] == params["domain"]
                    and item["path"] == params["path"]
                    and item.get("partitionKey") == partition.get("topLevelSite")
                    and item.get("_crHasCrossSiteAncestor", True)
                    == partition.get("hasCrossSiteAncestor")
                )
            ]
        return {}

    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._header_cdp_session = SimpleNamespace(send=send)
    driver._is_running = True

    driver.apply_cookie_delta(
        [],
        [("partitioned", "third.example", "/", "https://top.example")],
    )

    assert context.jar == []
    assert delete_params[0]["partitionKey"] == {
        "topLevelSite": "https://top.example",
        "hasCrossSiteAncestor": True,
    }
    assert driver.last_error_status is None


def test_playwright_partition_delete_fails_when_cdp_silently_does_nothing() -> None:
    cookie = {
        "name": "partitioned",
        "value": "private",
        "domain": "third.example",
        "path": "/",
        "secure": True,
        "partitionKey": "https://top.example",
        "_crHasCrossSiteAncestor": False,
    }
    context = MagicMock()
    context.cookies.return_value = [dict(cookie)]
    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._header_cdp_session = MagicMock()
    driver._is_running = True

    driver.apply_cookie_delta(
        [],
        [("partitioned", "third.example", "/", "https://top.example")],
    )

    assert driver.last_error_status is BrowserResultStatus.ERROR
    assert driver.last_error_code == "BROWSER_COOKIE_SYNC_FAILED"


def test_playwright_expired_chips_upsert_deletes_only_target_variant() -> None:
    base = {
        "name": "partitioned",
        "domain": "third.example",
        "path": "/",
        "secure": True,
        "partitionKey": "https://top.example",
    }

    class PartitionContext:
        def __init__(self) -> None:
            self.jar = [
                {**base, "value": "target", "_crHasCrossSiteAncestor": False},
                {**base, "value": "preserved", "_crHasCrossSiteAncestor": True},
            ]

        def cookies(self) -> list[dict[str, object]]:
            return [dict(item) for item in self.jar]

        def add_cookies(self, cookies) -> None:
            self.jar.extend(dict(item) for item in cookies)

    context = PartitionContext()

    def send(method: str, params=None):
        if method == "Network.deleteCookies":
            partition = params.get("partitionKey") or {}
            context.jar = [
                item
                for item in context.jar
                if not (
                    item["name"] == params["name"]
                    and item["domain"] == params["domain"]
                    and item["path"] == params["path"]
                    and item.get("partitionKey") == partition.get("topLevelSite")
                    and item.get("_crHasCrossSiteAncestor") == partition.get("hasCrossSiteAncestor")
                )
            ]
        return {}

    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._header_cdp_session = SimpleNamespace(send=send)
    driver._is_running = True

    driver.set_cookies(
        [
            {
                **base,
                "value": "expired",
                "expires": 0,
                "_crHasCrossSiteAncestor": False,
            }
        ]
    )

    assert driver.last_error_status is None
    assert context.jar == [{**base, "value": "preserved", "_crHasCrossSiteAncestor": True}]


def test_playwright_unflagged_expired_chips_targets_default_true_variant() -> None:
    base = {
        "name": "partitioned",
        "domain": "third.example",
        "path": "/",
        "secure": True,
        "partitionKey": "https://top.example",
    }

    class PartitionContext:
        def __init__(self) -> None:
            self.jar = [
                {**base, "value": "keep", "_crHasCrossSiteAncestor": False},
                {**base, "value": "delete", "_crHasCrossSiteAncestor": True},
            ]

        def cookies(self) -> list[dict[str, object]]:
            return [dict(item) for item in self.jar]

        def add_cookies(self, cookies) -> None:
            self.jar.extend(dict(item) for item in cookies)

    context = PartitionContext()

    def send(method: str, params=None):
        if method == "Network.deleteCookies":
            partition = params.get("partitionKey") or {}
            context.jar = [
                item
                for item in context.jar
                if not (
                    item["name"] == params["name"]
                    and item["domain"] == params["domain"]
                    and item["path"] == params["path"]
                    and item.get("partitionKey") == partition.get("topLevelSite")
                    and item.get("_crHasCrossSiteAncestor") == partition.get("hasCrossSiteAncestor")
                )
            ]
        return {}

    driver = PlaywrightBrowserDriver()
    driver._context = context
    driver._browser = SimpleNamespace(is_connected=lambda: True)
    driver._page = SimpleNamespace(is_closed=lambda: False)
    driver._header_cdp_session = SimpleNamespace(send=send)
    driver._is_running = True

    driver.set_cookies([{**base, "value": "expired", "expires": 0}])

    assert driver.last_error_status is None
    assert context.jar == [{**base, "value": "keep", "_crHasCrossSiteAncestor": False}]


def test_http_rejects_non_finite_cookie_expiry() -> None:
    driver = _http_driver()
    try:
        driver.set_cookies(
            [
                {
                    "name": "sid",
                    "value": "must-not-persist",
                    "domain": "example.test",
                    "path": "/",
                    "expires": float("nan"),
                }
            ]
        )
        assert driver.last_error_code == "BROWSER_INVALID_COOKIE"
        assert driver.get_cookies() == []
    finally:
        driver.close()


def test_session_rejects_non_finite_cookie_expiry(tmp_path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path), db_path="")

    assert (
        manager.save_session(
            "example.test",
            [
                {
                    "name": "sid",
                    "value": "must-not-persist",
                    "domain": "example.test",
                    "path": "/",
                    "expires": float("inf"),
                }
            ],
        )
        is False
    )


def test_playwright_direct_cookie_canonicalizes_url_path_and_unicode_host() -> None:
    context = _InMemoryPlaywrightCookieContext()
    driver = _playwright_cookie_driver(context)

    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "direct",
                "url": "https://bücher.example/account/login",
            }
        ]
    )

    assert driver.last_error_status is None
    assert driver.get_cookies() == [
        {
            "name": "sid",
            "value": "direct",
            "domain": "xn--bcher-kva.example",
            "path": "/account/",
            "secure": True,
        }
    ]


def test_mock_cookie_canonicalizes_url_path_and_unicode_host() -> None:
    driver = MockBrowserDriver()
    assert driver.launch() is True

    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "mock",
                "url": "https://bücher.example/account/login",
            }
        ]
    )

    assert driver.get_cookies() == [
        {
            "name": "sid",
            "value": "mock",
            "domain": "xn--bcher-kva.example",
            "path": "/account/",
            "secure": True,
        }
    ]


def test_http_cookie_canonicalizes_url_path_and_unicode_host() -> None:
    driver = _http_driver()
    try:
        driver.set_cookies(
            [
                {
                    "name": "sid",
                    "value": "http",
                    "url": "https://bücher.example/account/login",
                }
            ]
        )

        assert driver.get_cookies() == [
            {
                "name": "sid",
                "value": "http",
                "domain": "xn--bcher-kva.example",
                "path": "/account/",
                "secure": True,
            }
        ]
    finally:
        driver.close()


def test_mock_cookie_uses_uts46_nontransitional_idna() -> None:
    driver = MockBrowserDriver()
    assert driver.launch() is True

    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "uts46",
                "url": "https://faß.de/account/login",
            }
        ]
    )

    assert driver.get_cookies() == [
        {
            "name": "sid",
            "value": "uts46",
            "domain": "xn--fa-hia.de",
            "path": "/account/",
            "secure": True,
        }
    ]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/account/../private/login",
        "https://example.test/account/%2e%2e/private/login",
    ],
)
def test_mock_cookie_normalizes_url_dot_segments_before_default_path(url: str) -> None:
    driver = MockBrowserDriver()
    assert driver.launch() is True

    driver.set_cookies([{"name": "sid", "value": "scoped", "url": url}])

    assert driver.get_cookies() == [
        {
            "name": "sid",
            "value": "scoped",
            "domain": "example.test",
            "path": "/private/",
            "secure": True,
        }
    ]


@pytest.mark.parametrize(
    ("input_domain", "stored_domain"),
    [
        (".localhost", "localhost"),
        (".127.0.0.1", "127.0.0.1"),
        ("[::1]", "[::1]"),
    ],
)
def test_mock_cookie_normalizes_local_and_ip_domain_scope(
    input_domain: str,
    stored_domain: str,
) -> None:
    driver = MockBrowserDriver()
    assert driver.launch() is True

    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "local",
                "domain": input_domain,
                "path": "/",
            }
        ]
    )

    assert driver.get_cookies() == [
        {
            "name": "sid",
            "value": "local",
            "domain": stored_domain,
            "path": "/",
        }
    ]


def test_mock_deletion_canonicalizes_unicode_domain_and_partition_site() -> None:
    driver = MockBrowserDriver()
    assert driver.launch() is True
    driver.set_cookies(
        [
            {
                "name": "partitioned",
                "value": "private",
                "domain": "xn--bcher-kva.example",
                "path": "/account",
                "secure": True,
                "partitionKey": "https://example.com",
                "_crHasCrossSiteAncestor": True,
            }
        ]
    )

    driver.apply_cookie_delta(
        [],
        [
            (
                "partitioned",
                "BÜCHER.EXAMPLE",
                "/account",
                "https://Sub.Example.COM/private",
            )
        ],
    )

    assert driver.last_error_status is None
    assert driver.get_cookies() == []


@pytest.mark.parametrize(
    "cookie",
    [
        {
            "name": "trailing-dot-domain",
            "value": "must-not-persist",
            "domain": "example.test.",
            "path": "/",
        },
        {
            "name": "trailing-dot-url",
            "value": "must-not-persist",
            "url": "https://example.test./private",
        },
        {
            "name": "legacy-ipv4-short",
            "value": "must-not-persist",
            "domain": "127.1",
            "path": "/",
        },
        {
            "name": "legacy-ipv4-integer",
            "value": "must-not-persist",
            "domain": "2130706433",
            "path": "/",
        },
    ],
)
def test_mock_cookie_rejects_noncanonical_host_without_residue(
    cookie: dict[str, object],
) -> None:
    driver = MockBrowserDriver()
    assert driver.launch() is True
    original = {
        "name": "preserved",
        "value": "original",
        "domain": "example.test",
        "path": "/",
    }
    driver.set_cookies([original])

    driver.set_cookies([cookie])
    error_code = driver.last_error_code
    observed = driver.get_cookies()

    assert error_code == "BROWSER_INVALID_COOKIE"
    assert observed == [original]


@pytest.mark.parametrize("driver_kind", ["playwright", "mock", "http"])
def test_driver_rejects_public_suffix_cookie_without_residue(driver_kind: str) -> None:
    original = {
        "name": "preserved",
        "value": "original",
        "domain": "example.test",
        "path": "/",
    }
    if driver_kind == "playwright":
        context = _InMemoryPlaywrightCookieContext([original])
        driver = _playwright_cookie_driver(context)
    elif driver_kind == "mock":
        driver = MockBrowserDriver()
        assert driver.launch() is True
        driver.set_cookies([original])
    else:
        driver = _http_driver()
        driver.set_cookies([original])

    try:
        driver.set_cookies(
            [
                {
                    "name": "supercookie",
                    "value": "must-not-persist",
                    "domain": ".com",
                    "path": "/",
                }
            ]
        )
        error_code = driver.last_error_code
        observed = driver.get_cookies()

        assert error_code == "BROWSER_INVALID_COOKIE"
        assert observed == [original]
    finally:
        if driver_kind == "http":
            driver.close()


def test_session_accepts_secure_url_scoped_host_and_samesite_none_cookies(
    tmp_path,
) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path), db_path="")
    cookies = [
        {
            "name": "__Host-sid",
            "value": "root-only",
            "url": "https://example.test/",
        },
        {
            "name": "cross-site",
            "value": "secure-none",
            "url": "https://example.test/account/login",
            "sameSite": "None",
        },
    ]

    assert manager.save_session("https://example.test/account/login", cookies) is True
    stored = manager.load_session("example.test")
    assert stored is not None
    assert stored["cookies"] == [
        {
            "name": "__Host-sid",
            "value": "root-only",
            "domain": "example.test",
            "path": "/",
            "secure": True,
        },
        {
            "name": "cross-site",
            "value": "secure-none",
            "domain": "example.test",
            "path": "/account/",
            "secure": True,
            "sameSite": "None",
        },
    ]

    driver = MockBrowserDriver()
    assert driver.launch() is True
    assert manager.apply_to_driver(driver, "https://example.test/account/login") is True
    assert driver.get_cookies() == stored["cookies"]


def test_legacy_session_cookie_without_path_defaults_to_root(tmp_path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path), db_path="")
    (tmp_path / "example.test.json").write_text(
        """{
  "domain": "example.test",
  "cookies": [
    {"name": "legacy", "value": "compatible", "domain": "example.test"}
  ],
  "local_storage": {},
  "local_storage_origin": "",
  "user_agent": "legacy-agent"
}
""",
        encoding="utf-8",
    )

    stored = manager.load_session("example.test")
    assert stored is not None
    assert stored["cookies"] == [
        {
            "name": "legacy",
            "value": "compatible",
            "domain": "example.test",
            "path": "/",
        }
    ]

    driver = MockBrowserDriver()
    assert driver.launch() is True
    assert manager.apply_to_driver(driver, "https://example.test/private") is True
    assert driver.get_cookies() == stored["cookies"]


def test_session_dedup_preserves_both_chips_ancestor_variants(tmp_path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path), db_path="")
    base_cookie = {
        "name": "partitioned",
        "domain": "third.example.com",
        "path": "/",
        "secure": True,
        "partitionKey": "https://Sub.Example.COM/private",
    }
    cookies = [
        {**base_cookie, "value": "stale", "_crHasCrossSiteAncestor": False},
        {**base_cookie, "value": "cross-site", "_crHasCrossSiteAncestor": True},
        {**base_cookie, "value": "fresh", "_crHasCrossSiteAncestor": False},
    ]
    assert manager.save_session("https://third.example.com/private", cookies) is True

    driver = MockBrowserDriver()
    assert driver.launch() is True
    assert manager.apply_to_driver(driver, "https://third.example.com/private") is True

    observed = sorted(
        driver.get_cookies(),
        key=lambda cookie: bool(cookie["_crHasCrossSiteAncestor"]),
    )
    assert [
        (
            cookie["_crHasCrossSiteAncestor"],
            cookie["value"],
            cookie["partitionKey"],
        )
        for cookie in observed
    ] == [
        (False, "fresh", "https://example.com"),
        (True, "cross-site", "https://example.com"),
    ]


@pytest.mark.parametrize("driver_kind", ["playwright", "mock", "http"])
def test_driver_rejects_insecure_partitioned_cookie_without_residue(
    driver_kind: str,
) -> None:
    if driver_kind == "playwright":
        context = _InMemoryPlaywrightCookieContext()
        driver = _playwright_cookie_driver(context)
    elif driver_kind == "mock":
        driver = MockBrowserDriver()
        assert driver.launch() is True
    else:
        driver = _http_driver()

    try:
        driver.set_cookies(
            [
                {
                    "name": "partitioned",
                    "value": "must-not-persist",
                    "domain": "third.example",
                    "path": "/",
                    "partitionKey": "https://top.example",
                }
            ]
        )
        error_code = driver.last_error_code
        observed = driver.get_cookies()

        assert error_code == "BROWSER_INVALID_COOKIE"
        assert observed == []
    finally:
        if driver_kind == "http":
            driver.close()


def test_session_rejects_insecure_partitioned_cookie(tmp_path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path), db_path="")

    assert (
        manager.save_session(
            "third.example",
            [
                {
                    "name": "partitioned",
                    "value": "must-not-persist",
                    "domain": "third.example",
                    "path": "/",
                    "partitionKey": "https://top.example",
                }
            ],
        )
        is False
    )


def test_http_cookie_store_preserves_chips_ancestor_variant() -> None:
    driver = _http_driver()
    cookie = {
        "name": "partitioned",
        "value": "metadata",
        "domain": "third.example",
        "path": "/",
        "secure": True,
        "partitionKey": "https://top.example",
        "_crHasCrossSiteAncestor": True,
    }
    try:
        driver.set_cookies([cookie])

        assert driver.last_error_status is None
        assert driver.get_cookies() == [cookie]
    finally:
        driver.close()


@pytest.mark.parametrize("driver_kind", ["playwright", "mock", "http"])
@pytest.mark.parametrize("expires", [-2, -0.5])
def test_driver_rejects_unsupported_negative_cookie_expiry(
    driver_kind: str,
    expires: float,
) -> None:
    if driver_kind == "playwright":
        driver = _playwright_cookie_driver(_InMemoryPlaywrightCookieContext())
    elif driver_kind == "mock":
        driver = MockBrowserDriver()
        assert driver.launch() is True
    else:
        driver = _http_driver()
    try:
        driver.set_cookies(
            [
                {
                    "name": "sid",
                    "value": "must-not-persist",
                    "domain": "example.test",
                    "path": "/",
                    "expires": expires,
                }
            ]
        )
        error_code = driver.last_error_code
        observed = driver.get_cookies()

        assert error_code == "BROWSER_INVALID_COOKIE"
        assert observed == []
    finally:
        if driver_kind == "http":
            driver.close()


def test_session_rejects_unsupported_negative_cookie_expiry(tmp_path) -> None:
    manager = BrowserSessionManager(storage_dir=str(tmp_path), db_path="")

    assert (
        manager.save_session(
            "example.test",
            [
                {
                    "name": "sid",
                    "value": "must-not-persist",
                    "domain": "example.test",
                    "path": "/",
                    "expires": -2,
                }
            ],
        )
        is False
    )


@pytest.mark.parametrize("path", ["/a\\b", "/a;b", "/line\nbreak"])
def test_mock_cookie_rejects_path_chromium_would_rewrite(path: str) -> None:
    driver = MockBrowserDriver()
    assert driver.launch() is True

    driver.set_cookies(
        [
            {
                "name": "sid",
                "value": "must-not-persist",
                "domain": "example.test",
                "path": path,
            }
        ]
    )

    assert driver.last_error_code == "BROWSER_INVALID_COOKIE"
    assert driver.get_cookies() == []


@pytest.mark.parametrize("driver_kind", ["playwright", "mock", "http"])
def test_cookie_delta_classifies_invalid_upsert_before_mutation(driver_kind: str) -> None:
    if driver_kind == "playwright":
        driver = _playwright_cookie_driver(_InMemoryPlaywrightCookieContext())
    elif driver_kind == "mock":
        driver = MockBrowserDriver()
        assert driver.launch() is True
    else:
        driver = _http_driver()
    try:
        driver.apply_cookie_delta(
            [
                {
                    "name": "sid",
                    "value": "must-not-persist",
                    "domain": "example.test",
                    "path": "/a\\b",
                }
            ],
            [],
        )
        error_code = driver.last_error_code
        observed = driver.get_cookies()

        assert error_code == "BROWSER_INVALID_COOKIE"
        assert observed == []
    finally:
        if driver_kind == "http":
            driver.close()
