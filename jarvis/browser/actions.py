"""
High-Level Browser Actions and Automation Primitives.

Encapsulates discrete browser operations (navigation, element clicking, form entry,
file downloading with progress telemetry, and screenshot capture) with performance metrics
and standardized error recovery.
"""

import base64
import logging
import math
import os
import threading
import time
import urllib.parse
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from jarvis.browser.cookie_utils import (
    ResponseCookieAction,
    build_cookie_header,
    canonical_cookie_hostname,
    canonicalize_cookie_expiry,
    cookie_domain_attribute_is_allowed,
    cookie_pair_is_safe,
    cookie_path_is_valid,
    cookie_prefix_is_valid,
    normalize_cookie_path,
    parse_response_cookie_action,
    response_action_overlays_secure_cookie,
    response_domain_storage_domain,
)
from jarvis.browser.driver import BaseBrowserDriver
from jarvis.browser.models import (
    BrowserActionResult,
    BrowserResultStatus,
    DownloadProgress,
)

logger = logging.getLogger(__name__)


def _serialized_action(method: Callable[..., Any]) -> Callable[..., Any]:
    """Keep a multi-call action and the evidence it reads as one transaction."""

    @wraps(method)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._action_lock:
            return method(self, *args, **kwargs)

    return wrapped


def _redact_failure_url(url: str) -> str:
    """Keep only a credential-free origin in failed action payloads."""
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


def _cookie_header_for_url(
    cookies: list[dict[str, Any]],
    url: str,
    top_level_url: str | None = None,
) -> str:
    """Select and serialize cookies for exactly one download request hop."""

    return build_cookie_header(cookies, url, top_level_url)


def _download_cookie_identity(
    cookie: dict[str, Any],
) -> tuple[str, str, str, str | None]:
    partition_key = cookie.get("partitionKey")
    return (
        str(cookie.get("name") or ""),
        str(cookie.get("domain") or "").strip().lower(),
        str(cookie.get("path") or "/"),
        str(partition_key) if partition_key is not None else None,
    )


def _upsert_scoped_cookie(
    cookies: list[dict[str, Any]],
    cookie: dict[str, Any],
) -> None:
    key = _download_cookie_identity(cookie)
    cookies[:] = [existing for existing in cookies if _download_cookie_identity(existing) != key]
    if "expires" in cookie:
        try:
            expires = float(cookie["expires"])
        except (TypeError, ValueError):
            return
        if not math.isfinite(expires):
            return
        if expires == 0 or (expires > 0 and expires <= time.time()):
            return
    cookies.append(dict(cookie))


def _response_set_cookie_headers(response: Any) -> list[str]:
    raw_headers = getattr(getattr(response, "raw", None), "headers", None)
    if raw_headers is not None:
        for accessor_name in ("getlist", "get_all"):
            accessor = getattr(raw_headers, accessor_name, None)
            if callable(accessor):
                try:
                    values = accessor("Set-Cookie")
                except Exception:
                    values = None
                if isinstance(values, (list, tuple)) and values:
                    return [str(value) for value in values]
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("Set-Cookie") or headers.get("set-cookie")
    return [str(value)] if value else []


