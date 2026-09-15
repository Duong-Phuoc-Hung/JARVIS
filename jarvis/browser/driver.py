"""
Multi-Tier Browser Driver Hierarchy.

Provides four concrete execution tiers:
- Tier 1: PlaywrightBrowserDriver (Full headless/headed Chromium, Firefox, WebKit)
- Tier 2: CDPBrowserDriver (Chrome DevTools Protocol via WebSocket / REST)
- Tier 3: HttpScrapingDriver (Zero-browser lightweight requests + HTML parser fallback)
- Tier 4: MockBrowserDriver (Deterministic in-memory DOM simulation for CI/CD unit testing)
"""

import html
import json
import logging
import math
import re
import threading
import time
import urllib.parse
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Any

from jarvis.browser.cookie_utils import (
    ResponseCookieAction,
    build_cookie_header,
    canonical_cookie_hostname,
    canonicalize_cookie,
    cookie_domain_attribute_is_allowed,
    cookie_expiry_is_valid,
    cookie_pair_is_safe,
    cookie_path_is_valid,
    cookie_prefix_is_valid,
    normalize_cookie_path,
    parse_response_cookie_action,
    response_action_overlays_secure_cookie,
    response_domain_storage_domain,
)
from jarvis.browser.models import (
    BrowserConfig,
    BrowserDriverType,
    BrowserResultStatus,
    PageElement,
)

logger = logging.getLogger(__name__)


def _canonical_same_site(value: Any) -> str | None:
    if value is None:
        return None
    return {
        "strict": "Strict",
        "lax": "Lax",
        "none": "None",
    }.get(str(value).strip().lower())


def _http_origin(url: str) -> tuple[str, str, int] | None:
    """Normalize one unambiguous HTTP(S) origin for header scoping."""

    if not isinstance(url, str) or "\\" in url:
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = canonical_cookie_hostname(parsed.hostname or "")
        port = parsed.port
    except (AttributeError, TypeError, ValueError):
        return None
    if scheme not in {"http", "https"} or not hostname:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, hostname, port


def _safe_extra_headers(headers: dict[str, str]) -> dict[str, str]:
    forbidden = {"cookie", "host", "content-length", "proxy-authorization"}
    return {
        str(name): str(value)
        for name, value in headers.items()
        if str(name).strip() and str(name).lower() not in forbidden
    }


def _validate_playwright_cookie_snapshot(cookies: list[dict[str, Any]]) -> None:
    """Reject cookie shapes that Playwright cannot restore before clearing state."""

    if not isinstance(cookies, list):
        raise ValueError("Cookie snapshot must be a list.")
    for raw_cookie in cookies:
        cookie = canonicalize_cookie(raw_cookie)
        if not isinstance(cookie, dict):
            raise ValueError("Cookie snapshot entries must be mappings.")
        supported_fields = {
            "name",
            "value",
            "domain",
            "path",
            "expires",
            "httpOnly",
            "secure",
            "sameSite",
            "partitionKey",
            "_crHasCrossSiteAncestor",
        }
        if set(cookie) - supported_fields:
            raise ValueError("Cookie snapshot entry contains unsupported fields.")
        if not cookie_pair_is_safe(cookie.get("name"), cookie.get("value")):
            raise ValueError("Cookie name and value must be strings.")
        has_url = False
        has_domain_path = (
            isinstance(cookie.get("domain"), str)
            and bool(str(cookie.get("domain")).strip())
            and isinstance(cookie.get("path"), str)
            and str(cookie.get("path")).startswith("/")
        )
        if not has_url and not has_domain_path:
            raise ValueError("Cookie snapshot entry has no valid scope.")
        if "expires" in cookie and not cookie_expiry_is_valid(cookie.get("expires")):
            raise ValueError("Cookie expiry must be numeric when present.")
        if "sameSite" in cookie and cookie.get("sameSite") not in {
            "Strict",
            "Lax",
            "None",
        }:
            raise ValueError("Cookie SameSite value is invalid.")
        for flag_name in ("secure", "httpOnly"):
            if flag_name in cookie and not isinstance(cookie.get(flag_name), bool):
                raise ValueError(f"Cookie {flag_name} flag must be boolean.")
        if cookie.get("sameSite") == "None" and cookie.get("secure") is not True:
            raise ValueError("SameSite=None cookies must be Secure.")
        if has_url:
            try:
                cookie_scheme = urllib.parse.urlsplit(str(cookie["url"])).scheme.lower()
            except (TypeError, ValueError):
                cookie_scheme = ""
            host_only = True
            cookie_path = str(cookie.get("path") or "/")
        else:
            cookie_scheme = "https" if cookie.get("secure") is True else "http"
            host_only = not str(cookie.get("domain") or "").startswith(".")
            cookie_path = str(cookie.get("path") or "")
        if not cookie_prefix_is_valid(
            str(cookie.get("name")),
            secure=cookie.get("secure") is True,
            http_only=cookie.get("httpOnly") is True,
            host_only=host_only,
            path=cookie_path,
            scheme=cookie_scheme,
        ):
            raise ValueError("Cookie security prefix is invalid.")
        if "partitionKey" in cookie and (
            not isinstance(cookie.get("partitionKey"), str) or not cookie.get("partitionKey")
        ):
            raise ValueError("Cookie partition key must be a non-empty string.")
        if cookie.get("partitionKey") is not None and cookie.get("secure") is not True:
            raise ValueError("Partitioned cookies must be Secure.")
        if "_crHasCrossSiteAncestor" in cookie and (
            cookie.get("partitionKey") is None
            or not isinstance(cookie.get("_crHasCrossSiteAncestor"), bool)
        ):
            raise ValueError("Cookie partition variant is invalid.")


def _validate_cookie_deletions(
    deletions: list[tuple[str, str, str, str | None]],
) -> None:
    if not isinstance(deletions, list):
        raise ValueError("Cookie deletions must be a list.")
    for identity in deletions:
        if (
            not isinstance(identity, tuple)
            or len(identity) != 4
            or not all(isinstance(value, str) and bool(value.strip()) for value in identity[:3])
            or (
                identity[3] is not None
                and (not isinstance(identity[3], str) or not bool(identity[3].strip()))
            )
        ):
            raise ValueError("Cookie deletion identity is invalid.")


def _canonical_cookie_deletions(
    deletions: list[tuple[str, str, str, str | None]],
) -> list[tuple[str, str, str, str | None]]:
    """Canonicalize deletion identities before any backing store is touched."""

    _validate_cookie_deletions(deletions)
    normalized: list[tuple[str, str, str, str | None]] = []
    for name, domain, path, partition_key in deletions:
        if not cookie_pair_is_safe(name, ""):
            raise ValueError("Cookie deletion name is invalid.")
        candidate: dict[str, Any] = {
            "name": name,
            "value": "",
            "domain": domain,
            "path": path,
        }
        if partition_key is not None:
            candidate["partitionKey"] = partition_key
        normalized.append(_cookie_identity(canonicalize_cookie(candidate)))
    return normalized


def _cookie_identity(
    cookie: dict[str, Any],
) -> tuple[str, str, str, str | None]:
    cookie = canonicalize_cookie(cookie)
    name = cookie.get("name")
    domain = cookie.get("domain")
    path = cookie.get("path")
    if not all(isinstance(value, str) and bool(value.strip()) for value in (name, domain, path)):
        raise ValueError("Cookie delta entries require name, domain, and path.")
    partition_key = cookie.get("partitionKey")
    return (
        name,
        domain.strip().lower(),
        path,
        str(partition_key) if partition_key is not None else None,
    )


def _cookie_variant_identity(
    cookie: dict[str, Any],
) -> tuple[str, str, str, str | None, bool | None]:
    """Include Chromium's CHIPS ancestor bit when a snapshot exposes it."""

    normalized = canonicalize_cookie(cookie)
    identity = _cookie_identity(normalized)
    variant: bool | None = None
    if normalized.get("partitionKey") is not None and "_crHasCrossSiteAncestor" in normalized:
        raw_variant = normalized.get("_crHasCrossSiteAncestor")
        if not isinstance(raw_variant, bool):
            raise ValueError("Cookie partition variant must be boolean.")
        variant = raw_variant
    return (*identity, variant)


