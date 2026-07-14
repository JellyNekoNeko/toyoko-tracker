"""
东横酱 Toyoko Chan — Web version (Flask + Playwright/HTTP)

Relay：
  pip install flask beautifulsoup4 requests playwright

"""

from __future__ import annotations

import json
import html
import hashlib
import re
import time
import random
import threading
import os
import sys
import math
import platform
import shutil
import webbrowser
import socket
import subprocess
import tempfile
from collections import deque
from urllib.parse import quote, unquote
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, as_completed, wait
from copy import deepcopy
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import requests
from flask import request, jsonify, Response
from bs4 import BeautifulSoup

from .i18n import LANGUAGE_OPTIONS, normalize_primary_language as _normalize_primary_language
from .desktop_updater import (
    launch_update_helper as _launch_desktop_update_helper,
    prepare_desktop_update as _prepare_desktop_update,
    schedule_process_exit as _schedule_desktop_process_exit,
)
from .http_client import get as _http_get
from .hotel_info import (
    get_hotel_info as _get_hotel_info,
    get_provider_hotel_info as _get_provider_hotel_info,
)
from .hotel_catalog import (
    acknowledge_new_hotels as _acknowledge_new_hotels,
    catalog_status_snapshot as _catalog_status_snapshot,
    load_coordinate_cache as _load_catalog_coordinate_cache,
    request_catalog_refresh as _request_catalog_refresh,
    set_catalog_hooks as _set_catalog_hooks,
    start_catalog_scheduler as _catalog_start_scheduler,
    stop_catalog_scheduler as _catalog_stop_scheduler,
)
from .models import AppConfig, HotelResult
from .providers import capability_matrix as _provider_capability_matrix, get_provider as _get_provider_plugin
from .event_center import event_status_snapshot as _event_status_snapshot, list_events as _list_events
from .analytics import (
    analytics_status_snapshot as _analytics_status_snapshot,
    record_results as _record_analytics_results,
    scope_key_for_config as _analytics_scope_key,
    trend_snapshot as _trend_snapshot,
)
from .simulation import run_stress_test as _run_simulation_stress_test
from .traffic_meter import traffic_snapshot as _traffic_snapshot
from .routeinn import (
    build_booking_url as _build_routeinn_booking_url,
    fetch_coordinate_hotels as _fetch_routeinn_coordinate_hotels,
    fetch_offers as _fetch_routeinn_offers,
)
from .chain_providers import (
    build_booking_url as _build_chain_booking_url,
    fetch_dormy_offers as _fetch_dormy_offers,
    fetch_provider_hotels as _fetch_chain_provider_hotels,
    fetch_tripla_offers as _fetch_chain_tripla_offers,
    prefecture_id_from_text as _prefecture_id_from_text,
    region_id_for_prefecture_id as _region_id_for_prefecture_id,
)
from .hotel_database import (
    load_hotel as _db_load_hotel,
    load_hotels as _db_load_hotels,
    provider_count as _db_provider_count,
    record_sync_error as _db_record_sync_error,
    status_snapshot as _db_status_snapshot,
    sync_provider as _db_sync_provider,
)
from .notifications import (
    availability_log_revision,
    availability_log_snapshot,
    clear_alert_state,
    notification_status_snapshot,
    notification_checkpoint_snapshot,
    notify_local,
    process_notifications,
    restore_notification_checkpoint,
    send_start_notifications,
    send_stop_notifications,
    set_notification_hooks,
    validate_bark_key,
)
from .scan_cache import (
    clear as _scan_cache_clear,
    coalesced_call as _scan_cache_coalesced_call,
    get as _scan_cache_get,
    load_checkpoint as _load_runtime_checkpoint,
    mark_conditional_hit as _scan_cache_mark_conditional_hit,
    mark_fallback_hit as _scan_cache_mark_fallback_hit,
    mark_live_request as _scan_cache_mark_live_request,
    prune as _scan_cache_prune_impl,
    put as _scan_cache_put,
    save_checkpoint as _save_runtime_checkpoint,
    status_snapshot as _scan_cache_status_snapshot,
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
    ADAPTIVE_BACKOFF_MAX_MULTIPLIER,
    ADAPTIVE_BACKOFF_THRESHOLD_PERCENT,
    APP_AUTHOR,
    APP_NAME,
    APP_VERSION,
    __version__,
    AUTO_SAVE_PATH,
    BASE_DIR,
    BASE_URL,
    CONFIG_DIR,
    DEFAULT_BARK_SERVER,
    DEFAULT_BARK_CRITICAL_ENABLED,
    DEFAULT_BARK_CRITICAL_SOUND,
    DEFAULT_BARK_CRITICAL_VOLUME,
    DEFAULT_ADAPTIVE_BACKOFF_ENABLED,
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
    DEFAULT_ENABLED_PROVIDERS,
    SUPPORTED_PROVIDERS,
    HEADERS,
    RADIUS_HOTELS_CACHE_PATH,
    SEARCH_HISTORY_PATH,
    TIMEOUT,
)
from .desktop_version import DESKTOP_VERSION

# ---- precise timing helpers (monotonic) ----
def _now_wall() -> float:
    return time.time()

def _now_mono() -> float:
    return time.perf_counter()

# ========= Global Status =========
_LOG_LINES: List[str] = []
_LOG_LOCK = threading.Lock()
_LOG_SEQUENCE = 0
_LAST_RESULTS: List[HotelResult] = []
_RESULTS_LOCK = threading.Lock()
_RESULTS_REVISION = 0
_START_TIME = _now_wall()
_PROGRESS = {
    "round": 0,
    "done": 0,
    "total": 0,
    "round_started": 0.0,
    "round_started_mono": 0.0,
    "backoff_multiplier": 1,
    "unknown_ratio_percent": 0,
    "consecutive_unhealthy_rounds": 0,
    "effective_interval_sec": 0,
    "queue_pending": 0,
    "in_flight": 0,
    "priority_pending": 0,
}
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
_PROVIDER_HEALTH: Dict[str, Dict[str, Any]] = {}
_PROVIDER_HEALTH_LOCK = threading.Lock()
_HOTEL_RUNTIME_STATE: Dict[str, Dict[str, Any]] = {}
_HOTEL_RUNTIME_LOCK = threading.Lock()
_CHECKPOINT_RESTORED_SCOPE = ""

_HOTEL_RESULT_FIELDS = {field.name for field in fields(HotelResult)}

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
    global _LOG_SEQUENCE
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with _LOG_LOCK:
        _LOG_LINES.append(line)
        _LOG_SEQUENCE += 1
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
    values = [int(p) for p in parts[:4]]
    return tuple((values + [0, 0, 0, 0])[:4])


def _is_desktop_distribution() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_pipx_environment() -> bool:
    if any(os.environ.get(name) for name in ("PIPX_HOME", "PIPX_LOCAL_VENVS")):
        return True
    normalized = str(getattr(sys, "prefix", "") or "").replace("\\", "/").lower()
    return "/pipx/venvs/" in normalized or normalized.endswith("/pipx/venvs/toyoko-tracker")


def _install_method() -> str:
    if _is_desktop_distribution():
        return "desktop"
    return "pipx" if _is_pipx_environment() else "pip"


def _pypi_upgrade_command() -> List[str]:
    if _is_pipx_environment():
        pipx = shutil.which("pipx")
        if pipx:
            return [pipx, "upgrade", "toyoko-tracker"]
    return [sys.executable, "-m", "pip", "install", "--upgrade", "toyoko-tracker"]


def _desktop_asset_name() -> str:
    machine = platform.machine().lower()
    architecture = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if sys.platform == "darwin":
        return f"ToyokoTracker-macos-{architecture}.zip"
    if os.name == "nt":
        return f"ToyokoTracker-windows-{architecture}.zip"
    return f"ToyokoTracker-linux-{architecture}.tar.gz"


def _github_release_details(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("GitHub release response is invalid")
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag:
        raise ValueError("GitHub release did not include a version")
    expected_asset = _desktop_asset_name()
    download_url = ""
    checksum_url = ""
    for asset in data.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if name == expected_asset:
            download_url = str(asset.get("browser_download_url") or "")
        elif name == "SHA256SUMS.txt":
            checksum_url = str(asset.get("browser_download_url") or "")
    normalized_tag = tag[len("desktop-v"):] if tag.lower().startswith("desktop-v") else tag.lstrip("vV")
    return {
        "version": normalized_tag,
        "release_url": str(data.get("html_url") or "https://github.com/JellyNekoNeko/toyoko-tracker/releases/latest"),
        "download_url": download_url,
        "checksum_url": checksum_url,
        "asset_name": expected_asset,
        "release_notes": str(data.get("body") or "")[:4000],
    }


def _latest_desktop_release(data: Any) -> Dict[str, Any]:
    if not isinstance(data, list):
        raise ValueError("GitHub releases response is invalid")
    for release in data:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        if str(release.get("tag_name") or "").lower().startswith("desktop-v"):
            return release
    raise ValueError("no desktop release is available yet")


def _set_update_status(**kwargs: Any) -> None:
    with _UPDATE_LOCK:
        _UPDATE_STATUS.update(kwargs)


def _check_pypi_latest_async() -> None:
    with _UPDATE_LOCK:
        if _UPDATE_STATUS.get("state") in {"checking", "upgrading"}:
            return
        _UPDATE_STATUS.update({
            "state": "checking",
            "source": "pypi",
            "install_method": _install_method(),
            "message": "checking PyPI",
            "checked_at": _now_wall(),
        })

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
                source="pypi",
                install_method=_install_method(),
                current_version=__version__,
                latest_version=latest,
                message="update available" if update_available else "already latest",
                checked_at=_now_wall(),
            )
        except Exception as e:
            _set_update_status(
                state="failed",
                source="pypi",
                install_method=_install_method(),
                current_version=__version__,
                message=str(e),
                checked_at=_now_wall(),
            )

    threading.Thread(target=worker, name="pypi-update-check", daemon=True).start()


def _check_github_latest_async() -> None:
    with _UPDATE_LOCK:
        if _UPDATE_STATUS.get("state") in {"checking", "upgrading", "downloading", "installing"}:
            return
        _UPDATE_STATUS.update({
            "state": "checking",
            "source": "github",
            "install_method": "desktop",
            "message": "checking GitHub Releases",
            "checked_at": _now_wall(),
        })

    def worker() -> None:
        try:
            response = requests.get(
                "https://api.github.com/repos/JellyNekoNeko/toyoko-tracker/releases?per_page=20",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "ToyokoTracker-Updater"},
                timeout=8,
            )
            response.raise_for_status()
            release = _github_release_details(_latest_desktop_release(response.json()))
            latest = release["version"]
            update_available = _version_key(latest) > _version_key(DESKTOP_VERSION)
            _set_update_status(
                state="update_available" if update_available else "up_to_date",
                source="github",
                install_method="desktop",
                current_version=DESKTOP_VERSION,
                latest_version=latest,
                message="desktop update available" if update_available else "already latest",
                checked_at=_now_wall(),
                **release,
            )
        except Exception as exc:
            _set_update_status(
                state="failed",
                source="github",
                install_method="desktop",
                current_version=DESKTOP_VERSION,
                message=str(exc),
                checked_at=_now_wall(),
            )

    threading.Thread(target=worker, name="github-update-check", daemon=True).start()


def _check_latest_async() -> None:
    if _is_desktop_distribution():
        _check_github_latest_async()
    else:
        _check_pypi_latest_async()


def _upgrade_from_pypi_async() -> None:
    with _UPDATE_LOCK:
        if _UPDATE_STATUS.get("state") == "upgrading":
            return
        method = _install_method()
        _UPDATE_STATUS.update({
            "state": "upgrading",
            "source": "pypi",
            "install_method": method,
            "message": f"upgrading with {method}",
            "upgrade_output": "",
        })

    def worker() -> None:
        try:
            cmd = _pypi_upgrade_command()
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()[-4000:]
            if proc.returncode == 0:
                _set_update_status(state="upgraded", message="upgrade finished, please restart", upgrade_output=output)
            else:
                _set_update_status(state="failed", message=f"upgrade failed with code {proc.returncode}", upgrade_output=output)
        except Exception as e:
            _set_update_status(state="failed", message=str(e))

    threading.Thread(target=worker, name="pypi-upgrade", daemon=True).start()


def _upgrade_desktop_async() -> None:
    with _UPDATE_LOCK:
        if _UPDATE_STATUS.get("state") in {"downloading", "installing"}:
            return
        download_url = str(_UPDATE_STATUS.get("download_url") or "")
        checksum_url = str(_UPDATE_STATUS.get("checksum_url") or "")
        release_url = str(_UPDATE_STATUS.get("release_url") or "")
        version = str(_UPDATE_STATUS.get("latest_version") or "")
        asset_name = str(_UPDATE_STATUS.get("asset_name") or _desktop_asset_name())
        _UPDATE_STATUS.update({
            "state": "downloading",
            "source": "github",
            "install_method": "desktop",
            "message": "downloading desktop update",
            "download_percent": 0,
        })

    def progress(received: int, total: int) -> None:
        percent = int(received * 100 / total) if total else 0
        _set_update_status(
            state="downloading",
            message=f"downloading desktop update ({percent}%)" if total else "downloading desktop update",
            download_received=received,
            download_total=total,
            download_percent=percent,
        )

    def worker() -> None:
        try:
            update = _prepare_desktop_update(
                version=version,
                asset_name=asset_name,
                download_url=download_url,
                checksum_url=checksum_url,
                config_dir=Path(CONFIG_DIR),
                progress=progress,
            )
            _set_update_status(
                state="installing",
                message="update verified; restarting to install",
                download_percent=100,
                backup_path=str(update.backup_root),
            )
            _launch_desktop_update_helper(update)
            threading.Thread(
                target=_schedule_desktop_process_exit,
                name="desktop-update-exit",
                daemon=True,
            ).start()
        except Exception as exc:
            target = download_url or release_url or "https://github.com/JellyNekoNeko/toyoko-tracker/releases/latest"
            opened = webbrowser.open(target)
            _set_update_status(
                state="failed",
                source="github",
                install_method="desktop",
                message=f"{exc}; manual download opened" if opened else str(exc),
                open_url=target,
            )

    threading.Thread(target=worker, name="desktop-update", daemon=True).start()


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
            "code": code.zfill(5) if code.isdigit() else code,
            "display_code": str(h.get("display_code") or ""),
            "provider": str(h.get("provider") or (code.split(":", 1)[0] if ":" in code else "toyoko")),
            "brand": str(h.get("brand") or ""),
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
            "reservation_url": str(h.get("reservation_url") or ""),
            "address": str(h.get("address") or ""),
            "access": str(h.get("access") or ""),
            "lat": h.get("lat"),
            "lng": h.get("lng"),
            "distance_km": h.get("distance_km"),
            "booking_code": str(h.get("booking_code") or ""),
            "provider_hotel_id": str(h.get("provider_hotel_id") or ""),
            "search_keyword": str(h.get("search_keyword") or ""),
            "prefecture": str(h.get("prefecture") or ""),
            "region_id": h.get("region_id"),
            "prefecture_id": h.get("prefecture_id"),
            "priority": bool(h.get("priority", False)),
        })
    return clean


def _localize_selected_hotels(hotels: List[Dict[str, str]], primary_language: Optional[str]) -> List[Dict[str, str]]:
    localized: List[Dict[str, str]] = []
    for h in hotels or []:
        raw_code = str(h.get("code") or "")
        code = raw_code.zfill(5) if raw_code.isdigit() else raw_code
        if not code:
            continue
        if str(h.get("provider") or "toyoko") != "toyoko" or ":" in code:
            item = dict(h)
            lang = _normalize_primary_language(primary_language)
            item["provider"] = str(h.get("provider") or code.split(":", 1)[0])
            item["name_primary"] = h.get(f"name_{lang}") or h.get("name_primary") or h.get("name_ja") or h.get("name") or ""
            item["name_en"] = h.get("name_en") or item["name_primary"]
            localized.append(item)
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
            providers = data.get("enabled_providers", getattr(cfg, "enabled_providers", DEFAULT_ENABLED_PROVIDERS))
            if isinstance(providers, list):
                cfg.enabled_providers = [provider for provider in providers if provider in SUPPORTED_PROVIDERS]
            if not cfg.enabled_providers:
                cfg.enabled_providers = list(DEFAULT_ENABLED_PROVIDERS)
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
            cfg.adaptive_backoff_enabled = bool(data.get(
                'adaptive_backoff_enabled',
                getattr(cfg, 'adaptive_backoff_enabled', DEFAULT_ADAPTIVE_BACKOFF_ENABLED),
            ))
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
                'enabled_providers': list(getattr(cfg, 'enabled_providers', DEFAULT_ENABLED_PROVIDERS)),
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
                'adaptive_backoff_enabled': getattr(cfg, 'adaptive_backoff_enabled', DEFAULT_ADAPTIVE_BACKOFF_ENABLED),
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
        "adaptive_backoff_enabled": getattr(cfg, "adaptive_backoff_enabled", DEFAULT_ADAPTIVE_BACKOFF_ENABLED),
        "available_alert_repeat": cfg.available_alert_repeat,
        "available_alert_repeat_interval_sec": cfg.available_alert_repeat_interval_sec,
        "area_region": str(payload.get("area_region") or ""),
        "area_detail": str(payload.get("area_detail") or ""),
        "area_region_label": str(payload.get("area_region_label") or ""),
        "area_detail_label": str(payload.get("area_detail_label") or ""),
        "search_mode": getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE),
        "enabled_providers": list(getattr(cfg, "enabled_providers", DEFAULT_ENABLED_PROVIDERS)),
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
            "smart_parallel_enabled", "smart_parallel_workers", "adaptive_backoff_enabled", "available_alert_repeat",
            "available_alert_repeat_interval_sec", "area_region", "area_detail", "enabled_providers", "hotel_codes",
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
def _selected_hotel_for_code(cfg: AppConfig, code: str) -> Dict[str, Any]:
    return next(
        (hotel for hotel in (getattr(cfg, "selected_hotels", []) or []) if str(hotel.get("code") or "") == str(code)),
        {},
    )


