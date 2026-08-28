"""
Task Directed Acyclic Graph (TaskDAG) for the JARVIS ReAct Planner subsystem.
Handles dependency resolution, cycle detection, level-by-level topological sorting,
and recursive dynamic parameter interpolation ({{steps.node_id.output.path}}).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from jarvis.planner.models import StepStatus, TaskNode

logger = logging.getLogger("jarvis.planner.dag")


class TaskDAGException(Exception):
    """Base exception for TaskDAG errors."""
    pass


class CycleDetectedException(TaskDAGException):
    """Raised when a circular dependency is detected in the TaskDAG."""
    pass


class NodeNotFoundException(TaskDAGException):
    """Raised when a referenced step_id does not exist in the TaskDAG."""
    pass


class TaskDAG:
    """
    Directed Acyclic Graph representing a multi-step task execution plan.
    Manages node dependencies, topological scheduling, and variable resolution.
    """

    def __init__(self, plan_id: str | None = None, goal: str = "") -> None:
        self.plan_id = plan_id or ""
        self.goal = goal
        self._nodes: dict[str, TaskNode] = {}
        # Forward edges: parent -> set of child step_ids
        self._dependents: dict[str, set[str]] = {}
        # Reverse edges: child -> set of parent step_ids
        self._dependencies: dict[str, set[str]] = {}

    @property
    def nodes(self) -> dict[str, TaskNode]:
        """Returns dictionary of all nodes in the DAG."""
        return self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, step_id: str) -> bool:
        return step_id in self._nodes

    def add_node(self, node: TaskNode) -> None:
        """
        Adds a TaskNode to the graph.
        
        Args:
            node: TaskNode instance.
            
        Raises:
            ValueError: If a node with the same step_id already exists.
        """
        if node.step_id in self._nodes:
            raise ValueError(f"Node with step_id '{node.step_id}' already exists in the DAG.")

        self._nodes[node.step_id] = node
        if node.step_id not in self._dependents:
            self._dependents[node.step_id] = set()
        if node.step_id not in self._dependencies:
            self._dependencies[node.step_id] = set()

        for parent_id in node.depends_on:
            self._dependencies[node.step_id].add(parent_id)
            if parent_id not in self._dependents:
                self._dependents[parent_id] = set()
            self._dependents[parent_id].add(node.step_id)

    def add_dependency(self, parent_id: str, child_id: str) -> None:
        """
        Adds a directed dependency edge from parent to child (child depends on parent).
        
        Args:
            parent_id: ID of the prerequisite step.
            child_id: ID of the dependent step.
        """
        if parent_id not in self._nodes:
            raise NodeNotFoundException(f"Parent node '{parent_id}' not found in DAG.")
        if child_id not in self._nodes:
            raise NodeNotFoundException(f"Child node '{child_id}' not found in DAG.")

        child_node = self._nodes[child_id]
        if parent_id not in child_node.depends_on:
            child_node.depends_on.append(parent_id)

        self._dependencies[child_id].add(parent_id)
        self._dependents[parent_id].add(child_id)

        if self.has_cycle():
            # Rollback
            child_node.depends_on.remove(parent_id)
            self._dependencies[child_id].remove(parent_id)
            self._dependents[parent_id].remove(child_id)
            raise CycleDetectedException(f"Adding dependency '{parent_id}' -> '{child_id}' creates a cycle.")

    def get_node(self, step_id: str) -> TaskNode | None:
        """Retrieves a TaskNode by its step_id, or None if not found."""
        return self._nodes.get(step_id)

    def has_cycle(self) -> bool:
        """
        Checks whether the graph contains any circular dependencies using DFS graph coloring.
        0 = UNVISITED, 1 = VISITING (in recursion stack), 2 = VISITED.
        """
        state: dict[str, int] = {step_id: 0 for step_id in self._nodes}

        def _dfs(u: str) -> bool:
            state[u] = 1  # VISITING
            for v in self._dependents.get(u, set()):
                if v not in state:
                    continue
                if state[v] == 1:
                    return True  # Found cycle
                if state[v] == 0:
                    if _dfs(v):
                        return True
            state[u] = 2  # VISITED
            return False

        for node_id in self._nodes:
            if state[node_id] == 0:
                if _dfs(node_id):
                    return True
        return False

    def validate(self) -> None:
        """
        Validates the DAG integrity:
        - Confirms all depends_on references point to existing nodes.
        - Asserts graph is strictly acyclic.
        
        Raises:
            NodeNotFoundException: If any depends_on references a missing node.
            CycleDetectedException: If graph contains a cycle.
        """
        for step_id, node in self._nodes.items():
            for parent_id in node.depends_on:
                if parent_id not in self._nodes:
                    raise NodeNotFoundException(
                        f"Node '{step_id}' depends on non-existent node '{parent_id}'."
                    )

        if self.has_cycle():
            raise CycleDetectedException("TaskDAG contains a circular dependency.")

    def topological_sort(self) -> list[list[TaskNode]]:
        """
        Calculates level-by-level topological waves of execution using Kahn's algorithm.
        Each inner list contains nodes that can be executed concurrently in parallel.
        
        Returns:
            List of levels, where each level is a list of independent TaskNodes.
            
        Raises:
            CycleDetectedException: If the graph contains a cycle.
        """
        self.validate()

        in_degree: dict[str, int] = {
            step_id: len([p for p in node.depends_on if p in self._nodes])
            for step_id, node in self._nodes.items()
        }

        current_level: list[str] = [sid for sid, deg in in_degree.items() if deg == 0]
        waves: list[list[TaskNode]] = []
        processed_count = 0

        while current_level:
            level_nodes = [self._nodes[sid] for sid in current_level]
            waves.append(level_nodes)
            processed_count += len(current_level)

            next_level: list[str] = []
            for u in current_level:
                for v in self._dependents.get(u, set()):
                    if v in in_degree:
                        in_degree[v] -= 1
                        if in_degree[v] == 0:
                            next_level.append(v)
            current_level = next_level

        if processed_count != len(self._nodes):
            raise CycleDetectedException("Cycle detected during topological sorting.")

        return waves

    def get_linear_topological_sort(self) -> list[TaskNode]:
        """Returns a flat, linearly ordered list of TaskNodes honoring dependencies."""
        waves = self.topological_sort()
        linear: list[TaskNode] = []
        for wave in waves:
            linear.extend(wave)
        return linear

    def get_ready_nodes(self) -> list[TaskNode]:
        """
        Finds all nodes ready for immediate execution:
        - Node status is PENDING, READY, or RETRYING.
        - All parent nodes in depends_on have status == COMPLETED.
        
        Returns:
            List of executable TaskNodes.
        """
        ready: list[TaskNode] = []
        for step_id, node in self._nodes.items():
            if node.status in (StepStatus.PENDING, StepStatus.READY, StepStatus.RETRYING):
                parents_completed = True
                for parent_id in node.depends_on:
                    parent_node = self._nodes.get(parent_id)
                    if not parent_node or parent_node.status != StepStatus.COMPLETED:
                        parents_completed = False
                        break
                if parents_completed:
                    ready.append(node)
        return ready

    def mark_node_status(
        self,
        step_id: str,
        status: StepStatus,
        result_data: Any = None,
        error_message: str | None = None,
        execution_time_ms: float = 0.0,
    ) -> None:
        """Updates status and result data of a specific node."""
        node = self._nodes.get(step_id)
        if not node:
            raise NodeNotFoundException(f"Node '{step_id}' not found in DAG.")
        node.status = status
        if result_data is not None:
            node.result_data = result_data
        if error_message is not None:
            node.error_message = error_message
        if execution_time_ms > 0:
            node.execution_time_ms = execution_time_ms

    def get_downstream_nodes(self, step_id: str) -> list[TaskNode]:
        """Returns all direct downstream dependents of a step."""
        child_ids = self._dependents.get(step_id, set())
        return [self._nodes[cid] for cid in child_ids if cid in self._nodes]

    def get_upstream_nodes(self, step_id: str) -> list[TaskNode]:
        """Returns all direct upstream prerequisite nodes of a step."""
        parent_ids = self._dependencies.get(step_id, set())
        return [self._nodes[pid] for pid in parent_ids if pid in self._nodes]

    def get_completed_outputs(self) -> dict[str, Any]:
        """
        Builds a comprehensive dictionary of all completed step outputs.
        Provides both direct access and structured namespaces:
        - context['steps']['step_1']['output']
        - context['steps']['step_1']['data']
        - context['steps']['step_1']['result_data']
        - context['nodes']['step_1']
        """
        steps_dict: dict[str, Any] = {}
        nodes_dict: dict[str, Any] = {}

        for sid, node in self._nodes.items():
            nodes_dict[sid] = node.to_dict()
            if node.status == StepStatus.COMPLETED:
                steps_dict[sid] = {
                    "output": node.result_data,
                    "data": node.result_data,
                    "result_data": node.result_data,
                    "result": node.result_data,
                    "status": node.status.value,
                    "execution_time_ms": node.execution_time_ms,
                }
            else:
                steps_dict[sid] = {
                    "output": None,
                    "data": None,
                    "result_data": None,
                    "result": None,
                    "status": node.status.value,
                    "execution_time_ms": node.execution_time_ms,
                }

        return {
            "steps": steps_dict,
            "nodes": nodes_dict,
            "goal": self.goal,
            "plan_id": self.plan_id,
        }

    def interpolate_node_params(
        self,
        node: TaskNode,
        additional_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Resolves variable references in node parameters using outputs from completed steps.
        
        Supported template formats:
        - `{{steps.<step_id>.output.<path>}}`
        - `{{steps.<step_id>.data.<path>}}`
        - `{{steps.<step_id>.output}}`
        - `{{context.<key>}}`
        - `{{goal}}`
        
        Args:
            node: Target TaskNode whose parameters are to be interpolated.
            additional_context: Optional dictionary of additional context variables.
            
        Returns:
            Dictionary of interpolated parameters.
        """
        full_context = self.get_completed_outputs()
        if additional_context:
            full_context.update(additional_context)
            if "context" not in full_context:
                full_context["context"] = additional_context

        return interpolate_parameters(node.parameters, full_context)

    def is_finished(self) -> bool:
        """Returns True if all nodes have reached a terminal state."""
        terminal_states = {
            StepStatus.COMPLETED,
            StepStatus.FAILED,
            StepStatus.SKIPPED,
            StepStatus.BLOCKED,
        }
        return all(node.status in terminal_states for node in self._nodes.values())

    def is_successful(self) -> bool:
        """Returns True if execution succeeded (no failed/blocked nodes, and at least one completed)."""
        if not self._nodes:
            return False
        has_completed = any(node.status == StepStatus.COMPLETED for node in self._nodes.values())
        has_failure = any(node.status in (StepStatus.FAILED, StepStatus.BLOCKED) for node in self._nodes.values())
        return has_completed and not has_failure

    def has_failures(self) -> bool:
        """Returns True if any node failed or was blocked."""
        return any(node.status in (StepStatus.FAILED, StepStatus.BLOCKED) for node in self._nodes.values())

    def reset(self) -> None:
        """Resets all nodes to PENDING state and clears results."""
        for node in self._nodes.values():
            node.status = StepStatus.PENDING
            node.result_data = None
            node.error_message = None
            node.retry_count = 0
            node.confirmation_token = None
            node.execution_time_ms = 0.0
            node.started_at = None
            node.finished_at = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the entire TaskDAG to a dictionary."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "nodes": [node.to_dict() for node in self._nodes.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskDAG:
        """Constructs a TaskDAG from a dictionary."""
        dag = cls(plan_id=data.get("plan_id"), goal=data.get("goal", ""))
        for raw_node in data.get("nodes", []):
            if isinstance(raw_node, dict):
                node = TaskNode.from_dict(raw_node)
                dag.add_node(node)
            elif isinstance(raw_node, TaskNode):
                dag.add_node(raw_node)
        return dag

    def to_json(self, indent: int = 2) -> str:
        """Serializes TaskDAG to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> TaskDAG:
        """Constructs TaskDAG from JSON string."""
        return cls.from_dict(json.loads(json_str))


def _lookup_path(path: str, context: dict[str, Any]) -> Any:
    """
    Traverses a dot/bracket separated path into a nested dictionary/list structure.
    Examples:
        'steps.step_1.output.file_path'
        'steps.step_2.data[0].id'
        'context.user_id'
    """
    # Tokenize by dot or bracket notation e.g. "a[0].b" -> ["a", 0, "b"]
    tokens = []
    for part in path.split("."):
        # Check for bracket indices e.g. "output[0]"
        bracket_parts = re.findall(r"([^\[\]]+)|\[(\d+)\]", part)
        for name, idx in bracket_parts:
            if name:
                tokens.append(name)
            elif idx:
                tokens.append(int(idx))

    curr: Any = context
    for token in tokens:
        if isinstance(curr, dict):
            if str(token) in curr:
                curr = curr[str(token)]
            else:
                return None
        elif isinstance(curr, (list, tuple)):
            try:
                idx = int(token)
                if 0 <= idx < len(curr):
                    curr = curr[idx]
                else:
                    return None
            except (ValueError, IndexError):
                return None
        elif hasattr(curr, str(token)):
            curr = getattr(curr, str(token))
        else:
            return None

    return curr


def interpolate_parameters(params: Any, context: dict[str, Any]) -> Any:
    """
    Recursively replaces `{{path}}` expressions in dictionary values, lists, or strings
    with resolved values from the execution context.
    
    If the template is an exact full-string match (e.g. `"{{steps.s1.output}}"`),
    the returned value preserves the exact Python object type (e.g., dict, list, int).
    If the template is part of a longer string (e.g. `"file_{{steps.s1.output.id}}.csv"`),
    it is formatted as a string.
    """
    pattern = re.compile(r"\{\{([^}]+)\}\}")

    def _resolve_val(val: Any) -> Any:
        if isinstance(val, str):
            trimmed = val.strip()
            full_match = pattern.fullmatch(trimmed)
            if full_match:
                expr = full_match.group(1).strip()
                resolved = _lookup_path(expr, context)
                return resolved if resolved is not None else val

            # Substring replacement
            def _sub_repl(m: re.Match) -> str:
                expr = m.group(1).strip()
                res = _lookup_path(expr, context)
                return str(res) if res is not None else m.group(0)

            return pattern.sub(_sub_repl, val)

        elif isinstance(val, dict):
            return {k: _resolve_val(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [_resolve_val(item) for item in val]
        elif isinstance(val, tuple):
            return tuple(_resolve_val(item) for item in val)
        return val

    return _resolve_val(params)
