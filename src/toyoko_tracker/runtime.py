"""
东横酱 Toyoko Chan — Web version (Flask + Playwright/HTTP)

Relay：
  pip install flask beautifulsoup4 requests playwright

"""

from __future__ import annotations

import json
import html
import re
import time
import random
import threading
import os
import sys
import math
import webbrowser
import socket
import subprocess
import tempfile
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

import requests
from flask import request, jsonify, Response
from bs4 import BeautifulSoup

from .i18n import LANGUAGE_OPTIONS, normalize_primary_language as _normalize_primary_language
from .models import AppConfig, HotelResult
from .notifications import (
    availability_log_snapshot,
    clear_alert_state,
    notification_status_snapshot,
    notify_local,
    process_notifications,
    send_start_notifications,
    send_stop_notifications,
    set_notification_hooks,
    validate_bark_key,
)
from .parsing import (
    detect_price_available,
    extract_hotel_name,
    extract_offers,
    _extract_http_offers,
    _extract_next_data,
    _offer_matches_smoking_preference,
    _room_type_of,
)
from .renderer import (
    HAS_PLAYWRIGHT as _HAS_PLAYWRIGHT,
    PlaywrightRenderer,
    fetch_rendered_any,
    set_renderer_hooks,
)
from .settings import (
    APP_AUTHOR,
    APP_NAME,
    APP_VERSION,
    __version__,
    AUTO_SAVE_PATH,
    BASE_DIR,
    BASE_URL,
    DEFAULT_BARK_SERVER,
    DEFAULT_BARK_CRITICAL_ENABLED,
    DEFAULT_BARK_CRITICAL_SOUND,
    DEFAULT_BARK_CRITICAL_VOLUME,
    DEFAULT_BUDGET_ENABLED,
    DEFAULT_BUDGET_LIMIT,
    DEFAULT_ENGINE,
    DEFAULT_MEMBERSHIP_STATUS,
    DEFAULT_NOTIFY_AVAILABLE,
    DEFAULT_NOTIFY_AVAILABILITY_COUNT_CHANGE,
    DEFAULT_NOTIFY_SEARCH_ERROR,
    DEFAULT_NOTIFY_START,
    DEFAULT_NOTIFY_STOP,
    DEFAULT_NOTIFY_UNAVAILABLE,
    DEFAULT_PER_HOTEL_DELAY_SECONDS,
    DEFAULT_PRIMARY_LANGUAGE,
    DEFAULT_RADIUS_KM,
    DEFAULT_REQUEST_JITTER_PERCENT,
    DEFAULT_ROOM_REQUIREMENT,
    DEFAULT_SEARCH_MODE,
    DEFAULT_SMART_PARALLEL_ENABLED,
    DEFAULT_SMART_PARALLEL_WORKERS,
    DEFAULT_SMOKING,
    DEFAULT_START_DATE,
    DEFAULT_END_DATE,
    HEADERS,
    RADIUS_HOTELS_CACHE_PATH,
    SEARCH_HISTORY_PATH,
    TIMEOUT,
)

# ---- precise timing helpers (monotonic) ----
def _now_wall() -> float:
    return time.time()

def _now_mono() -> float:
    return time.perf_counter()

# ========= Global Status =========
_LOG_LINES: List[str] = []
_LOG_LOCK = threading.Lock()
_LAST_RESULTS: List[HotelResult] = []
_RESULTS_LOCK = threading.Lock()
_START_TIME = _now_wall()
_PROGRESS = {"round": 0, "done": 0, "total": 0, "round_started": 0.0, "round_started_mono": 0.0}
_UPTIME_STARTED: Optional[float] = None        # wall-clock (for display)
_UPTIME_STARTED_MONO: Optional[float] = None   # monotonic (for precise deltas)
_PROGRESS_LOCK = threading.Lock()
_ACTION_LOCK = threading.Lock()
_CURRENT_ACTION: str = "(idle)"
_ACTION_TS: float = 0.0
_UPDATE_LOCK = threading.Lock()
_UPDATE_STATUS: Dict[str, Any] = {
    "state": "idle",
    "current_version": __version__,
    "latest_version": None,
    "message": "",
    "upgrade_output": "",
    "checked_at": None,
}
_CONFIG = AppConfig()
_CONFIG_LOCK = threading.Lock()

_SECRET_CONFIG_FIELDS = {"bot_token", "bark_key", "serverchan_sendkey", "smtp_pass"}

_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_RUN_REQUESTED = False  # only set True by /start; set False by /stop

# ========= Utility Functions / Helper Functions =========
def _safe_print(text: str) -> None:
    try:
        print(text, flush=True)
    except Exception:
        try:
            sys.stdout.buffer.write((text + "\n").encode("utf-8", "replace"))
            sys.stdout.flush()
        except Exception:
            pass


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with _LOG_LOCK:
        _LOG_LINES.append(line)
        if len(_LOG_LINES) > 500:
            del _LOG_LINES[: len(_LOG_LINES) - 500]
    _safe_print(line)


def _set_action(msg: str) -> None:
    global _CURRENT_ACTION, _ACTION_TS
    with _ACTION_LOCK:
        _CURRENT_ACTION = str(msg)
        _ACTION_TS = time.time()


def _atomic_write_json(path: str, data: Any) -> None:
    parent_dir = os.path.dirname(path) or "."
    os.makedirs(parent_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".toyoko-", suffix=".tmp", dir=parent_dir)
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


def _public_config_dict(cfg: AppConfig) -> Dict[str, Any]:
    data = asdict(cfg)
    data["configured_secrets"] = {
        key: bool(data.get(key)) for key in sorted(_SECRET_CONFIG_FIELDS)
    }
    for key in _SECRET_CONFIG_FIELDS:
        data.pop(key, None)
    return data


def _html_attr(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _version_key(value: str) -> Tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or "0"))
    return tuple(int(p) for p in parts[:4]) or (0,)


def _set_update_status(**kwargs: Any) -> None:
    with _UPDATE_LOCK:
        _UPDATE_STATUS.update(kwargs)


def _check_pypi_latest_async() -> None:
    with _UPDATE_LOCK:
        if _UPDATE_STATUS.get("state") in {"checking", "upgrading"}:
            return
        _UPDATE_STATUS.update({"state": "checking", "message": "checking PyPI", "checked_at": _now_wall()})

    def worker() -> None:
        try:
            resp = requests.get("https://pypi.org/pypi/toyoko-tracker/json", timeout=8)
            resp.raise_for_status()
            data = resp.json()
            latest = str((data.get("info") or {}).get("version") or "")
            if not latest:
                raise ValueError("PyPI response did not include version")
            update_available = _version_key(latest) > _version_key(__version__)
            _set_update_status(
                state="update_available" if update_available else "up_to_date",
                current_version=__version__,
                latest_version=latest,
                message="update available" if update_available else "already latest",
                checked_at=_now_wall(),
            )
        except Exception as e:
            _set_update_status(
                state="failed",
                current_version=__version__,
                message=str(e),
                checked_at=_now_wall(),
            )

    threading.Thread(target=worker, name="pypi-update-check", daemon=True).start()


def _upgrade_from_pypi_async() -> None:
    with _UPDATE_LOCK:
        if _UPDATE_STATUS.get("state") == "upgrading":
            return
        _UPDATE_STATUS.update({"state": "upgrading", "message": "upgrading from PyPI", "upgrade_output": ""})

    def worker() -> None:
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "toyoko-tracker"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-4000:]
            if proc.returncode == 0:
                _set_update_status(state="upgraded", message="upgrade finished, please restart", upgrade_output=output)
            else:
                _set_update_status(state="failed", message=f"upgrade failed with code {proc.returncode}", upgrade_output=output)
        except Exception as e:
            _set_update_status(state="failed", message=str(e))

    threading.Thread(target=worker, name="pypi-upgrade", daemon=True).start()


set_renderer_hooks(_log, _set_action)
set_notification_hooks(_log, _set_action)


def _clean_selected_hotels(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    clean: List[Dict[str, str]] = []
    for h in value:
        if not isinstance(h, dict):
            continue
        code = str(h.get("code") or "").strip()
        if not code:
            continue
        clean.append({
            "code": code.zfill(5),
            "name": str(h.get("name") or ""),
            "name_primary": str(h.get("name_primary") or ""),
            "name_zh": str(h.get("name_zh") or ""),
            "name_zh_cn": str(h.get("name_zh_cn") or h.get("name_zh") or ""),
            "name_zh_tw": str(h.get("name_zh_tw") or ""),
            "name_ja": str(h.get("name_ja") or ""),
            "name_ko": str(h.get("name_ko") or ""),
            "name_en": str(h.get("name_en") or h.get("name") or ""),
            "url": str(h.get("url") or ""),
            "map_url": str(h.get("map_url") or ""),
            "lat": h.get("lat"),
            "lng": h.get("lng"),
            "distance_km": h.get("distance_km"),
        })
    return clean


def _localize_selected_hotels(hotels: List[Dict[str, str]], primary_language: Optional[str]) -> List[Dict[str, str]]:
    localized: List[Dict[str, str]] = []
    for h in hotels or []:
        code = str(h.get("code") or "").zfill(5)
        if not code:
            continue
        names = _hotel_names_by_code(code, h.get("name_en") or h.get("name"), primary_language)
        item = dict(h)
        item["name_primary"] = names.get("primary") or h.get("name_primary") or h.get("name_zh") or h.get("name_en") or h.get("name") or ""
        item["name_en"] = names.get("en") or h.get("name_en") or h.get("name") or ""
        item["name_zh"] = names.get("zh") or h.get("name_zh") or ""
        item["name_zh_cn"] = names.get("zh_cn") or h.get("name_zh_cn") or item["name_zh"]
        item["name_zh_tw"] = names.get("zh_tw") or h.get("name_zh_tw") or ""
        item["name_ja"] = names.get("ja") or h.get("name_ja") or ""
        item["name_ko"] = names.get("ko") or h.get("name_ko") or ""
        localized.append(item)
    return localized

# ========= Configuration Read/Write =========
def _load_config_from_file(path: str) -> bool:
    try:
        if not os.path.exists(path):
            return False
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with _CONFIG_LOCK:
            cfg = _CONFIG
            cfg.start_date = data.get('start_date', cfg.start_date)
            cfg.end_date = data.get('end_date', cfg.end_date)
            if isinstance(data.get('hotel_codes'), list):
                cfg.hotel_codes = [str(x) for x in data['hotel_codes']]
            cfg.area_region = str(data.get("area_region", getattr(cfg, "area_region", "")) or "")
            cfg.area_detail = str(data.get("area_detail", getattr(cfg, "area_detail", "")) or "")
            cfg.area_region_label = str(data.get("area_region_label", getattr(cfg, "area_region_label", "")) or "")
            cfg.area_detail_label = str(data.get("area_detail_label", getattr(cfg, "area_detail_label", "")) or "")
            cfg.search_mode = str(data.get("search_mode", getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE)) or DEFAULT_SEARCH_MODE)
            if cfg.search_mode not in {"area", "radius"}:
                cfg.search_mode = DEFAULT_SEARCH_MODE
            cfg.radius_query = str(data.get("radius_query", getattr(cfg, "radius_query", "")) or "")
            cfg.radius_lat = _optional_float(data.get("radius_lat", getattr(cfg, "radius_lat", None)))
            cfg.radius_lng = _optional_float(data.get("radius_lng", getattr(cfg, "radius_lng", None)))
            cfg.radius_km = max(1, min(50, int(data.get("radius_km", getattr(cfg, "radius_km", DEFAULT_RADIUS_KM)))))
            cfg.selected_hotels = _clean_selected_hotels(data.get("selected_hotels", getattr(cfg, "selected_hotels", [])))
            cfg.people = int(data.get('people', cfg.people))
            cfg.rooms = int(data.get('rooms', cfg.rooms))
            sm = str(data.get('smoking', cfg.smoking))
            if sm in {"Smoking", "noSmoking", "all"}:
                cfg.smoking = sm
            ms = str(data.get('membership_status', getattr(cfg, 'membership_status', DEFAULT_MEMBERSHIP_STATUS)))
            if ms in {"member", "non_member", "unknown"}:
                cfg.membership_status = ms
            cfg.primary_language = _normalize_primary_language(data.get("primary_language", getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)))
            cfg.selected_hotels = _localize_selected_hotels(getattr(cfg, "selected_hotels", []), cfg.primary_language)
            # Room requirement (supports both new 'room_requirement' and legacy 'om_requirement')
            rr = str(data.get(
                'room_requirement',
                data.get('om_requirement',
                         getattr(cfg, 'room_requirement', getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT)))
            ))
            if rr not in {'any', 'single', 'double', 'twin'}:
                rr = getattr(cfg, 'room_requirement', getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT))
            # store on both attribute names for forward/backward compat
            setattr(cfg, 'room_requirement', rr)
            setattr(cfg, 'om_requirement', rr)
            cfg.enable_telegram = bool(data.get('enable_telegram', cfg.enable_telegram))
            cfg.bot_token = data.get('bot_token', cfg.bot_token)
            cfg.chat_id = str(data.get('chat_id', cfg.chat_id))
            cfg.enable_bark = bool(data.get('enable_bark', cfg.enable_bark))
            cfg.bark_key = data.get('bark_key', cfg.bark_key)
            cfg.bark_server = data.get('bark_server', cfg.bark_server)
            cfg.bark_critical_enabled = bool(data.get('bark_critical_enabled', getattr(cfg, 'bark_critical_enabled', DEFAULT_BARK_CRITICAL_ENABLED)))
            cfg.bark_critical_volume = max(0, min(10, int(data.get('bark_critical_volume', getattr(cfg, 'bark_critical_volume', DEFAULT_BARK_CRITICAL_VOLUME)))))
            cfg.bark_critical_sound = str(data.get('bark_critical_sound', getattr(cfg, 'bark_critical_sound', DEFAULT_BARK_CRITICAL_SOUND)) or "").strip()
            cfg.enable_serverchan = bool(data.get('enable_serverchan', cfg.enable_serverchan))
            cfg.serverchan_sendkey = data.get('serverchan_sendkey', cfg.serverchan_sendkey)
            cfg.notify_available = bool(data.get('notify_available', getattr(cfg, 'notify_available', DEFAULT_NOTIFY_AVAILABLE)))
            cfg.notify_unavailable = bool(data.get('notify_unavailable', getattr(cfg, 'notify_unavailable', DEFAULT_NOTIFY_UNAVAILABLE)))
            cfg.notify_availability_count_change = bool(data.get(
                'notify_availability_count_change',
                getattr(cfg, 'notify_availability_count_change', DEFAULT_NOTIFY_AVAILABILITY_COUNT_CHANGE)
            ))
            cfg.notify_start = bool(data.get('notify_start', getattr(cfg, 'notify_start', DEFAULT_NOTIFY_START)))
            cfg.notify_stop = bool(data.get('notify_stop', getattr(cfg, 'notify_stop', DEFAULT_NOTIFY_STOP)))
            cfg.notify_search_error = bool(data.get('notify_search_error', getattr(cfg, 'notify_search_error', DEFAULT_NOTIFY_SEARCH_ERROR)))
            cfg.enable_local = bool(data.get('enable_local', cfg.enable_local))
            cfg.enable_email = bool(data.get('enable_email', cfg.enable_email))
            cfg.smtp_host = data.get('smtp_host', cfg.smtp_host)
            cfg.smtp_port = int(data.get('smtp_port', cfg.smtp_port))
            cfg.smtp_tls = bool(data.get('smtp_tls', cfg.smtp_tls))
            cfg.smtp_user = data.get('smtp_user', cfg.smtp_user)
            cfg.smtp_pass = data.get('smtp_pass', cfg.smtp_pass)
            cfg.email_from = data.get('email_from', cfg.email_from)
            cfg.email_to = data.get('email_to', cfg.email_to)
            cfg.loop_interval_seconds = max(30, min(3600, int(data.get('loop_interval_seconds', cfg.loop_interval_seconds))))
            cfg.per_hotel_delay_seconds = max(1, min(60, int(data.get(
                'per_hotel_delay_seconds',
                getattr(cfg, 'per_hotel_delay_seconds', DEFAULT_PER_HOTEL_DELAY_SECONDS)
            ))))
            cfg.request_jitter_percent = max(0, min(100, int(data.get(
                'request_jitter_percent',
                getattr(cfg, 'request_jitter_percent', DEFAULT_REQUEST_JITTER_PERCENT)
            ))))
            cfg.available_alert_repeat = max(0, min(11, int(data.get('available_alert_repeat', cfg.available_alert_repeat))))
            cfg.available_alert_repeat_interval_sec = max(60, min(86400, int(data.get('available_alert_repeat_interval_sec', cfg.available_alert_repeat_interval_sec))))
            cfg.smart_parallel_enabled = bool(data.get('smart_parallel_enabled', getattr(cfg, 'smart_parallel_enabled', DEFAULT_SMART_PARALLEL_ENABLED)))
            cfg.smart_parallel_workers = max(1, min(3, int(data.get(
                'smart_parallel_workers',
                getattr(cfg, 'smart_parallel_workers', DEFAULT_SMART_PARALLEL_WORKERS)
            ))))
            eng = str(data.get('engine', getattr(cfg, 'engine', DEFAULT_ENGINE)))
            if eng == "selenium":
                eng = DEFAULT_ENGINE
            if eng not in {'playwright', 'http'}:
                eng = DEFAULT_ENGINE
            if eng == "playwright" and not _HAS_PLAYWRIGHT:
                eng = DEFAULT_ENGINE
            cfg.engine = eng
            # Budget (non-member price limit)
            try:
                cfg.budget_enabled = bool(data.get('budget_enabled', getattr(cfg, 'budget_enabled', DEFAULT_BUDGET_ENABLED)))
            except Exception:
                cfg.budget_enabled = DEFAULT_BUDGET_ENABLED
            try:
                cfg.budget_limit = int(data.get('budget_limit', getattr(cfg, 'budget_limit', DEFAULT_BUDGET_LIMIT)))
            except Exception:
                cfg.budget_limit = DEFAULT_BUDGET_LIMIT
            if not getattr(cfg, "selected_hotels", None):
                try:
                    records = _load_search_history()
                    if records:
                        last = records[0]
                        cfg.area_region = str(last.get("area_region") or cfg.area_region or "")
                        cfg.area_detail = str(last.get("area_detail") or cfg.area_detail or "")
                        cfg.area_region_label = str(last.get("area_region_label") or cfg.area_region_label or "")
                        cfg.area_detail_label = str(last.get("area_detail_label") or cfg.area_detail_label or "")
                        cfg.selected_hotels = _clean_selected_hotels(last.get("selected_hotels"))
                        if cfg.selected_hotels:
                            cfg.hotel_codes = [h["code"] for h in cfg.selected_hotels]
                except Exception as e:
                    _log(f"[boot] search history restore skipped: {e}")
        _log(f"Loaded config from {path}")
        return True
    except Exception as e:
        _log(f"[error] load config from {path}: {e}")
        return False


