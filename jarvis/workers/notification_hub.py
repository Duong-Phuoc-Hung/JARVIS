"""
jarvis/workers/notification_hub.py
=====================================
Notification Hub: trung tâm thông báo đa kênh cho JARVIS.
Gửi thông báo đến: Telegram, Discord, Zalo, Windows Toast, Sound Alert.

Sử dụng:
  hub = NotificationHub()
  hub.notify("Pin máy tính sắp hết!", priority=Priority.HIGH, channels=["telegram", "sound"])
  hub.schedule("Họp lúc 3h", at="15:00")
  hub.add_rule("pin < 20%", "battery_low", channels=["all"])
"""
from __future__ import annotations

import datetime
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.workers.notification_hub")

_NOTIF_LOG = Path("logs/notifications.json")


class Priority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class Channel(Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    ZALO = "zalo"
    SOUND = "sound"
    TOAST = "toast"       # Windows Toast notification
    TTS = "tts"           # Speak aloud via TTS


@dataclass
class Notification:
    title: str
    message: str
    priority: Priority = Priority.NORMAL
    channels: list[str] = field(default_factory=lambda: ["toast", "sound"])
    icon: str = "🔔"
    sent_at: str = ""
    sent_via: list[str] = field(default_factory=list)
    success: bool = False
    error: str = ""


@dataclass
class ScheduledNotification:
    notification: Notification
    trigger_time: str          # "HH:MM" or ISO datetime
    repeat: str = "once"       # once | daily | hourly
    notif_id: str = ""
    active: bool = True


@dataclass
class AlertRule:
    rule_id: str
    condition: str             # Human-readable description
    check_fn: Callable | None = None  # Callable returning bool
    notification: Notification | None = None
    cooldown_s: int = 300      # Don't fire twice within N seconds
    last_fired: float = 0.0
    active: bool = True


class NotificationHub:
    """
    Multi-channel notification dispatcher.
    Supports: Telegram, Discord, Zalo, Windows Toast, Sound, TTS.
    """

    def __init__(self, is_mock: bool = False) -> None:
        self.is_mock = is_mock
        self._scheduled: list[ScheduledNotification] = []
        self._rules: list[AlertRule] = []
        self._history: list[Notification] = []
        self._running = False
        self._thread: threading.Thread | None = None
        Path("logs").mkdir(exist_ok=True)
        log.info("NotificationHub initialized (mock=%s)", is_mock)

    # ------------------------------------------------------------------
    # Core: Send Notification
    # ------------------------------------------------------------------

    def notify(
        self,
        message: str,
        title: str = "JARVIS",
        priority: Priority = Priority.NORMAL,
        channels: list[str] | None = None,
        icon: str = "🔔",
    ) -> Notification:
        """Send a notification across specified channels."""
        if channels is None:
            channels = ["toast", "sound"] if priority == Priority.NORMAL else ["toast", "sound", "tts"]
        if "all" in channels:
            channels = [c.value for c in Channel]

        notif = Notification(
            title=title,
            message=message,
            priority=priority,
            channels=channels,
            icon=icon,
            sent_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        sent_via = []
        errors = []

        for ch in channels:
            try:
                ok = self._dispatch(ch, notif)
                if ok:
                    sent_via.append(ch)
            except Exception as exc:
                errors.append(f"{ch}: {exc}")
                log.warning("Channel %s dispatch error: %s", ch, exc)

        notif.sent_via = sent_via
        notif.success = len(sent_via) > 0
        notif.error = "; ".join(errors)
        self._history.insert(0, notif)
        if len(self._history) > 100:
            self._history = self._history[:100]

        log.info("Notification sent via %s: %s", sent_via, message[:60])
        return notif

    def _dispatch(self, channel: str, notif: Notification) -> bool:
        """Dispatch to a single channel. Returns True if sent."""
        if self.is_mock:
            log.info("Mock dispatch [%s]: %s", channel, notif.message[:50])
            return True

        full_text = f"{notif.icon} {notif.title}\n{notif.message}"

        if channel == Channel.TOAST.value:
            return self._send_toast(notif.title, notif.message, notif.icon)

        elif channel == Channel.SOUND.value:
            return self._send_sound(notif.priority)

        elif channel == Channel.TTS.value:
            return self._send_tts(notif.message)

        elif channel == Channel.TELEGRAM.value:
            try:
                import os

                from jarvis.comms.telegram import TelegramBotController
                chat_id = os.environ.get("TELEGRAM_CHAT_ID")
                if not chat_id:
                    log.debug("Telegram dispatch skipped: TELEGRAM_CHAT_ID not configured")
                    return False
                tg = TelegramBotController(bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
                tg.send_message(int(chat_id), full_text)
                return True
            except Exception as exc:
                log.debug("Telegram dispatch error: %s", exc)
                return False

        elif channel == Channel.DISCORD.value:
            try:
                from jarvis.comms.discord import DiscordBotController
                dc = DiscordBotController(bot_token="")
                dc.send_message(channel_id=0, content=full_text)
                return True
            except Exception as exc:
                log.debug("Discord dispatch error: %s", exc)
                return False

        elif channel == Channel.ZALO.value:
            try:
                from jarvis.comms.zalo import ZaloBotController
                zalo = ZaloBotController()
                # Broadcast to all whitelisted users
                zalo.broadcast(full_text)
                return True
            except Exception as exc:
                log.debug("Zalo dispatch error: %s", exc)
                return False

        log.warning("Unknown channel: %s", channel)
        return False

    def _send_toast(self, title: str, message: str, icon: str = "🔔") -> bool:
        """Send Windows Toast notification."""
        try:
            # Try winotify (best library for Windows 10/11 toasts)
            from winotify import Notification as WinNotif  # type: ignore[import]
            from winotify import audio
            toast = WinNotif(
                app_id="JARVIS AI Assistant",
                title=f"{icon} {title}",
                msg=message[:200],
                duration="short",
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()
            return True
        except ImportError:
            pass
        try:
            # Fallback: PowerShell BurntToast / basic toast
            import subprocess
            ps = (
                f"[Windows.UI.Notifications.ToastNotificationManager, "
                f"Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; "
                f"$xml = [Windows.UI.Notifications.ToastNotificationManager]"
                f"::GetTemplateContent('ToastText02'); "
                f"$xml.GetElementsByTagName('text')[0].InnerText = '{title}'; "
                f"$xml.GetElementsByTagName('text')[1].InnerText = '{message[:100]}'; "
                f"$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
                f"[Windows.UI.Notifications.ToastNotificationManager]::"
                f"CreateToastNotifier('JARVIS').Show($toast)"
            )
            subprocess.run(["powershell", "-Command", ps], timeout=5, capture_output=True)
            return True
        except Exception as exc:
            log.debug("Toast fallback error: %s", exc)
            return False

    def _send_sound(self, priority: Priority) -> bool:
        """Play alert sound via SoundEffectsPlayer."""
        try:
            from jarvis.audio.sound_effects import SoundEffectsPlayer
            player = SoundEffectsPlayer()
            if priority == Priority.URGENT:
                player.play_alert()
            elif priority == Priority.HIGH:
                player.play_thinking()
            else:
                player.play_activation()
            return True
        except Exception as exc:
            log.debug("Sound dispatch error: %s", exc)
            return False

    def _send_tts(self, text: str) -> bool:
        """Speak notification via TTS."""
        try:
            from jarvis.tts.engine import TTSEngine
            engine = TTSEngine()
            engine.speak(text[:200])
            return True
        except Exception as exc:
            log.debug("TTS dispatch error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def schedule(
        self,
        message: str,
        at: str,
        title: str = "JARVIS Reminder",
        channels: list[str] | None = None,
        repeat: str = "once",
        notif_id: str = "",
    ) -> ScheduledNotification:
        """Schedule a future notification. at: 'HH:MM' or ISO datetime."""
        import uuid
        notif = Notification(title=title, message=message, channels=channels or ["toast", "sound"])
        sn = ScheduledNotification(
            notification=notif,
            trigger_time=at,
            repeat=repeat,
            notif_id=notif_id or str(uuid.uuid4())[:8],
        )
        self._scheduled.append(sn)
        log.info("Scheduled notification at %s: %s", at, message[:60])
        return sn

    def cancel_schedule(self, notif_id: str) -> bool:
        for sn in self._scheduled:
            if sn.notif_id == notif_id:
                sn.active = False
                return True
        return False

    def list_schedules(self) -> list[dict[str, Any]]:
        return [
            {"id": s.notif_id, "time": s.trigger_time, "repeat": s.repeat,
             "message": s.notification.message[:60], "active": s.active}
            for s in self._scheduled if s.active
        ]

    # ------------------------------------------------------------------
    # Alert Rules
    # ------------------------------------------------------------------

    def add_rule(
        self,
        condition: str,
        rule_id: str,
        check_fn: Callable | None = None,
        message: str = "",
        channels: list[str] | None = None,
        cooldown_s: int = 300,
    ) -> AlertRule:
        """Add an alert rule with a check function."""
        notif = Notification(
            title=f"Alert: {condition}",
            message=message or condition,
            priority=Priority.HIGH,
            channels=channels or ["toast", "sound"],
        )
        rule = AlertRule(
            rule_id=rule_id,
            condition=condition,
            check_fn=check_fn,
            notification=notif,
            cooldown_s=cooldown_s,
        )
        self._rules.append(rule)
        log.info("Alert rule added: %s", rule_id)
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        for rule in self._rules:
            if rule.rule_id == rule_id:
                rule.active = False
                return True
        return False

    # ------------------------------------------------------------------
    # Background Loop
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="NotificationHub")
        self._thread.start()
        log.info("NotificationHub background loop started")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            self._check_scheduled()
            self._check_rules()
            time.sleep(30)

    def _check_scheduled(self) -> None:
        now = datetime.datetime.now()
        for sn in self._scheduled:
            if not sn.active:
                continue
            try:
                trigger = self._parse_trigger_time(sn.trigger_time, now)
                if trigger and now >= trigger:
                    self.notify(
                        sn.notification.message,
                        sn.notification.title,
                        channels=sn.notification.channels,
                    )
                    if sn.repeat == "once":
                        sn.active = False
            except Exception as exc:
                log.debug("Schedule check error: %s", exc)

    def _parse_trigger_time(self, time_str: str, now: datetime.datetime) -> datetime.datetime | None:
        """Parse 'HH:MM' or ISO datetime into a datetime object."""
        if ":" in time_str and len(time_str) <= 5:
            h, m = map(int, time_str.split(":"))
            t = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if t < now:
                t += datetime.timedelta(days=1)
            return t
        try:
            return datetime.datetime.fromisoformat(time_str)
        except ValueError:
            return None

    def _check_rules(self) -> None:
        now_ts = time.time()
        for rule in self._rules:
            if not rule.active or rule.check_fn is None:
                continue
            if now_ts - rule.last_fired < rule.cooldown_s:
                continue
            try:
                if rule.check_fn():
                    rule.last_fired = now_ts
                    if rule.notification:
                        self.notify(
                            rule.notification.message,
                            rule.notification.title,
                            rule.notification.priority,
                            rule.notification.channels,
                        )
            except Exception as exc:
                log.debug("Rule check error %s: %s", rule.rule_id, exc)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            {"sent_at": n.sent_at, "title": n.title, "message": n.message[:100],
             "channels": n.sent_via, "success": n.success}
            for n in self._history[:limit]
        ]

    @property
    def count(self) -> int:
        return len(self._history)


__all__ = ["NotificationHub", "Notification", "Priority", "Channel", "ScheduledNotification"]
