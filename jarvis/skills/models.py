"""
Data models and schemas for JARVIS Persistent Skill Library.
Provides structured representation for skill metadata, definitions,
and execution telemetry.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.skills.validation import (
    coerce_dict,
    coerce_float,
    coerce_int,
    coerce_optional_dict,
    coerce_str,
    coerce_str_list,
)


@dataclass
class SkillMetadata:
    """Persistent metadata describing an auto-synthesized or registered skill."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    category: str = "general"         # Skill category e.g. 'data_analysis', 'automation'
    author: str = "jarvis_agentic_synthesizer"  # Who created/synthesized this skill
    parameters_schema: dict[str, Any] = field(default_factory=dict)
    return_schema: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "author": self.author,
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

    def to_manifest_dict(self) -> dict[str, Any]:
        """
        Static manifest view: the skill's durable definition fields only --
        no runtime telemetry (invocation_count/success_count/failure_count/
        total_latency_ms/success_rate/avg_latency_ms). Used whenever a new
        packaged metadata.json is written (e.g. SkillRegistry.register_skill())
        so a freshly-created manifest never bakes in telemetry, which
        conceptually belongs only in the separate runtime store (see
        jarvis.skills.telemetry). to_dict() is unchanged and still includes
        telemetry, for backward-compatible API/introspection use (e.g.
        SkillDefinition.to_dict(), dashboard endpoints that want to display
        current stats).
        """
        manifest = self.to_dict()
        for key in (
            "invocation_count",
            "success_count",
            "failure_count",
            "total_latency_ms",
            "success_rate",
            "avg_latency_ms",
        ):
            manifest.pop(key, None)
        return manifest

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillMetadata:
        """
        Build a SkillMetadata from a parsed manifest dict.

        Backward compatible: any field missing from `data` (older manifests
        written before a field existed) falls back to the dataclass default.
        Deterministic and fails closed per-field, not per-manifest: any
        field present but of the wrong type is ignored in favor of its
        default rather than propagating a malformed value onto a typed
        attribute (see jarvis.skills.validation) -- a single bad field can
        never raise or crash discovery.
        """
        if not isinstance(data, dict):
            data = {}
        now = time.time()
        return cls(
            name=coerce_str(data.get("name"), "unnamed_skill"),
            version=coerce_str(data.get("version"), "1.0.0"),
            description=coerce_str(data.get("description"), ""),
            category=coerce_str(data.get("category"), "general"),
            author=coerce_str(data.get("author"), "jarvis_agentic_synthesizer"),
            parameters_schema=coerce_dict(data.get("parameters_schema")),
            return_schema=coerce_optional_dict(data.get("return_schema")),
            tags=coerce_str_list(data.get("tags")),
            synthesized_by=coerce_str(data.get("synthesized_by"), "jarvis_agentic_synthesizer"),
            created_at=coerce_float(data.get("created_at"), now),
            updated_at=coerce_float(data.get("updated_at"), now),
            invocation_count=coerce_int(data.get("invocation_count"), 0),
            success_count=coerce_int(data.get("success_count"), 0),
            failure_count=coerce_int(data.get("failure_count"), 0),
            total_latency_ms=coerce_float(data.get("total_latency_ms"), 0.0),
        )


@dataclass
class SkillDefinition:
    """Complete specification of a skill including metadata, source, and entrypoint."""
    metadata: SkillMetadata
    entrypoint_code: str = ""
    entrypoint_function: str = "execute"
    file_path: str | None = None
    is_loaded: bool = False
    handler: Callable[..., Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "entrypoint_code": self.entrypoint_code,
            "entrypoint_function": self.entrypoint_function,
            "file_path": self.file_path,
            "is_loaded": self.is_loaded,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillDefinition:
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
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "success": self.success,
            "data": self.data,
            "artifacts": self.artifacts,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
        }
