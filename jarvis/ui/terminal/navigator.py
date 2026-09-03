"""
jarvis/ui/terminal/navigator.py
================================
Central navigation state machine for the Terminal Control Center.

Deliberately NOT implemented as recursive menu functions calling each other
(main_menu() -> hardware_menu() -> storage_menu() -> hardware_menu() ...).
A single stack-based navigator makes Back/Exit deterministic and unit-testable
without growing the Python call stack per navigation level.
"""
from __future__ import annotations

from collections.abc import Callable

from jarvis.ui.terminal.models import MenuScreen


class TerminalNavigator:
    """A simple push/pop screen stack.

    `resolve` maps a screen id to a freshly-built MenuScreen (screens are
    rebuilt on each visit so displayed data is never stale after a Back/
    Refresh cycle).
    """

    def __init__(self, resolve: Callable[[str], MenuScreen], root_id: str) -> None:
        self._resolve = resolve
        self._stack: list[str] = [root_id]
        self._exited = False

    @property
    def stack_ids(self) -> list[str]:
        return list(self._stack)

    @property
    def current_id(self) -> str:
        return self._stack[-1]

    @property
    def current(self) -> MenuScreen:
        return self._resolve(self.current_id)

    @property
    def depth(self) -> int:
        return len(self._stack)

    @property
    def at_root(self) -> bool:
        return len(self._stack) <= 1

    @property
    def exited(self) -> bool:
        return self._exited

    def push(self, screen_id: str) -> None:
        self._stack.append(screen_id)

    def pop(self) -> bool:
        """Pop exactly one level. Returns False (no-op) if already at root."""
        if self.at_root:
            return False
        self._stack.pop()
        return True

    def replace(self, screen_id: str) -> None:
        """Replace the current top of stack (used by Refresh/Run Again --
        stays at the same navigation level, never pushes a new one)."""
        self._stack[-1] = screen_id

    def reset(self, root_id: str | None = None) -> None:
        self._stack = [root_id if root_id is not None else self._stack[0]]

    def exit(self) -> None:
        self._exited = True

    def breadcrumb(self) -> list[str]:
        return self.current.breadcrumb