def build_url(cfg: AppConfig, code: str, start: str, end: str) -> str:
    hotel = _selected_hotel_for_code(cfg, code)
    provider = str(hotel.get("provider") or (str(code).split(":", 1)[0] if ":" in str(code) else "toyoko"))
    if provider == "routeinn":
        return _build_routeinn_booking_url(hotel, start, end, cfg.people, cfg.rooms)
    if provider in {"dormy", "mystays", "daiwa"}:
        return _build_chain_booking_url(hotel, start, end, cfg.people, cfg.rooms)
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
            **({"room_title_primary": o.get("room_title_primary")} if o.get("room_title_primary") else {}),
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


def _retry_after_seconds(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return max(1, min(3600, int(float(text))))
    except (TypeError, ValueError):
        return None


def _scan_cache_key(cfg: AppConfig, code: str, start: str, end: str) -> str:
    payload = {
        "provider": _provider_for_code(cfg, code),
        "code": str(code),
        "start": str(start),
        "end": str(end),
        "people": int(getattr(cfg, "people", 1) or 1),
        "rooms": int(getattr(cfg, "rooms", 1) or 1),
        "smoking": str(getattr(cfg, "smoking", "all") or "all"),
        "room_requirement": str(
            getattr(cfg, "room_requirement", None)
            or getattr(cfg, "om_requirement", "any")
            or "any"
        ),
        "membership": str(getattr(cfg, "membership_status", "member") or "member"),
        "engine": str(getattr(cfg, "engine", DEFAULT_ENGINE) or DEFAULT_ENGINE),
        "language": str(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)),
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scan_scope_key(cfg: AppConfig) -> str:
    payload = {
        "codes": sorted(str(code) for code in cfg.hotel_codes),
        "start": str(cfg.start_date),
        "end": str(cfg.end_date),
        "people": int(cfg.people),
        "rooms": int(cfg.rooms),
        "smoking": str(cfg.smoking),
        "room_requirement": str(
            getattr(cfg, "room_requirement", None)
            or getattr(cfg, "om_requirement", "any")
            or "any"
        ),
        "membership": str(cfg.membership_status),
        "engine": str(cfg.engine),
        "language": str(cfg.primary_language),
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hotel_result_from_dict(data: Dict[str, Any]) -> HotelResult:
    values = {key: value for key, value in data.items() if key in _HOTEL_RESULT_FIELDS}
    return HotelResult(**values)


def _cached_result(entry: Any, *, validated: bool = False, fallback: bool = False) -> HotelResult:
    result = _hotel_result_from_dict(entry.result)
    result.from_cache = not validated
    result.cache_age_sec = max(0, int(getattr(entry, "age_sec", 0) or 0))
    result.cache_validated = bool(validated)
    result.cache_fallback = bool(fallback)
    result.etag = str(getattr(entry, "etag", "") or result.etag or "") or None
    result.last_modified = str(
        getattr(entry, "last_modified", "") or result.last_modified or ""
    ) or None
    return result


def _scan_cache_ttl(cfg: AppConfig, result: HotelResult) -> int:
    if result.available is True:
        return 5
    if _hotel_is_manual_priority(cfg, result.code) or _hotel_is_adaptive_priority(result.code):
        return 15
    if result.available is False:
        return max(30, min(120, int(getattr(cfg, "loop_interval_seconds", 30) * 1.25)))
    return 12


def _http_error_metadata(exc: Exception) -> Tuple[Optional[int], Optional[int]]:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    retry_after = None
    if response is not None:
        retry_after = _retry_after_seconds(getattr(response, "headers", {}).get("Retry-After"))
    if status is None:
        match = re.search(r"\b(429|503)\b", str(exc))
        status = int(match.group(1)) if match else None
    return status, retry_after


def check_hotel_http(cfg: AppConfig, code: str, start: str, end: str) -> HotelResult:
    url = build_url(cfg, code, start, end)
    cache_key = _scan_cache_key(cfg, code, start, end)
    cached_entry = _scan_cache_get(cache_key, allow_expired=True, count_metrics=False)
    request_headers = dict(HEADERS)
    if cached_entry and cached_entry.etag:
        request_headers["If-None-Match"] = cached_entry.etag
    if cached_entry and cached_entry.last_modified:
        request_headers["If-Modified-Since"] = cached_entry.last_modified
    try:
        resp = _http_get(url, headers=request_headers, timeout=TIMEOUT)
        status_code = int(getattr(resp, "status_code", 200))
        if status_code == 304 and cached_entry:
            _scan_cache_mark_conditional_hit()
            return _cached_result(cached_entry, validated=True)
        if status_code >= 400:
            retry_after = _retry_after_seconds(getattr(resp, "headers", {}).get("Retry-After"))
            return HotelResult(
                code=code,
                url=url,
                name=None,
                available=None,
                engine_used="http",
                http_status=status_code,
                retry_after_sec=retry_after,
                error_summary=f"HTTP {status_code}" + (f"; Retry-After {retry_after}s" if retry_after else ""),
            )
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
        result = _hotel_result_from_offers(cfg, code, url, name, offers, offer_stats, None)
        result.engine_used = "http"
        response_headers = getattr(resp, "headers", {}) or {}
        result.etag = str(response_headers.get("ETag") or "") or None
        result.last_modified = str(response_headers.get("Last-Modified") or "") or None
        return result
    except Exception as e:
        _log(f"[http] failed for {code}: {e}")
        status, retry_after = _http_error_metadata(e)
        return HotelResult(
            code=code,
            url=url,
            name=None,
            available=None,
            engine_used="http",
            http_status=status,
            retry_after_sec=retry_after,
            error_summary=" ".join(str(e).split())[:240],
        )


def check_routeinn_hotel(cfg: AppConfig, code: str, start: str, end: str) -> HotelResult:
    hotel = _selected_hotel_for_code(cfg, code)
    url = build_url(cfg, code, start, end)
    if not hotel:
        return HotelResult(
            code=code,
            display_code=code,
            provider="routeinn",
            url=url,
            name=None,
            available=None,
            engine_used="routeinn_api",
            error_summary="Route Inn hotel metadata is missing; reload the hotel picker",
        )
    try:
        name_primary, name_en, url, offers, offer_stats = _fetch_routeinn_offers(
            hotel,
            start,
            end,
            cfg.people,
            cfg.rooms,
            _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)),
        )
        result = _hotel_result_from_offers(cfg, code, url, name_en or name_primary, offers, offer_stats, None)
        result.provider = "routeinn"
        result.display_code = str(hotel.get("display_code") or code)
        result.name = name_en or name_primary
        result.name_primary = name_primary
        result.name_en = name_en or name_primary
        result.name_zh = str(hotel.get("name_zh_cn") or name_primary)
        result.engine_used = "routeinn_api"
        return result
    except Exception as exc:
        _log(f"[routeinn] failed for {code}: {exc}")
        status, retry_after = _http_error_metadata(exc)
        return HotelResult(
            code=code,
            display_code=str(hotel.get("display_code") or code),
            provider="routeinn",
            url=url,
            name=str(hotel.get("name_en") or hotel.get("name") or "") or None,
            name_primary=str(hotel.get("name_primary") or hotel.get("name") or "") or None,
            name_en=str(hotel.get("name_en") or hotel.get("name") or "") or None,
            available=None,
            engine_used="routeinn_api",
            http_status=status,
            retry_after_sec=retry_after,
            error_summary=" ".join(str(exc).split())[:240],
        )


def check_chain_hotel(cfg: AppConfig, code: str, start: str, end: str, provider: str) -> HotelResult:
    hotel = _selected_hotel_for_code(cfg, code)
    url = build_url(cfg, code, start, end)
    if not hotel:
        return HotelResult(
            code=code,
            display_code=code,
            provider=provider,
            url=url,
            name=None,
            available=None,
            engine_used=f"{provider}_api",
            error_summary=f"{provider} hotel metadata is missing; reload the hotel picker",
        )
    try:
        fetcher = _fetch_dormy_offers if provider == "dormy" else _fetch_chain_tripla_offers
        name_primary, name_en, url, offers, offer_stats = fetcher(
            hotel,
            start,
            end,
            cfg.people,
            cfg.rooms,
            _normalize_primary_language(getattr(cfg, "primary_language", DEFAULT_PRIMARY_LANGUAGE)),
        )
        result = _hotel_result_from_offers(cfg, code, url, name_en or name_primary, offers, offer_stats, None)
        result.provider = provider
        result.display_code = str(hotel.get("display_code") or code)
        result.name = name_en or name_primary
        result.name_primary = name_primary
        result.name_en = name_en or name_primary
        result.name_zh = str(hotel.get("name_zh_cn") or name_primary)
        result.engine_used = f"{provider}_api"
        return result
    except Exception as exc:
        _log(f"[{provider}] failed for {code}: {exc}")
        status, retry_after = _http_error_metadata(exc)
        return HotelResult(
            code=code,
            display_code=str(hotel.get("display_code") or code),
            provider=provider,
            url=url,
            name=str(hotel.get("name_en") or hotel.get("name") or "") or None,
            name_primary=str(hotel.get("name_primary") or hotel.get("name") or "") or None,
            name_en=str(hotel.get("name_en") or hotel.get("name") or "") or None,
            available=None,
            engine_used=f"{provider}_api",
            http_status=status,
            retry_after_sec=retry_after,
            error_summary=" ".join(str(exc).split())[:240],
        )


def check_hotel_playwright(cfg: AppConfig, renderer: Optional[Any], code: str, start: str, end: str) -> HotelResult:
    url = build_url(cfg, code, start, end)
    try:
        rendered = fetch_rendered_any(cfg, renderer, url)
    except Exception as e:
        _log(f"[playwright] failed for {code}: {e}")
        return HotelResult(
            code=code,
            url=url,
            name=None,
            available=None,
            engine_used="playwright",
            error_summary=" ".join(str(e).split())[:240],
        )

    name = extract_hotel_name(rendered.soup)
    offers, offer_stats = extract_offers(rendered.soup)
    result = _hotel_result_from_offers(cfg, code, url, name, offers, offer_stats, rendered.visible_text)
    result.engine_used = "playwright"
    return result


def check_hotel(cfg: AppConfig, renderer: Optional[Any], code: str, start: str, end: str) -> HotelResult:
    started = _now_mono()
    hotel = _selected_hotel_for_code(cfg, code)
    provider = str(hotel.get("provider") or (str(code).split(":", 1)[0] if ":" in str(code) else "toyoko"))
    plugin = _get_provider_plugin(provider)
    strategy = plugin.scan_strategy if plugin else provider
    if strategy == "routeinn":
        result = check_routeinn_hotel(cfg, code, start, end)
    elif strategy in {"dormy", "tripla"}:
        result = check_chain_hotel(cfg, code, start, end, provider)
    elif strategy == "toyoko" and getattr(cfg, "engine", "playwright") == "http":
        result = check_hotel_http(cfg, code, start, end)
        if result.available is None and _HAS_PLAYWRIGHT and result.http_status not in {429, 503}:
            _log(f"[http] fallback to Playwright for {code}")
            fallback = check_hotel_playwright(cfg, renderer, code, start, end)
            if fallback.error_summary and result.error_summary:
                fallback.error_summary = f"HTTP: {result.error_summary}; Playwright: {fallback.error_summary}"[:240]
            result = fallback
    else:
        result = check_hotel_playwright(cfg, renderer, code, start, end)
    result.checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    result.elapsed_ms = max(0, int(round((_now_mono() - started) * 1000)))
    result.engine_used = result.engine_used or getattr(cfg, "engine", DEFAULT_ENGINE)
    return result


def _check_hotel_cached(
    cfg: AppConfig,
    renderer: Optional[Any],
    code: str,
    start: str,
    end: str,
    *,
    allow_cache: bool = True,
    force_refresh: bool = False,
) -> HotelResult:
    cache_key = _scan_cache_key(cfg, code, start, end)
    if allow_cache and not force_refresh:
        entry = _scan_cache_get(cache_key)
        if entry is not None:
            return _cached_result(entry)

    def producer() -> HotelResult:
        _scan_cache_mark_live_request()
        result = check_hotel(cfg, renderer, code, start, end)
        if result.available is None:
            stale_entry = _scan_cache_get(cache_key, allow_expired=True, count_metrics=False)
            if stale_entry is not None and stale_entry.result.get("available") is not None:
                cached = _cached_result(stale_entry, fallback=True)
                cached.error_summary = result.error_summary or cached.error_summary
                cached.http_status = result.http_status
                cached.retry_after_sec = result.retry_after_sec
                cached.checked_at = result.checked_at
                cached.elapsed_ms = result.elapsed_ms
                _scan_cache_mark_fallback_hit()
                return cached
        payload = asdict(result)
        payload.update({
            "from_cache": False,
            "cache_age_sec": None,
            "cache_validated": False,
            "cache_fallback": False,
        })
        _scan_cache_put(
            cache_key,
            _provider_for_code(cfg, code),
            code,
            payload,
            _scan_cache_ttl(cfg, result),
            etag=result.etag or "",
            last_modified=result.last_modified or "",
        )
        return result

    result, coalesced = _scan_cache_coalesced_call(
        cache_key,
        producer,
        timeout=max(10.0, float(TIMEOUT) + 20.0),
    )
    if coalesced:
        result.from_cache = True
        result.cache_age_sec = 0
        result.cache_validated = False
    return result


def _adaptive_backoff_state(
    results: List[HotelResult],
    consecutive_unhealthy_rounds: int,
    enabled: bool = True,
) -> Tuple[int, int, int]:
    total = len(results)
    unknown = sum(1 for result in results if result.available is None)
    ratio_percent = int(round((unknown * 100) / total)) if total else 0
    unhealthy = total > 0 and ratio_percent >= ADAPTIVE_BACKOFF_THRESHOLD_PERCENT
    if not enabled or not unhealthy:
        return 1, 0, ratio_percent
    consecutive = max(0, int(consecutive_unhealthy_rounds)) + 1
    multiplier = min(ADAPTIVE_BACKOFF_MAX_MULTIPLIER, 2 ** min(consecutive, 2))
    return multiplier, consecutive, ratio_percent


def _jittered_delay(base_seconds: int, jitter_percent: int) -> float:
    base = float(max(0, base_seconds))
    jitter = max(0, min(100, int(jitter_percent))) / 100.0
    if base <= 0 or jitter <= 0:
        return base
    low = base * (1.0 - jitter)
    high = base * (1.0 + jitter)
    return max(1.0, random.uniform(low, high))


def _jittered_spacing(base_seconds: float, jitter_percent: int) -> float:
    base = max(0.05, float(base_seconds))
    jitter = max(0, min(100, int(jitter_percent))) / 100.0
    if jitter <= 0:
        return base
    return max(0.05, random.uniform(base * (1.0 - jitter), base * (1.0 + jitter)))


def _provider_for_code(cfg: AppConfig, code: str) -> str:
    hotel = _selected_hotel_for_code(cfg, code)
    return str(hotel.get("provider") or (str(code).split(":", 1)[0] if ":" in str(code) else "toyoko"))


def _new_provider_health_state(base_delay: float = 1.0) -> Dict[str, Any]:
    return {
        "checks": 0,
        "successful_checks": 0,
        "access_failures": 0,
        "consecutive_failures": 0,
        "average_elapsed_ms": 0,
        "latency_samples_ms": [],
        "base_delay_sec": max(0.5, float(base_delay)),
        "adaptive_multiplier": 1.0,
        "cooldown_until_mono": 0.0,
        "cooldown_count": 0,
        "rate_limited_count": 0,
        "last_http_status": None,
        "last_error": "",
        "last_checked_at": None,
    }


def _reset_provider_health(providers: List[str], base_delay: float = 1.0) -> None:
    with _PROVIDER_HEALTH_LOCK:
        _PROVIDER_HEALTH.clear()
        for provider in dict.fromkeys(providers):
            _PROVIDER_HEALTH[provider] = _new_provider_health_state(base_delay)


def _provider_cooldown_until(provider: str) -> float:
    with _PROVIDER_HEALTH_LOCK:
        return float(_PROVIDER_HEALTH.get(provider, {}).get("cooldown_until_mono") or 0.0)


