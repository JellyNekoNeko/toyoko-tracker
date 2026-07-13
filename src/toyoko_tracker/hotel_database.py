from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .settings import HOTEL_DATABASE_PATH

_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS hotels (
            provider TEXT NOT NULL,
            code TEXT NOT NULL,
            display_code TEXT NOT NULL DEFAULT '',
            region_id INTEGER,
            prefecture_id INTEGER,
            detail_area_id INTEGER,
            lat REAL,
            lng REAL,
            data_json TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            PRIMARY KEY (provider, code)
        );
        CREATE INDEX IF NOT EXISTS idx_hotels_area
            ON hotels(provider, active, region_id, prefecture_id, detail_area_id);
        CREATE TABLE IF NOT EXISTS provider_sync (
            provider TEXT PRIMARY KEY,
            checked_at TEXT NOT NULL,
            hotel_count INTEGER NOT NULL DEFAULT 0,
            coordinate_count INTEGER NOT NULL DEFAULT 0,
            new_count INTEGER NOT NULL DEFAULT 0,
            removed_count INTEGER NOT NULL DEFAULT 0,
            new_hotels_json TEXT NOT NULL DEFAULT '[]',
            removed_hotels_json TEXT NOT NULL DEFAULT '[]',
            error TEXT NOT NULL DEFAULT ''
        );
        """
    )
    return connection


def sync_provider(provider: str, hotels: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    rows = [dict(hotel) for hotel in hotels if str(hotel.get("code") or "")]
    with _LOCK, _connect() as connection:
        previous = {
            row["code"]: row
            for row in connection.execute(
                "SELECT code, data_json FROM hotels WHERE provider=? AND active=1", (provider,)
            )
        }
        baseline = not bool(previous) and connection.execute(
            "SELECT 1 FROM provider_sync WHERE provider=?", (provider,)
        ).fetchone() is None
        current_codes = {str(hotel["code"]) for hotel in rows}
        new_codes = set() if baseline else current_codes - set(previous)
        removed_codes = set() if baseline else set(previous) - current_codes
        new_hotels = [
            {"code": str(hotel["code"]), "name": hotel.get("name_ja") or hotel.get("name_en") or hotel.get("name") or ""}
            for hotel in rows if str(hotel["code"]) in new_codes
        ]
        removed_hotels = []
        for code in sorted(removed_codes):
            try:
                old = json.loads(previous[code]["data_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                old = {}
            removed_hotels.append({"code": code, "name": old.get("name_ja") or old.get("name_en") or old.get("name") or ""})

        for hotel in rows:
            code = str(hotel["code"])
            connection.execute(
                """
                INSERT INTO hotels (
                    provider, code, display_code, region_id, prefecture_id, detail_area_id,
                    lat, lng, data_json, active, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(provider, code) DO UPDATE SET
                    display_code=excluded.display_code, region_id=excluded.region_id,
                    prefecture_id=excluded.prefecture_id, detail_area_id=excluded.detail_area_id,
                    lat=excluded.lat, lng=excluded.lng, data_json=excluded.data_json,
                    active=1, last_seen_at=excluded.last_seen_at
                """,
                (
                    provider, code, str(hotel.get("display_code") or code), hotel.get("region_id"),
                    hotel.get("prefecture_id"), hotel.get("detail_area_id"), hotel.get("lat"),
                    hotel.get("lng"), json.dumps(hotel, ensure_ascii=False), now, now,
                ),
            )
        if current_codes:
            placeholders = ",".join("?" for _ in current_codes)
            connection.execute(
                f"UPDATE hotels SET active=0, last_seen_at=? WHERE provider=? AND code NOT IN ({placeholders})",
                (now, provider, *sorted(current_codes)),
            )
        coordinate_count = sum(hotel.get("lat") is not None and hotel.get("lng") is not None for hotel in rows)
        connection.execute(
            """
            INSERT INTO provider_sync (
                provider, checked_at, hotel_count, coordinate_count, new_count, removed_count,
                new_hotels_json, removed_hotels_json, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')
            ON CONFLICT(provider) DO UPDATE SET
                checked_at=excluded.checked_at, hotel_count=excluded.hotel_count,
                coordinate_count=excluded.coordinate_count, new_count=excluded.new_count,
                removed_count=excluded.removed_count, new_hotels_json=excluded.new_hotels_json,
                removed_hotels_json=excluded.removed_hotels_json, error=''
            """,
            (
                provider, now, len(rows), coordinate_count, len(new_hotels), len(removed_hotels),
                json.dumps(new_hotels, ensure_ascii=False), json.dumps(removed_hotels, ensure_ascii=False),
            ),
        )
    return {"provider": provider, "count": len(rows), "new": new_hotels, "removed": removed_hotels}


def record_sync_error(provider: str, error: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO provider_sync(provider, checked_at, error) VALUES (?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET checked_at=excluded.checked_at, error=excluded.error
            """,
            (provider, now, str(error)[:1000]),
        )


def provider_count(provider: Optional[str] = None) -> int:
    sql = "SELECT COUNT(*) FROM hotels WHERE active=1"
    args: tuple[Any, ...] = ()
    if provider:
        sql += " AND provider=?"
        args = (provider,)
    with _LOCK, _connect() as connection:
        return int(connection.execute(sql, args).fetchone()[0])


def load_hotels(
    provider: str,
    primary_language: str = "zh_cn",
    *,
    region_id: Optional[int] = None,
    prefecture_id: Optional[int] = None,
    detail_area_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    clauses = ["provider=?", "active=1"]
    args: List[Any] = [provider]
    for column, value in (
        ("region_id", region_id), ("prefecture_id", prefecture_id), ("detail_area_id", detail_area_id),
    ):
        if value is not None:
            clauses.append(f"{column}=?")
            args.append(int(value))
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"SELECT data_json FROM hotels WHERE {' AND '.join(clauses)} ORDER BY display_code", args
        ).fetchall()
    language = primary_language if primary_language in {"zh_cn", "zh_tw", "ja", "ko", "en"} else "zh_cn"
    hotels = []
    for row in rows:
        try:
            hotel = json.loads(row["data_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        hotel["name_primary"] = hotel.get(f"name_{language}") or hotel.get("name_ja") or hotel.get("name_en") or hotel.get("name") or ""
        hotel["name"] = hotel["name_primary"]
        hotels.append(hotel)
    return hotels


def load_hotel(code: str, primary_language: str = "zh_cn") -> Optional[Dict[str, Any]]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT data_json FROM hotels WHERE code=? AND active=1 LIMIT 1", (str(code or ""),)
        ).fetchone()
    if row is None:
        return None
    try:
        hotel = json.loads(row["data_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    language = primary_language if primary_language in {"zh_cn", "zh_tw", "ja", "ko", "en"} else "zh_cn"
    hotel["name_primary"] = hotel.get(f"name_{language}") or hotel.get("name_ja") or hotel.get("name_en") or hotel.get("name") or ""
    hotel["name"] = hotel["name_primary"]
    return hotel


def status_snapshot() -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        rows = connection.execute("SELECT * FROM provider_sync ORDER BY provider").fetchall()
    providers = {}
    for row in rows:
        item = dict(row)
        for key in ("new_hotels_json", "removed_hotels_json"):
            target = key.removesuffix("_json")
            try:
                item[target] = json.loads(item.pop(key) or "[]")
            except json.JSONDecodeError:
                item[target] = []
        providers[item.pop("provider")] = item
    return {"database_path": HOTEL_DATABASE_PATH, "providers": providers}
