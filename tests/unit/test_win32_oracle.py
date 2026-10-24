"""
tests/unit/test_win32_oracle.py
===============================
Unit tests for Win32 execution grounding reward oracle.
"""
from __future__ import annotations

import pytest

from jarvis.core.models import ActionResult, ActionStatus
from jarvis.learning.win32_oracle import OracleConfig, Win32ExecutionRewardOracle


def test_oracle_success_reward():
    """Verifies positive execution reward for successful action."""
    oracle = Win32ExecutionRewardOracle()

    act_res = ActionResult(
        action_name="system_volume",
        status=ActionStatus.SUCCESS,
        code="VOLUME_SET_OK",
        message="Volume set to 80",
        data={"level": 80},
    )

    eval_res = oracle.evaluate(
        action_name="system_volume",
        parameters={"level": 80},
        action_result=act_res,
        initial_foreground_title="Desktop",
    )

    assert eval_res.total_reward > 0.0
    assert eval_res.status_reward == 1.0
    assert not eval_res.is_vetoed_by_security
    assert eval_res.evaluation_latency_ms > 0.0


def test_oracle_failed_action_penalty():
    """Verifies negative reward for failed action."""
    oracle = Win32ExecutionRewardOracle()

    act_res = ActionResult(
        action_name="app_launch",
        status=ActionStatus.FAILED,
        code="APP_NOT_FOUND",
        message="Cannot find app",
        data={},
    )

    eval_res = oracle.evaluate(
        action_name="app_launch",
        parameters={"app_name": "non_existent_app"},
        action_result=act_res,
    )

    assert eval_res.total_reward < 0.0
    assert eval_res.status_reward == -1.0


def test_oracle_security_veto_destructive_action():
    """Verifies that destructive intents are vetoed with severe negative penalty."""
    oracle = Win32ExecutionRewardOracle()

    eval_res = oracle.evaluate(
        action_name="format_disk",
        parameters={"drive": "C"},
        action_result=None,
    )

    assert eval_res.is_vetoed_by_security
    assert eval_res.total_reward == -2.0


def test_oracle_redundancy_penalty():
    """Verifies that redundant actions repeating identical state receive penalty."""
    oracle = Win32ExecutionRewardOracle()

    act_res = ActionResult(
        action_name="system_volume",
        status=ActionStatus.SUCCESS,
        code="VOLUME_SET_OK",
        message="Volume already at 80",
        data={"level": 80},
    )

    eval_res = oracle.evaluate(
        action_name="system_volume",
        parameters={"level": 80},
        action_result=act_res,
        is_state_identical_to_prior=True,
    )

    assert eval_res.redundancy_penalty == 1.0
    # Reward should be discounted by redundancy weight
    assert eval_res.total_reward < 1.0
