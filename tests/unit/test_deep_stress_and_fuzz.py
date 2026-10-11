"""
tests/unit/test_deep_stress_and_fuzz.py
=======================================
Deep Stress, Boundary Fuzzing, and Concurrency Verification Suite for JARVIS.
Validates system invariants beyond ordinary unit test cases:
  1. High-concurrency race condition resistance (SafetyGate, ActionDispatcher, EventBus).
  2. Boundary fuzzing on Path Traversal defense (PathGuard).
  3. Pathological dictionary inspection robustness (ToolRuntime).
  4. Homoglyph normalization & Unicode fuzzing against SafetyGateInterceptor.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Any
import pytest

from jarvis.agent.tool_runtime import _inspect_dict_failure, sanitize_secrets
from jarvis.automation.safety_gate import SafetyGate
from jarvis.core.dispatcher import ActionDispatcher, EventBus, _normalize_handler_outcome
from jarvis.planner.safety_interceptor import SafetyGateInterceptor, normalize_homoglyphs
from jarvis.security.path_guard import validate_safe_path


# ============================================================================
# 1. CONCURRENCY & RACE CONDITION STRESS TESTS
# ============================================================================

def test_concurrent_safety_gate_token_generation_and_consumption():
    """Verify SafetyGate maintains strict one-shot token consumption under concurrent race."""
    gate = SafetyGate(timeout_seconds=5.0)
    num_threads = 50
    tokens: list[str] = []
    lock = threading.Lock()

    def create_token(idx: int) -> None:
        tok = gate.request_confirmation(f"action_{idx}", payload={"idx": idx})
        with lock:
            tokens.append(tok)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(create_token, i) for i in range(num_threads)]
        concurrent.futures.wait(futures)

    assert len(tokens) == num_threads
    assert len(set(tokens)) == num_threads  # All tokens must be strictly unique

    # Confirm all tokens
    for tok in tokens:
        assert gate.confirm(tok) is True

    # Concurrent race to consume each token: exactly ONE thread must win consume()
    success_consumes: list[bool] = []

    def try_consume(tok: str) -> None:
        res = gate.consume(tok)
        with lock:
            if res:
                success_consumes.append(True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads * 2) as executor:
        consume_futures = []
        for tok in tokens:
            # 2 competing threads per token
            consume_futures.append(executor.submit(try_consume, tok))
            consume_futures.append(executor.submit(try_consume, tok))
        concurrent.futures.wait(consume_futures)

    # Exactly num_threads successful consumptions (zero duplicate consume)
    assert len(success_consumes) == num_threads


def test_concurrent_eventbus_dispatch_and_subscription_isolation():
    """Verify EventBus handles rapid concurrent event emission and subscriber isolation without deadlock."""
    bus = EventBus()
    received_counts: dict[str, int] = {"sub1": 0, "sub2": 0}
    lock = threading.Lock()

    def handler_1(**payload: Any) -> None:
        with lock:
            received_counts["sub1"] += 1

    def handler_2(**payload: Any) -> None:
        with lock:
            received_counts["sub2"] += 1

    bus.subscribe("stress.event", handler_1)
    bus.subscribe("stress.event", handler_2)

    num_emissions = 200

    def emit_event(seq: int) -> None:
        bus.publish("stress.event", seq=seq)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(emit_event, i) for i in range(num_emissions)]
        concurrent.futures.wait(futures)

    assert received_counts["sub1"] == num_emissions
    assert received_counts["sub2"] == num_emissions


# ============================================================================
# 2. PATH TRAVERSAL & BOUNDARY FUZZING TESTS
# ============================================================================

@pytest.mark.parametrize(
    "malicious_path",
    [
        "../../etc/passwd",
        "..\\..\\Windows\\System32\\cmd.exe",
        "%2e%2e%2f%2e%2e%2fWindows",
        "%252e%252e%252fWindows",
        "nested/dir/../../../secret.txt",
        "valid_dir/\x00hidden_traversal",
        "\x00../../boot.ini",
        "....//....//Windows",
        "..%5c..%5cWindows",
        " ",
        "\t\r\n",
        "",
        None,
    ],
)
def test_path_guard_fuzzing_rejects_malicious_inputs(tmp_path, malicious_path):
    """Verify validate_safe_path fails closed on malicious inputs and traversal patterns."""
    is_safe, code, resolved = validate_safe_path(malicious_path, base_dir=tmp_path)
    assert is_safe is False
    assert resolved is None
    assert code in ("PATH_EMPTY", "INVALID_CHARACTERS", "PATH_TRAVERSAL_DETECTED")


# ============================================================================
# 3. HOMOGLYPH & UNICODE EVASION FUZZING
# ============================================================================

@pytest.mark.parametrize(
    "raw_cmd, expected_canonical",
    [
        ("ѕhutdown", "shutdown"),           # Cyrillic small 's'
        ("fіle_delete", "file_delete"),     # Cyrillic small 'i'
        ("dеlеtе_fіlе", "delete_file"),     # Cyrillic 'e', 'i'
        ("kіll_prосеss", "kill_process"),   # Cyrillic 'i', 'o', 'c'
    ],
)
def test_homoglyph_normalization_foils_evasion(raw_cmd, expected_canonical):
    """Verify Unicode homoglyph normalization foils obfuscated action names."""
    normalized = normalize_homoglyphs(raw_cmd)
    assert normalized == expected_canonical


def test_safety_interceptor_catches_homoglyph_attacks():
    """Verify SafetyGateInterceptor identifies destructive actions disguised with homoglyphs."""
    # "fіle_delete" uses Cyrillic 'і'
    obfuscated_action = "fіle_delete"
    normalized = normalize_homoglyphs(obfuscated_action)
    assert normalized in SafetyGateInterceptor.HIGH_RISK_ACTIONS


# ============================================================================
# 4. PATHOLOGICAL DICTIONARY INSPECTION ROBUSTNESS
# ============================================================================

def test_inspect_dict_failure_handles_pathological_shapes():
    """Verify _inspect_dict_failure withstands unusual dictionary hierarchies without crashing."""
    # Deeply nested payload dictionary
    deep_dict = {"status": "ok"}
    curr = deep_dict
    for _ in range(5):
        curr["data"] = {"status": "ok"}
        curr = curr["data"]
    curr["status"] = "timeout"

    failed, msg = _inspect_dict_failure(deep_dict)
    assert failed is True
    assert "timeout" in str(msg).lower()

    # Non-dict inputs
    assert _inspect_dict_failure(None) == (False, None)
    assert _inspect_dict_failure("error string") == (False, None)
    assert _inspect_dict_failure([1, 2, 3]) == (False, None)


def test_sanitize_secrets_masks_sensitive_credentials():
    """Verify sanitize_secrets masks diverse API keys and bearer tokens."""
    raw = (
        "Logs: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI... "
        "and Gemini AIzaSyCGAb74_934jkd834hf84jfd834hf "
        "and OpenAI sk-proj-1234567890abcdef1234567890 "
        "and Bot token 123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"
    )
    sanitized = sanitize_secrets(raw)
    assert "AIzaSy" not in sanitized
    assert "sk-proj" not in sanitized
    assert "Bearer [REDACTED]" in sanitized
    assert "[REDACTED]" in sanitized
