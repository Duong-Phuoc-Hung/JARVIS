"""Deterministic loopback-only website used by T-01 browser tests."""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

_INDEX_HTML = b"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>JARVIS Browser E2E</title>
  <style>body { min-height: 2600px; } #scroll-target { margin-top: 1800px; }</style>
</head>
<body>
  <h1 id="heading">Deterministic Browser Page</h1>
  <label for="name-input">Name</label>
  <input id="name-input" value="stale value">
  <button id="action-button" type="button"
    onclick="document.querySelector('#result').textContent = document.querySelector('#name-input').value; document.querySelector('#result').dataset.clicked = 'true';">
    Apply
  </button>
  <div id="result">not clicked</div>
  <div id="delayed-host"></div>
  <a id="redirect-link" href="/redirect">Redirect</a>
  <div id="scroll-target">Scroll destination</div>
  <script>
    setTimeout(() => {
      const delayed = document.createElement('div');
      delayed.id = 'delayed-element';
      delayed.textContent = 'Loaded after delay';
      document.querySelector('#delayed-host').appendChild(delayed);
    }, 150);
  </script>
</body>
</html>"""

_PRODUCT_HTML = b"""<!doctype html>
<html>
<head>
  <title>Deterministic Product Catalog</title>
  <script type="application/ld+json">
  {"@context":"https://schema.org","@type":"Product","name":"JARVIS Test Widget","offers":{"@type":"Offer","price":"123.45","priceCurrency":"USD","availability":"https://schema.org/InStock","url":"/products/widget"}}
  </script>
</head>
<body><h1>JARVIS Test Widget</h1><p id="price">$123.45</p></body>
</html>"""


class _ThreadedServer(ThreadingHTTPServer):
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, body: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        path = urlsplit(self.path).path
        if path in ("/", "/index"):
            self._send(_INDEX_HTML)
        elif path == "/products":
            self._send(_PRODUCT_HTML)
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/redirected")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/redirected":
            self._send(b"<!doctype html><title>Redirect Complete</title><h1 id='redirected'>Redirected</h1>")
        elif path == "/timeout":
            time.sleep(1.0)
            self._send(b"<!doctype html><title>Too Late</title><h1>Delayed response</h1>")
        elif path == "/status/503":
            self._send(b"<!doctype html><title>Unavailable</title><h1>Unavailable</h1>", status=503)
        elif path == "/status/403":
            self._send(b"<!doctype html><title>Blocked</title><h1>Blocked</h1>", status=403)
        elif path == "/title-error":
            self._send(b"<!doctype html><title>Error</title><h1>Misleading success page</h1>")
        elif path == "/disconnect":
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
        else:
            self._send(b"<!doctype html><title>Not Found</title><h1>Not Found</h1>", status=404)


class LocalBrowserTestSite:
    """Context manager serving deterministic T-01 routes on an ephemeral port."""

    def __init__(self) -> None:
        self._server: _ThreadedServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("Local browser test site is not running.")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "LocalBrowserTestSite":
        self._server = _ThreadedServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="T01LocalBrowserSite",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None
