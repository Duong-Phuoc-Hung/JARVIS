"""
jarvis/proactive/briefing_scheduler.py
======================================
Daily Morning Briefing Scheduler for JARVIS.
Features:
  - Configurable scheduled morning briefing timer (default: 8:00 AM / "08:00").
  - Integrates with WebIntelligenceHub.generate_morning_briefing().
  - Thread-safe check loop with per-day single execution guarantee.
  - On-demand briefing trigger (trigger_now).
  - Automated TTS speech synthesis and UI Overlay notification.
"""
from __future__ import annotations

import datetime
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("jarvis.proactive.briefing_scheduler")


class DailyBriefingScheduler:
    """
    Schedules and triggers the automated 8:00 AM daily briefing.
    """

    def __init__(
        self,
        web_hub: Optional[Any] = None,
        briefing_provider: Optional[Callable[..., Dict[str, Any]]] = None,
        tts_callback: Optional[Callable[[str], None]] = None,
        overlay_callback: Optional[Callable[[str, str], None]] = None,
        target_time: str = "08:00",
        check_interval_seconds: float = 10.0,
        city: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self.web_hub = web_hub
        self.briefing_provider = briefing_provider
        self.tts_callback = tts_callback
        self.overlay_callback = overlay_callback
        self.check_interval_seconds = check_interval_seconds
        self.city = city
        self.enabled = enabled

        self._target_hour, self._target_minute = self._parse_time_str(target_time)
        self._last_briefing_date: Optional[str] = None

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    @staticmethod
    def _parse_time_str(time_str: str) -> tuple[int, int]:
        """Parses 'HH:MM' string into (hour, minute)."""
        try:
            parts = time_str.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
        except Exception:
            pass
        return 8, 0

    def set_target_time(self, time_str: str) -> None:
        """Updates target scheduled time (e.g. '07:30')."""
        with self._lock:
            self._target_hour, self._target_minute = self._parse_time_str(time_str)
            logger.info("Updated daily briefing scheduled time to %02d:%02d", self._target_hour, self._target_minute)

    # ──────────────────────────────────────────────────────────────────────────
    # Trigger Logic & Schedule Checking
    # ──────────────────────────────────────────────────────────────────────────

    def check_schedule(self, current_dt: Optional[datetime.datetime] = None) -> bool:
        """
        Evaluates whether current datetime has reached target time for today and has not run yet.
        """
        if not self.enabled:
            return False

        now = current_dt or datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        with self._lock:
            if self._last_briefing_date == today_str:
                return False

            # Check if current time has reached target hour and minute
            target_today = now.replace(
                hour=self._target_hour,
                minute=self._target_minute,
                second=0,
                microsecond=0,
            )

            if now >= target_today:
                return True

        return False

    def tick(self, current_dt: Optional[datetime.datetime] = None) -> Optional[Dict[str, Any]]:
        """
        Periodic scheduler tick. If due, executes the morning briefing.
        Returns briefing dictionary if triggered, or None.
        """
        if self.check_schedule(current_dt):
            now = current_dt or datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            with self._lock:
                self._last_briefing_date = today_str
            logger.info("Daily briefing schedule triggered for date %s at %s", today_str, now.strftime("%H:%M:%S"))
            return self.trigger_now(city=self.city)
        return None

    def trigger_now(self, city: Optional[str] = None) -> Dict[str, Any]:
        """
        Immediately generates and vocalizes morning briefing.
        """
        target_city = city or self.city
        briefing_data: Dict[str, Any] = {}

        # 1. Fetch briefing from provider or web_hub
        try:
            if self.briefing_provider:
                briefing_data = self.briefing_provider(city=target_city) if target_city else self.briefing_provider()
            elif self.web_hub and hasattr(self.web_hub, "generate_morning_briefing"):
                briefing_data = self.web_hub.generate_morning_briefing(city=target_city)
            else:
                # Default fallback summary
                now = datetime.datetime.now()
                briefing_data = {
                    "spoken_summary": f"Chào buổi sáng thưa Ngài. Bây giờ là {now.hour} giờ {now.minute} phút. Hệ thống JARVIS đang hoạt động bình thường.",
                    "overlay_bullets": [
                        f"⏰ Giờ hiện tại: {now.strftime('%H:%M:%S')}",
                        "✅ Hệ thống JARVIS trực tuyến",
                    ],
                    "timestamp": now.isoformat(),
                }
        except Exception as e:
            logger.error("Error generating morning briefing: %s", e)
            briefing_data = {
                "spoken_summary": "Chào buổi sáng thưa Ngài. Tôi gặp sự cố khi tải dữ liệu thời tiết và tin tức, nhưng hệ thống vẫn sẵn sàng phục vụ Ngài.",
                "overlay_bullets": ["⚠️ Không thể tải dữ liệu mạng"],
                "error": str(e),
            }

        # 2. Vocalize via TTS
        spoken_summary = briefing_data.get("spoken_summary", "")
        if spoken_summary and self.tts_callback:
            try:
                self.tts_callback(spoken_summary)
            except Exception as e:
                logger.error("Error vocalizing briefing via TTS: %s", e)

        # 3. Notify Overlay UI
        if self.overlay_callback:
            try:
                bullets = briefing_data.get("overlay_bullets", [])
                overlay_text = "\n".join(bullets) if bullets else spoken_summary
                self.overlay_callback("🌅 Bản tin buổi sáng", overlay_text)
            except Exception as e:
                logger.error("Error notifying briefing on overlay: %s", e)

        return briefing_data

    def reset_daily_flag(self) -> None:
        """Resets the daily execution tracker (allowing re-triggering today)."""
        with self._lock:
            self._last_briefing_date = None

    # ──────────────────────────────────────────────────────────────────────────
    # Background Thread Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts background briefing scheduler loop."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name="DailyBriefingSchedulerWorker",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info("DailyBriefingScheduler started (target time: %02d:%02d).", self._target_hour, self._target_minute)

    def stop(self) -> None:
        """Stops background briefing scheduler loop."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        logger.info("DailyBriefingScheduler stopped.")

    def is_running(self) -> bool:
        """Checks if scheduler background loop is alive."""
        return bool(self._worker_thread and self._worker_thread.is_alive())

    def _run_loop(self) -> None:
        """Worker loop executing tick() periodically."""
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                logger.error("Unexpected error in DailyBriefingScheduler tick: %s", e)
            self._stop_event.wait(timeout=self.check_interval_seconds)
