"""
tests/unit/test_terminal_navigator.py
========================================
Deterministic navigation-stack tests for jarvis.ui.terminal.navigator.
"""
from __future__ import annotations

from jarvis.ui.terminal.models import MenuScreen
from jarvis.ui.terminal.navigator import TerminalNavigator


def _screen(sid: str) -> MenuScreen:
    return MenuScreen(id=sid, title=sid.upper(), breadcrumb=["MAIN"] if sid == "main" else ["MAIN", sid.upper()])


def _make_navigator() -> TerminalNavigator:
    screens = {"main": _screen("main"), "hardware": _screen("hardware"), "storage": _screen("storage")}
    return TerminalNavigator(resolve=lambda sid: screens[sid], root_id="main")


def test_starts_at_root():
    nav = _make_navigator()
    assert nav.current_id == "main"
    assert nav.at_root is True
    assert nav.depth == 1


def test_push_then_pop_returns_to_previous_level():
    nav = _make_navigator()
    nav.push("hardware")
    assert nav.current_id == "hardware"
    assert nav.at_root is False
    popped = nav.pop()
    assert popped is True
    assert nav.current_id == "main"
    assert nav.at_root is True


def test_pop_at_root_is_a_noop():
    nav = _make_navigator()
    popped = nav.pop()
    assert popped is False
    assert nav.current_id == "main"


def test_three_level_push_and_pop_sequence():
    nav = _make_navigator()
    nav.push("hardware")
    nav.push("storage")
    assert nav.stack_ids == ["main", "hardware", "storage"]
    nav.pop()
    assert nav.stack_ids == ["main", "hardware"]
    nav.pop()
    assert nav.stack_ids == ["main"]


def test_pop_exactly_one_level_never_more():
    nav = _make_navigator()
    nav.push("hardware")
    nav.push("storage")
    nav.pop()
    assert nav.depth == 2  # not popped all the way to root in one call


def test_replace_does_not_grow_the_stack():
    nav = _make_navigator()
    nav.push("hardware")
    nav.replace("storage")
    assert nav.stack_ids == ["main", "storage"]


def test_reset_returns_to_root():
    nav = _make_navigator()
    nav.push("hardware")
    nav.push("storage")
    nav.reset()
    assert nav.stack_ids == ["main"]


def test_exit_sets_exited_flag():
    nav = _make_navigator()
    assert nav.exited is False
    nav.exit()
    assert nav.exited is True


def test_breadcrumb_reflects_current_screen():
    nav = _make_navigator()
    assert nav.breadcrumb() == ["MAIN"]
    nav.push("hardware")
    assert nav.breadcrumb() == ["MAIN", "HARDWARE"]


def test_current_is_rebuilt_on_every_access_not_cached():
    """Refresh correctness depends on this: the navigator must re-resolve
    the screen builder every time, so stateful screens (e.g. dynamic drive
    lists) reflect the latest state without any special 'refresh' call."""
    calls = {"count": 0}

    def resolve(sid: str) -> MenuScreen:
        calls["count"] += 1
        return _screen(sid)

    nav = TerminalNavigator(resolve=resolve, root_id="main")
    _ = nav.current
    _ = nav.current
    assert calls["count"] == 2
