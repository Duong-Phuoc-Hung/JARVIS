"""
tests/unit/test_browser_control.py
=====================================
Unit tests for Browser CDP Controller (mock mode — no real browser).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.browser.cdp_controller import BrowserCDPController, BrowserConfig, PageInfo


@pytest.fixture
def browser():
    return BrowserCDPController(is_mock=True)


class TestAvailability:
    def test_mock_is_available(self, browser):
        assert browser.is_available() is True

    def test_launch_mock_returns_true(self, browser):
        assert browser.launch() is True

    def test_close_no_exception(self, browser):
        browser.launch()
        browser.close()  # Should not raise


class TestNavigation:
    def test_navigate_returns_page_info(self, browser):
        page = browser.navigate("https://www.google.com")
        assert isinstance(page, PageInfo)
        assert page.url != ""

    def test_navigate_without_scheme_uses_search(self, browser):
        # Bare keyword → Google search URL
        page = browser.navigate("python tutorial")
        assert "google" in page.url or "python" in page.url

    def test_get_current_url_returns_string(self, browser):
        url = browser.get_current_url()
        assert isinstance(url, str)

    def test_search_google_returns_page(self, browser):
        page = browser.search_google("JARVIS AI assistant")
        assert page.url != ""
        assert "JARVIS" in page.content_md


class TestInteraction:
    def test_click_returns_true_mock(self, browser):
        assert browser.click("button.submit") is True

    def test_type_text_returns_true_mock(self, browser):
        assert browser.type_text("#input", "xin chào JARVIS") is True

    def test_press_key_returns_true_mock(self, browser):
        assert browser.press_key("Enter") is True

    def test_scroll_down_returns_true_mock(self, browser):
        assert browser.scroll("down", 300) is True

    def test_scroll_up_returns_true_mock(self, browser):
        assert browser.scroll("up", 200) is True


class TestScreenshot:
    def test_screenshot_creates_file(self, browser, tmp_path):
        browser.config.screenshot_dir = str(tmp_path)
        path = browser.screenshot("test_shot.png")
        assert path != ""
        assert Path(path).exists()

    def test_screenshot_is_valid_png(self, browser, tmp_path):
        browser.config.screenshot_dir = str(tmp_path)
        path = browser.screenshot("valid.png")
        content = Path(path).read_bytes()
        assert content[:4] == b"\x89PNG"


class TestExtract:
    def test_extract_returns_string(self, browser):
        content = browser.extract_content_as_markdown()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_get_links_returns_list(self, browser):
        links = browser.get_page_links()
        assert isinstance(links, list)

    def test_get_links_are_strings(self, browser):
        links = browser.get_page_links()
        for link in links:
            assert isinstance(link, str)


class TestTabManagement:
    def test_new_tab_returns_true_mock(self, browser):
        assert browser.new_tab() is True

    def test_close_tab_returns_true_mock(self, browser):
        assert browser.close_tab() is True
