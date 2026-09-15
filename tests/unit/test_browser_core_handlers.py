"""Regression tests for truthful browser results at the core handler seam."""

from __future__ import annotations

import json
from typing import Any

from jarvis.browser.models import (
    BrowserActionResult,
    BrowserConfig,
    BrowserDriverType,
    BrowserResultStatus,
    PriceComparisonItem,
    ScrapeResult,
)
from jarvis.core.app import JarvisApp, _build_browser_config


class _BrowserAgentBoundary:
    """Small browser boundary fake with explicit outcomes for core handler tests."""

    def __init__(
        self,
        *,
        navigate_result: BrowserActionResult | None = None,
        scrape_result: ScrapeResult | None = None,
        fill_form_result: BrowserActionResult | None = None,
        price_items: list[Any] | None = None,
        active_driver_type: BrowserDriverType | None = None,
    ) -> None:
        self.navigate_result = navigate_result
        self.scrape_result = scrape_result
        self.fill_form_result = fill_form_result
        self.price_items = price_items
        self.active_driver_type = active_driver_type

    def navigate(self, *, url: str) -> BrowserActionResult:
        assert self.navigate_result is not None
        return self.navigate_result

    def scrape_page(self, *, url: str, extract_tables: bool) -> ScrapeResult:
        assert self.scrape_result is not None
        return self.scrape_result

    def compare_prices(self, *, product: str, stores: list[str]) -> list[Any]:
        assert self.price_items is not None
        return self.price_items

    def fill_form(
        self,
        *,
        url: str,
        form_fields: dict[str, str],
        submit_selector: str | None,
    ) -> BrowserActionResult:
        assert self.fill_form_result is not None
        return self.fill_form_result

    def get_active_driver_type(self) -> BrowserDriverType | None:
        return self.active_driver_type


def _app_with_browser_agent(agent: Any) -> JarvisApp:
    app = JarvisApp.__new__(JarvisApp)
    app.browser_agent = agent
    return app


def test_navigate_failure_preserves_browser_outcome() -> None:
    result = BrowserActionResult(
        success=True,
        action="navigate",
        status=BrowserResultStatus.TIMEOUT,
        error_code="BROWSER_NAVIGATION_TIMEOUT",
        error_message="Navigation timed out.",
        driver_type=BrowserDriverType.HTTP_SCRAPER,
    )
    app = _app_with_browser_agent(_BrowserAgentBoundary(navigate_result=result))

    response = app._handle_browser_navigate("https://example.test/slow")

    assert response["success"] is False
    assert response["status"] == "failed"
    assert response["result_status"] == "TIMEOUT"
    assert response["error_code"] == "BROWSER_NAVIGATION_TIMEOUT"
    assert response["driver_type"] == "http_scraper"


def test_navigate_success_reports_the_observed_final_url() -> None:
    result = BrowserActionResult(
        success=True,
        action="navigate",
        url="https://example.test/final",
        title="Redirect complete",
        driver_type=BrowserDriverType.PLAYWRIGHT,
    )
    app = _app_with_browser_agent(_BrowserAgentBoundary(navigate_result=result))

    response = app._handle_browser_navigate("https://example.test/redirect")

    assert response["success"] is True
    assert response["url"] == "https://example.test/final"


def test_navigate_failure_redacts_query_credentials_from_response() -> None:
    secret = "private-token-98765"
    result = BrowserActionResult(
        success=False,
        action="navigate",
        url=f"https://example.test/private?token={secret}",
        title=f"Account page for {secret}",
        status=BrowserResultStatus.ERROR,
        error_code="BROWSER_NAVIGATION_ERROR",
        driver_type=BrowserDriverType.PLAYWRIGHT,
    )
    app = _app_with_browser_agent(_BrowserAgentBoundary(navigate_result=result))

    response = app._handle_browser_navigate(
        f"https://user:{secret}@example.test/private?token={secret}#fragment"
    )

    assert response["success"] is False
    assert secret not in json.dumps(response)


def test_scrape_failure_preserves_browser_outcome() -> None:
    secret = "private-page-title-and-content"
    result = ScrapeResult(
        url="https://example.test/protected",
        title=secret,
        markdown_content=secret,
        text_content=secret,
        status=BrowserResultStatus.BLOCKED,
        error_code="BROWSER_ACCESS_BLOCKED",
        error_message="The page blocked automated access.",
        driver_type=BrowserDriverType.PLAYWRIGHT,
    )
    app = _app_with_browser_agent(_BrowserAgentBoundary(scrape_result=result))

    response = app._handle_browser_scrape("https://example.test/protected")

    assert response["success"] is False
    assert response["status"] == "failed"
    assert response["result_status"] == "BLOCKED"
    assert response["error_code"] == "BROWSER_ACCESS_BLOCKED"
    assert response["driver_type"] == "playwright"
    assert secret not in json.dumps(response)


