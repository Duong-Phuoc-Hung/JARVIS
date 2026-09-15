"""
High-Level Autonomous Browser Agent.

Orchestrates multi-tier browser drivers, session state persistence, actions,
and web scraping into an autonomous, self-healing browser automation agent.
"""

import logging
import threading
import time
import urllib.parse
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from jarvis.browser.actions import BrowserActionExecutor
from jarvis.browser.driver import (
    BaseBrowserDriver,
    DriverFactory,
    MockBrowserDriver,
)
from jarvis.browser.models import (
    BrowserActionResult,
    BrowserConfig,
    BrowserDriverType,
    BrowserResultStatus,
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


def _safe_failure_url(url: str) -> str:
    """Return a credential-free origin for a failed browser payload."""

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


def _redact_failed_scrape(
    result: ScrapeResult,
    fallback_url: str,
    driver_type: BrowserDriverType,
) -> ScrapeResult:
    """Clear page evidence and credentials from a failed scrape payload."""

    if result.success:
        result.driver_type = driver_type
        return result
    return ScrapeResult(
        url=_safe_failure_url(result.url or fallback_url),
        title="",
        markdown_content="",
        text_content="",
        structured_data={},
        links=[],
        images=[],
        tables=[],
        metadata={},
        status=result.status,
        error_code=result.error_code,
        error_message=result.error_message,
        driver_type=driver_type,
    )


def _serialized_browser_operation(method: Callable[..., Any]) -> Callable[..., Any]:
    """Keep navigation, evidence reads, and session persistence indivisible."""

    @wraps(method)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._operation_lock:
            return method(self, *args, **kwargs)

    return wrapped


class BrowserAgent:
    """
    Unified Autonomous Browser Agent for JARVIS.
    Provides web browsing, dynamic DOM interaction, form automation, web scraping,
    price comparison across multiple merchants, and multi-step workflow execution.
    """

    def __init__(
        self,
        config: BrowserConfig | None = None,
        driver: BaseBrowserDriver | None = None,
        session_manager: BrowserSessionManager | None = None,
    ) -> None:
        self.config = config or BrowserConfig()
        self._driver: BaseBrowserDriver = driver or DriverFactory.create_driver(config=self.config)
        if session_manager is not None:
            self.session_manager = session_manager
        elif self.config.session_storage_dir:
            session_storage = Path(self.config.session_storage_dir)
            self.session_manager = BrowserSessionManager(
                storage_dir=str(session_storage),
                db_path=str(session_storage / "browser_sessions.sqlite3"),
            )
        else:
            self.session_manager = BrowserSessionManager()
        self.actions = BrowserActionExecutor(self._driver)
        self.scraper = WebScraper()
        self._is_active: bool = False
        self._operation_lock = threading.RLock()

    @property
    def driver(self) -> BaseBrowserDriver:
        return self._driver

    @_serialized_browser_operation
    def start(self) -> bool:
        """Start the active browser driver instance."""
        if not self._driver.is_running():
            ok = self._driver.launch(self.config)
            self._is_active = ok
            return ok
        self._is_active = True
        return True

    @_serialized_browser_operation
    def stop(self) -> None:
        """Shut down the active browser driver and release resources."""
        self._driver.close()
        self._is_active = False

    def get_active_driver_type(self) -> BrowserDriverType:
        """Return the current driver tier type."""
        return self._driver.driver_type

    def get_session_manager(self) -> BrowserSessionManager:
        """Return the attached session persistence manager."""
        return self.session_manager

    @_serialized_browser_operation
    def navigate(self, url: str) -> BrowserActionResult:
        """Navigate to target URL, applying stored session cookies if available."""
        if not self.start():
            return self._driver_unavailable_result("navigate")
        saved_session = self.session_manager.load_session(url)
        if saved_session is not None and not self.session_manager.apply_to_driver(
            self._driver,
            url,
            apply_local_storage=False,
        ):
            return BrowserActionResult(
                success=False,
                action="navigate",
                status=self._driver.last_error_status or BrowserResultStatus.ERROR,
                error_code=self._driver.last_error_code or "BROWSER_SESSION_APPLY_FAILED",
                error_message="The saved browser session could not be applied.",
                driver_type=self._driver.driver_type,
            )
        res = self.actions.navigate(url)
        if res.success:
            observed_url = res.url or url
            if saved_session is not None and saved_session.get("local_storage"):
                observed_origin = self.session_manager._normalize_origin(observed_url)
                saved_origin = self.session_manager._normalize_origin(
                    str(saved_session.get("local_storage_origin") or "")
                )
                res.metadata["local_storage_applied"] = False
                if (
                    self.session_manager.supports_local_storage(self._driver)
                    and saved_origin is not None
                    and saved_origin == observed_origin
                ):
                    if not self.session_manager.apply_to_driver(
                        self._driver,
                        observed_url,
                        apply_cookies=False,
                    ):
                        return BrowserActionResult(
                            success=False,
                            action="navigate",
                            url=_safe_failure_url(observed_url),
                            title="",
                            status=self._driver.last_error_status or BrowserResultStatus.ERROR,
                            error_code=self._driver.last_error_code
                            or "BROWSER_SESSION_APPLY_FAILED",
                            error_message="The saved browser session could not be applied.",
                            driver_type=self._driver.driver_type,
                        )
                    restored = self.actions.navigate(url)
                    if not restored.success:
                        return restored
                    restored_url = restored.url or observed_url
                    restored_origin = self.session_manager._normalize_origin(
                        restored_url
                    )
                    restored.metadata["local_storage_applied"] = (
                        restored_origin == saved_origin
                    )
                    res = restored
                    observed_url = restored_url
            # Persistence is auxiliary to navigation; record its observed outcome.
            res.metadata["session_captured"] = self.session_manager.capture_from_driver(
                self._driver,
                observed_url,
            )
        return res

    @_serialized_browser_operation
    def open_and_search(self, query: str, search_engine: str = "duckduckgo") -> ScrapeResult:
        """
        Execute web search query via DuckDuckGo, Google, or Bing and extract structured results.
        """
        if not self.start():
            return ScrapeResult(
                url="",
                title="",
                markdown_content="",
                text_content="",
                status=self._driver.last_error_status or BrowserResultStatus.UNAVAILABLE,
                error_code=self._driver.last_error_code or "BROWSER_DRIVER_UNAVAILABLE",
                error_message=self._driver.last_error_message
                or "The browser driver is unavailable.",
                driver_type=self._driver.driver_type,
            )
        encoded_q = urllib.parse.quote(query)

        if search_engine.lower() == "google":
            search_url = f"https://www.google.com/search?q={encoded_q}"
        elif search_engine.lower() == "bing":
            search_url = f"https://www.bing.com/search?q={encoded_q}"
        else:
            search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"

        navigation = self.navigate(search_url)
        if not navigation.success:
            return ScrapeResult(
                url="",
                title="",
                markdown_content="",
                text_content="",
                status=navigation.status,
                error_code=navigation.error_code,
                error_message=navigation.error_message,
                driver_type=self._driver.driver_type,
            )
        html_content = self._driver.get_html()
        result = self.scraper.scrape_html(
            html_content,
            url=self._driver.get_current_url() or search_url,
        )
        return _redact_failed_scrape(
            result,
            search_url,
            self._driver.driver_type,
        )

    @_serialized_browser_operation
    def scrape_url(self, url: str, extract_tables: bool = True) -> ScrapeResult:
        """
        Navigate to a webpage, wait for DOM completion, and produce a ScrapeResult.
        """
        if not self.start():
            return ScrapeResult(
                url=_safe_failure_url(url),
                title="",
                markdown_content="",
                text_content="",
                status=self._driver.last_error_status or BrowserResultStatus.UNAVAILABLE,
                error_code=self._driver.last_error_code or "BROWSER_DRIVER_UNAVAILABLE",
                error_message=self._driver.last_error_message
                or "The browser driver is unavailable.",
                driver_type=self._driver.driver_type,
            )
        navigation = self.navigate(url)
        if not navigation.success:
            return ScrapeResult(
                url=_safe_failure_url(navigation.url or url),
                title="",
                markdown_content="",
                text_content="",
                status=navigation.status,
                error_code=navigation.error_code,
                error_message=navigation.error_message,
                driver_type=self._driver.driver_type,
            )
        html_content = self._driver.get_html()
        result = self.scraper.scrape_html(
            html_content,
            url=self._driver.get_current_url() or url,
        )
        if not extract_tables:
            result.tables = []
        return _redact_failed_scrape(
            result,
            url,
            self._driver.driver_type,
        )

    # Method alias conforming to PROJECT.md § M3 contract
    scrape_page = scrape_url

    @_serialized_browser_operation
    def fill_form(
        self,
        url: str,
        form_fields: dict[str, str],
        submit_selector: str | None = None,
    ) -> BrowserActionResult:
        """
        Navigate to a form page, populate fields, and submit.
        """
        if not self.start():
            return self._driver_unavailable_result("fill_form")
        res = self.actions.fill_and_submit_form(
            fields=form_fields,
            submit_selector=submit_selector,
            url=url,
        )
        res.action = "fill_form"
        return res

    @_serialized_browser_operation
    def download_resource(
        self,
        url: str,
        target_path: str | None = None,
        on_progress: Callable[[DownloadProgress], None] | None = None,
    ) -> BrowserActionResult:
        """
        Download a file stream or asset with real-time progress callbacks.
        """
        if not self.start():
            return self._driver_unavailable_result("download_file")
        return self.actions.download_file(
            url=url,
            target_path=target_path,
            on_progress=on_progress,
        )

    @_serialized_browser_operation
    def compare_prices(
        self,
        product_name: str | None = None,
        stores: list[str] | None = None,
        product: str | None = None,
    ) -> list[PriceComparisonItem]:
        """
        Search for a product across specified or default eCommerce storefronts
        and aggregate a sorted list of price comparison offers.
        Supports both `product_name` and `product` parameter names.
        """
        target_product = product or product_name or ""
        if not self.start():
            return []
        target_stores = stores or ["Shopee", "Lazada", "Tiki", "CellphoneS", "GearVN"]
        all_items: list[PriceComparisonItem] = []

        store_url_templates = {
            "shopee": "https://shopee.vn/search?q={query}",
            "tiki": "https://tiki.vn/search?q={query}",
            "lazada": "https://www.lazada.vn/catalog/?q={query}",
            "cellphones": "https://cellphones.com.vn/catalogsearch/result?q={query}",
            "gearvn": "https://gearvn.com/search?q={query}",
        }

        for store in target_stores:
            try:
                st_key = store.strip().lower()
                query_encoded = urllib.parse.quote(target_product)
                if st_key in store_url_templates:
                    search_url = store_url_templates[st_key].format(query=query_encoded)
                else:
                    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(f'{target_product} {store}')}"

                navigation = self.navigate(search_url)
                if not navigation.success:
                    continue
                page_html = self._driver.get_html()

                items = PriceComparisonAggregator.extract_store_products(
                    store_name=store,
                    html_content=page_html,
                    base_url=search_url,
                )
                all_items.extend(items)
            except Exception:
                logger.warning("Price comparison failed for one configured store.")

        return PriceComparisonAggregator.aggregate_and_sort(all_items)

    @_serialized_browser_operation
    def execute_workflow(self, steps: list[dict[str, Any]]) -> BrowserActionResult:
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
        if not self.start():
            return self._driver_unavailable_result("execute_workflow")
        if not steps:
            return BrowserActionResult(
                success=False,
                action="execute_workflow",
                status=BrowserResultStatus.ERROR,
                error_code="BROWSER_WORKFLOW_EMPTY",
                error_message="The browser workflow contains no actions.",
                driver_type=self._driver.driver_type,
            )
        t0 = time.time()
        executed_steps: list[dict[str, Any]] = []
        last_extracted_data: Any = None

        for idx, step in enumerate(steps):
            act = step.get("action", "").lower()
            step_record: dict[str, Any] = {"step_index": idx, "action": act, "success": True}

            try:
                if act == "navigate":
                    url = step.get("url", "")
                    res = self.navigate(url)
                    step_record["success"] = res.success
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act == "click":
                    selector = step.get("selector", "")
                    timeout_ms = step.get("timeout_ms", 5000)
                    res = self.actions.click_element(selector, timeout_ms=timeout_ms)
                    step_record["success"] = res.success
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act in ("type", "type_text", "fill"):
                    selector = step.get("selector", "")
                    text = step.get("text", "")
                    clear = step.get("clear", True)
                    res = self.actions.fill_text(selector, text, clear=clear)
                    step_record["success"] = res.success
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act in ("select", "select_option"):
                    selector = step.get("selector", "")
                    val = step.get("value", "")
                    res = self.actions.select_dropdown(selector, val)
                    step_record["success"] = res.success
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act == "wait":
                    selector = step.get("selector", "")
                    timeout_ms = step.get("timeout_ms", 10000)
                    res = self.actions.wait_for_selector(selector, timeout_ms=timeout_ms)
                    step_record["success"] = res.success
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act == "fill_form":
                    fields = step.get("fields", {})
                    sub_sel = step.get("submit_selector")
                    res = self.actions.fill_and_submit_form(fields, submit_selector=sub_sel)
                    step_record["success"] = res.success
                    last_extracted_data = res.extracted_data
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act == "scrape":
                    html_content = self._driver.get_html()
                    scrape_res = self.scraper.scrape_html(html_content, url=self._driver.get_current_url())
                    last_extracted_data = scrape_res
                    step_record["extracted_title"] = scrape_res.title
                    step_record["success"] = scrape_res.success
                    if not scrape_res.success:
                        step_record["error_code"] = scrape_res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            scrape_res.error_message,
                            executed_steps,
                            t0,
                            status=scrape_res.status,
                            error_code=scrape_res.error_code,
                        )

                elif act == "download":
                    d_url = step.get("url", "")
                    d_target = step.get("target_path")
                    res = self.actions.download_file(d_url, target_path=d_target)
                    step_record["success"] = res.success
                    step_record["downloaded_file"] = res.downloaded_file
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act == "screenshot":
                    res = self.actions.take_screenshot()
                    step_record["success"] = res.success
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act == "scroll":
                    direction = step.get("direction", "down")
                    distance = step.get("distance", 500)
                    res = self.actions.scroll_page(direction=direction, distance=distance)
                    step_record["success"] = res.success
                    if not res.success:
                        step_record["error_code"] = res.error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            res.error_message,
                            executed_steps,
                            t0,
                            status=res.status,
                            error_code=res.error_code,
                        )

                elif act in ("eval", "evaluate"):
                    script = step.get("script", "")
                    eval_out = self._driver.evaluate_script(script)
                    last_extracted_data = eval_out
                    step_record["eval_result"] = eval_out

                    if self._driver.last_error_status is not None:
                        step_record["success"] = False
                        step_record["error_code"] = self._driver.last_error_code
                        executed_steps.append(step_record)
                        return self._workflow_failure(
                            act,
                            self._driver.last_error_message,
                            executed_steps,
                            t0,
                        )

                else:
                    step_record["success"] = False
                    step_record["error_code"] = "BROWSER_UNKNOWN_ACTION"
                    executed_steps.append(step_record)
                    return self._workflow_failure(
                        act or "unknown",
                        "The workflow action is not supported.",
                        executed_steps,
                        t0,
                        status=BrowserResultStatus.ERROR,
                        error_code="BROWSER_UNKNOWN_ACTION",
                    )

                executed_steps.append(step_record)

            except Exception:
                logger.error("A browser workflow step raised an exception.")
                step_record["success"] = False
                step_record["error_code"] = "BROWSER_WORKFLOW_ERROR"
                executed_steps.append(step_record)
                return self._workflow_failure(
                    act,
                    "The browser workflow step failed.",
                    executed_steps,
                    t0,
                    status=BrowserResultStatus.ERROR,
                    error_code="BROWSER_WORKFLOW_ERROR",
                )

        elapsed_ms = (time.time() - t0) * 1000.0
        return BrowserActionResult(
            success=True,
            action="execute_workflow",
            url=self._driver.get_current_url(),
            title=self._driver.get_title(),
            extracted_data=last_extracted_data,
            execution_time_ms=elapsed_ms,
            metadata={"steps_count": len(steps), "executed_steps": executed_steps},
            status=BrowserResultStatus.SUCCESS,
            driver_type=self._driver.driver_type,
        )

    def _workflow_failure(
        self,
        action: str,
        error_msg: str | None,
        executed_steps: list[dict[str, Any]],
        start_time: float,
        status: BrowserResultStatus | str | None = None,
        error_code: str | None = None,
    ) -> BrowserActionResult:
        elapsed_ms = (time.time() - start_time) * 1000.0
        safe_action_names = {
            "navigate",
            "click",
            "type",
            "type_text",
            "fill",
            "select",
            "select_option",
            "wait",
            "fill_form",
            "scrape",
            "download",
            "screenshot",
            "scroll",
            "eval",
            "evaluate",
        }
        redacted_steps: list[dict[str, Any]] = []
        for step in executed_steps:
            safe_step: dict[str, Any] = {
                "step_index": step.get("step_index"),
                "action": (
                    step.get("action")
                    if step.get("action") in safe_action_names
                    else "unknown"
                ),
                "success": bool(step.get("success", False)),
            }
            if step.get("error_code"):
                safe_step["error_code"] = step["error_code"]
            redacted_steps.append(safe_step)
        safe_action = action if action in safe_action_names else "unknown"
        return BrowserActionResult(
            success=False,
            action=f"workflow:{safe_action}",
            url=_safe_failure_url(self._driver.get_current_url()),
            title="",
            error_message=error_msg or "Step failed in workflow execution.",
            execution_time_ms=elapsed_ms,
            metadata={"executed_steps": redacted_steps},
            status=status or self._driver.last_error_status or BrowserResultStatus.ERROR,
            error_code=error_code or self._driver.last_error_code or "BROWSER_WORKFLOW_ERROR",
            driver_type=self._driver.driver_type,
        )

    def _driver_unavailable_result(self, action: str) -> BrowserActionResult:
        """Build a stable failure when the configured driver cannot start."""
        return BrowserActionResult(
            success=False,
            action=action,
            status=self._driver.last_error_status or BrowserResultStatus.UNAVAILABLE,
            error_code=self._driver.last_error_code or "BROWSER_DRIVER_UNAVAILABLE",
            error_message=self._driver.last_error_message
            or "The browser driver is unavailable.",
            driver_type=self._driver.driver_type,
        )
