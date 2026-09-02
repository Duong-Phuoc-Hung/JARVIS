"""
tests/unit/test_healing_truthfulness.py
========================================
Focused regression suite for the v4.5.2 self-healing (AutonomousTerminator /
HealingEngine) truthfulness hotfix.

All process termination in this file is simulated via deterministic mocks,
monkeypatched psutil/ctypes objects, or explicit injected test doubles. No
test in this file targets the developer's current Python PID, a real desktop
application, a real system PID, or any manually selected existing process,
and no test invokes a real Windows LockWorkStation/TerminateProcess API.
"""
from __future__ import annotations

import ctypes

import psutil
import pytest

import jarvis.healing.terminator as terminator_module
from jarvis.healing.terminator import AutonomousTerminator, HealingEngine

# ============================================================================
# Deterministic, synthetic test doubles -- never touch a real process/API.
# ============================================================================


class _LockstepWin32:
    """
    Minimal win32 double exposing only `.terminate_process()`, deliberately
    WITHOUT a `killed_pids` counter or `windows` dict, proving production
    trusts only the explicit callable result -- never a bookkeeping
    attribute's mere presence.
    """

    def __init__(self, result: bool = True, raise_exc: Exception | None = None):
        self.calls = 0
        self.result = result
        self.raise_exc = raise_exc

    def terminate_process(self, pid: int) -> bool:
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return bool(self.result)


class _NoOpWin32:
    """
    Win32 double with NO terminate_process/close_window/killed_pids at all,
    forcing AutonomousTerminator to fall through to the real psutil/ctypes
    code paths (both of which are separately monkeypatched in every test
    that uses this double -- no real API is ever reached).
    """


class _FakeProc:
    """Deterministic stand-in for a psutil.Process instance."""

    def __init__(
        self,
        terminate_exc: Exception | None = None,
        first_wait_exc: Exception | None = None,
        kill_exc: Exception | None = None,
        second_wait_exc: Exception | None = None,
    ):
        self.terminate_called = False
        self.kill_called = False
        self.wait_calls = 0
        self._terminate_exc = terminate_exc
        self._first_wait_exc = first_wait_exc
        self._kill_exc = kill_exc
        self._second_wait_exc = second_wait_exc

    def terminate(self):
        self.terminate_called = True
        if self._terminate_exc is not None:
            raise self._terminate_exc

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.wait_calls == 1 and self._first_wait_exc is not None:
            raise self._first_wait_exc
        if self.wait_calls == 2 and self._second_wait_exc is not None:
            raise self._second_wait_exc
        return None

    def kill(self):
        self.kill_called = True
        if self._kill_exc is not None:
            raise self._kill_exc


class _FakeKernel32:
    """
    Deterministic stand-in for ctypes.windll.kernel32. Never touches a real
    process -- OpenProcess/TerminateProcess/CloseHandle are pure Python
    bookkeeping.
    """

    def __init__(self, open_process_handle: int = 4444, terminate_result: int = 1):
        self.open_process_calls: list[int] = []
        self.terminate_calls: list[tuple[int, int]] = []
        self.close_handle_calls: list[int] = []
        self._open_process_handle = open_process_handle
        self._terminate_result = terminate_result

    def OpenProcess(self, access, inherit, pid):
        self.open_process_calls.append(pid)
        return self._open_process_handle

    def TerminateProcess(self, handle, exit_code):
        self.terminate_calls.append((handle, exit_code))
        return self._terminate_result

    def CloseHandle(self, handle):
        self.close_handle_calls.append(handle)
        return 1


class _SequentialRamProvider:
    """
    Returns successive values from a fixed sequence on each `ram_percent`
    access, simulating genuinely different RAM readings taken at different
    times (before vs after termination) -- without any production code
    mutating it.
    """

    def __init__(self, values: list[float]):
        self._values = list(values)
        self._index = 0

    @property
    def ram_percent(self) -> float:
        v = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return v


class _FailIfSetRamCalled:
    """Hardware double proving production never mutates telemetry: any call
    to `.set_ram()` fails the test immediately."""

    def __init__(self, ram_percent: float = 80.0):
        self.ram_percent = ram_percent

    def set_ram(self, value):
        raise AssertionError("hardware.set_ram() must never be called by production healing code")


# ============================================================================
# 1-3: terminate_process result determines healing report success/failure
# ============================================================================


def test_heal_hung_process_success_speech_only_after_confirmed_success():
    """[1] terminate_process True -> success True, speech only claims success after confirmation."""
    win32 = _LockstepWin32(result=True)
    hardware = _FailIfSetRamCalled(ram_percent=50.0)
    engine = HealingEngine(win32_platform=win32, hardware_provider=hardware, auto_kill=True)

    report = engine.heal_hung_process(pid=1111, name="leaky.exe")

    assert report["success"] is True
    assert win32.calls == 1
    assert "Đã xử lý" in report["spoken_message"]


