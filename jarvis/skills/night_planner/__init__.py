"""
jarvis/skills/night_planner/__init__.py
========================================
Night Shift Task Planner skill: voice interface for the NightShiftWorker.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("jarvis.skills.night_planner")

_WORKER = None


def _get_worker():
    global _WORKER
    if _WORKER is None:
        from jarvis.workers.night_shift import NightShiftWorker
        _WORKER = NightShiftWorker()
    return _WORKER


def execute(
    action: str = "list",
    title: str = "",
    description: str = "",
    scheduled_time: str = "23:00",
    report_time: str = "07:00",
    task_id: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Night Shift Task Planner.

    Args:
        action: 'add' | 'list' | 'cancel' | 'report' | 'run_now'
        title: Task title (for 'add')
        description: Detailed task description (for 'add')
        scheduled_time: 'HH:MM' when task should run (default '23:00')
        report_time: 'HH:MM' for morning report delivery (default '07:00')
        task_id: Task ID (for 'cancel' / 'run_now')
    """
    worker = _get_worker()
    act = action.lower().strip()

    if act == "add":
        if not title.strip() or not description.strip():
            msg = "Vui lòng cung cấp title và description để thêm tác vụ đêm."
            return {"data": {"text": msg, "success": False}, "output": msg}

        task = worker.add_task(
            title=title,
            description=description,
            scheduled_time=scheduled_time,
            report_time=report_time,
        )
        steps_preview = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(task.steps[:5]))
        msg = (
            f"🌙 Đã lên lịch tác vụ đêm:\n"
            f"**ID:** {task.task_id}\n"
            f"**Tiêu đề:** {task.title}\n"
            f"**Bắt đầu lúc:** {task.scheduled_time}\n"
            f"**Báo cáo lúc:** {task.report_time}\n"
            f"**Các bước ({len(task.steps)}):**\n{steps_preview}"
        )
        return {
            "data": {
                "task_id": task.task_id,
                "title": task.title,
                "scheduled_time": task.scheduled_time,
                "steps": task.steps,
                "text": msg,
                "success": True,
            },
            "output": msg,
        }

    elif act == "list":
        tasks = worker.list_tasks()
        if not tasks:
            msg = "Không có tác vụ đêm nào. Dùng action='add' để tạo tác vụ mới."
            return {"data": {"tasks": [], "text": msg, "success": True}, "output": msg}

        lines = [f"🌙 Danh sách {len(tasks)} tác vụ đêm:"]
        for t in tasks:
            status_icon = {"pending": "⏳", "running": "⚙️", "completed": "✅", "failed": "❌", "cancelled": "🚫"}.get(t.status, "?")
            lines.append(f"  {status_icon} [{t.task_id}] '{t.title}' — {t.status} (lên lịch: {t.scheduled_time})")
        msg = "\n".join(lines)

        tasks_dict = [
            {"task_id": t.task_id, "title": t.title, "status": t.status, "scheduled_time": t.scheduled_time}
            for t in tasks
        ]
        return {"data": {"tasks": tasks_dict, "text": msg, "success": True}, "output": msg}

    elif act == "cancel":
        if not task_id:
            msg = "Vui lòng cung cấp task_id để hủy tác vụ."
            return {"data": {"text": msg, "success": False}, "output": msg}

        ok = worker.cancel_task(task_id)
        msg = f"✅ Đã hủy tác vụ [{task_id}]." if ok else f"Không thể hủy tác vụ [{task_id}] (không tồn tại hoặc đã hoàn thành)."
        return {"data": {"text": msg, "task_id": task_id, "success": ok}, "output": msg}

    elif act == "report":
        # Find the latest completed task report
        reports = sorted(Path("logs").glob("night_report_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            msg = "Chưa có báo cáo đêm nào."
            return {"data": {"text": msg, "success": True}, "output": msg}

        latest = reports[0].read_text(encoding="utf-8")
        preview = latest[:800] + ("..." if len(latest) > 800 else "")
        return {"data": {"text": preview, "report_file": str(reports[0]), "success": True}, "output": preview}

    elif act == "run_now":
        if not task_id:
            msg = "Vui lòng cung cấp task_id để thực thi ngay."
            return {"data": {"text": msg, "success": False}, "output": msg}

        result = worker.run_task_now(task_id)
        if result.get("success"):
            msg = f"✅ Tác vụ [{task_id}] đã hoàn thành thành công!\n{result.get('report', '')[:400]}"
        else:
            msg = f"❌ Tác vụ [{task_id}] thất bại: {result.get('error', 'Unknown error')}"
        return {"data": {"text": msg, "result": result, "success": result.get("success", False)}, "output": msg}

    else:
        msg = f"Hành động '{act}' không hợp lệ. Hỗ trợ: add, list, cancel, report, run_now."
        return {"data": {"text": msg, "success": False}, "output": msg}
