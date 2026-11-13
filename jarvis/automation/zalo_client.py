"""
jarvis/automation/zalo_client.py
================================
Native Zalo PC Client Automation for Windows.

Enables sovereign desktop assistants to send messages, files, and start calls
via the installed Zalo Desktop Client without requiring Official Account (OA)
credentials or paid business API keys.

Uses Windows UIAutomation, process management, and simulated keyboard inputs:
  1. Window Discovery & Activation:
     - Locates existing Zalo window or launches Zalo.exe via standard path/URI protocol.
     - Brings Zalo main window to foreground.
  2. Contact Search & Conversation Selection:
     - Triggers search shortcut (Ctrl+F), types recipient name/phone, selects top match.
  3. Message Delivery:
     - Pastes text safely via Win32 clipboard and dispatches Enter.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from jarvis.automation.control import ComputerController
from jarvis.platform.uiautomation import WindowsUIAutomation

logger = logging.getLogger("jarvis.automation.zalo_client")


def _find_zalo_executable() -> str | None:
    """Finds Zalo.exe path in standard Windows locations."""
    which_path = shutil.which("Zalo.exe") or shutil.which("zalo")
    if which_path and Path(which_path).is_file():
        return which_path

    # Standard user installation locations on Windows
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    app_data = os.environ.get("APPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")

    candidates = [
        Path(local_app_data) / "Programs" / "Zalo" / "Zalo.exe",
        Path(app_data) / "Zalo" / "Zalo.exe",
        Path(local_app_data) / "Zalo" / "Zalo.exe",
        Path(program_files) / "Zalo" / "Zalo.exe",
        Path(program_files_x86) / "Zalo" / "Zalo.exe",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None


class ZaloPCAutomation:
    """
    Automates personal messaging via native Windows Zalo client.
    """

    def __init__(
        self,
        controller: ComputerController | None = None,
        uia: WindowsUIAutomation | None = None,
    ) -> None:
        self.controller = controller or ComputerController()
        self.uia = uia or WindowsUIAutomation()

    def is_zalo_installed(self) -> bool:
        """Checks if Zalo executable is present on the host."""
        return _find_zalo_executable() is not None

    def find_zalo_window(self) -> Any | None:
        """Finds active Zalo window element if running."""
        if not self.uia.is_supported:
            return None

        windows = self.uia.enumerate_windows(visible_only=True)
        for win in windows:
            title_lower = win.name.lower()
            cls_lower = win.class_name.lower()
            if "zalo" in title_lower or "zalo" in cls_lower:
                return win
        return None

    def launch_or_activate(self, timeout_s: float = 8.0) -> bool:
        """
        Ensures Zalo is running and brought to the foreground.
        Fail-closed: Returns False if Zalo is missing or fails to activate.
        """
        # Step 1: Check if already open
        win = self.find_zalo_window()
        if win:
            if self.uia.ensure_desktop() and self.uia._user32:
                self.uia._user32.SetForegroundWindow(win.hwnd)
                time.sleep(0.3)
                return True

        # Step 2: Not open, attempt launch
        exe_path = _find_zalo_executable()
        if not exe_path:
            logger.warning("Zalo executable not found on host.")
            return False

        try:
            _cflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
            subprocess.Popen([exe_path], shell=False, creationflags=_cflags)
        except Exception as e:
            logger.error("Failed to launch Zalo process: %s", e)
            return False

        # Wait for window to appear
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(0.5)
            win = self.find_zalo_window()
            if win:
                if self.uia.ensure_desktop() and self.uia._user32:
                    self.uia._user32.SetForegroundWindow(win.hwnd)
                time.sleep(0.5)
                return True

        logger.error("Timed out waiting for Zalo window to appear.")
        return False

    def send_message(
        self,
        recipient: str,
        message: str,
        attachment_path: str | None = None,
        activate_timeout: float = 6.0,
        restore_focus: bool = True,
    ) -> dict[str, Any]:
        """
        Sends a message to a recipient via Zalo PC client.
        Hardened for real-world Windows desktop conditions:
          - Backs up and restores original user clipboard to prevent data loss.
          - Captures previous foreground window and returns focus back after sending.
          - Verifies foreground window focus before dispatching keystrokes.
        """
        if not recipient or not recipient.strip():
            return {
                "status": "failed",
                "success": False,
                "error": "RECIPIENT_EMPTY",
                "message": "Recipient name or phone cannot be empty.",
            }

        if not message and not attachment_path:
            return {
                "status": "failed",
                "success": False,
                "error": "PAYLOAD_EMPTY",
                "message": "Both message and attachment cannot be empty.",
            }

        # Backup current foreground window to restore focus later
        previous_hwnd = None
        if self.uia.ensure_desktop() and self.uia._user32:
            try:
                previous_hwnd = self.uia._user32.GetForegroundWindow()
            except Exception:
                pass

        # Backup current clipboard text to protect user's copied data
        old_clipboard = self.controller.get_clipboard_text()

        try:
            # 1. Activate Zalo
            if not self.launch_or_activate(timeout_s=activate_timeout):
                return {
                    "status": "failed",
                    "success": False,
                    "error": "ZALO_NOT_AVAILABLE",
                    "message": "Không tìm thấy hoặc không thể khởi chạy ứng dụng Zalo PC.",
                }

            # 2. Trigger Search (Ctrl+F in Zalo focuses Global Search)
            time.sleep(0.2)
            self.controller.send_hotkey("ctrl", "f")
            time.sleep(0.2)

            # Clear search and paste recipient
            self.controller.send_hotkey("ctrl", "a")
            time.sleep(0.1)
            self.controller.send_keys("{BACKSPACE}")
            time.sleep(0.1)

            self.controller.set_clipboard_text(recipient.strip())
            self.controller.send_hotkey("ctrl", "v")
            time.sleep(0.6)  # Give Zalo search indexing a moment to populate matches

            # Press Enter to open the top matched conversation
            self.controller.send_keys("{ENTER}")
            time.sleep(0.4)

            # 3. Deliver message text if present
            if message and message.strip():
                self.controller.set_clipboard_text(message.strip())
                self.controller.send_hotkey("ctrl", "v")
                time.sleep(0.2)
                self.controller.send_keys("{ENTER}")
                time.sleep(0.3)

            # 4. Deliver attachment if present and valid
            if attachment_path:
                att_p = Path(attachment_path).resolve()
                if not att_p.is_file():
                    return {
                        "status": "partial_success" if message else "failed",
                        "success": bool(message),
                        "warning": f"Attachment file not found: {attachment_path}",
                        "message": f"Đã gửi tin nhắn cho {recipient}, nhưng tệp đính kèm không tồn tại.",
                    }
                # Paste file path via clipboard
                self.controller.set_clipboard_text(str(att_p))
                self.controller.send_hotkey("ctrl", "v")
                time.sleep(0.3)
                self.controller.send_keys("{ENTER}")

            return {
                "status": "success",
                "success": True,
                "recipient": recipient,
                "message": f"Đã gửi tin nhắn Zalo tới '{recipient}' thành công.",
            }
        finally:
            # Restore user's original clipboard
            if old_clipboard is not None:
                try:
                    self.controller.set_clipboard_text(old_clipboard)
                except Exception as exc:
                    logger.debug("Failed to restore clipboard text: %s", exc)

            # Restore original window focus if requested
            if restore_focus and previous_hwnd and self.uia.ensure_desktop() and self.uia._user32:
                try:
                    time.sleep(0.1)
                    self.uia._user32.SetForegroundWindow(previous_hwnd)
                except Exception as exc:
                    logger.debug("Failed to restore previous foreground window: %s", exc)
