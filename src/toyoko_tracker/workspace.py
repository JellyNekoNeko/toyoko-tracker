from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence

from .models import AppConfig
from .settings import (
    HOTEL_DATABASE_PATH,
    SUPPORTED_PROVIDERS,
)


WORKSPACE_SCHEMA_VERSION = 3
DEFAULT_TASK_ID = "default"
_LOCK = threading.RLock()

DESIRED_TASK_STATES = frozenset({"paused", "active"})
RUNTIME_TASK_STATES = frozenset({
    "idle",
    "queued",
    "scanning",
    "waiting",
    "pausing",
    "error",
})
RUN_STATES = frozenset({
    "queued",
    "running",
    "complete",
    "partial",
    "cancelled",
    "interrupted",
    "failed",
})
ACTIVE_RUN_STATES = frozenset({"queued", "running"})
TERMINAL_RUN_STATES = RUN_STATES - ACTIVE_RUN_STATES

_TASK_CONFIG_FIELDS = frozenset({
    "start_date",
    "end_date",
    "hotel_codes",
    "loop_interval_seconds",
    "per_hotel_delay_seconds",
    "request_jitter_percent",
    "people",
    "rooms",
    "budget_enabled",
    "budget_limit",
    "smoking",
    "membership_status",
    "primary_language",
    "room_requirement",
    "engine",
    "smart_parallel_enabled",
    "smart_parallel_workers",
    "adaptive_backoff_enabled",
    "area_region",
    "area_detail",
    "area_region_label",
    "area_detail_label",
    "search_mode",
    "enabled_providers",
    "radius_query",
    "radius_lat",
    "radius_lng",
    "radius_km",
    "selected_hotels",
})
_SELECTED_HOTEL_FIELDS = frozenset({
    "code",
    "display_code",
    "provider",
    "name",
    "name_primary",
    "name_en",
    "name_zh",
    "name_zh_cn",
    "name_zh_tw",
    "name_ja",
    "name_ko",
    "address",
    "address_en",
    "url",
    "map_url",
    "lat",
    "lng",
    "region_id",
    "prefecture_id",
    "detail_area_id",
    "prefecture",
    "priority",
})
_SECRET_OR_NOTIFICATION_FIELDS = frozenset({
    "enable_telegram",
    "bot_token",
    "chat_id",
    "enable_bark",
    "bark_key",
    "bark_server",
    "bark_critical_enabled",
    "bark_critical_volume",
    "bark_critical_sound",
    "enable_serverchan",
    "serverchan_sendkey",
    "enable_local",
    "enable_email",
    "smtp_host",
    "smtp_port",
    "smtp_tls",
    "smtp_user",
    "smtp_pass",
    "email_from",
    "email_to",
    "notify_available",
    "notify_unavailable",
    "notify_availability_count_change",
    "notify_start",
    "notify_stop",
    "notify_search_error",
    "available_alert_repeat",
    "available_alert_repeat_interval_sec",
})


class WorkspaceError(RuntimeError):
    """Base error for task persistence operations."""


class TaskNotFoundError(WorkspaceError):
    """Raised when a requested task or run does not exist."""


class TaskConflictError(WorkspaceError):
    """Raised when an optimistic revision check fails."""


class TaskValidationError(ValueError, WorkspaceError):
    """Raised when task state or search configuration is invalid."""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH) or ".", exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    try:
        with connection:
            _migrate(connection)
            yield connection
    finally:
        connection.close()


