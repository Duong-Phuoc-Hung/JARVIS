from __future__ import annotations

from jarvis.core.dispatcher import _normalize_handler_outcome
from jarvis.core.models import ActionResult, ActionStatus
from jarvis.core.result_model import BackendResult, HealthStatus


def test_backend_result_serializes_canonical_success_contract() -> None:
    result = BackendResult.ok(data={"value": 1}, message="ok")

    assert result.success is True
    assert result.status == ActionStatus.SUCCESS
    assert result.code == "OK"
    assert result.retryable is False
    assert result.to_dict()["data"] == {"value": 1}


def test_backend_result_failure_never_reports_success() -> None:
    result = BackendResult.failure(ActionStatus.NOT_CONFIGURED, "missing", code="MISSING_KEY")

    assert result.success is False
    assert result.status == ActionStatus.NOT_CONFIGURED
    assert result.code == "MISSING_KEY"
    assert result.message == "missing"


def test_backend_result_from_action_result_preserves_legacy_fields() -> None:
    legacy = ActionResult(
        action_name="weather",
        success=False,
        status=ActionStatus.UNAVAILABLE,
        code="NO_NETWORK",
        message="offline",
        retryable=True,
    )

    converted = BackendResult.from_action_result(legacy)

    assert converted.success is False
    assert converted.status == ActionStatus.UNAVAILABLE
    assert converted.code == "NO_NETWORK"
    assert converted.retryable is True


def test_health_status_is_explicit_and_serializable() -> None:
    assert HealthStatus.READY.value == "READY"
    assert HealthStatus.LIMITED.value == "LIMITED"
    assert HealthStatus.UNAVAILABLE.value == "UNAVAILABLE"
    assert HealthStatus.ERROR.value == "ERROR"


def test_dispatcher_normalizes_backend_result_without_success_upgrade() -> None:
    result = BackendResult.failure(ActionStatus.TIMEOUT, "timed out", code="BACKEND_TIMEOUT")

    success, data, error, code = _normalize_handler_outcome(result)

    assert success is False
    assert data is result
    assert error == "timed out"
    assert code == "BACKEND_TIMEOUT"
