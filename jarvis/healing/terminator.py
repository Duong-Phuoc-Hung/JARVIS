"""
jarvis/healing/terminator.py
============================
Safe process termination engine with immutable OS-critical whitelist,
two-phase graceful shutdown, memory reclamation, and vocalized healing reports.
Features:
  - F-43: Autonomous safe process termination, memory reclamation, voice healing report.
  - Immutable OS-critical whitelist (System, csrss.exe, wininit.exe, services.exe, lsass.exe, explorer.exe, dwm.exe, etc.).
  - Two-phase termination protocol (WM_CLOSE / SIGTERM -> TerminateProcess / SIGKILL).
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from jarvis.healing.watchdog import UnresponsiveAppDetector
from jarvis.platform.windows import platform_win32

log = logging.getLogger("jarvis.healing.terminator")

# Immutable Windows OS & JARVIS process whitelist (case-insensitive)
PROTECTED_PROCESS_WHITELIST: set[str] = {
    "system",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "winlogon.exe",
    "dwm.exe",
    "explorer.exe",
    "sihost.exe",
    "fontdrvhost.exe",
    "spoolsv.exe",
    "ctfmon.exe",
    "runtimebroker.exe",
    "python.exe",
    "pythonw.exe",
    "jarvis.exe",
}


class HealingMode(str, Enum):
    AUTONOMOUS = "autonomous"  # Auto-kills hung or memory leaking processes
    ADVISORY = "advisory"      # Warns via TTS/Logs without terminating processes


@dataclass
class HealingReport:
    """Structured report returned after healing execution, compatible with dict access."""
    success: bool
    pid: int | None = None
    name: str | None = None
    reclaimed_ram: float | None = None
    spoken_message: str = ""
    reason: str | None = None
    alert_issued: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "success": self.success,
            "spoken_message": self.spoken_message,
            "timestamp": self.timestamp,
        }
        if self.pid is not None:
            d["pid"] = self.pid
        if self.name is not None:
            d["name"] = self.name
        if self.reclaimed_ram is not None:
            d["reclaimed_ram"] = self.reclaimed_ram
        if self.reason is not None:
            d["reason"] = self.reason
        if self.alert_issued:
            d["alert_issued"] = self.alert_issued
        return d

    def __getitem__(self, item: str) -> Any:
        d = self.to_dict()
        if item in d:
            return d[item]
        return getattr(self, item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, item: str) -> bool:
        return item in self.to_dict()

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def keys(self) -> Iterator[str]:
        return iter(self.to_dict().keys())


class AutonomousTerminator:
    """Executes safe 2-phase process termination and memory recovery."""

    def __init__(
        self,
        win32_platform: Any | None = None,
        hardware_provider: Any | None = None,
        custom_whitelist: set[str] | None = None,
        grace_period_s: float = 2.5,
    ) -> None:
        self.win32 = win32_platform if win32_platform is not None else platform_win32
        self.hardware = hardware_provider
        self.grace_period_s = grace_period_s
        self.whitelist: set[str] = set(PROTECTED_PROCESS_WHITELIST)
        if custom_whitelist:
            self.whitelist.update(k.lower() for k in custom_whitelist)

        # Protect self PID
        self.self_pid = os.getpid()

    def is_protected(self, process_name: str, pid: int | None = None) -> bool:
        """Validates if process is on immutable OS whitelist or matches self PID."""
        if pid is not None and pid == self.self_pid:
            return True
        name_clean = (process_name or "").lower().strip()
        if name_clean in self.whitelist:
            return True
        if not name_clean.endswith(".exe") and f"{name_clean}.exe" in self.whitelist:
            return True
        return False

    def terminate_process(self, pid: int, process_name: str, hwnd: int | None = None) -> bool:
        """
        Executes two-phase safe termination:
        Phase 1: Graceful WM_CLOSE / SIGTERM.
        Phase 2: Forceful TerminateProcess / SIGKILL if process remains alive.

        Truthfulness contract (v4.5.2 self-healing hotfix): only a confirmed
        outcome is ever reported as True. An injected test/simulation
        backend's result is trusted only via an explicit callable it
        exposes -- the mere presence of a bookkeeping attribute (e.g.
        `killed_pids`) is never, by itself, treated as proof of a real or
        simulated successful termination. Every real-backend failure path
        (access denied, missing process, failed kill, a failed
        TerminateProcess return value, an exception, or an unconfirmed
        outcome) returns False -- `.terminate()`/`.kill()` being *called*
        without raising is not, by itself, proof the process actually
        exited.
        """
        if self.is_protected(process_name, pid=pid):
            log.warning("Refused termination of protected process: [%s] (pid=%d)", process_name, pid)
            return False

        log.info("Initiating safe termination for process [%s] (pid=%d)", process_name, pid)

        # 1. Explicit injected test/simulation backend. Trust only its
        # actual confirmed boolean result -- never the mere presence of a
        # `killed_pids`-style counter attribute.
        term_fn = getattr(self.win32, "terminate_process", None)
        if callable(term_fn):
            try:
                return bool(term_fn(pid))
            except Exception as exc:
                log.error("Injected win32.terminate_process() raised for pid=%d: %s", pid, exc)
                return False

        # 2. Phase 1: Graceful WM_CLOSE if window handle known
        if hwnd and hasattr(self.win32, "close_window"):
            try:
                self.win32.close_window(hwnd)
            except Exception as e:
                log.debug("WM_CLOSE delivery failed: %s", e)

        # Phase 1: psutil terminate (SIGTERM)
        proc_obj = None
        if HAS_PSUTIL:
            try:
                proc_obj = psutil.Process(pid)
                proc_obj.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                log.warning("Cannot signal pid=%d (%s) for termination: %s", pid, process_name, exc)
                proc_obj = None
            except Exception as exc:
                log.error("Unexpected error signaling pid=%d (%s) for termination: %s", pid, process_name, exc)
                proc_obj = None

        # Wait grace period and confirm the process actually exited.
        if proc_obj:
            try:
                proc_obj.wait(timeout=self.grace_period_s)
                log.info("Process [%s] (pid=%d) exited gracefully.", process_name, pid)
                return True
            except psutil.NoSuchProcess:
                # Confirmed gone -- a genuine successful exit, not an error.
                log.info("Process [%s] (pid=%d) no longer exists after wait.", process_name, pid)
                return True
            except psutil.TimeoutExpired:
                log.warning(
                    "Process [%s] (pid=%d) did not exit within grace period. Escalating to forceful kill.",
                    process_name,
                    pid,
                )
            except Exception as exc:
                log.error("Unexpected error waiting on pid=%d (%s): %s", pid, process_name, exc)

        # 3. Phase 2: Forceful TerminateProcess / kill, with confirmed exit.
        if proc_obj:
            try:
                proc_obj.kill()
            except psutil.NoSuchProcess:
                return True  # Already gone -- confirmed.
            except psutil.AccessDenied as exc:
                log.error("Access denied killing pid=%d (%s): %s", pid, process_name, exc)
                return False
            except Exception as exc:
                log.error("psutil.kill failed on pid %d (%s): %s", pid, process_name, exc)
                return False

            # Do not assume success merely because .kill() was invoked
            # without raising -- confirm the process actually exited.
            try:
                proc_obj.wait(timeout=self.grace_period_s)
                return True
            except psutil.NoSuchProcess:
                return True
            except psutil.TimeoutExpired:
                log.error("Process [%s] (pid=%d) still alive after forceful kill.", process_name, pid)
                return False
            except Exception as exc:
                log.error("Unexpected error confirming kill for pid=%d (%s): %s", pid, process_name, exc)
                return False

        # Direct Win32 TerminateProcess fallback via ctypes
        if sys.platform == "win32":
            try:
                kernel32 = getattr(ctypes.windll, "kernel32", None)
                if kernel32 and hasattr(kernel32, "OpenProcess") and hasattr(kernel32, "TerminateProcess"):
                    h_proc = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE = 0x0001
                    if h_proc:
                        try:
                            result = kernel32.TerminateProcess(h_proc, 1)
                            # A falsy/zero return means the API itself
                            # reported failure -- do not assume success
                            # merely because the function was invoked.
                            return bool(result)
                        finally:
                            if hasattr(kernel32, "CloseHandle"):
                                kernel32.CloseHandle(h_proc)
            except Exception as e:
                log.error("kernel32.TerminateProcess failed on pid %d: %s", pid, e)

        return False


class HealingEngine:
    """
    Unified Self-Healing Supervisor.
    Combines ResourceWatchdog, UnresponsiveAppDetector, and AutonomousTerminator
    providing 100% compatibility with test suites and live background daemon workflows.
    """

    def __init__(
        self,
        win32_platform: Any | None = None,
        hardware_provider: Any | None = None,
        auto_kill: bool = True,
        mode: HealingMode | str = HealingMode.AUTONOMOUS,
        custom_whitelist: set[str] | None = None,
        ram_threshold: float = 90.0,
    ) -> None:
        self.win32 = win32_platform if win32_platform is not None else platform_win32
        self.hardware = hardware_provider
        self.auto_kill = auto_kill if isinstance(auto_kill, bool) else (str(mode).lower() != "advisory")
        self.mode = HealingMode.AUTONOMOUS if self.auto_kill else HealingMode.ADVISORY
        self.ram_threshold = ram_threshold

        self.terminator = AutonomousTerminator(
            win32_platform=self.win32,
            hardware_provider=self.hardware,
            custom_whitelist=custom_whitelist,
        )
        self.detector = UnresponsiveAppDetector(win32_platform=self.win32)
        self.healing_log: list[dict[str, Any]] = []

    def is_ram_critical(self) -> bool:
        """Returns True if current system RAM >= ram_threshold."""
        if self.hardware is not None and hasattr(self.hardware, "ram_percent"):
            return float(self.hardware.ram_percent) >= self.ram_threshold
        if HAS_PSUTIL:
            try:
                return float(psutil.virtual_memory().percent) >= self.ram_threshold
            except Exception:
                pass
        return False

    def _read_ram_percent(self) -> float | None:
        """
        Reads the current observed system RAM percentage. Never fabricates a
        value -- returns None when RAM genuinely cannot be measured (no
        hardware provider and no psutil), so callers can omit the metric
        rather than inventing one.
        """
        if self.hardware is not None:
            # A single getattr() access -- not a `hasattr(...)` check
            # followed by a separate attribute read, which would invoke a
            # `ram_percent` property getter twice (once for the hasattr
            # probe, once for the real read) if the provider ever exposes
            # it as a property rather than a plain attribute.
            ram = getattr(self.hardware, "ram_percent", None)
            if ram is not None:
                try:
                    return float(ram)
                except Exception:
                    return None
        if HAS_PSUTIL:
            try:
                return float(psutil.virtual_memory().percent)
            except Exception:
                return None
        return None

    def find_hung_windows(self) -> list[Any]:
        """Returns list of unresponsive windows/applications."""
        return self.detector.find_hung_windows()

    def is_protected(self, process_name: str, pid: int | None = None) -> bool:
        """Checks if process name is on the protected whitelist."""
        return self.terminator.is_protected(process_name, pid=pid)

    def heal_hung_process(self, pid: int, name: str, hwnd: int | None = None) -> dict[str, Any]:
        """
        Remediates a hung or leaking application process:
        - Rejects protected system processes.
        - Issues spoken warning in Advisory mode.
        - Executes 2-phase termination in Autonomous mode.

        Truthfulness contract (v4.5.2 self-healing hotfix): `success` and the
        spoken message reflect only a CONFIRMED termination outcome --
        `terminator.terminate_process()`'s actual return value is captured
        and trusted, never assumed. An unexpected exception from the
        terminator is caught locally and reported as a truthful failure, not
        upgraded to success. RAM is never fabricated or mutated by this
        method: `reclaimed_ram` (when present) is the actual observed
        `ram_before - ram_after` delta (floored at 0.0), and is omitted
        entirely when RAM cannot be measured.
        """
        # 1. Protected whitelist check
        if self.is_protected(name, pid=pid):
            log.warning("Cannot terminate protected system process: %s (pid=%d)", name, pid)
            report = {
                "success": False,
                "reason": "PROTECTED_PROCESS",
                "spoken_message": f"Không thể tắt tiến trình hệ thống được bảo vệ: {name}",
            }
            return report

        # 2. Advisory mode check (auto_kill == False)
        if not self.auto_kill:
            log.info("Advisory mode active: issued warning for hung process %s (pid=%d)", name, pid)
            report = {
                "success": False,
                "reason": "AUTO_KILL_DISABLED",
                "alert_issued": True,
                "spoken_message": f"Cảnh báo: Tiến trình {name} đang bị treo.",
            }
            return report

        # 3. Autonomous kill execution -- capture and trust the real result.
        ram_before = self._read_ram_percent()
        try:
            terminated = self.terminator.terminate_process(pid=pid, process_name=name, hwnd=hwnd)
        except Exception as exc:
            log.error("terminate_process raised for pid=%d (%s): %s", pid, name, exc)
            report = {
                "success": False,
                "pid": pid,
                "name": name,
                "reason": "TERMINATION_FAILED",
                "spoken_message": f"Lỗi hệ thống khi cố gắng chấm dứt tiến trình {name}.",
            }
            self.healing_log.append(report)
            return report

        if not terminated:
            log.warning("Termination not confirmed for pid=%d (%s).", pid, name)
            report = {
                "success": False,
                "pid": pid,
                "name": name,
                "reason": "TERMINATION_FAILED",
                "spoken_message": f"Cảnh báo: không thể xác nhận đã chấm dứt tiến trình {name}.",
            }
            self.healing_log.append(report)
            return report

        # 4. Observed memory reclamation only -- never fabricated, never
        # mutated into the telemetry provider.
        ram_after = self._read_ram_percent()
        reclaimed_ram: float | None = None
        if ram_before is not None and ram_after is not None:
            reclaimed_ram = max(0.0, ram_before - ram_after)

        # Neutral, truthful base claim: only that the confirmed action
        # (terminating `name`) succeeded. heal_hung_process() is invoked for
        # any hung process, RAM-critical or not, so an "overloaded system"
        # claim is prepended ONLY when RAM was actually measured before the
        # termination attempt AND proven to be at/above the configured
        # critical threshold -- never asserted unconditionally.
        speech_segments = [f"Đã xử lý: {name}."]
        if ram_before is not None and ram_before >= self.ram_threshold:
            speech_segments.insert(0, "Hệ thống bị quá tải.")
        if reclaimed_ram:
            speech_segments.append(f"RAM hiện tại: {ram_after:.0f}%, đã giải phóng {reclaimed_ram:.0f}%.")
        elif ram_after is not None:
            speech_segments.append(f"RAM hiện tại: {ram_after:.0f}%.")
        speech = " ".join(speech_segments)

        report: dict[str, Any] = {
            "success": True,
            "pid": pid,
            "name": name,
            "spoken_message": speech,
        }
        if reclaimed_ram is not None:
            report["reclaimed_ram"] = reclaimed_ram
        if ram_before is not None:
            report["ram_before_percent"] = ram_before
        if ram_after is not None:
            report["ram_after_percent"] = ram_after
        self.healing_log.append(report)
        return report

    def run_auto_recovery_cycle(self) -> list[dict[str, Any]]:
        """
        Scans for all hung applications and performs autonomous healing.
        Returns list of recovery reports.
        """
        hung_apps = self.find_hung_windows()
        reports = []
        for app in hung_apps:
            pid = getattr(app, "pid", None)
            name = getattr(app, "process_name", getattr(app, "title", "Unknown"))
            hwnd = getattr(app, "hwnd", None)
            if pid:
                rep = self.heal_hung_process(pid=pid, name=name, hwnd=hwnd)
                reports.append(rep)
        return reports
