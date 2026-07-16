import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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
