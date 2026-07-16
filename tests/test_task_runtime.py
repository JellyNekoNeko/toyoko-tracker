import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from toyoko_tracker import task_runtime, workspace


class Clock:
    def __init__(self, value=100.0):
        self.value = float(value)

    def __call__(self):
        self.value += 1.0
        return self.value


def test_task_context_keeps_mutable_state_isolated_and_snapshots_detached():
    clock = Clock()
    first = task_runtime.TaskRuntimeContext("first", clock=clock)
    second = task_runtime.TaskRuntimeContext("second", clock=clock)
    source_result = {"hotel": {"code": "00001"}}
    source_checkpoint = {"seen": ["00001"]}

    first.begin_run("run-first")
    second.begin_run("run-second")
    first.update_progress({"done": 1}, total=3)
    first.append_result(source_result)
    first.append_error("temporary error", details={"provider": "toyoko"})
    first.set_checkpoint("notifications", source_checkpoint)

    source_result["hotel"]["code"] = "changed"
    source_checkpoint["seen"].append("changed")
    snapshot = first.snapshot()
    snapshot["results"][0]["hotel"]["code"] = "snapshot-change"
    snapshot["checkpoints"]["notifications"]["seen"].append("snapshot-change")

    fresh = first.snapshot()
    assert fresh["progress"] == {"done": 1, "total": 3}
    assert fresh["results"] == [{"hotel": {"code": "00001"}}]
    assert fresh["errors"][0]["details"] == {"provider": "toyoko"}
    assert fresh["checkpoints"] == {"notifications": {"seen": ["00001"]}}
    assert second.snapshot()["results"] == []
    assert first.cancel_event is not second.cancel_event


def test_task_context_is_safe_for_parallel_result_and_progress_updates():
    context = task_runtime.TaskRuntimeContext("parallel")
    context.begin_run("parallel-run")

    def write(worker):
        for index in range(100):
            context.append_result({"worker": worker, "index": index})
            context.update_progress({f"worker_{worker}": index})

    threads = [threading.Thread(target=write, args=(worker,)) for worker in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = context.snapshot()
    assert len(snapshot["results"]) == 400
    assert snapshot["progress"] == {
        "worker_0": 99,
        "worker_1": 99,
        "worker_2": 99,
        "worker_3": 99,
    }


def test_registry_starts_and_finishes_an_independent_durable_run():
    clock = Clock()
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task("Tokyo", {}, task_id="tokyo", desired_state="active")
            registry = task_runtime.TaskRuntimeRegistry(clock=clock)

            run = registry.begin_run("tokyo", run_id="tokyo-run")
            hydrated = registry.snapshot("tokyo")
            registry.get_or_create("tokyo").append_result({"available": True})
            completed = registry.finish_run(
                "tokyo",
                state="complete",
                result_summary={"available": 1},
                next_run_at=500.0,
            )
            task = workspace.get_task("tokyo")
            runs = workspace.list_task_runs("tokyo")

    assert run["state"] == "running"
    assert hydrated["desired_state"] == "active"
    assert hydrated["config"]["hotel_codes"]
    assert hydrated["revision"] == 1
    assert hydrated["runtime_revision"] == 1
    assert completed["state"] == "complete"
    assert task["runtime_state"] == "waiting"
    assert task["next_run_at"] == 500.0
    assert runs[0]["result_summary"] == {"available": 1}
    snapshot = registry.snapshot("tokyo")
    assert snapshot["run_id"] is None
    assert snapshot["runtime_state"] == "waiting"
    assert snapshot["results"] == [{"available": True}]


def test_pause_requests_cancellation_then_drains_to_idle():
    clock = Clock()
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task("Tokyo", {}, task_id="tokyo", desired_state="active")
            registry = task_runtime.TaskRuntimeRegistry(clock=clock)
            registry.begin_run("tokyo", run_id="tokyo-run")

            pausing = registry.request_pause("tokyo")
            durable_pausing = workspace.get_task("tokyo")
            assert pausing["runtime_state"] == "pausing"
            assert pausing["draining"] is True
            assert pausing["cancel_requested"] is True
            assert durable_pausing["desired_state"] == "paused"
            assert durable_pausing["runtime_state"] == "pausing"

            registry.finish_run("tokyo", state="cancelled")
            durable_idle = workspace.get_task("tokyo")

    idle = registry.snapshot("tokyo")
    assert durable_idle["runtime_state"] == "idle"
    assert idle["runtime_state"] == "idle"
    assert idle["draining"] is False
    assert idle["cancel_requested"] is False


def test_second_run_and_mismatched_finish_are_rejected_per_task():
    context = task_runtime.TaskRuntimeContext("tokyo")
    context.begin_run("first-run")

    with pytest.raises(task_runtime.TaskRunActiveError):
        context.begin_run("second-run")
    with pytest.raises(task_runtime.TaskRunMismatchError):
        context.end_run("other-run", runtime_state="idle")

    other = task_runtime.TaskRuntimeContext("osaka")
    other.begin_run("osaka-run")
    assert other.snapshot()["run_id"] == "osaka-run"


def test_recovery_interrupts_orphan_runs_and_rebuilds_from_desired_state():
    clock = Clock(value=100)
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task(
                "Active",
                {},
                task_id="active",
                desired_state="active",
            )
            workspace.create_task(
                "Paused",
                {},
                task_id="paused",
                desired_state="paused",
            )
            workspace.create_task(
                "Waiting",
                {},
                task_id="waiting",
                desired_state="active",
            )
            workspace.set_task_runtime_state(
                "waiting",
                "waiting",
                next_run_at=500,
            )
            workspace.start_task_run(
                "active",
                run_id="orphan-running",
                state="running",
            )
            workspace.start_task_run(
                "paused",
                run_id="orphan-queued",
                state="queued",
            )

            registry = task_runtime.TaskRuntimeRegistry(clock=clock)
            stale = registry.get_or_create("stale")
            stale.set_checkpoint("leak", {"value": True})
            recovered = registry.recover()

            active_task = workspace.get_task("active")
            paused_task = workspace.get_task("paused")
            waiting_task = workspace.get_task("waiting")
            active_runs = workspace.list_task_runs("active")
            paused_runs = workspace.list_task_runs("paused")

    assert stale.cancel_event.is_set()
    assert set(recovered["interrupted_run_ids"]) == {
        "orphan-running",
        "orphan-queued",
    }
    assert active_runs[0]["state"] == "interrupted"
    assert paused_runs[0]["state"] == "interrupted"
    assert active_task["runtime_state"] == "queued"
    assert paused_task["runtime_state"] == "idle"
    assert waiting_task["runtime_state"] == "waiting"
    assert waiting_task["next_run_at"] == 500
    assert recovered["contexts"]["active"]["checkpoints"] == {}
    assert recovered["contexts"]["paused"]["checkpoints"] == {}
    assert recovered["contexts"]["waiting"]["runtime_state"] == "waiting"
    assert "stale" not in recovered["contexts"]
