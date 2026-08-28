"""
JARVIS Built-in Skill: File Manager
Searches files, lists folder contents, and resolves system directory paths.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _get_known_folder(name: str) -> Path:
    """Resolve known user folders on Windows."""
    user_home = Path.home()
    lower = name.lower().strip()

    if lower in ("downloads", "download", "tai_ve", "tải về"):
        return user_home / "Downloads"
    elif lower in ("documents", "document", "tai_lieu", "tài liệu"):
        return user_home / "Documents"
    elif lower in ("desktop", "man_hinh", "màn hình"):
        return user_home / "Desktop"
    elif lower in ("pictures", "anh", "ảnh"):
        return user_home / "Pictures"
    elif lower in ("music", "nhac", "nhạc"):
        return user_home / "Music"
    elif lower in ("videos", "video"):
        return user_home / "Videos"
    elif lower in ("workspace", "code", "projects"):
        ws = Path("d:/Software GitCode/JARVIS")
        return ws if ws.exists() else user_home

    p = Path(name)
    if p.exists():
        return p
    return user_home


def execute(
    action: str = "search",
    query: str = "",
    directory: str = "",
    extension: str = "",
    max_results: int = 10,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    File search and management execution handler.
    """
    target_dir = _get_known_folder(directory) if directory else Path.cwd()
    if not target_dir.exists():
        target_dir = Path.home()

    if action == "open_folder":
        try:
            if sys.platform == "win32":
                os.startfile(str(target_dir))
            else:
                subprocess.Popen(["explorer" if sys.platform == "win32" else "xdg-open", str(target_dir)])
            msg = f"Đã mở thư mục: {target_dir}"
            return {"data": {"text": msg, "path": str(target_dir), "success": True}, "output": msg}
        except Exception as exc:
            msg = f"Không thể mở thư mục '{target_dir}': {exc}"
            return {"data": {"text": msg, "error": str(exc), "success": False}, "output": msg}

    elif action == "list_folder":
        try:
            entries = []
            for item in target_dir.iterdir():
                is_dir = item.is_dir()
                size = item.stat().st_size if not is_dir else 0
                entries.append({
                    "name": item.name,
                    "is_dir": is_dir,
                    "size_bytes": size,
                    "path": str(item),
                })
                if len(entries) >= max_results:
                    break

            summary = f"Danh sách {len(entries)} mục trong {target_dir.name}:\n" + "\n".join(
                [f"- {'📁' if e['is_dir'] else '📄'} {e['name']}" for e in entries]
            )
            return {"data": {"text": summary, "entries": entries, "count": len(entries)}, "output": summary}
        except Exception as exc:
            msg = f"Lỗi đọc thư mục '{target_dir}': {exc}"
            return {"data": {"text": msg, "error": str(exc), "success": False}, "output": msg}

    else:  # action == "search"
        found = []
        ext_clean = extension.lstrip(".").lower() if extension else ""
        q_lower = query.lower().strip()

        try:
            for root, dirs, files in os.walk(str(target_dir)):
                dirs[:] = [d for d in dirs if not d.startswith((".", "$", "__")) and d not in ("node_modules", ".git", ".venv")]

                for f in files:
                    f_lower = f.lower()
                    match = True
                    if q_lower and q_lower not in f_lower:
                        match = False
                    if ext_clean and not f_lower.endswith(f".{ext_clean}"):
                        match = False

                    if match:
                        full_p = Path(root) / f
                        found.append({
                            "name": f,
                            "path": str(full_p),
                            "size_bytes": full_p.stat().st_size if full_p.exists() else 0,
                        })
                        if len(found) >= max_results:
                            break
                if len(found) >= max_results:
                    break

            if found:
                summary = f"Tìm thấy {len(found)} file phù hợp trong {target_dir.name}:\n" + "\n".join(
                    [f"- 📄 {item['name']} ({item['path']})" for item in found]
                )
            else:
                summary = f"Không tìm thấy file nào khớp với '{query or extension}' trong {target_dir.name}."

            return {
                "data": {
                    "text": summary,
                    "results": found,
                    "count": len(found),
                },
                "output": summary,
            }
        except Exception as exc:
            msg = f"Lỗi tìm kiếm file: {exc}"
            return {"data": {"text": msg, "error": str(exc), "success": False}, "output": msg}
