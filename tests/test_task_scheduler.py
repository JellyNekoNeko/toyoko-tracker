import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from toyoko_tracker import workspace
from toyoko_tracker.models import AppConfig
from toyoko_tracker.provider_pacer import ProviderPacer
from toyoko_tracker.task_coordinator import TaskCoordinator
from toyoko_tracker.task_scheduler import TaskSchedulerKernel


class Clock:
    def __init__(self, value=100.0):
        self.value = float(value)

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += float(seconds)


def config(codes, cadence=30):
    cfg = AppConfig(
        hotel_codes=list(codes),
        selected_hotels=[
            {
                "code": code,
                "provider": (
                    code.split(":", 1)[0] if ":" in code else "toyoko"
                ),
                "priority": index == 0,
            }
            for index, code in enumerate(codes)
        ],
        loop_interval_seconds=cadence,
    )
    return workspace.task_config_snapshot(cfg)


def test_kernel_reconciles_orphans_and_registers_durable_tasks():
    wall = Clock()
    mono = Clock()
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "Active",
                config(["00001"]),
                task_id="active",
                desired_state="active",
            )
            workspace.create_task(
                "Paused",
                config(["00002"]),
                task_id="paused",
                desired_state="paused",
            )
            workspace.start_task_run("active", run_id="orphan", state="running")
            kernel = TaskSchedulerKernel(
                lambda item: {"code": item.hotel_code},
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            reconciled = kernel.reconcile()
            orphan = workspace.list_task_runs("active")[0]

    assert orphan["state"] == "interrupted"
    assert set(reconciled["registered"]) == {"active", "paused"}
    assert reconciled["scheduler"]["coordinator"]["tasks"]["active"][
        "desired_state"
    ] == "active"
    assert reconciled["scheduler"]["coordinator"]["tasks"]["paused"][
        "desired_state"
    ] == "paused"


def test_kernel_runs_fair_turns_and_keeps_task_results_isolated():
    wall = Clock()
    mono = Clock()
    seen = []

    def scan(item):
        seen.append((item.task_id, item.hotel_code, item.round_no))
        wall.advance(0.1)
        mono.advance(0.1)
        return {"task": item.task_id, "code": item.hotel_code}

    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "Large",
                config(["l1", "l2", "l3"]),
                task_id="large",
                desired_state="active",
            )
            workspace.create_task(
                "Small",
                config(["s1"]),
                task_id="small",
                desired_state="active",
            )
            kernel = TaskSchedulerKernel(
                scan,
                coordinator=TaskCoordinator(
                    max_consecutive_task_turns=1,
                    clock=mono,
                    wait=mono.advance,
                ),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            kernel.reconcile()
            turns = [kernel.run_next_turn(timeout=0) for _ in range(4)]
            snapshot = kernel.snapshot()
            large_runs = workspace.list_task_runs("large")
            small_runs = workspace.list_task_runs("small")

    assert [result.turn.task_id for result in turns] == [
        "large",
        "small",
        "large",
        "large",
    ]
    assert seen[0][2] == seen[2][2] == seen[3][2] == 1
    assert small_runs[0]["state"] == "complete"
    assert large_runs[0]["state"] == "complete"
    assert {
        result["task"]
        for result in snapshot["runtime"]["large"]["results"]
    } == {"large"}
    assert {
        result["task"]
        for result in snapshot["runtime"]["small"]["results"]
    } == {"small"}


def test_pausing_one_task_during_a_turn_leaves_other_tasks_ready():
    wall = Clock()
    mono = Clock()
    holder = {}

    def scan(item):
        if item.task_id == "a":
            holder["kernel"].pause("a")
        return {"code": item.hotel_code}

    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "A",
                config(["a1", "a2"]),
                task_id="a",
                desired_state="active",
            )
            workspace.create_task(
                "B",
                config(["b1"]),
                task_id="b",
                desired_state="active",
            )
            kernel = TaskSchedulerKernel(
                scan,
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            holder["kernel"] = kernel
            kernel.reconcile()
            cancelled = kernel.run_next_turn(timeout=0)
            next_result = kernel.run_next_turn(timeout=0)
            task_a = workspace.get_task("a")
            task_b = workspace.get_task("b")

    assert cancelled.task["runtime_state"] == "idle"
    assert task_a["desired_state"] == "paused"
    assert next_result.turn.task_id == "b"
    assert task_b["desired_state"] == "active"


def test_turn_failure_records_task_error_without_leaking_to_another_context():
    wall = Clock()
    mono = Clock()

    def scan(item):
        if item.task_id == "bad":
            raise RuntimeError("provider fixture failed")
        return {"code": item.hotel_code}

    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "Bad",
                config(["bad1"]),
                task_id="bad",
                desired_state="active",
            )
            workspace.create_task(
                "Good",
                config(["good1"]),
                task_id="good",
                desired_state="active",
            )
            kernel = TaskSchedulerKernel(
                scan,
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            kernel.reconcile()
            with pytest.raises(RuntimeError, match="provider fixture failed"):
                kernel.run_next_turn(timeout=0)
            good = kernel.run_next_turn(timeout=0)
            snapshot = kernel.snapshot()
            bad_run = workspace.list_task_runs("bad")[0]

    assert bad_run["state"] == "failed"
    assert snapshot["runtime"]["bad"]["errors"][0]["message"] == (
        "provider fixture failed"
    )
    assert snapshot["runtime"]["good"]["errors"] == []
    assert good.turn.task_id == "good"


def test_run_once_completes_one_round_without_changing_desired_state():
    wall = Clock()
    mono = Clock()
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "Paused",
                config(["h1", "h2"]),
                task_id="paused",
                desired_state="paused",
            )
            kernel = TaskSchedulerKernel(
                lambda item: {"code": item.hotel_code},
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            kernel.reconcile()
            kernel.activate("paused", run_once=True)
            first = kernel.run_next_turn(timeout=0)
            second = kernel.run_next_turn(timeout=0)
            no_more = kernel.run_next_turn(timeout=0)
            task = workspace.get_task("paused")
            run = workspace.list_task_runs("paused")[0]
            scheduled = kernel.coordinator.task_snapshot("paused")

    assert first.round_completed is False
    assert second.round_completed is True
    assert no_more is None
    assert task["desired_state"] == "paused"
    assert task["runtime_state"] == "idle"
    assert run["state"] == "complete"
    assert scheduled["desired_state"] == "paused"


def test_kernel_tasks_share_provider_cooldown_through_the_global_gate():
    wall = Clock(value=0)
    mono = Clock(value=0)
    calls = []

    def scan(item):
        calls.append((item.task_id, mono()))
        if item.task_id == "first":
            return {
                "code": item.hotel_code,
                "http_status": 429,
                "retry_after_sec": 5,
            }
        return {"code": item.hotel_code, "http_status": 200}

    pacer = ProviderPacer(
        total_limit=2,
        per_provider_limit=2,
        base_cooldown=1,
        max_cooldown=30,
        clock=mono,
        wait=mono.advance,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "First",
                config(["00001"]),
                task_id="first",
                desired_state="active",
            )
            workspace.create_task(
                "Second",
                config(["00002"]),
                task_id="second",
                desired_state="active",
            )
            kernel = TaskSchedulerKernel(
                scan,
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                pacer=pacer,
                wall_clock=wall,
                monotonic_clock=mono,
            )
            kernel.reconcile()
            kernel.run_next_turn(timeout=0)
            kernel.run_next_turn(timeout=0)

    assert calls == [("first", 0.0), ("second", 5.0)]


def test_kernel_request_interval_is_enforced_across_tasks():
    wall = Clock(value=0)
    mono = Clock(value=0)
    calls = []
    pacer = ProviderPacer(
        total_limit=2,
        per_provider_limit=2,
        clock=mono,
        wait=mono.advance,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "First",
                config(["00001"]),
                task_id="first",
                desired_state="active",
            )
            workspace.create_task(
                "Second",
                config(["00002"]),
                task_id="second",
                desired_state="active",
            )
            kernel = TaskSchedulerKernel(
                lambda item: calls.append((item.task_id, mono()))
                or {"code": item.hotel_code},
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                pacer=pacer,
                request_interval=lambda _item: 3,
                wall_clock=wall,
                monotonic_clock=mono,
            )
            kernel.reconcile()
            kernel.run_next_turn(timeout=0)
            kernel.run_next_turn(timeout=0)

    assert calls == [("first", 0.0), ("second", 3.0)]


def test_durable_wall_deadlines_are_mapped_to_monotonic_scheduler_time():
    wall = Clock(value=1_000)
    mono = Clock(value=50)
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            task = workspace.create_task(
                "Future",
                config(["h1"]),
                task_id="future",
                desired_state="active",
            )
            workspace.set_task_runtime_state(
                task["task_id"],
                "waiting",
                next_run_at=1_020,
            )
            kernel = TaskSchedulerKernel(
                lambda item: {"code": item.hotel_code},
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            reconciled = kernel.reconcile()
            scheduled = reconciled["registered"]["future"]
            no_turn = kernel.run_next_turn(timeout=0)
            mono.advance(20)
            turn = kernel.run_next_turn(timeout=0)

    assert scheduled["next_run_at"] == 70
    assert no_turn is None
    assert turn is not None


def test_pause_from_another_thread_cancels_an_active_scan_without_deadlock():
    wall = Clock()
    mono = Clock()
    entered = threading.Event()
    output = {}

    def scan(item):
        entered.set()
        assert item.cancel_event.wait(1)
        raise RuntimeError("cancelled by pause")

    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "Task",
                config(["h1"]),
                task_id="task",
                desired_state="active",
            )
            kernel = TaskSchedulerKernel(
                scan,
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            kernel.reconcile()

            def run_turn():
                output["result"] = kernel.run_next_turn(timeout=0)

            worker = threading.Thread(target=run_turn)
            worker.start()
            assert entered.wait(1)
            paused = kernel.pause("task")
            worker.join(timeout=1)
            task = workspace.get_task("task")
            run = workspace.list_task_runs("task")[0]

    assert not worker.is_alive()
    assert paused["task"]["runtime_state"] == "pausing"
    assert output["result"].task["runtime_state"] == "idle"
    assert task["desired_state"] == "paused"
    assert run["state"] == "cancelled"


def test_reconcile_isolates_an_active_task_with_no_hotels():
    wall = Clock()
    mono = Clock()
    empty = config(["h1"])
    empty["hotel_codes"] = []
    empty["selected_hotels"] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "Invalid active task",
                empty,
                task_id="empty",
                desired_state="active",
            )
            workspace.create_task(
                "Healthy",
                config(["h1"]),
                task_id="healthy",
                desired_state="active",
            )
            kernel = TaskSchedulerKernel(
                lambda item: {"code": item.hotel_code},
                coordinator=TaskCoordinator(clock=mono, wait=mono.advance),
                wall_clock=wall,
                monotonic_clock=mono,
            )
            reconciled = kernel.reconcile()
            empty_task = workspace.get_task("empty")
            healthy_turn = kernel.run_next_turn(timeout=0)

    assert "empty" in reconciled["registration_errors"]
    assert empty_task["runtime_state"] == "error"
    assert healthy_turn.turn.task_id == "healthy"
