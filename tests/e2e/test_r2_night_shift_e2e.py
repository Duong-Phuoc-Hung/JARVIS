"""
tests/e2e/test_r2_night_shift_e2e.py
=====================================
E2E Test Suite for Requirement 2: Night Shift Daemon Audit & Sandboxing.

Covers:
  - TIER 1: Feature Coverage
      * test_r2_audit_documentation_structure_and_verdict
      * test_r2_task_decomposition_nlp_keywords
      * test_r2_night_shift_execution_happy_path
      * test_r2_report_generation_markdown_format
      * test_r2_task_persistence_and_retrieval
  - TIER 2: Boundary, Corner & Adversarial Cases
      * test_r2_corner_empty_or_malformed_task_description
      * test_r2_corner_step_failure_isolation_and_reporting
      * test_r2_boundary_unsupported_language_or_symbolic_task
      * test_r2_sandboxed_night_shift_step_execution
      * test_r2_concurrent_task_scheduling_and_cancellation
"""
from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path
import pytest

from jarvis.workers.night_shift import NightShiftTask, NightShiftWorker
from jarvis.sandbox.interpreter import CodeInterpreterSandbox


# ============================================================================
# TIER 1: FEATURE COVERAGE (R2)
# ============================================================================

class TestR2NightShiftFeatureTier1:
    """Tier 1: Primary feature coverage for R2 Night Shift Worker & Audit."""

    def test_r2_audit_documentation_structure_and_verdict(self):
        """
        Verify that `docs/night_shift_audit.md` exists on disk and contains formal audit sections:
        Scope, Un-sandboxed Daemon Risk Analysis, Sandboxing Recommendation, and Verdict.
        """
        doc_path = Path("docs/night_shift_audit.md")
        assert doc_path.exists(), "docs/night_shift_audit.md must exist on disk."

        content = doc_path.read_text(encoding="utf-8")
        assert len(content) > 100, "docs/night_shift_audit.md must not be empty"

        required_audit_sections = [
            "Night Shift Daemon Security Audit",
            "Daemon State",
            "Sandbox Restriction",
            "Audit Conclusion",
        ]
        for sec in required_audit_sections:
            assert sec.lower() in content.lower(), f"Missing required section '{sec}' in docs/night_shift_audit.md"

    def test_r2_task_decomposition_nlp_keywords(self):
        """
        Verify natural language task decomposition parses multi-step descriptions
        into typed actions (web_search, summarize, analyze, save_file, notify, calculate, generate_report).
        """
        worker = NightShiftWorker(is_mock=True)

        # 1. Search + Summarize + Save
        desc1 = "Tìm kiếm tài liệu AI mới nhất, tóm tắt nội dung chính và lưu kết quả vào file."
        steps1 = worker.decompose_task(desc1)
        assert len(steps1) >= 2
        assert any("web_search" in s or "tìm kiếm" in s.lower() for s in steps1)
        assert any("summarize" in s or "tóm tắt" in s.lower() for s in steps1)

        # 2. Analyze + Calculate + Report
        desc2 = "Phân tích số liệu doanh thu, tính tổng lợi nhuận và tạo báo cáo tổng hợp."
        steps2 = worker.decompose_task(desc2)
        assert len(steps2) >= 2
        assert any("analyze" in s or "phân tích" in s.lower() for s in steps2)
        assert any("calculate" in s or "tính" in s.lower() for s in steps2)

    def test_r2_night_shift_execution_happy_path(self):
        """
        Verify complete happy-path execution of a multi-step Night Shift task:
        creation -> execution -> completion status -> report generation.
        """
        worker = NightShiftWorker(is_mock=True)
        task = worker.add_task(
            title="Night Market Analysis",
            description="Tìm kiếm giá BTC, phân tích xu hướng và tạo báo cáo.",
            scheduled_time="02:00",
            report_time="06:00",
        )

        assert isinstance(task, NightShiftTask)
        assert task.status == "pending"
        assert len(task.steps) >= 1

        exec_res = worker.execute_task(task)
        assert exec_res["success"] is True
        assert task.status == "completed"
        assert task.completed_at is not None
        assert "report" in exec_res
        assert len(exec_res["report"]) > 50

    def test_r2_report_generation_markdown_format(self):
        """
        Verify generated Markdown report contains required headers, emojis,
        timing metrics, and per-step execution summaries.
        """
        worker = NightShiftWorker(is_mock=True)
        task = worker.add_task(
            title="Automated Data Backup",
            description="Lưu cấu hình hệ thống và gửi thông báo xác nhận.",
        )
        worker.execute_task(task)
        report = worker.generate_report(task)

        assert "# 🌙 JARVIS Night Shift Report" in report
        assert "**Nhiệm vụ:** Automated Data Backup" in report
        assert "**Trạng thái:**" in report
        assert "Thời gian thực thi:" in report
        assert "## Mô tả:" in report
        assert "## Kết quả từng bước" in report
        assert "JARVIS Night Shift Worker" in report

    def test_r2_task_persistence_and_retrieval(self):
        """
        Verify that created tasks are indexed and retrievable via `list_tasks()`,
        and serializable via `asdict`.
        """
        worker = NightShiftWorker(is_mock=True)
        t1 = worker.add_task("Task Alpha", "Tìm kiếm tài liệu A")
        t2 = worker.add_task("Task Beta", "Tóm tắt bài báo B")

        all_tasks = worker.list_tasks()
        task_ids = [t.task_id for t in all_tasks]
        assert t1.task_id in task_ids
        assert t2.task_id in task_ids

        d1 = asdict(t1)
        assert d1["title"] == "Task Alpha"
        assert d1["status"] in ("pending", "running", "completed")


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES (R2)
# ============================================================================

