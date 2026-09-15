"""Concurrency contract for canonical browser actions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from jarvis.browser.actions import BrowserActionExecutor
from jarvis.browser.agent import BrowserAgent
from jarvis.browser.driver import MockBrowserDriver
from jarvis.browser.models import BrowserConfig, BrowserDriverType


def test_concurrent_navigation_results_cannot_observe_another_action_url() -> None:
    """A result must describe the navigation that produced it, not a later action."""

    driver = MockBrowserDriver()
    assert driver.launch() is True
    first_started = Event()
    second_started = Event()
    original_navigate = driver.navigate

    def interleaving_navigate(url: str, wait_until: str = "domcontentloaded") -> bool:
        result = original_navigate(url, wait_until)
        if url.endswith("/first"):
            first_started.set()
            second_started.wait(timeout=0.2)
        else:
            second_started.set()
        return result

    driver.navigate = interleaving_navigate  # type: ignore[method-assign]
    actions = BrowserActionExecutor(driver)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(actions.navigate, "https://example.test/first")
        assert first_started.wait(timeout=1.0)
        second_future = pool.submit(actions.navigate, "https://example.test/second")
        first_result = first_future.result(timeout=2.0)
        second_result = second_future.result(timeout=2.0)

    assert first_result.url == "https://example.test/first"
    assert second_result.url == "https://example.test/second"


def test_concurrent_agent_navigation_captures_the_matching_page_session() -> None:
    """Session capture must remain coupled to the navigation that triggered it."""

    first_capture_started = Event()
    second_navigation_finished = Event()
    captures: list[tuple[str, str]] = []

    class RecordingSessions:
        def load_session(self, _url: str) -> None:
            return None

        def capture_from_driver(
            self,
            active_driver: MockBrowserDriver,
            domain: str,
        ) -> bool:
            if domain.endswith("/first"):
                first_capture_started.set()
                second_navigation_finished.wait(timeout=0.2)
            captures.append((domain, active_driver.get_current_url()))
            return domain == active_driver.get_current_url()

    config = BrowserConfig(driver_type=BrowserDriverType.MOCK)
    driver = MockBrowserDriver(config)
    assert driver.launch() is True
    original_navigate = driver.navigate

    def observed_navigate(url: str, wait_until: str = "domcontentloaded") -> bool:
        result = original_navigate(url, wait_until)
        if url.endswith("/second"):
            second_navigation_finished.set()
        return result

    driver.navigate = observed_navigate  # type: ignore[method-assign]
    agent = BrowserAgent(
        config=config,
        driver=driver,
        session_manager=RecordingSessions(),  # type: ignore[arg-type]
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(agent.navigate, "https://example.test/first")
        assert first_capture_started.wait(timeout=1.0)
        second_future = pool.submit(agent.navigate, "https://example.test/second")
        first_result = first_future.result(timeout=2.0)
        second_result = second_future.result(timeout=2.0)

    assert first_result.metadata["session_captured"] is True
    assert second_result.metadata["session_captured"] is True
    assert captures == [
        ("https://example.test/first", "https://example.test/first"),
        ("https://example.test/second", "https://example.test/second"),
    ]
