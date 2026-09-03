"""
tests/unit/test_terminal_console.py
======================================
Input/rendering primitive tests. Uses injected key_source/line_source --
never touches real stdin, msvcrt, or a real terminal.
"""
from __future__ import annotations

import pytest

from jarvis.ui.terminal.console import TerminalConsole, supports_unicode, terminal_width
from jarvis.ui.terminal.theme import Ansi, StatusLevel, TerminalTheme


def test_read_key_uses_injected_key_source():
    console = TerminalConsole(key_source=lambda: "A", out=lambda t: None)
    assert console.read_key({"a"}, "> ") == "a"


def test_read_key_lowercases_uppercase_input():
    console = TerminalConsole(key_source=lambda: "J", out=lambda t: None)
    assert console.read_key({"j"}, "> ") == "j"


def test_read_key_raises_eof_when_source_exhausted():
    console = TerminalConsole(key_source=lambda: None, out=lambda t: None)
    with pytest.raises(EOFError):
        console.read_key({"a"}, "> ")


def test_read_line_uses_injected_line_source():
    console = TerminalConsole(line_source=lambda: "192.168.1.0/24", out=lambda t: None)
    assert console.read_line("target: ") == "192.168.1.0/24"


def test_read_line_strips_whitespace():
    console = TerminalConsole(line_source=lambda: "  hello  ", out=lambda t: None)
    assert console.read_line("> ") == "hello"


def test_print_lines_calls_out_for_each_line():
    captured = []
    console = TerminalConsole(out=captured.append)
    console.print_lines(["a", "b", "c"])
    assert captured == ["a", "b", "c"]


def test_no_color_theme_returns_plain_text():
    theme = TerminalTheme(color_enabled=False)
    assert theme.status(StatusLevel.PASS) == "PASS"
    assert Ansi.BRIGHT_CYAN not in theme.logo("J.A.R.V.I.S.")


def test_color_enabled_theme_wraps_ansi_codes():
    theme = TerminalTheme(color_enabled=True)
    styled = theme.error("FAILED")
    assert Ansi.RESET in styled
    assert "FAILED" in styled


def test_unknown_status_level_falls_back_to_unknown_not_a_crash():
    theme = TerminalTheme(color_enabled=False)
    assert theme.status("not_a_real_status") == "UNKNOWN"


def test_terminal_width_has_a_sane_floor():
    assert terminal_width() >= 60


def test_console_separator_is_ascii_safe_when_unicode_unsupported(monkeypatch):
    monkeypatch.setattr("jarvis.ui.terminal.console.supports_unicode", lambda: False)
    captured = []
    console = TerminalConsole(out=captured.append)
    console.separator(width=10)
    assert captured[0].strip() == "-" * 10


def test_console_separator_uses_unicode_when_supported(monkeypatch):
    monkeypatch.setattr("jarvis.ui.terminal.console.supports_unicode", lambda: True)
    captured = []
    console = TerminalConsole(out=captured.append)
    console.separator(width=10)
    assert "─" in captured[0]
