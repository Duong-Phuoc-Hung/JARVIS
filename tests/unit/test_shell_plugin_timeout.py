"""
tests/unit/test_shell_plugin_timeout.py
========================================
Regression coverage for the CI/production Windows shell-timeout fix in
jarvis/plugins/shell.py::ShellPlugin.exec_command().

Exercises the REAL production ShellPlugin (never the stale hand-duplicated
class in tests/test_plugins.py, which does not exercise the fix at all).

Background: subprocess.run(command, shell=True, timeout=N)'s own internal
Windows TimeoutExpired handling terminates only the immediate shell wrapper
(cmd.exe), then performs a SECOND, UNBOUNDED communicate() call to collect
output for the exception. If the shelled-out command spawned a grandchild
process that survives the wrapper's termination and keeps the inherited
stdout/stderr pipes open, that second call can block far past `timeout` --
this is exactly what made tests/unit/test_integration_e2e.py's inactivity
monitor test hang in CI on a real weather lookup (curl via shell_exec).

These tests reproduce the same process-tree shape (shell wrapper -> a
grandchild that sleeps far longer than the requested timeout) using Python
itself -- no network access, no destructive command -- and prove
exec_command() now returns in bounded wall-clock time regardless.
"""
from __future__ import annotations

import sys
import time

import pytest

from jarvis.plugins.shell import ShellPlugin

# Deliberately generous margins to avoid CI flakiness on slow runners, while
# staying far below GRANDCHILD_SLEEP_S so a regression (the old buggy
# behavior, which waits for the grandchild's own natural completion) is
# unmistakable rather than borderline.
REQUESTED_TIMEOUT_S = 1.0
GRANDCHILD_SLEEP_S = 8.25
MAX_ACCEPTABLE_WALL_CLOCK_S = 5.0  # well below GRANDCHILD_SLEEP_S


@pytest.fixture
def shell_plugin() -> ShellPlugin:
    return ShellPlugin.__new__(ShellPlugin)


def test_exec_command_timeout_is_wall_clock_bounded_not_grandchild_bounded(shell_plugin):
    """
    A shell=True command whose child spawns a grandchild that sleeps far
    longer than the requested timeout must still cause exec_command() to
    raise TimeoutError and RETURN within a bounded time close to the
    requested timeout -- not block until the grandchild's own natural
    completion. Cross-platform: the fix no longer relies on
    subprocess.run()'s own timeout handling on either OS, so this must hold
    on POSIX too, not just Windows.
    """
    command = f'"{sys.executable}" -c "import time; time.sleep({GRANDCHILD_SLEEP_S})"'

    t0 = time.monotonic()
    with pytest.raises(TimeoutError) as exc_info:
        shell_plugin.exec_command(command, timeout=REQUESTED_TIMEOUT_S)
    elapsed = time.monotonic() - t0

    assert f"timed out after {REQUESTED_TIMEOUT_S}s" in str(exc_info.value)
    assert elapsed < MAX_ACCEPTABLE_WALL_CLOCK_S, (
        f"exec_command() took {elapsed:.2f}s to raise TimeoutError -- it waited "
        f"for something close to the grandchild's {GRANDCHILD_SLEEP_S}s sleep "
        "instead of terminating the process tree promptly. This is the exact "
        "Windows subprocess.run(shell=True, timeout=...) grandchild-orphan "
        "defect this test guards against."
    )


def test_exec_command_normal_completion_still_returns_output(shell_plugin):
    """Sanity check: the Popen-based rewrite must not have broken the
    ordinary (non-timeout) success path -- exit code, stdout, stderr."""
    result = shell_plugin.exec_command(
        f'"{sys.executable}" -c "print(\'JARVIS_SHELL_OK\')"', timeout=10.0
    )
    assert result["exit_code"] == 0
    assert "JARVIS_SHELL_OK" in result["stdout"]
    assert result["stderr"] == ""


@pytest.mark.skipif(
    sys.platform != "win32",
    reason=(
        "This checks that the grandchild process itself (not just the "
        "immediate shell wrapper) is actually terminated -- the specific "
        "Windows process-tree defect this fix closes via `taskkill /F /T`. "
        "POSIX's subprocess timeout handling does not exhibit the same "
        "defect (CPython already populates output incrementally before "
        "raising TimeoutExpired there; see subprocess.py's own comment), "
        "and this project is Windows-first, so no POSIX tree-kill path "
        "was added to keep the fix minimal."
    ),
)
def test_exec_command_timeout_leaves_no_orphan_process(shell_plugin):
    """
    Regression test: after a timeout, the grandchild process itself must be
    terminated, not merely the cmd.exe wrapper -- an orphaned grandchild
    holding the output pipes open is exactly what caused the unbounded hang.
    """
    psutil = pytest.importorskip("psutil")

    sentinel = f"time.sleep({GRANDCHILD_SLEEP_S})"
    command = f'"{sys.executable}" -c "import time; {sentinel}"'

    with pytest.raises(TimeoutError):
        shell_plugin.exec_command(command, timeout=REQUESTED_TIMEOUT_S)

    # Give the OS a brief, bounded moment to finish reaping the terminated
    # tree, then confirm no matching process is still alive.
    time.sleep(0.5)
    survivors = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if sentinel in cmdline:
            survivors.append((proc.info["pid"], cmdline))

    assert not survivors, f"Orphan process(es) survived the timeout: {survivors}"
