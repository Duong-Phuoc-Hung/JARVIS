"""
jarvis/agent/graph.py
=======================
LangGraph ReAct Autonomous Agent — JARVIS v4.0 Full Autonomous Mode.

Architecture: Think → Act → Observe → Reflect → Done
Uses LangGraph StateGraph với tool calling và memory injection.

Lệnh kích hoạt:
  "JARVIS, bật chế độ tự trị"
  "Phân tích và tối ưu hóa code trong folder src/ cho tôi"
  "Nghiên cứu về LLM agents và tổng hợp báo cáo"
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from jarvis.agent.tool_runtime import (
    DEFAULT_MAX_OBSERVATION_CHARS,
    MAX_PYTHON_EXEC_TIMEOUT_SECONDS,
    ToolExecutionResult,
    format_observation,
    normalize_tool_output,
    sandbox_result_to_tool_result,
)
from jarvis.sandbox.interpreter import CodeInterpreterSandbox

log = logging.getLogger("jarvis.agent.graph")


class AgentState(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    REFLECTING = "reflecting"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ThoughtStep:
    step_type: str      # "thought" | "action" | "observation" | "reflection"
    content: str
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentTask:
    task_id: str
    goal: str
    steps: list[ThoughtStep] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    result: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    max_iterations: int = 10


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable
    args_schema: dict[str, str] = field(default_factory=dict)


class ReActAgent:
    """
    LangGraph-compatible ReAct Agent for JARVIS.
    Implements Think → Act → Observe → Reflect loop.
    Falls back to simple tool dispatch if LangGraph not installed.
    """

    def __init__(
        self,
        tools: list[Tool] | None = None,
        max_iterations: int = 10,
        is_mock: bool = False,
        sandbox: CodeInterpreterSandbox | None = None,
    ) -> None:
        self.tools: dict[str, Tool] = {t.name: t for t in (tools or [])}
        self.max_iterations = max_iterations
        self.is_mock = is_mock
        self._tasks: dict[str, AgentTask] = {}
        self._sandbox = sandbox
        self._register_default_tools()
        log.info("ReActAgent initialized with %d tools (mock=%s)", len(self.tools), is_mock)

    def _get_sandbox(self) -> CodeInterpreterSandbox:
        """Lazily construct the default CodeInterpreterSandbox (only when run_python is actually used)."""
        if self._sandbox is None:
            self._sandbox = CodeInterpreterSandbox(cleanup_on_exit=True)
        return self._sandbox

    # ------------------------------------------------------------------
    # Tool Registry
    # ------------------------------------------------------------------

    def _register_default_tools(self) -> None:
        """Register all 21 JARVIS skills as agent tools."""
        skill_tools = [
            ("web_search", "Tìm kiếm Google", self._tool_web_search),
            ("take_note", "Ghi chú nhanh", self._tool_take_note),
            ("read_file", "Đọc nội dung file", self._tool_read_file),
            ("write_file", "Ghi dữ liệu vào file", self._tool_write_file),
            ("run_python", "Chạy code Python an toàn", self._tool_run_python),
            ("browser_open", "Mở trình duyệt và điều hướng", self._tool_browser),
            ("screenshot", "Chụp ảnh màn hình", self._tool_screenshot),
            ("calculator", "Tính toán biểu thức", self._tool_calc),
            ("memory_search", "Tìm kiếm trong ký ức JARVIS", self._tool_memory_search),
            ("send_telegram", "Gửi thông báo Telegram", self._tool_send_telegram),
            ("list_dir", "Liệt kê nội dung thư mục", self._tool_list_dir),
            ("git_status", "Trạng thái Git repository", self._tool_git_status),
        ]
        for name, desc, fn in skill_tools:
            self.tools[name] = Tool(name=name, description=desc, fn=fn)

    def register_tool(self, name: str, description: str, fn: Callable, args_schema: dict | None = None) -> None:
        self.tools[name] = Tool(name=name, description=description, fn=fn, args_schema=args_schema or {})

    # ------------------------------------------------------------------
    # Core: Run Task
    # ------------------------------------------------------------------

    def run(self, goal: str) -> AgentTask:
        """Run a goal through the ReAct loop. Returns completed AgentTask."""
        task_id = str(uuid.uuid4())[:8]
        task = AgentTask(task_id=task_id, goal=goal, max_iterations=self.max_iterations)
        self._tasks[task_id] = task

        if self.is_mock:
            return self._mock_run(task)

        log.info("Agent starting task %s: %s", task_id, goal[:80])
        task.state = AgentState.THINKING
        try:
            self._react_loop(task)
        except Exception as exc:
            task.state = AgentState.FAILED
            task.error = str(exc)
            log.error("Agent task %s failed: %s", task_id, exc)
        return task

    def _react_loop(self, task: AgentTask) -> None:
        """Main ReAct iteration loop: Think → Act → Observe → Reflect."""
        for iteration in range(task.max_iterations):
            # 1. THINK: generate next action
            task.state = AgentState.THINKING
            thought, tool_name, tool_args = self._think(task)
            task.steps.append(ThoughtStep("thought", thought))
            log.debug("Iteration %d | Thought: %s | Tool: %s", iteration + 1, thought[:80], tool_name)

            if not tool_name or tool_name == "DONE":
                # Agent decided it's done
                task.state = AgentState.REFLECTING
                reflection = self._reflect(task)
                task.steps.append(ThoughtStep("reflection", reflection))
                task.result = reflection
                task.state = AgentState.DONE
                task.completed_at = time.time()
                log.info("Task %s completed after %d iterations", task.task_id, iteration + 1)
                return

            # 2. ACT: call the tool
            task.state = AgentState.ACTING
            action_step = ThoughtStep("action", f"Gọi tool: {tool_name}", tool_name, tool_args)
            task.steps.append(action_step)

            # 3. OBSERVE: collect result
            task.state = AgentState.OBSERVING
            observation = self._act(tool_name, tool_args)
            action_step.tool_result = observation
            task.steps.append(ThoughtStep("observation", observation))
            log.debug("Observation: %s", observation[:100])

        # Max iterations reached
        task.state = AgentState.DONE
        task.result = self._summarize_steps(task)
        task.completed_at = time.time()
        log.info("Task %s reached max iterations", task.task_id)

    def _think(self, task: AgentTask) -> tuple[str, str, dict[str, Any]]:
        """Generate next thought + tool call using LLM."""
        # Build context
        context = self._build_context(task)

        try:
            # Try LangGraph / Gemini
            from jarvis.llm.client import LLMClient
            client = LLMClient()
            # Build ReAct prompt
            react_prompt = (
                f"Mục tiêu: {task.goal}\n\n"
                f"Lịch sử:\n{context}\n\n"
                f"Công cụ có sẵn: {', '.join(self.tools.keys())}\n\n"
                f"Hãy quyết định bước tiếp theo. "
                f"Trả lời theo format:\n"
                f"Suy nghĩ: <lý do>\n"
                f"Hành động: <tên tool hoặc DONE>\n"
                f"Tham số: <json hoặc text>"
            )
            response = client.generate(react_prompt).content
            return self._parse_react_response(response)
        except Exception as exc:
            log.debug("LLM think error: %s", exc)
            # Simple heuristic fallback
            return self._heuristic_think(task)

    def _heuristic_think(self, task: AgentTask) -> tuple[str, str, dict[str, Any]]:
        """Simple keyword-based tool selection when LLM unavailable."""
        goal_lower = task.goal.lower()
        if not task.steps:
            # First step: analyze the goal
            if any(k in goal_lower for k in ["tìm", "search", "tra cứu"]):
                return ("Cần tìm kiếm thông tin", "web_search", {"query": task.goal})
            elif any(k in goal_lower for k in ["ghi chú", "note", "lưu"]):
                return ("Cần ghi chú", "take_note", {"text": task.goal})
            elif any(k in goal_lower for k in ["đọc", "file", "read"]):
                return ("Cần đọc file", "read_file", {"path": "."})
            elif any(k in goal_lower for k in ["mở", "browser", "chrome"]):
                return ("Cần mở trình duyệt", "browser_open", {"url": task.goal})
            elif any(k in goal_lower for k in ["tính", "calc"]):
                return ("Cần tính toán", "calculator", {"expression": task.goal})
        # Default: done
        return ("Đã hoàn thành phân tích", "DONE", {})

    def _parse_react_response(self, response: str) -> tuple[str, str, dict[str, Any]]:
        """Parse LLM ReAct response into (thought, tool_name, args)."""
        lines = response.strip().splitlines()
        thought = ""
        tool_name = "DONE"
        args: dict[str, Any] = {}
        for line in lines:
            if line.startswith("Suy nghĩ:") or line.startswith("Thought:"):
                thought = line.split(":", 1)[-1].strip()
            elif line.startswith("Hành động:") or line.startswith("Action:"):
                tool_name = line.split(":", 1)[-1].strip()
            elif line.startswith("Tham số:") or line.startswith("Input:"):
                raw = line.split(":", 1)[-1].strip()
                try:
                    import json
                    args = json.loads(raw)
                except Exception:
                    args = {"query": raw}
        return thought or "Phân tích tiếp theo...", tool_name, args

    def _act(self, tool_name: str, args: dict[str, Any]) -> str:
        """Execute a tool and return a bounded, deterministic string observation."""
        result = self._execute_tool(tool_name, args)
        return format_observation(result, max_chars=DEFAULT_MAX_OBSERVATION_CHARS)

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
        """
        Structured tool-execution boundary: unknown tools and malformed args
        fail deterministically, and a tool exception can never escape and
        crash the agent loop.
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolExecutionResult(success=False, output="", error=f"Tool '{tool_name}' không tồn tại.")
        if not isinstance(args, dict):
            return ToolExecutionResult(
                success=False,
                output="",
                error=f"Tham số không hợp lệ cho tool '{tool_name}': cần object/dict, nhận {type(args).__name__}.",
            )
        try:
            raw = tool.fn(**args)
        except Exception as exc:
            return ToolExecutionResult(success=False, output="", error=f"Lỗi tool {tool_name}: {exc}")
        return normalize_tool_output(raw)

    def _reflect(self, task: AgentTask) -> str:
        """Generate final summary from all steps."""
        observations = [s.tool_result for s in task.steps if s.step_type == "observation" and s.tool_result]
        if not observations:
            return f"Đã xử lý mục tiêu: {task.goal}"
        return f"Kết quả cho '{task.goal}':\n\n" + "\n".join(f"• {obs[:200]}" for obs in observations[-3:])

    def _summarize_steps(self, task: AgentTask) -> str:
        actions = [(s.tool_name, s.tool_result) for s in task.steps if s.step_type == "action"]
        return f"Hoàn thành {len(actions)} bước cho: {task.goal}"

    def _build_context(self, task: AgentTask) -> str:
        lines = []
        for s in task.steps[-6:]:  # Last 6 steps
            if s.step_type == "thought":
                lines.append(f"Suy nghĩ: {s.content[:150]}")
            elif s.step_type == "action":
                lines.append(f"Hành động: {s.tool_name}({s.tool_args})")
            elif s.step_type == "observation":
                lines.append(f"Quan sát: {s.content[:150]}")
        return "\n".join(lines) if lines else "Chưa có lịch sử"

    def _mock_run(self, task: AgentTask) -> AgentTask:
        """Return a mock completed task."""
        task.steps = [
            ThoughtStep("thought", f"Phân tích mục tiêu: {task.goal}"),
            ThoughtStep("action", "Gọi web_search", "web_search", {"query": task.goal}),
            ThoughtStep("observation", "Mock kết quả từ web_search"),
            ThoughtStep("reflection", f"Đã hoàn thành mock task cho: {task.goal}"),
        ]
        task.result = f"[MOCK] Đã xử lý: {task.goal}"
        task.state = AgentState.DONE
        task.completed_at = time.time()
        return task

    # ------------------------------------------------------------------
    # Built-in Tools
    # ------------------------------------------------------------------

    def _tool_web_search(self, query: str = "", **kw) -> dict:
        try:
            from jarvis.skills.briefing import execute as b
            return b(action="news", query=query)
        except Exception:
            return {"output": f"Tìm kiếm: {query} (web không khả dụng trong mock)"}

    def _tool_take_note(self, text: str = "", **kw) -> dict:
        try:
            from jarvis.skills.note_taker import execute as n
            return n(action="add", text=text)
        except Exception:
            return {"output": f"Ghi chú: {text}"}

    def _tool_read_file(self, path: str = ".", **kw) -> dict:
        from pathlib import Path
        try:
            p = Path(path)
            if p.is_file():
                return {"output": p.read_text(encoding="utf-8")[:2000]}
            return {"output": str(list(p.iterdir())[:20]) if p.is_dir() else "Không tìm thấy"}
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_write_file(self, path: str = "", content: str = "", **kw) -> dict:
        from pathlib import Path
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding="utf-8")
            return {"output": f"Đã ghi file: {path}"}
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_run_python(self, code: str = "", timeout_seconds: float | None = None, **kw) -> dict:
        """
        Execute Python code through the existing, unmodified
        CodeInterpreterSandbox (AST validation, isolated scratch dir,
        OS Restricted Token isolation, timeout/resource bounds) -- never a
        raw in-process dynamic code evaluation of any kind.
        """
        bounded_timeout = min(
            timeout_seconds if timeout_seconds is not None else CodeInterpreterSandbox.DEFAULT_TIMEOUT_SECONDS,
            MAX_PYTHON_EXEC_TIMEOUT_SECONDS,
        )
        # Best-effort capture of a top-level `result` variable, mirroring the
        # convention of the prior implementation, without using any
        # AST-forbidden introspection call (locals()/globals()/vars() are
        # all rejected by the sandbox's static validator).
        wrapped_code = f"{code}\n\ntry:\n    print(result)\nexcept NameError:\n    pass\n"
        sandbox_result = self._get_sandbox().execute_python(wrapped_code, timeout_seconds=bounded_timeout)
        tool_result = sandbox_result_to_tool_result(sandbox_result)
        # "output" always carries the human-facing text (success or failure),
        # preserving the pre-sandbox tool's contract; "success"/"error"/
        # "metadata" are additive fields for the new structured boundary.
        output_text = tool_result.output if tool_result.success else format_observation(tool_result)
        return {
            "success": tool_result.success,
            "output": output_text,
            "error": tool_result.error,
            "metadata": tool_result.metadata,
        }

    def _tool_browser(self, url: str = "", **kw) -> dict:
        try:
            from jarvis.skills.browser_control import execute as br
            return br(action="open", url=url)
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_screenshot(self, **kw) -> dict:
        try:
            from jarvis.skills.system_control import execute as sc
            return sc(action="screenshot")
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_calc(self, expression: str = "", **kw) -> dict:
        try:
            from jarvis.skills.calculator import execute as c
            return c(action="calculate", expression=expression)
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_memory_search(self, query: str = "", **kw) -> dict:
        try:
            from jarvis.memory.manager import MemoryManager
            mgr = MemoryManager()
            results = mgr.semantic_search(query)
            return {"output": str(results[:3])}
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_send_telegram(self, message: str = "", **kw) -> dict:
        try:
            import os

            from jarvis.comms.telegram import TelegramBotController
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")
            if not chat_id:
                return {"output": "Telegram: TELEGRAM_CHAT_ID not configured"}
            tg = TelegramBotController(bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
            tg.send_message(int(chat_id), message)
            return {"output": f"Telegram: {message[:60]}"}
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_list_dir(self, path: str = ".", **kw) -> dict:
        from pathlib import Path
        try:
            items = [str(p.name) for p in Path(path).iterdir()][:20]
            return {"output": "\n".join(items)}
        except Exception as exc:
            return {"output": str(exc)}

    def _tool_git_status(self, **kw) -> dict:
        import subprocess
        import sys
        try:
            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5, creationflags=_cflags)
            return {"output": r.stdout or "Working tree clean"}
        except Exception as exc:
            return {"output": str(exc)}

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        return [
            {"task_id": t.task_id, "goal": t.goal[:80], "state": t.state.value,
             "steps": len(t.steps), "result": t.result[:100]}
            for t in self._tasks.values()
        ]


__all__ = ["ReActAgent", "AgentTask", "AgentState", "ThoughtStep", "Tool"]
