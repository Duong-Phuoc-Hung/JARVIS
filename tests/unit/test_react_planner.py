"""
Unit and Integration Tests for JARVIS ReAct Planner Subsystem (Requirement R1).
Tests TaskDAG, cycle detection, dynamic variable interpolation, multi-step execution,
self-reflection triage, and safety gate interception.
"""
from __future__ import annotations

import time
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from jarvis.automation.safety_gate import SafetyGate
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult
from jarvis.planner.dag import (
    CycleDetectedException,
    NodeNotFoundException,
    TaskDAG,
    interpolate_parameters,
)
from jarvis.planner.engine import ReActTaskEngine
from jarvis.planner.models import (
    PlanMode,
    PlanResult,
    RecoveryStrategy,
    StepStatus,
    TaskNode,
)
from jarvis.planner.reflection import SelfReflectionEngine
from jarvis.planner.safety_interceptor import SafetyGateInterceptor


class TestReActPlanner(unittest.TestCase):
    """Test suite covering TaskDAG, ReActTaskEngine, SelfReflection, and SafetyGateInterceptor."""

    def setUp(self) -> None:
        self.event_bus = EventBus()
        self.dispatcher = ActionDispatcher(event_bus=self.event_bus)
        self.safety_gate = SafetyGate(timeout_seconds=5.0)
        self.safety_interceptor = SafetyGateInterceptor(safety_gate=self.safety_gate, timeout_seconds=5.0)
        self.reflection_engine = SelfReflectionEngine(base_backoff_seconds=0.01, max_backoff_seconds=0.1)
        self.engine = ReActTaskEngine(
            dispatcher=self.dispatcher,
            safety_interceptor=self.safety_interceptor,
            reflection_engine=self.reflection_engine,
            event_bus=self.event_bus,
            max_parallel_workers=4,
            default_timeout_seconds=10.0,
        )

    # 1. test_task_dag_creation_and_topological_sort
    def test_task_dag_creation_and_topological_sort(self) -> None:
        dag = TaskDAG(plan_id="plan_1", goal="Test DAG Sorting")
        n1 = TaskNode(step_id="step_1", action_name="fetch_data")
        n2 = TaskNode(step_id="step_2", action_name="parse_data", depends_on=["step_1"])
        n3 = TaskNode(step_id="step_3", action_name="validate_data", depends_on=["step_1"])
        n4 = TaskNode(step_id="step_4", action_name="save_report", depends_on=["step_2", "step_3"])

        dag.add_node(n1)
        dag.add_node(n2)
        dag.add_node(n3)
        dag.add_node(n4)

        waves = dag.topological_sort()
        self.assertEqual(len(waves), 3)
        # Wave 0: step_1
        self.assertEqual([n.step_id for n in waves[0]], ["step_1"])
        # Wave 1: step_2 and step_3 (parallel)
        self.assertEqual(set(n.step_id for n in waves[1]), {"step_2", "step_3"})
        # Wave 2: step_4
        self.assertEqual([n.step_id for n in waves[2]], ["step_4"])

    # 2. test_task_dag_cycle_detection_error
    def test_task_dag_cycle_detection_error(self) -> None:
        dag = TaskDAG(plan_id="plan_cycle", goal="Test Cycle")
        n1 = TaskNode(step_id="s1", action_name="act_1", depends_on=["s3"])
        n2 = TaskNode(step_id="s2", action_name="act_2", depends_on=["s1"])
        n3 = TaskNode(step_id="s3", action_name="act_3", depends_on=["s2"])

        dag.add_node(n1)
        dag.add_node(n2)
        dag.add_node(n3)

        self.assertTrue(dag.has_cycle())
        with self.assertRaises(CycleDetectedException):
            dag.topological_sort()

    # 3. test_dynamic_parameter_interpolation_nested
    def test_dynamic_parameter_interpolation_nested(self) -> None:
        context = {
            "steps": {
                "step_1": {
                    "output": {
                        "user_id": 42,
                        "file_path": "C:/data/export.csv",
                        "items": [{"id": "item_100", "score": 9.5}],
                    }
                }
            },
            "context": {"env": "production"},
            "goal": "Process CSV",
        }

        params = {
            "target_user": "{{steps.step_1.output.user_id}}",
            "file": "{{steps.step_1.output.file_path}}",
            "first_item_id": "{{steps.step_1.output.items[0].id}}",
            "template_str": "User {{steps.step_1.output.user_id}} in {{context.env}}",
        }

        resolved = interpolate_parameters(params, context)
        self.assertEqual(resolved["target_user"], 42)
        self.assertEqual(resolved["file"], "C:/data/export.csv")
        self.assertEqual(resolved["first_item_id"], "item_100")
        self.assertEqual(resolved["template_str"], "User 42 in production")

    # 4. test_planner_multi_step_sequential_execution_happy_path
    def test_planner_multi_step_sequential_execution_happy_path(self) -> None:
        dag = TaskDAG(plan_id="plan_seq", goal="Sequential Happy Path")

        # Step 1: generates data
        def step1_handler(prefix: str = "item") -> Dict[str, Any]:
            return {"file_id": f"{prefix}_123", "count": 5}

        # Step 2: consumes step 1 output
        def step2_handler(input_id: str, multiplier: int = 2) -> Dict[str, Any]:
            return {"processed_id": input_id.upper(), "total": 5 * multiplier}

        self.engine.register_action_handler("generate_data", step1_handler)
        self.engine.register_action_handler("process_data", step2_handler)

        dag.add_node(TaskNode(
            step_id="node_1",
            action_name="generate_data",
            parameters={"prefix": "order"},
        ))
        dag.add_node(TaskNode(
            step_id="node_2",
            action_name="process_data",
            parameters={
                "input_id": "{{steps.node_1.output.file_id}}",
                "multiplier": 3,
            },
            depends_on=["node_1"],
        ))

        result: PlanResult = self.engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)
        self.assertTrue(result.success)
        self.assertEqual(result.completed_steps, 2)
        self.assertEqual(result.failed_steps, 0)
        self.assertEqual(dag.nodes["node_2"].result_data, {"processed_id": "ORDER_123", "total": 15})

    # 5. test_planner_parallel_independent_step_execution
    def test_planner_parallel_independent_step_execution(self) -> None:
        dag = TaskDAG(plan_id="plan_par", goal="Parallel Execution")

        execution_times: List[float] = []

        def worker_fn(val: int) -> int:
            t_start = time.time()
            time.sleep(0.1)
            execution_times.append(t_start)
            return val * 10

        self.engine.register_action_handler("parallel_calc", worker_fn)

        for i in range(3):
            dag.add_node(TaskNode(
                step_id=f"step_par_{i}",
                action_name="parallel_calc",
                parameters={"val": i + 1},
            ))

        result = self.engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)
        self.assertTrue(result.success)
        self.assertEqual(result.completed_steps, 3)
        self.assertEqual(dag.nodes["step_par_0"].result_data, 10)
        self.assertEqual(dag.nodes["step_par_1"].result_data, 20)
        self.assertEqual(dag.nodes["step_par_2"].result_data, 30)

    # 6. test_planner_self_healing_retry_on_transient_failure
    def test_planner_self_healing_retry_on_transient_failure(self) -> None:
        dag = TaskDAG(plan_id="plan_retry", goal="Transient Failure Recovery")
        attempts = 0

        def flaky_action() -> Dict[str, str]:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("Simulated temporary gateway timeout")
            return {"status": "recovered"}

        self.engine.register_action_handler("flaky_call", flaky_action)

        dag.add_node(TaskNode(
            step_id="flaky_step",
            action_name="flaky_call",
            max_retries=4,
        ))

        result = self.engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)
        self.assertTrue(result.success)
        self.assertEqual(dag.nodes["flaky_step"].status, StepStatus.COMPLETED)
        self.assertEqual(dag.nodes["flaky_step"].retry_count, 2)
        self.assertEqual(dag.nodes["flaky_step"].result_data, {"status": "recovered"})

    # 7. test_planner_self_reflection_alternative_tool_selection
    def test_planner_self_reflection_alternative_tool_selection(self) -> None:
        dag = TaskDAG(plan_id="plan_tool_switch", goal="Alternative Tool Fallback")

        def broken_scraper(url: str) -> None:
            raise RuntimeError("Cloudflare captcha challenge blocked access")

        def fallback_search(query: str = "") -> Dict[str, str]:
            return {"extracted_text": "Successfully parsed via direct search"}

        self.engine.register_action_handler("browser_scrape", broken_scraper)
        self.engine.register_action_handler("web_search_direct", fallback_search)

        dag.add_node(TaskNode(
            step_id="scrape_step",
            action_name="browser_scrape",
            parameters={"url": "https://example.com"},
            max_retries=1,
        ))

        result = self.engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)
        self.assertTrue(result.success)
        self.assertEqual(dag.nodes["scrape_step"].action_name, "web_search_direct")
        self.assertEqual(dag.nodes["scrape_step"].status, StepStatus.COMPLETED)
        self.assertEqual(dag.nodes["scrape_step"].result_data, {"extracted_text": "Successfully parsed via direct search"})

    # 8. test_planner_self_healing_max_retries_exceeded_abort
    def test_planner_self_healing_max_retries_exceeded_abort(self) -> None:
        dag = TaskDAG(plan_id="plan_abort", goal="Exceeded Retries Abort")

        def fatal_action() -> None:
            raise ValueError("Unrecoverable data corruption")

        self.engine.register_action_handler("fatal_act", fatal_action)

        dag.add_node(TaskNode(
            step_id="fatal_step",
            action_name="fatal_act",
            max_retries=2,
        ))
        dag.add_node(TaskNode(
            step_id="dependent_step",
            action_name="noop",
            depends_on=["fatal_step"],
        ))

        result = self.engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)
        self.assertFalse(result.success)
        self.assertEqual(dag.nodes["fatal_step"].status, StepStatus.FAILED)
        self.assertEqual(dag.nodes["dependent_step"].status, StepStatus.BLOCKED)

    # 9. test_planner_safety_gate_interception_and_confirmation
    def test_planner_safety_gate_interception_and_confirmation(self) -> None:
        dag = TaskDAG(plan_id="plan_safety", goal="Safety Gate Confirmation")

        executed = False

        def destructive_act(target_dir: str) -> Dict[str, str]:
            nonlocal executed
            executed = True
            return {"deleted": target_dir}

        self.engine.register_action_handler("delete_folder", destructive_act)

        node = TaskNode(
            step_id="delete_step",
            action_name="delete_folder",
            parameters={"target_dir": "C:/temp/build_cache"},
            is_high_risk=True,
        )
        dag.add_node(node)

        # In a background thread, confirm token after short delay
        def async_confirm() -> None:
            time.sleep(0.2)
            for _ in range(20):
                if node.confirmation_token:
                    self.safety_gate.confirm(node.confirmation_token)
                    break
                time.sleep(0.05)

        import threading
        t = threading.Thread(target=async_confirm)
        t.start()

        result = self.engine.execute_plan(dag, mode=PlanMode.SAFETY_GATE)
        t.join()

        self.assertTrue(result.success)
        self.assertTrue(executed)
        self.assertEqual(dag.nodes["delete_step"].status, StepStatus.COMPLETED)

    # 10. test_planner_safety_gate_rejection_and_alternative_branch
    def test_planner_safety_gate_rejection_and_alternative_branch(self) -> None:
        dag = TaskDAG(plan_id="plan_reject", goal="Safety Gate Rejection")

        def dangerous_cmd() -> str:
            return "done"

        self.engine.register_action_handler("format_disk", dangerous_cmd)

        node = TaskNode(
            step_id="format_step",
            action_name="format_disk",
            parameters={"drive": "D:"},
            is_high_risk=True,
        )
        dag.add_node(node)

        def async_reject() -> None:
            time.sleep(0.1)
            for _ in range(20):
                if node.confirmation_token:
                    self.safety_gate.reject(node.confirmation_token)
                    break
                time.sleep(0.05)

        import threading
        t = threading.Thread(target=async_reject)
        t.start()

        result = self.engine.execute_plan(dag, mode=PlanMode.SAFETY_GATE)
        t.join()

        self.assertFalse(result.success)
        self.assertEqual(dag.nodes["format_step"].status, StepStatus.FAILED)

    # 11. test_planner_safety_gate_30s_timeout_expiration
    def test_planner_safety_gate_30s_timeout_expiration(self) -> None:
        # Fast-expiring safety gate for test (0.1s timeout)
        fast_gate = SafetyGate(timeout_seconds=0.1)
        fast_interceptor = SafetyGateInterceptor(safety_gate=fast_gate, timeout_seconds=0.1)
        fast_engine = ReActTaskEngine(
            dispatcher=self.dispatcher,
            safety_interceptor=fast_interceptor,
            reflection_engine=self.reflection_engine,
            event_bus=self.event_bus,
            default_timeout_seconds=1.0,
        )

        dag = TaskDAG(plan_id="plan_expire", goal="Safety Gate Expiration")
        node = TaskNode(
            step_id="gated_step",
            action_name="system_shutdown",
            is_high_risk=True,
        )
        dag.add_node(node)

        # Do not confirm; wait for expiration
        result = fast_engine.execute_plan(dag, mode=PlanMode.SAFETY_GATE)
        self.assertFalse(result.success)
        self.assertEqual(dag.nodes["gated_step"].status, StepStatus.FAILED)

    # 12. test_planner_telemetry_event_bus_emission
    def test_planner_telemetry_event_bus_emission(self) -> None:
        emitted_events: List[Dict[str, Any]] = []

        def event_listener(**payload: Any) -> None:
            emitted_events.append(payload)

        self.event_bus.subscribe("planner:plan_started", event_listener)
        self.event_bus.subscribe("planner:step_started", event_listener)
        self.event_bus.subscribe("planner:step_completed", event_listener)
        self.event_bus.subscribe("planner:plan_finished", event_listener)

        dag = TaskDAG(plan_id="plan_events", goal="Telemetry Test")
        self.engine.register_action_handler("mock_action", lambda: {"value": 123})

        dag.add_node(TaskNode(
            step_id="step_telemetry",
            action_name="mock_action",
        ))

        result = self.engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)
        self.assertTrue(result.success)
        self.assertGreaterEqual(len(emitted_events), 4)

    # 13. test_execute_step_unhandled_action_fails_closed (Requirement R1 Fail-Closed)
    def test_execute_step_unhandled_action_fails_closed(self) -> None:
        """R1 RED TEST: An unhandled action with no dispatcher must fail closed."""
        engine = ReActTaskEngine(dispatcher=None)
        node = TaskNode(step_id="step_x", action_name="nonexistent_action_xyz")
        res = engine.execute_step(node)

        self.assertFalse(res.success, "Unhandled action must fail closed")
        self.assertEqual(res.error_code, "HANDLER_NOT_FOUND")
        if isinstance(res.data, dict):
            self.assertNotIn("simulated", res.data)

    # 14. test_execute_plan_unhandled_action_aborts_plan (Requirement R1 Fail-Closed)
    def test_execute_plan_unhandled_action_aborts_plan(self) -> None:
        """R1 RED TEST: A TaskDAG containing an unhandled action must abort/fail the plan."""
        engine = ReActTaskEngine(dispatcher=None)
        dag = TaskDAG(plan_id="plan_unhandled_test", goal="Test unhandled action fail closed")
        dag.add_node(TaskNode(step_id="step_fail", action_name="nonexistent_action_abc"))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        self.assertFalse(plan_res.success)
        self.assertNotEqual(dag.nodes["step_fail"].status, StepStatus.COMPLETED)
        self.assertEqual(dag.nodes["step_fail"].status, StepStatus.FAILED)
        self.assertEqual(plan_res.failed_steps, 1)

    # 15. test_execute_step_direct_handler_failure_dict_preserved (Requirement R1 Fail-Closed)
    def test_execute_step_direct_handler_failure_dict_preserved(self) -> None:
        """R1 RED TEST: A direct handler returning success=False dict must not be masked as success."""
        engine = ReActTaskEngine(dispatcher=None)
        engine.register_action_handler(
            "failing_action",
            lambda **kw: {"success": False, "error": "Disk full", "error_code": "DISK_ERROR"},
        )
        node = TaskNode(step_id="step_failing", action_name="failing_action")
        res = engine.execute_step(node)

        self.assertFalse(res.success)
        self.assertEqual(res.error, "Disk full")
        self.assertEqual(res.error_code, "DISK_ERROR")

    # 16. test_execute_step_direct_handler_custom_error_code_preserved (Adversarial Challenge 1)
    def test_execute_step_direct_handler_custom_error_code_preserved(self) -> None:
        """Adversarial Challenge 1: Custom direct handler returning custom error and error_code is preserved."""
        engine = ReActTaskEngine(dispatcher=None)
        engine.register_action_handler(
            "custom_fail_action",
            lambda **kw: {"success": False, "error": "test error", "error_code": "CUSTOM_ERR"},
        )
        node = TaskNode(step_id="step_cf", action_name="custom_fail_action")
        res = engine.execute_step(node)

        self.assertFalse(res.success)
        self.assertEqual(res.error, "test error")
        self.assertEqual(res.error_code, "CUSTOM_ERR")
        self.assertEqual(res.action_name, "custom_fail_action")
        self.assertIsInstance(res.data, dict)
        self.assertEqual(res.data.get("error_code"), "CUSTOM_ERR")

    # 17. test_execute_step_direct_handler_default_error_code_fallback (Adversarial Challenge 1 Edge Case)
    def test_execute_step_direct_handler_default_error_code_fallback(self) -> None:
        """Adversarial Challenge 1b: If error_code is omitted, default ACTION_FAILED is used."""
        engine = ReActTaskEngine(dispatcher=None)
        engine.register_action_handler(
            "minimal_fail_action",
            lambda **kw: {"success": False, "error": "generic error"},
        )
        node = TaskNode(step_id="step_mf", action_name="minimal_fail_action")
        res = engine.execute_step(node)

        self.assertFalse(res.success)
        self.assertEqual(res.error, "generic error")
        self.assertEqual(res.error_code, "ACTION_FAILED")

    # 18. test_execute_step_direct_handler_raises_exception_handled_cleanly (Adversarial Challenge 2)
    def test_execute_step_direct_handler_raises_exception_handled_cleanly(self) -> None:
        """Adversarial Challenge 2: Direct handler raising RuntimeError is caught cleanly with HANDLER_EXCEPTION."""
        engine = ReActTaskEngine(dispatcher=None)

        def crashing_handler(**kw: Any) -> None:
            raise RuntimeError("Database connection suddenly dropped")

        engine.register_action_handler("crashing_action", crashing_handler)
        node = TaskNode(step_id="step_crash", action_name="crashing_action")
        res = engine.execute_step(node)

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "HANDLER_EXCEPTION")
        self.assertIn("Database connection suddenly dropped", str(res.error))
        self.assertEqual(res.action_name, "crashing_action")

    # 19. test_execute_step_direct_handler_typeerror_handled_cleanly (Adversarial Challenge 2 Signature Mismatch)
    def test_execute_step_direct_handler_typeerror_handled_cleanly(self) -> None:
        """Adversarial Challenge 2b: Direct handler with mismatched parameters raises TypeError, caught as HANDLER_EXCEPTION."""
        engine = ReActTaskEngine(dispatcher=None)

        def strict_handler(required_param: str) -> str:
            return f"Hello {required_param}"

        engine.register_action_handler("strict_action", strict_handler)
        node = TaskNode(step_id="step_strict", action_name="strict_action", parameters={"wrong_param": 123})
        res = engine.execute_step(node)

        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "HANDLER_EXCEPTION")
        self.assertIn("unexpected keyword argument", str(res.error))

    # 20. test_execute_step_legitimate_successful_handlers (Adversarial Challenge 3)
    def test_execute_step_legitimate_successful_handlers(self) -> None:
        """Adversarial Challenge 3: Legitimate successful handlers return success=True across various types."""
        engine = ReActTaskEngine(dispatcher=None)

        # 3a: returns ActionResult directly
        engine.register_action_handler(
            "action_result_handler",
            lambda: ActionResult(action_name="action_result_handler", success=True, data={"custom": "ok"}),
        )
        res_ar = engine.execute_step(TaskNode(step_id="s1", action_name="action_result_handler"))
        self.assertTrue(res_ar.success)
        self.assertEqual(res_ar.data, {"custom": "ok"})

        # 3b: returns dict with success=True
        engine.register_action_handler(
            "dict_success_handler",
            lambda: {"success": True, "metric": 99.5},
        )
        res_dict = engine.execute_step(TaskNode(step_id="s2", action_name="dict_success_handler"))
        self.assertTrue(res_dict.success)
        self.assertEqual(res_dict.data, {"success": True, "metric": 99.5})

        # 3c: returns arbitrary dict without success key
        engine.register_action_handler(
            "dict_arbitrary_handler",
            lambda: {"status_code": 200, "payload": "sample"},
        )
        res_arb = engine.execute_step(TaskNode(step_id="s3", action_name="dict_arbitrary_handler"))
        self.assertTrue(res_arb.success)
        self.assertEqual(res_arb.data, {"status_code": 200, "payload": "sample"})

        # 3d: returns scalar value
        engine.register_action_handler("scalar_handler", lambda: 42)
        res_scalar = engine.execute_step(TaskNode(step_id="s4", action_name="scalar_handler"))
        self.assertTrue(res_scalar.success)
        self.assertEqual(res_scalar.data, 42)

        # 3e: returns None
        engine.register_action_handler("none_handler", lambda: None)
        res_none = engine.execute_step(TaskNode(step_id="s5", action_name="none_handler"))
        self.assertTrue(res_none.success)
        self.assertIsNone(res_none.data)

    # 21. test_execute_plan_direct_handler_exception_aborts_plan (Adversarial DAG Integration)
    def test_execute_plan_direct_handler_exception_aborts_plan(self) -> None:
        """Adversarial DAG Integration: Direct handler raising exception aborts plan execution truthfully."""
        engine = ReActTaskEngine(dispatcher=None)

        def exploding_handler(**kw: Any) -> None:
            raise RuntimeError("Hardware sensor failure")

        engine.register_action_handler("exploding_sensor", exploding_handler)

        dag = TaskDAG(plan_id="plan_dag_crash", goal="Test DAG Crash Fail Closed")
        dag.add_node(TaskNode(step_id="step_crash", action_name="exploding_sensor", max_retries=1))
        dag.add_node(TaskNode(step_id="step_dependent", action_name="noop", depends_on=["step_crash"]))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        self.assertFalse(plan_res.success)
        self.assertEqual(dag.nodes["step_crash"].status, StepStatus.FAILED)
        self.assertEqual(dag.nodes["step_dependent"].status, StepStatus.BLOCKED)
        self.assertEqual(plan_res.failed_steps, 2)  # 1 FAILED + 1 BLOCKED

    # 22. test_execute_plan_direct_handler_custom_failure_aborts_plan (Adversarial DAG Integration)
    def test_execute_plan_direct_handler_custom_failure_aborts_plan(self) -> None:
        """Adversarial DAG Integration: Direct handler returning custom failure dict aborts plan execution."""
        engine = ReActTaskEngine(dispatcher=None)
        engine.register_action_handler(
            "custom_fail_action",
            lambda **kw: {"success": False, "error": "test error", "error_code": "CUSTOM_ERR"},
        )

        dag = TaskDAG(plan_id="plan_dag_custom_fail", goal="Test DAG Custom Fail Closed")
        dag.add_node(TaskNode(step_id="step_fail", action_name="custom_fail_action", max_retries=1))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        self.assertFalse(plan_res.success)
        self.assertEqual(dag.nodes["step_fail"].status, StepStatus.FAILED)
        self.assertEqual(plan_res.failed_steps, 1)

    # 23. test_adversarial_unhandled_action_strange_names (Challenge 1)
    def test_adversarial_unhandled_action_strange_names(self) -> None:
        """Adversarial Challenge 1: Unhandled actions with strange names fail closed."""
        engine_none = ReActTaskEngine(dispatcher=None)
        engine_disp = ReActTaskEngine(dispatcher=ActionDispatcher(event_bus=EventBus()))

        strange_names = [
            "",
            "   ",
            "\t\n\r",
            "tự_động_hóa_tiếng_việt_có_dấu_123",
            "🤖🚀💥🔥💻⚡",
            "こんにちは_世界_テスト",
            "اختبار_الإجراء_غير_المسجل",
            "'; DROP TABLE actions; --",
            "../../../../etc/passwd",
            "`id` && whoami || calc.exe",
            "!@#$%^&*()_+-=[]{}|;':\",./<>?",
            "\x00\x01\x02\x1f\x7f",
            "a" * 2000,
        ]

        for name in strange_names:
            # 1a. With dispatcher = None
            node_none = TaskNode(step_id="step_s", action_name=name)
            res_none = engine_none.execute_step(node_none)
            self.assertFalse(res_none.success, f"Action '{name}' succeeded with dispatcher=None!")
            self.assertEqual(res_none.error_code, "HANDLER_NOT_FOUND")
            self.assertTrue(res_none.error, "Error message must be non-empty")
            if isinstance(res_none.data, dict):
                self.assertNotIn("simulated", res_none.data)

            # 1b. With dispatcher = ActionDispatcher()
            node_disp = TaskNode(step_id="step_s2", action_name=name)
            res_disp = engine_disp.execute_step(node_disp)
            self.assertFalse(res_disp.success, f"Action '{name}' succeeded with ActionDispatcher!")
            self.assertEqual(res_disp.error_code, "ACTION_NOT_FOUND")

    # 24. test_adversarial_plan_multiple_unhandled_sequential (Challenge 2)
    def test_adversarial_plan_multiple_unhandled_sequential(self) -> None:
        """Adversarial Challenge 2a: Sequential DAG stops at unhandled step and truthfully blocks dependents."""
        reflection = SelfReflectionEngine(base_backoff_seconds=0.005, max_backoff_seconds=0.02)
        engine = ReActTaskEngine(dispatcher=None, reflection_engine=reflection)
        executed = []

        engine.register_action_handler("step1_act", lambda **kw: executed.append(1) or {"out": 1})
        engine.register_action_handler("step3_act", lambda **kw: executed.append(3) or {"out": 3})

        dag = TaskDAG(plan_id="plan_seq_adv", goal="Sequential failure containment")
        dag.add_node(TaskNode(step_id="s1", action_name="step1_act", max_retries=0))
        dag.add_node(TaskNode(step_id="s2", action_name="unhandled_seq_node", depends_on=["s1"], max_retries=0))
        dag.add_node(TaskNode(step_id="s3", action_name="step3_act", depends_on=["s2"], max_retries=0))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        self.assertFalse(plan_res.success)
        self.assertEqual(executed, [1], "Step 3 must NEVER execute after step 2 failure!")
        self.assertEqual(dag.nodes["s1"].status, StepStatus.COMPLETED)
        self.assertEqual(dag.nodes["s2"].status, StepStatus.FAILED)
        self.assertIn(dag.nodes["s3"].status, (StepStatus.PENDING, StepStatus.BLOCKED))
        self.assertNotEqual(dag.nodes["s3"].status, StepStatus.COMPLETED)
        self.assertEqual(plan_res.completed_steps, 1)
        self.assertGreaterEqual(plan_res.failed_steps, 1)

    # 25. test_adversarial_plan_multiple_unhandled_parallel (Challenge 2)
    def test_adversarial_plan_multiple_unhandled_parallel(self) -> None:
        """Adversarial Challenge 2b: Parallel DAG marks all unhandled branches as failed truthfully without deadlock."""
        reflection = SelfReflectionEngine(base_backoff_seconds=0.005, max_backoff_seconds=0.02)
        engine = ReActTaskEngine(dispatcher=None, reflection_engine=reflection)
        executed = []

        engine.register_action_handler("root_act", lambda **kw: executed.append("root") or {"res": "ok"})
        engine.register_action_handler("valid_branch", lambda **kw: executed.append("valid") or {"res": "ok"})
        engine.register_action_handler("join_act", lambda **kw: executed.append("join") or {"res": "ok"})

        dag = TaskDAG(plan_id="plan_par_adv", goal="Parallel failure containment")
        dag.add_node(TaskNode(step_id="root", action_name="root_act", max_retries=0))
        dag.add_node(TaskNode(step_id="p1", action_name="unhandled_par_1", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="p2", action_name="unhandled_par_2", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="p3", action_name="unhandled_par_3", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="p4", action_name="valid_branch", depends_on=["root"], max_retries=0))
        dag.add_node(TaskNode(step_id="join", action_name="join_act", depends_on=["p1", "p2", "p3", "p4"], max_retries=0))

        plan_res = engine.execute_plan(dag, mode=PlanMode.FULLY_AUTONOMOUS)

        self.assertFalse(plan_res.success)
        self.assertNotIn("join", executed, "Join node must NEVER run when prerequisite branches fail!")
        self.assertEqual(dag.nodes["root"].status, StepStatus.COMPLETED)
        self.assertEqual(dag.nodes["p1"].status, StepStatus.FAILED)
        self.assertEqual(dag.nodes["p2"].status, StepStatus.FAILED)
        self.assertEqual(dag.nodes["p3"].status, StepStatus.FAILED)
        self.assertEqual(dag.nodes["p4"].status, StepStatus.COMPLETED)
        self.assertEqual(dag.nodes["join"].status, StepStatus.BLOCKED)
        self.assertEqual(plan_res.failed_steps, 4)  # 3 FAILED + 1 BLOCKED
        self.assertEqual(plan_res.completed_steps, 2)

    # 26. test_adversarial_dispatcher_exception_and_failure_propagation (Challenge 3)
    def test_adversarial_dispatcher_exception_and_failure_propagation(self) -> None:
        """Adversarial Challenge 3: Dispatcher exception and failure results are propagated fail-closed."""
        # 3a. Dispatcher raises unexpected exception
        mock_disp_crash = MagicMock()
        mock_disp_crash.dispatch_action.side_effect = ConnectionResetError("Remote endpoint crash")
        engine_crash = ReActTaskEngine(dispatcher=mock_disp_crash)
        res_crash = engine_crash.execute_step(TaskNode(step_id="s_crash", action_name="any_action"))
        self.assertFalse(res_crash.success)
        self.assertEqual(res_crash.error_code, "DISPATCHER_EXCEPTION")
        self.assertIn("Remote endpoint crash", str(res_crash.error))

        # 3b. Dispatcher returns legitimate failure ActionResult
        mock_disp_fail = MagicMock()
        mock_disp_fail.dispatch_action.return_value = ActionResult(
            action_name="rate_limited_act",
            success=False,
            error="Rate limit exceeded",
            error_code="RATE_LIMIT_EXCEEDED",
        )
        engine_fail = ReActTaskEngine(dispatcher=mock_disp_fail)
        res_fail = engine_fail.execute_step(TaskNode(step_id="s_fail", action_name="rate_limited_act"))
        self.assertFalse(res_fail.success)
        self.assertEqual(res_fail.error_code, "RATE_LIMIT_EXCEEDED")
        self.assertEqual(res_fail.error, "Rate limit exceeded")

    # 27. test_adversarial_no_path_can_produce_success_for_unregistered_action (Challenge 4)
    def test_adversarial_no_path_can_produce_success_for_unregistered_action(self) -> None:
        """Adversarial Challenge 4: Parameter poisoning and dictionary attribute collision cannot forge success."""
        engine = ReActTaskEngine(dispatcher=None)

        # 4a. Parameter poisoning
        poisoned_parameters = [
            {"success": True},
            {"simulated": True},
            {"status": "COMPLETED"},
            {"code": "OK", "success": True},
            {"result": {"success": True}},
        ]
        for params in poisoned_parameters:
            node = TaskNode(step_id="s_inject", action_name="unregistered_act", parameters=params)
            res = engine.execute_step(node)
            self.assertFalse(res.success, f"Poisoned params {params} caused success=True!")
            self.assertEqual(res.error_code, "HANDLER_NOT_FOUND")

        # 4b. Built-in dict attribute collision
        dunder_names = ["__init__", "__call__", "__class__", "__doc__", "keys", "values", "items", "get", "pop"]
        for dunder in dunder_names:
            node = TaskNode(step_id="s_dunder", action_name=dunder)
            res = engine.execute_step(node)
            self.assertFalse(res.success, f"Action name '{dunder}' triggered success!")
            self.assertEqual(res.error_code, "HANDLER_NOT_FOUND")

        # 4c. All plan modes fail closed on unregistered action
        for mode in (PlanMode.FULLY_AUTONOMOUS, PlanMode.SAFETY_GATE):
            dag = TaskDAG(plan_id=f"plan_{mode.value}", goal="Mode test")
            dag.add_node(TaskNode(step_id="s_m", action_name="unregistered_mode_act", max_retries=0))
            plan_res = engine.execute_plan(dag, mode=mode)
            self.assertFalse(plan_res.success, f"Mode {mode.value} produced plan success=True!")
            self.assertEqual(dag.nodes["s_m"].status, StepStatus.FAILED)


if __name__ == "__main__":
    unittest.main()


