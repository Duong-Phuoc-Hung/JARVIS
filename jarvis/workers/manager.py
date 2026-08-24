"""
SubAgentManager for the JARVIS Autonomous Background Workers subsystem.
Coordinates worker pool concurrency, active worker registry, task cancellation,
health watchdog telemetry, and multi-channel completion dispatching.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Union

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.healing.watchdog import ResourceWatchdog
from jarvis.workers.models import WorkerStatus, WorkerTask, WorkerTelemetry
from jarvis.workers.notifications import WorkerNotificationDispatcher
from jarvis.workers.worker import BackgroundWorker

logger = logging.getLogger("jarvis.workers.manager")


class SubAgentManager:
    """
    Central Coordinator and Concurrency Manager for Sub-Agent Background Workers.
    Provides non-blocking task delegation, active lifecycle registry, and query interfaces.
    """

    def __init__(
        self,
        max_workers: int = 4,
        watchdog: Optional[ResourceWatchdog] = None,
        event_bus: Optional[EventBus] = None,
        dispatcher: Optional[ActionDispatcher] = None,
        notification_dispatcher: Optional[WorkerNotificationDispatcher] = None,
        history_maxlen: int = 100,
    ) -> None:
        self.max_workers = max(1, int(max_workers))
        self.watchdog = watchdog
        self.event_bus = event_bus or (dispatcher.event_bus if dispatcher else EventBus())
        self.dispatcher = dispatcher
        self.notifications = notification_dispatcher or WorkerNotificationDispatcher(event_bus=self.event_bus)

        self._active_workers: Dict[str, BackgroundWorker] = {}
        self._history: Deque[WorkerTelemetry] = deque(maxlen=history_maxlen)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SubAgentPool")
        self._is_shutdown = False

    def spawn_worker(self, task: WorkerTask) -> str:
        """
        Delegates a task to an autonomous background worker.
        
        Args:
            task: WorkerTask specification.
            
        Returns:
            Unique worker_id string.
        """
        with self._lock:
            if self._is_shutdown:
                raise RuntimeError("Cannot spawn worker: SubAgentManager is shutdown.")

            worker = BackgroundWorker(
                task=task,
                watchdog=self.watchdog,
                event_bus=self.event_bus,
                dispatcher=self.dispatcher,
                on_complete_callback=self._handle_worker_finished,
            )

            self._active_workers[worker.worker_id] = worker

        logger.info(
            "Spawning background sub-agent '%s' for task '%s' (type=%s, priority=%d)",
            worker.worker_id, task.name, task.task_type, int(task.priority)
        )

        self.notifications.notify_started(task, worker.telemetry)
        worker.start()
        return worker.worker_id

    def cancel_worker(self, worker_id: str) -> bool:
        """
        Signals cooperative cancellation to an active background worker.
        
        Returns:
            True if worker was found and signaled, False otherwise.
        """
        with self._lock:
            worker = self._active_workers.get(worker_id)
            if not worker:
                logger.warning("Attempted to cancel non-existent worker '%s'.", worker_id)
                return False

            worker.cancel()
            return True

    def pause_worker(self, worker_id: str) -> bool:
        """Pauses execution of an active worker."""
        with self._lock:
            worker = self._active_workers.get(worker_id)
            if worker:
                worker.pause()
                return True
            return False

    def resume_worker(self, worker_id: str) -> bool:
        """Resumes execution of a paused worker."""
        with self._lock:
            worker = self._active_workers.get(worker_id)
            if worker:
                worker.resume()
                return True
            return False

    def get_worker_status(self, worker_id: str) -> Optional[WorkerTelemetry]:
        """
        Retrieves telemetry for a worker by ID, searching active registry and history.
        """
        with self._lock:
            worker = self._active_workers.get(worker_id)
            if worker:
                return worker.telemetry

            # Check history
            for entry in self._history:
                if entry.worker_id == worker_id:
                    return entry

            return None

    def list_active_workers(self) -> List[WorkerTelemetry]:
        """Returns list of telemetry snapshots for all currently active workers."""
        with self._lock:
            return [w.telemetry for w in self._active_workers.values()]

    def list_history(self) -> List[WorkerTelemetry]:
        """Returns list of finished worker telemetry records."""
        with self._lock:
            return list(self._history)

    def list_all_workers(self) -> List[WorkerTelemetry]:
        """Returns active and historical worker telemetry records combined."""
        with self._lock:
            active = [w.telemetry for w in self._active_workers.values()]
            historical = list(self._history)
            return active + historical

    def wait_for_worker(self, worker_id: str, timeout: Optional[float] = None) -> Optional[WorkerTelemetry]:
        """
        Blocks until a specific worker finishes execution or timeout expires.
        
        Returns:
            Final WorkerTelemetry or None if timed out/not found.
        """
        worker = None
        with self._lock:
            worker = self._active_workers.get(worker_id)

        if worker:
            worker.join(timeout=timeout)
            return self.get_worker_status(worker_id)

        return self.get_worker_status(worker_id)

    def wait_all(self, timeout: Optional[float] = None) -> bool:
        """
        Blocks until all active workers finish execution.
        
        Returns:
            True if all finished, False if timeout elapsed.
        """
        deadline = (time.time() + timeout) if timeout is not None else None
        while True:
            with self._lock:
                workers = list(self._active_workers.values())
                if not workers:
                    return True

            if deadline and time.time() > deadline:
                return False

            for w in workers:
                remaining = (deadline - time.time()) if deadline else 0.5
                if remaining <= 0:
                    return False
                w.join(timeout=min(0.2, remaining))

    def _handle_worker_finished(self, telemetry: WorkerTelemetry, task: WorkerTask) -> None:
        """Internal callback invoked when a BackgroundWorker completes, fails, or cancels."""
        with self._lock:
            self._active_workers.pop(telemetry.worker_id, None)
            self._history.append(telemetry)

        # Dispatch multi-channel notifications
        if telemetry.status == WorkerStatus.COMPLETED:
            self.notifications.notify_completion(task, telemetry)
        elif telemetry.status == WorkerStatus.FAILED:
            self.notifications.notify_failure(task, telemetry)
        elif telemetry.status == WorkerStatus.CANCELLED:
            self.notifications.notify_cancellation(task, telemetry)

    def shutdown(self, wait: bool = True, cancel_running: bool = True) -> None:
        """
        Gracefully stops SubAgentManager.
        
        Args:
            wait: Whether to wait for active workers to terminate.
            cancel_running: Whether to signal cancellation to all running workers.
        """
        with self._lock:
            self._is_shutdown = True
            workers = list(self._active_workers.values())

        if cancel_running:
            for w in workers:
                w.cancel()

        if wait:
            for w in workers:
                w.join(timeout=2.0)

        self._executor.shutdown(wait=wait)
        logger.info("SubAgentManager shutdown complete.")
