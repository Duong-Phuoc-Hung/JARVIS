"""
tests/unit/test_macro_crystallizer.py
=====================================
Unit Test Suite for In-Situ Macro Crystallizer & Dynamic ActionTree Injection.
Validates:
  1. Fail-closed security rejection of prohibited intents (e.g. system_power).
  2. Reward expectation threshold gating (R >= 1.5).
  3. Dynamic ActionTree grammar injection and unregistration.
"""
import pytest

from jarvis.learning.macro_crystallizer import CrystallizationResult, InSituMacroCrystallizer
from jarvis.learning.macro_miner import CandidateMacro
from jarvis.planner.action_tree import InProcessGrammarTreeSearch


def test_crystallizer_prohibited_intent_rejection():
    """Validates that candidate macros containing prohibited intents are rejected fail-closed."""
    crystallizer = InSituMacroCrystallizer()
    tree = InProcessGrammarTreeSearch()

    bad_candidate = CandidateMacro(
        macro_id="macro_danger_01",
        action_intents=("app_open", "system_power"),
        action_slots=({}, {"power_state": "shutdown"}),
        support_count=5,
        context_app="desktop",
        suggested_triggers=("tắt máy tính và mở app",),
        confidence=0.95,
    )

    result = crystallizer.evaluate_and_crystallize(bad_candidate, tree)

    assert isinstance(result, CrystallizationResult)
    assert result.is_crystallized is False
    assert result.expected_reward == -2.0
    assert "violates autonomous crystallization safety rules" in str(result.rejection_reason)
    assert "macro_danger_01" not in tree.grammar.get("macro", {})


def test_crystallizer_successful_action_tree_injection():
    """Validates successful vetting, reward qualification, and ActionTree grammar injection."""
    crystallizer = InSituMacroCrystallizer(reward_threshold=1.5)
    tree = InProcessGrammarTreeSearch()

    good_candidate = CandidateMacro(
        macro_id="macro_dev_workflow_01",
        action_intents=("app_open", "tab_new", "spotify_play"),
        action_slots=({"app_name": "vscode"}, {}, {"query": "chill"}),
        support_count=4,
        context_app="desktop",
        suggested_triggers=("bắt đầu làm việc", "dev mode"),
        confidence=0.85,
    )

    result = crystallizer.evaluate_and_crystallize(good_candidate, tree)

    assert result.is_crystallized is True
    assert result.expected_reward >= 1.5
    assert "macro" in tree.grammar
    assert "macro_dev_workflow_01" in tree.grammar["macro"]

    # Retrieve macro
    saved_macro = crystallizer.get_crystallized_macro("macro_dev_workflow_01")
    assert saved_macro is not None
    assert saved_macro.macro_id == "macro_dev_workflow_01"

    # Unregister
    unregistered = crystallizer.unregister_macro("macro_dev_workflow_01", tree)
    assert unregistered is True
    assert "macro_dev_workflow_01" not in tree.grammar["macro"]
