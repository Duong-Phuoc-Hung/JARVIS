"""Canonical backend result and health contracts.

New integrations should return :class:`BackendResult`; existing handlers may
continue returning ``ActionResult`` or dictionaries while the dispatcher
normalizes them at the boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from jarvis.core.models import ActionResult, ActionStatus


class HealthStatus(str, Enum):
    READY = "READY"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class BackendResult:
    """Stable result shape for backend/connector boundaries."""

    success: bool
    status: ActionStatus
    code: str
    message: str = ""
    data: Any = None
    retryable: bool = False

    def __post_init__(self) -> None:
        status = self.status
        if isinstance(status, str):
            try:
                status = ActionStatus[status.upper().strip()]
            except KeyError:
                status = ActionStatus.ERROR
            object.__setattr__(self, "status", status)
        if self.status == ActionStatus.SUCCESS and not self.success:
            object.__setattr__(self, "status", ActionStatus.ERROR)
        if self.status != ActionStatus.SUCCESS and self.success:
            object.__setattr__(self, "success", False)

    @classmethod
    def ok(cls, data: Any = None, message: str = "", code: str = "OK") -> "BackendResult":
        return cls(True, ActionStatus.SUCCESS, code, message, data, False)

    @classmethod
    def failure(
        cls,
        status: ActionStatus | str,
        message: str,
        *,
        code: str | None = None,
        data: Any = None,
        retryable: bool = False,
    ) -> "BackendResult":
        normalized = status if isinstance(status, ActionStatus) else ActionStatus.__members__.get(status.upper(), ActionStatus.ERROR)
        return cls(False, normalized, code or normalized.value, message, data, retryable)

    @classmethod
    def from_action_result(cls, result: ActionResult) -> "BackendResult":
        status = result.status if isinstance(result.status, ActionStatus) else ActionStatus.ERROR
        return cls(result.success, status, result.code, result.message, result.data, result.retryable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value,
            "code": self.code,
            "message": self.message,
            "data": self.data,
            "retryable": self.retryable,
        }
