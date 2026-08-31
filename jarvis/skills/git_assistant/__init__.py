"""
JARVIS Built-in Skill: Git Assistant
Provides Git status, active branch info, recent commit logs, and repository overview.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _run_git(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Execute git command safely."""
    try:
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=_cflags,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return -1, "", str(exc)


def execute(
    action: str = "status",
    repo_path: str = "",
    limit: int = 5,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute Git assistant commands.
    """
    target_dir = Path(repo_path) if repo_path else Path("d:/Software GitCode/JARVIS")
    if not target_dir.exists():
        target_dir = Path.cwd()

    act = action.lower().strip()

    if act == "status":
        code, stdout, stderr = _run_git(["status", "--short"], target_dir)
        if code != 0:
            msg = f"Lỗi thực thi git status: {stderr or 'Không phải git repository'}"
            return {"data": {"text": msg, "success": False}, "output": msg}

        _, branch_out, _ = _run_git(["branch", "--show-current"], target_dir)
        branch_name = branch_out or "unknown"

        if not stdout:
            summary = f"🌿 Git [{branch_name}]: Thư mục làm việc sạch sẽ, không có thay đổi nào chưa commit."
            return {
                "data": {
                    "text": summary,
                    "branch": branch_name,
                    "modified_files": [],
                    "success": True,
                },
                "output": summary,
            }

        lines = stdout.splitlines()
        summary = f"🌿 Git [{branch_name}]: Có {len(lines)} file có thay đổi:\n" + "\n".join(
            [f"  • {line}" for line in lines[:10]]
        )
        if len(lines) > 10:
            summary += f"\n  ... và {len(lines) - 10} file khác."

        return {
            "data": {
                "text": summary,
                "branch": branch_name,
                "modified_count": len(lines),
                "files": lines,
                "success": True,
            },
            "output": summary,
        }

    elif act == "branch":
        code, stdout, stderr = _run_git(["branch", "-a"], target_dir)
        if code != 0:
            msg = f"Lỗi lấy danh sách branch: {stderr}"
            return {"data": {"text": msg, "success": False}, "output": msg}

        summary = f"🌿 Các nhánh Git:\n{stdout}"
        return {"data": {"text": summary, "branches": stdout.splitlines(), "success": True}, "output": summary}

    elif act == "log":
        code, stdout, stderr = _run_git(["log", f"-n{max(1, limit)}", "--oneline"], target_dir)
        if code != 0:
            msg = f"Lỗi lấy lịch sử git log: {stderr}"
            return {"data": {"text": msg, "success": False}, "output": msg}

        summary = f"🌿 {limit} Commit gần nhất:\n{stdout}"
        return {"data": {"text": summary, "commits": stdout.splitlines(), "success": True}, "output": summary}

    else:
        # Combined summary
        _, branch_name, _ = _run_git(["branch", "--show-current"], target_dir)
        _, status_out, _ = _run_git(["status", "--short"], target_dir)
        _, log_out, _ = _run_git(["log", "-n3", "--oneline"], target_dir)

        status_count = len(status_out.splitlines()) if status_out else 0
        summary = (
            f"🌿 Tổng quan Git Repository:\n"
            f"  • Nhánh hiện tại: {branch_name or 'main'}\n"
            f"  • Thay đổi chưa commit: {status_count} file\n"
            f"  • Commits gần đây:\n    {log_out.replace(chr(10), chr(10) + '    ')}"
        )
        return {"data": {"text": summary, "branch": branch_name, "success": True}, "output": summary}
