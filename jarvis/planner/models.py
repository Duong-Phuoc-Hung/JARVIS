"""
Data models, enums, and structured payloads for the JARVIS ReAct Planner subsystem.
Defines task graph nodes, lifecycle states, reflection results, and plan outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, Dict, List, Optional, Set, Union


class StepStatus(str, Enum):
    """Execution lifecycle status of an individual TaskNode."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    WAITING_CONFIRMATION = "waiting_confirmation"
    RETRYING = "retrying"


class PlanMode(str, Enum):
    """Execution mode of the ReAct Task Engine."""
    FULLY_AUTONOMOUS = "fully_autonomous"
    SAFETY_GATE = "safety_gate"


class RecoveryStrategy(str, Enum):
    """Recovery strategy recommended by the SelfReflectionEngine."""
    RETRY = "retry"                          # Retry same step with backoff / modified params
    ALTERNATIVE_TOOL = "alternative_tool"    # Switch tool to an alternative handler
    REPLAN = "replan"                        # Dynamically inject or alter downstream DAG nodes
    ABORT = "abort"                          # Terminate execution branch with error explanation


@dataclass
class TaskNode:
    """Represents a discrete step in the task execution graph."""
    step_id: str
    action_name: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    is_high_risk: bool = False
    max_retries: int = 3
    retry_count: int = 0
    result_data: Any = None
    error_message: Optional[str] = None
    confirmation_token: Optional[str] = None
    execution_time_ms: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the TaskNode into a JSON-serializable dictionary."""
        return {
            "step_id": self.step_id,
            "action_name": self.action_name,
            "description": self.description,
            "parameters": self.parameters,
            "depends_on": list(self.depends_on),
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "is_high_risk": self.is_high_risk,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "result_data": self.result_data,
            "error_message": self.error_message,
            "confirmation_token": self.confirmation_token,
            "execution_time_ms": self.execution_time_ms,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskNode:
        """Constructs a TaskNode from a dictionary."""
        raw_status = data.get("status", StepStatus.PENDING)
        if isinstance(raw_status, str):
            try:
                status_enum = StepStatus(raw_status)
            except ValueError:
                status_enum = StepStatus.PENDING
        else:
            status_enum = raw_status

        return cls(
            step_id=data["step_id"],
            action_name=data["action_name"],
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
            depends_on=data.get("depends_on", []),
            status=status_enum,
            is_high_risk=bool(data.get("is_high_risk", False)),
            max_retries=int(data.get("max_retries", 3)),
            retry_count=int(data.get("retry_count", 0)),
            result_data=data.get("result_data"),
            error_message=data.get("error_message"),
            confirmation_token=data.get("confirmation_token"),
            execution_time_ms=float(data.get("execution_time_ms", 0.0)),
            created_at=float(data.get("created_at", time.time())),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )

    def reset_for_retry(self) -> None:
        """Prepares the node for another execution attempt."""
        self.status = StepStatus.RETRYING
        self.error_message = None
        self.started_at = None
        self.finished_at = None


@dataclass
class ReflectionResult:
    """Outcome of self-reflection evaluation after a step failure."""
    step_id: str
    strategy: RecoveryStrategy
    diagnosis: str
    suggested_action: Optional[str] = None
    suggested_parameters: Optional[Dict[str, Any]] = None
    new_subgraph_nodes: Optional[List[TaskNode]] = None
    reasoning: str = ""
    backoff_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes reflection evaluation result."""
        return {
            "step_id": self.step_id,
            "strategy": self.strategy.value if isinstance(self.strategy, RecoveryStrategy) else str(self.strategy),
            "diagnosis": self.diagnosis,
            "suggested_action": self.suggested_action,
            "suggested_parameters": self.suggested_parameters,
            "new_subgraph_nodes": [n.to_dict() for n in self.new_subgraph_nodes] if self.new_subgraph_nodes else None,
            "reasoning": self.reasoning,
            "backoff_seconds": self.backoff_seconds,
        }


@dataclass
class PlanResult:
    """Overall outcome of task plan execution."""
    plan_id: str
    goal: str
    success: bool
    mode: PlanMode
    nodes: Dict[str, TaskNode] = field(default_factory=dict)
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    total_duration_ms: float = 0.0
    final_output: Any = None
    error: Optional[str] = None
    summary_message: str = ""

    @property
    def step_results(self) -> List[TaskNode]:
        """Returns list of TaskNode results for compatibility."""
        return list(self.nodes.values())

    @property
    def steps(self) -> List[TaskNode]:
        """Returns list of TaskNode steps for compatibility."""
        return list(self.nodes.values())

    def to_dict(self) -> Dict[str, Any]:
        """Serializes plan outcome and step states."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "success": self.success,
            "mode": self.mode.value if isinstance(self.mode, PlanMode) else str(self.mode),
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "total_duration_ms": self.total_duration_ms,
            "final_output": self.final_output,
            "error": self.error,
            "summary_message": self.summary_message,
        }
