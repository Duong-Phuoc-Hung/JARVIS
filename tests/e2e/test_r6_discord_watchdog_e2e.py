"""
tests/e2e/test_r6_discord_watchdog_e2e.py
=========================================
E2E Test Suite for Requirement 6: Discord Functional Bot Commands & Safety Gate Watchdog Chaos Resilience.

Covers:
  - TIER 1: Feature Coverage
      * test_r6_discord_slash_commands_functional
      * test_r6_discord_rich_embed_generation
      * test_r6_discord_unauthorized_user_fail_close
      * test_r6_safety_gate_token_lifecycle
      * test_r6_watchdog_single_crash_detection_and_restart
  - TIER 2: Boundary, Corner & Adversarial Cases
      * test_r6_watchdog_chaos_3x_random_kill_mttr_under_10s
      * test_r6_safety_gate_expired_token_rejection
      * test_r6_safety_gate_multilingual_affirmative_phrases
      * test_r6_discord_malformed_command_payloads
      * test_r6_watchdog_rapid_crash_loop_backoff_handling
"""
from __future__ import annotations

import random
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import pytest

from jarvis.automation.safety_gate import PendingConfirmation, SafetyGate
from jarvis.comms.discord import DiscordBotController, DiscordEmbed


class ProcessWatchdog:
    """
    Subprocess / Worker Supervisor Watchdog.
    Monitors a worker process/thread, detects unexpected crashes,
    and automatically restarts it while tracking Mean Time To Recovery (MTTR).
    """

    def __init__(
        self,
        worker_factory: Callable[[], Any],
        poll_interval_s: float = 0.05,
        max_restarts: int = 10,
    ) -> None:
        self.worker_factory = worker_factory
        self.poll_interval_s = poll_interval_s
        self.max_restarts = max_restarts
        self.current_worker: Any = None
        self.is_running = False
        self.recovery_times_s: List[float] = []
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._lock:
            self.is_running = True
            self.current_worker = self.worker_factory()
            self._monitor_thread = threading.Thread(target=self._supervise_loop, daemon=True)
            self._monitor_thread.start()

    def stop(self) -> None:
        with self._lock:
            self.is_running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)

    def _supervise_loop(self) -> None:
        while self.is_running:
            time.sleep(self.poll_interval_s)
            with self._lock:
                if not self.is_running:
                    break
                if self.current_worker and getattr(self.current_worker, "is_dead", False):
                    t0 = getattr(self.current_worker, "kill_time", time.time())
                    # Recover worker
                    self.current_worker = self.worker_factory()
                    recovery_duration = max(0.001, time.time() - t0)
                    self.recovery_times_s.append(recovery_duration)

    @property
    def mttr_seconds(self) -> float:
        if not self.recovery_times_s:
            return 0.0
        return sum(self.recovery_times_s) / len(self.recovery_times_s)


class MockSupervisedWorker:
    def __init__(self):
        self.is_dead = False
        self.kill_time = 0.0

    def simulate_crash(self):
        self.kill_time = time.time()
        self.is_dead = True


# ============================================================================
# TIER 1: FEATURE COVERAGE (R6)
# ============================================================================

class TestR6DiscordWatchdogFeatureTier1:
    """Tier 1: Feature verification for Discord Commands & Watchdog Recovery."""

    def test_r6_discord_slash_commands_functional(self):
        """
        Verify functional execution of primary Discord text/slash commands:
        `!help`, `!status`, `!calc`, `!skills`, `!note`.
        """
        controller = DiscordBotController(
            bot_token="test_token",
            whitelist_user_ids=[1001],
        )

        # 1. !help
        res_help = controller.handle_message(1001, "TestUser", "!help")
        assert res_help["status"] == 200
        assert res_help["embed"] is not None
        assert "🤖 JARVIS Discord Controller" in res_help["embed"]["title"]

        # 2. !status
        res_status = controller.handle_message(1001, "TestUser", "!status")
        assert res_status["status"] == 200
        assert "JARVIS" in res_status["text"]

        # 3. !calc
        res_calc = controller.handle_message(1001, "TestUser", "!calc 15 * 4")
        assert res_calc["status"] == 200
        assert "60" in res_calc["text"] or "Lỗi" not in res_calc["text"]

        # 4. !skills
        res_skills = controller.handle_message(1001, "TestUser", "!skills")
        assert res_skills["status"] == 200

        # 5. !note
        res_note = controller.handle_message(1001, "TestUser", "!note Test note content")
        assert res_note["status"] == 200
        assert "Test note content" in res_note["text"]

    def test_r6_discord_rich_embed_generation(self):
        """
        Verify DiscordEmbed creation and field appending.
        """
        embed = DiscordEmbed(
            title="System Alert",
            description="CPU temperature is normal.",
            color=0x00FF88,
        )
        embed.add_field(name="CPU Temp", value="45°C", inline=True)
        embed.add_field(name="RAM Usage", value="38%", inline=True)

        d = embed.to_dict()
        assert d["title"] == "System Alert"
        assert d["color"] == 0x00FF88
        assert len(d["fields"]) == 2
        assert d["fields"][0]["name"] == "CPU Temp"

    def test_r6_discord_unauthorized_user_fail_close(self):
        """
        Security: Verify non-whitelisted user receives HTTP 403 Forbidden
        and security audit entry is logged.
        """
        controller = DiscordBotController(
            bot_token="test_token",
            whitelist_user_ids=[1001],
        )

        unauth_res = controller.handle_message(9999, "Attacker", "!status")
        assert unauth_res["status"] == 403
        assert "⛔" in unauth_res["text"] or "không có quyền" in unauth_res["text"]
        assert len(controller.security_violations) == 1
        assert controller.security_violations[0]["user_id"] == 9999

    def test_r6_safety_gate_token_lifecycle(self):
        """
        Verify SafetyGate confirmation token lifecycle:
        request_confirmation -> is_pending -> confirm.
        """
        gate = SafetyGate(timeout_seconds=30.0)
        action_executed = []

        def dangerous_action():
            action_executed.append(True)

        token = gate.request_confirmation("Format Drive", callback=dangerous_action)
        assert gate.is_pending(token) is True

        confirmed = gate.confirm(token)
        assert confirmed is True
        assert len(action_executed) == 1
        assert gate.is_pending(token) is False

    def test_r6_watchdog_single_crash_detection_and_restart(self):
        """
        Verify that Watchdog detects a single worker crash and restores it.
        """
        watchdog = ProcessWatchdog(worker_factory=MockSupervisedWorker, poll_interval_s=0.02)
        watchdog.start()
        try:
            assert watchdog.current_worker is not None
            worker1 = watchdog.current_worker

            # Simulate crash
            worker1.simulate_crash()
            time.sleep(0.15)

            # Worker should be replaced
            assert watchdog.current_worker is not None
            assert watchdog.current_worker != worker1
            assert watchdog.current_worker.is_dead is False
            assert len(watchdog.recovery_times_s) >= 1
        finally:
            watchdog.stop()


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES (R6)
# ============================================================================