def _load_config_with_legacy(primary_path: str, legacy_path: str) -> Optional[str]:
    if _load_config_from_file(primary_path):
        return primary_path
    if primary_path != legacy_path and _load_config_from_file(legacy_path):
        if _save_config_to_file(primary_path):
            _log(f"Migrated config from {legacy_path} to {primary_path}")
        return legacy_path
    return None


def _save_config_to_file(path: str) -> bool:
    try:
        with _CONFIG_LOCK:
            cfg = _CONFIG
            data = {
                'start_date': cfg.start_date,
                'end_date': cfg.end_date,
                'hotel_codes': list(cfg.hotel_codes),
                'area_region': getattr(cfg, 'area_region', ""),
                'area_detail': getattr(cfg, 'area_detail', ""),
                'area_region_label': getattr(cfg, 'area_region_label', ""),
                'area_detail_label': getattr(cfg, 'area_detail_label', ""),
                'search_mode': getattr(cfg, 'search_mode', DEFAULT_SEARCH_MODE),
                'radius_query': getattr(cfg, 'radius_query', ""),
                'radius_lat': getattr(cfg, 'radius_lat', None),
                'radius_lng': getattr(cfg, 'radius_lng', None),
                'radius_km': getattr(cfg, 'radius_km', DEFAULT_RADIUS_KM),
                'selected_hotels': _clean_selected_hotels(getattr(cfg, 'selected_hotels', [])),
                'people': cfg.people,
                'rooms': cfg.rooms,
                'smoking': cfg.smoking,
                'membership_status': getattr(cfg, 'membership_status', DEFAULT_MEMBERSHIP_STATUS),
                'primary_language': getattr(cfg, 'primary_language', DEFAULT_PRIMARY_LANGUAGE),
                'room_requirement': getattr(cfg, 'room_requirement',
                                            getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT)),
                'enable_telegram': cfg.enable_telegram,
                'bot_token': cfg.bot_token,
                'chat_id': cfg.chat_id,
                'enable_bark': cfg.enable_bark,
                'bark_key': cfg.bark_key,
                'bark_server': cfg.bark_server,
                'bark_critical_enabled': getattr(cfg, 'bark_critical_enabled', DEFAULT_BARK_CRITICAL_ENABLED),
                'bark_critical_volume': getattr(cfg, 'bark_critical_volume', DEFAULT_BARK_CRITICAL_VOLUME),
                'bark_critical_sound': getattr(cfg, 'bark_critical_sound', DEFAULT_BARK_CRITICAL_SOUND),
                'enable_serverchan': cfg.enable_serverchan,
                'serverchan_sendkey': cfg.serverchan_sendkey,
                'notify_available': getattr(cfg, 'notify_available', DEFAULT_NOTIFY_AVAILABLE),
                'notify_unavailable': getattr(cfg, 'notify_unavailable', DEFAULT_NOTIFY_UNAVAILABLE),
                'notify_availability_count_change': getattr(
                    cfg, 'notify_availability_count_change', DEFAULT_NOTIFY_AVAILABILITY_COUNT_CHANGE
                ),
                'notify_start': getattr(cfg, 'notify_start', DEFAULT_NOTIFY_START),
                'notify_stop': getattr(cfg, 'notify_stop', DEFAULT_NOTIFY_STOP),
                'notify_search_error': getattr(cfg, 'notify_search_error', DEFAULT_NOTIFY_SEARCH_ERROR),
                'enable_local': cfg.enable_local,
                'enable_email': cfg.enable_email,
                'smtp_host': cfg.smtp_host,
                'smtp_port': cfg.smtp_port,
                'smtp_tls': cfg.smtp_tls,
                'smtp_user': cfg.smtp_user,
                'smtp_pass': cfg.smtp_pass,
                'email_from': cfg.email_from,
                'email_to': cfg.email_to,
                'loop_interval_seconds': cfg.loop_interval_seconds,
                'per_hotel_delay_seconds': cfg.per_hotel_delay_seconds,
                'request_jitter_percent': getattr(cfg, 'request_jitter_percent', DEFAULT_REQUEST_JITTER_PERCENT),
                'available_alert_repeat': cfg.available_alert_repeat,
                'available_alert_repeat_interval_sec': cfg.available_alert_repeat_interval_sec,
                'engine': cfg.engine,
                'smart_parallel_enabled': getattr(cfg, 'smart_parallel_enabled', DEFAULT_SMART_PARALLEL_ENABLED),
                'smart_parallel_workers': getattr(cfg, 'smart_parallel_workers', DEFAULT_SMART_PARALLEL_WORKERS),
                'budget_enabled': getattr(cfg, 'budget_enabled', DEFAULT_BUDGET_ENABLED),
                'budget_limit': getattr(cfg, 'budget_limit', DEFAULT_BUDGET_LIMIT),
            }
        _atomic_write_json(path, data)
        _log(f"Saved config to {path}")
        return True
    except Exception as e:
        _log(f"[error] save config to {path}: {e}")
        return False


def _load_search_history() -> List[Dict[str, Any]]:
    try:
        if not os.path.exists(SEARCH_HISTORY_PATH):
            return []
        with open(SEARCH_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)][:10]
    except Exception as e:
        _log(f"[history] load failed: {e}")
    return []


def _save_search_history(records: List[Dict[str, Any]]) -> None:
    try:
        _atomic_write_json(SEARCH_HISTORY_PATH, records[:10])
    except Exception as e:
        _log(f"[history] save failed: {e}")


def _search_history_record(payload: Dict[str, Any], cfg: AppConfig) -> Dict[str, Any]:
    clean_hotels = _clean_selected_hotels(payload.get("selected_hotels"))
    if not clean_hotels:
        clean_hotels = [{"code": str(code)} for code in cfg.hotel_codes]

    title_parts = [
        f"{cfg.start_date} -> {cfg.end_date}",
        f"{len(cfg.hotel_codes)} hotels",
        f"{cfg.people}P/{cfg.rooms}R",
    ]
    rr = getattr(cfg, "room_requirement", getattr(cfg, "om_requirement", DEFAULT_ROOM_REQUIREMENT))
    if rr and rr != "any":
        title_parts.append(str(rr))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "id": f"{int(time.time() * 1000)}",
        "title": " · ".join(title_parts),
        "created_at": now,
        "start_date": cfg.start_date,
        "end_date": cfg.end_date,
        "people": cfg.people,
        "rooms": cfg.rooms,
        "smoking": cfg.smoking,
        "membership_status": getattr(cfg, "membership_status", DEFAULT_MEMBERSHIP_STATUS),
        "primary_language": getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE),
        "room_requirement": rr,
        "engine": cfg.engine,
                "loop_interval_seconds": cfg.loop_interval_seconds,
                "per_hotel_delay_seconds": cfg.per_hotel_delay_seconds,
        "request_jitter_percent": getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT),
        "smart_parallel_enabled": getattr(cfg, "smart_parallel_enabled", DEFAULT_SMART_PARALLEL_ENABLED),
        "smart_parallel_workers": getattr(cfg, "smart_parallel_workers", DEFAULT_SMART_PARALLEL_WORKERS),
        "available_alert_repeat": cfg.available_alert_repeat,
        "available_alert_repeat_interval_sec": cfg.available_alert_repeat_interval_sec,
        "area_region": str(payload.get("area_region") or ""),
        "area_detail": str(payload.get("area_detail") or ""),
        "area_region_label": str(payload.get("area_region_label") or ""),
        "area_detail_label": str(payload.get("area_detail_label") or ""),
        "search_mode": getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE),
        "radius_query": getattr(cfg, "radius_query", ""),
        "radius_lat": getattr(cfg, "radius_lat", None),
        "radius_lng": getattr(cfg, "radius_lng", None),
        "radius_km": getattr(cfg, "radius_km", DEFAULT_RADIUS_KM),
        "hotel_codes": list(cfg.hotel_codes),
        "selected_hotels": clean_hotels,
    }
    return record


def _remember_search(payload: Dict[str, Any], cfg: AppConfig) -> None:
    try:
        record = _search_history_record(payload, cfg)
        signature_keys = (
            "start_date", "end_date", "people", "rooms", "smoking", "room_requirement",
            "membership_status", "primary_language", "engine", "loop_interval_seconds", "per_hotel_delay_seconds", "request_jitter_percent",
            "smart_parallel_enabled", "smart_parallel_workers", "available_alert_repeat",
            "available_alert_repeat_interval_sec", "area_region", "area_detail", "hotel_codes",
        )
        signature = json.dumps({k: record.get(k) for k in signature_keys}, ensure_ascii=False, sort_keys=True)
        records = _load_search_history()
        deduped = []
        for item in records:
            item_signature = json.dumps({k: item.get(k) for k in signature_keys}, ensure_ascii=False, sort_keys=True)
            if item_signature != signature:
                deduped.append(item)
        _save_search_history([record] + deduped)
    except Exception as e:
        _log(f"[history] remember failed: {e}")


# ========= Page Fetching / Parsing =========
def build_url(cfg: AppConfig, code: str, start: str, end: str) -> str:
    return (
        f"{BASE_URL}?hotel={code}"
        f"&people={cfg.people}&room={cfg.rooms}&smoking={cfg.smoking}"
        f"&start={start}&end={end}"
    )


def build_booking_url(cfg: AppConfig, code: str, start: str, end: str) -> str:
    return build_url(cfg, code, start, end)


