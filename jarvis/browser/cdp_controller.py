"""Backward-compatible browser controller backed by the canonical browser layer.

This module intentionally contains no Playwright implementation. Legacy callers keep
their public API while all browser work is delegated to ``BaseBrowserDriver`` and
``BrowserActionExecutor``.
"""

from __future__ import annotations

import base64
import importlib.util
import logging
import os
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from jarvis.browser.actions import BrowserActionExecutor
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.driver import (
    BaseBrowserDriver,
    CDPBrowserDriver,
    MockBrowserDriver,
    PlaywrightBrowserDriver,
)
from jarvis.browser.models import (
    BrowserActionResult,
    BrowserDriverType,
    BrowserResultStatus,
)
from jarvis.browser.models import (
    BrowserConfig as CanonicalBrowserConfig,
)
from jarvis.security.prompt_guard import PromptGuard

log = logging.getLogger("jarvis.browser.cdp")


def _safe_failure_url(url: str) -> str:
    """Return only a credential-free origin for failed legacy payloads."""

    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme}://{host}{port}"
    except (TypeError, ValueError):
        return ""


@dataclass
class BrowserConfig:
    """Legacy configuration mapped to :mod:`jarvis.browser.models`.

    An empty ``cdp_endpoint`` selects a real local Playwright browser. Supplying an
    endpoint opts into the canonical CDP driver. Mocking is controlled only by the
    explicit ``is_mock`` constructor argument on :class:`BrowserCDPController`.
    """

    headless: bool = False
    browser_type: str = "chromium"
    slow_mo_ms: int = 50
    timeout_ms: int = 15000
    screenshot_dir: str = ""
    user_data_dir: str = ""
    proxy: str | None = None
    cdp_endpoint: str | None = ""


@dataclass
class PageInfo:
    """Legacy page payload enriched with the canonical outcome contract."""

    url: str
    title: str
    content_md: str = ""
    screenshot_path: str = ""
    links: list[str] = field(default_factory=list)
    success: bool = True
    status: BrowserResultStatus | str | None = None
    error_code: str | None = None
    error_message: str | None = None
    driver_type: BrowserDriverType | None = None

    def __post_init__(self) -> None:
        legacy_success = self.success
        if self.status is None:
            self.status = (
                BrowserResultStatus.SUCCESS
                if self.success and self.title.strip().lower() != "error"
                else BrowserResultStatus.ERROR
            )
        elif not isinstance(self.status, BrowserResultStatus):
            try:
                self.status = BrowserResultStatus(str(self.status).upper())
            except ValueError:
                self.status = BrowserResultStatus.ERROR

        # A legacy ``title='Error'`` payload can never represent success.
        if self.status is BrowserResultStatus.SUCCESS and (
            not legacy_success
            or not self.url
            or self.title.strip().lower() == "error"
        ):
            self.status = BrowserResultStatus.ERROR
        self.success = self.status is BrowserResultStatus.SUCCESS
        if self.success:
            self.error_code = None
            self.error_message = None
        else:
            self.error_code = self.error_code or "BROWSER_ERROR"
            self.error_message = self.error_message or "The browser action failed."


@dataclass
class ElementResult:
    found: bool
    selector: str
    text: str = ""
    value: str = ""
    href: str = ""


