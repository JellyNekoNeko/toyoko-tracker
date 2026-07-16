from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, timedelta
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .settings import HOTEL_DATABASE_PATH


_PRICE_RE = re.compile(r"\d[\d,]*")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(HOTEL_DATABASE_PATH) or ".", exist_ok=True)
    connection = sqlite3.connect(HOTEL_DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    try:
        yield connection
    finally:
        connection.close()


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _price_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, int(value))
    match = _PRICE_RE.search(str(value))
    return int(match.group(0).replace(",", "")) if match else None


def percentile(values: Sequence[int], fraction: float) -> Optional[float]:
    """Return a deterministic R-7 interpolated percentile."""
    if not values:
        return None
    ordered = sorted(int(value) for value in values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = max(0.0, min(1.0, float(fraction))) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _rounded(value: Optional[float]) -> Optional[int]:
    return int(round(value)) if value is not None else None


def assess_price(
    current_price: Optional[int],
    values: Sequence[int],
) -> Dict[str, Any]:
    ordered = sorted(int(value) for value in values if value is not None)
    sample_count = len(ordered)
    p25 = percentile(ordered, 0.25)
    p75 = percentile(ordered, 0.75)
    if current_price is None:
        return {
            "label": "no_current_price",
            "position_percentile": None,
            "explanation": "No current price is available for comparison.",
        }
    if sample_count < 4:
        return {
            "label": "insufficient",
            "position_percentile": None,
            "explanation": (
                f"Only {sample_count} historical price sample(s) are available; "
                "at least 4 are required for a low/normal/high label."
            ),
        }
    below_or_equal = sum(value <= int(current_price) for value in ordered)
    position = int(round(below_or_equal * 100 / sample_count))
    if p25 is not None and p75 is not None and p25 < p75:
        label = (
            "low"
            if int(current_price) <= p25
            else "high"
            if int(current_price) >= p75
            else "normal"
        )
    else:
        median = percentile(ordered, 0.5) or float(current_price)
        tolerance = max(1.0, median * 0.05)
        label = (
            "low"
            if int(current_price) < median - tolerance
            else "high"
            if int(current_price) > median + tolerance
            else "normal"
        )
    return {
        "label": label,
        "position_percentile": position,
        "explanation": (
            f"Current JPY {int(current_price):,} is at approximately the "
            f"{position}th percentile of {sample_count} retained samples; "
            f"the low/high boundaries are P25 JPY {_rounded(p25):,} and "
            f"P75 JPY {_rounded(p75):,}."
        ),
    }


def _condition_matches(raw: Any, expected: Optional[Mapping[str, Any]]) -> bool:
    if not expected:
        return True
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(value, dict):
        return False
    return all(value.get(key) == expected.get(key) for key in expected)


def _historical_rows(
    hotel_codes: Sequence[str],
    *,
    days: int,
    scope_key: str = "",
    condition_key: str = "",
    conditions: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    codes = [str(code) for code in dict.fromkeys(hotel_codes) if str(code)]
    if not codes:
        return []
    cutoff = time.time() - max(1, min(730, int(days))) * 24 * 60 * 60
    placeholders = ",".join("?" for _ in codes)
    output: List[Dict[str, Any]] = []
    with _connect() as connection:
        if _table_exists(connection, "scan_observations"):
            clauses = [
                f"hotel_code IN ({placeholders})",
                "observed_at>=?",
                "min_price IS NOT NULL",
            ]
            params: List[Any] = [*codes, cutoff]
            if scope_key:
                clauses.append("scope_key=?")
                params.append(str(scope_key))
            rows = connection.execute(
                f"""
                SELECT observed_at,hotel_code,start_date,end_date,min_price
                FROM scan_observations
                WHERE {' AND '.join(clauses)}
                ORDER BY observed_at ASC
                """,
                params,
            ).fetchall()
            output.extend({
                "observed_at": float(row["observed_at"]),
                "hotel_code": str(row["hotel_code"]),
                "stay_date": str(row["start_date"] or ""),
                "checkout_date": str(row["end_date"] or ""),
                "price": int(row["min_price"]),
                "source": "scan_observation",
            } for row in rows)

        if _table_exists(connection, "price_calendar_days"):
            clauses = [
                f"hotel_code IN ({placeholders})",
                "observed_at>=?",
            ]
            params = [*codes, cutoff]
            if condition_key:
                clauses.append("condition_key=?")
                params.append(str(condition_key))
            rows = connection.execute(
                f"""
                SELECT observed_at,hotel_code,stay_date,checkout_date,result_json
                FROM price_calendar_days
                WHERE {' AND '.join(clauses)}
                ORDER BY observed_at ASC
                """,
                params,
            ).fetchall()
            for row in rows:
                try:
                    result = json.loads(str(row["result_json"] or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                price = _price_int(
                    result.get("min_price") or result.get("min_price_text")
                )
                if price is not None:
                    output.append({
                        "observed_at": float(row["observed_at"]),
                        "hotel_code": str(row["hotel_code"]),
                        "stay_date": str(row["stay_date"] or ""),
                        "checkout_date": str(row["checkout_date"] or ""),
                        "price": price,
                        "source": "price_calendar",
                    })

        if (
            _table_exists(connection, "flexible_stay_nights")
            and _table_exists(connection, "flexible_stay_jobs")
        ):
            rows = connection.execute(
                f"""
                SELECT n.observed_at,n.hotel_code,n.stay_date,n.checkout_date,
                       n.result_json,j.conditions_json
                FROM flexible_stay_nights AS n
                JOIN flexible_stay_jobs AS j ON j.job_id=n.job_id
                WHERE n.hotel_code IN ({placeholders}) AND n.observed_at>=?
                ORDER BY n.observed_at ASC
                """,
                [*codes, cutoff],
            ).fetchall()
            for row in rows:
                if not _condition_matches(row["conditions_json"], conditions):
                    continue
                try:
                    result = json.loads(str(row["result_json"] or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                price = _price_int(
                    result.get("min_price") or result.get("min_price_text")
                )
                if price is not None:
                    output.append({
                        "observed_at": float(row["observed_at"]),
                        "hotel_code": str(row["hotel_code"]),
                        "stay_date": str(row["stay_date"] or ""),
                        "checkout_date": str(row["checkout_date"] or ""),
                        "price": price,
                        "source": "flexible_stay",
                    })

    # One live check can be mirrored into several stores. Prefer the first
    # sample and collapse equal hotel/date/price values observed within 60 s.
    output.sort(key=lambda item: (
        item["hotel_code"],
        item["stay_date"],
        item["observed_at"],
        item["source"],
    ))
    deduped: List[Dict[str, Any]] = []
    recent: Dict[Tuple[str, str, int], float] = {}
    for row in output:
        key = (row["hotel_code"], row["stay_date"], int(row["price"]))
        previous = recent.get(key)
        if previous is not None and abs(float(row["observed_at"]) - previous) <= 60:
            continue
        recent[key] = float(row["observed_at"])
        deduped.append(row)
    return deduped


def _retained_prices(values: Sequence[int]) -> Tuple[List[int], int, Dict[str, Any]]:
    prices = sorted(int(value) for value in values)
    if len(prices) < 8:
        return prices, 0, {"method": "none", "lower_bound": None, "upper_bound": None}
    p25 = percentile(prices, 0.25)
    p75 = percentile(prices, 0.75)
    assert p25 is not None and p75 is not None
    spread = p75 - p25
    if spread <= 0:
        return prices, 0, {"method": "none", "lower_bound": None, "upper_bound": None}
    lower = max(0.0, p25 - 1.5 * spread)
    upper = p75 + 1.5 * spread
    retained = [value for value in prices if lower <= value <= upper]
    return retained, len(prices) - len(retained), {
        "method": "iqr_1.5",
        "lower_bound": _rounded(lower),
        "upper_bound": _rounded(upper),
    }


def price_statistics(
    hotel_codes: Sequence[str],
    *,
    days: int = 180,
    scope_key: str = "",
    condition_key: str = "",
    conditions: Optional[Mapping[str, Any]] = None,
    current_prices: Optional[Mapping[str, Any]] = None,
    hotel_metadata: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    codes = [str(code) for code in dict.fromkeys(hotel_codes) if str(code)]
    rows = _historical_rows(
        codes,
        days=days,
        scope_key=scope_key,
        condition_key=condition_key,
        conditions=conditions,
    )
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["hotel_code"])].append(row)
    output = []
    metadata = hotel_metadata or {}
    overrides = current_prices or {}
    for code in codes:
        hotel_rows = sorted(
            grouped.get(code, []),
            key=lambda item: (float(item["observed_at"]), str(item["stay_date"])),
        )
        raw_prices = [int(row["price"]) for row in hotel_rows]
        retained, excluded_count, anomaly = _retained_prices(raw_prices)
        current = _price_int(overrides.get(code))
        if current is None and hotel_rows:
            current = int(hotel_rows[-1]["price"])
        assessment = assess_price(current, retained)
        meta = metadata.get(code) or {}
        output.append({
            "hotel_code": code,
            "display_code": str(meta.get("display_code") or code),
            "name": str(
                meta.get("name_primary")
                or meta.get("name")
                or meta.get("name_en")
                or code
            ),
            "provider": str(
                meta.get("provider")
                or (code.split(":", 1)[0] if ":" in code else "toyoko")
            ),
            "current_price": current,
            "sample_count": len(retained),
            "raw_sample_count": len(raw_prices),
            "excluded_anomaly_count": excluded_count,
            "minimum": min(retained) if retained else None,
            "maximum": max(retained) if retained else None,
            "average": (
                int(round(sum(retained) / len(retained))) if retained else None
            ),
            "median": _rounded(percentile(retained, 0.5)),
            "p10": _rounded(percentile(retained, 0.10)),
            "p25": _rounded(percentile(retained, 0.25)),
            "p75": _rounded(percentile(retained, 0.75)),
            "p90": _rounded(percentile(retained, 0.90)),
            "assessment": assessment,
            "first_observed_at": (
                float(hotel_rows[0]["observed_at"]) if hotel_rows else None
            ),
            "last_observed_at": (
                float(hotel_rows[-1]["observed_at"]) if hotel_rows else None
            ),
            "sample_window": {
                "days": max(1, min(730, int(days))),
                "start_at": time.time() - max(1, min(730, int(days))) * 86400,
                "end_at": time.time(),
            },
            "method": {
                "percentile": "R-7 linear interpolation",
                "label": "low<=P25, high>=P75, otherwise normal; 4 samples required",
                "dedupe": "same hotel/stay-date/price within 60 seconds",
                "anomaly": anomaly,
                "sources": sorted({row["source"] for row in hotel_rows}),
            },
        })
    return {
        "hotels": output,
        "days": max(1, min(730, int(days))),
        "scope_filtered": bool(scope_key or condition_key or conditions),
        "generated_at": time.time(),
        "summary": {
            "hotel_count": len(output),
            "priced_hotels": sum(item["current_price"] is not None for item in output),
            "low_count": sum(
                item["assessment"]["label"] == "low" for item in output
            ),
            "normal_count": sum(
                item["assessment"]["label"] == "normal" for item in output
            ),
            "high_count": sum(
                item["assessment"]["label"] == "high" for item in output
            ),
            "insufficient_count": sum(
                item["assessment"]["label"] in {"insufficient", "no_current_price"}
                for item in output
            ),
        },
    }


def _haversine_km(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> Optional[float]:
    try:
        lat1, lon1 = float(left["lat"]), float(left["lng"])
        lat2, lon2 = float(right["lat"]), float(right["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    value = max(0.0, min(1.0, value))
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def optimize_split_stays(
    job: Mapping[str, Any],
    nightly_evidence: Sequence[Mapping[str, Any]],
    *,
    window_key: str = "",
    move_penalty: int = 2500,
    distance_cost_per_km: int = 200,
    unknown_distance_penalty: int = 1000,
    priority_bonus: int = 300,
    priority_by_hotel: Optional[Mapping[str, int]] = None,
    top_k: int = 8,
) -> Dict[str, Any]:
    windows = list(job.get("windows") or [])
    window = (
        next(
            (
                item
                for item in windows
                if str(item.get("key") or "") == str(window_key)
            ),
            None,
        )
        if window_key
        else windows[0] if windows else None
    )
    weights = {
        "move_penalty": max(0, int(move_penalty)),
        "distance_cost_per_km": max(0, int(distance_cost_per_km)),
        "unknown_distance_penalty": max(0, int(unknown_distance_penalty)),
        "priority_bonus": max(0, int(priority_bonus)),
    }
    if not window:
        return {
            "window": None,
            "plans": [],
            "split_plans": [],
            "complete_evidence": False,
            "message": "No stay window is available.",
            "weights": weights,
        }
    start = date.fromisoformat(str(window["checkin_date"]))
    stay_dates = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(int(window["nights"]))
    ]
    hotels = {
        str(item.get("code") or ""): deepcopy(dict(item))
        for item in (job.get("hotels") or [])
        if isinstance(item, Mapping) and item.get("code")
    }
    prefer_member = (
        (job.get("conditions") or {}).get("membership_status") == "member"
    )
    priorities = {
        str(code): max(0, min(5, int(value)))
        for code, value in (priority_by_hotel or {}).items()
    }
    candidates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    evidence_by_pair: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in nightly_evidence:
        stay_date = str(item.get("stay_date") or "")
        code = str(item.get("hotel_code") or "")
        result = item.get("result") if isinstance(item.get("result"), Mapping) else {}
        if stay_date not in stay_dates or not code or result.get("available") is not True:
            continue
        regular = _price_int(result.get("min_price") or result.get("min_price_text"))
        member = _price_int(
            result.get("min_member_price") or result.get("min_member_price_text")
        )
        price = member if prefer_member and member is not None else regular
        if price is None:
            continue
        evidence = {
            "stay_date": stay_date,
            "hotel_code": code,
            "price": int(price),
            "regular_price": regular,
            "member_price": member,
            "room_type": str(result.get("min_price_room") or ""),
            "url": str(result.get("url") or ""),
            "observed_at": item.get("observed_at"),
            "evidence_type": "nightly_provider_observation",
        }
        candidates[stay_date].append(evidence)
        evidence_by_pair[(stay_date, code)] = evidence
    missing_dates = [stay_date for stay_date in stay_dates if not candidates[stay_date]]
    if missing_dates:
        return {
            "window": deepcopy(window),
            "plans": [],
            "split_plans": [],
            "complete_evidence": False,
            "missing_dates": missing_dates,
            "message": "At least one night has no available priced hotel evidence.",
            "weights": weights,
        }

    # Keep the best K paths ending at each hotel. This is deterministic and
    # remains bounded for the Phase 3 maximum of 50 hotels and 14 nights.
    states: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for evidence in sorted(
        candidates[stay_dates[0]],
        key=lambda item: (item["price"], item["hotel_code"]),
    ):
        code = evidence["hotel_code"]
        priority = priorities.get(code, 0)
        states[code].append({
            "sequence": [code],
            "nightly": [evidence],
            "total_price": evidence["price"],
            "moves": 0,
            "distance_km": 0.0,
            "unknown_distance_moves": 0,
            "priority_points": priority,
            "score": evidence["price"] - priority * weights["priority_bonus"],
        })

    for stay_date in stay_dates[1:]:
        next_states: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for evidence in sorted(
            candidates[stay_date],
            key=lambda item: (item["price"], item["hotel_code"]),
        ):
            code = evidence["hotel_code"]
            priority = priorities.get(code, 0)
            for previous_code in sorted(states):
                for state in states[previous_code]:
                    moved = previous_code != code
                    distance = (
                        _haversine_km(
                            hotels.get(previous_code, {}),
                            hotels.get(code, {}),
                        )
                        if moved
                        else 0.0
                    )
                    unknown = bool(moved and distance is None)
                    distance_value = float(distance or 0.0)
                    incremental = (
                        int(evidence["price"])
                        + (weights["move_penalty"] if moved else 0)
                        + int(round(distance_value * weights["distance_cost_per_km"]))
                        + (weights["unknown_distance_penalty"] if unknown else 0)
                        - priority * weights["priority_bonus"]
                    )
                    next_states[code].append({
                        "sequence": [*state["sequence"], code],
                        "nightly": [*state["nightly"], evidence],
                        "total_price": state["total_price"] + evidence["price"],
                        "moves": state["moves"] + int(moved),
                        "distance_km": state["distance_km"] + distance_value,
                        "unknown_distance_moves": (
                            state["unknown_distance_moves"] + int(unknown)
                        ),
                        "priority_points": state["priority_points"] + priority,
                        "score": state["score"] + incremental,
                    })
        states = defaultdict(list)
        for code, paths in next_states.items():
            unique: Dict[Tuple[str, ...], Dict[str, Any]] = {}
            for path in paths:
                key = tuple(path["sequence"])
                previous = unique.get(key)
                if previous is None or (
                    path["score"],
                    path["total_price"],
                    path["moves"],
                ) < (
                    previous["score"],
                    previous["total_price"],
                    previous["moves"],
                ):
                    unique[key] = path
            states[code] = sorted(
                unique.values(),
                key=lambda item: (
                    item["score"],
                    item["total_price"],
                    item["moves"],
                    tuple(item["sequence"]),
                ),
            )[: max(1, min(20, int(top_k)))]

    paths = [
        path
        for hotel_paths in states.values()
        for path in hotel_paths
    ]
    unique_paths: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for path in paths:
        unique_paths.setdefault(tuple(path["sequence"]), path)
    ranked = sorted(
        unique_paths.values(),
        key=lambda item: (
            item["score"],
            item["total_price"],
            item["moves"],
            item["distance_km"],
            tuple(item["sequence"]),
        ),
    )[: max(1, min(20, int(top_k)))]
    plans = []
    for rank, path in enumerate(ranked, start=1):
        segments: List[Dict[str, Any]] = []
        for index, code in enumerate(path["sequence"]):
            if not segments or segments[-1]["hotel_code"] != code:
                segments.append({
                    "hotel_code": code,
                    "name": str(
                        hotels.get(code, {}).get("name_primary")
                        or hotels.get(code, {}).get("name")
                        or code
                    ),
                    "checkin_date": stay_dates[index],
                    "checkout_date": (
                        date.fromisoformat(stay_dates[index]) + timedelta(days=1)
                    ).isoformat(),
                    "nights": 1,
                    "subtotal": path["nightly"][index]["price"],
                })
            else:
                segment = segments[-1]
                segment["checkout_date"] = (
                    date.fromisoformat(stay_dates[index]) + timedelta(days=1)
                ).isoformat()
                segment["nights"] += 1
                segment["subtotal"] += path["nightly"][index]["price"]
        plan = {
            "rank": rank,
            "plan_type": "continuous" if path["moves"] == 0 else "split",
            "score": int(round(path["score"])),
            "total_price": int(path["total_price"]),
            "average_nightly_price": round(
                path["total_price"] / max(1, len(stay_dates)),
                2,
            ),
            "moves": int(path["moves"]),
            "distance_km": round(float(path["distance_km"]), 2),
            "unknown_distance_moves": int(path["unknown_distance_moves"]),
            "priority_points": int(path["priority_points"]),
            "segments": segments,
            "nightly": path["nightly"],
            "evidence_complete": len(path["nightly"]) == len(stay_dates),
            "currency": "JPY",
            "score_breakdown": {
                "room_total": int(path["total_price"]),
                "move_cost": int(path["moves"]) * weights["move_penalty"],
                "distance_cost": int(round(
                    float(path["distance_km"]) * weights["distance_cost_per_km"]
                )),
                "unknown_distance_cost": (
                    int(path["unknown_distance_moves"])
                    * weights["unknown_distance_penalty"]
                ),
                "priority_discount": (
                    int(path["priority_points"]) * weights["priority_bonus"]
                ),
            },
        }
        plans.append(plan)
    return {
        "window": deepcopy(window),
        "plans": plans,
        "split_plans": [plan for plan in plans if plan["moves"] > 0],
        "continuous_plans": [plan for plan in plans if plan["moves"] == 0],
        "complete_evidence": True,
        "missing_dates": [],
        "weights": weights,
        "method": (
            "bounded dynamic programming ranked by room total + move cost + "
            "distance cost + unknown-distance cost - hotel-priority discount"
        ),
        "generated_at": time.time(),
    }
