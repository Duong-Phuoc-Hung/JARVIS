"""
jarvis/platform/hotkeys.py
==========================
Global System-Wide Keyboard Hotkey Manager for Windows.
Provides low-latency, zero-dependency global shortcut interception using
Win32 RegisterHotKey API and dedicated message pump thread.
"""
from __future__ import annotations

import ctypes
import logging
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.platform.hotkeys")

# Win32 Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# Virtual Key Mapping
VK_MAP: dict[str, int] = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "enter": 0x0D, "return": 0x0D,
    "tab": 0x09, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
}


@dataclass
class HotkeyRegistration:
    """Represents an active or registered hotkey binding."""
    id: int
    combination: str
    callback: Callable[[], Any]
    description: str = ""
    modifiers: int = 0
    vk_code: int = 0
    is_active: bool = False


class GlobalHotkeyManager:
    """
    Manages global system-wide keyboard shortcuts on Windows.
    Runs a dedicated Win32 message pump thread to receive WM_HOTKEY events.
    """

    def __init__(self, is_mock: bool = False) -> None:
        self.is_mock = is_mock or (sys.platform != "win32")
        self._hotkeys: dict[int, HotkeyRegistration] = {}
        self._combo_map: dict[str, int] = {}
        self._next_id = 1
        self._lock = threading.RLock()

        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._running = False
        self._stop_event = threading.Event()

    def parse_combination(self, combination: str) -> tuple[int, int]:
        """
        Parses shortcut string e.g. 'ctrl+shift+j' into (modifiers, vk_code).
        """
        parts = [p.strip().lower() for p in combination.split("+") if p.strip()]
        modifiers = 0
        vk_code = 0

        for p in parts:
            if p in ("ctrl", "control"):
                modifiers |= MOD_CONTROL
            elif p in ("alt", "menu"):
                modifiers |= MOD_ALT
            elif p in ("shift",):
                modifiers |= MOD_SHIFT
            elif p in ("win", "windows", "super", "cmd"):
                modifiers |= MOD_WIN
            elif p in VK_MAP:
                vk_code = VK_MAP[p]
            elif len(p) == 1:
                # Alphanumeric character
                char = p.upper()
                vk_code = ord(char)
            else:
                raise ValueError(f"Unknown key in combination: '{p}'")

        if vk_code == 0:
            raise ValueError(f"No valid virtual key specified in combination: '{combination}'")

        # Include MOD_NOREPEAT to prevent auto-repeating triggers when held
        modifiers |= MOD_NOREPEAT
        return modifiers, vk_code

    def register(
        self,
        combination: str,
        callback: Callable[[], Any],
        description: str = "",
    ) -> int:
        """
        Registers a global shortcut combination with a callback.
        
        Args:
            combination: Shortcut string (e.g. 'Ctrl+Shift+J').
            callback: Function to invoke when hotkey is triggered.
            description: Human-readable description.
            
        Returns:
            Unique hotkey ID.
        """
        norm_combo = combination.lower().replace(" ", "")
        mods, vk = self.parse_combination(norm_combo)

        with self._lock:
            if norm_combo in self._combo_map:
                existing_id = self._combo_map[norm_combo]
                self.unregister(existing_id)

            hotkey_id = self._next_id
            self._next_id += 1

            reg = HotkeyRegistration(
                id=hotkey_id,
                combination=combination,
                callback=callback,
                description=description,
                modifiers=mods,
                vk_code=vk,
                is_active=False,
            )
            self._hotkeys[hotkey_id] = reg
            self._combo_map[norm_combo] = hotkey_id

            # If message loop thread is already running, register immediately if on win32
            if self._running and not self.is_mock and sys.platform == "win32":
                self._register_win32_hotkey(reg)

            logger.info("Registered hotkey '%s' (ID=%d): %s", combination, hotkey_id, description)
            return hotkey_id

    def unregister(self, hotkey_id: int) -> bool:
        """Unregisters a hotkey by its ID."""
        with self._lock:
            reg = self._hotkeys.pop(hotkey_id, None)
            if not reg:
                return False

            norm_combo = reg.combination.lower().replace(" ", "")
            self._combo_map.pop(norm_combo, None)

            if reg.is_active and not self.is_mock and sys.platform == "win32":
                try:
                    ctypes.windll.user32.UnregisterHotKey(None, reg.id)
                except Exception as exc:
                    logger.debug("Failed unregistering hotkey %d: %s", hotkey_id, exc)
                reg.is_active = False

            return True

    def unregister_all(self) -> None:
        """Unregisters all active hotkeys."""
        with self._lock:
            for hotkey_id in list(self._hotkeys.keys()):
                self.unregister(hotkey_id)

    def trigger(self, combination: str) -> bool:
        """
        Programmatically trigger hotkey callback (useful for testing or IPC).
        """
        norm_combo = combination.lower().replace(" ", "")
        with self._lock:
            hotkey_id = self._combo_map.get(norm_combo)
            if hotkey_id and hotkey_id in self._hotkeys:
                reg = self._hotkeys[hotkey_id]
                try:
                    reg.callback()
                    return True
                except Exception as exc:
                    logger.error("Error in hotkey callback '%s': %s", combination, exc, exc_info=True)
                    return False
        return False

    def list_hotkeys(self) -> list[dict[str, Any]]:
        """Returns metadata of all registered hotkeys."""
        with self._lock:
            return [
                {
                    "id": reg.id,
                    "combination": reg.combination,
                    "description": reg.description,
                    "is_active": reg.is_active,
                }
                for reg in self._hotkeys.values()
            ]

    def start(self) -> None:
        """Starts the background hotkey listener thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()

            if not self.is_mock and sys.platform == "win32":
                self._thread = threading.Thread(
                    target=self._message_pump_loop,
                    name="jarvis-hotkey-listener",
                    daemon=True,
                )
                self._thread.start()
            logger.info("GlobalHotkeyManager started (mock=%s)", self.is_mock)

    def stop(self) -> None:
        """Stops the listener and cleans up registered hotkeys."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

            if not self.is_mock and sys.platform == "win32" and self._thread_id:
                try:
                    ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
                except Exception as exc:
                    logger.debug("PostThreadMessageW failed: %s", exc)

            self.unregister_all()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        self._thread_id = None
        logger.info("GlobalHotkeyManager stopped.")

    def _register_win32_hotkey(self, reg: HotkeyRegistration) -> bool:
        """Invokes Win32 RegisterHotKey for a registration."""
        try:
            res = ctypes.windll.user32.RegisterHotKey(
                None,
                reg.id,
                reg.modifiers,
                reg.vk_code,
            )
            reg.is_active = bool(res)
            if not res:
                err = ctypes.GetLastError()
                logger.warning("RegisterHotKey failed for '%s' (Win32 Error=%d)", reg.combination, err)
            return reg.is_active
        except Exception as exc:
            logger.error("Exception in RegisterHotKey: %s", exc)
            return False

    def _message_pump_loop(self) -> None:
        """Win32 thread message pump handling WM_HOTKEY."""
        try:
            self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

            # Register all pending hotkeys on this thread
            with self._lock:
                for reg in self._hotkeys.values():
                    self._register_win32_hotkey(reg)

            msg = wintypes.MSG()
            while self._running and not self._stop_event.is_set():
                ret = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:  # WM_QUIT or Error
                    break

                if msg.message == WM_HOTKEY:
                    hotkey_id = msg.wParam
                    reg = None
                    with self._lock:
                        reg = self._hotkeys.get(hotkey_id)

                    if reg and reg.callback:
                        try:
                            # Run callback in background thread to avoid blocking pump
                            threading.Thread(
                                target=reg.callback,
                                name=f"hotkey-cb-{reg.id}",
                                daemon=True,
                            ).start()
                        except Exception as cb_exc:
                            logger.error("Hotkey callback exception: %s", cb_exc, exc_info=True)

                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

        except Exception as exc:
            logger.error("Hotkey message pump crashed: %s", exc, exc_info=True)
        finally:
            with self._lock:
                for reg in self._hotkeys.values():
                    if reg.is_active:
                        try:
                            ctypes.windll.user32.UnregisterHotKey(None, reg.id)
                        except Exception:
                            pass
                        reg.is_active = False
