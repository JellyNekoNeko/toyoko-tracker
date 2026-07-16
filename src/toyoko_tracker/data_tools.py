"""Portable data archives, transactional imports, backups, and storage cleanup."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from .settings import (
    AUTO_SAVE_FILENAME,
    BACKUP_DIR,
    CONFIG_DIR,
    DESKTOP_DEEP_LINK_INBOX_FILENAME,
    DESKTOP_PREFERENCES_FILENAME,
    DESKTOP_STATE_FILENAME,
    HOTEL_DATABASE_FILENAME,
    HOTEL_DATABASE_PATH,
    IMPORT_DIR,
    MOBILE_ACCESS_FILENAME,
    ROLLBACK_METADATA_PATH,
    SAVE_FILENAME,
    SEARCH_HISTORY_FILENAME,
    UPDATE_DIR,
    __version__,
)
from .workspace import WORKSPACE_SCHEMA_VERSION


ARCHIVE_FORMAT = "toyoko-tracker-backup"
ARCHIVE_VERSION = 1
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_FILES = 100
_ARCHIVE_LOCK = __import__("threading").RLock()

_SECRET_KEYS = frozenset({
    "bot_token",
    "chat_id",
    "bark_key",
    "serverchan_sendkey",
    "smtp_pass",
    "password",
    "passphrase",
    "secret",
    "token",
    "api_key",
    "access_key",
    "private_key",
    "cookie",
    "authorization",
})
_SECRET_KEY_PARTS = ("token", "secret", "password", "passphrase", "sendkey", "private_key")
_TOKEN_IN_TEXT = re.compile(
    r"(?i)(token|secret|password|passphrase|sendkey|api[_-]?key)"
    r"(\s*[:=]\s*)([^&\s,;]+)"
)

_COMPONENT_TABLES: dict[str, tuple[str, ...]] = {
    "tasks": ("workspace_meta", "monitor_tasks"),
    "rules": ("price_alert_rules", "notification_policies"),
    "travel": ("travel_lists", "travel_list_hotels", "travel_list_links"),
    "flexible": ("flexible_stay_jobs", "flexible_stay_nights", "flexible_stay_results"),
}
_HISTORY_TABLES: dict[str, tuple[str, ...]] = {
    "task_runs": ("task_runs",),
    "prices": ("scan_observations", "price_calendar_days"),
    "alerts": ("alert_observations", "alert_batches", "alert_events", "alert_deliveries"),
    "events": ("tracker_events", "notification_deliveries"),
}
_REBUILDABLE_TABLES = ("hotels", "provider_sync", "scan_cache", "runtime_checkpoints", "alert_meta")
_TABLE_ORDER = (
    "workspace_meta",
    "monitor_tasks",
    "price_alert_rules",
    "notification_policies",
    "travel_lists",
    "travel_list_hotels",
    "travel_list_links",
    "flexible_stay_jobs",
    "flexible_stay_nights",
    "flexible_stay_results",
    "task_runs",
    "scan_observations",
    "price_calendar_days",
    "alert_observations",
    "alert_batches",
    "alert_events",
    "alert_deliveries",
    "tracker_events",
    "notification_deliveries",
    "hotels",
    "provider_sync",
    "scan_cache",
    "runtime_checkpoints",
    "alert_meta",
)
_PORTABLE_FILES = (AUTO_SAVE_FILENAME, SEARCH_HISTORY_FILENAME)
_FULL_FILES = (
    AUTO_SAVE_FILENAME,
    SAVE_FILENAME,
    SEARCH_HISTORY_FILENAME,
    MOBILE_ACCESS_FILENAME,
    DESKTOP_PREFERENCES_FILENAME,
    DESKTOP_STATE_FILENAME,
    DESKTOP_DEEP_LINK_INBOX_FILENAME,
)


class DataArchiveError(ValueError):
    """Raised when an archive is malformed or incompatible."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".toyoko-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def redact_secrets(value: Any) -> Any:
    """Return a copy that omits credential fields and masks inline tokens."""

    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        configured: dict[str, bool] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("-", "_")
            if normalized == "_configured_secrets":
                if isinstance(raw_value, Mapping):
                    output[key] = {
                        str(name): bool(configured)
                        for name, configured in raw_value.items()
                    }
                continue
            sensitive = normalized in _SECRET_KEYS or any(part in normalized for part in _SECRET_KEY_PARTS)
            if sensitive:
                configured[key] = bool(raw_value)
                continue
            output[key] = redact_secrets(raw_value)
        if configured:
            output["_configured_secrets"] = configured
        return output
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _TOKEN_IN_TEXT.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", value)
    return value


