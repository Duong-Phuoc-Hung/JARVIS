"""
tests/unit/test_react_agent.py
=================================
Unit tests for ReActAgent (mock mode — no real LLM calls).
"""
from __future__ import annotations
import pytest
from jarvis.agent.graph import ReActAgent, AgentTask, AgentState, Tool


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
        from jarvis.agent.graph import AgentTask, AgentState
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
