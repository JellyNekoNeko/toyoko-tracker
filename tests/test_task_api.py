import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from toyoko_tracker import runtime, workspace
from toyoko_tracker.app import app
from toyoko_tracker.models import AppConfig
from toyoko_tracker.provider_pacer import ProviderPacer
from toyoko_tracker.task_scheduler import TaskSchedulerKernel
from toyoko_tracker.task_service import TaskSchedulerService


def _app_config(codes=("00001",)):
    return AppConfig(
        start_date="2026-07-17",
        end_date="2026-07-18",
        hotel_codes=list(codes),
        selected_hotels=[
            {
                "code": code,
                "provider": code.split(":", 1)[0] if ":" in code else "toyoko",
                "name": f"Hotel {code}",
            }
            for code in codes
        ],
        loop_interval_seconds=60,
    )


def _wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true")


def _build_service():
    def scan(item):
        return {
            "code": item.hotel_code,
            "provider": item.provider,
            "url": f"https://example.test/{item.hotel_code}",
            "name": f"Hotel {item.hotel_code}",
            "available": True,
            "min_price": 9800,
            "min_price_text": "¥9,800",
            "checked_at": "2026-07-17T00:00:00+00:00",
            "engine_used": "fixture",
            "http_status": 200,
        }

    kernel = TaskSchedulerKernel(
        scan,
        repository=workspace,
        pacer=ProviderPacer(
            total_limit=2,
            per_provider_limit=1,
            cancellation_poll_interval=0.01,
        ),
    )
    return TaskSchedulerService(
        scan,
        repository=workspace,
        kernel=kernel,
        poll_interval=0.01,
        drain_timeout=1,
    )


