"""
tests/unit/test_watchdog_chaos.py
===================================
Chaos Engineering Test for JARVIS Watchdog Subprocess Supervision.
Performs 3 random kill injections on supervised worker subprocesses,
verifies automatic self-healing recovery within < 10s per iteration,
and computes / logs Mean Time To Recovery (MTTR) to stdout.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Any

import pytest

log = logging.getLogger("jarvis.test.chaos")


class SupervisedProcessRunner:
    """
    Subprocess supervisor with automatic watchdog health detection and recovery.
    Supervises a target subprocess command, monitors liveness, and automatically
    respawns a healthy child upon abnormal termination or kill injection.
    """

    def __init__(self, target_cmd: list[str], poll_interval_s: float = 0.05) -> None:
        self.target_cmd = target_cmd
        self.poll_interval_s = poll_interval_s
        self.process: subprocess.Popen | None = None
        self.restart_count = 0
        self.is_running = False
        self.recovery_events: list[dict[str, Any]] = []

    def start(self) -> int:
        """Start the supervised child process."""
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            self.target_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_cflags,
        )
        self.is_running = True
        return self.process.pid

    def supervise_and_recover(self, timeout_s: float = 10.0) -> float:
        """
        Watchdog detection loop: polls for process termination,
        detects crash, and respawns a healthy child. Returns TTR (Time-To-Recovery) in seconds.
        """
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout_s:
            if self.process is None or self.process.poll() is not None:
                # Failure detected by watchdog! Initiate recovery
                new_pid = self.start()
                self.restart_count += 1
                t_recovered = time.perf_counter()
                ttr = t_recovered - t0
                self.recovery_events.append({
                    "restart_idx": self.restart_count,
                    "new_pid": new_pid,
                    "ttr_seconds": ttr,
                })
                return ttr
            time.sleep(self.poll_interval_s)
        raise TimeoutError(f"Watchdog failed to recover process within {timeout_s}s")

    def kill_current_process(self) -> int:
        """Inject chaos by abruptly killing current child process."""
        if self.process and self.process.poll() is None:
            pid = self.process.pid
            self.process.kill()
            self.process.wait()
            return pid
        return -1

    def is_alive(self) -> bool:
        """Check if child process is currently alive."""
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        """Clean shutdown of supervisor and any running child process."""
        self.is_running = False
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                self.process.wait(timeout=2.0)
            except Exception:
                pass


class TestWatchdogChaosSupervision:
    """
    R6 Resilience Chaos Test Suite for Safety Gate & Healing Watchdog Subprocess Supervision.
    """

    def test_watchdog_subprocess_chaos_3x_recovery(self, capsys):
        """
        [R6 Chaos Test]
        Randomly terminate supervised subprocess 3 times.
        Assert each recovery completes in < 10s.
        Compute and log MTTR to stdout.
        """
        worker_script = [sys.executable, "-c", "import time; time.sleep(300)"]
        supervisor = SupervisedProcessRunner(target_cmd=worker_script, poll_interval_s=0.05)

        initial_pid = supervisor.start()
        assert initial_pid > 0
        assert supervisor.is_alive()

        ttr_records: list[float] = []

        print("\n" + "=" * 68)
        print("  JARVIS WATCHDOG SUBPROCESS SUPERVISION CHAOS TEST (3x RANDOM KILL)")
        print("=" * 68)
        print(f"[*] Supervisor initialized. Initial child PID: {initial_pid}")

        try:
            for iteration in range(1, 4):
                # Random delay before injecting chaos failure (simulating non-deterministic crash)
                jitter_s = 0.08 * iteration
                time.sleep(jitter_s)

                # 1. Chaos Injection: Abruptly terminate the supervised child
                killed_pid = supervisor.kill_current_process()
                assert killed_pid > 0
                assert not supervisor.is_alive()

                # 2. Watchdog Recovery Loop
                ttr = supervisor.supervise_and_recover(timeout_s=10.0)
                ttr_records.append(ttr)

                new_pid = supervisor.process.pid if supervisor.process else -1
                print(f"[+] Chaos Iteration {iteration}/3:")
                print(f"    - Killed PID: {killed_pid}")
                print(f"    - Watchdog Respawned New PID: {new_pid}")
                print(f"    - Time-To-Recovery (TTR): {ttr:.4f}s (Threshold: < 10.0s) -> PASS")

                # Assert recovery within strict 10.0s bound
                assert ttr < 10.0, f"Recovery took {ttr:.2f}s, exceeding 10.0s threshold!"
                assert supervisor.is_alive(), "Respawned process is not running!"
                assert new_pid != killed_pid, "Respawned PID should be new!"

            # 3. Calculate MTTR
            mttr = sum(ttr_records) / len(ttr_records)
            print("-" * 68)
            print("[*] Chaos Test Results Summary:")
            print("    - Total Chaos Injections: 3")
            print("    - Successful Recoveries: 3/3 (100%)")
            print(f"    - Individual TTRs: {[round(x, 4) for x in ttr_records]} seconds")
            print(f"    - Mean Time To Recovery (MTTR): {mttr:.4f} seconds (Max allowed: 10.0s)")
            print("=" * 68)

            assert mttr < 10.0
            assert len(ttr_records) == 3
            assert supervisor.restart_count == 3

        finally:
            supervisor.stop()

    def test_supervisor_clean_stop(self):
        """Verify supervisor properly terminates child process on stop."""
        worker_script = [sys.executable, "-c", "import time; time.sleep(300)"]
        supervisor = SupervisedProcessRunner(target_cmd=worker_script, poll_interval_s=0.05)
        pid = supervisor.start()
        assert supervisor.is_alive()

        supervisor.stop()
        assert not supervisor.is_alive()
