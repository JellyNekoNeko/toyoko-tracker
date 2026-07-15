from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .settings import HOTEL_DATABASE_PATH


_LOCK = threading.RLock()


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    event_type: str
    dedupe_key: str
    payload: Dict[str, Any]
    created_at: float
    created: bool


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH) or ".", exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tracker_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            dedupe_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tracker_events_type_time
            ON tracker_events(event_type, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tracker_events_dedupe
            ON tracker_events(event_type, dedupe_key, created_at DESC);
        CREATE TABLE IF NOT EXISTS notification_deliveries (
            event_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            state TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL,
            PRIMARY KEY(event_id, channel)
        );
        """
    )
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def publish_event(
    event_type: str,
    dedupe_key: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    dedupe_window_seconds: int = 30,
) -> EventRecord:
    now = time.time()
    event_type = str(event_type or "event").strip()[:80]
    dedupe_key = str(dedupe_key or event_type).strip()[:500]
    payload = dict(payload or {})
    window = max(0, min(86400, int(dedupe_window_seconds)))
    with _LOCK, _connect() as connection:
        if window:
            row = connection.execute(
                """
                SELECT event_id, payload_json, created_at FROM tracker_events
                WHERE event_type=? AND dedupe_key=? AND created_at BETWEEN ? AND ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (event_type, dedupe_key, now - window, now + 300),
            ).fetchone()
            if row is not None:
                try:
                    existing_payload = json.loads(row["payload_json"])
                except (TypeError, ValueError):
                    existing_payload = payload
                return EventRecord(
                    str(row["event_id"]), event_type, dedupe_key,
                    existing_payload, float(row["created_at"]), False,
                )
        event_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO tracker_events(event_id,event_type,dedupe_key,payload_json,created_at) "
            "VALUES (?,?,?,?,?)",
            (
                event_id, event_type, dedupe_key,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now,
            ),
        )
        connection.execute(
            "DELETE FROM tracker_events WHERE created_at<?", (now - 90 * 24 * 60 * 60,)
        )
    return EventRecord(event_id, event_type, dedupe_key, payload, now, True)


def begin_delivery(event_id: str, channel: str) -> bool:
    now = time.time()
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT state FROM notification_deliveries WHERE event_id=? AND channel=?",
            (event_id, channel),
        ).fetchone()
        if row is not None and str(row["state"]) in {"queued", "sending", "success"}:
            return False
        connection.execute(
            """
            INSERT INTO notification_deliveries(event_id,channel,state,detail,updated_at)
            VALUES (?,?,?,'',?)
            ON CONFLICT(event_id,channel) DO UPDATE SET
                state=excluded.state, detail='', updated_at=excluded.updated_at
            """,
            (event_id, channel, "sending", now),
        )
    return True


def finish_delivery(event_id: str, channel: str, state: str, detail: str = "") -> None:
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO notification_deliveries(event_id,channel,state,detail,updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(event_id,channel) DO UPDATE SET
                state=excluded.state, detail=excluded.detail, updated_at=excluded.updated_at
            """,
            (event_id, channel, str(state or "success"), str(detail or "")[:500], time.time()),
        )


def list_events(limit: int = 100, event_type: str = "") -> List[Dict[str, Any]]:
    limit = max(1, min(500, int(limit)))
    query = "SELECT * FROM tracker_events"
    params: Tuple[Any, ...] = ()
    if event_type:
        query += " WHERE event_type=?"
        params = (str(event_type),)
    query += " ORDER BY created_at DESC LIMIT ?"
    params += (limit,)
    with _LOCK, _connect() as connection:
        rows = connection.execute(query, params).fetchall()
        deliveries = connection.execute(
            "SELECT event_id,channel,state,detail,updated_at FROM notification_deliveries "
            "WHERE event_id IN (SELECT event_id FROM tracker_events ORDER BY created_at DESC LIMIT ?)",
            (limit,),
        ).fetchall()
    by_event: Dict[str, List[Dict[str, Any]]] = {}
    for row in deliveries:
        by_event.setdefault(str(row["event_id"]), []).append({
            "channel": row["channel"], "state": row["state"],
            "detail": row["detail"], "updated_at": row["updated_at"],
        })
    output = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            payload = {}
        output.append({
            "event_id": row["event_id"], "event_type": row["event_type"],
            "dedupe_key": row["dedupe_key"], "payload": payload,
            "created_at": row["created_at"],
            "deliveries": by_event.get(str(row["event_id"]), []),
        })
    return output


def event_status_snapshot() -> Dict[str, int]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN created_at BETWEEN ? AND ? THEN 1 ELSE 0 END) AS recent
            FROM tracker_events
            """,
            (time.time() - 24 * 60 * 60, time.time() + 300),
        ).fetchone()
        pending = connection.execute(
            "SELECT COUNT(*) FROM notification_deliveries WHERE state IN ('queued','sending')"
        ).fetchone()[0]
    return {
        "total": int(row["total"] or 0),
        "last_24h": int(row["recent"] or 0),
        "pending_deliveries": int(pending or 0),
    }