def test_heal_hung_process_termination_returns_false():
    """[2] terminate_process False -> success False, reason TERMINATION_FAILED, no success speech."""
    win32 = _LockstepWin32(result=False)
    hardware = _FailIfSetRamCalled(ram_percent=80.0)
    engine = HealingEngine(win32_platform=win32, hardware_provider=hardware, auto_kill=True)

    report = engine.heal_hung_process(pid=2222, name="stuck.exe")

    assert report["success"] is False
    assert report["reason"] == "TERMINATION_FAILED"
    assert "Đã xử lý" not in report["spoken_message"]
    assert win32.calls == 1


def test_heal_hung_process_termination_raises():
    """[3] terminate_process raises -> exception does not escape, success False, truthful reason."""
    win32 = _LockstepWin32(raise_exc=RuntimeError("simulated backend crash"))
    hardware = _FailIfSetRamCalled(ram_percent=80.0)
    engine = HealingEngine(win32_platform=win32, hardware_provider=hardware, auto_kill=True)

    report = engine.heal_hung_process(pid=3333, name="crashy.exe")  # must not raise

    assert report["success"] is False
    assert report["reason"] == "TERMINATION_FAILED"
    assert "Đã xử lý" not in report["spoken_message"]
    assert report["spoken_message"]


# ============================================================================
# 4: failed termination never fabricates RAM
# ============================================================================


def test_failed_termination_never_calls_set_ram_or_fabricates_ram():
    """[4] Failed termination: hardware.set_ram is NEVER called, no fabricated reclaimed_ram."""
    win32 = _LockstepWin32(result=False)
    hardware = _FailIfSetRamCalled(ram_percent=91.0)
    engine = HealingEngine(win32_platform=win32, hardware_provider=hardware, auto_kill=True)

    report = engine.heal_hung_process(pid=4444, name="fail.exe")

    assert report["success"] is False
    assert hardware.ram_percent == 91.0  # unchanged; set_ram would have raised if called
    assert "reclaimed_ram" not in report


# ============================================================================
# 5-7: RAM telemetry semantics
# ============================================================================


def test_successful_termination_observed_ram_decrease():
    """[5][3] Successful termination + actual observed RAM decrease: reports only the observed delta, no synthetic percentage."""
    win32 = _LockstepWin32(result=True)
    # Both readings are below the default ram_threshold (90.0), so this
    # scenario is deliberately NOT an "overloaded system" case -- it isolates
    # the RAM-decrease-reporting behavior from the overload-claim behavior.
    hardware = _SequentialRamProvider([70.0, 50.0])  # before, after
    engine = HealingEngine(win32_platform=win32, hardware_provider=hardware, auto_kill=True)

    report = engine.heal_hung_process(pid=5555, name="leaky.exe")

    assert report["success"] is True
    assert report["ram_before_percent"] == 70.0
    assert report["ram_after_percent"] == 50.0
    assert report["reclaimed_ram"] == 20.0
    assert "giải phóng" in report["spoken_message"]
    assert "50%" in report["spoken_message"]
    assert "quá tải" not in report["spoken_message"]


def test_successful_termination_normal_ram_unchanged():
    """
    [6][1] Confirmed termination with normal (below-threshold) RAM: success
    True, contains a truthful process-success phrase, no "quá tải" overload
    claim, and no fabricated RAM-reclaimed claim when the delta is 0.
    """
    win32 = _LockstepWin32(result=True)
    hardware = _SequentialRamProvider([60.0, 60.0])  # both below default threshold (90.0)
    engine = HealingEngine(win32_platform=win32, hardware_provider=hardware, auto_kill=True)

    report = engine.heal_hung_process(pid=6666, name="stable.exe")

    assert report["success"] is True
    assert "Đã xử lý: stable.exe" in report["spoken_message"]
    assert report["reclaimed_ram"] == 0.0
    assert "giải phóng" not in report["spoken_message"]
    assert "quá tải" not in report["spoken_message"]


def test_successful_termination_ram_unavailable(monkeypatch):
    """
    [7][2] Confirmed termination with RAM telemetry unavailable: success
    True, no invented RAM percentage, no overload claim, no reclaimed-RAM
    claim.
    """
    win32 = _LockstepWin32(result=True)
    engine = HealingEngine(win32_platform=win32, hardware_provider=None, auto_kill=True)

    def _raise(*a, **kw):
        raise RuntimeError("psutil unavailable in this simulated environment")

    monkeypatch.setattr(terminator_module.psutil, "virtual_memory", _raise)

    report = engine.heal_hung_process(pid=7777, name="unmeasurable.exe")

    assert report["success"] is True
    assert "reclaimed_ram" not in report
    assert "ram_before_percent" not in report
    assert "ram_after_percent" not in report
    assert report["spoken_message"] == "Đã xử lý: unmeasurable.exe."
    assert "quá tải" not in report["spoken_message"]
    assert "RAM" not in report["spoken_message"]
    assert "giải phóng" not in report["spoken_message"]


