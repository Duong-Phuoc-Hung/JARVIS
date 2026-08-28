"""
JARVIS Built-in Skill: Clipboard Manager
Reads and writes clipboard text using tkinter or ctypes Win32 API.
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from typing import Any, Dict, Optional


def _get_clipboard_text() -> str:
    """Read clipboard text using Tkinter or Win32 fallback."""
    try:
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return str(text)
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            text = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            return str(text)
        except Exception:
            pass

    return ""


def _set_clipboard_text(text: str) -> bool:
    """Set clipboard text."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import win32clipboard
            import win32con
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return True
        except Exception:
            pass

    return False


def execute(
    action: str = "read",
    text: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Execute clipboard read or write operations.
    """
    act = action.lower().strip()

    if act == "copy" or (text and act != "read"):
        if not text:
            msg = "Vui lòng cung cấp văn bản cần sao chép."
            return {"text": msg, "output": msg, "success": False}
        
        ok = _set_clipboard_text(text)
        if ok:
            msg = f"📋 Đã sao chép vào clipboard: \"{text[:100]}{'...' if len(text) > 100 else ''}\""
            return {"text": msg, "output": msg, "copied_text": text, "success": True}
        else:
            msg = "Không thể sao chép văn bản vào clipboard."
            return {"text": msg, "output": msg, "success": False}

    elif act == "clear":
        _set_clipboard_text("")
        msg = "📋 Đã xóa sạch nội dung clipboard."
        return {"text": msg, "output": msg, "success": True}

    else:  # act == "read"
        clip_content = _get_clipboard_text()
        if not clip_content.strip():
            msg = "📋 Clipboard hiện đang trống."
            return {"text": msg, "output": msg, "content": "", "success": True}
        
        preview = clip_content[:200] + ("..." if len(clip_content) > 200 else "")
        msg = f"📋 Nội dung trong clipboard ({len(clip_content)} ký tự):\n\"{preview}\""
        return {
            "text": msg,
            "output": msg,
            "content": clip_content,
            "length": len(clip_content),
            "success": True,
        }
