"""
jarvis/proactive/inactivity.py
==============================
Inactivity Monitor & Proactive Check-in for JARVIS.
Features:
  - Tracks user activity timestamps across interactions (voice, gestures, UI).
  - Automatically triggers polite check-in greeting when idle > 2 hours (7200s):
      "Thưa Ngài, Ngài có cần hỗ trợ gì không?"
  - Cooldown period after greeting (default: 1 hour / 3600s) to prevent spam.
  - Automated TTS vocalization and UI Overlay notification.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger("jarvis.proactive.inactivity")


class InactivityMonitor:
    """
    Monitors user interaction activity and triggers proactive check-in greetings.
    """

    def __init__(
        self,
        tts_callback: Callable[[str], None] | None = None,
        overlay_callback: Callable[[str, str], None] | None = None,
        inactivity_threshold_seconds: float = 7200.0,  # 2 hours
        cooldown_seconds: float = 3600.0,              # 1 hour
        greeting_phrase: str = "Thưa Ngài, Ngài có cần hỗ trợ gì không?",
        check_interval_seconds: float = 10.0,
        enabled: bool = True,
    ) -> None:
        self.tts_callback = tts_callback
        self.overlay_callback = overlay_callback
        self.inactivity_threshold_seconds = float(inactivity_threshold_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self.greeting_phrase = greeting_phrase
        self.check_interval_seconds = check_interval_seconds
        self.enabled = enabled

        self._lock = threading.RLock()
        self._last_activity_time: float = time.time()
        self._last_greeting_time: float = 0.0

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    @property
    def last_activity_time(self) -> float:
        with self._lock:
            return self._last_activity_time

    # ──────────────────────────────────────────────────────────────────────────
    # Activity Tracking API
    # ──────────────────────────────────────────────────────────────────────────

    def record_activity(self, now: float | None = None) -> None:
        """
        Call this whenever user interacts with JARVIS (voice command, gesture, UI click).
        Resets inactivity timer.
        """
        current_time = time.time() if now is None else float(now)
        with self._lock:
            self._last_activity_time = current_time
            logger.debug("Recorded user activity at timestamp %.1f", current_time)

    def get_idle_seconds(self, now: float | None = None) -> float:
        """Returns elapsed seconds since last recorded user activity."""
        current_time = time.time() if now is None else float(now)
        with self._lock:
            return max(0.0, current_time - self._last_activity_time)

    def reset(self) -> None:
        """Resets both activity timer and greeting cooldown."""
        with self._lock:
            self._last_activity_time = time.time()
            self._last_greeting_time = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # Check & Ticking Logic
    # ──────────────────────────────────────────────────────────────────────────

    def check_inactivity(self, now: float | None = None) -> bool:
        """
        Checks if user inactivity has exceeded threshold and cooldown has passed.
        If triggered, fires vocal greeting and overlay notification.
        Returns True if greeting was fired, False otherwise.
        """
        if not self.enabled:
            return False

        current_time = time.time() if now is None else float(now)

        with self._lock:
            idle_seconds = current_time - self._last_activity_time
            time_since_last_greeting = current_time - self._last_greeting_time

            # Must exceed inactivity threshold AND cooldown period
            if idle_seconds >= self.inactivity_threshold_seconds and time_since_last_greeting >= self.cooldown_seconds:
                self._last_greeting_time = current_time
                logger.info(
                    "Inactivity greeting triggered: idle for %.0fs (threshold=%.0fs)",
                    idle_seconds,
                    self.inactivity_threshold_seconds,
                )
                trigger = True
            else:
                trigger = False

        if trigger:
            self._dispatch_greeting()
            return True

        return False

    def tick(self, now: float | None = None) -> bool:
        """Tick alias for check_inactivity."""
        return self.check_inactivity(now=now)

    def _dispatch_greeting(self) -> None:
        """Dispatches polite check-in via TTS and Overlay."""
        if self.tts_callback:
            try:
                self.tts_callback(self.greeting_phrase)
            except Exception as e:
                logger.error("Error dispatching inactivity greeting TTS: %s", e)

        if self.overlay_callback:
            try:
                self.overlay_callback("👋 Trợ lý JARVIS", self.greeting_phrase)
            except Exception as e:
                logger.error("Error dispatching inactivity overlay: %s", e)

    # ──────────────────────────────────────────────────────────────────────────
    # Background Thread Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts background inactivity watchdog loop."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name="InactivityMonitorWorker",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("InactivityMonitor started (threshold=%.0fs, cooldown=%.0fs).", self.inactivity_threshold_seconds, self.cooldown_seconds)

    def stop(self) -> None:
        """Stops background inactivity watchdog loop."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        logger.info("InactivityMonitor stopped.")

    def is_running(self) -> bool:
        """Checks if background loop is alive."""
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _run_loop(self) -> None:
        """Worker loop executing check_inactivity() periodically."""
        while not self._stop_event.is_set():
            try:
                self.check_inactivity()
            except Exception as e:
                logger.error("Unexpected error in InactivityMonitor check: %s", e)
            self._stop_event.wait(timeout=self.check_interval_seconds)