def _record_provider_result(provider: str, result: HotelResult) -> None:
    if result.from_cache and not result.cache_validated:
        return
    now_mono = _now_mono()
    with _PROVIDER_HEALTH_LOCK:
        state = _PROVIDER_HEALTH.setdefault(provider, _new_provider_health_state())
        state["checks"] += 1
        elapsed_ms = max(0, int(result.elapsed_ms or 0))
        previous_average = int(state.get("average_elapsed_ms") or 0)
        state["average_elapsed_ms"] = elapsed_ms if state["checks"] == 1 else int(round(previous_average * 0.75 + elapsed_ms * 0.25))
        samples = list(state.get("latency_samples_ms") or [])
        if elapsed_ms:
            samples.append(elapsed_ms)
            state["latency_samples_ms"] = samples[-40:]
        state["last_checked_at"] = result.checked_at or datetime.now().astimezone().isoformat(timespec="seconds")
        status = result.http_status
        if status is None:
            match = re.search(r"\b(429|503)\b", str(result.error_summary or ""))
            status = int(match.group(1)) if match else None
        state["last_http_status"] = status
        if result.available is None:
            state["access_failures"] += 1
            state["consecutive_failures"] += 1
            state["last_error"] = str(result.error_summary or "access check failed")[:180]
            cooldown_seconds = 0
            if status == 429:
                state["rate_limited_count"] += 1
                state["adaptive_multiplier"] = min(8.0, max(2.0, float(state.get("adaptive_multiplier") or 1.0) * 2.0))
                cooldown_seconds = int(result.retry_after_sec or 30)
            elif status == 503:
                state["adaptive_multiplier"] = min(8.0, max(1.5, float(state.get("adaptive_multiplier") or 1.0) * 1.5))
                cooldown_seconds = int(result.retry_after_sec or 15)
            elif state["consecutive_failures"] >= 3:
                state["adaptive_multiplier"] = min(8.0, float(state.get("adaptive_multiplier") or 1.0) + 0.5)
                cooldown_seconds = min(30, 2 ** min(5, state["consecutive_failures"] - 1))
            if cooldown_seconds:
                state["cooldown_count"] += 1
                state["cooldown_until_mono"] = max(
                    float(state.get("cooldown_until_mono") or 0.0),
                    now_mono + max(1, min(3600, cooldown_seconds)),
                )
        else:
            state["successful_checks"] += 1
            state["consecutive_failures"] = 0
            state["cooldown_until_mono"] = 0.0
            state["last_error"] = ""
            multiplier = float(state.get("adaptive_multiplier") or 1.0)
            if multiplier > 1.0:
                state["adaptive_multiplier"] = max(1.0, multiplier * 0.85)
            elif state["checks"] >= 5 and state["average_elapsed_ms"] <= 1500:
                state["adaptive_multiplier"] = max(0.75, multiplier - 0.05)


def _percentile(values: List[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(max(0, int(value)) for value in values)
    position = max(0, min(len(ordered) - 1, int(math.ceil((len(ordered) - 1) * percentile))))
    return ordered[position]


def provider_health_snapshot() -> Dict[str, Dict[str, Any]]:
    now_mono = _now_mono()
    with _PROVIDER_HEALTH_LOCK:
        snapshot = deepcopy(_PROVIDER_HEALTH)
    for state in snapshot.values():
        cooldown_until = float(state.pop("cooldown_until_mono", 0.0) or 0.0)
        samples = list(state.pop("latency_samples_ms", []) or [])
        cooldown_remaining = max(0, int(math.ceil(cooldown_until - now_mono)))
        checks = int(state.get("checks") or 0)
        successful = int(state.get("successful_checks") or 0)
        state["cooldown_remaining_sec"] = cooldown_remaining
        state["success_rate_percent"] = int(round(successful * 100 / checks)) if checks else 0
        state["p50_elapsed_ms"] = _percentile(samples, 0.50)
        state["p95_elapsed_ms"] = _percentile(samples, 0.95)
        state["adaptive_delay_sec"] = round(
            float(state.get("base_delay_sec") or 1.0) * float(state.get("adaptive_multiplier") or 1.0),
            2,
        )
        if cooldown_remaining:
            state["state"] = "cooldown"
        elif int(state.get("consecutive_failures") or 0):
            state["state"] = "degraded"
        elif checks:
            state["state"] = "healthy"
        else:
            state["state"] = "idle"
    return snapshot


def _provider_dynamic_spacing(provider: str, base_delay: float) -> float:
    with _PROVIDER_HEALTH_LOCK:
        state = _PROVIDER_HEALTH.get(provider) or {}
        recorded_base = float(state.get("base_delay_sec") or base_delay)
        multiplier = float(state.get("adaptive_multiplier") or 1.0) if abs(recorded_base - float(base_delay)) < 0.01 else 1.0
    return max(0.5, min(60.0, float(base_delay) * multiplier))


def _result_available_count(result: HotelResult) -> int:
    if result.available is not True:
        return 0
    total = 0
    for offer in result.offers_display or []:
        text = str(offer.get("remaining_norm") or offer.get("remaining") or "")
        match = re.search(r"\d+", text.replace(",", ""))
        if match:
            total += int(match.group(0))
    if total:
        return total
    match = re.search(r"\d+", str(result.min_remaining or "").replace(",", ""))
    return int(match.group(0)) if match else 1


def _record_hotel_runtime_result(result: HotelResult) -> None:
    if result.from_cache and not result.cache_validated:
        return
    now = _now_mono()
    count = _result_available_count(result)
    with _HOTEL_RUNTIME_LOCK:
        state = _HOTEL_RUNTIME_STATE.setdefault(result.code, {
            "checks": 0,
            "last_available": None,
            "last_count": None,
            "last_change_mono": 0.0,
            "consecutive_errors": 0,
        })
        previous_available = state.get("last_available")
        previous_count = state.get("last_count")
        state["checks"] += 1
        if result.available is None:
            state["consecutive_errors"] = int(state.get("consecutive_errors") or 0) + 1
            return
        state["consecutive_errors"] = 0
        if previous_available is not None and (
            bool(previous_available) != bool(result.available) or previous_count != count
        ):
            state["last_change_mono"] = now
        state["last_available"] = bool(result.available)
        state["last_count"] = count


def _hotel_is_manual_priority(cfg: AppConfig, code: str) -> bool:
    hotel = _selected_hotel_for_code(cfg, code)
    return bool(hotel.get("priority", False))


def _hotel_priority_score(cfg: AppConfig, code: str, now_mono: Optional[float] = None) -> int:
    if _hotel_is_manual_priority(cfg, code):
        return 1000
    now = _now_mono() if now_mono is None else float(now_mono)
    with _HOTEL_RUNTIME_LOCK:
        state = dict(_HOTEL_RUNTIME_STATE.get(code) or {})
    if not state:
        return 300
    if int(state.get("consecutive_errors") or 0):
        return max(10, 80 - int(state.get("consecutive_errors") or 0) * 15)
    if state.get("last_available") is True:
        return 500
    changed_at = float(state.get("last_change_mono") or 0.0)
    if changed_at and now - changed_at <= 900:
        return max(160, 280 - int((now - changed_at) / 10))
    return max(20, 120 - int(state.get("checks") or 0) * 5)


def _hotel_is_adaptive_priority(code: str, now_mono: Optional[float] = None) -> bool:
    now = _now_mono() if now_mono is None else float(now_mono)
    with _HOTEL_RUNTIME_LOCK:
        state = dict(_HOTEL_RUNTIME_STATE.get(code) or {})
    if not state or int(state.get("consecutive_errors") or 0):
        return False
    if state.get("last_available") is True:
        return True
    changed_at = float(state.get("last_change_mono") or 0.0)
    return bool(changed_at and now - changed_at <= 900)


def _prioritized_codes(cfg: AppConfig, codes: List[str]) -> List[str]:
    indexed = list(enumerate(codes))
    indexed.sort(key=lambda item: (-_hotel_priority_score(cfg, item[1]), item[0]))
    return [code for _index, code in indexed]


def _runtime_checkpoint_payload(cfg: AppConfig, results: List[HotelResult]) -> Dict[str, Any]:
    now_mono = _now_mono()
    with _HOTEL_RUNTIME_LOCK:
        hotel_runtime = deepcopy(_HOTEL_RUNTIME_STATE)
    for state in hotel_runtime.values():
        changed_at = float(state.pop("last_change_mono", 0.0) or 0.0)
        state["last_change_age_sec"] = max(0, int(now_mono - changed_at)) if changed_at else None
    with _PROGRESS_LOCK:
        progress = {
            key: deepcopy(_PROGRESS.get(key))
            for key in (
                "round", "backoff_multiplier", "unknown_ratio_percent",
                "consecutive_unhealthy_rounds", "effective_interval_sec",
            )
        }
    return {
        "version": 1,
        "results": [asdict(result) for result in results],
        "provider_health": provider_health_snapshot(),
        "hotel_runtime": hotel_runtime,
        "notification": notification_checkpoint_snapshot(),
        "progress": progress,
        "saved_at": _now_wall(),
    }


def _persist_runtime_checkpoint(
    cfg: Optional[AppConfig] = None,
    results: Optional[List[HotelResult]] = None,
) -> None:
    try:
        if cfg is None:
            with _CONFIG_LOCK:
                cfg = deepcopy(_CONFIG)
        if results is None:
            with _RESULTS_LOCK:
                results = deepcopy(_LAST_RESULTS)
        _save_runtime_checkpoint(
            _scan_scope_key(cfg),
            _runtime_checkpoint_payload(cfg, results),
        )
    except Exception as exc:
        _log(f"[checkpoint] save skipped: {exc}")


def _restore_runtime_checkpoint(cfg: Optional[AppConfig] = None) -> bool:
    global _LAST_RESULTS, _RESULTS_REVISION, _CHECKPOINT_RESTORED_SCOPE
    if cfg is None:
        with _CONFIG_LOCK:
            cfg = deepcopy(_CONFIG)
    scope_key = _scan_scope_key(cfg)
    try:
        payload = _load_runtime_checkpoint(scope_key)
    except Exception as exc:
        _log(f"[checkpoint] read skipped: {exc}")
        return False
    if not payload:
        return False

    restored_results: List[HotelResult] = []
    valid_codes = set(cfg.hotel_codes)
    for item in payload.get("results") or []:
        if not isinstance(item, dict) or str(item.get("code") or "") not in valid_codes:
            continue
        try:
            restored_results.append(_hotel_result_from_dict(item))
        except (TypeError, ValueError):
            continue
    if not restored_results:
        return False

    now_mono = _now_mono()
    with _PROVIDER_HEALTH_LOCK:
        _PROVIDER_HEALTH.clear()
        for provider, snapshot in (payload.get("provider_health") or {}).items():
            if not isinstance(snapshot, dict):
                continue
            state = _new_provider_health_state(cfg.per_hotel_delay_seconds)
            for key in (
                "checks", "successful_checks", "access_failures", "consecutive_failures",
                "average_elapsed_ms", "adaptive_multiplier", "cooldown_count",
                "rate_limited_count", "last_http_status", "last_error", "last_checked_at",
            ):
                if key in snapshot:
                    state[key] = deepcopy(snapshot[key])
            state["base_delay_sec"] = max(0.5, float(cfg.per_hotel_delay_seconds))
            state["cooldown_until_mono"] = now_mono + max(
                0, int(snapshot.get("cooldown_remaining_sec") or 0)
            )
            state["latency_samples_ms"] = [
                value for value in (
                    int(snapshot.get("p50_elapsed_ms") or 0),
                    int(snapshot.get("p95_elapsed_ms") or 0),
                ) if value > 0
            ]
            _PROVIDER_HEALTH[str(provider)] = state

    with _HOTEL_RUNTIME_LOCK:
        _HOTEL_RUNTIME_STATE.clear()
        for code, snapshot in (payload.get("hotel_runtime") or {}).items():
            if code not in valid_codes or not isinstance(snapshot, dict):
                continue
            state = deepcopy(snapshot)
            age = state.pop("last_change_age_sec", None)
            state["last_change_mono"] = now_mono - max(0, int(age)) if age is not None else 0.0
            _HOTEL_RUNTIME_STATE[code] = state

    restore_notification_checkpoint(payload.get("notification") or {})
    with _RESULTS_LOCK:
        by_code = {result.code: result for result in restored_results}
        _LAST_RESULTS = [by_code[code] for code in cfg.hotel_codes if code in by_code]
        _RESULTS_REVISION += 1
    with _PROGRESS_LOCK:
        saved_progress = payload.get("progress") or {}
        for key in (
            "round", "backoff_multiplier", "unknown_ratio_percent",
            "consecutive_unhealthy_rounds", "effective_interval_sec",
        ):
            if key in saved_progress:
                _PROGRESS[key] = saved_progress[key]
    _CHECKPOINT_RESTORED_SCOPE = scope_key
    _log(
        f"[checkpoint] restored {len(restored_results)} hotel result(s), "
        f"age={int(payload.get('checkpoint_age_sec') or 0)}s"
    )
    return True


class _ProviderAwareScheduler:
    def __init__(
        self,
        cfg: AppConfig,
        codes: List[str],
        workers: int,
        base_delay: int,
        jitter_percent: int,
    ) -> None:
        self.cfg = cfg
        self.workers = max(1, int(workers))
        self.base_delay = max(1, min(60, int(base_delay)))
        self.jitter_percent = max(0, min(100, int(jitter_percent)))
        self.global_spacing = max(0.15, self.base_delay / self.workers)
        self.queues: Dict[str, deque[Tuple[int, str]]] = {}
        ordered_codes = sorted(
            enumerate(codes),
            key=lambda item: (-_hotel_priority_score(cfg, item[1]), item[0]),
        )
        self.priority_codes = {
            code
            for _index, code in ordered_codes
            if _hotel_is_manual_priority(cfg, code) or _hotel_is_adaptive_priority(code)
        }
        for index, code in ordered_codes:
            provider = _provider_for_code(cfg, code)
            self.queues.setdefault(provider, deque()).append((index, code))
        self.providers = list(dict.fromkeys(_provider_for_code(cfg, code) for code in codes))
        self.provider_next_start = {provider: 0.0 for provider in self.providers}
        self.provider_in_flight = {provider: 0 for provider in self.providers}
        self.global_next_start = 0.0
        self.cursor = 0

    def has_pending(self) -> bool:
        return any(self.queues[provider] for provider in self.providers)

    def pending_count(self) -> int:
        return sum(len(queue) for queue in self.queues.values())

    def priority_pending_count(self) -> int:
        return sum(1 for queue in self.queues.values() for _index, code in queue if code in self.priority_codes)

    def mark_submitted(self, provider: str) -> None:
        self.provider_in_flight[provider] = int(self.provider_in_flight.get(provider, 0)) + 1

    def mark_completed(self, provider: str) -> None:
        self.provider_in_flight[provider] = max(0, int(self.provider_in_flight.get(provider, 0)) - 1)

    def _provider_concurrency_limit(self, provider: str) -> int:
        provider_count = max(1, len(self.providers))
        base_limit = max(1, int(math.ceil(self.workers / provider_count)))
        with _PROVIDER_HEALTH_LOCK:
            state = _PROVIDER_HEALTH.get(provider) or {}
            if int(state.get("consecutive_failures") or 0) or float(state.get("adaptive_multiplier") or 1.0) >= 1.5:
                return 1
        return min(self.workers, base_limit)

    def pop_ready(self, now_mono: Optional[float] = None) -> Tuple[Optional[Tuple[int, str, str]], float]:
        now = _now_mono() if now_mono is None else float(now_mono)
        if not self.has_pending():
            return None, 0.0
        earliest = float("inf")
        provider_count = len(self.providers)
        for offset in range(provider_count):
            position = (self.cursor + offset) % provider_count
            provider = self.providers[position]
            if not self.queues[provider]:
                continue
            if int(self.provider_in_flight.get(provider, 0)) >= self._provider_concurrency_limit(provider):
                continue
            ready_at = max(
                self.global_next_start,
                self.provider_next_start.get(provider, 0.0),
                _provider_cooldown_until(provider),
            )
            earliest = min(earliest, ready_at)
            if ready_at > now:
                continue
            index, code = self.queues[provider].popleft()
            self.cursor = (position + 1) % provider_count
            dynamic_spacing = _provider_dynamic_spacing(provider, self.base_delay)
            self.provider_next_start[provider] = now + _jittered_spacing(dynamic_spacing, self.jitter_percent)
            self.global_next_start = now + _jittered_spacing(self.global_spacing, self.jitter_percent // 2)
            return (index, code, provider), 0.0
        if not math.isfinite(earliest):
            return None, 0.05
        return None, max(0.01, earliest - now)


def _publish_partial_result(result: HotelResult, ordered_codes: List[str]) -> None:
    global _LAST_RESULTS, _RESULTS_REVISION
    with _RESULTS_LOCK:
        by_code = {item.code: item for item in _LAST_RESULTS}
        by_code[result.code] = result
        _LAST_RESULTS = [by_code[code] for code in ordered_codes if code in by_code]
        _RESULTS_REVISION += 1


def _round_wait_seconds(
    target_interval_sec: int,
    round_started_mono: float,
    jitter_percent: int,
    now_mono: Optional[float] = None,
    minimum_pause_sec: float = 3.0,
) -> Tuple[float, float, float]:
    target_period = min(
        3600.0,
        _jittered_delay(max(30, int(target_interval_sec)), max(0, min(50, int(jitter_percent)))),
    )
    current = _now_mono() if now_mono is None else float(now_mono)
    scan_elapsed = max(0.0, current - float(round_started_mono))
    wait_seconds = min(3600.0, max(float(minimum_pause_sec), target_period - scan_elapsed))
    return wait_seconds, target_period, scan_elapsed


def _parallel_allowed(cfg: AppConfig) -> bool:
    return bool(
        getattr(cfg, "smart_parallel_enabled", False)
        and getattr(cfg, "engine", "http") == "http"
        and int(getattr(cfg, "smart_parallel_workers", 1) or 1) > 1
    )


def _check_hotels_parallel_http(
    cfg: AppConfig,
    codes: List[str],
    start: str,
    end: str,
    *,
    allow_cache: bool = False,
) -> List[HotelResult]:
    workers = max(1, min(3, int(getattr(cfg, "smart_parallel_workers", DEFAULT_SMART_PARALLEL_WORKERS) or 1)))
    base_delay = max(1, min(60, int(cfg.per_hotel_delay_seconds)))
    jitter = getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT)
    results: List[Optional[HotelResult]] = [None] * len(codes)
    scheduler = _ProviderAwareScheduler(cfg, codes, workers, base_delay, jitter)
    with _PROGRESS_LOCK:
        _PROGRESS["queue_pending"] = scheduler.pending_count()
        _PROGRESS["in_flight"] = 0
        _PROGRESS["priority_pending"] = scheduler.priority_pending_count()

    _log(
        f"[parallel] Provider-aware scheduling enabled: workers={workers}, "
        f"providers={len(scheduler.providers)}, per-provider delay={base_delay}s, "
        f"cross-provider spacing={scheduler.global_spacing:.2f}s"
    )

    def _run_one(idx: int, code: str, provider: str) -> Tuple[int, str, HotelResult]:
        _set_action(f"[search:{provider}] Checking hotel {code} for {start} → {end}...")
        _log(f"[search:{provider}] Checking hotel {code} for {start} → {end}...")
        try:
            result = (
                _check_hotel_cached(cfg, None, code, start, end)
                if allow_cache
                else check_hotel(cfg, None, code, start, end)
            )
        except Exception as e:
            _log(f"[error] check {code}: {e}")
            result = HotelResult(
                code=code,
                url=build_url(cfg, code, start, end),
                name=None,
                available=None,
                provider=provider,
                error_summary=" ".join(str(e).split())[:240],
            )
        result.provider = provider
        return idx, provider, result

    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(codes))), thread_name_prefix="smart-search") as executor:
        in_flight: Dict[Future, Tuple[int, str, str]] = {}
        while (scheduler.has_pending() or in_flight) and not _stop_event.is_set():
            next_ready_delay: Optional[float] = None
            while scheduler.has_pending() and len(in_flight) < workers and not _stop_event.is_set():
                task, delay = scheduler.pop_ready()
                if task is None:
                    next_ready_delay = delay
                    break
                idx, code, provider = task
                future = executor.submit(_run_one, idx, code, provider)
                in_flight[future] = (idx, code, provider)
                scheduler.mark_submitted(provider)
                with _PROGRESS_LOCK:
                    _PROGRESS["queue_pending"] = scheduler.pending_count()
                    _PROGRESS["in_flight"] = len(in_flight)
                    _PROGRESS["priority_pending"] = scheduler.priority_pending_count()

            if not in_flight:
                if scheduler.has_pending() and _stop_event.wait(timeout=max(0.01, next_ready_delay or 0.05)):
                    break
                continue

            timeout = None
            if scheduler.has_pending() and len(in_flight) < workers:
                timeout = max(0.01, next_ready_delay or 0.05)
            completed, _pending = wait(tuple(in_flight), timeout=timeout, return_when=FIRST_COMPLETED)
            if not completed:
                continue
            for future in completed:
                expected_idx, expected_code, expected_provider = in_flight.pop(future)
                scheduler.mark_completed(expected_provider)
                try:
                    idx, provider, result = future.result()
                except Exception as exc:
                    _log(f"[parallel] worker exception for {expected_code}: {exc}")
                    idx, provider = expected_idx, expected_provider
                    result = HotelResult(
                        code=expected_code,
                        url=build_url(cfg, expected_code, start, end),
                        name=None,
                        available=None,
                        provider=expected_provider,
                        error_summary=" ".join(str(exc).split())[:240],
                    )
                results[idx] = result
                _record_provider_result(provider, result)
                _record_hotel_runtime_result(result)
                with _PROGRESS_LOCK:
                    _PROGRESS["done"] = min(_PROGRESS["done"] + 1, _PROGRESS["total"])
                    _PROGRESS["queue_pending"] = scheduler.pending_count()
                    _PROGRESS["in_flight"] = len(in_flight)
                    _PROGRESS["priority_pending"] = scheduler.priority_pending_count()
                _publish_partial_result(result, codes)

    return [
        r if r is not None else HotelResult(
            code=codes[idx],
            url=build_url(cfg, codes[idx], start, end),
            name=None,
            available=None,
            provider=_provider_for_code(cfg, codes[idx]),
            error_summary="scan interrupted",
        )
        for idx, r in enumerate(results)
    ]


