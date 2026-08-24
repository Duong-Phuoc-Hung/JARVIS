"""
Worker Notification Dispatcher for the JARVIS Autonomous Background Workers subsystem.
Dispatches completion and status notifications across multi-modal channels:
- Voice TTS announcement (TTSManager)
- EventBus progress & lifecycle broadcasting
- AlwaysOnOverlay HUD card display
- Telegram remote notification & artifact file dispatch
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Union

from jarvis.comms.telegram import TelegramBotController
from jarvis.core.dispatcher import EventBus
from jarvis.tts.manager import TTSManager
from jarvis.ui.overlay import AlwaysOnOverlay
from jarvis.workers.models import WorkerStatus, WorkerTask, WorkerTelemetry

logger = logging.getLogger("jarvis.workers.notifications")


class WorkerNotificationDispatcher:
    """
    Multi-channel notification dispatcher for background sub-agents.
    Coordinates voice TTS synthesis, HUD overlay cards, Telegram messaging, and file attachments.
    """

    def __init__(
        self,
        tts_manager: Optional[TTSManager] = None,
        overlay: Optional[AlwaysOnOverlay] = None,
        telegram_controller: Optional[TelegramBotController] = None,
        event_bus: Optional[EventBus] = None,
        default_telegram_chat_id: Optional[int] = None,
    ) -> None:
        self.tts_manager = tts_manager
        self.overlay = overlay
        self.telegram_controller = telegram_controller
        self.event_bus = event_bus
        self.default_telegram_chat_id = default_telegram_chat_id

    def format_vietnamese_summary(self, task: WorkerTask, telemetry: WorkerTelemetry) -> str:
        """Formats a natural Vietnamese announcement for speech and UI notifications."""
        elapsed = telemetry.elapsed_seconds
        elapsed_str = f"{elapsed:.1f} giây" if elapsed < 60 else f"{int(elapsed // 60)} phút {int(elapsed % 60)} giây"

        if telemetry.status == WorkerStatus.COMPLETED:
            artifact_note = f" Đã tạo {len(telemetry.artifacts)} tệp tin kết quả." if telemetry.artifacts else ""
            return f"Thưa Ngài, tác vụ nền '{task.name}' đã hoàn tất thành công trong {elapsed_str}.{artifact_note}"

        elif telemetry.status == WorkerStatus.FAILED:
            err = telemetry.error or "Lỗi không xác định"
            return f"Thưa Ngài, tác vụ nền '{task.name}' đã gặp sự cố: {err}."

        elif telemetry.status == WorkerStatus.CANCELLED:
            return f"Tác vụ nền '{task.name}' đã được dừng lại theo yêu cầu của Ngài."

        return f"Tác vụ nền '{task.name}' đang chạy: {telemetry.progress_pct:.0f}% ({telemetry.current_step})."

    def notify_started(self, task: WorkerTask, telemetry: WorkerTelemetry) -> None:
        """Broadcasts worker started event and updates overlay if configured."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                self.event_bus.publish("worker:started", telemetry=telemetry.to_dict(), task=task.to_dict())
            except Exception as e:
                logger.debug("Failed to publish worker:started: %s", e)

    def notify_progress(self, task: WorkerTask, telemetry: WorkerTelemetry) -> None:
        """Broadcasts worker progress event to HUD and EventBus."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                self.event_bus.publish("worker:progress", telemetry=telemetry.to_dict(), task=task.to_dict())
            except Exception as e:
                logger.debug("Failed to publish worker:progress: %s", e)

    def notify_completion(self, task: WorkerTask, telemetry: WorkerTelemetry) -> None:
        """Dispatches full completion notifications across TTS, Overlay, and Telegram."""
        summary = self.format_vietnamese_summary(task, telemetry)
        logger.info("Worker '%s' completion notification: %s", telemetry.worker_id, summary)

        # 1. Voice TTS Announcement
        if task.notify_tts and self.tts_manager and hasattr(self.tts_manager, "speak"):
            try:
                self.tts_manager.speak(summary, wait=False)
            except Exception as e:
                logger.warning("TTS completion notification failed: %s", e)

        # 2. AlwaysOnOverlay HUD Card
        if task.notify_overlay and self.overlay and hasattr(self.overlay, "add_turn"):
            try:
                self.overlay.add_turn(
                    user_text=f"⚙️ Tác vụ ngầm: {task.name}",
                    jarvis_text=summary,
                    action=f"worker_{telemetry.worker_id}",
                )
            except Exception as e:
                logger.warning("Overlay completion card notification failed: %s", e)

        # 3. Telegram Remote Notification & Artifacts
        if task.notify_telegram and self.telegram_controller:
            chat_id = task.telegram_chat_id or self.default_telegram_chat_id
            if chat_id:
                try:
                    self._dispatch_telegram(chat_id, summary, telemetry.artifacts)
                except Exception as e:
                    logger.warning("Telegram notification failed: %s", e)

        # 4. EventBus Completion Event
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                self.event_bus.publish(
                    "worker:completed",
                    telemetry=telemetry.to_dict(),
                    task=task.to_dict(),
                    summary=summary,
                )
            except Exception as e:
                logger.debug("Failed to publish worker:completed: %s", e)

    def notify_failure(self, task: WorkerTask, telemetry: WorkerTelemetry) -> None:
        """Dispatches failure notifications across channels."""
        summary = self.format_vietnamese_summary(task, telemetry)
        logger.warning("Worker '%s' failure notification: %s", telemetry.worker_id, summary)

        if task.notify_tts and self.tts_manager and hasattr(self.tts_manager, "speak"):
            try:
                self.tts_manager.speak(summary, wait=False)
            except Exception as e:
                logger.warning("TTS failure notification failed: %s", e)

        if task.notify_overlay and self.overlay and hasattr(self.overlay, "add_turn"):
            try:
                self.overlay.add_turn(
                    user_text=f"⚠️ Lỗi tác vụ: {task.name}",
                    jarvis_text=summary,
                    action="worker_error",
                )
            except Exception as e:
                logger.warning("Overlay error card notification failed: %s", e)

        if task.notify_telegram and self.telegram_controller:
            chat_id = task.telegram_chat_id or self.default_telegram_chat_id
            if chat_id:
                try:
                    self.telegram_controller.send_message(chat_id=chat_id, text=f"🚨 {summary}")
                except Exception as e:
                    logger.warning("Telegram failure notification failed: %s", e)

        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                self.event_bus.publish(
                    "worker:failed",
                    telemetry=telemetry.to_dict(),
                    task=task.to_dict(),
                    error=telemetry.error,
                )
            except Exception as e:
                logger.debug("Failed to publish worker:failed: %s", e)

    def notify_cancellation(self, task: WorkerTask, telemetry: WorkerTelemetry) -> None:
        """Dispatches cancellation notifications."""
        summary = self.format_vietnamese_summary(task, telemetry)

        if task.notify_overlay and self.overlay and hasattr(self.overlay, "add_turn"):
            try:
                self.overlay.add_turn(
                    user_text=f"⏹️ Hủy tác vụ: {task.name}",
                    jarvis_text=summary,
                    action="worker_cancelled",
                )
            except Exception as e:
                logger.debug("Overlay cancel card failed: %s", e)

        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                self.event_bus.publish(
                    "worker:cancelled",
                    telemetry=telemetry.to_dict(),
                    task=task.to_dict(),
                )
            except Exception as e:
                logger.debug("Failed to publish worker:cancelled: %s", e)

    def _dispatch_telegram(self, chat_id: int, text: str, artifacts: List[str]) -> None:
        """Sends message and uploads artifact files/photos to Telegram."""
        if not self.telegram_controller:
            return

        self.telegram_controller.send_message(chat_id=chat_id, text=text)

        for path in artifacts:
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
                try:
                    with open(path, "rb") as f:
                        img_bytes = f.read()
                    self.telegram_controller.send_photo(
                        chat_id=chat_id,
                        photo_bytes=img_bytes,
                        caption=os.path.basename(path),
                    )
                except Exception as e:
                    logger.warning("Failed to send photo artifact to Telegram: %s", e)
            else:
                try:
                    self.telegram_controller.send_message(
                        chat_id=chat_id,
                        text=f"📁 Tệp kết quả: {os.path.basename(path)} ({path})",
                    )
                except Exception as e:
                    logger.warning("Failed to send document link to Telegram: %s", e)
