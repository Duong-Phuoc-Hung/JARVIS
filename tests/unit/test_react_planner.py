"""
Unit and Integration Tests for JARVIS ReAct Planner Subsystem (Requirement R1).
Tests TaskDAG, cycle detection, dynamic variable interpolation, multi-step execution,
self-reflection triage, and safety gate interception.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List
import unittest
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


if __name__ == "__main__":
    unittest.main()
