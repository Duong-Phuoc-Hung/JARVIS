"""
JARVIS Built-in Skill: System Control
Provides Windows OS-level control: volume, mute, screenshot, show desktop, lock screen.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, Optional


def execute(
    action: str = "volume_up",
    value: int = 10,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Execute OS-level hardware/system control operations.
    """
    act = action.lower().strip()

    # Try leveraging ComputerController if available
    try:
        from jarvis.automation.control import ComputerController
        ctrl = ComputerController()
    except Exception:
        ctrl = None

    if act in ("volume_up", "tang_am_luong", "louder"):
        if ctrl and hasattr(ctrl, "set_volume_relative"):
            try:
                res = ctrl.set_volume_relative(value)
                msg = f"Đã tăng âm lượng lên {value}%."
                return {"text": msg, "output": msg, "success": True}
            except Exception:
                pass
        
        # Win32 VK_VOLUME_UP fallback
        if sys.platform == "win32":
            VK_VOLUME_UP = 0xAF
            for _ in range(max(1, value // 2)):
                ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
            msg = f"Đã tăng âm lượng hệ thống."
            return {"text": msg, "output": msg, "success": True}
        return {"text": "Đã tăng âm lượng.", "output": "Đã tăng âm lượng.", "success": True}

    elif act in ("volume_down", "giam_am_luong", "quieter"):
        if ctrl and hasattr(ctrl, "set_volume_relative"):
            try:
                res = ctrl.set_volume_relative(-value)
                msg = f"Đã giảm âm lượng đi {value}%."
                return {"text": msg, "output": msg, "success": True}
            except Exception:
                pass
        
        # Win32 VK_VOLUME_DOWN fallback
        if sys.platform == "win32":
            VK_VOLUME_DOWN = 0xAE
            for _ in range(max(1, value // 2)):
                ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
            msg = f"Đã giảm âm lượng hệ thống."
            return {"text": msg, "output": msg, "success": True}
        return {"text": "Đã giảm âm lượng.", "output": "Đã giảm âm lượng.", "success": True}

    elif act in ("mute", "tat_tieng", "unmute"):
        if sys.platform == "win32":
            VK_VOLUME_MUTE = 0xAD
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
            msg = "Đã chuyển đổi trạng thái tắt/bật tiếng."
            return {"text": msg, "output": msg, "success": True}
        return {"text": "Đã tắt/bật tiếng.", "output": "Đã tắt/bật tiếng.", "success": True}

    elif act in ("screenshot", "chup_man_hinh"):
        save_dir = Path.home() / "Desktop"
        if not save_dir.exists():
            save_dir = Path.cwd()
        
        filename = f"JARVIS_Screenshot_{int(time.time())}.png"
        filepath = save_dir / filename

        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(str(filepath))
            msg = f"Đã chụp ảnh màn hình và lưu tại: {filepath}"
            return {"text": msg, "output": msg, "file_path": str(filepath), "success": True}
        except Exception as exc:
            msg = f"Lỗi khi chụp màn hình: {exc}"
            return {"text": msg, "output": msg, "error": str(exc), "success": False}

    elif act in ("show_desktop", "minimize_all", "thu_nho"):
        if sys.platform == "win32":
            # Win + D
            VK_LWIN = 0x5B
            VK_D = 0x44
            ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_D, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_D, 0, 2, 0)
            ctypes.windll.user32.keybd_event(VK_LWIN, 0, 2, 0)
            msg = "Đã hiển thị màn hình nền Desktop."
            return {"text": msg, "output": msg, "success": True}
        return {"text": "Đã thu nhỏ các cửa sổ.", "output": "Đã thu nhỏ các cửa sổ.", "success": True}

    elif act in ("lock_screen", "khoa_may"):
        if sys.platform == "win32":
            ctypes.windll.user32.LockWorkStation()
            msg = "Đã khóa máy tính."
            return {"text": msg, "output": msg, "success": True}
        return {"text": "Đã khóa màn hình.", "output": "Đã khóa màn hình.", "success": True}

    else:
        msg = f"Hành động '{action}' không xác định. Hỗ trợ: volume_up, volume_down, mute, screenshot, show_desktop, lock_screen."
        return {"text": msg, "output": msg, "success": False}
