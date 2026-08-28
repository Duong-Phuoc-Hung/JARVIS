"""
JARVIS Built-in Skill: Pomodoro Timer & Focus Mode
Controls Pomodoro focus sessions and break intervals.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

# Module-level state for standalone skill usage
_POMODORO_STATE = {
    "is_running": False,
    "is_paused": False,
    "mode": "idle",  # "work", "break", "idle"
    "start_time": 0.0,
    "duration_seconds": 25 * 60,
    "break_seconds": 5 * 60,
    "completed_cycles": 0,
}


def execute(
    action: str = "start",
    duration_minutes: int = 25,
    break_minutes: int = 5,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Execute Pomodoro focus actions.
    """
    global _POMODORO_STATE
    now = time.time()

    if action == "start":
        _POMODORO_STATE["is_running"] = True
        _POMODORO_STATE["is_paused"] = False
        _POMODORO_STATE["mode"] = "work"
        _POMODORO_STATE["start_time"] = now
        _POMODORO_STATE["duration_seconds"] = int(duration_minutes) * 60
        _POMODORO_STATE["break_seconds"] = int(break_minutes) * 60

        msg = f"🍅 Bắt đầu chế độ tập trung Pomodoro {duration_minutes} phút! Hãy tập trung làm việc, tôi sẽ tắt các thông báo không quan trọng."
        return {
            "text": msg,
            "output": msg,
            "state": _POMODORO_STATE.copy(),
            "success": True,
        }

    elif action == "status":
        if not _POMODORO_STATE["is_running"]:
            msg = "🍅 Chế độ Pomodoro hiện đang tắt. Nói 'JARVIS, bắt đầu Pomodoro' để bắt đầu."
            return {"text": msg, "output": msg, "is_running": False, "success": True}
        
        elapsed = now - _POMODORO_STATE["start_time"]
        remaining = max(0, _POMODORO_STATE["duration_seconds"] - elapsed)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        
        mode_vi = "làm việc tập trung" if _POMODORO_STATE["mode"] == "work" else "nghỉ ngơi"
        msg = f"🍅 Đang trong phiên {mode_vi}. Thời gian còn lại: {mins} phút {secs:02d} giây (Chu kỳ đã hoàn thành: {_POMODORO_STATE['completed_cycles']})."
        return {
            "text": msg,
            "output": msg,
            "remaining_seconds": remaining,
            "mode": _POMODORO_STATE["mode"],
            "state": _POMODORO_STATE.copy(),
            "success": True,
        }

    elif action == "stop":
        _POMODORO_STATE["is_running"] = False
        _POMODORO_STATE["is_paused"] = False
        _POMODORO_STATE["mode"] = "idle"
        msg = "🍅 Đã kết thúc phiên Pomodoro."
        return {"text": msg, "output": msg, "success": True}

    elif action == "pause":
        _POMODORO_STATE["is_paused"] = True
        msg = "🍅 Đã tạm dừng phiên Pomodoro."
        return {"text": msg, "output": msg, "success": True}

    elif action == "resume":
        _POMODORO_STATE["is_paused"] = False
        msg = "🍅 Đã tiếp tục phiên Pomodoro."
        return {"text": msg, "output": msg, "success": True}

    else:
        msg = f"Hành động '{action}' không hợp lệ. Hỗ trợ: start, status, stop, pause, resume."
        return {"text": msg, "output": msg, "success": False}