# ========= Worker Loop =========
def _worker_loop(run_once: bool = False):
    global _LAST_RESULTS, _RESULTS_REVISION, _PROGRESS, _UPTIME_STARTED, _UPTIME_STARTED_MONO, _RUN_REQUESTED, _CHECKPOINT_RESTORED_SCOPE
    _log("Worker loop started.")
    _set_action("Worker loop started.")
    _UPTIME_STARTED = _now_wall()
    _UPTIME_STARTED_MONO = _now_mono()
    with _CONFIG_LOCK:
        cfg = deepcopy(_CONFIG)
        start, end = cfg.start_date, cfg.end_date
    current_scope = _scan_scope_key(cfg)
    if _CHECKPOINT_RESTORED_SCOPE == current_scope:
        _CHECKPOINT_RESTORED_SCOPE = ""
        with _PROVIDER_HEALTH_LOCK:
            for state in _PROVIDER_HEALTH.values():
                state["base_delay_sec"] = max(0.5, float(cfg.per_hotel_delay_seconds))
    else:
        _reset_provider_health(
            [_provider_for_code(cfg, code) for code in cfg.hotel_codes],
            getattr(cfg, "per_hotel_delay_seconds", DEFAULT_PER_HOTEL_DELAY_SECONDS),
        )

    renderer = None
    if getattr(cfg, "engine", "playwright") == "playwright" and _HAS_PLAYWRIGHT:
        renderer = PlaywrightRenderer(cfg)
    elif getattr(cfg, "engine", "playwright") == "playwright" and not _HAS_PLAYWRIGHT:
        _log("[engine] Playwright is unavailable; using HTTP/API engine for this run.")
        cfg.engine = "http"

    with _PROGRESS_LOCK:
        consecutive_unhealthy_rounds = max(
            0, int(_PROGRESS.get("consecutive_unhealthy_rounds") or 0)
        )
        previous_backoff_multiplier = max(
            1, int(_PROGRESS.get("backoff_multiplier") or 1)
        )

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
            _PROGRESS["queue_pending"] = len(cfg.hotel_codes)
            _PROGRESS["in_flight"] = 0
            _PROGRESS["priority_pending"] = sum(
                1
                for code in cfg.hotel_codes
                if _hotel_is_manual_priority(cfg, code) or _hotel_is_adaptive_priority(code)
            )
            _PROGRESS["round_started"] = _now_wall()
            _PROGRESS["round_started_mono"] = _now_mono()
        current_round = _PROGRESS["round"]
        round_started_mono = _PROGRESS["round_started_mono"]
        results: List[HotelResult] = []
        if _parallel_allowed(cfg):
            results = _check_hotels_parallel_http(
                cfg,
                list(cfg.hotel_codes),
                start,
                end,
                allow_cache=not run_once,
            )
        else:
            if getattr(cfg, "smart_parallel_enabled", False) and getattr(cfg, "engine", "http") != "http":
                _log("[parallel] Smart Parallel is only used with HTTP/API engine; running single-line search.")
            scan_codes = _prioritized_codes(cfg, list(cfg.hotel_codes))
            results_by_code: Dict[str, HotelResult] = {}
            for index, code in enumerate(scan_codes):
                if _stop_event.is_set():
                    break
                _set_action(f"[search] Checking hotel {code} for {start} → {end}...")
                _log(f"[search] Checking hotel {code} for {start} → {end}...")
                try:
                    result = (
                        _check_hotel_cached(cfg, renderer, code, start, end)
                        if not run_once
                        else check_hotel(cfg, renderer, code, start, end)
                    )
                except Exception as e:
                    _log(f"[error] check {code}: {e}")
                    result = HotelResult(code=code, url=build_url(cfg, code, start, end), name=None, available=None)
                result.provider = _provider_for_code(cfg, code)
                results_by_code[code] = result
                _record_provider_result(_provider_for_code(cfg, code), result)
                _record_hotel_runtime_result(result)
                with _PROGRESS_LOCK:
                    _PROGRESS["done"] = min(_PROGRESS["done"] + 1, _PROGRESS["total"])
                    _PROGRESS["queue_pending"] = max(0, len(scan_codes) - index - 1)
                    _PROGRESS["priority_pending"] = sum(
                        1 for pending_code in scan_codes[index + 1:]
                        if _hotel_is_manual_priority(cfg, pending_code) or _hotel_is_adaptive_priority(pending_code)
                    )
                _publish_partial_result(result, list(cfg.hotel_codes))
                if index < len(scan_codes) - 1:
                    per_hotel_delay = _jittered_delay(
                        max(1, min(60, int(cfg.per_hotel_delay_seconds))),
                        getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT),
                    )
                    if _stop_event.wait(timeout=per_hotel_delay):
                        break
            results = [results_by_code[code] for code in cfg.hotel_codes if code in results_by_code]

        newly_available_codes: List[str] = []
        try:
            newly_available_codes = process_notifications(cfg, results, start, end)
        except Exception as e:
            _log(f"[error] notify: {e}")
        try:
            _record_analytics_results(cfg, results)
        except Exception as e:
            _log(f"[analytics] record skipped: {e}")

        with _RESULTS_LOCK:
            _LAST_RESULTS = results
            _RESULTS_REVISION += 1
        with _PROGRESS_LOCK:
            _PROGRESS["done"] = _PROGRESS["total"]
            _PROGRESS["queue_pending"] = 0
            _PROGRESS["in_flight"] = 0
            _PROGRESS["priority_pending"] = 0

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

        backoff_multiplier, consecutive_unhealthy_rounds, unknown_ratio_percent = _adaptive_backoff_state(
            results,
            consecutive_unhealthy_rounds,
            bool(getattr(cfg, "adaptive_backoff_enabled", DEFAULT_ADAPTIVE_BACKOFF_ENABLED)) and not run_once,
        )
        effective_base_interval = min(
            3600,
            max(30, int(cfg.loop_interval_seconds)) * backoff_multiplier,
        )
        with _PROGRESS_LOCK:
            _PROGRESS["backoff_multiplier"] = backoff_multiplier
            _PROGRESS["unknown_ratio_percent"] = unknown_ratio_percent
            _PROGRESS["consecutive_unhealthy_rounds"] = consecutive_unhealthy_rounds
            _PROGRESS["effective_interval_sec"] = effective_base_interval
        if backoff_multiplier > 1:
            _log(
                f"[safety] Adaptive backoff {backoff_multiplier}x: "
                f"unknown={unknown_ratio_percent}%, next base wait={effective_base_interval}s"
            )
        elif previous_backoff_multiplier > 1:
            _log("[safety] Healthy round detected; adaptive backoff returned to 1x.")
        previous_backoff_multiplier = backoff_multiplier

        if not run_once:
            _persist_runtime_checkpoint(cfg, results)

        if run_once:
            _RUN_REQUESTED = False
            _set_action("Single scan complete.")
            _log("Single scan complete; worker is stopping.")
            break

        # Target-start cadence: scan time counts toward the requested round interval.
        wait_s, target_period, scan_elapsed = _round_wait_seconds(
            effective_base_interval,
            round_started_mono,
            max(0, min(50, int(getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT)) // 2)),
        )
        with _PROGRESS_LOCK:
            _PROGRESS["phase"] = "waiting"
            _PROGRESS["wait_started_mono"] = _now_mono()
            _PROGRESS["wait_total_sec"] = int(round(wait_s))
            _PROGRESS["wait_elapsed_sec"] = 0
            _PROGRESS["effective_interval_sec"] = int(round(target_period))
        _set_action(
            f"Round {current_round} complete in {scan_elapsed:.1f}s. "
            f"Next target cycle {target_period:.1f}s; waiting {wait_s:.1f}s..."
        )
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
                    r = _check_hotel_cached(
                        cfg,
                        renderer,
                        code,
                        start,
                        end,
                        allow_cache=False,
                        force_refresh=True,
                    )
                    _record_provider_result(_provider_for_code(cfg, code), r)
                    _record_hotel_runtime_result(r)
                    enhanced_results.append(r)
                    if r.available is not True:
                        watch_codes.discard(code)
                        _log(f"[enhanced] Availability changed for {code}; enhanced confirmation stopped for this hotel.")
                except Exception as e:
                    _log(f"[enhanced] recheck {code} failed: {e}")
                    watch_codes.discard(code)
                    failed_provider = _provider_for_code(cfg, code)
                    failed_result = HotelResult(
                        code=code,
                        url=build_url(cfg, code, start, end),
                        name=None,
                        available=None,
                        provider=failed_provider,
                    )
                    _record_provider_result(failed_provider, failed_result)
                    _record_hotel_runtime_result(failed_result)
                    enhanced_results.append(failed_result)
            if enhanced_results:
                try:
                    process_notifications(cfg, enhanced_results, start, end)
                except Exception as e:
                    _log(f"[enhanced] notify failed: {e}")
                try:
                    _record_analytics_results(cfg, enhanced_results, source="enhanced")
                except Exception as e:
                    _log(f"[analytics] enhanced record skipped: {e}")
                with _RESULTS_LOCK:
                    by_code = {r.code: r for r in _LAST_RESULTS}
                    for r in enhanced_results:
                        by_code[r.code] = r
                    _LAST_RESULTS = [by_code.get(r.code, r) for r in _LAST_RESULTS]
                    _RESULTS_REVISION += 1
                _persist_runtime_checkpoint(cfg)
        if _stop_event.is_set():
            break

    if isinstance(renderer, PlaywrightRenderer):
        renderer.close()
    if not run_once:
        _persist_runtime_checkpoint(cfg)
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
        trigger_class = "hotel-info-trigger"
        name_html = (
            f"<a class='{trigger_class}' data-hotel-code='{_html_attr(r.code)}' "
            f"href='{_html_attr(r.url)}' target='_blank' rel='noreferrer noopener'>"
            f"{html.escape(r.name or '(Hotel name not found)')}</a>"
        )
        for idx, row in enumerate(by_offers):
            code_cell = (r.display_code or r.code) if idx == 0 else ""
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
        f"<option value='{code}' {'selected' if current_primary_language == code else ''}>{info['label']}</option>"
        for code, info in LANGUAGE_OPTIONS.items()
    )
    page_html = f"""
    <html><head><meta charset='utf-8'><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{APP_NAME}</title>
    <meta name="theme-color" content="#155ec2">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <link rel="icon" type="image/png" href="/static/toyoko-chan-mascot.png?v=3">
    <link rel="apple-touch-icon" href="/static/toyoko-chan-mascot.png?v=3">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="stylesheet" href="/static/app.css?v={APP_VERSION}-traffic-1">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"></head>
	        <body data-theme="light" data-app-version="{APP_VERSION}">
	          <div class="app-shell">
	            <aside class="app-sidebar" id="app-sidebar" aria-label="Primary navigation">
	              <button class="sidebar-collapse-button" id="sidebar-collapse-button" type="button" aria-label="Collapse navigation" aria-expanded="true" title="Collapse navigation">‹</button>
	              <div class="sidebar-brand">
	                <span class="sidebar-brand-mark"><img src="/static/toyoko-chan-mascot.png?v=3" alt=""></span>
	                <div><strong>{APP_NAME}</strong><span>Vacancy workspace</span></div>
	              </div>
	              <nav class="sidebar-nav">
	                <button class="sidebar-nav-item active" data-app-view="home" aria-current="page"><span class="nav-icon">⌂</span><span class="nav-label">首页 / Home</span></button>
	                <button class="sidebar-nav-item" data-app-view="search"><span class="nav-icon">⌕</span><span class="nav-label">空房检索 / Vacancy Search</span></button>
	                <button class="sidebar-nav-item" data-app-view="monitor"><span class="nav-icon">◉</span><span class="nav-label">空房监控 / Vacancy Monitor</span><span class="nav-live-dot" aria-hidden="true"></span></button>
	                <button class="sidebar-nav-item" data-app-view="search-settings"><span class="nav-icon">≡</span><span class="nav-label">搜索设定 / Search Settings</span></button>
	                <button class="sidebar-nav-item" data-app-view="push-settings"><span class="nav-icon">✉</span><span class="nav-label">推送设定 / Push Settings</span></button>
	              </nav>
	              <div class="sidebar-utilities" aria-label="Interface tools">
	                <div class="language-menu-wrap">
	                  <button class="icon-button" id="language-menu-button" type="button" aria-haspopup="menu" aria-expanded="false" aria-label="Language" title="Language">🌐</button>
	                  <div class="language-menu" id="language-menu" role="menu" hidden>
	                    <button type="button" role="menuitemradio" data-language="zh_cn">中文（简体）</button>
	                    <button type="button" role="menuitemradio" data-language="zh_tw">中文（繁體）</button>
	                    <button type="button" role="menuitemradio" data-language="ja">日本語</button>
	                    <button type="button" role="menuitemradio" data-language="ko">한국어</button>
	                    <button type="button" role="menuitemradio" data-language="en">English</button>
	                  </div>
	                </div>
	                <button class="icon-button" id="theme-toggle-button" type="button" aria-label="Theme" title="Theme">◐</button>
	                <button class="icon-button" id="guide-open-button" type="button" aria-label="Guide" title="Guide">?</button>
	                <button class="icon-button update-open-button" id="update-open-button" type="button" aria-label="Software update" title="Software update"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v11m0 0 4-4m-4 4-4-4M5 18.5h14"/></svg></button>
	                <button class="icon-button interface-settings-button" id="interface-settings-button" data-app-view="interface" type="button" aria-label="Interface Settings" title="Interface Settings">⚙</button>
	              </div>
	              <div class="sidebar-footer-status">
	                <span class="sidebar-status-dot" id="sidebar-status-dot"></span>
	                <div><strong id="sidebar-status-text">STOPPED</strong><span id="sidebar-hotel-count">0 hotels</span></div>
	              </div>
	            </aside>
	            <button class="sidebar-scrim" id="sidebar-scrim" type="button" aria-label="Close navigation" hidden></button>
	            <main class="app-main">
	          <div class="topbar">
	            <button class="icon-button mobile-nav-button" id="mobile-nav-button" type="button" aria-label="Open navigation" title="Navigation">☰</button>
	            <h2>{APP_NAME}</h2>
	          </div>
          <nav class="command-dock" aria-label="Search controls">
            <div class="command-state">
              <span class="command-dot" id="command-dot" aria-hidden="true"></span>
              <div>
                <strong id="dock-status">STOPPED 已停止</strong>
                <span id="dock-summary">尚未选择酒店 No hotels selected</span>
                <span id="dock-config-state" class="config-state clean">配置已同步 Configuration ready</span>
                <span id="connection-state" class="connection-state online">连接正常 Connected</span>
              </div>
            </div>
            <div class="run-actions">
	              <button id="btn_scan_once">单次检索 Scan Once</button>
	              <button class="primary" id="btn_start">启动 Start</button>
	              <button class="danger" id="btn_stop" disabled>停止 Stop</button>
	            </div>
	          </nav>

	          <section class="app-view active" id="view-home" data-view="home" aria-label="Home">
	            <div class="home-dashboard">
	              <header class="home-welcome-card">
	                <div class="home-welcome-copy">
	                  <span class="home-eyebrow" id="home-eyebrow">今日监控台</span>
	                  <h1 id="home-greeting">欢迎回来</h1>
	                  <p id="home-hero-summary">正在读取上次的检索与监控状态…</p>
	                  <div class="home-welcome-actions">
	                    <button class="primary" id="home-primary-action" type="button">建立检索</button>
	                    <button id="home-secondary-action" type="button">查看监控</button>
	                  </div>
	                </div>
	                <div class="home-mascot-stage" aria-hidden="true">
	                  <span class="home-orbit home-orbit-one"></span>
	                  <span class="home-orbit home-orbit-two"></span>
	                  <img src="/static/toyoko-chan-mascot.png?v=3" alt="">
	                </div>
	                <div class="home-live-state">
	                  <span class="home-live-dot" id="home-live-dot"></span>
	                  <div><small id="home-live-label">监控状态</small><strong id="home-live-value">已停止</strong></div>
	                  <div class="home-next-scan"><small id="home-next-label">下次检索</small><strong id="home-next-value">—</strong></div>
	                </div>
	              </header>

	              <div class="home-metric-grid" aria-label="Monitoring overview">
	                <button class="home-metric-card status" type="button" data-home-nav="monitor">
	                  <span class="home-metric-icon">◉</span><span class="home-metric-label" id="home-metric-status-label">监控状态</span>
	                  <strong id="home-metric-status">已停止</strong><small id="home-metric-status-note">准备开始</small>
	                </button>
	                <button class="home-metric-card available" type="button" data-home-nav="monitor">
	                  <span class="home-metric-icon">✓</span><span class="home-metric-label" id="home-metric-available-label">当前空房</span>
	                  <strong id="home-metric-available">0</strong><small id="home-metric-available-note">0 家酒店</small>
	                </button>
	                <button class="home-metric-card hotels" type="button" data-home-nav="search">
	                  <span class="home-metric-icon">⌂</span><span class="home-metric-label" id="home-metric-hotels-label">监控酒店</span>
	                  <strong id="home-metric-hotels">0</strong><small id="home-metric-hotels-note">尚未选择</small>
	                </button>
	                <button class="home-metric-card next" type="button" data-home-nav="monitor">
	                  <span class="home-metric-icon">↻</span><span class="home-metric-label" id="home-metric-next-label">下次检索</span>
	                  <strong id="home-metric-next">—</strong><small id="home-metric-next-note">等待启动</small>
	                </button>
	                <div class="home-metric-card traffic" id="home-traffic-card" title="WebUI 应用层流量估算">
	                  <span class="home-metric-icon">⇅</span><span class="home-metric-label" id="home-metric-traffic-label">WebUI 流量</span>
	                  <strong id="home-metric-traffic-down">↓ 0 B</strong><small id="home-metric-traffic-note">↑ 0 B · 0 次访问</small>
	                </div>
	              </div>

	              <div class="home-content-grid">
	                <article class="home-card home-task-card">
	                  <header><div><span class="home-card-kicker" id="home-task-kicker">当前任务</span><h2 id="home-task-title">尚未建立监控任务</h2></div><span class="home-task-state" id="home-task-state">待配置</span></header>
	                  <div class="home-task-route">
	                    <div><small id="home-checkin-label">入住</small><strong id="home-task-checkin">—</strong></div>
	                    <span>→</span>
	                    <div><small id="home-checkout-label">退房</small><strong id="home-task-checkout">—</strong></div>
	                  </div>
	                  <div class="home-task-details">
	                    <span id="home-task-guests">1 人 · 1 房</span>
	                    <span id="home-task-preference">无烟房 · 不限房型</span>
	                    <span id="home-task-scope">尚未选择区域</span>
	                  </div>
	                  <div class="home-provider-chips" id="home-provider-chips"></div>
	                  <footer><button id="home-edit-search" type="button">修改条件</button><button class="primary" id="home-view-results" type="button">查看实时结果</button></footer>
	                </article>

	                <article class="home-card home-activity-card">
	                  <header><div><span class="home-card-kicker" id="home-activity-kicker">实时动态</span><h2 id="home-activity-title">最新空房变化</h2></div><button class="home-text-button" id="home-events-more" type="button">全部事件</button></header>
	                  <div class="home-activity-list" id="home-activity-list"><div class="home-empty-state">正在读取动态…</div></div>
	                </article>
	              </div>

	              <div class="home-bottom-grid">
	                <article class="home-card home-insight-card">
	                  <header><div><span class="home-card-kicker" id="home-trend-kicker">数据洞察</span><h2 id="home-trend-title">空房与价格趋势</h2></div><button class="home-text-button" id="home-trend-more" type="button">查看趋势</button></header>
	                  <div class="home-insight-summary"><strong id="home-trend-observations">0</strong><span id="home-trend-observations-label">条历史记录</span></div>
	                  <div class="home-trend-list" id="home-trend-list"><div class="home-empty-state">数据会在检索后自动积累</div></div>
	                </article>

	                <article class="home-card home-quick-card">
	                  <header><div><span class="home-card-kicker" id="home-quick-kicker">快捷入口</span><h2 id="home-quick-title">开始新的操作</h2></div></header>
	                  <div class="home-quick-grid">
	                    <button type="button" data-home-quick="area"><i>⌖</i><span id="home-quick-area">区域检索</span></button>
	                    <button type="button" data-home-quick="radius"><i>◎</i><span id="home-quick-radius">方圆检索</span></button>
	                    <button type="button" data-home-quick="history"><i>↶</i><span id="home-quick-history">搜索记录</span></button>
	                    <button type="button" data-home-quick="push"><i>✉</i><span id="home-quick-push">推送设定</span></button>
	                  </div>
	                </article>

	                <article class="home-card home-health-card">
	                  <header><div><span class="home-card-kicker" id="home-health-kicker">系统状态</span><h2 id="home-health-title">服务运行状态</h2></div><span class="home-health-badge" id="home-health-badge">检查中</span></header>
	                  <div class="home-health-list">
	                    <div><span id="home-health-connection-label">WebUI 连接</span><strong id="home-health-connection">正常</strong></div>
	                    <div><span id="home-health-providers-label">酒店来源</span><strong id="home-health-providers">等待</strong></div>
	                    <div><span id="home-health-notifications-label">推送渠道</span><strong id="home-health-notifications">0 个启用</strong></div>
	                    <div><span id="home-health-data-label">历史数据</span><strong id="home-health-data">0 条</strong></div>
	                  </div>
	                </article>
	              </div>
	            </div>
	          </section>

	          <section class="app-view" id="view-search" data-view="search" aria-label="Vacancy Search" hidden>
	           <details class="box search-panel" id="search_panel" open>
             <summary>搜索 Search</summary>
	             <div class="search-head">
	               <div>
	                 <div class="search-title">空房检索条件</div>
	                 <div class="search-subtitle">选择日期、入住条件和酒店范围；启动后会自动写入搜索记录。</div>
	               </div>
	               <button class="search-reset" id="btn_default" type="button"><span aria-hidden="true">↺</span> 默认 Default</button>
	             </div>

	             <div class="search-conditions">
	               <div class="stay-row">
	                 <div class="field-control">
	                   <label for="start_date">入住 Check-in</label>
	                   <input id='start_date' type='date' value='{_html_attr(cfg.start_date)}'>
	                 </div>
	                 <div class="field-control">
	                   <label for="end_date">退房 Check-out</label>
	                   <input id='end_date' type='date' value='{_html_attr(cfg.end_date)}'>
	                 </div>
	                 <div class="field-control quick-date-field">
	                   <label>快捷日期 Quick Dates</label>
	                   <div class="quick-actions" aria-label="Quick dates">
	                     <button id="btn_today" type="button">今晚 Tonight</button>
	                     <button id="btn_tomorrow" type="button">明晚 Tomorrow</button>
	                     <button id="btn_weekend" type="button">周末 Weekend</button>
	                   </div>
	                 </div>
	                 <div class="field-control compact-number">
	                   <label for="people">人数 People</label>
	                   <div class="number-stepper">
	                     <button type="button" class="step-button" data-step-target="people" data-step-delta="-1" aria-label="Decrease people">−</button>
	                     <input id='people' type='number' min='1' max='5' step='1' value='{cfg.people}'>
	                     <button type="button" class="step-button" data-step-target="people" data-step-delta="1" aria-label="Increase people">+</button>
	                   </div>
	                 </div>
	                 <div class="field-control compact-number">
	                   <label for="rooms">房间 Rooms</label>
	                   <div class="number-stepper">
	                     <button type="button" class="step-button" data-step-target="rooms" data-step-delta="-1" aria-label="Decrease rooms">−</button>
	                     <input id='rooms' type='number' min='1' max='9' step='1' value='{cfg.rooms}'>
	                     <button type="button" class="step-button" data-step-target="rooms" data-step-delta="1" aria-label="Increase rooms">+</button>
	                   </div>
	                 </div>
	               </div>
	               <div class="preference-row">
	                 <div class="field-control">
	                   <label for="smoking">吸烟 Smoking</label>
	                   <select id='smoking'>
	                     <option value='noSmoking' {'selected' if cfg.smoking == 'noSmoking' else ''}>无烟房 Non-Smoking</option>
	                     <option value='Smoking'   {'selected' if cfg.smoking == 'Smoking' else ''}>吸烟房 Smoking</option>
	                     <option value='all'       {'selected' if cfg.smoking == 'all' else ''}>不限制 Any</option>
	                   </select>
	                 </div>
	                 <div class="field-control">
	                   <label for="room_requirement">房型 Room Type</label>
	                   <select id="room_requirement">
	                     <option value="any"   {'selected' if current_room_requirement == 'any' else ''}>不限制 Any</option>
	                     <option value="single"{'selected' if current_room_requirement == 'single' else ''}>单人房 Single</option>
	                     <option value="double"{'selected' if current_room_requirement == 'double' else ''}>大床房 Double</option>
	                     <option value="twin"  {'selected' if current_room_requirement == 'twin' else ''}>双床房 Twin</option>
	                   </select>
	                 </div>
	                 <div class="field-control">
	                   <label for="membership_status">会员状态 Membership</label>
	                   <select id="membership_status">
	                     <option value="member" {'selected' if current_membership_status == 'member' else ''}>会员 Member</option>
	                     <option value="non_member" {'selected' if current_membership_status == 'non_member' else ''}>非会员 Non-member</option>
	                     <option value="unknown" {'selected' if current_membership_status == 'unknown' else ''}>未知 Unknown</option>
	                   </select>
	                 </div>
	                 <div class="provider-selector" id="provider_selector">
	                   <div class="provider-selector-head">
	                     <span class="provider-selector-title">酒店品牌 Hotel Brands</span>
	                   </div>
	                   <div class="provider-options">
	                     <button id="btn_provider_all" class="provider-all" type="button" aria-pressed="true">全部 All</button>
	                     <label class="provider-choice toyoko"><input id="provider_toyoko" type="checkbox" {'checked' if 'toyoko' in getattr(cfg, 'enabled_providers', DEFAULT_ENABLED_PROVIDERS) else ''}><i></i><span>东横 Toyoko Inn</span></label>
	                     <label class="provider-choice routeinn"><input id="provider_routeinn" type="checkbox" {'checked' if 'routeinn' in getattr(cfg, 'enabled_providers', DEFAULT_ENABLED_PROVIDERS) else ''}><i></i><span>露樱 Route Inn Hotels</span></label>
	                     <label class="provider-choice dormy"><input id="provider_dormy" type="checkbox" {'checked' if 'dormy' in getattr(cfg, 'enabled_providers', DEFAULT_ENABLED_PROVIDERS) else ''}><i></i><span>多美迎 Dormy Inn</span></label>
	                     <label class="provider-choice mystays"><input id="provider_mystays" type="checkbox" {'checked' if 'mystays' in getattr(cfg, 'enabled_providers', DEFAULT_ENABLED_PROVIDERS) else ''}><i></i><span>MYSTAYS Hotel</span></label>
	                     <label class="provider-choice daiwa"><input id="provider_daiwa" type="checkbox" {'checked' if 'daiwa' in getattr(cfg, 'enabled_providers', DEFAULT_ENABLED_PROVIDERS) else ''}><i></i><span>大和ROYNET Daiwa Roynet</span></label>
	                   </div>
	                 </div>
	               </div>
	             </div>

	             <section id="area_picker_panel" aria-label="Hotel picker">
	               <div class="area-picker-config">
	                 <div class="mode-tabs" id="hotel_picker_mode_tabs">
	                   <label><input type="radio" name="hotel_picker_mode" value="area" {'checked' if getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE) != "radius" else ''}> 区域模式 Area</label>
	                   <label><input type="radio" name="hotel_picker_mode" value="radius" {'checked' if getattr(cfg, "search_mode", DEFAULT_SEARCH_MODE) == "radius" else ''}> 方圆模式 Radius</label>
	                 </div>
	                 <div id="area_mode_panel" class="picker-mode">
	                   <div class="scope-config area-scope-config">
	                     <div class="field-control">
	                       <label for="area_region">大区域 Region</label>
	                       <select id="area_region">
	                         <option value="">请选择 Select Region</option>
	                       </select>
	                     </div>
	                     <div class="field-control">
	                       <label for="area_detail">详细区域 Detail Area</label>
	                       <select id="area_detail" disabled>
	                         <option value="">先选择大区域 Select a region first</option>
	                       </select>
	                     </div>
	                     <button id="btn_area_load" class="primary">加载酒店 Load Hotels</button>
	                   </div>
	                 </div>
	                 <div id="radius_mode_panel" class="picker-mode">
	                   <div class="scope-config radius-grid">
	                     <div class="field-control">
	                       <label for="radius_query">地名地址或者坐标 Place, Address, or Coordinates</label>
	                       <input id="radius_query" type="text" value="{_html_attr(getattr(cfg, 'radius_query', ''))}" placeholder="东京站或 35.6812,139.7671">
	                     </div>
	                     <div class="field-control radius-control">
	                       <label for="radius_km">方圆半径 Radius <b><span id="radius_km_val">{getattr(cfg, 'radius_km', DEFAULT_RADIUS_KM)}</span> km</b></label>
	                       <input id="radius_km" type="range" min="1" max="50" step="1" value="{getattr(cfg, 'radius_km', DEFAULT_RADIUS_KM)}">
	                     </div>
	                     <button id="btn_radius_load" class="primary">查找附近酒店 Load Nearby</button>
	                   </div>
	                 </div>
	                 <input id="radius_lat" type="hidden" value="{getattr(cfg, 'radius_lat', '') if getattr(cfg, 'radius_lat', None) is not None else ''}">
	                 <input id="radius_lng" type="hidden" value="{getattr(cfg, 'radius_lng', '') if getattr(cfg, 'radius_lng', None) is not None else ''}">
	                 <span class="selection-summary" id="area_selection_summary">已选 0 / 0 Selected</span>
	               </div>
	               <div class="area-status-row">
	                 <span id="area_status" role="status" aria-live="polite">选择大区域；详细区域可不选，默认加载整个大区域。勾选酒店后直接点击 Start 搜索。</span>
	               </div>
	               <div class="hotel-picker-toolbar">
	                 <div class="hotel-filter-wrap">
	                   <span aria-hidden="true">⌕</span>
	                   <input id="area_filter" class="hotel-filter" type="search" placeholder="按酒店名或编号过滤">
	                 </div>
	                 <button id="btn_area_selected_only" type="button" aria-pressed="false">仅看已选 Selected</button>
	                 <label class="hotel-sort-control"><span>排序 Sort</span><select id="area_sort">
	                   <option value="default">默认 Default</option>
	                   <option value="distance">距离 Distance</option>
	                   <option value="name">名称 Name</option>
	                   <option value="code">编号 Code</option>
	                 </select></label>
	                 <button id="btn_area_all">全选 Select All</button>
	                 <button id="btn_area_none">全不选 Select None</button>
	               </div>
	               <div class="hotel-workspace-tabs" role="tablist" aria-label="Hotel view">
	                 <button type="button" class="active" data-hotel-workspace-view="list" aria-pressed="true">列表 List</button>
	                 <button type="button" data-hotel-workspace-view="map" aria-pressed="false">地图 Map</button>
	               </div>
	               <div class="hotel-workspace" id="hotel_workspace" data-mobile-view="list">
	                 <div class="hotel-list-pane">
	                   <div class="hotel-list-meta"><span id="area_visible_summary">0 hotels</span></div>
	                   <div id="area_hotels" class="hotel-picker">
	                     <div class="hotel-picker-empty">尚未加载酒店 No hotels loaded yet</div>
	                   </div>
	                 </div>
	                 <div id="area_map_panel" class="selected-map-panel hotel-map-pane" hidden>
	                   <div class="selected-map-head">
	                     <div>
	                       <div class="selected-map-title">已选酒店地图 Selected Hotel Map</div>
	                       <div class="help" id="area_map_status">地图会显示当前已勾选且带坐标的酒店。</div>
	                     </div>
	                     <div id="area_map_legend" class="map-provider-legend"></div>
	                   </div>
	                   <div id="area_selected_map" class="selected-map-canvas"></div>
	                 </div>
	               </div>
	               <div id="hotel_catalog_panel" class="catalog-status" aria-live="polite">
	                 <span id="hotel_catalog_dot" class="catalog-status-dot" aria-hidden="true"></span>
	                 <div class="catalog-status-copy">
	                   <div id="hotel_catalog_title" class="catalog-status-title">酒店数据 Hotel Data</div>
	                   <div id="hotel_catalog_meta" class="catalog-status-meta">等待后台检查 Waiting for background check</div>
	                   <div id="provider_catalog_meta" class="catalog-status-meta">其他品牌本地数据库等待检查 Other-brand local database is waiting</div>
	                   <div id="provider_catalog_new" class="catalog-new-hotels" hidden></div>
	                   <div id="hotel_catalog_upcoming" class="catalog-status-upcoming" hidden></div>
	                   <div id="hotel_catalog_new" class="catalog-new-hotels" hidden></div>
	                 </div>
	                 <div class="catalog-status-actions">
	                   <button id="btn_catalog_refresh" type="button">刷新酒店数据 Refresh</button>
	                   <button id="btn_catalog_ack" type="button" hidden>知道了 Dismiss</button>
	                 </div>
	               </div>
	             </section>

	             <details class="box" id="search_history_panel">
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
	          </section>

	          <section class="app-view" id="view-monitor" data-view="monitor" aria-label="Vacancy Monitor" hidden>
	            <section class="run-panel">
              <div class="run-top">
                <div>
                  <div class="run-title">启动与监控 Run Control</div>
                  <div class="run-subtitle">启动后按当前搜索范围循环检索；运行中可以停止、保存配置或更新酒店库。</div>
                </div>
              </div>

              <div class="run-snapshot" id="run-snapshot" aria-label="Active search configuration">
                <div><span id="snapshot-dates-label">日期 Dates</span><b id="snapshot-dates">-</b></div>
                <div><span id="snapshot-hotels-label">酒店 Hotels</span><b id="snapshot-hotels">0</b></div>
                <div><span id="snapshot-engine-label">引擎 Engine</span><b id="snapshot-engine">HTTP/API</b></div>
                <div><span id="snapshot-cadence-label">每轮间隔 Round</span><b id="snapshot-cadence">30s</b></div>
                <div><span id="snapshot-safety-label">流量保护 Safety</span><b id="snapshot-safety">正常 Normal</b></div>
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
              <div id="provider-health" class="provider-health" aria-live="polite" hidden></div>
              <details id="runtime-diagnostics" class="runtime-diagnostics">
                <summary><span id="diagnostics-title">运行诊断 Run Diagnostics</span><small id="diagnostics-summary">自适应调度 Adaptive scheduling</small></summary>
                <div class="diagnostics-grid">
                  <div><span id="diagnostics-throughput-label">吞吐量 Throughput</span><b id="diagnostics-throughput">0/min</b></div>
                  <div><span id="diagnostics-eta-label">预计剩余 ETA</span><b id="diagnostics-eta">-</b></div>
                  <div><span id="diagnostics-queue-label">队列 Queue</span><b id="diagnostics-queue">0 + 0</b></div>
                  <div><span id="diagnostics-latency-label">最慢 P95 Slowest P95</span><b id="diagnostics-latency">-</b></div>
                  <div><span id="diagnostics-priority-label">优先酒店 Priority</span><b id="diagnostics-priority">0</b></div>
                  <div><span id="diagnostics-protection-label">保护事件 Protection</span><b id="diagnostics-protection">0</b></div>
                  <div><span id="diagnostics-cache-label">缓存命中 Cache Hit</span><b id="diagnostics-cache">0% · 0</b></div>
                  <div><span id="diagnostics-saved-label">节省请求 Saved</span><b id="diagnostics-saved">0</b></div>
                </div>
                <div class="diagnostics-actions"><button id="btn_cache_clear" class="btn small secondary" type="button">清除检索缓存 Clear Cache</button></div>
              </details>
              <div id='msg' class='notice success' role='status' aria-live='polite'></div>
              <div id='err' class='notice error' role='alert'></div>
	            </section>

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

            <div class="results-toolbar" aria-label="Result filters">
              <div class="result-filter-tabs" id="result_filter_tabs">
                <button data-result-filter="all" class="active" aria-pressed="true">全部 All</button>
                <button data-result-filter="available" aria-pressed="false">有房 Available</button>
                <button data-result-filter="unavailable" aria-pressed="false">无房 Unavailable</button>
                <button data-result-filter="check" aria-pressed="false">需确认 Check</button>
                <button data-result-filter="changes" aria-pressed="false">变化 Changes</button>
              </div>
              <div class="result-query-wrap">
                <label class="sr-only" for="result_query">搜索结果 Search results</label>
                <input id="result_query" type="search" placeholder="搜索编号、酒店或房型 Search code, hotel, or room">
              </div>
              <div class="results-sort-wrap">
                <span id="results_filter_count">显示 0 / 0 Showing</span>
                <span id="results_updated_at">尚未更新 Never updated</span>
                <label for="results_sort">排序 Sort</label>
                <select id="results_sort">
                  <option value="default">默认 Default</option>
                  <option value="status">状态 Status</option>
                  <option value="price">价格 Price</option>
                  <option value="name">酒店名 Hotel</option>
                  <option value="distance">距离 Distance</option>
                </select>
                <button id="btn_results_refresh">刷新 Refresh</button>
                <button id="btn_results_export">导出 CSV Export</button>
              </div>
            </div>
            <div id="result-change-note" class="result-change-note" role="status" aria-live="polite" hidden></div>

            <div class="results-table-wrap">
              <table class="result-table">
                <thead>
                  <tr>
                    <th style="width:110px">编号 Code</th>
                    <th>酒店 Hotel</th>
                    <th style="width:190px">状态 Status</th>
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

            <details class="result-log-panel trend-panel" id="trend-panel">
              <summary id="trend-panel-title">价格与空房趋势 Price &amp; Availability Trends</summary>
              <div class="trend-toolbar">
                <div class="trend-toolbar-summary">
                  <strong id="trend-summary">等待历史数据 Waiting for history</strong>
                  <small id="trend-scope-note">仅显示当前住宿条件的历史记录 Current stay conditions only</small>
                </div>
                <label class="trend-filter"><span id="trend-hotel-label">酒店 Hotel</span><select id="trend_hotel" aria-label="Hotel"></select></label>
                <label class="trend-filter trend-range-filter"><span id="trend-range-label">时间范围 Range</span><select id="trend_days" aria-label="Trend range">
                  <option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option>
                </select></label>
                <button type="button" id="btn_trend_refresh">刷新 Refresh</button>
              </div>
              <div class="trend-overview" id="trend-overview"></div>
              <div class="trend-chart" id="trend-chart" aria-live="polite"></div>
              <div class="trend-observations" id="trend-observations"></div>
            </details>

            <details class="result-log-panel event-center-panel" id="event-center-panel">
              <summary id="event-center-title">统一事件中心 Event Center</summary>
              <div class="event-center-list" id="event-center-list"><div class="trend-empty">No events</div></div>
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
	          </section>

	          <section class="app-view" id="view-search-settings" data-view="search-settings" aria-label="Search Settings" hidden>
	            <details class="box settings-panel" open>
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
                  <label class="inline"><input id='adaptive_backoff_enabled' type='checkbox' {'checked' if getattr(cfg, "adaptive_backoff_enabled", DEFAULT_ADAPTIVE_BACKOFF_ENABLED) else ''}> 启用自适应退避 Adaptive Backoff</label>
                  <div class='help adaptive-backoff-help'>访问异常达到 50% 时自动把下一轮间隔提高到 2 倍，连续异常最多 4 倍；恢复正常后自动回落。</div>
                </div>

              </div>
	            </details>
	          </section>

	          <section class="app-view" id="view-push-settings" data-view="push-settings" aria-label="Push Settings" hidden>
	            <details class="box settings-panel" open>
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
                  <h3 class="info-title" tabindex="0" data-tip="在本机弹出系统通知。步骤：1. 勾选启用本地通知。2. 点击“发送测试通知”。3. macOS 检查通知权限；Windows 需要 PowerShell；Linux 需要 notify-send 和图形桌面会话。4. 测试成功后启动搜索。">本地通知 Local</h3>
                  <label class="inline"><input id='enable_local' type='checkbox' {'checked' if cfg.enable_local else ''}> 启用本地通知 Enable Local</label>
                  <div class="area-toolbar">
                    <button id="btn_local_test">发送测试通知 Test Notification</button>
                  </div>
                  <div class='help'>macOS 使用 terminal-notifier/osascript；Windows 使用 PowerShell；Linux 需要 notify-send。</div>
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
	          </section>

	          <section class="app-view" id="view-interface" data-view="interface" aria-label="Interface Settings" hidden>
	            <div class="interface-settings-grid">
	              <section class="interface-card">
	                <span class="interface-card-icon">🌐</span>
	                <div><h2>语言</h2><p>界面仅显示当前选择的语言。</p></div>
	                <label class="sr-only" for="primary_language">语言 Language</label>
	                <select id="primary_language">{language_options_html}</select>
	              </section>
	              <section class="interface-card">
	                <span class="interface-card-icon">◐</span>
	                <div><h2>主题 / Theme</h2><p>可跟随系统，也可固定浅色或深色主题。</p></div>
	                <div class="theme-options" role="radiogroup" aria-label="Theme">
	                  <button type="button" data-theme-choice="system" aria-pressed="true">跟随系统 / System</button>
	                  <button type="button" data-theme-choice="light" aria-pressed="false">浅色 / Light</button>
	                  <button type="button" data-theme-choice="dark" aria-pressed="false">深色 / Dark</button>
	                </div>
	              </section>
	              <section class="interface-card pwa-install-card">
	                <span class="interface-card-icon">▣</span>
	                <div><h2 id="pwa-title">手机桌面版</h2><p id="pwa-help">安装到主屏幕，保留最近结果并自动重连。</p></div>
	                <div class="interface-card-actions">
	                  <button type="button" class="primary" id="btn_pwa_install">安装到桌面</button>
	                  <span id="pwa-state">正在检查安装状态</span>
	                </div>
	              </section>
	              <section class="interface-card provider-capability-card">
	                <span class="interface-card-icon">▦</span>
	                <div><h2 id="provider-matrix-title">品牌能力矩阵</h2><p id="provider-matrix-help">不同官网提供的数据能力可能不同。</p></div>
	                <div class="provider-capability-table" id="provider-capability-table">Loading...</div>
	              </section>
	              <section class="interface-card simulation-card">
	                <span class="interface-card-icon">◫</span>
	                <div><h2 id="simulation-title">响应模拟与压力测试</h2><p id="simulation-help">使用本地模拟官网响应，不访问真实酒店网站。</p></div>
	                <div class="simulation-controls">
	                  <label>Iterations <input id="simulation_iterations" type="number" min="1" max="5000" value="500"></label>
	                  <label>Concurrency <input id="simulation_concurrency" type="number" min="1" max="32" value="4"></label>
	                  <button type="button" id="btn_simulation_run">运行测试 Run</button>
	                </div>
	                <pre id="simulation-output">-</pre>
	              </section>
	              <section class="interface-card mobile-access-card" id="mobile-access-card">
	                <span class="interface-card-icon mobile-access-icon" aria-hidden="true">▯</span>
	                <div class="mobile-access-heading"><h2 id="mobile-access-title">手机访问</h2><p id="mobile-access-help">在局域网或 Tailscale 中安全连接手机。</p></div>
	                <div class="mobile-access-controls" id="mobile-access-host-controls">
	                  <label class="inline mobile-access-toggle"><input id="mobile_access_enabled" type="checkbox"> <span id="mobile-access-enable-label">启用手机访问</span></label>
	                  <button class="primary" id="btn_mobile_access_apply" type="button">应用</button>
	                </div>
	                <div class="mobile-access-state" id="mobile-access-state" data-state="loading" aria-live="polite">
	                  <span class="mobile-access-state-dot" aria-hidden="true"></span>
	                  <div><strong id="mobile-access-state-title">正在读取状态</strong><span id="mobile-access-state-message"></span></div>
	                </div>
	                <div class="mobile-access-details" id="mobile-access-details" hidden>
	                  <div class="mobile-access-setup">
	                    <div class="mobile-access-method">
	                      <div class="mobile-access-section-label" id="mobile-access-method-title">1. 选择连接方式</div>
	                      <div class="mobile-access-methods" role="radiogroup" aria-labelledby="mobile-access-method-title">
	                        <button type="button" class="mobile-access-method-button active" data-mobile-connection="lan" aria-pressed="true">
	                          <span class="mobile-access-method-icon" aria-hidden="true">⌂</span>
	                          <span><strong id="mobile-lan-title">同一 Wi-Fi</strong><small id="mobile-lan-help">适合在家中或酒店内使用</small></span>
	                          <em id="mobile-lan-status">检测中</em>
	                        </button>
	                        <button type="button" class="mobile-access-method-button" data-mobile-connection="tailscale" aria-pressed="false">
	                          <span class="mobile-access-method-icon" aria-hidden="true">↗</span>
	                          <span><strong id="mobile-tailscale-title">Tailscale 远程</strong><small id="mobile-tailscale-help">离开当前 Wi-Fi 后也可安全连接</small></span>
	                          <em id="mobile-tailscale-status">检测中</em>
	                        </button>
	                        <button type="button" class="mobile-access-method-button" data-mobile-connection="public" aria-pressed="false">
	                          <span class="mobile-access-method-icon" aria-hidden="true">◎</span>
	                          <span><strong id="mobile-public-title">公网直连</strong><small id="mobile-public-help">仅建议配合 HTTPS 使用</small></span>
	                          <em id="mobile-public-status">检测中</em>
	                        </button>
	                      </div>
	                    </div>
	                    <div class="mobile-access-connect">
	                      <div class="mobile-access-field"><label id="mobile-access-url-label" for="mobile_access_url">2. 在手机打开此地址</label><div><input id="mobile_access_url" type="text" readonly><button id="btn_mobile_access_copy" type="button">复制</button><a class="mobile-access-open" id="btn_mobile_access_open" href="#" target="_blank" rel="noreferrer" aria-label="打开地址" title="打开地址">↗</a></div></div>
	                      <div class="mobile-access-field"><label id="mobile-access-code-label" for="mobile_access_code">3. 输入配对码</label><div><input id="mobile_access_code" class="pairing-code" type="text" readonly><button id="btn_mobile_access_rotate" type="button">更换</button></div></div>
	                    </div>
	                    <div class="mobile-access-steps" id="mobile-access-steps" aria-label="Connection steps">
	                      <span><b>1</b><i id="mobile-step-network">连接网络</i></span>
	                      <span><b>2</b><i id="mobile-step-scan">扫码或打开地址</i></span>
	                      <span><b>3</b><i id="mobile-step-pair">完成配对</i></span>
	                    </div>
	                    <p class="mobile-access-note" id="mobile-access-note">首次连接需要输入配对码，之后会保留登录状态。</p>
	                  </div>
	                  <figure class="mobile-access-qr" id="mobile-access-qr-wrap"><div class="mobile-access-qr-label" id="mobile-access-qr-mode">同一 Wi-Fi</div><img id="mobile_access_qr" alt=""><figcaption id="mobile-access-qr-label">使用手机相机扫码连接</figcaption></figure>
	                </div>
	              </section>
	            </div>
	          </section>

	          <div class="update-modal" id="update-modal" hidden>
	            <section class="update-dialog" role="dialog" aria-modal="true" aria-labelledby="update-dialog-title">
	              <header class="update-dialog-header">
	                <div class="update-product">
	                  <img src="/static/toyoko-chan-mascot.png?v=3" alt="">
	                  <div><span id="update-dialog-kicker">SOFTWARE UPDATE</span><h2 id="update-dialog-title">软件更新</h2></div>
	                </div>
	                <button class="update-close" id="update-close-button" type="button" aria-label="关闭" title="关闭">×</button>
	              </header>
	              <div class="update-dialog-body">
	                <div class="update-app-name" id="update-app-name">东横酱</div>
	                <div class="update-version-grid" aria-label="Version information">
	                  <div><span id="update-current-label">当前版本</span><strong id="update-current-version">{APP_VERSION}</strong></div>
	                  <div><span id="update-latest-label">最新版本</span><strong id="update-latest-version">-</strong></div>
	                </div>
	                <div class="update-state-row" id="update-state-row" data-state="idle" aria-live="polite">
	                  <span class="update-state-dot" aria-hidden="true"></span>
	                  <div><strong id="update-state-title">正在检查更新</strong><span id="update-state-message"></span></div>
	                </div>
	                <div class="update-project-info">
	                  <div><span id="update-author-label">作者</span><a href="https://space.bilibili.com/4955287" target="_blank" rel="noreferrer noopener"><b>{APP_AUTHOR}</b><span aria-hidden="true">↗</span></a></div>
	                  <div><span id="update-github-label">GitHub</span><a href="https://github.com/JellyNekoNeko/toyoko-tracker" target="_blank" rel="noreferrer noopener"><b>JellyNekoNeko/toyoko-tracker</b><span aria-hidden="true">↗</span></a></div>
	                </div>
	              </div>
	              <footer class="update-actions">
	                <button type="button" id="btn_update_check">重新检查</button>
	                <button class="primary" type="button" id="btn_upgrade" disabled>更新</button>
	              </footer>
	            </section>
	          </div>

	          <div class="guide-modal" id="guide-modal" hidden>
	            <section class="guide-dialog" role="dialog" aria-modal="true" aria-labelledby="guide-title">
	              <header class="guide-header">
	                <div class="guide-brand">
	                  <img src="/static/toyoko-chan-mascot.png?v=3" alt="">
	                  <div><span id="guide-kicker">QUICK START</span><h2 id="guide-title">东横酱使用向导 / Toyoko Chan Guide</h2></div>
	                </div>
	                <button class="guide-close" id="guide-close-button" type="button" aria-label="Close guide" title="Close guide">×</button>
	              </header>
	              <nav class="guide-progress" id="guide-progress" aria-label="Guide progress">
	                <button type="button" data-guide-jump="0" aria-current="step"><span>1</span></button>
	                <button type="button" data-guide-jump="1"><span>2</span></button>
	                <button type="button" data-guide-jump="2"><span>3</span></button>
	                <button type="button" data-guide-jump="3"><span>4</span></button>
	                <button type="button" data-guide-jump="4"><span>5</span></button>
	              </nav>
	              <div class="guide-stage">
	                <div class="guide-visual" aria-hidden="true">
	                  <div class="guide-figure guide-figure-layout active" data-guide-visual="0">
	                    <div class="guide-mini-sidebar"><i></i><b></b><b></b><b></b><b></b></div>
	                    <div class="guide-mini-workspace"><div class="guide-mini-dock"><i></i><span></span><em></em></div><div class="guide-mini-content"><b></b><span></span><span></span><span></span></div></div>
	                  </div>
	                  <div class="guide-figure guide-figure-search" data-guide-visual="1" hidden>
	                    <div class="guide-mini-fields"><span></span><span></span><span></span><span></span></div>
	                    <div class="guide-mini-brands"><b></b><b></b><b></b></div>
	                    <div class="guide-mini-picker"><i>⌖</i><span></span><span></span><span></span></div>
	                  </div>
	                  <div class="guide-figure guide-figure-results" data-guide-visual="2" hidden>
	                    <div class="guide-mini-stats"><b class="good">2</b><b class="bad">1</b><b>3</b></div>
	                    <div class="guide-mini-table"><span></span><p><i class="good"></i><b></b><em></em></p><p><i class="bad"></i><b></b><em></em></p><p><i class="good"></i><b></b><em></em></p></div>
	                  </div>
	                  <div class="guide-figure guide-figure-search-settings" data-guide-visual="3" hidden>
	                    <div><i>HTTP</i><span></span></div><div><i>1×</i><span></span></div><div><i>120s</i><span></span><span></span></div>
	                  </div>
	                  <div class="guide-figure guide-figure-push" data-guide-visual="4" hidden>
	                    <div class="guide-mini-events"><span class="on"></span><span class="on"></span><span></span><span class="on"></span></div>
	                    <div class="guide-mini-channels"><b>◉</b><b>✉</b><b>●</b><b>⌁</b></div>
	                    <i class="guide-mini-notification">✓</i>
	                  </div>
	                </div>
	                <div class="guide-copy">
	                  <span class="guide-step-count" id="guide-step-count">1 / 5</span>
	                  <h3 id="guide-step-title">认识界面 / Interface Overview</h3>
	                  <p id="guide-step-body">使用左侧导航切换工作区；顶部操作条始终提供单次检索、启动和停止。 / Use the sidebar to switch workspaces; the top command bar keeps scan, start, and stop within reach.</p>
	                  <div class="guide-tip" id="guide-step-tip">提示：运行后会自动进入空房监控。 / Tip: Starting a scan automatically opens Vacancy Monitor.</div>
	                </div>
	              </div>
	              <footer class="guide-actions">
	                <button type="button" id="guide-skip-button">稍后 / Skip</button>
	                <div><button type="button" id="guide-prev-button">上一步 / Back</button><button class="primary" type="button" id="guide-next-button">下一步 / Next</button></div>
	              </footer>
	            </section>
	          </div>

          <aside id="hotel-info-popover" class="hotel-info-popover" role="dialog" aria-live="polite" hidden></aside>
	            </main>
	          </div>
        """

    page_html += f"""
          <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
          <script src="/static/app.js?v={APP_VERSION}-traffic-1"></script>
        </body></html>
        """
    response = Response(page_html, mimetype="text/html")
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

 # ---- Hotel name → code mapping (toyoko_hotel_names.json) ----