def _hotel_result_from_offers(
    cfg: AppConfig,
    code: str,
    url: str,
    name: Optional[str],
    offers: List[Dict[str, Any]],
    offer_stats: Dict[str, bool],
    visible_text: Optional[str] = None,
) -> HotelResult:
    # ---- Room requirement filtering (single/double/twin) ----
    rr = getattr(cfg, 'room_requirement', getattr(cfg, 'om_requirement', 'any')) or 'any'
    rr = rr.lower()

    filtered_offers = offers
    requirement_unmet = False
    if rr in {"single", "double", "twin"}:
        filtered_offers = [o for o in offers if _room_type_of(o.get("room_title")) == rr]
        if (len(offers) > 0) and (len(filtered_offers) == 0):
            requirement_unmet = True

    smoking_pref = getattr(cfg, "smoking", DEFAULT_SMOKING)
    before_smoking_filter_count = len(filtered_offers)
    filtered_offers = [o for o in filtered_offers if _offer_matches_smoking_preference(o, smoking_pref)]
    removed_by_smoking_filter = before_smoking_filter_count > 0 and len(filtered_offers) == 0 and str(smoking_pref or "all") != "all"

    membership_status = getattr(cfg, "membership_status", DEFAULT_MEMBERSHIP_STATUS)
    primary_language = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE))

    def _offer_sort_value(offer: Dict[str, Any]) -> int:
        if membership_status == "member":
            val = offer.get("member_price_val") or offer.get("price_val")
        else:
            val = offer.get("price_val")
        try:
            return int(val)
        except Exception:
            return 10**12

    # Build display list for UI: include every matching priced offer
    # Deduplicate by room_title (case-insensitive), keeping the lowest price for each
    best_by_room: Dict[str, Dict[str, Any]] = {}
    for o in filtered_offers:
        if o.get("price_val") is None:
            continue
        title_raw = (o.get("room_title") or "").strip()
        key = f"{title_raw.lower()}|{o.get('room_smoking') or ''}"
        prev = best_by_room.get(key)
        if (prev is None) or (_offer_sort_value(o) < _offer_sort_value(prev)):
            best_by_room[key] = o

    # Use only the cheapest offer per room title
    dedup_offers: List[Dict[str, Any]] = list(best_by_room.values())
    # Optional: sort by price ascending for a stable, nice UI
    dedup_offers.sort(key=_offer_sort_value)

    offers_display: List[Dict[str, Any]] = []
    for o in dedup_offers:
        room_title = o.get("room_title")
        offers_display.append({
            "price_text": o.get("price_text"),
            "member_price_text": o.get("member_price_text"),
            "remaining_norm": o.get("remaining_norm"),
            "room_title": room_title,
            **({"room_smoking": o.get("room_smoking")} if o.get("room_smoking") else {}),
        })

    offers_for_best = dedup_offers
    best = None
    for o in offers_for_best:
        if o.get("price_val") is not None:
            if best is None or _offer_sort_value(o) < _offer_sort_value(best):
                best = o

    # If there are priced offers but they are all heartful/accessible,
    # we should treat it as no rooms available.
    only_ignored_available = (
        offer_stats.get("had_any_offer")
        and not offer_stats.get("had_any_non_ignored_offer")
        and offer_stats.get("had_any_ignored_offer")
    )

    if best and not only_ignored_available:
        available = True
        min_price = int(best["price_val"])
        min_price_text = best.get("price_text")
        min_room = best.get("room_title")
        min_plan = best.get("plan_name")
        min_member_price_text = best.get("member_price_text")
        min_remaining = best.get("remaining_norm")
    else:
        # When only heartful/accessible rooms are priced, force unavailable.
        if only_ignored_available:
            available = False
        elif removed_by_smoking_filter:
            available = False
        else:
            # Fallback: if parsing found no usable offers, try text heuristic.
            available = detect_price_available(visible_text or "") if visible_text is not None else False
        min_price = None
        min_price_text = None
        min_room = None
        min_plan = None
        min_member_price_text = None
        min_remaining = None

    primary_language = _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE))
    name_info = _hotel_names_by_code(code, name, primary_language)
    return HotelResult(
        code=code,
        url=url,
        name=name,
        name_zh=name_info.get("zh"),
        name_en=name_info.get("en"),
        name_primary=name_info.get("primary"),
        primary_language=primary_language,
        available=available,
        min_price=min_price,
        min_price_text=min_price_text,
        min_price_room=min_room,
        min_price_plan=min_plan,
        min_member_price_text=min_member_price_text,
        min_remaining=min_remaining,
        requirement_unmet=requirement_unmet,
        offers_display=offers_display,
    )


def check_hotel_http(cfg: AppConfig, code: str, start: str, end: str) -> HotelResult:
    url = build_url(cfg, code, start, end)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        next_data = _extract_next_data(resp.text)
        if not next_data:
            raise RuntimeError("missing __NEXT_DATA__")
        page_props = ((next_data.get("props") or {}).get("pageProps") or {})
        plan_response = page_props.get("planResponse") or {}
        if not isinstance(plan_response, dict):
            raise RuntimeError("missing planResponse")
        name = (
            plan_response.get("hotelTitle")
            or plan_response.get("hotelName")
            or page_props.get("hotelName")
            or extract_hotel_name(BeautifulSoup(resp.text, "html.parser"))
        )
        offers, offer_stats = _extract_http_offers(plan_response)
        return _hotel_result_from_offers(cfg, code, url, name, offers, offer_stats, None)
    except Exception as e:
        _log(f"[http] failed for {code}: {e}")
        return HotelResult(code=code, url=url, name=None, available=None)


def check_hotel_playwright(cfg: AppConfig, renderer: Optional[Any], code: str, start: str, end: str) -> HotelResult:
    url = build_url(cfg, code, start, end)
    try:
        rendered = fetch_rendered_any(cfg, renderer, url)
    except Exception as e:
        _log(f"[playwright] failed for {code}: {e}")
        return HotelResult(code=code, url=url, name=None, available=None)

    name = extract_hotel_name(rendered.soup)
    offers, offer_stats = extract_offers(rendered.soup)
    return _hotel_result_from_offers(cfg, code, url, name, offers, offer_stats, rendered.visible_text)


def check_hotel(cfg: AppConfig, renderer: Optional[Any], code: str, start: str, end: str) -> HotelResult:
    if getattr(cfg, "engine", "playwright") == "http":
        result = check_hotel_http(cfg, code, start, end)
        if result.available is not None:
            return result
        if _HAS_PLAYWRIGHT:
            _log(f"[http] fallback to Playwright for {code}")
            return check_hotel_playwright(cfg, renderer, code, start, end)
        return result
    return check_hotel_playwright(cfg, renderer, code, start, end)


def _jittered_delay(base_seconds: int, jitter_percent: int) -> float:
    base = float(max(0, base_seconds))
    jitter = max(0, min(100, int(jitter_percent))) / 100.0
    if base <= 0 or jitter <= 0:
        return base
    low = base * (1.0 - jitter)
    high = base * (1.0 + jitter)
    return max(1.0, random.uniform(low, high))


def _parallel_allowed(cfg: AppConfig) -> bool:
    return bool(
        getattr(cfg, "smart_parallel_enabled", False)
        and getattr(cfg, "engine", "http") == "http"
        and int(getattr(cfg, "smart_parallel_workers", 1) or 1) > 1
    )


def _check_hotels_parallel_http(cfg: AppConfig, codes: List[str], start: str, end: str) -> List[HotelResult]:
    workers = max(1, min(3, int(getattr(cfg, "smart_parallel_workers", DEFAULT_SMART_PARALLEL_WORKERS) or 1)))
    base_delay = max(1, min(60, int(cfg.per_hotel_delay_seconds)))
    jitter = getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT)
    results: List[Optional[HotelResult]] = [None] * len(codes)

    _log(f"[parallel] Smart Parallel enabled: workers={workers}, global-ish delay={base_delay}s")

    def _run_slot(slot: int, indexed_codes: List[Tuple[int, str]]) -> None:
        if slot > 0:
            if _stop_event.wait(timeout=_jittered_delay(base_delay * slot, jitter)):
                return
        for idx, code in indexed_codes:
            if _stop_event.is_set():
                return
            _set_action(f"[search:{slot + 1}/{workers}] Checking hotel {code} for {start} → {end}...")
            _log(f"[search:{slot + 1}/{workers}] Checking hotel {code} for {start} → {end}...")
            try:
                results[idx] = check_hotel(cfg, None, code, start, end)
            except Exception as e:
                _log(f"[error] check {code}: {e}")
                results[idx] = HotelResult(code=code, url=build_url(cfg, code, start, end), name=None, available=None)
            with _PROGRESS_LOCK:
                _PROGRESS["done"] = min(_PROGRESS["done"] + 1, _PROGRESS["total"])
            if _stop_event.wait(timeout=_jittered_delay(base_delay * workers, jitter)):
                return

    slots: List[List[Tuple[int, str]]] = [[] for _ in range(workers)]
    for idx, code in enumerate(codes):
        slots[idx % workers].append((idx, code))

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="smart-search") as executor:
        futures = [executor.submit(_run_slot, slot, indexed) for slot, indexed in enumerate(slots) if indexed]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                _log(f"[parallel] worker exception: {e}")

    return [
        r if r is not None else HotelResult(code=codes[idx], url=build_url(cfg, codes[idx], start, end), name=None, available=None)
        for idx, r in enumerate(results)
    ]