class BrowserCDPController:
    """Compatibility adapter over the canonical browser driver/action seams."""

    def __init__(
        self,
        config: BrowserConfig | None = None,
        is_mock: bool = False,
    ) -> None:
        self.config = config or BrowserConfig()
        self.is_mock = bool(is_mock)
        self._lock = threading.RLock()
        self._driver: BaseBrowserDriver | None = None
        self._actions: BrowserActionExecutor | None = None
        self._agent: BrowserAgent | None = None
        self._closed_explicitly = False
        self._selected_driver_type = self._resolve_driver_type()
        self._last_status: BrowserResultStatus | None = None
        self._last_error_code: str | None = None
        self._last_error_message: str | None = None
        log.info(
            "BrowserCDPController initialized (driver=%s, headless=%s)",
            self._selected_driver_type.value,
            self.config.headless,
        )

    @property
    def driver_type(self) -> BrowserDriverType:
        """Report the concrete driver selected/used by this adapter."""

        return self._driver.driver_type if self._driver is not None else self._selected_driver_type

    @property
    def last_status(self) -> BrowserResultStatus | None:
        return self._last_status

    @property
    def last_error_code(self) -> str | None:
        return self._last_error_code

    @property
    def last_error_message(self) -> str | None:
        return self._last_error_message

    def _resolve_driver_type(self) -> BrowserDriverType:
        if self.is_mock:
            return BrowserDriverType.MOCK
        if (self.config.cdp_endpoint or "").strip():
            return BrowserDriverType.CDP
        return BrowserDriverType.PLAYWRIGHT

    def _canonical_config(self) -> CanonicalBrowserConfig:
        return CanonicalBrowserConfig(
            driver_type=self._selected_driver_type,
            headless=self.config.headless,
            timeout_ms=self.config.timeout_ms,
            slow_mo_ms=self.config.slow_mo_ms,
            proxy=self.config.proxy,
            session_storage_dir=self.config.user_data_dir,
            cdp_endpoint=self.config.cdp_endpoint or "http://127.0.0.1:9222",
        )

    def _make_driver(self, config: CanonicalBrowserConfig) -> BaseBrowserDriver:
        if self._selected_driver_type is BrowserDriverType.MOCK:
            return MockBrowserDriver(config)
        if self._selected_driver_type is BrowserDriverType.CDP:
            return CDPBrowserDriver(config)
        return PlaywrightBrowserDriver(config)

    @staticmethod
    def _coerce_status(value: BrowserResultStatus | str | None) -> BrowserResultStatus:
        if isinstance(value, BrowserResultStatus):
            return value
        if value is not None:
            try:
                return BrowserResultStatus(str(value).upper())
            except ValueError:
                pass
        return BrowserResultStatus.ERROR

    @staticmethod
    def _safe_error_message(status: BrowserResultStatus) -> str:
        messages = {
            BrowserResultStatus.TIMEOUT: "The browser action timed out.",
            BrowserResultStatus.NOT_CONFIGURED: "The browser is not configured.",
            BrowserResultStatus.UNAVAILABLE: "The browser driver is unavailable.",
            BrowserResultStatus.AUTH_FAILED: "Browser authentication failed.",
            BrowserResultStatus.RATE_LIMITED: "The browser request was rate limited.",
            BrowserResultStatus.BLOCKED: "The browser action was blocked.",
            BrowserResultStatus.CANCELLED: "The browser action was cancelled.",
            BrowserResultStatus.DISCONNECTED: "The browser session is disconnected.",
            BrowserResultStatus.ERROR: "The browser action failed.",
        }
        return messages.get(status, "The browser action failed.")

    def _mark_success(self) -> None:
        self._last_status = BrowserResultStatus.SUCCESS
        self._last_error_code = None
        self._last_error_message = None

    def _mark_failure(
        self,
        status: BrowserResultStatus,
        error_code: str,
    ) -> None:
        self._last_status = status
        self._last_error_code = error_code
        self._last_error_message = self._safe_error_message(status)

    def _remember_result(self, result: BrowserActionResult) -> bool:
        status = self._coerce_status(result.status)
        if result.success and status is BrowserResultStatus.SUCCESS:
            self._mark_success()
            return True
        self._mark_failure(status, result.error_code or "BROWSER_ERROR")
        return False

    # ------------------------------------------------------------------
    # Availability and lifecycle
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        if self._selected_driver_type is BrowserDriverType.MOCK:
            return True
        if importlib.util.find_spec("playwright") is None:
            return False
        if self._selected_driver_type is BrowserDriverType.CDP:
            if self._driver is not None and self._driver.is_running():
                return True
            candidate = CDPBrowserDriver(self._canonical_config())
            launched = False
            closed = False
            try:
                launched = candidate.launch(self._canonical_config())
            except Exception:
                launched = False
            finally:
                try:
                    closed = candidate.close()
                except Exception:
                    closed = False
            return launched and closed
        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            try:
                return Path(playwright.chromium.executable_path).is_file()
            finally:
                playwright.stop()
        except Exception:
            return False

    def launch(self) -> bool:
        """Launch exactly the configured canonical driver, without silent fallback."""

        with self._lock:
            self._closed_explicitly = False
            if self._driver is not None and self._driver.is_running():
                self._mark_success()
                return True

            # The canonical Playwright driver currently supports Chromium only.
            if (
                self._selected_driver_type is BrowserDriverType.PLAYWRIGHT
                and self.config.browser_type.lower().strip() != "chromium"
            ):
                self._mark_failure(
                    BrowserResultStatus.UNAVAILABLE,
                    "BROWSER_TYPE_UNAVAILABLE",
                )
                return False

            stale_driver = self._driver
            self._driver = None
            self._actions = None
            self._agent = None
            if stale_driver is not None:
                try:
                    stale_driver.close()
                except Exception:
                    pass

            canonical_config = self._canonical_config()
            driver = self._make_driver(canonical_config)
            agent = (
                BrowserAgent(config=canonical_config, driver=driver)
                if self.config.user_data_dir
                else None
            )
            try:
                launched = agent.start() if agent is not None else driver.launch()
            except Exception as exc:
                log.error("Canonical browser launch failed (%s).", type(exc).__name__)
                launched = False

            if launched and driver.is_running():
                self._driver = driver
                self._agent = agent
                self._actions = (
                    agent.actions if agent is not None else BrowserActionExecutor(driver)
                )
                self._mark_success()
                return True

            status = driver.last_error_status or BrowserResultStatus.UNAVAILABLE
            code = driver.last_error_code or "BROWSER_DRIVER_UNAVAILABLE"
            try:
                driver.close()
            except Exception:
                pass
            self._driver = None
            self._actions = None
            self._agent = None
            self._mark_failure(status, code)
            return False

    def close(self) -> bool:
        """Close the canonical driver and report whether cleanup was verified."""

        with self._lock:
            driver = self._driver
            self._driver = None
            self._actions = None
            self._agent = None
            self._closed_explicitly = True
            if driver is None:
                self._mark_failure(
                    BrowserResultStatus.DISCONNECTED,
                    "BROWSER_NO_ACTIVE_SESSION",
                )
                return False
            try:
                closed = driver.close()
                if closed is not True or driver.is_running():
                    self._mark_failure(
                        BrowserResultStatus.ERROR,
                        "BROWSER_CLOSE_FAILED",
                    )
                    return False
            except Exception as exc:
                log.debug("Canonical browser close failed (%s).", type(exc).__name__)
                self._mark_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_CLOSE_FAILED",
                )
                return False
            self._mark_success()
            return True

    def _ensure_launched(self) -> bool:
        with self._lock:
            if self._closed_explicitly:
                self._mark_failure(
                    BrowserResultStatus.DISCONNECTED,
                    "BROWSER_DISCONNECTED",
                )
                return False
            if self._driver is not None:
                if self._driver.is_running():
                    return True
                self._mark_failure(
                    self._driver.last_error_status or BrowserResultStatus.DISCONNECTED,
                    self._driver.last_error_code or "BROWSER_DISCONNECTED",
                )
                return False
            return self.launch()

    # ------------------------------------------------------------------
    # Navigation and interaction
    # ------------------------------------------------------------------

    def _failure_page(self, url: str) -> PageInfo:
        status = self._last_status or BrowserResultStatus.UNAVAILABLE
        code = self._last_error_code or "BROWSER_DRIVER_UNAVAILABLE"
        message = self._last_error_message or self._safe_error_message(status)
        return PageInfo(
            url=_safe_failure_url(url),
            title="Error",
            content_md="Browser không khởi động được."
            if status is BrowserResultStatus.UNAVAILABLE
            else message,
            success=False,
            status=status,
            error_code=code,
            error_message=message,
            driver_type=self.driver_type,
        )

    def navigate(self, url: str) -> PageInfo:
        """Navigate through ``BrowserActionExecutor`` and normalize the result."""

        target = url
        if not target.startswith(("http://", "https://")):
            target = "https://www.google.com/search?q=" f"{urllib.parse.quote_plus(target)}"

        if not self._ensure_launched():
            return self._failure_page(target)

        if self._agent is not None:
            result = self._agent.navigate(target)
        else:
            assert self._actions is not None
            result = self._actions.navigate(target)
        success = self._remember_result(result)
        if success:
            if not result.url:
                self._mark_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_NAVIGATION_UNVERIFIED",
                )
                success = False
            elif result.title.strip().lower() == "error":
                self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_INVALID_PAGE")
                success = False

        if not success:
            return PageInfo(
                url=_safe_failure_url(result.url or target),
                title="",
                content_md=self.last_error_message or "The browser action failed.",
                success=False,
                status=self.last_status,
                error_code=self.last_error_code,
                error_message=self.last_error_message,
                driver_type=result.driver_type or self.driver_type,
            )

        return PageInfo(
            url=result.url,
            title=result.title,
            success=True,
            status=BrowserResultStatus.SUCCESS,
            driver_type=result.driver_type or self.driver_type,
        )

    def get_current_url(self) -> str:
        if self._driver is None:
            return ""
        try:
            return self._driver.get_current_url()
        except Exception:
            return ""

    def click(self, selector: str, timeout_ms: int | None = None) -> bool:
        if not self._ensure_launched():
            return False
        assert self._actions is not None
        result = self._actions.click_element(
            selector,
            timeout_ms=timeout_ms or self.config.timeout_ms,
        )
        return self._remember_result(result)

    def type_text(self, selector: str, text: str, clear_first: bool = True) -> bool:
        if not self._ensure_launched():
            return False
        assert self._actions is not None
        result = self._actions.fill_text(
            selector,
            text,
            clear=clear_first,
            delay_ms=30,
        )
        return self._remember_result(result)

    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int | None = None,
    ) -> bool:
        if not self._ensure_launched():
            return False
        assert self._actions is not None
        result = self._actions.wait_for_selector(
            selector,
            state=state,
            timeout_ms=timeout_ms or self.config.timeout_ms,
        )
        return self._remember_result(result)

    def press_key(self, key: str) -> bool:
        """Keep the legacy method honest until the canonical seam supports keys."""

        if not self._ensure_launched():
            return False
        if self.driver_type is BrowserDriverType.MOCK:
            self._mark_success()
            return True
        self._mark_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
        )
        return False

    def scroll(self, direction: str = "down", amount: int = 500) -> bool:
        normalized_direction = direction.lower().strip()
        if normalized_direction not in {"down", "up", "top", "bottom"}:
            self._mark_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_SCROLL_DIRECTION",
            )
            return False
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            self._mark_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_SCROLL_DISTANCE",
            )
            return False
        if not self._ensure_launched():
            return False
        assert self._actions is not None
        result = self._actions.scroll_page(
            direction=normalized_direction,
            distance=amount,
        )
        return self._remember_result(result)

    def search_google(self, query: str) -> PageInfo:
        search_url = "https://www.google.com/search?q=" f"{urllib.parse.quote_plus(query)}"
        page = self.navigate(search_url)
        if page.success:
            page.content_md = f"🔍 Đang tìm kiếm: **{query}**\nURL: {page.url}"
        return page

    # ------------------------------------------------------------------
    # Screenshot and content
    # ------------------------------------------------------------------

    def _screenshot_root(self) -> Path:
        if self.config.screenshot_dir:
            return Path(self.config.screenshot_dir)
        app_data = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return Path(app_data) / "JARVIS" / "screenshots"

    @staticmethod
    def _looks_like_image(raw: bytes) -> bool:
        return raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")

    def screenshot(self, filename: str = "") -> str:
        if not self._ensure_launched():
            return ""
        assert self._actions is not None
        result = self._actions.take_screenshot(full_page=False)
        if not self._remember_result(result) or not result.screenshot_b64:
            if self.last_status is BrowserResultStatus.SUCCESS:
                self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_SCREENSHOT_EMPTY")
            return ""

        try:
            raw = base64.b64decode(result.screenshot_b64, validate=True)
        except (ValueError, TypeError):
            self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_SCREENSHOT_INVALID")
            return ""
        if not self._looks_like_image(raw):
            self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_SCREENSHOT_INVALID")
            return ""

        safe_name = Path(filename).name if filename else ""
        if not safe_name:
            safe_name = f"browser_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = self._screenshot_root() / safe_name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            if not path.is_file() or path.stat().st_size != len(raw):
                raise OSError("incomplete screenshot write")
        except OSError as exc:
            log.error("Browser screenshot write failed (%s).", type(exc).__name__)
            self._mark_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_SCREENSHOT_WRITE_FAILED",
            )
            return ""

        self._mark_success()
        return str(path)

    def extract_content_as_markdown(self) -> str:
        if not self._ensure_launched():
            return ""
        assert self._actions is not None
        result = self._actions.read_page()
        if not self._remember_result(result) or not isinstance(result.extracted_data, dict):
            return ""

        raw_content = result.extracted_data.get("text") or result.extracted_data.get("html") or ""
        if not isinstance(raw_content, str) or not raw_content:
            self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_EMPTY_DOCUMENT")
            return ""
        try:
            sanitized = PromptGuard.sanitize(
                raw_content,
                source=self.get_current_url() or "browser_cdp",
            )
        except Exception as exc:
            log.error("Browser content sanitization failed (%s).", type(exc).__name__)
            self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_CONTENT_READ_FAILED")
            return ""
        if not sanitized.clean_text:
            self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_EMPTY_DOCUMENT")
            return ""
        self._mark_success()
        return sanitized.clean_text

    def get_page_links(self, limit: int = 20) -> list[str]:
        if not self._ensure_launched() or self._driver is None:
            return []
        try:
            evaluated = self._driver.evaluate_script(
                """() => Array.from(document.querySelectorAll('a[href]'))
                    .map((anchor) => anchor.href)"""
            )
            if self._driver.last_error_status is not None:
                self._mark_failure(
                    self._driver.last_error_status,
                    self._driver.last_error_code or "BROWSER_CONTENT_READ_FAILED",
                )
                return []
            if isinstance(evaluated, list):
                links = [
                    link
                    for link in evaluated
                    if isinstance(link, str)
                    and link.startswith(("http://", "https://"))
                ]
            else:
                elements = self._driver.find_elements("a[href]")
                links = [
                    element.attributes["href"]
                    for element in elements
                    if element.attributes.get("href", "").startswith(
                        ("http://", "https://")
                    )
                ]
            self._mark_success()
            return links[: max(0, int(limit))]
        except Exception as exc:
            log.error("Browser link extraction failed (%s).", type(exc).__name__)
            self._mark_failure(BrowserResultStatus.ERROR, "BROWSER_CONTENT_READ_FAILED")
            return []

    # ------------------------------------------------------------------
    # Legacy tab management
    # ------------------------------------------------------------------

    def new_tab(self) -> bool:
        if not self._ensure_launched():
            return False
        if self.driver_type is BrowserDriverType.MOCK:
            self._mark_success()
            return True
        self._mark_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
        )
        return False

    def close_tab(self) -> bool:
        if not self._ensure_launched():
            return False
        if self.driver_type is BrowserDriverType.MOCK:
            self._mark_success()
            return True
        self._mark_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
        )
        return False


__all__ = ["BrowserCDPController", "BrowserConfig", "PageInfo"]