HOTEL_NAME_JSON = os.path.join(BASE_DIR, "toyoko_hotel_names.json")
AREA_INDEX_JSON = os.path.join(BASE_DIR, "toyoko_area_index.json")
_HOTEL_NAME_CACHE = None  # type: Optional[dict]
_HOTEL_NAME_CACHE_MTIME = 0.0
_AREA_INDEX_CACHE = None  # type: Optional[dict]
_AREA_INDEX_CACHE_MTIME = 0.0
_AREA_HOTELS_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_RADIUS_BUILD_LOCK = threading.Lock()


def _invalidate_hotel_catalog_caches() -> None:
    _AREA_HOTELS_CACHE.clear()


_set_catalog_hooks(log_hook=_log, refresh_hook=_invalidate_hotel_catalog_caches)


def _start_catalog_scheduler() -> None:
    _catalog_start_scheduler()


def _stop_catalog_scheduler() -> None:
    _catalog_stop_scheduler()


_PROVIDER_DATABASE_LOCK = threading.Lock()
_PROVIDER_DATABASE_STOP = threading.Event()
_PROVIDER_DATABASE_THREAD: Optional[threading.Thread] = None
_PROVIDER_DATABASE_INTERVAL = 6 * 60 * 60


def _detail_area_references() -> Dict[int, List[Tuple[int, float, float]]]:
    jobs: List[Tuple[int, int]] = []
    for region in _load_area_index().get("regions") or []:
        for prefecture in region.get("prefectures") or []:
            try:
                prefecture_id = int(prefecture.get("id"))
            except (TypeError, ValueError):
                continue
            for area in prefecture.get("areas") or []:
                area_name = str(area.get("name") or "").lower()
                if "within tokyo's 23 wards" in area_name:
                    continue
                try:
                    jobs.append((prefecture_id, int(area.get("id"))))
                except (TypeError, ValueError):
                    continue

    references: Dict[int, List[Tuple[int, float, float]]] = {}

    def fetch(job: Tuple[int, int]) -> Tuple[int, int, List[Dict[str, Any]]]:
        prefecture_id, area_id = job
        return prefecture_id, area_id, _fetch_hotels_for_selector("area", area_id)

    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="area-classifier") as executor:
        futures = {executor.submit(fetch, job): job for job in jobs}
        for future in as_completed(futures):
            prefecture_id, area_id = futures[future]
            try:
                _, _, hotels = future.result()
            except Exception as exc:
                _log(f"[database] area reference {area_id} skipped: {exc}")
                continue
            for hotel in hotels:
                lat = _optional_float(hotel.get("lat"))
                lng = _optional_float(hotel.get("lng"))
                if lat is not None and lng is not None:
                    references.setdefault(prefecture_id, []).append((area_id, lat, lng))
    return references


