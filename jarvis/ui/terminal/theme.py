"""
jarvis/ui/terminal/theme.py
===========================
J.A.R.V.I.S. Terminal Control Center — color palette and truthful status model.

Plain ANSI escape sequences only (no Rich/colorama dependency), matching the
existing hand-rolled ANSI convention already used by jarvis/core/logger.py's
LogColors. Colors degrade to no-ops when the target stream is not a TTY, when
NO_COLOR is set, or when the caller explicitly disables color (redirected
output, CI, headless environments).
"""
from __future__ import annotations

import os
import sys
from enum import Enum


class Ansi:
    """Raw ANSI escape codes. Never printed directly -- always go through
    TerminalTheme.color()/style() so color-disabled output stays clean."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    CYAN = "\033[36m"
    BRIGHT_CYAN = "\033[96m"
    GREEN = "\033[32m"
    BRIGHT_GREEN = "\033[92m"
    YELLOW = "\033[33m"
    BRIGHT_YELLOW = "\033[93m"
    RED = "\033[31m"
    BRIGHT_RED = "\033[91m"
    MAGENTA = "\033[35m"
    BRIGHT_MAGENTA = "\033[95m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"


class StatusLevel(str, Enum):
    """Truthful status vocabulary for the terminal UI.

    A component is never READY/AVAILABLE merely because a class imported
    successfully -- callers must derive this from an actual real check.
    """
    READY = "READY"
    AVAILABLE = "AVAILABLE"
    PASS = "PASS"
    LIMITED = "LIMITED"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"
    OFFLINE = "OFFLINE"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


_STATUS_COLOR = {
    StatusLevel.READY: "BRIGHT_GREEN",
    StatusLevel.AVAILABLE: "GREEN",
    StatusLevel.PASS: "GREEN",
    StatusLevel.LIMITED: "YELLOW",
    StatusLevel.PARTIAL: "YELLOW",
    StatusLevel.SKIPPED: "YELLOW",
    StatusLevel.OFFLINE: "GRAY",
    StatusLevel.BLOCKED: "BRIGHT_RED",
    StatusLevel.ERROR: "BRIGHT_RED",
    StatusLevel.FAILED: "BRIGHT_RED",
    StatusLevel.UNKNOWN: "GRAY",
}


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("JARVIS_TERMINAL_FORCE_COLOR") == "1":
        return True
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


class TerminalTheme:
    """Central color/style application point. All rendering goes through here
    so the no-color fallback is a single switch, not scattered conditionals."""

    def __init__(self, color_enabled: bool | None = None) -> None:
        self.color_enabled = _color_enabled() if color_enabled is None else color_enabled

    def style(self, text: str, *codes: str) -> str:
        if not self.color_enabled or not codes:
            return text
        prefix = "".join(getattr(Ansi, c) for c in codes)
        return f"{prefix}{text}{Ansi.RESET}"

    # Semantic helpers -------------------------------------------------
    def logo(self, text: str) -> str:
        return self.style(text, "BOLD", "BRIGHT_CYAN")

    def header(self, text: str) -> str:
        return self.style(text, "CYAN")

    def key(self, text: str) -> str:
        return self.style(text, "BOLD", "GREEN")

    def key_j(self, text: str) -> str:
        return self.style(text, "BOLD", "BRIGHT_YELLOW")

    def key_a(self, text: str) -> str:
        return self.style(text, "BOLD", "MAGENTA")

    def key_r(self, text: str) -> str:
        return self.style(text, "BOLD", "GREEN")

    def key_s(self, text: str) -> str:
        return self.style(text, "BOLD", "CYAN")

    def key_b(self, text: str) -> str:
        return self.style(text, "BOLD", "YELLOW")

    def title(self, text: str) -> str:
        return self.style(text, "CYAN")

    def desc(self, text: str) -> str:
        return self.style(text, "DIM", "GRAY")

    def dim(self, text: str) -> str:
        return self.style(text, "DIM", "GRAY")

    def warn(self, text: str) -> str:
        return self.style(text, "YELLOW")

    def error(self, text: str) -> str:
        return self.style(text, "BOLD", "BRIGHT_RED")

    def success(self, text: str) -> str:
        return self.style(text, "GREEN")

    def breadcrumb_prefix(self, text: str) -> str:
        return self.style(text, "DIM", "GRAY")

    def breadcrumb_path(self, text: str) -> str:
        return self.style(text, "CYAN")

    def breadcrumb_current(self, text: str) -> str:
        return self.style(text, "BOLD", "BRIGHT_CYAN")

    def status(self, level: StatusLevel | str) -> str:
        try:
            lvl = level if isinstance(level, StatusLevel) else StatusLevel(str(level).upper())
        except ValueError:
            lvl = StatusLevel.UNKNOWN
        code = _STATUS_COLOR.get(lvl, "GRAY")
        return self.style(lvl.value, "BOLD", code)

    def status_text(self, level: StatusLevel | str, text: str) -> str:
        try:
            lvl = level if isinstance(level, StatusLevel) else StatusLevel(str(level).upper())
        except ValueError:
            lvl = StatusLevel.UNKNOWN
        code = _STATUS_COLOR.get(lvl, "GRAY")
        return self.style(text, code)
