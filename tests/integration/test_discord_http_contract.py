"""Discord REST loopback contract, NOT Discord-server round-trip evidence."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import requests

from jarvis.comms.discord import DiscordBotController
from jarvis.core.dispatcher import ActionDispatcher


def test_real_http_inbound_outbound_and_safety_no_side_effect(tmp_path):
    messages = []
    posts = []
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, data):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def do_GET(self):
            calls.append(("GET", self.path))
            if self.path == "/api/v10/channels/30":
                self.reply({"id": "30", "guild_id": "20"})
            else:
                self.reply(messages)

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            posts.append(data)
            self.reply({"id": str(100 + len(posts)), "channel_id": "30"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class LoopbackTransport:
        def request(self, method, url, **kwargs):
            path = urlsplit(url)
            return requests.request(
                method,
                f"http://127.0.0.1:{server.server_port}{path.path}?{path.query}"
                if path.query
                else f"http://127.0.0.1:{server.server_port}{path.path}",
                **kwargs,
            )

    canary = tmp_path / "side-effect"
    dispatcher = ActionDispatcher()
    dispatcher.register_action("shell_exec", lambda **kw: canary.write_text("bad"))
    controller = DiscordBotController(
        "dummy", [1], 20, 30, dispatcher, LoopbackTransport(), admin_user_ids=[1]
    )
    try:
        assert controller.poll_once()
        messages.append({"id": "1", "channel_id": "30", "author": {"id": "1"}, "content": "!help"})
        assert controller.poll_once()
        assert posts[-1]["embeds"][0]["fields"]
        assert controller.last_poll_status["reply_message_id"] == "101"
        messages.append(
            {
                "id": "2",
                "channel_id": "30",
                "author": {"id": "1"},
                "content": '!exec shell_exec {"command":"echo private-canary"}',
            }
        )
        assert controller.poll_once()
        assert controller.last_poll_status["command_status"] == 409
        assert posts[-1]["content"] == "CONFIRMATION_REQUIRED"
        assert not canary.exists()
        assert len(dispatcher.safety_interceptor.safety_gate.list_pending()) == 1
        assert controller.poll_once() and len(posts) == 2
        assert "private-canary" not in str(controller.sent_messages)
        assert posts[-1]["allowed_mentions"] == {"parse": []}
    finally:
        controller.stop_polling()
        server.shutdown()
        server.server_close()
        thread.join(2)
