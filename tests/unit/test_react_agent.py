"""
tests/unit/test_react_agent.py
=================================
Unit tests for ReActAgent (mock mode — no real LLM calls).
"""
from __future__ import annotations

import inspect

import pytest

from jarvis.agent.graph import AgentState, AgentTask, ReActAgent, Tool
from jarvis.agent.tool_runtime import ToolExecutionResult
from jarvis.sandbox.interpreter import SandboxResult


@pytest.fixture
def agent():
    return ReActAgent(is_mock=True, max_iterations=5)


@pytest.fixture
def agent_with_tool():
    results = []
    def my_tool(query="", **kw):
        results.append(query)
        return {"output": f"Result for: {query}"}
    a = ReActAgent(is_mock=True)
    a.register_tool("my_tool", "Test tool", my_tool)
    a._results = results
    return a


class TestAgentInit:
    def test_agent_has_default_tools(self, agent):
        assert len(agent.tools) >= 10

    def test_agent_tools_are_callable(self, agent):
        for tool in agent.tools.values():
            assert callable(tool.fn)

    def test_register_custom_tool(self, agent):
        agent.register_tool("custom", "desc", lambda **kw: {"output": "ok"})
        assert "custom" in agent.tools


class TestMockRun:
    def test_run_returns_task(self, agent):
        task = agent.run("Tóm tắt tin tức hôm nay")
        assert isinstance(task, AgentTask)

    def test_mock_task_is_done(self, agent):
        task = agent.run("Test goal")
        assert task.state == AgentState.DONE

    def test_mock_task_has_steps(self, agent):
        task = agent.run("Phân tích tài liệu")
        assert len(task.steps) >= 3  # thought, action, observation, reflection

    def test_mock_task_has_result(self, agent):
        task = agent.run("Tìm kiếm thông tin")
        assert task.result != ""
        assert "MOCK" in task.result or task.goal in task.result

    def test_mock_task_has_task_id(self, agent):
        task = agent.run("Any goal")
        assert task.task_id != ""

    def test_task_stored_in_registry(self, agent):
        task = agent.run("Test task")
        retrieved = agent.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

    def test_completed_at_set(self, agent):
        task = agent.run("Quick task")
        assert task.completed_at > 0


class TestListTasks:
    def test_list_tasks_empty_initially(self):
        fresh_agent = ReActAgent(is_mock=True)
        assert fresh_agent.list_tasks() == []

    def test_list_tasks_after_run(self, agent):
        agent.run("Task A")
        agent.run("Task B")
        tasks = agent.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_contain_goal(self, agent):
        agent.run("My specific goal 123")
        tasks = agent.list_tasks()
        goals = [t["goal"] for t in tasks]
        assert any("specific goal" in g for g in goals)


class TestBuiltinTools:
    def test_read_file_tool_returns_string(self, agent):
        result = agent._tool_read_file(path="README.md")
        assert isinstance(result, dict)
        assert "output" in result

    def test_write_file_tool(self, agent, tmp_path):
        path = str(tmp_path / "test_out.txt")
        result = agent._tool_write_file(path=path, content="Hello JARVIS")
        assert result["output"] != ""

    def test_run_python_simple(self, agent):
        result = agent._tool_run_python(code="x = 2 + 2\nresult = x")
        assert "4" in result["output"] or "thành công" in result["output"]

    def test_run_python_syntax_error(self, agent):
        result = agent._tool_run_python(code="def broken(")
        assert "Lỗi" in result["output"] or "error" in result["output"].lower()

    def test_list_dir_tool(self, agent):
        result = agent._tool_list_dir(path=".")
        assert isinstance(result["output"], str)
        assert len(result["output"]) > 0


