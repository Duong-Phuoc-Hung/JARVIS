"""
tests/unit/test_result_health_migration.py
==========================================
TDD Unit test suite for Task 12: RESULT-HEALTH-MIGRATION.
Tests canonical boundary migrations to BackendResult and HealthStatus:
1. ActionDispatcher preserves all structured fields when handlers return BackendResult
   (status, code, message, inner data, retryable).
2. ActionDispatcher.dispatch_backend() provides a direct canonical BackendResult contract.
3. PluginHealth maps to canonical HealthStatus (READY, LIMITED, UNAVAILABLE, ERROR).
4. WebhookPlugin and HomeAssistantClient boundaries integrate with BackendResult.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import (
    ActionResult,
    ActionStatus,
    PluginHealth,
    PluginMetadata,
    PluginStatus,
    PrivilegeLevel,
    RequesterContext,
)
from jarvis.core.result_model import BackendResult, HealthStatus
from jarvis.plugins.webhook import WebhookPlugin
from jarvis.smart_home.home_assistant import HomeAssistantClient


class TestResultHealthMigration:
    """Verifies seamless migration to BackendResult and HealthStatus contracts."""

    @pytest.fixture
    def dispatcher(self) -> ActionDispatcher:
        return ActionDispatcher(bypass_security=True)

    def test_dispatcher_dispatch_preserves_backend_result_attributes(
        self, dispatcher: ActionDispatcher
    ) -> None:
        """
        When a registered handler returns a BackendResult, dispatcher.dispatch() must
        faithfully preserve status (e.g. NOT_CONFIGURED), code, message, retryable,
        and unpack the inner data payload rather than wrapping the BackendResult object.
        """
        def handler(**kwargs: Any) -> BackendResult:
            return BackendResult.failure(
                status=ActionStatus.NOT_CONFIGURED,
                message="Home Assistant integration token is not configured",
                code="NOT_CONFIGURED",
                data={"entity_id": "light.living_room"},
                retryable=False,
            )

        dispatcher.register_action(
            name="test_backend_action",
            handler=handler,
            required_privilege=PrivilegeLevel.NORMAL,
        )

        res = dispatcher.dispatch("test_backend_action", {})

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.status == ActionStatus.NOT_CONFIGURED
        assert res.code == "NOT_CONFIGURED"
        assert res.error_code == "NOT_CONFIGURED"
        assert res.message == "Home Assistant integration token is not configured"
        assert res.error == "Home Assistant integration token is not configured"
        assert res.retryable is False
        assert res.data == {"entity_id": "light.living_room"}

    def test_dispatcher_dispatch_backend_returns_canonical_backend_result(
        self, dispatcher: ActionDispatcher
    ) -> None:
        """
        ActionDispatcher.dispatch_backend() returns a canonical BackendResult directly.
        """
        def handler(**kwargs: Any) -> dict[str, Any]:
            return {"success": True, "count": 42, "message": "done"}

        dispatcher.register_action(
            name="test_dict_action",
            handler=handler,
            required_privilege=PrivilegeLevel.NORMAL,
        )

        backend_res = dispatcher.dispatch_backend("test_dict_action", {})

        assert isinstance(backend_res, BackendResult)
        assert backend_res.success is True
        assert backend_res.status == ActionStatus.SUCCESS
        assert backend_res.code == "OK"
        assert backend_res.data == {"success": True, "count": 42, "message": "done"}

    def test_plugin_health_maps_to_canonical_health_status(self) -> None:
        """
        PluginHealth must provide a health_status property mapping cleanly to HealthStatus enum.
        """
        h_ready = PluginHealth("test_p1", PluginStatus.RUNNING, True)
        assert h_ready.health_status == HealthStatus.READY

        h_limited = PluginHealth("test_p2", PluginStatus.INITIALIZED, True)
        assert h_limited.health_status == HealthStatus.LIMITED

        h_error = PluginHealth("test_p3", PluginStatus.ERROR, False)
        assert h_error.health_status == HealthStatus.ERROR

        h_unavail = PluginHealth("test_p4", PluginStatus.STOPPED, False)
        assert h_unavail.health_status == HealthStatus.UNAVAILABLE

    def test_webhook_plugin_returns_backend_result(self, dispatcher: ActionDispatcher) -> None:
        """
        WebhookPlugin.send_payload() should return BackendResult with structured delivery status.
        """
        plugin = WebhookPlugin()
        plugin.initialize({}, dispatcher)

        mock_http = MagicMock()
        res = plugin.send_payload(
            url="https://example.com/webhook",
            payload={"event": "ping"},
            mock_http=mock_http,
        )

        assert isinstance(res, BackendResult)
        assert res.success is True
        assert res.status == ActionStatus.SUCCESS
        assert res.data["delivered"] is True

    def test_home_assistant_call_service_backend(self) -> None:
        """
        HomeAssistantClient.call_service_backend() returns BackendResult with NOT_CONFIGURED
        when token is missing.
        """
        client = HomeAssistantClient(base_url="http://localhost:8123")
        client.token = ""

        res = client.call_service_backend(
            domain="light",
            service="turn_on",
            entity_id="light.kitchen",
        )

        assert isinstance(res, BackendResult)
        assert res.success is False
        assert res.status == ActionStatus.NOT_CONFIGURED
        assert res.code == "NOT_CONFIGURED"

    def test_webhook_plugin_invalid_url_and_mock_failure(self, dispatcher: ActionDispatcher) -> None:
        """WebhookPlugin must fail-closed on empty URL or mock failure."""
        plugin = WebhookPlugin()
        plugin.initialize({}, dispatcher)

        # Empty URL failure
        res_empty = plugin.send_payload(url="", payload={"event": "ping"})
        assert isinstance(res_empty, BackendResult)
        assert res_empty.success is False
        assert res_empty.code == "WEBHOOK_INVALID_URL"

        # Mock failure
        mock_http = MagicMock()
        mock_http.should_fail = True
        res_mock_fail = plugin.send_payload(
            url="https://example.com/webhook",
            payload={"event": "ping"},
            mock_http=mock_http,
        )
        assert isinstance(res_mock_fail, BackendResult)
        assert res_mock_fail.success is False
        assert res_mock_fail.code == "WEBHOOK_DELIVERY_FAILED"
