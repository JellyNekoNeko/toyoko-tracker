from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, Iterator, List, Optional

from .models import AppConfig, HotelResult
from .settings import HOTEL_DATABASE_PATH


_LOCK = threading.RLock()
_PRICE_PATTERN = re.compile(r"\d[\d,]*")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH) or ".", exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS price_calendar_days (
            condition_key TEXT NOT NULL,
            hotel_code TEXT NOT NULL,
            provider TEXT NOT NULL,
            stay_date TEXT NOT NULL,
            checkout_date TEXT NOT NULL,
            observed_at REAL NOT NULL,
            result_json TEXT NOT NULL,
            PRIMARY KEY(condition_key, hotel_code, stay_date)
        );
        CREATE INDEX IF NOT EXISTS idx_price_calendar_hotel_month
            ON price_calendar_days(hotel_code, stay_date);
        CREATE INDEX IF NOT EXISTS idx_price_calendar_observed
            ON price_calendar_days(observed_at);
        """
    )
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def condition_key(cfg: AppConfig) -> str:
    """Return the cache namespace for one set of price-affecting stay conditions."""
    payload = {
        "people": max(1, int(getattr(cfg, "people", 1) or 1)),
        "rooms": max(1, int(getattr(cfg, "rooms", 1) or 1)),
        "smoking": str(getattr(cfg, "smoking", "all") or "all"),
        "room_requirement": str(
            getattr(cfg, "room_requirement", None)
            or getattr(cfg, "om_requirement", "any")
            or "any"
        ),
        "membership": str(getattr(cfg, "membership_status", "member") or "member"),
    }
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def month_dates(month: str) -> List[str]:
    if not re.fullmatch(r"\d{4}-\d{2}", str(month or "")):
        raise ValueError("month must use YYYY-MM")
    year, month_number = (int(part) for part in month.split("-"))
    if not 1 <= month_number <= 12:
        raise ValueError("month must use YYYY-MM")
    count = calendar.monthrange(year, month_number)[1]
    return [f"{year:04d}-{month_number:02d}-{day:02d}" for day in range(1, count + 1)]


def _price_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    match = _PRICE_PATTERN.search(str(value))
    return int(match.group(0).replace(",", "")) if match else None


def _freshness_seconds(result: Dict[str, Any]) -> int:
    available = result.get("available")
    if available is True:
        return 20 * 60
    if available is False:
        return 60 * 60
    return 5 * 60


def record_day(
    cfg: AppConfig,
    hotel_code: str,
    provider: str,
    stay_date: str,
    checkout_date: str,
    result: HotelResult,
) -> None:
    date.fromisoformat(stay_date)
    date.fromisoformat(checkout_date)
    payload = asdict(result)
    payload["min_member_price"] = _price_int(result.min_member_price_text)
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO price_calendar_days(
                condition_key, hotel_code, provider, stay_date, checkout_date,
                observed_at, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(condition_key, hotel_code, stay_date) DO UPDATE SET
                provider=excluded.provider,
                checkout_date=excluded.checkout_date,
                observed_at=excluded.observed_at,
                result_json=excluded.result_json
            """,
            (
                condition_key(cfg), str(hotel_code), str(provider or "toyoko"),
                stay_date, checkout_date, now,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        connection.execute(
            """
            DELETE FROM price_calendar_days
            WHERE observed_at < ? OR stay_date < ?
            """,
            (now - 400 * 24 * 60 * 60, date.fromordinal(date.today().toordinal() - 45).isoformat()),
        )


def calendar_snapshot(cfg: AppConfig, hotel_code: str, month: str) -> Dict[str, Any]:
    all_dates = month_dates(month)
    start_date, end_date = all_dates[0], all_dates[-1]
    now = time.time()
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT provider, stay_date, checkout_date, observed_at, result_json
            FROM price_calendar_days
            WHERE condition_key=? AND hotel_code=? AND stay_date BETWEEN ? AND ?
            ORDER BY stay_date ASC
            """,
            (condition_key(cfg), str(hotel_code), start_date, end_date),
        ).fetchall()

    days: List[Dict[str, Any]] = []
    invalid_dates: List[str] = []
    for row in rows:
        observed_at = float(row["observed_at"])
        age = now - observed_at
        if age < -300:
            invalid_dates.append(str(row["stay_date"]))
            continue
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            invalid_dates.append(str(row["stay_date"]))
            continue
        age_sec = max(0, int(age))
        stale = age_sec >= _freshness_seconds(result)
        days.append({
            "date": str(row["stay_date"]),
            "checkout_date": str(row["checkout_date"]),
            "provider": str(row["provider"] or "toyoko"),
            "available": result.get("available"),
            "min_price": _price_int(result.get("min_price") or result.get("min_price_text")),
            "min_price_text": result.get("min_price_text"),
            "min_member_price": _price_int(
                result.get("min_member_price") or result.get("min_member_price_text")
            ),
            "min_member_price_text": result.get("min_member_price_text"),
            "room_type": result.get("min_price_room"),
            "remaining": result.get("min_remaining"),
            "url": result.get("url"),
            "checked_at": result.get("checked_at"),
            "error_summary": result.get("error_summary"),
            "from_cache": bool(result.get("from_cache")),
            "observed_at": observed_at,
            "age_sec": age_sec,
            "stale": stale,
        })

    if invalid_dates:
        with _LOCK, _connect() as connection:
            placeholders = ",".join("?" for _ in invalid_dates)
            connection.execute(
                f"DELETE FROM price_calendar_days WHERE condition_key=? AND hotel_code=? "
                f"AND stay_date IN ({placeholders})",
                (condition_key(cfg), str(hotel_code), *invalid_dates),
            )

    priced = [day for day in days if day["min_price"] is not None]
    fresh_days = [day for day in days if not day["stale"]]
    return {
        "month": month,
        "condition_key": condition_key(cfg),
        "days": days,
        "summary": {
            "loaded_days": len(days),
            "fresh_days": len(fresh_days),
            "stale_days": len(days) - len(fresh_days),
            "available_days": sum(day["available"] is True for day in days),
            "unavailable_days": sum(day["available"] is False for day in days),
            "unknown_days": sum(day["available"] is None for day in days),
            "lowest_price": min((day["min_price"] for day in priced), default=None),
            "lowest_member_price": min(
                (day["min_member_price"] for day in days if day["min_member_price"] is not None),
                default=None,
            ),
            "last_updated_at": max((day["observed_at"] for day in days), default=None),
        },
    }


def is_day_fresh(cfg: AppConfig, hotel_code: str, stay_date: str) -> bool:
    month = str(stay_date)[:7]
    snapshot = calendar_snapshot(cfg, hotel_code, month)
    return any(day["date"] == stay_date and not day["stale"] for day in snapshot["days"])