def test_successful_termination_ram_at_or_above_threshold_may_claim_overload():
    """
    Confirmed termination where RAM was actually measured at/above the
    configured critical threshold BEFORE the termination attempt: the
    overload claim is truthfully proven and may appear.
    """
    win32 = _LockstepWin32(result=True)
    hardware = _SequentialRamProvider([94.0, 94.0])  # at/above default threshold (90.0)
    engine = HealingEngine(win32_platform=win32, hardware_provider=hardware, auto_kill=True)

    report = engine.heal_hung_process(pid=8888, name="overloaded.exe")

    assert report["success"] is True
    assert "quá tải" in report["spoken_message"]


# ============================================================================
# 8-9: protected process / advisory mode unchanged
# ============================================================================


def test_protected_process_unchanged_no_termination():
    """[8] Protected process: unchanged behavior, no termination attempted."""
    win32 = _LockstepWin32(result=True)
    engine = HealingEngine(win32_platform=win32, auto_kill=True)

    report = engine.heal_hung_process(pid=101, name="explorer.exe")

    assert report["success"] is False
    assert report["reason"] == "PROTECTED_PROCESS"
    assert win32.calls == 0


def test_advisory_mode_unchanged_no_termination():
    """[9] Advisory mode: unchanged AUTO_KILL_DISABLED behavior, no termination."""
    win32 = _LockstepWin32(result=True)
    engine = HealingEngine(win32_platform=win32, auto_kill=False)

    report = engine.heal_hung_process(pid=202, name="stuck.exe")

    assert report["success"] is False
    assert report["reason"] == "AUTO_KILL_DISABLED"
    assert report["alert_issued"] is True
    assert win32.calls == 0


# ============================================================================
# 10: run_auto_recovery_cycle mixed outcomes
# ============================================================================


def test_run_auto_recovery_cycle_mixed_outcomes(mock_win32_platform, monkeypatch):
    """[10] Mixed outcomes: successful target reports True, failed target reports False, no blanket success."""
    mock_win32_platform.add_hung_window("good_app.exe", pid=9101)
    mock_win32_platform.add_hung_window("bad_app.exe", pid=9102)

    def _selective_terminate(pid):
        if pid == 9101:
            mock_win32_platform.killed_pids.append(pid)
            return True
        return False

    monkeypatch.setattr(mock_win32_platform, "terminate_process", _selective_terminate)

    engine = HealingEngine(win32_platform=mock_win32_platform, auto_kill=True)
    reports = engine.run_auto_recovery_cycle()

    assert len(reports) == 2
    by_pid = {r["pid"]: r for r in reports if "pid" in r}
    assert by_pid[9101]["success"] is True
    assert by_pid[9102]["success"] is False
    assert by_pid[9102]["reason"] == "TERMINATION_FAILED"
    assert 9101 in mock_win32_platform.killed_pids
    assert 9102 not in mock_win32_platform.killed_pids


# ============================================================================
# 11-13: AutonomousTerminator direct injected-backend contract
# ============================================================================


def test_terminator_injected_backend_success_trusted_and_pid_recorded_once():
    """[11] Explicit callable result True is trusted; the backend is invoked exactly once."""
    win32 = _LockstepWin32(result=True)
    terminator = AutonomousTerminator(win32_platform=win32)

    result = terminator.terminate_process(pid=8001, process_name="good.exe")

    assert result is True
    assert win32.calls == 1


def test_terminator_injected_backend_failure_result_is_false():
    """[12] False result remains False; the backend is invoked exactly once."""
    win32 = _LockstepWin32(result=False)
    terminator = AutonomousTerminator(win32_platform=win32)

    result = terminator.terminate_process(pid=8002, process_name="bad.exe")

    assert result is False
    assert win32.calls == 1


def test_terminator_injected_backend_raises_returns_false_no_fabricated_kill():
    """[13] Injected backend raises: termination returns False, no fabricated success."""
    win32 = _LockstepWin32(raise_exc=OSError("simulated backend failure"))
    terminator = AutonomousTerminator(win32_platform=win32)

    result = terminator.terminate_process(pid=8003, process_name="crashy.exe")  # must not raise

    assert result is False
    assert win32.calls == 1


