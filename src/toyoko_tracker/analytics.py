from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .models import AppConfig, HotelResult
from .settings import HOTEL_DATABASE_PATH


_LOCK = threading.RLock()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH) or ".", exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS scan_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at REAL NOT NULL,
            scope_key TEXT NOT NULL,
            hotel_code TEXT NOT NULL,
            provider TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            available INTEGER,
            room_count INTEGER NOT NULL DEFAULT 0,
            min_price INTEGER,
            room_type TEXT NOT NULL DEFAULT '',
            engine TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'live'
        );
        CREATE INDEX IF NOT EXISTS idx_scan_observations_hotel_time
            ON scan_observations(hotel_code, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_scan_observations_scope_time
            ON scan_observations(scope_key, observed_at DESC);
        """
    )
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _scope_key(cfg: AppConfig) -> str:
    payload = {
        "start": cfg.start_date, "end": cfg.end_date,
        "people": cfg.people, "rooms": cfg.rooms,
        "smoking": cfg.smoking,
        "room": getattr(cfg, "room_requirement", getattr(cfg, "om_requirement", "any")),
        "membership": cfg.membership_status,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def scope_key_for_config(cfg: AppConfig) -> str:
    """Return the history scope used for one set of stay conditions."""
    return _scope_key(cfg)


def _room_count(result: HotelResult) -> int:
    if result.available is not True:
        return 0
    total = 0
    for offer in result.offers_display or []:
        match = re.search(r"\d+", str(offer.get("remaining_norm") or "").replace(",", ""))
        if match:
            total += int(match.group(0))
    if total:
        return total
    match = re.search(r"\d+", str(result.min_remaining or "").replace(",", ""))
    return int(match.group(0)) if match else 1


def _price(result: HotelResult) -> Optional[int]:
    if result.min_price is not None:
        return max(0, int(result.min_price))
    match = re.search(r"\d[\d,]*", str(result.min_price_text or ""))
    return int(match.group(0).replace(",", "")) if match else None


def record_results(cfg: AppConfig, results: Iterable[HotelResult], source: str = "live") -> int:
    now = time.time()
    scope = _scope_key(cfg)
    inserted = 0
    with _LOCK, _connect() as connection:
        for result in results:
            if result.from_cache and not result.cache_validated:
                continue
            available = None if result.available is None else int(bool(result.available))
            count = _room_count(result)
            price = _price(result)
            room_type = str(result.min_price_room or "")
            previous = connection.execute(
                """
                SELECT observed_at,available,room_count,min_price,room_type
                FROM scan_observations
                WHERE scope_key=? AND hotel_code=?
                ORDER BY observed_at DESC LIMIT 1
                """,
                (scope, result.code),
            ).fetchone()
            unchanged = bool(
                previous
                and previous["available"] == available
                and int(previous["room_count"] or 0) == count
                and previous["min_price"] == price
                and str(previous["room_type"] or "") == room_type
            )
            if unchanged and now - float(previous["observed_at"]) < 15 * 60:
                continue
            connection.execute(
                """
                INSERT INTO scan_observations(
                    observed_at,scope_key,hotel_code,provider,start_date,end_date,
                    available,room_count,min_price,room_type,engine,source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    now, scope, result.code, result.provider,
                    cfg.start_date, cfg.end_date, available, count, price,
                    room_type, str(result.engine_used or cfg.engine), str(source or "live"),
                ),
            )
            inserted += 1
        connection.execute(
            "DELETE FROM scan_observations WHERE observed_at<?", (now - 180 * 24 * 60 * 60,)
        )
    return inserted


