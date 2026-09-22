"""Launch installed applications and verify their actual Windows UI identity.

Neither window titles nor executable basenames are evidence. Store windows may
be hosted by ApplicationFrameHost; check the child process AUMID as well.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from typing import Any

import psutil

from jarvis.automation.app_catalog import InstalledApp
from jarvis.platform.window_identity import window_app_id
from jarvis.platform.windows import platform_win32


def process_identity(pid: int) -> tuple[str, str]:
    """Read executable and application ID with limited query rights, no elevation."""
    executable = ""
    try:
        executable = psutil.Process(pid).exe()
    except (psutil.Error, OSError):
        pass
    if sys.platform != "win32":
        return executable, ""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetApplicationUserModelId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    kernel.GetApplicationUserModelId.restype = wintypes.LONG
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return executable, ""
    try:
        size = wintypes.UINT(0)
        if kernel.GetApplicationUserModelId(handle, ctypes.byref(size), None) != 122:
            return executable, ""
        if not 0 < size.value <= 1024:
            return executable, ""
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel.GetApplicationUserModelId(handle, ctypes.byref(size), buffer) == 0:
            return executable, buffer.value
        return executable, ""
    finally:
        kernel.CloseHandle(handle)


def window_child_pids(hwnd: int) -> tuple[int, ...]:
    """Return visible child-window owners, including hosted Store content."""
    if sys.platform != "win32":
        return ()
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    user.EnumChildWindows.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    pids: set[int] = set()

    @callback_type
    def visit(child: int, unused: int) -> bool:
        if user.IsWindowVisible(child):
            pid = wintypes.DWORD()
            user.GetWindowThreadProcessId(child, ctypes.byref(pid))
            if pid.value:
                pids.add(pid.value)
        return True

    user.EnumChildWindows(hwnd, visit, 0)
    return tuple(sorted(pids))


class WindowsWindowProbe:
    def __init__(self, platform: Any = None) -> None:
        self.platform = platform if platform is not None else platform_win32

    def find(self, app: InstalledApp) -> dict[str, Any] | None:
        expected_id = getattr(app, "app_id", "") or (app.target if app.kind == "app_id" else "")
        expected_exe = getattr(app, "executable", "") or (app.target if app.kind == "exe" else "")
        identities: dict[int, tuple[str, str]] = {}
        for window in self.platform.list_windows(visible_only=True, min_size=(0, 0)):
            for pid in (window.pid, *window_child_pids(window.hwnd)):
                if pid not in identities:
                    identities[pid] = process_identity(pid)
                executable, app_id = identities[pid]
                # If both processes have a package identity, never substitute
                # the shared executable of another app from the same package.
                if expected_id and "!" in expected_id:
                    matched = expected_id.casefold() == app_id.casefold()
                    verification = "window_app_id"
                else:
                    matched = bool(not getattr(app, "executable_shared", False) and expected_exe and executable and
                                   os.path.normcase(os.path.normpath(expected_exe)) ==
                                   os.path.normcase(os.path.normpath(executable)))
                    verification = "window_executable"
                if matched:
                    return {"pid": pid, "hwnd": window.hwnd, "verification": verification}
            # Minimized Store apps can detach their content child completely.
            # The host's explicit AUMID still identifies the requested window.
            if expected_id and window_app_id(window.hwnd).casefold() == expected_id.casefold():
                return {"pid": window.pid, "hwnd": window.hwnd,
                        "verification": "window_app_id_property"}
        return None

    def focus(self, hwnd: int) -> bool:
        return bool(self.platform.focus_window(hwnd))


class WindowsApplicationLauncher:
    """Single launch, bounded observation; never retries or kills user processes."""

    def __init__(self, probe: WindowsWindowProbe | None = None, timeout: float = 5.0, interval: float = 0.1) -> None:
        self.probe = probe if probe is not None else WindowsWindowProbe()
        self.timeout = max(0.0, min(timeout, 15.0))
        self.interval = max(0.001, interval)

    def _find(self, app: InstalledApp) -> dict[str, Any] | None:
        try:
            return self.probe.find(app)
        except (OSError, psutil.Error):
            return None

    def _success(self, app: InstalledApp, proof: dict[str, Any], existing: bool) -> dict[str, Any]:
        try:
            focused = bool(self.probe.focus(proof["hwnd"]))
        except OSError:
            focused = False
        return {"success": True, "status": "success", **proof, "already_running": existing,
                "focused": focused, "app": app.name, "message": f"Đã xác minh cửa sổ ứng dụng {app.name}."}

    def open(self, app: InstalledApp) -> dict[str, Any]:
        existing = self._find(app)
        if existing:
            return self._success(app, existing, True)
        try:
            if app.kind == "exe":
                if not os.path.isfile(app.target):
                    return {"success": False, "error_code": "APP_NOT_FOUND", "message": "Ứng dụng đã bị di chuyển hoặc gỡ cài đặt."}
                # This is the requested app, not a background discovery helper.
                # Keep console apps visible instead of hiding their only UI.
                startupinfo = None
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 1  # SW_SHOWNORMAL
                subprocess.Popen(
                    [app.target], shell=False,
                    startupinfo=startupinfo, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
            elif app.kind == "app_id":
                if not hasattr(os, "startfile"):
                    return {"success": False, "error_code": "APP_LAUNCH_UNAVAILABLE", "message": "Cần Windows để mở ứng dụng này."}
                os.startfile("shell:AppsFolder\\" + app.target)
            else:
                return {"success": False, "error_code": "INVALID_APP_TARGET", "message": "Loại ứng dụng không được hỗ trợ."}
        except OSError as exc:
            return {"success": False, "error_code": "APP_LAUNCH_FAILED", "message": f"Không mở được ứng dụng ({type(exc).__name__})."}
        deadline = time.monotonic() + self.timeout
        while True:
            proof = self._find(app)
            if proof:
                return self._success(app, proof, False)
            if time.monotonic() >= deadline:
                break
            time.sleep(min(self.interval, max(0.0, deadline - time.monotonic())))
        return {"success": False, "status": "timeout", "error_code": "APP_LAUNCH_UNVERIFIED",
                "verification": "launch_requested", "app": app.name,
                "message": f"Đã yêu cầu mở {app.name} nhưng chưa xác minh được cửa sổ; không tự mở lại."}
