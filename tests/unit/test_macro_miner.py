"""
tests/unit/test_macro_miner.py
==============================
Unit Test Suite for Sequential Action Trajectory Miner.
Validates:
  1. Action trajectory recording and buffer bounds.
  2. Session partitioning based on time gaps.
  3. Mining frequent compound macro sequences (PrefixSpan).
  4. Suggested trigger generation in natural Vietnamese.
"""
import time
import pytest

from jarvis.learning.macro_miner import CandidateMacro, SequentialMacroMiner


def test_macro_miner_recording_and_partitioning():
    """Validates action logging and session separation."""
    miner = SequentialMacroMiner(max_history_len=10, session_gap_threshold_s=0.1)

    # Session 1: two rapid actions
    miner.record_action("app_open", {"app_name": "chrome"}, context_app="desktop")
    miner.record_action("tab_new", {}, context_app="browser")

    # Wait to trigger session gap
    time.sleep(0.15)

    # Session 2: one action
    miner.record_action("system_volume", {"level": 50}, context_app="system")

    sessions = miner.extract_sessions()
    assert len(sessions) == 2
    assert len(sessions[0]) == 2
    assert len(sessions[1]) == 1


def test_macro_miner_frequent_subsequence_detection():
    """Validates detection of frequent contiguous action subsequences."""
    miner = SequentialMacroMiner(session_gap_threshold_s=1.0)

    # Simulate repeating workflow 3 times: [app_open -> terminal_run -> git_pull]
    workflow = [
        ("app_open", {"app_name": "vscode"}, "desktop"),
        ("terminal_run", {"cmd": "git status"}, "vscode"),
        ("git_pull", {}, "vscode"),
    ]

    base_time = 1000.0
    for repetition in range(3):
        for step_idx, (intent, slots, ctx) in enumerate(workflow):
            t_act = base_time + (repetition * 100.0) + (step_idx * 0.1)
            miner.record_action(intent, slots, context_app=ctx, timestamp_s=t_act)

    # Mine macros with min_support=3
    candidates = miner.mine_frequent_macros(min_support=3, min_length=2, max_length=3)

    assert len(candidates) >= 1
    top_candidate = candidates[0]
    assert isinstance(top_candidate, CandidateMacro)
    assert top_candidate.support_count == 3
    assert len(top_candidate.action_intents) >= 2
    assert len(top_candidate.suggested_triggers) >= 1
    assert any("thực hiện quy trình" in trig for trig in top_candidate.suggested_triggers)
