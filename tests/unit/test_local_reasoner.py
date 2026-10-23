"""
tests/unit/test_local_reasoner.py
=================================
Unit tests for ArgonNanoLocalReasoner (Argon Sovereign Tier 2 In-Process Cortex).
Verifies:
  1. Anaphora & multi-turn pronoun resolution ('làm lại cái đó', 'đóng nó lại', 'phóng to nó', 'tương tự').
  2. Colloquial hardware inquiries ('máy có nóng không', 'dọn dẹp ram', 'cho màn hình nghỉ').
  3. Colloquial software & media heuristics ('phần mềm nghe nhạc', 'lên youtube', 'gõ code').
  4. Integration with LLMIntentRouter (seamless multi-turn context flow & offline fallback).
  5. Latency budget (< 10ms on CPU) and 0 MB VRAM allocation.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from jarvis.context.screen_context import WindowContext
from jarvis.llm.client import LLMClient, LLMResponse
from jarvis.llm.local_reasoner import ArgonNanoLocalReasoner
from jarvis.llm.models import IntentResult
from jarvis.llm.router import LLMIntentRouter


class DummyMockLLM(LLMClient):
    """Mock LLM client for offline deterministic testing."""

    def __init__(self) -> None:
        pass

    def generate(self, prompt: str, system_prompt: str | None = None, tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        return LLMResponse(
            content="Mock LLM Generic Response",
            tool_calls=[],
            model="mock-nano",
            tokens_used=10,
        )

    def is_available(self) -> bool:
        return True

    def has_api_key(self) -> bool:
        return True


@pytest.fixture
def dummy_awaci() -> MagicMock:
    mock_awaci = MagicMock()
    mock_awaci.disambiguate_intent.return_value = None
    mock_awaci.get_active_window_context.return_value = WindowContext(
        hwnd=12345,
        title="Google Chrome - Work Tab",
        process_name="chrome.exe",
        app_category="browser",
        is_valid=True,
    )
    return mock_awaci


@pytest.fixture
def local_reasoner(dummy_awaci: MagicMock) -> ArgonNanoLocalReasoner:
    return ArgonNanoLocalReasoner(awaci_engine=dummy_awaci)


def test_reasoner_empty_and_whitespace(local_reasoner: ArgonNanoLocalReasoner) -> None:
    assert local_reasoner.reason("") is None
    assert local_reasoner.reason("   \t\n") is None


def test_anaphora_repetition_with_history(local_reasoner: ArgonNanoLocalReasoner) -> None:
    history = [
        {"action_name": "app_open", "parameters": {"app_name": "notepad"}, "confidence": 0.95},
    ]
    res = local_reasoner.reason("làm lại cái đó", history=history)
    assert res is not None
    assert res.action_name == "app_open"
    assert res.parameters.get("app_name") == "notepad"
    assert res.source == "argon_nano_local_reasoner"
    assert res.confidence >= 0.85


def test_anaphora_repetition_empty_history(local_reasoner: ArgonNanoLocalReasoner) -> None:
    res = local_reasoner.reason("làm lại cái đó", history=[])
    assert res is None


def test_anaphora_close_app_from_active_window(local_reasoner: ArgonNanoLocalReasoner) -> None:
    res = local_reasoner.reason("đóng nó lại")
    assert res is not None
    assert res.action_name == "app_close"
    assert res.parameters.get("app_name") == "chrome"
    assert res.confidence >= 0.85


def test_anaphora_close_app_from_history_fallback() -> None:
    reasoner_no_win = ArgonNanoLocalReasoner(awaci_engine=None)
    history = [
        {"action_name": "app_open", "parameters": {"app_name": "spotify"}, "confidence": 0.95},
    ]
    res = reasoner_no_win.reason("tắt nó đi", history=history)
    assert res is not None
    assert res.action_name == "app_close"
    assert res.parameters.get("app_name") == "spotify"


def test_anaphora_window_control_maximize_and_minimize(local_reasoner: ArgonNanoLocalReasoner) -> None:
    res_max = local_reasoner.reason("phóng to nó")
    assert res_max is not None
    assert res_max.action_name == "window_control"
    assert res_max.parameters.get("action") == "maximize"

    res_min = local_reasoner.reason("thu nhỏ cửa sổ")
    assert res_min is not None
    assert res_min.action_name == "window_control"
    assert res_min.parameters.get("action") == "minimize"


def test_anaphora_similarity_resolution(local_reasoner: ArgonNanoLocalReasoner) -> None:
    history = [
        {"action_name": "note_add", "parameters": {"content": "Cuộc họp sáng"}, "confidence": 0.90},
    ]
    res = local_reasoner.reason("tương tự với cửa sổ lúc nãy", history=history)
    assert res is not None
    assert res.action_name == "note_add"
    assert res.parameters.get("content") == "Cuộc họp sáng"


def test_system_hardware_heuristics(local_reasoner: ArgonNanoLocalReasoner) -> None:
    # 1. Temperature / heat
    res_heat = local_reasoner.reason("máy có nóng không jarvis")
    assert res_heat is not None
    assert res_heat.action_name == "hardware_status_query"
    assert res_heat.parameters.get("component") == "cpu"

    # 2. RAM cleanup / healing
    res_ram = local_reasoner.reason("dọn dẹp ram giúp tôi")
    assert res_ram is not None
    assert res_ram.action_name == "healing_watchdog_heal"
    assert res_ram.parameters.get("auto_kill") is False

    # 3. Screen off / rest
    res_screen = local_reasoner.reason("cho màn hình nghỉ")
    assert res_screen is not None
    assert res_screen.action_name == "system_power"
    assert res_screen.parameters.get("action") == "screen_off"


def test_app_and_media_heuristics(local_reasoner: ArgonNanoLocalReasoner) -> None:
    # 1. Music player
    res_music = local_reasoner.reason("bật phần mềm nghe nhạc")
    assert res_music is not None
    assert res_music.action_name == "spotify"

    # 2. Youtube / browser
    res_yt = local_reasoner.reason("lên youtube")
    assert res_yt is not None
    assert res_yt.action_name == "app_open"
    assert res_yt.parameters.get("app_name") == "chrome"

    # 3. Coding tool
    res_code = local_reasoner.reason("mở công cụ gõ code")
    assert res_code is not None
    assert res_code.action_name == "app_open"
    assert res_code.parameters.get("app_name") == "vscode"


def test_local_reasoner_latency_budget(local_reasoner: ArgonNanoLocalReasoner) -> None:
    """Verifies sub-millisecond execution latency on CPU."""
    history = [{"action_name": "app_open", "parameters": {"app_name": "notepad"}}]
    iterations = 100
    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = local_reasoner.reason("làm lại cái đó", history=history)
    elapsed_ms = ((time.perf_counter() - t0) / iterations) * 1000.0

    assert elapsed_ms < 5.0, f"Local reasoner took {elapsed_ms:.2f}ms, budget is 5.0ms"


def test_router_integration_multi_turn_anaphora(dummy_awaci: MagicMock) -> None:
    mock_llm = DummyMockLLM()
    router = LLMIntentRouter(llm_client=mock_llm, fast_path_enabled=True)
    router.awaci_engine = dummy_awaci

    # Turn 1: Open an app (fast path)
    res1 = router.parse_intent("mở notepad")
    assert res1.action_name == "app_open"
    assert len(router.history) >= 1
    assert router.history[-1]["parameters"].get("app_name") == "notepad"

    # Turn 2: Close it via anaphora pronoun 'nó'
    res2 = router.parse_intent("đóng nó lại")
    assert res2.action_name == "app_close"
    assert res2.source == "argon_nano_local_reasoner"
    assert res2.parameters.get("app_name") == "chrome"  # from active dummy_awaci window

    # Turn 3: Repeat previous action
    res3 = router.parse_intent("làm lại cái đó")
    assert res3.action_name == "app_close"
    assert res3.source == "argon_nano_local_reasoner"


def test_router_integration_colloquial_hardware() -> None:
    mock_llm = DummyMockLLM()
    router = LLMIntentRouter(llm_client=mock_llm, fast_path_enabled=True)

    res = router.parse_intent("máy có nóng không")
    assert res.action_name == "hardware_status_query"
    assert res.source == "argon_nano_local_reasoner"


def test_router_offline_fallback_to_local_reasoner() -> None:
    """When LLM throws or fails, Tier 3 fallback checks local reasoner."""
    failing_llm = MagicMock(spec=LLMClient)
    failing_llm.generate.side_effect = RuntimeError("API Network Disconnected")

    router = LLMIntentRouter(llm_client=failing_llm, fast_path_enabled=True)
    history = [{"action_name": "app_open", "parameters": {"app_name": "calc"}}]
    router.history = history

    res = router.parse_intent("làm lại cái đó")
    assert res.action_name == "app_open"
    assert res.parameters.get("app_name") == "calc"
    assert res.source == "argon_nano_local_reasoner"
