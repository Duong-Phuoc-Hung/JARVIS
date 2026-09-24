"""OA protocol tests; controlled HTTP responses are engineering evidence only."""

import hashlib
import json
import time
from types import SimpleNamespace

from jarvis.comms.zalo import ZaloBotController, ZaloConfig


def test_official_webhook_mac_is_verified_over_exact_raw_body():
    body = json.dumps(
        {
            "app_id": "app",
            "timestamp": str(int(time.time() * 1000)),
            "event_name": "user_send_text",
            "recipient": {"id": "oa"},
            "sender": {"id": "tester"},
            "message": {"msg_id": "m1", "text": "/help"},
        },
        ensure_ascii=False,
    ).encode()
    data = json.loads(body)
    signature = (
        "mac=" + hashlib.sha256(b"app" + body + data["timestamp"].encode() + b"secret").hexdigest()
    )
    config = ZaloConfig(webhook_secret="secret", oa_id="oa", whitelist_user_ids=["tester"])
    config.app_id = "app"
    bot = ZaloBotController(config)
    assert bot.verify_webhook_signature(body, signature)
    assert not bot.verify_webhook_signature(body + b" ", signature)


def test_outbound_needs_a_real_message_id(monkeypatch):
    import jarvis.comms.zalo as module

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"error":0,"data":{}}'

    monkeypatch.setattr(module, "urlopen", lambda *a, **kw: Response())
    bot = ZaloBotController(
        ZaloConfig(access_token="test-token", oa_id="oa", whitelist_user_ids=["tester"])
    )
    assert bot.send_message("tester", "test").success is False


def signed(payload, secret="secret"):
    body = json.dumps(payload, ensure_ascii=False).encode()
    return body, "mac=" + hashlib.sha256(
        payload["app_id"].encode() + body + payload["timestamp"].encode() + secret.encode()
    ).hexdigest()


def event(**changes):
    data = {
        "app_id": "app",
        "timestamp": str(int(time.time() * 1000)),
        "event_name": "user_send_text",
        "recipient": {"id": "oa"},
        "sender": {"id": "tester"},
        "message": {"msg_id": "m1", "text": "/help"},
    }
    data.update(changes)
    return data


def bot():
    return ZaloBotController(
        ZaloConfig(app_id="app", oa_id="oa", webhook_secret="secret", whitelist_user_ids=["tester"])
    )


def test_webhook_rejects_forgery_before_dispatch():
    controller = bot()
    body, sig = signed(event())
    assert controller.handle_webhook(body, "mac=" + "0" * 64)["status"] == 403
    assert controller.received_messages == []


def test_webhook_is_bound_to_oa_and_deduplicates():
    controller = bot()
    body, sig = signed(event(recipient={"id": "other-oa"}))
    assert controller.handle_webhook(body, sig)["status"] == 403
    body, sig = signed(event())
    assert controller.handle_webhook(body, sig)["status"] == 200
    assert controller.handle_webhook(body, sig)["duplicate"] is True
    assert len(controller.received_messages) == 1


def test_outbound_network_error_never_echoes_payload(monkeypatch):
    from urllib.error import URLError

    import jarvis.comms.zalo as module

    def offline(*a, **kw):
        raise URLError("test-token private-content")

    monkeypatch.setattr(module, "urlopen", offline)
    controller = bot()
    controller.config.access_token = "test-token"
    result = controller.send_message("tester", "private-content")
    assert not result.success and result.error == "OFFLINE"
    assert "test-token" not in str(result) + str(controller.sent_messages)
    assert "private-content" not in str(controller.sent_messages)


import pytest


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("timeout", "TIMEOUT"),
        ("auth", "AUTH_FAILED"),
        ("limit", "RATE_LIMITED"),
        ("api", "API_ERROR"),
    ],
)
def test_outbound_error_status_and_redaction(monkeypatch, kind, expected):
    from urllib.error import HTTPError

    import jarvis.comms.zalo as module

    def transport(*a, **kw):
        if kind == "timeout":
            raise TimeoutError("private-token")
        if kind == "api":

            class R:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

                def read(self):
                    return b'{"error":-999,"message":"private-token"}'

            return R()
        raise HTTPError(
            "sensitive", 401 if kind == "auth" else 429, "sensitive", {"Retry-After": "2"}, None
        )

    monkeypatch.setattr(module, "urlopen", transport)
    controller = bot()
    controller.config.access_token = "private-token"
    result = controller.send_message("tester", "private-message")
    assert not result.success and result.error == expected
    assert "private-token" not in str(result) + str(controller.evidence)
    assert "private-message" not in str(controller.evidence)


def test_status_without_metrics_does_not_claim_active(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "psutil", None)
    controller = bot()
    outcome = controller.handle_message("tester", "", "/status")
    assert outcome["status"] == 503
    assert outcome["error_code"] == "STATUS_UNAVAILABLE"
    assert "Active" not in outcome["text"] and "Online" not in outcome["text"]
