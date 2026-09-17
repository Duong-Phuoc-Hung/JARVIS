"""
tests/test_adversarial_m1_planner_failclosed.py
================================================
Empirical Challenger Test Suite for Milestone M1 (Planner Fail-Closed).
Adversarially stress-tests `jarvis/planner/engine.py` across:
1. Strange and hostile action names (Unicode, emoji, empty string, whitespace, control chars, symbols, null bytes, long strings).
2. Plan with multiple unhandled nodes in parallel or sequence — verifying DAG stops and marks failed steps truthfully without deadlocks.
3. Dispatcher being None vs Dispatcher returning ActionResult vs Dispatcher exceptions.
4. Exhaustive verification that NO execution path can produce `success=True` for an unregistered action.
"""
import time
import pytest
from unittest.mock import MagicMock

from jarvis.automation.safety_gate import SafetyGate
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult
from jarvis.planner.dag import TaskDAG
from jarvis.planner.engine import ReActTaskEngine
from jarvis.planner.models import PlanMode, StepStatus, TaskNode
from jarvis.planner.reflection import SelfReflectionEngine
from jarvis.planner.safety_interceptor import SafetyGateInterceptor


def _create_test_engine(dispatcher=None, max_retries=1):
    """Helper to instantiate engine with fast backoff for high-speed adversarial testing."""
    safety_gate = SafetyGate(timeout_seconds=2.0)
    safety_interceptor = SafetyGateInterceptor(safety_gate=safety_gate, timeout_seconds=2.0)
    reflection_engine = SelfReflectionEngine(base_backoff_seconds=0.005, max_backoff_seconds=0.02)
    engine = ReActTaskEngine(
        dispatcher=dispatcher,
        safety_interceptor=safety_interceptor,
        reflection_engine=reflection_engine,
    )
    return engine


class TestAdversarialStrangeActionNamesFailClosed:
    """Challenge 1: Unhandled action with strange names (unicode, empty string, symbols, null bytes, etc.)."""

    STRANGE_ACTION_NAMES = [
        "",  # Empty string
        "   ",  # Whitespace only
        "\t\n\r",  # Control characters
        "tự_động_hóa_tiếng_việt_có_dấu_123",  # Vietnamese diacritics
        "🤖🚀💥🔥💻⚡",  # Emojis
        "こんにちは_世界_テスト",  # Japanese Kanji/Hiragana
        "اختبار_الإجراء_غير_المسجل",  # Arabic script
        "'; DROP TABLE actions; --",  # SQL injection attempt
        "../../../../etc/passwd",  # Path traversal attempt
        "`id` && whoami || calc.exe",  # Shell injection attempt
        "<script>alert('xss')</script>",  # HTML / XSS attempt
        "!@#$%^&*()_+-=[]{}|;':\",./<>?",  # Special symbols
        "\x00\x01\x02\x1f\x7f",  # Binary / null bytes / non-printable
        "a" * 5000,  # Extremely long identifier (5,000 characters)
        "   leading_and_trailing_spaces   ",  # Padded name
    ]

    @pytest.mark.parametrize("action_name", STRANGE_ACTION_NAMES)
    def test_execute_step_strange_action_names_dispatcher_none(self, action_name):
        """When dispatcher is None, any unregistered action name must fail closed."""
        engine = _create_test_engine(dispatcher=None)
        node = TaskNode(step_id="step_strange", action_name=action_name)
        res = engine.execute_step(node)

        assert isinstance(res, ActionResult), f"Expected ActionResult, got {type(res)}"
        assert res.success is False, f"VULNERABILITY: Action '{action_name}' returned success=True!"
        assert res.error_code == "HANDLER_NOT_FOUND", f"Unexpected error_code: {res.error_code}"
        assert res.error is not None and len(res.error) > 0, "Error message must be non-empty"
        if isinstance(res.data, dict):
            assert "simulated" not in res.data, "VULNERABILITY: 'simulated' success flag found in data!"

    @pytest.mark.parametrize("action_name", STRANGE_ACTION_NAMES)
    def test_execute_step_strange_action_names_with_dispatcher(self, action_name):
        """When dispatcher is present, an unregistered strange action name must fail closed via dispatcher."""
        dispatcher = ActionDispatcher(event_bus=EventBus())
        engine = _create_test_engine(dispatcher=dispatcher)
        node = TaskNode(step_id="step_strange_disp", action_name=action_name)
        res = engine.execute_step(node)

        assert isinstance(res, ActionResult), f"Expected ActionResult, got {type(res)}"
        assert res.success is False, f"VULNERABILITY: Action '{action_name}' returned success=True with dispatcher!"
        assert res.error_code == "ACTION_NOT_FOUND", f"Unexpected error_code: {res.error_code}"
        assert res.error is not None and len(res.error) > 0

    def test_execute_step_none_action_name(self):
        """If action_name is None, execute_step must fail closed gracefully without crashing."""
        engine = _create_test_engine(dispatcher=None)
        node = TaskNode(step_id="step_none", action_name=None)  # type: ignore
        res = engine.execute_step(node)

        assert res.success is False
        assert res.error_code == "HANDLER_NOT_FOUND"


