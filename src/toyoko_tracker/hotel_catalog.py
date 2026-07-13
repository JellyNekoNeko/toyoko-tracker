from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from .settings import (
    HEADERS,
    HOTEL_CATALOG_CHECK_INTERVAL_SECONDS,
    HOTEL_CATALOG_SNAPSHOT_PATH,
    HOTEL_CATALOG_URL,
    HOTEL_COORDINATE_CACHE_TTL_SECONDS,
    RADIUS_HOTELS_CACHE_PATH,
)

_STATE_LOCK = threading.RLock()
_REFRESH_LOCK = threading.Lock()
_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_STOP = threading.Event()
_SCHEDULER_THREAD: Optional[threading.Thread] = None


def _noop_log(_message: str) -> None:
    return None


def _noop_refresh() -> None:
    return None


_LOG_HOOK: Callable[[str], None] = _noop_log
_REFRESH_HOOK: Callable[[], None] = _noop_refresh
_STATE_HYDRATED = False
_CACHE_META_MTIME: Optional[float] = None
_CACHE_META_DOCUMENT: Dict[str, Any] = {}

_STATE: Dict[str, Any] = {
    "state": "idle",
    "message": "",
    "checked_at": None,
    "next_check_at": None,
    "official_count": 0,
    "open_japan_count": 0,
    "upcoming_count": 0,
    "coordinate_count": 0,
    "unresolved_coordinate_count": 0,
    "new_hotels": [],
    "removed_hotels": [],
    "upcoming_hotels": [],
    "last_error": "",
}


def set_catalog_hooks(
    *,
    log_hook: Optional[Callable[[str], None]] = None,
    refresh_hook: Optional[Callable[[], None]] = None,
) -> None:
    global _LOG_HOOK, _REFRESH_HOOK
    if log_hook is not None:
        _LOG_HOOK = log_hook
    if refresh_hook is not None:
        _REFRESH_HOOK = refresh_hook


def _log(message: str) -> None:
    try:
        _LOG_HOOK(message)
    except Exception:
        pass


def _atomic_write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".toyoko-catalog-", suffix=".tmp", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError, TypeError):
        return None


