"""
Data models and schemas for JARVIS Persistent Skill Library.
Provides structured representation for skill metadata, definitions,
and execution telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Dict, List, Optional


@dataclass
class SkillMetadata:
    """Persistent metadata describing an auto-synthesized or registered skill."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    return_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)
    synthesized_by: str = "jarvis_agentic_synthesizer"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    invocation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate skill invocation success rate between 0.0 and 1.0."""
        if self.invocation_count <= 0:
            return 0.0
        return round(self.success_count / self.invocation_count, 4)

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average execution latency in milliseconds."""
        if self.invocation_count <= 0:
            return 0.0
        return round(self.total_latency_ms / self.invocation_count, 2)

    def record_invocation(self, success: bool, latency_ms: float) -> None:
        """Update metrics following an execution."""
        self.invocation_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.total_latency_ms += latency_ms
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "parameters_schema": self.parameters_schema,
            "return_schema": self.return_schema,
            "tags": self.tags,
            "synthesized_by": self.synthesized_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "invocation_count": self.invocation_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_latency_ms": self.total_latency_ms,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillMetadata:
        return cls(
            name=data.get("name", "unnamed_skill"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            parameters_schema=data.get("parameters_schema", {}),
            return_schema=data.get("return_schema"),
            tags=data.get("tags", []),
            synthesized_by=data.get("synthesized_by", "jarvis_agentic_synthesizer"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            invocation_count=data.get("invocation_count", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            total_latency_ms=data.get("total_latency_ms", 0.0),
        )


@dataclass
class SkillDefinition:
    """Complete specification of a skill including metadata, source, and entrypoint."""
    metadata: SkillMetadata
    entrypoint_code: str = ""
    entrypoint_function: str = "execute"
    file_path: Optional[str] = None
    is_loaded: bool = False
    handler: Optional[Callable[..., Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "entrypoint_code": self.entrypoint_code,
            "entrypoint_function": self.entrypoint_function,
            "file_path": self.file_path,
            "is_loaded": self.is_loaded,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SkillDefinition:
        metadata_dict = data.get("metadata", {})
        metadata = SkillMetadata.from_dict(metadata_dict) if metadata_dict else SkillMetadata(name="unnamed")
        return cls(
            metadata=metadata,
            entrypoint_code=data.get("entrypoint_code", ""),
            entrypoint_function=data.get("entrypoint_function", "execute"),
            file_path=data.get("file_path"),
            is_loaded=data.get("is_loaded", False),
        )


@dataclass
class SkillExecutionResult:
    """Structured execution outcome of invoking a persistent skill."""
    skill_name: str
    success: bool
    data: Any = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "success": self.success,
            "data": self.data,
            "artifacts": self.artifacts,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
        }
