"""
High-Level Autonomous Browser Agent.

Orchestrates multi-tier browser drivers, session state persistence, actions,
and web scraping into an autonomous, self-healing browser automation agent.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.parse

from jarvis.browser.actions import BrowserActions
from jarvis.browser.driver import (
    BaseBrowserDriver,
    DriverFactory,
    MockBrowserDriver,
)
from jarvis.browser.models import (
    BrowserActionResult,
    BrowserConfig,
    BrowserDriverType,
    DownloadProgress,
    PriceComparisonItem,
    ScrapeResult,
)
from jarvis.browser.scraper import (
    PriceComparisonAggregator,
    WebScraper,
)
from jarvis.browser.session import BrowserSessionManager

logger = logging.getLogger(__name__)


class BrowserAgent:
    """
    Unified Autonomous Browser Agent for JARVIS.
    Provides web browsing, dynamic DOM interaction, form automation, web scraping,
    price comparison across multiple merchants, and multi-step workflow execution.
    """

    def __init__(
        self,
        config: Optional[BrowserConfig] = None,
        driver: Optional[BaseBrowserDriver] = None,
        session_manager: Optional[BrowserSessionManager] = None,
    ) -> None:
        self.config = config or BrowserConfig()
        self._driver: BaseBrowserDriver = driver or DriverFactory.create_driver(config=self.config)
        self.session_manager: BrowserSessionManager = session_manager or BrowserSessionManager(
            storage_dir=self.config.session_storage_dir
        )
        self.actions = BrowserActions(self._driver)
        self.scraper = WebScraper()
        self._is_active: bool = False

    @property
    def driver(self) -> BaseBrowserDriver:
        return self._driver

    def start(self) -> bool:
        """Start the active browser driver instance."""
        if not self._driver.is_running():
            ok = self._driver.launch(self.config)
            self._is_active = ok
            return ok
        self._is_active = True
        return True

    def stop(self) -> None:
        """Shut down the active browser driver and release resources."""
        if self._driver.is_running():
            self._driver.close()
        self._is_active = False

    def get_active_driver_type(self) -> BrowserDriverType:
        """Return the current driver tier type."""
        if isinstance(self._driver, MockBrowserDriver):
            return BrowserDriverType.MOCK
        return self.config.driver_type

    def get_session_manager(self) -> BrowserSessionManager:
        """Return the attached session persistence manager."""
        return self.session_manager

    def navigate(self, url: str) -> BrowserActionResult:
        """Navigate to target URL, applying stored session cookies if available."""
        self.start()
        # Apply stored cookies for domain if exists
        self.session_manager.apply_to_driver(self._driver, url)
        res = self.actions.navigate(url)
        if res.success:
            # Update session store with newly received cookies
            self.session_manager.capture_from_driver(self._driver, url)
        return res

    def open_and_search(self, query: str, search_engine: str = "duckduckgo") -> ScrapeResult:
        """
        Execute web search query via DuckDuckGo, Google, or Bing and extract structured results.
        """
        self.start()
        encoded_q = urllib.parse.quote(query)

        if search_engine.lower() == "google":
            search_url = f"https://www.google.com/search?q={encoded_q}"
        elif search_engine.lower() == "bing":
            search_url = f"https://www.bing.com/search?q={encoded_q}"
        else:
            search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"

        self.navigate(search_url)
        html_content = self._driver.get_html()
        return self.scraper.scrape_html(html_content, url=search_url)

    def scrape_url(self, url: str, extract_tables: bool = True) -> ScrapeResult:
        """
        Navigate to a webpage, wait for DOM completion, and produce a ScrapeResult.
        """
        self.start()
        self.navigate(url)
        html_content = self._driver.get_html()
        result = self.scraper.scrape_html(html_content, url=url)
        if not extract_tables:
            result.tables = []
        return result

    # Method alias conforming to PROJECT.md § M3 contract
    scrape_page = scrape_url

    def fill_form(
        self,
        url: str,
        form_fields: Dict[str, str],
        submit_selector: Optional[str] = None,
    ) -> BrowserActionResult:
        """
        Navigate to a form page, populate fields, and submit.
        """
        self.start()
        return self.actions.fill_and_submit_form(
            fields=form_fields,
            submit_selector=submit_selector,
            url=url,
        )

    def download_resource(
        self,
        url: str,
        target_path: Optional[str] = None,
        on_progress: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> BrowserActionResult:
        """
        Download a file stream or asset with real-time progress callbacks.
        """
        self.start()
        return self.actions.download_file(
            url=url,
            target_path=target_path,
            on_progress=on_progress,
        )

    def compare_prices(
        self,
        product_name: Optional[str] = None,
        stores: Optional[List[str]] = None,
        product: Optional[str] = None,
    ) -> List[PriceComparisonItem]:
        """
        Search for a product across specified or default eCommerce storefronts
        and aggregate a sorted list of price comparison offers.
        Supports both `product_name` and `product` parameter names.
        """
        target_product = product or product_name or ""
        self.start()
        target_stores = stores or ["Shopee", "Lazada", "Tiki", "CellphoneS", "GearVN"]
        all_items: List[PriceComparisonItem] = []

        for store in target_stores:
            try:
                # Query search for each store
                encoded_q = urllib.parse.quote(f"{target_product} {store}")
                search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
                self.navigate(search_url)
                page_html = self._driver.get_html()

                items = PriceComparisonAggregator.extract_store_products(
                    store_name=store,
                    html_content=page_html,
                    base_url=search_url,
                )
                if not items:
                    # Provide fallback synthetic item if scraping blocked
                    items.append(
                        PriceComparisonItem(
                            store_name=store,
                            product_title=f"{target_product} ({store})",
                            price=0.0,
                            currency="VND",
                            product_url=search_url,
                            in_stock=True,
                            source="search_estimate",
                        )
                    )
                all_items.extend(items)
            except Exception as exc:
                logger.warning("Error comparing prices on store %s: %s", store, exc)

        return PriceComparisonAggregator.aggregate_and_sort(all_items)

    def execute_workflow(self, steps: List[Dict[str, Any]]) -> BrowserActionResult:
        """
        Execute a multi-step sequence of browser actions.
        Step format:
        - {"action": "navigate", "url": "https://..."}
        - {"action": "click", "selector": "#button"}
        - {"action": "type", "selector": "input", "text": "hello"}
        - {"action": "select", "selector": "select", "value": "val"}
        - {"action": "wait", "selector": ".loaded", "timeout_ms": 5000}
        - {"action": "fill_form", "fields": {"name": "JARVIS"}, "submit_selector": "#btn"}
        - {"action": "scrape"}
        - {"action": "download", "url": "...", "target_path": "..."}
        - {"action": "screenshot"}
        - {"action": "scroll", "direction": "down", "distance": 500}
        - {"action": "eval", "script": "..."}
        """
        self.start()
        t0 = time.time()
        executed_steps: List[Dict[str, Any]] = []
        last_extracted_data: Any = None

        for idx, step in enumerate(steps):
            act = step.get("action", "").lower()
            step_record: Dict[str, Any] = {"step_index": idx, "action": act, "success": True}

            try:
                if act == "navigate":
                    url = step.get("url", "")
                    res = self.navigate(url)
                    step_record["success"] = res.success
                    if not res.success:
                        return self._workflow_failure(act, res.error_message, executed_steps, t0)

                elif act == "click":
                    selector = step.get("selector", "")
                    timeout_ms = step.get("timeout_ms", 5000)
                    res = self.actions.click_element(selector, timeout_ms=timeout_ms)
                    step_record["success"] = res.success
                    if not res.success:
                        return self._workflow_failure(act, res.error_message, executed_steps, t0)

                elif act in ("type", "type_text", "fill"):
                    selector = step.get("selector", "")
                    text = step.get("text", "")
                    clear = step.get("clear", True)
                    res = self.actions.fill_text(selector, text, clear=clear)
                    step_record["success"] = res.success
                    if not res.success:
                        return self._workflow_failure(act, res.error_message, executed_steps, t0)

                elif act in ("select", "select_option"):
                    selector = step.get("selector", "")
                    val = step.get("value", "")
                    res = self.actions.select_dropdown(selector, val)
                    step_record["success"] = res.success
                    if not res.success:
                        return self._workflow_failure(act, res.error_message, executed_steps, t0)

                elif act == "wait":
                    selector = step.get("selector", "")
                    timeout_ms = step.get("timeout_ms", 10000)
                    ok = self._driver.wait_for_selector(selector, timeout_ms=timeout_ms)
                    step_record["success"] = ok

                elif act == "fill_form":
                    fields = step.get("fields", {})
                    sub_sel = step.get("submit_selector")
                    res = self.actions.fill_and_submit_form(fields, submit_selector=sub_sel)
                    step_record["success"] = res.success
                    last_extracted_data = res.extracted_data

                elif act == "scrape":
                    html_content = self._driver.get_html()
                    scrape_res = self.scraper.scrape_html(html_content, url=self._driver.get_current_url())
                    last_extracted_data = scrape_res
                    step_record["extracted_title"] = scrape_res.title

                elif act == "download":
                    d_url = step.get("url", "")
                    d_target = step.get("target_path")
                    res = self.actions.download_file(d_url, target_path=d_target)
                    step_record["success"] = res.success
                    step_record["downloaded_file"] = res.downloaded_file

                elif act == "screenshot":
                    res = self.actions.take_screenshot()
                    step_record["success"] = res.success

                elif act == "scroll":
                    direction = step.get("direction", "down")
                    distance = step.get("distance", 500)
                    res = self.actions.scroll_page(direction=direction, distance=distance)
                    step_record["success"] = res.success

                elif act in ("eval", "evaluate"):
                    script = step.get("script", "")
                    eval_out = self._driver.evaluate_script(script)
                    last_extracted_data = eval_out
                    step_record["eval_result"] = eval_out

                executed_steps.append(step_record)

            except Exception as exc:
                logger.error("Workflow step %d ('%s') raised exception: %s", idx, act, exc)
                step_record["success"] = False
                step_record["error"] = str(exc)
                executed_steps.append(step_record)
                return self._workflow_failure(act, str(exc), executed_steps, t0)

        elapsed_ms = (time.time() - t0) * 1000.0
        return BrowserActionResult(
            success=True,
            action="execute_workflow",
            url=self._driver.get_current_url(),
            title=self._driver.get_title(),
            extracted_data=last_extracted_data,
            execution_time_ms=elapsed_ms,
            metadata={"steps_count": len(steps), "executed_steps": executed_steps},
        )

    def _workflow_failure(
        self,
        action: str,
        error_msg: Optional[str],
        executed_steps: List[Dict[str, Any]],
        start_time: float,
    ) -> BrowserActionResult:
        elapsed_ms = (time.time() - start_time) * 1000.0
        return BrowserActionResult(
            success=False,
            action=f"workflow:{action}",
            url=self._driver.get_current_url(),
            title=self._driver.get_title(),
            error_message=error_msg or "Step failed in workflow execution.",
            execution_time_ms=elapsed_ms,
            metadata={"executed_steps": executed_steps},
        )
