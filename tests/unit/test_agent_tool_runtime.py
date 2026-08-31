"""
tests/unit/test_agent_tool_runtime.py
=======================================
Unit tests for jarvis.agent.tool_runtime — the structured tool-execution
contract (ToolExecutionResult, truncation, SandboxResult conversion).

Fully deterministic and hardware-free: SandboxResult instances are
constructed directly (no real sandbox process is spawned).
"""
from __future__ import annotations

import pytest

from jarvis.agent.tool_runtime import (
    DEFAULT_MAX_OBSERVATION_CHARS,
    ToolExecutionResult,
    format_observation,
    normalize_tool_output,
    sandbox_result_to_tool_result,
    truncate_text,
)
from jarvis.sandbox.interpreter import SandboxResult

# --- truncate_text -----------------------------------------------------

def test_truncate_text_short_text_is_unchanged():
    text = "hello world"
    assert truncate_text(text, max_chars=100) == text


def test_truncate_text_exact_length_is_unchanged():
    text = "x" * 50
    assert truncate_text(text, max_chars=50) == text


def test_truncate_text_long_text_is_bounded_with_marker():
    text = "x" * 10000
    result = truncate_text(text, max_chars=100)
    assert len(result) > 100  # marker adds length, but original content is bounded
    assert result.startswith("x" * 100)
    assert "[TRUNCATED" in result
    assert "100" in result


def test_truncate_text_none_is_empty_string():
    assert truncate_text(None, max_chars=100) == ""  # type: ignore[arg-type]


# --- normalize_tool_output ----------------------------------------------

def test_normalize_tool_output_passthrough_result():
    original = ToolExecutionResult(success=False, output="", error="boom")
    assert normalize_tool_output(original) is original


def test_normalize_tool_output_dict_with_output_key():
    result = normalize_tool_output({"output": "hello"})
    assert result.success is True
    assert result.output == "hello"
    assert result.error is None


def test_normalize_tool_output_dict_with_explicit_failure():
    result = normalize_tool_output({"output": "", "success": False, "error": "nope"})
    assert result.success is False
    assert result.error == "nope"


def test_normalize_tool_output_dict_without_output_key_stringifies_whole_dict():
    raw = {"foo": "bar"}
    result = normalize_tool_output(raw)
    assert result.success is True
    assert "foo" in result.output


def test_normalize_tool_output_non_dict_value_becomes_successful_string():
    result = normalize_tool_output(42)
    assert result.success is True
    assert result.output == "42"


def test_normalize_tool_output_metadata_preserved():
    result = normalize_tool_output({"output": "ok", "metadata": {"exit_code": 0}})
    assert result.metadata == {"exit_code": 0}


def test_normalize_tool_output_non_dict_metadata_is_ignored_safely():
    result = normalize_tool_output({"output": "ok", "metadata": "not-a-dict"})
    assert result.metadata == {}


# --- sandbox_result_to_tool_result ---------------------------------------

def _make_sandbox_result(**overrides) -> SandboxResult:
    defaults = dict(success=True, exit_code=0, stdout="", stderr="")
    defaults.update(overrides)
    return SandboxResult(**defaults)


def test_sandbox_result_to_tool_result_success_uses_stdout():
    sr = _make_sandbox_result(success=True, exit_code=0, stdout="42\n")
    result = sandbox_result_to_tool_result(sr)
    assert result.success is True
    assert result.output == "42"


def test_sandbox_result_to_tool_result_success_empty_stdout_has_fallback_message():
    sr = _make_sandbox_result(success=True, exit_code=0, stdout="")
    result = sandbox_result_to_tool_result(sr)
    assert result.success is True
    assert result.output != ""


def test_sandbox_result_to_tool_result_failure_includes_error():
    sr = _make_sandbox_result(
        success=False, exit_code=-1, stdout="", stderr="", error="AST Safety Check Failed: Forbidden import 'os'"
    )
    result = sandbox_result_to_tool_result(sr)
    assert result.success is False
    assert "Forbidden import" in result.error


def test_sandbox_result_to_tool_result_failure_falls_back_to_stderr_when_no_error():
    sr = _make_sandbox_result(success=False, exit_code=1, stdout="", stderr="boom trace", error=None)
    result = sandbox_result_to_tool_result(sr)
    assert result.success is False
    assert "boom trace" in result.error


def test_sandbox_result_to_tool_result_bounds_huge_stdout():
    """A sandbox call that legitimately succeeds with huge stdout must still be
    bounded before it is treated as an agent observation — regardless of the
    sandbox's own much larger internal 1MB cap."""
    huge = "y" * 50000
    sr = _make_sandbox_result(success=True, exit_code=0, stdout=huge)
    result = sandbox_result_to_tool_result(sr, max_chars=500)
    assert len(result.output) < len(huge)
    assert "[TRUNCATED" in result.output


def test_sandbox_result_to_tool_result_strips_leaked_readiness_sentinel_lf():
    sr = _make_sandbox_result(success=True, exit_code=0, stdout="\x02JARVIS_SANDBOX_READY_v1\x03\n7\n")
    result = sandbox_result_to_tool_result(sr)
    assert "\x02" not in result.output
    assert "\x03" not in result.output
    assert "7" in result.output


def test_sandbox_result_to_tool_result_strips_leaked_readiness_sentinel_crlf():
    """Defensive cleanup for the CRLF-vs-LF mismatch: a Windows CRLF-terminated
    sentinel line must also be fully stripped, not just partially."""
    sr = _make_sandbox_result(success=True, exit_code=0, stdout="\x02JARVIS_SANDBOX_READY_v1\x03\r\n7\r\n")
    result = sandbox_result_to_tool_result(sr)
    assert "\x02" not in result.output
    assert "\x03" not in result.output
    assert "7" in result.output


def test_sandbox_result_to_tool_result_metadata_has_exit_code():
    sr = _make_sandbox_result(success=True, exit_code=0, stdout="ok", execution_time_ms=12.5)
    result = sandbox_result_to_tool_result(sr)
    assert result.metadata["exit_code"] == 0
    assert result.metadata["execution_time_ms"] == 12.5


# --- format_observation ----------------------------------------------------

def test_format_observation_success_returns_output_unprefixed():
    result = ToolExecutionResult(success=True, output="all good")
    assert format_observation(result) == "all good"


def test_format_observation_failure_prefixes_loi():
    result = ToolExecutionResult(success=False, output="", error="something broke")
    observation = format_observation(result)
    assert observation.startswith("Lỗi:")
    assert "something broke" in observation


def test_format_observation_does_not_double_prefix_when_error_already_prefixed():
    result = ToolExecutionResult(success=False, output="", error="Lỗi: already prefixed")
    observation = format_observation(result)
    assert observation.count("Lỗi:") == 1


def test_format_observation_unknown_tool_message_is_not_re_prefixed():
    result = ToolExecutionResult(success=False, output="", error="Tool 'ghost' không tồn tại.")
    observation = format_observation(result)
    assert observation.count("Lỗi") == 0
    assert "không tồn tại" in observation


def test_format_observation_is_bounded_for_huge_failed_output():
    result = ToolExecutionResult(success=False, output="z" * 20000, error=None)
    observation = format_observation(result, max_chars=200)
    assert len(observation) < 20000


def test_format_observation_default_bound_matches_module_default():
    result = ToolExecutionResult(success=True, output="x" * (DEFAULT_MAX_OBSERVATION_CHARS + 500))
    observation = format_observation(result)
    assert "[TRUNCATED" in observation