def _classify_provider_hotels(
    hotels: List[Dict[str, Any]],
    references: Dict[int, List[Tuple[int, float, float]]],
) -> List[Dict[str, Any]]:
    classified = []
    for source in hotels:
        hotel = dict(source)
        prefecture_id = hotel.get("prefecture_id")
        if not prefecture_id:
            prefecture_id = _prefecture_id_from_text(
                str(hotel.get("prefecture") or hotel.get("address") or hotel.get("address_en") or "")
            )
        try:
            prefecture_id = int(prefecture_id) if prefecture_id else None
        except (TypeError, ValueError):
            prefecture_id = None
        hotel["prefecture_id"] = prefecture_id
        hotel["region_id"] = hotel.get("region_id") or _region_id_for_prefecture_id(prefecture_id)
        lat = _optional_float(hotel.get("lat"))
        lng = _optional_float(hotel.get("lng"))
        candidates = references.get(prefecture_id or -1, [])
        if lat is not None and lng is not None and candidates:
            nearest = min(candidates, key=lambda row: _haversine_km(lat, lng, row[1], row[2]))
            hotel["detail_area_id"] = nearest[0]
            hotel["detail_area_distance_km"] = round(_haversine_km(lat, lng, nearest[1], nearest[2]), 3)
        else:
            hotel["detail_area_id"] = None
        classified.append(hotel)
    return classified