class TestAdversarialMultipleUnhandledNodesDAG:
    """Challenge 2: Plan with multiple unhandled nodes in parallel or sequence — verify DAG stops and marks failed steps truthfully."""

    def test_sequential_dag_with_unhandled_middle_step(self):
        """
        Sequence: Step 1 (valid) -> Step 2 (unhandled) -> Step 3 (valid, depends on Step 2).
        Must execute Step 1, fail Step 2, and NEVER execute Step 3.
        Plan result must be success=False.
        """
        engine = _create_test_engine(dispatcher=None)
        executed_steps = []

        engine.register_action_handler("valid_step_1", lambda **kw: executed_steps.append("step_1") or {"success": True, "data": "out1"})
        engine.register_action_handler("valid_step_3", lambda **kw: executed_steps.append("step_3") or {"success": True, "data": "out3"})

        dag = TaskDAG(plan_id="plan_seq_adversarial", goal="Verify sequential failure containment")
        dag.add_node(TaskNode(step_id="step_1", action_name="valid_step_1", max_retries=0))
        dag.add_node(TaskNode(step_id="step_2", action_name="unhandled_action_middle", depends_on=["step_1"], max_retries=0))
        dag.add_node(TaskNode(step_id="step_3", action_name="valid_step_3", depends_on=["step_2"], max_retries=0))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        assert plan_res.success is False, "Plan with unhandled step must return success=False"
        assert executed_steps == ["step_1"], f"Step 3 must not execute! Executed: {executed_steps}"
        assert dag.nodes["step_1"].status == StepStatus.COMPLETED
        assert dag.nodes["step_2"].status == StepStatus.FAILED
        assert dag.nodes["step_3"].status in (StepStatus.PENDING, StepStatus.BLOCKED)
        assert dag.nodes["step_3"].status != StepStatus.COMPLETED
        assert plan_res.completed_steps == 1
        assert plan_res.failed_steps >= 1

    def test_parallel_dag_with_multiple_unhandled_branches(self):
        """
        Parallel structure:
        Root (valid) -> [unhandled_p1, unhandled_p2, unhandled_p3, valid_p4] -> Join (valid)
        All 3 unhandled branches must fail concurrently.
        Valid branch p4 should succeed.
        Join step must NEVER execute.
        """
        engine = _create_test_engine(dispatcher=None)
        executed_steps = []

        engine.register_action_handler("root_action", lambda **kw: executed_steps.append("root") or {"res": "root_ok"})
        engine.register_action_handler("valid_branch_action", lambda **kw: executed_steps.append("p4") or {"res": "p4_ok"})
        engine.register_action_handler("join_action", lambda **kw: executed_steps.append("join") or {"res": "join_ok"})

        dag = TaskDAG(plan_id="plan_parallel_adversarial", goal="Verify parallel unhandled steps fail closed")
        dag.add_node(TaskNode(step_id="root", action_name="root_action", max_retries=0))
        dag.add_node(TaskNode(step_id="p1", action_name="unhandled_p1_💥", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="p2", action_name="unhandled_p2_⚡", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="p3", action_name="unhandled_p3_🔥", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="p4", action_name="valid_branch_action", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="join", action_name="join_action", depends_on=["p1", "p2", "p3", "p4"], max_retries=0))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        assert plan_res.success is False, "Plan with parallel failures must be False"
        assert "join" not in executed_steps, f"Join node must NEVER run when prerequisite branches fail!"
        assert dag.nodes["root"].status == StepStatus.COMPLETED
        assert dag.nodes["p1"].status == StepStatus.FAILED
        assert dag.nodes["p2"].status == StepStatus.FAILED
        assert dag.nodes["p3"].status == StepStatus.FAILED
        assert dag.nodes["p4"].status == StepStatus.COMPLETED
        assert dag.nodes["join"].status == StepStatus.BLOCKED
        assert plan_res.failed_steps == 4  # 3 FAILED + 1 BLOCKED
        assert plan_res.completed_steps == 2

    def test_plan_with_all_unhandled_steps(self):
        """DAG with 4 unhandled nodes. Completed steps must be 0, failed_steps must be >= 1."""
        engine = _create_test_engine(dispatcher=None)
        dag = TaskDAG(plan_id="plan_all_unhandled", goal="All unhandled nodes")
        dag.add_node(TaskNode(step_id="u1", action_name="bogus_1", max_retries=0))
        dag.add_node(TaskNode(step_id="u2", action_name="bogus_2", max_retries=0))
        dag.add_node(TaskNode(step_id="u3", action_name="bogus_3", depends_on=["u1"], max_retries=0))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        assert plan_res.success is False
        assert plan_res.completed_steps == 0
        assert plan_res.failed_steps >= 2
        assert dag.nodes["u1"].status == StepStatus.FAILED
        assert dag.nodes["u2"].status == StepStatus.FAILED


