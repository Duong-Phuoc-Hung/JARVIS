"""
jarvis/plugins/webhook.py
=========================
HTTP Webhook JSON dispatching plugin for JARVIS.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import PluginMetadata
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

    def initialize(self, config: Dict[str, Any], dispatcher: ActionDispatcher) -> None:
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
        payload: Dict[str, Any],
        mock_http: Optional[Any] = None,
        timeout: float = 5.0,
        **kwargs,
    ) -> Dict[str, Any]:
        """Sends HTTP POST request with JSON payload."""
        if mock_http is not None:
            mock_http.last_webhook_payload = payload
            return {"status": 200, "delivered": True, "payload": payload}

        try:
            import requests
            resp = requests.post(url, json=payload, timeout=timeout)
            return {"status": resp.status_code, "delivered": resp.ok, "response": resp.text}
        except Exception as e:
            log.warning("Webhook dispatch to %s failed: %s", url, e)
            return {"status": 500, "delivered": False, "error": str(e)}
