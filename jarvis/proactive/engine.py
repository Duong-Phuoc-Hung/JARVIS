"""
jarvis/proactive/engine.py
==========================
Master Proactive Intelligence Engine for JARVIS (R6).
Coordinates:
  - ReminderScheduler: Timed and priority queue smart reminders
  - SystemHealthMonitor: Realtime CPU/RAM/Disk/Temp/Battery threshold watchdog
  - PomodoroTimer: Focus mode and notification suppression state machine
  - DailyBriefingScheduler: Configurable 8:00 AM daily intelligence briefing
  - InactivityMonitor: 2-hour idle detection and polite check-in prompter
"""
from __future__ import annotations

import datetime
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jarvis.proactive.briefing_scheduler import DailyBriefingScheduler
from jarvis.proactive.health_monitor import SystemHealthMonitor
from jarvis.proactive.inactivity import InactivityMonitor
from jarvis.proactive.pomodoro import PomodoroTimer
from jarvis.proactive.reminders import ReminderScheduler, ScheduledReminder

logger = logging.getLogger("jarvis.proactive.engine")


@dataclass
class ProactiveConfig:
    """Configuration container for Proactive Engine and all sub-modules."""
    enabled: bool = True
    reminders_enabled: bool = True
    reminders_interval_s: float = 0.5

    health_monitor_enabled: bool = True
    health_interval_s: float = 30.0      # Check every 30s (was 5s — way too frequent)
    cpu_threshold: float = 92.0          # Raised from 90.0
    ram_threshold: float = 92.0          # Raised from 85.0
    disk_min_free_gb: float = 5.0        # Lowered from 10.0
    temp_threshold_c: float = 92.0      # Raised from 85.0 — 85-90°C is normal for laptops
    battery_min_percent: float = 15.0   # Lowered from 20.0
    health_cooldown_s: float = 600.0    # 10 minutes (was 60s — too spammy)

    pomodoro_enabled: bool = True
    pomodoro_interval_s: float = 0.5
    pomodoro_work_m: float = 25.0
    pomodoro_break_m: float = 5.0

    daily_briefing_enabled: bool = True
    daily_briefing_time: str = "08:00"
    daily_briefing_interval_s: float = 10.0
    daily_briefing_city: str | None = None

    inactivity_greeting_enabled: bool = True
    inactivity_timeout_s: float = 7200.0  # 2 hours
    inactivity_cooldown_s: float = 3600.0 # 1 hour
    inactivity_phrase: str = "Thưa Ngài, Ngài có cần hỗ trợ gì không?"
    inactivity_interval_s: float = 10.0

    @classmethod
    def from_dict(cls, cfg: dict[str, Any] | None) -> ProactiveConfig:
        """Parses flat or nested YAML/JSON config dictionary."""
        if not cfg:
            return cls()

        # Handle top-level proactive block if present
        p_cfg = cfg.get("proactive", cfg) if isinstance(cfg, dict) and "proactive" in cfg else cfg

        # Extract nested blocks
        reminders_cfg = p_cfg.get("reminders", {})
        health_cfg = p_cfg.get("health_monitor", {})
        pomodoro_cfg = p_cfg.get("pomodoro", p_cfg.get("focus_mode", {}))
        briefing_cfg = p_cfg.get("daily_briefing", {})
        inactivity_cfg = p_cfg.get("inactivity_greeting", p_cfg.get("inactivity", {}))

        return cls(
            enabled=bool(p_cfg.get("enabled", True)),
            # Reminders
            reminders_enabled=bool(reminders_cfg.get("enabled", p_cfg.get("reminders_enabled", True))),
            reminders_interval_s=float(reminders_cfg.get("check_interval_s", p_cfg.get("reminders_interval_s", 0.5))),
            # Health Monitor
            health_monitor_enabled=bool(health_cfg.get("enabled", p_cfg.get("health_monitor_enabled", True))),
            health_interval_s=float(health_cfg.get("check_interval_s", p_cfg.get("health_interval_s", 5.0))),
            cpu_threshold=float(health_cfg.get("cpu_threshold", p_cfg.get("cpu_threshold", 90.0))),
            ram_threshold=float(health_cfg.get("ram_threshold", p_cfg.get("ram_threshold", 85.0))),
            disk_min_free_gb=float(health_cfg.get("disk_min_free_gb", p_cfg.get("disk_min_free_gb", 10.0))),
            temp_threshold_c=float(health_cfg.get("temp_threshold_c", p_cfg.get("temp_threshold_c", 85.0))),
            battery_min_percent=float(health_cfg.get("battery_min_percent", p_cfg.get("battery_min_percent", 20.0))),
            health_cooldown_s=float(health_cfg.get("cooldown_s", p_cfg.get("health_cooldown_s", 60.0))),
            # Pomodoro
            pomodoro_enabled=bool(pomodoro_cfg.get("enabled", p_cfg.get("pomodoro_enabled", True))),
            pomodoro_interval_s=float(pomodoro_cfg.get("check_interval_s", p_cfg.get("pomodoro_interval_s", 0.5))),
            pomodoro_work_m=float(pomodoro_cfg.get("work_duration_m", p_cfg.get("pomodoro_work_m", 25.0))),
            pomodoro_break_m=float(pomodoro_cfg.get("break_duration_m", p_cfg.get("pomodoro_break_m", 5.0))),
            # Briefing
            daily_briefing_enabled=bool(briefing_cfg.get("enabled", p_cfg.get("daily_briefing_enabled", True))),
            daily_briefing_time=str(briefing_cfg.get("time", p_cfg.get("daily_briefing_time", "08:00"))),
            daily_briefing_interval_s=float(briefing_cfg.get("check_interval_s", p_cfg.get("daily_briefing_interval_s", 10.0))),
            daily_briefing_city=briefing_cfg.get("city", p_cfg.get("daily_briefing_city", None)),
            # Inactivity
            inactivity_greeting_enabled=bool(inactivity_cfg.get("enabled", p_cfg.get("inactivity_greeting_enabled", True))),
            inactivity_timeout_s=float(inactivity_cfg.get("timeout_seconds", p_cfg.get("inactivity_timeout_s", 7200.0))),
            inactivity_cooldown_s=float(inactivity_cfg.get("cooldown_seconds", p_cfg.get("inactivity_cooldown_s", 3600.0))),
            inactivity_phrase=str(inactivity_cfg.get("phrase", p_cfg.get("inactivity_phrase", "Thưa Ngài, Ngài có cần hỗ trợ gì không?"))),
            inactivity_interval_s=float(inactivity_cfg.get("check_interval_s", p_cfg.get("inactivity_interval_s", 10.0))),
        )


