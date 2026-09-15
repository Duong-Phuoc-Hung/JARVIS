"""Thread ownership and lifecycle contracts for the sync Playwright adapters."""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from jarvis.browser.driver import (
    CDPBrowserDriver,
    DriverFactory,
    HttpScrapingDriver,
    PlaywrightBrowserDriver,
)
from jarvis.browser.models import BrowserConfig, BrowserDriverType, BrowserResultStatus


class _CallTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.thread_ids: set[int] = set()

    def run(self, value: Any) -> Any:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.thread_ids.add(threading.get_ident())
        try:
            time.sleep(0.02)
            return value
        finally:
            with self._lock:
                self.active -= 1


class _FakePage:
    def __init__(self, tracker: _CallTracker | None = None) -> None:
        self.url = "about:blank"
        self._closed = False
        self._tracker = tracker

    def set_default_timeout(self, _timeout_ms: int) -> None:
        return None

    def set_extra_http_headers(self, _headers: dict[str, str]) -> None:
        return None

    def route(self, _pattern: str, _handler: Any) -> None:
        return None

    def is_closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True

    def title(self) -> str:
        return "Fake Playwright Page"

    def evaluate(self, script: str, *_args: Any) -> Any:
        if self._tracker is None:
            return script
        return self._tracker.run(script)


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False

    def new_page(self) -> _FakePage:
        return self._page

    @property
    def pages(self) -> list[_FakePage]:
        return [self._page]

    def new_cdp_session(self, _page: _FakePage) -> "_FakeCDPSession":
        return _FakeCDPSession()

    def close(self) -> None:
        self.closed = True


class _FakeCDPSession:
    def __init__(self) -> None:
        self.listeners: dict[str, Any] = {}
        self.detached = False

    def on(self, event: str, callback: Any) -> None:
        self.listeners[event] = callback

    def send(self, method: str, _params: Any = None) -> dict[str, Any]:
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "main-frame", "url": "about:blank"}}}
        return {}

    def detach(self) -> None:
        self.detached = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self._context = context
        self._connected = True
        self._listeners: dict[str, Any] = {}

    def on(self, event: str, callback: Any) -> None:
        self._listeners[event] = callback

    @property
    def contexts(self) -> list[_FakeContext]:
        return [self._context]

    def new_context(self, **_options: Any) -> _FakeContext:
        return self._context

    def is_connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self._connected = False


class _FakeChromium:
    def __init__(self, state: _FakePlaywrightState) -> None:
        self._state = state

    def launch(self, **_options: Any) -> _FakeBrowser:
        self._state.launch_count += 1
        return self._state.browser

    def connect_over_cdp(self, endpoint: str, **_options: Any) -> _FakeBrowser:
        self._state.cdp_endpoints.append(endpoint)
        self._state.cdp_options.append(dict(_options))
        return self._state.browser


class _FakePlaywright:
    def __init__(self, state: _FakePlaywrightState) -> None:
        self._state = state
        self.chromium = _FakeChromium(state)

    def stop(self) -> None:
        self._state.stop_count += 1


class _FakePlaywrightState:
    def __init__(self, tracker: _CallTracker | None = None) -> None:
        self.start_count = 0
        self.launch_count = 0
        self.stop_count = 0
        self.cdp_endpoints: list[str] = []
        self.cdp_options: list[dict[str, Any]] = []
        self.page = _FakePage(tracker)
        self.context = _FakeContext(self.page)
        self.browser = _FakeBrowser(self.context)

    def sync_playwright(self) -> Any:
        state = self

        class _Starter:
            def start(self) -> _FakePlaywright:
                state.start_count += 1
                return _FakePlaywright(state)

        return _Starter()


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch, sync_playwright: Any) -> None:
    package = ModuleType("playwright")
    package.__path__ = []  # type: ignore[attr-defined]
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = sync_playwright  # type: ignore[attr-defined]
    package.sync_api = sync_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_inactive_action_does_not_create_owner_executor() -> None:
    driver = PlaywrightBrowserDriver()

    assert driver.click("#not-running") is False
    assert driver.last_error_status is BrowserResultStatus.UNAVAILABLE
    assert driver._owner_executor is None
    assert driver._owner_thread_id is None


def test_failed_launch_releases_owner_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingStarter:
        def start(self) -> Any:
            raise RuntimeError("synthetic launch failure")

    _install_fake_playwright(monkeypatch, lambda: _FailingStarter())
    driver = PlaywrightBrowserDriver()

    assert driver.launch() is False
    assert driver.last_error_status is BrowserResultStatus.UNAVAILABLE
    assert driver._owner_executor is None
    assert driver._owner_thread_id is None