def test_task_api_crud_controls_results_runs_and_conflicts():
    app.config.update(TESTING=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        cfg = _app_config()
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.initialize_workspace()
            workspace.ensure_default_task(cfg)
            service = _build_service()
            with patch.object(runtime, "_TASK_SERVICE", service), \
                 patch.object(runtime, "_CONFIG", cfg), \
                 patch.object(runtime, "send_start_notifications"), \
                 patch.object(runtime, "send_stop_notifications"):
                client = app.test_client()
                listed = client.get("/api/v1/tasks").get_json()
                assert [task["task_id"] for task in listed["tasks"]] == ["default"]
                assert listed["summary"]["service_running"] is True

                created_response = client.post(
                    "/api/v1/tasks",
                    json={"source_task_id": "default", "name": "Tokyo weekend"},
                )
                assert created_response.status_code == 201
                created = created_response.get_json()["task"]

                renamed_response = client.patch(
                    f"/api/v1/tasks/{created['task_id']}",
                    json={
                        "name": "Tokyo event",
                        "expected_revision": created["revision"],
                    },
                )
                renamed = renamed_response.get_json()["task"]
                assert renamed["name"] == "Tokyo event"

                configured_response = client.patch(
                    f"/api/v1/tasks/{created['task_id']}",
                    json={
                        "config": {"people": 3},
                        "expected_revision": renamed["revision"],
                    },
                )
                configured = configured_response.get_json()["task"]
                assert configured["config"]["people"] == 3

                conflict = client.patch(
                    f"/api/v1/tasks/{created['task_id']}",
                    json={
                        "name": "Stale update",
                        "expected_revision": renamed["revision"],
                    },
                )
                assert conflict.status_code == 409
                assert conflict.get_json()["task"]["revision"] == configured["revision"]

                current_default = client.get(
                    "/api/v1/tasks/default"
                ).get_json()["task"]
                reordered = client.post(
                    "/api/v1/tasks/reorder",
                    json={
                        "task_ids": [created["task_id"], "default"],
                        "expected_revisions": {
                            created["task_id"]: configured["revision"],
                            "default": current_default["revision"],
                        },
                    },
                )
                assert reordered.status_code == 200
                reordered_tasks = reordered.get_json()["tasks"]
                selected = reordered_tasks[0]

                started = client.post(
                    f"/api/v1/tasks/{selected['task_id']}/start",
                    json={
                        "run_once": True,
                        "expected_revision": selected["revision"],
                    },
                )
                assert started.status_code == 200
                _wait_until(
                    lambda: bool(workspace.list_task_runs(selected["task_id"]))
                    and workspace.list_task_runs(selected["task_id"])[0]["state"]
                    == "complete"
                )

                results = client.get(
                    f"/api/v1/tasks/{selected['task_id']}/results?since=-1"
                ).get_json()
                assert results["changed"] is True
                assert results["results"][0]["code"] == "00001"
                unchanged = client.get(
                    f"/api/v1/tasks/{selected['task_id']}/results"
                    f"?since={results['revision']}"
                ).get_json()
                assert unchanged["changed"] is False

                runs = client.get(
                    f"/api/v1/tasks/{selected['task_id']}/runs"
                ).get_json()["runs"]
                assert runs[0]["state"] == "complete"
                status = client.get(
                    f"/api/v1/tasks/{selected['task_id']}/status"
                ).get_json()
                assert status["task"]["result_count"] == 1
                assert "provider_pacer" in status

                latest = status["task"]
                deleted = client.delete(
                    f"/api/v1/tasks/{selected['task_id']}",
                    json={"expected_revision": latest["revision"]},
                )
                assert deleted.status_code == 200
                final_delete = client.delete("/api/v1/tasks/default")
                assert final_delete.status_code == 409
            service.shutdown()


def test_legacy_routes_project_the_requested_task_through_the_scheduler():
    app.config.update(TESTING=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        cfg = _app_config()
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.initialize_workspace()
            workspace.ensure_default_task(cfg)
            second = workspace.create_task(
                "Osaka",
                workspace.task_config_snapshot(_app_config(("00002",))),
                task_id="osaka",
            )
            service = _build_service()
            with patch.object(runtime, "_TASK_SERVICE", service), \
                 patch.object(runtime, "_CONFIG", cfg), \
                 patch.object(runtime, "_save_config_to_file"), \
                 patch.object(runtime, "_remember_search"), \
                 patch.object(runtime, "send_start_notifications"), \
                 patch.object(runtime, "send_stop_notifications"):
                client = app.test_client()
                response = client.post(
                    "/start",
                    json={
                        "task_id": "osaka",
                        "expected_revision": second["revision"],
                        "run_once": True,
                        "start_date": "2026-08-01",
                        "end_date": "2026-08-02",
                        "hotel_codes": ["00003"],
                        "selected_hotels": [{
                            "code": "00003",
                            "provider": "toyoko",
                            "name": "Hotel 00003",
                        }],
                    },
                )
                body = response.get_json()
                assert response.status_code == 200
                assert body["message"] == "scan_once_started"
                assert body["task_id"] == "osaka"
                assert body["run_once"] is True
                assert "config" in body

                _wait_until(
                    lambda: bool(workspace.list_task_runs("osaka"))
                    and workspace.list_task_runs("osaka")[0]["state"] == "complete"
                )
                projected = client.get("/status?task_id=osaka").get_json()
                assert projected["task_id"] == "osaka"
                assert projected["config"]["hotel_codes"] == ["00003"]
                assert projected["results"][0]["code"] == "00003"

                delta = client.get(
                    "/api/v1/results?task_id=osaka&since=-1"
                ).get_json()
                assert delta["task_id"] == "osaka"
                assert delta["results"][0]["code"] == "00003"

                latest = workspace.get_task("osaka")
                stopped = client.post(
                    "/stop",
                    json={
                        "task_id": "osaka",
                        "expected_revision": latest["revision"],
                    },
                )
                assert stopped.status_code == 200
                assert stopped.get_json()["task_id"] == "osaka"
            service.shutdown()
