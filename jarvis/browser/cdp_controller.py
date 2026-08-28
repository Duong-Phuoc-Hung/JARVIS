"""
jarvis/browser/cdp_controller.py
==================================
Browser CDP Controller: điều khiển Chrome/Edge qua Chrome DevTools Protocol.
Hỗ trợ Playwright (ưu tiên) hoặc CDP trực tiếp qua websocket.

Lệnh thoại:
  "JARVIS, mở YouTube tìm lofi music"
  "Điền form đăng nhập cho tôi"
  "Chụp ảnh trang web này"
  "Trích xuất nội dung bài báo"

Cài đặt: pip install playwright && playwright install chromium
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.browser.cdp")


@dataclass
class BrowserConfig:
    headless: bool = False          # False = hiện trình duyệt
    browser_type: str = "chromium"  # chromium | firefox | webkit
    slow_mo_ms: int = 50            # Chờ giữa các thao tác (ms)
    timeout_ms: int = 15000         # Timeout mặc định
    screenshot_dir: str = "logs/screenshots"
    user_data_dir: str = ""         # Giữ cookie/session
    proxy: str | None = None


@dataclass
class PageInfo:
    url: str
    title: str
    content_md: str = ""
    screenshot_path: str = ""
    links: list[str] = field(default_factory=list)


@dataclass
class ElementResult:
    found: bool
    selector: str
    text: str = ""
    value: str = ""
    href: str = ""


class BrowserCDPController:
    """
    Chrome DevTools Protocol controller via Playwright.
    Lazy-initializes browser on first use.
    Falls back to mock mode when Playwright not installed.
    """

    def __init__(
        self,
        config: BrowserConfig | None = None,
        is_mock: bool = False,
    ) -> None:
        self.config = config or BrowserConfig()
        self.is_mock = is_mock
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._page: Any | None = None
        self._lock = threading.Lock()
        Path(self.config.screenshot_dir).mkdir(parents=True, exist_ok=True)
        log.info("BrowserCDPController initialized (mock=%s, headless=%s)", is_mock, self.config.headless)

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        if self.is_mock:
            return True
        try:
            import playwright  # type: ignore[import]  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def launch(self) -> bool:
        """Launch browser. Returns True on success."""
        if self.is_mock:
            log.info("Browser mock launched")
            return True
        if self._browser:
            return True
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import]
            self._playwright = sync_playwright().__enter__()
            browser_launcher = getattr(self._playwright, self.config.browser_type)
            launch_kwargs: dict[str, Any] = {
                "headless": self.config.headless,
                "slow_mo": self.config.slow_mo_ms,
            }
            if self.config.user_data_dir:
                self._browser = browser_launcher.launch_persistent_context(
                    self.config.user_data_dir, **launch_kwargs
                )
                self._page = self._browser.pages[0] if self._browser.pages else self._browser.new_page()
            else:
                self._browser = browser_launcher.launch(**launch_kwargs)
                self._page = self._browser.new_page()
            log.info("Browser launched: %s", self.config.browser_type)
            return True
        except Exception as exc:
            log.error("Browser launch error: %s", exc)
            return False

    def close(self) -> None:
        """Close browser and cleanup."""
        try:
            if self._browser:
                self._browser.close()
                self._browser = None
                self._page = None
            if self._playwright:
                self._playwright.__exit__(None, None, None)
                self._playwright = None
        except Exception as exc:
            log.debug("Browser close error: %s", exc)

    def _ensure_launched(self) -> bool:
        with self._lock:
            if self._browser is None and not self.is_mock:
                return self.launch()
        return True

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, url: str) -> PageInfo:
        """Navigate to URL and return page info."""
        if not url.startswith(("http://", "https://")):
            url = f"https://www.google.com/search?q={url.replace(' ', '+')}"

        if self.is_mock:
            return PageInfo(url=url, title=f"Mock Page: {url}", content_md=f"# Mock Content\nURL: {url}")

        if not self._ensure_launched():
            return PageInfo(url=url, title="Error", content_md="Browser không khởi động được.")

        assert self._page is not None
        try:
            self._page.goto(url, timeout=self.config.timeout_ms)
            self._page.wait_for_load_state("domcontentloaded")
            title = self._page.title()
            return PageInfo(url=self._page.url, title=title)
        except Exception as exc:
            log.error("Navigate error: %s", exc)
            return PageInfo(url=url, title="Error", content_md=str(exc))

    def get_current_url(self) -> str:
        if self.is_mock:
            return "https://mock.jarvis.local/"
        return self._page.url if self._page else ""

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def click(self, selector: str, timeout_ms: int | None = None) -> bool:
        """Click an element by CSS selector or text."""
        if self.is_mock:
            log.info("Mock click: %s", selector)
            return True
        if not self._ensure_launched():
            return False
        assert self._page is not None
        try:
            t = timeout_ms or self.config.timeout_ms
            # Try CSS selector first
            if self._page.locator(selector).count() > 0:
                self._page.click(selector, timeout=t)
            else:
                # Try text selector
                self._page.get_by_text(selector, exact=False).first.click(timeout=t)
            return True
        except Exception as exc:
            log.error("Click error (%s): %s", selector, exc)
            return False

    def type_text(self, selector: str, text: str, clear_first: bool = True) -> bool:
        """Type text into an input field."""
        if self.is_mock:
            log.info("Mock type into %s: %s", selector, text[:30])
            return True
        if not self._ensure_launched():
            return False
        assert self._page is not None
        try:
            elem = self._page.locator(selector).first
            if clear_first:
                elem.clear()
            elem.type(text, delay=30)
            return True
        except Exception as exc:
            log.error("Type error (%s): %s", selector, exc)
            return False

    def press_key(self, key: str) -> bool:
        """Press a keyboard key (Enter, Escape, Tab, F5...)."""
        if self.is_mock:
            return True
        if not self._ensure_launched():
            return False
        assert self._page is not None
        try:
            self._page.keyboard.press(key)
            return True
        except Exception as exc:
            log.error("Key press error (%s): %s", key, exc)
            return False

    def scroll(self, direction: str = "down", amount: int = 500) -> bool:
        """Scroll page up or down."""
        if self.is_mock:
            return True
        if not self._ensure_launched():
            return False
        assert self._page is not None
        try:
            delta = amount if direction == "down" else -amount
            self._page.evaluate(f"window.scrollBy(0, {delta})")
            return True
        except Exception as exc:
            log.error("Scroll error: %s", exc)
            return False

    def search_google(self, query: str) -> PageInfo:
        """Open Google and search for a query."""
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        page = self.navigate(search_url)
        if not self.is_mock:
            time.sleep(1.0)  # Wait for results
        page.content_md = f"🔍 Đang tìm kiếm: **{query}**\nURL: {search_url}"
        return page

    # ------------------------------------------------------------------
    # Screenshot & Content
    # ------------------------------------------------------------------

    def screenshot(self, filename: str = "") -> str:
        """Take screenshot, return saved file path."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        if not filename:
            filename = f"browser_{ts}.png"
        path = Path(self.config.screenshot_dir) / filename

        if self.is_mock:
            # Create a minimal valid PNG (1x1 white pixel)
            png_bytes = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
                b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
                b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            path.write_bytes(png_bytes)
            return str(path)

        if not self._ensure_launched():
            return ""
        assert self._page is not None
        try:
            self._page.screenshot(path=str(path), full_page=False)
            log.info("Screenshot saved: %s", path)
            return str(path)
        except Exception as exc:
            log.error("Screenshot error: %s", exc)
            return ""

    def extract_content_as_markdown(self) -> str:
        """Extract visible text content of current page as Markdown."""
        if self.is_mock:
            return "# Mock Page Content\n\nThis is mock extracted content."

        if not self._ensure_launched():
            return ""
        assert self._page is not None
        try:
            # Get all visible text
            content = self._page.evaluate("""() => {
                const headings = Array.from(document.querySelectorAll('h1,h2,h3')).map(h =>
                    '#'.repeat(parseInt(h.tagName[1])) + ' ' + h.innerText.trim()
                );
                const paragraphs = Array.from(document.querySelectorAll('p,li')).map(p =>
                    p.innerText.trim()
                ).filter(t => t.length > 20);
                return [...headings, ...paragraphs].slice(0, 80).join('\\n\\n');
            }""")
            return content or ""
        except Exception as exc:
            log.error("Content extraction error: %s", exc)
            return ""

    def get_page_links(self, limit: int = 20) -> list[str]:
        """Get all links on the current page."""
        if self.is_mock:
            return ["https://mock.jarvis.local/link1", "https://mock.jarvis.local/link2"]
        if not self._ensure_launched():
            return []
        assert self._page is not None
        try:
            links = self._page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(h => h.startsWith('http'))
                    .slice(0, 50);
            }""")
            return links[:limit]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Tab Management
    # ------------------------------------------------------------------

    def new_tab(self) -> bool:
        if self.is_mock:
            return True
        if not self._ensure_launched():
            return False
        assert self._browser is not None
        try:
            self._page = self._browser.new_page()
            return True
        except Exception as exc:
            log.error("New tab error: %s", exc)
            return False

    def close_tab(self) -> bool:
        if self.is_mock:
            return True
        if not self._ensure_launched():
            return False
        assert self._page is not None
        assert self._browser is not None
        try:
            self._page.close()
            pages = self._browser.pages
            if pages:
                self._page = pages[-1]
            return True
        except Exception as exc:
            log.error("Close tab error: %s", exc)
            return False


__all__ = ["BrowserCDPController", "BrowserConfig", "PageInfo"]
