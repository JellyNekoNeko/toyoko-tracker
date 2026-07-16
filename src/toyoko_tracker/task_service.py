from __future__ import annotations

import threading
import time
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Dict, Mapping, Optional

from . import workspace
from .provider_pacer import PacerCancelled
from .task_coordinator import CoordinatorCancelled
from .task_scheduler import TaskSchedulerKernel, TaskWorkItem


class TaskServiceError(RuntimeError):
    """Base error for the process-wide task scheduler service."""


class TaskBusyError(TaskServiceError):
    """Raised when a task still has work draining after a control request."""


class LastTaskError(TaskServiceError):
    """Raised when deleting the final compatibility task."""


def _serialized(method: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize task-definition mutations through the process service."""

    @wraps(method)
    def wrapped(self: "TaskSchedulerService", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapped


class TaskSchedulerService:
    """Own one background scheduler thread and the task mutation boundary."""

    def __init__(
        self,
        scan_one: Callable[[TaskWorkItem], Any],
        *,
        repository: Any = workspace,
        on_round_complete: Optional[
            Callable[[str, Mapping[str, Any], tuple[Any, ...]], None]
        ] = None,
        request_interval: Optional[Callable[[TaskWorkItem], float]] = None,
        log: Optional[Callable[[str], None]] = None,
        poll_interval: float = 0.25,
        drain_timeout: float = 5.0,
        kernel: Optional[TaskSchedulerKernel] = None,
    ) -> None:
        self.repository = repository
        self.kernel = kernel or TaskSchedulerKernel(
            scan_one,
            repository=repository,
            on_round_complete=on_round_complete,
            request_interval=request_interval,
        )
        self._log = log or (lambda _message: None)
        self._poll_interval = max(0.05, float(poll_interval))
        self._drain_timeout = max(0.1, float(drain_timeout))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = False

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self.running:
                return self.summary()
            reconciled = self.kernel.reconcile()
            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                args=(),
                name="task-coordinator",
                daemon=True,
            )
            self._thread.start()
            self._started = True
            self._log(
                "[tasks] coordinator started "
                f"with {len(reconciled['registered'])} registered task(s)"
            )
            return self.summary()

    def shutdown(self, timeout: float = 3.0) -> None:
        with self._lock:
            thread = self._thread
            self._stop_event.set()
            self._wake_event.set()
            self.kernel.cancel_in_flight()
        if thread and thread.is_alive():
            thread.join(timeout=max(0.0, float(timeout)))
        with self._lock:
            if thread is None or not thread.is_alive():
                self._thread = None
                self._started = False
            else:
                self._thread = thread
                self._started = True
                self._log("[tasks] coordinator is still draining during shutdown")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = self.kernel.run_next_turn(
                    cancel_event=self._stop_event,
                    timeout=self._poll_interval,
                )
                if result is None:
                    self._wake_event.wait(self._poll_interval)
                    self._wake_event.clear()
            except (CoordinatorCancelled, PacerCancelled):
                if self._stop_event.is_set():
                    break
            except Exception as exc:
                self._log(f"[tasks] scheduler turn failed: {exc}")
                self._stop_event.wait(0.2)

    def wake(self) -> None:
        self._wake_event.set()

    def _wait_until_idle(self, task_id: str) -> None:
        deadline = time.monotonic() + self._drain_timeout
        while time.monotonic() < deadline:
            if self.kernel.task_idle(task_id):
                return
            time.sleep(0.02)
        raise TaskBusyError(f"task is still draining: {task_id}")

    @staticmethod
    def _assert_expected_revision(
        task: Mapping[str, Any],
        expected_revision: Optional[int],
    ) -> None:
        if expected_revision is None:
            return
        try:
            expected = int(expected_revision)
        except (TypeError, ValueError) as exc:
            raise workspace.TaskValidationError(
                "expected_revision must be an integer"
            ) from exc
        current = int(task["revision"])
        if expected != current:
            raise workspace.TaskConflictError(
                f"task revision conflict: expected {expected}, current {current}"
            )

    def public_task(
        self,
        task_id: str,
        *,
        include_results: bool = False,
    ) -> Dict[str, Any]:
        task = self.repository.get_task(task_id)
        runtime = self.kernel.registry.get_or_create(
            task_id,
            task_record=task,
        ).snapshot()
        public = deepcopy(task)
        public.update({
            "progress": runtime["progress"],
            "run_id": runtime["run_id"],
            "run_started_at": runtime["run_started_at"],
            "draining": runtime["draining"],
            "cancel_requested": runtime["cancel_requested"],
            "results_revision": runtime["results_revision"],
            "result_count": len(runtime["results"]),
            "error_count": len(runtime["errors"]),
            "errors": runtime["errors"][-10:],
        })
        if include_results:
            public["results"] = runtime["results"]
        return public

    def list_tasks(self) -> list[Dict[str, Any]]:
        return [
            self.public_task(str(task["task_id"]))
            for task in self.repository.list_tasks()
        ]

    def summary(self) -> Dict[str, Any]:
        tasks = self.list_tasks()
        return {
            "task_count": len(tasks),
            "active_count": sum(
                1 for task in tasks if task["desired_state"] == "active"
            ),
            "running_count": sum(
                1 for task in tasks if task["runtime_state"] == "scanning"
            ),
            "paused_count": sum(
                1 for task in tasks if task["desired_state"] == "paused"
            ),
            "error_count": sum(
                1 for task in tasks if task["runtime_state"] == "error"
            ),
            "provider_pacer": self.kernel.pacer.snapshot(),
            "service_running": self.running,
        }

    @_serialized
    def create_task(
        self,
        name: str,
        config: Mapping[str, Any],
        *,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        task = self.repository.create_task(
            name,
            config,
            task_id=task_id,
            desired_state="paused",
        )
        try:
            self.kernel.sync_task(task["task_id"])
        except workspace.TaskValidationError:
            pass
        self.wake()
        return self.public_task(task["task_id"])

    @_serialized
    def duplicate_task(
        self,
        task_id: str,
        *,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        task = self.repository.duplicate_task(task_id, name=name)
        self.kernel.sync_task(task["task_id"])
        return self.public_task(task["task_id"])

    @_serialized
    def update_task(
        self,
        task_id: str,
        *,
        name: Optional[str] = None,
        config: Optional[Mapping[str, Any]] = None,
        replace_config: bool = False,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        current = self.repository.get_task(task_id)
        self._assert_expected_revision(current, expected_revision)
        if config is None:
            updated = self.repository.update_task(
                task_id,
                name=name,
                expected_revision=current["revision"],
            )
            self.kernel.registry.get_or_create(
                task_id,
                task_record=updated,
            )
            return self.public_task(task_id)

        was_active = current["desired_state"] == "active"
        runtime = self.kernel.registry.get_or_create(
            task_id,
            task_record=current,
        ).snapshot()
        if was_active or runtime.get("run_id"):
            self.kernel.pause(task_id)
            self._wait_until_idle(task_id)
            current = self.repository.get_task(task_id)
        updated = self.repository.update_task(
            task_id,
            name=name,
            config=config,
            replace_config=replace_config,
            desired_state="active" if was_active else None,
            expected_revision=current["revision"],
        )
        self.kernel.sync_task(task_id)
        self.wake()
        return self.public_task(updated["task_id"])

    @_serialized
    def replace_config_and_start(
        self,
        task_id: str,
        config: Mapping[str, Any],
        *,
        run_once: bool = False,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        current = self.repository.get_task(task_id)
        self._assert_expected_revision(current, expected_revision)
        restarted = bool(
            current["desired_state"] == "active"
            or current["runtime_state"] in {"queued", "scanning", "waiting", "pausing"}
        )
        runtime = self.kernel.registry.get_or_create(
            task_id,
            task_record=current,
        ).snapshot()
        if restarted or runtime.get("run_id"):
            self.kernel.pause(task_id)
            self._wait_until_idle(task_id)
            current = self.repository.get_task(task_id)
        updated = self.repository.update_task(
            task_id,
            config=config,
            replace_config=True,
            desired_state="paused" if run_once else "active",
            expected_revision=current["revision"],
        )
        self.kernel.sync_task(task_id)
        if run_once:
            self.kernel.activate(task_id, run_once=True)
        self.wake()
        return {
            "task": self.public_task(updated["task_id"]),
            "restarted": restarted,
            "run_once": bool(run_once),
        }

    @_serialized
    def activate(
        self,
        task_id: str,
        *,
        run_once: bool = False,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        current = self.repository.get_task(task_id)
        self._assert_expected_revision(current, expected_revision)
        result = self.kernel.activate(task_id, run_once=run_once)
        self.wake()
        return {
            "task": self.public_task(task_id),
            "schedule": result["schedule"],
            "run_once": bool(run_once),
        }

    @_serialized
    def pause(
        self,
        task_id: str,
        *,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        current = self.repository.get_task(task_id)
        self._assert_expected_revision(current, expected_revision)
        result = self.kernel.pause(task_id)
        self.wake()
        return {
            "task": self.public_task(task_id),
            "schedule": result["schedule"],
        }

    @_serialized
    def delete_task(
        self,
        task_id: str,
        *,
        expected_revision: Optional[int] = None,
    ) -> Dict[str, Any]:
        tasks = self.repository.list_tasks()
        if len(tasks) <= 1:
            raise LastTaskError("the final compatibility task must be retained")
        current = self.repository.get_task(task_id)
        self._assert_expected_revision(current, expected_revision)
        runtime = self.kernel.registry.get_or_create(
            task_id,
            task_record=current,
        ).snapshot()
        if current["desired_state"] == "active" or runtime.get("run_id"):
            self.kernel.pause(task_id)
            self._wait_until_idle(task_id)
            current = self.repository.get_task(task_id)
        self.kernel.remove_task(task_id)
        return self.repository.delete_task(
            task_id,
            expected_revision=current["revision"],
        )

    @_serialized
    def reorder(
        self,
        task_ids: list[str],
        *,
        expected_revisions: Optional[Mapping[str, int]] = None,
    ) -> list[Dict[str, Any]]:
        reordered = self.repository.reorder_tasks(
            task_ids,
            expected_revisions=expected_revisions,
        )
        for task in reordered:
            self.kernel.registry.get_or_create(
                task["task_id"],
                task_record=task,
            )
        return [self.public_task(task["task_id"]) for task in reordered]


__all__ = [
    "LastTaskError",
    "TaskBusyError",
    "TaskSchedulerService",
    "TaskServiceError",
]