def _merge_download_response_cookies(
    cookies: list[dict[str, Any]],
    response: Any,
    request_url: str,
) -> tuple[
    list[dict[str, Any]],
    list[tuple[str, str, str, str | None]],
]:
    """Merge one response while retaining host-only and security attributes."""

    upserts: list[dict[str, Any]] = []
    deletions: list[tuple[str, str, str, str | None]] = []

    try:
        request = urllib.parse.urlsplit(request_url)
        request_scheme = request.scheme.lower()
        request_host = canonical_cookie_hostname(request.hostname or "")
        request_path = request.path or "/"
    except (AttributeError, TypeError, ValueError):
        return upserts, deletions
    if not request_host:
        return upserts, deletions

    default_path = (
        "/"
        if not request_path.startswith("/") or request_path.count("/") <= 1
        else request_path.rsplit("/", 1)[0] or "/"
    )
    set_cookie_headers = _response_set_cookie_headers(response)
    if set_cookie_headers:
        for header in set_cookie_headers:
            action = parse_response_cookie_action(header, request_url)
            if action is None or response_action_overlays_secure_cookie(
                action,
                cookies,
                request_url,
            ):
                continue
            for identity in action.deletions:
                cookies[:] = [
                    cookie for cookie in cookies if _download_cookie_identity(cookie) != identity
                ]
                upserts[:] = [
                    cookie for cookie in upserts if _download_cookie_identity(cookie) != identity
                ]
                deletions[:] = [item for item in deletions if item != identity]
                deletions.append(identity)
            if action.upsert is not None:
                _upsert_scoped_cookie(cookies, action.upsert)
                _upsert_scoped_cookie(upserts, action.upsert)
                identity = _download_cookie_identity(action.upsert)
                deletions[:] = [item for item in deletions if item != identity]
        return upserts, deletions

    try:
        response_cookies = iter(getattr(response, "cookies", ()))
    except TypeError:
        response_cookies = iter(())
    for observed in response_cookies:
        observed_name = getattr(observed, "name", "")
        observed_value = getattr(observed, "value", "")
        if not cookie_pair_is_safe(observed_name, observed_value):
            continue
        domain = str(getattr(observed, "domain", "") or request_host).lower()
        try:
            bare_domain = canonical_cookie_hostname(domain.lstrip("."))
        except ValueError:
            continue
        domain_specified = bool(getattr(observed, "domain_specified", False))
        if (
            domain_specified and not cookie_domain_attribute_is_allowed(request_host, bare_domain)
        ) or (not domain_specified and request_host != bare_domain):
            continue
        rest = {
            str(key).lower(): value for key, value in (getattr(observed, "_rest", {}) or {}).items()
        }
        if "partitioned" in rest:
            continue
        secure = bool(getattr(observed, "secure", False))
        if secure and request_scheme != "https":
            continue
        path = normalize_cookie_path(getattr(observed, "path", None), default_path)
        if not cookie_path_is_valid(path):
            continue
        http_only = "httponly" in rest
        if not cookie_prefix_is_valid(
            str(observed_name),
            secure=secure,
            http_only=http_only,
            host_only=not domain_specified,
            path=path,
            scheme=request_scheme,
        ):
            continue
        entry = {
            "name": observed_name,
            "value": observed_value,
            "domain": response_domain_storage_domain(
                request_host,
                domain_specified,
                bare_domain,
            ),
            "path": path,
            "secure": secure,
        }
        expires = getattr(observed, "expires", None)
        if expires is not None:
            try:
                numeric_expires = float(expires)
            except (TypeError, ValueError):
                continue
            if (
                not math.isfinite(numeric_expires)
                or numeric_expires == 0
                or (numeric_expires > 0 and numeric_expires <= time.time())
            ):
                continue
            try:
                entry["expires"] = canonicalize_cookie_expiry(expires)
            except ValueError:
                continue
        if http_only:
            entry["httpOnly"] = True
        same_site = {
            "strict": "Strict",
            "lax": "Lax",
            "none": "None",
        }.get(str(rest.get("samesite") or "").strip().lower())
        if same_site == "None" and not secure:
            continue
        if same_site is not None:
            entry["sameSite"] = same_site
        fallback_action = ResponseCookieAction(upsert=entry)
        if response_action_overlays_secure_cookie(fallback_action, cookies, request_url):
            continue
        _upsert_scoped_cookie(cookies, entry)
        _upsert_scoped_cookie(upserts, entry)
        identity = _download_cookie_identity(entry)
        if any(_download_cookie_identity(cookie) == identity for cookie in upserts):
            deletions[:] = [item for item in deletions if item != identity]

    return upserts, deletions


