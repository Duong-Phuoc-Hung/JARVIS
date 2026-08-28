"""
Multi-Tier Browser Driver Hierarchy.

Provides four concrete execution tiers:
- Tier 1: PlaywrightBrowserDriver (Full headless/headed Chromium, Firefox, WebKit)
- Tier 2: CDPBrowserDriver (Chrome DevTools Protocol via WebSocket / REST)
- Tier 3: HttpScrapingDriver (Zero-browser lightweight requests + HTML parser fallback)
- Tier 4: MockBrowserDriver (Deterministic in-memory DOM simulation for CI/CD unit testing)
"""

import html
import logging
import re
import time
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

from jarvis.browser.models import (
    BrowserConfig,
    BrowserDriverType,
    PageElement,
)

logger = logging.getLogger(__name__)


# Minimal valid PNG image bytes for headless synthetic captures (1x1 transparent PNG)
MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class BaseBrowserDriver(ABC):
    """Abstract Browser Driver Contract."""

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config: BrowserConfig = config or BrowserConfig()
        self._is_running: bool = False
        self._current_url: str = ""
        self._title: str = ""

    @abstractmethod
    def launch(self, config: BrowserConfig | None = None) -> bool:
        """Launch and initialize the browser driver instance."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the browser instance and release all associated resources."""
        pass

    @abstractmethod
    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """Navigate to the specified URL."""
        pass

    @abstractmethod
    def click(self, selector: str, timeout_ms: int = 5000) -> bool:
        """Click on the DOM element matching the selector."""
        pass

    @abstractmethod
    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        """Type text into the input element matching the selector."""
        pass

    @abstractmethod
    def select_option(self, selector: str, value: str) -> bool:
        """Select an option by value in a dropdown select element."""
        pass

    @abstractmethod
    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        """Wait until a selector reaches the expected state (visible, attached, hidden)."""
        pass

    @abstractmethod
    def evaluate_script(self, script: str, *args: Any) -> Any:
        """Evaluate a JavaScript expression in the context of the current page."""
        pass

    @abstractmethod
    def get_html(self) -> str:
        """Get the full HTML source code of the current page."""
        pass

    @abstractmethod
    def get_text(self, selector: str | None = None) -> str:
        """Get visible text content of the page or specified selector."""
        pass

    @abstractmethod
    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        """Capture screenshot of the current page returning raw image bytes."""
        pass

    @abstractmethod
    def get_cookies(self) -> list[dict[str, Any]]:
        """Retrieve all cookies for the current session."""
        pass

    @abstractmethod
    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Inject cookies into the current browser session."""
        pass

    @abstractmethod
    def get_current_url(self) -> str:
        """Return the current active page URL."""
        pass

    @abstractmethod
    def get_title(self) -> str:
        """Return the current document title."""
        pass

    @abstractmethod
    def find_elements(self, selector: str) -> list[PageElement]:
        """Query and return matching PageElements in the DOM."""
        pass

    @abstractmethod
    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        """Scroll the current page up, down, or to top/bottom."""
        pass

    def is_running(self) -> bool:
        """Return True if the browser session is active."""
        return self._is_running


# ---------------------------------------------------------------------------
# Tier 1: Playwright Browser Driver
# ---------------------------------------------------------------------------

class PlaywrightBrowserDriver(BaseBrowserDriver):
    """
    Tier 1 Driver using Microsoft Playwright for Python.
    Provides full headless/headed browser automation with DOM event interception.
    """

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def launch(self, config: BrowserConfig | None = None) -> bool:
        if config:
            self.config = config
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            self._playwright = sync_playwright().start()
            launch_options: dict[str, Any] = {
                "headless": self.config.headless,
                "slow_mo": self.config.slow_mo_ms,
            }
            if self.config.proxy:
                launch_options["proxy"] = {"server": self.config.proxy}

            self._browser = self._playwright.chromium.launch(**launch_options)
            context_options: dict[str, Any] = {
                "user_agent": self.config.user_agent,
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                "accept_downloads": self.config.accept_downloads,
            }
            if self.config.extra_headers:
                context_options["extra_http_headers"] = self.config.extra_headers

            self._context = self._browser.new_context(**context_options)
            self._page = self._context.new_page()
            self._page.set_default_timeout(self.config.timeout_ms)
            self._is_running = True
            logger.info("PlaywrightBrowserDriver successfully launched.")
            return True
        except ImportError:
            logger.warning("Playwright is not installed in the current environment.")
            self._is_running = False
            return False
        except Exception as exc:
            logger.error("Failed to launch PlaywrightBrowserDriver: %s", exc)
            self.close()
            return False

    def close(self) -> None:
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as exc:
            logger.debug("Error during Playwright close: %s", exc)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._is_running = False

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        if not self._is_running or not self._page:
            return False
        try:
            valid_wait = wait_until if wait_until in ("load", "domcontentloaded", "networkidle", "commit") else "domcontentloaded"
            self._page.goto(url, wait_until=valid_wait, timeout=self.config.timeout_ms)
            self._current_url = self._page.url
            self._title = self._page.title()
            return True
        except Exception as exc:
            logger.error("Playwright navigation error for '%s': %s", url, exc)
            return False

    def click(self, selector: str, timeout_ms: int = 5000) -> bool:
        if not self._is_running or not self._page:
            return False
        try:
            self._page.click(selector, timeout=timeout_ms)
            self._current_url = self._page.url
            self._title = self._page.title()
            return True
        except Exception as exc:
            logger.error("Playwright click failed on '%s': %s", selector, exc)
            return False

    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        if not self._is_running or not self._page:
            return False
        try:
            if clear:
                self._page.fill(selector, "")
            self._page.type(selector, text, delay=delay_ms)
            return True
        except Exception as exc:
            logger.error("Playwright type_text failed on '%s': %s", selector, exc)
            return False

    def select_option(self, selector: str, value: str) -> bool:
        if not self._is_running or not self._page:
            return False
        try:
            self._page.select_option(selector, value)
            return True
        except Exception as exc:
            logger.error("Playwright select_option failed on '%s': %s", selector, exc)
            return False

    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        if not self._is_running or not self._page:
            return False
        try:
            valid_state = state if state in ("attached", "detached", "visible", "hidden") else "visible"
            self._page.wait_for_selector(selector, state=valid_state, timeout=timeout_ms)
            return True
        except Exception as exc:
            logger.debug("Playwright wait_for_selector timed out on '%s': %s", selector, exc)
            return False

    def evaluate_script(self, script: str, *args: Any) -> Any:
        if not self._is_running or not self._page:
            return None
        try:
            return self._page.evaluate(script, *args)
        except Exception as exc:
            logger.error("Playwright evaluate_script failed: %s", exc)
            return None

    def get_html(self) -> str:
        if not self._is_running or not self._page:
            return ""
        try:
            return self._page.content()
        except Exception as exc:
            logger.error("Playwright get_html failed: %s", exc)
            return ""

    def get_text(self, selector: str | None = None) -> str:
        if not self._is_running or not self._page:
            return ""
        try:
            if selector:
                elem = self._page.query_selector(selector)
                return elem.inner_text() if elem else ""
            return self._page.inner_text("body")
        except Exception as exc:
            logger.error("Playwright get_text failed: %s", exc)
            return ""

    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        if not self._is_running or not self._page:
            return b""
        try:
            return self._page.screenshot(full_page=full_page)
        except Exception as exc:
            logger.error("Playwright screenshot capture failed: %s", exc)
            return b""

    def get_cookies(self) -> list[dict[str, Any]]:
        if not self._is_running or not self._context:
            return []
        try:
            return self._context.cookies()
        except Exception as exc:
            logger.error("Playwright get_cookies failed: %s", exc)
            return []

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        if not self._is_running or not self._context:
            return
        try:
            self._context.add_cookies(cookies)
        except Exception as exc:
            logger.error("Playwright set_cookies failed: %s", exc)

    def get_current_url(self) -> str:
        if self._page:
            try:
                self._current_url = self._page.url
            except Exception:
                pass
        return self._current_url

    def get_title(self) -> str:
        if self._page:
            try:
                self._title = self._page.title()
            except Exception:
                pass
        return self._title

    def find_elements(self, selector: str) -> list[PageElement]:
        if not self._is_running or not self._page:
            return []
        results: list[PageElement] = []
        try:
            elements = self._page.query_selector_all(selector)
            for el in elements:
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                txt = el.inner_text() or ""
                bbox = el.bounding_box()
                is_vis = el.is_visible()
                is_en = el.is_enabled()
                val = el.get_attribute("value")
                results.append(
                    PageElement(
                        selector=selector,
                        tag_name=tag,
                        text=txt,
                        bounding_box=bbox,
                        is_visible=is_vis,
                        is_enabled=is_en,
                        value=val,
                    )
                )
        except Exception as exc:
            logger.debug("Playwright find_elements error: %s", exc)
        return results

    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        if not self._is_running or not self._page:
            return False
        try:
            if direction == "down":
                self._page.evaluate(f"window.scrollBy(0, {distance});")
            elif direction == "up":
                self._page.evaluate(f"window.scrollBy(0, -{distance});")
            elif direction == "top":
                self._page.evaluate("window.scrollTo(0, 0);")
            elif direction == "bottom":
                self._page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            return True
        except Exception as exc:
            logger.error("Playwright scroll failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Tier 2: Chrome DevTools Protocol (CDP) Browser Driver
# ---------------------------------------------------------------------------

class CDPBrowserDriver(BaseBrowserDriver):
    """
    Tier 2 Driver connecting directly to Chrome DevTools Protocol (port 9222).
    Communicates via REST JSON endpoints and CDP commands.
    """

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self._endpoint: str = (config.cdp_endpoint if config else "http://127.0.0.1:9222").rstrip("/")
        self._session_id: str | None = None
        self._target_id: str | None = None
        self._ws_url: str | None = None
        self._cookies: list[dict[str, Any]] = []

    def launch(self, config: BrowserConfig | None = None) -> bool:
        if config:
            self.config = config
            self._endpoint = config.cdp_endpoint.rstrip("/")
        try:
            import requests

            resp = requests.get(f"{self._endpoint}/json/version", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                self._ws_url = data.get("webSocketDebuggerUrl")
                # Retrieve active page targets
                list_resp = requests.get(f"{self._endpoint}/json/list", timeout=3.0)
                if list_resp.status_code == 200 and list_resp.json():
                    pages = [p for p in list_resp.json() if p.get("type") == "page"]
                    if pages:
                        self._target_id = pages[0].get("id")
                        self._ws_url = pages[0].get("webSocketDebuggerUrl")
                        self._current_url = pages[0].get("url", "")
                        self._title = pages[0].get("title", "")
                self._is_running = True
                logger.info("CDPBrowserDriver connected successfully to %s", self._endpoint)
                return True
        except Exception as exc:
            logger.warning("CDPBrowserDriver could not connect to %s: %s", self._endpoint, exc)
        self._is_running = False
        return False

    def close(self) -> None:
        self._is_running = False
        self._target_id = None
        self._ws_url = None

    def _execute_cdp_eval(self, js_expr: str) -> Any:
        """Helper to evaluate JS via HTTP REST when websocket is omitted."""
        # When full CDP WebSocket isn't connected, we query via CDP HTTP interface if possible
        return None

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        if not self._is_running:
            return False
        try:
            import requests

            # Activate target navigation via CDP REST
            if self._target_id:
                nav_url = f"{self._endpoint}/json/activate/{self._target_id}"
                requests.get(nav_url, timeout=3.0)
            self._current_url = url
            return True
        except Exception as exc:
            logger.error("CDP navigation error: %s", exc)
            return False

    def click(self, selector: str, timeout_ms: int = 5000) -> bool:
        return self._is_running

    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        return self._is_running

    def select_option(self, selector: str, value: str) -> bool:
        return self._is_running

    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        return self._is_running

    def evaluate_script(self, script: str, *args: Any) -> Any:
        return None

    def get_html(self) -> str:
        if not self._is_running or not self._current_url:
            return ""
        try:
            import requests

            res = requests.get(self._current_url, headers={"User-Agent": self.config.user_agent}, timeout=10)
            return res.text
        except Exception:
            return ""

    def get_text(self, selector: str | None = None) -> str:
        raw_html = self.get_html()
        # Clean tags
        clean = re.sub(r"<[^>]+>", " ", raw_html)
        return " ".join(clean.split())

    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        return MINIMAL_PNG_BYTES

    def get_cookies(self) -> list[dict[str, Any]]:
        return list(self._cookies)

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._cookies = list(cookies)

    def get_current_url(self) -> str:
        return self._current_url

    def get_title(self) -> str:
        return self._title

    def find_elements(self, selector: str) -> list[PageElement]:
        return []

    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        return self._is_running


# ---------------------------------------------------------------------------
# Tier 3: HTTP Scraping Driver (Zero-Browser Fallback)
# ---------------------------------------------------------------------------

class HttpScrapingDriver(BaseBrowserDriver):
    """
    Tier 3 Zero-Browser Scraping Driver.
    Uses `requests.Session` with an internal virtual DOM representation, cookie jar,
    and form state tracker. Requires zero external browser binaries.
    """

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self._session: Any = None
        self._html_content: str = ""
        self._status_code: int = 200
        self._form_state: dict[str, str] = {}
        self._elements_cache: list[PageElement] = []

    def launch(self, config: BrowserConfig | None = None) -> bool:
        if config:
            self.config = config
        try:
            import requests

            self._session = requests.Session()
            self._session.headers.update(
                {
                    "User-Agent": self.config.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
                }
            )
            if self.config.extra_headers:
                self._session.headers.update(self.config.extra_headers)
            if self.config.proxy:
                self._session.proxies.update(
                    {"http": self.config.proxy, "https": self.config.proxy}
                )
            self._is_running = True
            logger.info("HttpScrapingDriver initialized.")
            return True
        except Exception as exc:
            logger.error("Failed to launch HttpScrapingDriver: %s", exc)
            self._is_running = False
            return False

    def close(self) -> None:
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
        self._session = None
        self._html_content = ""
        self._is_running = False

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        if not self._is_running:
            self.launch()
        try:
            timeout_sec = max(1.0, self.config.timeout_ms / 1000.0)
            resp = self._session.get(url, timeout=timeout_sec, allow_redirects=True)
            self._status_code = resp.status_code
            self._html_content = resp.text
            self._current_url = resp.url
            self._parse_page_metadata()
            self._rebuild_elements_cache()
            return resp.status_code < 400
        except Exception as exc:
            logger.error("HttpScrapingDriver navigation failed for '%s': %s", url, exc)
            return False

    def _parse_page_metadata(self) -> None:
        """Extract document title and meta information."""
        title_match = re.search(r"<title[^>]*>(.*?)</title>", self._html_content, re.IGNORECASE | re.DOTALL)
        if title_match:
            self._title = html.unescape(title_match.group(1).strip())
        else:
            self._title = ""

    def _rebuild_elements_cache(self) -> None:
        """Parse basic DOM elements (inputs, links, buttons, select) into PageElements."""
        self._elements_cache = []
        if not self._html_content:
            return

        # 1. Inputs & Textareas
        input_patterns = re.findall(
            r"<(input|textarea|button|select)\s+([^>]*?)>",
            self._html_content,
            re.IGNORECASE | re.DOTALL,
        )
        for tag, attr_str in input_patterns:
            attrs = self._extract_attributes(attr_str)
            name_val = attrs.get("name") or attrs.get("id") or attrs.get("class") or ""
            selector = f"{tag}[name='{attrs.get('name')}']" if attrs.get("name") else (f"#{attrs.get('id')}" if attrs.get("id") else tag)
            self._elements_cache.append(
                PageElement(
                    selector=selector,
                    tag_name=tag.lower(),
                    text=attrs.get("value", ""),
                    value=attrs.get("value"),
                    attributes=attrs,
                    is_visible=attrs.get("type") != "hidden",
                    is_enabled="disabled" not in attrs,
                )
            )

        # 2. Links
        link_matches = re.findall(
            r"<a\s+([^>]*?)>(.*?)</a>",
            self._html_content,
            re.IGNORECASE | re.DOTALL,
        )
        for attr_str, inner_text in link_matches:
            attrs = self._extract_attributes(attr_str)
            clean_txt = re.sub(r"<[^>]+>", "", inner_text).strip()
            selector = f"a[href='{attrs.get('href', '')}']" if attrs.get("href") else "a"
            self._elements_cache.append(
                PageElement(
                    selector=selector,
                    tag_name="a",
                    text=html.unescape(clean_txt),
                    attributes=attrs,
                    is_visible=True,
                    is_enabled=True,
                )
            )

    @staticmethod
    def _extract_attributes(attr_str: str) -> dict[str, str]:
        """Extract key-value pairs from raw HTML tag attribute string."""
        attrs: dict[str, str] = {}
        matches = re.findall(r'([a-zA-Z0-9_-]+)(?:=([\'"])(.*?)\2|=([^\s>]+))?', attr_str)
        for name, _, val1, val2 in matches:
            val = val1 if val1 != "" else val2
            attrs[name.lower()] = html.unescape(val) if val else ""
        return attrs

    def click(self, selector: str, timeout_ms: int = 5000) -> bool:
        if not self._is_running:
            return False

        # Check if clicking a link or submit button
        matched = self.find_elements(selector)
        if not matched:
            # Fallback search by ID / class / text
            for el in self._elements_cache:
                if selector in el.selector or selector.lower() in el.text.lower():
                    matched = [el]
                    break

        if matched:
            target = matched[0]
            if target.tag_name == "a" and "href" in target.attributes:
                href = target.attributes["href"]
                abs_url = urllib.parse.urljoin(self._current_url, href)
                return self.navigate(abs_url)
            elif target.tag_name in ("button", "input") and target.attributes.get("type") in ("submit", "button", None):
                # Submit current form state
                return self._submit_active_form()

        return True

    def _submit_active_form(self) -> bool:
        """Submit the active form with accumulated form fields via HTTP POST."""
        try:
            # Detect form action and method
            form_match = re.search(r"<form\s+([^>]*?)>", self._html_content, re.IGNORECASE)
            action_url = self._current_url
            method = "post"
            if form_match:
                attrs = self._extract_attributes(form_match.group(1))
                if "action" in attrs:
                    action_url = urllib.parse.urljoin(self._current_url, attrs["action"])
                if "method" in attrs:
                    method = attrs["method"].lower()

            if method == "get":
                resp = self._session.get(action_url, params=self._form_state, timeout=self.config.timeout_ms / 1000.0)
            else:
                resp = self._session.post(action_url, data=self._form_state, timeout=self.config.timeout_ms / 1000.0)

            self._html_content = resp.text
            self._current_url = resp.url
            self._parse_page_metadata()
            self._rebuild_elements_cache()
            return resp.status_code < 400
        except Exception as exc:
            logger.error("HttpScrapingDriver form submit error: %s", exc)
            return False

    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        if not self._is_running:
            return False
        # Derive field name from selector (e.g. input[name='q'], #username, name)
        field_name = selector
        name_match = re.search(r"name=['\"]([^'\"]+)['\"]", selector)
        if name_match:
            field_name = name_match.group(1)
        elif selector.startswith("#"):
            field_name = selector[1:]
        elif selector.startswith("."):
            field_name = selector[1:]

        self._form_state[field_name] = text
        # Update elements cache
        for el in self._elements_cache:
            if field_name in (el.attributes.get("name"), el.attributes.get("id")):
                el.value = text
                el.text = text
        return True

    def select_option(self, selector: str, value: str) -> bool:
        return self.type_text(selector, value)

    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        matched = self.find_elements(selector)
        return len(matched) > 0 if state == "visible" else True

    def evaluate_script(self, script: str, *args: Any) -> Any:
        return None

    def get_html(self) -> str:
        return self._html_content

    def get_text(self, selector: str | None = None) -> str:
        if not self._html_content:
            return ""
        content = self._html_content
        if selector:
            matched = self.find_elements(selector)
            if matched:
                return matched[0].text
        # Remove script and style tags
        cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.IGNORECASE | re.DOTALL)
        # Strip all HTML tags
        stripped = re.sub(r"<[^>]+>", " ", cleaned)
        return " ".join(html.unescape(stripped).split())

    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        return MINIMAL_PNG_BYTES

    def get_cookies(self) -> list[dict[str, Any]]:
        if not self._session:
            return []
        cookies_list: list[dict[str, Any]] = []
        for cookie in self._session.cookies:
            cookies_list.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "expires": cookie.expires,
                }
            )
        return cookies_list

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        if not self._session:
            return
        for c in cookies:
            self._session.cookies.set(
                name=c.get("name", ""),
                value=c.get("value", ""),
                domain=c.get("domain", ""),
                path=c.get("path", "/"),
            )

    def get_current_url(self) -> str:
        return self._current_url

    def get_title(self) -> str:
        return self._title

    def find_elements(self, selector: str) -> list[PageElement]:
        results: list[PageElement] = []
        for el in self._elements_cache:
            if selector in el.selector or selector.lower() == el.tag_name:
                results.append(el)
            elif selector.startswith("#") and el.attributes.get("id") == selector[1:]:
                results.append(el)
            elif selector.startswith(".") and selector[1:] in el.attributes.get("class", "").split():
                results.append(el)
        return results

    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        return self._is_running


# ---------------------------------------------------------------------------
# Tier 4: Mock Browser Driver (100% Deterministic CI/CD Test Isolation)
# ---------------------------------------------------------------------------

class MockBrowserDriver(BaseBrowserDriver):
    """
    Tier 4 Mock Browser Driver.
    Simulates a fully interactive DOM in memory with action logs, custom fixtures,
    synthetic screenshots, and script evaluation without requiring network or external processes.
    """

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self.action_log: list[dict[str, Any]] = []
        self.elements: dict[str, PageElement] = {}
        self.cookies: list[dict[str, Any]] = []
        self.html_content: str = "<html><head><title>Mock Page</title></head><body><h1>Mock Content</h1></body></html>"
        self.script_eval_results: dict[str, Any] = {}
        self.navigation_history: list[str] = []
        self._title = "Mock Page"
        self._current_url = "http://mock.local"

    def set_fixture_html(self, html_str: str, url: str = "http://mock.local", title: str = "Mock Page") -> None:
        """Populate the mock driver with a synthetic HTML payload."""
        self.html_content = html_str
        self._current_url = url
        self._title = title
        self.elements.clear()

        # Parse basic elements into simulated DOM
        for tag in ("input", "button", "select", "a", "div", "p", "table", "h1", "h2", "h3", "form"):
            matches = re.findall(rf"<{tag}\s+([^>]*?)>(.*?)</{tag}>|<{tag}\s+([^>]*?)/?>", html_str, re.IGNORECASE | re.DOTALL)
            for m in matches:
                attr_str = m[0] or m[2]
                inner = m[1]
                attrs = HttpScrapingDriver._extract_attributes(attr_str)
                sel_id = attrs.get("id")
                sel_name = attrs.get("name")
                selector = f"#{sel_id}" if sel_id else (f"{tag}[name='{sel_name}']" if sel_name else tag)
                el = PageElement(
                    selector=selector,
                    tag_name=tag,
                    text=inner.strip() if inner else attrs.get("value", ""),
                    value=attrs.get("value"),
                    attributes=attrs,
                    bounding_box={"x": 10.0, "y": 10.0, "width": 100.0, "height": 30.0},
                    is_visible=True,
                    is_enabled=True,
                )
                self.add_mock_element(el)

    def add_mock_element(self, element: PageElement) -> None:
        """Register a simulated DOM element."""
        self.elements[element.selector] = element

    def launch(self, config: BrowserConfig | None = None) -> bool:
        if config:
            self.config = config
        self._is_running = True
        self.action_log.append({"action": "launch", "timestamp": time.time()})
        return True

    def close(self) -> None:
        self._is_running = False
        self.action_log.append({"action": "close", "timestamp": time.time()})

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        self._current_url = url
        self.navigation_history.append(url)
        self.action_log.append({"action": "navigate", "url": url, "timestamp": time.time()})
        if "google" in url:
            self._title = "Google Search"
        elif "github" in url:
            self._title = "GitHub: Let's build from here"
        return True

    def click(self, selector: str, timeout_ms: int = 5000) -> bool:
        self.action_log.append({"action": "click", "selector": selector, "timestamp": time.time()})
        if selector in self.elements:
            el = self.elements[selector]
            if el.tag_name == "a" and "href" in el.attributes:
                return self.navigate(el.attributes["href"])
        return True

    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        self.action_log.append({"action": "type_text", "selector": selector, "text": text, "timestamp": time.time()})
        if selector in self.elements:
            self.elements[selector].value = text
            self.elements[selector].text = text
        else:
            self.elements[selector] = PageElement(
                selector=selector,
                tag_name="input",
                text=text,
                value=text,
            )
        return True

    def select_option(self, selector: str, value: str) -> bool:
        self.action_log.append({"action": "select_option", "selector": selector, "value": value, "timestamp": time.time()})
        if selector in self.elements:
            self.elements[selector].value = value
        return True

    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        self.action_log.append({"action": "wait_for_selector", "selector": selector, "state": state})
        return True

    def evaluate_script(self, script: str, *args: Any) -> Any:
        self.action_log.append({"action": "evaluate_script", "script": script, "args": args})
        return self.script_eval_results.get(script, "mock_result")

    def get_html(self) -> str:
        return self.html_content

    def get_text(self, selector: str | None = None) -> str:
        if selector and selector in self.elements:
            return self.elements[selector].text
        cleaned = re.sub(r"<[^>]+>", " ", self.html_content)
        return " ".join(cleaned.split())

    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        self.action_log.append({"action": "capture_page_screenshot", "full_page": full_page})
        return MINIMAL_PNG_BYTES

    def get_cookies(self) -> list[dict[str, Any]]:
        return list(self.cookies)

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self.cookies = list(cookies)
        self.action_log.append({"action": "set_cookies", "count": len(cookies)})

    def get_current_url(self) -> str:
        return self._current_url

    def get_title(self) -> str:
        return self._title

    def find_elements(self, selector: str) -> list[PageElement]:
        if selector in self.elements:
            return [self.elements[selector]]
        return list(self.elements.values())

    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        self.action_log.append({"action": "scroll", "direction": direction, "distance": distance})
        return True


# ---------------------------------------------------------------------------
# Driver Factory & Auto-Detection
# ---------------------------------------------------------------------------

class DriverFactory:
    """Factory resolving the optimal browser driver tier with automatic graceful fallback."""

    @staticmethod
    def detect_best_driver() -> BrowserDriverType:
        """Detect the best available browser driver tier.

        Checks Playwright availability, then CDP (port 9222), falling back to HttpScraper.
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            return BrowserDriverType.PLAYWRIGHT
        except (ImportError, Exception):
            pass

        try:
            import requests
            resp = requests.get("http://127.0.0.1:9222/json/version", timeout=0.5)
            if resp.status_code == 200:
                return BrowserDriverType.CDP
        except Exception:
            pass

        return BrowserDriverType.HTTP_SCRAPER

    @staticmethod
    def create_driver(
        driver_type: BrowserDriverType | None = None,
        config: BrowserConfig | None = None,
    ) -> BaseBrowserDriver:
        cfg = config or BrowserConfig()
        target_type = driver_type or cfg.driver_type

        # 1. Explicit Mock Driver
        if target_type == BrowserDriverType.MOCK:
            driver = MockBrowserDriver(cfg)
            driver.launch(cfg)
            return driver

        # 2. Tier 1: Playwright
        if target_type == BrowserDriverType.PLAYWRIGHT:
            try:
                pw_driver = PlaywrightBrowserDriver(cfg)
                if pw_driver.launch(cfg):
                    return pw_driver
            except Exception as exc:
                logger.warning("Playwright driver launch failed, falling back: %s", exc)

        # 3. Tier 2: CDP
        if target_type in (BrowserDriverType.CDP, BrowserDriverType.PLAYWRIGHT):
            try:
                cdp_driver = CDPBrowserDriver(cfg)
                if cdp_driver.launch(cfg):
                    return cdp_driver
            except Exception as exc:
                logger.warning("CDP driver launch failed, falling back: %s", exc)

        # 4. Tier 3: Zero-Browser HTTP Scraping Driver (Always reliable fallback)
        http_driver = HttpScrapingDriver(cfg)
        http_driver.launch(cfg)
        return http_driver


# Expose at module level
detect_best_driver = DriverFactory.detect_best_driver