class TestAdversarialDispatcherInteractions:
    """Challenge 3: Dispatcher being None vs Dispatcher returning ActionResult vs exceptions."""

    def test_dispatcher_is_none(self):
        """When dispatcher is None, execute_step returns fail-closed HANDLER_NOT_FOUND."""
        engine = _create_test_engine(dispatcher=None)
        node = TaskNode(step_id="s1", action_name="some_unregistered_action")
        res = engine.execute_step(node)

        assert res.success is False
        assert res.error_code == "HANDLER_NOT_FOUND"
        assert "No handler registered" in res.error

    def test_dispatcher_is_standard_action_dispatcher(self):
        """When dispatcher is ActionDispatcher and action is unregistered, returns ACTION_NOT_FOUND."""
        dispatcher = ActionDispatcher(event_bus=EventBus())
        engine = _create_test_engine(dispatcher=dispatcher)
        node = TaskNode(step_id="s1", action_name="some_unregistered_action")
        res = engine.execute_step(node)

        assert res.success is False
        assert res.error_code == "ACTION_NOT_FOUND"
        assert "not registered" in res.error

    def test_dispatcher_raises_exception(self):
        """If dispatcher.dispatch_action raises an unexpected exception, engine fails closed with DISPATCHER_EXCEPTION."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch_action.side_effect = ConnectionResetError("Remote RPC disconnected unexpectedly")

        engine = _create_test_engine(dispatcher=mock_dispatcher)
        node = TaskNode(step_id="s1", action_name="rpc_action")
        res = engine.execute_step(node)

        assert isinstance(res, ActionResult)
        assert res.success is False
        assert res.error_code == "DISPATCHER_EXCEPTION"
        assert "Remote RPC disconnected unexpectedly" in res.error

    def test_dispatcher_returns_legitimate_failure_result(self):
        """If dispatcher returns an explicit failure ActionResult, engine preserves it intact."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch_action.return_value = ActionResult(
            action_name="gated_action",
            success=False,
            error="Rate limit exceeded for endpoint",
            error_code="RATE_LIMITED",
            data={"retry_after": 60},
        )

        engine = _create_test_engine(dispatcher=mock_dispatcher)
        node = TaskNode(step_id="s1", action_name="gated_action")
        res = engine.execute_step(node)

        assert res.success is False
        assert res.error_code == "RATE_LIMITED"
        assert res.error == "Rate limit exceeded for endpoint"
        assert res.data == {"retry_after": 60}

    def test_direct_handler_raises_exception(self):
        """If a direct handler throws an uncaught exception, engine fails closed with HANDLER_EXCEPTION."""
        engine = _create_test_engine(dispatcher=None)
        def exploding_handler(**kw):
            raise ZeroDivisionError("Hardware division by zero")

        engine.register_action_handler("exploding_op", exploding_handler)
        node = TaskNode(step_id="s1", action_name="exploding_op")
        res = engine.execute_step(node)

        assert res.success is False
        assert res.error_code == "HANDLER_EXCEPTION"
        assert "division by zero" in res.error

    def test_direct_handler_returns_failure_dict(self):
        """If a direct handler returns a dictionary with success=False, engine preserves failure without masking."""
        engine = _create_test_engine(dispatcher=None)
        engine.register_action_handler(
            "flaky_service",
            lambda **kw: {"success": False, "error": "Database locked", "error_code": "DB_LOCKED"}
        )
        node = TaskNode(step_id="s1", action_name="flaky_service")
        res = engine.execute_step(node)

        assert res.success is False
        assert res.error_code == "DB_LOCKED"
        assert res.error == "Database locked"


