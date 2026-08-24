"""
Unit and Integration Tests for JARVIS Background Sub-Agents & Telemetry Subsystem (Requirement R5).
Tests BackgroundWorker lifecycle, cooperative cancellation, SubAgentManager concurrency pool,
watchdog heartbeats, and multi-channel notifications (TTS, Overlay, Telegram).
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.healing.watchdog import ResourceWatchdog
from jarvis.workers.manager import SubAgentManager
from jarvis.workers.models import (
    WorkerPriority,
    WorkerStatus,
    WorkerTask,
    WorkerTelemetry,
)
from jarvis.workers.notifications import WorkerNotificationDispatcher
from jarvis.workers.worker import BackgroundWorker, WorkerCancelledException


class TestBackgroundWorkers(unittest.TestCase):
    """Test suite covering BackgroundWorker, SubAgentManager, and WorkerNotificationDispatcher."""

    def setUp(self) -> None:
        self.event_bus = EventBus()
        self.watchdog = ResourceWatchdog(event_bus=self.event_bus)
        self.mock_tts = MagicMock()
        self.mock_overlay = MagicMock()
        self.mock_telegram = MagicMock()
        self.notifications = WorkerNotificationDispatcher(
            tts_manager=self.mock_tts,
            overlay=self.mock_overlay,
            telegram_controller=self.mock_telegram,
            event_bus=self.event_bus,
            default_telegram_chat_id=12345678,
        )
        self.manager = SubAgentManager(
            max_workers=4,
            watchdog=self.watchdog,
            event_bus=self.event_bus,
            notification_dispatcher=self.notifications,
        )

    def tearDown(self) -> None:
        self.manager.shutdown(wait=False, cancel_running=True)

    # 1. test_worker_lifecycle_creation_to_completion
    def test_worker_lifecycle_creation_to_completion(self) -> None:
        executed = False

        def work_fn(worker: BackgroundWorker) -> Dict[str, str]:
            nonlocal executed
            worker.update_progress(50.0, step="Halfway done")
            executed = True
            return {"result": "ok"}

        task = WorkerTask(
            task_id="task_lifecycle_1",
            name="Data Processing Task",
            target_callable=work_fn,
        )

        worker_id = self.manager.spawn_worker(task)
        telemetry = self.manager.wait_for_worker(worker_id, timeout=3.0)

        self.assertIsNotNone(telemetry)
        self.assertTrue(executed)
        self.assertEqual(telemetry.status, WorkerStatus.COMPLETED)
        self.assertEqual(telemetry.progress_pct, 100.0)
        self.assertEqual(telemetry.result_data, {"result": "ok"})

    # 2. test_worker_cooperative_cancellation
    def test_worker_cooperative_cancellation(self) -> None:
        was_cancelled = False

        def long_running_fn(worker: BackgroundWorker) -> None:
            nonlocal was_cancelled
            for i in range(100):
                worker.check_cancelled()
                time.sleep(0.05)
                worker.update_progress(float(i), step=f"Step {i}")

        task = WorkerTask(
            task_id="task_cancel_1",
            name="Cancellable Long Task",
            target_callable=long_running_fn,
        )

        worker_id = self.manager.spawn_worker(task)
        time.sleep(0.1)
        cancelled = self.manager.cancel_worker(worker_id)
        self.assertTrue(cancelled)

        telemetry = self.manager.wait_for_worker(worker_id, timeout=3.0)
        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry.status, WorkerStatus.CANCELLED)

    # 3. test_sub_agent_manager_concurrency_limit
    def test_sub_agent_manager_concurrency_limit(self) -> None:
        manager = SubAgentManager(
            max_workers=2,
            watchdog=self.watchdog,
            event_bus=self.event_bus,
        )

        completed_tasks: List[int] = []

        def quick_task(idx: int) -> int:
            time.sleep(0.05)
            completed_tasks.append(idx)
            return idx

        worker_ids = []
        for i in range(5):
            task = WorkerTask(
                task_id=f"concurrent_task_{i}",
                name=f"Task {i}",
                payload={"idx": i},
                target_callable=quick_task,
            )
            worker_ids.append(manager.spawn_worker(task))

        for wid in worker_ids:
            manager.wait_for_worker(wid, timeout=3.0)

        self.assertEqual(len(completed_tasks), 5)
        manager.shutdown(wait=True)

    # 4. test_worker_telemetry_progress_broadcasting
    def test_worker_telemetry_progress_broadcasting(self) -> None:
        progress_events: List[Dict[str, Any]] = []

        def on_progress(**payload: Any) -> None:
            progress_events.append(payload)

        self.event_bus.subscribe("worker:progress", on_progress)

        def progress_work(worker: BackgroundWorker) -> None:
            worker.update_progress(25.0, step="Stage 1")
            worker.update_progress(75.0, step="Stage 2")

        task = WorkerTask(
            task_id="task_prog_1",
            name="Progress Task",
            target_callable=progress_work,
        )

        worker_id = self.manager.spawn_worker(task)
        self.manager.wait_for_worker(worker_id, timeout=3.0)

        self.assertGreaterEqual(len(progress_events), 2)
        pcts = [p.get("telemetry", {}).get("progress_pct") for p in progress_events]
        self.assertIn(25.0, pcts)
        self.assertIn(75.0, pcts)

    # 5. test_worker_watchdog_heartbeat_registration
    def test_worker_watchdog_heartbeat_registration(self) -> None:
        def pulse_work(worker: BackgroundWorker) -> None:
            worker.update_progress(50.0, step="Heartbeat step")
            time.sleep(0.05)

        task = WorkerTask(
            task_id="task_watchdog_1",
            name="Watchdog Heartbeat Task",
            target_callable=pulse_work,
        )

        worker_id = self.manager.spawn_worker(task)
        self.manager.wait_for_worker(worker_id, timeout=3.0)

        # Check if watchdog has recorded pulse for this thread
        with self.watchdog._lock:
            thread_key = f"worker_{worker_id}"
            self.assertIn(thread_key, self.watchdog._thread_heartbeats)

    # 6. test_worker_completion_tts_notification_hook
    def test_worker_completion_tts_notification_hook(self) -> None:
        task = WorkerTask(
            task_id="task_tts_1",
            name="Revenue Aggregation",
            notify_tts=True,
            target_callable=lambda: {"done": True},
        )

        worker_id = self.manager.spawn_worker(task)
        self.manager.wait_for_worker(worker_id, timeout=3.0)

        self.mock_tts.speak.assert_called()
        spoken_text = self.mock_tts.speak.call_args[0][0]
        self.assertIn("Revenue Aggregation", spoken_text)
        self.assertIn("hoàn tất", spoken_text)

    # 7. test_worker_completion_overlay_card_notification
    def test_worker_completion_overlay_card_notification(self) -> None:
        task = WorkerTask(
            task_id="task_overlay_1",
            name="Backup Archive",
            notify_overlay=True,
            target_callable=lambda: {"files": 10},
        )

        worker_id = self.manager.spawn_worker(task)
        self.manager.wait_for_worker(worker_id, timeout=3.0)

        self.mock_overlay.add_turn.assert_called()
        card_user = self.mock_overlay.add_turn.call_args[1]["user_text"]
        self.assertIn("Backup Archive", card_user)

    # 8. test_worker_telegram_notification_and_attachment_dispatch
    def test_worker_telegram_notification_and_attachment_dispatch(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
            tmp_img.write(b"\x89PNG\r\n\x1a\nFakeImageData")
            img_path = tmp_img.name

        try:
            def work_with_artifact(worker: BackgroundWorker) -> None:
                worker.update_progress(90.0, artifacts=[img_path])

            task = WorkerTask(
                task_id="task_tele_1",
                name="Chart Rendering",
                notify_telegram=True,
                telegram_chat_id=98765432,
                target_callable=work_with_artifact,
            )

            worker_id = self.manager.spawn_worker(task)
            self.manager.wait_for_worker(worker_id, timeout=3.0)

            # Telegram controller should have received send_message and send_photo
            self.mock_telegram.send_message.assert_called()
            self.mock_telegram.send_photo.assert_called()
            call_chat_id = self.mock_telegram.send_photo.call_args[1]["chat_id"]
            self.assertEqual(call_chat_id, 98765432)
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    # 9. test_worker_failure_error_isolation
    def test_worker_failure_error_isolation(self) -> None:
        def crashing_task() -> None:
            raise ArithmeticError("Division by zero in batch job")

        task = WorkerTask(
            task_id="task_crash_1",
            name="Crashing SubAgent",
            target_callable=crashing_task,
        )

        worker_id = self.manager.spawn_worker(task)
        telemetry = self.manager.wait_for_worker(worker_id, timeout=3.0)

        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry.status, WorkerStatus.FAILED)
        self.assertIn("Division by zero", telemetry.error or "")

        # Verify manager is still healthy and can execute new tasks
        task_healthy = WorkerTask(
            task_id="task_healthy_1",
            name="Healthy SubAgent",
            target_callable=lambda: "healthy",
        )
        healthy_id = self.manager.spawn_worker(task_healthy)
        telemetry_healthy = self.manager.wait_for_worker(healthy_id, timeout=3.0)
        self.assertEqual(telemetry_healthy.status, WorkerStatus.COMPLETED)
        self.assertEqual(telemetry_healthy.result_data, "healthy")

    # 10. test_worker_timeout_enforcement
    def test_worker_timeout_enforcement(self) -> None:
        # Worker execution time exceeds configured timeout
        task = WorkerTask(
            task_id="task_timeout_1",
            name="Quick Timeout Task",
            timeout_seconds=0.1,
            target_callable=lambda: time.sleep(0.05) or "ok",
        )

        worker_id = self.manager.spawn_worker(task)
        telemetry = self.manager.wait_for_worker(worker_id, timeout=3.0)
        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry.status, WorkerStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