def test_compare_prices_without_real_offers_fails_closed() -> None:
    app = _app_with_browser_agent(
        _BrowserAgentBoundary(
            price_items=[],
            active_driver_type=BrowserDriverType.HTTP_SCRAPER,
        )
    )

    response = app._handle_browser_compare_prices(
        "missing product",
        stores=["TestStore"],
    )

    assert response["success"] is False
    assert response["status"] == "failed"
    assert response["result_status"] == "UNAVAILABLE"
    assert response["error_code"] == "BROWSER_PRICE_DATA_UNAVAILABLE"
    assert response["driver_type"] == "http_scraper"
    assert response["items"] == []


def test_compare_prices_serializes_real_price_items() -> None:
    item = PriceComparisonItem(
        store_name="TestStore",
        product_title="JARVIS Keyboard",
        price=1_250_000.0,
        product_url="https://example.test/product/keyboard",
    )
    app = _app_with_browser_agent(
        _BrowserAgentBoundary(
            price_items=[item],
            active_driver_type=BrowserDriverType.PLAYWRIGHT,
        )
    )

    response = app._handle_browser_compare_prices(
        "JARVIS Keyboard",
        stores=["TestStore"],
    )

    assert response["success"] is True
    assert response["status"] == "success"
    assert response["result_status"] == "SUCCESS"
    assert response["error_code"] is None
    assert response["driver_type"] == "playwright"
    assert response["items"][0]["store_name"] == "TestStore"
    assert response["items"][0]["price"] == 1_250_000.0
    json.dumps(response)


def test_compare_prices_marks_incomplete_store_coverage_as_partial() -> None:
    item = PriceComparisonItem(
        store_name="TestStore",
        product_title="Evidence-backed Keyboard",
        price=1_250_000.0,
        product_url="https://example.test/product/keyboard",
        source="json_ld",
    )
    app = _app_with_browser_agent(
        _BrowserAgentBoundary(
            price_items=[item],
            active_driver_type=BrowserDriverType.PLAYWRIGHT,
        )
    )

    response = app._handle_browser_compare_prices(
        "JARVIS Keyboard",
        stores=["TestStore", "UnavailableStore"],
    )

    assert response["success"] is True
    assert response["partial"] is True
    assert response["evidenced_stores"] == ["TestStore"]
    assert response["missing_stores"] == ["UnavailableStore"]
    assert "2 sàn" not in response["message"]


def test_fill_form_failure_is_truthful_without_echoing_field_values() -> None:
    username = "private-user-91827"
    password = "secret-password-47511"
    result = BrowserActionResult(
        success=True,
        action="fill_form",
        status=BrowserResultStatus.AUTH_FAILED,
        error_code="BROWSER_FORM_AUTH_FAILED",
        error_message=f"Credentials rejected: {username}/{password}",
        driver_type=BrowserDriverType.CDP,
    )
    app = _app_with_browser_agent(_BrowserAgentBoundary(fill_form_result=result))

    response = app._handle_browser_fill_form(
        "https://example.test/login",
        fields={"#username": username, "#password": password},
        submit_selector="#submit",
    )

    serialized_response = json.dumps(response)
    assert response["success"] is False
    assert response["status"] == "failed"
    assert response["result_status"] == "AUTH_FAILED"
    assert response["error_code"] == "BROWSER_FORM_AUTH_FAILED"
    assert response["driver_type"] == "cdp"
    assert response["field_count"] == 2
    assert "fields" not in response
    assert username not in serialized_response
    assert password not in serialized_response


def test_unconfigured_browser_handler_has_stable_failure_contract() -> None:
    app = _app_with_browser_agent(None)

    response = app._handle_browser_navigate("https://example.test/")

    assert response["success"] is False
    assert response["status"] == "failed"
    assert response["result_status"] == "NOT_CONFIGURED"
    assert response["error_code"] == "BROWSER_AGENT_NOT_CONFIGURED"
    assert response["driver_type"] is None


def test_core_browser_config_maps_every_canonical_runtime_setting() -> None:
    config = _build_browser_config(
        {
            "driver": "cdp",
            "headless": False,
            "user_agent": "JARVIS-T01",
            "viewport_width": 1440,
            "viewport_height": 900,
            "timeout_ms": 12_345,
            "downloads_dir": "browser-downloads",
            "cdp_endpoint": "http://127.0.0.1:9333",
            "proxy": "http://127.0.0.1:8080",
            "accept_downloads": False,
            "slow_mo_ms": 17,
            "extra_headers": {"X-Test": 1},
        },
        session_dir="browser-sessions",
        app_headless=True,
    )

    assert isinstance(config, BrowserConfig)
    assert config.driver_type is BrowserDriverType.CDP
    assert config.headless is False
    assert config.user_agent == "JARVIS-T01"
    assert (config.viewport_width, config.viewport_height) == (1440, 900)
    assert config.timeout_ms == 12_345
    assert config.downloads_dir == "browser-downloads"
    assert config.session_storage_dir == "browser-sessions"
    assert config.cdp_endpoint == "http://127.0.0.1:9333"
    assert config.proxy == "http://127.0.0.1:8080"
    assert config.accept_downloads is False
    assert config.slow_mo_ms == 17
    assert config.extra_headers == {"X-Test": "1"}
