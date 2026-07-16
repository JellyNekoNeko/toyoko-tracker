from __future__ import annotations

import heapq
import math
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

from .workspace import (
    DESIRED_TASK_STATES as DESIRED_STATES,
)


class CoordinatorCancelled(RuntimeError):
    """Raised when a caller cancels while waiting for a coordinator turn."""


class TaskCoordinatorError(RuntimeError):
    """Base error for invalid coordinator operations."""


@dataclass(frozen=True)
class TaskTurn:
    """One bounded unit of work selected by the coordinator."""

    turn_id: str
    task_id: str
    hotels: Tuple[str, ...]
    scheduled_for: float
    issued_at: float
    priority: bool
    cancel_event: threading.Event = field(compare=False, repr=False)


@dataclass
class _TaskSchedule:
    task_id: str
    hotels: Tuple[str, ...]
    priority_hotels: Tuple[str, ...]
    cadence_seconds: float
    batch_size: int
    desired_state: str
    runtime_state: str
    next_run_at: Optional[float]
    target_at: Optional[float]
    regular_queue: Deque[str] = field(default_factory=deque)
    priority_queue: Deque[str] = field(default_factory=deque)
    priority_streak: int = 0
    generation: int = 0
    queued_generation: Optional[int] = None
    in_flight_turn_id: Optional[str] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    resume_at: Optional[float] = None
    last_error: str = ""
    turns_completed: int = 0
    rounds_completed: int = 0


