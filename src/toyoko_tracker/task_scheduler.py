from __future__ import annotations

import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from . import workspace
from .provider_pacer import provider_pacer
from .task_coordinator import TaskCoordinator, TaskCoordinatorError, TaskTurn
from .task_runtime import TaskRuntimeRegistry


@dataclass(frozen=True)
class TaskWorkItem:
    task_id: str
    run_id: str
    hotel_code: str
    provider: str
    round_no: int
    config: Dict[str, Any]
    cancel_event: threading.Event


@dataclass(frozen=True)
class TaskTurnResult:
    turn: TaskTurn
    run_id: str
    results: Tuple[Any, ...]
    task: Dict[str, Any]
    round_completed: bool


class TaskSchedulerKernel:
    """Synchronous integration boundary for coordinator, contexts and storage.

    A later lifecycle worker can repeatedly call :meth:`run_next_turn`; tests
    can drive the same method deterministically without background threads.
    """

    def __init__(
        self,
        scan_one: Callable[[TaskWorkItem], Any],
        *,
        repository: Any = workspace,
        registry: Optional[TaskRuntimeRegistry] = None,
        coordinator: Optional[TaskCoordinator] = None,
        pacer: Any = provider_pacer,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not callable(scan_one):
            raise ValueError("scan_one must be callable")
        self._scan_one = scan_one
        self._repository = repository
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self.registry = registry or TaskRuntimeRegistry(
            repository=repository,
            clock=wall_clock,
        )
        self.coordinator = coordinator or TaskCoordinator()
        self.pacer = pacer
        self._lock = threading.RLock()
        self._run_once_tasks: set[str] = set()

    def _to_monotonic(self, wall_timestamp: Any) -> Optional[float]:
        if wall_timestamp is None:
            return None
        delay = max(0.0, float(wall_timestamp) - float(self._wall_clock()))
        return float(self._monotonic_clock()) + delay

    def _to_wall(self, monotonic_timestamp: Any) -> Optional[float]:
        if monotonic_timestamp is None:
            return None
        delay = max(
            0.0,
            float(monotonic_timestamp) - float(self._monotonic_clock()),
        )
        return float(self._wall_clock()) + delay

    @staticmethod
    def _priority_hotels(config: Mapping[str, Any]) -> Tuple[str, ...]:
        return tuple(
            str(hotel.get("code"))
            for hotel in config.get("selected_hotels") or []
            if isinstance(hotel, Mapping)
            and hotel.get("code")
            and bool(hotel.get("priority"))
        )

    @staticmethod
    def _provider(config: Mapping[str, Any], hotel_code: str) -> str:
        for hotel in config.get("selected_hotels") or []:
            if not isinstance(hotel, Mapping):
                continue
            if str(hotel.get("code") or "") == hotel_code:
                provider = str(hotel.get("provider") or "").strip()
                if provider:
                    return provider
        prefix = hotel_code.split(":", 1)[0]
        return prefix if prefix in workspace.SUPPORTED_PROVIDERS else "toyoko"

    def _register_record(self, task: Mapping[str, Any]) -> Dict[str, Any]:
        config = dict(task.get("config") or {})
        hotel_codes = tuple(str(code) for code in config.get("hotel_codes") or [])
        if not hotel_codes:
            raise workspace.TaskValidationError(
                f"task has no hotels: {task.get('task_id')}"
            )
        return self.coordinator.register_task(
            str(task["task_id"]),
            hotel_codes,
            cadence_seconds=float(config.get("loop_interval_seconds") or 30),
            next_run_at=self._to_monotonic(task.get("next_run_at")),
            desired_state=str(task.get("desired_state") or "paused"),
            priority_hotels=self._priority_hotels(config),
            batch_size=1,
        )

    def reconcile(self) -> Dict[str, Any]:
        """Recover durable state and rebuild the in-memory ready queue."""
        with self._lock:
            self._run_once_tasks.clear()
            recovery = self.registry.recover()
            for task_id in tuple(self.coordinator.snapshot()["tasks"]):
                self.coordinator.unregister_task(task_id)
            registered: Dict[str, Dict[str, Any]] = {}
            registration_errors: Dict[str, str] = {}
            for task in self._repository.list_tasks():
                task_id = str(task["task_id"])
                try:
                    registered[task_id] = self._register_record(task)
                except (TaskCoordinatorError, workspace.TaskValidationError) as exc:
                    message = str(exc)
                    registration_errors[task_id] = message
                    runtime_state = (
                        "error"
                        if task.get("desired_state") == "active"
                        else "idle"
                    )
                    updated = self._repository.set_task_runtime_state(
                        task_id,
                        runtime_state,
                        next_run_at=None,
                        last_error=message,
                    )
                    self.registry.get_or_create(
                        task_id,
                        task_record=updated,
                    )
            return {
                "recovery": recovery,
                "registered": registered,
                "registration_errors": registration_errors,
                "scheduler": self.snapshot(),
            }

    def activate(self, task_id: str, *, run_once: bool = False) -> Dict[str, Any]:
        """Activate a durable task and make it eligible for a scheduler turn."""
        with self._lock:
            if run_once:
                task = self._repository.get_task(task_id)
                self.registry.get_or_create(task_id, task_record=task)
                self.registry.mark_queued(task_id)
                self._run_once_tasks.add(str(task_id))
            else:
                self._run_once_tasks.discard(str(task_id))
                self.registry.activate(task_id)
                task = self._repository.get_task(task_id)
            try:
                scheduled = self.coordinator.activate_task(task_id)
            except TaskCoordinatorError:
                self._register_record(task)
                if run_once or task["desired_state"] == "active":
                    scheduled = self.coordinator.activate_task(task_id)
                else:
                    scheduled = self.coordinator.task_snapshot(task_id)
            return {
                "task": self.registry.snapshot(task_id),
                "schedule": scheduled,
                "run_once": bool(run_once),
            }

    def pause(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            self._run_once_tasks.discard(str(task_id))
            runtime = self.registry.request_pause(task_id)
            try:
                schedule = self.coordinator.pause_task(task_id)
            except TaskCoordinatorError:
                schedule = None
            return {"task": runtime, "schedule": schedule}

    def _begin_or_resume_run(self, task_id: str) -> Tuple[str, int, Dict[str, Any]]:
        context = self.registry.get_or_create(task_id)
        snapshot = context.snapshot()
        if snapshot["run_id"]:
            return (
                str(snapshot["run_id"]),
                int(snapshot["progress"].get("round") or 1),
                snapshot,
            )
        run = self.registry.begin_run(task_id)
        snapshot = context.snapshot()
        round_no = int(context.checkpoint("round_no", 0)) + 1
        context.set_checkpoint("round_no", round_no)
        context.replace_progress({
            "round": round_no,
            "done": 0,
            "total": len(snapshot["config"].get("hotel_codes") or []),
        })
        return str(run["run_id"]), round_no, context.snapshot()

    def run_next_turn(
        self,
        *,
        cancel_event: Optional[Any] = None,
        timeout: Optional[float] = 0,
    ) -> Optional[TaskTurnResult]:
        turn = self.coordinator.next_turn(
            cancel_event=cancel_event,
            timeout=timeout,
        )
        if turn is None:
            return None

        with self._lock:
            run_id, round_no, context_snapshot = self._begin_or_resume_run(
                turn.task_id
            )
            context = self.registry.get_or_create(turn.task_id)
            config = deepcopy(context_snapshot["config"])
            before = self.coordinator.task_snapshot(turn.task_id)
        collected = []
        try:
            for hotel_code in turn.hotels:
                if turn.cancel_event.is_set():
                    break
                item = TaskWorkItem(
                    task_id=turn.task_id,
                    run_id=run_id,
                    hotel_code=hotel_code,
                    provider=self._provider(config, hotel_code),
                    round_no=round_no,
                    config=deepcopy(config),
                    cancel_event=turn.cancel_event,
                )
                with self.pacer.acquire(
                    item.provider,
                    task_id=item.task_id,
                    cancel_event=item.cancel_event,
                ):
                    result = self._scan_one(item)
                status = (
                    result.get("http_status")
                    if isinstance(result, Mapping)
                    else getattr(result, "http_status", None)
                )
                retry_after = (
                    result.get("retry_after_sec")
                    if isinstance(result, Mapping)
                    else getattr(result, "retry_after_sec", None)
                )
                if status is not None:
                    self.pacer.report_response(
                        item.provider,
                        int(status),
                        retry_after=retry_after,
                    )
                collected.append(deepcopy(result))
                context.append_result(result)
                progress = context.snapshot()["progress"]
                context.update_progress(done=int(progress.get("done") or 0) + 1)
        except Exception as exc:
            with self._lock:
                if turn.cancel_event.is_set():
                    self.coordinator.complete_turn(turn)
                    self.registry.finish_run(
                        turn.task_id,
                        state="cancelled",
                        result_summary={
                            "completed": len(context.snapshot()["results"]),
                            "total": int(
                                context.snapshot()["progress"].get("total") or 0
                            ),
                        },
                        next_run_at=None,
                    )
                    return TaskTurnResult(
                        turn=turn,
                        run_id=run_id,
                        results=tuple(collected),
                        task=self.registry.snapshot(turn.task_id),
                        round_completed=False,
                    )
                context.append_error(
                    exc,
                    details={"turn_id": turn.turn_id, "hotels": list(turn.hotels)},
                )
                schedule = self.coordinator.fail_turn(
                    turn,
                    exc,
                )
                if turn.task_id in self._run_once_tasks:
                    self._run_once_tasks.discard(turn.task_id)
                    schedule = self.coordinator.pause_task(turn.task_id)
                self.registry.finish_run(
                    turn.task_id,
                    state="failed",
                    result_summary={
                        "completed": len(context.snapshot()["results"]),
                        "total": int(context.snapshot()["progress"].get("total") or 0),
                    },
                    error=str(exc),
                    next_run_at=self._to_wall(schedule.get("next_run_at")),
                )
                raise

        with self._lock:
            schedule = self.coordinator.complete_turn(
                turn,
            )
            round_completed = (
                int(schedule["rounds_completed"])
                > int(before["rounds_completed"])
            )
            if round_completed and turn.task_id in self._run_once_tasks:
                self._run_once_tasks.discard(turn.task_id)
                schedule = self.coordinator.pause_task(turn.task_id)
            if schedule["desired_state"] == "paused":
                self.registry.finish_run(
                    turn.task_id,
                    state="complete" if round_completed else "cancelled",
                    result_summary={
                        "completed": len(context.snapshot()["results"]),
                        "total": int(context.snapshot()["progress"].get("total") or 0),
                    },
                    next_run_at=None,
                )
            elif round_completed:
                results = context.snapshot()["results"]
                self.registry.finish_run(
                    turn.task_id,
                    state="complete",
                    result_summary={
                        "completed": len(results),
                        "total": int(context.snapshot()["progress"].get("total") or 0),
                    },
                    next_run_at=self._to_wall(schedule.get("next_run_at")),
                )
            return TaskTurnResult(
                turn=turn,
                run_id=run_id,
                results=tuple(collected),
                task=self.registry.snapshot(turn.task_id),
                round_completed=round_completed,
            )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "coordinator": self.coordinator.snapshot(),
            "runtime": self.registry.snapshot_all(),
        }


__all__ = [
    "TaskSchedulerKernel",
    "TaskTurnResult",
    "TaskWorkItem",
]