class TestAdversarialNoExecutionPathCanProduceSuccess:
    """Challenge 4: Verify no execution path can produce success=True for an unregistered action."""

    PARAMETER_INJECTIONS = [
        {"success": True},
        {"simulated": True},
        {"status": "COMPLETED"},
        {"ok": True},
        {"action_name": "registered_override"},
        {"code": "OK", "success": True, "error": None},
        {"result": {"success": True}},
    ]

    @pytest.mark.parametrize("poisoned_params", PARAMETER_INJECTIONS)
    def test_parameter_injection_cannot_trick_dispatcher_none(self, poisoned_params):
        """Poisoning node.parameters with success flags must NOT fool execute_step when unregistered."""
        engine = _create_test_engine(dispatcher=None)
        node = TaskNode(
            step_id="step_inject",
            action_name="unregistered_target",
            parameters=poisoned_params,
        )
        res = engine.execute_step(node)

        assert res.success is False, f"VULNERABILITY: Parameter injection {poisoned_params} caused success=True!"
        assert res.error_code == "HANDLER_NOT_FOUND"

    @pytest.mark.parametrize("poisoned_params", PARAMETER_INJECTIONS)
    def test_parameter_injection_cannot_trick_with_dispatcher(self, poisoned_params):
        """Poisoning node.parameters with success flags must NOT fool ActionDispatcher when unregistered."""
        dispatcher = ActionDispatcher(event_bus=EventBus())
        engine = _create_test_engine(dispatcher=dispatcher)
        node = TaskNode(
            step_id="step_inject_disp",
            action_name="unregistered_target_disp",
            parameters=poisoned_params,
        )
        res = engine.execute_step(node)

        assert res.success is False, f"VULNERABILITY: Parameter injection {poisoned_params} caused success=True!"
        assert res.error_code == "ACTION_NOT_FOUND"

    BUILTIN_ATTRIBUTES = [
        "__init__",
        "__call__",
        "__class__",
        "__doc__",
        "__dict__",
        "keys",
        "values",
        "items",
        "get",
        "pop",
        "clear",
        "update",
        "setdefault",
    ]

    @pytest.mark.parametrize("attr_name", BUILTIN_ATTRIBUTES)
    def test_builtin_attribute_names_do_not_collide_with_handlers(self, attr_name):
        """Actions named after dict methods/dunder attributes must not trigger internal methods or succeed."""
        engine = _create_test_engine(dispatcher=None)
        node = TaskNode(step_id="step_attr", action_name=attr_name)
        res = engine.execute_step(node)

        assert res.success is False
        assert res.error_code == "HANDLER_NOT_FOUND"

    @pytest.mark.parametrize("mode", [PlanMode.FULLY_AUTONOMOUS, PlanMode.SAFETY_GATE])
    def test_unregistered_action_fails_under_all_plan_modes(self, mode):
        """An unregistered action must fail closed regardless of PlanMode."""
        engine = _create_test_engine(dispatcher=None)
        dag = TaskDAG(plan_id=f"plan_mode_{mode.value}", goal=f"Test under mode {mode.value}")
        dag.add_node(TaskNode(step_id="s1", action_name="ghost_action_mode_test", max_retries=0))

        plan_res = engine.execute_plan(dag, mode=mode)
        assert plan_res.success is False
        assert dag.nodes["s1"].status == StepStatus.FAILED

    def test_reflection_retries_exhaust_and_abort_cleanly(self):
        """
        Verify that when an unhandled action is executed with retries enabled (max_retries=2),
        the reflection engine retries and eventually aborts with FAILED status, never fabricating success.
        """
        engine = _create_test_engine(dispatcher=None)
        dag = TaskDAG(plan_id="plan_retry_exhaust", goal="Test reflection retry exhaustion")
        dag.add_node(TaskNode(step_id="step_retry", action_name="permanently_unregistered", max_retries=2))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        assert plan_res.success is False
        assert dag.nodes["step_retry"].status == StepStatus.FAILED
        assert dag.nodes["step_retry"].retry_count >= 2
        assert plan_res.completed_steps == 0
        assert plan_res.failed_steps == 1