# ========= Worker Loop =========
def _worker_loop():
    global _LAST_RESULTS, _PROGRESS, _UPTIME_STARTED, _UPTIME_STARTED_MONO
    _log("Worker loop started.")
    _set_action("Worker loop started.")
    _UPTIME_STARTED = _now_wall()
    _UPTIME_STARTED_MONO = _now_mono()
    with _CONFIG_LOCK:
        cfg = deepcopy(_CONFIG)
        start, end = cfg.start_date, cfg.end_date

    renderer = None
    if getattr(cfg, "engine", "playwright") == "playwright" and _HAS_PLAYWRIGHT:
        renderer = PlaywrightRenderer(cfg)
    elif getattr(cfg, "engine", "playwright") == "playwright" and not _HAS_PLAYWRIGHT:
        _log("[engine] Playwright is unavailable; using HTTP/API engine for this run.")
        cfg.engine = "http"

    # Guard loop: (no code yet)
    while not _stop_event.is_set():
        # Hard guard: if user has requested stop, do not continue another round
        try:
            if not _RUN_REQUESTED:
                _log("Worker noticed RUN_REQUESTED=False, exiting loop.")
                break
        except NameError:
            # Backward-compat if the flag wasn't defined
            pass
        with _PROGRESS_LOCK:
            _PROGRESS["round"] += 1
            _PROGRESS["done"] = 0
            _PROGRESS["total"] = len(cfg.hotel_codes)
            _PROGRESS["phase"] = "scanning"
            _PROGRESS["wait_started_mono"] = 0.0
            _PROGRESS["wait_total_sec"] = 0
            _PROGRESS["wait_elapsed_sec"] = 0
            _PROGRESS["round_started"] = _now_wall()
            _PROGRESS["round_started_mono"] = _now_mono()
        current_round = _PROGRESS["round"]
        results: List[HotelResult] = []
        if _parallel_allowed(cfg):
            results = _check_hotels_parallel_http(cfg, list(cfg.hotel_codes), start, end)
        else:
            if getattr(cfg, "smart_parallel_enabled", False) and getattr(cfg, "engine", "http") != "http":
                _log("[parallel] Smart Parallel is only used with HTTP/API engine; running single-line search.")
            for code in cfg.hotel_codes:
                if _stop_event.is_set():
                    break
                _set_action(f"[search] Checking hotel {code} for {start} → {end}...")
                _log(f"[search] Checking hotel {code} for {start} → {end}...")
                try:
                    result = check_hotel(cfg, renderer, code, start, end)
                except Exception as e:
                    _log(f"[error] check {code}: {e}")
                    result = HotelResult(code=code, url=build_url(cfg, code, start, end), name=None, available=None)
                results.append(result)
                with _PROGRESS_LOCK:
                    _PROGRESS["done"] = min(_PROGRESS["done"] + 1, _PROGRESS["total"])
                per_hotel_delay = _jittered_delay(
                    max(1, min(60, int(cfg.per_hotel_delay_seconds))),
                    getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT),
                )
                if _stop_event.wait(timeout=per_hotel_delay):
                    break

        newly_available_codes: List[str] = []
        try:
            newly_available_codes = process_notifications(cfg, results, start, end)
        except Exception as e:
            _log(f"[error] notify: {e}")

        with _RESULTS_LOCK:
            _LAST_RESULTS = results
        with _PROGRESS_LOCK:
            _PROGRESS["done"] = _PROGRESS["total"]

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        widths = {
            'code': max(len("HotelCode"), *(len(r.code) for r in results)) if results else 9,
            'name': max(len("HotelName"), *(len((r.name or "(Hotel name not found)")) for r in results)) if results else 9,
            'res':  max(len("Result"), *(len("✅" if r.available else "❌" if r.available is False else "❓") for r in results)) if results else 6,
        }
        bar = "=" * (widths['code'] + widths['name'] + widths['res'] + 2)
        _log(bar)
        _log(f"Time: {ts}")
        _log(f"Search Dates: {start} → {end}")
        _log(f"{'HotelCode':<{widths['code']}} {'HotelName':<{widths['name']}} {'Result':<{widths['res']}}")
        _log("-" * (widths['code'] + widths['name'] + widths['res'] + 2))
        for r in results:
            res = "✅" if r.available else ("❌" if r.available is False else "❓")
            _log(f"{r.code:<{widths['code']}} {(r.name or '(Hotel name not found)'):<{widths['name']}} {res:<{widths['res']}}")
        _log(bar)

        # Post-wait model: after a loop finishes, always wait the full interval
        wait_s = _jittered_delay(
            max(30, min(3600, int(cfg.loop_interval_seconds))),
            max(0, min(50, int(getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT)) // 2)),
        )
        with _PROGRESS_LOCK:
            _PROGRESS["phase"] = "waiting"
            _PROGRESS["wait_started_mono"] = _now_mono()
            _PROGRESS["wait_total_sec"] = int(round(wait_s))
            _PROGRESS["wait_elapsed_sec"] = 0
        _set_action(f"Round {current_round} complete. Waiting {wait_s:.1f}s...")
        watch_codes = set(newly_available_codes or [])
        if watch_codes:
            _log(f"[enhanced] New availability detected; confirming every 5s during wait: {', '.join(sorted(watch_codes))}")
        wait_deadline = _now_mono() + wait_s
        while not _stop_event.is_set():
            remaining_wait = wait_deadline - _now_mono()
            if remaining_wait <= 0:
                break
            if not watch_codes:
                if _stop_event.wait(timeout=remaining_wait):
                    break
                break
            if _stop_event.wait(timeout=min(5.0, max(0.1, remaining_wait))):
                break
            if _now_mono() >= wait_deadline:
                break

            enhanced_results: List[HotelResult] = []
            for code in list(watch_codes):
                if _stop_event.is_set():
                    break
                try:
                    _set_action(f"[enhanced] Rechecking available hotel {code}...")
                    r = check_hotel(cfg, renderer, code, start, end)
                    enhanced_results.append(r)
                    if r.available is not True:
                        watch_codes.discard(code)
                        _log(f"[enhanced] Availability changed for {code}; enhanced confirmation stopped for this hotel.")
                except Exception as e:
                    _log(f"[enhanced] recheck {code} failed: {e}")
                    watch_codes.discard(code)
                    enhanced_results.append(HotelResult(code=code, url=build_url(cfg, code, start, end), name=None, available=None))
            if enhanced_results:
                try:
                    process_notifications(cfg, enhanced_results, start, end)
                except Exception as e:
                    _log(f"[enhanced] notify failed: {e}")
                with _RESULTS_LOCK:
                    by_code = {r.code: r for r in _LAST_RESULTS}
                    for r in enhanced_results:
                        by_code[r.code] = r
                    _LAST_RESULTS = [by_code.get(r.code, r) for r in _LAST_RESULTS]
        if _stop_event.is_set():
            break

    if isinstance(renderer, PlaywrightRenderer):
        renderer.close()
    _log("Worker loop stopped.")

# ========= Web Handlers =========
def home() -> Response:
    with _CONFIG_LOCK:
        cfg = _CONFIG
    with _RESULTS_LOCK:
        results = list(_LAST_RESULTS)

    rows = []
    for r in results:
        # 生成本酒店需要显示的“行数据”列表（每个房型=一行）
        by_offers = []
        if getattr(r, "requirement_unmet", False):
            # 没有满足房型需求：仅给出一行，状态❗，其余列为-
            by_offers.append({
                "status": "❗",
                "price_html": "-",
                "left_html": "-",
                "room_html": "-"
            })
        else:
            if getattr(r, "offers_display", None):
                # 有多房型：为每个符合条件的房型单独生成一行
                for o in (r.offers_display or []):
                    price = o.get("price_text") or "-"
                    mp = o.get("member_price_text")
                    # 会员价第二行小字括号：用 <div> 避免 &lt;br&gt; 被转义
                    if mp:
                        price = f"{price}<div>({mp})</div>"
                    by_offers.append({
                        "status": "✅",
                        "price_html": price,
                        "left_html": o.get("remaining_norm") or "-",
                        "room_html": o.get("room_title") or "-"
                    })
            else:
                # 退回到单值字段（兼容无 offers_display 的情况）
                status = "✅" if r.available else ("❌" if r.available is False else "❓")
                if r.min_price_text:
                    price = r.min_price_text
                    if r.min_member_price_text:
                        price = f"{price}<div>({r.min_member_price_text})</div>"
                else:
                    price = "-"
                by_offers.append({
                    "status": status,
                    "price_html": price,
                    "left_html": r.min_remaining or "-",
                    "room_html": r.min_price_room or "-"
                })

        # 渲染多行：同一酒店只在首行显示 Code 和 HotelName
        name_html = f"<a href='{r.url}' target='_blank'>{(r.name or '(Hotel name not found)')}</a>"
        for idx, row in enumerate(by_offers):
            code_cell = r.code if idx == 0 else ""
            name_cell = name_html if idx == 0 else ""
            rows.append(
                f"<tr>"
                f"<td>{code_cell}</td>"
                f"<td>{name_cell}</td>"
                f"<td>{row['status']}</td>"
                f"<td>{row['price_html']}</td>"
                f"<td>{row['left_html']}</td>"
                f"<td>{row['room_html']}</td>"
                f"</tr>"
            )

    current_room_requirement = getattr(cfg, 'room_requirement', getattr(cfg, 'om_requirement', 'any'))
    current_membership_status = getattr(cfg, 'membership_status', DEFAULT_MEMBERSHIP_STATUS)
    current_primary_language = _normalize_primary_language(getattr(cfg, 'primary_language', DEFAULT_PRIMARY_LANGUAGE))
    language_options_html = "\n".join(
        f"<option value='{code}' {'selected' if current_primary_language == code else ''}>{info['label']} / {info['english']}</option>"
        for code, info in LANGUAGE_OPTIONS.items()
    )
    html = f"""
    <html><head><meta charset='utf-8'><title>{APP_NAME}</title>
    <link rel="stylesheet" href="/static/app.css">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"></head>
        <body>
          <div class="topbar">
            <div></div>
            <h2>{APP_NAME}</h2>
            <div class="topbar-tools">
              <label for="primary_language">语言 Language</label>
              <select id="primary_language">{language_options_html}</select>
            </div>
          </div>
          <div id="update-banner" class="update-banner" hidden>
            <div>
              <div class="update-title" id="update-title">发现新版本 Update available</div>
              <div class="update-message" id="update-message"></div>
            </div>
            <button id="btn_upgrade" class="primary">升级 Update</button>
          </div>

          <fieldset id="run_settings_panel">
            <legend id="run_settings_legend">运行配置 Run Settings</legend>

           <details class="box search-panel" id="search_panel" open>
             <summary>搜索 Search</summary>
             <div class="search-head">
               <div>
                 <div class="search-title">空房检索条件</div>
                 <div class="search-subtitle">选择日期、入住条件和酒店范围；启动后会自动写入搜索记录。</div>
               </div>
               <div class="quick-actions">
                 <button id="btn_today">今晚 Tonight</button>
                 <button id="btn_tomorrow">明晚 Tomorrow</button>
                 <button id="btn_weekend">周末 Weekend</button>
               </div>
             </div>

             <div class='search-grid'>
               <div class="control-box">
                 <label>入住 Check-in</label>
                 <input id='start_date' type='date' value='{_html_attr(cfg.start_date)}'>
               </div>
               <div class="control-box">
                 <label>退房 Check-out</label>
                 <input id='end_date' type='date' value='{_html_attr(cfg.end_date)}'>
               </div>
               <div class="control-box">
                 <label>人数 People</label>
                 <input id='people' type='number' min='1' max='5' step='1' value='{cfg.people}'>
               </div>
               <div class="control-box">
                 <label>房间 Rooms</label>
                 <input id='rooms' type='number' min='1' max='9' step='1' value='{cfg.rooms}'>
               </div>
               <div class="control-box wide">
                 <label>吸烟 Smoking</label>
                 <select id='smoking'>
                   <option value='noSmoking' {'selected' if cfg.smoking == 'noSmoking' else ''}>无烟房 Non-Smoking</option>
                   <option value='Smoking'   {'selected' if cfg.smoking == 'Smoking' else ''}>吸烟房 Smoking</option>
                   <option value='all'       {'selected' if cfg.smoking == 'all' else ''}>不限制 Any</option>
                 </select>
               </div>
               <div class="control-box">
                 <label>房型 Room Type</label>
                 <select id="room_requirement">
                   <option value="any"   {'selected' if current_room_requirement == 'any' else ''}>不限制 Any</option>
                   <option value="single"{'selected' if current_room_requirement == 'single' else ''}>单人房 Single</option>
                   <option value="double"{'selected' if current_room_requirement == 'double' else ''}>大床房 Double</option>
                   <option value="twin"  {'selected' if current_room_requirement == 'twin' else ''}>双床房 Twin</option>
                 </select>
               </div>
               <div class="control-box">
                 <label>会员状态 Membership</label>
                 <select id="membership_status">
                   <option value="member" {'selected' if current_membership_status == 'member' else ''}>会员 Member</option>
                   <option value="non_member" {'selected' if current_membership_status == 'non_member' else ''}>非会员 Non-member</option>
                   <option value="unknown" {'selected' if current_membership_status == 'unknown' else ''}>未知 Unknown</option>
                 </select>
               </div>
             </div>

             <details class="box" id="area_picker_panel" open>
               <summary>区域酒店搜索 Area Hotel Picker</summary>
               <div class="area-toolbar">
                 <div class="mode-tabs" id="hotel_picker_mode_tabs">
                   <label><input type="radio" name="hotel_picker_mode" value="area" {'checked' if getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE) != "radius" else ''}> 区域模式 Area</label>
                   <label><input type="radio" name="hotel_picker_mode" value="radius" {'checked' if getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE) == "radius" else ''}> 方圆模式 Radius</label>
                 </div>
               </div>
               <div id="area_mode_panel" class="picker-mode">
                 <div class="row">
                   <div>
                     <label>大区域 Region</label>
                     <select id="area_region">
                       <option value="">请选择 Select Region</option>
                     </select>
                   </div>
                   <div>
                     <label>详细区域 Detail Area</label>
                     <select id="area_detail" disabled>
                       <option value="">先选择大区域 Select a region first</option>
                     </select>
                   </div>
                 </div>
                 <div class="area-toolbar">
                   <button id="btn_area_load" class="primary">加载酒店 Load Hotels</button>
                 </div>
               </div>
               <div id="radius_mode_panel" class="picker-mode">
                 <div class="radius-grid">
                   <div>
                     <label>地名地址或者坐标 Place, Address, or Coordinates</label>
                     <input id="radius_query" type="text" value="{_html_attr(getattr(cfg, 'radius_query', ''))}" placeholder="东京站 / Tokyo Station / 35.6812,139.7671">
                   </div>
                   <div>
                     <label>方圆半径 Radius</label>
                     <input id="radius_km" type="range" min="1" max="50" step="1" value="{getattr(cfg, 'radius_km', DEFAULT_RADIUS_KM)}">
                     <div class="help">当前 Current: <b><span id="radius_km_val">{getattr(cfg, 'radius_km', DEFAULT_RADIUS_KM)}</span></b> km</div>
                   </div>
                 </div>
                 <input id="radius_lat" type="hidden" value="{getattr(cfg, 'radius_lat', '') if getattr(cfg, 'radius_lat', None) is not None else ''}">
                 <input id="radius_lng" type="hidden" value="{getattr(cfg, 'radius_lng', '') if getattr(cfg, 'radius_lng', None) is not None else ''}">
                 <div class="area-toolbar">
                   <button id="btn_radius_load" class="primary">查找附近酒店 Load Nearby</button>
                   <span class="help">地址会优先通过 OpenStreetMap/Nominatim 解析；坐标可直接本地解析。</span>
                 </div>
               </div>
               <div class="area-toolbar">
                 <button id="btn_area_all">全选 Select All</button>
                 <button id="btn_area_none">全不选 Select None</button>
                 <span class="help" id="area_status">选择大区域；详细区域可不选，默认加载整个大区域。勾选酒店后直接点击 Start 搜索。</span>
               </div>
               <input id="area_filter" class="hotel-filter" type="text" placeholder="过滤酒店中文/英文名或编号 Filter by Chinese/English hotel name or code">
	               <div id="area_hotels" class="hotel-picker">
	                 <div class="hotel-picker-empty">尚未加载酒店 No hotels loaded yet</div>
	               </div>
	               <div id="area_map_panel" class="selected-map-panel" hidden>
	                 <div class="selected-map-head">
	                   <div>
	                     <div class="selected-map-title">已选酒店地图 Selected Hotel Map</div>
	                     <div class="help" id="area_map_status">地图会显示当前已勾选且带坐标的酒店。</div>
	                   </div>
	                 </div>
	                 <div id="area_selected_map" class="selected-map-canvas"></div>
	               </div>
	             </details>

             <details class="box">
               <summary>搜索记录 Search History</summary>
               <div class="area-toolbar">
                 <button id="btn_history_refresh">刷新 Refresh</button>
                 <button id="btn_history_clear" class="danger">清空 Clear</button>
                 <span class="help">最多显示最近 10 条；完全相同设定不会重复记录。</span>
               </div>
               <div id="search_history" class="history-list">
                 <div class="history-empty">暂无搜索记录 No history yet</div>
               </div>
             </details>
           </details>

            <section class="run-panel">
              <div class="run-top">
                <div>
                  <div class="run-title">启动与监控 Run Control</div>
                  <div class="run-subtitle">启动后按当前搜索范围循环检索；运行中可以停止、保存配置或更新酒店库。</div>
                </div>
                <div class="run-actions">
                  <button class='primary' id='btn_start'>启动 Start</button>
                  <button class='danger' id='btn_stop'>停止 Stop</button>
                  <button id='btn_default'>默认 Default</button>
                </div>
              </div>

              <div class="status-grid">
                <div class="metric">
                  <span>状态 Status</span>
                  <b><span class='pill {('on' if (_worker_thread and _worker_thread.is_alive()) else 'off')}' id='running-pill'>{('RUNNING 运行中' if (_worker_thread and _worker_thread.is_alive()) else 'STOPPED 已停止')}</span></b>
                </div>
                <div class="metric">
                  <span>追踪轮次 Loop</span>
                  <b id='round-num'>0</b>
                </div>
                <div class="metric">
                  <span>本轮进度 Progress</span>
                  <b id='progress-ratio'>0 / 0</b>
                </div>
                <div class="metric">
                  <span>总耗时 Uptime</span>
                  <b id='uptime-text'>0s</b>
                </div>
              </div>

              <div class="progress-track">
                <div id='prog-bar' class="progress-fill"></div>
              </div>
              <div class="run-meta">
                <span id='prog-text'>进度 Progress: 0 / 0 (0%)</span>
                <span id='time-text'>耗时 Loop elapsed: 0s | 总耗时 Uptime: 0s</span>
                <span id='action-text'>状态 Current: (idle)</span>
              </div>
              <div id='msg' class='notice success'></div>
              <div id='err' class='notice error'></div>
            </section>
          </fieldset>

          <section class="results-panel">
            <div class="results-head">
              <div>
                <div class="results-title">搜索结果 Search Results</div>
              </div>
              <div class="results-summary">
                <div class="result-stat good"><span>有房 Available</span><b id="stat-available">0</b></div>
                <div class="result-stat bad"><span>无房 Unavailable</span><b id="stat-unavailable">0</b></div>
                <div class="result-stat warn"><span>需确认 Check</span><b id="stat-unknown">0</b></div>
                <div class="result-stat"><span>总计 Total</span><b id="stat-total">0</b></div>
              </div>
            </div>

            <div class="results-table-wrap">
              <table class="result-table">
                <thead>
                  <tr>
                    <th style="width:110px">编号 Code</th>
                    <th>酒店 Hotel</th>
                    <th style="width:130px">状态 Status</th>
                    <th style="width:140px">最低价 Min Price</th>
                    <th style="width:90px">剩余 Left</th>
                    <th style="width:220px">房型 Room Type</th>
                  </tr>
                </thead>
                <tbody id='results-body'>{''.join(rows) or '<tr><td colspan=6 class="empty-results">暂无结果 No data yet</td></tr>'}</tbody>
              </table>
            </div>

            <details class="result-log-panel">
              <summary>搜索结果日志 Search Result Log</summary>
              <div class="results-table-wrap">
                <table class="result-table result-log-table">
                  <thead>
                    <tr>
                      <th style="width:110px">编号 Code</th>
                      <th>酒店 Hotel</th>
                      <th style="width:170px">空房出现时间 Available Since</th>
                      <th style="width:150px">有效持续时间 Duration</th>
                      <th style="width:140px">价格 Price</th>
                      <th style="width:220px">房型 Room Type</th>
                    </tr>
                  </thead>
                  <tbody id="availability-log-body"><tr><td colspan=6 class="empty-results">暂无日志 No log yet</td></tr></tbody>
                </table>
              </div>
            </details>

            <div class="push-status-panel">
              <div class="push-status-head">
                <div>
                  <div class="push-title">推送状态 Notification Status</div>
                  <div class="push-subtitle">显示每个推送方式是否启用，以及最近一次实时推送状态。</div>
                </div>
              </div>
              <div class="push-grid" id="push-status-grid">
                <div class="push-card">
                  <div class="push-name">加载中 Loading</div>
                  <div class="push-enabled">等待状态同步 Waiting for status</div>
                  <span class="push-chip waiting">等待 Waiting</span>
                </div>
              </div>
            </div>
          </section>

            <details class="box settings-panel">
              <summary>搜索设定 Search Settings</summary>
              <div class="settings-note">引擎、检索节奏和智能并行集中在这里。智能并行仅用于 HTTP/API，并会错峰请求。</div>
              <div class="settings-grid">
                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="HTTP/API 是默认推荐：轻量、速度快、资源占用低；当接口解析失败时会自动尝试回退 Playwright。Playwright 更接近真实浏览器，适合官网结构变化或 HTTP 失败时使用，但更重。">引擎 Engine</h3>
                  <label>检索引擎 Search Engine</label>
                  <select id='engine'>
                    <option value='http' {'selected' if getattr(cfg,'engine','http') == 'http' else ''}>HTTP/API (推荐轻量/Recommended)</option>
                    <option value='playwright' {'selected' if getattr(cfg,'engine','http') == 'playwright' else ''} {'disabled' if not _HAS_PLAYWRIGHT else ''}>Playwright (兼容/Stable)</option>
                  </select>
                  <div class='help'>HTTP/API 请求更少更快；失败时会尝试回退 Playwright。</div>
                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="仅 HTTP/API 生效。会把酒店分成 1-3 条检索线并错峰启动，同时放大每条线的间隔，兼顾效率和请求节奏。默认 1 条；酒店较多时再提高到 2-3 条。">智能并行 Smart Parallel</h3>
                  <label class="inline"><input id='smart_parallel_enabled' type='checkbox' {'checked' if getattr(cfg, "smart_parallel_enabled", False) else ''}> 启用智能并行 Enable</label>
                  <label>并行线数 Workers</label>
                  <input id='smart_parallel_workers' type='range' min='1' max='3' step='1' value='{getattr(cfg, "smart_parallel_workers", DEFAULT_SMART_PARALLEL_WORKERS)}'>
                  <div class='help'>当前 Current: <b><span id="smart_parallel_workers_val">{getattr(cfg, "smart_parallel_workers", DEFAULT_SMART_PARALLEL_WORKERS)}</span></b>（仅 HTTP/API 生效；错峰启动并放大单线间隔）</div>
                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="每轮检索间隔控制两轮之间等待多久；每家酒店基础间隔控制同一检索线内访问频率；随机抖动会让间隔更自然。更稳妥的配置是每轮 120 秒以上、单店 2-5 秒并保留 30-50% 抖动。">检索节奏 Scan Cadence</h3>
                  <label>每轮检索间隔 Round Interval</label>
                  <input id='loop_interval' type='range' min='30' max='3600' step='30' value='{cfg.loop_interval_seconds}'>
                  <div class='help'>当前 Current: <b><span id="loop_interval_val">{cfg.loop_interval_seconds}</span></b> 秒 sec（建议 120 秒以上 / 120+ recommended）</div>
                  <label>每家酒店基础间隔 Per-hotel Base Delay</label>
                  <input id='per_hotel_delay' type='range' min='1' max='60' step='1' value='{cfg.per_hotel_delay_seconds}'>
                  <div class='help'>当前 Current: <b><span id="per_hotel_delay_val">{cfg.per_hotel_delay_seconds}</span></b> 秒 sec</div>
                  <label>随机抖动 Request Jitter</label>
                  <input id='request_jitter' type='range' min='0' max='100' step='5' value='{getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT)}'>
                  <div class='help'>当前 Current: <b><span id="request_jitter_val">{getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT)}</span></b>%</div>
                </div>

              </div>
            </details>

            <details class="box settings-panel">
              <summary>推送设定 Push Settings</summary>
              <div class="settings-note">空房、重复提醒、无房变化和启动通知会发送到所有已启用渠道。</div>
              <div class="settings-grid">
	                <div class="settings-card">
	                  <h3 class="info-title" tabindex="0" data-tip="控制发现空房后的重复提醒。重复提醒次数为首次提醒后的追加提醒次数；最右侧 INF 表示持续提醒。冷却时间用于避免同一酒店短时间反复推送，建议 300 秒以上。">提醒策略 Reminder Policy</h3>
	                  <div class="section-label" id="notify_events_title">推送事件 Notification Events</div>
	                  <div class="switch-list">
	                    <label class="inline"><input id='notify_available' type='checkbox' {'checked' if getattr(cfg, "notify_available", DEFAULT_NOTIFY_AVAILABLE) else ''}> 房源可用提醒 Room Available</label>
	                    <label class="inline"><input id='notify_unavailable' type='checkbox' {'checked' if getattr(cfg, "notify_unavailable", DEFAULT_NOTIFY_UNAVAILABLE) else ''}> 房源不再可用提醒 No Longer Available</label>
	                    <label class="inline"><input id='notify_availability_count_change' type='checkbox' {'checked' if getattr(cfg, "notify_availability_count_change", DEFAULT_NOTIFY_AVAILABILITY_COUNT_CHANGE) else ''}> 可用房间数量变动提醒 Room Count Change</label>
	                    <label class="inline"><input id='notify_start' type='checkbox' {'checked' if getattr(cfg, "notify_start", DEFAULT_NOTIFY_START) else ''}> 启动搜索提醒 Start Search</label>
	                    <label class="inline"><input id='notify_stop' type='checkbox' {'checked' if getattr(cfg, "notify_stop", DEFAULT_NOTIFY_STOP) else ''}> 停止搜索提醒 Stop Search</label>
	                    <label class="inline"><input id='notify_search_error' type='checkbox' {'checked' if getattr(cfg, "notify_search_error", DEFAULT_NOTIFY_SEARCH_ERROR) else ''}> 搜索异常提醒 Search Check</label>
	                  </div>
	                  <div class="section-label" id="repeat_reminder_title">重复提醒 Repeat Reminder</div>
	                  <label>重复提醒次数 Reminder Repeat Count</label>
                  <input id='alert_repeat' type='range' min='0' max='11' step='1' value='{cfg.available_alert_repeat}'>
                  <div class='help'>当前 Current: <b><span id="alert_repeat_val">{cfg.available_alert_repeat}</span></b> 次 Time(s)</div>
                  <label>重复提醒冷却 Reminder Cooldown</label>
                  <input id='alert_interval' type='range' min='60' max='86400' step='60' value='{cfg.available_alert_repeat_interval_sec}'>
                  <div class='help'>当前 Current: <b><span id="alert_interval_val">{cfg.available_alert_repeat_interval_sec}</span></b> 秒 sec</div>
                </div>
                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="适合 iPhone/iPad。步骤：1. iPhone/iPad 安装 Bark App。2. 复制 App 首页的 Device Key。3. 填入 Bark Key。4. 公共服务保持默认 Bark Server；自建服务则填你的服务器地址。5. 勾选启用后启动搜索。">Bark</h3>
                  <label class="inline"><input id='enable_bark' type='checkbox' {'checked' if getattr(cfg, "enable_bark", False) else ''}> 启用 Bark 推送 Enable Bark</label>
                  <label>Bark Key</label>
                  <input id='bark_key' type='password' value='' placeholder='Bark device key (leave blank to keep saved value)'>
                  <label>Bark Server</label>
                  <input id='bark_server' type='text' value='{_html_attr(getattr(cfg, "bark_server", DEFAULT_BARK_SERVER))}' placeholder='https://api.day.app'>
                  <label class="inline"><input id='bark_critical_enabled' type='checkbox' {'checked' if getattr(cfg, "bark_critical_enabled", DEFAULT_BARK_CRITICAL_ENABLED) else ''}> iPhone Critical Alert</label>
                  <div class='help'>Critical Alert 会忽略 Silent 和 DND modes。启用后会把房源信息作为 Critical Alert 发送一次。</div>
                  <label>Critical Alert 音量 Volume</label>
                  <input id='bark_critical_volume' type='range' min='0' max='10' step='1' value='{getattr(cfg, "bark_critical_volume", DEFAULT_BARK_CRITICAL_VOLUME)}'>
                  <div class='help'>当前 Current: <b><span id="bark_critical_volume_val">{getattr(cfg, "bark_critical_volume", DEFAULT_BARK_CRITICAL_VOLUME)}</span></b> / 10</div>
                  <label>Critical Alert 声音 Sound</label>
                  <input id='bark_critical_sound' type='text' list='bark_sound_options' value='{_html_attr(getattr(cfg, "bark_critical_sound", DEFAULT_BARK_CRITICAL_SOUND) or DEFAULT_BARK_CRITICAL_SOUND)}' placeholder='alarm'>
                  <datalist id='bark_sound_options'>
                    <option value='alarm'>
                    <option value='anticipate'>
                    <option value='bell'>
                    <option value='birdsong'>
                    <option value='calypso'>
                    <option value='chime'>
                    <option value='electronic'>
                    <option value='glass'>
                    <option value='minuet'>
                    <option value='multiwayinvitation'>
                    <option value='newmail'>
                    <option value='newsflash'>
                    <option value='noir'>
                    <option value='shake'>
                    <option value='sherwoodforest'>
                    <option value='spell'>
                    <option value='suspense'>
                    <option value='telegraph'>
                    <option value='tiptoes'>
                    <option value='typewriters'>
                    <option value='update'>
                  </datalist>
	                  <div class='help'>Critical Alert 默认使用 alarm。请确认 iOS Settings &gt; Notifications &gt; Bark 已允许 Critical Alerts 和 Sounds。</div>
	                  <div class="area-toolbar">
	                    <button id="btn_bark_test">发送 Bark 测试 Test Bark</button>
	                    <button id="btn_bark_sound_test">应用/测试声音 Apply Sound</button>
	                  </div>
	                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="适合微信推送。步骤：1. 打开 Server 酱官网并用微信登录。2. 绑定微信推送通道。3. 在 SendKey 页面复制 SCT 开头的 SendKey。4. 粘贴到这里。5. 勾选启用后启动搜索。推送失败时请检查 SendKey、账号额度和网络连通性。">Server 酱</h3>
                  <label class="inline"><input id='enable_serverchan' type='checkbox' {'checked' if getattr(cfg, "enable_serverchan", False) else ''}> 启用 Server 酱 Enable ServerChan</label>
                  <label>SendKey</label>
                  <input id='serverchan_sendkey' type='password' value='' placeholder='SCT... (leave blank to keep saved value)'>
                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="步骤：1. 在 Telegram 搜索 BotFather。2. 使用 /newbot 创建机器人并复制 Bot Token。3. 给机器人发一条消息，或把机器人加入群组。4. 获取 Chat ID 后填入。5. 勾选启用后启动搜索。群组通常需要允许机器人发送消息。">Telegram Bot</h3>
                  <label class="inline"><input id='enable_telegram' type='checkbox' {'checked' if cfg.enable_telegram else ''}> 启用 Telegram Enable</label>
                  <label>Bot Token</label>
                  <input id='bot_token' type='password' value='' placeholder='BOT_TOKEN (leave blank to keep saved value)'>
                  <label>Chat ID</label>
                  <input id='chat_id' type='text' value='{_html_attr(cfg.chat_id)}' placeholder='CHAT_ID'>
                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="在本机弹出系统通知。步骤：1. 勾选启用本地通知。2. 点击“发送测试通知”。3. 如果 macOS 没弹窗，到 System Settings > Notifications 允许 Terminal / Python / osascript。4. 测试成功后启动搜索即可。正式空房提醒支持多行内容。">本地通知 Local</h3>
                  <label class="inline"><input id='enable_local' type='checkbox' {'checked' if cfg.enable_local else ''}> 启用本地通知 Enable Local</label>
                  <div class="area-toolbar">
                    <button id="btn_local_test">发送测试通知 Test Notification</button>
                  </div>
                  <div class='help'>macOS 首次使用可能需要在 System Settings &gt; Notifications 中允许 Terminal / Python / osascript 通知。</div>
                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="使用 SMTP 发送邮件。步骤：1. 在邮箱后台开启 SMTP。2. 生成应用专用密码。3. 填 SMTP Host、Port、Username、Password。4. 填 From 和 To。5. 465 通常启用 SSL/TLS；587 通常也可启用 TLS。6. 勾选启用后启动搜索。">Email</h3>
                  <label class="inline"><input id='enable_email' type='checkbox' {'checked' if cfg.enable_email else ''}> 启用邮件推送 Enable Email</label>
                  <div class="row">
                    <div>
                      <label>SMTP Host</label>
                      <input id='smtp_host' type='text' value='{_html_attr(cfg.smtp_host)}' placeholder='smtp.example.com'>
                    </div>
                    <div>
                      <label>SMTP Port</label>
                      <input id='smtp_port' type='number' min='1' step='1' value='{cfg.smtp_port}'>
                    </div>
                  </div>
                  <label class="inline"><input id='smtp_tls' type='checkbox' {'checked' if cfg.smtp_tls else ''}> Use SSL / TLS</label>
                  <label>SMTP Username</label>
                  <input id='smtp_user' type='text' value='{_html_attr(cfg.smtp_user)}' placeholder='user@example.com'>
                  <label>SMTP Password</label>
                  <input id='smtp_pass' type='password' value='' placeholder='app password (leave blank to keep saved value)'>
                  <label>From</label>
                  <input id='email_from' type='text' value='{_html_attr(cfg.email_from)}' placeholder='sender@example.com'>
                  <label>To (comma separated)</label>
                  <input id='email_to' type='text' value='{_html_attr(cfg.email_to)}' placeholder='a@b.com, c@d.com'>
                </div>
              </div>
            </details>


          <footer>
            <span id="footer-app-name">{APP_NAME}</span> — Version: <b>{APP_VERSION}</b> · Author:
            <a href="https://space.bilibili.com/4955287" target="_blank" rel="noreferrer noopener"><b>{APP_AUTHOR}</b></a>
            · Github:
            <a href="https://github.com/JellyNekoNeko/toyoko-tracker" target="_blank" rel="noreferrer noopener"><b>JellyNekoNeko/toyoko-tracker</b></a>
          </footer>
        """

    html += """
          <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
          <script src="/static/app.js"></script>
        </body></html>
        """
    return Response(html, mimetype="text/html")

 # ---- Hotel name → code mapping (toyoko_hotel_names.json) ----
HOTEL_NAME_JSON = os.path.join(BASE_DIR, "toyoko_hotel_names.json")
AREA_INDEX_JSON = os.path.join(BASE_DIR, "toyoko_area_index.json")
_HOTEL_NAME_CACHE = None  # type: Optional[dict]
_HOTEL_NAME_CACHE_MTIME = 0.0
_AREA_INDEX_CACHE = None  # type: Optional[dict]
_AREA_INDEX_CACHE_MTIME = 0.0
_AREA_HOTELS_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_RADIUS_BUILD_LOCK = threading.Lock()

def _normalize_name(s: str) -> str:
    """Normalize hotel name for matching (remove spaces/punct, lowercase)."""
    if not isinstance(s, str):
        return ""
    s = s.strip().lower()
    # remove common prefixes
    s = s.replace("toyoko inn", "").replace("東横inn", "").replace("東橫inn", "")
    # remove spaces and punctuation-like chars
    s = re.sub(r"[\s\u3000\-_.·・,，。!！:：;；'\"“”‘’()（）\[\]{}#@/\\]+", "", s)
    return s

def _load_hotel_name_index():
    """Load/refresh hotel name library; returns (exact_map, searchable_list).
    exact_map: normalized name -> code
    searchable_list: list of (code, normalized_full_name_concatenated)
    """
    global _HOTEL_NAME_CACHE, _HOTEL_NAME_CACHE_MTIME
    try:
        mtime = os.path.getmtime(HOTEL_NAME_JSON)
    except Exception:
        return {}, []
    if _HOTEL_NAME_CACHE is not None and abs(mtime - _HOTEL_NAME_CACHE_MTIME) < 1e-6:
        return _HOTEL_NAME_CACHE["exact"], _HOTEL_NAME_CACHE["list"]
    try:
        with open(HOTEL_NAME_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}, []

    exact = {}
    by_code = {}
    search_list = []
    for row in data:
        code = str(row.get("code") or "").zfill(5)
        by_code[code] = row
        names = []
        for k, v in row.items():
            if k.startswith("name_") and v:
                names.append(str(v))
        # build exact keys on each field
        for n in names:
            key = _normalize_name(n)
            if key:
                exact.setdefault(key, code)
        # build a long string for substring search
        joined = _normalize_name("".join(names))
        search_list.append((code, joined))
    _HOTEL_NAME_CACHE = {"exact": exact, "list": search_list, "by_code": by_code}
    _HOTEL_NAME_CACHE_MTIME = mtime
    return exact, search_list


def _hotel_names_by_code(code: str, fallback: Optional[str] = None, primary_language: Optional[str] = None) -> Dict[str, str]:
    try:
        _load_hotel_name_index()
        row = (_HOTEL_NAME_CACHE or {}).get("by_code", {}).get(str(code).zfill(5), {})
        lang = _normalize_primary_language(primary_language)
        lang_info = LANGUAGE_OPTIONS[lang]
        primary = row.get(lang_info["name_key"]) or row.get(lang_info["short_key"]) or ""
        zh = row.get("name_full_zh_cn") or row.get("name_zh_cn") or ""
        en = row.get("name_full_en") or row.get("name_en") or fallback or ""
        display = primary and en and f"{primary} / {en}" or primary or en or fallback or ""
        return {
            "primary": primary,
            "primary_language": lang,
            "zh": zh,
            "en": en,
            "display": display,
            "zh_cn": row.get("name_full_zh_cn") or row.get("name_zh_cn") or "",
            "zh_tw": row.get("name_full_zh_tw") or row.get("name_zh_tw") or "",
            "ja": row.get("name_full_ja") or row.get("name_ja") or "",
            "ko": row.get("name_full_ko") or row.get("name_ko") or "",
        }
    except Exception:
        lang = _normalize_primary_language(primary_language)
        return {"primary": "", "primary_language": lang, "zh": "", "en": fallback or "", "display": fallback or ""}

def _codes_from_name_input(text: str) -> list:
    """Convert free text that may contain 5-digit codes and/or hotel names into codes.
    - Accept tokens separated by comma/space/semicolon/newline
    - For a 5-digit number, keep as-is.
    - Otherwise, try exact name match; if not, use substring search to include all matched codes.
    Return a unique list preserving insertion order.
    """
    if not isinstance(text, str):
        return []
    exact, search_list = _load_hotel_name_index()
    out = []
    seen = set()
    # split by commas/semicolons/newlines; keep multi-word tokens (names)
    for raw in re.split(r"[\n,;]+", text):
        token = raw.strip()
        if not token:
            continue
        # if token still has multiple spaces, keep them for name; but also test if it's mostly digits
        digits = re.sub(r"\D", "", token)
        if len(token) == 5 and token.isdigit():
            code = token
            if code not in seen:
                seen.add(code)
                out.append(code)
            continue
        if len(digits) == 5 and digits.isdigit():
            code = digits
            if code not in seen:
                seen.add(code)
                out.append(code)
            continue
        key = _normalize_name(token)
        # exact field match first
        code = exact.get(key)
        if code and code not in seen:
            seen.add(code)
            out.append(code)
            continue
        # substring search across concatenated names
        if key:
            for c, joined in search_list:
                if key in joined and c not in seen:
                    seen.add(c)
                    out.append(c)
    return out


def _load_area_index() -> Dict[str, Any]:
    global _AREA_INDEX_CACHE, _AREA_INDEX_CACHE_MTIME
    try:
        mtime = os.path.getmtime(AREA_INDEX_JSON)
    except Exception:
        return {"regions": []}
    if _AREA_INDEX_CACHE is not None and abs(mtime - _AREA_INDEX_CACHE_MTIME) < 1e-6:
        return _AREA_INDEX_CACHE
    try:
        with open(AREA_INDEX_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"regions": []}
    _AREA_INDEX_CACHE = data
    _AREA_INDEX_CACHE_MTIME = mtime
    return data


def _find_area_selection(region_id: Optional[int], detail_id: str) -> Tuple[str, List[Tuple[str, int]]]:
    index = _load_area_index()
    regions = index.get("regions") if isinstance(index, dict) else []
    region = next((r for r in regions or [] if int(r.get("id", -1)) == int(region_id or -1)), None)
    if not region:
        return "none", []
    detail_id = str(detail_id or "")
    if detail_id.startswith("area-"):
        try:
            return detail_id, [("area", int(detail_id.split("-", 1)[1]))]
        except Exception:
            return "none", []
    if detail_id.startswith("pref-"):
        try:
            return detail_id, [("prefecture", int(detail_id.split("-", 1)[1]))]
        except Exception:
            return "none", []
    selectors = []
    for pref in region.get("prefectures") or []:
        try:
            selectors.append(("prefecture", int(pref.get("id"))))
        except Exception:
            continue
    return f"region-{region.get('id')}", selectors


def _extract_search_hotels_from_html(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
        hotels = data["props"]["pageProps"]["searchResponse"].get("hotels") or []
    except Exception:
        return []
    out = []
    seen = set()
    for h in hotels:
        code = str(h.get("hotelCode") or "").zfill(5)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append({
            "code": code,
            "name": h.get("name") or "",
            "name_en": h.get("name") or "",
            "status": h.get("hotelStatus") or "",
            "lat": _optional_float(h.get("latDegree")),
            "lng": _optional_float(h.get("lngDegree")),
            "url": f"https://www.toyoko-inn.com/eng/search/detail/{code}/",
            "map_url": (
                h.get("googleMapUrl")
                or (
                    f"https://www.google.com/maps/search/?api=1&query={h.get('latDegree')},{h.get('lngDegree')}"
                    if h.get("latDegree") is not None and h.get("lngDegree") is not None
                    else ""
                )
            ),
        })
    return out


def _fetch_hotels_for_selector_locale(kind: str, selector_id: int, locale_path: str) -> List[Dict[str, Any]]:
    params = {
        kind: int(selector_id),
        "start": DEFAULT_START_DATE,
        "end": DEFAULT_END_DATE,
        "people": 1,
        "room": 1,
        "smoking": "all",
    }
    url = f"https://www.toyoko-inn.com/{locale_path}/search/result/"
    resp = requests.get(url, params=params, headers=HEADERS, timeout=12)
    resp.raise_for_status()
    return _extract_search_hotels_from_html(resp.text)


def _fetch_hotels_for_selector(kind: str, selector_id: int) -> List[Dict[str, Any]]:
    cache_key = f"{kind}:{selector_id}"
    cached = _AREA_HOTELS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    en_hotels = _fetch_hotels_for_selector_locale(kind, selector_id, "eng")
    try:
        zh_hotels = _fetch_hotels_for_selector_locale(kind, selector_id, "china_cn")
    except Exception:
        zh_hotels = []
    zh_by_code = {h["code"]: h for h in zh_hotels}
    hotels = []
    for h in en_hotels:
        zh = zh_by_code.get(h["code"], {})
        names = _hotel_names_by_code(h["code"], h.get("name"))
        h["name_en"] = h.get("name_en") or h.get("name") or ""
        h["name_zh"] = zh.get("name") or names.get("zh_cn") or ""
        h["name_zh_cn"] = names.get("zh_cn") or h["name_zh"]
        h["name_zh_tw"] = names.get("zh_tw") or ""
        h["name_ja"] = names.get("ja") or ""
        h["name_ko"] = names.get("ko") or ""
        hotels.append(h)
    _AREA_HOTELS_CACHE[cache_key] = hotels
    return hotels


def _hotel_for_primary_language(hotel: Dict[str, Any], primary_language: Optional[str]) -> Dict[str, Any]:
    lang = _normalize_primary_language(primary_language)
    names = _hotel_names_by_code(hotel.get("code", ""), hotel.get("name_en") or hotel.get("name"), lang)
    item = dict(hotel)
    item["name_primary"] = names.get("primary") or hotel.get(f"name_{lang}") or hotel.get("name_zh") or hotel.get("name_en") or hotel.get("name") or ""
    item["name_en"] = names.get("en") or hotel.get("name_en") or hotel.get("name") or ""
    item["name_zh"] = names.get("zh") or hotel.get("name_zh") or ""
    item["name_zh_cn"] = names.get("zh_cn") or hotel.get("name_zh_cn") or item["name_zh"]
    item["name_zh_tw"] = names.get("zh_tw") or hotel.get("name_zh_tw") or ""
    item["name_ja"] = names.get("ja") or hotel.get("name_ja") or ""
    item["name_ko"] = names.get("ko") or hotel.get("name_ko") or ""
    return item


def _hotels_for_area_selection(region_id: Optional[int], detail_id: str, primary_language: Optional[str] = None) -> List[Dict[str, Any]]:
    selection_key, selectors = _find_area_selection(region_id, detail_id)
    cached = _AREA_HOTELS_CACHE.get(selection_key)
    if cached is None:
        merged: Dict[str, Dict[str, Any]] = {}
        for kind, selector_id in selectors:
            for hotel in _fetch_hotels_for_selector(kind, selector_id):
                merged.setdefault(hotel["code"], hotel)
        cached = sorted(merged.values(), key=lambda x: x["code"])
        _AREA_HOTELS_CACHE[selection_key] = cached
    return [_hotel_for_primary_language(h, primary_language) for h in cached]


def _all_area_selectors() -> List[Tuple[str, int]]:
    index = _load_area_index()
    selectors: List[Tuple[str, int]] = []
    seen = set()
    for region in (index.get("regions") or []):
        for pref in (region.get("prefectures") or []):
            try:
                key = ("prefecture", int(pref.get("id")))
            except Exception:
                continue
            if key not in seen:
                seen.add(key)
                selectors.append(key)
    return selectors


def _all_hotels_for_radius(primary_language: Optional[str] = None) -> List[Dict[str, Any]]:
    cached = _AREA_HOTELS_CACHE.get("all")
    if cached is None:
        cached = _load_radius_hotels_cache()
        if cached is not None:
            _AREA_HOTELS_CACHE["all"] = cached
    if cached is None:
        with _RADIUS_BUILD_LOCK:
            cached = _AREA_HOTELS_CACHE.get("all") or _load_radius_hotels_cache()
            if cached is None:
                selectors = _all_area_selectors()
                merged: Dict[str, Dict[str, Any]] = {}
                _log(f"[radius] building hotel coordinate cache from {len(selectors)} selectors...")

                def fetch_one(selector: Tuple[str, int]) -> List[Dict[str, Any]]:
                    kind, selector_id = selector
                    try:
                        return _fetch_hotels_for_selector(kind, selector_id)
                    except Exception as e:
                        _log(f"[radius] selector {kind}:{selector_id} skipped: {e}")
                        return []

                with ThreadPoolExecutor(max_workers=6, thread_name_prefix="radius-hotels") as executor:
                    futures = [executor.submit(fetch_one, selector) for selector in selectors]
                    for idx, fut in enumerate(as_completed(futures), 1):
                        for hotel in fut.result():
                            if _optional_float(hotel.get("lat")) is not None and _optional_float(hotel.get("lng")) is not None:
                                merged.setdefault(hotel["code"], hotel)
                        if idx % 10 == 0 or idx == len(futures):
                            _log(f"[radius] coordinate cache progress: {idx}/{len(futures)} selectors, {len(merged)} hotels")
                cached = sorted(merged.values(), key=lambda x: x["code"])
                _AREA_HOTELS_CACHE["all"] = cached
                _save_radius_hotels_cache(cached)
    return [_hotel_for_primary_language(h, primary_language) for h in cached]


def _load_radius_hotels_cache() -> Optional[List[Dict[str, Any]]]:
    try:
        if not os.path.exists(RADIUS_HOTELS_CACHE_PATH):
            return None
        with open(RADIUS_HOTELS_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        hotels = data.get("hotels") if isinstance(data, dict) else None
        if isinstance(hotels, list) and hotels:
            _log(f"[radius] loaded coordinate cache: {len(hotels)} hotels")
            return [h for h in hotels if isinstance(h, dict)]
    except Exception as e:
        _log(f"[radius] load coordinate cache failed: {e}")
    return None


def _save_radius_hotels_cache(hotels: List[Dict[str, Any]]) -> None:
    try:
        _atomic_write_json(
            RADIUS_HOTELS_CACHE_PATH,
            {"generated_at": datetime.now().isoformat(timespec="seconds"), "hotels": hotels},
        )
        _log(f"[radius] saved coordinate cache: {len(hotels)} hotels")
    except Exception as e:
        _log(f"[radius] save coordinate cache failed: {e}")


def _parse_coordinate_query(text: str) -> Optional[Tuple[float, float]]:
    raw = unquote(str(text or "").strip())
    if not raw:
        return None
    patterns = [
        r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)(?:[,/]|$)",
        r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)",
        r"(?:q|query|ll)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
        r"^\s*(-?\d+(?:\.\d+)?)\s*[,，\s]\s*(-?\d+(?:\.\d+)?)\s*$",
    ]
    for pattern in patterns:
        m = re.search(pattern, raw)
        if not m:
            continue
        lat = float(m.group(1))
        lng = float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    return None


def _coordinate_is_japanish(lat: float, lng: float) -> bool:
    return 20.0 <= lat <= 46.5 and 122.0 <= lng <= 154.5


def _extract_maps_coordinates(*texts: str) -> Optional[Tuple[float, float]]:
    candidates: List[Tuple[float, float, int]] = []

    def add(lat: float, lng: float, score: int) -> None:
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            if _coordinate_is_japanish(lat, lng):
                score += 10
            candidates.append((lat, lng, score))

    for source in texts:
        text = unquote(str(source or ""))
        if not text:
            continue
        coord = _parse_coordinate_query(text)
        if coord:
            add(coord[0], coord[1], 100)
        for pattern, score in (
            (r"@(-?\d+\.\d+),(-?\d+\.\d+),", 95),
            (r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", 95),
            (r'"lat"\s*:\s*(-?\d+\.\d+)\s*,\s*"lng"\s*:\s*(-?\d+\.\d+)', 90),
            (r"\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]", 85),
            (r"\[(-?\d+\.\d+),(-?\d+\.\d+)\]", 20),
        ):
            for m in re.finditer(pattern, text):
                add(float(m.group(1)), float(m.group(2)), score)
        # Google internal arrays sometimes store longitude before latitude.
        for m in re.finditer(r"\[(-?\d+\.\d+),(-?\d+\.\d+),(-?\d+\.\d+)\]", text):
            a = float(m.group(1))
            b = float(m.group(2))
            c = float(m.group(3))
            if -180 <= a <= 180 and -90 <= b <= 90:
                add(b, a, 18)
            if -90 <= b <= 90 and -180 <= c <= 180:
                add(b, c, 18)

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[0][0], candidates[0][1]


def _geocode_nominatim(query: str) -> Tuple[float, float, str]:
    q = str(query or "").strip()
    if not q:
        raise ValueError("empty query")
    headers = {
        **HEADERS,
        "User-Agent": f"ToyokoChan/{APP_VERSION} (local hotel search tool)",
        "Accept-Language": "ja,en;q=0.9",
    }
    params = {
        "q": q,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "jp",
    }
    resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise ValueError("address not found by OpenStreetMap Nominatim")
    first = data[0]
    lat = float(first["lat"])
    lng = float(first["lon"])
    if -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng, "nominatim"
    raise ValueError("invalid Nominatim coordinates")


def _geocode_google_maps(query: str) -> Tuple[float, float, str]:
    coord = _parse_coordinate_query(query)
    if coord:
        return coord[0], coord[1], "coordinates"
    q = str(query or "").strip()
    if not q:
        raise ValueError("empty query")
    headers = dict(HEADERS)
    headers.setdefault("Accept-Language", "ja,en-US;q=0.9,en;q=0.8")
    urls = [
        "https://www.google.com/maps/search/" + quote(q),
        "https://www.google.com/maps/place/" + quote(q),
        "https://maps.google.com/maps?q=" + quote(q),
        "https://maps.google.com/maps?output=search&q=" + quote(q),
    ]
    last_error = None
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
            resp.raise_for_status()
            coord = _extract_maps_coordinates(resp.url, resp.text)
            if coord:
                return coord[0], coord[1], "google_maps"
        except Exception as e:
            last_error = e
            continue
    if last_error:
        _log(f"[radius] Google Maps geocode failed: {last_error}")
    raise ValueError("could not parse Google Maps coordinates")


def _geocode_location(query: str) -> Tuple[float, float, str]:
    coord = _parse_coordinate_query(query)
    if coord:
        return coord[0], coord[1], "coordinates"
    try:
        return _geocode_nominatim(query)
    except Exception as e:
        _log(f"[radius] Nominatim geocode failed: {e}")
    # Fallback only; the primary provider is OpenStreetMap/Nominatim.
    return _geocode_google_maps(query)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _hotels_within_radius(query: str, radius_km: int, primary_language: Optional[str] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    lat, lng, source = _geocode_location(query)
    radius = max(1, min(50, int(radius_km or DEFAULT_RADIUS_KM)))
    hotels = []
    for h in _all_hotels_for_radius(primary_language):
        hlat = _optional_float(h.get("lat"))
        hlng = _optional_float(h.get("lng"))
        if hlat is None or hlng is None:
            continue
        distance = _haversine_km(lat, lng, hlat, hlng)
        if distance <= radius:
            item = dict(h)
            item["distance_km"] = round(distance, 2)
            hotels.append(item)
    hotels.sort(key=lambda x: (float(x.get("distance_km") or 9999), str(x.get("code") or "")))
    center = {"lat": round(lat, 7), "lng": round(lng, 7), "source": source, "radius_km": radius}
    return center, hotels


def _int_from_payload(payload: Dict[str, Any], key: str, current: int, min_value: Optional[int] = None,
                      max_value: Optional[int] = None) -> int:
    if key not in payload:
        return current
    try:
        value = int(payload.get(key, current))
    except Exception:
        return current
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _apply_payload_to_config(cfg: AppConfig, payload: Dict[str, Any]) -> None:
    cfg.start_date = payload.get("start_date", cfg.start_date)
    cfg.end_date = payload.get("end_date", cfg.end_date)

    raw_codes = payload.get("hotel_codes_raw")
    if isinstance(raw_codes, str) and raw_codes.strip():
        cfg.hotel_codes = _codes_from_name_input(raw_codes)
    else:
        codes = payload.get("hotel_codes")
        if isinstance(codes, list) and all(isinstance(x, str) for x in codes):
            cfg.hotel_codes = codes

    cfg.area_region = str(payload.get("area_region", getattr(cfg, "area_region", "")) or "")
    cfg.area_detail = str(payload.get("area_detail", getattr(cfg, "area_detail", "")) or "")
    cfg.area_region_label = str(payload.get("area_region_label", getattr(cfg, "area_region_label", "")) or "")
    cfg.area_detail_label = str(payload.get("area_detail_label", getattr(cfg, "area_detail_label", "")) or "")
    cfg.search_mode = str(payload.get("search_mode", getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE)) or DEFAULT_SEARCH_MODE)
    if cfg.search_mode not in {"area", "radius"}:
        cfg.search_mode = DEFAULT_SEARCH_MODE
    cfg.radius_query = str(payload.get("radius_query", getattr(cfg, "radius_query", "")) or "")
    cfg.radius_lat = _optional_float(payload.get("radius_lat", getattr(cfg, "radius_lat", None)))
    cfg.radius_lng = _optional_float(payload.get("radius_lng", getattr(cfg, "radius_lng", None)))
    cfg.radius_km = _int_from_payload(payload, "radius_km", getattr(cfg, "radius_km", DEFAULT_RADIUS_KM), 1, 50)
    selected_hotels = _clean_selected_hotels(payload.get("selected_hotels"))
    cfg.primary_language = _normalize_primary_language(payload.get("primary_language", getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)))
    selected_hotels = _localize_selected_hotels(selected_hotels, cfg.primary_language)
    if selected_hotels:
        cfg.selected_hotels = selected_hotels
    elif cfg.hotel_codes:
        cfg.selected_hotels = _localize_selected_hotels([{"code": str(code).zfill(5)} for code in cfg.hotel_codes], cfg.primary_language)

    cfg.loop_interval_seconds = _int_from_payload(payload, "loop_interval_seconds", cfg.loop_interval_seconds, 30, 3600)
    cfg.per_hotel_delay_seconds = _int_from_payload(payload, "per_hotel_delay_seconds", cfg.per_hotel_delay_seconds, 1, 60)
    cfg.request_jitter_percent = _int_from_payload(
        payload,
        "request_jitter_percent",
        getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT),
        0,
        100,
    )
    cfg.available_alert_repeat = _int_from_payload(payload, "available_alert_repeat", cfg.available_alert_repeat, 0, 11)
    cfg.available_alert_repeat_interval_sec = _int_from_payload(
        payload, "available_alert_repeat_interval_sec", cfg.available_alert_repeat_interval_sec, 60, 86400
    )
    if "smart_parallel_enabled" in payload:
        cfg.smart_parallel_enabled = bool(payload["smart_parallel_enabled"])
    cfg.smart_parallel_workers = _int_from_payload(
        payload,
        "smart_parallel_workers",
        getattr(cfg, "smart_parallel_workers", DEFAULT_SMART_PARALLEL_WORKERS),
        1,
        3,
    )
    cfg.people = _int_from_payload(payload, "people", cfg.people, 1, 5)
    cfg.rooms = _int_from_payload(payload, "rooms", cfg.rooms, 1, 9)

    sm = str(payload.get("smoking", cfg.smoking))
    if sm in {"Smoking", "noSmoking", "all"}:
        cfg.smoking = sm
    ms = str(payload.get("membership_status", getattr(cfg, "membership_status", DEFAULT_MEMBERSHIP_STATUS)))
    if ms in {"member", "non_member", "unknown"}:
        cfg.membership_status = ms
    rr = str(payload.get("room_requirement", getattr(cfg, "room_requirement", getattr(cfg, "om_requirement", DEFAULT_ROOM_REQUIREMENT))))
    if rr in {"any", "single", "double", "twin"}:
        setattr(cfg, "room_requirement", rr)
        setattr(cfg, "om_requirement", rr)

    cfg.budget_enabled = False
    cfg.budget_limit = DEFAULT_BUDGET_LIMIT

    for key in (
        "enable_telegram", "enable_local", "enable_email", "enable_bark", "enable_serverchan",
        "bark_critical_enabled", "notify_available", "notify_unavailable", "notify_start",
        "notify_stop", "notify_search_error", "notify_availability_count_change",
    ):
        if key in payload:
            setattr(cfg, key, bool(payload[key]))

    for key in (
        "smtp_host", "smtp_user", "email_from", "email_to", "bark_server", "bark_critical_sound",
    ):
        if key in payload:
            setattr(cfg, key, payload[key])
    for key in _SECRET_CONFIG_FIELDS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            setattr(cfg, key, value.strip())
    if getattr(cfg, "enable_bark", False):
        ok, message = validate_bark_key(getattr(cfg, "bark_key", ""))
        if not ok:
            raise ValueError(message)
    cfg.bark_critical_volume = _int_from_payload(
        payload,
        "bark_critical_volume",
        getattr(cfg, "bark_critical_volume", DEFAULT_BARK_CRITICAL_VOLUME),
        0,
        10,
    )
    if "chat_id" in payload:
        cfg.chat_id = str(payload["chat_id"])
    cfg.smtp_port = _int_from_payload(payload, "smtp_port", cfg.smtp_port, 1, None)
    if "smtp_tls" in payload:
        cfg.smtp_tls = bool(payload["smtp_tls"])

    if "engine" in payload:
        eng = str(payload["engine"])
        if eng == "selenium":
            eng = DEFAULT_ENGINE
        if eng in {"playwright", "http"}:
            if eng == "playwright" and not _HAS_PLAYWRIGHT:
                eng = DEFAULT_ENGINE
            cfg.engine = eng


