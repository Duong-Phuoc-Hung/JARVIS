"""
jarvis/proactive/reminders.py
=============================
Smart Reminder Scheduler for JARVIS.
Features:
  - Thread-safe priority queue of scheduled reminders.
  - Delay-based scheduling (seconds/minutes/hours) and absolute timestamps.
  - Cancellation and status querying.
  - Automated TTS vocalization and UI Overlay notification upon expiry.
  - Regex-based Vietnamese/English relative time parsing utility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import logging
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.proactive.reminders")


@dataclass(order=True)
class ScheduledReminder:
    """Represents a scheduled reminder in the priority queue."""
    trigger_timestamp: float
    reminder_id: str = field(compare=False)
    text: str = field(compare=False)
    created_timestamp: float = field(compare=False, default_factory=time.time)
    callback: Optional[Callable[[ScheduledReminder], None]] = field(compare=False, default=None)
    completed: bool = field(compare=False, default=False)
    cancelled: bool = field(compare=False, default=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert reminder to dictionary."""
        return {
            "reminder_id": self.reminder_id,
            "text": self.text,
            "trigger_timestamp": self.trigger_timestamp,
            "created_timestamp": self.created_timestamp,
            "completed": self.completed,
            "cancelled": self.cancelled,
            "time_remaining_s": max(0.0, self.trigger_timestamp - time.time()),
        }


