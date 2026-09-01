"""
tests/unit/test_night_planner.py
==================================
Unit tests for Night Shift Worker and Night Planner skill.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.workers.night_shift import NightShiftTask, NightShiftWorker


@pytest.fixture
def worker(tmp_path, monkeypatch):
    import jarvis.workers.night_shift as mod
    monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")
    return NightShiftWorker(is_mock=True)


class TestAddTask:
    def test_add_task_returns_task_object(self, worker):
        task = worker.add_task("Test Task", "Phân tích dữ liệu")
        assert isinstance(task, NightShiftTask)
        assert task.task_id != ""
        assert task.title == "Test Task"

    def test_add_task_has_unique_id(self, worker):
        t1 = worker.add_task("Task 1", "Mô tả 1")
        t2 = worker.add_task("Task 2", "Mô tả 2")
        assert t1.task_id != t2.task_id

    def test_add_task_default_status_pending(self, worker):
        task = worker.add_task("Pending Task", "test")
        assert task.status == "pending"

    def test_add_task_scheduled_time_stored(self, worker):
        task = worker.add_task("Scheduled", "test", scheduled_time="22:30")
        assert task.scheduled_time == "22:30"


class TestDecomposeTask:
    def test_decompose_web_search_step(self, worker):
        steps = worker.decompose_task("tìm kiếm thông tin về AI năm 2026")
        assert len(steps) >= 1
        assert any("web_search" in s.lower() or "tìm" in s.lower() for s in steps)

    def test_decompose_report_step(self, worker):
        steps = worker.decompose_task("tạo báo cáo tổng hợp tuần này")
        assert len(steps) >= 1

    def test_decompose_returns_list(self, worker):
        steps = worker.decompose_task("phân tích dữ liệu và lưu kết quả")
        assert isinstance(steps, list)
        assert len(steps) > 0

    def test_decompose_empty_description_fallback(self, worker):
        steps = worker.decompose_task("x")
        assert isinstance(steps, list)
        assert len(steps) >= 1


class TestListTasks:
    def test_list_includes_added_tasks(self, worker):
        worker.add_task("Task A", "mô tả A")
        tasks = worker.list_tasks()
        assert len(tasks) >= 1
        assert any(t.title == "Task A" for t in tasks)

    def test_list_empty_when_no_tasks(self, worker):
        tasks = worker.list_tasks()
        assert isinstance(tasks, list)


class TestCancelTask:
    def test_cancel_pending_task_succeeds(self, worker):
        task = worker.add_task("To Cancel", "test")
        ok = worker.cancel_task(task.task_id)
        assert ok is True

    def test_cancel_changes_status_to_cancelled(self, worker):
        task = worker.add_task("Cancel Me", "test")
        worker.cancel_task(task.task_id)
        tasks = worker.list_tasks()
        match = next((t for t in tasks if t.task_id == task.task_id), None)
        assert match is not None
        assert match.status == "cancelled"

    def test_cancel_nonexistent_returns_false(self, worker):
        ok = worker.cancel_task("nonexistent_id_xyz")
        assert ok is False


class TestGenerateReport:
    def test_report_contains_task_title(self, worker):
        task = worker.add_task("My Report Task", "Mô tả tác vụ kiểm tra")
        task.steps = ["[auto] bước 1"]
        task.status = "completed"
        task.result = {
            "steps_completed": 1, "all_success": True,
            "elapsed_s": 2.5, "step_results": [{"success": True, "type": "auto", "result": "OK"}]
        }
        report = worker.generate_report(task)
        assert "My Report Task" in report
        assert "completed" in report.lower() or "✅" in report

    def test_report_is_markdown_string(self, worker):
        task = worker.add_task("MD Task", "test")
        task.status = "failed"
        task.result = {"steps_completed": 0, "all_success": False, "elapsed_s": 0, "step_results": []}
        report = worker.generate_report(task)
        assert isinstance(report, str)
        assert "#" in report  # Has markdown headers


class TestNightShiftSandboxing:
    def test_night_shift_worker_initializes_sandbox(self, tmp_path, monkeypatch):
        import jarvis.workers.night_shift as mod
        from jarvis.sandbox.interpreter import CodeInterpreterSandbox
        monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")

        worker = NightShiftWorker(is_mock=False, sandbox_dir=tmp_path / "sandbox_scratch")
        assert isinstance(worker.sandbox, CodeInterpreterSandbox)
        assert worker.sandbox.base_scratch_dir.resolve() == (tmp_path / "sandbox_scratch").resolve()

    def test_night_shift_executes_math_via_sandbox(self, tmp_path, monkeypatch):
        import jarvis.workers.night_shift as mod
        monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")

        worker = NightShiftWorker(is_mock=False, sandbox_dir=tmp_path / "sandbox_scratch")
        res = worker._execute_step("[calculate] 123 * 456")
        assert res.get("success") is True
        assert "56088" in str(res.get("result"))

    def test_night_shift_sandboxed_code_scrubs_secrets(self, tmp_path, monkeypatch):
        import jarvis.workers.night_shift as mod
        monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")
        monkeypatch.setenv("GOOGLE_API_KEY", "super_secret_ai_token_123")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram_secret_token_999")

        worker = NightShiftWorker(is_mock=False, sandbox_dir=tmp_path / "sandbox_scratch")
        code = """