class TestHeuristicThink:
    def test_heuristic_search_goal(self, agent):
        from jarvis.agent.graph import AgentState, AgentTask
        task = AgentTask(task_id="t1", goal="tìm kiếm tin tức AI")
        thought, tool, args = agent._heuristic_think(task)
        assert tool == "web_search"

    def test_heuristic_note_goal(self, agent):
        from jarvis.agent.graph import AgentTask
        task = AgentTask(task_id="t2", goal="ghi chú họp lúc 3h")
        thought, tool, args = agent._heuristic_think(task)
        assert tool == "take_note"

    def test_heuristic_done_when_steps_exist(self, agent):
        from jarvis.agent.graph import AgentTask, ThoughtStep
        task = AgentTask(task_id="t3", goal="unknown task with no keyword")
        task.steps.append(ThoughtStep("thought", "some thought"))
        thought, tool, args = agent._heuristic_think(task)
        assert tool == "DONE"


class _FakeSandbox:
    """Deterministic CodeInterpreterSandbox double — never spawns a real process."""

    DEFAULT_TIMEOUT_SECONDS = 15.0

    def __init__(self, result: SandboxResult):
        self._result = result
        self.calls: list[dict] = []

    def execute_python(self, code, timeout_seconds=None, **kw):
        self.calls.append({"code": code, "timeout_seconds": timeout_seconds})
        return self._result


class TestSandboxedPythonExecution:
    """
    Required outcome 1: generated Python must never go through a raw
    exec()/eval() inside this process — it must route through the existing,
    unmodified CodeInterpreterSandbox.
    """

    def test_run_python_source_never_calls_builtin_exec_or_eval(self):
        source = inspect.getsource(ReActAgent._tool_run_python)
        assert "exec(" not in source
        assert "eval(" not in source

    def test_run_python_uses_injected_sandbox_instance(self):
        fake_result = SandboxResult(success=True, exit_code=0, stdout="hello\n", stderr="")
        fake_sandbox = _FakeSandbox(fake_result)
        agent = ReActAgent(is_mock=True, sandbox=fake_sandbox)

        result = agent._tool_run_python(code="print('hello')")

        assert len(fake_sandbox.calls) == 1
        assert "print('hello')" in fake_sandbox.calls[0]["code"]
        assert result["success"] is True
        assert "hello" in result["output"]

    def test_run_python_safe_code_becomes_observation(self, agent):
        """Real sandbox integration: a safe script's result becomes a clean observation."""
        observation = agent._act("run_python", {"code": "result = 6 * 7"})
        assert "42" in observation
        assert "Lỗi" not in observation

    def test_run_python_sandbox_rejection_becomes_failed_observation(self, agent):
        """A script the sandbox's own AST validator rejects must surface as a
        failed observation, never as a silent success."""
        observation = agent._act("run_python", {"code": "import subprocess"})
        assert "Lỗi" in observation
        assert "forbidden" in observation.lower()

    def test_run_python_timeout_becomes_failed_observation(self, agent):
        """Real sandbox integration: a script that outruns its timeout must be
        reported as a bounded failure, not hang the agent or crash it."""
        observation = agent._act(
            "run_python",
            {"code": "import time as _t\n_t.sleep(5)", "timeout_seconds": 0.5},
        )
        assert "Lỗi" in observation
        assert "timed out" in observation.lower() or "timeout" in observation.lower()

    def test_run_python_huge_stdout_is_bounded_before_reaching_observation(self):
        """
        A sandbox call that legitimately succeeds with a very large stdout
        must never be injected into agent history unbounded. Uses a fake
        sandbox so this is deterministic and fast regardless of the real
        sandbox's own performance characteristics.
        """
        huge_stdout = "z" * 100_000
        fake_result = SandboxResult(success=True, exit_code=0, stdout=huge_stdout, stderr="")
        fake_sandbox = _FakeSandbox(fake_result)
        agent = ReActAgent(is_mock=True, sandbox=fake_sandbox)

        observation = agent._act("run_python", {"code": "result = 'z' * 100000"})

        assert len(observation) < len(huge_stdout)
        assert "[TRUNCATED" in observation

    def test_run_python_timeout_is_clamped_to_a_sane_maximum(self):
        """An absurdly large requested timeout must be clamped, not passed through verbatim."""
        fake_result = SandboxResult(success=True, exit_code=0, stdout="ok", stderr="")
        fake_sandbox = _FakeSandbox(fake_result)
        agent = ReActAgent(is_mock=True, sandbox=fake_sandbox)

        agent._tool_run_python(code="pass", timeout_seconds=99999.0)

        assert fake_sandbox.calls[0]["timeout_seconds"] <= 30.0


