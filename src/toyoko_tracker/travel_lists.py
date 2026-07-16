from __future__ import annotations

import html
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from typing import Any, Dict, Iterator, List, Mapping, Optional

from .settings import HOTEL_DATABASE_PATH


_LOCK = threading.RLock()
RESOURCE_TYPES = frozenset({"task", "alert_rule", "comparison"})
STATUSES = frozenset({"planning", "booked", "completed", "archived"})
_SENSITIVE_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "smtp_pass",
    "bark_key",
    "sendkey",
    "chat_id",
)


class TravelListError(RuntimeError):
    """Base error for travel-list operations."""


class TravelListNotFoundError(TravelListError):
    """Raised when a travel list is missing."""


class TravelListConflictError(TravelListError):
    """Raised when an optimistic revision is stale."""


class TravelListValidationError(ValueError, TravelListError):
    """Raised when travel-list input is invalid."""


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
        CREATE TABLE IF NOT EXISTS travel_lists (
            list_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            budget_limit REAL,
            notes TEXT NOT NULL DEFAULT '',
            currency TEXT NOT NULL DEFAULT 'JPY',
            status TEXT NOT NULL DEFAULT 'planning',
            revision INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_travel_lists_updated
            ON travel_lists(updated_at DESC);

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
        CREATE INDEX IF NOT EXISTS idx_travel_list_hotels_order
            ON travel_list_hotels(list_id, priority DESC, sort_order, created_at);

        CREATE TABLE IF NOT EXISTS travel_list_links (
            list_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            PRIMARY KEY(list_id, resource_type, resource_id),
            FOREIGN KEY(list_id) REFERENCES travel_lists(list_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_travel_list_links_resource
            ON travel_list_links(resource_type, resource_id);
        """
    )
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(travel_lists)").fetchall()
    }
    additions = {
        "currency": "TEXT NOT NULL DEFAULT 'JPY'",
        "status": "TEXT NOT NULL DEFAULT 'planning'",
        "revision": "INTEGER NOT NULL DEFAULT 1",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(
                f"ALTER TABLE travel_lists ADD COLUMN {column} {definition}"
            )


def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise TravelListValidationError(f"value is not JSON serializable: {exc}") from exc


def _json_object(raw: Any) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any, label: str, limit: int, *, required: bool = False) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    if required and not cleaned:
        raise TravelListValidationError(f"{label} is required")
    return cleaned[:limit]


def _clean_dates(start_value: Any, end_value: Any) -> tuple[str, str]:
    start_text = str(start_value or "").strip()
    end_text = str(end_value or "").strip()
    if bool(start_text) != bool(end_text):
        raise TravelListValidationError("start_date and end_date must be set together")
    if not start_text:
        return "", ""
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except ValueError as exc:
        raise TravelListValidationError("dates must use YYYY-MM-DD") from exc
    if end <= start:
        raise TravelListValidationError("end_date must be after start_date")
    return start.isoformat(), end.isoformat()


def _clean_budget(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise TravelListValidationError("budget_limit must be a number")
    try:
        budget = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise TravelListValidationError("budget_limit must be a number") from exc
    if budget < 0 or budget > 1_000_000_000:
        raise TravelListValidationError("budget_limit is outside the supported range")
    return budget


def _select_list(connection: sqlite3.Connection, list_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM travel_lists WHERE list_id=?",
        (str(list_id),),
    ).fetchone()
    if row is None:
        raise TravelListNotFoundError(f"travel list not found: {list_id}")
    return row


def _hotel_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    metadata = _json_object(row["hotel_json"])
    return {
        "list_id": str(row["list_id"]),
        "hotel_code": str(row["hotel_code"]),
        "provider": str(row["provider"] or "toyoko"),
        "hotel": metadata,
        "display_code": str(metadata.get("display_code") or row["hotel_code"]),
        "name": str(
            metadata.get("name_primary")
            or metadata.get("name")
            or metadata.get("name_en")
            or row["hotel_code"]
        ),
        "priority": int(row["priority"]),
        "sort_order": int(row["sort_order"]),
        "notes": str(row["notes"] or ""),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def _link_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "list_id": str(row["list_id"]),
        "resource_type": str(row["resource_type"]),
        "resource_id": str(row["resource_id"]),
        "metadata": _json_object(row["metadata_json"]),
        "created_at": float(row["created_at"]),
    }


def _list_from_row(
    row: sqlite3.Row,
    *,
    hotels: Optional[List[Dict[str, Any]]] = None,
    links: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    budget = None if row["budget_limit"] is None else int(round(row["budget_limit"]))
    return {
        "list_id": str(row["list_id"]),
        "name": str(row["name"]),
        "start_date": str(row["start_date"] or ""),
        "end_date": str(row["end_date"] or ""),
        "budget_limit": budget,
        "notes": str(row["notes"] or ""),
        "currency": str(row["currency"] or "JPY"),
        "status": str(row["status"] or "planning"),
        "revision": int(row["revision"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
        "hotels": hotels or [],
        "links": links or [],
        "hotel_count": len(hotels or []),
        "link_count": len(links or []),
    }


def list_travel_lists() -> List[Dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM travel_lists ORDER BY updated_at DESC,name,list_id"
        ).fetchall()
        counts = {
            str(row["list_id"]): (int(row["hotels"]), int(row["links"]))
            for row in connection.execute(
                """
                SELECT l.list_id,
                       COUNT(DISTINCT h.hotel_code) AS hotels,
                       COUNT(DISTINCT k.resource_type || ':' || k.resource_id) AS links
                FROM travel_lists AS l
                LEFT JOIN travel_list_hotels AS h ON h.list_id=l.list_id
                LEFT JOIN travel_list_links AS k ON k.list_id=l.list_id
                GROUP BY l.list_id
                """
            ).fetchall()
        }
    output = []
    for row in rows:
        item = _list_from_row(row)
        item["hotel_count"], item["link_count"] = counts.get(item["list_id"], (0, 0))
        output.append(item)
    return output


def get_travel_list(list_id: str) -> Dict[str, Any]:
    with _LOCK, _connect() as connection:
        row = _select_list(connection, list_id)
        hotels = [
            _hotel_from_row(item)
            for item in connection.execute(
                """
                SELECT * FROM travel_list_hotels
                WHERE list_id=?
                ORDER BY priority DESC,sort_order,created_at,hotel_code
                """,
                (str(list_id),),
            ).fetchall()
        ]
        links = [
            _link_from_row(item)
            for item in connection.execute(
                """
                SELECT * FROM travel_list_links
                WHERE list_id=?
                ORDER BY resource_type,created_at,resource_id
                """,
                (str(list_id),),
            ).fetchall()
        ]
    return _list_from_row(row, hotels=hotels, links=links)


def create_travel_list(payload: Mapping[str, Any]) -> Dict[str, Any]:
    name = _clean_text(payload.get("name"), "name", 120, required=True)
    start_date, end_date = _clean_dates(
        payload.get("start_date"),
        payload.get("end_date"),
    )
    budget = _clean_budget(payload.get("budget_limit"))
    notes = str(payload.get("notes") or "")[:5000]
    currency = str(payload.get("currency") or "JPY").upper()
    if currency != "JPY":
        raise TravelListValidationError("currency must currently be JPY")
    status = str(payload.get("status") or "planning")
    if status not in STATUSES:
        raise TravelListValidationError("unsupported travel-list status")
    now = time.time()
    list_id = uuid.uuid4().hex
    with _LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO travel_lists(
                list_id,name,start_date,end_date,budget_limit,notes,
                currency,status,revision,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,1,?,?)
            """,
            (
                list_id,
                name,
                start_date,
                end_date,
                budget,
                notes,
                currency,
                status,
                now,
                now,
            ),
        )
    return get_travel_list(list_id)


def update_travel_list(
    list_id: str,
    payload: Mapping[str, Any],
    *,
    expected_revision: Optional[int] = None,
) -> Dict[str, Any]:
    current = get_travel_list(list_id)
    if expected_revision is not None and int(expected_revision) != current["revision"]:
        raise TravelListConflictError(
            f"travel-list revision conflict: expected {expected_revision}, "
            f"current {current['revision']}"
        )
    merged = {**current, **dict(payload)}
    name = _clean_text(merged.get("name"), "name", 120, required=True)
    start_date, end_date = _clean_dates(
        merged.get("start_date"),
        merged.get("end_date"),
    )
    budget = _clean_budget(merged.get("budget_limit"))
    notes = str(merged.get("notes") or "")[:5000]
    currency = str(merged.get("currency") or "JPY").upper()
    if currency != "JPY":
        raise TravelListValidationError("currency must currently be JPY")
    status = str(merged.get("status") or "planning")
    if status not in STATUSES:
        raise TravelListValidationError("unsupported travel-list status")
    now = time.time()
    with _LOCK, _connect() as connection:
        persisted = _select_list(connection, list_id)
        persisted_revision = int(persisted["revision"])
        if (
            expected_revision is not None
            and int(expected_revision) != persisted_revision
        ):
            raise TravelListConflictError(
                f"travel-list revision conflict: expected {expected_revision}, "
                f"current {persisted_revision}"
            )
        cursor = connection.execute(
            """
            UPDATE travel_lists
            SET name=?,start_date=?,end_date=?,budget_limit=?,notes=?,
                currency=?,status=?,revision=revision+1,updated_at=?
            WHERE list_id=? AND revision=?
            """,
            (
                name,
                start_date,
                end_date,
                budget,
                notes,
                currency,
                status,
                now,
                str(list_id),
                persisted_revision,
            ),
        )
        if not cursor.rowcount:
            latest = _select_list(connection, list_id)
            raise TravelListConflictError(
                f"travel-list revision conflict: expected {persisted_revision}, "
                f"current {int(latest['revision'])}"
            )
    return get_travel_list(list_id)


def delete_travel_list(list_id: str) -> None:
    with _LOCK, _connect() as connection:
        _select_list(connection, list_id)
        connection.execute("DELETE FROM travel_lists WHERE list_id=?", (str(list_id),))


def upsert_hotel(
    list_id: str,
    hotel_code: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    code = str(hotel_code or "").strip()
    if not code:
        raise TravelListValidationError("hotel_code is required")
    provider = str(
        payload.get("provider")
        or (code.split(":", 1)[0] if ":" in code else "toyoko")
    )[:50]
    priority = max(0, min(5, int(payload.get("priority", 0) or 0)))
    sort_order = max(0, min(100000, int(payload.get("sort_order", 0) or 0)))
    notes = str(payload.get("notes") or "")[:2000]
    hotel = payload.get("hotel", payload)
    if not isinstance(hotel, Mapping):
        raise TravelListValidationError("hotel must be an object")
    safe_hotel = {
        str(key): deepcopy(value)
        for key, value in hotel.items()
        if not any(fragment in str(key).lower() for fragment in _SENSITIVE_FRAGMENTS)
    }
    safe_hotel["code"] = code
    safe_hotel["provider"] = provider
    now = time.time()
    with _LOCK, _connect() as connection:
        _select_list(connection, list_id)
        connection.execute(
            """
            INSERT INTO travel_list_hotels(
                list_id,hotel_code,provider,hotel_json,priority,sort_order,
                notes,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(list_id,hotel_code) DO UPDATE SET
                provider=excluded.provider,hotel_json=excluded.hotel_json,
                priority=excluded.priority,sort_order=excluded.sort_order,
                notes=excluded.notes,updated_at=excluded.updated_at
            """,
            (
                str(list_id),
                code,
                provider,
                _json_dump(safe_hotel),
                priority,
                sort_order,
                notes,
                now,
                now,
            ),
        )
        connection.execute(
            "UPDATE travel_lists SET revision=revision+1,updated_at=? WHERE list_id=?",
            (now, str(list_id)),
        )
    return next(
        item
        for item in get_travel_list(list_id)["hotels"]
        if item["hotel_code"] == code
    )


def remove_hotel(list_id: str, hotel_code: str) -> None:
    now = time.time()
    with _LOCK, _connect() as connection:
        _select_list(connection, list_id)
        cursor = connection.execute(
            "DELETE FROM travel_list_hotels WHERE list_id=? AND hotel_code=?",
            (str(list_id), str(hotel_code)),
        )
        if not cursor.rowcount:
            raise TravelListNotFoundError(
                f"hotel is not in travel list: {hotel_code}"
            )
        connection.execute(
            "UPDATE travel_lists SET revision=revision+1,updated_at=? WHERE list_id=?",
            (now, str(list_id)),
        )


def link_resource(
    list_id: str,
    resource_type: str,
    resource_id: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    kind = str(resource_type or "")
    identifier = str(resource_id or "").strip()
    if kind not in RESOURCE_TYPES:
        raise TravelListValidationError("unsupported resource_type")
    if not identifier:
        raise TravelListValidationError("resource_id is required")
    safe_metadata = _redact(dict(metadata or {}))
    now = time.time()
    with _LOCK, _connect() as connection:
        _select_list(connection, list_id)
        connection.execute(
            """
            INSERT INTO travel_list_links(
                list_id,resource_type,resource_id,metadata_json,created_at
            ) VALUES (?,?,?,?,?)
            ON CONFLICT(list_id,resource_type,resource_id) DO UPDATE SET
                metadata_json=excluded.metadata_json
            """,
            (
                str(list_id),
                kind,
                identifier,
                _json_dump(safe_metadata),
                now,
            ),
        )
        connection.execute(
            "UPDATE travel_lists SET revision=revision+1,updated_at=? WHERE list_id=?",
            (now, str(list_id)),
        )
    return next(
        item
        for item in get_travel_list(list_id)["links"]
        if item["resource_type"] == kind and item["resource_id"] == identifier
    )


def unlink_resource(list_id: str, resource_type: str, resource_id: str) -> None:
    now = time.time()
    with _LOCK, _connect() as connection:
        _select_list(connection, list_id)
        cursor = connection.execute(
            """
            DELETE FROM travel_list_links
            WHERE list_id=? AND resource_type=? AND resource_id=?
            """,
            (str(list_id), str(resource_type), str(resource_id)),
        )
        if not cursor.rowcount:
            raise TravelListNotFoundError("travel-list resource link not found")
        connection.execute(
            "UPDATE travel_lists SET revision=revision+1,updated_at=? WHERE list_id=?",
            (now, str(list_id)),
        )


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _redact(item)
            for key, item in value.items()
            if not any(
                fragment in str(key).lower()
                for fragment in _SENSITIVE_FRAGMENTS
            )
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    return deepcopy(value)


def trip_summary_payload(
    travel_list: Mapping[str, Any],
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    safe_list = _redact(dict(travel_list))
    safe_context = _redact(dict(context or {}))
    estimated_total = safe_context.get("estimated_total")
    budget = safe_list.get("budget_limit")
    remaining = (
        int(budget) - int(estimated_total)
        if budget is not None and estimated_total is not None
        else None
    )
    return {
        "schema_version": 1,
        "generated_at": time.time(),
        "travel_list": safe_list,
        "decision_context": safe_context,
        "budget": {
            "currency": safe_list.get("currency") or "JPY",
            "limit": budget,
            "estimated_total": estimated_total,
            "remaining": remaining,
            "status": (
                "within_budget"
                if remaining is not None and remaining >= 0
                else "over_budget"
                if remaining is not None
                else "not_comparable"
            ),
        },
    }


def trip_summary_markdown(summary: Mapping[str, Any]) -> str:
    travel = summary.get("travel_list") or {}
    budget = summary.get("budget") or {}
    context = summary.get("decision_context") or {}
    lines = [
        f"# {travel.get('name') or 'Trip Summary'}",
        "",
        f"- Dates: {travel.get('start_date') or '—'} → {travel.get('end_date') or '—'}",
        f"- Status: {travel.get('status') or 'planning'}",
        f"- Budget: {budget.get('currency') or 'JPY'} "
        f"{budget.get('limit') if budget.get('limit') is not None else '—'}",
        f"- Estimated stay total: {budget.get('estimated_total') if budget.get('estimated_total') is not None else '—'}",
        f"- Budget result: {budget.get('status') or 'not_comparable'}",
        "",
        "## Hotels",
        "",
    ]
    hotels = travel.get("hotels") or []
    if hotels:
        for item in hotels:
            lines.append(
                f"- Priority {item.get('priority', 0)} — "
                f"{item.get('display_code') or item.get('hotel_code')} "
                f"{item.get('name') or ''}"
                + (f" — {item.get('notes')}" if item.get("notes") else "")
            )
    else:
        lines.append("- No hotels added")
    lines.extend(["", "## Linked resources", ""])
    links = travel.get("links") or []
    if links:
        for item in links:
            lines.append(
                f"- {item.get('resource_type')}: {item.get('resource_id')}"
            )
    else:
        lines.append("- No linked resources")
    plans = context.get("split_plans") or []
    lines.extend(["", "## Recommended stay plan", ""])
    if plans:
        best = plans[0]
        lines.append(
            f"- Total JPY {best.get('total_price')} · "
            f"{best.get('moves')} move(s) · score {best.get('score')}"
        )
        for segment in best.get("segments") or []:
            lines.append(
                f"  - {segment.get('checkin_date')} → {segment.get('checkout_date')}: "
                f"{segment.get('name') or segment.get('hotel_code')} "
                f"({segment.get('nights')} night(s), JPY {segment.get('subtotal')})"
            )
    else:
        lines.append("- No complete split-stay recommendation")
    price_stats = context.get("price_statistics") or []
    lines.extend(["", "## Price assessment", ""])
    if price_stats:
        for item in price_stats:
            lines.append(
                f"- {item.get('name') or item.get('hotel_code')}: "
                f"{(item.get('assessment') or {}).get('label', 'insufficient')} · "
                f"current JPY {item.get('current_price') if item.get('current_price') is not None else '—'} · "
                f"{item.get('sample_count', 0)} samples"
            )
    else:
        lines.append("- No historical price assessment")
    if travel.get("notes"):
        lines.extend(["", "## Notes", "", str(travel["notes"])])
    lines.extend([
        "",
        "_Price and availability conclusions use stored Provider observations and should be rechecked before booking._",
        "",
    ])
    return "\n".join(lines)


def trip_summary_html(summary: Mapping[str, Any]) -> str:
    markdown = trip_summary_markdown(summary)
    lines = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- ") or line.startswith("  - "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            content = line[2:] if line.startswith("- ") else line[4:]
            lines.append(f"<li>{html.escape(content)}</li>")
        elif line.startswith("_") and line.endswith("_"):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p><em>{html.escape(line.strip('_'))}</em></p>")
        elif line:
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        lines.append("</ul>")
    title = html.escape(str((summary.get("travel_list") or {}).get("name") or "Trip Summary"))
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{max-width:880px;margin:32px auto;padding:0 20px;"
        "font:15px/1.6 system-ui;color:#203047}h1,h2{color:#17365d}"
        "li{margin:4px 0}em{color:#667085}</style></head><body>"
        + "".join(lines)
        + "</body></html>"
    )
