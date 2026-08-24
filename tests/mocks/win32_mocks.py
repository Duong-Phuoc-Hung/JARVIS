"""
Mock Win32 structures and API providers for cross-platform and isolated unit testing.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class MockWinreg:
    """In-memory dictionary mock for winreg module."""

    HKEY_CURRENT_USER = 1
    KEY_SET_VALUE = 0x0002
    KEY_QUERY_VALUE = 0x0001
    KEY_READ = 0x20019
    REG_SZ = 1

    def __init__(self) -> None:
        self.store: Dict[str, Tuple[str, int]] = {}

    def OpenKey(self, hkey: int, subkey: str, reserved: int = 0, access: int = 0):
        outer = self

        class KeyContext:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return KeyContext()

    def SetValueEx(self, key: Any, value_name: str, reserved: int, typ: int, value: str) -> None:
        self.store[value_name] = (value, typ)

    def QueryValueEx(self, key: Any, value_name: str) -> Tuple[str, int]:
        if value_name in self.store:
            return self.store[value_name]
        raise FileNotFoundError(f"Key {value_name} not found")

    def DeleteValue(self, key: Any, value_name: str) -> None:
        if value_name in self.store:
            del self.store[value_name]
        else:
            raise FileNotFoundError(f"Key {value_name} not found")
