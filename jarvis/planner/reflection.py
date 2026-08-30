"""
Self-Reflection and Self-Healing Engine for the JARVIS ReAct Planner subsystem.
Provides root-cause diagnosis, strategy matrix evaluation (RETRY, ALTERNATIVE_TOOL, REPLAN, ABORT),
exponential backoff calculation, and dynamic graph repair.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from jarvis.planner.dag import TaskDAG
from jarvis.planner.models import RecoveryStrategy, ReflectionResult, StepStatus, TaskNode

logger = logging.getLogger("jarvis.planner.reflection")


class SelfReflectionEngine:
    """
    Analyzes execution failures and formulates self-healing recovery strategies.
    Employs deterministic heuristic triage with optional LLM reasoning fallback.
    """

    DEFAULT_TOOL_FALLBACKS: dict[str, str] = {
        "browser_scrape": "web_search_direct",
        "playwright_navigate": "http_fetch",
        "web_crawler": "web_search_direct",
        "shell_exec": "python_sandbox_exec",
        "powershell_script": "python_sandbox_exec",
        "gui_click": "keyboard_shortcut",
        "gui_type": "clipboard_paste",
        "excel_vba": "python_pandas_process",
    }

    def __init__(
        self,
        llm_client: Any | None = None,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        tool_fallbacks: dict[str, str] | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.base_backoff_seconds = float(base_backoff_seconds)
        self.max_backoff_seconds = float(max_backoff_seconds)
        self.tool_fallbacks = dict(self.DEFAULT_TOOL_FALLBACKS)
        if tool_fallbacks:
            self.tool_fallbacks.update(tool_fallbacks)

    def calculate_backoff(self, retry_count: int) -> float:
        """Computes exponential backoff with a cap: base * 2^(retry_count)."""
        backoff = self.base_backoff_seconds * (2 ** max(0, retry_count))
        return min(self.max_backoff_seconds, backoff)

    def reflect(
        self,
        node: TaskNode,
        error: str | Exception,
        dag: TaskDAG | None = None,
        context: dict[str, Any] | None = None,
    ) -> ReflectionResult:
        """
        Main reflection entrypoint. Analyzes step failure and determines recovery plan.
        
        Args:
            node: Failed TaskNode.
            error: Error message string or Exception instance.
            dag: Optional TaskDAG for graph context.
            context: Optional runtime context dictionary.
            
        Returns:
            ReflectionResult with recommended strategy and proposed modifications.
        """
        err_msg = str(error) if error is not None else "Unknown execution failure"
        err_lower = err_msg.lower()

        logger.info(
            "Initiating self-reflection for node '%s' (action='%s', retry=%d/%d). Error: %s",
            node.step_id, node.action_name, node.retry_count, node.max_retries, err_msg
        )

        # 1. Check Max Retries Exhaustion
        if node.retry_count >= node.max_retries:
            # Check if an alternative tool is available before completely aborting
            alt_tool = self.tool_fallbacks.get(node.action_name)
            if alt_tool and alt_tool != node.action_name:
                return ReflectionResult(
                    step_id=node.step_id,
                    strategy=RecoveryStrategy.ALTERNATIVE_TOOL,
                    diagnosis=f"Tác vụ '{node.action_name}' đã hết số lần thử lại ({node.max_retries}). Chuyển sang công cụ dự phòng '{alt_tool}'.",
                    suggested_action=alt_tool,
                    suggested_parameters=dict(node.parameters),
                    reasoning=f"Primary tool exhausted max retries; falling back to {alt_tool}.",
                    backoff_seconds=0.5,
                )

            return ReflectionResult(
                step_id=node.step_id,
                strategy=RecoveryStrategy.ABORT,
                diagnosis=f"Tác vụ '{node.action_name}' thất bại sau {node.max_retries} lần thử lại: {err_msg}",
                reasoning="Exceeded maximum retries with no viable alternative tools.",
            )

        # 2. Try LLM Reflection if configured and available
        if self.llm_client and hasattr(self.llm_client, "generate_reflection"):
            try:
                llm_res = self._llm_reflect(node, err_msg, dag, context)
                if llm_res:
                    return llm_res
            except Exception as exc:
                logger.warning("LLM reflection failed, using deterministic heuristics: %s", exc)

        # 3. Deterministic Heuristic Triage
        return self._heuristic_reflect(node, err_msg)

    def _heuristic_reflect(self, node: TaskNode, err_msg: str) -> ReflectionResult:
        """Rule-based heuristic failure classifier and strategy selector."""
        err_lower = err_msg.lower()
        backoff = self.calculate_backoff(node.retry_count)

        # Case A: Timeouts & Transient Network Errors -> RETRY with backoff and increased timeout
        timeout_indicators = ("timeout", "timed out", "timeoutexpired", "deadline exceeded", "connection reset")
        if any(ind in err_lower for ind in timeout_indicators):
            new_params = dict(node.parameters)
            if "timeout" in new_params and isinstance(new_params["timeout"], (int, float)):
                new_params["timeout"] = float(new_params["timeout"]) * 1.5
            elif "timeout_seconds" in new_params and isinstance(new_params["timeout_seconds"], (int, float)):
                new_params["timeout_seconds"] = float(new_params["timeout_seconds"]) * 1.5

            return ReflectionResult(
                step_id=node.step_id,
                strategy=RecoveryStrategy.RETRY,
                diagnosis=f"Lỗi quá thời gian chờ (Timeout) khi thực thi '{node.action_name}'. Thử lại với thời gian gia hạn.",
                suggested_parameters=new_params,
                reasoning="Transient timeout detected. Retrying with exponential backoff and increased timeout parameter.",
                backoff_seconds=backoff,
            )

        # Case B: Rate Limiting (HTTP 429 / Too Many Requests) -> RETRY with larger backoff
        if "429" in err_lower or "rate limit" in err_lower or "too many requests" in err_lower:
            return ReflectionResult(
                step_id=node.step_id,
                strategy=RecoveryStrategy.RETRY,
                diagnosis=f"Bị giới hạn tần suất gọi API (Rate Limit 429) tại bước '{node.action_name}'.",
                reasoning="Rate limit encountered. Enforcing exponential cooldown before retry.",
                backoff_seconds=max(backoff * 2.0, 3.0),
            )

        # Case C: Tool / Action Not Found or Blocked -> ALTERNATIVE_TOOL
        not_found_indicators = (
            "action_not_found", "not registered", "unsupported action",
            "cloudflare", "captcha", "access denied", "blocked by cloudflare"
        )
        if any(ind in err_lower for ind in not_found_indicators):
            alt_tool = self.tool_fallbacks.get(node.action_name)
            if alt_tool:
                adapted_params = dict(node.parameters)
                if alt_tool in ("web_search_direct", "web_search", "web_search_fallback"):
                    if "url" in adapted_params and "query" not in adapted_params:
                        adapted_params["query"] = adapted_params.pop("url")
                return ReflectionResult(
                    step_id=node.step_id,
                    strategy=RecoveryStrategy.ALTERNATIVE_TOOL,
                    diagnosis=f"Công cụ '{node.action_name}' không khả dụng hoặc bị chặn. Tự động đổi sang '{alt_tool}'.",
                    suggested_action=alt_tool,
                    suggested_parameters=adapted_params,
                    reasoning=f"Tool unavailable or blocked. Switching to registered fallback '{alt_tool}'.",
                    backoff_seconds=0.5,
                )

        # Case D: Permission Denied or Explicit Safety Rejection/Expiry -> ABORT
        # ("safety_gate_" covers both "safety_gate_rejected" and
        # "safety_gate_expired"; "confirmation"/"xác nhận" cover
        # ActionDispatcher-level CONFIRMATION_* refusals -- see
        # jarvis/core/dispatcher.py's _evaluate_safety_gate().)
        if (
            "permission_denied" in err_lower
            or "safety_gate_" in err_lower
            or "user_cancelled" in err_lower
            or "confirmation" in err_lower
            or "xác nhận" in err_lower
        ):
            return ReflectionResult(
                step_id=node.step_id,
                strategy=RecoveryStrategy.ABORT,
                diagnosis=f"Hành động '{node.action_name}' bị từ chối quyền truy cập hoặc bị người dùng hủy bỏ.",
                reasoning="Explicit permission refusal or user cancellation.",
            )

        # Case E: Generic Exception -> RETRY
        return ReflectionResult(
            step_id=node.step_id,
            strategy=RecoveryStrategy.RETRY,
            diagnosis=f"Gặp lỗi ngoại lệ trong quá trình chạy '{node.action_name}': {err_msg}. Đang tự động thử lại.",
            suggested_parameters=dict(node.parameters),
            reasoning="Generic recoverable failure. Retrying step.",
            backoff_seconds=backoff,
        )

    def _llm_reflect(
        self,
        node: TaskNode,
        err_msg: str,
        dag: TaskDAG | None,
        context: dict[str, Any] | None,
    ) -> ReflectionResult | None:
        """Queries LLM for intelligent failure reasoning and recovery proposal."""
        prompt = (
            f"You are the JARVIS Autonomous ReAct Reflection Agent.\n"
            f"Step ID: {node.step_id}\n"
            f"Action: {node.action_name}\n"
            f"Description: {node.description}\n"
            f"Parameters: {json.dumps(node.parameters, default=str)}\n"
            f"Retry Count: {node.retry_count}/{node.max_retries}\n"
            f"Error Message: {err_msg}\n\n"
            f"Respond with a JSON object containing:\n"
            f'{{"strategy": "retry"|"alternative_tool"|"replan"|"abort", '
            f'"diagnosis": "short Vietnamese explanation", '
            f'"suggested_action": "action_name or null", '
            f'"suggested_parameters": {{...}} or null, '
            f'"reasoning": "English explanation"}}\n'
        )

        assert self.llm_client is not None
        resp = self.llm_client.generate_reflection(prompt)
        if isinstance(resp, str):
            # Parse JSON from markdown code block or direct text
            match = re.search(r"\{.*\}", resp, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                return None
        elif isinstance(resp, dict):
            data = resp
        else:
            return None

        strat_str = data.get("strategy", "retry").lower()
        strategy = RecoveryStrategy.RETRY
        for s in RecoveryStrategy:
            if s.value == strat_str:
                strategy = s
                break

        return ReflectionResult(
            step_id=node.step_id,
            strategy=strategy,
            diagnosis=data.get("diagnosis", err_msg),
            suggested_action=data.get("suggested_action"),
            suggested_parameters=data.get("suggested_parameters"),
            reasoning=data.get("reasoning", ""),
            backoff_seconds=self.calculate_backoff(node.retry_count),
        )

    def apply_reflection(
        self,
        reflection: ReflectionResult,
        node: TaskNode,
        dag: TaskDAG,
    ) -> bool:
        """
        Applies the formulated reflection strategy to the TaskNode and TaskDAG.
        
        Returns:
            True if execution of the DAG can continue, False if aborted.
        """
        logger.info(
            "Applying recovery strategy '%s' to node '%s'",
            reflection.strategy.value, node.step_id
        )

        if reflection.strategy == RecoveryStrategy.RETRY:
            node.retry_count += 1
            if reflection.suggested_parameters:
                node.parameters.update(reflection.suggested_parameters)
            node.status = StepStatus.RETRYING
            node.error_message = None
            if reflection.backoff_seconds > 0:
                time.sleep(min(reflection.backoff_seconds, 5.0))  # Cap sleep in tests
            return True

        elif reflection.strategy == RecoveryStrategy.ALTERNATIVE_TOOL:
            node.retry_count = 0  # Reset retry budget for new tool
            if reflection.suggested_action:
                node.action_name = reflection.suggested_action
            if reflection.suggested_parameters:
                node.parameters = dict(reflection.suggested_parameters)
            node.status = StepStatus.READY
            node.error_message = None
            return True

        elif reflection.strategy == RecoveryStrategy.REPLAN:
            if reflection.new_subgraph_nodes:
                for new_node in reflection.new_subgraph_nodes:
                    if new_node.step_id not in dag.nodes:
                        dag.add_node(new_node)
            node.status = StepStatus.SKIPPED
            return True

        elif reflection.strategy == RecoveryStrategy.ABORT:
            node.status = StepStatus.FAILED
            node.error_message = reflection.diagnosis
            # Mark all downstream dependents as BLOCKED
            downstream = dag.get_downstream_nodes(node.step_id)
            for d in downstream:
                if d.status in (StepStatus.PENDING, StepStatus.READY):
                    d.status = StepStatus.BLOCKED
                    d.error_message = f"Blocked due to prerequisite failure in step '{node.step_id}'."
            return False

        return False
