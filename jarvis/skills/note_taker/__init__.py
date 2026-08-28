"""
JARVIS Built-in Skill: Note Taker
Manages quick personal voice notes, tags, timestamps, and search.
"""
from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _get_notes_file() -> Path:
    """Return path to notes storage file."""
    p = Path("logs/notes.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("[]", encoding="utf-8")
    return p


def _load_notes() -> list[dict[str, Any]]:
    p = _get_notes_file()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_notes(notes: list[dict[str, Any]]) -> None:
    p = _get_notes_file()
    p.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")


def execute(
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
            "id": len(notes) + 1,
            "content": content.strip(),
            "tag": tag.strip() or "general",
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": time.time(),
        }
        notes.append(new_note)
        _save_notes(notes)

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
        msg = "Đã xóa toàn bộ ghi chú cá nhân."
        return {"data": {"text": msg, "success": True}, "output": msg}

    else:
        msg = f"Hành động '{action}' không hợp lệ. Hỗ trợ: add, list, search, clear."
        return {"data": {"text": msg, "success": False}, "output": msg}
