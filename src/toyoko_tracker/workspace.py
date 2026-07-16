from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Dict, Iterator, List

from .models import AppConfig
from .settings import HOTEL_DATABASE_PATH


WORKSPACE_SCHEMA_VERSION = 1
DEFAULT_TASK_ID = "default"
_LOCK = threading.RLock()

_TASK_CONFIG_FIELDS = {
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
    "om_requirement",
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
}


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH) or ".", exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
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


def task_config_snapshot(cfg: AppConfig) -> Dict[str, Any]:
    raw = asdict(cfg)
    snapshot = {key: raw[key] for key in _TASK_CONFIG_FIELDS if key in raw}
    snapshot["room_requirement"] = str(
        getattr(cfg, "room_requirement", None)
        or getattr(cfg, "om_requirement", "any")
        or "any"
    )
    snapshot.pop("om_requirement", None)
    return snapshot


def ensure_default_task(cfg: AppConfig, name: str = "默认监控") -> str:
    now = time.time()
    config_json = json.dumps(
        task_config_snapshot(cfg),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT task_id FROM monitor_tasks ORDER BY sort_order, created_at LIMIT 1"
        ).fetchone()
        if row is not None:
            return str(row["task_id"])
        connection.execute(
            """
            INSERT INTO monitor_tasks(
                task_id, name, desired_state, runtime_state, config_json,
                sort_order, revision, created_at, updated_at
            ) VALUES (?, ?, 'paused', 'idle', ?, 0, 1, ?, ?)
            """,
            (DEFAULT_TASK_ID, str(name or "默认监控")[:120], config_json, now, now),
        )
    return DEFAULT_TASK_ID


def list_tasks() -> List[Dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT task_id, name, desired_state, runtime_state, config_json,
                   sort_order, revision, created_at, updated_at, last_started_at,
                   last_stopped_at, next_run_at, last_error, result_summary_json
            FROM monitor_tasks
            ORDER BY sort_order, created_at
            """
        ).fetchall()
    tasks: List[Dict[str, Any]] = []
    for row in rows:
        try:
            config = json.loads(row["config_json"])
        except (TypeError, ValueError):
            config = {}
        try:
            summary = json.loads(row["result_summary_json"])
        except (TypeError, ValueError):
            summary = {}
        tasks.append({
            "task_id": str(row["task_id"]),
            "name": str(row["name"]),
            "desired_state": str(row["desired_state"]),
            "runtime_state": str(row["runtime_state"]),
            "config": config,
            "sort_order": int(row["sort_order"]),
            "revision": int(row["revision"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "last_started_at": row["last_started_at"],
            "last_stopped_at": row["last_stopped_at"],
            "next_run_at": row["next_run_at"],
            "last_error": str(row["last_error"] or ""),
            "result_summary": summary,
        })
    return tasks
