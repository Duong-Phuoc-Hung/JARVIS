"""
tests/unit/test_browser_agent.py
=================================
Comprehensive Unit & Integration Test Suite for JARVIS Browser Automation Subsystem (R3).
Covers:
- Multi-tier driver fallback (Playwright -> CDP -> HTTP Scraper -> Mock) via DriverFactory.
- MockBrowserDriver in-memory DOM simulation, navigation history, and action logging.
- HttpScrapingDriver zero-browser fallback requests and virtual DOM parsing.
- BrowserSessionManager cookie/storage persistence (JSON and SQLite backing stores).
- HTMLToMarkdownConverter clean markdown extraction with noise removal.
- HTMLTableParser structured table extraction into dictionaries.
- StructuredDataExtractor OpenGraph, Twitter Cards, and Schema.org JSON-LD extraction.
- PriceComparisonAggregator multi-store price extraction and sorting.
- BrowserAgent high-level automation: navigation, form filling, scraping, price comparison, downloads.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch

from jarvis.browser.actions import BrowserActions
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.driver import (
    BaseBrowserDriver,
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
    DownloadProgress,
    PageElement,
    PriceComparisonItem,
    ScrapeResult,
)
from jarvis.browser.scraper import (
    HTMLTableParser,
    HTMLToMarkdownConverter,
    PriceComparisonAggregator,
    StructuredDataExtractor,
    WebScraper,
)
from jarvis.browser.session import BrowserSessionManager


class TestBrowserDriversAndFactory(unittest.TestCase):
    """Tests covering multi-tier driver instantiation, fallbacks, and mock driver operations."""

    def test_mock_driver_launch_navigate_and_action_log(self) -> None:
        cfg = BrowserConfig(driver_type=BrowserDriverType.MOCK)
        driver = MockBrowserDriver(cfg)
        self.assertTrue(driver.launch(cfg))
        self.assertTrue(driver.is_running())

        # Navigation
        self.assertTrue(driver.navigate("https://news.ycombinator.com"))
        self.assertEqual(driver.get_current_url(), "https://news.ycombinator.com")
        self.assertIn("https://news.ycombinator.com", driver.navigation_history)

        # Action logging
        actions = [a["action"] for a in driver.action_log]
        self.assertIn("launch", actions)
        self.assertIn("navigate", actions)

        driver.close()
        self.assertFalse(driver.is_running())

    def test_mock_driver_fixture_html_and_dom_interaction(self) -> None:
        html_payload = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Store Portal</title></head>
        <body>
            <h1>Welcome to Store</h1>
            <form id="search-form" action="/search" method="get">
                <input id="search-box" name="q" value="laptop" type="text" />
                <button id="submit-btn" type="submit">Search</button>
            </form>
            <a id="cart-link" href="https://store.local/cart">Shopping Cart (2)</a>
        </body>
        </html>
        """
        driver = MockBrowserDriver()
        driver.launch()
        driver.set_fixture_html(html_payload, url="https://store.local", title="Test Store Portal")

        self.assertEqual(driver.get_title(), "Test Store Portal")
        self.assertEqual(driver.get_current_url(), "https://store.local")

        # Type text
        self.assertTrue(driver.type_text("#search-box", "gaming keyboard"))
        elements = driver.find_elements("#search-box")
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].value, "gaming keyboard")

        # Click link navigates
        self.assertTrue(driver.click("#cart-link"))
        self.assertEqual(driver.get_current_url(), "https://store.local/cart")

    def test_driver_factory_mock_driver_creation(self) -> None:
        cfg = BrowserConfig(driver_type=BrowserDriverType.MOCK)
        driver = DriverFactory.create_driver(config=cfg)
        self.assertIsInstance(driver, MockBrowserDriver)
        self.assertTrue(driver.is_running())

    def test_driver_factory_fallback_to_http_scraper_when_playwright_unavailable(self) -> None:
        cfg = BrowserConfig(driver_type=BrowserDriverType.PLAYWRIGHT)
        with patch.object(PlaywrightBrowserDriver, "launch", side_effect=ImportError("Playwright not installed")):
            with patch.object(CDPBrowserDriver, "launch", side_effect=ConnectionRefusedError("CDP endpoint closed")):
                driver = DriverFactory.create_driver(config=cfg)
                self.assertIsInstance(driver, HttpScrapingDriver)
                self.assertTrue(driver.is_running())

    def test_http_scraping_driver_virtual_dom_and_text_extraction(self) -> None:
        driver = HttpScrapingDriver()
        sample_html = """
        <html>
        <head><title>Sample Documentation</title></head>
        <body>
            <script>var x = 10;</script>
            <style>.hidden { display: none; }</style>
            <h2>System Architecture</h2>
            <p>JARVIS uses a <strong>multi-tier</strong> browser automation driver.</p>
            <input name="username" value="admin" />
        </body>
        </html>
        """
        driver._is_running = True
        driver._html_content = sample_html
        driver._parse_page_metadata()
        driver._rebuild_elements_cache()

        self.assertEqual(driver.get_title(), "Sample Documentation")
        text = driver.get_text()
        self.assertIn("System Architecture", text)
        self.assertIn("JARVIS uses a multi-tier browser automation driver.", text)
        self.assertNotIn("var x = 10", text)

        inputs = driver.find_elements("input[name='username']")
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0].value, "admin")


