from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from toyoko_tracker import data_tools, diagnostics
from toyoko_tracker.app import app


def _database(path: Path, *, task_name: str = "Current", cache: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE workspace_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE monitor_tasks (
                task_id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE price_alert_rules (
                rule_id TEXT PRIMARY KEY,
                task_id TEXT,
                name TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE
            );
            CREATE TABLE scan_cache (
                cache_key TEXT PRIMARY KEY,
                stored_at REAL NOT NULL
            );
            CREATE TABLE scan_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at REAL NOT NULL,
                hotel_code TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO workspace_meta VALUES ('schema_version','4',1)"
        )
        connection.execute(
            "INSERT INTO monitor_tasks VALUES ('task-a',?)",
            (task_name,),
        )
        connection.execute(
            "INSERT INTO price_alert_rules VALUES ('rule-a','task-a','Target')"
        )
        if cache:
            connection.execute("INSERT INTO scan_cache VALUES ('cached',1)")
        connection.executemany(
            "INSERT INTO scan_observations(observed_at,hotel_code) VALUES (?,?)",
            [(1, "00001"), (4_000_000_000, "00002")],
        )


def _task_name(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection, connection:
        return str(connection.execute(
            "SELECT name FROM monitor_tasks WHERE task_id='task-a'"
        ).fetchone()[0])


def test_portable_archive_has_manifest_hashes_and_omits_credentials(tmp_path: Path):
    database = tmp_path / "hotel_database.sqlite3"
    _database(database, task_name="Archived")
    (tmp_path / "auto_save.json").write_text(
        json.dumps({
            "people": 2,
            "bot_token": "123456:very-secret-token-value",
            "smtp_pass": "mail-secret",
        }),
        encoding="utf-8",
    )

    archive = data_tools.create_export_archive(
        config_dir=tmp_path,
        database_path=database,
        include_history=False,
    )

    with zipfile.ZipFile(archive["path"]) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        settings = json.loads(bundle.read("data/files/auto_save.json"))
        exported_database = tmp_path / "portable.sqlite3"
        exported_database.write_bytes(bundle.read("data/database.sqlite3"))
        for item in manifest["files"]:
            content = bundle.read(item["path"])
            assert len(content) == item["size"]
            assert hashlib.sha256(content).hexdigest() == item["sha256"]

    assert manifest["contains_credentials"] is False
    assert "bot_token" not in settings
    assert "smtp_pass" not in settings
    assert settings["_configured_secrets"]["bot_token"] is True
    with closing(sqlite3.connect(exported_database)) as connection, connection:
        assert connection.execute("SELECT COUNT(*) FROM scan_cache").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM monitor_tasks").fetchone()[0] == 1


def test_import_preview_is_read_only_and_reports_conflicts(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source_database = source / "hotel_database.sqlite3"
    target_database = target / "hotel_database.sqlite3"
    _database(source_database, task_name="Archived")
    _database(target_database, task_name="Current")
    archive = data_tools.create_export_archive(
        config_dir=source,
        database_path=source_database,
    )
    before = hashlib.sha256(target_database.read_bytes()).hexdigest()

    preview = data_tools.preview_import_archive(
        archive["path"],
        database_path=target_database,
    )

    assert preview["read_only"] is True
    assert preview["valid"] is True
    assert preview["conflict_total"] >= 2
    assert hashlib.sha256(target_database.read_bytes()).hexdigest() == before
    assert _task_name(target_database) == "Current"


def test_import_preview_rejects_payload_checksum_mismatch(tmp_path: Path):
    database = tmp_path / "hotel_database.sqlite3"
    _database(database)
    archive = data_tools.create_export_archive(
        config_dir=tmp_path,
        database_path=database,
    )
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive["path"]) as source, zipfile.ZipFile(broken, "w") as target:
        for member in source.infolist():
            content = source.read(member.filename)
            if member.filename == "data/database.sqlite3":
                content = bytes([content[0] ^ 0x01]) + content[1:]
            target.writestr(member, content)

    with pytest.raises(data_tools.DataArchiveError, match="checksum mismatch"):
        data_tools.preview_import_archive(broken, database_path=database)


def test_import_keep_and_overwrite_preserve_local_credentials(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source_database = source / "hotel_database.sqlite3"
    target_database = target / "hotel_database.sqlite3"
    _database(source_database, task_name="Archived")
    _database(target_database, task_name="Current")
    (source / "auto_save.json").write_text(
        json.dumps({"people": 2, "bot_token": "archived-secret"}),
        encoding="utf-8",
    )
    (target / "auto_save.json").write_text(
        json.dumps({"people": 1, "bot_token": "current-secret"}),
        encoding="utf-8",
    )
    archive = data_tools.create_export_archive(
        config_dir=source,
        database_path=source_database,
    )

    data_tools.apply_import_archive(
        archive["path"],
        "keep_existing",
        config_dir=target,
        database_path=target_database,
    )
    assert _task_name(target_database) == "Current"
    assert json.loads((target / "auto_save.json").read_text())["people"] == 1

    result = data_tools.apply_import_archive(
        archive["path"],
        "overwrite",
        config_dir=target,
        database_path=target_database,
    )
    settings = json.loads((target / "auto_save.json").read_text())
    assert _task_name(target_database) == "Archived"
    assert settings["people"] == 2
    assert settings["bot_token"] == "current-secret"
    assert Path(result["rollback"]["path"]).is_file()
    assert json.loads((target / "rollback.json").read_text())["state"] == "applied"


def test_failed_import_does_not_replace_current_database(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source_database = source / "hotel_database.sqlite3"
    target_database = target / "hotel_database.sqlite3"
    _database(source_database, task_name="Archived")
    _database(target_database, task_name="Current")
    archive = data_tools.create_export_archive(
        config_dir=source,
        database_path=source_database,
    )
    before = hashlib.sha256(target_database.read_bytes()).hexdigest()

    def fail_merge(*_args, **_kwargs):
        raise RuntimeError("injected merge failure")

    monkeypatch.setattr(data_tools, "_merge_table", fail_merge)
    with pytest.raises(RuntimeError, match="injected"):
        data_tools.apply_import_archive(
            archive["path"],
            "overwrite",
            config_dir=target,
            database_path=target_database,
        )

    assert hashlib.sha256(target_database.read_bytes()).hexdigest() == before
    assert _task_name(target_database) == "Current"
    assert list((target / "backups").glob("toyoko-pre-import-*.zip"))


def test_cleanup_and_storage_status_only_remove_selected_history(tmp_path: Path):
    database = tmp_path / "hotel_database.sqlite3"
    _database(database)

    preview = data_tools.cleanup_storage(
        ["cache", "analytics"],
        older_than_days=30,
        dry_run=True,
        config_dir=tmp_path,
        database_path=database,
    )
    assert preview["deleted"]["scan_cache"] == 1
    assert preview["deleted"]["scan_observations"] == 1
    with closing(sqlite3.connect(database)) as connection, connection:
        assert connection.execute("SELECT COUNT(*) FROM scan_cache").fetchone()[0] == 1

    data_tools.cleanup_storage(
        ["cache", "analytics"],
        older_than_days=30,
        config_dir=tmp_path,
        database_path=database,
    )
    status = data_tools.storage_status(config_dir=tmp_path, database_path=database)
    assert status["tables"]["scan_cache"] == 0
    assert status["tables"]["scan_observations"] == 1
    assert status["tables"]["monitor_tasks"] == 1


def test_pre_upgrade_backup_records_rollback_metadata(tmp_path: Path):
    database = tmp_path / "hotel_database.sqlite3"
    _database(database)
    (tmp_path / "auto_save.json").write_text(
        json.dumps({"bot_token": "full-backup-secret"}),
        encoding="utf-8",
    )

    result = data_tools.create_pre_upgrade_backup(
        "0.7.1",
        "ToyokoTracker-macos-arm64.zip",
        config_dir=tmp_path,
        database_path=database,
    )
    metadata = json.loads((tmp_path / "rollback.json").read_text())

    assert Path(result["path"]).is_file()
    assert metadata["state"] == "prepared"
    assert metadata["target_version"] == "0.7.1"
    assert metadata["data_archive_sha256"] == result["sha256"]
    with zipfile.ZipFile(result["path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["purpose"] == "pre-upgrade"
        assert manifest["contains_credentials"] is True


def test_diagnostic_support_bundle_is_redacted_and_self_verifying(tmp_path: Path):
    database = tmp_path / "hotel_database.sqlite3"
    _database(database)
    secret = "pypi-secret-value-1234567890"
    destination = tmp_path / "support.zip"

    bundle = diagnostics.create_support_bundle(
        destination,
        runtime={"state": "idle", "bot_token": secret},
        logs=[f"bot_token={secret}", f"Authorization: Bearer {secret}"],
        known_secrets=[secret],
        config_dir=tmp_path,
        database_path=database,
    )
    verification = diagnostics.verify_support_bundle(
        bundle["path"],
        known_secrets=[secret],
    )
    raw = destination.read_bytes()

    assert verification["valid"] is True
    assert verification["manifest"]["credential_scan"] == "passed"
    assert secret.encode() not in raw
    with zipfile.ZipFile(destination) as archive:
        assert b"[redacted]" in archive.read("report.txt")


def test_phase6_routes_and_cross_platform_matrix_are_present():
    client = app.test_client()
    home = client.get("/")
    storage = client.get("/api/v1/data/storage")
    diagnostic = client.get("/api/v1/diagnostics")

    assert home.status_code == 200
    assert b"phase6-data-card" in home.data
    assert b"phase6-diagnostics-card" in home.data
    assert storage.status_code == 200
    assert storage.get_json()["ok"] is True
    assert diagnostic.status_code == 200
    assert diagnostic.get_json()["ok"] is True

    workflow = Path(".github/workflows/desktop.yml").read_text(encoding="utf-8")
    for target in (
        "windows-x64",
        "windows-arm64",
        "linux-x64",
        "linux-arm64",
        "macos-x64",
        "macos-arm64",
    ):
        assert f"target: {target}" in workflow
    assert "smoke_test_posix.py" in workflow
    assert "verify_desktop_artifact.py" in workflow