def _read_json(path: Path, fallback: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError, TypeError):
        return fallback


def _database_snapshot(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source, timeout=30)) as source_connection, source_connection:
        source_connection.execute("PRAGMA busy_timeout=30000")
        try:
            source_connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.DatabaseError:
            pass
        with (
            closing(sqlite3.connect(destination)) as destination_connection,
            destination_connection,
        ):
            source_connection.backup(destination_connection)
            destination_connection.execute("PRAGMA journal_mode=DELETE")
            result = destination_connection.execute("PRAGMA integrity_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise DataArchiveError("database snapshot failed its integrity check")


def _checkpoint_database(path: Path) -> None:
    if not path.exists():
        return
    with closing(sqlite3.connect(path, timeout=30)) as connection, connection:
        connection.execute("PRAGMA busy_timeout=30000")
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result and int(result[0] or 0) != 0:
            raise DataArchiveError("database is busy and could not be checkpointed")


def _existing_tables(connection: sqlite3.Connection, schema: str = "main") -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _table_count(connection: sqlite3.Connection, table: str, schema: str = "main") -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0])


def _normalize_components(
    components: Optional[Mapping[str, Any]],
    include_history: bool | Sequence[str],
    *,
    purpose: str,
) -> tuple[dict[str, bool], list[str], list[str]]:
    if purpose != "portable":
        component_flags = {name: True for name in _COMPONENT_TABLES}
        history = list(_HISTORY_TABLES)
        tables = list(_TABLE_ORDER)
        return component_flags, history, tables

    component_flags = {
        name: bool((components or {}).get(name, True))
        for name in _COMPONENT_TABLES
    }
    if component_flags["rules"]:
        component_flags["tasks"] = True
    if component_flags["travel"]:
        component_flags["tasks"] = True
    if component_flags["flexible"]:
        component_flags["tasks"] = True
    if include_history is True:
        history = list(_HISTORY_TABLES)
    elif isinstance(include_history, Sequence) and not isinstance(include_history, (str, bytes)):
        history = [name for name in include_history if name in _HISTORY_TABLES]
    else:
        history = []
    if "task_runs" in history:
        component_flags["tasks"] = True
    if "alerts" in history:
        component_flags["tasks"] = True
        component_flags["rules"] = True
    tables: list[str] = []
    for name, enabled in component_flags.items():
        if enabled:
            tables.extend(_COMPONENT_TABLES[name])
    for name in history:
        tables.extend(_HISTORY_TABLES[name])
    return component_flags, history, list(dict.fromkeys(tables))


def _prune_snapshot(path: Path, exported_tables: Sequence[str]) -> dict[str, int]:
    keep = set(exported_tables)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        tables = _existing_tables(connection)
        for table in tables:
            if table not in keep:
                connection.execute(f'DELETE FROM "{table}"')
        counts = {
            table: _table_count(connection, table)
            for table in exported_tables
            if table in tables
        }
        connection.commit()
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise DataArchiveError("portable database failed its integrity check")
    return counts


