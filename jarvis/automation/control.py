"""
ComputerController: OS Automation, Window Orchestration, Peripheral & System Control for Windows.
Provides window management, mouse/keyboard/clipboard manipulation, master volume,
screen brightness, bounded file search, and system folder launch.
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any, Union
from urllib.parse import urlencode, urlsplit

from jarvis.core.runaway_guard import canonical_app_key, canonical_url_key, launch_dedupe_guard
from jarvis.platform.windows import WindowsPlatformAPI, platform_win32

logger = logging.getLogger(__name__)


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
        from jarvis.automation.app_catalog import ApplicationCatalog
        self.app_catalog = ApplicationCatalog()
        self.win32 = win32 or platform_win32
        from jarvis.automation.app_launcher import WindowsApplicationLauncher, WindowsWindowProbe
        self.app_launcher = WindowsApplicationLauncher(probe=WindowsWindowProbe(self.win32))
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
    @staticmethod
    def _get_audio_endpoint(speakers: Any) -> Any:
        if speakers is None:
            return None
        if hasattr(speakers, "EndpointVolume"):
            return speakers.EndpointVolume
        if hasattr(speakers, "Activate"):
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities  # type: ignore
            return speakers.Activate(
                AudioUtilities.IAudioEndpointVolume._iid_,
                CLSCTX_ALL,
                None,
            )
        if hasattr(speakers, "_dev") and hasattr(speakers._dev, "Activate"):
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities  # type: ignore
            return speakers._dev.Activate(
                AudioUtilities.IAudioEndpointVolume._iid_,
                CLSCTX_ALL,
                None,
            )
        return None

    # -----------------------------------------------------------------------
    # Master Volume Adjustment
    # -----------------------------------------------------------------------
    def get_volume(self) -> int:
        """Returns master volume level (0-100%)."""
        try:
            from pycaw.pycaw import AudioUtilities  # type: ignore
            speakers = AudioUtilities.GetSpeakers()
            endpoint = self._get_audio_endpoint(speakers)
            if endpoint:
                vol = endpoint.GetMasterVolumeLevelScalar()
                self._current_volume = int(round(vol * 100))
                return self._current_volume
        except Exception:
            pass
        return self._current_volume

    def set_volume(self, level_percent: int) -> int | None:
        """Sets master volume to an exact percentage (0-100%)."""
        level = max(0, min(100, int(level_percent)))
        try:
            from pycaw.pycaw import AudioUtilities  # type: ignore
            speakers = AudioUtilities.GetSpeakers()
            endpoint = self._get_audio_endpoint(speakers)
            if endpoint:
                endpoint.SetMasterVolumeLevelScalar(level / 100.0, None)
                self._current_volume = level
                return self._current_volume
            else:
                logger.warning("No audio speaker endpoint found on this host")
                return None
        except Exception as exc:
            logger.warning("Failed to set master volume via pycaw: %s", exc)
            return None

    def change_volume(self, delta_percent: int) -> int | None:
        """
        Adjusts master volume by delta (+10%, -10%) via the authoritative
        pycaw backend only.

        H-08 review fix: this previously ALSO sent volume_up/volume_down
        hotkeys after a successful set_volume() -- on a real Windows
        machine that double-applies the requested delta (pycaw sets the
        exact level, then the hotkeys shift it again). Worse, the hotkeys
        fired unconditionally even when set_volume() failed and returned
        None, so real hardware volume could still change while JARVIS
        truthfully reported failure. pycaw is now the sole backend and
        the sole side effect: no hotkey fallback ever fires, and a failed
        set_volume() call has zero secondary effect.

        H-08 final correction: delta=0 is now a REAL no-op -- it returns
        the current volume via a pure read (get_volume(), which only ever
        calls the read-only GetMasterVolumeLevelScalar()) and never calls
        set_volume()/SetMasterVolumeLevelScalar() at all, not even as a
        harmless-seeming write-back of the unchanged value. "No change
        requested" must mean zero backend writes, not a same-value write.
        """
        delta = int(delta_percent)
        if delta == 0:
            return self.get_volume()
        new_level = max(0, min(100, self.get_volume() + delta))
        return self.set_volume(new_level)

    def mute_volume(self, mute: bool | None = None) -> bool | None:
        """
        Sets (mute=True/False) or toggles (mute=None) the REAL master
        audio endpoint mute state via pycaw.

        H-08 fix: this previously wrote self._is_muted BEFORE ever
        attempting the real backend call, then -- on any pycaw failure --
        silently fell back to blindly sending a "volume_mute" TOGGLE
        hotkey while still returning the pre-computed cached value as if
        it were a confirmed result. That hotkey cannot verify it achieved
        the requested desired state (a toggle can just as easily undo a
        real prior mute as apply one), so the old code could report
        success for the opposite of what actually happened, and could
        never fail closed at all -- every call "succeeded".

        Returns the confirmed new state on success, or None if the
        backend endpoint could not be reached/controlled -- callers MUST
        treat None as failure and must NEVER report success or silently
        keep serving the last cached self._is_muted value in that case.
        self._is_muted is written ONLY after a real, unraised SetMute()
        call -- never before, never on failure -- mirroring
        set_volume()'s existing fail-closed contract for this same class.
        A toggle (mute=None) reads the REAL current hardware mute state
        via GetMute() first, rather than trusting a possibly-stale cached
        self._is_muted (which could have drifted if the mute state
        changed through another path, e.g. a physical hardware mute key).

        H-08 review fix: after SetMute(), the resulting REAL endpoint
        state is read back via GetMute() and compared against the
        requested value before self._is_muted is updated or success is
        reported. A confirmed SetMute() call is not, by itself, proof the
        endpoint actually ended up in the requested state -- if the
        read-back disagrees, this fails closed (returns None) and leaves
        the cached state untouched, exactly like a raised exception would.
        """
        try:
            from pycaw.pycaw import AudioUtilities  # type: ignore
            speakers = AudioUtilities.GetSpeakers()
            # _get_audio_endpoint() lazily imports comtypes itself, only on
            # the code path that actually needs a fresh .Activate() call --
            # the mocked/real EndpointVolume-attribute path used by tests
            # and some pycaw versions never needs comtypes at all.
            endpoint = self._get_audio_endpoint(speakers)
            if endpoint is None:
                logger.warning("No audio speaker endpoint found on this host")
                return None

            new_value = (not bool(endpoint.GetMute())) if mute is None else bool(mute)
            endpoint.SetMute(int(new_value), None)
            confirmed = bool(endpoint.GetMute())
            if confirmed != new_value:
                logger.warning(
                    "Speaker mute set to %s but backend read-back reports %s; "
                    "treating as a failed request rather than claiming success.",
                    new_value, confirmed,
                )
                return None
            self._is_muted = confirmed
            return confirmed
        except Exception as exc:
            logger.warning("Failed to set speaker mute via pycaw: %s", exc)
            return None

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
        # H-07 fix: the router's universal web-launcher regex lists both
        # "claude" and "claude ai" as SITE alternatives, but regex
        # alternation tries "claude" first and succeeds at that position
        # for input like "mở claude ai" (leaving " ai" to be absorbed as a
        # trailing "query"). _make_web_intent() then reconstructs
        # target=f"{site} {query}" = "claude ai", which prioritizes over
        # the correctly-resolvable site="claude" in _handle_web_open()'s
        # dest lookup -- without this key, that reconstructed phrase missed
        # WEBSITE_MAP entirely and silently fell through to a Google search
        # for "claude ai" instead of opening Claude. Mirrors the existing
        # "google dịch"/"zalo web" precedent below for multi-word aliases.
        "claude ai": "https://claude.ai",
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

    def open_installed_app(self, app_name: str) -> dict[str, Any]:
        """Launch an exact catalog match; never guess or claim unverified UI success."""
        matches = self.app_catalog.resolve(app_name)
        if not matches and not self.app_catalog.errors:
            # Fixed aliases remain useful, but resolve them back into the
            # discovered catalog; never launch an unchecked guessed path.
            import ntpath
            mapped = self.APP_MAP.get(app_name.strip().casefold(), [])
            aliases = mapped if isinstance(mapped, list) else [mapped]
            resolved_matches = []
            for alias in aliases:
                if not isinstance(alias, str) or " --" in alias or alias.endswith(":"):
                    continue
                for entry in self.app_catalog.resolve(ntpath.splitext(ntpath.basename(alias))[0]):
                    if entry not in resolved_matches:
                        resolved_matches.append(entry)
            matches = tuple(resolved_matches)
        if self.app_catalog.errors:
            return {"success": False, "error_code": "APP_DISCOVERY_UNAVAILABLE", "message": "Không đọc được danh mục ứng dụng Windows."}
        if not matches:
            return {"success": False, "error_code": "APP_NOT_FOUND", "message": f"Không tìm thấy ứng dụng '{app_name}' trong danh mục Windows."}
        if len(matches) != 1:
            return {"success": False, "error_code": "APP_AMBIGUOUS", "message": "Có nhiều ứng dụng cùng tên; cần chọn ứng dụng trước khi mở.",
                    "candidates": [{"name": app.name, "kind": app.kind, "target": app.target} for app in matches]}
        app = matches[0]
        if not launch_dedupe_guard.should_allow("app_launch", canonical_app_key(app.name)):
            return {"success": False, "error_code": "LAUNCH_RATE_LIMITED", "message": "Yêu cầu mở ứng dụng lặp lại quá nhanh."}
        result = self.app_launcher.open(app)
        if result.get("error_code") == "APP_NOT_FOUND":
            self.app_catalog.refresh()
        return result

    def open_app(self, app_name: str) -> dict[str, Any]:
        """Launches target application by friendly name, alias, or executable path."""
        if not app_name:
            return {"success": False, "error": "Application name is empty"}

        clean_name = app_name.strip().lower()
        clean_name = re.sub(r"^(?:mở|bật|khởi động|chạy|open|launch|start)\s+", "", clean_name).strip()

        # P0 runaway-hardening: every prior call unconditionally re-launched the
        # target app -- a repeated/runaway dispatch (e.g. a passive
        # acoustic-trigger loop, or a garbled STT transcript matching the same
        # app repeatedly) could spawn it over and over. Report a suppressed
        # repeat truthfully rather than a fabricated success. Keyed by
        # canonical APP identity so this shares one budget with
        # SpotifyPlugin/CursorPlugin for the same real application reached
        # through their own dedicated action names.
        if not launch_dedupe_guard.should_allow("app_launch", canonical_app_key(clean_name)):
            return {
                "success": False,
                "app": clean_name,
                "status": "suppressed",
                "error": f"Yêu cầu mở '{clean_name}' bị chặn do lặp lại quá nhanh.",
                "error_code": "LAUNCH_RATE_LIMITED",
            }

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
            # Unknown names must not silently launch a different known app.
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

                # A6 fix (2026-09-04): shell=True + `start "" "..."` always exits 0 even
                # for non-existent executables — must verify via shutil.which first.
                import shutil as _shutil
                _resolved_cand = _shutil.which(expanded) or _shutil.which(cand)
                if not _resolved_cand:
                    continue  # not on PATH, skip to next candidate

                _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.Popen(
                    [_resolved_cand],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_cflags,
                )
                return {"success": True, "app": clean_name, "message": f"Đã khởi chạy {clean_name}, thưa Ngài."}
            except Exception:
                continue


        # Last resort: try spawning via shell (handles apps on PATH not in APP_MAP).
        # A6 fix (2026-09-04): previously returned success=True unconditionally here
        # because shell=True never raises CalledProcessError even for unknown names.
        # Now we check shutil.which() first: only claim success if the executable
        # exists on PATH. If not found, return fail-closed success=False.
        import shutil
        resolved = shutil.which(clean_name) or shutil.which(f"{clean_name}.exe")
        if not resolved:
            return {
                "success": False,
                "app": clean_name,
                "error_code": "APP_NOT_FOUND",
                "message": f"Không tìm thấy ứng dụng '{clean_name}' trên hệ thống.",
            }
        try:
            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(resolved, shell=False, creationflags=_cflags)
            return {"success": True, "app": clean_name, "message": f"Đã khởi chạy {clean_name}, thưa Ngài."}
        except Exception as exc:
            return {"success": False, "app": clean_name, "error": str(exc), "message": f"Không thể mở {clean_name}: {exc}"}

    def open_website(self, target: str) -> dict[str, Any]:
        """Opens a website URL, search query, or friendly domain in the default browser."""
        if not target:
            return {"success": False, "error": "Website target is empty"}

        clean = re.sub(r"^(?:mở|truy cập|vào|open|go to|visit)\s+", "", target.strip(), flags=re.IGNORECASE).strip()
        if not clean or any(ord(char) < 32 for char in clean):
            return {"success": False, "error_code": "INVALID_URL", "error": "Invalid website target"}

        url = ""
        yt_search = re.fullmatch(r"(?:youtube|yt)\s+(?:(?:xem|nghe|tìm|bài)\s+)?(.+)", clean, re.IGNORECASE)
        if yt_search:
            q = yt_search.group(1).strip()
            url = "https://www.youtube.com/results?" + urlencode({"search_query": q})
        elif clean.lower().startswith(("tìm kiếm ", "search ", "tra cứu ")):
            q = re.sub(r"^(?:tìm kiếm|search|tra cứu)\s+", "", clean, flags=re.IGNORECASE).strip()
            url = "https://www.google.com/search?" + urlencode({"q": q})
        elif clean.lower() in self.WEBSITE_MAP:
            url = self.WEBSITE_MAP[clean.lower()]
        elif re.fullmatch(r"[\w-]+(?:\.[\w-]+)+(?::\d+)?(?:[/?#][^\s]*)?", clean):
            url = f"https://{clean}"
        elif re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", clean):
            url = clean
        else:
            url = "https://www.google.com/search?" + urlencode({"q": clean})

        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and not parsed.username and not parsed.password
                     and not any(char.isspace() for char in url) and "\\" not in url)
            parsed.port  # Validate malformed/out-of-range ports before launching.
        except ValueError:
            valid = False
        if not valid:
            return {"success": False, "error_code": "INVALID_URL", "error": "Only valid HTTP(S) URLs without credentials are supported"}

        # P0 runaway-hardening: every prior call unconditionally re-opened the
        # target URL -- a repeated/runaway dispatch (e.g. a passive
        # acoustic-trigger loop, or a garbled STT transcript repeatedly
        # resolving to the same URL) could open it over and over. Report a
        # suppressed repeat truthfully rather than a fabricated success.
        # Keyed by canonical domain so this shares one budget with
        # ChromeMultiMonitorPlugin.open_url() for the same site reached
        # through a different code path.
        if not launch_dedupe_guard.should_allow("web_launch", canonical_url_key(url)):
            return {
                "success": False,
                "url": url,
                "status": "suppressed",
                "error": f"Yêu cầu mở '{url}' bị chặn do lặp lại quá nhanh.",
                "error_code": "LAUNCH_RATE_LIMITED",
            }

        try:
            import webbrowser
            if not webbrowser.open(url):
                return {"success": False, "url": url, "error_code": "BROWSER_OPEN_FAILED", "error": "Trình duyệt không chấp nhận yêu cầu mở trang web."}
            return {
                "success": True,
                "url": url,
                "message": f"Đã gửi yêu cầu mở {url} tới trình duyệt; chưa xác minh trang đã tải.",
                "verification": "browser_launch_acknowledged",
            }
        except Exception as exc:
            return {"success": False, "url": url, "error_code": "BROWSER_OPEN_FAILED", "error": str(exc), "message": f"Không thể mở trang web: {exc}"}