def test_double_launch_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakePlaywrightState()
    _install_fake_playwright(monkeypatch, state.sync_playwright)
    driver = PlaywrightBrowserDriver()

    try:
        assert driver.launch() is True
        first_browser = driver._browser

        assert driver.launch() is True
        assert driver._browser is first_browser
        assert state.start_count == 1
        assert state.launch_count == 1
    finally:
        assert driver.close() is True


def test_cdp_launch_uses_replacement_config_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _FakePlaywrightState()
    _install_fake_playwright(monkeypatch, state.sync_playwright)
    driver = CDPBrowserDriver(
        BrowserConfig(
            driver_type=BrowserDriverType.CDP,
            cdp_endpoint="http://127.0.0.1:9222",
        )
    )
    replacement = BrowserConfig(
        driver_type=BrowserDriverType.CDP,
        cdp_endpoint="http://127.0.0.1:9333/",
        extra_headers={"Authorization": "Bearer page-only"},
        cdp_headers={"Authorization": "Bearer cdp-only"},
    )

    try:
        assert driver.launch(replacement) is True
        assert state.cdp_endpoints == ["http://127.0.0.1:9333"]
        assert state.cdp_options[0]["headers"] == {"Authorization": "Bearer cdp-only"}
    finally:
        assert driver.close() is True


def test_stale_handle_cleanup_failure_fails_launch_closed() -> None:
    class _UncloseablePage:
        def close(self) -> None:
            raise RuntimeError("stale page stayed open")

    driver = PlaywrightBrowserDriver()
    driver._page = _UncloseablePage()
    driver._has_started = True

    assert driver.launch() is False
    assert driver.last_error_status is BrowserResultStatus.ERROR
    assert driver.last_error_code == "BROWSER_CLOSE_FAILED"
    assert driver._page is None
    assert driver._owner_executor is None
    assert driver._owner_thread_id is None


def test_detection_rejects_playwright_when_probe_close_is_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_calls = 0

    def launch(_driver: PlaywrightBrowserDriver, _config: Any = None) -> bool:
        return True

    def close(_driver: PlaywrightBrowserDriver) -> bool:
        nonlocal close_calls
        close_calls += 1
        return False

    monkeypatch.setattr(PlaywrightBrowserDriver, "launch", launch)
    monkeypatch.setattr(PlaywrightBrowserDriver, "close", close)
    monkeypatch.setattr(
        "requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=503),
    )

    assert DriverFactory.detect_best_driver() is BrowserDriverType.HTTP_SCRAPER
    assert close_calls == 1


@pytest.mark.parametrize("failure_mode", ["false", "exception"])
def test_factory_closes_each_failed_browser_candidate(
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    playwright_closed: list[PlaywrightBrowserDriver] = []
    cdp_closed: list[CDPBrowserDriver] = []

    def failed_launch(_driver: PlaywrightBrowserDriver, _config: Any = None) -> bool:
        if failure_mode == "exception":
            raise RuntimeError("candidate launch failure")
        return False

    def close_playwright(driver: PlaywrightBrowserDriver) -> bool:
        playwright_closed.append(driver)
        return True

    def close_cdp(driver: CDPBrowserDriver) -> bool:
        cdp_closed.append(driver)
        return True

    def launch_http(driver: HttpScrapingDriver, _config: Any = None) -> bool:
        driver._is_running = True
        return True

    monkeypatch.setattr(PlaywrightBrowserDriver, "launch", failed_launch)
    monkeypatch.setattr(PlaywrightBrowserDriver, "close", close_playwright)
    monkeypatch.setattr(CDPBrowserDriver, "launch", failed_launch)
    monkeypatch.setattr(CDPBrowserDriver, "close", close_cdp)
    monkeypatch.setattr(HttpScrapingDriver, "launch", launch_http)

    result = DriverFactory.create_driver(driver_type=BrowserDriverType.PLAYWRIGHT)

    assert isinstance(result, HttpScrapingDriver)
    assert len(playwright_closed) == 1
    assert len(cdp_closed) == 1


def test_concurrent_calls_are_serialized_on_one_owner_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _CallTracker()
    state = _FakePlaywrightState(tracker)
    _install_fake_playwright(monkeypatch, state.sync_playwright)
    driver = PlaywrightBrowserDriver()
    worker_count = 8
    callers: set[int] = set()
    callers_lock = threading.Lock()
    start_barrier = threading.Barrier(worker_count)

    def evaluate(index: int) -> Any:
        with callers_lock:
            callers.add(threading.get_ident())
        start_barrier.wait(timeout=2)
        return driver.evaluate_script(f"value-{index}")

    try:
        assert driver.launch() is True
        owner_thread_id = driver._owner_thread_id
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(evaluate, range(worker_count)))

        assert results == [f"value-{index}" for index in range(worker_count)]
        assert tracker.max_active == 1
        assert tracker.thread_ids == {owner_thread_id}
        assert tracker.thread_ids.isdisjoint(callers)
    finally:
        assert driver.close() is True
