"""
Background Sub-Agent Worker implementation for JARVIS.
Executes delegated long-running tasks in dedicated background threads with cooperative cancellation,
heartbeat telemetry to ResourceWatchdog, error isolation, and real-time progress broadcasting.
"""
from __future__ import annotations

import inspect
import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.healing.watchdog import ResourceWatchdog
from jarvis.workers.models import WorkerStatus, WorkerTask, WorkerTelemetry

logger = logging.getLogger("jarvis.workers.worker")


class WorkerCancelledException(Exception):
    """Raised when a task terminates cooperatively due to a cancellation request."""
    pass


class BackgroundWorker:
    """
    Independent background execution thread for a long-running delegated task.
    Enforces cooperative cancellation, periodic watchdog heartbeats, and telemetry updates.
    """

    def __init__(
        self,
        task: WorkerTask,
        worker_id: str | None = None,
        watchdog: ResourceWatchdog | None = None,
        event_bus: EventBus | None = None,
        dispatcher: ActionDispatcher | None = None,
        on_complete_callback: Callable[[WorkerTelemetry, WorkerTask], None] | None = None,
    ) -> None:
        self.task = task
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.watchdog = watchdog
        self.event_bus = event_bus
        self.dispatcher = dispatcher
        self.on_complete_callback = on_complete_callback

        self._cancel_token = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused by default (set means running)

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None

        self._telemetry = WorkerTelemetry(
            worker_id=self.worker_id,
            task_id=self.task.task_id,
            task_name=self.task.name,
            status=WorkerStatus.INITIALIZING,
            progress_pct=0.0,
            current_step="Khởi tạo sub-agent",
            elapsed_seconds=0.0,
            heartbeat_timestamp=time.time(),
        )

    @property
    def telemetry(self) -> WorkerTelemetry:
        """Returns a snapshot copy of current worker telemetry."""
        with self._lock:
            if self._telemetry.started_at and not self._telemetry.finished_at:
                self._telemetry.elapsed_seconds = time.time() - self._telemetry.started_at
            return WorkerTelemetry(
                worker_id=self._telemetry.worker_id,
                task_id=self._telemetry.task_id,
                task_name=self._telemetry.task_name,
                status=self._telemetry.status,
                progress_pct=self._telemetry.progress_pct,
                current_step=self._telemetry.current_step,
                elapsed_seconds=self._telemetry.elapsed_seconds,
                estimated_remaining_seconds=self._telemetry.estimated_remaining_seconds,
                artifacts=list(self._telemetry.artifacts),
                error=self._telemetry.error,
                result_data=self._telemetry.result_data,
                heartbeat_timestamp=self._telemetry.heartbeat_timestamp,
                started_at=self._telemetry.started_at,
                finished_at=self._telemetry.finished_at,
            )

    @property
    def is_alive(self) -> bool:
        """Returns True if the underlying worker thread is currently running."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Starts background worker thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.warning("Worker '%s' is already running.", self.worker_id)
                return

            self._thread = threading.Thread(
                target=self._run_wrapper,
                daemon=True,
                name=f"SubAgent-{self.worker_id}",
            )
            self._thread.start()

    def cancel(self) -> None:
        """Signals cooperative cancellation to the worker."""
        logger.info("Signaling cancellation to worker '%s' (task='%s').", self.worker_id, self.task.name)
        self._cancel_token.set()
        # If paused, unpause so it can observe the cancellation signal
        self._pause_event.set()

    def pause(self) -> None:
        """Pauses the worker loop if cooperative pausing is supported."""
        with self._lock:
            if self._telemetry.status == WorkerStatus.RUNNING:
                self._pause_event.clear()
                self._telemetry.status = WorkerStatus.PAUSED
                logger.info("Worker '%s' paused.", self.worker_id)
                self._publish_event("worker:paused", telemetry=self.telemetry.to_dict())

    def resume(self) -> None:
        """Resumes a paused worker."""
        with self._lock:
            if self._telemetry.status == WorkerStatus.PAUSED:
                self._pause_event.set()
                self._telemetry.status = WorkerStatus.RUNNING
                logger.info("Worker '%s' resumed.", self.worker_id)
                self._publish_event("worker:resumed", telemetry=self.telemetry.to_dict())

    def is_cancelled(self) -> bool:
        """Checks if cancellation has been requested."""
        return self._cancel_token.is_set()

    def check_cancelled(self) -> None:
        """Raises WorkerCancelledException if cancellation has been requested."""
        if self._cancel_token.is_set():
            raise WorkerCancelledException(f"Worker '{self.worker_id}' was cancelled by user request.")

    def wait_if_paused(self) -> None:
        """Blocks execution while the worker is in PAUSED state."""
        self._pause_event.wait()
        self.check_cancelled()

    def update_progress(
        self,
        pct: float,
        step: str = "",
        artifacts: list[str] | None = None,
        estimated_remaining_seconds: float | None = None,
        data: Any = None,
    ) -> None:
        """
        Updates worker progress and broadcasts telemetry.
        
        Args:
            pct: Percentage complete (0.0 to 100.0).
            step: Short description of current progress step.
            artifacts: List of file paths or generated artifacts.
            estimated_remaining_seconds: Optional ETA in seconds.
            data: Optional intermediate data.
        """
        self.check_cancelled()
        self.wait_if_paused()

        now = time.time()
        with self._lock:
            self._telemetry.progress_pct = max(0.0, min(100.0, float(pct)))
            if step:
                self._telemetry.current_step = step
            if artifacts:
                self._telemetry.artifacts.extend(
                    [a for a in artifacts if a not in self._telemetry.artifacts]
                )
            if estimated_remaining_seconds is not None:
                self._telemetry.estimated_remaining_seconds = float(estimated_remaining_seconds)
            if self._telemetry.started_at:
                self._telemetry.elapsed_seconds = now - self._telemetry.started_at
            self._telemetry.heartbeat_timestamp = now

        # Pulse watchdog
        self._pulse_watchdog()

        # Publish progress event
        self._publish_event("worker:progress", telemetry=self.telemetry.to_dict())

    def _pulse_watchdog(self) -> None:
        """Pushes heartbeat to ResourceWatchdog."""
        if self.watchdog and hasattr(self.watchdog, "record_heartbeat"):
            try:
                self.watchdog.record_heartbeat(
                    thread_name=f"worker_{self.worker_id}",
                    timeout_s=60.0,
                )
            except Exception as e:
                logger.debug("Failed to record watchdog heartbeat: %s", e)

    def _run_wrapper(self) -> None:
        """Thread entrypoint executing the worker task with full exception isolation."""
        now = time.time()
        with self._lock:
            self._telemetry.status = WorkerStatus.RUNNING
            self._telemetry.started_at = now
            self._telemetry.heartbeat_timestamp = now

        self._pulse_watchdog()
        self._publish_event("worker:started", telemetry=self.telemetry.to_dict())
        logger.info("Worker '%s' started executing task '%s'.", self.worker_id, self.task.name)

        try:
            # Execute actual workload
            result = self._execute_task()
            self.check_cancelled()

            with self._lock:
                self._telemetry.status = WorkerStatus.COMPLETED
                self._telemetry.progress_pct = 100.0
                self._telemetry.finished_at = time.time()
                self._telemetry.elapsed_seconds = self._telemetry.finished_at - (self._telemetry.started_at or now)
                self._telemetry.result_data = result
                self._telemetry.current_step = "Hoàn thành"

            logger.info("Worker '%s' COMPLETED task '%s' in %.2fs.", self.worker_id, self.task.name, self._telemetry.elapsed_seconds)
            self._publish_event("worker:completed", telemetry=self.telemetry.to_dict())

        except WorkerCancelledException as exc:
            with self._lock:
                self._telemetry.status = WorkerStatus.CANCELLED
                self._telemetry.finished_at = time.time()
                self._telemetry.elapsed_seconds = self._telemetry.finished_at - (self._telemetry.started_at or now)
                self._telemetry.error = str(exc)
                self._telemetry.current_step = "Đã hủy bởi người dùng"

            logger.info("Worker '%s' was CANCELLED.", self.worker_id)
            self._publish_event("worker:cancelled", telemetry=self.telemetry.to_dict())

        except Exception as exc:
            with self._lock:
                self._telemetry.status = WorkerStatus.FAILED
                self._telemetry.finished_at = time.time()
                self._telemetry.elapsed_seconds = self._telemetry.finished_at - (self._telemetry.started_at or now)
                self._telemetry.error = str(exc)
                self._telemetry.current_step = f"Lỗi: {exc}"

            logger.error("Worker '%s' FAILED with exception: %s", self.worker_id, exc, exc_info=True)
            self._publish_event("worker:failed", telemetry=self.telemetry.to_dict())

        finally:
            if self.on_complete_callback and callable(self.on_complete_callback):
                try:
                    self.on_complete_callback(self.telemetry, self.task)
                except Exception as cb_err:
                    logger.warning("Worker completion callback failed: %s", cb_err)

    def _execute_task(self) -> Any:
        """Executes the specific target callable or dispatcher action."""
        self.check_cancelled()

        # Target Callable execution
        if self.task.target_callable and callable(self.task.target_callable):
            fn = self.task.target_callable
            sig = inspect.signature(fn)
            kwargs: dict[str, Any] = dict(self.task.payload)

            # Pass worker or helper dependencies if requested in parameters
            if "worker" in sig.parameters:
                kwargs["worker"] = self
            if "cancel_token" in sig.parameters:
                kwargs["cancel_token"] = self._cancel_token
            if "update_progress" in sig.parameters:
                kwargs["update_progress"] = self.update_progress

            return fn(**kwargs)

        # ActionDispatcher execution
        elif self.task.action_name and self.dispatcher:
            res = self.dispatcher.dispatch_action(
                action_name=self.task.action_name,
                payload=self.task.payload,
                requester=f"worker:{self.worker_id}",
            )
            if not res.success:
                raise RuntimeError(res.error or f"Action '{self.task.action_name}' execution failed.")
            return res.data

        else:
            # Default simulated work loop with progress
            for i in range(1, 6):
                self.check_cancelled()
                self.wait_if_paused()
                time.sleep(0.1)
                self.update_progress(i * 20.0, step=f"Đang xử lý bước {i}/5")
            return {"status": "success", "message": f"Task {self.task.name} completed successfully."}

    def join(self, timeout: float | None = None) -> None:
        """Blocks until the worker thread terminates."""
        if self._thread:
            self._thread.join(timeout=timeout)

    def _publish_event(self, topic: str, **kwargs: Any) -> None:
        """Publishes event to the event bus."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                self.event_bus.publish(topic, **kwargs)
            except Exception as e:
                logger.debug("Error publishing '%s': %s", topic, e)
