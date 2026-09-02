"""
jarvis/workers/proactive.py
===========================
Proactive Background Worker and Coordinator Adapter for JARVIS.
Bridges, coordinates, and exposes the Proactive Intelligence Subsystem (R6)
under the Autonomous Workers subsystem architecture.

Sub-services provided:
  1. ReminderScheduler: Timed queue reminders and ActionDispatcher registration.
  2. SystemHealthMonitor: Realtime CPU/RAM/Disk/Temp/Battery threshold watchdog with EventBus alerts.
  3. PomodoroTimer: Work/Break focus cycles and DND notification suppression.
  4. DailyBriefingScheduler: Daily automated morning intelligence briefings.
  5. InactivityMonitor: Idle session watchdog and user engagement prompter.
"""
from __future__ import annotations

import datetime
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from jarvis.proactive.briefing_scheduler import DailyBriefingScheduler
from jarvis.proactive.engine import ProactiveConfig, ProactiveEngine as BaseProactiveEngine
from jarvis.proactive.health_monitor import HealthAlert, SystemHealthMonitor
from jarvis.proactive.inactivity import InactivityMonitor
from jarvis.proactive.pomodoro import PomodoroState, PomodoroStatus, PomodoroTimer
from jarvis.proactive.reminders import ReminderScheduler, ScheduledReminder

logger = logging.getLogger("jarvis.workers.proactive")


class ProactiveEngine(BaseProactiveEngine):
    """
    Proactive Intelligence Worker and Master Coordinator for JARVIS.
    Extends and bridges BaseProactiveEngine with seamless ActionDispatcher
    action registration and EventBus alert integration.
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
        dispatcher: Any | None = None,
        event_bus: Any | None = None,
    ) -> None:
        super().__init__(
            app_context=app_context,
            config=config,
            tts_callback=tts_callback,
            overlay_callback=overlay_callback,
            web_hub=web_hub,
            hardware_monitor=hardware_monitor,
            telemetry_provider=telemetry_provider,
        )

        self.dispatcher = dispatcher or (getattr(app_context, "dispatcher", None) if app_context else None)
        self.event_bus = event_bus or (
            getattr(app_context, "event_bus", None)
            if app_context
            else (getattr(self.dispatcher, "event_bus", None) if self.dispatcher else None)
        )

        # Automatically register actions if an ActionDispatcher is available
        if self.dispatcher is not None:
            self.register_actions(self.dispatcher)

        # Hook health monitor alerts to EventBus if event_bus is present
        self._wrap_health_monitor_event_bus()

    def _wrap_health_monitor_event_bus(self) -> None:
        """Hooks SystemHealthMonitor alert dispatching to publish 'hardware.alert' on EventBus."""
        orig_dispatch = self.health_monitor._dispatch_alert

        def _dispatch_with_event_bus(alert: HealthAlert) -> None:
            orig_dispatch(alert)
            if self.event_bus is not None:
                try:
                    payload = alert.to_dict()
                    payload["component"] = alert.alert_type
                    self.event_bus.publish("hardware.alert", **payload)
                except Exception as exc:
                    logger.debug("Failed to publish hardware.alert on EventBus: %s", exc)

        self.health_monitor._dispatch_alert = _dispatch_with_event_bus  # type: ignore[assignment]

    def register_actions(self, dispatcher: Any) -> None:
        """
        Registers proactive actions into the provided ActionDispatcher:
          - 'proactive_reminder': Schedules timed or delayed reminders.
          - 'proactive_pomodoro_start': Starts Pomodoro focus mode.
          - 'proactive_pomodoro_stop': Stops active Pomodoro timer.
        """
        if dispatcher is None or not hasattr(dispatcher, "register_action"):
            return

        def handle_reminder(
            message: str,
            delay_seconds: float | None = None,
            delay_minutes: float | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            sec = float(delay_seconds if delay_seconds is not None else ((delay_minutes or 5.0) * 60.0))
            r_id = self.add_reminder(text=message, delay_seconds=sec)
            msg = f"Đã đặt lời nhắc '{message}' sau {int(sec)} giây cho Ngài."
            return {
                "status": "success",
                "reminder_id": r_id,
                "message": msg,
            }

        def handle_pomodoro_start(
            work_minutes: float = 25.0,
            break_minutes: float = 5.0,
            **kwargs: Any,
        ) -> dict[str, Any]:
            res = self.start_pomodoro(work_minutes=work_minutes, break_minutes=break_minutes)
            msg = f"Đã bắt đầu phiên tập trung Focus Mode {work_minutes} phút, thưa Ngài."
            return {
                "status": "success",
                "message": msg,
                "details": res,
            }

        def handle_pomodoro_stop(**kwargs: Any) -> dict[str, Any]:
            self.stop_pomodoro()
            return {
                "status": "success",
                "message": "Đã dừng phiên tập trung Focus Mode, thưa Ngài.",
            }

        try:
            dispatcher.register_action(
                name="proactive_reminder",
                handler=handle_reminder,
                description="Schedules a proactive timed reminder",
            )
            dispatcher.register_action(
                name="proactive_pomodoro_start",
                handler=handle_pomodoro_start,
                description="Starts a Pomodoro focus mode timer",
            )
            dispatcher.register_action(
                name="proactive_pomodoro_stop",
                handler=handle_pomodoro_stop,
                description="Stops active Pomodoro focus mode timer",
            )
            logger.debug("Successfully registered proactive actions with ActionDispatcher.")
        except Exception as exc:
            logger.warning("Error registering actions with ActionDispatcher: %s", exc)


__all__ = [
    "ProactiveEngine",
    "ProactiveConfig",
    "ReminderScheduler",
    "ScheduledReminder",
    "SystemHealthMonitor",
    "HealthAlert",
    "PomodoroTimer",
    "PomodoroState",
    "PomodoroStatus",
    "DailyBriefingScheduler",
    "InactivityMonitor",
]
