"""
tests/unit/test_macro_dag.py
============================
Unit & Safety Verification for Compound Declarative Macro DAG Pipeline (Argon Sovereign Frontier 5).
Validates:
  - Clause splitting across Vietnamese sequential conjunctions ('sau đó', 'rồi', 'tiếp theo').
  - Compilation of compound utterance into DeclarativeMacroDAG.
  - Inter-step context inheritance (e.g. step 1 'mở chrome' -> step 2 inherits browser='chrome',
    step 3 'phóng to toàn màn hình' inherits app_name='chrome').
  - Fail-closed transactional execution semantics: if step 2 fails, step 3 is aborted immediately
    and exact error reported without side-effect runaway.
  - Happy-path complete sequential execution.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
import pytest

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, ActionStatus, PrivilegeLevel, RequesterContext
from jarvis.llm.models import IntentResult
from jarvis.nlp.multi_intent import (
    CompoundIntentDecomposer,
    DeclarativeMacroDAG,
    MacroDAGExecutionResult,
    MacroStep,
    split_compound_utterance,
)


def mock_router_parser(clause: str) -> IntentResult:
    """Mock parser mapping clauses to typed IntentResults for DAG compilation."""
    c = clause.strip().lower()
    if "mở chrome" in c or "mo chrome" in c:
        return IntentResult(
            action_name="app_open",
            parameters={"app_name": "chrome", "installed_only": True},
            confidence=0.95,
            source="mock_router",
            raw_text=clause,
        )
    elif "tìm kiếm" in c or "tim kiem" in c:
        # Extract query after 'tìm kiếm'
        query = clause.split("tìm kiếm", 1)[-1].strip() if "tìm kiếm" in clause else "Độ Mixi"
        return IntentResult(
            action_name="web_search",
            parameters={"query": query},
            confidence=0.95,
            source="mock_router",
            raw_text=clause,
        )
    elif "phóng to" in c or "toàn màn hình" in c:
        return IntentResult(
            action_name="window_control",
            parameters={"action": "maximize"},
            confidence=0.90,
            source="mock_router",
            raw_text=clause,
        )
    elif "đóng" in c:
        return IntentResult(
            action_name="app_close",
            parameters={},
            confidence=0.90,
            source="mock_router",
            raw_text=clause,
        )
    return IntentResult(
        action_name="unknown_intent",
        parameters={"raw_text": clause},
        confidence=0.0,
        source="mock_router",
        raw_text=clause,
    )


class TestDeclarativeMacroDAG:
    """Direct unit tests for DeclarativeMacroDAG pipeline and context inheritance."""

    def test_clause_decomposition_sequential(self) -> None:
        """Verifies splitting across Vietnamese sequence conjunctions."""
        text = "mở chrome sau đó tìm kiếm Độ Mixi rồi phóng to toàn màn hình"
        clauses = split_compound_utterance(text)
        assert len(clauses) == 3
        assert clauses[0] == "mở chrome"
        assert clauses[1] == "tìm kiếm Độ Mixi"
        assert clauses[2] == "phóng to toàn màn hình"

    def test_compile_dag_inter_step_context_inheritance(self) -> None:
        """Step 2 and Step 3 inherit application context from Step 1."""
        text = "mở chrome sau đó tìm kiếm Độ Mixi rồi phóng to toàn màn hình"
        dag = DeclarativeMacroDAG.compile(text, router_parser=mock_router_parser)
        assert len(dag.steps) == 3

        # Step 1: Open Chrome
        step1 = dag.steps[0]
        assert step1.action_name == "app_open"
        assert step1.parameters.get("app_name") == "chrome"

        # Step 2: Search -> inherits browser='chrome'
        step2 = dag.steps[1]
        assert step2.action_name == "web_search"
        assert step2.parameters.get("query") == "Độ Mixi"
        assert step2.inherited_context.get("browser") == "chrome"

        # Step 3: Maximize window -> inherits app_name='chrome'
        step3 = dag.steps[2]
        assert step3.action_name == "window_control"
        assert step3.parameters.get("action") == "maximize"
        assert step3.inherited_context.get("app_name") == "chrome"

    def test_dag_execution_happy_path(self) -> None:
        """Executes full 3-step DAG sequentially with 100% success."""
        dispatcher = ActionDispatcher()
        execution_trace = []

        def handle_app_open(**kwargs):
            app = kwargs.get("app_name")
            execution_trace.append(f"open:{app}")
            return ActionResult(action_name="app_open", success=True, data={"hwnd": 12345, "app_name": app})

        def handle_search(**kwargs):
            q = kwargs.get("query")
            b = kwargs.get("browser")
            execution_trace.append(f"search:{q}:{b}")
            return ActionResult(action_name="web_search", success=True, data={"query": q})

        def handle_window(**kwargs):
            act = kwargs.get("action")
            app = kwargs.get("app_name")
            hwnd = kwargs.get("hwnd")
            execution_trace.append(f"window:{act}:{app}:{hwnd}")
            return ActionResult(action_name="window_control", success=True)

        dispatcher.register_action("app_open", handle_app_open)
        dispatcher.register_action("web_search", handle_search)
        dispatcher.register_action("window_control", handle_window)

        text = "mở chrome sau đó tìm kiếm Độ Mixi rồi phóng to toàn màn hình"
        dag = DeclarativeMacroDAG.compile(text, router_parser=mock_router_parser)
        res = dag.execute(dispatcher=dispatcher)

        assert res.success is True
        assert res.total_steps == 3
        assert res.executed_steps == 3
        assert res.failed_step_id is None
        assert len(execution_trace) == 3
        assert execution_trace[0] == "open:chrome"
        assert execution_trace[1] == "search:Độ Mixi:chrome"
        # Window control received hwnd dynamically propagated from step 1!
        assert execution_trace[2] == "window:maximize:chrome:12345"

    def test_dag_fail_closed_transactional_semantics(self) -> None:
        """When step 2 fails, execution halts immediately and step 3 is aborted."""
        dispatcher = ActionDispatcher()
        executed_steps = []

        def handle_app_open(**kwargs):
            executed_steps.append(1)
            return ActionResult(action_name="app_open", success=True, data={"hwnd": 999})

        def handle_search_failure(**kwargs):
            executed_steps.append(2)
            return ActionResult(
                action_name="web_search",
                success=False,
                error="Network unreachable (DNS resolution failure)",
                error_code="NETWORK_OFFLINE",
            )

        def handle_window(**kwargs):
            executed_steps.append(3)
            return ActionResult(action_name="window_control", success=True)

        dispatcher.register_action("app_open", handle_app_open)
        dispatcher.register_action("web_search", handle_search_failure)
        dispatcher.register_action("window_control", handle_window)

        text = "mở chrome sau đó tìm kiếm Độ Mixi rồi phóng to toàn màn hình"
        dag = DeclarativeMacroDAG.compile(text, router_parser=mock_router_parser)
        res = dag.execute(dispatcher=dispatcher)

        assert res.success is False
        assert res.failed_step_id == 2
        assert "NETWORK_OFFLINE" in str(res.error) or "Network unreachable" in str(res.error)
        assert res.executed_steps == 2
        # Step 3 must NOT run!
        assert 3 not in executed_steps
        assert dag.steps[2].status == "aborted"
        assert "failure in preceding step 2" in str(dag.steps[2].error)

    def test_compound_intent_decomposer_compile_and_execute(self) -> None:
        """CompoundIntentDecomposer helper methods integration."""
        decomposer = CompoundIntentDecomposer()
        dag = decomposer.compile_dag("mở chrome rồi đóng lại", router_parser=mock_router_parser)
        assert len(dag.steps) == 2
        assert dag.steps[1].inherited_context.get("app_name") == "chrome"

    def test_context_inheritance_replaces_placeholder_current(self) -> None:
        """When sub-intent has app_name='current', it is correctly overwritten by preceding app."""
        def mock_parser_with_placeholder(clause: str) -> IntentResult:
            if "mở notepad" in clause:
                return IntentResult(
                    action_name="app_open",
                    parameters={"app_name": "notepad"},
                    raw_text=clause,
                )
            if "đóng nó" in clause:
                return IntentResult(
                    action_name="app_close",
                    parameters={"app_name": "current", "target": "current"},
                    raw_text=clause,
                )
            return IntentResult(action_name="unknown", parameters={})

        text = "mở notepad sau đó đóng nó"
        dag = DeclarativeMacroDAG.compile(text, router_parser=mock_parser_with_placeholder)
        assert len(dag.steps) == 2
        assert dag.steps[0].parameters.get("app_name") == "notepad"
        # Step 2 placeholder 'current' replaced by 'notepad'
        assert dag.steps[1].parameters.get("app_name") == "notepad"
        assert dag.steps[1].inherited_context.get("app_name") == "notepad"

    def test_router_execute_intent_with_typed_intent_objects(self) -> None:
        """LLMIntentRouter.execute_intent supports list of IntentResult objects in actions parameter."""
        dispatcher = ActionDispatcher()
        calls = []

        def handle_action_1(**kwargs):
            calls.append(1)
            return ActionResult(action_name="app_open", success=True, data={"hwnd": 111, "app_name": "calc"})

        def handle_action_2(**kwargs):
            calls.append(kwargs.get("app_name"))
            return ActionResult(action_name="window_control", success=True)

        dispatcher.register_action("app_open", handle_action_1)
        dispatcher.register_action("window_control", handle_action_2)

        from jarvis.llm.client import LLMClient
        mock_llm = MagicMock(spec=LLMClient)
        from jarvis.llm.router import LLMIntentRouter
        router = LLMIntentRouter(llm_client=mock_llm, dispatcher=dispatcher)

        # Compound intent containing typed IntentResult items instead of raw dicts
        compound = IntentResult(
            action_name="compound_multi_action",
            parameters={
                "actions": [
                    IntentResult(action_name="app_open", parameters={"app_name": "calc"}),
                    IntentResult(action_name="window_control", parameters={"action": "maximize"}),
                ]
            },
        )
        res = router.execute_intent(compound)
        assert res.success is True
        assert calls == [1, "calc"]
