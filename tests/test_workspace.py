import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from toyoko_tracker import workspace
from toyoko_tracker.models import AppConfig


def _config() -> AppConfig:
    cfg = AppConfig(
        hotel_codes=["00001"],
        selected_hotels=[{
            "code": "00001",
            "provider": "toyoko",
            "name_primary": "Test Hotel",
        }],
        enable_bark=True,
        bark_key="secret-bark-key",
        enable_telegram=True,
        bot_token="secret-bot-token",
        chat_id="secret-chat-id",
        smtp_pass="secret-mail-password",
    )
    cfg.room_requirement = "single"
    return cfg


def test_workspace_schema_is_initialized_idempotently():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            first = workspace.initialize_workspace()
            second = workspace.initialize_workspace()

        assert first["schema_version"] == workspace.WORKSPACE_SCHEMA_VERSION
        assert second["schema_version"] == workspace.WORKSPACE_SCHEMA_VERSION
        with sqlite3.connect(database) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert {
            "workspace_meta",
            "monitor_tasks",
            "task_runs",
            "price_alert_rules",
            "notification_policies",
            "travel_lists",
            "travel_list_hotels",
        }.issubset(tables)


def test_workspace_v1_adds_runtime_revision_without_rewriting_tasks():
    cfg = _config()
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                CREATE TABLE monitor_tasks (
                    task_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    desired_state TEXT NOT NULL DEFAULT 'paused',
                    runtime_state TEXT NOT NULL DEFAULT 'idle',
                    config_json TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    last_started_at REAL,
                    last_stopped_at REAL,
                    next_run_at REAL,
                    last_error TEXT NOT NULL DEFAULT '',
                    result_summary_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO monitor_tasks(
                    task_id, name, desired_state, runtime_state, config_json,
                    sort_order, revision, created_at, updated_at
                ) VALUES ('legacy', 'Legacy', 'paused', 'idle', ?, 0, 7, 1, 1)
                """,
                (json.dumps(workspace.task_config_snapshot(cfg)),),
            )
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            initialized = workspace.initialize_workspace()
            task = workspace.get_task("legacy")

    assert initialized["schema_version"] == workspace.WORKSPACE_SCHEMA_VERSION
    assert task["revision"] == 7
    assert task["runtime_revision"] == 0
    assert task["config"]["hotel_codes"] == ["00001"]


def test_default_task_imports_search_config_without_notification_secrets():
    cfg = _config()
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            task_id = workspace.ensure_default_task(cfg)
            tasks = workspace.list_tasks()

    assert task_id == workspace.DEFAULT_TASK_ID
    assert len(tasks) == 1
    stored = tasks[0]["config"]
    assert stored["hotel_codes"] == ["00001"]
    assert stored["room_requirement"] == "single"
    serialized = json.dumps(stored)
    assert "secret-bark-key" not in serialized
    assert "secret-bot-token" not in serialized
    assert "secret-chat-id" not in serialized
    assert "secret-mail-password" not in serialized


def test_default_task_creation_keeps_existing_tasks_unchanged():
    cfg = _config()
    cfg.start_date = "2026-08-01"
    cfg.end_date = "2026-08-02"
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.ensure_default_task(cfg)
            first = workspace.list_tasks()
            cfg.start_date = "2026-09-01"
            workspace.ensure_default_task(cfg)
            second = workspace.list_tasks()

    assert len(second) == 1
    assert second[0]["config"]["start_date"] == first[0]["config"]["start_date"]


def test_task_config_round_trip_preserves_global_credentials_outside_task():
    cfg = _config()
    snapshot = workspace.task_config_snapshot(cfg)

    restored = workspace.app_config_from_task_config(snapshot, base=cfg)

    assert restored.hotel_codes == ["00001"]
    assert restored.room_requirement == "single"
    assert restored.om_requirement == "single"
    assert restored.bark_key == "secret-bark-key"
    assert restored.bot_token == "secret-bot-token"
    assert "bark_key" not in snapshot
    assert "bot_token" not in snapshot
    assert "smtp_pass" not in snapshot


def test_task_config_normalizes_legacy_room_requirement_and_selected_hotels():
    cfg = _config()
    raw = workspace.task_config_snapshot(cfg)
    raw.pop("room_requirement")
    raw["om_requirement"] = "twin"
    raw["hotel_codes"] = ["00001", "routeinn:7", "00001"]
    raw["selected_hotels"] = [{
        "code": "00001",
        "name_primary": "Safe Hotel",
        "bot_token": "nested-secret",
    }]

    normalized = workspace.validate_task_config(raw)

    assert normalized["room_requirement"] == "twin"
    assert "om_requirement" not in normalized
    assert normalized["hotel_codes"] == ["00001", "routeinn:7"]
    assert [hotel["code"] for hotel in normalized["selected_hotels"]] == [
        "00001",
        "routeinn:7",
    ]
    assert normalized["selected_hotels"][1]["provider"] == "routeinn"
    assert "nested-secret" not in json.dumps(normalized)


@pytest.mark.parametrize(
    ("patch_data", "message"),
    [
        ({"end_date": "not-a-date"}, "YYYY-MM-DD"),
        ({"people": 0}, "people"),
        ({"enabled_providers": []}, "provider"),
        ({"room_requirement": "suite"}, "room_requirement"),
        ({"radius_lat": 35.0, "radius_lng": None}, "provided together"),
    ],
)
def test_task_config_rejects_invalid_search_fields(patch_data, message):
    with pytest.raises(workspace.TaskValidationError, match=message):
        workspace.validate_task_config(patch_data)


def test_task_crud_duplicate_and_patch_update_are_revisioned():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            created = workspace.create_task(
                "Tokyo",
                _config(),
                task_id="tokyo",
            )
            updated = workspace.update_task(
                "tokyo",
                name="Tokyo Weekend",
                config={"people": 2},
                expected_revision=created["revision"],
            )
            copied = workspace.duplicate_task(
                "tokyo",
                name="Tokyo Copy",
                new_task_id="tokyo-copy",
            )
            fetched = workspace.get_task("tokyo")
            deleted = workspace.delete_task(
                "tokyo-copy",
                expected_revision=copied["revision"],
            )

    assert created["revision"] == 1
    assert updated["revision"] == 2
    assert updated["config"]["people"] == 2
    assert updated["config"]["hotel_codes"] == ["00001"]
    assert fetched["name"] == "Tokyo Weekend"
    assert copied["desired_state"] == "paused"
    assert copied["runtime_state"] == "idle"
    assert copied["config"] == updated["config"]
    assert deleted["task_id"] == "tokyo-copy"


def test_task_update_uses_optimistic_revision_lock():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            task = workspace.create_task("Tokyo", _config(), task_id="tokyo")
            workspace.update_task(
                "tokyo",
                name="First editor",
                expected_revision=task["revision"],
            )
            with pytest.raises(workspace.TaskConflictError, match="revision conflict"):
                workspace.update_task(
                    "tokyo",
                    name="Stale editor",
                    expected_revision=task["revision"],
                )
            current = workspace.get_task("tokyo")

    assert current["name"] == "First editor"
    assert current["revision"] == 2


def test_reorder_is_atomic_and_increments_only_changed_task_revisions():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            first = workspace.create_task("First", _config(), task_id="first")
            second = workspace.create_task("Second", _config(), task_id="second")
            third = workspace.create_task("Third", _config(), task_id="third")
            reordered = workspace.reorder_tasks(
                ["third", "second", "first"],
                expected_revisions={
                    "first": first["revision"],
                    "second": second["revision"],
                    "third": third["revision"],
                },
            )
            before_failed_reorder = workspace.list_tasks()
            with pytest.raises(workspace.TaskValidationError):
                workspace.reorder_tasks(["first", "second"])
            after_failed_reorder = workspace.list_tasks()

    assert [task["task_id"] for task in reordered] == ["third", "second", "first"]
    assert reordered[0]["revision"] == 2
    assert reordered[1]["revision"] == 1
    assert reordered[2]["revision"] == 2
    assert after_failed_reorder == before_failed_reorder


def test_desired_and_runtime_states_store_schedule_progress_and_error():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            task = workspace.create_task("Tokyo", _config(), task_id="tokyo")
            desired = workspace.set_task_desired_state(
                "tokyo",
                "active",
                expected_revision=task["revision"],
            )
            running = workspace.set_task_runtime_state(
                "tokyo",
                "scanning",
                next_run_at=180.0,
                result_summary={"done": 1, "total": 3},
                expected_revision=desired["revision"],
                expected_runtime_revision=desired["runtime_revision"],
            )
            failed = workspace.set_task_runtime_state(
                "tokyo",
                "error",
                next_run_at=None,
                last_error="provider timeout",
                expected_revision=running["revision"],
                expected_runtime_revision=running["runtime_revision"],
            )

    assert desired["desired_state"] == "active"
    assert running["runtime_state"] == "scanning"
    assert running["revision"] == desired["revision"]
    assert running["runtime_revision"] == desired["runtime_revision"] + 1
    assert running["last_started_at"] is not None
    assert running["next_run_at"] == 180.0
    assert running["result_summary"] == {"done": 1, "total": 3}
    assert failed["runtime_state"] == "error"
    assert failed["revision"] == running["revision"]
    assert failed["runtime_revision"] == running["runtime_revision"] + 1
    assert failed["last_stopped_at"] is not None
    assert failed["next_run_at"] is None
    assert failed["last_error"] == "provider timeout"


def test_task_run_history_and_delete_cascade():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            task = workspace.create_task("Tokyo", _config(), task_id="tokyo")
            first = workspace.start_task_run(
                task["task_id"],
                run_id="run-1",
                started_at=100.0,
            )
            completed = workspace.finish_task_run(
                first["run_id"],
                state="complete",
                completed_at=110.0,
                result_summary={"available": 2},
            )
            workspace.start_task_run(
                task["task_id"],
                run_id="run-2",
                started_at=120.0,
            )
            runs = workspace.list_task_runs(task["task_id"])
            workspace.delete_task(task["task_id"])
            with sqlite3.connect(database) as connection:
                remaining_runs = connection.execute(
                    "SELECT COUNT(*) FROM task_runs"
                ).fetchone()[0]

    assert completed["state"] == "complete"
    assert completed["completed_at"] == 110.0
    assert completed["result_summary"] == {"available": 2}
    assert [run["run_id"] for run in runs] == ["run-2", "run-1"]
    assert remaining_runs == 0


def test_task_run_states_follow_the_frozen_phase_one_contract():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            task = workspace.create_task("Tokyo", _config(), task_id="tokyo")
            queued = workspace.start_task_run(
                task["task_id"],
                run_id="queued-run",
                state="queued",
                started_at=100.0,
            )
            finished = workspace.finish_task_run(
                queued["run_id"],
                state="cancelled",
                completed_at=101.0,
            )
            with pytest.raises(workspace.TaskConflictError, match="already terminal"):
                workspace.finish_task_run(finished["run_id"], state="failed")
            with pytest.raises(workspace.TaskValidationError, match="queued or running"):
                workspace.start_task_run(
                    task["task_id"],
                    run_id="invalid-run",
                    state="complete",
                )

    assert queued["state"] == "queued"
    assert finished["state"] == "cancelled"


def test_active_run_listing_promotion_and_restart_interruption_are_atomic():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            first_task = workspace.create_task("First", _config(), task_id="first")
            second_task = workspace.create_task("Second", _config(), task_id="second")
            first_run = workspace.start_task_run(
                first_task["task_id"],
                run_id="first-run",
                state="queued",
                started_at=10.0,
            )
            second_run = workspace.start_task_run(
                second_task["task_id"],
                run_id="second-run",
                state="running",
                started_at=20.0,
            )
            terminal_run = workspace.start_task_run(
                second_task["task_id"],
                run_id="terminal-run",
                state="running",
                started_at=5.0,
            )
            workspace.finish_task_run(
                terminal_run["run_id"],
                state="complete",
                completed_at=6.0,
            )
            promoted = workspace.mark_task_run_running(first_run["run_id"])
            active_for_first = workspace.list_active_task_runs(first_task["task_id"])
            active_all = workspace.list_active_task_runs()
            interrupted = workspace.interrupt_active_task_runs(
                completed_at=30.0,
                error="restart recovery",
            )
            remaining = workspace.list_active_task_runs()
            all_second_runs = workspace.list_task_runs(second_task["task_id"])
            with pytest.raises(workspace.TaskConflictError, match="not queued"):
                workspace.mark_task_run_running(second_run["run_id"])

    assert promoted["state"] == "running"
    assert [run["run_id"] for run in active_for_first] == ["first-run"]
    assert [run["run_id"] for run in active_all] == ["first-run", "second-run"]
    assert [run["state"] for run in interrupted] == ["interrupted", "interrupted"]
    assert all(run["completed_at"] == 30.0 for run in interrupted)
    assert all(run["error"] == "restart recovery" for run in interrupted)
    assert remaining == []
    assert next(run for run in all_second_runs if run["run_id"] == "terminal-run")[
        "state"
    ] == "complete"


def test_runtime_updates_do_not_create_definition_revision_conflicts():
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            created = workspace.create_task("Tokyo", _config(), task_id="tokyo")
            scanning = workspace.set_task_runtime_state(
                "tokyo",
                "scanning",
                expected_runtime_revision=created["runtime_revision"],
            )
            renamed = workspace.update_task(
                "tokyo",
                name="Tokyo Weekend",
                expected_revision=created["revision"],
            )
            waiting = workspace.set_task_runtime_state(
                "tokyo",
                "waiting",
                next_run_at=500.0,
                expected_runtime_revision=scanning["runtime_revision"],
            )
            with pytest.raises(
                workspace.TaskConflictError,
                match="runtime revision conflict",
            ):
                workspace.set_task_runtime_state(
                    "tokyo",
                    "idle",
                    expected_runtime_revision=scanning["runtime_revision"],
                )

    assert scanning["revision"] == created["revision"]
    assert renamed["revision"] == created["revision"] + 1
    assert renamed["runtime_revision"] == scanning["runtime_revision"]
    assert waiting["revision"] == renamed["revision"]
    assert waiting["runtime_revision"] == scanning["runtime_revision"] + 1


def test_task_table_never_serializes_notification_fields_from_mapping():
    config = workspace.task_config_snapshot(_config())
    config.update({
        "bark_key": "top-secret",
        "smtp_pass": "mail-secret",
        "notify_available": True,
    })
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = str(Path(tmp_dir) / "workspace.sqlite3")
        with patch.object(workspace, "HOTEL_DATABASE_PATH", database):
            workspace.create_task("Tokyo", config, task_id="tokyo")
            with sqlite3.connect(database) as connection:
                stored = connection.execute(
                    "SELECT config_json FROM monitor_tasks WHERE task_id='tokyo'"
                ).fetchone()[0]

    assert "top-secret" not in stored
    assert "mail-secret" not in stored
    assert "bark_key" not in stored
    assert "smtp_pass" not in stored
