from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .settings import HOTEL_DATABASE_PATH


ALERT_SCHEMA_VERSION = 1
RULE_TYPES = frozenset({
    "target_price",
    "member_price",
    "price_drop",
    "vacancy_transition",
})
DIGEST_MODES = frozenset({"off", "daily"})
DELIVERY_STATES = frozenset({
    "queued",
    "sending",
    "sent",
    "partial",
    "failed",
    "skipped",
})
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_PRICE_RE = re.compile(r"\d[\d,]*")
_LOCK = threading.RLock()


class AlertError(RuntimeError):
    """Base error for Phase 2 alert operations."""


class AlertNotFoundError(AlertError):
    """Raised when an alert rule is missing."""


class AlertConflictError(AlertError):
    """Raised when an optimistic revision check fails."""


class AlertValidationError(ValueError, AlertError):
    """Raised when a rule or policy is invalid."""


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


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
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
            revision INTEGER NOT NULL DEFAULT 1,
            critical INTEGER NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_price_alert_rules_task
            ON price_alert_rules(task_id, enabled, updated_at);

        CREATE TABLE IF NOT EXISTS notification_policies (
            task_id TEXT PRIMARY KEY,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            quiet_start TEXT NOT NULL DEFAULT '',
            quiet_end TEXT NOT NULL DEFAULT '',
            digest_mode TEXT NOT NULL DEFAULT 'off',
            digest_time TEXT NOT NULL DEFAULT '09:00',
            aggregation_window_seconds INTEGER NOT NULL DEFAULT 120,
            allow_critical INTEGER NOT NULL DEFAULT 1,
            policy_json TEXT NOT NULL DEFAULT '{}',
            revision INTEGER NOT NULL DEFAULT 1,
            updated_at REAL NOT NULL,
            FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS alert_observations (
            rule_id TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            hotel_code TEXT NOT NULL,
            stay_date TEXT NOT NULL,
            available INTEGER,
            price_value REAL,
            member_price_value REAL,
            matched INTEGER NOT NULL DEFAULT 0,
            trigger_count INTEGER NOT NULL DEFAULT 0,
            observed_at REAL NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(rule_id, scope_key),
            FOREIGN KEY(rule_id) REFERENCES price_alert_rules(rule_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_alert_observations_hotel
            ON alert_observations(hotel_code, stay_date, observed_at DESC);

        CREATE TABLE IF NOT EXISTS alert_batches (
            batch_id TEXT PRIMARY KEY,
            task_id TEXT,
            mode TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'queued',
            due_at REAL NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            event_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_alert_batches_due
            ON alert_batches(state, due_at);

        CREATE TABLE IF NOT EXISTS alert_events (
            alert_event_id TEXT PRIMARY KEY,
            rule_id TEXT,
            task_id TEXT,
            batch_id TEXT,
            event_type TEXT NOT NULL,
            hotel_code TEXT NOT NULL DEFAULT '',
            stay_date TEXT NOT NULL DEFAULT '',
            fingerprint TEXT NOT NULL UNIQUE,
            state TEXT NOT NULL DEFAULT 'queued',
            critical INTEGER NOT NULL DEFAULT 0,
            rule_revision INTEGER NOT NULL DEFAULT 1,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            first_observed_at REAL NOT NULL,
            last_observed_at REAL NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY(rule_id) REFERENCES price_alert_rules(rule_id) ON DELETE SET NULL,
            FOREIGN KEY(task_id) REFERENCES monitor_tasks(task_id) ON DELETE CASCADE,
            FOREIGN KEY(batch_id) REFERENCES alert_batches(batch_id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alert_events_task_time
            ON alert_events(task_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_alert_events_calendar
            ON alert_events(task_id, hotel_code, stay_date);

        CREATE TABLE IF NOT EXISTS alert_deliveries (
            delivery_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            state TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            attempted_at REAL NOT NULL,
            completed_at REAL,
            UNIQUE(batch_id, channel),
            FOREIGN KEY(batch_id) REFERENCES alert_batches(batch_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_alert_deliveries_state
            ON alert_deliveries(state, attempted_at DESC);

        CREATE TABLE IF NOT EXISTS alert_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        """
    )
    rule_columns = _columns(connection, "price_alert_rules")
    for statement, column in (
        ("ALTER TABLE price_alert_rules ADD COLUMN revision INTEGER NOT NULL DEFAULT 1", "revision"),
        ("ALTER TABLE price_alert_rules ADD COLUMN critical INTEGER NOT NULL DEFAULT 0", "critical"),
        ("ALTER TABLE price_alert_rules ADD COLUMN priority INTEGER NOT NULL DEFAULT 0", "priority"),
    ):
        if column not in rule_columns:
            connection.execute(statement)
    policy_columns = _columns(connection, "notification_policies")
    if "revision" not in policy_columns:
        connection.execute(
            "ALTER TABLE notification_policies ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"
        )
    event_columns = _columns(connection, "alert_events")
    if "rule_revision" not in event_columns:
        connection.execute(
            "ALTER TABLE alert_events ADD COLUMN rule_revision INTEGER NOT NULL DEFAULT 1"
        )
    connection.execute(
        """
        INSERT INTO alert_meta(key,value,updated_at) VALUES ('schema_version',?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (str(ALERT_SCHEMA_VERSION), time.time()),
    )


def initialize_alerting() -> Dict[str, int]:
    with _LOCK, _connect() as connection:
        return {
            "schema_version": ALERT_SCHEMA_VERSION,
            "rules": int(connection.execute(
                "SELECT COUNT(*) FROM price_alert_rules"
            ).fetchone()[0]),
            "queued_batches": int(connection.execute(
                "SELECT COUNT(*) FROM alert_batches WHERE state='queued'"
            ).fetchone()[0]),
        }


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise AlertValidationError(f"value is not JSON serializable: {exc}") from exc


def _json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _clean_date(value: Any, field: str, *, optional: bool = True) -> str:
    text = str(value or "").strip()
    if not text and optional:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise AlertValidationError(f"{field} must use YYYY-MM-DD") from exc


def _clean_number(
    value: Any,
    field: str,
    *,
    minimum: float = 0,
    maximum: float = 100_000_000,
    optional: bool = True,
) -> Optional[float]:
    if value in (None, "") and optional:
        return None
    if isinstance(value, bool):
        raise AlertValidationError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AlertValidationError(f"{field} must be a number") from exc
    if number < minimum or number > maximum:
        raise AlertValidationError(
            f"{field} must be between {minimum:g} and {maximum:g}"
        )
    return number


def _clean_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise AlertValidationError(f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise AlertValidationError(f"{field} must be an integer") from exc
    if number < minimum or number > maximum:
        raise AlertValidationError(f"{field} must be between {minimum} and {maximum}")
    return number


def _assert_task(connection: sqlite3.Connection, task_id: str) -> str:
    cleaned = str(task_id or "").strip()
    if not cleaned:
        raise AlertValidationError("task_id is required")
    row = connection.execute(
        "SELECT task_id FROM monitor_tasks WHERE task_id=?", (cleaned,)
    ).fetchone()
    if row is None:
        raise AlertValidationError(f"task not found: {cleaned}")
    return cleaned


def _rule_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "rule_id": str(row["rule_id"]),
        "task_id": str(row["task_id"] or ""),
        "name": str(row["name"]),
        "rule_type": str(row["rule_type"]),
        "hotel_code": str(row["hotel_code"] or ""),
        "date_start": str(row["date_start"] or ""),
        "date_end": str(row["date_end"] or ""),
        "threshold_value": row["threshold_value"],
        "threshold_percent": row["threshold_percent"],
        "enabled": bool(row["enabled"]),
        "cooldown_seconds": int(row["cooldown_seconds"]),
        "critical": bool(row["critical"]),
        "priority": int(row["priority"]),
        "config": _json_object(row["rule_json"]),
        "revision": int(row["revision"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def _validate_rule(
    payload: Mapping[str, Any],
    *,
    base: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(base or {})
    merged.update(dict(payload))
    name = " ".join(str(merged.get("name") or "").split()).strip()
    if not name:
        raise AlertValidationError("rule name is required")
    rule_type = str(merged.get("rule_type") or "").strip()
    if rule_type not in RULE_TYPES:
        raise AlertValidationError("unsupported rule_type")
    start = _clean_date(merged.get("date_start"), "date_start")
    end = _clean_date(merged.get("date_end"), "date_end")
    if start and end and end < start:
        raise AlertValidationError("date_end must be on or after date_start")
    threshold_value = _clean_number(
        merged.get("threshold_value"), "threshold_value"
    )
    threshold_percent = _clean_number(
        merged.get("threshold_percent"),
        "threshold_percent",
        maximum=100,
    )
    if rule_type in {"target_price", "member_price"} and not threshold_value:
        raise AlertValidationError("threshold_value is required for this rule type")
    if rule_type == "price_drop" and not threshold_value and not threshold_percent:
        raise AlertValidationError(
            "price_drop requires threshold_value or threshold_percent"
        )
    config = merged.get("config", merged.get("rule_json", {}))
    if not isinstance(config, Mapping):
        raise AlertValidationError("config must be an object")
    raw_config = dict(config)
    price_basis = str(raw_config.get("price_basis") or "best")
    if price_basis not in {"best", "member", "non_member"}:
        raise AlertValidationError("price_basis must be best, member, or non_member")
    direction = str(raw_config.get("direction") or "available")
    if direction not in {"available", "unavailable", "any"}:
        raise AlertValidationError(
            "vacancy direction must be available, unavailable, or any"
        )
    config = {
        "price_basis": price_basis,
        "direction": direction,
    }
    return {
        "name": name[:120],
        "rule_type": rule_type,
        "hotel_code": str(merged.get("hotel_code") or "").strip()[:120],
        "date_start": start,
        "date_end": end,
        "threshold_value": threshold_value,
        "threshold_percent": threshold_percent,
        "enabled": bool(merged.get("enabled", True)),
        "cooldown_seconds": _clean_int(
            merged.get("cooldown_seconds", 1800),
            "cooldown_seconds",
            0,
            30 * 24 * 60 * 60,
        ),
        "critical": bool(merged.get("critical", False)),
        "priority": _clean_int(merged.get("priority", 0), "priority", -1000, 1000),
        "config": config,
    }


def list_rules(task_id: str = "", *, enabled_only: bool = False) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if task_id:
        clauses.append("task_id=?")
        params.append(str(task_id))
    if enabled_only:
        clauses.append("enabled=1")
    query = "SELECT * FROM price_alert_rules"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY priority DESC, created_at ASC, rule_id ASC"
    with _LOCK, _connect() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [_rule_from_row(row) for row in rows]


def has_rule_type(task_id: str, rule_type: str) -> bool:
    with _LOCK, _connect() as connection:
        return connection.execute(
            """
            SELECT 1 FROM price_alert_rules
            WHERE task_id=? AND rule_type=? AND enabled=1 LIMIT 1
            """,
            (str(task_id), str(rule_type)),
        ).fetchone() is not None


def get_rule(rule_id: str) -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM price_alert_rules WHERE rule_id=?",
            (str(rule_id),),
        ).fetchone()
    if row is None:
        raise AlertNotFoundError(f"alert rule not found: {rule_id}")
    return _rule_from_row(row)


def create_rule(task_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    cleaned = _validate_rule(payload)
    now = time.time()
    rule_id = str(payload.get("rule_id") or uuid.uuid4().hex)
    with _LOCK, _connect() as connection:
        task_id = _assert_task(connection, task_id)
        try:
            connection.execute(
                """
                INSERT INTO price_alert_rules(
                    rule_id,task_id,name,rule_type,hotel_code,date_start,date_end,
                    threshold_value,threshold_percent,enabled,cooldown_seconds,
                    rule_json,revision,critical,priority,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)
                """,
                (
                    rule_id, task_id, cleaned["name"], cleaned["rule_type"],
                    cleaned["hotel_code"], cleaned["date_start"], cleaned["date_end"],
                    cleaned["threshold_value"], cleaned["threshold_percent"],
                    int(cleaned["enabled"]), cleaned["cooldown_seconds"],
                    _json_dump(cleaned["config"]), int(cleaned["critical"]),
                    cleaned["priority"], now, now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AlertConflictError(f"alert rule already exists: {rule_id}") from exc
    return get_rule(rule_id)


def update_rule(
    rule_id: str,
    payload: Mapping[str, Any],
    *,
    expected_revision: Optional[int] = None,
) -> Dict[str, Any]:
    current = get_rule(rule_id)
    if expected_revision is not None and int(expected_revision) != current["revision"]:
        raise AlertConflictError(
            f"alert rule revision conflict: expected {expected_revision}, "
            f"current {current['revision']}"
        )
    cleaned = _validate_rule(payload, base=current)
    evaluation_changed = any(
        current.get(key) != cleaned.get(key)
        for key in (
            "rule_type",
            "hotel_code",
            "date_start",
            "date_end",
            "threshold_value",
            "threshold_percent",
            "config",
        )
    )
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            UPDATE price_alert_rules SET
                name=?,rule_type=?,hotel_code=?,date_start=?,date_end=?,
                threshold_value=?,threshold_percent=?,enabled=?,cooldown_seconds=?,
                rule_json=?,critical=?,priority=?,revision=revision+1,updated_at=?
            WHERE rule_id=?
            """,
            (
                cleaned["name"], cleaned["rule_type"], cleaned["hotel_code"],
                cleaned["date_start"], cleaned["date_end"],
                cleaned["threshold_value"], cleaned["threshold_percent"],
                int(cleaned["enabled"]), cleaned["cooldown_seconds"],
                _json_dump(cleaned["config"]), int(cleaned["critical"]),
                cleaned["priority"], time.time(), str(rule_id),
            ),
        )
        if evaluation_changed:
            connection.execute(
                "DELETE FROM alert_observations WHERE rule_id=?",
                (str(rule_id),),
            )
    return get_rule(rule_id)


def delete_rule(rule_id: str, *, expected_revision: Optional[int] = None) -> Dict[str, Any]:
    current = get_rule(rule_id)
    if expected_revision is not None and int(expected_revision) != current["revision"]:
        raise AlertConflictError(
            f"alert rule revision conflict: expected {expected_revision}, "
            f"current {current['revision']}"
        )
    with _LOCK, _connect() as connection:
        connection.execute(
            "DELETE FROM price_alert_rules WHERE rule_id=?", (str(rule_id),)
        )
    return current


def _local_timezone_name() -> str:
    tzinfo = datetime.now().astimezone().tzinfo
    key = getattr(tzinfo, "key", "")
    return str(key or "UTC")


def _default_policy(task_id: str) -> Dict[str, Any]:
    return {
        "task_id": str(task_id),
        "timezone": _local_timezone_name(),
        "quiet_start": "",
        "quiet_end": "",
        "digest_mode": "off",
        "digest_time": "09:00",
        "aggregation_window_seconds": 120,
        "allow_critical": True,
        "config": {},
        "revision": 0,
        "updated_at": 0.0,
    }


def _policy_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "task_id": str(row["task_id"]),
        "timezone": str(row["timezone"] or "UTC"),
        "quiet_start": str(row["quiet_start"] or ""),
        "quiet_end": str(row["quiet_end"] or ""),
        "digest_mode": str(row["digest_mode"] or "off"),
        "digest_time": str(row["digest_time"] or "09:00"),
        "aggregation_window_seconds": int(row["aggregation_window_seconds"]),
        "allow_critical": bool(row["allow_critical"]),
        "config": _json_object(row["policy_json"]),
        "revision": int(row["revision"]),
        "updated_at": float(row["updated_at"]),
    }


def get_policy(task_id: str) -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        _assert_task(connection, task_id)
        row = connection.execute(
            "SELECT * FROM notification_policies WHERE task_id=?",
            (str(task_id),),
        ).fetchone()
    return _policy_from_row(row) if row is not None else _default_policy(task_id)


def _validate_policy(
    task_id: str,
    payload: Mapping[str, Any],
    *,
    base: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    merged = dict(base or _default_policy(task_id))
    merged.update(dict(payload))
    timezone_name = str(merged.get("timezone") or "UTC").strip()
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AlertValidationError("timezone is not available") from exc
    quiet_start = str(merged.get("quiet_start") or "").strip()
    quiet_end = str(merged.get("quiet_end") or "").strip()
    if bool(quiet_start) != bool(quiet_end):
        raise AlertValidationError("quiet_start and quiet_end must be set together")
    if quiet_start and (
        not _TIME_RE.fullmatch(quiet_start) or not _TIME_RE.fullmatch(quiet_end)
    ):
        raise AlertValidationError("quiet hours must use HH:MM")
    digest_mode = str(merged.get("digest_mode") or "off")
    if digest_mode not in DIGEST_MODES:
        raise AlertValidationError("digest_mode must be off or daily")
    digest_time = str(merged.get("digest_time") or "09:00")
    if not _TIME_RE.fullmatch(digest_time):
        raise AlertValidationError("digest_time must use HH:MM")
    config = merged.get("config", merged.get("policy_json", {}))
    if not isinstance(config, Mapping):
        raise AlertValidationError("config must be an object")
    return {
        "task_id": str(task_id),
        "timezone": timezone_name,
        "quiet_start": quiet_start,
        "quiet_end": quiet_end,
        "digest_mode": digest_mode,
        "digest_time": digest_time,
        "aggregation_window_seconds": _clean_int(
            merged.get("aggregation_window_seconds", 120),
            "aggregation_window_seconds",
            0,
            3600,
        ),
        "allow_critical": bool(merged.get("allow_critical", True)),
        "config": {},
    }


def update_policy(
    task_id: str,
    payload: Mapping[str, Any],
    *,
    expected_revision: Optional[int] = None,
) -> Dict[str, Any]:
    current = get_policy(task_id)
    if expected_revision is not None and int(expected_revision) != current["revision"]:
        raise AlertConflictError(
            f"notification policy revision conflict: expected {expected_revision}, "
            f"current {current['revision']}"
        )
    cleaned = _validate_policy(task_id, payload, base=current)
    now = time.time()
    next_revision = current["revision"] + 1
    with _LOCK, _connect() as connection:
        _assert_task(connection, task_id)
        connection.execute(
            """
            INSERT INTO notification_policies(
                task_id,timezone,quiet_start,quiet_end,digest_mode,digest_time,
                aggregation_window_seconds,allow_critical,policy_json,revision,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
                timezone=excluded.timezone,quiet_start=excluded.quiet_start,
                quiet_end=excluded.quiet_end,digest_mode=excluded.digest_mode,
                digest_time=excluded.digest_time,
                aggregation_window_seconds=excluded.aggregation_window_seconds,
                allow_critical=excluded.allow_critical,
                policy_json=excluded.policy_json,revision=excluded.revision,
                updated_at=excluded.updated_at
            """,
            (
                task_id, cleaned["timezone"], cleaned["quiet_start"],
                cleaned["quiet_end"], cleaned["digest_mode"],
                cleaned["digest_time"], cleaned["aggregation_window_seconds"],
                int(cleaned["allow_critical"]), _json_dump(cleaned["config"]),
                next_revision, now,
            ),
        )
    return get_policy(task_id)


def _price_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, int(value))
    match = _PRICE_RE.search(str(value))
    return int(match.group(0).replace(",", "")) if match else None


def _result_dict(result: Any) -> Dict[str, Any]:
    if isinstance(result, Mapping):
        return deepcopy(dict(result))
    if is_dataclass(result):
        return asdict(result)
    return {
        key: deepcopy(value)
        for key, value in vars(result).items()
        if not key.startswith("_")
    }


def _selected_price(rule: Mapping[str, Any], result: Mapping[str, Any]) -> Optional[int]:
    normal = _price_int(result.get("min_price") or result.get("min_price_text"))
    member = _price_int(
        result.get("min_member_price") or result.get("min_member_price_text")
    )
    basis = str((rule.get("config") or {}).get("price_basis") or "best")
    if basis == "member":
        return member
    if basis == "non_member":
        return normal
    values = [value for value in (member, normal) if value is not None]
    return min(values) if values else None


def _rule_applies(rule: Mapping[str, Any], hotel_code: str, stay_date: str) -> bool:
    if rule.get("hotel_code") and str(rule["hotel_code"]) != hotel_code:
        return False
    if rule.get("date_start") and stay_date < str(rule["date_start"]):
        return False
    if rule.get("date_end") and stay_date > str(rule["date_end"]):
        return False
    return True


def _observation(
    connection: sqlite3.Connection,
    rule_id: str,
    scope_key: str,
) -> Optional[Dict[str, Any]]:
    row = connection.execute(
        "SELECT * FROM alert_observations WHERE rule_id=? AND scope_key=?",
        (rule_id, scope_key),
    ).fetchone()
    if row is None:
        return None
    return {
        "available": None if row["available"] is None else bool(row["available"]),
        "price_value": row["price_value"],
        "member_price_value": row["member_price_value"],
        "matched": bool(row["matched"]),
        "trigger_count": int(row["trigger_count"]),
        "observed_at": float(row["observed_at"]),
        "payload": _json_object(row["payload_json"]),
    }


def _quiet_window_end(policy: Mapping[str, Any], now: float) -> Optional[float]:
    start_text = str(policy.get("quiet_start") or "")
    end_text = str(policy.get("quiet_end") or "")
    if not start_text or not end_text:
        return None
    tz = ZoneInfo(str(policy.get("timezone") or "UTC"))
    local_now = datetime.fromtimestamp(now, tz)
    start_hour, start_minute = (int(part) for part in start_text.split(":"))
    end_hour, end_minute = (int(part) for part in end_text.split(":"))
    start = local_now.replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )
    end = local_now.replace(
        hour=end_hour, minute=end_minute, second=0, microsecond=0
    )
    if start_text == end_text:
        return None
    if start_text < end_text:
        if start <= local_now < end:
            return end.timestamp()
        return None
    if local_now >= start:
        return (end + timedelta(days=1)).timestamp()
    if local_now < end:
        return end.timestamp()
    return None


def _next_digest_at(policy: Mapping[str, Any], now: float) -> float:
    tz = ZoneInfo(str(policy.get("timezone") or "UTC"))
    local_now = datetime.fromtimestamp(now, tz)
    hour, minute = (
        int(part) for part in str(policy.get("digest_time") or "09:00").split(":")
    )
    due = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due <= local_now:
        due += timedelta(days=1)
    quiet_end = _quiet_window_end(policy, due.timestamp())
    return quiet_end if quiet_end is not None else due.timestamp()


def _event_due(
    policy: Mapping[str, Any],
    *,
    critical: bool,
    now: float,
) -> tuple[float, str]:
    if critical and bool(policy.get("allow_critical", True)):
        return now, "critical"
    if policy.get("digest_mode") == "daily":
        return _next_digest_at(policy, now), "daily_digest"
    quiet_end = _quiet_window_end(policy, now)
    if quiet_end is not None:
        return quiet_end, "quiet_queue"
    window = max(0, int(policy.get("aggregation_window_seconds") or 0))
    return now + window, "aggregate" if window else "immediate"


def _find_or_create_batch(
    connection: sqlite3.Connection,
    task_id: str,
    mode: str,
    due_at: float,
    *,
    aggregation_window: int,
    now: float,
) -> str:
    tolerance = max(1, aggregation_window)
    row = connection.execute(
        """
        SELECT batch_id FROM alert_batches
        WHERE task_id=? AND mode=? AND state='queued'
          AND due_at BETWEEN ? AND ?
        ORDER BY created_at ASC LIMIT 1
        """,
        (task_id, mode, due_at - tolerance, due_at + tolerance),
    ).fetchone()
    if row is not None:
        return str(row["batch_id"])
    batch_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO alert_batches(
            batch_id,task_id,mode,state,due_at,created_at,updated_at,event_count
        ) VALUES (?,? ,?,'queued',?,?,?,0)
        """,
        (batch_id, task_id, mode, due_at, now, now),
    )
    return batch_id


def _event_payload(
    rule: Mapping[str, Any],
    result: Mapping[str, Any],
    stay_date: str,
    checkout_date: str,
    event_type: str,
    previous: Optional[Mapping[str, Any]],
    price: Optional[int],
    member_price: Optional[int],
) -> Dict[str, Any]:
    return {
        "rule_id": rule["rule_id"],
        "rule_name": rule["name"],
        "rule_type": rule["rule_type"],
        "event_type": event_type,
        "task_id": rule["task_id"],
        "hotel_code": str(result.get("code") or ""),
        "hotel_name": str(result.get("name") or ""),
        "provider": str(result.get("provider") or "toyoko"),
        "stay_date": stay_date,
        "checkout_date": checkout_date,
        "available": result.get("available"),
        "price": price,
        "member_price": member_price,
        "previous_price": previous.get("price_value") if previous else None,
        "previous_member_price": previous.get("member_price_value") if previous else None,
        "threshold_value": rule.get("threshold_value"),
        "threshold_percent": rule.get("threshold_percent"),
        "url": str(result.get("url") or ""),
        "critical": bool(rule.get("critical")),
        "observed_at": time.time(),
    }


def _store_event(
    connection: sqlite3.Connection,
    rule: Mapping[str, Any],
    payload: Mapping[str, Any],
    trigger_count: int,
    *,
    now: float,
) -> Optional[Dict[str, Any]]:
    policy_row = connection.execute(
        "SELECT * FROM notification_policies WHERE task_id=?",
        (str(rule["task_id"]),),
    ).fetchone()
    policy = (
        _policy_from_row(policy_row)
        if policy_row is not None
        else _default_policy(str(rule["task_id"]))
    )
    due_at, mode = _event_due(
        policy, critical=bool(rule.get("critical")), now=now
    )
    fingerprint_source = "|".join([
        str(rule["rule_id"]),
        str(payload.get("hotel_code") or ""),
        str(payload.get("stay_date") or ""),
        str(payload.get("event_type") or ""),
        str(rule.get("revision") or 1),
        str(trigger_count),
    ])
    fingerprint = hashlib.sha256(
        fingerprint_source.encode("utf-8")
    ).hexdigest()
    cooldown = max(0, int(rule.get("cooldown_seconds") or 0))
    if cooldown:
        recent = connection.execute(
            """
            SELECT alert_event_id,batch_id FROM alert_events
            WHERE rule_id=? AND hotel_code=? AND stay_date=? AND event_type=?
              AND rule_revision=? AND last_observed_at>=?
            ORDER BY last_observed_at DESC LIMIT 1
            """,
            (
                rule["rule_id"], payload["hotel_code"], payload["stay_date"],
                payload["event_type"], int(rule.get("revision") or 1),
                now - cooldown,
            ),
        ).fetchone()
        if recent is not None:
            connection.execute(
                """
                UPDATE alert_events SET occurrence_count=occurrence_count+1,
                    last_observed_at=?,payload_json=?,updated_at=?
                WHERE alert_event_id=?
                """,
                (
                    now, _json_dump(payload), now, recent["alert_event_id"],
                ),
            )
            connection.execute(
                """
                UPDATE alert_batches SET updated_at=? WHERE batch_id=?
                """,
                (now, recent["batch_id"]),
            )
            return None
    existing = connection.execute(
        "SELECT alert_event_id,occurrence_count FROM alert_events WHERE fingerprint=?",
        (fingerprint,),
    ).fetchone()
    if existing is not None:
        connection.execute(
            """
            UPDATE alert_events SET occurrence_count=occurrence_count+1,
                last_observed_at=?,updated_at=? WHERE alert_event_id=?
            """,
            (now, now, existing["alert_event_id"]),
        )
        return None
    batch_id = _find_or_create_batch(
        connection,
        str(rule["task_id"]),
        mode,
        due_at,
        aggregation_window=int(policy["aggregation_window_seconds"]),
        now=now,
    )
    event_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO alert_events(
            alert_event_id,rule_id,task_id,batch_id,event_type,hotel_code,
            stay_date,fingerprint,state,critical,rule_revision,occurrence_count,
            first_observed_at,last_observed_at,payload_json,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?, 'queued',?,?,1,?,?,?,?,?)
        """,
        (
            event_id, rule["rule_id"], rule["task_id"], batch_id,
            payload["event_type"], payload["hotel_code"], payload["stay_date"],
            fingerprint, int(bool(rule.get("critical"))),
            int(rule.get("revision") or 1), now, now,
            _json_dump(payload), now, now,
        ),
    )
    connection.execute(
        """
        UPDATE alert_batches SET event_count=event_count+1,updated_at=?
        WHERE batch_id=?
        """,
        (now, batch_id),
    )
    return {
        "alert_event_id": event_id,
        "batch_id": batch_id,
        "due_at": due_at,
        "mode": mode,
        "payload": deepcopy(dict(payload)),
    }


def evaluate_results(
    task_id: str,
    results: Iterable[Any],
    stay_date: str,
    checkout_date: str,
    *,
    now: Optional[float] = None,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    stay_date = _clean_date(stay_date, "stay_date", optional=False)
    checkout_date = _clean_date(checkout_date, "checkout_date", optional=False)
    observed_at = time.time() if now is None else float(now)
    rules = list_rules(task_id, enabled_only=True)
    if not rules:
        return []
    created: List[Dict[str, Any]] = []
    with _LOCK, _connect() as connection:
        _assert_task(connection, task_id)
        for raw_result in results:
            result = _result_dict(raw_result)
            if result.get("from_cache") and not result.get("cache_validated"):
                continue
            if result.get("requirement_unmet"):
                continue
            hotel_code = str(result.get("code") or "")
            if not hotel_code:
                continue
            member_price = _price_int(
                result.get("min_member_price")
                or result.get("min_member_price_text")
            )
            for rule in rules:
                if not _rule_applies(rule, hotel_code, stay_date):
                    continue
                scope_key = f"{hotel_code}|{stay_date}|{checkout_date}"
                previous = _observation(connection, rule["rule_id"], scope_key)
                available = result.get("available")
                price = _selected_price(rule, result)
                event_type = ""
                matched = bool(previous and previous["matched"])
                stored_available = (
                    available
                    if isinstance(available, bool)
                    else previous.get("available")
                    if previous
                    else None
                )
                stored_price = (
                    price
                    if price is not None
                    else previous.get("price_value")
                    if previous
                    else None
                )
                stored_member_price = (
                    member_price
                    if member_price is not None
                    else previous.get("member_price_value")
                    if previous
                    else None
                )
                rule_type = rule["rule_type"]
                if rule_type == "target_price":
                    if price is not None:
                        matched = price <= float(rule["threshold_value"])
                        if matched and not bool(previous and previous["matched"]):
                            event_type = "price.target_reached"
                elif rule_type == "member_price":
                    if member_price is not None:
                        matched = member_price <= float(rule["threshold_value"])
                        if matched and not bool(previous and previous["matched"]):
                            event_type = "price.member_target_reached"
                elif rule_type == "price_drop":
                    prior = (
                        previous.get("price_value")
                        if previous and previous.get("price_value") is not None
                        else None
                    )
                    if prior is not None and price is not None and price < prior:
                        absolute_drop = float(prior) - float(price)
                        percent_drop = absolute_drop * 100 / float(prior) if prior else 0
                        matched = bool(
                            (
                                rule.get("threshold_value")
                                and absolute_drop >= float(rule["threshold_value"])
                            )
                            or (
                                rule.get("threshold_percent")
                                and percent_drop >= float(rule["threshold_percent"])
                            )
                        )
                        if matched:
                            event_type = "price.drop"
                elif rule_type == "vacancy_transition":
                    direction = str(rule["config"].get("direction") or "available")
                    previous_available = previous.get("available") if previous else None
                    if isinstance(available, bool):
                        changed = (
                            (previous is None and available is True)
                            or (
                                previous is not None
                                and isinstance(previous_available, bool)
                                and previous_available != available
                            )
                        )
                        matched = bool(
                            changed
                            and (
                                direction == "any"
                                or (direction == "available" and available is True)
                                or (
                                    direction == "unavailable"
                                    and available is False
                                )
                            )
                        )
                        if matched:
                            event_type = (
                                "availability.available"
                                if available is True
                                else "availability.unavailable"
                            )
                trigger_count = int(previous.get("trigger_count") or 0) if previous else 0
                if event_type:
                    trigger_count += 1
                    payload = _event_payload(
                        rule, result, stay_date, checkout_date, event_type,
                        previous, price, member_price,
                    )
                    if dry_run:
                        created.append({"preview": True, "payload": payload})
                    else:
                        event = _store_event(
                            connection, rule, payload, trigger_count, now=observed_at
                        )
                        if event:
                            created.append(event)
                if not dry_run:
                    observation_payload = {
                        "checked_at": result.get("checked_at"),
                        "http_status": result.get("http_status"),
                        "triggered": bool(event_type),
                    }
                    connection.execute(
                        """
                        INSERT INTO alert_observations(
                            rule_id,scope_key,hotel_code,stay_date,available,
                            price_value,member_price_value,matched,trigger_count,
                            observed_at,payload_json
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(rule_id,scope_key) DO UPDATE SET
                            available=excluded.available,
                            price_value=excluded.price_value,
                            member_price_value=excluded.member_price_value,
                            matched=excluded.matched,
                            trigger_count=excluded.trigger_count,
                            observed_at=excluded.observed_at,
                            payload_json=excluded.payload_json
                        """,
                        (
                            rule["rule_id"], scope_key, hotel_code, stay_date,
                            (
                                None
                                if stored_available is None
                                else int(bool(stored_available))
                            ),
                            stored_price, stored_member_price, int(matched),
                            trigger_count,
                            observed_at, _json_dump(observation_payload),
                        ),
                    )
    return created


def preview_rule(
    task_id: str,
    payload: Mapping[str, Any],
    results: Iterable[Any],
    stay_date: str,
    checkout_date: str,
) -> List[Dict[str, Any]]:
    """Preview threshold matches without changing baselines, events or queues."""
    cleaned = _validate_rule(payload)
    rule = {
        **cleaned,
        "rule_id": "preview",
        "task_id": str(task_id),
    }
    stay_date = _clean_date(stay_date, "stay_date", optional=False)
    checkout_date = _clean_date(checkout_date, "checkout_date", optional=False)
    matches: List[Dict[str, Any]] = []
    for raw_result in results:
        result = _result_dict(raw_result)
        hotel_code = str(result.get("code") or "")
        if not hotel_code or not _rule_applies(rule, hotel_code, stay_date):
            continue
        price = _selected_price(rule, result)
        member_price = _price_int(
            result.get("min_member_price") or result.get("min_member_price_text")
        )
        event_type = ""
        if rule["rule_type"] == "target_price":
            if price is not None and price <= float(rule["threshold_value"]):
                event_type = "price.target_reached"
        elif rule["rule_type"] == "member_price":
            if (
                member_price is not None
                and member_price <= float(rule["threshold_value"])
            ):
                event_type = "price.member_target_reached"
        elif rule["rule_type"] == "price_drop":
            previous_price = _price_int(payload.get("previous_price"))
            if previous_price is not None and price is not None and price < previous_price:
                drop = previous_price - price
                percent = drop * 100 / previous_price if previous_price else 0
                if (
                    rule.get("threshold_value")
                    and drop >= float(rule["threshold_value"])
                ) or (
                    rule.get("threshold_percent")
                    and percent >= float(rule["threshold_percent"])
                ):
                    event_type = "price.drop"
        elif rule["rule_type"] == "vacancy_transition":
            desired = str(rule["config"].get("direction") or "available")
            if (
                desired == "any"
                or (desired == "available" and result.get("available") is True)
                or (desired == "unavailable" and result.get("available") is False)
            ):
                event_type = (
                    "availability.available"
                    if result.get("available") is True
                    else "availability.unavailable"
                )
        if event_type:
            matches.append(
                _event_payload(
                    rule,
                    result,
                    stay_date,
                    checkout_date,
                    event_type,
                    None,
                    price,
                    member_price,
                )
            )
    return matches


def _redact_detail(value: Any) -> str:
    text = " ".join(str(value or "").split())[:500]
    text = re.sub(
        r"(?i)(token|key|secret|password|authorization)\s*[=:]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", text)
    text = re.sub(
        r"(?i)([?&](?:token|key|secret|password)=)[^&\s]+",
        r"\1[redacted]",
        text,
    )
    text = re.sub(r"https?://\S+@", "https://[redacted]@", text)
    return text


def _batch_events(connection: sqlite3.Connection, batch_id: str) -> List[Dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT e.*,r.name AS current_rule_name
        FROM alert_events e
        LEFT JOIN price_alert_rules r ON r.rule_id=e.rule_id
        WHERE e.batch_id=? ORDER BY e.created_at,e.alert_event_id
        """,
        (batch_id,),
    ).fetchall()
    output: List[Dict[str, Any]] = []
    for row in rows:
        payload = _json_object(row["payload_json"])
        if row["current_rule_name"] and not payload.get("rule_name"):
            payload["rule_name"] = row["current_rule_name"]
        output.append({
            "alert_event_id": row["alert_event_id"],
            "rule_id": row["rule_id"],
            "event_type": row["event_type"],
            "hotel_code": row["hotel_code"],
            "stay_date": row["stay_date"],
            "critical": bool(row["critical"]),
            "occurrence_count": int(row["occurrence_count"]),
            "payload": payload,
        })
    return output


def _compose_batch(
    batch: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    language: str = "en",
) -> tuple[str, str, str]:
    language = language if language in {"zh_cn", "zh_tw", "ja", "ko", "en"} else "en"
    copy = {
        "zh_cn": {
            "digest": "Toyoko Tracker · 每日提醒摘要",
            "critical": "Toyoko Tracker · 紧急价格提醒",
            "alerts": "Toyoko Tracker · 价格提醒",
            "drop": "价格下降",
            "member": "会员价",
            "member_available": "发现会员价",
            "target": "达到目标价",
            "available": "出现空房",
            "unavailable": "空房消失",
        },
        "zh_tw": {
            "digest": "Toyoko Tracker · 每日提醒摘要",
            "critical": "Toyoko Tracker · 緊急價格提醒",
            "alerts": "Toyoko Tracker · 價格提醒",
            "drop": "價格下降",
            "member": "會員價",
            "member_available": "發現會員價",
            "target": "達到目標價",
            "available": "出現空房",
            "unavailable": "空房消失",
        },
        "ja": {
            "digest": "Toyoko Tracker · 日次通知まとめ",
            "critical": "Toyoko Tracker · 緊急料金通知",
            "alerts": "Toyoko Tracker · 料金通知",
            "drop": "値下げ",
            "member": "会員料金",
            "member_available": "会員料金を検出",
            "target": "目標料金に到達",
            "available": "空室が出ました",
            "unavailable": "空室がなくなりました",
        },
        "ko": {
            "digest": "Toyoko Tracker · 일일 알림 요약",
            "critical": "Toyoko Tracker · 긴급 가격 알림",
            "alerts": "Toyoko Tracker · 가격 알림",
            "drop": "가격 인하",
            "member": "회원가",
            "member_available": "회원가 발견",
            "target": "목표가 도달",
            "available": "빈 객실 발생",
            "unavailable": "빈 객실 종료",
        },
        "en": {
            "digest": "Toyoko Tracker · Daily alert digest",
            "critical": "Toyoko Tracker · Critical price alert",
            "alerts": "Toyoko Tracker · Price alerts",
            "drop": "price dropped",
            "member": "member price",
            "member_available": "member price available",
            "target": "target reached",
            "available": "room became available",
            "unavailable": "room became unavailable",
        },
    }[language]
    mode = str(batch.get("mode") or "")
    if mode == "daily_digest":
        title = f"{copy['digest']} ({len(events)})"
    elif any(bool(event.get("critical")) for event in events):
        title = f"{copy['critical']} ({len(events)})"
    else:
        title = f"{copy['alerts']} ({len(events)})"
    lines: List[str] = []
    first_url = ""
    for event in events:
        payload = event.get("payload") or {}
        event_type = str(event.get("event_type") or "")
        hotel = str(
            payload.get("hotel_name")
            or payload.get("hotel_code")
            or event.get("hotel_code")
            or "Hotel"
        )
        stay = str(payload.get("stay_date") or event.get("stay_date") or "")
        price = payload.get("price")
        member = payload.get("member_price")
        if event_type == "price.drop":
            prior = payload.get("previous_price")
            detail = f"{copy['drop']} {prior or '—'} → {price or '—'}"
        elif event_type == "price.member_target_reached":
            detail = (
                f"{copy['member']} ¥{int(member):,}"
                if member is not None
                else copy["member_available"]
            )
        elif event_type == "price.target_reached":
            detail = (
                f"{copy['target']} ¥{int(price):,}"
                if price is not None
                else copy["target"]
            )
        elif event_type == "availability.available":
            detail = copy["available"]
        elif event_type == "availability.unavailable":
            detail = copy["unavailable"]
        else:
            detail = event_type.replace(".", " ")
        lines.append(f"• {hotel} · {stay} · {detail}")
        if not first_url:
            first_url = str(payload.get("url") or "")
    return title, "\n".join(lines), first_url


def claim_due_batches(
    *,
    now: Optional[float] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    current = time.time() if now is None else float(now)
    claimed: List[Dict[str, Any]] = []
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM alert_batches
            WHERE state='queued' AND due_at<=?
            ORDER BY due_at,created_at LIMIT ?
            """,
            (current, max(1, min(100, int(limit)))),
        ).fetchall()
        for row in rows:
            changed = connection.execute(
                """
                UPDATE alert_batches SET state='sending',updated_at=?
                WHERE batch_id=? AND state='queued'
                """,
                (current, row["batch_id"]),
            ).rowcount
            if not changed:
                continue
            batch = dict(row)
            batch["state"] = "sending"
            batch["events"] = _batch_events(connection, str(row["batch_id"]))
            claimed.append(batch)
    return claimed


def finish_batch(
    batch_id: str,
    outcomes: Mapping[str, Mapping[str, Any] | str],
    *,
    title: str,
    body: str,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    completed = time.time() if now is None else float(now)
    with _LOCK, _connect() as connection:
        for channel, raw in outcomes.items():
            if isinstance(raw, Mapping):
                state = str(raw.get("state") or "sent")
                detail = _redact_detail(raw.get("detail") or raw.get("message") or "")
            else:
                state = str(raw or "sent")
                detail = ""
            if state not in {"sent", "success", "queued", "failed", "skipped"}:
                state = "failed"
            normalized = "sent" if state == "success" else state
            connection.execute(
                """
                INSERT INTO alert_deliveries(
                    delivery_id,batch_id,channel,state,detail,attempted_at,completed_at
                ) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(batch_id,channel) DO UPDATE SET
                    state=excluded.state,detail=excluded.detail,
                    attempted_at=excluded.attempted_at,
                    completed_at=excluded.completed_at
                """,
                (
                    uuid.uuid4().hex, batch_id, str(channel), normalized,
                    detail, completed, completed,
                ),
            )
        states = [
            str(row["state"])
            for row in connection.execute(
                "SELECT state FROM alert_deliveries WHERE batch_id=?",
                (batch_id,),
            ).fetchall()
        ]
        if not states:
            final_state = "skipped"
        elif all(state in {"sent", "queued"} for state in states):
            final_state = "sent"
        elif any(state in {"sent", "queued"} for state in states):
            final_state = "partial"
        else:
            final_state = "failed"
        connection.execute(
            """
            UPDATE alert_batches SET state=?,title=?,body=?,updated_at=?
            WHERE batch_id=?
            """,
            (final_state, title[:200], body[:8000], completed, batch_id),
        )
        connection.execute(
            "UPDATE alert_events SET state=?,updated_at=? WHERE batch_id=?",
            (final_state, completed, batch_id),
        )
    return get_batch(batch_id)


def retry_batch(batch_id: str) -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM alert_batches WHERE batch_id=?", (str(batch_id),)
        ).fetchone()
        if row is None:
            raise AlertNotFoundError(f"alert batch not found: {batch_id}")
        if str(row["state"]) not in {"failed", "partial"}:
            raise AlertConflictError(
                f"alert batch is not retryable: {row['state']}"
            )
        connection.execute(
            """
            UPDATE alert_batches SET state='queued',due_at=?,updated_at=?
            WHERE batch_id=?
            """,
            (time.time(), time.time(), str(batch_id)),
        )
        connection.execute(
            "UPDATE alert_events SET state='queued',updated_at=? WHERE batch_id=?",
            (time.time(), str(batch_id)),
        )
    return get_batch(batch_id)


def get_batch(batch_id: str) -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM alert_batches WHERE batch_id=?", (str(batch_id),)
        ).fetchone()
        if row is None:
            raise AlertNotFoundError(f"alert batch not found: {batch_id}")
        events = _batch_events(connection, str(batch_id))
        deliveries = [
            {
                "channel": delivery["channel"],
                "state": delivery["state"],
                "detail": _redact_detail(delivery["detail"]),
                "attempted_at": delivery["attempted_at"],
                "completed_at": delivery["completed_at"],
            }
            for delivery in connection.execute(
                """
                SELECT channel,state,detail,attempted_at,completed_at
                FROM alert_deliveries WHERE batch_id=? ORDER BY channel
                """,
                (str(batch_id),),
            ).fetchall()
        ]
    return {
        "batch_id": row["batch_id"],
        "task_id": row["task_id"],
        "mode": row["mode"],
        "state": row["state"],
        "due_at": row["due_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "title": row["title"],
        "body": row["body"],
        "event_count": row["event_count"],
        "events": events,
        "deliveries": deliveries,
    }


def list_history(
    *,
    task_id: str = "",
    hotel_code: str = "",
    event_type: str = "",
    state: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if task_id:
        clauses.append("e.task_id=?")
        params.append(str(task_id))
    if hotel_code:
        clauses.append("e.hotel_code=?")
        params.append(str(hotel_code))
    if event_type:
        clauses.append("e.event_type=?")
        params.append(str(event_type))
    if state:
        clauses.append("e.state=?")
        params.append(str(state))
    query = """
        SELECT e.*,b.mode,b.due_at,b.title,b.body,b.state AS batch_state,
               r.name AS current_rule_name
        FROM alert_events e
        LEFT JOIN alert_batches b ON b.batch_id=e.batch_id
        LEFT JOIN price_alert_rules r ON r.rule_id=e.rule_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY e.created_at DESC LIMIT ?"
    params.append(max(1, min(500, int(limit))))
    with _LOCK, _connect() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
        batch_ids = list({str(row["batch_id"]) for row in rows if row["batch_id"]})
        deliveries: Dict[str, List[Dict[str, Any]]] = {}
        if batch_ids:
            placeholders = ",".join("?" for _ in batch_ids)
            for row in connection.execute(
                f"""
                SELECT batch_id,channel,state,detail,attempted_at,completed_at
                FROM alert_deliveries WHERE batch_id IN ({placeholders})
                ORDER BY attempted_at
                """,
                tuple(batch_ids),
            ).fetchall():
                deliveries.setdefault(str(row["batch_id"]), []).append({
                    "channel": row["channel"],
                    "state": row["state"],
                    "detail": _redact_detail(row["detail"]),
                    "attempted_at": row["attempted_at"],
                    "completed_at": row["completed_at"],
                })
    output: List[Dict[str, Any]] = []
    for row in rows:
        payload = _json_object(row["payload_json"])
        payload.pop("credentials", None)
        output.append({
            "alert_event_id": row["alert_event_id"],
            "rule_id": row["rule_id"],
            "rule_name": payload.get("rule_name") or row["current_rule_name"] or "",
            "task_id": row["task_id"],
            "batch_id": row["batch_id"],
            "batch_mode": row["mode"],
            "event_type": row["event_type"],
            "hotel_code": row["hotel_code"],
            "stay_date": row["stay_date"],
            "state": row["state"],
            "critical": bool(row["critical"]),
            "occurrence_count": int(row["occurrence_count"]),
            "first_observed_at": row["first_observed_at"],
            "last_observed_at": row["last_observed_at"],
            "due_at": row["due_at"],
            "created_at": row["created_at"],
            "payload": payload,
            "deliveries": deliveries.get(str(row["batch_id"]), []),
        })
    return output


def calendar_badges(
    task_id: str,
    hotel_code: str,
    month: str,
) -> Dict[str, Dict[str, Any]]:
    if not re.fullmatch(r"\d{4}-\d{2}", str(month or "")):
        raise AlertValidationError("month must use YYYY-MM")
    start = f"{month}-01"
    year, month_number = (int(part) for part in month.split("-"))
    if not 1 <= month_number <= 12:
        raise AlertValidationError("month must use YYYY-MM")
    if month_number == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month_number + 1:02d}-01"
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT stay_date,COUNT(*) AS count,
                   SUM(CASE WHEN critical=1 THEN 1 ELSE 0 END) AS critical_count,
                   MAX(created_at) AS latest_at
            FROM alert_events
            WHERE task_id=? AND hotel_code=? AND stay_date>=? AND stay_date<?
            GROUP BY stay_date ORDER BY stay_date
            """,
            (str(task_id), str(hotel_code), start, end),
        ).fetchall()
    return {
        str(row["stay_date"]): {
            "count": int(row["count"]),
            "critical_count": int(row["critical_count"] or 0),
            "latest_at": float(row["latest_at"]),
        }
        for row in rows
    }


def alert_summary(task_id: str = "") -> Dict[str, Any]:
    where = " WHERE task_id=?" if task_id else ""
    params: tuple[Any, ...] = (str(task_id),) if task_id else ()
    with _LOCK, _connect() as connection:
        rule_row = connection.execute(
            "SELECT COUNT(*) AS total,SUM(enabled) AS enabled FROM price_alert_rules"
            + where,
            params,
        ).fetchone()
        event_row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN state='queued' THEN 1 ELSE 0 END) AS queued,
                   SUM(CASE WHEN created_at>=? THEN 1 ELSE 0 END) AS recent
            FROM alert_events
            """
            + (" WHERE task_id=?" if task_id else ""),
            ((time.time() - 86400, str(task_id)) if task_id else (time.time() - 86400,)),
        ).fetchone()
    return {
        "rules": int(rule_row["total"] or 0),
        "enabled_rules": int(rule_row["enabled"] or 0),
        "events": int(event_row["total"] or 0),
        "queued_events": int(event_row["queued"] or 0),
        "last_24h": int(event_row["recent"] or 0),
    }


def record_legacy_event(
    *,
    source_event_id: str,
    task_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    outcomes: Optional[Mapping[str, Mapping[str, Any] | str]] = None,
) -> Optional[str]:
    """Mirror a delivered legacy availability event into Phase 2 history."""
    if not task_id:
        return None
    now = time.time()
    fingerprint = hashlib.sha256(
        f"legacy|{source_event_id}".encode("utf-8")
    ).hexdigest()
    with _LOCK, _connect() as connection:
        if connection.execute(
            "SELECT 1 FROM alert_events WHERE fingerprint=?", (fingerprint,)
        ).fetchone():
            return None
        _assert_task(connection, task_id)
        batch_id = uuid.uuid4().hex
        connection.execute(
            """
            INSERT INTO alert_batches(
                batch_id,task_id,mode,state,due_at,created_at,updated_at,event_count
            ) VALUES (?,?,'legacy','sent',?,?,?,1)
            """,
            (batch_id, task_id, now, now, now),
        )
        event_id = uuid.uuid4().hex
        event_payload = deepcopy(dict(payload))
        event_payload["source_event_id"] = source_event_id
        connection.execute(
            """
            INSERT INTO alert_events(
                alert_event_id,rule_id,task_id,batch_id,event_type,hotel_code,
                stay_date,fingerprint,state,critical,occurrence_count,
                first_observed_at,last_observed_at,payload_json,created_at,updated_at
            ) VALUES (?,NULL,?,?,?,?,?,?, 'sent',0,1,?,?,?,?,?)
            """,
            (
                event_id, task_id, batch_id, event_type,
                str(payload.get("code") or payload.get("hotel_code") or ""),
                str(payload.get("stay_date") or ""),
                fingerprint, now, now, _json_dump(event_payload), now, now,
            ),
        )
    if outcomes:
        finish_batch(
            batch_id,
            outcomes,
            title=str(payload.get("title") or ""),
            body=str(payload.get("body") or ""),
            now=now,
        )
    return event_id


class AlertDispatcher:
    """Persistent due-batch dispatcher used by WebUI and desktop runtimes."""

    def __init__(
        self,
        config_provider: Callable[[str], Any],
        delivery_handler: Callable[
            ..., Mapping[str, Mapping[str, Any] | str]
        ],
        *,
        log: Optional[Callable[[str], None]] = None,
        poll_interval: float = 1.0,
    ) -> None:
        self._config_provider = config_provider
        self._delivery_handler = delivery_handler
        self._log = log or (lambda _message: None)
        self._poll_interval = max(0.1, float(poll_interval))
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            initialize_alerting()
            with _LOCK, _connect() as connection:
                connection.execute(
                    """
                    UPDATE alert_batches SET state='queued',due_at=?,updated_at=?
                    WHERE state='sending'
                    """,
                    (time.time(), time.time()),
                )
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="alert-dispatcher", daemon=True
            )
            self._thread.start()
        self._log("[alerts] dispatcher started")

    def stop(self, timeout: float = 3.0) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
            self._wake.set()
        if thread and thread.is_alive():
            thread.join(timeout=max(0, float(timeout)))
        with self._lock:
            if thread is None or not thread.is_alive():
                self._thread = None

    def wake(self) -> None:
        self._wake.set()

    def deliver_due_once(self, *, now: Optional[float] = None) -> int:
        batches = claim_due_batches(now=now)
        delivered = 0
        for batch in batches:
            try:
                events = batch.get("events") or []
                cfg = self._config_provider(str(batch.get("task_id") or ""))
                title, body, url = _compose_batch(
                    batch,
                    events,
                    str(getattr(cfg, "primary_language", "en") or "en"),
                )
                previous = get_batch(str(batch["batch_id"])).get("deliveries") or []
                retry_channels = (
                    [
                        str(item["channel"])
                        for item in previous
                        if str(item.get("state") or "") not in {"sent", "queued"}
                    ]
                    if previous
                    else None
                )
                try:
                    outcomes = self._delivery_handler(
                        cfg, title, body, url, retry_channels
                    )
                except TypeError:
                    outcomes = self._delivery_handler(cfg, title, body, url)
                finish_batch(
                    str(batch["batch_id"]), outcomes, title=title, body=body, now=now
                )
                delivered += 1
            except Exception as exc:
                self._log(
                    f"[alerts] batch {str(batch.get('batch_id') or '')[:8]} failed: {exc}"
                )
                try:
                    finish_batch(
                        str(batch["batch_id"]),
                        {"dispatcher": {"state": "failed", "detail": str(exc)}},
                        title="Toyoko Tracker alert",
                        body="Alert delivery failed",
                        now=now,
                    )
                except AlertNotFoundError:
                    pass
        return delivered

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.deliver_due_once()
            except Exception as exc:
                self._log(f"[alerts] dispatcher loop error: {exc}")
            self._wake.wait(self._poll_interval)
            self._wake.clear()
