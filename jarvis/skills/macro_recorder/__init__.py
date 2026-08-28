"""
jarvis/skills/macro_recorder/__init__.py
=========================================
Voice Macro Recorder: record, store, and replay UI automation sequences.
Macros stored as JSON step lists in logs/macros.json.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.macro_recorder")

_MACROS_FILE = Path("logs/macros.json")


def _load_macros() -> Dict[str, List[Dict]]:
    _MACROS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _MACROS_FILE.exists():
        return {}
    try:
        return json.loads(_MACROS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_macros(macros: Dict[str, List[Dict]]) -> None:
    _MACROS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MACROS_FILE.write_text(json.dumps(macros, indent=2, ensure_ascii=False), encoding="utf-8")


def _execute_step(step: Dict) -> Dict:
    """Execute a single macro step."""
    step_type = step.get("type", "")
    params = step.get("params", {})
    description = step.get("description", "")

    try:
        if step_type == "wait":
            duration = float(params.get("seconds", 0.5))
            time.sleep(min(duration, 5.0))
            return {"success": True, "type": step_type, "description": description}

        elif step_type == "key":
            keys = params.get("keys", "")
            try:
                import pyautogui  # type: ignore[import]
                pyautogui.hotkey(*keys.split("+")) if "+" in keys else pyautogui.press(keys)
            except ImportError:
                # Fallback: powershell SendKeys
                if sys.platform == "win32":
                    subprocess.run(
                        ["powershell", "-Command", f"[System.Windows.Forms.SendKeys]::SendWait('{keys}')"],
                        timeout=5, capture_output=True,
                    )
            return {"success": True, "type": step_type, "description": description}

        elif step_type == "type":
            text = params.get("text", "")
            try:
                import pyautogui  # type: ignore[import]
                pyautogui.typewrite(text, interval=0.05)
            except ImportError:
                import pyperclip  # type: ignore[import]
                pyperclip.copy(text)
                log.info("type step: copied to clipboard (pyautogui not installed)")
            return {"success": True, "type": step_type, "description": description}

        elif step_type == "open":
            target = params.get("target", "")
            if target:
                os.startfile(target) if sys.platform == "win32" else subprocess.Popen(["xdg-open", target])
            return {"success": True, "type": step_type, "description": description}

        else:
            return {"success": True, "type": step_type, "description": f"[skipped: {description}]"}

    except Exception as exc:
        log.error("Macro step error (%s): %s", step_type, exc)
        return {"success": False, "type": step_type, "error": str(exc)}


def execute(
    action: str = "list",
    macro_name: str = "",
    steps: Optional[List[Dict]] = None,
    description: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Macro recording and playback manager.

    Args:
        action: 'list' | 'record' | 'play' | 'delete' | 'stop'
        macro_name: Name identifier for the macro
        steps: List of step dicts for 'record' action
        description: Human-readable description of this macro
    """
    macros = _load_macros()
    act = action.lower().strip()

    if act == "list":
        if not macros:
            msg = "Chưa có macro nào được lưu. Dùng action='record' để tạo macro mới."
            return {"data": {"macros": {}, "count": 0, "text": msg, "success": True}, "output": msg}

        lines = [f"📹 Danh sách {len(macros)} macro đã lưu:"]
        for name, step_list in macros.items():
            lines.append(f"  • '{name}' ({len(step_list)} bước)")
        msg = "\n".join(lines)
        return {"data": {"macros": macros, "count": len(macros), "text": msg, "success": True}, "output": msg}

    elif act == "record":
        if not macro_name:
            msg = "Vui lòng cung cấp macro_name để lưu macro."
            return {"data": {"text": msg, "success": False}, "output": msg}

        record_steps = steps or [
            {"type": "wait", "params": {"seconds": 0.5}, "description": "Chờ khởi động"},
        ]

        # Add metadata fields
        macro_data = {
            "description": description or f"Macro '{macro_name}'",
            "created_at": datetime.datetime.now().isoformat(),
            "steps": record_steps,
        }
        macros[macro_name] = record_steps
        _save_macros(macros)

        msg = f"✅ Đã lưu macro '{macro_name}' với {len(record_steps)} bước."
        return {
            "data": {"text": msg, "macro_name": macro_name, "steps": record_steps, "success": True},
            "output": msg,
        }

    elif act == "play":
        if not macro_name:
            msg = "Vui lòng cung cấp macro_name để phát lại."
            return {"data": {"text": msg, "success": False}, "output": msg}

        if macro_name not in macros:
            available = ", ".join(macros.keys()) or "không có"
            msg = f"Macro '{macro_name}' không tồn tại. Sẵn có: {available}"
            return {"data": {"text": msg, "success": False}, "output": msg}

        step_list = macros[macro_name]
        results = []
        for i, step in enumerate(step_list):
            log.info("Macro '%s' step %d/%d: %s", macro_name, i + 1, len(step_list), step.get("description", ""))
            result = _execute_step(step)
            results.append(result)
            if not result.get("success"):
                msg = f"Macro '{macro_name}' thất bại ở bước {i + 1}: {result.get('error', 'Unknown')}"
                return {"data": {"text": msg, "results": results, "success": False}, "output": msg}

        msg = f"✅ Đã thực thi macro '{macro_name}' thành công ({len(step_list)} bước)."
        return {"data": {"text": msg, "results": results, "success": True}, "output": msg}

    elif act == "delete":
        if not macro_name or macro_name not in macros:
            msg = f"Macro '{macro_name}' không tồn tại."
            return {"data": {"text": msg, "success": False}, "output": msg}

        del macros[macro_name]
        _save_macros(macros)
        msg = f"🗑️ Đã xóa macro '{macro_name}'."
        return {"data": {"text": msg, "macro_name": macro_name, "success": True}, "output": msg}

    else:
        msg = f"Hành động '{act}' không hợp lệ. Hỗ trợ: list, record, play, delete."
        return {"data": {"text": msg, "success": False}, "output": msg}