def _refresh_provider_database(force: bool = False) -> Dict[str, Any]:
    if not _PROVIDER_DATABASE_LOCK.acquire(blocking=False):
        return {"ok": True, "state": "checking", "providers": {}}
    try:
        _log("[database] refreshing non-Toyoko hotel database...")
        references = _detail_area_references()
        fetchers = {
            "routeinn": lambda: _fetch_routeinn_coordinate_hotels(DEFAULT_PRIMARY_LANGUAGE, force=force),
            "dormy": lambda: _fetch_chain_provider_hotels("dormy", DEFAULT_PRIMARY_LANGUAGE, force=force),
            "mystays": lambda: _fetch_chain_provider_hotels("mystays", DEFAULT_PRIMARY_LANGUAGE, force=force),
            "daiwa": lambda: _fetch_chain_provider_hotels("daiwa", DEFAULT_PRIMARY_LANGUAGE, force=force),
        }
        results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=len(fetchers), thread_name_prefix="provider-catalog") as executor:
            futures = {executor.submit(fetcher): provider for provider, fetcher in fetchers.items()}
            for future in as_completed(futures):
                provider = futures[future]
                try:
                    hotels = _classify_provider_hotels(future.result(), references)
                    results[provider] = _db_sync_provider(provider, hotels)
                    _log(f"[database] {provider}: {len(hotels)} hotels synchronized")
                except Exception as exc:
                    _db_record_sync_error(provider, str(exc))
                    results[provider] = {"error": str(exc)}
                    _log(f"[database] {provider} refresh failed: {exc}")
        return {"ok": True, "state": "complete", "providers": results}
    finally:
        _PROVIDER_DATABASE_LOCK.release()


def _request_provider_database_refresh(force: bool = True) -> bool:
    if _PROVIDER_DATABASE_LOCK.locked():
        return False
    threading.Thread(
        target=_refresh_provider_database,
        kwargs={"force": force},
        name="provider-database-refresh",
        daemon=True,
    ).start()
    return True


def _provider_database_worker() -> None:
    _refresh_provider_database(force=False)
    while not _PROVIDER_DATABASE_STOP.wait(_PROVIDER_DATABASE_INTERVAL):
        _refresh_provider_database(force=True)


def _start_provider_database_scheduler() -> None:
    global _PROVIDER_DATABASE_THREAD
    if _PROVIDER_DATABASE_THREAD and _PROVIDER_DATABASE_THREAD.is_alive():
        return
    _PROVIDER_DATABASE_STOP.clear()
    _PROVIDER_DATABASE_THREAD = threading.Thread(
        target=_provider_database_worker,
        name="provider-database-scheduler",
        daemon=True,
    )
    _PROVIDER_DATABASE_THREAD.start()


def _stop_provider_database_scheduler() -> None:
    _PROVIDER_DATABASE_STOP.set()

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
        display = primary or en or fallback or ""
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
    item["provider"] = "toyoko"
    item["display_code"] = item.get("display_code") or item.get("code")
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


def _prefecture_id_for_detail(region_id: Optional[int], detail_id: str) -> Optional[int]:
    detail = str(detail_id or "")
    if detail.startswith("pref-"):
        try:
            return int(detail.split("-", 1)[1])
        except ValueError:
            return None
    if not detail.startswith("area-"):
        return None
    try:
        area_id = int(detail.split("-", 1)[1])
    except ValueError:
        return None
    index = _load_area_index()
    for region in index.get("regions") or []:
        if region_id is not None and int(region.get("id", -1)) != int(region_id):
            continue
        for prefecture in region.get("prefectures") or []:
            if any(int(area.get("id", -1)) == area_id for area in prefecture.get("areas") or []):
                return int(prefecture.get("id"))
    return None


def _prefecture_ids_for_region(region_id: int) -> List[int]:
    index = _load_area_index()
    for region in index.get("regions") or []:
        if int(region.get("id", -1)) != int(region_id):
            continue
        ids: List[int] = []
        for prefecture in region.get("prefectures") or []:
            try:
                ids.append(int(prefecture.get("id")))
            except (TypeError, ValueError):
                continue
        return ids
    return []


def _all_toyoko_hotels_for_radius(primary_language: Optional[str] = None) -> List[Dict[str, Any]]:
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


