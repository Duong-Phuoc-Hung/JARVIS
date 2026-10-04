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

    def dismiss_dialog(self, hwnd: int, action: str = "ok") -> bool:
        """
        Sends appropriate button click or close command to dismiss a modal dialog.
        Supports: 'ok' (IDOK=1), 'cancel' (IDCANCEL=2), 'close' (WM_CLOSE=0x0010).
        """
        if not self._is_windows:
            return False

        try:
            user32 = getattr(ctypes.windll, "user32", None)
            if user32 is None:
                return False

            clean_act = (action or "ok").lower().strip()

            # Method 1: Find matching button control (OK, Cancel, Close, Yes, No)
            btn_hwnd = None
            target_labels = ("ok", "đồng ý") if clean_act == "ok" else ("cancel", "hủy", "close", "đóng")

            def enum_btn_proc(chwnd: int, lparam: int) -> int:
                nonlocal btn_hwnd
                try:
                    cls_buf = ctypes.create_unicode_buffer(64)
                    user32.GetClassNameW(chwnd, cls_buf, 64)
                    if cls_buf.value.lower() == "button":
                        txt_len = user32.GetWindowTextLengthW(chwnd)
                        if txt_len > 0:
                            t_buf = ctypes.create_unicode_buffer(txt_len + 1)
                            user32.GetWindowTextW(chwnd, t_buf, txt_len + 1)
                            b_text = t_buf.value.lower().strip()
                            if any(target in b_text for target in target_labels):
                                btn_hwnd = chwnd
                                return 0
                except Exception:
                    pass
                return 1

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
            proc = WNDENUMPROC(enum_btn_proc)
            enum_child_func = getattr(user32, "EnumChildWindows", None)
            if enum_child_func:
                enum_child_func(hwnd, proc, 0)

            # If matching button found, send BM_CLICK (0x00F5)
            if btn_hwnd and hasattr(user32, "PostMessageW"):
                if user32.PostMessageW(btn_hwnd, 0x00F5, 0, 0):
                    time.sleep(0.05)
                    if not bool(user32.IsWindow(hwnd)):
                        return True

            # Method 2: Fallback to WM_COMMAND with IDOK (1) or IDCANCEL (2)
            cmd_id = 1 if clean_act == "ok" else 2
            if hasattr(user32, "PostMessageW"):
                # Submit only the requested action, without an unsolicited close.
                message = 0x0010 if clean_act == "close" else 0x0111
                if user32.PostMessageW(hwnd, message, cmd_id if message == 0x0111 else 0, 0):
                    time.sleep(0.05)
                    return not bool(user32.IsWindow(hwnd))

        except Exception as exc:
            logger.warning("Failed to dismiss dialog %s: %s", hwnd, exc)

        return False

    def resolve_error_dialogs(self, auto_dismiss: bool = True, preferred_action: str = "ok") -> list[dict[str, Any]]:
        """
        Scans for active error dialogs and optionally dismisses them.
        Returns list of handled dialog reports.
        """
        found = self.scan_for_dialogs()
        results = []
        for d in found:
            h = d.get("hwnd", 0)
            d_report = dict(d)
            if auto_dismiss and h > 0:
                closed = self.dismiss_dialog(h, action=preferred_action)
                d_report["dismissed"] = closed
                d_report["action_taken"] = preferred_action if closed else "failed"
            else:
                d_report["dismissed"] = False
                d_report["action_taken"] = "inspected"
            results.append(d_report)
        return results


# Backward compatibility alias
DialogDetector = ErrorDialogDetector
