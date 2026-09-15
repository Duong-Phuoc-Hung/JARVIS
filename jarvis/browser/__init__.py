"""
JARVIS Autonomous Web Browser Automation Subsystem.

Provides multi-tier browser automation (Playwright -> CDP -> HTTP Scraping -> Mock),
persistent session/cookie management, markdown web scraping, structured data extraction,
form automation, price comparison aggregation, and autonomous browser workflows.
"""

from jarvis.browser.actions import BrowserActionExecutor, BrowserActions
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
    BrowserResultStatus,
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

__all__ = [
    # Main Agent Controller
    "BrowserAgent",
    # Drivers & Factory
    "BaseBrowserDriver",
    "PlaywrightBrowserDriver",
    "CDPBrowserDriver",
    "HttpScrapingDriver",
    "MockBrowserDriver",
    "DriverFactory",
    # Session Management
    "BrowserSessionManager",
    # Actions & Scrapers
    "BrowserActions",
    "BrowserActionExecutor",
    "WebScraper",
    "HTMLToMarkdownConverter",
    "HTMLTableParser",
    "StructuredDataExtractor",
    "PriceComparisonAggregator",
    # Data Models
    "BrowserConfig",
    "BrowserDriverType",
    "BrowserResultStatus",
    "PageElement",
    "BrowserActionResult",
    "PriceComparisonItem",
    "ScrapeResult",
    "DownloadProgress",
]
