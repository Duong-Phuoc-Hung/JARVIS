"""
tests/unit/test_app_web_dedupe_stress.py
=======================================
H-07 Acceptance Test:
Verify that rapid repeated open_app / open_website dispatches (3 commands x 20 iterations)
enforce rate-limiting and deduplication without process fanout or runaway.
"""
from unittest.mock import MagicMock, patch
import pytest

from jarvis.automation.control import ComputerController
from jarvis.core.runaway_guard import launch_dedupe_guard


@pytest.fixture(autouse=True)
def clean_guard():
    """Reset the launch dedupe guard state before and after each test."""
    launch_dedupe_guard.reset()
    yield
    launch_dedupe_guard.reset()


def test_h07_open_app_20_times_no_fanout():
    """Calling open_app 20 times rapidly allows only 1 dispatch; 19 are suppressed."""
    ctrl = ComputerController()
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as mock_startfile, \
         patch("subprocess.Popen") as mock_popen:

        results = []
        for i in range(20):
            res = ctrl.open_app("spotify")
            results.append(res)

        # Exactly 1 success
        successes = [r for r in results if r.get("success") is True]
        assert len(successes) == 1

        # Exactly 19 suppressed with LAUNCH_RATE_LIMITED
        suppressed = [r for r in results if r.get("error_code") == "LAUNCH_RATE_LIMITED"]
        assert len(suppressed) == 19

        # Process launched exactly once
        total_launches = mock_startfile.call_count + mock_popen.call_count
        assert total_launches == 1


def test_h07_open_website_20_times_no_fanout():
    """Calling open_website 20 times rapidly allows only 1 dispatch; 19 are suppressed."""
    ctrl = ComputerController()
    with patch("webbrowser.open") as mock_wb, \
         patch("os.startfile", create=True) as mock_startfile, \
         patch("subprocess.Popen") as mock_popen:

        results = []
        for i in range(20):
            res = ctrl.open_website("https://claude.ai")
            results.append(res)

        successes = [r for r in results if r.get("success") is True]
        assert len(successes) == 1

        suppressed = [r for r in results if r.get("error_code") == "LAUNCH_RATE_LIMITED"]
        assert len(suppressed) == 19

        total_launches = mock_wb.call_count + mock_startfile.call_count + mock_popen.call_count
        assert total_launches == 1


def test_h07_three_commands_cross_action_dedupe():
    """3 distinct targets x 20 times each = 60 total calls -> exactly 3 launches."""
    ctrl = ComputerController()
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as mock_startfile, \
         patch("webbrowser.open") as mock_wb, \
         patch("subprocess.Popen") as mock_popen:

        targets = [
            ("app", "spotify"),
            ("app", "chrome"),
            ("web", "https://claude.ai"),
        ]

        total_dispatches = 0
        total_suppressed = 0

        for kind, target in targets:
            for _ in range(20):
                if kind == "app":
                    res = ctrl.open_app(target)
                else:
                    res = ctrl.open_website(target)

                if res.get("success") is True:
                    total_dispatches += 1
                elif res.get("error_code") == "LAUNCH_RATE_LIMITED":
                    total_suppressed += 1

        assert total_dispatches == 3
        assert total_suppressed == 57
