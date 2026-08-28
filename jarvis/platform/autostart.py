"""
Windows Registry Autostart Manager for JARVIS.
Configures Windows Startup execution via HKCU Run registry key.
"""
from __future__ import annotations

import logging
import os
import sys
from enum import Enum

log = logging.getLogger(__name__)

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_APP_NAME = "JARVIS_Assistant"


class AutoStartMode(str, Enum):
    REGISTRY = "registry"
    TASK_SCHEDULER = "task_scheduler"


class AutostartStatus:
    """Represents autostart state; behaves both as a boolean and a tuple (enabled, command)."""

    def __init__(self, enabled: bool, command: str | None = None) -> None:
        self.enabled = enabled
        self.command = command

    def __bool__(self) -> bool:
        return self.enabled

    def __iter__(self):
        yield self.enabled
        yield self.command

    def __getitem__(self, index: int):
        return (self.enabled, self.command)[index]

    def __repr__(self) -> str:
        return f"AutostartStatus(enabled={self.enabled}, command={self.command!r})"


def set_autostart(app_name: str = DEFAULT_APP_NAME, exe_path: str | None = None, enabled: bool = True) -> bool:
    """Configures Windows Startup execution via HKCU Run registry key."""
    if sys.platform != "win32":
        log.warning("set_autostart is only supported on Windows.")
        return False

    try:
        import winreg
    except ImportError:
        log.error("winreg module unavailable.")
        return False

    try:
        if enabled:
            if not exe_path:
                py_exe = sys.executable
                if py_exe.lower().endswith("python.exe"):
                    pyw = os.path.join(os.path.dirname(py_exe), "pythonw.exe")
                    if os.path.isfile(pyw):
                        py_exe = pyw
                exe_path = f'"{py_exe}" -m jarvis run'

            key_or_ctx = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                key = key_or_ctx.__enter__() if hasattr(key_or_ctx, "__enter__") else key_or_ctx
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
                log.info("Installed Windows autostart entry for '%s': %s", app_name, exe_path)
                return True
            finally:
                if hasattr(key_or_ctx, "__exit__"):
                    key_or_ctx.__exit__(None, None, None)
                elif hasattr(winreg, "CloseKey"):
                    try:
                        winreg.CloseKey(key_or_ctx)
                    except Exception:
                        pass
        else:
            key_or_ctx = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            )
            try:
                key = key_or_ctx.__enter__() if hasattr(key_or_ctx, "__enter__") else key_or_ctx
                try:
                    winreg.DeleteValue(key, app_name)
                    log.info("Uninstalled Windows autostart entry for '%s'.", app_name)
                except FileNotFoundError:
                    log.debug("Autostart entry for '%s' was already absent.", app_name)
                return True
            finally:
                if hasattr(key_or_ctx, "__exit__"):
                    key_or_ctx.__exit__(None, None, None)
                elif hasattr(winreg, "CloseKey"):
                    try:
                        winreg.CloseKey(key_or_ctx)
                    except Exception:
                        pass
    except Exception as e:
        log.error("Failed to update Windows autostart registry: %s", e)
        return False


def get_autostart_status(app_name: str = DEFAULT_APP_NAME) -> AutostartStatus:
    """Queries whether autostart entry exists and returns AutostartStatus(enabled, command)."""
    if sys.platform != "win32":
        return AutostartStatus(False, None)

    try:
        import winreg
    except ImportError:
        return AutostartStatus(False, None)

    try:
        key_or_ctx = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            winreg.KEY_READ,
        )
        try:
            key = key_or_ctx.__enter__() if hasattr(key_or_ctx, "__enter__") else key_or_ctx
            val, _ = winreg.QueryValueEx(key, app_name)
            return AutostartStatus(True, str(val))
        finally:
            if hasattr(key_or_ctx, "__exit__"):
                key_or_ctx.__exit__(None, None, None)
            elif hasattr(winreg, "CloseKey"):
                try:
                    winreg.CloseKey(key_or_ctx)
                except Exception:
                    pass
    except FileNotFoundError:
        return AutostartStatus(False, None)
    except Exception as e:
        log.error("Failed to query autostart registry status: %s", e)
        return AutostartStatus(False, None)


class AutoStartManager:
    """High-level manager for Windows autostart operations."""

    def __init__(self, app_name: str = "JARVIS", mode: AutoStartMode = AutoStartMode.REGISTRY) -> None:
        self.app_name = app_name
        self.mode = mode

    def enable(self, command_args: list[str] | None = None) -> bool:
        py_exe = sys.executable
        args_str = " " + " ".join(command_args) if command_args else " run"
        exe_path = f'"{py_exe}" -m jarvis{args_str}'
        return set_autostart(app_name=self.app_name, exe_path=exe_path, enabled=True)

    def disable(self) -> bool:
        return set_autostart(app_name=self.app_name, enabled=False)

    def is_enabled(self) -> bool:
        status = get_autostart_status(app_name=self.app_name)
        return bool(status)

    def get_status(self) -> AutostartStatus:
        return get_autostart_status(app_name=self.app_name)
