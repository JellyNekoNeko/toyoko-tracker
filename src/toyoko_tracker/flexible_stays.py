from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence

from .models import HotelResult
from .settings import HOTEL_DATABASE_PATH


_LOCK = threading.RLock()
_PRICE_PATTERN = re.compile(r"\d[\d,]*")
JOB_STATES = frozenset({
    "queued",
    "running",
    "paused",
    "complete",
    "partial",
    "cancelled",
    "failed",
})
ACTIVE_JOB_STATES = frozenset({"queued", "running"})
TERMINAL_JOB_STATES = frozenset({"complete", "partial", "cancelled", "failed"})
SHORTCUTS = frozenset({"custom", "weekend", "next_30"})


class FlexibleStayError(RuntimeError):
    """Base error for flexible-stay searches."""


class FlexibleStayNotFoundError(FlexibleStayError):
    """Raised when a requested flexible-stay job does not exist."""


class FlexibleStayValidationError(ValueError, FlexibleStayError):
    """Raised when a flexible-stay request is invalid."""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH) or ".", exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
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
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise FlexibleStayValidationError(f"value is not JSON serializable: {exc}") from exc


def _json_value(raw: Any, fallback: Any) -> Any:
    try:
        value = json.loads(str(raw or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return deepcopy(fallback)
    return value


def _clean_codes(value: Any) -> List[str]:
    if not isinstance(value, list):
        raise FlexibleStayValidationError("hotel_codes must be a list")
    output: List[str] = []
    for raw in value:
        code = str(raw or "").strip()
        if code and code not in output:
            output.append(code)
    if not output:
        raise FlexibleStayValidationError("select at least one hotel")
    if len(output) > 50:
        raise FlexibleStayValidationError("a flexible search supports up to 50 hotels")
    return output


def generate_stay_windows(
    earliest_date: str,
    latest_date: str,
    nights: int,
    shortcut: str = "custom",
) -> List[Dict[str, Any]]:
    """Generate stable, unique check-in/check-out combinations.

    ``latest_date`` is the latest permitted checkout date. Weekend mode keeps
    Friday and Saturday check-ins, while next-30 uses the same deterministic
    expansion as a custom window after the UI applies its 30-day range.
    """
    try:
        earliest = date.fromisoformat(str(earliest_date or ""))
        latest = date.fromisoformat(str(latest_date or ""))
        stay_nights = int(nights)
    except (TypeError, ValueError) as exc:
        raise FlexibleStayValidationError(
            "earliest_date/latest_date must use YYYY-MM-DD and nights must be an integer"
        ) from exc
    mode = str(shortcut or "custom")
    if mode not in SHORTCUTS:
        raise FlexibleStayValidationError("shortcut must be custom, weekend, or next_30")
    if stay_nights < 1 or stay_nights > 14:
        raise FlexibleStayValidationError("nights must be between 1 and 14")
    if latest <= earliest:
        raise FlexibleStayValidationError("latest_date must be after earliest_date")
    if (latest - earliest).days > 90:
        raise FlexibleStayValidationError("date window must be 90 days or less")
    if earliest + timedelta(days=stay_nights) > latest:
        raise FlexibleStayValidationError("date window is shorter than the requested stay")

    windows: List[Dict[str, Any]] = []
    current = earliest
    while current + timedelta(days=stay_nights) <= latest:
        checkout = current + timedelta(days=stay_nights)
        if mode != "weekend" or current.weekday() in {4, 5}:
            windows.append({
                "key": f"{current.isoformat()}:{checkout.isoformat()}",
                "checkin_date": current.isoformat(),
                "checkout_date": checkout.isoformat(),
                "nights": stay_nights,
                "weekend": current.weekday() in {4, 5},
            })
        current += timedelta(days=1)
    if not windows:
        raise FlexibleStayValidationError("the selected window has no matching stay combination")
    return windows


def required_stay_dates(windows: Sequence[Mapping[str, Any]]) -> List[str]:
    values = set()
    for window in windows:
        start = date.fromisoformat(str(window["checkin_date"]))
        nights = int(window["nights"])
        for offset in range(nights):
            values.add((start + timedelta(days=offset)).isoformat())
    return sorted(values)


def normalize_request(payload: Mapping[str, Any]) -> Dict[str, Any]:
    earliest = str(payload.get("earliest_date") or "")
    latest = str(payload.get("latest_date") or "")
    try:
        nights = int(payload.get("nights", 1))
    except (TypeError, ValueError) as exc:
        raise FlexibleStayValidationError("nights must be an integer") from exc
    shortcut = str(payload.get("shortcut") or "custom")
    windows = generate_stay_windows(earliest, latest, nights, shortcut)
    hotel_codes = _clean_codes(payload.get("hotel_codes"))

    selected = payload.get("selected_hotels")
    if not isinstance(selected, list):
        selected = []
    by_code = {
        str(item.get("code") or ""): deepcopy(dict(item))
        for item in selected
        if isinstance(item, Mapping) and str(item.get("code") or "") in hotel_codes
    }
    hotels = []
    for code in hotel_codes:
        hotel = by_code.get(code, {"code": code})
        hotel["code"] = code
        hotel["provider"] = str(
            hotel.get("provider")
            or (code.split(":", 1)[0] if ":" in code else "toyoko")
        )
        hotels.append(hotel)

    conditions = payload.get("conditions")
    if not isinstance(conditions, Mapping):
        conditions = {}
    conditions = {
        "people": max(1, min(5, int(conditions.get("people", 1) or 1))),
        "rooms": max(1, min(9, int(conditions.get("rooms", 1) or 1))),
        "smoking": str(conditions.get("smoking") or "all"),
        "room_requirement": str(conditions.get("room_requirement") or "any"),
        "membership_status": str(conditions.get("membership_status") or "member"),
    }
    return {
        "task_id": str(payload.get("task_id") or ""),
        "name": " ".join(str(payload.get("name") or "").split())[:120],
        "earliest_date": earliest,
        "latest_date": latest,
        "nights": nights,
        "shortcut": shortcut,
        "hotel_codes": hotel_codes,
        "hotels": hotels,
        "conditions": conditions,
        "windows": windows,
        "stay_dates": required_stay_dates(windows),
    }


def _job_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    hotels = _json_value(row["hotels_json"], [])
    codes = _json_value(row["hotel_codes_json"], [])
    conditions = _json_value(row["conditions_json"], {})
    windows = generate_stay_windows(
        str(row["earliest_date"]),
        str(row["latest_date"]),
        int(row["nights"]),
        str(row["shortcut"]),
    )
    total = int(row["total_work"])
    done = int(row["completed_work"])
    return {
        "job_id": str(row["job_id"]),
        "task_id": str(row["task_id"] or ""),
        "name": str(row["name"] or ""),
        "earliest_date": str(row["earliest_date"]),
        "latest_date": str(row["latest_date"]),
        "nights": int(row["nights"]),
        "shortcut": str(row["shortcut"]),
        "status": str(row["status"]),
        "running": str(row["status"]) in ACTIVE_JOB_STATES,
        "hotel_codes": codes if isinstance(codes, list) else [],
        "hotels": hotels if isinstance(hotels, list) else [],
        "conditions": conditions if isinstance(conditions, dict) else {},
        "windows": windows,
        "total_work": total,
        "completed_work": done,
        "progress_percent": int(round(done * 100 / total)) if total else 0,
        "error_count": int(row["error_count"]),
        "current_hotel": str(row["current_hotel"] or ""),
        "current_date": str(row["current_date"] or ""),
        "last_error": str(row["last_error"] or ""),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "capabilities": {
            "currency": "JPY",
            "tax_basis": "provider_display",
            "stay_evidence": "nightly_composite",
            "provider_verified_full_stay": False,
        },
    }


def create_job(payload: Mapping[str, Any]) -> Dict[str, Any]:
    request_data = normalize_request(payload)
    now = time.time()
    job_id = uuid.uuid4().hex
    total_work = len(request_data["hotel_codes"]) * len(request_data["stay_dates"])
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            DELETE FROM flexible_stay_jobs
            WHERE status IN ('complete','partial','cancelled','failed')
              AND updated_at < ?
            """,
            (now - 180 * 24 * 60 * 60,),
        )
        connection.execute(
            """
            INSERT INTO flexible_stay_jobs(
                job_id, task_id, name, earliest_date, latest_date, nights,
                shortcut, status, hotel_codes_json, hotels_json, conditions_json,
                total_work, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                request_data["task_id"],
                request_data["name"],
                request_data["earliest_date"],
                request_data["latest_date"],
                request_data["nights"],
                request_data["shortcut"],
                _json_dump(request_data["hotel_codes"]),
                _json_dump(request_data["hotels"]),
                _json_dump(request_data["conditions"]),
                total_work,
                now,
                now,
            ),
        )
    return get_job(job_id)


def _select_job(connection: sqlite3.Connection, job_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM flexible_stay_jobs WHERE job_id=?",
        (str(job_id),),
    ).fetchone()
    if row is None:
        raise FlexibleStayNotFoundError(f"flexible-stay job not found: {job_id}")
    return row


def get_job(job_id: str) -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        return _job_from_row(_select_job(connection, job_id))


def list_jobs(task_id: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(100, int(limit)))
    with _LOCK, _connect() as connection:
        if task_id:
            rows = connection.execute(
                """
                SELECT * FROM flexible_stay_jobs
                WHERE task_id=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (str(task_id), safe_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM flexible_stay_jobs ORDER BY created_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
    return [_job_from_row(row) for row in rows]


def set_job_state(
    job_id: str,
    status: str,
    *,
    last_error: Optional[str] = None,
) -> Dict[str, Any]:
    state = str(status)
    if state not in JOB_STATES:
        raise FlexibleStayValidationError(f"unsupported job state: {state}")
    now = time.time()
    with _LOCK, _connect() as connection:
        row = _select_job(connection, job_id)
        started_at = row["started_at"]
        if state == "running" and started_at is None:
            started_at = now
        completed_at = now if state in TERMINAL_JOB_STATES else None
        connection.execute(
            """
            UPDATE flexible_stay_jobs
            SET status=?, updated_at=?, started_at=?, completed_at=?,
                current_hotel=CASE WHEN ? IN ('queued','running') THEN current_hotel ELSE '' END,
                current_date=CASE WHEN ? IN ('queued','running') THEN current_date ELSE '' END,
                last_error=COALESCE(?, last_error)
            WHERE job_id=?
            """,
            (
                state,
                now,
                started_at,
                completed_at,
                state,
                state,
                None if last_error is None else " ".join(str(last_error).split())[:240],
                str(job_id),
            ),
        )
    return get_job(job_id)


def update_job_progress(
    job_id: str,
    *,
    current_hotel: str = "",
    current_date: str = "",
    error: str = "",
) -> Dict[str, Any]:
    now = time.time()
    with _LOCK, _connect() as connection:
        _select_job(connection, job_id)
        completed = int(connection.execute(
            """
            SELECT COUNT(*) FROM flexible_stay_nights
            WHERE job_id=? AND state IN ('available','unavailable')
            """,
            (str(job_id),),
        ).fetchone()[0])
        connection.execute(
            """
            UPDATE flexible_stay_jobs
            SET completed_work=?, current_hotel=?, current_date=?, updated_at=?,
                error_count=error_count+?, last_error=CASE WHEN ?='' THEN last_error ELSE ? END
            WHERE job_id=?
            """,
            (
                completed,
                str(current_hotel or ""),
                str(current_date or ""),
                now,
                1 if error else 0,
                str(error or ""),
                " ".join(str(error or "").split())[:240],
                str(job_id),
            ),
        )
    return get_job(job_id)


def delete_job(job_id: str) -> None:
    with _LOCK, _connect() as connection:
        _select_job(connection, job_id)
        connection.execute("DELETE FROM flexible_stay_jobs WHERE job_id=?", (str(job_id),))


def recover_active_jobs() -> int:
    """Turn process-local active states into resumable paused jobs after restart."""
    now = time.time()
    with _LOCK, _connect() as connection:
        cursor = connection.execute(
            """
            UPDATE flexible_stay_jobs
            SET status='paused', updated_at=?, current_hotel='', current_date='',
                last_error=CASE WHEN last_error='' THEN 'interrupted; ready to resume' ELSE last_error END
            WHERE status IN ('queued','running')
            """,
            (now,),
        )
        return int(cursor.rowcount or 0)


def pending_work(job_id: str) -> List[Dict[str, str]]:
    job = get_job(job_id)
    dates = required_stay_dates(job["windows"])
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT hotel_code, stay_date
            FROM flexible_stay_nights
            WHERE job_id=? AND state IN ('available','unavailable')
            """,
            (str(job_id),),
        ).fetchall()
    completed = {(str(row["hotel_code"]), str(row["stay_date"])) for row in rows}
    providers = {
        str(item.get("code") or ""): str(item.get("provider") or "toyoko")
        for item in job["hotels"]
        if isinstance(item, Mapping)
    }
    return [
        {
            "hotel_code": code,
            "provider": providers.get(code) or (code.split(":", 1)[0] if ":" in code else "toyoko"),
            "stay_date": stay_date,
            "checkout_date": (date.fromisoformat(stay_date) + timedelta(days=1)).isoformat(),
        }
        for code in job["hotel_codes"]
        for stay_date in dates
        if (code, stay_date) not in completed
    ]


def record_night(
    job_id: str,
    hotel_code: str,
    provider: str,
    stay_date: str,
    checkout_date: str,
    result: HotelResult | Mapping[str, Any],
) -> None:
    date.fromisoformat(stay_date)
    date.fromisoformat(checkout_date)
    payload = asdict(result) if isinstance(result, HotelResult) else deepcopy(dict(result))
    available = payload.get("available")
    state = "available" if available is True else "unavailable" if available is False else "unknown"
    now = time.time()
    with _LOCK, _connect() as connection:
        _select_job(connection, job_id)
        connection.execute(
            """
            INSERT INTO flexible_stay_nights(
                job_id, hotel_code, provider, stay_date, checkout_date,
                state, observed_at, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, hotel_code, stay_date) DO UPDATE SET
                provider=excluded.provider,
                checkout_date=excluded.checkout_date,
                state=excluded.state,
                observed_at=excluded.observed_at,
                result_json=excluded.result_json
            """,
            (
                str(job_id),
                str(hotel_code),
                str(provider or "toyoko"),
                stay_date,
                checkout_date,
                state,
                now,
                _json_dump(payload),
            ),
        )


def list_nights(job_id: str) -> List[Dict[str, Any]]:
    get_job(job_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT hotel_code, provider, stay_date, checkout_date, state,
                   observed_at, result_json
            FROM flexible_stay_nights
            WHERE job_id=?
            ORDER BY stay_date, hotel_code
            """,
            (str(job_id),),
        ).fetchall()
    output = []
    for row in rows:
        result = _json_value(row["result_json"], {})
        output.append({
            "hotel_code": str(row["hotel_code"]),
            "provider": str(row["provider"]),
            "stay_date": str(row["stay_date"]),
            "checkout_date": str(row["checkout_date"]),
            "state": str(row["state"]),
            "observed_at": float(row["observed_at"]),
            "result": result if isinstance(result, dict) else {},
        })
    return output


def _price_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, int(value))
    match = _PRICE_PATTERN.search(str(value))
    return int(match.group(0).replace(",", "")) if match else None


def _normalized_room(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _night_room_prices(result: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    offers = result.get("offers_display")
    if isinstance(offers, list):
        for offer in offers:
            if not isinstance(offer, Mapping):
                continue
            title = str(
                offer.get("room_title_primary")
                or offer.get("room_title")
                or ""
            ).strip()
            key = _normalized_room(title)
            price = _price_int(offer.get("price_val") or offer.get("price_text"))
            member = _price_int(
                offer.get("member_price_val") or offer.get("member_price_text")
            )
            if not key or price is None:
                continue
            previous = output.get(key)
            if previous is None or price < int(previous["price"]):
                output[key] = {
                    "title": title,
                    "price": price,
                    "member_price": member,
                }
    fallback_price = _price_int(result.get("min_price") or result.get("min_price_text"))
    fallback_title = str(result.get("min_price_room") or "").strip()
    if fallback_price is not None and fallback_title:
        key = _normalized_room(fallback_title)
        output.setdefault(key, {
            "title": fallback_title,
            "price": fallback_price,
            "member_price": _price_int(
                result.get("min_member_price") or result.get("min_member_price_text")
            ),
        })
    return output


def evaluate_continuous_stay(
    hotel_code: str,
    window: Mapping[str, Any],
    nightly_evidence: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Evaluate full-stay availability and quote totals from nightly evidence."""
    expected_dates = [
        (date.fromisoformat(str(window["checkin_date"])) + timedelta(days=offset)).isoformat()
        for offset in range(int(window["nights"]))
    ]
    evidence_by_date = {
        str(item.get("stay_date") or ""): item
        for item in nightly_evidence
        if str(item.get("stay_date") or "")
    }
    nights: List[Dict[str, Any]] = []
    for stay_date in expected_dates:
        row = evidence_by_date.get(stay_date)
        if row is None:
            nights.append({
                "stay_date": stay_date,
                "state": "missing",
                "available": None,
                "price": None,
                "member_price": None,
                "room_type": "",
                "url": "",
                "error": "nightly evidence is missing",
            })
            continue
        result = row.get("result") if isinstance(row.get("result"), Mapping) else row
        available = result.get("available")
        nights.append({
            "stay_date": stay_date,
            "state": "available" if available is True else "unavailable" if available is False else "unknown",
            "available": available,
            "price": _price_int(result.get("min_price") or result.get("min_price_text")),
            "member_price": _price_int(
                result.get("min_member_price") or result.get("min_member_price_text")
            ),
            "room_type": str(result.get("min_price_room") or ""),
            "url": str(result.get("url") or ""),
            "error": str(result.get("error_summary") or ""),
            "rooms": _night_room_prices(result),
            "observed_at": row.get("observed_at"),
        })

    if any(night["state"] == "missing" for night in nights):
        state = "incomplete"
    elif any(night["available"] is False for night in nights):
        state = "unavailable"
    elif any(night["available"] is not True for night in nights):
        state = "unknown"
    else:
        state = "available"

    room_sets = [set(night["rooms"]) for night in nights if night["available"] is True]
    common_rooms = set.intersection(*room_sets) if room_sets and len(room_sets) == len(nights) else set()
    selected_room = ""
    room_continuity = "not_applicable"
    total_price: Optional[int] = None
    member_total_price: Optional[int] = None
    room_sequence: List[str] = []

    if state == "available":
        if common_rooms:
            selected_key = min(
                common_rooms,
                key=lambda key: (
                    sum(int(night["rooms"][key]["price"]) for night in nights),
                    key,
                ),
            )
            selected_room = str(nights[0]["rooms"][selected_key]["title"])
            room_sequence = [
                str(night["rooms"][selected_key]["title"]) for night in nights
            ]
            total_price = sum(
                int(night["rooms"][selected_key]["price"]) for night in nights
            )
            member_values = [
                night["rooms"][selected_key].get("member_price") for night in nights
            ]
            if all(value is not None for value in member_values):
                member_total_price = sum(int(value) for value in member_values)
            room_continuity = "same_room"
        else:
            room_sequence = [
                str(night["room_type"] or next(iter(night["rooms"].values()), {}).get("title") or "")
                for night in nights
            ]
            prices = [night["price"] for night in nights]
            members = [night["member_price"] for night in nights]
            if all(value is not None for value in prices):
                total_price = sum(int(value) for value in prices)
            if all(value is not None for value in members):
                member_total_price = sum(int(value) for value in members)
            room_continuity = "room_change_required"
    elif state == "incomplete":
        room_continuity = "insufficient_evidence"
    elif state == "unknown":
        room_continuity = "provider_unknown"
    elif state == "unavailable":
        room_continuity = "stay_unavailable"

    for night in nights:
        night.pop("rooms", None)
    night_count = int(window["nights"])
    return {
        "hotel_code": str(hotel_code),
        "window_key": str(window.get("key") or ""),
        "checkin_date": str(window["checkin_date"]),
        "checkout_date": str(window["checkout_date"]),
        "nights": night_count,
        "state": state,
        "full_stay_available": state == "available",
        "isolated_available_nights": sum(night["available"] is True for night in nights),
        "missing_evidence_nights": sum(night["state"] == "missing" for night in nights),
        "unknown_nights": sum(night["state"] == "unknown" for night in nights),
        "unavailable_nights": sum(night["state"] == "unavailable" for night in nights),
        "missing_price_nights": sum(
            night["available"] is True and night["price"] is None for night in nights
        ),
        "total_price": total_price,
        "average_nightly_price": (
            round(total_price / night_count, 2) if total_price is not None else None
        ),
        "member_total_price": member_total_price,
        "member_average_nightly_price": (
            round(member_total_price / night_count, 2)
            if member_total_price is not None
            else None
        ),
        "room_continuity": room_continuity,
        "selected_room": selected_room,
        "room_sequence": room_sequence,
        "evidence_type": "nightly_composite",
        "provider_verified_full_stay": False,
        "currency": "JPY",
        "tax_basis": "provider_display",
        "nightly": nights,
    }


def recompute_results(job_id: str) -> List[Dict[str, Any]]:
    job = get_job(job_id)
    nights = list_nights(job_id)
    by_hotel: Dict[str, List[Dict[str, Any]]] = {}
    for night in nights:
        by_hotel.setdefault(str(night["hotel_code"]), []).append(night)
    results = [
        evaluate_continuous_stay(
            hotel_code,
            window,
            by_hotel.get(hotel_code, []),
        )
        for hotel_code in job["hotel_codes"]
        for window in job["windows"]
    ]
    now = time.time()
    with _LOCK, _connect() as connection:
        connection.execute("DELETE FROM flexible_stay_results WHERE job_id=?", (str(job_id),))
        connection.executemany(
            """
            INSERT INTO flexible_stay_results(
                job_id, hotel_code, checkin_date, checkout_date, nights,
                state, total_price, member_total_price, result_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(job_id),
                    result["hotel_code"],
                    result["checkin_date"],
                    result["checkout_date"],
                    result["nights"],
                    result["state"],
                    result["total_price"],
                    result["member_total_price"],
                    _json_dump(result),
                    now,
                )
                for result in results
            ],
        )
    return results


def list_results(job_id: str) -> List[Dict[str, Any]]:
    get_job(job_id)
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT result_json FROM flexible_stay_results
            WHERE job_id=?
            ORDER BY checkin_date, hotel_code
            """,
            (str(job_id),),
        ).fetchall()
    results = [_json_value(row["result_json"], {}) for row in rows]
    return [result for result in results if isinstance(result, dict)]


def comparison_snapshot(job_id: str) -> Dict[str, Any]:
    job = get_job(job_id)
    results = list_results(job_id)
    if not results and job["completed_work"]:
        results = recompute_results(job_id)
    result_by_key = {
        (str(result["hotel_code"]), str(result["window_key"])): result
        for result in results
    }
    hotel_meta = {
        str(item.get("code") or ""): item
        for item in job["hotels"]
        if isinstance(item, Mapping)
    }
    prefer_member = job["conditions"].get("membership_status") == "member"
    columns = deepcopy(job["windows"])
    minima: Dict[str, Dict[str, Any]] = {}
    heat_by_cell: Dict[tuple[str, str], int] = {}
    for window in columns:
        key = str(window["key"])
        priced = []
        for code in job["hotel_codes"]:
            result = result_by_key.get((code, key), {})
            value = (
                result.get("member_total_price")
                if prefer_member and result.get("member_total_price") is not None
                else result.get("total_price")
            )
            if result.get("state") == "available" and value is not None:
                priced.append((code, int(value)))
        if priced:
            minimum = min(value for _code, value in priced)
            maximum = max(value for _code, value in priced)
            cheapest = [code for code, value in priced if value == minimum]
            minima[str(window["checkin_date"])] = {
                "window_key": key,
                "price": minimum,
                "hotel_codes": cheapest,
                "currency": "JPY",
            }
            for code, value in priced:
                level = 1 if maximum == minimum else 1 + int(round((value - minimum) * 4 / (maximum - minimum)))
                heat_by_cell[(code, key)] = max(1, min(5, level))

    rows = []
    for code in job["hotel_codes"]:
        meta = hotel_meta.get(code, {})
        cells = []
        for window in columns:
            key = str(window["key"])
            result = result_by_key.get((code, key))
            if result is None:
                cells.append({
                    "window_key": key,
                    "state": "not_evaluated",
                    "price": None,
                    "heat_level": 0,
                    "daily_cheapest": False,
                })
                continue
            price = (
                result.get("member_total_price")
                if prefer_member and result.get("member_total_price") is not None
                else result.get("total_price")
            )
            cheapest = code in minima.get(str(window["checkin_date"]), {}).get("hotel_codes", [])
            cells.append({
                "window_key": key,
                "state": result.get("state"),
                "price": price,
                "regular_total_price": result.get("total_price"),
                "member_total_price": result.get("member_total_price"),
                "average_nightly_price": (
                    result.get("member_average_nightly_price")
                    if prefer_member and result.get("member_total_price") is not None
                    else result.get("average_nightly_price")
                ),
                "heat_level": heat_by_cell.get((code, key), 0),
                "daily_cheapest": cheapest,
                "room_continuity": result.get("room_continuity"),
                "selected_room": result.get("selected_room"),
                "missing_price_nights": result.get("missing_price_nights"),
                "isolated_available_nights": result.get("isolated_available_nights"),
                "nights": result.get("nights"),
                "nightly": result.get("nightly"),
            })
        rows.append({
            "hotel_code": code,
            "display_code": str(meta.get("display_code") or code),
            "provider": str(meta.get("provider") or (code.split(":", 1)[0] if ":" in code else "toyoko")),
            "name": str(
                meta.get("name_primary")
                or meta.get("name")
                or meta.get("name_en")
                or meta.get("name_zh_cn")
                or code
            ),
            "cells": cells,
        })

    nights = list_nights(job_id)
    nightly_minima: Dict[str, Dict[str, Any]] = {}
    for stay_date in sorted({str(item["stay_date"]) for item in nights}):
        candidates = []
        for item in nights:
            if item["stay_date"] != stay_date:
                continue
            result = item["result"]
            value = _price_int(
                (
                    result.get("min_member_price")
                    or result.get("min_member_price_text")
                )
                if prefer_member
                else (result.get("min_price") or result.get("min_price_text"))
            )
            if result.get("available") is True and value is not None:
                candidates.append((str(item["hotel_code"]), value))
        if candidates:
            minimum = min(value for _code, value in candidates)
            nightly_minima[stay_date] = {
                "price": minimum,
                "hotel_codes": [
                    code for code, value in candidates if value == minimum
                ],
                "currency": "JPY",
            }

    available_cells = sum(
        cell["state"] == "available"
        for row in rows
        for cell in row["cells"]
    )
    missing_cells = sum(
        cell["state"] in {"not_evaluated", "incomplete", "unknown"}
        or (cell["state"] == "available" and cell.get("price") is None)
        for row in rows
        for cell in row["cells"]
    )
    return {
        "job": job,
        "columns": columns,
        "rows": rows,
        "daily_minima": minima,
        "nightly_minima": nightly_minima,
        "summary": {
            "hotel_count": len(rows),
            "combination_count": len(columns),
            "available_stays": available_cells,
            "missing_or_unknown": missing_cells,
            "lowest_total_price": min(
                (item["price"] for item in minima.values()),
                default=None,
            ),
        },
        "limitations": [
            "Full-stay status is a composite of one-night provider observations.",
            "A room change is reported when no normalized room type spans every night.",
            "Currency and tax basis follow the provider display; missing prices stay explicit.",
        ],
    }
