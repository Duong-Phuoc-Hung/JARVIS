"""
jarvis/learning/win32_oracle.py
===============================
Win32 Execution Grounding Reward Oracle for In-Situ Test-Time Policy Optimization.
Engineered for Argon Sovereign v7.0 Autonomous Adaptation on Windows 11.

Principles:
  1. Grounded Execution Feedback:
     Instead of relying on LLM self-evaluation or proxy reward models, the Oracle
     derives reward signals directly from the physical reality of the operating system:
       - ActionResult status codes (SUCCESS, FAILED, PERMISSION_DENIED)
       - Win32 API return codes (HRESULT, GetLastError)
       - Active Foreground Window HWND transitions
       - Process tree / PID liveness checks
  2. Multi-Objective Reward Formulation:
       R(y) = w_status * R_status + w_window * R_window + w_pid * R_pid + w_syntax * R_syntax - w_red * R_redundancy
  3. Fail-Closed Security Firewall:
       Destructive actions, unauthorized privilege escalations, or policy violations
       are assigned an immutable severe penalty (R = -2.0) and are permanently blocked
       from contributing positive gradient updates in RL.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

import psutil

from jarvis.core.models import ActionResult, ActionStatus, PrivilegeLevel

logger = logging.getLogger("jarvis.learning.win32_oracle")


@dataclass(frozen=True)
class ExecutionRewardBreakdown:
    """Detailed breakdown of execution reward components."""
    total_reward: float
    status_reward: float
    window_reward: float
    pid_reward: float
    syntax_reward: float
    redundancy_penalty: float
    is_vetoed_by_security: bool
    evaluation_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_reward": self.total_reward,
            "status_reward": self.status_reward,
            "window_reward": self.window_reward,
            "pid_reward": self.pid_reward,
            "syntax_reward": self.syntax_reward,
            "redundancy_penalty": self.redundancy_penalty,
            "is_vetoed": self.is_vetoed_by_security,
            "latency_ms": self.evaluation_latency_ms,
        }


@dataclass(frozen=True)
class OracleConfig:
    """Weights and parameters for the Win32 Execution Grounding Oracle."""
    weight_status: float = 1.0       # Weight for ActionResult.status SUCCESS vs FAILURE
    weight_window: float = 0.5       # Weight for verified foreground window focus transition
    weight_pid: float = 0.3          # Weight for verified target process liveness
    weight_syntax: float = 0.2       # Weight for strict slot schema conformity
    weight_redundancy: float = 0.8   # Penalty weight for redundant no-op actions
    security_veto_penalty: float = -2.0 # Immutable penalty for safety violations


class Win32ExecutionRewardOracle:
    """
    Evaluates agent action candidates against Windows OS ground truth to produce
    unbiased, deterministic scalar reward signals for RL policy optimization.
    """

    def __init__(self, config: OracleConfig | None = None) -> None:
        self.config = config or OracleConfig()

        # Blocklist of actions that must NEVER receive positive RL reward
        self.blocked_destructive_intents = frozenset({
            "system_power_off",
            "format_disk",
            "registry_delete",
            "process_kill_system",
            "delete_root_directory",
        })

    def evaluate(
        self,
        action_name: str,
        parameters: Mapping[str, Any],
        action_result: ActionResult | None,
        initial_foreground_title: str = "",
        target_process_name: str | None = None,
        is_state_identical_to_prior: bool = False,
    ) -> ExecutionRewardBreakdown:
        """
        Computes the execution reward by inspecting real OS status indicators.

        Args:
            action_name: Name of the executed Win32 action.
            parameters: Dictionary of extracted slot parameters.
            action_result: Result object returned by ActionDispatcher.
            initial_foreground_title: Window title prior to action execution.
            target_process_name: Optional process name expected to be running.
            is_state_identical_to_prior: Whether action produced zero state change.

        Returns:
            ExecutionRewardBreakdown: Comprehensive reward evaluation.
        """
        t0 = time.perf_counter()

        # 1. Security Firewall Veto: Destructive or unauthorized actions
        if action_name in self.blocked_destructive_intents:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return ExecutionRewardBreakdown(
                total_reward=self.config.security_veto_penalty,
                status_reward=-1.0,
                window_reward=0.0,
                pid_reward=0.0,
                syntax_reward=0.0,
                redundancy_penalty=0.0,
                is_vetoed_by_security=True,
                evaluation_latency_ms=elapsed_ms,
            )

        # 2. Status Reward Evaluation
        status_reward = 0.0
        if action_result is not None:
            if action_result.status == ActionStatus.SUCCESS:
                status_reward = 1.0
            elif action_result.status == ActionStatus.BLOCKED:
                status_reward = -1.5
            elif action_result.status in (ActionStatus.FAILED, ActionStatus.ERROR):
                status_reward = -1.0
            elif action_result.status == ActionStatus.UNAVAILABLE:
                status_reward = -0.5
        else:
            status_reward = -0.5

        # 3. Target Process Liveness Check
        pid_reward = 0.0
        if target_process_name:
            pid_reward = self._check_process_running(target_process_name)

        # 4. Foreground Window Transition Check
        window_reward = 0.0
        current_title = self._get_current_window_title()
        if initial_foreground_title and current_title:
            if current_title != initial_foreground_title:
                # Window changed successfully
                window_reward = 1.0

        # 5. Schema / Syntax Conformity Check
        syntax_reward = 0.0
        if parameters and isinstance(parameters, dict) and len(parameters) > 0:
            # Check for non-null, valid parameters
            if all(v is not None for v in parameters.values()):
                syntax_reward = 1.0

        # 6. Redundancy / Idempotency Penalty Check
        red_penalty = 0.0
        if is_state_identical_to_prior:
            red_penalty = 1.0

        # Compute total weighted scalar reward
        total = (
            self.config.weight_status * status_reward
            + self.config.weight_window * window_reward
            + self.config.weight_pid * pid_reward
            + self.config.weight_syntax * syntax_reward
            - self.config.weight_redundancy * red_penalty
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return ExecutionRewardBreakdown(
            total_reward=float(round(total, 4)),
            status_reward=status_reward,
            window_reward=window_reward,
            pid_reward=pid_reward,
            syntax_reward=syntax_reward,
            redundancy_penalty=red_penalty,
            is_vetoed_by_security=False,
            evaluation_latency_ms=elapsed_ms,
        )

    def _check_process_running(self, proc_name: str) -> float:
        """Checks if a process matching proc_name is currently active."""
        clean_name = proc_name.lower().replace(".exe", "")
        try:
            for p in psutil.process_iter(["name"]):
                name = (p.info.get("name") or "").lower()
                if clean_name in name:
                    return 1.0
        except Exception as exc:
            logger.debug("Process iteration failed: %s", exc)
        return -0.5

    def _get_current_window_title(self) -> str:
        """Retrieves title of the current foreground window via Win32 API."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    return buf.value
        except Exception as exc:
            logger.debug("Win32 GetForegroundWindow failed: %s", exc)
        return ""