class TestBrowserSessionManager(unittest.TestCase):
    """Tests covering session state persistence, Netscape cookie export, and SQLite storage."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.db"
        self.session_mgr = BrowserSessionManager(
            storage_dir=self.temp_dir.name,
            db_path=str(self.db_path),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_save_and_load_session_json_and_sqlite(self) -> None:
        domain = "shopee.vn"
        cookies = [
            {"name": "SPC_SEC_T", "value": "token_abc123", "domain": ".shopee.vn", "path": "/"},
            {"name": "SPC_U", "value": "user_9876", "domain": ".shopee.vn", "path": "/"},
        ]
        local_storage = {"theme": "dark", "cart_count": "3"}

        # Save session
        ok = self.session_mgr.save_session(
            domain=domain,
            cookies=cookies,
            local_storage=local_storage,
            user_agent="JARVIS-Browser/2.0",
        )
        self.assertTrue(ok)

        # Check JSON file written
        json_file = Path(self.temp_dir.name) / "shopee.vn.json"
        self.assertTrue(json_file.exists())

        # Load session
        loaded = self.session_mgr.load_session("https://shopee.vn/flash-sale")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["domain"], "shopee.vn")
        self.assertEqual(len(loaded["cookies"]), 2)
        self.assertEqual(loaded["local_storage"]["theme"], "dark")
        self.assertEqual(loaded["user_agent"], "JARVIS-Browser/2.0")

    def test_export_netscape_cookies(self) -> None:
        domain = "github.com"
        cookies = [
            {
                "name": "user_session",
                "value": "session_tok",
                "domain": ".github.com",
                "path": "/",
                "secure": True,
                "expires": 1893456000,
            }
        ]
        self.session_mgr.save_session(domain, cookies)

        export_path = Path(self.temp_dir.name) / "cookies.txt"
        exported = self.session_mgr.export_netscape_cookies(domain, export_path)
        self.assertTrue(exported)
        self.assertTrue(export_path.exists())

        content = export_path.read_text(encoding="utf-8")
        self.assertIn("# Netscape HTTP Cookie File", content)
        self.assertIn(".github.com", content)
        self.assertIn("user_session", content)

    def test_apply_and_capture_session_with_driver(self) -> None:
        driver = MockBrowserDriver()
        driver.launch()

        # Save session
        cookies = [{"name": "auth_token", "value": "xyz123", "domain": "example.com", "path": "/"}]
        self.session_mgr.save_session("example.com", cookies)

        # Apply to driver
        applied = self.session_mgr.apply_to_driver(driver, "https://example.com/dashboard")
        self.assertTrue(applied)
        self.assertEqual(len(driver.get_cookies()), 1)
        self.assertEqual(driver.get_cookies()[0]["name"], "auth_token")

        # Mutate cookies in driver and capture back
        driver.set_cookies([
            {"name": "auth_token", "value": "new_xyz456", "domain": "example.com", "path": "/"},
            {"name": "session_id", "value": "sess_999", "domain": "example.com", "path": "/"},
        ])
        captured = self.session_mgr.capture_from_driver(driver, "https://example.com/profile")
        self.assertTrue(captured)

        # Verify updated session
        updated = self.session_mgr.load_session("example.com")
        self.assertEqual(len(updated["cookies"]), 2)


class TestWebScrapingAndParsers(unittest.TestCase):
    """Tests covering HTML to Markdown conversion, Table extraction, and Price comparison."""

    def test_html_to_markdown_converter_clean_rendering(self) -> None:
        raw_html = """
        <html>
        <head><title>Product Guide</title></head>
        <body>
            <nav><a href="/home">Home</a></nav>
            <h1>Product Overview</h1>
            <p>This is a <strong>powerful</strong> and <em>versatile</em> AI device.</p>
            <ul>
                <li>High-speed local execution</li>
                <li>Persistent episodic memory</li>
            </ul>
            <pre><code class="language-python">result = jarvis.run("analyze")</code></pre>
            <script>console.log("ad code");</script>
        </body>
        </html>
        """
        converter = HTMLToMarkdownConverter()
        md = converter.convert(raw_html)

        self.assertIn("# Product Overview", md)
        self.assertIn("**powerful**", md)
        self.assertIn("*versatile*", md)
        self.assertIn("- High-speed local execution", md)
        self.assertIn("```python", md)
        self.assertIn('result = jarvis.run("analyze")', md)
        self.assertNotIn("console.log", md)
        self.assertNotIn("Home", md)  # nav tag stripped

    def test_html_table_parser_structured_records(self) -> None:
        table_html = """
        <table class="data-table">
            <thead>
                <tr>
                    <th>Product</th>
                    <th>Price (USD)</th>
                    <th>Stock</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>JARVIS Core Hub</td>
                    <td>299.00</td>
                    <td>In Stock</td>
                </tr>
                <tr>
                    <td>Neural Vision Camera</td>
                    <td>149.50</td>
                    <td>Low Stock</td>
                </tr>
            </tbody>
        </table>
        """
        tables = HTMLTableParser.parse_tables(table_html)

        self.assertEqual(len(tables), 1)
        records = tables[0]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["Product"], "JARVIS Core Hub")
        self.assertEqual(records[0]["Price (USD)"], "299.00")
        self.assertEqual(records[1]["Product"], "Neural Vision Camera")
        self.assertEqual(records[1]["Stock"], "Low Stock")

    def test_structured_data_extractor_opengraph_and_json_ld(self) -> None:
        html_with_meta = """
        <html>
        <head>
            <title>AI Developer Conference 2026</title>
            <meta property="og:title" content="AI DevCon 2026 Vietnam" />
            <meta property="og:description" content="The premier autonomous agent summit." />
            <meta property="og:url" content="https://aidevcon.vn" />
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Event",
                "name": "AI DevCon 2026",
                "startDate": "2026-11-15",
                "location": {
                    "@type": "Place",
                    "name": "Hanoi Convention Center"
                }
            }
            </script>
        </head>
        <body><p>Event details</p></body>
        </html>
        """
        data = StructuredDataExtractor.extract_structured_data(html_with_meta)

        self.assertEqual(data["opengraph"]["title"], "AI DevCon 2026 Vietnam")
        self.assertEqual(data["opengraph"]["description"], "The premier autonomous agent summit.")
        self.assertEqual(len(data["json_ld"]), 1)
        self.assertEqual(data["json_ld"][0]["name"], "AI DevCon 2026")
        self.assertEqual(data["json_ld"][0]["location"]["name"], "Hanoi Convention Center")

    def test_price_comparison_aggregator(self) -> None:
        shopee_html = """
        <div class="product-item">
            <div class="title">Bàn phím cơ không dây Bluetooth RGB</div>
            <div class="price">₫1.250.000</div>
            <a href="https://shopee.vn/product/123">Xem chi tiết</a>
        </div>
        """
        tiki_html = """
        <div class="item">
            <h3 class="name">Bàn phím cơ không dây Bluetooth RGB cao cấp</h3>
            <span class="price-discount">1.190.000 ₫</span>
            <a href="https://tiki.vn/product/456">Mua ngay</a>
        </div>
        """
        items_shopee = PriceComparisonAggregator.extract_store_products("Shopee", shopee_html, "https://shopee.vn")
        items_tiki = PriceComparisonAggregator.extract_store_products("Tiki", tiki_html, "https://tiki.vn")

        all_items = items_shopee + items_tiki
        sorted_items = PriceComparisonAggregator.aggregate_and_sort(all_items)

        self.assertGreaterEqual(len(sorted_items), 2)
        # Tiki should be cheaper (1,190,000 vs 1,250,000)
        self.assertEqual(sorted_items[0].store_name, "Tiki")
        self.assertEqual(sorted_items[0].price, 1190000.0)
        self.assertEqual(sorted_items[1].store_name, "Shopee")
        self.assertEqual(sorted_items[1].price, 1250000.0)


class TestBrowserAgentHighLevel(unittest.TestCase):
    """Tests covering unified BrowserAgent interface, form automation, and workflows."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = BrowserConfig(
            driver_type=BrowserDriverType.MOCK,
            session_storage_dir=self.temp_dir.name,
        )
        self.driver = MockBrowserDriver(self.config)
        self.session_mgr = BrowserSessionManager(storage_dir=self.temp_dir.name)
        self.agent = BrowserAgent(
            config=self.config,
            driver=self.driver,
            session_manager=self.session_mgr,
        )

    def tearDown(self) -> None:
        self.agent.stop()
        self.temp_dir.cleanup()

    def test_browser_agent_navigate_and_scrape(self) -> None:
        html_content = """
        <html>
        <head><title>JARVIS Tech Briefing</title></head>
        <body>
            <h1>Autonomous Superpower Upgrade</h1>
            <p>JARVIS introduces autonomous ReAct planning, computer use, and web automation.</p>
            <table id="specs">
                <tr><th>Module</th><th>Version</th></tr>
                <tr><td>BrowserAgent</td><td>2.0</td></tr>
                <tr><td>ReActPlanner</td><td>1.5</td></tr>
            </table>
            <a href="https://example.com/docs">Documentation</a>
        </body>
        </html>
        """
        self.driver.set_fixture_html(html_content, url="https://jarvis.internal/briefing", title="JARVIS Tech Briefing")

        # Scrape page
        scrape_res: ScrapeResult = self.agent.scrape_url("https://jarvis.internal/briefing")
        self.assertEqual(scrape_res.title, "JARVIS Tech Briefing")
        self.assertIn("# Autonomous Superpower Upgrade", scrape_res.markdown_content)
        self.assertIn("https://example.com/docs", scrape_res.links)
        self.assertEqual(len(scrape_res.tables), 1)
        self.assertEqual(scrape_res.tables[0][0]["Module"], "BrowserAgent")

    def test_browser_agent_fill_form(self) -> None:
        form_html = """
        <html>
        <head><title>Login Portal</title></head>
        <body>
            <form id="login-form" action="/auth" method="post">
                <input id="username" name="user" type="text" />
                <input id="password" name="pass" type="password" />
                <select id="role" name="role">
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                </select>
                <button id="login-btn" type="submit">Log In</button>
            </form>
        </body>
        </html>
        """
        self.driver.set_fixture_html(form_html, url="https://auth.internal/login", title="Login Portal")

        fields = {
            "#username": "admin_hung",
            "#password": "SecretPass123!",
            "#role": "admin",
        }
        res = self.agent.fill_form(
            url="https://auth.internal/login",
            form_fields=fields,
            submit_selector="#login-btn",
        )
        self.assertTrue(res.success)
        self.assertEqual(res.action, "fill_form")

        # Verify fields were set in DOM
        elements = self.driver.elements
        self.assertEqual(elements["#username"].value, "admin_hung")
        self.assertEqual(elements["#password"].value, "SecretPass123!")

    def test_browser_agent_compare_prices(self) -> None:
        mock_html_responses = {
            "https://shopee.vn/search?q=rtx4090": """
                <div class="product"><h2 class="title">ASUS ROG Strix RTX 4090 24GB</h2><span class="price">₫48.500.000</span></div>
            """,
            "https://tiki.vn/search?q=rtx4090": """
                <div class="product"><h2 class="title">Gigabyte RTX 4090 Gaming OC 24GB</h2><span class="price">46.990.000 ₫</span></div>
            """,
        }

        def mock_navigate(url: str, wait_until: str = "domcontentloaded") -> bool:
            self.driver._current_url = url
            if url in mock_html_responses:
                self.driver.html_content = mock_html_responses[url]
            return True

        self.driver.navigate = mock_navigate

        items = self.agent.compare_prices(
            product_name="rtx4090",
            stores=["Shopee", "Tiki"],
        )
        self.assertGreaterEqual(len(items), 2)
        # Lowest price first (Tiki: 46,990,000 vs Shopee: 48,500,000)
        self.assertEqual(items[0].store_name, "Tiki")
        self.assertEqual(items[0].price, 46990000.0)
        self.assertEqual(items[1].store_name, "Shopee")
        self.assertEqual(items[1].price, 48500000.0)

    def test_browser_agent_download_file_simulation(self) -> None:
        download_target = Path(self.temp_dir.name) / "report_2026.pdf"
        progress_events: List[DownloadProgress] = []

        def on_progress(p: DownloadProgress) -> None:
            progress_events.append(p)

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.headers = {"Content-Length": "1024"}
            mock_resp.iter_content = MagicMock(return_value=[b"A" * 512, b"B" * 512])
            mock_resp.__enter__.return_value = mock_resp
            mock_get.return_value = mock_resp

            res = self.agent.download_resource(
                url="https://example.com/files/report_2026.pdf",
                target_path=str(download_target),
                on_progress=on_progress,
            )

            self.assertTrue(res.success)
            self.assertTrue(download_target.exists())
            self.assertEqual(download_target.stat().st_size, 1024)
            self.assertGreater(len(progress_events), 0)
            self.assertEqual(progress_events[-1].status, "completed")
            self.assertEqual(progress_events[-1].percentage, 100.0)


if __name__ == "__main__":
    unittest.main()
