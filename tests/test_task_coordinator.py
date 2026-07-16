import threading

import pytest

from toyoko_tracker.task_coordinator import (
    CoordinatorCancelled,
    TaskCoordinator,
    TaskCoordinatorError,
)


class VirtualClock:
    def __init__(self, now=0.0):
        self.now = float(now)
        self.waits = []

    def clock(self):
        return self.now

    def wait(self, seconds):
        seconds = float(seconds)
        assert seconds >= 0
        self.waits.append(seconds)
        self.now += seconds

    def advance(self, seconds):
        self.now += float(seconds)


def take_and_complete(coordinator, virtual):
    turn = coordinator.next_turn(timeout=0)
    assert turn is not None
    virtual.advance(1)
    coordinator.complete_turn(turn)
    return turn


def test_ready_tasks_are_ordered_by_target_and_equal_targets_rotate():
    virtual = VirtualClock()
    coordinator = TaskCoordinator(clock=virtual.clock, wait=virtual.wait)
    coordinator.register_task("later", ["l1"], cadence_seconds=30, next_run_at=5)
    coordinator.register_task("a", ["a1", "a2"], cadence_seconds=30, next_run_at=0)
    coordinator.register_task("b", ["b1", "b2"], cadence_seconds=30, next_run_at=0)

    first = take_and_complete(coordinator, virtual)
    second = take_and_complete(coordinator, virtual)
    third = take_and_complete(coordinator, virtual)

    assert [first.task_id, second.task_id, third.task_id] == ["a", "b", "a"]
    assert first.scheduled_for == second.scheduled_for == 0
    assert third.hotels == ("a2",)


def test_turns_are_small_bounded_batches():
    coordinator = TaskCoordinator(max_turn_batch_size=3)
    coordinator.register_task(
        "task",
        ["h1", "h2", "h3", "h4", "h5"],
        cadence_seconds=60,
        batch_size=3,
    )

    first = coordinator.next_turn(timeout=0)
    assert first is not None
    assert first.hotels == ("h1", "h2", "h3")
    coordinator.complete_turn(first)
    second = coordinator.next_turn(timeout=0)
    assert second is not None
    assert second.hotels == ("h4", "h5")

    with pytest.raises(ValueError):
        coordinator.register_task(
            "too-large",
            ["h1"],
            cadence_seconds=60,
            batch_size=4,
        )


def test_priority_hotels_yield_after_a_bounded_number_of_turns():
    coordinator = TaskCoordinator(max_priority_turns=2)
    coordinator.register_task(
        "task",
        ["p1", "p2", "p3", "n1", "n2"],
        priority_hotels=["p1", "p2", "p3"],
        cadence_seconds=60,
    )

    turns = []
    for _ in range(5):
        turn = coordinator.next_turn(timeout=0)
        assert turn is not None
        turns.append((turn.hotels[0], turn.priority))
        coordinator.complete_turn(turn)

    assert turns == [
        ("p1", True),
        ("p2", True),
        ("n1", False),
        ("p3", True),
        ("n2", False),
    ]


def test_slow_round_skips_missed_cadences_without_catch_up():
    assert TaskCoordinator.next_cadence_at(10, 5, 10) == 15
    assert TaskCoordinator.next_cadence_at(10, 5, 15) == 20
    assert TaskCoordinator.next_cadence_at(10, 5, 27) == 30

    virtual = VirtualClock(now=10)
    coordinator = TaskCoordinator(clock=virtual.clock, wait=virtual.wait)
    coordinator.register_task(
        "slow",
        ["hotel"],
        cadence_seconds=5,
        next_run_at=10,
    )
    turn = coordinator.next_turn(timeout=0)
    assert turn is not None
    virtual.advance(17)
    state = coordinator.complete_turn(turn)

    assert state["runtime_state"] == "waiting"
    assert state["next_run_at"] == 30
    assert coordinator.next_turn(timeout=0) is None
    virtual.advance(3)
    assert coordinator.next_turn(timeout=0) is not None


def test_three_different_task_sizes_receive_fair_opportunities():
    virtual = VirtualClock()
    coordinator = TaskCoordinator(
        max_consecutive_task_turns=2,
        clock=virtual.clock,
        wait=virtual.wait,
    )
    coordinator.register_task(
        "large",
        [f"l{index}" for index in range(12)],
        cadence_seconds=100,
    )
    coordinator.register_task(
        "medium",
        ["m1", "m2"],
        cadence_seconds=4,
    )
    coordinator.register_task(
        "small",
        ["s1"],
        cadence_seconds=2,
    )

    selected = [take_and_complete(coordinator, virtual).task_id for _ in range(14)]

    assert selected[:3] == ["large", "medium", "small"]
    assert selected.count("large") > selected.count("medium")
    assert selected.count("medium") >= 2
    assert selected.count("small") >= 2
    assert max(
        sum(1 for _ in group)
        for group in _consecutive_groups(selected, "large")
    ) <= 2


def _consecutive_groups(values, target):
    current = []
    for value in values:
        if value == target:
            current.append(value)
        elif current:
            yield current
            current = []
    if current:
        yield current


def test_wait_is_cancellable_without_issuing_work():
    virtual = VirtualClock()
    cancel = threading.Event()

    def wait_and_cancel(seconds):
        virtual.wait(seconds)
        cancel.set()

    coordinator = TaskCoordinator(
        cancellation_poll_interval=0.25,
        clock=virtual.clock,
        wait=wait_and_cancel,
    )
    coordinator.register_task(
        "future",
        ["hotel"],
        cadence_seconds=60,
        next_run_at=30,
    )

    with pytest.raises(CoordinatorCancelled):
        coordinator.next_turn(cancel_event=cancel)

    state = coordinator.task_snapshot("future")
    assert state["runtime_state"] == "waiting"
    assert state["in_flight"] is False
    assert virtual.waits == [0.25]


def test_pause_removes_future_work_and_signals_an_active_turn():
    coordinator = TaskCoordinator()
    coordinator.register_task("task", ["h1", "h2"], cadence_seconds=60)
    turn = coordinator.next_turn(timeout=0)
    assert turn is not None
    assert not turn.cancel_event.is_set()

    state = coordinator.pause_task("task")
    assert state["desired_state"] == "paused"
    assert state["runtime_state"] == "pausing"
    assert state["next_run_at"] is None
    assert turn.cancel_event.is_set()
    assert coordinator.next_turn(timeout=0) is None

    state = coordinator.complete_turn(turn)
    assert state["runtime_state"] == "idle"
    assert state["remaining_hotels"] == 0


def test_failure_uses_error_state_until_the_next_cadence():
    virtual = VirtualClock()
    coordinator = TaskCoordinator(clock=virtual.clock, wait=virtual.wait)
    coordinator.register_task("task", ["h1", "h2"], cadence_seconds=10)
    turn = coordinator.next_turn(timeout=0)
    assert turn is not None
    virtual.advance(3)
    state = coordinator.fail_turn(turn, "provider failed")

    assert state["runtime_state"] == "error"
    assert state["last_error"] == "provider failed"
    assert state["next_run_at"] == 10
    virtual.advance(7)
    retry = coordinator.next_turn(timeout=0)
    assert retry is not None
    assert retry.hotels == ("h1",)


def test_turn_completion_is_strictly_matched():
    coordinator = TaskCoordinator()
    coordinator.register_task("task", ["hotel"], cadence_seconds=60)
    turn = coordinator.next_turn(timeout=0)
    assert turn is not None
    coordinator.complete_turn(turn)

    with pytest.raises(TaskCoordinatorError):
        coordinator.complete_turn(turn)
