"""
jarvis/proactive/pomodoro.py
============================
Pomodoro Focus Mode Timer for JARVIS.
Features:
  - Configurable focus/break cycles (default: 25-minute work, 5-minute break).
  - Notification suppression state machine (DND mode during focus cycles).
  - Vocal announcements on phase transitions:
      * Start: "Bắt đầu phiên tập trung 25 phút"
      * Work -> Break: "Đã hết 25 phút, Ngài hãy nghỉ ngơi 5 phút"
      * Break -> Work: "Thời gian nghỉ kết thúc. Bắt đầu phiên tập trung tiếp theo 25 phút."
      * Complete: "Đã hoàn thành toàn bộ chu kỳ tập trung. Chúc mừng Ngài."
  - Lifecycle: start(), pause(), resume(), stop(), get_status(), tick().
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.proactive.pomodoro")


class PomodoroState(str, Enum):
    IDLE = "IDLE"
    WORK = "WORK"
    BREAK = "BREAK"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


@dataclass
class PomodoroStatus:
    """Snapshot of current Pomodoro state."""
    state: PomodoroState
    current_cycle: int
    total_cycles: int
    work_minutes: float
    break_minutes: float
    time_remaining_seconds: float
    elapsed_seconds: float
    is_suppressing_notifications: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "current_cycle": self.current_cycle,
            "total_cycles": self.total_cycles,
            "work_minutes": self.work_minutes,
            "break_minutes": self.break_minutes,
            "time_remaining_seconds": max(0.0, round(self.time_remaining_seconds, 1)),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "is_suppressing_notifications": self.is_suppressing_notifications,
        }


class PomodoroTimer:
    """
    Pomodoro Focus Mode Manager with Notification Suppression.
    """

    def __init__(
        self,
        tts_callback: Callable[[str], None] | None = None,
        overlay_callback: Callable[[str, str], None] | None = None,
        check_interval_seconds: float = 0.5,
        default_work_minutes: float = 25.0,
        default_break_minutes: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self.tts_callback = tts_callback
        self.overlay_callback = overlay_callback
        self.check_interval_seconds = check_interval_seconds
        self.default_work_minutes = float(default_work_minutes)
        self.default_break_minutes = float(default_break_minutes)
        self.enabled = enabled

        self._state: PomodoroState = PomodoroState.IDLE
        self._previous_state_before_pause: PomodoroState = PomodoroState.WORK
        self._work_minutes: float = self.default_work_minutes
        self._break_minutes: float = self.default_break_minutes
        self._total_cycles: int = 1
        self._current_cycle: int = 1

        self._phase_start_time: float = 0.0
        self._phase_duration_seconds: float = 0.0
        self._paused_remaining_seconds: float = 0.0

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    # ──────────────────────────────────────────────────────────────────────────
    # State & Control API
    # ──────────────────────────────────────────────────────────────────────────

    def start(
        self,
        work_minutes: float | None = None,
        break_minutes: float | None = None,
        cycles: int = 1,
    ) -> str:
        """
        Starts or restarts a Pomodoro focus session.
        """
        if not self.enabled:
            return "Chế độ tập trung hiện đang bị vô hiệu hóa trong cấu hình."

        with self._lock:
            self._work_minutes = float(work_minutes) if work_minutes is not None else self.default_work_minutes
            self._break_minutes = float(break_minutes) if break_minutes is not None else self.default_break_minutes
            self._total_cycles = max(1, int(cycles))
            self._current_cycle = 1

            self._state = PomodoroState.WORK
            self._phase_duration_seconds = self._work_minutes * 60.0
            self._phase_start_time = time.time()
            self._paused_remaining_seconds = 0.0

            work_min_int = int(self._work_minutes) if self._work_minutes.is_integer() else self._work_minutes
            announcement = f"Bắt đầu phiên tập trung {work_min_int} phút"
            logger.info("Started Pomodoro: %s (cycles=%d)", announcement, self._total_cycles)

        self._dispatch_phase_change(
            title="🎯 Chế độ tập trung",
            message=announcement,
            vocal_phrase=announcement,
        )

        self._ensure_worker_running()
        return announcement

    def pause(self) -> bool:
        """
        Pauses current active Pomodoro session.
        """
        with self._lock:
            if self._state not in (PomodoroState.WORK, PomodoroState.BREAK):
                return False

            now = time.time()
            elapsed = now - self._phase_start_time
            self._paused_remaining_seconds = max(0.0, self._phase_duration_seconds - elapsed)
            self._previous_state_before_pause = self._state
            self._state = PomodoroState.PAUSED
            announcement = "Đã tạm dừng phiên tập trung."
            logger.info("Paused Pomodoro (remaining=%.1fs)", self._paused_remaining_seconds)

        self._dispatch_phase_change(
            title="⏸️ Tạm dừng tập trung",
            message=announcement,
            vocal_phrase=announcement,
        )
        return True

    def resume(self) -> bool:
        """
        Resumes a paused Pomodoro session.
        """
        with self._lock:
            if self._state != PomodoroState.PAUSED:
                return False

            self._state = self._previous_state_before_pause
            self._phase_duration_seconds = self._paused_remaining_seconds
            self._phase_start_time = time.time()
            self._paused_remaining_seconds = 0.0
            announcement = "Đã tiếp tục phiên tập trung."
            logger.info("Resumed Pomodoro into state %s (remaining=%.1fs)", self._state.value, self._phase_duration_seconds)

        self._dispatch_phase_change(
            title="▶️ Tiếp tục tập trung",
            message=announcement,
            vocal_phrase=announcement,
        )
        self._ensure_worker_running()
        return True

    def stop(self) -> bool:
        """
        Stops and resets Pomodoro timer back to IDLE.
        """
        with self._lock:
            if self._state == PomodoroState.IDLE:
                return False

            self._state = PomodoroState.IDLE
            self._paused_remaining_seconds = 0.0
            self._phase_duration_seconds = 0.0
            announcement = "Đã dừng phiên tập trung."
            logger.info("Stopped Pomodoro.")

        self._dispatch_phase_change(
            title="⏹️ Kết thúc tập trung",
            message=announcement,
            vocal_phrase=announcement,
        )
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Status & Suppression Queries
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """Returns True if Pomodoro timer is actively running in WORK or BREAK phase."""
        with self._lock:
            return self._state in (PomodoroState.WORK, PomodoroState.BREAK, PomodoroState.PAUSED)

    def is_suppressing_notifications(self) -> bool:
        """Returns True if currently in WORK phase where notifications should be suppressed."""
        with self._lock:
            return self._state == PomodoroState.WORK

    def should_suppress_notification(self, is_critical: bool = False) -> bool:
        """Returns True if the incoming notification should be blocked."""
        if is_critical:
            return False
        return self.is_suppressing_notifications()

    def get_status(self) -> PomodoroStatus:
        """Returns the current Pomodoro status snapshot."""
        with self._lock:
            now = time.time()
            if self._state in (PomodoroState.WORK, PomodoroState.BREAK):
                elapsed = now - self._phase_start_time
                remaining = max(0.0, self._phase_duration_seconds - elapsed)
            elif self._state == PomodoroState.PAUSED:
                remaining = self._paused_remaining_seconds
                elapsed = self._phase_duration_seconds - remaining
            else:
                remaining = 0.0
                elapsed = 0.0

            return PomodoroStatus(
                state=self._state,
                current_cycle=self._current_cycle,
                total_cycles=self._total_cycles,
                work_minutes=self._work_minutes,
                break_minutes=self._break_minutes,
                time_remaining_seconds=remaining,
                elapsed_seconds=elapsed,
                is_suppressing_notifications=self.is_suppressing_notifications(),
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Ticking & Phase Transitions
    # ──────────────────────────────────────────────────────────────────────────

    def tick(self, now: float | None = None) -> str | None:
        """
        Evaluates elapsed time and executes state transitions.
        Returns event string ('WORK_FINISHED', 'BREAK_FINISHED', 'COMPLETED') or None.
        """
        current_time = time.time() if now is None else float(now)
        event_fired: str | None = None
        announcement_title = ""
        announcement_msg = ""

        with self._lock:
            if self._state not in (PomodoroState.WORK, PomodoroState.BREAK):
                return None

            elapsed = current_time - self._phase_start_time
            if elapsed >= self._phase_duration_seconds:
                if self._state == PomodoroState.WORK:
                    # Transition from WORK -> BREAK
                    self._state = PomodoroState.BREAK
                    self._phase_duration_seconds = self._break_minutes * 60.0
                    self._phase_start_time = current_time

                    work_min_int = int(self._work_minutes) if self._work_minutes.is_integer() else self._work_minutes
                    break_min_int = int(self._break_minutes) if self._break_minutes.is_integer() else self._break_minutes
                    announcement_title = "☕ Giờ nghỉ ngơi"
                    announcement_msg = f"Đã hết {work_min_int} phút, Ngài hãy nghỉ ngơi {break_min_int} phút"
                    event_fired = "WORK_FINISHED"
                    logger.info("Pomodoro transitioned WORK -> BREAK: %s", announcement_msg)

                elif self._state == PomodoroState.BREAK:
                    if self._current_cycle < self._total_cycles:
                        # Transition from BREAK -> next WORK cycle
                        self._current_cycle += 1
                        self._state = PomodoroState.WORK
                        self._phase_duration_seconds = self._work_minutes * 60.0
                        self._phase_start_time = current_time

                        work_min_int = int(self._work_minutes) if self._work_minutes.is_integer() else self._work_minutes
                        announcement_title = "🎯 Phiên tập trung tiếp theo"
                        announcement_msg = f"Thời gian nghỉ kết thúc. Bắt đầu phiên tập trung tiếp theo {work_min_int} phút."
                        event_fired = "BREAK_FINISHED"
                        logger.info("Pomodoro transitioned BREAK -> WORK (Cycle %d/%d)", self._current_cycle, self._total_cycles)
                    else:
                        # All cycles completed
                        self._state = PomodoroState.COMPLETED
                        self._phase_duration_seconds = 0.0
                        announcement_title = "🎉 Hoàn thành tập trung"
                        announcement_msg = "Đã hoàn thành toàn bộ chu kỳ tập trung. Chúc mừng Ngài."
                        event_fired = "COMPLETED"
                        logger.info("Pomodoro COMPLETED all %d cycles.", self._total_cycles)

        if event_fired and announcement_msg:
            self._dispatch_phase_change(
                title=announcement_title,
                message=announcement_msg,
                vocal_phrase=announcement_msg,
            )

        return event_fired

    def _dispatch_phase_change(self, title: str, message: str, vocal_phrase: str) -> None:
        """Dispatches voice announcement and UI overlay update."""
        if self.tts_callback:
            try:
                self.tts_callback(vocal_phrase)
            except Exception as e:
                logger.error("Error dispatching Pomodoro TTS: %s", e)

        if self.overlay_callback:
            try:
                self.overlay_callback(title, message)
            except Exception as e:
                logger.error("Error dispatching Pomodoro overlay: %s", e)

    # ──────────────────────────────────────────────────────────────────────────
    # Background Thread Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def _ensure_worker_running(self) -> None:
        """Ensures background ticking thread is alive."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name="PomodoroTimerWorker",
                daemon=True,
            )
            self._worker_thread.start()

    def stop_worker(self) -> None:
        """Stops background ticking thread."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None

    def is_running(self) -> bool:
        """Checks if timer is actively running in WORK or BREAK phase."""
        with self._lock:
            return self._state in (PomodoroState.WORK, PomodoroState.BREAK)

    def _run_loop(self) -> None:
        """Worker loop executing tick() every check_interval_seconds."""
        while not self._stop_event.is_set():
            try:
                event = self.tick()
                if self._state in (PomodoroState.IDLE, PomodoroState.COMPLETED) and not event:
                    # Timer is not active, can exit worker
                    break
            except Exception as e:
                logger.error("Unexpected error in Pomodoro tick loop: %s", e)
            self._stop_event.wait(timeout=self.check_interval_seconds)
