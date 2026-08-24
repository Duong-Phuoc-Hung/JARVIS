"""
Data models, enums, and telemetry dataclasses for the JARVIS Autonomous Background Workers subsystem.
Defines worker tasks, execution lifecycle statuses, and real-time telemetry packets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
import time
from typing import Any, Callable, Dict, List, Optional, Union


class WorkerStatus(str, Enum):
    """Lifecycle states of a background sub-agent worker."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerPriority(IntEnum):
    """Priority level for background worker scheduling."""
    LOW = -1
    NORMAL = 0
    HIGH = 1
    CRITICAL = 2


@dataclass
class WorkerTask:
    """Specification of a long-running background task delegated to a sub-agent."""
    task_id: str
    name: str
    task_type: str = "generic_task"
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: WorkerPriority = WorkerPriority.NORMAL
    timeout_seconds: float = 300.0
    target_callable: Optional[Callable[..., Any]] = None
    action_name: Optional[str] = None
    notify_tts: bool = True
    notify_overlay: bool = True
    notify_telegram: bool = False
    telegram_chat_id: Optional[int] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the WorkerTask specification to a dictionary."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "task_type": self.task_type,
            "payload": self.payload,
            "priority": int(self.priority),
            "timeout_seconds": self.timeout_seconds,
            "action_name": self.action_name,
            "notify_tts": self.notify_tts,
            "notify_overlay": self.notify_overlay,
            "notify_telegram": self.notify_telegram,
            "telegram_chat_id": self.telegram_chat_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkerTask:
        """Constructs a WorkerTask from a dictionary."""
        raw_pri = data.get("priority", 0)
        try:
            priority = WorkerPriority(int(raw_pri))
        except (ValueError, TypeError):
            priority = WorkerPriority.NORMAL

        return cls(
            task_id=data["task_id"],
            name=data.get("name", "Unnamed Task"),
            task_type=data.get("task_type", "generic_task"),
            payload=data.get("payload", {}),
            priority=priority,
            timeout_seconds=float(data.get("timeout_seconds", 300.0)),
            action_name=data.get("action_name"),
            notify_tts=bool(data.get("notify_tts", True)),
            notify_overlay=bool(data.get("notify_overlay", True)),
            notify_telegram=bool(data.get("notify_telegram", False)),
            telegram_chat_id=data.get("telegram_chat_id"),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class WorkerTelemetry:
    """Real-time telemetry and execution status of an active BackgroundWorker."""
    worker_id: str
    task_id: str
    task_name: str
    status: WorkerStatus = WorkerStatus.INITIALIZING
    progress_pct: float = 0.0          # Range 0.0 to 100.0
    current_step: str = ""
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None
    result_data: Any = None
    heartbeat_timestamp: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes telemetry status into JSON-compatible dictionary."""
        return {
            "worker_id": self.worker_id,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status.value if isinstance(self.status, WorkerStatus) else str(self.status),
            "progress_pct": round(float(self.progress_pct), 2),
            "current_step": self.current_step,
            "elapsed_seconds": round(float(self.elapsed_seconds), 2),
            "estimated_remaining_seconds": round(float(self.estimated_remaining_seconds), 2) if self.estimated_remaining_seconds is not None else None,
            "artifacts": list(self.artifacts),
            "error": self.error,
            "result_data": self.result_data,
            "heartbeat_timestamp": self.heartbeat_timestamp,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
