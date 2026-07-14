from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, TypeVar

from .settings import HOTEL_DATABASE_PATH


T = TypeVar("T")
_LOCK = threading.RLock()
_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT: Dict[str, "_Inflight"] = {}
_METRICS: Dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "writes": 0,
    "live_requests": 0,
    "coalesced_requests": 0,
    "conditional_hits": 0,
    "fallback_hits": 0,
    "evictions": 0,
}
_STATUS_CACHE: Dict[str, Any] = {"checked_at": 0.0, "entries": 0, "fresh_entries": 0}


@dataclass
class CacheEntry:
    cache_key: str
    result: Dict[str, Any]
    age_sec: int
    expired: bool
    etag: str = ""
    last_modified: str = ""


@dataclass
class _Inflight:
    event: threading.Event
    result: Any = None
    error: Optional[BaseException] = None


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS scan_cache (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            hotel_code TEXT NOT NULL,
            result_json TEXT NOT NULL,
            etag TEXT NOT NULL DEFAULT '',
            last_modified TEXT NOT NULL DEFAULT '',
            stored_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            last_accessed_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scan_cache_expiry ON scan_cache(expires_at);
        CREATE INDEX IF NOT EXISTS idx_scan_cache_hotel ON scan_cache(provider, hotel_code);
        CREATE TABLE IF NOT EXISTS runtime_checkpoints (
            scope_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        """
    )
    return connection


def _metric(name: str, amount: int = 1) -> None:
    with _LOCK:
        _METRICS[name] = int(_METRICS.get(name, 0)) + amount


def get(cache_key: str, *, allow_expired: bool = False, count_metrics: bool = True) -> Optional[CacheEntry]:
    now = time.time()
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM scan_cache WHERE cache_key=?", (cache_key,)
        ).fetchone()
        if row is None:
            if count_metrics:
                _metric("misses")
            return None
        expired = float(row["expires_at"]) <= now
        if expired and not allow_expired:
            if count_metrics:
                _metric("misses")
            return None
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            connection.execute("DELETE FROM scan_cache WHERE cache_key=?", (cache_key,))
            _metric("evictions")
            if count_metrics:
                _metric("misses")
            return None
        connection.execute(
            "UPDATE scan_cache SET last_accessed_at=? WHERE cache_key=?", (now, cache_key)
        )
    if count_metrics:
        _metric("hits")
    return CacheEntry(
        cache_key=cache_key,
        result=result,
        age_sec=max(0, int(now - float(row["stored_at"]))),
        expired=expired,
        etag=str(row["etag"] or ""),
        last_modified=str(row["last_modified"] or ""),
    )


def put(
    cache_key: str,
    provider: str,
    hotel_code: str,
    result: Dict[str, Any],
    ttl_seconds: float,
    *,
    etag: str = "",
    last_modified: str = "",
) -> None:
    now = time.time()
    ttl = max(1.0, min(3600.0, float(ttl_seconds)))
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO scan_cache(
                cache_key, provider, hotel_code, result_json, etag, last_modified,
                stored_at, expires_at, last_accessed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                provider=excluded.provider, hotel_code=excluded.hotel_code,
                result_json=excluded.result_json, etag=excluded.etag,
                last_modified=excluded.last_modified, stored_at=excluded.stored_at,
                expires_at=excluded.expires_at, last_accessed_at=excluded.last_accessed_at
            """,
            (
                cache_key,
                provider,
                hotel_code,
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                str(etag or ""),
                str(last_modified or ""),
                now,
                now + ttl,
                now,
            ),
        )
    _metric("writes")
    with _LOCK:
        _STATUS_CACHE["checked_at"] = 0.0


def mark_live_request() -> None:
    _metric("live_requests")


def mark_conditional_hit() -> None:
    _metric("conditional_hits")


def mark_fallback_hit() -> None:
    _metric("fallback_hits")


def coalesced_call(cache_key: str, producer: Callable[[], T], timeout: float = 30.0) -> tuple[T, bool]:
    with _INFLIGHT_LOCK:
        pending = _INFLIGHT.get(cache_key)
        if pending is None:
            pending = _Inflight(event=threading.Event())
            _INFLIGHT[cache_key] = pending
            owner = True
        else:
            owner = False
            _metric("coalesced_requests")
    if not owner:
        if not pending.event.wait(timeout=max(1.0, float(timeout))):
            raise TimeoutError("timed out waiting for a coalesced hotel request")
        if pending.error is not None:
            raise pending.error
        return deepcopy(pending.result), True
    try:
        pending.result = producer()
        return deepcopy(pending.result), False
    except BaseException as exc:
        pending.error = exc
        raise
    finally:
        pending.event.set()
        with _INFLIGHT_LOCK:
            _INFLIGHT.pop(cache_key, None)


def prune(max_age_seconds: int = 7 * 24 * 60 * 60) -> int:
    cutoff = time.time() - max(3600, int(max_age_seconds))
    with _LOCK, _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM scan_cache WHERE last_accessed_at < ?", (cutoff,)
        )
        removed = max(0, int(cursor.rowcount or 0))
    if removed:
        _metric("evictions", removed)
        with _LOCK:
            _STATUS_CACHE["checked_at"] = 0.0
    return removed


def clear() -> int:
    with _LOCK, _connect() as connection:
        count = int(connection.execute("SELECT COUNT(*) FROM scan_cache").fetchone()[0])
        connection.execute("DELETE FROM scan_cache")
        _STATUS_CACHE.update({"checked_at": 0.0, "entries": 0, "fresh_entries": 0})
    return count


def status_snapshot() -> Dict[str, Any]:
    now = time.time()
    with _LOCK:
        if now - float(_STATUS_CACHE.get("checked_at") or 0.0) >= 10.0:
            with _connect() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS total, "
                    "SUM(CASE WHEN expires_at>? THEN 1 ELSE 0 END) AS fresh FROM scan_cache",
                    (now,),
                ).fetchone()
            _STATUS_CACHE.update({
                "checked_at": now,
                "entries": int(row["total"] or 0),
                "fresh_entries": int(row["fresh"] or 0),
            })
        metrics = dict(_METRICS)
        entries = int(_STATUS_CACHE.get("entries") or 0)
        fresh_entries = int(_STATUS_CACHE.get("fresh_entries") or 0)
    hits = int(metrics.get("hits") or 0)
    misses = int(metrics.get("misses") or 0)
    total_reads = hits + misses
    metrics.update({
        "entries": entries,
        "fresh_entries": fresh_entries,
        "hit_rate_percent": int(round(hits * 100 / total_reads)) if total_reads else 0,
        "saved_requests": hits + int(metrics.get("coalesced_requests") or 0) + int(metrics.get("conditional_hits") or 0),
    })
    return metrics


def save_checkpoint(scope_key: str, payload: Dict[str, Any]) -> None:
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO runtime_checkpoints(scope_key, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(scope_key) DO UPDATE SET
                payload_json=excluded.payload_json, updated_at=excluded.updated_at
            """,
            (scope_key, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
        )
        connection.execute(
            "DELETE FROM runtime_checkpoints WHERE updated_at < ?", (now - 7 * 24 * 60 * 60,)
        )


def load_checkpoint(scope_key: str, max_age_seconds: int = 24 * 60 * 60) -> Optional[Dict[str, Any]]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT payload_json, updated_at FROM runtime_checkpoints WHERE scope_key=?", (scope_key,)
        ).fetchone()
    if row is None or time.time() - float(row["updated_at"]) > max(60, int(max_age_seconds)):
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    payload["checkpoint_age_sec"] = max(0, int(time.time() - float(row["updated_at"])))
    return payload
