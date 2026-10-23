"""
tests/unit/test_action_tree.py
==============================
Unit Test Suite for In-Process Grammar-Constrained Action-Tree Search (Argon v6.0).
Validates:
  - Tri-Signal value scoring function and weights.
  - Fail-closed security pruning on unauthorized privileged actions.
  - AWACI desktop window alignment bonus.
  - Sub-millisecond CPU search latency (< 0.65ms per query).
  - Integration with ArgonNanoLocalReasoner.
"""
import time
import pytest

from jarvis.context.screen_context import WindowContext
from jarvis.llm.local_reasoner import ArgonNanoLocalReasoner
from jarvis.planner.action_tree import (
    ActionCandidateNode,
    InProcessGrammarTreeSearch,
    TriSignalScorer,
)


def test_tri_signal_scorer_basic_and_awaci():
    """Validates TriSignalScorer weights and window alignment bonus."""
    scorer = TriSignalScorer(weight_nlu=0.50, weight_awaci=0.35, weight_security=0.15)
    schema = {
        "default_app": "spotify",
        "app_match": "spotify",
        "requires_admin": False,
    }

    # Case A: High NLU, No window match, User privilege
    score_a, pruned_a, _ = scorer.score(
        domain="media",
        intent="spotify_play",
        schema=schema,
        nlu_priors={"spotify_play": 0.80},
        active_window_title="Google Chrome - YouTube",
        privilege_level="USER",
    )
    assert not pruned_a
    # NLU: 0.50 * 0.80 = 0.40; AWACI: 0.35 * 0.0 = 0.0; Security: 0.15 * 0.8 = 0.12 => 0.52
    assert pytest.approx(score_a, 0.01) == 0.52

    # Case B: Same NLU, but Spotify window IS active
    score_b, pruned_b, _ = scorer.score(
        domain="media",
        intent="spotify_play",
        schema=schema,
        nlu_priors={"spotify_play": 0.80},
        active_window_title="Spotify Free - Sơn Tùng M-TP",
        privilege_level="USER",
    )
    assert not pruned_b
    # AWACI gets 1.0 => +0.35 => total 0.87
    assert pytest.approx(score_b, 0.01) == 0.87
    assert score_b > score_a


def test_tri_signal_scorer_fail_closed_privilege_pruning():
    """Validates that actions requiring admin are strictly pruned for standard users."""
    scorer = TriSignalScorer()
    admin_schema = {
        "default_app": "system",
        "requires_admin": True,
    }

    # Standard USER: must be pruned
    score_user, is_pruned, reason = scorer.score(
        domain="system",
        intent="system_power",
        schema=admin_schema,
        nlu_priors={"system_power": 0.99},
        active_window_title="",
        privilege_level="USER",
    )
    assert is_pruned is True
    assert score_user == -float("inf")
    assert reason == "UNAUTHORIZED_PRIVILEGE_REQUIRED"

    # ADMIN: allowed
    score_admin, is_pruned_admin, _ = scorer.score(
        domain="system",
        intent="system_power",
        schema=admin_schema,
        nlu_priors={"system_power": 0.99},
        active_window_title="",
        privilege_level="ADMIN",
    )
    assert is_pruned_admin is False
    assert score_admin > 0.50


def test_in_process_grammar_tree_search():
    """Validates bounded tree search over typed action space."""
    tree_search = InProcessGrammarTreeSearch(confidence_cutoff=0.40)

    # 1. Clear media query
    candidate = tree_search.search(
        text="bật nhạc chill",
        nlu_priors={"media": 0.85, "spotify_play": 0.85},
        active_window_title="Spotify",
        privilege_level="USER",
    )
    assert isinstance(candidate, ActionCandidateNode)
    assert candidate.domain == "media"
    assert candidate.intent == "spotify_play"
    assert candidate.value_score >= 0.70

    # 2. Ambiguous query below cutoff returns None
    low_cand = tree_search.search(
        text="hôm nay trời đẹp nhỉ",
        nlu_priors={"media": 0.05, "system": 0.05},
        active_window_title="Desktop",
        privilege_level="USER",
    )
    assert low_cand is None


def test_in_process_grammar_tree_latency_budget():
    """Validates that Action-Tree Search executes under 0.65ms per query."""
    tree_search = InProcessGrammarTreeSearch(confidence_cutoff=0.40)
    priors = {"system": 0.80, "system_volume": 0.80}

    # Warmup
    for _ in range(5):
        tree_search.search("tăng âm lượng", priors, "Desktop", "USER")

    n_runs = 50
    t0 = time.perf_counter()
    for _ in range(n_runs):
        tree_search.search("tăng âm lượng", priors, "Desktop", "USER")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    avg_ms = elapsed_ms / n_runs
    assert avg_ms < 0.65, f"Action-Tree search too slow: {avg_ms:.3f}ms (budget < 0.65ms)"


def test_argon_nano_local_reasoner_tree_integration():
    """Validates ArgonNanoLocalReasoner utilizing Action-Tree search for resolution."""
    reasoner = ArgonNanoLocalReasoner(confidence_threshold=0.35)

    # A. Volume query resolved via tree search
    res_vol = reasoner.reason("chỉnh âm lượng giúp tôi")
    assert res_vol is not None
    assert res_vol.action_name == "system_volume"
    assert res_vol.source == "argon_action_tree_search"
    assert res_vol.confidence >= 0.35

    # B. Weather query resolved via tree search
    res_weather = reasoner.reason("xem thời tiết hôm nay")
    assert res_weather is not None
    assert res_weather.action_name == "weather_query"
    assert res_weather.source == "argon_action_tree_search"

    # C. Active window context alignment via tab navigation
    chrome_ctx = WindowContext(hwnd=123, title="Google Chrome", process_name="chrome.exe", app_category="browser")
    res_tab = reasoner.reason("mở tab mới giúp tôi", awaci_context=chrome_ctx)
    assert res_tab is not None
    assert res_tab.action_name == "tab_new"
    assert res_tab.source == "argon_action_tree_search"
    assert res_tab.confidence >= 0.70  # Gets AWACI bonus for Chrome!

    # D. Unresolvable query returns None
    res_unknown = reasoner.reason("triết học hiện sinh là gì")
    assert res_unknown is None
