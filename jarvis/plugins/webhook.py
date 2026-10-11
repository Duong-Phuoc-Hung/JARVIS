"""
jarvis/plugins/webhook.py
=========================
HTTP Webhook JSON dispatching plugin for JARVIS.
"""
from __future__ import annotations

import logging
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionStatus, PluginMetadata
from jarvis.core.plugin import BasePlugin

log = logging.getLogger("jarvis.plugins.webhook")


class WebhookPlugin(BasePlugin):
    """Sends JSON payloads to HTTP webhook endpoints."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="webhook",
            version="1.0.0",
            description="HTTP Webhook dispatcher",
        )

    def initialize(self, config: dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.config = config or {}
        self.dispatcher = dispatcher
        self.register_action(
            name="webhook_send",
            handler=self.send_payload,
            description="Send webhook payload",
        )

    def send_payload(
        self,
        url: str,
        payload: dict[str, Any],
        mock_http: Any | None = None,
        timeout: float = 5.0,
        **kwargs,
    ) -> Any:
        """Sends HTTP POST request with JSON payload returning canonical BackendResult."""
        from jarvis.core.result_model import BackendResult

        if not url or not isinstance(url, str) or not url.strip():
            return BackendResult.failure(
                ActionStatus.ERROR,
                "Webhook URL is missing or empty.",
                code="WEBHOOK_INVALID_URL",
                data={"status": 400, "delivered": False, "error": "Missing URL"},
                retryable=False,
            )

        if mock_http is not None:
            mock_http.last_webhook_payload = payload
            if getattr(mock_http, "should_fail", False) is True:
                return BackendResult.failure(
                    ActionStatus.ERROR,
                    "Webhook mock delivery failure",
                    code="WEBHOOK_DELIVERY_FAILED",
                    data={"status": 500, "delivered": False, "error": "Mock failure"},
                )
            if hasattr(mock_http, "__dict__") and "handle_webhook_send" in mock_http.__dict__:
                handler = mock_http.__dict__["handle_webhook_send"]
                if callable(handler):
                    res = handler(url, payload)
                    if isinstance(res, BackendResult):
                        return res
            elif not type(mock_http).__name__.startswith("MagicMock") and hasattr(mock_http, "handle_webhook_send"):
                handler = mock_http.handle_webhook_send
                if callable(handler):
                    res = handler(url, payload)
                    if isinstance(res, BackendResult):
                        return res
            return BackendResult.ok(
                data={"status": 200, "delivered": True, "payload": payload},
                message="Webhook payload delivered successfully (mock)",
            )

        try:
            import requests
            resp = requests.post(url, json=payload, timeout=timeout)
            data = {"status": resp.status_code, "delivered": resp.ok, "response": resp.text}
            if resp.ok:
                return BackendResult.ok(
                    data=data,
                    message=f"Webhook response: HTTP {resp.status_code}",
                )
            return BackendResult.failure(
                ActionStatus.ERROR,
                f"Webhook delivery failed: HTTP {resp.status_code}",
                code="WEBHOOK_DELIVERY_FAILED",
                data=data,
                retryable=(resp.status_code >= 500 or resp.status_code == 429),
            )
        except Exception as e:
            log.warning("Webhook dispatch to %s failed: %s", url, e)
            return BackendResult.failure(
                ActionStatus.ERROR,
                f"Webhook dispatch failed: {e}",
                code="WEBHOOK_DELIVERY_FAILED",
                data={"status": 500, "delivered": False, "error": str(e)},
                retryable=True,
            )