def _migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS workspace_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS monitor_tasks (
            task_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            desired_state TEXT NOT NULL DEFAULT 'paused',
            runtime_state TEXT NOT NULL DEFAULT 'idle',
            config_json TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1,
            runtime_revision INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_started_at REAL,
            last_stopped_at REAL,
            next_run_at REAL,
            last_error TEXT NOT NULL DEFAULT '',
            result_summary_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_monitor_tasks_sort
            ON monitor_tasks(sort_order, created_at);
        CREATE INDEX IF NOT EXISTS idx_monitor_tasks_desired_state
            ON monitor_tasks(desired_state, updated_at);

        CREATE TABLE IF NOT EXISTS task_runs (
            run_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            state TEXT NOT NULL,
            started_at REAL NOT NULL,
            completed_at REAL,
            result_summary_json TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_task_runs_task_time
            ON task_runs(task_id, started_at DESC);

        CREATE TABLE IF NOT EXISTS price_alert_rules (
            rule_id TEXT PRIMARY KEY,
            task_id TEXT,
            name TEXT NOT NULL,
            rule_type TEXT NOT NULL,
            hotel_code TEXT NOT NULL DEFAULT '',
            date_start TEXT NOT NULL DEFAULT '',
            date_end TEXT NOT NULL DEFAULT '',
            threshold_value REAL,
            threshold_percent REAL,
            enabled INTEGER NOT NULL DEFAULT 1,
            cooldown_seconds INTEGER NOT NULL DEFAULT 1800,
            rule_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_price_alert_rules_task
            ON price_alert_rules(task_id, enabled, updated_at);

        CREATE TABLE IF NOT EXISTS notification_policies (
            task_id TEXT PRIMARY KEY,
            timezone TEXT NOT NULL DEFAULT '',
            quiet_start TEXT NOT NULL DEFAULT '',
            quiet_end TEXT NOT NULL DEFAULT '',
            digest_mode TEXT NOT NULL DEFAULT 'off',
            digest_time TEXT NOT NULL DEFAULT '',
            aggregation_window_seconds INTEGER NOT NULL DEFAULT 120,
            allow_critical INTEGER NOT NULL DEFAULT 1,
            policy_json TEXT NOT NULL DEFAULT '{}',
            updated_at REAL NOT NULL,
            FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS travel_lists (
            list_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            budget_limit REAL,
            notes TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS travel_list_hotels (
            list_id TEXT NOT NULL,
            hotel_code TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'toyoko',
            hotel_json TEXT NOT NULL DEFAULT '{}',
            priority INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY(list_id, hotel_code),
            FOREIGN KEY(list_id) REFERENCES travel_lists(list_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS flexible_stay_jobs (
            job_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            earliest_date TEXT NOT NULL,
            latest_date TEXT NOT NULL,
            nights INTEGER NOT NULL,
            shortcut TEXT NOT NULL DEFAULT 'custom',
            status TEXT NOT NULL DEFAULT 'queued',
            hotel_codes_json TEXT NOT NULL DEFAULT '[]',
            hotels_json TEXT NOT NULL DEFAULT '[]',
            conditions_json TEXT NOT NULL DEFAULT '{}',
            total_work INTEGER NOT NULL DEFAULT 0,
            completed_work INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            current_hotel TEXT NOT NULL DEFAULT '',
            current_date TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            started_at REAL,
            completed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_flexible_stay_jobs_task_time
            ON flexible_stay_jobs(task_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_flexible_stay_jobs_status
            ON flexible_stay_jobs(status, updated_at);

        CREATE TABLE IF NOT EXISTS flexible_stay_nights (
            job_id TEXT NOT NULL,
            hotel_code TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'toyoko',
            stay_date TEXT NOT NULL,
            checkout_date TEXT NOT NULL,
            state TEXT NOT NULL,
            observed_at REAL NOT NULL,
            result_json TEXT NOT NULL,
            PRIMARY KEY(job_id, hotel_code, stay_date),
            FOREIGN KEY(job_id) REFERENCES flexible_stay_jobs(job_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_flexible_stay_nights_job_date
            ON flexible_stay_nights(job_id, stay_date, hotel_code);

        CREATE TABLE IF NOT EXISTS flexible_stay_results (
            job_id TEXT NOT NULL,
            hotel_code TEXT NOT NULL,
            checkin_date TEXT NOT NULL,
            checkout_date TEXT NOT NULL,
            nights INTEGER NOT NULL,
            state TEXT NOT NULL,
            total_price INTEGER,
            member_total_price INTEGER,
            result_json TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY(job_id, hotel_code, checkin_date, checkout_date),
            FOREIGN KEY(job_id) REFERENCES flexible_stay_jobs(job_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_flexible_stay_results_job_dates
            ON flexible_stay_results(job_id, checkin_date, hotel_code);
        """
    )
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(monitor_tasks)").fetchall()
    }
    if "runtime_revision" not in columns:
        connection.execute(
            """
            ALTER TABLE monitor_tasks
            ADD COLUMN runtime_revision INTEGER NOT NULL DEFAULT 0
            """
        )
    connection.execute(
        """
        INSERT INTO workspace_meta(key, value, updated_at)
        VALUES ('schema_version', ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (str(WORKSPACE_SCHEMA_VERSION), time.time()),
    )


def initialize_workspace() -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT value, updated_at FROM workspace_meta WHERE key='schema_version'"
        ).fetchone()
        task_count = int(connection.execute("SELECT COUNT(*) FROM monitor_tasks").fetchone()[0])
    return {
        "schema_version": int(row["value"]) if row is not None else 0,
        "updated_at": float(row["updated_at"]) if row is not None else 0.0,
        "task_count": task_count,
    }


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TaskValidationError(f"value is not JSON serializable: {exc}") from exc


def _json_object(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return deepcopy(raw)
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _clean_name(name: Any) -> str:
    value = " ".join(str(name or "").split()).strip()
    if not value:
        raise TaskValidationError("task name is required")
    return value[:120]


def _clean_identifier(value: Any, label: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise TaskValidationError(f"{label} is required")
    if len(cleaned) > 120:
        raise TaskValidationError(f"{label} is too long")
    return cleaned


def _clean_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise TaskValidationError(f"{field} must be an integer")
    try:
        cleaned = int(value)
    except (TypeError, ValueError) as exc:
        raise TaskValidationError(f"{field} must be an integer") from exc
    if cleaned < minimum or cleaned > maximum:
        raise TaskValidationError(f"{field} must be between {minimum} and {maximum}")
    return cleaned


def _clean_optional_float(
    value: Any,
    field: str,
    minimum: float,
    maximum: float,
) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise TaskValidationError(f"{field} must be a number")
    try:
        cleaned = float(value)
    except (TypeError, ValueError) as exc:
        raise TaskValidationError(f"{field} must be a number") from exc
    if cleaned < minimum or cleaned > maximum:
        raise TaskValidationError(f"{field} must be between {minimum} and {maximum}")
    return cleaned


def _provider_for_code(code: str) -> str:
    prefix = code.split(":", 1)[0]
    return prefix if prefix in SUPPORTED_PROVIDERS else "toyoko"


def _clean_selected_hotels(value: Any, hotel_codes: Sequence[str]) -> List[Dict[str, Any]]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise TaskValidationError("selected_hotels must be a list")
    allowed_codes = set(hotel_codes)
    by_code: Dict[str, Dict[str, Any]] = {}
    for raw_hotel in value:
        if not isinstance(raw_hotel, Mapping):
            raise TaskValidationError("each selected hotel must be an object")
        code = str(raw_hotel.get("code") or "").strip()
        if not code or code not in allowed_codes or code in by_code:
            continue
        hotel = {
            str(key): deepcopy(item)
            for key, item in raw_hotel.items()
            if key in _SELECTED_HOTEL_FIELDS
            and key not in _SECRET_OR_NOTIFICATION_FIELDS
        }
        hotel["code"] = code
        provider = str(hotel.get("provider") or _provider_for_code(code))
        hotel["provider"] = provider if provider in SUPPORTED_PROVIDERS else _provider_for_code(code)
        hotel["priority"] = bool(hotel.get("priority", False))
        by_code[code] = hotel
    return [
        by_code.get(code, {"code": code, "provider": _provider_for_code(code), "priority": False})
        for code in hotel_codes
    ]


def validate_task_config(
    config: Mapping[str, Any] | AppConfig,
    *,
    base: Optional[Mapping[str, Any] | AppConfig] = None,
) -> Dict[str, Any]:
    """Normalize one task search configuration and drop all global notification fields."""
    if isinstance(base, AppConfig):
        merged = task_config_snapshot(base)
    elif isinstance(base, Mapping):
        merged = {key: deepcopy(value) for key, value in base.items() if key in _TASK_CONFIG_FIELDS}
    else:
        merged = task_config_snapshot(AppConfig())

    if isinstance(config, AppConfig):
        supplied = task_config_snapshot(config)
    elif isinstance(config, Mapping):
        supplied = {
            ("room_requirement" if key == "om_requirement" else str(key)): deepcopy(value)
            for key, value in config.items()
            if key in _TASK_CONFIG_FIELDS or key == "om_requirement"
        }
    else:
        raise TaskValidationError("task config must be an object or AppConfig")
    merged.update(supplied)

    try:
        start = date.fromisoformat(str(merged.get("start_date") or ""))
        end = date.fromisoformat(str(merged.get("end_date") or ""))
    except ValueError as exc:
        raise TaskValidationError("start_date and end_date must use YYYY-MM-DD") from exc
    if end <= start:
        raise TaskValidationError("end_date must be after start_date")
    merged["start_date"] = start.isoformat()
    merged["end_date"] = end.isoformat()

    raw_codes = merged.get("hotel_codes")
    if not isinstance(raw_codes, list):
        raise TaskValidationError("hotel_codes must be a list")
    hotel_codes: List[str] = []
    for raw_code in raw_codes:
        code = str(raw_code or "").strip()
        if not code:
            raise TaskValidationError("hotel_codes cannot contain empty values")
        if code not in hotel_codes:
            hotel_codes.append(code)
    merged["hotel_codes"] = hotel_codes

    merged["loop_interval_seconds"] = _clean_int(
        merged.get("loop_interval_seconds"), "loop_interval_seconds", 30, 3600
    )
    merged["per_hotel_delay_seconds"] = _clean_int(
        merged.get("per_hotel_delay_seconds"), "per_hotel_delay_seconds", 1, 60
    )
    merged["request_jitter_percent"] = _clean_int(
        merged.get("request_jitter_percent"), "request_jitter_percent", 0, 100
    )
    merged["people"] = _clean_int(merged.get("people"), "people", 1, 5)
    merged["rooms"] = _clean_int(merged.get("rooms"), "rooms", 1, 9)
    merged["budget_enabled"] = bool(merged.get("budget_enabled", False))
    merged["budget_limit"] = _clean_int(
        merged.get("budget_limit"), "budget_limit", 0, 10_000_000
    )

    smoking = str(merged.get("smoking") or "")
    if smoking not in {"Smoking", "noSmoking", "all"}:
        raise TaskValidationError("smoking must be Smoking, noSmoking, or all")
    merged["smoking"] = smoking
    membership = str(merged.get("membership_status") or "")
    if membership not in {"member", "non_member", "unknown"}:
        raise TaskValidationError(
            "membership_status must be member, non_member, or unknown"
        )
    merged["membership_status"] = membership
    language = str(merged.get("primary_language") or "")
    if language not in {"zh_cn", "zh_tw", "ja", "ko", "en"}:
        raise TaskValidationError("primary_language is not supported")
    merged["primary_language"] = language
    room_requirement = str(
        merged.get("room_requirement")
        or merged.get("om_requirement")
        or "any"
    ).lower()
    if room_requirement not in {"any", "single", "double", "twin"}:
        raise TaskValidationError("room_requirement is not supported")
    merged["room_requirement"] = room_requirement
    merged.pop("om_requirement", None)

    engine = str(merged.get("engine") or "http")
    if engine == "selenium":
        engine = "http"
    if engine not in {"http", "playwright"}:
        raise TaskValidationError("engine must be http or playwright")
    merged["engine"] = engine
    merged["smart_parallel_enabled"] = bool(merged.get("smart_parallel_enabled", False))
    merged["smart_parallel_workers"] = _clean_int(
        merged.get("smart_parallel_workers"), "smart_parallel_workers", 1, 3
    )
    merged["adaptive_backoff_enabled"] = bool(
        merged.get("adaptive_backoff_enabled", True)
    )

    for field in (
        "area_region",
        "area_detail",
        "area_region_label",
        "area_detail_label",
        "radius_query",
    ):
        merged[field] = str(merged.get(field) or "")[:500]
    search_mode = str(merged.get("search_mode") or "area")
    if search_mode not in {"area", "radius"}:
        raise TaskValidationError("search_mode must be area or radius")
    merged["search_mode"] = search_mode

    raw_providers = merged.get("enabled_providers")
    if not isinstance(raw_providers, list):
        raise TaskValidationError("enabled_providers must be a list")
    providers = [
        str(provider)
        for provider in dict.fromkeys(raw_providers)
        if str(provider) in SUPPORTED_PROVIDERS
    ]
    if not providers:
        raise TaskValidationError("at least one supported provider is required")
    merged["enabled_providers"] = providers
    merged["radius_lat"] = _clean_optional_float(
        merged.get("radius_lat"), "radius_lat", -90.0, 90.0
    )
    merged["radius_lng"] = _clean_optional_float(
        merged.get("radius_lng"), "radius_lng", -180.0, 180.0
    )
    if (merged["radius_lat"] is None) != (merged["radius_lng"] is None):
        raise TaskValidationError("radius_lat and radius_lng must be provided together")
    merged["radius_km"] = _clean_int(merged.get("radius_km"), "radius_km", 1, 50)
    merged["selected_hotels"] = _clean_selected_hotels(
        merged.get("selected_hotels"), hotel_codes
    )

    normalized = {
        key: deepcopy(merged[key])
        for key in _TASK_CONFIG_FIELDS
        if key in merged
    }
    _json_dump(normalized)
    return normalized


def task_config_snapshot(cfg: AppConfig) -> Dict[str, Any]:
    raw = asdict(cfg)
    raw["room_requirement"] = str(
        getattr(cfg, "room_requirement", None)
        or getattr(cfg, "om_requirement", "any")
        or "any"
    )
    raw.pop("om_requirement", None)
    safe = {
        key: deepcopy(value)
        for key, value in raw.items()
        if key in _TASK_CONFIG_FIELDS and key not in _SECRET_OR_NOTIFICATION_FIELDS
    }
    return validate_task_config(safe, base=safe)


def app_config_from_task_config(
    config: Mapping[str, Any],
    *,
    base: Optional[AppConfig] = None,
) -> AppConfig:
    """Apply task-owned search fields to an AppConfig while retaining global credentials."""
    normalized = validate_task_config(config, base=base)
    output = deepcopy(base) if base is not None else AppConfig()
    for key, value in normalized.items():
        if key == "room_requirement":
            setattr(output, "om_requirement", value)
            setattr(output, "room_requirement", value)
        elif hasattr(output, key):
            setattr(output, key, deepcopy(value))
    return output


task_config_to_app_config = app_config_from_task_config


def _task_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "task_id": str(row["task_id"]),
        "name": str(row["name"]),
        "desired_state": str(row["desired_state"]),
        "runtime_state": str(row["runtime_state"]),
        "config": _json_object(row["config_json"]),
        "sort_order": int(row["sort_order"]),
        "revision": int(row["revision"]),
        "runtime_revision": int(row["runtime_revision"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
        "last_started_at": row["last_started_at"],
        "last_stopped_at": row["last_stopped_at"],
        "next_run_at": row["next_run_at"],
        "last_error": str(row["last_error"] or ""),
        "result_summary": _json_object(row["result_summary_json"]),
    }


def _select_task(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT task_id, name, desired_state, runtime_state, config_json,
               sort_order, revision, runtime_revision, created_at, updated_at,
               last_started_at, last_stopped_at, next_run_at, last_error,
               result_summary_json
        FROM monitor_tasks WHERE task_id=?
        """,
        (task_id,),
    ).fetchone()
    if row is None:
        raise TaskNotFoundError(f"task not found: {task_id}")
    return row


def _assert_revision(row: sqlite3.Row, expected_revision: Optional[int]) -> None:
    if expected_revision is None:
        return
    try:
        expected = int(expected_revision)
    except (TypeError, ValueError) as exc:
        raise TaskValidationError("expected_revision must be an integer") from exc
    current = int(row["revision"])
    if expected != current:
        raise TaskConflictError(
            f"task revision conflict: expected {expected}, current {current}"
        )


def ensure_default_task(cfg: AppConfig, name: str = "默认监控") -> str:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT task_id FROM monitor_tasks ORDER BY sort_order, created_at LIMIT 1"
        ).fetchone()
        if row is not None:
            return str(row["task_id"])
        now = time.time()
        connection.execute(
            """
            INSERT INTO monitor_tasks(
                task_id, name, desired_state, runtime_state, config_json,
                sort_order, revision, created_at, updated_at
            ) VALUES (?, ?, 'paused', 'idle', ?, 0, 1, ?, ?)
            """,
            (
                DEFAULT_TASK_ID,
                _clean_name(name or "默认监控"),
                _json_dump(task_config_snapshot(cfg)),
                now,
                now,
            ),
        )
    return DEFAULT_TASK_ID


def list_tasks() -> List[Dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT task_id, name, desired_state, runtime_state, config_json,
                   sort_order, revision, runtime_revision, created_at, updated_at,
                   last_started_at, last_stopped_at, next_run_at, last_error,
                   result_summary_json
            FROM monitor_tasks
            ORDER BY sort_order, created_at, task_id
            """
        ).fetchall()
    return [_task_from_row(row) for row in rows]


def get_task(task_id: str) -> Dict[str, Any]:
    cleaned_id = _clean_identifier(task_id, "task_id")
    with _LOCK, _connect() as connection:
        return _task_from_row(_select_task(connection, cleaned_id))


def create_task(
    name: str,
    config: Optional[Mapping[str, Any] | AppConfig] = None,
    *,
    task_id: Optional[str] = None,
    desired_state: str = "paused",
) -> Dict[str, Any]:
    cleaned_name = _clean_name(name)
    cleaned_id = _clean_identifier(task_id or uuid.uuid4().hex, "task_id")
    desired = str(desired_state or "paused")
    if desired not in DESIRED_TASK_STATES:
        raise TaskValidationError("desired_state must be paused or active")
    normalized = validate_task_config(config or {})
    now = time.time()
    with _LOCK, _connect() as connection:
        sort_order = int(
            connection.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM monitor_tasks"
            ).fetchone()[0]
        )
        try:
            connection.execute(
                """
                INSERT INTO monitor_tasks(
                    task_id, name, desired_state, runtime_state, config_json,
                    sort_order, revision, created_at, updated_at
                ) VALUES (?, ?, ?, 'idle', ?, ?, 1, ?, ?)
                """,
                (
                    cleaned_id,
                    cleaned_name,
                    desired,
                    _json_dump(normalized),
                    sort_order,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise TaskConflictError(f"task already exists: {cleaned_id}") from exc
        return _task_from_row(_select_task(connection, cleaned_id))


def update_task(
    task_id: str,
    *,
    name: Optional[str] = None,
    config: Optional[Mapping[str, Any] | AppConfig] = None,
    replace_config: bool = False,
    desired_state: Optional[str] = None,
    runtime_state: Optional[str] = None,
    next_run_at: Any = ...,
    last_error: Optional[str] = None,
    result_summary: Optional[Mapping[str, Any]] = None,
    expected_revision: Optional[int] = None,
    expected_runtime_revision: Optional[int] = None,
) -> Dict[str, Any]:
    cleaned_id = _clean_identifier(task_id, "task_id")
    with _LOCK, _connect() as connection:
        row = _select_task(connection, cleaned_id)
        _assert_revision(row, expected_revision)
        if expected_runtime_revision is not None:
            try:
                expected_runtime = int(expected_runtime_revision)
            except (TypeError, ValueError) as exc:
                raise TaskValidationError(
                    "expected_runtime_revision must be an integer"
                ) from exc
            current_runtime = int(row["runtime_revision"])
            if expected_runtime != current_runtime:
                raise TaskConflictError(
                    "task runtime revision conflict: "
                    f"expected {expected_runtime}, current {current_runtime}"
                )
        updates: Dict[str, Any] = {}
        definition_changed = False
        runtime_changed = False
        if name is not None:
            updates["name"] = _clean_name(name)
            definition_changed = True
        if config is not None:
            base = None if replace_config else _json_object(row["config_json"])
            updates["config_json"] = _json_dump(validate_task_config(config, base=base))
            definition_changed = True
        if desired_state is not None:
            desired = str(desired_state)
            if desired not in DESIRED_TASK_STATES:
                raise TaskValidationError("desired_state must be paused or active")
            updates["desired_state"] = desired
            definition_changed = True
        if runtime_state is not None:
            runtime = str(runtime_state)
            if runtime not in RUNTIME_TASK_STATES:
                raise TaskValidationError("runtime_state is not supported")
            updates["runtime_state"] = runtime
            runtime_changed = True
        if next_run_at is not ...:
            if next_run_at is None:
                updates["next_run_at"] = None
            else:
                try:
                    updates["next_run_at"] = float(next_run_at)
                except (TypeError, ValueError) as exc:
                    raise TaskValidationError("next_run_at must be a timestamp") from exc
            runtime_changed = True
        if last_error is not None:
            updates["last_error"] = str(last_error or "")[:1000]
            runtime_changed = True
        if result_summary is not None:
            if not isinstance(result_summary, Mapping):
                raise TaskValidationError("result_summary must be an object")
            updates["result_summary_json"] = _json_dump(dict(result_summary))
            runtime_changed = True
        if not updates:
            return _task_from_row(row)

        now = time.time()
        updates["updated_at"] = now
        if definition_changed:
            updates["revision"] = int(row["revision"]) + 1
        if runtime_changed:
            updates["runtime_revision"] = int(row["runtime_revision"]) + 1
        if updates.get("runtime_state") == "scanning":
            updates["last_started_at"] = now
        elif updates.get("runtime_state") in {"idle", "error"}:
            updates["last_stopped_at"] = now
        assignments = ", ".join(f"{column}=?" for column in updates)
        conditions = ["task_id=?"]
        condition_values: List[Any] = [cleaned_id]
        if definition_changed:
            conditions.append("revision=?")
            condition_values.append(int(row["revision"]))
        if runtime_changed:
            conditions.append("runtime_revision=?")
            condition_values.append(int(row["runtime_revision"]))
        cursor = connection.execute(
            f"UPDATE monitor_tasks SET {assignments} WHERE {' AND '.join(conditions)}",
            (*updates.values(), *condition_values),
        )
        if cursor.rowcount != 1:
            current = _select_task(connection, cleaned_id)
            if definition_changed and int(current["revision"]) != int(row["revision"]):
                raise TaskConflictError(
                    "task revision conflict: "
                    f"expected {int(row['revision'])}, current {int(current['revision'])}"
                )
            raise TaskConflictError(
                "task runtime revision conflict: "
                f"expected {int(row['runtime_revision'])}, "
                f"current {int(current['runtime_revision'])}"
            )
        return _task_from_row(_select_task(connection, cleaned_id))


def set_task_desired_state(
    task_id: str,
    desired_state: str,
    *,
    expected_revision: Optional[int] = None,
) -> Dict[str, Any]:
    return update_task(
        task_id,
        desired_state=desired_state,
        expected_revision=expected_revision,
    )


def set_task_runtime_state(
    task_id: str,
    runtime_state: str,
    *,
    next_run_at: Any = ...,
    last_error: Optional[str] = None,
    result_summary: Optional[Mapping[str, Any]] = None,
    expected_revision: Optional[int] = None,
    expected_runtime_revision: Optional[int] = None,
) -> Dict[str, Any]:
    return update_task(
        task_id,
        runtime_state=runtime_state,
        next_run_at=next_run_at,
        last_error=last_error,
        result_summary=result_summary,
        expected_revision=expected_revision,
        expected_runtime_revision=expected_runtime_revision,
    )


def duplicate_task(
    task_id: str,
    *,
    name: Optional[str] = None,
    new_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    source = get_task(task_id)
    return create_task(
        name or f"{source['name']} 副本",
        source["config"],
        task_id=new_task_id,
        desired_state="paused",
    )


def delete_task(
    task_id: str,
    *,
    expected_revision: Optional[int] = None,
) -> Dict[str, Any]:
    cleaned_id = _clean_identifier(task_id, "task_id")
    with _LOCK, _connect() as connection:
        row = _select_task(connection, cleaned_id)
        _assert_revision(row, expected_revision)
        deleted = _task_from_row(row)
        cursor = connection.execute(
            "DELETE FROM monitor_tasks WHERE task_id=? AND revision=?",
            (cleaned_id, int(row["revision"])),
        )
        if cursor.rowcount != 1:
            current = _select_task(connection, cleaned_id)
            raise TaskConflictError(
                "task revision conflict: "
                f"expected {int(row['revision'])}, current {int(current['revision'])}"
            )
        remaining = connection.execute(
            """
            SELECT task_id, sort_order FROM monitor_tasks
            ORDER BY sort_order, created_at, task_id
            """
        ).fetchall()
        now = time.time()
        for index, item in enumerate(remaining):
            if int(item["sort_order"]) == index:
                continue
            connection.execute(
                """
                UPDATE monitor_tasks
                SET sort_order=?, revision=revision+1, updated_at=?
                WHERE task_id=?
                """,
                (index, now, str(item["task_id"])),
            )
    return deleted


def reorder_tasks(
    task_ids: Sequence[str],
    *,
    expected_revisions: Optional[Mapping[str, int]] = None,
) -> List[Dict[str, Any]]:
    cleaned_ids = [_clean_identifier(task_id, "task_id") for task_id in task_ids]
    if len(cleaned_ids) != len(set(cleaned_ids)):
        raise TaskValidationError("task_ids must not contain duplicates")
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT task_id, revision, sort_order FROM monitor_tasks
            ORDER BY sort_order, created_at, task_id
            """
        ).fetchall()
        existing_ids = [str(row["task_id"]) for row in rows]
        if set(cleaned_ids) != set(existing_ids) or len(cleaned_ids) != len(existing_ids):
            raise TaskValidationError("task_ids must contain every task exactly once")
        by_id = {str(row["task_id"]): row for row in rows}
        if expected_revisions is not None:
            for task_id in cleaned_ids:
                if task_id not in expected_revisions:
                    raise TaskValidationError(
                        "expected_revisions must contain every task"
                    )
                _assert_revision(by_id[task_id], expected_revisions[task_id])
        now = time.time()
        for sort_order, task_id in enumerate(cleaned_ids):
            if int(by_id[task_id]["sort_order"]) == sort_order:
                continue
            connection.execute(
                """
                UPDATE monitor_tasks
                SET sort_order=?, revision=revision+1, updated_at=?
                WHERE task_id=?
                """,
                (sort_order, now, task_id),
            )
        output_rows = [_select_task(connection, task_id) for task_id in cleaned_ids]
    return [_task_from_row(row) for row in output_rows]


def _run_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "task_id": str(row["task_id"]),
        "state": str(row["state"]),
        "started_at": float(row["started_at"]),
        "completed_at": row["completed_at"],
        "result_summary": _json_object(row["result_summary_json"]),
        "error": str(row["error"] or ""),
    }


def start_task_run(
    task_id: str,
    *,
    run_id: Optional[str] = None,
    state: str = "running",
    started_at: Optional[float] = None,
) -> Dict[str, Any]:
    cleaned_task_id = _clean_identifier(task_id, "task_id")
    cleaned_run_id = _clean_identifier(run_id or uuid.uuid4().hex, "run_id")
    active_state = str(state)
    if active_state not in ACTIVE_RUN_STATES:
        raise TaskValidationError("new run state must be queued or running")
    started = time.time() if started_at is None else float(started_at)
    with _LOCK, _connect() as connection:
        _select_task(connection, cleaned_task_id)
        try:
            connection.execute(
                """
                INSERT INTO task_runs(
                    run_id, task_id, state, started_at, completed_at,
                    result_summary_json, error
                ) VALUES (?, ?, ?, ?, NULL, '{}', '')
                """,
                (cleaned_run_id, cleaned_task_id, active_state, started),
            )
        except sqlite3.IntegrityError as exc:
            raise TaskConflictError(f"run already exists: {cleaned_run_id}") from exc
        row = connection.execute(
            "SELECT * FROM task_runs WHERE run_id=?", (cleaned_run_id,)
        ).fetchone()
    return _run_from_row(row)


def mark_task_run_running(run_id: str) -> Dict[str, Any]:
    """Promote one queued run to running without altering its enqueue timestamp."""
    cleaned_run_id = _clean_identifier(run_id, "run_id")
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM task_runs WHERE run_id=?", (cleaned_run_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(f"run not found: {cleaned_run_id}")
        if str(row["state"]) != "queued":
            raise TaskConflictError(
                f"run is not queued: {cleaned_run_id} ({row['state']})"
            )
        cursor = connection.execute(
            "UPDATE task_runs SET state='running' WHERE run_id=? AND state='queued'",
            (cleaned_run_id,),
        )
        if cursor.rowcount != 1:
            raise TaskConflictError(f"run state conflict: {cleaned_run_id}")
        updated = connection.execute(
            "SELECT * FROM task_runs WHERE run_id=?", (cleaned_run_id,)
        ).fetchone()
    return _run_from_row(updated)


def finish_task_run(
    run_id: str,
    *,
    state: str = "complete",
    result_summary: Optional[Mapping[str, Any]] = None,
    error: str = "",
    completed_at: Optional[float] = None,
) -> Dict[str, Any]:
    cleaned_run_id = _clean_identifier(run_id, "run_id")
    terminal_state = str(state)
    if terminal_state not in TERMINAL_RUN_STATES:
        raise TaskValidationError("run state must be terminal")
    if result_summary is not None and not isinstance(result_summary, Mapping):
        raise TaskValidationError("result_summary must be an object")
    completed = time.time() if completed_at is None else float(completed_at)
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM task_runs WHERE run_id=?", (cleaned_run_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(f"run not found: {cleaned_run_id}")
        if str(row["state"]) not in ACTIVE_RUN_STATES:
            raise TaskConflictError(
                f"run is already terminal: {cleaned_run_id} ({row['state']})"
            )
        connection.execute(
            """
            UPDATE task_runs
            SET state=?, completed_at=?, result_summary_json=?, error=?
            WHERE run_id=?
            """,
            (
                terminal_state,
                completed,
                _json_dump(dict(result_summary or {})),
                str(error or "")[:1000],
                cleaned_run_id,
            ),
        )
        updated = connection.execute(
            "SELECT * FROM task_runs WHERE run_id=?", (cleaned_run_id,)
        ).fetchone()
    return _run_from_row(updated)


def list_active_task_runs(task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return queued/running records for one task or for the whole workspace."""
    parameters: tuple[Any, ...] = ()
    where = "state IN ('queued', 'running')"
    if task_id is not None:
        cleaned_task_id = _clean_identifier(task_id, "task_id")
        where += " AND task_id=?"
        parameters = (cleaned_task_id,)
    with _LOCK, _connect() as connection:
        if task_id is not None:
            _select_task(connection, parameters[0])
        rows = connection.execute(
            f"""
            SELECT run_id, task_id, state, started_at, completed_at,
                   result_summary_json, error
            FROM task_runs
            WHERE {where}
            ORDER BY started_at, run_id
            """,
            parameters,
        ).fetchall()
    return [_run_from_row(row) for row in rows]


def interrupt_active_task_runs(
    *,
    completed_at: Optional[float] = None,
    error: str = "application restarted",
) -> List[Dict[str, Any]]:
    """Atomically mark every orphaned queued/running record as interrupted."""
    completed = time.time() if completed_at is None else float(completed_at)
    clean_error = str(error or "")[:1000]
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT run_id FROM task_runs
            WHERE state IN ('queued', 'running')
            ORDER BY started_at, run_id
            """
        ).fetchall()
        run_ids = [str(row["run_id"]) for row in rows]
        if run_ids:
            connection.execute(
                """
                UPDATE task_runs
                SET state='interrupted', completed_at=?, error=?
                WHERE state IN ('queued', 'running')
                """,
                (completed, clean_error),
            )
        updated = [
            connection.execute(
                "SELECT * FROM task_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            for run_id in run_ids
        ]
    return [_run_from_row(row) for row in updated if row is not None]


def list_task_runs(task_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    cleaned_task_id = _clean_identifier(task_id, "task_id")
    cleaned_limit = _clean_int(limit, "limit", 1, 500)
    with _LOCK, _connect() as connection:
        _select_task(connection, cleaned_task_id)
        rows = connection.execute(
            """
            SELECT run_id, task_id, state, started_at, completed_at,
                   result_summary_json, error
            FROM task_runs WHERE task_id=?
            ORDER BY started_at DESC, run_id DESC LIMIT ?
            """,
            (cleaned_task_id, cleaned_limit),
        ).fetchall()
    return [_run_from_row(row) for row in rows]
