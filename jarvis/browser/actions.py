"""
High-Level Browser Actions and Automation Primitives.

Encapsulates discrete browser operations (navigation, element clicking, form entry,
file downloading with progress telemetry, and screenshot capture) with performance metrics
and standardized error recovery.
"""

import base64
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.parse

from jarvis.browser.driver import BaseBrowserDriver
from jarvis.browser.models import (
    BrowserActionResult,
    DownloadProgress,
    PageElement,
)

logger = logging.getLogger(__name__)


class BrowserActions:
    """
    Executes atomic and composite browser actions against an active BaseBrowserDriver.
    Wraps all operations in execution time tracking, screenshot capture, and robust exception handling.
    """

    def __init__(self, driver: BaseBrowserDriver) -> None:
        self.driver = driver

    def _make_result(
        self,
        action: str,
        success: bool,
        start_time: float,
        url: Optional[str] = None,
        title: Optional[str] = None,
        extracted_data: Any = None,
        downloaded_file: Optional[str] = None,
        error_message: Optional[str] = None,
        include_screenshot: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BrowserActionResult:
        """Helper to create standardized BrowserActionResult with timing."""
        elapsed_ms = (time.time() - start_time) * 1000.0
        active_url = url if url is not None else self.driver.get_current_url()
        active_title = title if title is not None else self.driver.get_title()

        screenshot_b64 = None
        if include_screenshot or (not success and self.driver.is_running()):
            try:
                raw_bytes = self.driver.capture_page_screenshot()
                if raw_bytes:
                    screenshot_b64 = base64.b64encode(raw_bytes).decode("utf-8")
            except Exception as exc:
                logger.debug("Failed capturing action screenshot: %s", exc)

        return BrowserActionResult(
            success=success,
            action=action,
            url=active_url,
            title=active_title,
            extracted_data=extracted_data,
            downloaded_file=downloaded_file,
            error_message=error_message,
            screenshot_b64=screenshot_b64,
            execution_time_ms=elapsed_ms,
            metadata=metadata or {},
        )

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> BrowserActionResult:
        """Navigate to target URL and record page title and metrics."""
        t0 = time.time()
        try:
            ok = self.driver.navigate(url, wait_until=wait_until)
            if ok:
                return self._make_result(
                    action="navigate",
                    success=True,
                    start_time=t0,
                    metadata={"wait_until": wait_until},
                )
            return self._make_result(
                action="navigate",
                success=False,
                start_time=t0,
                error_message=f"Navigation to '{url}' failed or returned error status.",
            )
        except Exception as exc:
            return self._make_result(
                action="navigate",
                success=False,
                start_time=t0,
                error_message=str(exc),
            )

    def click_element(self, selector: str, timeout_ms: int = 5000) -> BrowserActionResult:
        """Click on the DOM element specified by the selector."""
        t0 = time.time()
        try:
            ok = self.driver.click(selector, timeout_ms=timeout_ms)
            if ok:
                return self._make_result(
                    action="click",
                    success=True,
                    start_time=t0,
                    metadata={"selector": selector},
                )
            return self._make_result(
                action="click",
                success=False,
                start_time=t0,
                error_message=f"Element with selector '{selector}' could not be clicked.",
            )
        except Exception as exc:
            return self._make_result(
                action="click",
                success=False,
                start_time=t0,
                error_message=str(exc),
            )

    def fill_text(
        self,
        selector: str,
        text: str,
        clear: bool = True,
        delay_ms: int = 20,
    ) -> BrowserActionResult:
        """Type text into an input or textarea element."""
        t0 = time.time()
        try:
            ok = self.driver.type_text(selector, text, delay_ms=delay_ms, clear=clear)
            if ok:
                return self._make_result(
                    action="fill_text",
                    success=True,
                    start_time=t0,
                    metadata={"selector": selector, "text_length": len(text)},
                )
            return self._make_result(
                action="fill_text",
                success=False,
                start_time=t0,
                error_message=f"Failed typing text into element '{selector}'.",
            )
        except Exception as exc:
            return self._make_result(
                action="fill_text",
                success=False,
                start_time=t0,
                error_message=str(exc),
            )

    def select_dropdown(self, selector: str, value: str) -> BrowserActionResult:
        """Select option by value in dropdown element."""
        t0 = time.time()
        try:
            ok = self.driver.select_option(selector, value)
            if ok:
                return self._make_result(
                    action="select_dropdown",
                    success=True,
                    start_time=t0,
                    metadata={"selector": selector, "selected_value": value},
                )
            return self._make_result(
                action="select_dropdown",
                success=False,
                start_time=t0,
                error_message=f"Failed selecting option '{value}' on element '{selector}'.",
            )
        except Exception as exc:
            return self._make_result(
                action="select_dropdown",
                success=False,
                start_time=t0,
                error_message=str(exc),
            )

    def fill_and_submit_form(
        self,
        fields: Dict[str, str],
        submit_selector: Optional[str] = None,
        url: Optional[str] = None,
    ) -> BrowserActionResult:
        """
        Populate multiple form input fields and trigger submission.
        """
        t0 = time.time()
        if url:
            nav_res = self.navigate(url)
            if not nav_res.success:
                return nav_res

        filled_fields: List[str] = []
        for field_name, value in fields.items():
            # Try multiple selector variations (id, name, css)
            selectors = [
                field_name,
                f"input[name='{field_name}']",
                f"textarea[name='{field_name}']",
                f"select[name='{field_name}']",
                f"#{field_name}",
            ]
            success = False
            for sel in selectors:
                if self.driver.type_text(sel, str(value), clear=True):
                    filled_fields.append(field_name)
                    success = True
                    break
            if not success:
                logger.warning("Form field '%s' could not be filled with standard selectors.", field_name)

        # Trigger submission
        if submit_selector:
            self.driver.click(submit_selector)
        else:
            # Fallback to standard submit button selectors
            for sub_sel in ("button[type='submit']", "input[type='submit']", "form button", "form"):
                if self.driver.click(sub_sel):
                    break

        return self._make_result(
            action="fill_and_submit_form",
            success=len(filled_fields) > 0,
            start_time=t0,
            extracted_data={"filled_fields": filled_fields},
            metadata={"target_fields_count": len(fields), "filled_count": len(filled_fields)},
        )

    def download_file(
        self,
        url: str,
        target_path: Optional[str] = None,
        on_progress: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> BrowserActionResult:
        """
        Download a remote file or asset stream with progress reporting.
        """
        t0 = time.time()
        try:
            import requests

            downloads_dir = Path(self.driver.config.downloads_dir)
            downloads_dir.mkdir(parents=True, exist_ok=True)

            # Determine destination path
            if not target_path:
                parsed_url = urllib.parse.urlparse(url)
                filename = os.path.basename(parsed_url.path) or f"download_{int(time.time())}.bin"
                dest_path = downloads_dir / filename
            else:
                dest_path = Path(target_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)

            cookies_dict = {c["name"]: c["value"] for c in self.driver.get_cookies() if "name" in c}
            headers = {"User-Agent": self.driver.config.user_agent}

            progress = DownloadProgress(
                url=url,
                target_path=str(dest_path),
                status="downloading",
            )
            if on_progress:
                on_progress(progress)

            with requests.get(
                url,
                stream=True,
                headers=headers,
                cookies=cookies_dict,
                timeout=self.driver.config.timeout_ms / 1000.0,
            ) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                progress.total_bytes = total_size

                downloaded = 0
                chunk_size = 64 * 1024
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress.downloaded_bytes = downloaded
                            if total_size > 0:
                                progress.percentage = round((downloaded / total_size) * 100.0, 2)
                            if on_progress:
                                on_progress(progress)

            progress.status = "completed"
            progress.percentage = 100.0
            if on_progress:
                on_progress(progress)

            return self._make_result(
                action="download_file",
                success=True,
                start_time=t0,
                downloaded_file=str(dest_path),
                extracted_data={"file_size_bytes": downloaded, "path": str(dest_path)},
            )
        except Exception as exc:
            logger.error("Download failed for '%s': %s", url, exc)
            if on_progress:
                on_progress(
                    DownloadProgress(
                        url=url,
                        target_path=str(target_path or ""),
                        status="failed",
                        error=str(exc),
                    )
                )
            return self._make_result(
                action="download_file",
                success=False,
                start_time=t0,
                error_message=str(exc),
            )

    def scroll_page(self, direction: str = "down", distance: int = 500) -> BrowserActionResult:
        """Scroll active document."""
        t0 = time.time()
        ok = self.driver.scroll(direction=direction, distance=distance)
        return self._make_result(
            action="scroll",
            success=ok,
            start_time=t0,
            metadata={"direction": direction, "distance": distance},
        )

    def take_screenshot(self, full_page: bool = False) -> BrowserActionResult:
        """Capture screenshot and encode to base64."""
        t0 = time.time()
        raw_bytes = self.driver.capture_page_screenshot(full_page=full_page)
        if raw_bytes:
            b64_data = base64.b64encode(raw_bytes).decode("utf-8")
            return self._make_result(
                action="screenshot",
                success=True,
                start_time=t0,
                extracted_data={"b64_size": len(b64_data), "bytes_len": len(raw_bytes)},
                include_screenshot=True,
            )
        return self._make_result(
            action="screenshot",
            success=False,
            start_time=t0,
            error_message="Failed capturing screenshot from active driver.",
        )