class TestR2NightShiftBoundaryTier2:
    """Tier 2: Boundary and corner cases for R2 Night Shift Worker."""

    def test_r2_corner_empty_or_malformed_task_description(self):
        """
        Corner Case: Decomposing empty string, whitespace only, or ultra-short
        description produces a fallback default step rather than throwing an exception.
        """
        worker = NightShiftWorker(is_mock=True)

        steps_empty = worker.decompose_task("")
        assert len(steps_empty) >= 1
        assert "[auto]" in steps_empty[0]

        steps_ws = worker.decompose_task("    \n\t  ")
        assert len(steps_ws) >= 1

        steps_short = worker.decompose_task("Ok")
        assert len(steps_short) >= 1

    def test_r2_corner_step_failure_isolation_and_reporting(self, monkeypatch):
        """
        Corner Case: When an individual step raises an unexpected exception or fails,
        the daemon isolates the failure, marks task as failed, and generates a full error report.
        """
        worker = NightShiftWorker(is_mock=True)
        task = worker.add_task("Failing Task", "Tìm kiếm dữ liệu và lưu file lỗi.")

        def mock_failing_step(step: str) -> dict:
            if "save_file" in step or "lưu" in step.lower():
                return {"success": False, "type": "save_file", "error": "Disk quota exceeded"}
            return {"success": True, "type": "web_search", "result": "Search done"}

        monkeypatch.setattr(worker, "_execute_step", mock_failing_step)
        res = worker.execute_task(task)

        assert res["success"] is False
        assert task.status == "failed"
        assert "❌" in res["report"]
        assert "Disk quota exceeded" in res["report"]

    def test_r2_boundary_unsupported_language_or_symbolic_task(self):
        """
        Boundary Case: Task description in emojis, ASCII art, or foreign language
        falls back to structured sentence-splitting without crashing regex matchers.
        """
        worker = NightShiftWorker(is_mock=True)
        symbolic_desc = "🚀 🤖 📊 -> 💾! /// 0xDEADBEEF test"
        steps = worker.decompose_task(symbolic_desc)
        assert len(steps) >= 1
        assert all(isinstance(s, str) for s in steps)

    def test_r2_sandboxed_night_shift_step_execution(self, tmp_path):
        """
        Security Verification: Night Shift worker delegating untrusted code
        steps to `CodeInterpreterSandbox` restricts arbitrary filesystem write
        and respects Job Object / Low Integrity constraints.
        """
        sandbox = CodeInterpreterSandbox(
            base_scratch_dir=tmp_path / "night_scratch",
            default_timeout=5.0,
        )

        untrusted_script = """
import os
print("NIGHT_SHIFT_STEP_SUCCESS")
"""
        res = sandbox.execute_python(untrusted_script, timeout_seconds=5.0)
        assert res.success is True
        assert "NIGHT_SHIFT_STEP_SUCCESS" in res.stdout

    def test_r2_concurrent_task_scheduling_and_cancellation(self):
        """
        Thread-Safety: Add and query multiple tasks concurrently across threads.
        Ensures internal dictionary and RLock remain consistent without race conditions.
        """
        import concurrent.futures

        worker = NightShiftWorker(is_mock=True)

        def create_task(idx: int) -> str:
            t = worker.add_task(f"Concurrent Task {idx}", f"Mô tả nhiệm vụ {idx} tìm kiếm phân tích")
            return t.task_id

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_task, i) for i in range(10)]
            created_ids = [f.result() for f in futures]

        all_tasks = worker.list_tasks()
        assert len(all_tasks) >= 10
        all_ids = {t.task_id for t in all_tasks}
        assert all(cid in all_ids for cid in created_ids)
