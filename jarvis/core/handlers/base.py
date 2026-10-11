"""
jarvis/core/handlers/base.py
============================
Shared utility helpers, string wrappers, and alias dictionaries for JARVIS action handlers.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from jarvis.browser.models import BrowserConfig, BrowserDriverType


def _safe_browser_failure_url(url: str) -> str:
    """Return only a credential-free origin for failed browser responses."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme}://{host}{port}"
    except (TypeError, ValueError):
        return ""


class _DualErrorStr(str):
    """String subclass matching both human-readable message and machine error code."""

    def __new__(cls, msg: str, code: str) -> _DualErrorStr:
        obj = super().__new__(cls, msg)
        obj.code = code
        return obj

    def __eq__(self, other: Any) -> bool:
        return str(self) == other or getattr(self, "code", None) == other

    def __hash__(self) -> int:
        return hash(str(self))


class BaseActionService:
    """Base class for composed action service domains in JARVIS (Composition pattern)."""

    def __init__(self, app: Any = None) -> None:
        self._app = app

    @property
    def app(self) -> Any:
        app_ref = self.__dict__.get("_app", None)
        return app_ref if app_ref is not None else self

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        app = self.__dict__.get("_app", None)
        if app is not None and app is not self and hasattr(app, name):
            return getattr(app, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


def _build_browser_config(
    browser_cfg: dict[str, Any],
    *,
    session_dir: str,
    app_headless: bool,
) -> BrowserConfig:
    """Map the application configuration onto the canonical browser contract."""
    defaults = BrowserConfig()
    raw_driver = browser_cfg.get(
        "driver_type",
        browser_cfg.get("driver", defaults.driver_type.value),
    )
    driver_type = (
        raw_driver
        if isinstance(raw_driver, BrowserDriverType)
        else BrowserDriverType(str(raw_driver).strip().lower())
    )
    extra_headers = browser_cfg.get("extra_headers", {})
    if not isinstance(extra_headers, dict):
        raise ValueError("browser.extra_headers must be a mapping")
    cdp_headers = browser_cfg.get("cdp_headers", {})
    if not isinstance(cdp_headers, dict):
        raise ValueError("browser.cdp_headers must be a mapping")
    return BrowserConfig(
        driver_type=driver_type,
        headless=bool(browser_cfg.get("headless", app_headless)),
        user_agent=str(browser_cfg.get("user_agent", defaults.user_agent)),
        viewport_width=int(browser_cfg.get("viewport_width", defaults.viewport_width)),
        viewport_height=int(browser_cfg.get("viewport_height", defaults.viewport_height)),
        timeout_ms=int(browser_cfg.get("timeout_ms", defaults.timeout_ms)),
        downloads_dir=str(browser_cfg.get("downloads_dir", defaults.downloads_dir)),
        session_storage_dir=session_dir,
        cdp_endpoint=str(browser_cfg.get("cdp_endpoint", defaults.cdp_endpoint)),
        proxy=browser_cfg.get("proxy"),
        accept_downloads=bool(
            browser_cfg.get("accept_downloads", defaults.accept_downloads)
        ),
        slow_mo_ms=int(browser_cfg.get("slow_mo_ms", defaults.slow_mo_ms)),
        extra_headers={str(key): str(value) for key, value in extra_headers.items()},
        cdp_headers={str(key): str(value) for key, value in cdp_headers.items()},
    )


# Deterministic system_power sub-action alias normalization. Keys are matched
# case-insensitively/trimmed against the incoming "action"/"power_action"
# parameter; values are the canonical action _handle_system_power() acts on.
_POWER_ACTION_ALIASES: dict[str, str] = {
    "shutdown": "shutdown",
    "power_off": "shutdown",
    "poweroff": "shutdown",
    "power off": "shutdown",
    "turn_off": "shutdown",
    "restart": "restart",
    "reboot": "restart",
    "sleep": "sleep",
    "suspend": "sleep",
    "hibernate": "hibernate",
    "lock": "lock",
    "lock_screen": "lock",
    "lock screen": "lock",
    "screen_off": "screen_off",
    "screen off": "screen_off",
    "turn_off_screen": "screen_off",
    "abort": "abort",
    "cancel": "abort",
    "abort_shutdown": "abort",
    "cancel_shutdown": "abort",
    "cancel shutdown": "abort",
    "abort shutdown": "abort",
    "huy_tat_may": "abort",
    "huy tat may": "abort",
    "huy": "abort",
}

# Canonical power actions with no trustworthy, authoritative backend anywhere
# in this repository today.
_UNSUPPORTED_POWER_ACTIONS: frozenset[str] = frozenset({"shutdown", "restart", "sleep", "hibernate"})

