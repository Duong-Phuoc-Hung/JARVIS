"""
jarvis/agent/tool_runtime.py
=============================
Small, structured tool-execution boundary for ReActAgent.

Every built-in/registered agent tool call is normalized into a
ToolExecutionResult (success/output/error/metadata) and every observation
that goes back into agent history/context is deterministically bounded in
size before it is ever injected into an LLM prompt. This module has no
LLM/network/hardware dependency and is pure/deterministic, so it is fully
unit-testable in isolation.

Also provides sandbox_result_to_tool_result(), the single place that
converts a jarvis.sandbox.interpreter.SandboxResult (the existing,
unmodified sandbox's own structured outcome) into this agent-facing
contract — this is the only sandbox integration point ReActAgent uses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.sandbox.interpreter import SandboxResult

# Deliberately much smaller than the sandbox's own internal 1MB stdout cap
# (jarvis/sandbox/interpreter.py::_MAX_STDOUT_CAPTURE_BYTES) -- that cap
# protects the sandbox subprocess pipe itself, not LLM context budgets.
DEFAULT_MAX_OBSERVATION_CHARS = 4000

# Upper bound on how long a single run_python call may execute for, applied
# regardless of what an LLM/heuristic asks for, so a single tool call can
# never stall the agent loop indefinitely.
MAX_PYTHON_EXEC_TIMEOUT_SECONDS = 30.0

# Pre-existing, non-security cosmetic defect in
# jarvis.sandbox.security.strip_sandbox_ready_sentinel(): it only strips an
# LF-terminated sentinel line, so a CRLF-terminated child stdout (observed
# on Windows) leaks the raw \x02..\x03 marker bytes through unstripped.
# jarvis/sandbox/** is intentionally left unmodified (no proven security
# defect, and it is a NO-TOUCH-adjacent module) -- this regex is a
# defensive, consumer-side cleanup applied only to the copy of stdout this
# module turns into an agent observation.
_RESIDUAL_SANDBOX_SENTINEL_RE = re.compile(r"\x02JARVIS_SANDBOX_READY_v1\x03\r?\n?")

_SECRET_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"), "[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED]"),
    (re.compile(r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}\b"), "[REDACTED]"),
]


def sanitize_secrets(text: str) -> str:
    """Mask known sensitive token and API key patterns from output or observation text."""
    if not text:
        return text
    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


@dataclass(frozen=True)
class ToolExecutionResult:
    """Structured, uniform outcome for any agent tool call."""
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


def truncate_text(text: str, max_chars: int = DEFAULT_MAX_OBSERVATION_CHARS) -> str:
    """Deterministically bound text length with a clear, visible truncation marker."""
    if text is None:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n[TRUNCATED: output exceeded {max_chars} chars]"


def _clean_sandbox_text(text: str) -> str:
    """Defensively strip a leaked sandbox readiness sentinel (see module docstring)."""
    if not text:
        return text
    return _RESIDUAL_SANDBOX_SENTINEL_RE.sub("", text, count=1)


def _inspect_dict_failure(d: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Inspect a dictionary for explicit failure indicators, including nested data objects.
    Returns (has_failed, error_message).
    """
    if not isinstance(d, dict):
        return False, None

    # Explicit success / ok check (respect explicit truthiness)
    if "success" in d:
        if not bool(d["success"]):
            err = d.get("error") or d.get("message") or d.get("description")
            return True, str(err) if err is not None else "Operation failed"
        return False, None

    if "ok" in d:
        if not bool(d["ok"]):
            err = d.get("error") or d.get("message") or d.get("description")
            return True, str(err) if err is not None else "Operation failed"
        return False, None

    # Status check
    status_str = str(d.get("status", "")).lower().strip()
    if status_str in ("error", "failed", "failure", "unverified", "timeout", "blocked", "not_configured", "rate_limited"):
        err = d.get("error") or d.get("message") or d.get("description") or f"Status: {status_str}"
        return True, str(err)

    # Explicit non-empty top-level error
    if d.get("error"):
        return True, str(d["error"])

    # Check nested payload dictionaries
    for key in ("data", "result", "payload", "action_result", "backend_result", "response"):
        nested = d.get(key)
        if isinstance(nested, dict):
            failed, err = _inspect_dict_failure(nested)
            if failed:
                return True, err

    return False, None


def normalize_tool_output(raw: Any) -> ToolExecutionResult:
    """
    Convert whatever a tool callable returned into a ToolExecutionResult.
    Accepts: a ToolExecutionResult (pass-through), a dict (legacy
    {"output": ...} shape, optionally with "success"/"error"/"metadata" or nested payload dicts),
    or any other value (stringified as a successful result).
    """
    if isinstance(raw, ToolExecutionResult):
        return raw
    if isinstance(raw, dict):
        failed, err_msg = _inspect_dict_failure(raw)
        metadata = raw.get("metadata", {})
        output = raw["output"] if "output" in raw else raw
        output_str = sanitize_secrets(str(output)) if output is not None else ""

        if failed:
            error = sanitize_secrets(err_msg) if err_msg else "Tool execution failed."
            return ToolExecutionResult(
                success=False,
                output=output_str,
                error=error,
                metadata=metadata if isinstance(metadata, dict) else {},
            )
        return ToolExecutionResult(
            success=True,
            output=output_str,
            error=None,
            metadata=metadata if isinstance(metadata, dict) else {},
        )
    return ToolExecutionResult(success=True, output=sanitize_secrets(str(raw)))



def sandbox_result_to_tool_result(
    result: SandboxResult, max_chars: int = DEFAULT_MAX_OBSERVATION_CHARS
) -> ToolExecutionResult:
    """Convert a CodeInterpreterSandbox.execute_python() SandboxResult into a ToolExecutionResult."""
    stdout = sanitize_secrets(_clean_sandbox_text(result.stdout or ""))
    if result.success:
        output = stdout.strip() or "Code chạy thành công (không có output)."
        return ToolExecutionResult(
            success=True,
            output=truncate_text(output, max_chars),
            metadata={"exit_code": result.exit_code, "execution_time_ms": result.execution_time_ms},
        )

    error_text = sanitize_secrets(result.error or _clean_sandbox_text(result.stderr or "") or "Sandbox execution failed.")
    return ToolExecutionResult(
        success=False,
        output=truncate_text(stdout, max_chars),
        error=truncate_text(error_text, max_chars),
        metadata={"exit_code": result.exit_code, "execution_time_ms": result.execution_time_ms},
    )


def format_observation(result: ToolExecutionResult, max_chars: int = DEFAULT_MAX_OBSERVATION_CHARS) -> str:
    """Render a ToolExecutionResult as the bounded observation string stored in agent history."""
    if result.success:
        return truncate_text(sanitize_secrets(result.output), max_chars)
    text = sanitize_secrets(result.error or result.output or "Lỗi không xác định.")
    if not text.lstrip().startswith(("Lỗi", "Tool", "Tham số")):
        text = f"Lỗi: {text}"
    return truncate_text(text, max_chars)