# ============================================================================
# 14-15: Direct Win32 TerminateProcess ctypes fallback (fully mocked, never real)
# ============================================================================


def test_ctypes_terminate_process_returns_zero_yields_false(monkeypatch):
    """[14] Windows TerminateProcess mocked return 0 -> returns False. No real Win32 call."""

    def _raise_no_such_process(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(terminator_module.psutil, "Process", _raise_no_such_process)
    fake_kernel32 = _FakeKernel32(open_process_handle=5555, terminate_result=0)
    monkeypatch.setattr(ctypes.windll, "kernel32", fake_kernel32, raising=False)

    terminator = AutonomousTerminator(win32_platform=_NoOpWin32())
    result = terminator.terminate_process(pid=9999999, process_name="nonexistent.exe")

    assert result is False
    assert fake_kernel32.terminate_calls  # the mocked API was invoked, never a real one
    assert fake_kernel32.close_handle_calls


def test_ctypes_terminate_process_confirmed_success(monkeypatch):
    """[15] Windows TerminateProcess mocked successful result -> success under the confirmed contract. No real Win32 call."""

    def _raise_no_such_process(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(terminator_module.psutil, "Process", _raise_no_such_process)
    fake_kernel32 = _FakeKernel32(open_process_handle=5555, terminate_result=1)
    monkeypatch.setattr(ctypes.windll, "kernel32", fake_kernel32, raising=False)

    terminator = AutonomousTerminator(win32_platform=_NoOpWin32())
    result = terminator.terminate_process(pid=9999998, process_name="nonexistent2.exe")

    assert result is True
    assert fake_kernel32.terminate_calls == [(5555, 1)]
    assert fake_kernel32.close_handle_calls == [5555]


# ============================================================================
# 16: psutil real-path failure semantics -- no fabricated success
# ============================================================================


def test_psutil_access_denied_never_fabricates_success(monkeypatch):
    """[16a] psutil.AccessDenied on Process() construction: no fabricated success."""

    def _process_factory(pid):
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(terminator_module.psutil, "Process", _process_factory)
    # No real process obtained -> falls through to ctypes; force ctypes to
    # also fail deterministically so the overall result stays truthful.
    fake_kernel32 = _FakeKernel32(open_process_handle=0, terminate_result=0)
    monkeypatch.setattr(ctypes.windll, "kernel32", fake_kernel32, raising=False)

    terminator = AutonomousTerminator(win32_platform=_NoOpWin32())
    result = terminator.terminate_process(pid=7001, process_name="denied.exe")

    assert result is False


def test_psutil_timeout_then_kill_access_denied_never_fabricates_success(monkeypatch):
    """[16b] Grace-period timeout, then AccessDenied on the forceful kill: no fabricated success."""
    fake_proc = _FakeProc(
        first_wait_exc=psutil.TimeoutExpired(seconds=2.5, pid=7002),
        kill_exc=psutil.AccessDenied(7002),
    )
    monkeypatch.setattr(terminator_module.psutil, "Process", lambda pid: fake_proc)

    terminator = AutonomousTerminator(win32_platform=_NoOpWin32(), grace_period_s=0.01)
    result = terminator.terminate_process(pid=7002, process_name="stubborn.exe")

    assert result is False
    assert fake_proc.kill_called is True


def test_psutil_still_alive_after_forceful_kill_never_fabricates_success(monkeypatch):
    """[16c] kill() itself doesn't raise, but the process is confirmed still alive afterward: no fabricated success."""
    fake_proc = _FakeProc(
        first_wait_exc=psutil.TimeoutExpired(seconds=2.5, pid=7003),
        second_wait_exc=psutil.TimeoutExpired(seconds=2.5, pid=7003),
    )
    monkeypatch.setattr(terminator_module.psutil, "Process", lambda pid: fake_proc)

    terminator = AutonomousTerminator(win32_platform=_NoOpWin32(), grace_period_s=0.01)
    result = terminator.terminate_process(pid=7003, process_name="zombie.exe")

    assert result is False
    assert fake_proc.kill_called is True


def test_psutil_graceful_terminate_confirmed_success(monkeypatch):
    """
    Real psutil path, graceful exit confirmed via wait() -- genuine success,
    not merely 'terminate() didn't raise'.
    """
    fake_proc = _FakeProc()  # no exceptions anywhere -> terminate() then wait() succeeds
    monkeypatch.setattr(terminator_module.psutil, "Process", lambda pid: fake_proc)

    terminator = AutonomousTerminator(win32_platform=_NoOpWin32())
    result = terminator.terminate_process(pid=7500, process_name="graceful.exe")

    assert result is True
    assert fake_proc.terminate_called is True
    assert fake_proc.wait_calls == 1
    assert fake_proc.kill_called is False
