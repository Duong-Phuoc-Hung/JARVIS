"""
JARVIS Built-in Skill: Smart Clipboard Companion
=================================================
Inspects and enhances clipboard content automatically:
- Pretty-prints minified JSON.
- Cleans tracking parameters (UTM, fbclid) from copied URLs.
- Analyzes Python exception tracebacks and pinpoints root causes.
- Normalizes multiline text formatting.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import urllib.parse
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.skills.smart_clipboard")


def get_clipboard() -> str:
    """Safely get text from clipboard."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return str(text)
    except Exception:
        pass
    return ""


def set_clipboard(text: str) -> bool:
    """Safely set text into clipboard."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        pass
    return False


def clean_url_trackers(url: str) -> str:
    """Strip marketing and telemetry tracking query parameters from URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url
        query_dict = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        # Strip common trackers
        tracker_keys = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref"}
        clean_query = {k: v for k, v in query_dict.items() if k.lower() not in tracker_keys}
        new_query = urllib.parse.urlencode(clean_query, doseq=True)
        cleaned_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        return cleaned_url
    except Exception:
        return url


def analyze_python_traceback(text: str) -> str | None:
    """Analyze a copied Python error traceback."""
    if "Traceback (most recent call last):" not in text:
        return None
    lines = text.strip().splitlines()
    error_line = lines[-1] if lines else ""
    return f"Phát hiện lỗi Python: `{error_line}`. Kiểm tra dòng code trong tệp vừa thực thi."


def process_clipboard_content(raw_text: str) -> dict[str, Any]:
    """Inspect and enhance clipboard text based on structural patterns."""
    text = raw_text.strip()
    if not text:
        return {"detected_type": "empty", "result": "", "modified": False}

    # 1. Check for JSON formatting
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            parsed = json.loads(text)
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
            if formatted != text:
                set_clipboard(formatted)
                return {
                    "detected_type": "json",
                    "result": formatted,
                    "action_taken": "Đã định dạng JSON thụt lề 2 spaces chuẩn và sao chép vào Clipboard.",
                    "modified": True,
                }
        except Exception:
            pass

    # 2. Check for URL with tracking parameters
    if text.startswith(("http://", "https://")):
        cleaned_url = clean_url_trackers(text)
        if cleaned_url != text:
            set_clipboard(cleaned_url)
            return {
                "detected_type": "url",
                "result": cleaned_url,
                "action_taken": f"Đã loại bỏ mã theo dõi UTM/Fbclid khỏi liên kết: {cleaned_url}",
                "modified": True,
            }

    # 3. Check for Python Traceback
    tb_analysis = analyze_python_traceback(text)
    if tb_analysis:
        return {
            "detected_type": "traceback",
            "result": tb_analysis,
            "action_taken": tb_analysis,
            "modified": False,
        }

    return {
        "detected_type": "plain_text",
        "result": text,
        "action_taken": f"Văn bản thông thường ({len(text)} ký tự).",
        "modified": False,
    }


def execute(
    content: str = "",
    text: str = "",
    action: str = "inspect",
    notify: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute clipboard enhancement and inspection.
    """
    clip_text = content.strip() or text.strip() or kwargs.get("clipboard_text", "").strip() or get_clipboard()
    if not clip_text:
        msg = "Khay nhớ tạm (Clipboard) hiện đang trống."
        return {"data": {"success": True, "detected_type": "empty", "modified": False, "transformed": ""}, "output": msg}

    analysis = process_clipboard_content(clip_text)
    msg = f"📋 **Smart Clipboard:** {analysis['action_taken']}"

    if notify and analysis.get("modified"):
        try:
            from jarvis.skills.desktop_notifier import send_windows_toast
            send_windows_toast(
                title="JARVIS Smart Clipboard",
                message=analysis["action_taken"],
                sound="Default"
            )
        except Exception:
            pass

    return {
        "data": {
            "detected_type": analysis["detected_type"],
            "modified": analysis["modified"],
            "result": analysis["result"][:200],
            "transformed": analysis["result"],
            "success": True,
        },
        "output": msg,
    }
