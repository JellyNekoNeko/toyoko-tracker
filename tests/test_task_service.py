import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from toyoko_tracker import workspace
from toyoko_tracker.models import AppConfig
from toyoko_tracker.provider_pacer import ProviderPacer
from toyoko_tracker.task_scheduler import TaskSchedulerKernel
from toyoko_tracker.task_service import LastTaskError, TaskSchedulerService


def _config(codes, *, cadence=60):
    cfg = AppConfig(
        hotel_codes=list(codes),
        selected_hotels=[
            {
                "code": code,
                "provider": code.split(":", 1)[0] if ":" in code else "toyoko",
                "name": f"Hotel {code}",
            }
            for code in codes
        ],
        loop_interval_seconds=cadence,
    )
    return workspace.task_config_snapshot(cfg)


def _service(scan_one, *, poll_interval=0.01):
    kernel = TaskSchedulerKernel(
        scan_one,
        repository=workspace,
        pacer=ProviderPacer(
            total_limit=2,
            per_provider_limit=1,
            cancellation_poll_interval=0.01,
        ),
    )
    return TaskSchedulerService(
        scan_one,
        repository=workspace,
        kernel=kernel,
        poll_interval=poll_interval,
        drain_timeout=1,
    )


def _wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true")


def test_service_serializes_crud_revisions_reorder_and_last_task_guard():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.initialize_workspace()
            service = _service(lambda item: {"code": item.hotel_code})

            first = service.create_task("First", _config(["00001"]), task_id="first")
            second = service.duplicate_task("first", name="Second")
            renamed = service.update_task(
                second["task_id"],
                name="Renamed",
                expected_revision=second["revision"],
            )

            with pytest.raises(workspace.TaskConflictError):
                service.update_task(
                    second["task_id"],
                    name="Stale",
                    expected_revision=second["revision"],
                )

            current_first = service.public_task(first["task_id"])
            reordered = service.reorder(
                [renamed["task_id"], current_first["task_id"]],
                expected_revisions={
                    renamed["task_id"]: renamed["revision"],
                    current_first["task_id"]: current_first["revision"],
                },
            )
            assert [task["task_id"] for task in reordered] == [
                renamed["task_id"],
                current_first["task_id"],
            ]

            deleted = service.delete_task(
                renamed["task_id"],
                expected_revision=reordered[0]["revision"],
            )
            assert deleted["task_id"] == renamed["task_id"]
            with pytest.raises(LastTaskError):
                service.delete_task(current_first["task_id"])


def test_service_uses_one_coordinator_and_pausing_one_task_keeps_others_active():
    seen = []
    seen_lock = threading.Lock()

    def scan(item):
        with seen_lock:
            seen.append((item.task_id, item.hotel_code))
        return {"task_id": item.task_id, "code": item.hotel_code, "http_status": 200}

    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.initialize_workspace()
            for task_id, codes in (
                ("large", ["l1", "l2", "l3"]),
                ("small", ["s1"]),
                ("medium", ["m1", "m2"]),
            ):
                workspace.create_task(
                    task_id.title(),
                    _config(codes),
                    task_id=task_id,
                    desired_state="active",
                )
            service = _service(scan)
            try:
                service.start()
                coordinator_thread = service._thread
                service.start()
                assert service._thread is coordinator_thread
                _wait_until(
                    lambda: {"large", "small", "medium"}.issubset(
                        {task_id for task_id, _code in seen}
                    )
                )

                large = service.public_task("large")
                paused = service.pause(
                    "large",
                    expected_revision=large["revision"],
                )
                _wait_until(lambda: service.kernel.task_idle("large"))

                assert paused["task"]["desired_state"] == "paused"
                assert service.public_task("small")["desired_state"] == "active"
                assert service.public_task("medium")["desired_state"] == "active"
                assert service.summary()["active_count"] == 2
            finally:
                service.shutdown()

            assert service.running is False
            assert workspace.list_task_runs("small")
            assert workspace.list_task_runs("medium")


def test_service_shutdown_cancels_in_flight_work_and_preserves_resume_intent():
    entered = threading.Event()

    def scan(item):
        entered.set()
        item.cancel_event.wait(1)
        raise RuntimeError("shutdown cancellation")

    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.initialize_workspace()
            workspace.create_task(
                "Active",
                _config(["00001"]),
                task_id="active",
                desired_state="active",
            )
            service = _service(scan)
            service.start()
            assert entered.wait(1)
            service.shutdown(timeout=1)

            task = workspace.get_task("active")
            runs = workspace.list_task_runs("active")

    assert service.running is False
    assert task["desired_state"] == "active"
    assert task["runtime_state"] == "waiting"
    assert runs[0]["state"] == "cancelled"