def _prediction(rows: List[sqlite3.Row]) -> Dict[str, Any]:
    known = [row for row in rows if row["available"] is not None]
    if not known:
        return {"probability_percent": None, "confidence_percent": 0, "signal": "insufficient"}
    recent = known[-20:]
    weights = list(range(1, len(recent) + 1))
    weighted = sum(int(row["available"]) * weight for row, weight in zip(recent, weights))
    probability = weighted / max(1, sum(weights))
    transitions = sum(
        1 for left, right in zip(recent, recent[1:])
        if left["available"] != right["available"]
    )
    if recent[-1]["available"] == 1:
        probability = min(0.98, probability + 0.12)
    elif transitions:
        probability = min(0.95, probability + min(0.12, transitions * 0.02))
    confidence = min(95, 25 + len(known) * 3)
    signal = "likely" if probability >= 0.65 else "possible" if probability >= 0.3 else "unlikely"
    return {
        "probability_percent": int(round(probability * 100)),
        "confidence_percent": int(confidence),
        "signal": signal,
        "sample_count": len(known),
        "transition_count": transitions,
    }


def trend_snapshot(
    hotel_codes: Iterable[str],
    *,
    days: int = 30,
    limit: int = 3000,
    scope_key: Optional[str] = None,
) -> Dict[str, Any]:
    codes = [str(code) for code in dict.fromkeys(hotel_codes) if str(code)]
    if not codes:
        return {"points": [], "hotels": [], "days": days}
    days = max(1, min(180, int(days)))
    limit = max(1, min(10000, int(limit)))
    placeholders = ",".join("?" for _ in codes)
    conditions = [f"hotel_code IN ({placeholders})", "observed_at>=?"]
    params: List[Any] = [*codes, time.time() - days * 24 * 60 * 60]
    if scope_key:
        conditions.append("scope_key=?")
        params.append(str(scope_key))
    params.append(limit)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM scan_observations
            WHERE {' AND '.join(conditions)}
            ORDER BY observed_at ASC LIMIT ?
            """,
            params,
        ).fetchall()
    grouped: Dict[str, List[sqlite3.Row]] = defaultdict(list)
    points = []
    for row in rows:
        grouped[str(row["hotel_code"])].append(row)
        points.append({
            "ts": row["observed_at"], "code": row["hotel_code"],
            "provider": row["provider"], "available": (
                None if row["available"] is None else bool(row["available"])
            ),
            "room_count": int(row["room_count"] or 0),
            "price": row["min_price"], "room_type": row["room_type"],
        })
    hotels = []
    for code in codes:
        hotel_rows = grouped.get(code, [])
        known = [row for row in hotel_rows if row["available"] is not None]
        latest = hotel_rows[-1] if hotel_rows else None
        prices = [int(row["min_price"]) for row in hotel_rows if row["min_price"] is not None]
        available_checks = sum(int(row["available"]) for row in known)
        hotels.append({
            "code": code,
            "samples": len(hotel_rows),
            "known_samples": len(known),
            "available_checks": available_checks,
            "unavailable_checks": len(known) - available_checks,
            "unknown_checks": len(hotel_rows) - len(known),
            "availability_rate_percent": (
                int(round(available_checks * 100 / len(known)))
                if known else None
            ),
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "average_price": int(round(sum(prices) / len(prices))) if prices else None,
            "latest_price": prices[-1] if prices else None,
            "current_price": (
                int(latest["min_price"])
                if latest is not None and latest["min_price"] is not None else None
            ),
            "latest_available": (
                None if latest is None or latest["available"] is None
                else bool(latest["available"])
            ),
            "latest_room_count": int(latest["room_count"] or 0) if latest is not None else 0,
            "latest_room_type": str(latest["room_type"] or "") if latest is not None else "",
            "first_observed_at": float(hotel_rows[0]["observed_at"]) if hotel_rows else None,
            "latest_observed_at": float(latest["observed_at"]) if latest is not None else None,
            "prediction": _prediction(hotel_rows),
        })
    return {
        "points": points,
        "hotels": hotels,
        "days": days,
        "scope_filtered": bool(scope_key),
        "generated_at": time.time(),
    }


def analytics_status_snapshot() -> Dict[str, int]:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total, COUNT(DISTINCT hotel_code) AS hotels FROM scan_observations"
        ).fetchone()
    return {"observations": int(row["total"] or 0), "hotels": int(row["hotels"] or 0)}