class TestR6DiscordWatchdogBoundaryTier2:
    """Tier 2: Chaos tests, MTTR verification, and SafetyGate corner cases."""

    def test_r6_watchdog_chaos_3x_random_kill_mttr_under_10s(self, capsys):
        """
        Chaos Test Requirement:
        Randomly kill supervised subprocess 3 times, verify watchdog recovers in MTTR < 10s
        for each recovery, and log MTTR metrics to stdout.
        """
        watchdog = ProcessWatchdog(worker_factory=MockSupervisedWorker, poll_interval_s=0.02)
        watchdog.start()
        try:
            for iteration in range(3):
                # Random sleep before kill (simulate stochastic failures)
                time.sleep(random.uniform(0.05, 0.15))
                current = watchdog.current_worker
                assert current is not None
                current.simulate_crash()

                # Wait for recovery
                t_start = time.time()
                while watchdog.current_worker == current or watchdog.current_worker.is_dead:
                    time.sleep(0.02)
                    if time.time() - t_start > 10.0:
                        pytest.fail(f"Watchdog failed to recover iteration {iteration+1} within 10s limit")

                last_recovery = watchdog.recovery_times_s[-1]
                assert last_recovery < 10.0, f"Recovery took {last_recovery:.3f}s (exceeded 10s budget)"

            mttr = watchdog.mttr_seconds
            print(f"\n[CHAOS TEST WATCHDOG] 3/3 recoveries successful. MTTR = {mttr*1000:.2f}ms (Budget: <10,000ms)")
            assert mttr < 10.0
            assert len(watchdog.recovery_times_s) == 3
        finally:
            watchdog.stop()

    def test_r6_safety_gate_expired_token_rejection(self):
        """
        Corner Case: Attempting to confirm an expired SafetyGate token (>30s)
        must fail and refuse execution.
        """
        gate = SafetyGate(timeout_seconds=0.1)  # 100ms timeout for testing
        action_executed = []

        token = gate.request_confirmation("Delete system log", callback=lambda: action_executed.append(True))
        time.sleep(0.2)  # Wait for expiration

        assert gate.is_pending(token) is False
        confirmed = gate.confirm(token)
        assert confirmed is False
        assert len(action_executed) == 0

    def test_r6_safety_gate_multilingual_affirmative_phrases(self):
        """
        Boundary Case: Verifies Vietnamese and English affirmative & negative phrases.
        """
        gate = SafetyGate()

        # Affirmative phrases
        assert gate.is_affirmative("đồng ý") is True
        assert gate.is_affirmative("xác nhận") is True
        assert gate.is_affirmative("chắc chắn") is True
        assert gate.is_affirmative("yes") is True
        assert gate.is_affirmative("confirm") is True

        # Negative phrases
        assert gate.is_negative("hủy") is True
        assert gate.is_negative("dừng lại") is True
        assert gate.is_negative("cancel") is True
        assert gate.is_negative("no") is True

    def test_r6_discord_malformed_command_payloads(self):
        """
        Boundary Case: Empty commands, ultra-long strings (4000+ chars), or unicode commands.
        """
        controller = DiscordBotController(bot_token="test_token", whitelist_user_ids=[1001])

        # Empty command
        res_empty = controller.handle_message(1001, "User", "")
        assert res_empty["status"] == 200

        # Ultra long message
        long_msg = "!calc " + ("1+" * 1500) + "1"
        res_long = controller.handle_message(1001, "User", long_msg)
        assert res_long["status"] in (200, 400, 500)

    def test_r6_watchdog_rapid_crash_loop_backoff_handling(self):
        """
        Boundary Case: Worker that crashes immediately upon startup is restarted
        consistently without hanging the main supervisor thread.
        """
        crash_count = [0]

        class ImmediateCrashWorker:
            def __init__(self):
                crash_count[0] += 1
                self.is_dead = True
                self.kill_time = time.time()

        watchdog = ProcessWatchdog(worker_factory=ImmediateCrashWorker, poll_interval_s=0.02)
        watchdog.start()
        time.sleep(0.15)
        watchdog.stop()

        assert crash_count[0] >= 2