class TestToolExecutionContract:
    """
    Required outcome 2/3: a small structured tool-execution boundary with
    deterministic failure for unknown tools/malformed args, and an
    exception in any tool must never crash the agent loop.
    """

    def test_unknown_tool_fails_deterministically(self, agent):
        result = agent._execute_tool("does_not_exist", {})
        assert isinstance(result, ToolExecutionResult)
        assert result.success is False
        assert "không tồn tại" in result.error

        observation = agent._act("does_not_exist", {})
        assert "không tồn tại" in observation

    def test_malformed_non_dict_args_fail_gracefully(self, agent):
        result = agent._execute_tool("calculator", "not-a-dict")  # type: ignore[arg-type]
        assert result.success is False
        assert result.error is not None

        # Must not raise even when routed through the full _act() path.
        observation = agent._act("calculator", "not-a-dict")  # type: ignore[arg-type]
        assert isinstance(observation, str)

    def test_malformed_none_args_fail_gracefully(self, agent):
        result = agent._execute_tool("calculator", None)  # type: ignore[arg-type]
        assert result.success is False

    def test_tool_exception_does_not_crash_agent(self, agent):
        def exploding_tool(**kw):
            raise RuntimeError("simulated tool crash")

        agent.register_tool("boom", "explodes", exploding_tool)
        result = agent._execute_tool("boom", {})
        assert result.success is False
        assert "simulated tool crash" in result.error

        observation = agent._act("boom", {})
        assert "Lỗi" in observation

    def test_tool_returning_structured_result_is_passed_through(self, agent):
        def structured_tool(**kw):
            return ToolExecutionResult(success=True, output="structured ok")

        agent.register_tool("structured", "returns ToolExecutionResult", structured_tool)
        observation = agent._act("structured", {})
        assert observation == "structured ok"

    def test_tool_output_is_bounded_for_any_tool_not_just_run_python(self, agent):
        def verbose_tool(**kw):
            return {"output": "v" * 50_000}

        agent.register_tool("verbose", "produces huge output", verbose_tool)
        observation = agent._act("verbose", {})
        assert len(observation) < 50_000
        assert "[TRUNCATED" in observation


class TestAgentLifecycle:
    """Required outcome 3: max_iterations stays bounded and task state
    transitions remain coherent, even when the agent never decides DONE."""

    def test_max_iterations_terminates_and_reaches_done(self, monkeypatch):
        agent = ReActAgent(is_mock=False, max_iterations=4)
        call_count = {"n": 0}

        def never_done(task):
            call_count["n"] += 1
            return ("thinking...", "calculator", {"expression": "1+1"})

        monkeypatch.setattr(agent, "_think", never_done)
        task = agent.run("goal that never terminates on its own")

        assert call_count["n"] == 4  # exactly max_iterations, never more
        assert task.state == AgentState.DONE
        assert task.completed_at > 0

    def test_run_catches_exception_and_sets_failed_state(self, monkeypatch):
        agent = ReActAgent(is_mock=False, max_iterations=3)

        def exploding_think(task):
            raise RuntimeError("simulated planner crash")

        monkeypatch.setattr(agent, "_think", exploding_think)
        task = agent.run("goal")

        assert task.state == AgentState.FAILED
        assert "simulated planner crash" in task.error

    def test_normal_completion_reaches_done_via_reflection(self, monkeypatch):
        agent = ReActAgent(is_mock=False, max_iterations=5)

        def immediately_done(task):
            return ("done thinking", "DONE", {})

        monkeypatch.setattr(agent, "_think", immediately_done)
        task = agent.run("goal")

        assert task.state == AgentState.DONE
        assert any(s.step_type == "reflection" for s in task.steps)

    def test_existing_mock_mode_still_deterministic_and_unaffected(self):
        """Mock mode must remain fully deterministic and must not touch the sandbox at all."""
        agent = ReActAgent(is_mock=True)
        task = agent.run("some goal")
        assert task.state == AgentState.DONE
        assert agent._sandbox is None  # never constructed since run_python was never called
