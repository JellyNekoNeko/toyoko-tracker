from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any, Callable, Dict, List, Mapping, Optional

from . import workspace


class TaskRuntimeError(RuntimeError):
    """Base error for in-memory task runtime operations."""


class TaskRunActiveError(TaskRuntimeError):
    """Raised when a second run is started for the same task."""


class TaskRunMismatchError(TaskRuntimeError):
    """Raised when a caller tries to finish a different task run."""


class TaskRuntimeContext:
    """Thread-safe, task-local mutable state used by one coordinator."""

    def __init__(
        self,
        task_id: str,
        *,
        runtime_state: str = "idle",
        task_record: Optional[Mapping[str, Any]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        cleaned_task_id = str(task_id or "").strip()
        if not cleaned_task_id:
            raise ValueError("task_id is required")
        if runtime_state not in workspace.RUNTIME_TASK_STATES:
            raise ValueError("runtime_state is not supported")
        self.task_id = cleaned_task_id
        self.cancel_event = threading.Event()
        self._clock = clock
        self._lock = threading.RLock()
        self._runtime_state = runtime_state
        self._name = ""
        self._config: Dict[str, Any] = {}
        self._revision = 0
        self._runtime_revision = 0
        self._desired_state = "paused"
        self._next_run_at: Optional[float] = None
        self._last_error = ""
        self._run_id: Optional[str] = None
        self._run_started_at: Optional[float] = None
        self._draining = False
        self._progress: Dict[str, Any] = {}
        self._results: List[Any] = []
        self._results_revision = 0
        self._errors: List[Dict[str, Any]] = []
        self._checkpoints: Dict[str, Any] = {}
        if task_record is not None:
            self.apply_task_record(task_record)

    def apply_task_record(self, task: Mapping[str, Any]) -> None:
        """Refresh the durable definition without sharing mutable references."""
        task_id = str(task.get("task_id") or "").strip()
        if task_id and task_id != self.task_id:
            raise ValueError("task record does not match context task_id")
        desired_state = str(task.get("desired_state") or "paused")
        runtime_state = str(task.get("runtime_state") or self._runtime_state)
        if desired_state not in workspace.DESIRED_TASK_STATES:
            raise ValueError("desired_state is not supported")
        if runtime_state not in workspace.RUNTIME_TASK_STATES:
            raise ValueError("runtime_state is not supported")
        with self._lock:
            self._name = str(task.get("name") or "")
            self._config = deepcopy(dict(task.get("config") or {}))
            self._revision = int(task.get("revision") or 0)
            self._runtime_revision = int(task.get("runtime_revision") or 0)
            self._desired_state = desired_state
            self._runtime_state = runtime_state
            next_run_at = task.get("next_run_at")
            self._next_run_at = (
                None if next_run_at is None else float(next_run_at)
            )
            self._last_error = str(task.get("last_error") or "")

    def assert_can_begin(self) -> None:
        with self._lock:
            if self._run_id is not None:
                raise TaskRunActiveError(
                    f"task already has an active run: {self.task_id}"
                )

    def begin_run(self, run_id: str, *, started_at: Optional[float] = None) -> None:
        cleaned_run_id = str(run_id or "").strip()
        if not cleaned_run_id:
            raise ValueError("run_id is required")
        with self._lock:
            if self._run_id is not None:
                raise TaskRunActiveError(
                    f"task already has an active run: {self.task_id}"
                )
            self.cancel_event.clear()
            self._draining = False
            self._runtime_state = "scanning"
            self._run_id = cleaned_run_id
            self._run_started_at = (
                self._clock() if started_at is None else float(started_at)
            )
            self._progress = {}
            self._results = []
            self._results_revision += 1
            self._errors = []

    def end_run(self, run_id: str, *, runtime_state: str) -> None:
        if runtime_state not in workspace.RUNTIME_TASK_STATES:
            raise ValueError("runtime_state is not supported")
        with self._lock:
            if self._run_id != str(run_id or "").strip():
                raise TaskRunMismatchError(
                    f"active run mismatch for task: {self.task_id}"
                )
            self._runtime_state = runtime_state
            self._run_id = None
            self._run_started_at = None
            self._draining = False
            self.cancel_event.clear()

    def mark_queued(self) -> None:
        with self._lock:
            if self._run_id is not None:
                raise TaskRunActiveError(
                    f"task already has an active run: {self.task_id}"
                )
            self.cancel_event.clear()
            self._draining = False
            self._runtime_state = "queued"

    def request_pause(self) -> str:
        with self._lock:
            self.cancel_event.set()
            if self._run_id is None:
                self._runtime_state = "idle"
                self._draining = False
            else:
                self._runtime_state = "pausing"
                self._draining = True
            return self._runtime_state

    def signal_cancel(self) -> None:
        """Wake cancellable waits while a registry is being replaced."""
        self.cancel_event.set()

    def update_progress(
        self,
        values: Optional[Mapping[str, Any]] = None,
        **fields: Any,
    ) -> None:
        updates = dict(values or {})
        updates.update(fields)
        with self._lock:
            self._progress.update(deepcopy(updates))

    def replace_progress(self, progress: Mapping[str, Any]) -> None:
        with self._lock:
            self._progress = deepcopy(dict(progress))

    def append_result(self, result: Any) -> None:
        with self._lock:
            self._results.append(deepcopy(result))
            self._results_revision += 1

    def replace_results(self, results: List[Any]) -> None:
        with self._lock:
            self._results = deepcopy(list(results))
            self._results_revision += 1

    def append_error(
        self,
        error: Any,
        *,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        record = {
            "message": str(error),
            "recorded_at": float(self._clock()),
            "details": deepcopy(dict(details or {})),
        }
        with self._lock:
            self._errors.append(record)

    def set_checkpoint(self, name: str, value: Any) -> None:
        cleaned_name = str(name or "").strip()
        if not cleaned_name:
            raise ValueError("checkpoint name is required")
        with self._lock:
            self._checkpoints[cleaned_name] = deepcopy(value)

    def update_checkpoints(self, values: Mapping[str, Any]) -> None:
        for name, value in dict(values).items():
            self.set_checkpoint(str(name), value)

    def checkpoint(self, name: str, default: Any = None) -> Any:
        with self._lock:
            return deepcopy(self._checkpoints.get(name, default))

    def clear_checkpoints(self) -> None:
        with self._lock:
            self._checkpoints = {}

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "task_id": self.task_id,
                "name": self._name,
                "config": deepcopy(self._config),
                "revision": self._revision,
                "runtime_revision": self._runtime_revision,
                "desired_state": self._desired_state,
                "runtime_state": self._runtime_state,
                "next_run_at": self._next_run_at,
                "last_error": self._last_error,
                "run_id": self._run_id,
                "run_started_at": self._run_started_at,
                "draining": self._draining,
                "cancel_requested": self.cancel_event.is_set(),
                "progress": deepcopy(self._progress),
                "results": deepcopy(self._results),
                "results_revision": self._results_revision,
                "errors": deepcopy(self._errors),
                "checkpoints": deepcopy(self._checkpoints),
            }


class TaskRuntimeRegistry:
    """Owns process-local contexts and coordinates their durable run records."""

    def __init__(
        self,
        *,
        repository: Any = workspace,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._lock = threading.RLock()
        self._contexts: Dict[str, TaskRuntimeContext] = {}

    def get_or_create(
        self,
        task_id: str,
        *,
        runtime_state: str = "idle",
        task_record: Optional[Mapping[str, Any]] = None,
    ) -> TaskRuntimeContext:
        cleaned_task_id = str(task_id or "").strip()
        if not cleaned_task_id:
            raise ValueError("task_id is required")
        with self._lock:
            context = self._contexts.get(cleaned_task_id)
            if context is None:
                if task_record is not None:
                    record = task_record
                else:
                    try:
                        record = self._repository.get_task(cleaned_task_id)
                    except workspace.TaskNotFoundError:
                        record = {
                            "task_id": cleaned_task_id,
                            "runtime_state": runtime_state,
                        }
                context = TaskRuntimeContext(
                    cleaned_task_id,
                    runtime_state=runtime_state,
                    task_record=record,
                    clock=self._clock,
                )
                self._contexts[cleaned_task_id] = context
            elif task_record is not None:
                context.apply_task_record(task_record)
            return context

    def snapshot(self, task_id: str) -> Dict[str, Any]:
        return self.get_or_create(task_id).snapshot()

    def snapshot_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            contexts = list(self._contexts.items())
        return {task_id: context.snapshot() for task_id, context in contexts}

    def mark_queued(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            context = self.get_or_create(task_id)
            task = self._repository.set_task_runtime_state(task_id, "queued")
            context.mark_queued()
            context.apply_task_record(task)
            return context.snapshot()

    def activate(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._repository.set_task_desired_state(task_id, "active")
            self.get_or_create(task_id).apply_task_record(task)
            return self.mark_queued(task_id)

    def begin_run(
        self,
        task_id: str,
        *,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            context = self.get_or_create(task_id)
            context.assert_can_begin()
            started_at = float(self._clock())
            run = self._repository.start_task_run(
                task_id,
                run_id=run_id,
                state="running",
                started_at=started_at,
            )
            try:
                context.begin_run(run["run_id"], started_at=started_at)
                task = self._repository.set_task_runtime_state(task_id, "scanning")
                context.apply_task_record(task)
            except Exception:
                try:
                    self._repository.finish_task_run(
                        run["run_id"],
                        state="interrupted",
                        error="run setup failed",
                        completed_at=float(self._clock()),
                    )
                finally:
                    if context.snapshot()["run_id"] == run["run_id"]:
                        context.end_run(run["run_id"], runtime_state="error")
                raise
            return run

    def finish_run(
        self,
        task_id: str,
        *,
        state: str = "complete",
        result_summary: Optional[Mapping[str, Any]] = None,
        error: str = "",
        next_run_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            context = self.get_or_create(task_id)
            current = context.snapshot()
            run_id = current["run_id"]
            if not run_id:
                raise TaskRunMismatchError(
                    f"task has no active run: {str(task_id or '').strip()}"
                )
            completed = self._repository.finish_task_run(
                run_id,
                state=state,
                result_summary=result_summary,
                error=error,
                completed_at=float(self._clock()),
            )
            task = self._repository.get_task(task_id)
            if task["desired_state"] == "paused":
                runtime_state = "idle"
                durable_next_run_at = None
            elif state == "failed":
                runtime_state = "error"
                durable_next_run_at = next_run_at
            else:
                runtime_state = "waiting"
                durable_next_run_at = next_run_at
            try:
                updated_task = self._repository.set_task_runtime_state(
                    task_id,
                    runtime_state,
                    next_run_at=durable_next_run_at,
                    last_error=error,
                    result_summary=result_summary or {},
                )
                context.apply_task_record(updated_task)
            finally:
                context.end_run(run_id, runtime_state=runtime_state)
            return completed

    def request_pause(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            context = self.get_or_create(task_id)
            task = self._repository.set_task_desired_state(task_id, "paused")
            context.apply_task_record(task)
            runtime_state = context.request_pause()
            task = self._repository.set_task_runtime_state(
                task_id,
                runtime_state,
                next_run_at=None,
            )
            context.apply_task_record(task)
            return context.snapshot()

    def recover(self) -> Dict[str, Any]:
        """Rebuild contexts from durable desired state after process startup."""
        with self._lock:
            for context in self._contexts.values():
                context.signal_cancel()

            recovered: Dict[str, TaskRuntimeContext] = {}
            interrupted = self._repository.interrupt_active_task_runs(
                completed_at=float(self._clock()),
                error="application restarted before the run completed",
            )
            interrupted_run_ids = [str(run["run_id"]) for run in interrupted]
            tasks = self._repository.list_tasks()
            for task in tasks:
                task_id = str(task["task_id"])
                next_run_at = task.get("next_run_at")
                if task["desired_state"] != "active":
                    runtime_state = "idle"
                    next_run_at = None
                elif (
                    next_run_at is not None
                    and float(next_run_at) > float(self._clock())
                ):
                    runtime_state = "waiting"
                else:
                    runtime_state = "queued"
                task = self._repository.set_task_runtime_state(
                    task_id,
                    runtime_state,
                    next_run_at=next_run_at,
                )
                recovered[task_id] = TaskRuntimeContext(
                    task_id,
                    runtime_state=runtime_state,
                    task_record=task,
                    clock=self._clock,
                )

            self._contexts = recovered
            return {
                "task_count": len(recovered),
                "interrupted_run_ids": interrupted_run_ids,
                "contexts": self.snapshot_all(),
            }


TaskContext = TaskRuntimeContext
TaskRuntimeManager = TaskRuntimeRegistry

__all__ = [
    "TaskContext",
    "TaskRunActiveError",
    "TaskRunMismatchError",
    "TaskRuntimeContext",
    "TaskRuntimeError",
    "TaskRuntimeManager",
    "TaskRuntimeRegistry",
]
