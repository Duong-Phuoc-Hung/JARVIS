"""
JARVIS Built-in Skill: Note Taker
Manages quick personal voice notes, tags, timestamps, and search.
"""
from __future__ import annotations

import datetime
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

# Serialize read-modify-write within this process; no shared in-memory cache.
_transaction_lock = threading.Lock()
_save_lock = threading.Lock()


def _get_notes_file() -> Path:
    """Return path to notes storage file."""
    import os as _os
    _apd = _os.environ.get("LOCALAPPDATA") or _os.environ.get("APPDATA")
    p = (Path(_apd) / "JARVIS" / "notes.json") if _apd else Path.home() / ".jarvis" / "notes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_notes() -> list[dict[str, Any]]:
    p = _get_notes_file()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(data, list) or any(
        not isinstance(note, dict)
        or not isinstance(note.get("id"), int)
        or not isinstance(note.get("content"), str)
        for note in data
    ):
        raise ValueError("NOTES_STORAGE_INVALID: existing notebook was preserved")
    return data


def _save_notes(notes: list[dict[str, Any]]) -> None:
    with _save_lock:
        p = _get_notes_file()
        snapshot = json.dumps(notes, indent=2, ensure_ascii=False)
        tmp = p.with_name(f"{p.name}.tmp.{threading.get_ident()}.{time.time_ns()}")
        try:
            with tmp.open("x", encoding="utf-8") as stream:
                stream.write(snapshot)
                stream.flush()
                os.fsync(stream.fileno())
            for attempt in range(1, 6):
                try:
                    tmp.replace(p)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.02 * attempt)
        finally:
            tmp.unlink(missing_ok=True)


def execute(
    action: str = "add",
    content: str = "",
    tag: str = "general",
    query: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute a notebook transaction without losing concurrent writes."""
    with _transaction_lock:
        return _execute_locked(action=action, content=content, tag=tag, query=query, **kwargs)


def _execute_locked(
    action: str = "add",
    content: str = "",
    tag: str = "general",
    query: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute note management operations.
    """
    notes = _load_notes()

    if action == "add":
        if not content.strip():
            msg = "Nội dung ghi chú trống. Vui lòng cung cấp nội dung."
            return {"data": {"text": msg, "success": False}, "output": msg}

        now = datetime.datetime.now()
        new_note = {
            "id": max((note["id"] for note in notes), default=0) + 1,
            "content": content.strip(),
            "tag": tag.strip() or "general",
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": time.time(),
        }
        notes.append(new_note)
        _save_notes(notes)

        # Sync to Desktop Markdown file for fast human glance
        try:
            desktop = Path.home() / "Desktop"
            if desktop.exists():
                notes_md = desktop / "JARVIS_Notes.md"
                md_line = f"- **[{new_note['created_at']}]** ({new_note['tag']}): {new_note['content']}\n"
                if not notes_md.exists():
                    notes_md.write_text(f"# 📝 JARVIS Notes\n\n{md_line}", encoding="utf-8")
                else:
                    with open(notes_md, "a", encoding="utf-8") as f:
                        f.write(md_line)
        except Exception:
            pass

        msg = f"Đã lưu ghi chú #{new_note['id']} [{new_note['tag']}]: \"{new_note['content']}\""
        return {
            "data": {
                "text": msg,
                "note": new_note,
                "total_notes": len(notes),
                "success": True,
            },
            "output": msg,
        }

    elif action == "list":
        if not notes:
            msg = "Hiện tại chưa có ghi chú nào được lưu."
            return {"data": {"text": msg, "notes": [], "success": True}, "output": msg}

        lines = [f"Danh sách {len(notes)} ghi chú:"]
        for n in notes[-10:]:
            lines.append(f"  • #{n['id']} [{n.get('tag', 'general')}] ({n.get('created_at', '')}): {n['content']}")

        summary = "\n".join(lines)
        return {
            "data": {
                "text": summary,
                "notes": notes,
                "success": True,
            },
            "output": summary,
        }

    elif action == "search":
        q = (query or content).lower().strip()
        matched = [n for n in notes if q in n.get("content", "").lower() or q in n.get("tag", "").lower()]

        if matched:
            lines = [f"Tìm thấy {len(matched)} ghi chú khớp với '{q}':"]
            for n in matched:
                lines.append(f"  • #{n['id']} [{n.get('tag', 'general')}]: {n['content']}")
            summary = "\n".join(lines)
        else:
            summary = f"Không tìm thấy ghi chú nào khớp với '{q}'."

        return {
            "data": {
                "text": summary,
                "results": matched,
                "success": True,
            },
            "output": summary,
        }

    elif action == "clear":
        _save_notes([])
        try:
            desktop = Path.home() / "Desktop"
            notes_md = desktop / "JARVIS_Notes.md"
            if notes_md.exists():
                notes_md.unlink(missing_ok=True)
        except Exception:
            pass
        msg = "Đã xóa toàn bộ ghi chú cá nhân."
        return {"data": {"text": msg, "success": True}, "output": msg}

    else:
        msg = f"Hành động '{action}' không hợp lệ. Hỗ trợ: add, list, search, clear."
        return {"data": {"text": msg, "success": False}, "output": msg}
