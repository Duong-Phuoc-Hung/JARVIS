"""Scripted Discord HTTP boundary; never a provider runtime credential/evidence."""

from collections import deque
from threading import Lock
from types import SimpleNamespace

from jarvis.comms.discord import DiscordBotController


class DiscordHTTP:
    def __init__(self, batches=()):
        self.batches = deque(batches)
        self.posts = []
        self.calls = []
        self.lock = Lock()

    def request(self, method, url, **kwargs):
        with self.lock:
            self.calls.append((method, url))
            assert kwargs["timeout"] == 10 and kwargs["allow_redirects"] is False
            if url.endswith("/channels/30"):
                data = {"id": "30", "guild_id": "20"}
                status = 200
            elif method == "POST":
                self.posts.append(kwargs["json"])
                data = {"id": str(10000 + len(self.posts)), "channel_id": "30"}
                status = 200
            else:
                item = self.batches.popleft() if self.batches else []
                if isinstance(item, Exception):
                    raise item
                status, data = item if isinstance(item, tuple) else (200, item)
            return SimpleNamespace(status_code=status, json=lambda: data)


def message(mid, uid=1, content="!help", **kwargs):
    return {
        "id": str(mid),
        "channel_id": "30",
        "author": {"id": str(uid)},
        "content": content,
        **kwargs,
    }


def bot(client, **kwargs):
    return DiscordBotController(
        bot_token="dummy",
        guild_id=20,
        channel_id=30,
        whitelist_user_ids=[1],
        http_client=client,
        poll_interval_s=0.01,
        **kwargs,
    )
