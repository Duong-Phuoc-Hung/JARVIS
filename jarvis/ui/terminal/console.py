"""
jarvis/ui/terminal/console.py
==============================
Low-level rendering + one-key input primitives for the Terminal Control
Center. Kept deliberately dependency-free (no Rich/colorama/curses) --
plain ANSI + msvcrt, matching the hand-rolled-ANSI convention already used
by jarvis/core/logger.py's LogColors.

Input design:
  - Windows interactive TTY: one-key selection via msvcrt.getwch() (no
    Enter required).
  - Any other case (non-Windows, no msvcrt, redirected/non-tty stdin,
    EOF): line-based `input()` fallback, first non-blank token used.
  - Tests inject a `key_source` callable instead of touching real IO --
    this is the seam tests use to drive navigation deterministically.

Ctrl+C and EOF are handled by the caller (TerminalApp) using the
KeyboardInterrupt / EOFError this module raises through cleanly -- no
traceback is printed for either.
"""
from __future__ import annotations

import shutil
import sys
from collections.abc import Callable, Iterable

from jarvis.ui.terminal.theme import TerminalTheme

try:
    import msvcrt
    _MSVCRT_AVAILABLE = True
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None  # type: ignore[assignment]
    _MSVCRT_AVAILABLE = False

DEFAULT_WIDTH = 78
MIN_NARROW_WIDTH = 60


def terminal_width() -> int:
    try:
        size = shutil.get_terminal_size(fallback=(DEFAULT_WIDTH, 24))
        return max(size.columns, MIN_NARROW_WIDTH)
    except Exception:
        return DEFAULT_WIDTH


def supports_unicode() -> bool:
    """True only if sys.stdout's real encoding can round-trip the box-
    drawing/block characters used by the wide logo and separators. Legacy
    Windows consoles (cp1252/cp437) fall back to plain ASCII."""
    encoding = getattr(sys.stdout, "encoding", None) or ""
    if not encoding:
        return False
    try:
        "██╗╚═─".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _stdin_is_interactive() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


class TerminalConsole:
    """Thin IO wrapper: all printing and key-reading go through here so
    tests can substitute `key_source` and capture `out_lines` without
    touching real stdio or msvcrt."""

    def __init__(
        self,
        theme: TerminalTheme | None = None,
        key_source: Callable[[], str] | None = None,
        line_source: Callable[[], str] | None = None,
        out: Callable[[str], None] | None = None,
    ) -> None:
        self.theme = theme or TerminalTheme()
        self._key_source = key_source
        self._line_source = line_source
        self._out = out or print

    def print(self, text: str = "") -> None:
        self._out(text)

    def print_lines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self._out(line)

    def separator(self, char: str | None = None, width: int | None = None) -> None:
        w = width if width is not None else terminal_width()
        if char is None:
            char = "-" * w if not supports_unicode() else "─" * w
        else:
            char = char * w
        self._out(self.theme.dim(char))

    def width(self) -> int:
        return terminal_width()

    def is_narrow(self) -> bool:
        return self.width() < 90

    # -- Input --------------------------------------------------------
    def read_key(self, valid_keys: set[str], prompt: str) -> str:
        """Reads exactly one logical key selection.

        Returns the lowercased key. Raises KeyboardInterrupt on Ctrl+C and
        EOFError on end-of-input -- callers must handle both gracefully
        (no traceback shown to the user).
        """
        if self._key_source is not None:
            raw = self._key_source()
            if raw is None:
                raise EOFError("test key_source exhausted")
            return raw.strip().lower()

        if _MSVCRT_AVAILABLE and _stdin_is_interactive():
            return self._read_key_msvcrt(prompt)
        return self._read_key_line(prompt)

    def _read_key_msvcrt(self, prompt: str) -> str:
        self._out(prompt)
        while True:
            ch = msvcrt.getwch()  # type: ignore[union-attr]
            if ch in ("\x03",):  # Ctrl+C when console mode doesn't raise SIGINT itself
                raise KeyboardInterrupt
            if ch in ("\x00", "\xe0"):
                # Extended/function key prefix -- consume and discard the
                # follow-up byte, it maps to no menu action here.
                msvcrt.getwch()  # type: ignore[union-attr]
                continue
            if ch in ("\r", "\n"):
                continue
            return ch.lower()

    def _read_key_line(self, prompt: str) -> str:
        try:
            raw = input(prompt)
        except EOFError:
            raise
        except KeyboardInterrupt:
            raise
        raw = raw.strip()
        if not raw:
            return ""
        return raw[0].lower()

    def read_line(self, prompt: str) -> str:
        """Reads a full line of free-text input (e.g. a scan target or file
        path) -- distinct from read_key()'s single-character selection.
        Raises KeyboardInterrupt/EOFError, same contract as read_key()."""
        if self._line_source is not None:
            raw = self._line_source()
            if raw is None:
                raise EOFError("test line_source exhausted")
            return raw.strip()
        raw = input(prompt)
        return raw.strip()
