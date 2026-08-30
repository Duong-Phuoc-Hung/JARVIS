"""
ReAct Task Execution Engine for the JARVIS Autonomous Planner subsystem.
Executes TaskDAGs, coordinates parallel branches, enforces safety gate confirmations,
runs the self-healing self-reflection loop, and reports telemetry.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult
from jarvis.planner.dag import TaskDAG
from jarvis.planner.models import (
    PlanMode,
    PlanResult,
    StepStatus,
    TaskNode,
)
from jarvis.planner.reflection import SelfReflectionEngine
from jarvis.planner.safety_interceptor import SafetyGateInterceptor

logger = logging.getLogger("jarvis.planner.engine")


class ReActTaskEngine:
    """
    Core Autonomous Multi-Step Reasoning and Acting Engine.
    Takes complex goals, builds executable TaskDAGs, orchestrates parallel execution,
    and self-heals transient/structural failures.
    """

    def __init__(
        self,
        dispatcher: ActionDispatcher | None = None,
        safety_interceptor: SafetyGateInterceptor | None = None,
        reflection_engine: SelfReflectionEngine | None = None,
        event_bus: EventBus | None = None,
        max_parallel_workers: int = 4,
        default_timeout_seconds: float = 300.0,
        custom_action_handlers: dict[str, Callable[..., Any]] | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.event_bus = event_bus or (dispatcher.event_bus if dispatcher else EventBus())
        self.safety_interceptor = safety_interceptor or SafetyGateInterceptor()
        self.reflection_engine = reflection_engine or SelfReflectionEngine()
        self.max_parallel_workers = max(1, int(max_parallel_workers))
        self.default_timeout_seconds = float(default_timeout_seconds)
        self._action_handlers: dict[str, Callable[..., Any]] = dict(custom_action_handlers or {})

    def register_action_handler(self, action_name: str, handler: Callable[..., Any]) -> None:
        """Registers a direct Python callable handler for a specific action."""
        self._action_handlers[action_name] = handler

    def create_plan(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
    ) -> TaskDAG:
        """
        Decomposes a user goal into an executable TaskDAG.
        
        Args:
            goal: Natural language goal or user request.
            context: Optional contextual parameters (e.g. user_id, active window, cwd).
            
        Returns:
            Constructed TaskDAG instance.
        """
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        dag = TaskDAG(plan_id=plan_id, goal=goal)

        # If goal contains structured instructions or test cases:
        # In full system, this calls LLM planner; here we also provide robust heuristics
        goal_lower = goal.strip().lower()

        # Rule-based plan generation for common workflow patterns
        if "csv" in goal_lower and ("revenue" in goal_lower or "doanh thu" in goal_lower or "tính tổng" in goal_lower):
            dag.add_node(TaskNode(
                step_id="step_find_files",
                action_name="file_search",
                description="Tìm kiếm các file CSV trong thư mục",
                parameters={"pattern": "*.csv", "directory": context.get("cwd", ".") if context else "."},
            ))
            dag.add_node(TaskNode(
                step_id="step_aggregate_data",
                action_name="sandbox_python_exec",
                description="Tổng hợp dữ liệu doanh thu và xuất file Excel",
                parameters={
                    "files": "{{steps.step_find_files.output.files}}",
                    "output_file": "revenue_report.xlsx"
                },
                depends_on=["step_find_files"],
            ))
            dag.add_node(TaskNode(
                step_id="step_notify_telegram",
                action_name="telegram_send_document",
                description="Gửi báo cáo doanh thu qua Telegram",
                parameters={
                    "file_path": "{{steps.step_aggregate_data.output.artifact_path}}",
                    "caption": "Báo cáo doanh thu đã hoàn tất"
                },
                depends_on=["step_aggregate_data"],
                is_high_risk=True,
            ))
        else:
            # Default single-step execution node
            dag.add_node(TaskNode(
                step_id="step_1",
                action_name=context.get("action_name", "generic_task") if context else "generic_task",
                description=goal,
                parameters=context.get("parameters", {}) if context else {},
            ))

        return dag

    def execute_plan(
        self,
        dag: TaskDAG,
        mode: PlanMode = PlanMode.FULLY_AUTONOMOUS,
        timeout_seconds: float | None = None,
    ) -> PlanResult:
        """
        Executes the provided TaskDAG according to the chosen PlanMode.
        
        Args:
            dag: The TaskDAG to execute.
            mode: PlanMode.FULLY_AUTONOMOUS or PlanMode.SAFETY_GATE.
            timeout_seconds: Maximum wall-clock time in seconds for the entire plan.
            
        Returns:
            PlanResult detailing execution metrics, individual node statuses, and outputs.
        """
        t0 = time.perf_counter()
        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        deadline = time.time() + timeout

        logger.info(
            "Starting execution of plan '%s' (mode=%s, total_steps=%d)",
            dag.plan_id, mode.value, len(dag)
        )

        self._emit_event(
            "planner:plan_started",
            plan_id=dag.plan_id,
            goal=dag.goal,
            mode=mode.value,
            total_steps=len(dag),
        )

        with ThreadPoolExecutor(max_workers=self.max_parallel_workers, thread_name_prefix="ReActPlanner") as pool:
            active_futures: dict[Future[ActionResult], TaskNode] = {}

            while not dag.is_finished():
                if time.time() > deadline:
                    logger.warning("Plan '%s' exceeded timeout of %.1fs. Aborting.", dag.plan_id, timeout)
                    # Mark remaining unfinished nodes as FAILED
                    for node in dag.nodes.values():
                        if node.status in (StepStatus.PENDING, StepStatus.READY, StepStatus.RUNNING, StepStatus.WAITING_CONFIRMATION):
                            node.status = StepStatus.FAILED
                            node.error_message = "Execution timed out."
                    break

                # 1. Check Safety Gate Confirmations for WAITING_CONFIRMATION nodes
                for node in dag.nodes.values():
                    if node.status == StepStatus.WAITING_CONFIRMATION and node.confirmation_token:
                        is_confirmed, status_str = self.safety_interceptor.check_confirmation(node.confirmation_token)
                        if is_confirmed:
                            logger.info("Token %s confirmed for node '%s'. Advancing to READY.", node.confirmation_token, node.step_id)
                            node.status = StepStatus.READY
                        elif status_str in ("REJECTED", "EXPIRED"):
                            logger.info("Token %s was %s for node '%s'.", node.confirmation_token, status_str, node.step_id)
                            node.error_message = f"Safety confirmation {status_str.lower()}."
                            reflection = self.reflection_engine.reflect(
                                node, f"safety_gate_{status_str.lower()}", dag=dag
                            )
                            self.reflection_engine.apply_reflection(reflection, node, dag)

                # 2. Get Ready Nodes
                ready_nodes = dag.get_ready_nodes()

                # 3. Interpolate parameters, then evaluate Safety Gate
                #    interception. High-risk nodes are ALWAYS gated here,
                #    regardless of PlanMode -- FULLY_AUTONOMOUS only skips
                #    gating for nodes the shared SafetyGateInterceptor does
                #    NOT classify as high-risk. This closes the gap where
                #    the real production caller of execute_plan() never
                #    requests PlanMode.SAFETY_GATE (see CLAUDE.md 8.3/9.1).
                #    Parameters are interpolated here (not at dispatch time
                #    below) so a gated token binds to the exact final
                #    parameters that will later be verified at dispatch.
                executable_nodes: list[TaskNode] = []
                for node in ready_nodes:
                    try:
                        node.parameters = dag.interpolate_node_params(node)
                    except Exception as exc:
                        logger.error("Parameter interpolation error on node '%s': %s", node.step_id, exc)
                        node.status = StepStatus.FAILED
                        node.error_message = f"Parameter interpolation failed: {exc}"
                        continue

                    if self.safety_interceptor.is_high_risk_node(node):
                        # Only intercept if not already confirmed
                        if not node.confirmation_token:
                            self.safety_interceptor.intercept_node(node, event_bus=self.event_bus)
                            continue
                        elif node.status == StepStatus.WAITING_CONFIRMATION:
                            # Still waiting for confirmation
                            continue
                    executable_nodes.append(node)

                # 4. Dispatch Executable Nodes to ThreadPool
                for node in executable_nodes:
                    node.status = StepStatus.RUNNING
                    node.started_at = time.time()
                    self._emit_event(
                        "planner:step_started",
                        plan_id=dag.plan_id,
                        step_id=node.step_id,
                        action_name=node.action_name,
                        parameters=node.parameters,
                    )

                    # Submit to pool
                    fut = pool.submit(self.execute_step, node, dag)
                    active_futures[fut] = node

                # 5. Wait for at least one active future or brief sleep
                if active_futures:
                    # Check completed futures with small timeout to allow loop liveness
                    done_futures = [f for f in active_futures if f.done()]
                    if not done_futures:
                        time.sleep(0.05)
                        continue

                    for fut in done_futures:
                        node = active_futures.pop(fut)
                        node.finished_at = time.time()
                        if node.started_at:
                            node.execution_time_ms = (node.finished_at - node.started_at) * 1000.0

                        try:
                            action_result = fut.result()
                        except Exception as exc:
                            action_result = ActionResult(
                                action_name=node.action_name,
                                success=False,
                                error=str(exc),
                                error_code="UNCAUGHT_EXCEPTION",
                            )

                        self._process_step_result(node, action_result, dag)
                else:
                    # No active running futures; check if we're waiting for confirmation
                    waiting_nodes = [
                        n for n in dag.nodes.values()
                        if n.status == StepStatus.WAITING_CONFIRMATION
                    ]
                    if waiting_nodes:
                        time.sleep(0.1)
                    else:
                        # No ready, no running, no waiting confirmation -> execution complete or blocked
                        break

        # Post-Execution Summary
        total_duration_ms = (time.perf_counter() - t0) * 1000.0
        completed_count = sum(1 for n in dag.nodes.values() if n.status == StepStatus.COMPLETED)
        failed_count = sum(1 for n in dag.nodes.values() if n.status in (StepStatus.FAILED, StepStatus.BLOCKED))
        skipped_count = sum(1 for n in dag.nodes.values() if n.status == StepStatus.SKIPPED)
        is_success = dag.is_successful()

        # Find final output from last topological completed node
        final_output = None
        for wave in reversed(dag.topological_sort() if not dag.has_cycle() else []):
            for n in wave:
                if n.status == StepStatus.COMPLETED and n.result_data is not None:
                    final_output = n.result_data
                    break
            if final_output is not None:
                break

        summary_msg = (
            f"Kế hoạch '{dag.goal}' đã hoàn tất thành công ({completed_count}/{len(dag)} bước)."
            if is_success else
            f"Kế hoạch '{dag.goal}' kết thúc với {failed_count} bước thất bại hoặc bị chặn."
        )

        plan_result = PlanResult(
            plan_id=dag.plan_id,
            goal=dag.goal,
            success=is_success,
            mode=mode,
            nodes=dict(dag.nodes),
            total_steps=len(dag),
            completed_steps=completed_count,
            failed_steps=failed_count,
            skipped_steps=skipped_count,
            total_duration_ms=total_duration_ms,
            final_output=final_output,
            error=None if is_success else "One or more steps failed.",
            summary_message=summary_msg,
        )

        self._emit_event(
            "planner:plan_finished",
            plan_id=dag.plan_id,
            goal=dag.goal,
            success=is_success,
            completed_steps=completed_count,
            total_steps=len(dag),
            total_duration_ms=total_duration_ms,
        )

        logger.info(
            "Plan '%s' finished: success=%s, completed=%d/%d, duration=%.2fms",
            dag.plan_id, is_success, completed_count, len(dag), total_duration_ms
        )

        return plan_result

    def _process_step_result(self, node: TaskNode, result: ActionResult, dag: TaskDAG) -> None:
        """Processes the outcome of a step, triggering self-reflection if needed."""
        if result.success:
            node.status = StepStatus.COMPLETED
            node.result_data = result.data
            node.error_message = None
            logger.info("Step '%s' (%s) COMPLETED successfully.", node.step_id, node.action_name)
            self._emit_event(
                "planner:step_completed",
                plan_id=dag.plan_id,
                step_id=node.step_id,
                action_name=node.action_name,
                result_data=node.result_data,
                execution_time_ms=node.execution_time_ms,
            )
        else:
            node.error_message = result.error or "Action execution failed."
            logger.warning(
                "Step '%s' (%s) FAILED. Error: %s",
                node.step_id, node.action_name, node.error_message
            )
            self._emit_event(
                "planner:step_failed",
                plan_id=dag.plan_id,
                step_id=node.step_id,
                action_name=node.action_name,
                error=node.error_message,
            )

            # Trigger SelfReflection
            reflection = self.reflection_engine.reflect(
                node=node,
                error=node.error_message,
                dag=dag,
            )
            self.reflection_engine.apply_reflection(reflection, node, dag)

    def execute_step(self, node: TaskNode, dag: TaskDAG | None = None) -> ActionResult:
        """
        Executes a single discrete step action.
        Routes to direct handler or ActionDispatcher.
        """
        action_name = node.action_name
        params = node.parameters or {}

        # 1. Check custom direct handlers
        if action_name in self._action_handlers:
            try:
                handler = self._action_handlers[action_name]
                res = handler(**params) if isinstance(params, dict) else handler(params)
                if isinstance(res, ActionResult):
                    return res
                return ActionResult(
                    action_name=action_name,
                    success=True,
                    data=res,
                )
            except Exception as e:
                return ActionResult(
                    action_name=action_name,
                    success=False,
                    error=str(e),
                    error_code="HANDLER_EXCEPTION",
                )

        # 2. Check ActionDispatcher
        if self.dispatcher:
            try:
                return self.dispatcher.dispatch_action(
                    action_name=action_name,
                    payload=params,
                    requester="planner",
                    # Nodes classified high-risk were already gated and
                    # confirmed above in execute_plan() (step 3), against
                    # these exact same, already-interpolated parameters --
                    # pass the token through so the dispatcher's own
                    # independent safety check verifies and consumes it
                    # instead of re-gating an already-confirmed action.
                    confirmation_token=node.confirmation_token,
                )
            except Exception as e:
                return ActionResult(
                    action_name=action_name,
                    success=False,
                    error=str(e),
                    error_code="DISPATCHER_EXCEPTION",
                )

        # 3. Default fallback mock execution
        logger.debug("No handler found for '%s', returning simulated success.", action_name)
        return ActionResult(
            action_name=action_name,
            success=True,
            data={"simulated": True, "action": action_name, "parameters": params},
        )

    def confirm_step(self, token: str) -> bool:
        """Confirms a pending safety gate token."""
        return self.safety_interceptor.confirm(token)

    def reject_step(self, token: str) -> bool:
        """Rejects a pending safety gate token."""
        return self.safety_interceptor.reject(token)

    def _emit_event(self, topic: str, **kwargs: Any) -> None:
        """Helper to publish events to the EventBus."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                self.event_bus.publish(topic, **kwargs)
            except Exception as exc:
                logger.debug("Failed to publish event '%s': %s", topic, exc)