class BrowserActionExecutor:
    """
    Executes atomic and composite browser actions against an active BaseBrowserDriver.
    Wraps all operations in execution time tracking, screenshot capture, and robust exception handling.
    """

    def __init__(self, driver: BaseBrowserDriver) -> None:
        self.driver = driver
        self._action_lock = threading.RLock()

    def _make_result(
        self,
        action: str,
        success: bool,
        start_time: float,
        url: str | None = None,
        title: str | None = None,
        extracted_data: Any = None,
        downloaded_file: str | None = None,
        error_message: str | None = None,
        error_code: str | None = None,
        status: BrowserResultStatus | None = None,
        include_screenshot: bool = False,
        screenshot_bytes: bytes | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BrowserActionResult:
        """Helper to create standardized BrowserActionResult with timing."""
        elapsed_ms = (time.time() - start_time) * 1000.0
        active_url = url if url is not None else self.driver.get_current_url()
        active_title = title if title is not None else self.driver.get_title()
        failure_status = self.driver.last_error_status
        failure_code = self.driver.last_error_code
        failure_message = self.driver.last_error_message

        screenshot_b64 = None
        raw_bytes = screenshot_bytes
        if include_screenshot and raw_bytes is None:
            try:
                raw_bytes = self.driver.capture_page_screenshot()
            except Exception:
                logger.debug("Failed capturing action screenshot.")
        if raw_bytes:
            screenshot_b64 = base64.b64encode(raw_bytes).decode("utf-8")

        resolved_status = BrowserResultStatus.SUCCESS
        resolved_error_code = None
        if not success:
            resolved_status = status or failure_status or BrowserResultStatus.ERROR
            resolved_error_code = error_code or failure_code or "BROWSER_ERROR"
            error_message = failure_message or error_message
            active_url = _redact_failure_url(active_url)
            active_title = ""

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
            status=resolved_status,
            error_code=resolved_error_code,
            driver_type=self.driver.driver_type,
        )

    @_serialized_action
    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> BrowserActionResult:
        """Navigate to target URL and record page title and metrics."""
        t0 = time.time()
        try:
            ok = self.driver.navigate(url, wait_until=wait_until)
            if ok:
                if self.driver.get_title().strip().lower() == "error":
                    self.driver._record_failure(
                        BrowserResultStatus.ERROR,
                        "BROWSER_INVALID_PAGE",
                        "The browser returned an invalid error page.",
                    )
                    return self._make_result(
                        action="navigate",
                        success=False,
                        start_time=t0,
                        error_message="The browser returned an invalid error page.",
                    )
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
                error_message="Browser navigation failed or returned an error status.",
            )
        except Exception:
            return self._make_result(
                action="navigate",
                success=False,
                start_time=t0,
                error_message="The browser navigation action failed.",
            )

    @_serialized_action
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
                )
            return self._make_result(
                action="click",
                success=False,
                start_time=t0,
                error_message="The browser element could not be clicked.",
            )
        except Exception:
            return self._make_result(
                action="click",
                success=False,
                start_time=t0,
                error_message="The browser click action failed.",
            )

    @_serialized_action
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
                    metadata={"clear_first": clear},
                )
            return self._make_result(
                action="fill_text",
                success=False,
                start_time=t0,
                error_message="The browser text entry could not be completed.",
            )
        except Exception:
            return self._make_result(
                action="fill_text",
                success=False,
                start_time=t0,
                error_message="The browser text entry action failed.",
            )

    @_serialized_action
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
                )
            return self._make_result(
                action="select_dropdown",
                success=False,
                start_time=t0,
                error_message="The browser option could not be selected.",
            )
        except Exception:
            return self._make_result(
                action="select_dropdown",
                success=False,
                start_time=t0,
                error_message="The browser selection action failed.",
            )

    @_serialized_action
    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> BrowserActionResult:
        """Wait for an element state through the canonical result contract."""
        t0 = time.time()
        try:
            ok = self.driver.wait_for_selector(selector, state=state, timeout_ms=timeout_ms)
            return self._make_result(
                action="wait",
                success=ok,
                start_time=t0,
                error_message=None
                if ok
                else "The browser element did not reach the requested state.",
                metadata={"state": state, "timeout_ms": timeout_ms},
            )
        except Exception:
            return self._make_result(
                action="wait",
                success=False,
                start_time=t0,
                error_message="The browser wait action failed.",
                metadata={"state": state, "timeout_ms": timeout_ms},
            )

    @_serialized_action
    def read_page(self) -> BrowserActionResult:
        """Read the active page URL, title, DOM, and visible text."""
        t0 = time.time()
        if not self.driver.is_running():
            self.driver._record_inactive_failure()
            return self._make_result(
                action="read_page",
                success=False,
                start_time=t0,
                error_message="No active browser page is available.",
            )
        try:
            html_content = self.driver.get_html()
            if self.driver.last_error_status is not None:
                return self._make_result(
                    action="read_page",
                    success=False,
                    start_time=t0,
                    error_message="The browser DOM could not be read.",
                )
            text_content = self.driver.get_text()
            if self.driver.last_error_status is not None:
                return self._make_result(
                    action="read_page",
                    success=False,
                    start_time=t0,
                    error_message="The browser page content could not be read.",
                )
            url = self.driver.get_current_url()
            title = self.driver.get_title()
            has_page_evidence = bool(url and html_content)
            if not has_page_evidence:
                self.driver._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_EMPTY_DOCUMENT",
                    "No browser page content was captured.",
                )
            return self._make_result(
                action="read_page",
                success=has_page_evidence,
                start_time=t0,
                url=url,
                title=title,
                extracted_data={
                    "url": url,
                    "title": title,
                    "html": html_content,
                    "text": text_content,
                }
                if has_page_evidence
                else None,
                error_message=None if has_page_evidence else "No active browser page is available.",
            )
        except Exception:
            return self._make_result(
                action="read_page",
                success=False,
                start_time=t0,
                error_message="The browser page could not be read.",
            )

    @_serialized_action
    def fill_and_submit_form(
        self,
        fields: dict[str, str],
        submit_selector: str | None = None,
        url: str | None = None,
    ) -> BrowserActionResult:
        """
        Populate multiple form input fields and trigger submission.
        """
        t0 = time.time()
        if url:
            nav_res = self.navigate(url)
            if not nav_res.success:
                return nav_res

        filled_count = 0
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
                    filled_count += 1
                    success = True
                    break
            if not success:
                logger.warning("One form field could not be filled with standard selectors.")

        if filled_count != len(fields):
            failure_status = self.driver.last_error_status or BrowserResultStatus.ERROR
            failure_code = self.driver.last_error_code or "BROWSER_FORM_INCOMPLETE"
            return self._make_result(
                action="fill_and_submit_form",
                success=False,
                start_time=t0,
                extracted_data={"filled_count": filled_count},
                error_message="One or more form fields could not be filled.",
                error_code=failure_code,
                status=failure_status,
                metadata={
                    "target_fields_count": len(fields),
                    "filled_count": filled_count,
                },
            )

        # Trigger submission
        submitted = False
        if submit_selector:
            submitted = self.driver.click(submit_selector)
        else:
            # Fallback to standard submit button selectors
            for sub_sel in (
                "button[type='submit']",
                "input[type='submit']",
                "form button",
            ):
                if self.driver.click(sub_sel):
                    submitted = True
                    break

        if not submitted:
            failure_status = self.driver.last_error_status or BrowserResultStatus.ERROR
            failure_code = self.driver.last_error_code or "BROWSER_FORM_SUBMIT_FAILED"
            return self._make_result(
                action="fill_and_submit_form",
                success=False,
                start_time=t0,
                extracted_data={"filled_count": filled_count},
                error_message="The form could not be submitted.",
                error_code=failure_code,
                status=failure_status,
                metadata={
                    "target_fields_count": len(fields),
                    "filled_count": filled_count,
                },
            )

        return self._make_result(
            action="fill_and_submit_form",
            success=True,
            start_time=t0,
            extracted_data={"filled_count": filled_count},
            metadata={"target_fields_count": len(fields), "filled_count": filled_count},
        )

    @_serialized_action
    def download_file(
        self,
        url: str,
        target_path: str | None = None,
        on_progress: Callable[[DownloadProgress], None] | None = None,
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

            browser_cookies = self.driver.get_cookies()
            if self.driver.last_error_status is not None:
                raise RuntimeError("Browser cookie state could not be read.")
            headers = {"User-Agent": self.driver.config.user_agent}

            progress = DownloadProgress(
                url=_redact_failure_url(url),
                target_path=str(dest_path),
                status="downloading",
            )
            if on_progress:
                on_progress(progress)

            initial_url = requests.Request("GET", url).prepare().url
            if not initial_url:
                raise ValueError("Unsupported browser download URL.")
            current_url = initial_url
            max_redirects = 10
            downloaded = 0
            for redirect_count in range(max_redirects + 1):
                prepared_url = requests.Request("GET", current_url).prepare().url
                if not prepared_url:
                    raise ValueError("Unsupported browser download URL.")
                current_url = prepared_url
                parsed_target = urllib.parse.urlsplit(current_url)
                if (
                    parsed_target.scheme.lower() not in {"http", "https"}
                    or not parsed_target.hostname
                ):
                    raise ValueError("Unsupported browser download URL.")

                request_headers = dict(headers)
                cookie_header = _cookie_header_for_url(
                    browser_cookies,
                    current_url,
                    initial_url,
                )
                if cookie_header:
                    request_headers["Cookie"] = cookie_header
                response = requests.get(
                    current_url,
                    stream=True,
                    headers=request_headers,
                    timeout=self.driver.config.timeout_ms / 1000.0,
                    allow_redirects=False,
                )
                cookie_upserts, cookie_deletions = _merge_download_response_cookies(
                    browser_cookies,
                    response,
                    current_url,
                )
                if cookie_upserts or cookie_deletions:
                    self.driver.apply_cookie_delta(cookie_upserts, cookie_deletions)
                    if self.driver.last_error_status is not None:
                        raise RuntimeError("Browser cookie state could not be synchronized.")
                status_code = int(response.status_code)
                if 300 <= status_code < 400:
                    location = response.headers.get("location")
                    response.close()
                    if (
                        status_code not in {301, 302, 303, 307, 308}
                        or not location
                        or redirect_count >= max_redirects
                    ):
                        raise RuntimeError(
                            "Browser download redirect could not be followed safely."
                        )
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue

                with response:
                    response.raise_for_status()
                    total_size = int(response.headers.get("content-length", 0))
                    progress.total_bytes = total_size

                    chunk_size = 64 * 1024
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress.downloaded_bytes = downloaded
                                if total_size > 0:
                                    progress.percentage = round(
                                        (downloaded / total_size) * 100.0,
                                        2,
                                    )
                                if on_progress:
                                    on_progress(progress)
                break

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
        except Exception:
            logger.error("Browser download failed.")
            if on_progress:
                on_progress(
                    DownloadProgress(
                        url=_redact_failure_url(url),
                        target_path=str(target_path or ""),
                        status="failed",
                        error="The browser download failed.",
                    )
                )
            return self._make_result(
                action="download_file",
                success=False,
                start_time=t0,
                error_message="The browser download failed.",
            )

    @_serialized_action
    def scroll_page(self, direction: str = "down", distance: int = 500) -> BrowserActionResult:
        """Scroll active document."""
        t0 = time.time()
        if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
            return self._make_result(
                action="scroll",
                success=False,
                start_time=t0,
                error_message="The browser scroll distance is invalid.",
                error_code="BROWSER_INVALID_SCROLL_DISTANCE",
                status=BrowserResultStatus.ERROR,
            )
        try:
            ok = self.driver.scroll(direction=direction, distance=distance)
        except Exception:
            ok = False
        return self._make_result(
            action="scroll",
            success=ok,
            start_time=t0,
            metadata={"direction": direction, "distance": distance},
        )

    @_serialized_action
    def take_screenshot(self, full_page: bool = False) -> BrowserActionResult:
        """Capture screenshot and encode to base64."""
        t0 = time.time()
        try:
            raw_bytes = self.driver.capture_page_screenshot(full_page=full_page)
        except Exception:
            raw_bytes = b""
        if raw_bytes:
            b64_data = base64.b64encode(raw_bytes).decode("utf-8")
            return self._make_result(
                action="screenshot",
                success=True,
                start_time=t0,
                extracted_data={"b64_size": len(b64_data), "bytes_len": len(raw_bytes)},
                screenshot_bytes=raw_bytes,
            )
        return self._make_result(
            action="screenshot",
            success=False,
            start_time=t0,
            error_message="Failed capturing screenshot from active driver.",
        )


# Backward-compatible name retained for existing callers.
BrowserActions = BrowserActionExecutor