def start() -> Response:
        global _worker_thread, _RUN_REQUESTED
        payload = request.get_json(force=True, silent=True) or {}
        restarted = False

        if _worker_thread and _worker_thread.is_alive():
            restarted = True
            _RUN_REQUESTED = False
            _stop_event.set()
            _worker_thread.join(timeout=5)
            if _worker_thread and _worker_thread.is_alive():
                return jsonify({"ok": False, "message": "Could not stop current worker for restart"}), 409
            _worker_thread = None
            _stop_event.clear()

        try:
            with _CONFIG_LOCK:
                _apply_payload_to_config(_CONFIG, payload)
        except ValueError as e:
            return jsonify({"ok": False, "message": str(e), "error": str(e)}), 400

        with _CONFIG_LOCK:
            if not _CONFIG.hotel_codes:
                return jsonify({
                    "ok": False,
                    "message": "Please load and select hotels in Area Hotel Picker first.",
                }), 400

        # Mark that user explicitly wants the worker to run
        _RUN_REQUESTED = True

        # Start save to auto_save.json
        _save_config_to_file(AUTO_SAVE_PATH)
        _remember_search(payload, _CONFIG)

        # Reset and Restart worker
        _set_action(
            f"[start] hotels={len(_CONFIG.hotel_codes)} | {_CONFIG.start_date} → {_CONFIG.end_date} | people={_CONFIG.people}, rooms={_CONFIG.rooms}, smoking={_CONFIG.smoking}")

        _stop_event.set()
        if _worker_thread and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        _stop_event.clear()

        with _RESULTS_LOCK:
            global _LAST_RESULTS
            _LAST_RESULTS = []
        clear_alert_state()

        _worker_thread = threading.Thread(target=_worker_loop, name="checker-thread", daemon=True)
        _worker_thread.start()
        _log("Started worker.")
        _log(f"{APP_NAME} {APP_VERSION} · Author: {APP_AUTHOR}")

        try:
            with _CONFIG_LOCK:
                cfg_snapshot = deepcopy(_CONFIG)
            send_start_notifications(cfg_snapshot)
        except Exception as e:
            _log(f"[start] could not send start notifications: {e}")

        return jsonify({"ok": True, "message": "restarted" if restarted else "started", "restarted": restarted, "config": _public_config_dict(_CONFIG)})