def create_export_archive(
    destination: Optional[str | Path] = None,
    *,
    components: Optional[Mapping[str, Any]] = None,
    include_history: bool | Sequence[str] = False,
    purpose: str = "portable",
    config_dir: Optional[str | Path] = None,
    database_path: Optional[str | Path] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Create one self-verifying ZIP archive from a consistent SQLite snapshot."""

    root = Path(config_dir or CONFIG_DIR)
    database = Path(database_path or (root / HOTEL_DATABASE_FILENAME if config_dir else HOTEL_DATABASE_PATH))
    purpose = str(purpose or "portable").strip().lower()
    if purpose not in {"portable", "pre-upgrade", "pre-import", "manual-full"}:
        raise DataArchiveError("unsupported backup purpose")
    component_flags, history, exported_tables = _normalize_components(
        components,
        include_history,
        purpose=purpose,
    )
    backup_dir = root / Path(BACKUP_DIR).name
    backup_dir.mkdir(parents=True, exist_ok=True)
    if destination is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination_path = backup_dir / f"toyoko-{purpose}-{timestamp}-{uuid.uuid4().hex[:8]}.zip"
    else:
        destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    with _ARCHIVE_LOCK, tempfile.TemporaryDirectory(prefix="toyoko-export-") as temporary_dir:
        temporary = Path(temporary_dir)
        snapshot = temporary / "database.sqlite3"
        _database_snapshot(database, snapshot)
        if purpose == "portable":
            table_counts = _prune_snapshot(snapshot, exported_tables)
        else:
            with closing(sqlite3.connect(snapshot)) as connection, connection:
                tables = _existing_tables(connection)
                table_counts = {
                    table: _table_count(connection, table)
                    for table in exported_tables
                    if table in tables
                }

        payloads: dict[str, bytes] = {"data/database.sqlite3": snapshot.read_bytes()}
        filenames = _PORTABLE_FILES if purpose == "portable" else _FULL_FILES
        for filename in filenames:
            path = root / filename
            if not path.is_file():
                continue
            if purpose == "portable":
                value = _read_json(path, {})
                payloads[f"data/files/{filename}"] = _json_bytes(redact_secrets(value))
            else:
                payloads[f"data/files/{filename}"] = path.read_bytes()

        files = [
            {
                "path": name,
                "size": len(content),
                "sha256": _sha256_bytes(content),
            }
            for name, content in sorted(payloads.items())
        ]
        manifest = {
            "format": ARCHIVE_FORMAT,
            "format_version": ARCHIVE_VERSION,
            "archive_id": uuid.uuid4().hex,
            "purpose": purpose,
            "created_at": _utc_now(),
            "app_version": __version__,
            "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
            "components": component_flags,
            "history": history,
            "exported_tables": exported_tables,
            "table_counts": table_counts,
            "contains_credentials": purpose != "portable",
            "files": files,
            "metadata": dict(metadata or {}),
        }
        temporary_archive = destination_path.with_suffix(destination_path.suffix + ".part")
        temporary_archive.unlink(missing_ok=True)
        with zipfile.ZipFile(
            temporary_archive,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as bundle:
            bundle.writestr("manifest.json", _json_bytes(manifest))
            for name, content in payloads.items():
                bundle.writestr(name, content)
        os.replace(temporary_archive, destination_path)
    return {
        "path": str(destination_path),
        "filename": destination_path.name,
        "size": destination_path.stat().st_size,
        "sha256": _sha256_file(destination_path),
        "manifest": manifest,
    }


def _validate_member_name(name: str) -> None:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise DataArchiveError(f"unsafe archive member: {name}")


def _read_validated_archive(path: Path, extract_to: Optional[Path] = None) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not path.is_file():
        raise DataArchiveError("archive file was not found")
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise DataArchiveError("archive is too large")
    try:
        bundle = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise DataArchiveError("archive is not a valid ZIP file") from exc
    with bundle:
        members = bundle.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise DataArchiveError("archive contains too many files")
        total_uncompressed = 0
        for member in members:
            _validate_member_name(member.filename)
            if member.file_size > MAX_ARCHIVE_BYTES:
                raise DataArchiveError("archive member is too large")
            total_uncompressed += int(member.file_size)
            if total_uncompressed > MAX_ARCHIVE_BYTES:
                raise DataArchiveError("archive expands beyond the size limit")
        try:
            manifest = json.loads(bundle.read("manifest.json"))
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise DataArchiveError("archive manifest is missing or invalid") from exc
        if manifest.get("format") != ARCHIVE_FORMAT:
            raise DataArchiveError("archive format is not recognized")
        if int(manifest.get("format_version") or 0) != ARCHIVE_VERSION:
            raise DataArchiveError("archive format version is not supported")
        if int(manifest.get("workspace_schema_version") or 0) > WORKSPACE_SCHEMA_VERSION:
            raise DataArchiveError("archive workspace schema is newer than this application")
        payloads: dict[str, bytes] = {}
        expected_files = manifest.get("files")
        if not isinstance(expected_files, list):
            raise DataArchiveError("archive file manifest is invalid")
        for item in expected_files:
            if not isinstance(item, Mapping):
                raise DataArchiveError("archive file manifest is invalid")
            name = str(item.get("path") or "")
            _validate_member_name(name)
            try:
                content = bundle.read(name)
            except KeyError as exc:
                raise DataArchiveError(f"archive member is missing: {name}") from exc
            if len(content) != int(item.get("size") or -1):
                raise DataArchiveError(f"archive member size mismatch: {name}")
            if _sha256_bytes(content) != str(item.get("sha256") or "").lower():
                raise DataArchiveError(f"archive member checksum mismatch: {name}")
            payloads[name] = content
            if extract_to is not None:
                target = extract_to / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        if "data/database.sqlite3" not in payloads:
            raise DataArchiveError("archive database snapshot is missing")
    return dict(manifest), payloads


def _primary_key_columns(connection: sqlite3.Connection, table: str, schema: str = "main") -> list[str]:
    rows = connection.execute(f'PRAGMA "{schema}".table_info("{table}")').fetchall()
    return [
        str(row[1])
        for row in sorted(rows, key=lambda row: int(row[5] or 0))
        if int(row[5] or 0) > 0
    ]


def _conflict_count(
    current: sqlite3.Connection,
    source_path: Path,
    table: str,
) -> int:
    current.execute("ATTACH DATABASE ? AS preview_source", (str(source_path),))
    try:
        current_tables = _existing_tables(current)
        source_tables = _existing_tables(current, "preview_source")
        if table not in current_tables or table not in source_tables:
            return 0
        primary = _primary_key_columns(current, table)
        source_primary = _primary_key_columns(current, table, "preview_source")
        if not primary or primary != source_primary:
            return 0
        predicate = " AND ".join(
            f'main."{table}"."{column}" = preview_source."{table}"."{column}"'
            for column in primary
        )
        return int(current.execute(
            f'SELECT COUNT(*) FROM preview_source."{table}" '
            f'WHERE EXISTS (SELECT 1 FROM main."{table}" WHERE {predicate})'
        ).fetchone()[0])
    finally:
        current.execute("DETACH DATABASE preview_source")


def preview_import_archive(
    archive_path: str | Path,
    *,
    database_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Validate and compare an archive without changing application data."""

    archive = Path(archive_path)
    database = Path(database_path or HOTEL_DATABASE_PATH)
    with _ARCHIVE_LOCK, tempfile.TemporaryDirectory(prefix="toyoko-preview-") as temporary_dir:
        temporary = Path(temporary_dir)
        manifest, _ = _read_validated_archive(archive, temporary)
        snapshot = temporary / "data" / "database.sqlite3"
        with closing(sqlite3.connect(snapshot)) as source, source:
            result = source.execute("PRAGMA integrity_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise DataArchiveError("archive database failed its integrity check")
            source_tables = _existing_tables(source)
            source_counts = {
                table: _table_count(source, table)
                for table in manifest.get("exported_tables", [])
                if table in source_tables
            }
        conflicts: dict[str, int] = {}
        if database.exists():
            with closing(sqlite3.connect(database)) as current, current:
                for table in manifest.get("exported_tables", []):
                    conflicts[table] = _conflict_count(current, snapshot, str(table))
        else:
            conflicts = {str(table): 0 for table in manifest.get("exported_tables", [])}
    return {
        "valid": True,
        "archive": str(archive),
        "archive_sha256": _sha256_file(archive),
        "manifest": manifest,
        "table_counts": source_counts,
        "conflicts": conflicts,
        "conflict_total": sum(conflicts.values()),
        "strategies": ["keep_existing", "overwrite", "replace_imported"],
        "read_only": True,
    }


def _columns(connection: sqlite3.Connection, table: str, schema: str = "main") -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(f'PRAGMA "{schema}".table_info("{table}")').fetchall()
    ]


def _merge_table(connection: sqlite3.Connection, table: str, strategy: str) -> int:
    current_columns = _columns(connection, table)
    source_columns = set(_columns(connection, table, "import_source"))
    columns = [column for column in current_columns if column in source_columns]
    if not columns:
        return 0
    quoted = ",".join(f'"{column}"' for column in columns)
    if strategy == "keep_existing":
        connection.execute(
            f'INSERT OR IGNORE INTO main."{table}" ({quoted}) '
            f'SELECT {quoted} FROM import_source."{table}"'
        )
    else:
        primary = _primary_key_columns(connection, table)
        updates = [column for column in columns if column not in primary]
        if primary and updates:
            conflict = ",".join(f'"{column}"' for column in primary)
            assignments = ",".join(
                f'"{column}"=excluded."{column}"'
                for column in updates
            )
            connection.execute(
                f'INSERT INTO main."{table}" ({quoted}) '
                f'SELECT {quoted} FROM import_source."{table}" WHERE true '
                f'ON CONFLICT ({conflict}) DO UPDATE SET {assignments}'
            )
        else:
            connection.execute(
                f'INSERT OR IGNORE INTO main."{table}" ({quoted}) '
                f'SELECT {quoted} FROM import_source."{table}"'
            )
    return int(connection.execute("SELECT changes()").fetchone()[0])


def _merge_settings(current: Any, incoming: Any, strategy: str) -> Any:
    if not isinstance(current, Mapping) or not isinstance(incoming, Mapping):
        return incoming if strategy != "keep_existing" else current
    output = dict(current)
    for key, value in incoming.items():
        if key == "_configured_secrets":
            continue
        if strategy == "keep_existing" and key in output:
            continue
        output[key] = value
    return output


def apply_import_archive(
    archive_path: str | Path,
    strategy: str = "keep_existing",
    *,
    config_dir: Optional[str | Path] = None,
    database_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    """Apply a validated archive via a staged database and rollback backup."""

    strategy = str(strategy or "keep_existing")
    if strategy not in {"keep_existing", "overwrite", "replace_imported"}:
        raise DataArchiveError("unsupported import strategy")
    root = Path(config_dir or CONFIG_DIR)
    database = Path(database_path or (root / HOTEL_DATABASE_FILENAME if config_dir else HOTEL_DATABASE_PATH))
    archive = Path(archive_path)
    with _ARCHIVE_LOCK, tempfile.TemporaryDirectory(prefix="toyoko-import-") as temporary_dir:
        temporary = Path(temporary_dir)
        manifest, payloads = _read_validated_archive(archive, temporary)
        source_database = temporary / "data" / "database.sqlite3"
        _checkpoint_database(database)
        rollback = create_export_archive(
            purpose="pre-import",
            config_dir=root,
            database_path=database,
            metadata={
                "source_archive": archive.name,
                "source_sha256": _sha256_file(archive),
                "strategy": strategy,
            },
        )
        staged_database = temporary / "staged.sqlite3"
        _database_snapshot(database, staged_database)
        changed: dict[str, int] = {}
        with closing(sqlite3.connect(staged_database)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("ATTACH DATABASE ? AS import_source", (str(source_database),))
            current_tables = _existing_tables(connection)
            source_tables = _existing_tables(connection, "import_source")
            exported = [
                str(table)
                for table in manifest.get("exported_tables", [])
                if str(table) in current_tables and str(table) in source_tables
            ]
            try:
                connection.execute("BEGIN IMMEDIATE")
                if strategy == "replace_imported":
                    for table in reversed(_TABLE_ORDER):
                        if table in exported:
                            connection.execute(f'DELETE FROM main."{table}"')
                    merge_strategy = "overwrite"
                else:
                    merge_strategy = strategy
                for table in _TABLE_ORDER:
                    if table in exported:
                        changed[table] = _merge_table(connection, table, merge_strategy)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.execute("DETACH DATABASE import_source")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or str(integrity[0]).lower() != "ok":
                raise DataArchiveError("imported database failed its integrity check")
            foreign_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_errors:
                raise DataArchiveError("imported database contains broken relationships")

        file_updates: dict[Path, bytes] = {}
        portable = not bool(manifest.get("contains_credentials"))
        for member_name, content in payloads.items():
            if not member_name.startswith("data/files/"):
                continue
            filename = Path(member_name).name
            if filename not in _FULL_FILES:
                continue
            target = root / filename
            if portable:
                incoming = json.loads(content)
                current = _read_json(target, {})
                content = _json_bytes(_merge_settings(current, incoming, strategy))
            file_updates[target] = content

        database.parent.mkdir(parents=True, exist_ok=True)
        previous_database = database.with_name(f".{database.name}.phase6-{uuid.uuid4().hex}.previous")
        original_files: dict[Path, Optional[bytes]] = {
            target: target.read_bytes() if target.exists() else None
            for target in file_updates
        }
        swapped = False
        try:
            if database.exists():
                os.replace(database, previous_database)
            os.replace(staged_database, database)
            swapped = True
            for suffix in ("-wal", "-shm"):
                Path(str(database) + suffix).unlink(missing_ok=True)
            for target, content in file_updates.items():
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary_file = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
                temporary_file.write_bytes(content)
                os.replace(temporary_file, target)
        except Exception:
            for target, content in original_files.items():
                if content is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(content)
            if swapped:
                database.unlink(missing_ok=True)
            if previous_database.exists():
                os.replace(previous_database, database)
            raise
        finally:
            previous_database.unlink(missing_ok=True)

    metadata = {
        "kind": "import",
        "state": "applied",
        "created_at": _utc_now(),
        "archive": str(archive),
        "archive_sha256": _sha256_file(archive),
        "rollback_archive": rollback["path"],
        "rollback_sha256": rollback["sha256"],
        "strategy": strategy,
    }
    _atomic_json(root / Path(ROLLBACK_METADATA_PATH).name, metadata)
    return {
        "applied": True,
        "strategy": strategy,
        "changed": changed,
        "rollback": rollback,
        "restart_recommended": True,
    }


def create_pre_upgrade_backup(
    target_version: str,
    asset_name: str = "",
    *,
    config_dir: Optional[str | Path] = None,
    database_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    root = Path(config_dir or CONFIG_DIR)
    backup = create_export_archive(
        purpose="pre-upgrade",
        config_dir=root,
        database_path=database_path,
        metadata={
            "current_version": __version__,
            "target_version": str(target_version or ""),
            "asset_name": str(asset_name or ""),
        },
    )
    rollback = {
        "kind": "application-upgrade",
        "state": "prepared",
        "created_at": _utc_now(),
        "current_version": __version__,
        "target_version": str(target_version or ""),
        "asset_name": str(asset_name or ""),
        "data_archive": backup["path"],
        "data_archive_sha256": backup["sha256"],
    }
    metadata_path = root / Path(ROLLBACK_METADATA_PATH).name
    _atomic_json(metadata_path, rollback)
    return {**backup, "rollback_metadata_path": str(metadata_path)}


def update_rollback_metadata(
    updates: Mapping[str, Any],
    *,
    config_dir: Optional[str | Path] = None,
) -> dict[str, Any]:
    root = Path(config_dir or CONFIG_DIR)
    path = root / Path(ROLLBACK_METADATA_PATH).name
    value = _read_json(path, {})
    if not isinstance(value, dict):
        value = {}
    value.update(dict(updates))
    value["updated_at"] = _utc_now()
    _atomic_json(path, value)
    return value


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def storage_status(
    *,
    config_dir: Optional[str | Path] = None,
    database_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    root = Path(config_dir or CONFIG_DIR)
    database = Path(database_path or (root / HOTEL_DATABASE_FILENAME if config_dir else HOTEL_DATABASE_PATH))
    tables: dict[str, int] = {}
    schema_version = 0
    if database.exists():
        with closing(sqlite3.connect(database)) as connection, connection:
            existing = _existing_tables(connection)
            tables = {
                table: _table_count(connection, table)
                for table in _TABLE_ORDER
                if table in existing
            }
            if "workspace_meta" in existing:
                row = connection.execute(
                    "SELECT value FROM workspace_meta WHERE key='schema_version'"
                ).fetchone()
                schema_version = int(row[0]) if row else 0
    backup_dir = root / Path(BACKUP_DIR).name
    import_dir = root / Path(IMPORT_DIR).name
    update_dir = root / Path(UPDATE_DIR).name
    return {
        "config_dir": str(root),
        "database_path": str(database),
        "database_size": database.stat().st_size if database.exists() else 0,
        "total_size": _directory_size(root),
        "backup_size": _directory_size(backup_dir),
        "import_size": _directory_size(import_dir),
        "update_size": _directory_size(update_dir),
        "backup_count": len(list(backup_dir.glob("*.zip"))) if backup_dir.exists() else 0,
        "import_count": len(list(import_dir.glob("*.zip"))) if import_dir.exists() else 0,
        "workspace_schema_version": schema_version,
        "supported_schema_version": WORKSPACE_SCHEMA_VERSION,
        "tables": tables,
        "rollback": _read_json(root / Path(ROLLBACK_METADATA_PATH).name, {}),
    }


def _delete_older(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    cutoff: float,
    extra: str = "",
) -> int:
    if table not in _existing_tables(connection):
        return 0
    connection.execute(
        f'DELETE FROM "{table}" WHERE "{column}" < ? {extra}',
        (cutoff,),
    )
    return int(connection.execute("SELECT changes()").fetchone()[0])


def cleanup_storage(
    categories: Iterable[str],
    *,
    older_than_days: int = 30,
    dry_run: bool = False,
    config_dir: Optional[str | Path] = None,
    database_path: Optional[str | Path] = None,
) -> dict[str, Any]:
    root = Path(config_dir or CONFIG_DIR)
    database = Path(database_path or (root / HOTEL_DATABASE_FILENAME if config_dir else HOTEL_DATABASE_PATH))
    selected = {str(item) for item in categories}
    allowed = {
        "cache",
        "events",
        "alerts",
        "analytics",
        "prices",
        "task_runs",
        "completed_flexible",
        "imports",
        "updates",
        "backups",
    }
    if not selected or not selected <= allowed:
        raise DataArchiveError("cleanup categories are invalid")
    days = max(1, min(3650, int(older_than_days)))
    cutoff = time.time() - days * 86400
    deleted: dict[str, int] = {}
    before = _directory_size(root)
    if database.exists():
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            if dry_run:
                connection.execute("BEGIN")
            if "cache" in selected:
                for table in ("scan_cache", "runtime_checkpoints"):
                    if table in _existing_tables(connection):
                        count = _table_count(connection, table)
                        connection.execute(f'DELETE FROM "{table}"')
                        deleted[table] = count
            if "events" in selected:
                if {
                    "notification_deliveries",
                    "tracker_events",
                } <= _existing_tables(connection):
                    connection.execute(
                        """
                        DELETE FROM notification_deliveries
                        WHERE event_id IN (
                            SELECT event_id FROM tracker_events WHERE created_at < ?
                        )
                        """,
                        (cutoff,),
                    )
                    deleted["notification_deliveries"] = int(
                        connection.execute("SELECT changes()").fetchone()[0]
                    )
                deleted["tracker_events"] = _delete_older(
                    connection, "tracker_events", "created_at", cutoff
                )
            if "alerts" in selected:
                deleted["alert_observations"] = _delete_older(
                    connection, "alert_observations", "observed_at", cutoff
                )
                deleted["alert_batches"] = _delete_older(
                    connection, "alert_batches", "created_at", cutoff
                )
            if "analytics" in selected:
                deleted["scan_observations"] = _delete_older(
                    connection, "scan_observations", "observed_at", cutoff
                )
            if "prices" in selected:
                deleted["price_calendar_days"] = _delete_older(
                    connection, "price_calendar_days", "observed_at", cutoff
                )
            if "task_runs" in selected:
                deleted["task_runs"] = _delete_older(
                    connection, "task_runs", "started_at", cutoff,
                    "AND state NOT IN ('queued','running')",
                )
            if "completed_flexible" in selected:
                deleted["flexible_stay_jobs"] = _delete_older(
                    connection, "flexible_stay_jobs", "updated_at", cutoff,
                    "AND status IN ('complete','partial','cancelled','failed')",
                )
            if dry_run:
                connection.rollback()
            else:
                connection.commit()
                try:
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except sqlite3.DatabaseError:
                    pass

    for category, directory_name, pattern in (
        ("imports", Path(IMPORT_DIR).name, "*.zip"),
        ("updates", Path(UPDATE_DIR).name, "*"),
        ("backups", Path(BACKUP_DIR).name, "*.zip"),
    ):
        if category not in selected:
            continue
        directory = root / directory_name
        count = 0
        if directory.exists():
            candidates = sorted(directory.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
            keep = 1 if category == "backups" else 0
            for index, item in enumerate(candidates):
                if index < keep or item.stat().st_mtime >= cutoff:
                    continue
                count += 1
                if not dry_run:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink(missing_ok=True)
        deleted[category] = count
    after = before if dry_run else _directory_size(root)
    return {
        "dry_run": bool(dry_run),
        "older_than_days": days,
        "deleted": deleted,
        "bytes_reclaimed": max(0, before - after),
    }
