"""
tests/unit/test_terminal_theme_vocabulary.py
============================================
Seam-First TDD tests for Milestone M3: Health Status Vocabulary Standardization.

Verifies:
1. StatusLevel enum has exactly the 5 canonical states: READY, LIMITED, BLOCKED, ERROR, UNAVAILABLE.
2. StatusLevel defines UNAVAILABLE.
3. TerminalTheme formats all 5 states properly.
4. Zero non-standard states are used in production code under jarvis/ui/terminal/.
"""
from __future__ import annotations

import re
from pathlib import Path
import pytest


def test_status_level_has_exact_five_canonical_members():
    """Assert that StatusLevel defines exactly: READY, LIMITED, BLOCKED, ERROR, UNAVAILABLE."""
    from jarvis.ui.terminal.theme import StatusLevel

    canonical_states = {"READY", "LIMITED", "BLOCKED", "ERROR", "UNAVAILABLE"}
    primary_members = {m.name for m in StatusLevel}
    assert primary_members == canonical_states
    assert len(StatusLevel) == 5


def test_status_level_has_unavailable():
    """Assert hasattr(StatusLevel, 'UNAVAILABLE') and StatusLevel.UNAVAILABLE.value == 'UNAVAILABLE'."""
    from jarvis.ui.terminal.theme import StatusLevel

    assert hasattr(StatusLevel, "UNAVAILABLE"), "StatusLevel must have member UNAVAILABLE"
    assert StatusLevel.UNAVAILABLE.value == "UNAVAILABLE"


def test_theme_formats_all_five_states():
    """Assert TerminalTheme().status() returns styled string without error for all 5 states."""
    from jarvis.ui.terminal.theme import StatusLevel, TerminalTheme

    theme_no_color = TerminalTheme(color_enabled=False)
    for state in (
        StatusLevel.READY,
        StatusLevel.LIMITED,
        StatusLevel.BLOCKED,
        StatusLevel.ERROR,
        StatusLevel.UNAVAILABLE,
    ):
        result = theme_no_color.status(state)
        assert state.value in result

    theme_color = TerminalTheme(color_enabled=True)
    for state in (
        StatusLevel.READY,
        StatusLevel.LIMITED,
        StatusLevel.BLOCKED,
        StatusLevel.ERROR,
        StatusLevel.UNAVAILABLE,
    ):
        result = theme_color.status(state)
        assert state.value in result


def test_zero_non_standard_states_in_production_modules():
    """Audit that StatusLevel.AVAILABLE, StatusLevel.PASS, StatusLevel.PARTIAL,
    StatusLevel.SKIPPED, StatusLevel.OFFLINE, StatusLevel.FAILED are not used in
    jarvis/ui/terminal/modules/, jarvis/ui/terminal/models.py, jarvis/ui/terminal/app.py.
    """
    terminal_dir = Path(__file__).resolve().parent.parent.parent / "jarvis" / "ui" / "terminal"
    pattern = re.compile(r"StatusLevel\.(AVAILABLE|PASS|PARTIAL|SKIPPED|OFFLINE|FAILED)")

    targets = [
        terminal_dir / "models.py",
        terminal_dir / "app.py",
        *(terminal_dir / "modules").glob("*.py"),
    ]

    violations = []
    for file_path in targets:
        assert file_path.is_file(), f"Target file does not exist: {file_path}"
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, start=1):
            if pattern.search(line):
                violations.append(f"{file_path.name}:{idx} {line.strip()}")

    assert not violations, (
        f"Found {len(violations)} non-standard StatusLevel usages in production code:\n"
        + "\n".join(violations)
    )


def test_legacy_status_aliases():
    """Verify that legacy enum names are safely aliased to canonical members."""
    from jarvis.ui.terminal.theme import StatusLevel

    assert StatusLevel.AVAILABLE == StatusLevel.READY
    assert StatusLevel.PASS == StatusLevel.READY
    assert StatusLevel.PARTIAL == StatusLevel.LIMITED
    assert StatusLevel.SKIPPED == StatusLevel.BLOCKED
    assert StatusLevel.OFFLINE == StatusLevel.UNAVAILABLE
    assert StatusLevel.FAILED == StatusLevel.ERROR
    assert StatusLevel.UNKNOWN == StatusLevel.UNAVAILABLE


def test_status_icons_mapped_for_all_canonical_states():
    """Verify that _STATUS_ICON maps all 5 canonical states and status_icon formats without error."""
    from jarvis.ui.terminal.theme import StatusLevel, TerminalTheme, _STATUS_ICON

    canonical_states = (
        StatusLevel.READY,
        StatusLevel.LIMITED,
        StatusLevel.BLOCKED,
        StatusLevel.ERROR,
        StatusLevel.UNAVAILABLE,
    )
    for state in canonical_states:
        assert state in _STATUS_ICON
        assert _STATUS_ICON[state] != ""

    theme = TerminalTheme(color_enabled=False)
    for state in canonical_states:
        icon_str = theme.status_icon(state)
        assert _STATUS_ICON[state] in icon_str