def stop() -> Response:
        global _worker_thread, _RUN_REQUESTED
        _RUN_REQUESTED = False  # prevent worker from continuing or restarting
        _stop_event.set()
        if _worker_thread and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        _worker_thread = None
        with _PROGRESS_LOCK:
            _PROGRESS["round"] = 0
            _PROGRESS["done"] = 0
            _PROGRESS["total"] = 0
            _PROGRESS["phase"] = "idle"
            _PROGRESS["wait_started_mono"] = 0.0
            _PROGRESS["wait_total_sec"] = 0
            _PROGRESS["wait_elapsed_sec"] = 0
            _PROGRESS["round_started"] = 0.0
            _PROGRESS["round_started_mono"] = 0.0
        global _UPTIME_STARTED, _UPTIME_STARTED_MONO
        _UPTIME_STARTED = None
        _UPTIME_STARTED_MONO = None
        _set_action("Stopped worker.")
        _log("Stopped worker.")
        try:
            with _CONFIG_LOCK:
                cfg_snapshot = deepcopy(_CONFIG)
            send_stop_notifications(cfg_snapshot)
        except Exception as e:
            _log(f"[stop] could not send stop notifications: {e}")
        return jsonify({"ok": True, "message": "stopped"})


def local_notify_test() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        with _CONFIG_LOCK:
            if "enable_local" in payload:
                _CONFIG.enable_local = bool(payload.get("enable_local"))
            else:
                _CONFIG.enable_local = True
            cfg_snapshot = deepcopy(_CONFIG)
        notify_local(
            cfg_snapshot,
            "Toyoko Tracker test",
            f"Local notifications are enabled.\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        )
        return jsonify({"ok": True, "message": "test notification sent", "config": _public_config_dict(_CONFIG)})

def bark_notify_test() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        with _CONFIG_LOCK:
            if "enable_bark" in payload:
                _CONFIG.enable_bark = bool(payload.get("enable_bark"))
            else:
                _CONFIG.enable_bark = True
            bark_key = payload.get("bark_key")
            if isinstance(bark_key, str) and bark_key.strip():
                _CONFIG.bark_key = bark_key.strip()
            if payload.get("bark_server"):
                _CONFIG.bark_server = payload["bark_server"]
            if "bark_critical_sound" in payload:
                _CONFIG.bark_critical_sound = str(payload.get("bark_critical_sound") or "").strip()
            if "bark_critical_enabled" in payload:
                _CONFIG.bark_critical_enabled = bool(payload.get("bark_critical_enabled"))
            _CONFIG.bark_critical_volume = _int_from_payload(
                payload,
                "bark_critical_volume",
                getattr(_CONFIG, "bark_critical_volume", DEFAULT_BARK_CRITICAL_VOLUME),
                0,
                10,
            )
            cfg_snapshot = deepcopy(_CONFIG)
        from .notifications import notify_bark
        notify_bark(
            cfg_snapshot,
            "Toyoko Chan Bark test",
            "Bark test notification / Bark 测试通知",
        )
        return jsonify({"ok": True, "message": "bark test notification sent", "config": _public_config_dict(_CONFIG)})


def bark_sound_test() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        with _CONFIG_LOCK:
            _CONFIG.enable_bark = True
            _CONFIG.bark_critical_enabled = True
            bark_key = payload.get("bark_key")
            if isinstance(bark_key, str) and bark_key.strip():
                _CONFIG.bark_key = bark_key.strip()
            if payload.get("bark_server"):
                _CONFIG.bark_server = payload["bark_server"]
            sound = str(payload.get("bark_critical_sound") or DEFAULT_BARK_CRITICAL_SOUND).strip() or DEFAULT_BARK_CRITICAL_SOUND
            _CONFIG.bark_critical_sound = sound
            _CONFIG.bark_critical_volume = _int_from_payload(
                payload,
                "bark_critical_volume",
                getattr(_CONFIG, "bark_critical_volume", DEFAULT_BARK_CRITICAL_VOLUME),
                0,
                10,
            )
            cfg_snapshot = deepcopy(_CONFIG)
        _save_config_to_file(AUTO_SAVE_PATH)
        from .notifications import notify_bark
        notify_bark(
            cfg_snapshot,
            "Toyoko Chan Critical Sound Test",
            f"Critical Alert sound test / Critical Alert 声音测试\nSound: {cfg_snapshot.bark_critical_sound}\nVolume: {cfg_snapshot.bark_critical_volume}",
        )
        return jsonify({"ok": True, "message": "bark critical sound test sent", "config": _public_config_dict(_CONFIG)})

def status() -> Response:
        with _CONFIG_LOCK:
            cfg = _public_config_dict(_CONFIG)
        with _RESULTS_LOCK:
            results = [asdict(r) for r in _LAST_RESULTS]
        with _LOG_LOCK:
            logs = list(_LOG_LINES[-300:])
        with _PROGRESS_LOCK:
            progress = dict(_PROGRESS)

        now_ts = _now_wall()
        now_mono = _now_mono()

        rs_mono = float(progress.get("round_started_mono") or 0.0)

        try:
            running = bool(_RUN_REQUESTED and _worker_thread and _worker_thread.is_alive())
        except NameError:
            running = bool(_worker_thread and _worker_thread.is_alive())

        if running and _UPTIME_STARTED_MONO:
            progress["uptime_sec"] = int(now_mono - _UPTIME_STARTED_MONO)
        else:
            progress["uptime_sec"] = 0

        if running and rs_mono > 0.0:
            progress["round_elapsed_sec"] = int(now_mono - rs_mono)
        else:
            progress["round_elapsed_sec"] = 0

        if running and progress.get("phase") == "waiting":
            wait_started = float(progress.get("wait_started_mono") or 0.0)
            wait_total = int(progress.get("wait_total_sec") or 0)
            progress["wait_elapsed_sec"] = max(0, min(wait_total, int(now_mono - wait_started))) if wait_started else 0
        elif running:
            progress["phase"] = progress.get("phase") or "scanning"
            progress["wait_elapsed_sec"] = 0
        else:
            progress["phase"] = "idle"
            progress["wait_elapsed_sec"] = 0
            progress["wait_total_sec"] = 0

        with _ACTION_LOCK:
            action = _CURRENT_ACTION
            action_ts = _ACTION_TS
        action_age_sec = int(now_ts - action_ts) if action_ts else None

        def _fmt_secs(s: int) -> str:
            d, rem = divmod(int(s), 86400)
            h, rem = divmod(rem, 3600)
            m, sec = divmod(rem, 60)
            parts = []
            if d:
                parts.append(f"{d}d")
            if h or d:
                parts.append(f"{h}h")
            if m or h or d:
                parts.append(f"{m}m")
            parts.append(f"{sec}s")
            return " ".join(parts)

        progress["uptime_human"] = _fmt_secs(progress["uptime_sec"])
        progress["round_elapsed_human"] = _fmt_secs(progress["round_elapsed_sec"])
        return jsonify({
            "ok": True,
            "running": running,
            "config": cfg,
            "results": results,
            "logs": logs,
            "progress": progress,
            "action": action,
            "action_ts": action_ts,
            "action_age_sec": action_age_sec,
            "notification_status": notification_status_snapshot(cfg),
            "availability_logs": availability_log_snapshot(),
        })


def health() -> Response:
        running = bool(_RUN_REQUESTED and _worker_thread and _worker_thread.is_alive())
        return jsonify({
            "ok": True,
            "app": "toyoko-tracker",
            "name": APP_NAME,
            "version": __version__,
            "pid": os.getpid(),
            "running": running,
        })

def update_status() -> Response:
        with _UPDATE_LOCK:
            data = dict(_UPDATE_STATUS)
        return jsonify({"ok": True, "update": data})


def upgrade() -> Response:
        _upgrade_from_pypi_async()
        with _UPDATE_LOCK:
            data = dict(_UPDATE_STATUS)
        return jsonify({"ok": True, "update": data})


def area_index() -> Response:
        return jsonify({"ok": True, "data": _load_area_index()})


def search_history() -> Response:
        return jsonify({"ok": True, "records": _load_search_history()})


def search_history_clear() -> Response:
        _save_search_history([])
        return jsonify({"ok": True})


def area_hotels() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        try:
            region_id = int(payload.get("region_id"))
        except Exception:
            return jsonify({"ok": False, "error": "region_id is required"}), 400
        detail_id = str(payload.get("detail_id") or "")
        primary_language = _normalize_primary_language(payload.get("primary_language", DEFAULT_PRIMARY_LANGUAGE))
        try:
            hotels = _hotels_for_area_selection(region_id, detail_id, primary_language)
            return jsonify({"ok": True, "hotels": hotels, "count": len(hotels)})
        except Exception as e:
            _log(f"[area] load hotels failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


def radius_hotels() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        query = str(payload.get("query") or "").strip()
        radius_km = max(1, min(50, int(payload.get("radius_km") or DEFAULT_RADIUS_KM)))
        primary_language = _normalize_primary_language(payload.get("primary_language", DEFAULT_PRIMARY_LANGUAGE))
        if not query:
            return jsonify({"ok": False, "error": "address or coordinates are required"}), 400
        try:
            center, hotels = _hotels_within_radius(query, radius_km, primary_language)
            return jsonify({"ok": True, "center": center, "hotels": hotels, "count": len(hotels)})
        except Exception as e:
            _log(f"[radius] load hotels failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


 # ========= Startup Helper: Port and Browser =========
def _find_free_port(preferred: int = 4170) -> int:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", preferred))
            s.close()
            return preferred
        except OSError:
            s.close()
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

def _open_browser_when_ready(url: str, host: str, port: int, timeout_sec: int = 15) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    break
            except Exception:
                time.sleep(0.3)
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            pass

# ---- Cross-platform terminal launcher for hotel_scan.py ----
def _launch_terminal_for_hotel_scan() -> None:
    """
    Launch `hotel_scan.py` in a new terminal window using the current Python interpreter.
    Cross-platform support:
      - Windows: open a new cmd window and execute, window stays open.
      - macOS:   use AppleScript to open Terminal, cd into app directory, run script.
      - Linux:   try common terminals; if none available, run headless as a fallback.
    """
    script = os.path.join(BASE_DIR, "hotel_scan.py")
    if not os.path.exists(script):
        raise FileNotFoundError(f"hotel_scan.py not found at: {script}")

    py = sys.executable
    cwd = BASE_DIR

    if os.name == "nt":
        # Start a new cmd window, keep it open (/k) so user can watch logs
        cmd = f'start "HotelNameLibUpdate" cmd /k "{py}" -u "{script}"'
        subprocess.Popen(cmd, shell=True, cwd=cwd)

    elif sys.platform == "darwin":
        # Use AppleScript to open Terminal.app and run the command in a new window
        quoted_cwd = cwd.replace('"', '\\"')
        quoted_cmd = f'{py} -u "{script}"'.replace('"', '\\"')
        osa = (
            'tell application "Terminal"\n'
            '  activate\n'
            f'  do script "cd \\"{quoted_cwd}\\"; {quoted_cmd}"\n'
            'end tell'
        )
        subprocess.Popen(["osascript", "-e", osa], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    else:
        # Linux: try several common terminal emulators; fall back to headless run
        term_cmds = [
            ["gnome-terminal", "--", "bash", "-lc", f'cd "{cwd}"; "{py}" -u "{script}"; exec bash'],
            ["x-terminal-emulator", "-e", f'bash -lc \'cd "{cwd}"; "{py}" -u "{script}"; exec bash\''],
            ["konsole", "-e", f'bash -lc \'cd "{cwd}"; "{py}" -u "{script}"; exec bash\''],
            ["xterm", "-hold", "-e", f'{py} -u "{script}"'],
        ]
        spawned = False
        for cmd in term_cmds:
            try:
                subprocess.Popen(cmd)
                spawned = True
                break
            except Exception:
                continue
        if not spawned:
            # Fallback: run in the background without a new window
            subprocess.Popen([py, "-u", script], cwd=cwd,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
