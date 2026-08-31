"""
jarvis/comms/mobile_bridge.py
==============================
Mobile Device Bridge: bidirectional file and clipboard transfer.
Receive files from phone (via Telegram) to PC, send clipboard/screenshots
from PC to phone in under 2 seconds.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

from jarvis.core.paths import data_path

log = logging.getLogger("jarvis.comms.mobile_bridge")

_DEFAULT_SAVE_DIR = Path("downloads")


def _get_transfer_log_path() -> Path:
    """Resolves the transfer-history log path under the central JARVIS data dir."""
    return data_path("logs", "mobile_transfers.json")

_ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".txt", ".md", ".json", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".wav", ".mp4",
}
_MAX_FILE_SIZE_MB = 50




class MobileFileBridge:
    """
    Bidirectional file and clipboard bridge between mobile and desktop.
    Integrates with TelegramController for sending/receiving.
    """

    def __init__(
        self,
        save_directory: str = "",
        max_file_size_mb: int = _MAX_FILE_SIZE_MB,
        telegram_controller: Any | None = None,
    ) -> None:
        self.save_dir = Path(save_directory) if save_directory else _DEFAULT_SAVE_DIR
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_file_size_mb * 1024 * 1024
        self.telegram = telegram_controller
        log.info("MobileFileBridge initialized (save_dir=%s)", self.save_dir)

    # ------------------------------------------------------------------
    # Receive (Mobile → PC)
    # ------------------------------------------------------------------

    def receive_file(
        self,
        file_bytes: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Save an incoming file from mobile to the configured directory.

        Returns:
            dict with success, saved_path, size_kb keys
        """
        validation_error = self._validate_file(filename, len(file_bytes))
        if validation_error:
            log.warning("File rejected: %s — %s", filename, validation_error)
            return {"success": False, "error": validation_error}

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = Path(filename).stem[:40]
        suffix = Path(filename).suffix.lower()
        safe_name = f"{stem}_{ts}{suffix}"
        dest = self.save_dir / safe_name

        try:
            dest.write_bytes(file_bytes)
            size_kb = len(file_bytes) // 1024
            self._log_transfer("receive", filename, str(dest), size_kb)
            msg = f"✅ Đã lưu file từ điện thoại: {dest.name} ({size_kb}KB)"
            log.info("File received: %s (%dKB)", dest, size_kb)
            return {"success": True, "saved_path": str(dest), "size_kb": size_kb, "text": msg}
        except Exception as exc:
            log.error("File save error: %s", exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Send (PC → Mobile)
    # ------------------------------------------------------------------

    def send_clipboard_to_mobile(
        self,
        telegram_chat_id: int | None = None,
    ) -> dict[str, Any]:
        """Read system clipboard and send as text message to Telegram."""
        text = self._get_clipboard_text()
        if not text:
            return {"success": False, "error": "Clipboard trống hoặc không đọc được."}

        preview = text[:200] + ("..." if len(text) > 200 else "")
        log.info("Clipboard sent to mobile (%d chars)", len(text))

        if self.telegram and telegram_chat_id:
            try:
                self.telegram.send_message(telegram_chat_id, f"📋 Clipboard:\n{text}")
            except Exception as exc:
                log.warning("Telegram send failed: %s", exc)

        self._log_transfer("clipboard_send", "clipboard", "telegram", len(text))
        return {"success": True, "text": preview, "length": len(text)}

    def send_screenshot_to_mobile(
        self,
        telegram_chat_id: int | None = None,
    ) -> dict[str, Any]:
        """Capture screenshot and send to Telegram as image."""
        png_bytes = self._capture_screenshot()
        if not png_bytes:
            return {"success": False, "error": "Không thể chụp màn hình."}

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_path = self.save_dir / f"screenshot_{ts}.png"
        temp_path.write_bytes(png_bytes)
        size_kb = len(png_bytes) // 1024

        if self.telegram and telegram_chat_id:
            try:
                self.telegram.send_photo(telegram_chat_id, png_bytes, caption=f"📸 Screenshot {ts}")
            except Exception as exc:
                log.warning("Telegram photo send failed: %s", exc)

        self._log_transfer("screenshot_send", "screen", "telegram", size_kb)
        return {"success": True, "saved_path": str(temp_path), "size_kb": size_kb}

    def get_file_transfer_history(self) -> list[dict[str, Any]]:
        """Return recent file transfer records."""
        log_path = _get_transfer_log_path()
        if not log_path.exists():
            return []
        try:
            return json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _validate_file(self, filename: str, size_bytes: int) -> str | None:
        path_obj = Path(filename)
        suffix = path_obj.suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            return f"Định dạng file '{suffix}' không được phép."
        
        # Check against dangerous intermediate extensions (double extension attack, e.g. payload.exe.pdf)
        dangerous_suffixes = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".dll", ".scr", ".msi", ".jar", ".py", ".zip", ".sh"}
        all_suffixes = [s.lower() for s in path_obj.suffixes]
        if any(s in dangerous_suffixes for s in all_suffixes):
            return "Phát hiện cấu trúc tệp chứa phần mở rộng nguy hiểm (Double Extension)."

        if size_bytes > self.max_size_bytes:
            return f"File quá lớn ({size_bytes // 1024 // 1024}MB > {self.max_size_bytes // 1024 // 1024}MB)."
        return None

    def _get_clipboard_text(self) -> str | None:
        try:
            import ctypes
            ctypes.windll.user32.OpenClipboard(0)
            CF_UNICODETEXT = 13
            data = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
            text = ctypes.wstring_at(data) if data else None
            ctypes.windll.user32.CloseClipboard()
            return text
        except Exception:
            pass
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    def _capture_screenshot(self) -> bytes | None:
        try:
            import mss
            import mss.tools
            with mss.mss() as sct:
                img = sct.grab(sct.monitors[1])
                return mss.tools.to_png(img.rgb, img.size)
        except ImportError:
            pass
        try:
            import io

            from PIL import ImageGrab
            buf = io.BytesIO()
            ImageGrab.grab().save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            return None

    def _log_transfer(
        self,
        transfer_type: str,
        source: str,
        destination: str,
        size: int,
    ) -> None:
        record = {
            "type": transfer_type,
            "source": source,
            "destination": destination,
            "size": size,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        history = self.get_file_transfer_history()
        history.insert(0, record)
        history = history[:200]  # Keep last 200
        log_path = _get_transfer_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            log_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


__all__ = ["MobileFileBridge"]
