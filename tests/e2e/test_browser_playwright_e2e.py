"""T-01 deterministic real-Playwright tests against the loopback site."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from base64 import b64decode
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from jarvis.browser.agent import BrowserAgent
from jarvis.browser.cdp_controller import BrowserCDPController
from jarvis.browser.cdp_controller import (
    BrowserConfig as LegacyBrowserConfig,
)
from jarvis.browser.driver import CDPBrowserDriver, PlaywrightBrowserDriver
from jarvis.browser.models import BrowserConfig, BrowserDriverType, BrowserResultStatus
from jarvis.browser.scraper import PriceComparisonAggregator
from jarvis.browser.session import BrowserSessionManager
from jarvis.core.app import JarvisApp
from tests.browser_test_site import LocalBrowserTestSite

pytestmark = pytest.mark.browser_e2e


def _require_opt_in() -> None:
    if os.environ.get("JARVIS_RUN_BROWSER_E2E") != "1":
        pytest.skip("Set JARVIS_RUN_BROWSER_E2E=1 to run real Chromium tests.")


def _evidence_path(filename: str) -> Path | None:
    root_value = os.environ.get("JARVIS_BROWSER_EVIDENCE_DIR")
    if not root_value:
        return None
    root = Path(root_value)
    root.mkdir(parents=True, exist_ok=True)
    return root / filename


def _write_result_evidence(filename: str, result) -> None:
    path = _evidence_path(filename)
    if path is None:
        return
    payload = {
        "success": result.success,
        "status": result.status.value,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "driver_type": result.driver_type.value if result.driver_type else None,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def real_agent(tmp_path):
    _require_opt_in()
    config = BrowserConfig(
        driver_type=BrowserDriverType.PLAYWRIGHT,
        headless=True,
        timeout_ms=500,
        slow_mo_ms=0,
        session_storage_dir=str(tmp_path / "sessions"),
    )
    driver = PlaywrightBrowserDriver(config)
    sessions = BrowserSessionManager(
        storage_dir=str(tmp_path / "sessions"),
        db_path=str(tmp_path / "sessions.db"),
    )
    agent = BrowserAgent(config=config, driver=driver, session_manager=sessions)
    try:
        if not agent.start():
            pytest.fail("Real Playwright Chromium failed to launch; no fallback is allowed.")
        assert type(agent.driver) is PlaywrightBrowserDriver
        yield agent
    finally:
        agent.stop()


@pytest.fixture
def real_cdp_agent(tmp_path):
    _require_opt_in()
    requests = pytest.importorskip("requests")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.fail("Playwright is required for the real CDP E2E test.")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        cdp_port = probe.getsockname()[1]

    owner_browser = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "cdp_browser_host.py"),
            str(cdp_port),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    endpoint = f"http://127.0.0.1:{cdp_port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{endpoint}/json/version", timeout=0.2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.05)
    else:
        return_code = owner_browser.poll()
        if return_code is None:
            owner_browser.terminate()
        _, diagnostic = owner_browser.communicate(timeout=5)
        pytest.fail(
            "Chromium did not expose the local CDP endpoint "
            f"(return_code={return_code}, stderr={diagnostic!r})."
        )

    config = BrowserConfig(
        driver_type=BrowserDriverType.CDP,
        headless=True,
        timeout_ms=5_000,
        cdp_endpoint=endpoint,
        session_storage_dir=str(tmp_path / "cdp-sessions"),
    )
    driver = CDPBrowserDriver(config)
    sessions = BrowserSessionManager(
        storage_dir=str(tmp_path / "cdp-sessions"),
        db_path=str(tmp_path / "cdp-sessions.db"),
    )
    agent = BrowserAgent(config=config, driver=driver, session_manager=sessions)
    try:
        if not agent.start():
            return_code = owner_browser.poll()
            owner_stderr = ""
            if return_code is not None and owner_browser.stderr is not None:
                owner_stderr = owner_browser.stderr.read()[-1000:]
            pytest.fail(
                "The production CDP driver could not attach to real Chromium "
                f"(owner_return_code={return_code}, stderr={owner_stderr!r})."
            )
        yield agent, owner_browser
    finally:
        agent.stop()
        if owner_browser.poll() is None:
            assert owner_browser.stdin is not None
            owner_browser.stdin.write("stop\n")
            owner_browser.stdin.flush()
            try:
                owner_browser.wait(timeout=5)
            except subprocess.TimeoutExpired:
                owner_browser.kill()
                owner_browser.wait(timeout=5)


def test_http_503_navigation_fails_closed(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        result = real_agent.navigate(f"{site.base_url}/status/503")

    assert result.success is False
    assert result.status is BrowserResultStatus.UNAVAILABLE
    assert result.error_code == "BROWSER_NAVIGATION_UNAVAILABLE"
    assert result.driver_type is BrowserDriverType.PLAYWRIGHT


def test_http_403_navigation_reports_blocked(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        result = real_agent.navigate(f"{site.base_url}/status/403")

    assert result.success is False
    assert result.status is BrowserResultStatus.BLOCKED
    assert result.error_code == "BROWSER_ACCESS_BLOCKED"


def test_http_200_error_title_cannot_report_success(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        result = real_agent.navigate(f"{site.base_url}/title-error")

    assert result.success is False
    assert result.status is BrowserResultStatus.ERROR
    assert result.error_code == "BROWSER_INVALID_PAGE"


def test_redirect_reports_final_real_url_and_dom(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        expected_url = f"{site.base_url}/redirected"
        result = real_agent.navigate(f"{site.base_url}/redirect")
        page = real_agent.actions.read_page()

    assert result.success is True
    assert result.url == expected_url
    assert result.title == "Redirect Complete"
    assert page.success is True
    assert "Redirected" in page.extracted_data["text"]


def test_playwright_extra_headers_do_not_cross_redirect_origin(
    real_agent: BrowserAgent,
) -> None:
    observed: dict[str, dict[str, str]] = {}
    probe_url = ""
    return_url = ""

    class FinalHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            observed["final"] = dict(self.headers.items())
            body = (
                "<!doctype html><title>Scoped Header Final</title><h1>Done</h1>"
                f'<img src="{probe_url}" alt="probe">'
                f'<a id="return-link" href="{return_url}">Return</a>'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    final_server = ThreadingHTTPServer(("127.0.0.1", 0), FinalHandler)
    final_thread = threading.Thread(target=final_server.serve_forever, daemon=True)
    final_thread.start()
    final_url = f"http://127.0.0.1:{final_server.server_port}/final"

    class RedirectHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path == "/probe":
                observed["probe"] = dict(self.headers.items())
                body = b"probe"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/private":
                observed["private"] = dict(self.headers.items())
                body = b"<!doctype html><title>Private Return</title>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            observed["initial"] = dict(self.headers.items())
            self.send_response(302)
            self.send_header("Location", final_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

    redirect_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = threading.Thread(
        target=redirect_server.serve_forever,
        daemon=True,
    )
    redirect_thread.start()
    start_url = f"http://127.0.0.1:{redirect_server.server_port}/start"
    probe_url = f"http://127.0.0.1:{redirect_server.server_port}/probe"
    return_url = f"http://127.0.0.1:{redirect_server.server_port}/private"
    real_agent.config.extra_headers = {
        "Authorization": "Bearer scoped-browser-secret",
        "X-API-Key": "scoped-api-secret",
    }

    try:
        result = real_agent.navigate(start_url)
        deadline = time.monotonic() + 2.0
        while "probe" not in observed and time.monotonic() < deadline:
            time.sleep(0.01)
        clicked = real_agent.actions.click_element("#return-link")
        deadline = time.monotonic() + 2.0
        while "private" not in observed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        redirect_server.shutdown()
        redirect_server.server_close()
        final_server.shutdown()
        final_server.server_close()
        redirect_thread.join(timeout=2.0)
        final_thread.join(timeout=2.0)

    assert result.success is True
    assert observed["initial"]["Authorization"] == "Bearer scoped-browser-secret"
    assert observed["initial"]["X-API-Key"] == "scoped-api-secret"
    assert "Authorization" not in observed["final"]
    assert "X-API-Key" not in observed["final"]
    assert "Authorization" not in observed["probe"]
    assert "X-API-Key" not in observed["probe"]
    assert clicked.success is True
    assert "Authorization" not in observed["private"]
    assert "X-API-Key" not in observed["private"]


def test_playwright_extra_headers_survive_same_origin_redirect(
    real_agent: BrowserAgent,
) -> None:
    observed: dict[str, dict[str, str]] = {}

    class RedirectHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path == "/start":
                observed["initial"] = dict(self.headers.items())
                self.send_response(302)
                self.send_header("Location", "/final")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if self.path == "/asset":
                observed["asset"] = dict(self.headers.items())
                body = b"asset"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            observed["final"] = dict(self.headers.items())
            body = (
                b"<!doctype html><title>Same Origin Final</title><h1>Done</h1>"
                b'<img src="/asset" alt="asset">'
            )
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    start_url = f"http://127.0.0.1:{server.server_port}/start"
    real_agent.config.extra_headers = {
        "Authorization": "Bearer scoped-browser-secret",
        "X-API-Key": "scoped-api-secret",
    }

    try:
        result = real_agent.navigate(start_url)
        deadline = time.monotonic() + 2.0
        while "asset" not in observed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2.0)

    assert result.success is True
    assert observed["initial"]["Authorization"] == "Bearer scoped-browser-secret"
    assert observed["initial"]["X-API-Key"] == "scoped-api-secret"
    assert observed["final"]["Authorization"] == "Bearer scoped-browser-secret"
    assert observed["final"]["X-API-Key"] == "scoped-api-secret"
    assert observed["asset"]["Authorization"] == "Bearer scoped-browser-secret"
    assert observed["asset"]["X-API-Key"] == "scoped-api-secret"


def test_playwright_redirect_never_readds_headers_after_cross_origin_bounce(
    real_agent: BrowserAgent,
) -> None:
    observed: dict[str, dict[str, str]] = {}
    bounce_url = ""

    class TrustedHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path == "/start":
                observed["initial"] = dict(self.headers.items())
                self.send_response(302)
                self.send_header("Location", bounce_url)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            observed["final"] = dict(self.headers.items())
            body = b"<!doctype html><title>Bounce Complete</title>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    trusted_server = ThreadingHTTPServer(("127.0.0.1", 0), TrustedHandler)
    trusted_thread = threading.Thread(target=trusted_server.serve_forever, daemon=True)
    trusted_thread.start()
    final_url = f"http://127.0.0.1:{trusted_server.server_port}/final"

    class BounceHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            observed["bounce"] = dict(self.headers.items())
            self.send_response(302)
            self.send_header("Location", final_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

    bounce_server = ThreadingHTTPServer(("127.0.0.1", 0), BounceHandler)
    bounce_thread = threading.Thread(target=bounce_server.serve_forever, daemon=True)
    bounce_thread.start()
    bounce_url = f"http://127.0.0.1:{bounce_server.server_port}/bounce"
    start_url = f"http://127.0.0.1:{trusted_server.server_port}/start"
    real_agent.config.extra_headers = {"X-Probe": "probe-secret"}

    try:
        result = real_agent.navigate(start_url)
    finally:
        trusted_server.shutdown()
        trusted_server.server_close()
        bounce_server.shutdown()
        bounce_server.server_close()
        trusted_thread.join(timeout=2.0)
        bounce_thread.join(timeout=2.0)

    assert result.success is True
    assert observed["initial"]["X-Probe"] == "probe-secret"
    assert "X-Probe" not in observed["bounce"]
    assert "X-Probe" not in observed["final"]


def test_playwright_subresource_bounce_never_readds_scoped_header(
    real_agent: BrowserAgent,
) -> None:
    observed: dict[str, dict[str, str]] = {}
    bounce_url = ""

    class TrustedHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path == "/page":
                observed["page"] = dict(self.headers.items())
                body = (
                    b"<!doctype html><title>Trusted Page</title>"
                    b'<img src="/asset-start" alt="redirecting asset">'
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/asset-start":
                observed["asset_initial"] = dict(self.headers.items())
                self.send_response(302)
                self.send_header("Location", bounce_url)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path == "/private":
                observed["private"] = dict(self.headers.items())
                body = b"not-a-real-private-image"
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    trusted_server = ThreadingHTTPServer(("127.0.0.1", 0), TrustedHandler)
    trusted_thread = threading.Thread(target=trusted_server.serve_forever, daemon=True)
    trusted_thread.start()
    private_url = f"http://127.0.0.1:{trusted_server.server_port}/private"

    class BounceHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            observed["bounce"] = dict(self.headers.items())
            self.send_response(302)
            self.send_header("Location", private_url)
            self.send_header("Content-Length", "0")
            self.end_headers()

    bounce_server = ThreadingHTTPServer(("127.0.0.1", 0), BounceHandler)
    bounce_thread = threading.Thread(target=bounce_server.serve_forever, daemon=True)
    bounce_thread.start()
    bounce_url = f"http://127.0.0.1:{bounce_server.server_port}/bounce"
    page_url = f"http://127.0.0.1:{trusted_server.server_port}/page"
    real_agent.config.extra_headers = {"X-Probe": "subresource-secret"}

    try:
        result = real_agent.navigate(page_url)
        deadline = time.monotonic() + 2.0
        while "private" not in observed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        trusted_server.shutdown()
        trusted_server.server_close()
        bounce_server.shutdown()
        bounce_server.server_close()
        trusted_thread.join(timeout=2.0)
        bounce_thread.join(timeout=2.0)

    assert result.success is True
    assert observed["page"]["X-Probe"] == "subresource-secret"
    assert observed["asset_initial"]["X-Probe"] == "subresource-secret"
    assert "X-Probe" not in observed["bounce"]
    assert "X-Probe" not in observed["private"]


def test_playwright_cross_origin_iframe_cannot_spend_scoped_header(
    real_agent: BrowserAgent,
) -> None:
    observed: dict[str, dict[str, str]] = {}
    iframe_url = ""
    private_url = ""

    class TrustedHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path == "/page":
                observed["page"] = dict(self.headers.items())
                body = (
                    "<!doctype html><title>Trusted Frame Host</title>"
                    '<img src="/asset" alt="trusted asset">'
                    f'<iframe src="{iframe_url}"></iframe>'
                ).encode()
            elif self.path == "/asset":
                observed["asset"] = dict(self.headers.items())
                body = b"trusted asset"
            elif self.path == "/private":
                observed["private"] = dict(self.headers.items())
                body = b"private response"
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    trusted_server = ThreadingHTTPServer(("127.0.0.1", 0), TrustedHandler)
    trusted_thread = threading.Thread(target=trusted_server.serve_forever, daemon=True)
    trusted_thread.start()
    private_url = f"http://127.0.0.1:{trusted_server.server_port}/private"

    class FrameHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            observed["frame"] = dict(self.headers.items())
            body = (
                "<!doctype html><title>Untrusted Frame</title>"
                f'<img src="{private_url}" alt="private probe">'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    frame_server = ThreadingHTTPServer(("127.0.0.1", 0), FrameHandler)
    frame_thread = threading.Thread(target=frame_server.serve_forever, daemon=True)
    frame_thread.start()
    iframe_url = f"http://127.0.0.1:{frame_server.server_port}/frame"
    page_url = f"http://127.0.0.1:{trusted_server.server_port}/page"
    real_agent.config.extra_headers = {"X-Probe": "frame-secret"}

    try:
        result = real_agent.navigate(page_url)
        deadline = time.monotonic() + 2.0
        while "private" not in observed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        trusted_server.shutdown()
        trusted_server.server_close()
        frame_server.shutdown()
        frame_server.server_close()
        trusted_thread.join(timeout=2.0)
        frame_thread.join(timeout=2.0)

    assert result.success is True
    assert observed["page"]["X-Probe"] == "frame-secret"
    assert observed["asset"]["X-Probe"] == "frame-secret"
    assert "X-Probe" not in observed["frame"]
    assert "X-Probe" not in observed["private"]


def test_playwright_cross_origin_iframe_top_navigation_is_not_trusted_click(
    real_agent: BrowserAgent,
) -> None:
    observed: dict[str, dict[str, str]] = {}
    iframe_url = ""
    private_url = ""

    class TrustedHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path == "/page":
                observed["page"] = dict(self.headers.items())
                body = (
                    "<!doctype html><title>Trusted Top Frame</title>"
                    f'<iframe sandbox="allow-scripts allow-top-navigation" src="{iframe_url}">'
                    "</iframe>"
                ).encode()
            elif self.path == "/private-top":
                observed["private_top"] = dict(self.headers.items())
                body = b"<!doctype html><title>Top Navigation Complete</title>"
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    trusted_server = ThreadingHTTPServer(("127.0.0.1", 0), TrustedHandler)
    trusted_thread = threading.Thread(target=trusted_server.serve_forever, daemon=True)
    trusted_thread.start()
    private_url = f"http://127.0.0.1:{trusted_server.server_port}/private-top"

    class FrameHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            observed["frame"] = dict(self.headers.items())
            body = (
                "<!doctype html><title>Untrusted Navigator</title>"
                f"<script>window.top.location.href = {json.dumps(private_url)};</script>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    frame_server = ThreadingHTTPServer(("127.0.0.1", 0), FrameHandler)
    frame_thread = threading.Thread(target=frame_server.serve_forever, daemon=True)
    frame_thread.start()
    iframe_url = f"http://127.0.0.1:{frame_server.server_port}/frame"
    page_url = f"http://127.0.0.1:{trusted_server.server_port}/page"
    real_agent.config.extra_headers = {"X-Probe": "top-frame-secret"}

    try:
        result = real_agent.navigate(page_url)
        deadline = time.monotonic() + 2.0
        while "private_top" not in observed and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        trusted_server.shutdown()
        trusted_server.server_close()
        frame_server.shutdown()
        frame_server.server_close()
        trusted_thread.join(timeout=2.0)
        frame_thread.join(timeout=2.0)

    assert result.success is True
    assert observed["page"]["X-Probe"] == "top-frame-secret"
    assert "X-Probe" not in observed["frame"]
    assert "X-Probe" not in observed["private_top"]


def test_playwright_cookie_delta_only_mutates_targeted_identity(
    real_agent: BrowserAgent,
) -> None:
    with LocalBrowserTestSite() as site:
        assert real_agent.navigate(site.base_url).success is True
        real_agent.driver.set_cookies(
            [
                {
                    "name": "sid",
                    "value": "remove-me",
                    "url": site.base_url,
                },
                {
                    "name": "live-tab",
                    "value": "must-survive",
                    "url": site.base_url,
                },
            ]
        )
        assert real_agent.driver.last_error_status is None

        real_agent.driver.apply_cookie_delta(
            [
                {
                    "name": "nonce",
                    "value": "response-cookie",
                    "domain": "127.0.0.1",
                    "path": "/",
                }
            ],
            [("sid", "127.0.0.1", "/", None)],
        )
        cookies = real_agent.driver.get_cookies()

    assert real_agent.driver.last_error_status is None
    assert {(cookie["name"], cookie["value"]) for cookie in cookies} == {
        ("live-tab", "must-survive"),
        ("nonce", "response-cookie"),
    }


def test_core_handler_can_use_browser_launched_on_another_thread(
    real_agent: BrowserAgent,
) -> None:
    app = JarvisApp.__new__(JarvisApp)
    app.browser_agent = real_agent
    with LocalBrowserTestSite() as site:
        expected_url = f"{site.base_url}/redirected"
        with ThreadPoolExecutor(max_workers=1) as executor:
            response = executor.submit(
                app._handle_browser_navigate,
                f"{site.base_url}/redirect",
            ).result(timeout=10)

    assert response["success"] is True
    assert response["result_status"] == "SUCCESS"
    assert response["driver_type"] == "playwright"
    assert response["url"] == expected_url


def test_local_product_page_yields_only_evidenced_offer(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        result = real_agent.scrape_url(f"{site.base_url}/products")
        offers = PriceComparisonAggregator.extract_store_products(
            "Local Test Store",
            real_agent.driver.get_html(),
            f"{site.base_url}/products",
        )

    assert result.success is True
    assert result.title == "Deterministic Product Catalog"
    assert len(offers) == 1
    assert offers[0].product_title == "JARVIS Test Widget"
    assert offers[0].price == 123.45
    assert offers[0].currency == "USD"
    assert offers[0].in_stock is True
    assert offers[0].source == "json_ld"


def test_real_browser_full_action_and_dom_flow(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        base_url = site.base_url
        navigation = real_agent.navigate(f"{base_url}/")
        typed = real_agent.actions.fill_text("#name-input", "Ada Lovelace", clear=True)
        clicked = real_agent.actions.click_element("#action-button")
        waited = real_agent.actions.wait_for_selector("#delayed-element", timeout_ms=1000)
        screenshot = real_agent.actions.take_screenshot(full_page=False)
        scrolled = real_agent.actions.scroll_page("bottom", 500)
        scroll_y = real_agent.driver.evaluate_script("window.scrollY")
        page = real_agent.actions.read_page()

    assert navigation.success is True
    assert navigation.url == f"{base_url}/"
    assert navigation.title == "JARVIS Browser E2E"
    assert typed.success is True
    assert clicked.success is True
    assert real_agent.driver.get_text("#result") == "Ada Lovelace"
    assert waited.success is True
    assert scrolled.success is True
    assert scroll_y > 0
    assert screenshot.success is True
    assert screenshot.screenshot_b64 is not None
    screenshot_bytes = b64decode(screenshot.screenshot_b64)
    image = Image.open(BytesIO(screenshot_bytes))
    assert image.width == 1280
    assert image.height == 800
    assert page.success is True
    assert page.extracted_data["url"] == f"{base_url}/"
    assert page.extracted_data["title"] == "JARVIS Browser E2E"
    assert "Deterministic Browser Page" in page.extracted_data["text"]
    assert 'id="name-input"' in page.extracted_data["html"]
    evidence_path = _evidence_path("playwright-action-flow.png")
    if evidence_path is not None:
        evidence_path.write_bytes(screenshot_bytes)


def test_wait_timeout_has_stable_timeout_result(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        assert real_agent.navigate(f"{site.base_url}/").success is True
        result = real_agent.actions.wait_for_selector("#never-appears", timeout_ms=50)

    assert result.success is False
    assert result.status is BrowserResultStatus.TIMEOUT
    assert result.error_code == "BROWSER_TIMEOUT"
    assert result.error_message == "Timed out waiting for the browser element."
    _write_result_evidence("wait-timeout.json", result)


def test_navigation_timeout_fails_closed(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        result = real_agent.navigate(f"{site.base_url}/timeout")

    assert result.success is False
    assert result.status is BrowserResultStatus.TIMEOUT
    assert result.error_code == "BROWSER_TIMEOUT"
    assert result.error_message == "Browser navigation timed out."
    _write_result_evidence("navigation-timeout.json", result)


def test_action_after_session_close_reports_disconnected(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        assert real_agent.navigate(f"{site.base_url}/").success is True
    real_agent.stop()

    result = real_agent.actions.click_element("#action-button")

    assert result.success is False
    assert result.status is BrowserResultStatus.DISCONNECTED
    assert result.error_code == "BROWSER_DISCONNECTED"
    assert result.error_message == "The browser session is disconnected."
    _write_result_evidence("session-close.json", result)


def test_invalid_selector_returns_stable_error(real_agent: BrowserAgent) -> None:
    with LocalBrowserTestSite() as site:
        assert real_agent.navigate(f"{site.base_url}/").success is True
        result = real_agent.actions.click_element("[")

    assert result.success is False
    assert result.status is BrowserResultStatus.ERROR
    assert result.error_code == "BROWSER_INVALID_SELECTOR"
    assert result.error_message == "The browser selector is invalid."


def test_real_cdp_attach_navigates_and_interacts(real_cdp_agent) -> None:
    agent, _owner_browser = real_cdp_agent
    with LocalBrowserTestSite() as site:
        navigation = agent.navigate(f"{site.base_url}/")
        typed = agent.actions.fill_text("#name-input", "CDP verified", clear=True)
        clicked = agent.actions.click_element("#action-button")
        screenshot = agent.actions.take_screenshot()

    assert navigation.success is True
    assert navigation.title == "JARVIS Browser E2E"
    assert navigation.driver_type is BrowserDriverType.CDP
    assert typed.success is True
    assert clicked.success is True
    assert agent.driver.get_text("#result") == "CDP verified"
    assert screenshot.success is True
    assert screenshot.screenshot_b64 is not None
    screenshot_bytes = b64decode(screenshot.screenshot_b64)
    image = Image.open(BytesIO(screenshot_bytes))
    assert image.width > 1 and image.height > 1
    evidence_path = _evidence_path("cdp-action-flow.png")
    if evidence_path is not None:
        evidence_path.write_bytes(screenshot_bytes)


def test_real_cdp_disconnect_fails_closed(real_cdp_agent) -> None:
    agent, owner_browser = real_cdp_agent
    with LocalBrowserTestSite() as site:
        assert agent.navigate(f"{site.base_url}/").success is True

        assert owner_browser.stdin is not None
        assert owner_browser.stdout is not None
        owner_browser.stdin.write("close\n")
        owner_browser.stdin.flush()
        while owner_browser.stdout.readline().strip() != "CLOSED":
            pass

        result = agent.actions.click_element("#action-button")

    assert result.success is False
    assert result.status is BrowserResultStatus.DISCONNECTED
    assert result.error_code == "BROWSER_DISCONNECTED"
    assert result.driver_type is BrowserDriverType.CDP
    _write_result_evidence("cdp-disconnect.json", result)


def test_legacy_controller_delegates_to_real_canonical_browser(tmp_path) -> None:
    _require_opt_in()
    controller = BrowserCDPController(
        config=LegacyBrowserConfig(
            headless=True,
            slow_mo_ms=0,
            timeout_ms=1_000,
            screenshot_dir=str(tmp_path),
        )
    )
    launched = controller.launch()
    try:
        assert launched is True
        with LocalBrowserTestSite() as site:
            page = controller.navigate(f"{site.base_url}/")
            typed = controller.type_text("#name-input", "Legacy verified")
            clicked = controller.click("#action-button")
            content = controller.extract_content_as_markdown()
            screenshot_path = controller.screenshot("legacy-action-flow.png")

        assert page.success is True
        assert page.driver_type is BrowserDriverType.PLAYWRIGHT
        assert typed is True
        assert clicked is True
        assert "Legacy verified" in content
        assert screenshot_path
        screenshot_bytes = Path(screenshot_path).read_bytes()
        image = Image.open(BytesIO(screenshot_bytes))
        assert image.width == 1280
        assert image.height == 800
        evidence_path = _evidence_path("legacy-action-flow.png")
        if evidence_path is not None:
            evidence_path.write_bytes(screenshot_bytes)
    finally:
        if launched:
            assert controller.close() is True
