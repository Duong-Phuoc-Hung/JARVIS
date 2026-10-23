"""
jarvis/nlp/multi_intent.py
==========================
Compound Multi-Intent Decomposer and Sequential Execution Pipeline.
Enables parsing and executing compound natural language commands in Vietnamese.
Handles:
  - Clause splitting across conjunctions ('và', 'đồng thời', 'sau đó', 'rồi', ',').
  - Predicate ellipsis resolution (e.g. 'tắt đèn phòng khách và phòng ngủ').
  - Entity protection for search queries and quoted text.
  - Coordination and sequential execution across ActionDispatcher.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

from jarvis.llm.models import IntentResult

logger = logging.getLogger("jarvis.nlp.multi_intent")

# Explicit conjunction patterns sorted from longest/most specific to shortest
_STRONG_SEPARATORS = [
    re.compile(r"\s*(?:;\s*|\.\s+)\s*"),
    re.compile(r"\s+(?:sau đó|rồi sau đó|tiep theo|kế tiếp)\s+", re.IGNORECASE),
    re.compile(r"\s+(?:đồng thời|dong thoi|tiện thể|nhân tiện)\s+", re.IGNORECASE),
    re.compile(r"\s+(?:rồi|roi)\s+", re.IGNORECASE),
]

_WEAK_SEPARATORS = [
    re.compile(r"\s+(?:và|va)\s+", re.IGNORECASE),
    re.compile(r",\s*"),
]

# Vietnamese action verbs that indicate a standalone command clause
_ACTION_VERBS = [
    "bật", "bat", "tắt", "tat", "mở", "mo", "đóng", "dong", "thoát", "thoat",
    "tăng", "tang", "giảm", "giam", "chỉnh", "chinh", "vặn", "van", "cho",
    "phát", "phat", "dừng", "dung", "tạm dừng", "tam dung", "chuyển", "chuyen",
    "quay lại", "quay lai", "lùi", "lui", "kiểm tra", "kiem tra", "báo cáo", "bao cao",
    "đặt", "dat", "hẹn", "hen", "nhắc", "nhac", "tìm kiếm", "tim kiem", "tra cứu", "tra cuu",
    "khởi động", "khoi dong", "chạy", "chay", "thu nhỏ", "thu nho", "phóng to", "phong to",
    "sao chép", "sao chep", "copy", "dán", "dan", "paste", "xóa", "xoa", "dọn dẹp", "don dep",
]

# Patterns where conjunctions should NOT be split (Entity Protection)
_SEARCH_PREFIXES = (
    "tìm kiếm", "tim kiem", "tra cứu", "tra cuu", "tìm trên mạng", "tim tren mang",
    "tra google", "tìm", "tim", "google",
)


def _starts_with_action_verb(clause: str) -> bool:
    """Checks if a clause starts with an actionable command verb."""
    cleaned = clause.strip().lower()
    for verb in _ACTION_VERBS:
        if cleaned == verb or cleaned.startswith(f"{verb} "):
            return True
    return False


def _extract_predicate_phrase(clause: str) -> str:
    """
    Extracts the action verb + entity category (e.g. 'tắt đèn', 'mở', 'bật quạt')
    from the beginning of a clause to resolve predicate ellipsis.
    """
    words = clause.strip().split()
    if not words:
        return ""
    # Check 2-word verb phrases first (e.g. 'tắt đèn', 'bật quạt', 'vặn to')
    if len(words) >= 2:
        two_words = f"{words[0]} {words[1]}".lower()
        if any(two_words.startswith(v) for v in ["tắt đèn", "bật đèn", "bật quạt", "tắt quạt", "bật điều hòa", "tắt điều hòa", "mở ứng dụng", "đóng ứng dụng", "tăng âm", "giảm âm"]):
            return f"{words[0]} {words[1]}"
    # Fallback to single verb
    for verb in _ACTION_VERBS:
        if words[0].lower() == verb:
            return words[0]
    return ""


def split_compound_utterance(raw_text: str) -> list[str]:
    """
    Splits a compound Vietnamese natural language utterance into individual command clauses.
    Applies entity protection and predicate ellipsis resolution.

    Args:
        raw_text: Raw input utterance string.

    Returns:
        List of individual actionable command strings.
    """
    text = raw_text.strip()
    if not text:
        return []

    text_lower = text.lower()

    # Entity protection: If the command is a web search query without strong sequential markers,
    # do not split on 'và' or commas (e.g. 'tìm kiếm tom và jerry').
    is_search = any(text_lower.startswith(p) for p in _SEARCH_PREFIXES)
    has_strong_sep = any(sep.search(text) for sep in _STRONG_SEPARATORS)

    if is_search and not has_strong_sep:
        return [text]

    # Step 1: Split by strong separators first
    clauses: list[str] = [text]
    for sep in _STRONG_SEPARATORS:
        new_clauses: list[str] = []
        for c in clauses:
            parts = [p.strip() for p in sep.split(c) if p.strip()]
            new_clauses.extend(parts if parts else [c])
        clauses = new_clauses

    # Step 2: Split by weak separators ('và', ',') if the right side is an action or elided target
    final_clauses: list[str] = []
    for c in clauses:
        sub_parts: list[str] = [c]
        for weak_sep in _WEAK_SEPARATORS:
            splitted: list[str] = []
            for sp in sub_parts:
                tokens = [t.strip() for t in weak_sep.split(sp) if t.strip()]
                if len(tokens) <= 1:
                    splitted.append(sp)
                    continue

                # Verify each split
                valid_split = True
                curr_assembled: list[str] = []
                left_clause = tokens[0]
                curr_assembled.append(left_clause)

                for next_clause in tokens[1:]:
                    # Case A: next clause has its own action verb -> valid split
                    if _starts_with_action_verb(next_clause):
                        curr_assembled.append(next_clause)
                    else:
                        # Case B: next clause does not have an action verb
                        # Check predicate ellipsis (e.g. 'tắt đèn phòng khách' + 'phòng ngủ')
                        pred = _extract_predicate_phrase(curr_assembled[-1])
                        if pred and len(next_clause.split()) <= 4:
                            # Inherit predicate!
                            restored = f"{pred} {next_clause}"
                            curr_assembled.append(restored)
                        else:
                            # Not an actionable split (e.g. "tom và jerry"), merge back
                            valid_split = False
                            break

                if valid_split:
                    splitted.extend(curr_assembled)
                else:
                    splitted.append(sp)
            sub_parts = splitted
        final_clauses.extend(sub_parts)

    return [cl.strip() for cl in final_clauses if cl.strip()]


class CompoundIntentDecomposer:
    """
    Decomposes multi-intent utterances into sequential IntentResults and coordinates execution.
    """

    def __init__(self, router_instance: Any = None) -> None:
        self.router = router_instance

    def decompose(self, text: str) -> list[str]:
        """Splits raw text into command clauses."""
        return split_compound_utterance(text)

    def resolve(self, text: str, router_parser: Any) -> list[IntentResult]:
        """
        Parses all sub-intents in a compound command using the provided router parser.

        Args:
            text: Raw input text.
            router_parser: Callable that takes text and returns IntentResult.

        Returns:
            List of resolved IntentResults.
        """
        clauses = self.decompose(text)
        if not clauses:
            return []

        results: list[IntentResult] = []
        for clause in clauses:
            res = router_parser(clause)
            if res:
                results.append(res)
        return results

    def compile_dag(
        self,
        text: str,
        router_parser: Callable[[str], IntentResult | None],
    ) -> DeclarativeMacroDAG:
        """Compiles compound text into a DeclarativeMacroDAG pipeline with context inheritance."""
        return DeclarativeMacroDAG.compile(text, router_parser)

    def execute_dag(
        self,
        dag: DeclarativeMacroDAG,
        dispatcher: Any,
        requester: Any = "system",
    ) -> MacroDAGExecutionResult:
        """Executes a DeclarativeMacroDAG with transactional fail-closed semantics."""
        return dag.execute(dispatcher, requester=requester)


@dataclass
class MacroStep:
    """Represents a discrete step in a declarative macro DAG."""
    step_id: int
    clause: str
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    inherited_context: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # "pending", "running", "success", "failed", "aborted"
    result: Any | None = None
    error: str | None = None
    execution_time_ms: float = 0.0


@dataclass
class MacroDAGExecutionResult:
    """Outcome of a DeclarativeMacroDAG transactional execution."""
    success: bool
    total_steps: int
    executed_steps: int
    failed_step_id: int | None = None
    error: str | None = None
    step_results: list[Any] = field(default_factory=list)
    steps: list[MacroStep] = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_steps": self.total_steps,
            "executed_steps": self.executed_steps,
            "failed_step_id": self.failed_step_id,
            "error": self.error,
            "step_results": [
                r.to_dict() if hasattr(r, "to_dict") else str(r)
                for r in self.step_results
            ],
            "execution_time_ms": self.execution_time_ms,
        }


class DeclarativeMacroDAG:
    """
    Compound Declarative Macro Directed Acyclic Graph (Argon Sovereign Frontier 5).
    Provides:
      - Sequential declarative pipeline of decomposed command clauses.
      - Inter-step context and entity inheritance (e.g. active app, window handle).
      - Fail-closed transactional execution: if any step fails, abort remaining steps
        immediately and report exact error without side-effect runaway.
    """

    def __init__(self, steps: list[MacroStep] | None = None) -> None:
        self.steps: list[MacroStep] = steps or []

    @classmethod
    def compile(
        cls,
        raw_text: str,
        router_parser: Callable[[str], IntentResult | None],
    ) -> DeclarativeMacroDAG:
        """
        Decomposes compound text into clauses, resolves intents via router_parser,
        and links inter-step inherited context.
        """
        clauses = split_compound_utterance(raw_text)
        if not clauses:
            return cls([])

        steps: list[MacroStep] = []
        active_app: str | None = None
        active_hwnd: int | None = None

        for idx, clause in enumerate(clauses, start=1):
            intent = router_parser(clause)
            if intent is None:
                steps.append(MacroStep(
                    step_id=idx,
                    clause=clause,
                    action_name="unknown_intent",
                    parameters={"raw_text": clause},
                    status="pending",
                ))
                continue

            action_name = intent.action_name
            params = dict(intent.parameters)
            inherited: dict[str, Any] = {}

            # Context inheritance heuristics:
            # 1. Track app open or launch
            if action_name in ("app_open", "open_app", "app_launch"):
                app = params.get("app_name") or params.get("name") or params.get("app")
                if app:
                    active_app = str(app).strip()

            # 2. Inherit active app for window controls (maximize, minimize, close)
            if action_name in ("window_control", "app_close"):
                if active_app and not params.get("app_name") and not params.get("app"):
                    inherited["app_name"] = active_app
                    params["app_name"] = active_app
                if active_hwnd and not params.get("hwnd"):
                    inherited["hwnd"] = active_hwnd
                    params["hwnd"] = active_hwnd

            # 3. Inherit target for web search / browser operations if following app_open(browser)
            if action_name in ("web_search", "browser_open_url"):
                if active_app in ("chrome", "edge", "firefox", "browser") and not params.get("browser"):
                    inherited["browser"] = active_app
                    params["browser"] = active_app

            steps.append(MacroStep(
                step_id=idx,
                clause=clause,
                action_name=action_name,
                parameters=params,
                inherited_context=inherited,
                status="pending",
            ))

        return cls(steps=steps)

    def execute(
        self,
        dispatcher: Any,
        requester: Any = "system",
    ) -> MacroDAGExecutionResult:
        """
        Executes DAG steps sequentially with strict fail-closed transactional semantics.
        If any step fails, halts execution immediately and marks remaining steps as aborted.
        """
        import time
        t0 = time.perf_counter()
        step_results: list[Any] = []
        accumulated_context: dict[str, Any] = {}

        for step in self.steps:
            # Inject dynamically accumulated context from earlier steps if missing
            for k, v in accumulated_context.items():
                if k not in step.parameters:
                    step.parameters[k] = v
                    step.inherited_context[k] = v

            step_t0 = time.perf_counter()
            step.status = "running"
            try:
                result = dispatcher.dispatch_action(
                    action_name=step.action_name,
                    payload=step.parameters,
                    requester=requester,
                )
            except Exception as exc:
                step.execution_time_ms = (time.perf_counter() - step_t0) * 1000.0
                step.status = "failed"
                step.error = f"Exception in step {step.step_id} ('{step.action_name}'): {exc}"
                self._abort_subsequent_steps(step.step_id)
                dur = (time.perf_counter() - t0) * 1000.0
                return MacroDAGExecutionResult(
                    success=False,
                    total_steps=len(self.steps),
                    executed_steps=step.step_id,
                    failed_step_id=step.step_id,
                    error=step.error,
                    step_results=step_results,
                    steps=self.steps,
                    execution_time_ms=dur,
                )

            step.execution_time_ms = (time.perf_counter() - step_t0) * 1000.0
            step.result = result
            step_results.append(result)

            if not getattr(result, "success", False):
                step.status = "failed"
                step.error = getattr(result, "error", f"Action {step.action_name} failed")
                self._abort_subsequent_steps(step.step_id)
                dur = (time.perf_counter() - t0) * 1000.0
                return MacroDAGExecutionResult(
                    success=False,
                    total_steps=len(self.steps),
                    executed_steps=step.step_id,
                    failed_step_id=step.step_id,
                    error=f"Step {step.step_id} ('{step.action_name}') failed: {step.error}",
                    step_results=step_results,
                    steps=self.steps,
                    execution_time_ms=dur,
                )

            step.status = "success"

            # Extract any runtime handles (e.g. hwnd, process_id) to pass to next steps
            if hasattr(result, "data") and isinstance(result.data, dict):
                if "hwnd" in result.data:
                    accumulated_context["hwnd"] = result.data["hwnd"]
                if "app_name" in result.data:
                    accumulated_context["app_name"] = result.data["app_name"]

        dur = (time.perf_counter() - t0) * 1000.0
        return MacroDAGExecutionResult(
            success=True,
            total_steps=len(self.steps),
            executed_steps=len(self.steps),
            failed_step_id=None,
            error=None,
            step_results=step_results,
            steps=self.steps,
            execution_time_ms=dur,
        )

    def _abort_subsequent_steps(self, failed_step_id: int) -> None:
        """Marks all steps after failed_step_id as aborted."""
        for rem in self.steps:
            if rem.step_id > failed_step_id:
                rem.status = "aborted"
                rem.error = f"Aborted due to failure in preceding step {failed_step_id}"


__all__ = [
    "split_compound_utterance",
    "CompoundIntentDecomposer",
    "DeclarativeMacroDAG",
    "MacroStep",
    "MacroDAGExecutionResult",
]