import os
leaked = [k for k in ["GOOGLE_API_KEY", "TELEGRAM_BOT_TOKEN"] if os.environ.get(k)]
print(f"LEAKED: {leaked}")
"""
        exec_res = worker.execute_sandboxed_code(code)
        assert exec_res.get("success") is True
        assert "LEAKED: []" in exec_res.get("stdout", "")

    def test_night_shift_code_execution_timeout(self, tmp_path, monkeypatch):
        import jarvis.workers.night_shift as mod
        monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")

        worker = NightShiftWorker(is_mock=False, sandbox_dir=tmp_path / "sandbox_scratch")
        code = """
import time
while True:
    time.sleep(0.1)
"""
        exec_res = worker.execute_sandboxed_code(code, timeout_seconds=1.0)
        assert exec_res.get("success") is False

    def test_night_shift_save_file_confinement(self, tmp_path, monkeypatch):
        import jarvis.workers.night_shift as mod
        monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))

        worker = NightShiftWorker(is_mock=False, sandbox_dir=tmp_path / "sandbox_scratch")
        res = worker._execute_step("[save_file] night work output data")
        assert res.get("success") is True
        assert "night_output_" in str(res.get("result"))


class TestNightShiftSchedulingAndReportingReality:
    """Locks in the current, verified scheduling/reporting behavior documented
    in docs/night_shift_audit.md (corrected 2026-09-01): report_time is task
    metadata only and does not influence scheduling, and report "delivery"
    is currently a local file write, not a Telegram/comms send."""

    def test_schedule_task_ignores_report_time(self, tmp_path, monkeypatch):
        """_schedule_task()'s computed delay must depend only on
        scheduled_time -- two tasks sharing the same scheduled_time but
        wildly different report_time values must be scheduled identically."""
        import jarvis.workers.night_shift as mod
        monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")

        captured_delays = []

        class _FakeTimer:
            def __init__(self, delay, fn, args=None):
                captured_delays.append(delay)
            def start(self):
                pass
            def cancel(self):
                pass

        monkeypatch.setattr(mod.threading, "Timer", _FakeTimer)

        worker = NightShiftWorker(is_mock=False, sandbox_dir=tmp_path / "sandbox_scratch")
        worker.add_task("A", "test", scheduled_time="03:00", report_time="04:00")
        worker.add_task("B", "test", scheduled_time="03:00", report_time="23:59")

        assert len(captured_delays) == 2
        # Same scheduled_time -> same target datetime -> essentially the same
        # delay (allowing a fraction of a second of real wall-clock drift
        # between the two add_task() calls).
        assert abs(captured_delays[0] - captured_delays[1]) < 2.0

    def test_send_morning_report_writes_file_only(self, tmp_path, monkeypatch):
        """_send_morning_report() currently persists the Markdown report to
        a local file; this regression test locks in that observable
        behavior. No comms delivery is implemented."""
        import jarvis.workers.night_shift as mod
        monkeypatch.setattr(mod, "_TASKS_FILE", tmp_path / "tasks.json")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))

        worker = NightShiftWorker(is_mock=True)
        task = worker.add_task("Report Delivery Test", "test")
        task.status = "completed"
        task.result = {
            "steps_completed": 0, "all_success": True,
            "elapsed_s": 0.1, "step_results": [],
        }
        report = worker.generate_report(task)

        worker._send_morning_report(task, report)

        expected_path = tmp_path / "appdata" / "JARVIS" / "logs" / f"night_report_{task.task_id}.md"
        assert expected_path.exists()
        assert expected_path.read_text(encoding="utf-8") == report