class ReminderScheduler:
    """
    Thread-safe Priority Queue Reminder Scheduler.
    """

    def __init__(
        self,
        tts_callback: Optional[Callable[[str], None]] = None,
        overlay_callback: Optional[Callable[[str, str], None]] = None,
        check_interval_seconds: float = 0.5,
        enabled: bool = True,
    ) -> None:
        self.tts_callback = tts_callback
        self.overlay_callback = overlay_callback
        self.check_interval_seconds = check_interval_seconds
        self.enabled = enabled

        self._queue: List[ScheduledReminder] = []
        self._reminders_by_id: Dict[str, ScheduledReminder] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    # ──────────────────────────────────────────────────────────────────────────
    # Core Scheduling API
    # ──────────────────────────────────────────────────────────────────────────

    def add_reminder(
        self,
        text: str,
        delay_seconds: float,
        callback: Optional[Callable[[ScheduledReminder], None]] = None,
    ) -> str:
        """
        Schedules a reminder after delay_seconds from current time.
        Returns a unique reminder_id.
        """
        now = time.time()
        trigger_time = now + max(0.0, float(delay_seconds))
        return self.add_scheduled_reminder(text=text, trigger_timestamp=trigger_time, callback=callback)

    def add_scheduled_reminder(
        self,
        text: str,
        trigger_timestamp: float,
        callback: Optional[Callable[[ScheduledReminder], None]] = None,
    ) -> str:
        """
        Schedules a reminder at an absolute unix timestamp.
        """
        reminder_id = str(uuid.uuid4())[:8]
        reminder = ScheduledReminder(
            trigger_timestamp=float(trigger_timestamp),
            reminder_id=reminder_id,
            text=text.strip(),
            created_timestamp=time.time(),
            callback=callback,
        )

        with self._lock:
            heapq.heappush(self._queue, reminder)
            self._reminders_by_id[reminder_id] = reminder

        logger.info(
            "Scheduled reminder [%s] '%s' in %.1fs (at %.0f)",
            reminder_id,
            reminder.text,
            max(0.0, reminder.trigger_timestamp - time.time()),
            reminder.trigger_timestamp,
        )
        return reminder_id

    def cancel_reminder(self, reminder_id: str) -> bool:
        """
        Cancels a pending reminder.
        Returns True if cancelled, False if not found or already completed/cancelled.
        """
        with self._lock:
            reminder = self._reminders_by_id.get(reminder_id)
            if reminder is None or reminder.completed or reminder.cancelled:
                return False
            reminder.cancelled = True
            logger.info("Cancelled reminder [%s] '%s'", reminder_id, reminder.text)
            return True

    def get_reminder(self, reminder_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve reminder details by ID."""
        with self._lock:
            reminder = self._reminders_by_id.get(reminder_id)
            if reminder:
                return reminder.to_dict()
            return None

    def get_pending_reminders(self) -> List[Dict[str, Any]]:
        """Returns list of pending (not cancelled, not completed) reminders ordered by trigger time."""
        with self._lock:
            pending = [
                r.to_dict()
                for r in sorted(self._queue, key=lambda x: x.trigger_timestamp)
                if not r.cancelled and not r.completed
            ]
            return pending

    def clear(self) -> None:
        """Clears all reminders."""
        with self._lock:
            self._queue.clear()
            self._reminders_by_id.clear()

    # ──────────────────────────────────────────────────────────────────────────
    # Execution & Ticking
    # ──────────────────────────────────────────────────────────────────────────

    def tick(self, now: Optional[float] = None) -> List[ScheduledReminder]:
        """
        Evaluates queue against current time `now`, executes due reminders, and pops expired items.
        Returns list of executed reminders.
        """
        if not self.enabled:
            return []

        current_time = time.time() if now is None else float(now)
        due_reminders: List[ScheduledReminder] = []

        with self._lock:
            while self._queue:
                earliest = self._queue[0]
                if earliest.cancelled:
                    heapq.heappop(self._queue)
                    continue

                if earliest.trigger_timestamp <= current_time:
                    reminder = heapq.heappop(self._queue)
                    if not reminder.cancelled and not reminder.completed:
                        reminder.completed = True
                        due_reminders.append(reminder)
                else:
                    break

        for reminder in due_reminders:
            self._dispatch_reminder(reminder)

        return due_reminders

    def _dispatch_reminder(self, reminder: ScheduledReminder) -> None:
        """Fires callbacks, TTS vocalization, and Overlay notifications for an expired reminder."""
        logger.info("Triggering reminder [%s]: %s", reminder.reminder_id, reminder.text)

        # 1. Custom callback
        if reminder.callback:
            try:
                reminder.callback(reminder)
            except Exception as e:
                logger.error("Error in reminder callback for [%s]: %s", reminder.reminder_id, e)

        # 2. Vocalize via TTS
        vocal_phrase = f"Thưa Ngài, đây là lời nhắc: {reminder.text}"
        if self.tts_callback:
            try:
                self.tts_callback(vocal_phrase)
            except Exception as e:
                logger.error("Error dispatching reminder TTS: %s", e)

        # 3. Notify Overlay
        if self.overlay_callback:
            try:
                self.overlay_callback("⏰ Lời nhắc", reminder.text)
            except Exception as e:
                logger.error("Error dispatching reminder overlay: %s", e)

    # ──────────────────────────────────────────────────────────────────────────
    # Background Thread Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts the background worker thread."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name="ReminderSchedulerWorker",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("ReminderScheduler started.")

    def stop(self) -> None:
        """Stops the background worker thread."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        logger.info("ReminderScheduler stopped.")

    def is_running(self) -> bool:
        """Checks if the background worker thread is running."""
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _run_loop(self) -> None:
        """Background loop ticking every check_interval_seconds."""
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                logger.error("Unexpected error in ReminderScheduler tick: %s", e)
            self._stop_event.wait(timeout=self.check_interval_seconds)

    # ──────────────────────────────────────────────────────────────────────────
    # Natural Language Helper Utility
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def parse_relative_time(command: str) -> Optional[Tuple[str, float]]:
        """
        Parses natural language relative time requests.
        Examples:
          - 'nhắc tôi sau 5 phút kiểm tra email' -> ('kiểm tra email', 300.0)
          - 'nhắc tôi sau 30 giây' -> ('lời nhắc', 30.0)
          - 'nhắc sau 2 giờ họp team' -> ('họp team', 7200.0)
          - 'remind me in 10 minutes to take medicine' -> ('take medicine', 600.0)
        Returns (reminder_text, delay_seconds) or None.
        """
        cmd = command.strip()

        # Vietnamese pattern: (nhắc|nhắc nhở|nhắc tôi) sau (\d+) (giây|phút|tiếng|giờ) (?:làm gì|rằng|để)?\s*(.*)
        vi_pattern = re.compile(
            r"(?:nhắc|nhắc nhở|nhắc tôi)\s+sau\s+(\d+(?:\.\d+)?)\s*(giây|phút|tiếng|giờ)\b\s*(?:để|rằng|:)?\s*(.*)",
            re.IGNORECASE,
        )
        m = vi_pattern.search(cmd)
        if m:
            val = float(m.group(1))
            unit = m.group(2).lower()
            text = m.group(3).strip() or "lời nhắc đã hẹn"
            multiplier = 1.0
            if "phút" in unit:
                multiplier = 60.0
            elif "tiếng" in unit or "giờ" in unit:
                multiplier = 3600.0
            return (text, val * multiplier)

        # English pattern: remind (?:me)? in (\d+) (sec|seconds|min|mins|minutes|hour|hours) (?:to)?\s*(.*)
        en_pattern = re.compile(
            r"remind\s+(?:me\s+)?in\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b\s*(?:to|that|:)?\s*(.*)",
            re.IGNORECASE,
        )
        m_en = en_pattern.search(cmd)
        if m_en:
            val = float(m_en.group(1))
            unit = m_en.group(2).lower()
            text = m_en.group(3).strip() or "scheduled reminder"
            multiplier = 1.0
            if unit.startswith("min"):
                multiplier = 60.0
            elif unit.startswith("hour") or unit.startswith("hr"):
                multiplier = 3600.0
            return (text, val * multiplier)

        return None
