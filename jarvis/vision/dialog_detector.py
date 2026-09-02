"""
jarvis/vision/dialog_detector.py
================================
Modal Error and Warning Dialog Detector for Windows Desktop.
Scans running window hierarchies for Win32 `#32770` modal dialogs,
error popups, message boxes, and application crash dialogs.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Any

logger = logging.getLogger("jarvis.vision.dialog_detector")

# Win32 Dialog Window Class Name
WIN32_DIALOG_CLASS = "#32770"

# Common error keywords in English & Vietnamese
ERROR_KEYWORDS = {
    "error",
    "warning",
    "exception",
    "crash",
    "fatal",
    "critical",
    "failed",
    "failure",
    "not responding",
    "stopped working",
    "lỗi",
    "cảnh báo",
    "thất bại",
    "sự cố",
    "bị treo",
    "không phản hồi",
}


class ErrorDialogDetector:
    """
    Scans the Windows desktop window tree to identify error dialogs,
    warning message boxes (#32770), and application crash windows.
    """

    def __init__(self, custom_keywords: list[str] | None = None) -> None:
        self.error_keywords = set(ERROR_KEYWORDS)
        if custom_keywords:
            for kw in custom_keywords:
                self.error_keywords.add(kw.strip().lower())
        self._is_windows = (sys.platform == "win32")

    @classmethod
    def is_available(cls) -> bool:
        """Returns True if Win32 dialog inspection is supported on the current platform."""
        return sys.platform == "win32"

    def scan_for_dialogs(self) -> list[dict[str, Any]]:
        """
        Enumerates all visible top-level windows and returns detected modal dialogs / error popups.
        """
        if not self._is_windows:
            logger.debug("Non-Windows OS detected; returning empty dialog list.")
            return []

        dialogs: list[dict[str, Any]] = []

        try:
            user32 = getattr(ctypes.windll, "user32", None)
            if user32 is None:
                return []

            # Define EnumWindows callback
            def enum_windows_proc(hwnd: int, lparam: int) -> int:
                try:
                    # Check window visibility
                    if not user32.IsWindowVisible(hwnd):
                        return 1

                    # Get Class Name
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buf, 256)
                    class_name = cls_buf.value

                    # Get Title
                    length = user32.GetWindowTextLengthW(hwnd)
                    buf_size = max(length + 1, 512)
                    title_buf = ctypes.create_unicode_buffer(buf_size)
                    user32.GetWindowTextW(hwnd, title_buf, buf_size)
                    title = title_buf.value

                    # Get Window Rect
                    class RECT(ctypes.Structure):
                        _fields_ = [
                            ("left", ctypes.c_long),
                            ("top", ctypes.c_long),
                            ("right", ctypes.c_long),
                            ("bottom", ctypes.c_long),
                        ]

                    rect = RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    rect_tuple = (rect.left, rect.top, rect.right, rect.bottom)
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top

                    # Ignore zero-sized or tiny utility windows
                    if width <= 10 or height <= 10:
                        return 1

                    # Extract Child Text Content
                    child_texts = self._get_child_window_texts(hwnd, user32)
                    full_text = " ".join(child_texts).strip()

                    # Heuristic detection
                    is_32770_dialog = (class_name == WIN32_DIALOG_CLASS)
                    has_error_title = any(kw in title.lower() for kw in self.error_keywords)
                    has_error_body = any(kw in full_text.lower() for kw in self.error_keywords)

                    if is_32770_dialog or has_error_title or has_error_body:
                        # Determine severity
                        if "crash" in title.lower() or "fatal" in title.lower() or "crash" in full_text.lower() or "fatal" in full_text.lower():
                            severity = "critical"
                        elif has_error_title or has_error_body:
                            severity = "error"
                        else:
                            severity = "warning"

                        dialogs.append({
                            "hwnd": hwnd,
                            "title": title,
                            "class_name": class_name,
                            "text": full_text,
                            "rect": rect_tuple,
                            "width": width,
                            "height": height,
                            "is_dialog": is_32770_dialog,
                            "is_error": has_error_title or has_error_body or is_32770_dialog,
                            "severity": severity,
                        })

                except Exception as exc:
                    logger.debug("Error inspecting hwnd %s: %s", hwnd, exc)

                return 1

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
            proc = WNDENUMPROC(enum_windows_proc)
            user32.EnumWindows(proc, 0)

        except Exception as exc:
            logger.warning("Failed to enumerate desktop windows for dialog inspection: %s", exc)

        return dialogs

    def _get_child_window_texts(self, parent_hwnd: int, user32: Any) -> list[str]:
        """Extracts text strings from all child static and edit controls."""
        texts: list[str] = []

        try:
            def enum_child_proc(hwnd: int, lparam: int) -> int:
                try:
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            val = buf.value.strip()
                            if val and val not in ("OK", "Cancel", "Close", "Yes", "No", "Abort", "Retry", "Ignore"):
                                texts.append(val)
                except Exception:
                    pass
                return 1

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
            proc = WNDENUMPROC(enum_child_proc)
            enum_child_func = getattr(user32, "EnumChildWindows", None)
            if enum_child_func:
                enum_child_func(parent_hwnd, proc, 0)
        except Exception:
            pass

        return texts

    def get_active_error_dialog(self) -> dict[str, Any] | None:
        """
        Returns the most relevant active error dialog if found on screen,
        or None if no errors/dialogs are present.
        """
        dialogs = self.scan_for_dialogs()
        if not dialogs:
            return None

        # Prioritize windows explicitly flagged as errors or with #32770 class
        for d in dialogs:
            if d.get("is_error"):
                return d

        return dialogs[0]

    def has_error_dialog(self) -> bool:
        """Returns True if any error dialog or warning popup is detected."""
        return self.get_active_error_dialog() is not None

    def format_error_summary(self, dialog: dict[str, Any] | None = None) -> str:
        """
        Creates a clean, vocalizable Vietnamese description of the error dialog.
        """
        target = dialog or self.get_active_error_dialog()
        if not target:
            return "Không phát hiện hộp thoại lỗi nào trên màn hình, thưa Ngài."

        title = target.get("title", "Hộp thoại hệ thống")
        text = target.get("text", "")
        if text:
            return f"Phát hiện hộp thoại cảnh báo '{title}': {text}."
        return f"Phát hiện hộp thoại cảnh báo '{title}' đang hiển thị trên màn hình."


# Backward compatibility alias
DialogDetector = ErrorDialogDetector
