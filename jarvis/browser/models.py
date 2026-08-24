"""
Browser Automation Models and Data Classes.

Defines configuration, element structures, action outcomes, scrape payloads,
and price comparison representations for the JARVIS browser automation subsystem.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BrowserDriverType(str, Enum):
    """Supported browser driver execution tiers."""
    PLAYWRIGHT = "playwright"
    CDP = "cdp"
    HTTP_SCRAPER = "http_scraper"
    MOCK = "mock"


@dataclass
class BrowserConfig:
    """Configuration parameters for the browser driver lifecycle."""
    driver_type: BrowserDriverType = BrowserDriverType.PLAYWRIGHT
    headless: bool = True
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    viewport_width: int = 1280
    viewport_height: int = 800
    timeout_ms: int = 30000
    downloads_dir: str = "downloads"
    session_storage_dir: str = "logs/browser_sessions"
    cdp_endpoint: str = "http://127.0.0.1:9222"
    proxy: Optional[str] = None
    accept_downloads: bool = True
    slow_mo_ms: int = 0
    extra_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class PageElement:
    """Represents a discrete DOM element extracted or targeted on a web page."""
    selector: str
    tag_name: str
    text: str = ""
    role: Optional[str] = None
    aria_label: Optional[str] = None
    bounding_box: Optional[Dict[str, float]] = None  # {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    is_visible: bool = True
    is_enabled: bool = True
    attributes: Dict[str, str] = field(default_factory=dict)
    value: Optional[str] = None


@dataclass
class BrowserActionResult:
    """Outcome report for an executed browser action or multi-step workflow."""
    success: bool
    action: str
    url: str = ""
    title: str = ""
    extracted_data: Any = None
    downloaded_file: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_b64: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def error(self) -> Optional[str]:
        """Convenience alias for error_message."""
        return self.error_message


@dataclass
class PriceComparisonItem:
    """Normalized representation of a product offer scraped from an eCommerce store."""
    store_name: str
    product_title: str
    price: float
    currency: str = "VND"
    product_url: str = ""
    rating: Optional[float] = None
    in_stock: bool = True
    shipping_cost: float = 0.0
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """Structured extraction payload from a scraped web page."""
    url: str
    title: str
    markdown_content: str
    text_content: str
    structured_data: Dict[str, Any] = field(default_factory=dict)
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    tables: List[List[Dict[str, str]]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def markdown(self) -> str:
        """Convenience alias for markdown_content."""
        return self.markdown_content

    @property
    def error(self) -> Optional[str]:
        """Convenience alias returning None on successful scrape payload."""
        return None

    @property
    def success(self) -> bool:
        """Convenience boolean indicator for successful scraping."""
        return True



@dataclass
class DownloadProgress:
    """Real-time progress telemetry for file download streams."""
    url: str
    target_path: str
    total_bytes: int = 0
    downloaded_bytes: int = 0
    percentage: float = 0.0
    status: str = "pending"  # "pending", "downloading", "completed", "failed"
    error: Optional[str] = None
