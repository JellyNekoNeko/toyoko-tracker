import threading
import time

import pytest

from toyoko_tracker.provider_pacer import PacerCancelled, ProviderPacer


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


def test_three_tasks_share_provider_spacing_and_cooldown():
    virtual = VirtualClock()
    pacer = ProviderPacer(
        total_limit=3,
        per_provider_limit=3,
        min_start_interval=2,
        base_cooldown=3,
        max_cooldown=60,
        clock=virtual.clock,
        wait=virtual.wait,
    )

    with pacer.acquire("toyoko", task_id="task-a"):
        assert virtual.now == 0
    with pacer.acquire("toyoko", task_id="task-b"):
        assert virtual.now == 2

    assert pacer.report_response("toyoko", 429, retry_after=7) == 7
    with pacer.acquire("toyoko", task_id="task-c"):
        assert virtual.now == 9

    snapshot = pacer.snapshot()
    assert snapshot["acquired_total"] == 3
    assert snapshot["released_total"] == 3
    assert snapshot["active_total"] == 0
    assert snapshot["providers"]["toyoko"]["last_started_at"] == 9
    assert sum(virtual.waits) == 9


def test_429_and_503_use_exponential_or_explicit_retry_after():
    virtual = VirtualClock()
    pacer = ProviderPacer(
        base_cooldown=4,
        max_cooldown=60,
        clock=virtual.clock,
        wait=virtual.wait,
    )

    assert pacer.report_response("toyoko", 429) == 4
    assert pacer.report_response("toyoko", 503) == 8
    assert pacer.report_response("toyoko", 429, retry_after="30") == 30
    snapshot = pacer.snapshot()["providers"]["toyoko"]
    assert snapshot["failure_streak"] == 3
    assert snapshot["cooldown_remaining"] == 30

    virtual.now += 10
    pacer.report_response("toyoko", 200)
    snapshot = pacer.snapshot()["providers"]["toyoko"]
    assert snapshot["failure_streak"] == 0
    assert snapshot["cooldown_remaining"] == 20


def test_cancelled_wait_does_not_occupy_a_token():
    virtual = VirtualClock()
    cancel = threading.Event()

    def wait_and_cancel(seconds):
        virtual.wait(seconds)
        cancel.set()

    pacer = ProviderPacer(
        total_limit=1,
        per_provider_limit=1,
        cancellation_poll_interval=0.25,
        clock=virtual.clock,
        wait=wait_and_cancel,
    )
    held = pacer.acquire("toyoko", task_id="holder")

    with pytest.raises(PacerCancelled):
        pacer.acquire("toyoko", task_id="cancelled", cancel_event=cancel)

    snapshot = pacer.snapshot()
    assert snapshot["active_total"] == 1
    assert snapshot["waiting_total"] == 0
    assert snapshot["acquired_total"] == 1
    assert snapshot["cancelled_total"] == 1
    held.release()
    assert pacer.snapshot()["active_total"] == 0


def test_total_and_per_provider_concurrency_limits_are_independent():
    virtual = VirtualClock()
    pacer = ProviderPacer(
        total_limit=3,
        per_provider_limit=2,
        provider_limits={"routeinn": 1},
        clock=virtual.clock,
        wait=virtual.wait,
    )

    toyoko_a = pacer.acquire("toyoko")
    toyoko_b = pacer.acquire("toyoko")
    routeinn = pacer.acquire("routeinn")
    snapshot = pacer.snapshot()
    assert snapshot["active_total"] == 3
    assert snapshot["providers"]["toyoko"]["active"] == 2
    assert snapshot["providers"]["routeinn"]["active"] == 1

    toyoko_a.release()
    toyoko_b.release()
    routeinn.release()
    assert pacer.snapshot()["active_total"] == 0


def test_virtual_clock_makes_spacing_and_snapshot_deterministic():
    virtual = VirtualClock(now=100)
    pacer = ProviderPacer(
        min_start_interval=5,
        provider_min_start_intervals={"routeinn": 3},
        clock=virtual.clock,
        wait=virtual.wait,
    )

    first = pacer.acquire("routeinn")
    first.release()
    second = pacer.acquire("routeinn")
    second.release()

    assert virtual.waits == [3]
    assert virtual.now == 103
    snapshot = pacer.snapshot()
    assert snapshot["providers"]["routeinn"] == {
        "active": 0,
        "waiting": 0,
        "concurrency_limit": 2,
        "min_start_interval": 3,
        "last_started_at": 103,
        "next_start_at": 106,
        "spacing_remaining": 3,
        "cooldown_until": None,
        "cooldown_remaining": 0,
        "failure_streak": 0,
    }


def test_request_specific_spacing_is_shared_with_the_next_feature():
    virtual = VirtualClock()
    pacer = ProviderPacer(
        min_start_interval=0,
        clock=virtual.clock,
        wait=virtual.wait,
    )

    with pacer.acquire(
        "toyoko",
        task_id="monitor-task",
        min_start_interval=4,
    ):
        pass
    with pacer.acquire("toyoko", task_id="price-calendar"):
        assert virtual.now == 4

    snapshot = pacer.snapshot()["providers"]["toyoko"]
    assert snapshot["last_started_at"] == 4
    assert snapshot["spacing_remaining"] == 0


def test_context_manager_and_manual_release_are_idempotent():
    pacer = ProviderPacer(total_limit=1, per_provider_limit=1)
    permit = pacer.acquire("toyoko")
    with permit:
        assert pacer.snapshot()["active_total"] == 1
    permit.release()
    pacer.release(permit)
    assert pacer.snapshot()["active_total"] == 0
    assert pacer.snapshot()["released_total"] == 1


def test_waiting_task_enters_after_a_global_slot_is_released():
    pacer = ProviderPacer(
        total_limit=1,
        per_provider_limit=1,
        cancellation_poll_interval=0.01,
    )
    held = pacer.acquire("toyoko", task_id="task-a")
    acquired = threading.Event()

    def wait_for_slot():
        with pacer.acquire("routeinn", task_id="task-b"):
            acquired.set()

    worker = threading.Thread(target=wait_for_slot, daemon=True)
    worker.start()
    deadline = time.monotonic() + 1
    while pacer.snapshot()["waiting_total"] != 1 and time.monotonic() < deadline:
        time.sleep(0.005)

    assert pacer.snapshot()["waiting_total"] == 1
    assert not acquired.is_set()
    held.release()
    assert acquired.wait(1)
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert pacer.snapshot()["active_total"] == 0
