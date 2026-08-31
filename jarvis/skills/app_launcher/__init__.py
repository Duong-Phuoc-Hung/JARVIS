"""
JARVIS Built-in Skill: Application Launcher
Launches and focuses common desktop applications.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Known executable mapping
KNOWN_APPS = {
    "chrome": ["chrome.exe", "google-chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"],
    "vscode": ["code.cmd", "code.exe", "code"],
    "spotify": ["spotify.exe", "spotify"],
    "notepad": ["notepad.exe", "notepad"],
    "calc": ["calc.exe", "calculator"],
    "calculator": ["calc.exe"],
    "terminal": ["wt.exe", "powershell.exe", "cmd.exe"],
    "powershell": ["powershell.exe"],
    "cmd": ["cmd.exe"],
    "explorer": ["explorer.exe"],
    "taskmanager": ["taskmgr.exe"],
    "settings": ["ms-settings:"],
}


def _find_executable(candidates: list[str]) -> str | None:
    """Find the first available executable candidate."""
    for c in candidates:
        if c.startswith("ms-settings:"):
            return c
        if Path(c).is_file():
            return c
        which_path = shutil.which(c)
        if which_path:
            return which_path
    return None


def execute(
    app_name: str = "notepad",
    args: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Launch requested desktop application.
    """
    app_key = app_name.lower().strip()
    candidates = KNOWN_APPS.get(app_key, [app_name])

    exe_target = _find_executable(candidates)
    if not exe_target:
        # Try direct name
        exe_target = app_name

    try:
        if exe_target.startswith("ms-settings:"):
            if sys.platform == "win32":
                os.startfile(exe_target)
            msg = "🚀 Đã mở Cài đặt Windows Settings."
            return {"text": msg, "output": msg, "target": exe_target, "success": True}

        cmd = [exe_target]
        if args:
            cmd.extend(args.split())

        _cflags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_cflags,
        )
        msg = f"🚀 Đã khởi chạy ứng dụng '{app_name}' thành công."
        return {
            "text": msg,
            "output": msg,
            "app_name": app_name,
            "executable": exe_target,
            "success": True,
        }
    except Exception as exc:
        msg = f"Không thể mở ứng dụng '{app_name}': {exc}"
        return {"text": msg, "output": msg, "error": str(exc), "success": False}