class ProactiveEngine:
    """
    Master Coordinator for all Proactive Intelligence sub-engines.
    """

    def __init__(
        self,
        app_context: Any | None = None,
        config: dict[str, Any] | ProactiveConfig | None = None,
        tts_callback: Callable[[str], None] | None = None,
        overlay_callback: Callable[[str, str], None] | None = None,
        web_hub: Any | None = None,
        hardware_monitor: Any | None = None,
        telemetry_provider: Any | None = None,
    ) -> None:
        self.app_context = app_context
        self.raw_config = config or {}
        if isinstance(config, ProactiveConfig):
            self.config = config
        else:
            self.config = ProactiveConfig.from_dict(config)

        # Resolve TTS / Overlay callbacks from app_context if not passed explicitly
        self.tts_callback = tts_callback
        if self.tts_callback is None and app_context is not None and hasattr(app_context, "tts_manager"):
            self.tts_callback = lambda text: app_context.tts_manager.speak(text, wait=False)

        self.overlay_callback = overlay_callback
        if self.overlay_callback is None and app_context is not None and hasattr(app_context, "overlay"):
            self.overlay_callback = lambda title, body: app_context.overlay.show_response(title, body)

        # Web Hub & Hardware Monitor resolution
        self.web_hub = web_hub
        if self.web_hub is None and app_context is not None and hasattr(app_context, "web_hub"):
            self.web_hub = app_context.web_hub

        self.hardware_monitor = hardware_monitor
        if self.hardware_monitor is None and app_context is not None and hasattr(app_context, "hardware_monitor"):
            self.hardware_monitor = app_context.hardware_monitor

        self.telemetry_provider = telemetry_provider

        # ──────────────────────────────────────────────────────────────────────
        # Sub-Engines Initialization
        # ──────────────────────────────────────────────────────────────────────

        # 1. Reminders
        self.reminders = ReminderScheduler(
            tts_callback=self._handle_tts_dispatch,
            overlay_callback=self.overlay_callback,
            check_interval_seconds=self.config.reminders_interval_s,
            enabled=self.config.enabled and self.config.reminders_enabled,
        )

        # 2. Health Monitor
        self.health_monitor = SystemHealthMonitor(
            hardware_monitor=self.hardware_monitor,
            telemetry_provider=self.telemetry_provider,
            tts_callback=self._handle_tts_dispatch,
            overlay_callback=self.overlay_callback,
            check_interval_seconds=self.config.health_interval_s,
            cpu_threshold=self.config.cpu_threshold,
            ram_threshold=self.config.ram_threshold,
            disk_min_free_gb=self.config.disk_min_free_gb,
            temp_threshold_c=self.config.temp_threshold_c,
            battery_min_percent=self.config.battery_min_percent,
            cooldown_seconds=self.config.health_cooldown_s,
            enabled=self.config.enabled and self.config.health_monitor_enabled,
        )

        # 3. Pomodoro Focus Mode
        self.pomodoro = PomodoroTimer(
            tts_callback=self._handle_tts_dispatch,
            overlay_callback=self.overlay_callback,
            check_interval_seconds=self.config.pomodoro_interval_s,
            default_work_minutes=self.config.pomodoro_work_m,
            default_break_minutes=self.config.pomodoro_break_m,
            enabled=self.config.enabled and self.config.pomodoro_enabled,
        )

        # 4. Daily Briefing Scheduler
        self.briefing_scheduler = DailyBriefingScheduler(
            web_hub=self.web_hub,
            tts_callback=self._handle_tts_dispatch,
            overlay_callback=self.overlay_callback,
            target_time=self.config.daily_briefing_time,
            check_interval_seconds=self.config.daily_briefing_interval_s,
            city=self.config.daily_briefing_city,
            enabled=self.config.enabled and self.config.daily_briefing_enabled,
        )

        # 5. Inactivity Monitor
        self.inactivity = InactivityMonitor(
            tts_callback=self._handle_tts_dispatch,
            overlay_callback=self.overlay_callback,
            inactivity_threshold_seconds=self.config.inactivity_timeout_s,
            cooldown_seconds=self.config.inactivity_cooldown_s,
            greeting_phrase=self.config.inactivity_phrase,
            check_interval_seconds=self.config.inactivity_interval_s,
            enabled=self.config.enabled and self.config.inactivity_greeting_enabled,
        )

        self._running = False
        self._lock = threading.RLock()

    def _handle_tts_dispatch(self, text: str) -> None:
        """Internal TTS dispatcher that checks Pomodoro DND suppression if needed."""
        if self.tts_callback:
            try:
                self.tts_callback(text)
            except Exception as e:
                logger.error("Error in ProactiveEngine TTS callback: %s", e)

    # ──────────────────────────────────────────────────────────────────────────
    # Master Lifecycle (start, stop, is_running)
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Starts all enabled proactive sub-engines."""
        with self._lock:
            if self._running:
                return

            if not self.config.enabled:
                logger.info("ProactiveEngine master toggle is disabled. Skipping start.")
                return

            logger.info("Starting ProactiveEngine sub-services...")
            if self.config.reminders_enabled:
                self.reminders.start()
            if self.config.health_monitor_enabled:
                self.health_monitor.start()
            if self.config.daily_briefing_enabled:
                self.briefing_scheduler.start()
            if self.config.inactivity_greeting_enabled:
                self.inactivity.start()

            self._running = True
            logger.info("ProactiveEngine running.")

    def stop(self) -> None:
        """Gracefully stops all running proactive sub-engines."""
        with self._lock:
            if not self._running:
                return

            logger.info("Stopping ProactiveEngine sub-services...")
            self.reminders.stop()
            self.health_monitor.stop()
            self.pomodoro.stop_worker()
            self.briefing_scheduler.stop()
            self.inactivity.stop()

            self._running = False
            logger.info("ProactiveEngine stopped.")

    def is_running(self) -> bool:
        """Checks if the master proactive engine is actively running."""
        with self._lock:
            return self._running

    # ──────────────────────────────────────────────────────────────────────────
    # Delegated Public Interfaces
    # ──────────────────────────────────────────────────────────────────────────

    def add_reminder(
        self,
        text: str,
        delay_seconds: float,
        callback: Callable[[ScheduledReminder], None] | None = None,
    ) -> str:
        """Schedules a new reminder via ReminderScheduler."""
        return self.reminders.add_reminder(text=text, delay_seconds=delay_seconds, callback=callback)

    def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancels a pending reminder."""
        return self.reminders.cancel_reminder(reminder_id)

    def get_pending_reminders(self) -> list[dict[str, Any]]:
        """Returns pending reminders."""
        return self.reminders.get_pending_reminders()

    def start_pomodoro(
        self,
        work_minutes: float | None = None,
        break_minutes: float | None = None,
        cycles: int = 1,
    ) -> str:
        """Starts Pomodoro focus session."""
        return self.pomodoro.start(work_minutes=work_minutes, break_minutes=break_minutes, cycles=cycles)

    def pause_pomodoro(self) -> bool:
        """Pauses active Pomodoro session."""
        return self.pomodoro.pause()

    def resume_pomodoro(self) -> bool:
        """Resumes paused Pomodoro session."""
        return self.pomodoro.resume()

    def stop_pomodoro(self) -> bool:
        """Stops and resets Pomodoro timer."""
        return self.pomodoro.stop()

    def get_pomodoro_status(self) -> dict[str, Any]:
        """Returns current Pomodoro status."""
        return self.pomodoro.get_status().to_dict()

    def is_suppressing_notifications(self) -> bool:
        """Returns True if Pomodoro focus mode is actively blocking notifications."""
        return self.pomodoro.is_suppressing_notifications()

    def should_suppress_notification(self, is_critical: bool = False) -> bool:
        """Returns True if a notification should be suppressed."""
        return self.pomodoro.should_suppress_notification(is_critical=is_critical)

    def record_user_activity(self, now: float | None = None) -> None:
        """Registers user interaction to reset inactivity timer."""
        self.inactivity.record_activity(now=now)

    def trigger_briefing(self, city: str | None = None) -> dict[str, Any]:
        """Manually triggers morning briefing synthesis."""
        return self.briefing_scheduler.trigger_now(city=city)

    def check_health_now(self) -> list[dict[str, Any]]:
        """Performs on-demand telemetry check and returns alerts."""
        alerts = self.health_monitor.check_telemetry()
        return [a.to_dict() for a in alerts]

    @property
    def inactivity_monitor(self) -> InactivityMonitor:
        """Property alias for inactivity monitor instance."""
        return self.inactivity

    # ──────────────────────────────────────────────────────────────────────────
    # Unified Synchronous Tick (Useful for Deterministic Testing)
    # ──────────────────────────────────────────────────────────────────────────

    def tick(
        self,
        now: float | None = None,
        current_dt: datetime.datetime | None = None,
    ) -> dict[str, Any]:
        """
        Executes a synchronous tick across all sub-engines.
        Useful for unit tests and deterministic simulation without real time sleep.
        """
        curr_time = time.time() if now is None else float(now)
        curr_dt = current_dt or datetime.datetime.fromtimestamp(curr_time)

        executed_reminders = self.reminders.tick(now=curr_time)
        health_alerts = self.health_monitor.check_telemetry(now=curr_time)
        pomodoro_event = self.pomodoro.tick(now=curr_time)
        briefing_result = self.briefing_scheduler.tick(current_dt=curr_dt)
        inactivity_triggered = self.inactivity.tick(now=curr_time)

        return {
            "reminders_executed": [r.to_dict() for r in executed_reminders],
            "health_alerts": [a.to_dict() for a in health_alerts],
            "pomodoro_event": pomodoro_event,
            "briefing_triggered": briefing_result is not None,
            "briefing_data": briefing_result,
            "inactivity_triggered": inactivity_triggered,
        }
