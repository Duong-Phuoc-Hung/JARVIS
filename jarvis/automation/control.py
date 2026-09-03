"""
ComputerController: OS Automation, Window Orchestration, Peripheral & System Control for Windows.
Provides window management, mouse/keyboard/clipboard manipulation, master volume,
screen brightness, bounded file search, and system folder launch.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any, Union

from jarvis.platform.windows import WindowsPlatformAPI, platform_win32


class ComputerController:
    """
    High-level Windows OS Controller for JARVIS.
    """

    SYSTEM_FOLDER_MAP: dict[str, str] = {
        "downloads": "Downloads",
        "tải về": "Downloads",
        "tai ve": "Downloads",
        "desktop": "Desktop",
        "màn hình chính": "Desktop",
        "man hinh chinh": "Desktop",
        "documents": "Documents",
        "tài liệu": "Documents",
        "tai lieu": "Documents",
        "pictures": "Pictures",
        "ảnh": "Pictures",
        "anh": "Pictures",
        "music": "Music",
        "nhạc": "Music",
        "nhac": "Music",
        "videos": "Videos",
        "video": "Videos",
        "phim": "Videos",
        "d": "D:\\",
        "d:": "D:\\",
        "d:\\": "D:\\",
        "d:/": "D:\\",
        "ổ d": "D:\\",
        "o d": "D:\\",
        "c": "C:\\",
        "c:": "C:\\",
        "c:\\": "C:\\",
        "c:/": "C:\\",
        "ổ c": "C:\\",
        "o c": "C:\\",
    }

    DEFAULT_IGNORE_DIRS = {
        "node_modules", ".git", ".venv", "venv", "__pycache__",
        "AppData", "Temp", "$Recycle.Bin", "System Volume Information",
        ".cache", "build", "dist", ".idea", ".vscode"
    }

    def __init__(self, win32: WindowsPlatformAPI | None = None) -> None:
        self.win32 = win32 or platform_win32
        self._current_volume: int = 50
        self._is_muted: bool = False
        self._current_brightness: int = 70

    # -----------------------------------------------------------------------
    # Window Management
    # -----------------------------------------------------------------------
    def get_active_window(self) -> dict[str, Any]:
        """Returns metadata of the current foreground top-level window."""
        win = self.win32.get_active_window()
        if not win:
            return {"hwnd": 0, "title": "", "process_name": "", "pid": 0}
        return {
            "hwnd": win.hwnd,
            "title": win.title,
            "process_name": win.process_name,
            "pid": win.pid,
            "rect": win.rect,
            "width": win.width,
            "height": win.height,
            "is_minimized": win.is_minimized,
            "is_maximized": win.is_maximized,
        }

    def minimize_all(self) -> bool:
        """Minimizes all windows (Show Desktop) via Win+D."""
        return bool(self.win32.send_hotkey("win", "d"))

    def close_active_window(self) -> bool:
        """Closes the current foreground window."""
        win = self.win32.get_active_window()
        if win and win.hwnd:
            return bool(self.win32.close_window(win.hwnd))
        return bool(self.win32.send_hotkey("alt", "f4"))

    def close_window(self, hwnd: int | None = None) -> bool:
        """Closes window with specified HWND, or active window if None."""
        if hwnd is not None and hwnd > 0:
            return bool(self.win32.close_window(hwnd))
        return self.close_active_window()

    def close_tab(self) -> bool:
        """Closes the active tab in current application (Ctrl+W)."""
        return bool(self.win32.send_hotkey("ctrl", "w"))

    def list_windows(self, visible_only: bool = True) -> list[dict[str, Any]]:
        """Lists active top-level windows."""
        windows = self.win32.list_windows(visible_only=visible_only)
        results: list[dict[str, Any]] = []
        for w in windows:
            results.append({
                "hwnd": w.hwnd,
                "title": w.title,
                "process_name": w.process_name,
                "pid": w.pid,
                "rect": w.rect,
                "width": w.width,
                "height": w.height,
                "is_minimized": w.is_minimized,
                "is_maximized": w.is_maximized,
            })
        return results

    def focus_window_by_title(self, title_substring: str) -> bool:
        """Searches visible windows and brings matching window to foreground."""
        if not title_substring:
            return False
        sub = title_substring.strip().lower()
        windows = self.win32.list_windows(visible_only=True)
        for w in windows:
            if sub in w.title.lower() or sub in w.process_name.lower():
                return bool(self.win32.focus_window(w.hwnd))
        return False

    def focus_window_by_pid(self, pid: int) -> bool:
        """Focuses window belonging to process ID."""
        if pid <= 0:
            return False
        windows = self.win32.list_windows(visible_only=True)
        for w in windows:
            if w.pid == pid:
                return bool(self.win32.focus_window(w.hwnd))
        return False

    def focus_app(self, target: str | int) -> bool:
        """Focuses an application by name substring or PID."""
        if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
            return self.focus_window_by_pid(int(target))
        return self.focus_window_by_title(str(target))

    def get_monitors(self) -> list[Any]:
        """Enumerates active physical displays/monitors."""
        if hasattr(self.win32, "get_monitors"):
            return self.win32.get_monitors()
        return []

    # -----------------------------------------------------------------------
    # Mouse, Keyboard & Clipboard Operations
    # -----------------------------------------------------------------------
    def mouse_click(
        self,
        x: int | None = None,
        y: int | None = None,
        button: str = "left",
        clicks: int = 1,
    ) -> bool:
        """Simulates mouse click at coordinates (or current cursor position)."""
        try:
            import pyautogui  # type: ignore
            pyautogui.click(x=x, y=y, clicks=clicks, button=button)
            return True
        except Exception:
            pass

        # Fallback using ctypes
        if sys.platform == "win32" and hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            u32 = ctypes.windll.user32
            if x is not None and y is not None:
                u32.SetCursorPos(int(x), int(y))
            # MOUSEEVENTF_LEFTDOWN = 0x0002, LEFTUP = 0x0004
            down_flag = 0x0002 if button == "left" else 0x0008
            up_flag = 0x0004 if button == "left" else 0x0010
            for _ in range(clicks):
                u32.mouse_event(down_flag, 0, 0, 0, 0)
                u32.mouse_event(up_flag, 0, 0, 0, 0)
            return True
        return True

    def mouse_move(self, x: int, y: int, smooth: bool = False) -> bool:
        """Moves mouse cursor to target coordinates."""
        try:
            import pyautogui  # type: ignore
            dur = 0.2 if smooth else 0.0
            pyautogui.moveTo(x, y, duration=dur)
            return True
        except Exception:
            pass

        if sys.platform == "win32" and hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
            return True
        return True

    def mouse_scroll(self, clicks: int) -> bool:
        """Scrolls mouse wheel (positive up, negative down)."""
        try:
            import pyautogui  # type: ignore
            pyautogui.scroll(clicks)
            return True
        except Exception:
            pass

        if sys.platform == "win32" and hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            # MOUSEEVENTF_WHEEL = 0x0800
            ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(clicks * 120), 0)
            return True
        return True

    def type_text(self, text: str) -> bool:
        """Types text accurately with Unicode character support."""
        if not text:
            return False
        return bool(self.win32.type_unicode_text(text))

    def send_hotkey(self, *keys: str) -> bool:
        """Injects keyboard hotkey combination."""
        return bool(self.win32.send_hotkey(*keys))

    def get_clipboard_text(self) -> str:
        """Reads plain text from Windows clipboard."""
        try:
            import pyperclip  # type: ignore
            return pyperclip.paste() or ""
        except Exception:
            pass

        if sys.platform == "win32" and hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            try:
                u32 = ctypes.windll.user32
                k32 = ctypes.windll.kernel32

                u32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
                u32.OpenClipboard.restype = ctypes.wintypes.BOOL
                u32.CloseClipboard.argtypes = []
                u32.CloseClipboard.restype = ctypes.wintypes.BOOL
                u32.GetClipboardData.argtypes = [ctypes.c_uint]
                u32.GetClipboardData.restype = ctypes.c_void_p
                k32.GlobalLock.argtypes = [ctypes.c_void_p]
                k32.GlobalLock.restype = ctypes.c_void_p
                k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
                k32.GlobalUnlock.restype = ctypes.wintypes.BOOL

                if u32.OpenClipboard(None):
                    try:
                        # CF_UNICODETEXT = 13
                        h_glb = u32.GetClipboardData(13)
                        if h_glb:
                            ptr = k32.GlobalLock(h_glb)
                            if ptr:
                                try:
                                    val = ctypes.c_wchar_p(ptr).value or ""
                                    self._clipboard_cache = val
                                    return val
                                finally:
                                    k32.GlobalUnlock(h_glb)
                    finally:
                        u32.CloseClipboard()
            except Exception:
                pass
        return getattr(self, "_clipboard_cache", "")

    def set_clipboard_text(self, text: str) -> bool:
        """Sets plain text to Windows clipboard."""
        self._clipboard_cache = text
        try:
            import pyperclip  # type: ignore
            pyperclip.copy(text)
            return True
        except Exception:
            pass

        if sys.platform == "win32" and hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            try:
                u32 = ctypes.windll.user32
                k32 = ctypes.windll.kernel32

                u32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
                u32.OpenClipboard.restype = ctypes.wintypes.BOOL
                u32.CloseClipboard.argtypes = []
                u32.CloseClipboard.restype = ctypes.wintypes.BOOL
                u32.EmptyClipboard.argtypes = []
                u32.EmptyClipboard.restype = ctypes.wintypes.BOOL
                u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
                u32.SetClipboardData.restype = ctypes.c_void_p
                k32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
                k32.GlobalAlloc.restype = ctypes.c_void_p
                k32.GlobalLock.argtypes = [ctypes.c_void_p]
                k32.GlobalLock.restype = ctypes.c_void_p
                k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
                k32.GlobalUnlock.restype = ctypes.wintypes.BOOL

                if u32.OpenClipboard(None):
                    try:
                        u32.EmptyClipboard()
                        # GMEM_MOVEABLE = 0x0002
                        buf = ctypes.create_unicode_buffer(text)
                        bytes_len = (len(text) + 1) * 2
                        h_glb = k32.GlobalAlloc(0x0002, bytes_len)
                        if h_glb:
                            ptr = k32.GlobalLock(h_glb)
                            if ptr:
                                ctypes.memmove(ptr, buf, bytes_len)
                                k32.GlobalUnlock(h_glb)
                                u32.SetClipboardData(13, h_glb)
                                return True
                    finally:
                        u32.CloseClipboard()
            except Exception:
                pass
        return True

    def copy_selection(self) -> str:
        """Sends Ctrl+C and reads clipboard text."""
        self.send_hotkey("ctrl", "c")
        time.sleep(0.1)
        return self.get_clipboard_text()

    def paste_text(self, text: str | None = None) -> bool:
        """Pastes text (or current clipboard contents) via Ctrl+V."""
        if text is not None:
            self.set_clipboard_text(text)
        return self.send_hotkey("ctrl", "v")

    # -----------------------------------------------------------------------
    # Master Volume Adjustment
    # -----------------------------------------------------------------------
    def get_volume(self) -> int:
        """Returns master volume level (0-100%)."""
        try:
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities  # type: ignore
            speakers = AudioUtilities.GetSpeakers()
            if speakers:
                endpoint = speakers.Activate(
                    AudioUtilities.IAudioEndpointVolume._iid_,
                    CLSCTX_ALL,
                    None,
                )
                vol = endpoint.GetMasterVolumeLevelScalar()
                self._current_volume = int(round(vol * 100))
                return self._current_volume
        except Exception:
            pass
        return self._current_volume

    def set_volume(self, level_percent: int) -> int:
        """Sets master volume to an exact percentage (0-100%)."""
        level = max(0, min(100, int(level_percent)))
        self._current_volume = level
        try:
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities  # type: ignore
            speakers = AudioUtilities.GetSpeakers()
            if speakers:
                endpoint = speakers.Activate(
                    AudioUtilities.IAudioEndpointVolume._iid_,
                    CLSCTX_ALL,
                    None,
                )
                endpoint.SetMasterVolumeLevelScalar(level / 100.0, None)
                return self._current_volume
        except Exception:
            pass
        return self._current_volume

    def change_volume(self, delta_percent: int) -> int:
        """Adjusts master volume by delta (+10%, -10%)."""
        delta = int(delta_percent)
        new_level = max(0, min(100, self.get_volume() + delta))
        self.set_volume(new_level)

        # Dispatch keystrokes for hardware feedback
        steps = max(1, abs(delta) // 2)
        key = "volume_up" if delta > 0 else "volume_down"
        for _ in range(steps):
            self.win32.send_hotkey(key)

        return self._current_volume

    def mute_volume(self, mute: bool | None = None) -> bool:
        """Toggles or sets master audio mute state."""
        if mute is None:
            self._is_muted = not self._is_muted
        else:
            self._is_muted = bool(mute)

        try:
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities  # type: ignore
            speakers = AudioUtilities.GetSpeakers()
            if speakers:
                endpoint = speakers.Activate(
                    AudioUtilities.IAudioEndpointVolume._iid_,
                    CLSCTX_ALL,
                    None,
                )
                endpoint.SetMute(int(self._is_muted), None)
                return self._is_muted
        except Exception:
            pass

        self.win32.send_hotkey("volume_mute")
        return self._is_muted

    def is_muted(self) -> bool:
        """Returns True if audio is currently muted."""
        return self._is_muted

    # -----------------------------------------------------------------------
    # Display Brightness Adjustment
    # -----------------------------------------------------------------------
    def get_brightness(self) -> int:
        """Returns primary display brightness (0-100%)."""
        return self._current_brightness

    def set_brightness(self, level: int) -> int:
        """Sets display brightness to exact level (0-100%)."""
        lvl = max(0, min(100, int(level)))
        self._current_brightness = lvl

        try:
            import screen_brightness_control as sbc  # type: ignore
            sbc.set_brightness(lvl)
            return self._current_brightness
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                cmd = f"powershell -NoProfile -Command \"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {lvl})\""
                _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3, creationflags=_cflags)
            except Exception:
                pass

        return self._current_brightness

    def change_brightness(self, delta: int) -> int:
        """Adjusts brightness by delta (+10, -10)."""
        new_val = max(0, min(100, self.get_brightness() + int(delta)))
        return self.set_brightness(new_val)

    # -----------------------------------------------------------------------
    # Fast Local File Search & Folder Opener
    # -----------------------------------------------------------------------
    def search_files(
        self,
        filename: str,
        root_dir: str | None = None,
        max_depth: int = 4,
        max_results: int = 20,
    ) -> list[str]:
        """
        Fast bounded local file search using os.scandir.
        Limits search depth to `max_depth` (default 4) and filters ignored directories.
        """
        if not filename:
            return []

        search_root = root_dir
        if not search_root:
            search_root = os.path.expanduser("~")

        if not os.path.isdir(search_root):
            return []

        pattern = filename.strip().lower()
        matches: list[str] = []

        # (current_path, current_depth)
        queue: deque[tuple[str, int]] = deque([(os.path.abspath(search_root), 0)])

        while queue and len(matches) < max_results:
            current_path, depth = queue.popleft()
            if depth > max_depth:
                continue

            try:
                with os.scandir(current_path) as entries:
                    for entry in entries:
                        try:
                            # Skip ignored system / virtual directories
                            if entry.is_dir(follow_symlinks=False):
                                if entry.name in self.DEFAULT_IGNORE_DIRS or entry.name.startswith("."):
                                    continue
                                if depth < max_depth:
                                    queue.append((entry.path, depth + 1))
                            elif entry.is_file(follow_symlinks=False):
                                if pattern in entry.name.lower():
                                    matches.append(entry.path)
                                    if len(matches) >= max_results:
                                        break
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue

        return matches

    def resolve_folder_path(self, folder_name_or_path: str) -> str | None:
        """Resolves shortcut names and aliases to absolute folder paths."""
        raw = folder_name_or_path.strip().lower()
        if raw in self.SYSTEM_FOLDER_MAP:
            mapped = self.SYSTEM_FOLDER_MAP[raw]
            if mapped.endswith(":\\"):
                return mapped
            return os.path.join(os.path.expanduser("~"), mapped)

        # Check for partial matches — only for keys >= 4 chars to avoid
        # false positives (e.g. key "d" matching "invalid_folder_alias_xyz")
        for k, v in self.SYSTEM_FOLDER_MAP.items():
            if len(k) >= 4 and raw == k:
                if v.endswith(":\\"):
                    return v
                return os.path.join(os.path.expanduser("~"), v)

        # Fallback to direct path
        expanded = os.path.expanduser(folder_name_or_path.strip())
        abs_path = os.path.abspath(expanded)
        if os.path.isdir(abs_path):
            return abs_path
        return None

    def open_folder(self, folder_name_or_path: str) -> bool:
        """Opens specified folder in Windows Explorer."""
        target = self.resolve_folder_path(folder_name_or_path)
        if not target or not os.path.exists(target):
            return False

        try:
            if hasattr(os, "startfile") and sys.platform == "win32":
                os.startfile(target)  # type: ignore
                return True
            else:
                _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.Popen(["explorer.exe", target], creationflags=_cflags)
                return True
        except Exception:
            return False

    def take_screenshot(self, output_path: str | None = None) -> str:
        """Captures screenshot and saves to Desktop by default."""
        target = output_path
        if not target:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            os.makedirs(desktop, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = os.path.join(desktop, f"JARVIS_Screenshot_{ts}.png")

        # Try PIL ImageGrab
        try:
            from PIL import ImageGrab  # type: ignore
            img = ImageGrab.grab()
            img.save(target)
            return target
        except Exception:
            pass

        # Try mss
        try:
            import mss  # type: ignore
            with mss.mss() as sct:
                sct.shot(output=target)
                return target
        except Exception:
            pass

        return target

    # -----------------------------------------------------------------------
    # Universal Application & Website Opener
    # -----------------------------------------------------------------------
    APP_MAP: dict[str, Union[str, list[str]]] = {
        "chrome": ["chrome", "google-chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"],
        "google chrome": ["chrome", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"],
        "trình duyệt": ["chrome", "msedge"],
        "browser": ["chrome", "msedge"],
        "edge": ["msedge", "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"],
        "microsoft edge": ["msedge"],
        "cốc cốc": ["coccoc", "C:\\Users\\%USERNAME%\\AppData\\Local\\CocCoc\\Browser\\Application\\browser.exe"],
        "firefox": ["firefox", "C:\\Program Files\\Mozilla Firefox\\firefox.exe"],
        "notepad": "notepad.exe",
        "sổ tay": "notepad.exe",
        "ghi chú": "notepad.exe",
        "calculator": "calc.exe",
        "máy tính": "calc.exe",
        "calc": "calc.exe",
        "word": ["winword.exe", "start winword"],
        "ms word": ["winword.exe"],
        "microsoft word": ["winword.exe"],
        "excel": ["excel.exe", "start excel"],
        "ms excel": ["excel.exe"],
        "microsoft excel": ["excel.exe"],
        "bảng tính": ["excel.exe"],
        "powerpoint": ["powerpnt.exe", "start powerpnt"],
        "ppt": ["powerpnt.exe"],
        "cursor": ["cursor", "cursor.cmd", "C:\\Users\\%USERNAME%\\AppData\\Local\\Programs\\cursor\\Cursor.exe"],
        "cursor ide": ["cursor"],
        "cursor ai": ["cursor"],
        "vscode": ["code", "code.cmd", "C:\\Users\\%USERNAME%\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe"],
        "vs code": ["code", "code.cmd"],
        "visual studio code": ["code"],
        "code": ["code", "code.cmd"],
        "task manager": "taskmgr.exe",
        "quản lý tác vụ": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "terminal": ["wt.exe", "powershell.exe"],
        "powershell": "powershell.exe",
        "cmd": "cmd.exe",
        "dòng lệnh": "cmd.exe",
        "command prompt": "cmd.exe",
        "paint": "mspaint.exe",
        "vẽ": "mspaint.exe",
        "spotify": ["spotify.exe", "C:\\Users\\%USERNAME%\\AppData\\Roaming\\Spotify\\Spotify.exe"],
        "discord": ["discord.exe", "C:\\Users\\%USERNAME%\\AppData\\Local\\Discord\\Update.exe --processStart Discord.exe"],
        "telegram": ["telegram.exe", "C:\\Users\\%USERNAME%\\AppData\\Roaming\\Telegram Desktop\\Telegram.exe"],
        "zalo": ["zalo.exe", "C:\\Users\\%USERNAME%\\AppData\\Local\\Programs\\Zalo\\Zalo.exe"],
        "settings": "ms-settings:",
        "cài đặt": "ms-settings:",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "quản lý file": "explorer.exe",
    }

    WEBSITE_MAP: dict[str, str] = {
        "youtube": "https://www.youtube.com",
        "yt": "https://www.youtube.com",
        "google": "https://www.google.com",
        "gg": "https://www.google.com",
        "facebook": "https://www.facebook.com",
        "fb": "https://www.facebook.com",
        "github": "https://www.github.com",
        "gh": "https://www.github.com",
        "chatgpt": "https://chatgpt.com",
        "gpt": "https://chatgpt.com",
        "claude": "https://claude.ai",
        "binance": "https://www.binance.com",
        "zalo web": "https://chat.zalo.me",
        "gmail": "https://mail.google.com",
        "email": "https://mail.google.com",
        "mail": "https://mail.google.com",
        "hòm thư": "https://mail.google.com",
        "vnexpress": "https://vnexpress.net",
        "báo": "https://vnexpress.net",
        "dantri": "https://dantri.com.vn",
        "dân trí": "https://dantri.com.vn",
        "shopee": "https://shopee.vn",
        "tiki": "https://tiki.vn",
        "lazada": "https://lazada.vn",
        "reddit": "https://www.reddit.com",
        "twitter": "https://x.com",
        "x": "https://x.com",
        "bản đồ": "https://maps.google.com",
        "google maps": "https://maps.google.com",
        "maps": "https://maps.google.com",
        "dịch": "https://translate.google.com",
        "google dịch": "https://translate.google.com",
        "translate": "https://translate.google.com",
    }

    def open_app(self, app_name: str) -> dict[str, Any]:
        """Launches target application by friendly name, alias, or executable path."""
        if not app_name:
            return {"success": False, "error": "Application name is empty"}

        clean_name = app_name.strip().lower()
        clean_name = re.sub(r"^(?:mở|bật|khởi động|chạy|open|launch|start)\s+", "", clean_name).strip()

        # Check if it's actually a website query
        if clean_name in self.WEBSITE_MAP or any(clean_name.endswith(ext) for ext in (".com", ".vn", ".net", ".org", ".io", ".edu")):
            return self.open_website(clean_name)

        # Check if it's a folder/directory
        if clean_name in self.SYSTEM_FOLDER_MAP or os.path.isdir(clean_name):
            ok = self.open_folder(clean_name)
            return {
                "success": ok,
                "app": clean_name,
                "message": f"Đã mở thư mục '{clean_name}', thưa Ngài." if ok else f"Không thể mở thư mục '{clean_name}'.",
            }

        # Resolve candidate executables
        candidates: list[str] = []
        if clean_name in self.APP_MAP:
            mapped = self.APP_MAP[clean_name]
            candidates = mapped if isinstance(mapped, list) else [mapped]
        else:
            for k, v in self.APP_MAP.items():
                if k in clean_name or clean_name in k:
                    candidates = v if isinstance(v, list) else [v]
                    break
            if not candidates:
                candidates = [clean_name, f"{clean_name}.exe"]

        for cand in candidates:
            expanded = os.path.expandvars(os.path.expanduser(cand))
            try:
                if expanded.startswith("ms-") or expanded.endswith(":"):
                    if sys.platform == "win32":
                        os.startfile(expanded)  # type: ignore
                        return {"success": True, "app": clean_name, "message": f"Đã mở {clean_name}, thưa Ngài."}

                if os.path.exists(expanded):
                    if sys.platform == "win32" and hasattr(os, "startfile"):
                        os.startfile(expanded)  # type: ignore
                    else:
                        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                        subprocess.Popen([expanded], shell=False, creationflags=_cflags)
                    return {"success": True, "app": clean_name, "message": f"Đã mở ứng dụng {clean_name}, thưa Ngài."}

                _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.Popen(
                    f"start \"\" \"{expanded}\"",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_cflags,
                )
                return {"success": True, "app": clean_name, "message": f"Đã khởi chạy {clean_name}, thưa Ngài."}
            except Exception:
                continue

        try:
            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(clean_name, shell=True, creationflags=_cflags)
            return {"success": True, "app": clean_name, "message": f"Đã khởi chạy {clean_name}, thưa Ngài."}
        except Exception as exc:
            return {"success": False, "app": clean_name, "error": str(exc), "message": f"Không thể mở {clean_name}: {exc}"}

    def open_website(self, target: str) -> dict[str, Any]:
        """Opens a website URL, search query, or friendly domain in the default browser."""
        if not target:
            return {"success": False, "error": "Website target is empty"}

        clean = target.strip().lower()
        clean = re.sub(r"^(?:mở|truy cập|vào|open|go to|visit)\s+", "", clean).strip()

        url = ""
        yt_search = re.search(r"(?:youtube|yt)\s+(?:xem|nghe|tìm|bài)?\s*(.+)", clean)
        if yt_search:
            q = yt_search.group(1).strip()
            _q_encoded = subprocess.list2cmdline([q]).strip('"')
            url = f"https://www.youtube.com/results?search_query={_q_encoded}"
        elif clean.startswith(("tìm kiếm ", "search ", "tra cứu ")):
            q = re.sub(r"^(?:tìm kiếm|search|tra cứu)\s+", "", clean).strip()
            url = f"https://www.google.com/search?q={q}"
        elif clean in self.WEBSITE_MAP:
            url = self.WEBSITE_MAP[clean]
        elif any(clean.startswith(p) for p in ("http://", "https://")):
            url = target.strip()
        elif any(clean.endswith(ext) or ext in clean for ext in (".com", ".vn", ".net", ".org", ".io", ".edu", ".gov")):
            url = f"https://{clean}" if not clean.startswith("http") else clean
        else:
            url = f"https://www.google.com/search?q={clean}"

        try:
            import webbrowser
            webbrowser.open(url)
            domain_name = clean.split()[0] if clean else "trang web"
            return {
                "success": True,
                "url": url,
                "message": f"Đã mở {domain_name} ({url}) cho Ngài.",
            }
        except Exception:
            try:
                if sys.platform == "win32" and hasattr(os, "startfile"):
                    os.startfile(url)  # type: ignore
                    return {"success": True, "url": url, "message": f"Đã mở {url} cho Ngài."}
                _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.Popen(f"start {url}", shell=True, creationflags=_cflags)
                return {"success": True, "url": url, "message": f"Đã mở {url} cho Ngài."}
            except Exception as exc:
                return {"success": False, "url": url, "error": str(exc), "message": f"Không thể mở trang web: {exc}"}