def _all_hotels_for_radius(
    primary_language: Optional[str] = None,
    enabled_providers: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    providers = [provider for provider in (enabled_providers or DEFAULT_ENABLED_PROVIDERS) if provider in SUPPORTED_PROVIDERS]
    hotels: List[Dict[str, Any]] = []
    if "toyoko" in providers:
        hotels.extend(_all_toyoko_hotels_for_radius(primary_language))
    for provider in ("routeinn", "dormy", "mystays", "daiwa"):
        if provider in providers:
            cached = _db_load_hotels(provider, primary_language or DEFAULT_PRIMARY_LANGUAGE)
            if cached:
                hotels.extend(cached)
            elif provider == "routeinn":
                hotels.extend(_fetch_routeinn_coordinate_hotels(primary_language or DEFAULT_PRIMARY_LANGUAGE))
            else:
                hotels.extend(_fetch_chain_provider_hotels(provider, primary_language or DEFAULT_PRIMARY_LANGUAGE))
    return hotels


def _load_radius_hotels_cache() -> Optional[List[Dict[str, Any]]]:
    try:
        hotels = _load_catalog_coordinate_cache(allow_stale=True)
        if hotels:
            _log(f"[radius] loaded coordinate cache: {len(hotels)} hotels")
            return hotels
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


def _hotels_within_radius(
    query: str,
    radius_km: int,
    primary_language: Optional[str] = None,
    enabled_providers: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    lat, lng, source = _geocode_location(query)
    radius = max(1, min(50, int(radius_km or DEFAULT_RADIUS_KM)))
    hotels = []
    radius_hotels = (
        _all_hotels_for_radius(primary_language)
        if enabled_providers is None
        else _all_hotels_for_radius(primary_language, enabled_providers)
    )
    for h in radius_hotels:
        hlat = _optional_float(h.get("lat"))
        hlng = _optional_float(h.get("lng"))
        if hlat is None or hlng is None:
            continue
        distance = _haversine_km(lat, lng, hlat, hlng)
        if distance <= radius:
            item = dict(h)
            item["distance_km"] = round(distance, 2)
            hotels.append(item)
    hotels.sort(key=lambda x: (
        float(x["distance_km"]) if x.get("distance_km") is not None else 9999.0,
        str(x.get("code") or ""),
    ))
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
    providers = payload.get("enabled_providers", getattr(cfg, "enabled_providers", DEFAULT_ENABLED_PROVIDERS))
    if isinstance(providers, list):
        cfg.enabled_providers = [provider for provider in providers if provider in SUPPORTED_PROVIDERS]
    if not cfg.enabled_providers:
        raise ValueError("Please enable at least one hotel brand / 请至少启用一个酒店品牌")
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
    if "adaptive_backoff_enabled" in payload:
        cfg.adaptive_backoff_enabled = bool(payload["adaptive_backoff_enabled"])
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


_PREFERENCE_KEYS = {
    "primary_language",
    "enable_telegram", "bot_token", "chat_id",
    "enable_bark", "bark_key", "bark_server",
    "bark_critical_enabled", "bark_critical_volume", "bark_critical_sound",
    "enable_serverchan", "serverchan_sendkey",
    "enable_local", "enable_email", "smtp_host", "smtp_port", "smtp_tls",
    "smtp_user", "smtp_pass", "email_from", "email_to",
    "notify_available", "notify_unavailable", "notify_availability_count_change",
    "notify_start", "notify_stop", "notify_search_error",
    "available_alert_repeat", "available_alert_repeat_interval_sec",
    "loop_interval_seconds", "per_hotel_delay_seconds", "request_jitter_percent",
    "smart_parallel_enabled", "smart_parallel_workers", "adaptive_backoff_enabled",
    "engine",
}


def save_preferences() -> Response:
    payload = request.get_json(force=True, silent=True) or {}
    patch = {key: value for key, value in payload.items() if key in _PREFERENCE_KEYS}
    if not patch:
        return jsonify({"ok": False, "message": "no supported preference fields"}), 400
    with _CONFIG_LOCK:
        candidate = deepcopy(_CONFIG)
    try:
        _apply_payload_to_config(candidate, patch)
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    with _CONFIG_LOCK:
        for key in patch:
            if hasattr(candidate, key):
                setattr(_CONFIG, key, getattr(candidate, key))
    if not _save_config_to_file(AUTO_SAVE_PATH):
        return jsonify({"ok": False, "message": "preference save failed"}), 500
    return jsonify({"ok": True, "saved": sorted(patch)})


def start() -> Response:
        global _worker_thread, _RUN_REQUESTED, _LAST_RESULTS, _RESULTS_REVISION
        payload = request.get_json(force=True, silent=True) or {}
        run_once = bool(payload.get("run_once", False))
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

        with _CONFIG_LOCK:
            cfg_snapshot = deepcopy(_CONFIG)
        restored_checkpoint = bool(not run_once and _restore_runtime_checkpoint(cfg_snapshot))
        if not restored_checkpoint:
            with _RESULTS_LOCK:
                _LAST_RESULTS = []
                _RESULTS_REVISION += 1
            clear_alert_state()
        if not restored_checkpoint:
            with _PROGRESS_LOCK:
                _PROGRESS["backoff_multiplier"] = 1
                _PROGRESS["unknown_ratio_percent"] = 0
                _PROGRESS["consecutive_unhealthy_rounds"] = 0
                _PROGRESS["effective_interval_sec"] = int(_CONFIG.loop_interval_seconds)

        _worker_thread = threading.Thread(
            target=_worker_loop,
            args=(run_once,),
            name="checker-thread",
            daemon=True,
        )
        _worker_thread.start()
        _log("Started worker.")
        _log(f"{APP_NAME} {APP_VERSION} · Author: {APP_AUTHOR}")

        try:
            with _CONFIG_LOCK:
                cfg_snapshot = deepcopy(_CONFIG)
            send_start_notifications(cfg_snapshot)
        except Exception as e:
            _log(f"[start] could not send start notifications: {e}")

        message = "scan_once_started" if run_once else ("restarted" if restarted else "started")
        return jsonify({
            "ok": True,
            "message": message,
            "restarted": restarted,
            "run_once": run_once,
            "config": _public_config_dict(_CONFIG),
        })

def stop() -> Response:
        global _worker_thread, _RUN_REQUESTED
        _RUN_REQUESTED = False  # prevent worker from continuing or restarting
        _stop_event.set()
        if _worker_thread and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        _worker_thread = None
        _persist_runtime_checkpoint()
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
            _PROGRESS["backoff_multiplier"] = 1
            _PROGRESS["unknown_ratio_percent"] = 0
            _PROGRESS["consecutive_unhealthy_rounds"] = 0
            _PROGRESS["effective_interval_sec"] = 0
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

def _fmt_elapsed_seconds(seconds: int) -> str:
    days, remaining = divmod(int(seconds), 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, seconds = divmod(remaining, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _runtime_diagnostics_snapshot(
    progress: Dict[str, Any],
    provider_health: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    elapsed = max(0, int(progress.get("round_elapsed_sec") or 0))
    done = max(0, int(progress.get("done") or 0))
    total = max(done, int(progress.get("total") or 0))
    throughput = round(done * 60 / elapsed, 1) if elapsed and done else 0.0
    remaining = max(0, total - done)
    eta = int(math.ceil(remaining * 60 / throughput)) if throughput > 0 and remaining else 0
    slowest_provider = ""
    slowest_p95 = 0
    for provider, state in provider_health.items():
        p95 = int(state.get("p95_elapsed_ms") or 0)
        if p95 > slowest_p95:
            slowest_provider = provider
            slowest_p95 = p95
    with _CONFIG_LOCK:
        current_cfg = deepcopy(_CONFIG)
    manual_priority = sum(
        1 for code in current_cfg.hotel_codes if _hotel_is_manual_priority(current_cfg, code)
    )
    adaptive_priority = sum(
        1
        for code in current_cfg.hotel_codes
        if not _hotel_is_manual_priority(current_cfg, code) and _hotel_is_adaptive_priority(code)
    )
    try:
        cache_status = _scan_cache_status_snapshot()
    except Exception:
        cache_status = {}
    try:
        event_status = _event_status_snapshot()
        analytics_status = _analytics_status_snapshot()
    except Exception:
        event_status = {}
        analytics_status = {}
    return {
        "throughput_per_min": throughput,
        "estimated_remaining_sec": eta,
        "queue_pending": max(0, int(progress.get("queue_pending", remaining))),
        "in_flight": max(0, int(progress.get("in_flight") or 0)),
        "priority_pending": max(0, int(progress.get("priority_pending") or 0)),
        "manual_priority_hotels": manual_priority,
        "adaptive_priority_hotels": adaptive_priority,
        "access_failures": sum(int(state.get("access_failures") or 0) for state in provider_health.values()),
        "rate_limited_count": sum(int(state.get("rate_limited_count") or 0) for state in provider_health.values()),
        "cooldown_providers": sum(1 for state in provider_health.values() if state.get("state") == "cooldown"),
        "slowest_provider": slowest_provider,
        "slowest_p95_ms": slowest_p95,
        "cache_entries": int(cache_status.get("entries") or 0),
        "cache_fresh_entries": int(cache_status.get("fresh_entries") or 0),
        "cache_hit_rate_percent": int(cache_status.get("hit_rate_percent") or 0),
        "cache_saved_requests": int(cache_status.get("saved_requests") or 0),
        "cache_live_requests": int(cache_status.get("live_requests") or 0),
        "cache_coalesced_requests": int(cache_status.get("coalesced_requests") or 0),
        "cache_conditional_hits": int(cache_status.get("conditional_hits") or 0),
        "cache_fallback_hits": int(cache_status.get("fallback_hits") or 0),
        "events_last_24h": int(event_status.get("last_24h") or 0),
        "pending_deliveries": int(event_status.get("pending_deliveries") or 0),
        "trend_observations": int(analytics_status.get("observations") or 0),
    }


def _runtime_status_snapshot() -> Dict[str, Any]:
    with _PROGRESS_LOCK:
        progress = dict(_PROGRESS)
    now_ts = _now_wall()
    now_mono = _now_mono()
    running = bool(_RUN_REQUESTED and _worker_thread and _worker_thread.is_alive())
    round_started_mono = float(progress.get("round_started_mono") or 0.0)

    progress["uptime_sec"] = int(now_mono - _UPTIME_STARTED_MONO) if running and _UPTIME_STARTED_MONO else 0
    progress["round_elapsed_sec"] = int(now_mono - round_started_mono) if running and round_started_mono else 0
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
    progress["uptime_human"] = _fmt_elapsed_seconds(progress["uptime_sec"])
    progress["round_elapsed_human"] = _fmt_elapsed_seconds(progress["round_elapsed_sec"])

    with _ACTION_LOCK:
        action = _CURRENT_ACTION
        action_ts = _ACTION_TS
    with _RESULTS_LOCK:
        results_revision = _RESULTS_REVISION
    with _CONFIG_LOCK:
        channel_config = {
            key: bool(getattr(_CONFIG, key, False))
            for key in ("enable_telegram", "enable_local", "enable_email", "enable_bark", "enable_serverchan")
        }
    push_status = notification_status_snapshot(channel_config)
    provider_health = provider_health_snapshot()

    return {
        "ok": True,
        "instance_id": f"{os.getpid()}:{int(_START_TIME)}",
        "running": running,
        "progress": progress,
        "action": action,
        "action_ts": action_ts,
        "action_age_sec": int(now_ts - action_ts) if action_ts else None,
        "notification_status": push_status,
        "provider_health": provider_health,
        "diagnostics": _runtime_diagnostics_snapshot(progress, provider_health),
        "traffic": _traffic_snapshot(),
        "results_revision": results_revision,
        "availability_logs_revision": availability_log_revision(),
    }


def runtime_status() -> Response:
    return jsonify(_runtime_status_snapshot())


def cache_status() -> Response:
    return jsonify({"ok": True, "cache": _scan_cache_status_snapshot()})


def cache_clear() -> Response:
    removed = _scan_cache_clear()
    return jsonify({"ok": True, "removed": removed, "cache": _scan_cache_status_snapshot()})


def provider_capabilities_status() -> Response:
    with _CONFIG_LOCK:
        enabled = list(_CONFIG.enabled_providers)
    return jsonify({"ok": True, "matrix": _provider_capability_matrix(enabled)})


def events_status() -> Response:
    try:
        limit = max(1, min(500, int(request.args.get("limit", 100))))
    except (TypeError, ValueError):
        limit = 100
    event_type = str(request.args.get("type", "") or "")
    return jsonify({
        "ok": True,
        "events": _list_events(limit=limit, event_type=event_type),
        "status": _event_status_snapshot(),
    })


def trends_status() -> Response:
    requested = [code.strip() for code in str(request.args.get("codes", "")).split(",") if code.strip()]
    with _CONFIG_LOCK:
        config_snapshot = deepcopy(_CONFIG)
    if not requested:
        requested = list(config_snapshot.hotel_codes)
    try:
        days = max(1, min(180, int(request.args.get("days", 30))))
    except (TypeError, ValueError):
        days = 30
    trends = _trend_snapshot(
        requested,
        days=days,
        scope_key=_analytics_scope_key(config_snapshot),
    )
    hotel_meta = {
        str(item.get("code") or ""): item
        for item in config_snapshot.selected_hotels
        if isinstance(item, dict) and item.get("code")
    }
    for hotel in trends.get("hotels", []):
        meta = hotel_meta.get(str(hotel.get("code") or ""), {})
        hotel["display_code"] = str(meta.get("display_code") or hotel.get("code") or "")
        hotel["name"] = str(
            meta.get("name_primary")
            or meta.get("name")
            or meta.get("name_en")
            or ""
        )
    return jsonify({"ok": True, "trends": trends})


def simulation_stress() -> Response:
    payload = request.get_json(force=True, silent=True) or {}
    try:
        iterations = max(1, min(5000, int(payload.get("iterations", 500))))
        concurrency = max(1, min(32, int(payload.get("concurrency", 4))))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "invalid stress test parameters"}), 400
    scenario = str(payload.get("scenario", "mixed") or "mixed")
    if scenario not in {"mixed", "available", "unavailable"}:
        scenario = "mixed"
    return jsonify(_run_simulation_stress_test(
        iterations=iterations,
        concurrency=concurrency,
        scenario=scenario,
    ))


def _prune_scan_cache() -> int:
    return _scan_cache_prune_impl()


def results_status() -> Response:
    try:
        since = int(request.args.get("since", -1))
    except (TypeError, ValueError):
        since = -1
    with _RESULTS_LOCK:
        revision = _RESULTS_REVISION
        changed = since != revision
        results = [asdict(result) for result in _LAST_RESULTS] if changed else None
    payload: Dict[str, Any] = {"ok": True, "changed": changed, "revision": revision}
    if results is not None:
        payload["results"] = results
    return jsonify(payload)


def availability_logs_status() -> Response:
    try:
        since = int(request.args.get("since", -1))
    except (TypeError, ValueError):
        since = -1
    revision = availability_log_revision()
    changed = since != revision
    payload: Dict[str, Any] = {"ok": True, "changed": changed, "revision": revision}
    if changed:
        payload["availability_logs"] = availability_log_snapshot()
    return jsonify(payload)


def logs_status() -> Response:
    try:
        after = max(0, int(request.args.get("after", 0)))
    except (TypeError, ValueError):
        after = 0
    with _LOG_LOCK:
        latest = _LOG_SEQUENCE
        first_sequence = latest - len(_LOG_LINES) + 1
        reset = bool(_LOG_LINES and after < first_sequence - 1)
        if reset:
            lines = list(_LOG_LINES[-300:])
        else:
            offset = max(0, after - (first_sequence - 1))
            lines = list(_LOG_LINES[offset:][-300:])
    return jsonify({"ok": True, "cursor": latest, "reset": reset, "logs": lines})


def status() -> Response:
    runtime_payload = _runtime_status_snapshot()
    with _CONFIG_LOCK:
        cfg = _public_config_dict(_CONFIG)
    with _RESULTS_LOCK:
        results = [asdict(result) for result in _LAST_RESULTS]
    with _LOG_LOCK:
        logs = list(_LOG_LINES[-300:])
        log_cursor = _LOG_SEQUENCE
    runtime_payload.update({
        "config": cfg,
        "results": results,
        "logs": logs,
        "log_cursor": log_cursor,
        "availability_logs": availability_log_snapshot(),
        "hotel_catalog": _catalog_status_snapshot(),
        "provider_catalog": {**_db_status_snapshot(), "checking": _PROVIDER_DATABASE_LOCK.locked()},
    })
    return jsonify(runtime_payload)


def hotel_info() -> Response:
        code = str(request.args.get("code") or "").strip()
        language = _normalize_primary_language(request.args.get("language") or DEFAULT_PRIMARY_LANGUAGE)
        try:
            if re.fullmatch(r"\d{1,5}", code):
                info = _get_hotel_info(code, language)
            else:
                hotel = _db_load_hotel(code, language)
                if not hotel:
                    raise ValueError("hotel is not present in the local database")
                info = _get_provider_hotel_info(hotel, language)
            return jsonify({"ok": True, "info": info})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            _log(f"[hotel-info] {code}/{language}: {exc}")
            return jsonify({"ok": False, "error": "official hotel information is temporarily unavailable"}), 502


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


def update_check() -> Response:
        _check_latest_async()
        with _UPDATE_LOCK:
            data = dict(_UPDATE_STATUS)
        return jsonify({"ok": True, "update": data}), 202


def hotel_catalog_status() -> Response:
        return jsonify({"ok": True, "catalog": _catalog_status_snapshot()})


def hotel_catalog_refresh() -> Response:
        return jsonify({"ok": True, "catalog": _request_catalog_refresh(force=True)}), 202


def hotel_catalog_acknowledge() -> Response:
        return jsonify({"ok": True, "catalog": _acknowledge_new_hotels()})


def provider_catalog_status() -> Response:
        return jsonify({"ok": True, **_db_status_snapshot(), "checking": _PROVIDER_DATABASE_LOCK.locked()})


def provider_catalog_refresh() -> Response:
        started = _request_provider_database_refresh(force=True)
        return jsonify({"ok": True, "started": started, "checking": True}), 202


def upgrade() -> Response:
        if _is_desktop_distribution():
            _upgrade_desktop_async()
        else:
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
        requested_providers = payload.get("providers", DEFAULT_ENABLED_PROVIDERS)
        providers = [provider for provider in requested_providers if provider in SUPPORTED_PROVIDERS] if isinstance(requested_providers, list) else list(DEFAULT_ENABLED_PROVIDERS)
        if not providers:
            return jsonify({"ok": False, "error": "at least one hotel brand is required"}), 400
        try:
            hotels: List[Dict[str, Any]] = []
            provider_counts: Dict[str, int] = {}
            provider_errors: Dict[str, str] = {}
            if "toyoko" in providers:
                try:
                    toyoko_hotels = _hotels_for_area_selection(region_id, detail_id, primary_language)
                    hotels.extend(toyoko_hotels)
                    provider_counts["toyoko"] = len(toyoko_hotels)
                except Exception as exc:
                    provider_errors["toyoko"] = str(exc)
            database_providers = [
                provider for provider in ("routeinn", "dormy", "mystays", "daiwa") if provider in providers
            ]
            if database_providers:
                prefecture_id = _prefecture_id_for_detail(region_id, detail_id)
                detail_area_id = None
                if detail_id.startswith("area-"):
                    try:
                        detail_area_id = int(detail_id.split("-", 1)[1])
                    except ValueError:
                        pass
                if not any(_db_provider_count(provider) for provider in database_providers):
                    _refresh_provider_database(force=False)
                for provider in database_providers:
                    try:
                        if detail_area_id == 5287:
                            provider_hotels = [
                                hotel for hotel in _db_load_hotels(
                                    provider, primary_language, region_id=region_id, prefecture_id=13
                                )
                                if int(hotel.get("detail_area_id") or 0) != 469
                            ]
                        else:
                            provider_hotels = _db_load_hotels(
                                provider,
                                primary_language,
                                region_id=region_id,
                                prefecture_id=prefecture_id,
                                detail_area_id=detail_area_id,
                            )
                        hotels.extend(provider_hotels)
                        provider_counts[provider] = len(provider_hotels)
                    except Exception as exc:
                        provider_errors[provider] = str(exc)
            provider_order = {provider: index for index, provider in enumerate(SUPPORTED_PROVIDERS)}
            hotels.sort(key=lambda hotel: (
                provider_order.get(str(hotel.get("provider") or ""), 9),
                str(hotel.get("display_code") or hotel.get("code") or ""),
            ))
            if not hotels and provider_errors:
                raise RuntimeError("; ".join(f"{key}: {value}" for key, value in provider_errors.items()))
            return jsonify({
                "ok": True,
                "hotels": hotels,
                "count": len(hotels),
                "provider_counts": provider_counts,
                "provider_errors": provider_errors,
            })
        except Exception as e:
            _log(f"[area] load hotels failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


def radius_hotels() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        query = str(payload.get("query") or "").strip()
        radius_km = max(1, min(50, int(payload.get("radius_km") or DEFAULT_RADIUS_KM)))
        primary_language = _normalize_primary_language(payload.get("primary_language", DEFAULT_PRIMARY_LANGUAGE))
        providers = payload.get("providers", DEFAULT_ENABLED_PROVIDERS)
        if not isinstance(providers, list):
            providers = list(DEFAULT_ENABLED_PROVIDERS)
        providers = [provider for provider in providers if provider in SUPPORTED_PROVIDERS]
        if not query:
            return jsonify({"ok": False, "error": "address or coordinates are required"}), 400
        if not providers:
            return jsonify({"ok": False, "error": "at least one hotel brand is required"}), 400
        try:
            center, hotels = _hotels_within_radius(query, radius_km, primary_language, providers)
            provider_counts = {
                provider: sum(1 for hotel in hotels if str(hotel.get("provider") or "toyoko") == provider)
                for provider in providers
            }
            return jsonify({
                "ok": True,
                "center": center,
                "hotels": hotels,
                "count": len(hotels),
                "provider_counts": provider_counts,
            })
        except Exception as e:
            _log(f"[radius] load hotels failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500


 # ========= Startup Helper: Port and Browser =========
def _find_free_port(preferred: int = 4170, host: str = "127.0.0.1") -> int:
        s = socket.socket()
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, preferred))
            s.close()
            return preferred
        except OSError:
            s.close()
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
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