def _browser_thread_affine(
    *,
    create_owner: bool = False,
    shutdown_after: bool = False,
    shutdown_on_failure: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Run a sync-Playwright method on its driver's single owner thread.

    Playwright's synchronous API is backed by a greenlet and every object it
    creates must continue to be used from the thread that started it. Core
    handlers are dispatched to worker threads, so all handle access is proxied
    through one serialized owner thread.
    """

    def decorate(method: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(method)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            return self._call_on_owner_thread(
                lambda: method(self, *args, **kwargs),
                create_owner=create_owner,
                shutdown_after=shutdown_after,
                shutdown_on_failure=shutdown_on_failure,
            )

        return wrapped

    return decorate


# Explicit mock-only PNG bytes; production adapters never return this test fixture.
MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class BaseBrowserDriver(ABC):
    """Abstract Browser Driver Contract."""

    _DRIVER_TYPE: BrowserDriverType

    def __init__(self, config: BrowserConfig | None = None) -> None:
        self.config: BrowserConfig = config or BrowserConfig()
        self._is_running: bool = False
        self._has_started: bool = False
        self._current_url: str = ""
        self._title: str = ""
        self._last_error_status: BrowserResultStatus | None = None
        self._last_error_code: str | None = None
        self._last_error_message: str | None = None

    @property
    def driver_type(self) -> BrowserDriverType:
        """Return the concrete adapter actually executing browser work."""
        return self._DRIVER_TYPE

    @property
    def last_error_status(self) -> BrowserResultStatus | None:
        return self._last_error_status

    @property
    def last_error_code(self) -> str | None:
        return self._last_error_code

    @property
    def last_error_message(self) -> str | None:
        return self._last_error_message

    def _record_success(self) -> None:
        self._last_error_status = None
        self._last_error_code = None
        self._last_error_message = None

    def _record_failure(
        self,
        status: BrowserResultStatus,
        code: str,
        message: str,
    ) -> None:
        self._last_error_status = status
        self._last_error_code = code
        self._last_error_message = message

    def _record_inactive_failure(self) -> None:
        if self._has_started:
            self._record_failure(
                BrowserResultStatus.DISCONNECTED,
                "BROWSER_DISCONNECTED",
                "The browser session is disconnected.",
            )
        else:
            self._record_failure(
                BrowserResultStatus.UNAVAILABLE,
                "BROWSER_DRIVER_UNAVAILABLE",
                "The browser driver is unavailable.",
            )

    @abstractmethod
    def launch(self, config: BrowserConfig | None = None) -> bool:
        """Launch and initialize the browser driver instance."""
        pass

    @abstractmethod
    def close(self) -> bool:
        """Close browser resources and report whether cleanup was verified."""
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

    def apply_cookie_delta(
        self,
        upserts: list[dict[str, Any]],
        deletions: list[tuple[str, str, str, str | None]],
    ) -> None:
        """Apply response cookie changes without replacing unrelated live state."""

        self._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_COOKIE_SYNC_UNSUPPORTED",
            "The browser driver cannot synchronize response cookie changes.",
        )

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

    _DRIVER_TYPE = BrowserDriverType.PLAYWRIGHT

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._thread_call_lock = threading.RLock()
        self._owner_executor: ThreadPoolExecutor | None = None
        self._owner_thread_id: int | None = None
        self._navigation_header_origin: tuple[str, str, int] | None = None
        self._committed_header_origin: tuple[str, str, int] | None = None
        self._main_frame_id: str | None = None
        self._header_cdp_session: Any = None
        self._explicit_navigation_in_progress = False
        self._trusted_interaction_in_progress = False
        self._header_chain_tainted = False
        self._tainted_header_networks: dict[str, None] = {}
        self._header_network_tracking_failed_closed = False
        self._pending_main_frame_header_authorized = False
        self._committed_header_authorized = False
        self._frame_header_state: dict[str, tuple[tuple[str, str, int] | None, bool]] = {}
        self._pending_frame_header_authorized: dict[str, bool] = {}
        self._frame_parents: dict[str, str] = {}

    def _install_header_interceptor(self) -> None:
        """Install per-hop Chromium interception for exact-origin page headers."""

        if self._context is None or self._page is None:
            raise RuntimeError("Browser context is unavailable.")
        session = self._context.new_cdp_session(self._page)
        self._header_cdp_session = session
        frame_tree = session.send("Page.getFrameTree")
        root_frame = ((frame_tree or {}).get("frameTree") or {}).get("frame") or {}
        self._main_frame_id = str(root_frame.get("id") or "") or None
        self._committed_header_origin = _http_origin(str(root_frame.get("url") or ""))
        if self._main_frame_id is not None:
            self._frame_header_state[self._main_frame_id] = (
                self._committed_header_origin,
                False,
            )
        session.on("Page.frameNavigated", self._on_frame_navigated)
        session.on("Page.frameAttached", self._on_frame_attached)
        session.on("Page.frameDetached", self._on_frame_detached)
        session.on("Fetch.requestPaused", self._on_request_paused)
        session.on("Network.loadingFinished", self._on_network_request_complete)
        session.on("Network.loadingFailed", self._on_network_request_complete)
        session.send("Page.enable")
        session.send("Network.enable")
        session.send(
            "Fetch.enable",
            {
                "patterns": [
                    {"urlPattern": "http://*", "requestStage": "Request"},
                    {"urlPattern": "https://*", "requestStage": "Request"},
                ]
            },
        )

    def _on_frame_navigated(self, params: dict[str, Any]) -> None:
        frame = params.get("frame") or {}
        frame_id = str(frame.get("id") or "")
        if not frame_id:
            return
        parent_id = str(frame.get("parentId") or "")
        if parent_id:
            self._frame_parents[frame_id] = parent_id
        else:
            self._main_frame_id = frame_id
        committed_origin = _http_origin(str(frame.get("url") or ""))
        authorized = bool(
            self._pending_frame_header_authorized.pop(frame_id, False)
            and committed_origin == self._navigation_header_origin
        )
        self._frame_header_state[frame_id] = (committed_origin, authorized)
        if frame_id == self._main_frame_id:
            self._committed_header_origin = committed_origin
            self._committed_header_authorized = bool(authorized and not self._header_chain_tainted)

    def _on_frame_attached(self, params: dict[str, Any]) -> None:
        frame_id = str(params.get("frameId") or "")
        parent_id = str(params.get("parentFrameId") or "")
        if frame_id and parent_id:
            self._frame_parents[frame_id] = parent_id

    def _on_frame_detached(self, params: dict[str, Any]) -> None:
        frame_id = str(params.get("frameId") or "")
        if not frame_id:
            return
        self._frame_header_state.pop(frame_id, None)
        self._pending_frame_header_authorized.pop(frame_id, None)
        self._frame_parents.pop(frame_id, None)

    @staticmethod
    def _header_network_key(params: dict[str, Any], request_id: str) -> str:
        network_id = str(params.get("networkId") or "")
        if network_id:
            return network_id
        prefix, separator, suffix = request_id.rpartition(".")
        if separator and prefix and suffix.isdigit():
            return prefix
        return request_id

    def _on_network_request_complete(self, params: dict[str, Any]) -> None:
        network_id = str(params.get("requestId") or "")
        if network_id:
            self._tainted_header_networks.pop(network_id, None)

    def _on_request_paused(self, params: dict[str, Any]) -> None:
        """Continue one paused request with credentials scoped to this hop only."""

        session = self._header_cdp_session
        request_id = str(params.get("requestId") or "")
        if session is None or not request_id:
            return
        try:
            scoped_headers = _safe_extra_headers(self.config.extra_headers)
            if not scoped_headers:
                session.send("Fetch.continueRequest", {"requestId": request_id})
                return

            request = params.get("request") or {}
            request_url = str(request.get("url") or "")
            request_origin = _http_origin(request_url)
            frame_id = str(params.get("frameId") or "")
            network_key = self._header_network_key(params, request_id)
            if request_origin != self._navigation_header_origin:
                if len(self._tainted_header_networks) >= 2048:
                    self._header_network_tracking_failed_closed = True
                else:
                    self._tainted_header_networks[network_key] = None
            network_tainted = (
                self._header_network_tracking_failed_closed
                or network_key in self._tainted_header_networks
            )
            is_main_document = (
                params.get("resourceType") == "Document" and frame_id == self._main_frame_id
            )
            is_document = params.get("resourceType") == "Document"
            if is_main_document:
                if request_origin != self._navigation_header_origin:
                    self._header_chain_tainted = True
                document_authorized = bool(
                    not self._header_chain_tainted
                    and self._navigation_header_origin is not None
                    and request_origin == self._navigation_header_origin
                    and (
                        self._explicit_navigation_in_progress
                        or (
                            self._trusted_interaction_in_progress
                            and self._committed_header_authorized
                        )
                    )
                )
                self._pending_main_frame_header_authorized = document_authorized
                self._pending_frame_header_authorized[frame_id] = document_authorized
                self._frame_header_state[frame_id] = (
                    request_origin,
                    document_authorized,
                )
            elif is_document:
                if frame_id in self._frame_header_state:
                    initiator_authorized = self._frame_header_state[frame_id][1]
                else:
                    initiator_authorized = self._frame_header_state.get(
                        self._frame_parents.get(frame_id, ""),
                        (None, False),
                    )[1]
                document_authorized = bool(
                    not network_tainted
                    and self._navigation_header_origin is not None
                    and request_origin == self._navigation_header_origin
                    and initiator_authorized
                )
                self._pending_frame_header_authorized[frame_id] = document_authorized
                self._frame_header_state[frame_id] = (
                    request_origin,
                    document_authorized,
                )
            else:
                document_authorized = False
            frame_authorized = self._frame_header_state.get(
                frame_id,
                (
                    self._committed_header_origin,
                    self._committed_header_authorized,
                )
                if frame_id and frame_id == self._main_frame_id
                else (None, False),
            )[1]
            may_inject = (
                not network_tainted
                and self._navigation_header_origin is not None
                and request_origin == self._navigation_header_origin
                and (document_authorized or (not is_document and frame_authorized))
            )
            configured_names = {name.lower() for name in scoped_headers}
            headers = [
                {"name": str(name), "value": str(value)}
                for name, value in dict(request.get("headers") or {}).items()
                if str(name).lower() not in configured_names
            ]
            if may_inject:
                headers.extend(
                    {"name": name, "value": value} for name, value in scoped_headers.items()
                )
            session.send(
                "Fetch.continueRequest",
                {"requestId": request_id, "headers": headers},
            )
        except Exception:
            logger.error("Browser request header scoping failed.")
            try:
                session.send(
                    "Fetch.failRequest",
                    {"requestId": request_id, "errorReason": "BlockedByClient"},
                )
            except Exception:
                pass

    def _execute_owner_call(self, operation: Callable[[], Any]) -> Any:
        self._owner_thread_id = threading.get_ident()
        return operation()

    def _call_on_owner_thread(
        self,
        operation: Callable[[], Any],
        *,
        create_owner: bool = False,
        shutdown_after: bool = False,
        shutdown_on_failure: bool = False,
    ) -> Any:
        """Serialize an operation onto the thread that owns Playwright handles."""

        if threading.get_ident() == self._owner_thread_id:
            try:
                result = operation()
            except Exception:
                if shutdown_on_failure:
                    self._shutdown_owner_executor(wait=False)
                raise
            if shutdown_after or (shutdown_on_failure and result is False):
                self._shutdown_owner_executor(wait=False)
            return result

        with self._thread_call_lock:
            executor = self._owner_executor
            if executor is None:
                if not create_owner:
                    return operation()
                executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="JARVISBrowserOwner",
                )
                self._owner_executor = executor

            completed = False
            result: Any = None
            try:
                result = executor.submit(self._execute_owner_call, operation).result()
                completed = True
                return result
            finally:
                if shutdown_after or (shutdown_on_failure and (not completed or result is False)):
                    self._shutdown_owner_executor(executor=executor, wait=True)

    def _shutdown_owner_executor(
        self,
        *,
        executor: ThreadPoolExecutor | None = None,
        wait: bool,
    ) -> None:
        active_executor = executor or self._owner_executor
        if active_executor is None:
            return
        active_executor.shutdown(wait=wait)
        if self._owner_executor is active_executor:
            self._owner_executor = None
            self._owner_thread_id = None

    def _record_playwright_exception(self, action: str, exc: Exception) -> None:
        """Normalize Playwright exceptions without exposing raw page data or secrets."""
        exc_name = type(exc).__name__.lower()
        exc_text = str(exc).lower()
        if "timeout" in exc_name:
            messages = {
                "navigate": "Browser navigation timed out.",
                "wait": "Timed out waiting for the browser element.",
            }
            self._record_failure(
                BrowserResultStatus.TIMEOUT,
                "BROWSER_TIMEOUT",
                messages.get(action, "The browser action timed out."),
            )
        elif (
            any(
                marker in exc_text
                for marker in (
                    "target page, context or browser has been closed",
                    "browser has been closed",
                    "page has been closed",
                    "target closed",
                    "browser disconnected",
                    "connection closed",
                )
            )
            or "targetclosed" in exc_name
        ):
            self._is_running = False
            self._record_failure(
                BrowserResultStatus.DISCONNECTED,
                "BROWSER_DISCONNECTED",
                "The browser session is disconnected.",
            )
        elif any(
            marker in exc_text
            for marker in (
                "not a valid selector",
                "unexpected token",
                "error while parsing selector",
                "unknown engine",
            )
        ):
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_SELECTOR",
                "The browser selector is invalid.",
            )
        else:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_ACTION_ERROR",
                "The browser action failed.",
            )

    def _on_disconnected(self, *_args: Any) -> None:
        self._is_running = False
        self._record_failure(
            BrowserResultStatus.DISCONNECTED,
            "BROWSER_DISCONNECTED",
            "The browser session is disconnected.",
        )

    @_browser_thread_affine(create_owner=True, shutdown_on_failure=True)
    def launch(self, config: BrowserConfig | None = None) -> bool:
        if self.is_running():
            return True
        if config:
            self.config = config
            self._endpoint = config.cdp_endpoint.rstrip("/")
        if (
            any(
                resource is not None
                for resource in (
                    self._page,
                    self._context,
                    self._browser,
                    self._playwright,
                )
            )
            and not self._close_resources()
        ):
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_CLOSE_FAILED",
                "Stale browser resources could not be closed cleanly.",
            )
            return False
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
            self._browser.on("disconnected", self._on_disconnected)
            context_options: dict[str, Any] = {
                "user_agent": self.config.user_agent,
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                "accept_downloads": self.config.accept_downloads,
            }
            self._context = self._browser.new_context(**context_options)
            self._page = self._context.new_page()
            self._install_header_interceptor()
            self._page.set_default_timeout(self.config.timeout_ms)
            self._is_running = True
            self._has_started = True
            self._record_success()
            logger.info("PlaywrightBrowserDriver successfully launched.")
            return True
        except ImportError:
            logger.warning("Playwright is not installed in the current environment.")
            self._is_running = False
            self._record_failure(
                BrowserResultStatus.NOT_CONFIGURED,
                "BROWSER_PLAYWRIGHT_NOT_CONFIGURED",
                "Playwright is not installed for browser control.",
            )
            return False
        except Exception:
            logger.error("Playwright browser launch failed.")
            self._close_resources()
            self._record_failure(
                BrowserResultStatus.UNAVAILABLE,
                "BROWSER_PLAYWRIGHT_UNAVAILABLE",
                "The Playwright browser is unavailable.",
            )
            return False

    def _close_resources(self) -> bool:
        header_session = self._header_cdp_session
        page = self._page
        context = self._context
        browser = self._browser
        playwright = self._playwright
        self._header_cdp_session = None
        self._main_frame_id = None
        self._committed_header_origin = None
        self._explicit_navigation_in_progress = False
        self._trusted_interaction_in_progress = False
        self._header_chain_tainted = False
        self._tainted_header_networks.clear()
        self._header_network_tracking_failed_closed = False
        self._pending_main_frame_header_authorized = False
        self._committed_header_authorized = False
        self._frame_header_state.clear()
        self._pending_frame_header_authorized.clear()
        self._frame_parents.clear()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._is_running = False
        clean = True
        for resource, method_name in (
            (header_session, "detach"),
            (page, "close"),
            (context, "close"),
            (browser, "close"),
            (playwright, "stop"),
        ):
            if resource is None:
                continue
            try:
                getattr(resource, method_name)()
            except Exception:
                clean = False
                logger.debug("A Playwright resource could not be closed cleanly.")
        return clean

    @_browser_thread_affine(shutdown_after=True)
    def close(self) -> bool:
        clean = self._close_resources()
        if clean:
            self._record_success()
        else:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_CLOSE_FAILED",
                "The browser session could not be closed cleanly.",
            )
        return clean

    def is_running(self) -> bool:
        """Check the live browser and page handles, not only a cached flag."""
        if not self._is_running or self._browser is None or self._page is None:
            return False
        return bool(self._call_on_owner_thread(self._is_running_on_owner_thread))

    def _is_running_on_owner_thread(self) -> bool:
        try:
            active = self._browser.is_connected() and not self._page.is_closed()
        except Exception:
            active = False
        if not active:
            self._on_disconnected()
        return active

    @_browser_thread_affine()
    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return False
        self._navigation_header_origin = _http_origin(url)
        if self.config.extra_headers and self._navigation_header_origin is None:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_URL",
                "The browser navigation URL is invalid.",
            )
            return False
        self._header_chain_tainted = False
        self._pending_main_frame_header_authorized = False
        try:
            self._explicit_navigation_in_progress = True
            valid_wait = (
                wait_until
                if wait_until in ("load", "domcontentloaded", "networkidle", "commit")
                else "domcontentloaded"
            )
            response = self._page.goto(
                url,
                wait_until=valid_wait,
                timeout=self.config.timeout_ms,
            )
            self._current_url = self._page.url
            self._title = self._page.title()
            if response is not None and response.status >= 400:
                if response.status == 401:
                    status = BrowserResultStatus.AUTH_FAILED
                    code = "BROWSER_AUTH_FAILED"
                elif response.status in (403, 451):
                    status = BrowserResultStatus.BLOCKED
                    code = "BROWSER_ACCESS_BLOCKED"
                elif response.status == 429:
                    status = BrowserResultStatus.RATE_LIMITED
                    code = "BROWSER_RATE_LIMITED"
                elif response.status in (408, 504):
                    status = BrowserResultStatus.TIMEOUT
                    code = "BROWSER_TIMEOUT"
                elif response.status >= 500:
                    status = BrowserResultStatus.UNAVAILABLE
                    code = "BROWSER_NAVIGATION_UNAVAILABLE"
                else:
                    status = BrowserResultStatus.ERROR
                    code = "BROWSER_HTTP_ERROR"
                self._record_failure(
                    status,
                    code,
                    f"Browser navigation returned HTTP {response.status}.",
                )
                return False
            self._record_success()
            return True
        except Exception as exc:
            self._record_playwright_exception("navigate", exc)
            logger.error("Playwright navigation failed (%s).", self.last_error_code)
            return False
        finally:
            self._explicit_navigation_in_progress = False

    @_browser_thread_affine()
    def click(self, selector: str, timeout_ms: int = 5000) -> bool:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return False
        try:
            self._trusted_interaction_in_progress = bool(
                self._committed_header_authorized
                and self._committed_header_origin == self._navigation_header_origin
            )
            self._page.click(selector, timeout=timeout_ms)
            self._current_url = self._page.url
            self._title = self._page.title()
            self._record_success()
            return True
        except Exception as exc:
            self._record_playwright_exception("click", exc)
            logger.error("Playwright click failed (%s).", self.last_error_code)
            return False
        finally:
            self._trusted_interaction_in_progress = False

    @_browser_thread_affine()
    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return False
        try:
            if clear:
                self._page.fill(selector, "")
            self._page.type(selector, text, delay=delay_ms)
            actual_value = self._page.input_value(selector)
            if (clear and actual_value != text) or (not clear and not actual_value.endswith(text)):
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_WRITE_NOT_APPLIED",
                    "The browser text entry was not applied.",
                )
                return False
            self._record_success()
            return True
        except Exception as exc:
            self._record_playwright_exception("type", exc)
            logger.error("Playwright text entry failed (%s).", self.last_error_code)
            return False

    @_browser_thread_affine()
    def select_option(self, selector: str, value: str) -> bool:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return False
        try:
            selected = self._page.select_option(selector, value)
            if value not in selected:
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_SELECTION_NOT_APPLIED",
                    "The browser selection was not applied.",
                )
                return False
            self._record_success()
            return True
        except Exception as exc:
            self._record_playwright_exception("select", exc)
            logger.error("Playwright selection failed (%s).", self.last_error_code)
            return False

    @_browser_thread_affine()
    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return False
        try:
            valid_state = (
                state if state in ("attached", "detached", "visible", "hidden") else "visible"
            )
            self._page.wait_for_selector(selector, state=valid_state, timeout=timeout_ms)
            self._record_success()
            return True
        except Exception as exc:
            self._record_playwright_exception("wait", exc)
            logger.debug(
                "Playwright wait_for_selector failed (%s).",
                self.last_error_code,
            )
            return False

    @_browser_thread_affine()
    def evaluate_script(self, script: str, *args: Any) -> Any:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return None
        try:
            result = self._page.evaluate(script, *args)
            self._record_success()
            return result
        except Exception as exc:
            self._record_playwright_exception("evaluate", exc)
            logger.error("Playwright script evaluation failed (%s).", self.last_error_code)
            return None

    @_browser_thread_affine()
    def get_html(self) -> str:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return ""
        try:
            content = self._page.content()
            self._record_success()
            return content
        except Exception as exc:
            self._record_playwright_exception("read", exc)
            logger.error("Playwright DOM read failed (%s).", self.last_error_code)
            return ""

    @_browser_thread_affine()
    def get_text(self, selector: str | None = None) -> str:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return ""
        try:
            if selector:
                elem = self._page.query_selector(selector)
                if elem is None:
                    self._record_failure(
                        BrowserResultStatus.ERROR,
                        "BROWSER_ELEMENT_NOT_FOUND",
                        "The browser element was not found.",
                    )
                    return ""
                text = elem.inner_text()
            else:
                text = self._page.inner_text("body")
            self._record_success()
            return text
        except Exception as exc:
            self._record_playwright_exception("read", exc)
            logger.error("Playwright text read failed (%s).", self.last_error_code)
            return ""

    @_browser_thread_affine()
    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
            return b""
        try:
            screenshot = self._page.screenshot(full_page=full_page)
            if not screenshot:
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_SCREENSHOT_EMPTY",
                    "The browser screenshot was empty.",
                )
                return b""
            self._record_success()
            return screenshot
        except Exception as exc:
            self._record_playwright_exception("screenshot", exc)
            logger.error("Playwright screenshot failed (%s).", self.last_error_code)
            return b""

    @_browser_thread_affine()
    def get_cookies(self) -> list[dict[str, Any]]:
        if not self.is_running() or not self._context:
            self._record_inactive_failure()
            return []
        try:
            cookies = self._context.cookies()
            self._record_success()
            return cookies
        except Exception as exc:
            self._record_playwright_exception("cookies", exc)
            logger.error("Playwright cookie read failed (%s).", self.last_error_code)
            return []

    @_browser_thread_affine()
    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        if not self.is_running() or not self._context:
            self._record_inactive_failure()
            return
        try:
            _validate_playwright_cookie_snapshot(cookies)
        except ValueError:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_COOKIE",
                "The browser cookie payload is invalid.",
            )
            return
        self.apply_cookie_delta(cookies, [])

    @_browser_thread_affine()
    def apply_cookie_delta(
        self,
        upserts: list[dict[str, Any]],
        deletions: list[tuple[str, str, str, str | None]],
    ) -> None:
        if not self.is_running() or not self._context or not self._header_cdp_session:
            self._record_inactive_failure()
            return
        previous: list[dict[str, Any]] = []
        affected: set[tuple[str, str, str, str | None]] = set()
        mutated = False
        try:
            normalized_by_variant: dict[
                tuple[str, str, str, str | None, bool | None], dict[str, Any]
            ] = {}
            for cookie in upserts:
                normalized = canonicalize_cookie(cookie)
                normalized_by_variant[_cookie_variant_identity(normalized)] = normalized
            normalized_upserts = list(normalized_by_variant.values())
            _validate_playwright_cookie_snapshot(normalized_upserts)
            normalized_deletions = _canonical_cookie_deletions(deletions)
            affected.update(_cookie_identity(cookie) for cookie in normalized_upserts)
            affected.update(normalized_deletions)
            before = [dict(cookie) for cookie in self._context.cookies()]
            previous = [cookie for cookie in before if _cookie_identity(cookie) in affected]

            def delete_identity(
                identity: tuple[str, str, str, str | None],
                snapshot: list[dict[str, Any]],
            ) -> None:
                name, domain, path, partition_key = identity
                delete_params: dict[str, Any] = {
                    "name": name,
                    "domain": domain,
                    "path": path,
                }
                if partition_key is None:
                    self._header_cdp_session.send(
                        "Network.deleteCookies",
                        delete_params,
                    )
                    return
                variants = {
                    bool(cookie.get("_crHasCrossSiteAncestor", True))
                    for cookie in snapshot
                    if _cookie_identity(cookie) == identity
                }
                # If the public snapshot cannot expose a hidden variant, delete
                # both CDP identities rather than report a ghost success.
                if not variants:
                    variants = {False, True}
                for has_cross_site_ancestor in variants:
                    partitioned_params = dict(delete_params)
                    partitioned_params["partitionKey"] = {
                        "topLevelSite": partition_key,
                        "hasCrossSiteAncestor": has_cross_site_ancestor,
                    }
                    self._header_cdp_session.send(
                        "Network.deleteCookies",
                        partitioned_params,
                    )

            def add_entries(entries: list[dict[str, Any]]) -> None:
                public_entries: list[dict[str, Any]] = []
                for entry in entries:
                    expires = entry.get("expires")
                    expired = expires is not None and (
                        float(expires) == 0
                        or (float(expires) > 0 and float(expires) <= time.time())
                    )
                    if expired:
                        delete_params: dict[str, Any] = {
                            "name": str(entry["name"]),
                            "domain": str(entry["domain"]),
                            "path": str(entry["path"]),
                        }
                        if entry.get("partitionKey") is not None:
                            delete_params["partitionKey"] = {
                                "topLevelSite": str(entry["partitionKey"]),
                                "hasCrossSiteAncestor": bool(
                                    entry["_crHasCrossSiteAncestor"]
                                ),
                            }
                        self._header_cdp_session.send(
                            "Network.deleteCookies",
                            delete_params,
                        )
                        continue
                    if "_crHasCrossSiteAncestor" not in entry:
                        public_entries.append(entry)
                        continue
                    params = {
                        key: entry[key]
                        for key in (
                            "name",
                            "value",
                            "domain",
                            "path",
                            "secure",
                            "httpOnly",
                            "sameSite",
                        )
                        if key in entry
                    }
                    if isinstance(expires, (int, float)) and float(expires) > 0:
                        params["expires"] = float(expires)
                    params["partitionKey"] = {
                        "topLevelSite": str(entry["partitionKey"]),
                        "hasCrossSiteAncestor": bool(entry["_crHasCrossSiteAncestor"]),
                    }
                    result = self._header_cdp_session.send(
                        "Network.setCookie",
                        params,
                    )
                    if isinstance(result, dict) and result.get("success") is False:
                        raise RuntimeError("Partitioned cookie upsert was rejected.")
                if public_entries:
                    self._context.add_cookies(public_entries)

            for identity in normalized_deletions:
                delete_identity(
                    identity,
                    before,
                )
                mutated = True
            if upserts:
                mutated = True
                add_entries(normalized_upserts)

            after = [dict(cookie) for cookie in self._context.cookies()]
            for identity in affected:
                observed = [cookie for cookie in after if _cookie_identity(cookie) == identity]
                expected_entries = [
                    cookie for cookie in normalized_upserts if _cookie_identity(cookie) == identity
                ]
                if not expected_entries:
                    if observed:
                        raise RuntimeError("Cookie deletion was not applied.")
                    continue
                for expected in expected_entries:
                    expected_variant = expected.get("_crHasCrossSiteAncestor")
                    expected_observed = [
                        cookie
                        for cookie in observed
                        if "_crHasCrossSiteAncestor" not in expected
                        or cookie.get("_crHasCrossSiteAncestor") == expected_variant
                    ]
                    expires = expected.get("expires")
                    expired = expires is not None and (
                        float(expires) == 0
                        or (float(expires) > 0 and float(expires) <= time.time())
                    )
                    if expired:
                        if expected_observed:
                            raise RuntimeError("Expired cookie mutation was not applied.")
                        continue
                    matching = [
                        cookie
                        for cookie in expected_observed
                        if str(cookie.get("value") or "") == str(expected.get("value") or "")
                        and all(
                            key not in expected or cookie.get(key) == expected.get(key)
                            for key in ("secure", "httpOnly", "sameSite")
                        )
                    ]
                    if not matching:
                        raise RuntimeError("Cookie upsert was not applied.")
                    if "expires" in expected:
                        observed_expiry = matching[0].get("expires")
                        if (
                            not isinstance(observed_expiry, (int, float))
                            or not math.isfinite(float(observed_expiry))
                            or abs(float(observed_expiry) - float(expected["expires"])) > 2.0
                        ):
                            raise RuntimeError("Cookie expiry was not applied.")
            self._record_success()
        except ValueError:
            if mutated:
                try:
                    current = [dict(cookie) for cookie in self._context.cookies()]
                    for identity in affected:
                        delete_identity(identity, current)
                    if previous:
                        add_entries(previous)
                except Exception:
                    logger.error("Playwright cookie delta rollback failed.")
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_COOKIE_SYNC_FAILED",
                    "The browser cookie changes could not be synchronized.",
                )
            else:
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_INVALID_COOKIE",
                    "The browser cookie payload is invalid.",
                )
        except Exception:
            if mutated:
                try:
                    current = [dict(cookie) for cookie in self._context.cookies()]
                    for identity in affected:
                        delete_identity(identity, current)
                    if previous:
                        add_entries(previous)
                except Exception:
                    logger.error("Playwright cookie delta rollback failed.")
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_COOKIE_SYNC_FAILED",
                "The browser cookie changes could not be synchronized.",
            )
            logger.error("Playwright cookie delta failed (%s).", self.last_error_code)

    @_browser_thread_affine()
    def get_current_url(self) -> str:
        if self._page:
            try:
                self._current_url = self._page.url
            except Exception:
                pass
        return self._current_url

    @_browser_thread_affine()
    def get_title(self) -> str:
        if self._page:
            try:
                self._title = self._page.title()
            except Exception:
                pass
        return self._title

    @_browser_thread_affine()
    def find_elements(self, selector: str) -> list[PageElement]:
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
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
            self._record_success()
        except Exception as exc:
            self._record_playwright_exception("read", exc)
            logger.debug("Playwright element query failed (%s).", self.last_error_code)
        return results

    @_browser_thread_affine()
    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_SCROLL_DISTANCE",
                "The browser scroll distance is invalid.",
            )
            return False
        if not self.is_running() or not self._page:
            self._record_inactive_failure()
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
            else:
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_INVALID_SCROLL_DIRECTION",
                    "The browser scroll direction is invalid.",
                )
                return False
            self._record_success()
            return True
        except Exception as exc:
            self._record_playwright_exception("scroll", exc)
            logger.error("Playwright scroll failed (%s).", self.last_error_code)
            return False


# ---------------------------------------------------------------------------
# Tier 2: Chrome DevTools Protocol (CDP) Browser Driver
# ---------------------------------------------------------------------------


class CDPBrowserDriver(PlaywrightBrowserDriver):
    """Tier 2 adapter attaching Playwright to a real Chromium CDP endpoint."""

    _DRIVER_TYPE = BrowserDriverType.CDP

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self._endpoint = (config.cdp_endpoint if config else "http://127.0.0.1:9222").rstrip("/")

    @_browser_thread_affine(create_owner=True, shutdown_on_failure=True)
    def launch(self, config: BrowserConfig | None = None) -> bool:
        if self.is_running():
            return True
        if config:
            self.config = config
            self._endpoint = config.cdp_endpoint.rstrip("/")
        if any(
            resource is not None
            for resource in (
                self._page,
                self._context,
                self._browser,
                self._playwright,
            )
        ):
            if not self._cleanup_connection():
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_CLOSE_FAILED",
                    "Stale CDP resources could not be closed cleanly.",
                )
                return False
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(
                self._endpoint,
                timeout=self.config.timeout_ms,
                slow_mo=self.config.slow_mo_ms,
                headers=self.config.cdp_headers or None,
            )
            contexts = self._browser.contexts
            if not contexts:
                raise RuntimeError("CDP endpoint exposed no browser context.")
            self._context = contexts[0]
            live_pages = [page for page in self._context.pages if not page.is_closed()]
            self._page = live_pages[0] if live_pages else self._context.new_page()
            self._install_header_interceptor()
            self._page.set_default_timeout(self.config.timeout_ms)
            self._browser.on("disconnected", self._on_disconnected)
            self._current_url = self._page.url
            self._title = self._page.title()
            self._is_running = True
            self._has_started = True
            self._record_success()
            logger.info("CDPBrowserDriver attached to a Chromium browser session.")
            return True
        except ImportError:
            failure = (
                BrowserResultStatus.NOT_CONFIGURED,
                "BROWSER_PLAYWRIGHT_NOT_CONFIGURED",
                "Playwright is not installed for CDP browser control.",
            )
        except Exception as exc:
            logger.debug("CDP attach failed (%s).", type(exc).__name__)
            failure = (
                BrowserResultStatus.UNAVAILABLE,
                "BROWSER_CDP_UNAVAILABLE",
                "The Chromium CDP endpoint is unavailable.",
            )
        self._cleanup_connection()
        self._record_failure(*failure)
        return False

    def _cleanup_connection(self) -> bool:
        header_session = self._header_cdp_session
        browser = self._browser
        playwright = self._playwright
        self._header_cdp_session = None
        self._main_frame_id = None
        self._committed_header_origin = None
        self._explicit_navigation_in_progress = False
        self._trusted_interaction_in_progress = False
        self._header_chain_tainted = False
        self._tainted_header_networks.clear()
        self._header_network_tracking_failed_closed = False
        self._pending_main_frame_header_authorized = False
        self._committed_header_authorized = False
        self._frame_header_state.clear()
        self._pending_frame_header_authorized.clear()
        self._frame_parents.clear()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._is_running = False
        clean = True
        if header_session is not None:
            try:
                header_session.detach()
            except Exception:
                clean = False
        if browser is not None:
            try:
                browser.close()
            except Exception:
                clean = False
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                clean = False
        return clean

    @_browser_thread_affine(shutdown_after=True)
    def close(self) -> bool:
        """Close the attached browser session and release the Playwright client."""
        clean = self._cleanup_connection()
        if clean:
            self._record_success()
        else:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_CLOSE_FAILED",
                "The CDP browser session could not be closed cleanly.",
            )
        return clean


# ---------------------------------------------------------------------------
# Tier 3: HTTP Scraping Driver (Zero-Browser Fallback)
# ---------------------------------------------------------------------------


class HttpScrapingDriver(BaseBrowserDriver):
    """
    Tier 3 Zero-Browser Scraping Driver.
    Uses `requests.Session` with an internal virtual DOM representation, cookie jar,
    and form state tracker. Requires zero external browser binaries.
    """

    _DRIVER_TYPE = BrowserDriverType.HTTP_SCRAPER

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self._session: Any = None
        self._cookie_store: list[dict[str, Any]] = []
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
            self._cookie_store = []
            self._session.headers.update(
                {
                    "User-Agent": self.config.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
                }
            )
            if self.config.proxy:
                self._session.proxies.update(
                    {"http": self.config.proxy, "https": self.config.proxy}
                )
            self._is_running = True
            self._has_started = True
            self._record_success()
            logger.info("HttpScrapingDriver initialized.")
            return True
        except Exception:
            logger.error("HTTP scraper initialization failed.")
            self._is_running = False
            self._record_failure(
                BrowserResultStatus.NOT_CONFIGURED,
                "BROWSER_HTTP_NOT_CONFIGURED",
                "The HTTP scraper is not configured.",
            )
            return False

    def close(self) -> bool:
        clean = True
        if self._session:
            try:
                self._session.close()
            except Exception:
                clean = False
        self._session = None
        self._cookie_store = []
        self._html_content = ""
        self._is_running = False
        if clean:
            self._record_success()
        else:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_CLOSE_FAILED",
                "The HTTP browser session could not be closed cleanly.",
            )
        return clean

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        self._html_content = ""
        self._elements_cache = []
        self._current_url = ""
        self._title = ""
        if not self._is_running and not self.launch():
            return False
        try:
            import requests

            timeout_sec = max(1.0, self.config.timeout_ms / 1000.0)
            initial_url = requests.Request("GET", url).prepare().url
            if not initial_url:
                raise ValueError("Invalid browser navigation URL.")
            current_url = initial_url
            headers_allowed = True
            resp: Any = None
            for redirect_count in range(11):
                prepared_url = requests.Request("GET", current_url).prepare().url
                if not prepared_url:
                    raise ValueError("Invalid browser navigation URL.")
                current_url = prepared_url
                try:
                    parsed_target = urllib.parse.urlsplit(current_url)
                except (TypeError, ValueError):
                    parsed_target = urllib.parse.SplitResult("", "", "", "", "")
                if (
                    parsed_target.scheme.lower() not in {"http", "https"}
                    or not parsed_target.hostname
                ):
                    self._record_failure(
                        BrowserResultStatus.ERROR,
                        "BROWSER_INVALID_URL",
                        "The browser navigation URL is invalid.",
                    )
                    return False
                initial_origin = self._exact_origin(initial_url)
                current_origin = self._exact_origin(current_url)
                if initial_origin is None or current_origin != initial_origin:
                    headers_allowed = False
                request_headers = (
                    self._headers_for_url(initial_url, current_url) if headers_allowed else {}
                )
                cookie_header = self._cookie_header_for_url(current_url, initial_url)
                if cookie_header:
                    request_headers["Cookie"] = cookie_header
                resp = self._session.get(
                    current_url,
                    timeout=timeout_sec,
                    allow_redirects=False,
                    headers=request_headers,
                )
                self._merge_session_cookies(resp, current_url)
                status_code = int(resp.status_code)
                if 300 <= status_code < 400:
                    location = resp.headers.get("location")
                    resp.close()
                    if (
                        status_code not in {301, 302, 303, 307, 308}
                        or not location
                        or redirect_count >= 10
                    ):
                        self._record_failure(
                            BrowserResultStatus.ERROR,
                            "BROWSER_REDIRECT_ERROR",
                            "The browser redirect could not be followed safely.",
                        )
                        return False
                    current_url = urllib.parse.urljoin(current_url, location)
                    continue
                break

            if resp is None:
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_NAVIGATION_ERROR",
                    "Browser navigation failed.",
                )
                return False
            self._status_code = resp.status_code
            if resp.status_code >= 400:
                if resp.status_code == 401:
                    status = BrowserResultStatus.AUTH_FAILED
                    code = "BROWSER_AUTH_FAILED"
                elif resp.status_code in (403, 451):
                    status = BrowserResultStatus.BLOCKED
                    code = "BROWSER_ACCESS_BLOCKED"
                elif resp.status_code == 429:
                    status = BrowserResultStatus.RATE_LIMITED
                    code = "BROWSER_RATE_LIMITED"
                elif resp.status_code in (408, 504):
                    status = BrowserResultStatus.TIMEOUT
                    code = "BROWSER_TIMEOUT"
                elif resp.status_code >= 500:
                    status = BrowserResultStatus.UNAVAILABLE
                    code = "BROWSER_NAVIGATION_UNAVAILABLE"
                else:
                    status = BrowserResultStatus.ERROR
                    code = "BROWSER_HTTP_ERROR"
                self._current_url = resp.url
                self._record_failure(
                    status,
                    code,
                    f"Browser navigation returned HTTP {resp.status_code}.",
                )
                return False
            self._html_content = resp.text
            self._current_url = resp.url
            self._parse_page_metadata()
            self._rebuild_elements_cache()
            self._record_success()
            return True
        except requests.exceptions.ReadTimeout:
            self._record_failure(
                BrowserResultStatus.TIMEOUT,
                "BROWSER_TIMEOUT",
                "Browser navigation timed out while waiting for a response.",
            )
            return False
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
            self._record_failure(
                BrowserResultStatus.UNAVAILABLE,
                "BROWSER_NAVIGATION_UNAVAILABLE",
                "The browser destination is unavailable.",
            )
            return False
        except Exception:
            logger.error("HTTP scraper navigation failed.")
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_NAVIGATION_ERROR",
                "Browser navigation failed.",
            )
            return False

    def _parse_page_metadata(self) -> None:
        """Extract document title and meta information."""
        title_match = re.search(
            r"<title[^>]*>(.*?)</title>", self._html_content, re.IGNORECASE | re.DOTALL
        )
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
            selector = (
                f"{tag}[name='{attrs.get('name')}']"
                if attrs.get("name")
                else (f"#{attrs.get('id')}" if attrs.get("id") else tag)
            )
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
        self._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
            "The active HTTP scraper cannot perform interactive click actions.",
        )
        return False

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
                resp = self._session.get(
                    action_url, params=self._form_state, timeout=self.config.timeout_ms / 1000.0
                )
            else:
                resp = self._session.post(
                    action_url, data=self._form_state, timeout=self.config.timeout_ms / 1000.0
                )

            self._html_content = resp.text
            self._current_url = resp.url
            self._parse_page_metadata()
            self._rebuild_elements_cache()
            return resp.status_code < 400
        except Exception as exc:
            logger.error(
                "HTTP scraper form submission failed (%s).",
                type(exc).__name__,
            )
            return False

    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        self._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
            "The active HTTP scraper cannot perform interactive typing actions.",
        )
        return False

    def select_option(self, selector: str, value: str) -> bool:
        return self.type_text(selector, value)

    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        self._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
            "The active HTTP scraper cannot wait for dynamic browser state.",
        )
        return False

    def evaluate_script(self, script: str, *args: Any) -> Any:
        self._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
            "The active HTTP scraper cannot evaluate browser scripts.",
        )
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
        cleaned = re.sub(
            r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.IGNORECASE | re.DOTALL
        )
        # Strip all HTML tags
        stripped = re.sub(r"<[^>]+>", " ", cleaned)
        return " ".join(html.unescape(stripped).split())

    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        self._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
            "The active HTTP scraper cannot capture a browser screenshot.",
        )
        return b""

    def get_cookies(self) -> list[dict[str, Any]]:
        if not self._is_running or not self._session:
            self._record_inactive_failure()
            return []
        self._record_success()
        return [dict(cookie) for cookie in self._cookie_store]

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        if not self._is_running or not self._session:
            self._record_inactive_failure()
            return
        try:
            normalized_cookies: list[dict[str, Any]] = []
            for cookie in cookies:
                normalized = canonicalize_cookie(cookie)
                if normalized.get("sameSite") is not None:
                    same_site = _canonical_same_site(normalized.get("sameSite"))
                    if same_site is None:
                        raise ValueError("Cookie SameSite value is invalid.")
                    normalized["sameSite"] = same_site
                normalized_cookies.append(normalized)
            _validate_playwright_cookie_snapshot(normalized_cookies)
            entries: list[dict[str, Any]] = []
            for cookie in normalized_cookies:
                _cookie_identity(cookie)
                entry = {
                    key: value
                    for key, value in cookie.items()
                    if key
                    in {
                        "name",
                        "value",
                        "domain",
                        "path",
                        "secure",
                        "httpOnly",
                        "sameSite",
                        "partitionKey",
                        "_crHasCrossSiteAncestor",
                        "expires",
                    }
                }
                entries.append(entry)
        except Exception:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_COOKIE",
                "The browser cookie payload is invalid.",
            )
            return

        previous = [dict(cookie) for cookie in self._cookie_store]
        try:
            for entry in entries:
                self._upsert_cookie(entry)
            self._record_success()
        except ValueError:
            self._cookie_store = previous
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_COOKIE",
                "The browser cookie payload is invalid.",
            )
        except Exception:
            self._cookie_store = previous
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_COOKIE_SYNC_FAILED",
                "The HTTP browser cookies could not be synchronized.",
            )

    def apply_cookie_delta(
        self,
        upserts: list[dict[str, Any]],
        deletions: list[tuple[str, str, str, str | None]],
    ) -> None:
        if not self._is_running or not self._session:
            self._record_inactive_failure()
            return
        previous = [dict(cookie) for cookie in self._cookie_store]
        try:
            normalized_upserts = [canonicalize_cookie(cookie) for cookie in upserts]
            _validate_playwright_cookie_snapshot(normalized_upserts)
            normalized_deletions = _canonical_cookie_deletions(deletions)
            for name, domain, path, partition_key in normalized_deletions:
                self._delete_cookie(name, domain, path, partition_key)
            for cookie in normalized_upserts:
                _cookie_identity(cookie)
                self._upsert_cookie(cookie)
            self._record_success()
        except ValueError:
            self._cookie_store = previous
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_COOKIE",
                "The browser cookie payload is invalid.",
            )
        except Exception:
            self._cookie_store = previous
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_COOKIE_SYNC_FAILED",
                "The HTTP browser cookie changes could not be synchronized.",
            )

    @staticmethod
    def _exact_origin(url: str) -> tuple[str, str, int] | None:
        """Return a normalized HTTP origin for redirect credential scoping."""

        try:
            parsed = urllib.parse.urlsplit(url)
            scheme = parsed.scheme.lower()
            hostname = canonical_cookie_hostname(parsed.hostname or "")
            port = parsed.port
        except (AttributeError, TypeError, ValueError):
            return None
        if scheme not in {"http", "https"} or not hostname:
            return None
        if port is None:
            port = 443 if scheme == "https" else 80
        return scheme, hostname, port

    def _headers_for_url(self, initial_url: str, current_url: str) -> dict[str, str]:
        """Keep caller-provided headers on the initial exact origin only."""

        initial_origin = self._exact_origin(initial_url)
        if initial_origin is None or self._exact_origin(current_url) != initial_origin:
            return {}
        forbidden = {"cookie", "host", "content-length", "proxy-authorization"}
        return {
            str(name): str(value)
            for name, value in (self.config.extra_headers or {}).items()
            if str(name).lower() not in forbidden
        }

    def _cookie_header_for_url(
        self,
        url: str,
        top_level_url: str | None = None,
    ) -> str:
        """Select and serialize persisted cookies for one HTTP request hop."""

        return build_cookie_header(self._cookie_store, url, top_level_url)

    def _upsert_cookie(self, cookie: dict[str, Any]) -> None:
        """Store one cookie without weakening its observed domain/path scope."""

        cookie = canonicalize_cookie(cookie)
        key = _cookie_variant_identity(cookie)
        self._cookie_store = [
            existing for existing in self._cookie_store if _cookie_variant_identity(existing) != key
        ]
        if "expires" in cookie:
            try:
                expires = float(cookie["expires"])
            except (TypeError, ValueError):
                return
            if not math.isfinite(expires):
                return
            if expires == 0 or (expires > 0 and expires <= time.time()):
                return
        self._cookie_store.append(dict(cookie))

    def _delete_cookie(
        self,
        name: str,
        domain: str,
        path: str,
        partition_key: str | None = None,
    ) -> None:
        """Delete one cookie using the same host/domain/path identity as storage."""

        normalized_domain = domain.strip().lower()
        normalized_path = path or "/"
        self._cookie_store = [
            cookie
            for cookie in self._cookie_store
            if _cookie_identity(cookie) != (name, normalized_domain, normalized_path, partition_key)
        ]

    @staticmethod
    def _set_cookie_headers(response: Any) -> list[str]:
        """Read individual Set-Cookie fields without splitting Expires commas."""

        raw_headers = getattr(getattr(response, "raw", None), "headers", None)
        if raw_headers is not None:
            for accessor_name in ("getlist", "get_all"):
                accessor = getattr(raw_headers, accessor_name, None)
                if callable(accessor):
                    try:
                        values = accessor("Set-Cookie")
                    except Exception:
                        values = None
                    if values:
                        return [str(value) for value in values]
        headers = getattr(response, "headers", {}) or {}
        value = headers.get("Set-Cookie") or headers.get("set-cookie")
        return [str(value)] if value else []

    @staticmethod
    def _default_cookie_path(request_path: str) -> str:
        if not request_path.startswith("/") or request_path.count("/") <= 1:
            return "/"
        return request_path.rsplit("/", 1)[0] or "/"

    def _apply_response_cookie_headers(self, response: Any, request_url: str) -> bool:
        """Apply ordered Set-Cookie fields without weakening their observed scope."""

        headers = self._set_cookie_headers(response)
        if not headers:
            return False

        for header in headers:
            action = parse_response_cookie_action(header, request_url)
            if action is None or response_action_overlays_secure_cookie(
                action,
                self._cookie_store,
                request_url,
            ):
                continue
            for name, domain, path, partition_key in action.deletions:
                self._delete_cookie(name, domain, path, partition_key)
            if action.upsert is not None:
                self._upsert_cookie(action.upsert)
        return True

    def _merge_session_cookies(self, response: Any, request_url: str) -> None:
        """Capture response cookies, preserving host-only versus domain scope."""

        if not self._session:
            return
        applied_headers = self._apply_response_cookie_headers(response, request_url)
        if applied_headers:
            self._session.cookies.clear()
            return
        try:
            parsed_request = urllib.parse.urlsplit(request_url)
            request_scheme = parsed_request.scheme.lower()
            request_host = canonical_cookie_hostname(parsed_request.hostname or "")
            default_path = self._default_cookie_path(parsed_request.path or "/")
        except (AttributeError, TypeError, ValueError):
            request_scheme = ""
            request_host = ""
            default_path = "/"
        for cookie in self._session.cookies:
            if not cookie_pair_is_safe(cookie.name, cookie.value):
                continue
            try:
                domain = canonical_cookie_hostname(str(cookie.domain or "").lower().lstrip("."))
            except ValueError:
                continue
            domain_specified = bool(cookie.domain_specified)
            if (
                not domain
                or (
                    domain_specified
                    and not cookie_domain_attribute_is_allowed(request_host, domain)
                )
                or (not domain_specified and domain != request_host)
            ):
                continue
            secure = bool(cookie.secure)
            if secure and request_scheme != "https":
                continue
            path = normalize_cookie_path(cookie.path, default_path)
            if not cookie_path_is_valid(path):
                continue
            rest = {
                str(name).lower(): value
                for name, value in (getattr(cookie, "_rest", {}) or {}).items()
            }
            if "partitioned" in rest:
                # Requests cannot derive a valid CHIPS top-level partition.
                continue
            http_only = "httponly" in rest
            if not cookie_prefix_is_valid(
                cookie.name,
                secure=secure,
                http_only=http_only,
                host_only=not domain_specified,
                path=path,
                scheme=request_scheme,
            ):
                continue
            entry: dict[str, Any] = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": response_domain_storage_domain(
                    request_host,
                    domain_specified,
                    domain,
                ),
                "path": path,
                "secure": secure,
            }
            if cookie.expires is not None:
                try:
                    numeric_expires = float(cookie.expires)
                except (TypeError, ValueError):
                    continue
                if (
                    not math.isfinite(numeric_expires)
                    or numeric_expires == 0
                    or (numeric_expires > 0 and numeric_expires <= time.time())
                ):
                    continue
                entry["expires"] = cookie.expires
            if http_only:
                entry["httpOnly"] = True
            same_site = _canonical_same_site(rest.get("samesite"))
            if same_site == "None" and not secure:
                continue
            if same_site is not None:
                entry["sameSite"] = same_site
            action = ResponseCookieAction(upsert=entry)
            if response_action_overlays_secure_cookie(
                action,
                self._cookie_store,
                request_url,
            ):
                continue
            self._upsert_cookie(entry)
        self._session.cookies.clear()

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
            elif (
                selector.startswith(".") and selector[1:] in el.attributes.get("class", "").split()
            ):
                results.append(el)
        return results

    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        self._record_failure(
            BrowserResultStatus.UNAVAILABLE,
            "BROWSER_CAPABILITY_UNAVAILABLE",
            "The active HTTP scraper cannot scroll a browser page.",
        )
        return False


# ---------------------------------------------------------------------------
# Tier 4: Mock Browser Driver (100% Deterministic CI/CD Test Isolation)
# ---------------------------------------------------------------------------


class MockBrowserDriver(BaseBrowserDriver):
    """
    Tier 4 Mock Browser Driver.
    Simulates a fully interactive DOM in memory with action logs, custom fixtures,
    synthetic screenshots, and script evaluation without requiring network or external processes.
    """

    _DRIVER_TYPE = BrowserDriverType.MOCK

    def __init__(self, config: BrowserConfig | None = None) -> None:
        super().__init__(config)
        self.action_log: list[dict[str, Any]] = []
        self.elements: dict[str, PageElement] = {}
        self.cookies: list[dict[str, Any]] = []
        self.html_content: str = (
            "<html><head><title>Mock Page</title></head><body><h1>Mock Content</h1></body></html>"
        )
        self.script_eval_results: dict[str, Any] = {}
        self.navigation_history: list[str] = []
        self._title = "Mock Page"
        self._current_url = "http://mock.local"

    def set_fixture_html(
        self, html_str: str, url: str = "http://mock.local", title: str = "Mock Page"
    ) -> None:
        """Populate the mock driver with a synthetic HTML payload."""
        self.html_content = html_str
        self._current_url = url
        self._title = title
        self.elements.clear()

        # Parse basic elements into simulated DOM
        for tag in (
            "input",
            "button",
            "select",
            "a",
            "div",
            "p",
            "table",
            "h1",
            "h2",
            "h3",
            "form",
        ):
            matches = re.findall(
                rf"<{tag}\s+([^>]*?)>(.*?)</{tag}>|<{tag}\s+([^>]*?)/?>",
                html_str,
                re.IGNORECASE | re.DOTALL,
            )
            for m in matches:
                attr_str = m[0] or m[2]
                inner = m[1]
                attrs = HttpScrapingDriver._extract_attributes(attr_str)
                sel_id = attrs.get("id")
                sel_name = attrs.get("name")
                selector = (
                    f"#{sel_id}" if sel_id else (f"{tag}[name='{sel_name}']" if sel_name else tag)
                )
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
        self._has_started = True
        self._record_success()
        self.action_log.append({"action": "launch", "timestamp": time.time()})
        return True

    def close(self) -> bool:
        self._is_running = False
        self.action_log.append({"action": "close", "timestamp": time.time()})
        self._record_success()
        return True

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        if not self._is_running:
            self._record_inactive_failure()
            return False
        self._current_url = url
        self.navigation_history.append(url)
        self.action_log.append({"action": "navigate", "url": url, "timestamp": time.time()})
        if "google" in url:
            self._title = "Google Search"
        elif "github" in url:
            self._title = "GitHub: Let's build from here"
        self._record_success()
        return True

    def click(self, selector: str, timeout_ms: int = 5000) -> bool:
        if not self._is_running:
            self._record_inactive_failure()
            return False
        self.action_log.append({"action": "click", "selector": selector, "timestamp": time.time()})
        if selector in self.elements:
            el = self.elements[selector]
            if el.tag_name == "a" and "href" in el.attributes:
                return self.navigate(el.attributes["href"])
        self._record_success()
        return True

    def type_text(
        self,
        selector: str,
        text: str,
        delay_ms: int = 50,
        clear: bool = False,
    ) -> bool:
        if not self._is_running:
            self._record_inactive_failure()
            return False
        self.action_log.append(
            {"action": "type_text", "selector": selector, "text": text, "timestamp": time.time()}
        )
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
        self._record_success()
        return True

    def select_option(self, selector: str, value: str) -> bool:
        if not self._is_running:
            self._record_inactive_failure()
            return False
        self.action_log.append(
            {
                "action": "select_option",
                "selector": selector,
                "value": value,
                "timestamp": time.time(),
            }
        )
        if selector in self.elements:
            self.elements[selector].value = value
        self._record_success()
        return True

    def wait_for_selector(
        self,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 10000,
    ) -> bool:
        if not self._is_running:
            self._record_inactive_failure()
            return False
        self.action_log.append(
            {"action": "wait_for_selector", "selector": selector, "state": state}
        )
        self._record_success()
        return True

    def evaluate_script(self, script: str, *args: Any) -> Any:
        if not self._is_running:
            self._record_inactive_failure()
            return None
        self.action_log.append({"action": "evaluate_script", "script": script, "args": args})
        if "jarvis:apply-local-storage" in script and args:
            payload = args[0] if isinstance(args[0], dict) else {}
            parsed = urllib.parse.urlsplit(self._current_url)
            scheme = parsed.scheme.lower()
            try:
                hostname = canonical_cookie_hostname(parsed.hostname or "")
            except ValueError:
                self._record_failure(
                    BrowserResultStatus.ERROR,
                    "BROWSER_INVALID_URL",
                    "The browser origin is invalid.",
                )
                return False
            rendered_host = f"[{hostname}]" if ":" in hostname else hostname
            port = parsed.port
            default_port = 443 if scheme == "https" else 80
            suffix = "" if port in {None, default_port} else f":{port}"
            actual_origin = f"{scheme}://{rendered_host}{suffix}"
            self._record_success()
            return payload.get("origin") == actual_origin
        if "jarvis:capture-local-storage" in script and args:
            expected_origin = args[0]
            legacy_value = self.script_eval_results.get(
                "JSON.stringify(window.localStorage);",
                "{}",
            )
            try:
                storage = json.loads(legacy_value) if isinstance(legacy_value, str) else {}
            except (TypeError, ValueError):
                storage = {}
            self._record_success()
            return {
                "origin": expected_origin,
                "entries": [[str(key), str(value)] for key, value in storage.items()],
            }
        if (
            script == "JSON.stringify(window.localStorage);"
            and script not in self.script_eval_results
        ):
            self._record_success()
            return "{}"
        self._record_success()
        return self.script_eval_results.get(script, "mock_result")

    def get_html(self) -> str:
        return self.html_content

    def get_text(self, selector: str | None = None) -> str:
        if selector and selector in self.elements:
            return self.elements[selector].text
        cleaned = re.sub(r"<[^>]+>", " ", self.html_content)
        return " ".join(cleaned.split())

    def capture_page_screenshot(self, full_page: bool = False) -> bytes:
        if not self._is_running:
            self._record_inactive_failure()
            return b""
        self.action_log.append({"action": "capture_page_screenshot", "full_page": full_page})
        self._record_success()
        return MINIMAL_PNG_BYTES

    def get_cookies(self) -> list[dict[str, Any]]:
        if not self._is_running:
            self._record_inactive_failure()
            return []
        self._record_success()
        return list(self.cookies)

    def set_cookies(self, cookies: list[dict[str, Any]]) -> None:
        if not self._is_running:
            self._record_inactive_failure()
            return
        try:
            normalized_cookies = [canonicalize_cookie(cookie) for cookie in cookies]
            _validate_playwright_cookie_snapshot(normalized_cookies)
        except Exception:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_COOKIE",
                "The browser cookie payload is invalid.",
            )
            return
        for cookie in normalized_cookies:
            identity = _cookie_variant_identity(cookie)
            self.cookies = [
                existing
                for existing in self.cookies
                if _cookie_variant_identity(existing) != identity
            ]
            if "expires" in cookie:
                expires = float(cookie["expires"])
                if expires == 0 or (expires > 0 and expires <= time.time()):
                    continue
            self.cookies.append(dict(cookie))
        self.action_log.append({"action": "set_cookies", "count": len(normalized_cookies)})
        self._record_success()

    def apply_cookie_delta(
        self,
        upserts: list[dict[str, Any]],
        deletions: list[tuple[str, str, str, str | None]],
    ) -> None:
        if not self._is_running:
            self._record_inactive_failure()
            return
        previous = [dict(cookie) for cookie in self.cookies]
        try:
            normalized_upserts = [canonicalize_cookie(cookie) for cookie in upserts]
            _validate_playwright_cookie_snapshot(normalized_upserts)
            deletion_keys = set(_canonical_cookie_deletions(deletions))
            self.cookies = [
                cookie for cookie in self.cookies if _cookie_identity(cookie) not in deletion_keys
            ]
            for cookie in normalized_upserts:
                identity = _cookie_variant_identity(cookie)
                self.cookies = [
                    existing
                    for existing in self.cookies
                    if _cookie_variant_identity(existing) != identity
                ]
                if "expires" in cookie:
                    expires = float(cookie["expires"])
                    if expires == 0 or (expires > 0 and expires <= time.time()):
                        continue
                self.cookies.append(dict(cookie))
            self.action_log.append(
                {
                    "action": "apply_cookie_delta",
                    "upserts": len(upserts),
                    "deletions": len(deletions),
                }
            )
            self._record_success()
        except ValueError:
            self.cookies = previous
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_COOKIE",
                "The browser cookie payload is invalid.",
            )
        except Exception:
            self.cookies = previous
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_COOKIE_SYNC_FAILED",
                "The mock browser cookie changes could not be synchronized.",
            )

    def get_current_url(self) -> str:
        return self._current_url

    def get_title(self) -> str:
        return self._title

    def find_elements(self, selector: str) -> list[PageElement]:
        if not self._is_running:
            self._record_inactive_failure()
            return []
        if selector in self.elements:
            self._record_success()
            return [self.elements[selector]]
        self._record_success()
        return list(self.elements.values())

    def scroll(self, direction: str = "down", distance: int = 500) -> bool:
        if isinstance(distance, bool) or not isinstance(distance, int) or distance < 0:
            self._record_failure(
                BrowserResultStatus.ERROR,
                "BROWSER_INVALID_SCROLL_DISTANCE",
                "The browser scroll distance is invalid.",
            )
            return False
        if not self._is_running:
            self._record_inactive_failure()
            return False
        self.action_log.append({"action": "scroll", "direction": direction, "distance": distance})
        self._record_success()
        return True


# ---------------------------------------------------------------------------
# Driver Factory & Auto-Detection
# ---------------------------------------------------------------------------


class DriverFactory:
    """Factory resolving the optimal browser driver tier with automatic graceful fallback."""

    @staticmethod
    def detect_best_driver() -> BrowserDriverType:
        """Detect the best available browser driver tier.

        Verifies a real local Playwright launch, then probes CDP on port 9222,
        falling back to the read-only HTTP scraper.
        """
        playwright_driver = PlaywrightBrowserDriver(BrowserConfig())
        launched = False
        closed = False
        try:
            launched = playwright_driver.launch()
        except Exception:
            logger.debug("Playwright runtime availability probe failed.")
        finally:
            try:
                closed = playwright_driver.close()
            except Exception:
                closed = False
        if launched and closed:
            return BrowserDriverType.PLAYWRIGHT

        cdp_config = BrowserConfig(
            driver_type=BrowserDriverType.CDP,
            cdp_endpoint="http://127.0.0.1:9222",
            timeout_ms=500,
        )
        cdp_driver = CDPBrowserDriver(cdp_config)
        cdp_launched = False
        cdp_closed = False
        try:
            cdp_launched = cdp_driver.launch(cdp_config)
        except Exception:
            logger.debug("CDP runtime availability probe failed.")
        finally:
            try:
                cdp_closed = cdp_driver.close()
            except Exception:
                cdp_closed = False
        if cdp_launched and cdp_closed:
            return BrowserDriverType.CDP

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
            pw_driver = PlaywrightBrowserDriver(cfg)
            playwright_launched = False
            try:
                playwright_launched = pw_driver.launch(cfg)
                if playwright_launched:
                    return pw_driver
            except Exception as exc:
                logger.warning(
                    "Playwright driver launch failed (%s); trying the next tier.",
                    type(exc).__name__,
                )
            finally:
                if not playwright_launched:
                    try:
                        pw_driver.close()
                    except Exception as exc:
                        logger.debug(
                            "Failed Playwright candidate cleanup (%s).",
                            type(exc).__name__,
                        )

        # 3. Tier 2: CDP
        if target_type in (BrowserDriverType.CDP, BrowserDriverType.PLAYWRIGHT):
            cdp_driver = CDPBrowserDriver(cfg)
            cdp_launched = False
            try:
                cdp_launched = cdp_driver.launch(cfg)
                if cdp_launched:
                    return cdp_driver
            except Exception as exc:
                logger.warning(
                    "CDP driver launch failed (%s); trying the HTTP tier.",
                    type(exc).__name__,
                )
            finally:
                if not cdp_launched:
                    try:
                        cdp_driver.close()
                    except Exception as exc:
                        logger.debug(
                            "Failed CDP candidate cleanup (%s).",
                            type(exc).__name__,
                        )

        # 4. Tier 3: Zero-Browser HTTP Scraping Driver (Always reliable fallback)
        http_driver = HttpScrapingDriver(cfg)
        http_driver.launch(cfg)
        return http_driver


# Expose at module level
detect_best_driver = DriverFactory.detect_best_driver