class TaskCoordinator:
    """Fair, process-wide scheduler for recurring monitoring tasks.

    Time values are monotonic seconds. Durable wall-clock timestamps are mapped
    to the process monotonic clock by the runtime layer before registration.
    """

    def __init__(
        self,
        *,
        max_turn_batch_size: int = 4,
        max_priority_turns: int = 2,
        max_consecutive_task_turns: int = 2,
        cancellation_poll_interval: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        if int(max_turn_batch_size) < 1:
            raise ValueError("max_turn_batch_size must be at least 1")
        if int(max_priority_turns) < 1:
            raise ValueError("max_priority_turns must be at least 1")
        if int(max_consecutive_task_turns) < 1:
            raise ValueError("max_consecutive_task_turns must be at least 1")
        if float(cancellation_poll_interval) <= 0:
            raise ValueError("cancellation_poll_interval must be positive")

        self.max_turn_batch_size = int(max_turn_batch_size)
        self.max_priority_turns = int(max_priority_turns)
        self.max_consecutive_task_turns = int(max_consecutive_task_turns)
        self.cancellation_poll_interval = float(cancellation_poll_interval)
        self._clock = clock
        self._wait = wait
        self._lock = threading.RLock()
        self._tasks: Dict[str, _TaskSchedule] = {}
        self._ready_heap: List[Tuple[float, int, str, int]] = []
        self._ticket = 0
        self._last_selected_task_id: Optional[str] = None
        self._consecutive_task_turns = 0

    @staticmethod
    def _task_id(value: str) -> str:
        task_id = str(value or "").strip()
        if not task_id:
            raise ValueError("task_id must be non-empty")
        return task_id

    @staticmethod
    def _hotel_list(values: Iterable[Any], field_name: str) -> Tuple[str, ...]:
        hotels: List[str] = []
        seen = set()
        for value in values:
            hotel = str(value or "").strip()
            if not hotel:
                raise ValueError(f"{field_name} must contain non-empty values")
            if hotel in seen:
                raise ValueError(f"{field_name} must not contain duplicates")
            seen.add(hotel)
            hotels.append(hotel)
        if field_name == "hotels" and not hotels:
            raise ValueError("hotels must contain at least one hotel")
        return tuple(hotels)

    @staticmethod
    def _is_cancelled(cancel_event: Optional[Any]) -> bool:
        return bool(cancel_event is not None and cancel_event.is_set())

    @staticmethod
    def next_cadence_at(
        previous_target: float,
        cadence_seconds: float,
        completed_at: float,
    ) -> float:
        """Return the first cadence target strictly after completion.

        Missed cadence points are skipped, so a slow run never produces a
        burst of immediate catch-up runs.
        """

        target = float(previous_target)
        cadence = float(cadence_seconds)
        completed = float(completed_at)
        if not math.isfinite(target) or not math.isfinite(completed):
            raise ValueError("cadence timestamps must be finite")
        if not math.isfinite(cadence) or cadence <= 0:
            raise ValueError("cadence_seconds must be positive")

        candidate = target + cadence
        if candidate <= completed:
            skipped = math.floor((completed - candidate) / cadence) + 1
            candidate += skipped * cadence
        return candidate

    def _next_ticket(self) -> int:
        self._ticket += 1
        return self._ticket

    def _reset_round(self, task: _TaskSchedule) -> None:
        priority_set = set(task.priority_hotels)
        task.priority_queue = deque(task.priority_hotels)
        task.regular_queue = deque(
            hotel for hotel in task.hotels if hotel not in priority_set
        )
        task.priority_streak = 0

    def _enqueue(self, task: _TaskSchedule, ready_at: float) -> None:
        task.generation += 1
        task.queued_generation = task.generation
        task.next_run_at = float(ready_at)
        heapq.heappush(
            self._ready_heap,
            (
                float(ready_at),
                self._next_ticket(),
                task.task_id,
                task.generation,
            ),
        )

    def _invalidate_queue(self, task: _TaskSchedule) -> None:
        task.generation += 1
        task.queued_generation = None

    def register_task(
        self,
        task_id: str,
        hotels: Sequence[Any],
        *,
        cadence_seconds: float,
        next_run_at: Optional[float] = None,
        desired_state: str = "active",
        priority_hotels: Sequence[Any] = (),
        batch_size: int = 1,
    ) -> Dict[str, Any]:
        """Register one recurring task and return its public state."""

        cleaned_id = self._task_id(task_id)
        cleaned_hotels = self._hotel_list(hotels, "hotels")
        cleaned_priority = self._hotel_list(priority_hotels, "priority_hotels")
        unknown_priority = set(cleaned_priority).difference(cleaned_hotels)
        if unknown_priority:
            raise ValueError("priority_hotels must be included in hotels")
        cadence = float(cadence_seconds)
        if not math.isfinite(cadence) or cadence <= 0:
            raise ValueError("cadence_seconds must be positive")
        desired = str(desired_state)
        if desired not in DESIRED_STATES:
            raise ValueError("desired_state must be paused or active")
        cleaned_batch_size = int(batch_size)
        if not 1 <= cleaned_batch_size <= self.max_turn_batch_size:
            raise ValueError(
                f"batch_size must be between 1 and {self.max_turn_batch_size}"
            )

        now = float(self._clock())
        ready_at = now if next_run_at is None else float(next_run_at)
        if not math.isfinite(ready_at):
            raise ValueError("next_run_at must be finite")
        with self._lock:
            if cleaned_id in self._tasks:
                raise TaskCoordinatorError(f"task already registered: {cleaned_id}")
            task = _TaskSchedule(
                task_id=cleaned_id,
                hotels=cleaned_hotels,
                priority_hotels=cleaned_priority,
                cadence_seconds=cadence,
                batch_size=cleaned_batch_size,
                desired_state=desired,
                runtime_state="idle",
                next_run_at=None,
                target_at=None,
            )
            self._tasks[cleaned_id] = task
            if desired == "active":
                self._reset_round(task)
                task.target_at = ready_at
                task.runtime_state = "queued" if ready_at <= now else "waiting"
                self._enqueue(task, ready_at)
            return self._task_snapshot(task)

    def unregister_task(self, task_id: str) -> Dict[str, Any]:
        cleaned_id = self._task_id(task_id)
        with self._lock:
            task = self._get_task(cleaned_id)
            task.cancel_event.set()
            self._invalidate_queue(task)
            snapshot = self._task_snapshot(task)
            del self._tasks[cleaned_id]
            return snapshot

    def _get_task(self, task_id: str) -> _TaskSchedule:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise TaskCoordinatorError(f"task not registered: {task_id}") from exc

    def activate_task(
        self,
        task_id: str,
        *,
        next_run_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        cleaned_id = self._task_id(task_id)
        now = float(self._clock())
        ready_at = now if next_run_at is None else float(next_run_at)
        if not math.isfinite(ready_at):
            raise ValueError("next_run_at must be finite")
        with self._lock:
            task = self._get_task(cleaned_id)
            was_active = task.desired_state == "active"
            task.desired_state = "active"
            task.last_error = ""
            if task.in_flight_turn_id is not None:
                if was_active:
                    return self._task_snapshot(task)
                task.cancel_event = threading.Event()
                task.resume_at = ready_at
                task.runtime_state = "pausing"
                return self._task_snapshot(task)

            task.cancel_event = threading.Event()
            self._invalidate_queue(task)
            self._reset_round(task)
            task.target_at = ready_at
            task.resume_at = None
            task.runtime_state = "queued" if ready_at <= now else "waiting"
            self._enqueue(task, ready_at)
            return self._task_snapshot(task)

    def pause_task(self, task_id: str) -> Dict[str, Any]:
        """Remove future work and signal cancellation to an issued turn."""

        cleaned_id = self._task_id(task_id)
        with self._lock:
            task = self._get_task(cleaned_id)
            task.desired_state = "paused"
            task.cancel_event.set()
            task.resume_at = None
            self._invalidate_queue(task)
            task.regular_queue.clear()
            task.priority_queue.clear()
            task.next_run_at = None
            task.target_at = None
            if task.in_flight_turn_id is not None:
                task.runtime_state = "pausing"
            else:
                task.runtime_state = "idle"
            return self._task_snapshot(task)

    def _valid_heap_entry(
        self, entry: Tuple[float, int, str, int]
    ) -> Optional[_TaskSchedule]:
        _ready_at, _ticket, task_id, generation = entry
        task = self._tasks.get(task_id)
        if task is None:
            return None
        if task.desired_state != "active" or task.in_flight_turn_id is not None:
            return None
        if task.queued_generation != generation:
            return None
        return task

    def _clean_heap_head(self) -> None:
        while self._ready_heap and self._valid_heap_entry(self._ready_heap[0]) is None:
            heapq.heappop(self._ready_heap)

    def _pop_ready_task(self, now: float) -> Optional[Tuple[_TaskSchedule, float]]:
        self._clean_heap_head()
        if not self._ready_heap or self._ready_heap[0][0] > now:
            return None

        deferred: List[Tuple[float, int, str, int]] = []
        selected_entry = heapq.heappop(self._ready_heap)
        selected_task = self._valid_heap_entry(selected_entry)
        if selected_task is None:
            return self._pop_ready_task(now)

        priority_is_bounded = (
            selected_task.task_id == self._last_selected_task_id
            and self._consecutive_task_turns >= self.max_consecutive_task_turns
        )
        if priority_is_bounded:
            while self._ready_heap:
                candidate = heapq.heappop(self._ready_heap)
                candidate_task = self._valid_heap_entry(candidate)
                if candidate_task is None:
                    continue
                if candidate[0] > now:
                    deferred.append(candidate)
                    break
                if candidate_task.task_id != selected_task.task_id:
                    deferred.append(selected_entry)
                    selected_entry = candidate
                    selected_task = candidate_task
                    break
                deferred.append(candidate)

        for entry in deferred:
            heapq.heappush(self._ready_heap, entry)
        selected_task.queued_generation = None
        return selected_task, float(selected_entry[0])

    def _take_hotels(self, task: _TaskSchedule) -> Tuple[Tuple[str, ...], bool]:
        use_priority = bool(task.priority_queue) and (
            not task.regular_queue
            or task.priority_streak < self.max_priority_turns
        )
        queue = task.priority_queue if use_priority else task.regular_queue
        if not queue:
            queue = task.priority_queue
            use_priority = True
        selected = tuple(
            queue.popleft() for _ in range(min(task.batch_size, len(queue)))
        )
        if use_priority:
            task.priority_streak += 1
        else:
            task.priority_streak = 0
        return selected, use_priority

    def _issue_turn(
        self,
        task: _TaskSchedule,
        scheduled_for: float,
        now: float,
    ) -> TaskTurn:
        hotels, priority = self._take_hotels(task)
        if not hotels:
            raise TaskCoordinatorError(f"task has no work queued: {task.task_id}")
        turn_id = uuid.uuid4().hex
        task.in_flight_turn_id = turn_id
        task.runtime_state = "scanning"
        task.next_run_at = scheduled_for
        if task.task_id == self._last_selected_task_id:
            self._consecutive_task_turns += 1
        else:
            self._last_selected_task_id = task.task_id
            self._consecutive_task_turns = 1
        return TaskTurn(
            turn_id=turn_id,
            task_id=task.task_id,
            hotels=hotels,
            scheduled_for=scheduled_for,
            issued_at=now,
            priority=priority,
            cancel_event=task.cancel_event,
        )

    def next_turn(
        self,
        *,
        cancel_event: Optional[Any] = None,
        timeout: Optional[float] = None,
    ) -> Optional[TaskTurn]:
        """Wait for and return the next fair task turn.

        ``None`` is returned when ``timeout`` expires. Cancellation raises
        :class:`CoordinatorCancelled`.
        """

        if timeout is not None and float(timeout) < 0:
            raise ValueError("timeout must be non-negative")
        started_at = float(self._clock())
        deadline = None if timeout is None else started_at + float(timeout)
        while True:
            if self._is_cancelled(cancel_event):
                raise CoordinatorCancelled("coordinator wait cancelled")

            now = float(self._clock())
            with self._lock:
                ready = self._pop_ready_task(now)
                if ready is not None:
                    task, scheduled_for = ready
                    return self._issue_turn(task, scheduled_for, now)
                self._clean_heap_head()
                future_at = self._ready_heap[0][0] if self._ready_heap else None

            if deadline is not None and now >= deadline:
                return None
            if future_at is None:
                wait_for = self.cancellation_poll_interval
            else:
                wait_for = max(0.0, future_at - now)
            if cancel_event is not None:
                wait_for = min(wait_for, self.cancellation_poll_interval)
            if deadline is not None:
                wait_for = min(wait_for, max(0.0, deadline - now))
            if wait_for <= 0:
                continue
            self._wait(wait_for)

    def _validate_turn(self, turn: TaskTurn) -> _TaskSchedule:
        task = self._get_task(self._task_id(turn.task_id))
        if task.in_flight_turn_id != turn.turn_id:
            raise TaskCoordinatorError(
                f"turn is not active for task {turn.task_id}: {turn.turn_id}"
            )
        return task

    def _schedule_fresh_round(
        self,
        task: _TaskSchedule,
        *,
        ready_at: float,
        now: float,
    ) -> None:
        self._reset_round(task)
        task.target_at = ready_at
        task.resume_at = None
        task.runtime_state = "queued" if ready_at <= now else "waiting"
        self._enqueue(task, ready_at)

    def complete_turn(
        self,
        turn: TaskTurn,
        *,
        completed_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Record one successful turn and schedule the next fair opportunity."""

        now = float(self._clock()) if completed_at is None else float(completed_at)
        if not math.isfinite(now):
            raise ValueError("completed_at must be finite")
        with self._lock:
            task = self._validate_turn(turn)
            task.in_flight_turn_id = None
            task.turns_completed += 1
            task.last_error = ""

            if task.desired_state != "active":
                task.runtime_state = "idle"
                task.next_run_at = None
                task.target_at = None
                return self._task_snapshot(task)

            if turn.cancel_event.is_set():
                ready_at = now if task.resume_at is None else task.resume_at
                self._schedule_fresh_round(task, ready_at=ready_at, now=now)
                return self._task_snapshot(task)

            if task.priority_queue or task.regular_queue:
                target = turn.scheduled_for
                task.runtime_state = "queued"
                self._enqueue(task, target)
                return self._task_snapshot(task)

            task.rounds_completed += 1
            next_target = self.next_cadence_at(
                turn.scheduled_for,
                task.cadence_seconds,
                now,
            )
            self._schedule_fresh_round(task, ready_at=next_target, now=now)
            return self._task_snapshot(task)

    def fail_turn(
        self,
        turn: TaskTurn,
        error: Any,
        *,
        completed_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Record a task-level turn failure and defer to the next cadence."""

        now = float(self._clock()) if completed_at is None else float(completed_at)
        if not math.isfinite(now):
            raise ValueError("completed_at must be finite")
        with self._lock:
            task = self._validate_turn(turn)
            task.in_flight_turn_id = None
            task.last_error = str(error or "")[:1000]
            if task.desired_state != "active":
                task.runtime_state = "idle"
                task.next_run_at = None
                task.target_at = None
                return self._task_snapshot(task)

            if turn.cancel_event.is_set():
                ready_at = now if task.resume_at is None else task.resume_at
                self._schedule_fresh_round(task, ready_at=ready_at, now=now)
                return self._task_snapshot(task)

            next_target = self.next_cadence_at(
                turn.scheduled_for,
                task.cadence_seconds,
                now,
            )
            self._reset_round(task)
            task.target_at = next_target
            task.runtime_state = "error"
            self._enqueue(task, next_target)
            task.runtime_state = "error"
            return self._task_snapshot(task)

    def _task_snapshot(self, task: _TaskSchedule) -> Dict[str, Any]:
        return {
            "task_id": task.task_id,
            "desired_state": task.desired_state,
            "runtime_state": task.runtime_state,
            "next_run_at": task.next_run_at,
            "cadence_seconds": task.cadence_seconds,
            "batch_size": task.batch_size,
            "hotel_count": len(task.hotels),
            "remaining_hotels": len(task.priority_queue) + len(task.regular_queue),
            "priority_remaining": len(task.priority_queue),
            "in_flight": task.in_flight_turn_id is not None,
            "last_error": task.last_error,
            "turns_completed": task.turns_completed,
            "rounds_completed": task.rounds_completed,
        }

    def task_snapshot(self, task_id: str) -> Dict[str, Any]:
        cleaned_id = self._task_id(task_id)
        with self._lock:
            return self._task_snapshot(self._get_task(cleaned_id))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "task_count": len(self._tasks),
                "ready_queue_size": sum(
                    1
                    for entry in self._ready_heap
                    if self._valid_heap_entry(entry) is not None
                ),
                "tasks": {
                    task_id: self._task_snapshot(task)
                    for task_id, task in sorted(self._tasks.items())
                },
            }