def _parse_iso(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat(timespec="seconds")


def _hotel_summary(hotel: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "code": str(hotel.get("code") or hotel.get("hotelCode") or "").zfill(5),
        "name": str(hotel.get("name") or hotel.get("name_en") or ""),
        "open_date": hotel.get("open_date") or hotel.get("openDate"),
        "status": hotel.get("status") or hotel.get("hotelStatus") or "",
        "url": hotel.get("url") or "",
    }


def parse_official_catalog_html(page_html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(page_html or "", "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        raise ValueError("official hotel list did not contain __NEXT_DATA__")
    payload = json.loads(tag.string)
    richest: Dict[str, Dict[str, Any]] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            code = value.get("hotelCode")
            if code is not None:
                normalized = str(code).zfill(5)
                if len(value) > len(richest.get(normalized, {})):
                    richest[normalized] = value
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    hotels: List[Dict[str, Any]] = []
    for code, row in richest.items():
        hotels.append({
            "code": code,
            "name": row.get("name") or "",
            "name_en": row.get("name") or "",
            "status": row.get("hotelStatus") or "",
            "open_date": row.get("openDate"),
            "country": row.get("country"),
            "prefecture": row.get("prefecture"),
            "city": row.get("city") or "",
            "zipcode": row.get("zipcode") or "",
            "address": row.get("address") or "",
            "phone": row.get("phoneNumber") or "",
            "map_url": row.get("googleMapUrl") or "",
            "url": f"https://www.toyoko-inn.com/eng/search/detail/{code}/",
        })
    return sorted(hotels, key=lambda item: item["code"])


def _extract_search_coordinates(page_html: str, code: str) -> Optional[Tuple[float, float]]:
    soup = BeautifulSoup(page_html or "", "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        hotels = json.loads(tag.string)["props"]["pageProps"]["searchResponse"].get("hotels") or []
    except (KeyError, TypeError, ValueError):
        return None
    for row in hotels:
        if str(row.get("hotelCode") or "").zfill(5) != str(code).zfill(5):
            continue
        try:
            return float(row["latDegree"]), float(row["lngDegree"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _resolve_official_coordinates(hotel: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    try:
        prefecture = int(hotel.get("prefecture"))
    except (TypeError, ValueError):
        return None
    today = datetime.now().date()
    params = {
        "prefecture": prefecture,
        "start": today.isoformat(),
        "end": (today + timedelta(days=1)).isoformat(),
        "people": 1,
        "room": 1,
        "smoking": "all",
    }
    response = requests.get(
        "https://www.toyoko-inn.com/eng/search/result/",
        params=params,
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    return _extract_search_coordinates(response.text, hotel["code"])


def _resolve_nominatim_coordinates(hotel: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    query = ", ".join(
        part for part in (hotel.get("address"), hotel.get("city"), hotel.get("zipcode"), "Japan") if part
    )
    if not query:
        return None
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "jp"},
        headers={**HEADERS, "User-Agent": "Toyoko-Chan hotel catalog refresh"},
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    return float(rows[0]["lat"]), float(rows[0]["lon"])


def _load_coordinate_cache_document() -> Dict[str, Any]:
    payload = _read_json(RADIUS_HOTELS_CACHE_PATH)
    return payload if isinstance(payload, dict) else {}


def load_coordinate_cache(*, allow_stale: bool = True) -> Optional[List[Dict[str, Any]]]:
    payload = _load_coordinate_cache_document()
    hotels = payload.get("hotels")
    if not isinstance(hotels, list) or not hotels:
        return None
    generated_at = _parse_iso(payload.get("generated_at"))
    fresh = bool(generated_at and (_utc_now() - generated_at).total_seconds() <= HOTEL_COORDINATE_CACHE_TTL_SECONDS)
    if not allow_stale and not fresh:
        return None
    return [item for item in hotels if isinstance(item, dict)]


def _cache_metadata() -> Dict[str, Any]:
    global _CACHE_META_MTIME, _CACHE_META_DOCUMENT
    try:
        mtime = os.path.getmtime(RADIUS_HOTELS_CACHE_PATH)
    except OSError:
        mtime = None
    with _STATE_LOCK:
        if mtime != _CACHE_META_MTIME:
            _CACHE_META_DOCUMENT = _load_coordinate_cache_document()
            _CACHE_META_MTIME = mtime
        payload = deepcopy(_CACHE_META_DOCUMENT)
    generated = _parse_iso(payload.get("generated_at"))
    age = max(0, int((_utc_now() - generated).total_seconds())) if generated else None
    hotels = payload.get("hotels") if isinstance(payload.get("hotels"), list) else []
    return {
        "cache_generated_at": generated.isoformat(timespec="seconds") if generated else None,
        "cache_age_seconds": age,
        "cache_ttl_seconds": HOTEL_COORDINATE_CACHE_TTL_SECONDS,
        "cache_fresh": bool(age is not None and age <= HOTEL_COORDINATE_CACHE_TTL_SECONDS),
        "coordinate_count": len(hotels),
    }


def _hydrate_state_from_snapshot() -> None:
    global _STATE_HYDRATED
    if _STATE_HYDRATED:
        return
    snapshot = _read_json(HOTEL_CATALOG_SNAPSHOT_PATH)
    if not isinstance(snapshot, dict):
        _STATE_HYDRATED = True
        return
    with _STATE_LOCK:
        _STATE.update({
            "checked_at": snapshot.get("checked_at"),
            "official_count": int(snapshot.get("official_count") or 0),
            "open_japan_count": len(snapshot.get("current_hotels") or []),
            "upcoming_count": len(snapshot.get("upcoming_hotels") or []),
            "new_hotels": deepcopy(snapshot.get("unseen_new_hotels") or []),
            "removed_hotels": deepcopy(snapshot.get("last_removed_hotels") or []),
            "upcoming_hotels": deepcopy(snapshot.get("upcoming_hotels") or []),
        })
    _STATE_HYDRATED = True


def catalog_status_snapshot() -> Dict[str, Any]:
    with _STATE_LOCK:
        state = deepcopy(_STATE)
    state.update(_cache_metadata())
    checked = _parse_iso(state.get("checked_at"))
    if checked:
        state["next_check_at"] = (checked + timedelta(seconds=HOTEL_CATALOG_CHECK_INTERVAL_SECONDS)).isoformat(timespec="seconds")
    return state


def refresh_catalog(*, force: bool = False) -> Dict[str, Any]:
    if not _REFRESH_LOCK.acquire(blocking=False):
        return catalog_status_snapshot()
    try:
        previous_snapshot = _read_json(HOTEL_CATALOG_SNAPSHOT_PATH)
        previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}
        last_checked = _parse_iso(previous_snapshot.get("checked_at"))
        if not force and last_checked:
            age = (_utc_now() - last_checked).total_seconds()
            if age < HOTEL_CATALOG_CHECK_INTERVAL_SECONDS:
                with _STATE_LOCK:
                    _STATE.update({"state": "fresh", "message": "hotel data is current", "last_error": ""})
                return catalog_status_snapshot()

        with _STATE_LOCK:
            _STATE.update({"state": "checking", "message": "checking the official hotel list", "last_error": ""})
        _log("[catalog] checking official hotel list...")
        response = requests.get(HOTEL_CATALOG_URL, headers=HEADERS, timeout=25)
        response.raise_for_status()
        official = parse_official_catalog_html(response.text)
        japan = [hotel for hotel in official if hotel.get("country") == 1]
        if len(japan) < 300:
            raise ValueError(f"official hotel list validation failed: only {len(japan)} Japan hotels")
        current = [hotel for hotel in japan if hotel.get("status") in {"operation", "opened"}]
        upcoming = [hotel for hotel in japan if hotel.get("status") == "before_opening_reserve"]

        old_cache = load_coordinate_cache(allow_stale=True) or []
        old_by_code = {str(item.get("code") or "").zfill(5): item for item in old_cache}
        previous_current = previous_snapshot.get("current_hotels")
        if isinstance(previous_current, list) and previous_current:
            previous_by_code = {str(item.get("code") or "").zfill(5): item for item in previous_current}
        else:
            previous_by_code = old_by_code
        current_by_code = {hotel["code"]: hotel for hotel in current}
        new_codes = sorted(set(current_by_code) - set(previous_by_code))
        removed_codes = sorted(set(previous_by_code) - set(current_by_code))

        merged: List[Dict[str, Any]] = []
        unresolved = 0
        for hotel in current:
            existing = dict(old_by_code.get(hotel["code"], {}))
            item = {**existing, **hotel}
            lat = item.get("lat")
            lng = item.get("lng")
            try:
                valid_coordinates = lat is not None and lng is not None and -90 <= float(lat) <= 90 and -180 <= float(lng) <= 180
            except (TypeError, ValueError):
                valid_coordinates = False
            if not valid_coordinates:
                coordinates = None
                try:
                    coordinates = _resolve_official_coordinates(hotel)
                except Exception as exc:
                    _log(f"[catalog] official coordinates unavailable for {hotel['code']}: {exc}")
                if coordinates is None:
                    try:
                        coordinates = _resolve_nominatim_coordinates(hotel)
                    except Exception as exc:
                        _log(f"[catalog] address coordinates unavailable for {hotel['code']}: {exc}")
                if coordinates:
                    item["lat"], item["lng"] = coordinates
                else:
                    unresolved += 1
            merged.append(item)

        checked_at = _iso_now()
        unseen = {
            str(item.get("code") or "").zfill(5): item
            for item in (previous_snapshot.get("unseen_new_hotels") or [])
            if isinstance(item, dict)
        }
        for code in new_codes:
            unseen[code] = _hotel_summary(current_by_code[code])
        removed = [_hotel_summary(previous_by_code[code]) for code in removed_codes]
        upcoming_summaries = [_hotel_summary(hotel) for hotel in upcoming]
        snapshot = {
            "schema_version": 1,
            "source": HOTEL_CATALOG_URL,
            "checked_at": checked_at,
            "official_count": len(official),
            "current_hotels": [_hotel_summary(hotel) for hotel in current],
            "upcoming_hotels": upcoming_summaries,
            "unseen_new_hotels": list(unseen.values()),
            "last_new_hotels": [_hotel_summary(current_by_code[code]) for code in new_codes],
            "last_removed_hotels": removed,
        }
        _atomic_write_json(HOTEL_CATALOG_SNAPSHOT_PATH, snapshot)
        _atomic_write_json(RADIUS_HOTELS_CACHE_PATH, {
            "schema_version": 2,
            "source": HOTEL_CATALOG_URL,
            "generated_at": checked_at,
            "expires_at": (_utc_now() + timedelta(seconds=HOTEL_COORDINATE_CACHE_TTL_SECONDS)).isoformat(timespec="seconds"),
            "hotels": sorted(merged, key=lambda item: item["code"]),
        })
        try:
            _REFRESH_HOOK()
        except Exception as exc:
            _log(f"[catalog] cache refresh hook failed: {exc}")

        state_name = "updated" if new_codes or removed_codes else "fresh"
        message = f"{len(current)} open Japan hotels; {len(upcoming)} upcoming"
        with _STATE_LOCK:
            _STATE.update({
                "state": state_name,
                "message": message,
                "checked_at": checked_at,
                "official_count": len(official),
                "open_japan_count": len(current),
                "upcoming_count": len(upcoming),
                "coordinate_count": len(merged),
                "unresolved_coordinate_count": unresolved,
                "new_hotels": list(unseen.values()),
                "removed_hotels": removed,
                "upcoming_hotels": upcoming_summaries,
                "last_error": "",
            })
        _log(f"[catalog] refresh complete: {message}; {len(new_codes)} new, {len(removed_codes)} removed")
        return catalog_status_snapshot()
    except Exception as exc:
        with _STATE_LOCK:
            _STATE.update({
                "state": "failed",
                "message": "official hotel data refresh failed; using the previous cache",
                "last_error": str(exc),
            })
        _log(f"[catalog] refresh failed, keeping previous cache: {exc}")
        return catalog_status_snapshot()
    finally:
        _REFRESH_LOCK.release()


def request_catalog_refresh(*, force: bool = True) -> Dict[str, Any]:
    with _STATE_LOCK:
        if _STATE.get("state") == "checking":
            return catalog_status_snapshot()
        _STATE.update({"state": "checking", "message": "refresh queued", "last_error": ""})
    threading.Thread(
        target=refresh_catalog,
        kwargs={"force": force},
        name="hotel-catalog-refresh",
        daemon=True,
    ).start()
    return catalog_status_snapshot()


def acknowledge_new_hotels() -> Dict[str, Any]:
    snapshot = _read_json(HOTEL_CATALOG_SNAPSHOT_PATH)
    if isinstance(snapshot, dict):
        snapshot["unseen_new_hotels"] = []
        _atomic_write_json(HOTEL_CATALOG_SNAPSHOT_PATH, snapshot)
    with _STATE_LOCK:
        _STATE["new_hotels"] = []
    return catalog_status_snapshot()


def start_catalog_scheduler() -> None:
    global _SCHEDULER_THREAD
    with _SCHEDULER_LOCK:
        if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
            return
        _SCHEDULER_STOP.clear()

        def scheduler() -> None:
            refresh_catalog(force=False)
            while not _SCHEDULER_STOP.wait(HOTEL_CATALOG_CHECK_INTERVAL_SECONDS):
                refresh_catalog(force=False)

        _SCHEDULER_THREAD = threading.Thread(target=scheduler, name="hotel-catalog-scheduler", daemon=True)
        _SCHEDULER_THREAD.start()


def stop_catalog_scheduler() -> None:
    _SCHEDULER_STOP.set()


_hydrate_state_from_snapshot()
