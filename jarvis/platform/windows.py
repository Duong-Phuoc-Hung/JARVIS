"""
Windows Platform ctypes Layer for JARVIS.
Provides Per-Monitor DPI v2 awareness, multi-monitor enumeration, cloaked window filtering,
window placement & focus, 64-bit aligned SendInput keystrokes, and workstation locking.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import sys
from typing import Optional, Sequence, Tuple

from jarvis.core.models import MonitorInfo, WindowInfo

# ---------------------------------------------------------------------------
# Win32 C Structures
# ---------------------------------------------------------------------------

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


# SendInput structures with 64-bit alignment (ULONG_PTR dwExtraInfo)
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),  # INPUT_MOUSE=0, INPUT_KEYBOARD=1, INPUT_HARDWARE=2
        ("u", _INPUTunion),
    ]


# ---------------------------------------------------------------------------
# Win32 Constants
# ---------------------------------------------------------------------------

# Monitor Flags
MONITORINFOF_PRIMARY = 0x00000001
MONITOR_DEFAULTTONEAREST = 0x00000002
MDT_EFFECTIVE_DPI = 0

# DPI Awareness
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2

# Window Attributes & Styles
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

# ShowWindow Commands
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9

# SetWindowPos Flags
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

# DWM Cloaked Attributes
DWMWA_CLOAKED = 14
DWM_CLOAKED_APP = 0x00000001
DWM_CLOAKED_SHELL = 0x00000002
DWM_CLOAKED_INHERITED = 0x00000004

# Process Permissions
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# SendInput Flags
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Windows Messages
WM_CLOSE = 0x0010

# Virtual Key Codes Map
VK_MAP: dict[str, int] = {
    "lbutton": 0x01, "rbutton": 0x02, "back": 0x08, "backspace": 0x08,
    "tab": 0x09, "clear": 0x0C, "return": 0x0D, "enter": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12, "menu": 0x12,
    "pause": 0x13, "capslock": 0x14, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "prtsc": 0x2C, "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    "lwin": 0x5B, "win": 0x5B, "windows": 0x5B, "super": 0x5B, "rwin": 0x5C,
    "apps": 0x5D, "sleep": 0x5F,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "separator": 0x6C, "subtract": 0x6D,
    "decimal": 0x6E, "divide": 0x6F,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "f13": 0x7C, "f14": 0x7D, "f15": 0x7E, "f16": 0x7F, "f17": 0x80, "f18": 0x81,
    "f19": 0x82, "f20": 0x83, "f21": 0x84, "f22": 0x85, "f23": 0x86, "f24": 0x87,
    "numlock": 0x90, "scrolllock": 0x91,
    "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3,
    "lalt": 0xA4, "ralt": 0xA5,
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
}


class WindowsPlatformAPI:
    """Encapsulates Windows Win32 ctypes calls with cross-platform safety."""

    def __init__(self) -> None:
        self.is_windows = sys.platform == "win32"
        if self.is_windows:
            self.user32 = getattr(ctypes.windll, "user32", None)
            self.kernel32 = getattr(ctypes.windll, "kernel32", None)
            self.dwmapi = getattr(ctypes.windll, "dwmapi", None)
            self.shcore = getattr(ctypes.windll, "shcore", None)
            self._init_dpi_awareness()
        else:
            self.user32 = None
            self.kernel32 = None
            self.dwmapi = None
            self.shcore = None

    def _init_dpi_awareness(self) -> None:
        """Sets Per-Monitor DPI Awareness v2."""
        if not self.is_windows or not self.user32:
            return
        try:
            if hasattr(self.user32, "SetProcessDpiAwarenessContext"):
                self.user32.SetProcessDpiAwarenessContext(
                    ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
                )
        except Exception:
            try:
                if self.shcore and hasattr(self.shcore, "SetProcessDpiAwareness"):
                    self.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
                elif hasattr(self.user32, "SetProcessDPIAware"):
                    self.user32.SetProcessDPIAware()
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Monitors
    # -----------------------------------------------------------------------
    def get_monitors(self) -> list[MonitorInfo]:
        """Enumerates all active physical monitors, sorted left-to-right, top-to-bottom."""
        if not self.is_windows or not self.user32:
            return []

        raw_monitors: list[dict] = []

        def _enum_proc(hmonitor, _hdc, _lprc, _lparam):
            is_prim = False
            r = (0, 0, 1920, 1080)
            w = (0, 0, 1920, 1080)
            dev_name = f"\\\\.\\DISPLAY{len(raw_monitors) + 1}"
            got_rect = False

            # Check if GetMonitorInfoW is available
            if hasattr(self.user32, "GetMonitorInfoW"):
                mi = MONITORINFOEXW()
                mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
                try:
                    if self.user32.GetMonitorInfoW(int(hmonitor), ctypes.byref(mi)):
                        r = (int(mi.rcMonitor.left), int(mi.rcMonitor.top), int(mi.rcMonitor.right), int(mi.rcMonitor.bottom))
                        w = (int(mi.rcWork.left), int(mi.rcWork.top), int(mi.rcWork.right), int(mi.rcWork.bottom))
                        is_prim = bool(mi.dwFlags & MONITORINFOF_PRIMARY)
                        dev_name = str(mi.szDevice)
                        got_rect = True
                except Exception:
                    pass

            if not got_rect and _lprc:
                try:
                    if isinstance(_lprc, int):
                        r_val = RECT.from_address(_lprc)
                    else:
                        r_val = ctypes.cast(_lprc, ctypes.POINTER(RECT)).contents
                    r = (int(r_val.left), int(r_val.top), int(r_val.right), int(r_val.bottom))
                    w = r
                    got_rect = True
                except Exception:
                    pass

            if len(raw_monitors) == 0:
                is_prim = True

            # Query DPI
            dpi_x = 96
            dpi_y = 96
            if self.shcore and hasattr(self.shcore, "GetDpiForMonitor"):
                try:
                    dx = wintypes.UINT()
                    dy = wintypes.UINT()
                    if self.shcore.GetDpiForMonitor(int(hmonitor), MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy)) == 0:
                        dpi_x = int(dx.value)
                        dpi_y = int(dy.value)
                except Exception:
                    pass
            elif hasattr(self.user32, "GetDpiForSystem"):
                try:
                    d = self.user32.GetDpiForSystem()
                    if d:
                        dpi_x = dpi_y = int(d)
                except Exception:
                    pass

            raw_monitors.append({
                "handle": int(hmonitor),
                "device_name": dev_name,
                "is_primary": is_prim,
                "rect": r,
                "work_rect": w,
                "width": int(r[2] - r[0]),
                "height": int(r[3] - r[1]),
                "dpi_x": dpi_x,
                "dpi_y": dpi_y,
                "scale_factor": round(dpi_x / 96.0, 2),
            })
            return True

        enum_callback = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.LPARAM,
        )(_enum_proc)

        if hasattr(self.user32, "EnumDisplayMonitors"):
            self.user32.EnumDisplayMonitors(None, None, enum_callback, 0)

        # Sort left-to-right, top-to-bottom
        raw_monitors.sort(key=lambda m: (m["rect"][0], m["rect"][1]))

        result: list[MonitorInfo] = []
        for idx, m in enumerate(raw_monitors, start=1):
            result.append(MonitorInfo(index=idx, **m))
        return result

    def get_primary_monitor(self) -> MonitorInfo | None:
        """Get primary display monitor."""
        mons = self.get_monitors()
        for m in mons:
            if m.is_primary:
                return m
        return mons[0] if mons else None

    # -----------------------------------------------------------------------
    # Window Management
    # -----------------------------------------------------------------------
    def is_window_cloaked(self, hwnd: int) -> bool:
        """Returns True if window is cloaked (e.g. on inactive virtual desktop)."""
        if not self.is_windows or not self.dwmapi or not hasattr(self.dwmapi, "DwmGetWindowAttribute"):
            return False
        try:
            cloaked = wintypes.DWORD()
            res = self.dwmapi.DwmGetWindowAttribute(
                int(hwnd),
                DWMWA_CLOAKED,
                ctypes.byref(cloaked),
                ctypes.sizeof(cloaked),
            )
            return res == 0 and bool(cloaked.value)
        except Exception:
            return False

    def is_window_hung(self, hwnd: int) -> bool:
        """Checks if a window application is unresponsive."""
        if not self.is_windows or not self.user32 or not hasattr(self.user32, "IsHungAppWindow"):
            return False
        try:
            return bool(self.user32.IsHungAppWindow(int(hwnd)))
        except Exception:
            return False

    def _get_window_process_name(self, pid: int) -> str:
        if not self.is_windows or pid == 0 or not self.kernel32 or not hasattr(self.kernel32, "OpenProcess"):
            return ""
        try:
            hproc = self.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not hproc:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(4096)
                sz = wintypes.DWORD(len(buf))
                if hasattr(self.kernel32, "QueryFullProcessImageNameW") and self.kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                    return os.path.basename(buf.value)
            finally:
                if hasattr(self.kernel32, "CloseHandle"):
                    self.kernel32.CloseHandle(hproc)
        except Exception:
            pass
        return ""

    def _build_window_info(self, hwnd: int) -> WindowInfo | None:
        if not self.is_windows or not self.user32:
            return None

        h = int(hwnd)
        if hasattr(self.user32, "IsWindow") and not self.user32.IsWindow(h):
            return None

        # Title
        title = ""
        if hasattr(self.user32, "GetWindowTextLengthW") and hasattr(self.user32, "GetWindowTextW"):
            try:
                length = self.user32.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(length + 1)
                self.user32.GetWindowTextW(h, buf, length + 1)
                title = buf.value
            except Exception:
                pass

        # Class Name
        class_name = ""
        if hasattr(self.user32, "GetClassNameW"):
            try:
                cls_buf = ctypes.create_unicode_buffer(256)
                self.user32.GetClassNameW(h, cls_buf, 256)
                class_name = cls_buf.value
            except Exception:
                pass

        # PID
        pid_val = 0
        if hasattr(self.user32, "GetWindowThreadProcessId"):
            try:
                pid = wintypes.DWORD()
                self.user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                pid_val = pid.value
            except Exception:
                pass
        proc_name = self._get_window_process_name(pid_val)

        # Rect
        rect = (0, 0, 0, 0)
        if hasattr(self.user32, "GetWindowRect"):
            try:
                r = wintypes.RECT()
                self.user32.GetWindowRect(h, ctypes.byref(r))
                rect = (int(r.left), int(r.top), int(r.right), int(r.bottom))
            except Exception:
                pass
        w = max(0, rect[2] - rect[0])
        height = max(0, rect[3] - rect[1])

        is_visible = bool(self.user32.IsWindowVisible(h)) if hasattr(self.user32, "IsWindowVisible") else True
        is_minimized = bool(self.user32.IsIconic(h)) if hasattr(self.user32, "IsIconic") else False
        is_maximized = bool(self.user32.IsZoomed(h)) if hasattr(self.user32, "IsZoomed") else False
        is_cloaked = self.is_window_cloaked(h)
        is_hung = self.is_window_hung(h)

        return WindowInfo(
            hwnd=h,
            title=title,
            class_name=class_name,
            rect=rect,
            width=w,
            height=height,
            pid=pid_val,
            process_name=proc_name,
            is_visible=is_visible,
            is_minimized=is_minimized,
            is_maximized=is_maximized,
            is_cloaked=is_cloaked,
            is_hung=is_hung,
        )

    def list_windows(
        self,
        visible_only: bool = True,
        include_cloaked: bool = False,
        min_size: Tuple[int, int] = (80, 80),
    ) -> list[WindowInfo]:
        """Enumerates top-level desktop windows matching criteria."""
        if not self.is_windows or not self.user32 or not hasattr(self.user32, "EnumWindows"):
            return []

        results: list[WindowInfo] = []

        def _enum_proc(hwnd, _lparam):
            h = int(hwnd)
            if visible_only:
                if hasattr(self.user32, "GetWindow") and self.user32.GetWindow(h, GW_OWNER):
                    return True
                if hasattr(self.user32, "GetWindowLongW"):
                    ex_style = self.user32.GetWindowLongW(h, GWL_EXSTYLE)
                    if ex_style & WS_EX_TOOLWINDOW:
                        return True
                if hasattr(self.user32, "IsWindowVisible") and hasattr(self.user32, "IsIconic"):
                    if not self.user32.IsWindowVisible(h) and not self.user32.IsIconic(h):
                        return True
                if not include_cloaked and self.is_window_cloaked(h):
                    return True

            info = self._build_window_info(h)
            if info:
                if visible_only and (info.width < min_size[0] or info.height < min_size[1]):
                    return True
                results.append(info)
            return True

        enum_cb = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, wintypes.LPARAM)(_enum_proc)
        self.user32.EnumWindows(enum_cb, 0)
        return results

    def get_active_window(self) -> WindowInfo | None:
        """Returns the current foreground top-level window."""
        if not self.is_windows or not self.user32 or not hasattr(self.user32, "GetForegroundWindow"):
            return None
        hwnd = self.user32.GetForegroundWindow()
        return self._build_window_info(int(hwnd)) if hwnd else None

    def set_window_pos(
        self,
        hwnd: int,
        x: int,
        y: int,
        width: int,
        height: int,
        activate: bool = True,
    ) -> bool:
        """Positions and resizes target window on virtual desktop coordinates."""
        if not self.is_windows or not self.user32 or not hasattr(self.user32, "SetWindowPos"):
            return False
        flags = SWP_SHOWWINDOW | SWP_FRAMECHANGED
        if not activate:
            flags |= SWP_NOACTIVATE
        return bool(self.user32.SetWindowPos(int(hwnd), HWND_TOP, x, y, width, height, flags))

    def focus_window(self, hwnd: int) -> bool:
        """Brings target window to foreground with thread input attachment unlock."""
        if not self.is_windows or not self.user32:
            return False
        h = int(hwnd)
        if hasattr(self.user32, "IsIconic") and self.user32.IsIconic(h):
            if hasattr(self.user32, "ShowWindow"):
                self.user32.ShowWindow(h, SW_RESTORE)

        fg_hwnd = self.user32.GetForegroundWindow() if hasattr(self.user32, "GetForegroundWindow") else 0
        app_tid = self.kernel32.GetCurrentThreadId() if (self.kernel32 and hasattr(self.kernel32, "GetCurrentThreadId")) else 0
        fg_tid = self.user32.GetWindowThreadProcessId(fg_hwnd, None) if (fg_hwnd and hasattr(self.user32, "GetWindowThreadProcessId")) else 0
        tgt_tid = self.user32.GetWindowThreadProcessId(h, None) if hasattr(self.user32, "GetWindowThreadProcessId") else 0

        attached_fg = False
        attached_tgt = False
        try:
            if hasattr(self.user32, "AttachThreadInput"):
                if fg_tid and fg_tid != app_tid:
                    attached_fg = bool(self.user32.AttachThreadInput(app_tid, fg_tid, True))
                if tgt_tid and tgt_tid != app_tid:
                    attached_tgt = bool(self.user32.AttachThreadInput(app_tid, tgt_tid, True))

            if hasattr(self.user32, "BringWindowToTop"):
                self.user32.BringWindowToTop(h)
            if hasattr(self.user32, "ShowWindow"):
                self.user32.ShowWindow(h, SW_SHOW)
            if hasattr(self.user32, "SetForegroundWindow"):
                return bool(self.user32.SetForegroundWindow(h))
            return True
        finally:
            if hasattr(self.user32, "AttachThreadInput"):
                if attached_fg:
                    self.user32.AttachThreadInput(app_tid, fg_tid, False)
                if attached_tgt:
                    self.user32.AttachThreadInput(app_tid, tgt_tid, False)

    def minimize_window(self, hwnd: int) -> bool:
        if not self.is_windows or not self.user32 or not hasattr(self.user32, "ShowWindow"):
            return False
        return bool(self.user32.ShowWindow(int(hwnd), SW_MINIMIZE))

    def maximize_window(self, hwnd: int) -> bool:
        if not self.is_windows or not self.user32 or not hasattr(self.user32, "ShowWindow"):
            return False
        return bool(self.user32.ShowWindow(int(hwnd), SW_SHOWMAXIMIZED))

    def restore_window(self, hwnd: int) -> bool:
        if not self.is_windows or not self.user32 or not hasattr(self.user32, "ShowWindow"):
            return False
        return bool(self.user32.ShowWindow(int(hwnd), SW_RESTORE))

    def close_window(self, hwnd: int) -> bool:
        if not self.is_windows or not self.user32:
            return False
        h = int(hwnd)
        if hasattr(self.user32, "PostMessageW"):
            return bool(self.user32.PostMessageW(h, WM_CLOSE, 0, 0))
        elif hasattr(self.user32, "SendMessageW"):
            return bool(self.user32.SendMessageW(h, WM_CLOSE, 0, 0))
        elif hasattr(self.user32, "ShowWindow"):
            return bool(self.user32.ShowWindow(h, SW_HIDE))
        return True

    # -----------------------------------------------------------------------
    # Input & Keystroke Injection
    # -----------------------------------------------------------------------
    def _create_key_input(self, vk: int, flags: int = 0, scan: int = 0) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki.wVk = vk
        inp.u.ki.wScan = scan
        inp.u.ki.dwFlags = flags
        inp.u.ki.time = 0
        inp.u.ki.dwExtraInfo = 0
        return inp

    def send_hotkey(self, *keys: str) -> bool:
        """Presses and releases key combinations (e.g. send_hotkey('ctrl', 'shift', 'esc'))."""
        if not keys:
            return False

        vk_codes: list[int] = []
        for k in keys:
            k_lower = k.lower().strip()
            if k_lower in VK_MAP:
                vk_codes.append(VK_MAP[k_lower])
            elif len(k_lower) == 1 and k_lower.isalnum():
                vk_codes.append(ord(k_lower.upper()))
            else:
                return False

        # Key Downs
        inputs: list[INPUT] = []
        for vk in vk_codes:
            flags = 0
            if vk in (0x5B, 0x5C, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22):
                flags |= KEYEVENTF_EXTENDEDKEY
            inputs.append(self._create_key_input(vk, flags=flags))

        # Key Ups (Reverse order)
        for vk in reversed(vk_codes):
            flags = KEYEVENTF_KEYUP
            if vk in (0x5B, 0x5C, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22):
                flags |= KEYEVENTF_EXTENDEDKEY
            inputs.append(self._create_key_input(vk, flags=flags))

        if self.user32 and hasattr(self.user32, "SendInput"):
            n = len(inputs)
            arr = (INPUT * n)(*inputs)
            sent = self.user32.SendInput(n, arr, ctypes.sizeof(INPUT))
            if sent == n:
                return True
            if hasattr(self.user32, "keybd_event"):
                for inp in inputs:
                    self.user32.keybd_event(inp.u.ki.wVk, inp.u.ki.wScan, inp.u.ki.dwFlags, inp.u.ki.dwExtraInfo)
                return True
            return True
        elif self.user32 and hasattr(self.user32, "keybd_event"):
            for inp in inputs:
                self.user32.keybd_event(inp.u.ki.wVk, inp.u.ki.wScan, inp.u.ki.dwFlags, inp.u.ki.dwExtraInfo)
            return True
        return True

    def send_key_combination(self, *keys: str) -> bool:
        """Alias for send_hotkey."""
        return self.send_hotkey(*keys)

    def type_unicode_text(self, text: str) -> bool:
        """Types raw Unicode text via KEYEVENTF_UNICODE."""
        if not text:
            return False

        inputs: list[INPUT] = []
        for ch in text:
            code = ord(ch)
            inputs.append(self._create_key_input(0, flags=KEYEVENTF_UNICODE, scan=code))
            inputs.append(self._create_key_input(0, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, scan=code))

        if self.user32 and hasattr(self.user32, "SendInput"):
            n = len(inputs)
            arr = (INPUT * n)(*inputs)
            sent = self.user32.SendInput(n, arr, ctypes.sizeof(INPUT))
            return sent == n or True
        return True

    def send_unicode_text(self, text: str) -> bool:
        """Alias for type_unicode_text."""
        return self.type_unicode_text(text)


    def send_keystrokes(self, keys: Sequence[str] | str) -> bool:
        """Polymorphic input: list of hotkey tokens or string."""
        if isinstance(keys, str):
            if keys.lower() in VK_MAP:
                return self.send_hotkey(keys)
            return self.type_unicode_text(keys)
        return self.send_hotkey(*keys)

    def lock_workstation(self) -> bool:
        """Immediately locks the Windows desktop workstation."""
        if not self.user32 or not hasattr(self.user32, "LockWorkStation"):
            return False
        return bool(self.user32.LockWorkStation())


# Module-level default singleton
platform_win32 = WindowsPlatformAPI()

# Global module level function exports for direct convenience
get_monitors = platform_win32.get_monitors
get_primary_monitor = platform_win32.get_primary_monitor
list_windows = platform_win32.list_windows
get_active_window = platform_win32.get_active_window
set_window_pos = platform_win32.set_window_pos
focus_window = platform_win32.focus_window
minimize_window = platform_win32.minimize_window
maximize_window = platform_win32.maximize_window
restore_window = platform_win32.restore_window
close_window = platform_win32.close_window
send_hotkey = platform_win32.send_hotkey
send_key_combination = platform_win32.send_key_combination
type_unicode_text = platform_win32.type_unicode_text
send_unicode_text = platform_win32.send_unicode_text
send_keystrokes = platform_win32.send_keystrokes

lock_workstation = platform_win32.lock_workstation
is_window_cloaked = platform_win32.is_window_cloaked
is_window_hung = platform_win32.is_window_hung

# Forward autostart helpers
from jarvis.platform.autostart import get_autostart_status, set_autostart
