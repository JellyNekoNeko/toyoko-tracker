from __future__ import annotations

"""
东横酱 Toyoko Chan — Web version (Flask + Playwright/HTTP)

Relay：
  pip install flask beautifulsoup4 requests playwright

"""

import json
import re
import time
import random
import threading
import logging
import os
import sys
import webbrowser
import socket
import subprocess
import shutil
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any

import requests
from flask import Flask, request, jsonify, Response
from bs4 import BeautifulSoup
import smtplib
from email.message import EmailMessage

from importlib.metadata import version, PackageNotFoundError

# ---- precise timing helpers (monotonic) ----
def _now_wall() -> float:
    return time.time()

def _now_mono() -> float:
    return time.perf_counter()

# ---- Optional: Playwright (Driverless/Recommendation) ----
try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except Exception:
    _HAS_PLAYWRIGHT = False


# ========= Version number and application metadata =========
try:
    __version__ = version("toyoko-tracker")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

APP_NAME    = "东横酱 Toyoko Chan"
APP_AUTHOR  = "bilibili @果冻猫猫丶"
APP_VERSION = f"v{__version__}"


# ========= Constants (Configuration and Defaults)=========
DEFAULT_START_DATE = datetime.now().strftime("%Y-%m-%d")
DEFAULT_END_DATE   = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
DEFAULT_HOTEL_CODES: List[str] = [
    "00001", "00003", "00005", "00007", "00009"
]
DEFAULT_LOOP_INTERVAL_SECONDS = 30
DEFAULT_PER_HOTEL_DELAY_SECONDS = 1
DEFAULT_REQUEST_JITTER_PERCENT = 40
DEFAULT_ROOM_REQUIREMENT = "any"  # any|single|double|twin
DEFAULT_PEOPLE = 1
DEFAULT_ROOMS = 1
DEFAULT_SMOKING = "noSmoking"
DEFAULT_MEMBERSHIP_STATUS = "member"  # member|non_member|unknown
DEFAULT_AVAILABLE_ALERT_REPEAT = 1
DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC = 300
DEFAULT_BUDGET_ENABLED = False
DEFAULT_BUDGET_LIMIT = 30000  # non-member price, JPY
DEFAULT_ENABLE_TELEGRAM = False
DEFAULT_BOT_TOKEN = ""
DEFAULT_CHAT_ID = ""
DEFAULT_ENABLE_BARK = False
DEFAULT_BARK_KEY = ""
DEFAULT_BARK_SERVER = "https://api.day.app"
DEFAULT_ENABLE_SERVERCHAN = False
DEFAULT_SERVERCHAN_SENDKEY = ""
DEFAULT_SMART_PARALLEL_ENABLED = False
DEFAULT_SMART_PARALLEL_WORKERS = 1
DEFAULT_ENGINE = "http"
# Local desktop notifications
DEFAULT_ENABLE_LOCAL = False

# Email defaults
DEFAULT_ENABLE_EMAIL = False
DEFAULT_SMTP_HOST = ""
DEFAULT_SMTP_PORT = 465       # 587=STARTTLS; 465=SSL
DEFAULT_SMTP_TLS = True
DEFAULT_SMTP_USER = ""
DEFAULT_SMTP_PASS = ""
DEFAULT_EMAIL_FROM = ""
DEFAULT_EMAIL_TO = ""

# Configuration File Path (New Rules)
SAVE_FILENAME = "save.json"           # Manual Save/Load
AUTO_SAVE_FILENAME = "auto_save.json" # Start
SEARCH_HISTORY_FILENAME = "search_history.json"
BASE_DIR = os.path.dirname(__file__)
LEGACY_SAVE_PATH = os.path.join(BASE_DIR, SAVE_FILENAME)
LEGACY_AUTO_SAVE_PATH = os.path.join(BASE_DIR, AUTO_SAVE_FILENAME)


def _default_config_dir() -> str:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(root, "toyoko-tracker")


CONFIG_DIR = os.environ.get("TOYOKO_TRACKER_CONFIG_DIR") or _default_config_dir()
SAVE_PATH = os.path.join(CONFIG_DIR, SAVE_FILENAME)
AUTO_SAVE_PATH = os.path.join(CONFIG_DIR, AUTO_SAVE_FILENAME)
SEARCH_HISTORY_PATH = os.path.join(CONFIG_DIR, SEARCH_HISTORY_FILENAME)

# Fetch Configuration
BASE_URL = "https://www.toyoko-inn.com/eng/search/result/room_plan/"
TIMEOUT = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ========= Data Structure =========
@dataclass
class HotelResult:
    code: str
    url: str
    name: Optional[str]
    available: Optional[bool]
    # Non-Member
    min_price: Optional[int] = None
    min_price_text: Optional[str] = None
    min_price_room: Optional[str] = None
    min_price_plan: Optional[str] = None
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    # Member
    min_member_price_text: Optional[str] = None
    # Left
    min_remaining: Optional[str] = None
    # For UI: all matching offers to display (each: price_text, member_price_text, remaining_norm, room_title)
    offers_display: Optional[List[Dict[str, Any]]] = None
    requirement_unmet: bool = False


@dataclass
class AppConfig:
    start_date: str = DEFAULT_START_DATE
    end_date: str = DEFAULT_END_DATE
    hotel_codes: List[str] = None
    loop_interval_seconds: int = DEFAULT_LOOP_INTERVAL_SECONDS
    per_hotel_delay_seconds: int = DEFAULT_PER_HOTEL_DELAY_SECONDS
    request_jitter_percent: int = DEFAULT_REQUEST_JITTER_PERCENT
    people: int = DEFAULT_PEOPLE
    rooms: int = DEFAULT_ROOMS
    # Budget
    budget_enabled: bool = DEFAULT_BUDGET_ENABLED
    budget_limit: int = DEFAULT_BUDGET_LIMIT
    smoking: str = DEFAULT_SMOKING
    membership_status: str = DEFAULT_MEMBERSHIP_STATUS
    om_requirement: str = DEFAULT_ROOM_REQUIREMENT  # any|single|double|twin
    # Telegram
    enable_telegram: bool = DEFAULT_ENABLE_TELEGRAM
    bot_token: str = DEFAULT_BOT_TOKEN
    chat_id: str = DEFAULT_CHAT_ID
    # Bark / ServerChan
    enable_bark: bool = DEFAULT_ENABLE_BARK
    bark_key: str = DEFAULT_BARK_KEY
    bark_server: str = DEFAULT_BARK_SERVER
    enable_serverchan: bool = DEFAULT_ENABLE_SERVERCHAN
    serverchan_sendkey: str = DEFAULT_SERVERCHAN_SENDKEY
    # Local notifications
    enable_local: bool = DEFAULT_ENABLE_LOCAL
    # Email
    enable_email: bool = DEFAULT_ENABLE_EMAIL
    smtp_host: str = DEFAULT_SMTP_HOST
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_tls: bool = DEFAULT_SMTP_TLS
    smtp_user: str = DEFAULT_SMTP_USER
    smtp_pass: str = DEFAULT_SMTP_PASS
    email_from: str = DEFAULT_EMAIL_FROM
    email_to: str = DEFAULT_EMAIL_TO
    # Alerts repeat
    available_alert_repeat: int = DEFAULT_AVAILABLE_ALERT_REPEAT
    available_alert_repeat_interval_sec: int = DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC
    # Rendering engine: "http" or "playwright"
    engine: str = DEFAULT_ENGINE
    smart_parallel_enabled: bool = DEFAULT_SMART_PARALLEL_ENABLED
    smart_parallel_workers: int = DEFAULT_SMART_PARALLEL_WORKERS
    area_region: str = ""
    area_detail: str = ""
    area_region_label: str = ""
    area_detail_label: str = ""
    selected_hotels: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.hotel_codes is None:
            self.hotel_codes = list(DEFAULT_HOTEL_CODES)
        if self.selected_hotels is None:
            self.selected_hotels = []


# ========= Global Status =========
_ALERT_STATE: Dict[str, Dict[str, Any]] = {}
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
_PUSH_STATUS_LOCK = threading.Lock()
_PUSH_STATUS: Dict[str, Dict[str, Any]] = {}
_CONFIG = AppConfig()
_CONFIG_LOCK = threading.Lock()

_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_RUN_REQUESTED = False  # only set True by /start; set False by /stop
# ========= Mail Queue (async, non-blocking) =========
_MAIL_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue()
_MAIL_THREAD: Optional[threading.Thread] = None
_MAIL_STOP = threading.Event()

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


def _set_push_status(channel: str, state: str, message: str = "") -> None:
    with _PUSH_STATUS_LOCK:
        _PUSH_STATUS[channel] = {
            "state": state,
            "message": message,
            "ts": time.time(),
        }


def _notification_status_snapshot(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    channels = [
        ("telegram", "Telegram机器人", "Telegram Bot", bool(cfg.get("enable_telegram"))),
        ("local", "本地通知", "Local Notifications", bool(cfg.get("enable_local"))),
        ("email", "邮件", "Email", bool(cfg.get("enable_email"))),
        ("bark", "Bark", "Bark", bool(cfg.get("enable_bark"))),
        ("serverchan", "Server酱", "Server Chan", bool(cfg.get("enable_serverchan"))),
    ]
    now = time.time()
    with _PUSH_STATUS_LOCK:
        latest = deepcopy(_PUSH_STATUS)
    out: List[Dict[str, Any]] = []
    for key, label_zh, label_en, enabled in channels:
        item = latest.get(key, {})
        state = str(item.get("state") or "waiting")
        if not enabled:
            state = "disabled"
        out.append({
            "key": key,
            "label_zh": label_zh,
            "label_en": label_en,
            "enabled": enabled,
            "state": state,
            "message": item.get("message") or "",
        "age_sec": int(now - float(item.get("ts") or now)) if item.get("ts") else None,
        })
    return out


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
            "name_zh": str(h.get("name_zh") or ""),
            "name_en": str(h.get("name_en") or h.get("name") or ""),
            "url": str(h.get("url") or ""),
            "map_url": str(h.get("map_url") or ""),
        })
    return clean

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
            cfg.selected_hotels = _clean_selected_hotels(data.get("selected_hotels", getattr(cfg, "selected_hotels", [])))
            cfg.people = int(data.get('people', cfg.people))
            cfg.rooms = int(data.get('rooms', cfg.rooms))
            sm = str(data.get('smoking', cfg.smoking))
            if sm in {"Smoking", "noSmoking", "all"}:
                cfg.smoking = sm
            ms = str(data.get('membership_status', getattr(cfg, 'membership_status', DEFAULT_MEMBERSHIP_STATUS)))
            if ms in {"member", "non_member", "unknown"}:
                cfg.membership_status = ms
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
            cfg.enable_serverchan = bool(data.get('enable_serverchan', cfg.enable_serverchan))
            cfg.serverchan_sendkey = data.get('serverchan_sendkey', cfg.serverchan_sendkey)
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
            cfg.available_alert_repeat = max(1, min(11, int(data.get('available_alert_repeat', cfg.available_alert_repeat))))
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
                'selected_hotels': _clean_selected_hotels(getattr(cfg, 'selected_hotels', [])),
                'people': cfg.people,
                'rooms': cfg.rooms,
                'smoking': cfg.smoking,
                'membership_status': getattr(cfg, 'membership_status', DEFAULT_MEMBERSHIP_STATUS),
                'room_requirement': getattr(cfg, 'room_requirement',
                                            getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT)),
                'enable_telegram': cfg.enable_telegram,
                'bot_token': cfg.bot_token,
                'chat_id': cfg.chat_id,
                'enable_bark': cfg.enable_bark,
                'bark_key': cfg.bark_key,
                'bark_server': cfg.bark_server,
                'enable_serverchan': cfg.enable_serverchan,
                'serverchan_sendkey': cfg.serverchan_sendkey,
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
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SEARCH_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(records[:10], f, ensure_ascii=False, indent=2)
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
        "hotel_codes": list(cfg.hotel_codes),
        "selected_hotels": clean_hotels,
    }
    return record


def _remember_search(payload: Dict[str, Any], cfg: AppConfig) -> None:
    try:
        record = _search_history_record(payload, cfg)
        signature_keys = (
            "start_date", "end_date", "people", "rooms", "smoking", "room_requirement",
            "membership_status", "engine", "loop_interval_seconds", "per_hotel_delay_seconds", "request_jitter_percent",
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


def _room_title_zh(title: Optional[str]) -> str:
    if not title:
        return ""
    t = str(title).lower()
    if "economy" in t and "single" in t:
        return "经济单人房"
    if "single" in t:
        return "单人房"
    if "economy" in t and "double" in t:
        return "经济大床房"
    if "double" in t:
        return "大床房"
    if "economy" in t and "twin" in t:
        return "经济双床房"
    if "twin" in t:
        return "双床房"
    if "heartful" in t or "accessible" in t:
        return "无障碍房"
    return ""


def _local_notification_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    return (text
            .replace("🟢", "[START]")
            .replace("✅", "[OK]")
            .replace("❌", "[NO]")
            .replace("❗", "[CHECK]")
            .replace("❓", "[UNKNOWN]")
            .replace("→", "->"))


class RenderedPage:
    def __init__(self, soup: BeautifulSoup, visible_text: str):
        self.soup = soup
        self.visible_text = visible_text


# ---- Playwright-based renderer ----
def _playwright_launch_args(cfg: AppConfig) -> List[str]:
    args = []
    args.append("--lang=en-US,en;q=0.9")
    args.append("--no-sandbox")
    args.append("--disable-dev-shm-usage")
    args.append("--disable-gpu")
    args.append("--window-size=1280,1600")
    return args


def _playwright_route_request(route: Any) -> None:
    try:
        request_obj = route.request
        if request_obj.resource_type in {"image", "media", "font"}:
            route.abort()
            return
        host = ""
        try:
            from urllib.parse import urlparse
            host = urlparse(request_obj.url).netloc.lower()
        except Exception:
            host = ""
        if any(x in host for x in ("googletagmanager", "google-analytics", "doubleclick")):
            route.abort()
            return
        route.continue_()
    except Exception:
        try:
            route.continue_()
        except Exception:
            pass


def _fetch_rendered_playwright_page(page: Any, url: str) -> RenderedPage:
    page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
    # Wait for either main or body, then for possible price value span (best-effort).
    try:
        page.wait_for_selector("main", timeout=3000)
    except Exception:
        try:
            page.wait_for_selector("body", timeout=3000)
        except Exception:
            pass
    try:
        page.wait_for_selector('span[class*="SearchResultRoomPlanChildCard_value"]', timeout=2500)
    except Exception:
        pass
    try:
        page.wait_for_timeout(400)
    except Exception:
        pass
    html = page.content()
    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        body_text = ""
    soup = BeautifulSoup(html, "html.parser")
    return RenderedPage(soup, body_text)


class PlaywrightRenderer:
    """Reusable Playwright browser session for a worker loop."""

    def __init__(self, cfg: AppConfig):
        if not _HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright is not available")
        _log("Launching headless Chromium via Playwright...")
        _set_action("Launching headless Chromium via Playwright...")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True, args=_playwright_launch_args(cfg))
        self._context = self._browser.new_context(
            user_agent=HEADERS.get("User-Agent", None),
            viewport={"width": 1280, "height": 1600},
        )
        self._context.set_default_timeout(TIMEOUT * 1000)
        self._context.set_default_navigation_timeout(TIMEOUT * 1000)
        try:
            self._context.route("**/*", _playwright_route_request)
        except Exception as e:
            _log(f"[playwright] route optimization skipped: {e}")
        self._page = self._context.new_page()
        _log("Playwright Chromium is ready.")
        _set_action("Playwright Chromium is ready.")

    def fetch(self, url: str) -> RenderedPage:
        return _fetch_rendered_playwright_page(self._page, url)

    def close(self) -> None:
        for obj in (getattr(self, "_context", None), getattr(self, "_browser", None)):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        self._context = None
        self._browser = None
        try:
            if getattr(self, "_pw", None):
                self._pw.stop()
        except Exception:
            pass
        self._pw = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def fetch_rendered_playwright(cfg: AppConfig, url: str) -> RenderedPage:
    """
    Use Playwright (Chromium) to render pages.
    This one-shot helper is kept for compatibility; the worker uses PlaywrightRenderer.
    """
    renderer = PlaywrightRenderer(cfg)
    try:
        return renderer.fetch(url)
    finally:
        renderer.close()


def fetch_rendered_any(cfg: AppConfig, renderer: Optional[Any], url: str) -> RenderedPage:
    """
    Fetch a rendered page with Playwright.
    """
    if not _HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright is not available")
    if isinstance(renderer, PlaywrightRenderer):
        return renderer.fetch(url)
    return fetch_rendered_playwright(cfg, url)


def extract_hotel_name(soup: BeautifulSoup) -> Optional[str]:
    tag = soup.select_one('h1[class*="room_plan_title"]')
    if tag and tag.get_text(strip=True):
        return tag.get_text(strip=True)
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return None


def _parse_price_int(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"¥\s*([\d,]+)", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except Exception:
        return None


def parse_remaining(text: str) -> Optional[str]:
    """
    - "Only 3 Rooms Left" -> "3"
    - "Only 1 Room Left"  -> "1"
    - "Reserve"           -> "≥10"
    """
    if not text:
        return None
    t = text.strip()
    low = t.lower()
    if low.startswith("only"):
        m = re.search(r"(\d+)", t)
        if m:
            return m.group(1)
    if low == "reserve":
        return "≥10"
    return None


def _is_ignored_room(title: Optional[str]) -> bool:
    """Ignore heartful / accessible Room(s)。"""
    if not title:
        return False
    t = str(title).lower()
    return ("heartful" in t) or ("accessible" in t)


def _smoking_type_from_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    raw = str(text)
    low = raw.lower()
    if (
        "non-smoking" in low
        or "non smoking" in low
        or "nonsmoking" in low
        or "no smoking" in low
        or "禁煙" in raw
        or "禁烟" in raw
    ):
        return "non_smoking"
    if "smoking" in low or "喫煙" in raw or "吸煙" in raw or "吸烟" in raw:
        return "smoking"
    return None


def extract_offers(soup: BeautifulSoup) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    """
    Extract All Sub-Cards（offer）：
      room_title, plan_name, price_text(Non-Member)、price_val、member_price_text、remaining_text/remaining_norm
    """
    offers: List[Dict[str, Any]] = []
    had_any_offer = False                 # any offer with a numeric price
    had_any_non_ignored_offer = False     # any non-ignored offer with price
    had_any_ignored_offer = False         # any ignored (heartful/accessible) offer with price

    def _extract_one_child(child, room_title, room_smoking=None):
        plan_name = None
        plan_el = child.select_one('[class*="SearchResultRoomPlanChildCard_title"]')
        if plan_el:
            plan_name = plan_el.get_text(strip=True) or None

        price_text = None
        price_val: Optional[int] = None
        member_price_text = None
        member_price_val: Optional[int] = None
        offer_url = None
        link_el = child.find("a", href=True)
        if link_el:
            offer_url = requests.compat.urljoin(BASE_URL, link_el.get("href"))

        # Non-Member Price
        price_block = child.select_one('div[class*="SearchResultRoomPlanChildCard_price"]')
        if price_block:
            val_el = price_block.select_one('span[class*="SearchResultRoomPlanChildCard_value"]')
            if val_el:
                price_text = val_el.get_text(strip=True)
                price_val = _parse_price_int(price_text)
            else:
                m = re.search(r"¥\s*[\d,]+", price_block.get_text(" ", strip=True))
                if m:
                    price_text = m.group(0)
                    price_val = _parse_price_int(price_text)

        # Member Price
        mem_el = child.select_one(
            'div[class*="SearchResultRoomPlanChildCard_member-section"] '
            'span[class*="SearchResultRoomPlanChildCard_value"]'
        )
        if mem_el:
            member_price_text = mem_el.get_text(strip=True)
            member_price_val = _parse_price_int(member_price_text)
        if not member_price_text:
            txt = child.get_text(" ", strip=True)
            m = re.search(r"Club\s*Card\s*Member\s*Price\s*(¥\s*[\d,]+)", txt, re.I)
            if m:
                member_price_text = m.group(1).strip()
                member_price_val = _parse_price_int(member_price_text)

        # Rooms Left
        remaining_text = None
        block_text = child.get_text(" ", strip=True)
        m = re.search(r"Only\s+\d+\s+Rooms?\s+Left", block_text, re.I)
        if m:
            remaining_text = m.group(0)
        elif re.search(r"\bReserve\b", block_text, re.I):
            remaining_text = "Reserve"

        # Determine if this child represents a priced offer
        has_price = (price_val is not None)
        if has_price:
            nonlocal had_any_offer
            had_any_offer = True

        # Ignore special accessibility rooms for the main offer list,
        # but record that such priced offers existed.
        if _is_ignored_room(room_title):
            if has_price:
                nonlocal had_any_ignored_offer
                had_any_ignored_offer = True
            return

        if has_price:
            nonlocal had_any_non_ignored_offer
            had_any_non_ignored_offer = True

        item = {
            "room_title": room_title,
            "plan_name": plan_name,
            "price_text": price_text,
            "price_val": price_val,
            "member_price_text": member_price_text,
            "member_price_val": member_price_val,
            "remaining_text": remaining_text,
            "remaining_norm": parse_remaining(remaining_text) if remaining_text else None,
            "url": offer_url,
        }
        if room_smoking:
            item["room_smoking"] = room_smoking
        offers.append(item)

    # Ordinary Parent/Child Structure
    for room_card in soup.select('div[class*="SearchResultRoomPlanParentCard_card"]'):
        room_title = None
        title_el = room_card.select_one('[class*="SearchResultRoomPlanParentCard_title"]')
        if title_el:
            room_title = title_el.get_text(strip=True)
        room_smoking = _smoking_type_from_text(room_card.get_text(" ", strip=True))
        for child in room_card.select('div[class*="SearchResultRoomPlanChildCard_card-wrapper"]'):
            _extract_one_child(child, room_title, room_smoking)

    for child in soup.select('div[class*="SearchResultRoomPlanChildCard_card-wrapper"]'):
        anc = child.find_parent(attrs={"class": re.compile("SearchResultRoomPlanParentCard_card")})
        if anc:
            continue
        room_title = None
        title_parent = child.find_previous(attrs={"class": re.compile("SearchResultRoomPlanParentCard_title")})
        if title_parent:
            room_title = title_parent.get_text(strip=True)
        _extract_one_child(child, room_title, _smoking_type_from_text(child.get_text(" ", strip=True)))

    stats = {
        "had_any_offer": had_any_offer,
        "had_any_non_ignored_offer": had_any_non_ignored_offer,
        "had_any_ignored_offer": had_any_ignored_offer,
    }
    return offers, stats


def detect_price_available(visible_text: str) -> bool:
    text = " ".join(visible_text.split())
    if re.search(r"¥\s*\d", text):
        return True
    if re.search(r"\b\d{1,3}(?:,\d{3})+\b", text):
        return True
    return False


def _room_type_of(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    t = title.lower()
    # single: 单人房 / single
    # double: 大床房 / double
    # twin:   双床房 / twin
    if "single" in t:
        return "single"
    if "double" in t:
        return "double"
    if "twin" in t:
        return "twin"
    return None


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

    membership_status = getattr(cfg, "membership_status", DEFAULT_MEMBERSHIP_STATUS)

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
        else:
            # Fallback: if parsing found no usable offers, try text heuristic.
            available = detect_price_available(visible_text or "") if visible_text is not None else False
        min_price = None
        min_price_text = None
        min_room = None
        min_plan = None
        min_member_price_text = None
        min_remaining = None

    name_info = _hotel_names_by_code(code, name)
    return HotelResult(
        code=code,
        url=url,
        name=name,
        name_zh=name_info.get("zh"),
        name_en=name_info.get("en"),
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


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return int(value)
    except Exception:
        return None


def _extract_next_data(html: str) -> Optional[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        return None
    raw = tag.string or tag.get_text("", strip=True)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_http_offers(plan_response: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    offers: List[Dict[str, Any]] = []
    had_any_offer = False
    had_any_non_ignored_offer = False
    had_any_ignored_offer = False

    room_types = plan_response.get("roomTypeList") or []
    for room in room_types:
        if not isinstance(room, dict):
            continue
        room_title = (
            room.get("roomTypeName")
            or room.get("roomTypeTitle")
            or room.get("roomName")
            or room.get("name")
        )
        room_smoking = None
        specs = room.get("specs") if isinstance(room.get("specs"), dict) else {}
        if "isSmoking" in specs:
            room_smoking = "smoking" if bool(specs.get("isSmoking")) else "non_smoking"
        if not room_smoking:
            room_smoking = _smoking_type_from_text(" ".join(str(v) for v in room.values() if isinstance(v, str)))
        plans = room.get("plans") or room.get("planList") or []
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            price = plan.get("price") or {}
            vacant = plan.get("vacant") or {}
            general_vacant = _coerce_int(vacant.get("generalVacantRoom"))
            member_vacant = _coerce_int(vacant.get("membershipVacantRoom"))
            vacant_candidates = [v for v in (general_vacant, member_vacant) if v is not None]
            vacant_rooms = max(vacant_candidates) if vacant_candidates else 0
            if vacant_rooms <= 0:
                continue

            price_val = _coerce_int(
                price.get("generalPrice")
                or price.get("price")
                or plan.get("generalPrice")
                or plan.get("price")
            )
            if price_val is None:
                continue

            had_any_offer = True
            if _is_ignored_room(room_title):
                had_any_ignored_offer = True
                continue

            had_any_non_ignored_offer = True
            member_price_val = _coerce_int(
                price.get("membershipPrice")
                or price.get("memberPrice")
                or plan.get("membershipPrice")
                or plan.get("memberPrice")
            )
            item = {
                "room_title": room_title,
                "plan_name": plan.get("planName") or plan.get("name"),
                "price_text": f"¥ {price_val:,}",
                "price_val": price_val,
                "member_price_text": f"¥ {member_price_val:,}" if member_price_val is not None else None,
                "member_price_val": member_price_val,
                "remaining_text": "Reserve" if vacant_rooms >= 10 else f"Only {vacant_rooms} Room{'s' if vacant_rooms != 1 else ''} Left",
                "remaining_norm": "≥10" if vacant_rooms >= 10 else str(vacant_rooms),
            }
            if room_smoking:
                item["room_smoking"] = room_smoking
            offers.append(item)

    stats = {
        "had_any_offer": had_any_offer,
        "had_any_non_ignored_offer": had_any_non_ignored_offer,
        "had_any_ignored_offer": had_any_ignored_offer,
    }
    return offers, stats


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


# ========= Notification（Telegram/Local/Mail）=========
def _tg_enabled(cfg: AppConfig) -> bool:
    return cfg.enable_telegram and bool(cfg.bot_token) and bool(cfg.chat_id)


def notify_telegram(cfg: AppConfig, message: str) -> None:
    if not _tg_enabled(cfg):
        return
    try:
        _set_push_status("telegram", "pushing", "sending")
        _set_action("[tg] sending message...")
        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        payload = {"chat_id": cfg.chat_id, "text": message}
        resp = requests.post(url, data=payload, timeout=15)
        ok = False
        err = None
        if resp is not None:
            try:
                data = resp.json()
                ok = bool(data.get("ok"))
                if not ok:
                    err = data.get("description") or str(data)
            except Exception:
                err = f"HTTP {resp.status_code} non-JSON"
        if ok:
            _set_action("[tg] sent OK")
            _set_push_status("telegram", "success", "sent OK")
            _log("[tg] sent OK")
        else:
            _set_action(f"[tg] failed: {err or 'unknown error'}")
            _set_push_status("telegram", "failed", err or "unknown error")
            _log(f"[tg] failed: {err or 'unknown error'}")
    except Exception as e:
        _set_action(f"[tg] exception: {e}")
        _set_push_status("telegram", "failed", str(e))
        _log(f"[tg] exception: {e}")


def _bark_enabled(cfg: AppConfig) -> bool:
    return bool(getattr(cfg, "enable_bark", False) and getattr(cfg, "bark_key", ""))


def notify_bark(cfg: AppConfig, title: str, body: str, url: Optional[str] = None) -> None:
    if not _bark_enabled(cfg):
        return
    try:
        _set_push_status("bark", "pushing", "sending")
        server = (getattr(cfg, "bark_server", DEFAULT_BARK_SERVER) or DEFAULT_BARK_SERVER).rstrip("/")
        key = str(getattr(cfg, "bark_key", "")).strip().strip("/")
        endpoint = f"{server}/{key}"
        payload = {
            "title": title,
            "body": body,
            "sound": "minuet",
            "group": "Toyoko Tracker",
        }
        if url:
            payload["url"] = url
        resp = requests.post(endpoint, json=payload, timeout=15)
        ok = 200 <= resp.status_code < 300
        if ok:
            try:
                data = resp.json()
                ok = (data.get("code") in (200, 0, None)) or bool(data.get("success"))
            except Exception:
                ok = True
        if ok:
            _set_action("[bark] sent OK")
            _set_push_status("bark", "success", "sent OK")
            _log("[bark] sent OK")
        else:
            _set_action(f"[bark] failed: HTTP {resp.status_code}")
            _set_push_status("bark", "failed", f"HTTP {resp.status_code}")
            _log(f"[bark] failed: HTTP {resp.status_code} {resp.text[:160]}")
    except Exception as e:
        _set_action(f"[bark] exception: {e}")
        _set_push_status("bark", "failed", str(e))
        _log(f"[bark] exception: {e}")


def _serverchan_enabled(cfg: AppConfig) -> bool:
    return bool(getattr(cfg, "enable_serverchan", False) and getattr(cfg, "serverchan_sendkey", ""))


def notify_serverchan(cfg: AppConfig, title: str, body: str) -> None:
    if not _serverchan_enabled(cfg):
        return
    try:
        _set_push_status("serverchan", "pushing", "sending")
        sendkey = str(getattr(cfg, "serverchan_sendkey", "")).strip()
        endpoint = f"https://sctapi.ftqq.com/{sendkey}.send"
        resp = requests.post(endpoint, data={"title": title, "desp": body}, timeout=15)
        ok = 200 <= resp.status_code < 300
        if ok:
            try:
                data = resp.json()
                ok = int(data.get("code", 0)) == 0
            except Exception:
                ok = True
        if ok:
            _set_action("[serverchan] sent OK")
            _set_push_status("serverchan", "success", "sent OK")
            _log("[serverchan] sent OK")
        else:
            _set_action(f"[serverchan] failed: HTTP {resp.status_code}")
            _set_push_status("serverchan", "failed", f"HTTP {resp.status_code}")
            _log(f"[serverchan] failed: HTTP {resp.status_code} {resp.text[:160]}")
    except Exception as e:
        _set_action(f"[serverchan] exception: {e}")
        _set_push_status("serverchan", "failed", str(e))
        _log(f"[serverchan] exception: {e}")


def notify_push_channels(cfg: AppConfig, title: str, body: str, url: Optional[str] = None) -> None:
    notify_telegram(cfg, body)
    notify_email(cfg, title, body)
    notify_local(cfg, title, body)
    notify_bark(cfg, title, body, url)
    notify_serverchan(cfg, title, body)


def notify_local(cfg: AppConfig, title: str, body: str) -> None:
    if not getattr(cfg, "enable_local", False):
        _log("[local] skipped: enable_local = False")
        return
    try:
        _set_push_status("local", "pushing", "notifying")
        _set_action("[local] notifying...")
        # Windows consoles/toasters may not render emoji properly — sanitize to ASCII
        if os.name == "nt":
            title = _local_notification_text(title)
            body = _local_notification_text(body)
        if sys.platform == "darwin":
            title = _local_notification_text(title)
            body = _local_notification_text(body)
            # macOS requires notification permission for the sending app.
            # Prefer terminal-notifier when installed; fall back to osascript.
            tn = shutil.which("terminal-notifier")
            sent = False
            if tn:
                try:
                    proc = subprocess.run(
                        [tn, "-title", title, "-message", body, "-group", "toyoko-inn-tracker", "-sound", "default"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    )
                    if proc.returncode == 0:
                        sent = True
                        _set_push_status("local", "success", "terminal-notifier sent OK")
                        _log("[local] terminal-notifier sent OK")
                    else:
                        err = (proc.stderr or proc.stdout or "").strip()
                        _log(f"[local] terminal-notifier failed: {err or 'non-zero exit'}")
                except Exception as _tn_e:
                    _log(f"[local] terminal-notifier failed: {_tn_e}")
            if not sent:
                script = (
                    'on run argv\n'
                    '  display notification (item 2 of argv) with title (item 1 of argv) '
                    'subtitle "Toyoko Tracker" sound name "Glass"\n'
                    'end run'
                )
                try:
                    proc = subprocess.run(
                        ["osascript", "-e", script, title, body],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    )
                    if proc.returncode == 0:
                        sent = True
                        _set_push_status("local", "success", "osascript sent OK")
                        _log("[local] osascript sent OK")
                    else:
                        err = (proc.stderr or proc.stdout or "").strip()
                        _log(f"[local] osascript failed: {err or 'non-zero exit'}")
                except Exception as _e2:
                    _log(f"[local] osascript failed: {_e2}")
            if not sent:
                _set_push_status("local", "failed", "macOS notification not delivered")
                _log("[local] macOS notification was not delivered. Check System Settings > Notifications for Terminal/Python/osascript.")
        elif os.name == "nt":
            # Non-blocking Windows balloon tip via PowerShell + NotifyIcon (no user confirmation required)
            try:
                # Prepare a short PowerShell script that shows a system tray balloon tip and exits
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "Add-Type -AssemblyName System.Drawing; "
                    "$ni = New-Object System.Windows.Forms.NotifyIcon; "
                    "$ni.Icon = [System.Drawing.SystemIcons]::Information; "
                    "$ni.Visible = $true; "
                    f"$ni.BalloonTipTitle = {json.dumps(title)}; "
                    f"$ni.BalloonTipText = {json.dumps(body)}; "
                    "$ni.ShowBalloonTip(4000); "  # show for ~4s
                    "Start-Sleep -Milliseconds 1200; "  # give it a moment to appear, but do not block our process
                    "$ni.Dispose();"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                _set_push_status("local", "success", "NotifyIcon invoked")
                _log("[local] powershell NotifyIcon balloon shown (non-blocking)")
            except Exception as _e_win_balloon:
                _log(f"[local] NotifyIcon balloon failed: {_e_win_balloon}")
        else:
            try:
                subprocess.Popen(["notify-send", title, body],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _set_push_status("local", "success", "notify-send invoked")
                _log("[local] notify-send invoked")
            except Exception as _e4:
                _set_push_status("local", "failed", str(_e4))
                _log(f"[local] notify-send failed: {_e4}")
    except Exception as e:
        _set_push_status("local", "failed", str(e))
        _log(f"[local] exception: {e}")


def _email_enabled(cfg: AppConfig) -> bool:
    return bool(cfg.enable_email and cfg.smtp_host and cfg.email_from and cfg.email_to)

def _send_email_now(cfg_snapshot: Dict[str, Any], subject: str, body: str) -> None:
    """
    低层“立即发送”函数：使用配置快照（dict）防止并发修改。
    逻辑与旧版同步发送一致。
    """
    try:
        host = cfg_snapshot.get("smtp_host") or ""
        port = int(cfg_snapshot.get("smtp_port") or 0)
        use_tls = bool(cfg_snapshot.get("smtp_tls"))
        user = cfg_snapshot.get("smtp_user") or ""
        passwd = cfg_snapshot.get("smtp_pass") or ""
        email_from = cfg_snapshot.get("email_from") or ""
        email_to = cfg_snapshot.get("email_to") or ""

        if not (host and email_from and email_to and port):
            _set_push_status("email", "failed", "incomplete SMTP configuration")
            _log("[mail] skipped: incomplete SMTP configuration")
            return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = email_from
        tos = [x.strip() for x in str(email_to).split(",") if x.strip()]
        msg["To"] = ", ".join(tos) if tos else email_to
        msg.set_content(body)

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if use_tls:
                try:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                except Exception:
                    pass

        if user and passwd:
            server.login(user, passwd)
        server.send_message(msg)
        try:
            server.quit()
        except Exception:
            server.close()

        _log("[mail] sent OK (worker)")
        _set_push_status("email", "success", "sent OK")
    except Exception as e:
        _set_push_status("email", "failed", str(e))
        _log(f"[mail] exception (worker): {e}")


def _ensure_mail_worker_started() -> None:
    global _MAIL_THREAD
    if _MAIL_THREAD and _MAIL_THREAD.is_alive():
        return
    _MAIL_STOP.clear()

    def _mail_worker():
        _log("[mail] worker started")
        while not _MAIL_STOP.is_set():
            try:
                item = _MAIL_QUEUE.get(timeout=0.5)
            except Exception:
                continue
            try:
                _send_email_now(item["cfg"], item["subject"], item["body"])
            finally:
                try:
                    _MAIL_QUEUE.task_done()
                except Exception:
                    pass
        _log("[mail] worker stopped")

    _MAIL_THREAD = threading.Thread(target=_mail_worker, name="mail-worker", daemon=True)
    _MAIL_THREAD.start()

def notify_email(cfg: AppConfig, subject: str, body: str) -> None:
    """
    """
    if not _email_enabled(cfg):
        return
    try:
        _ensure_mail_worker_started()
        cfg_snapshot = deepcopy(asdict(cfg))
        _MAIL_QUEUE.put_nowait({"cfg": cfg_snapshot, "subject": subject, "body": body})
        _set_action("[mail] queued")
        _set_push_status("email", "pushing", "queued")
        _log("[mail] queued")
    except Exception as e:
        _set_action(f"[mail] queue exception: {e}")
        _set_push_status("email", "failed", str(e))
        _log(f"[mail] queue exception: {e}")


def _send_start_notifications(cfg: AppConfig) -> None:
    try:
        codes = ", ".join(cfg.hotel_codes) if cfg.hotel_codes else "(none)"
        summary_lines = [
            "🟢 Tracking started",
            f"Dates: {cfg.start_date} → {cfg.end_date}",
            f"People: {cfg.people} | Rooms: {cfg.rooms} | Smoking: {cfg.smoking}",
            f"Hotels ({len(cfg.hotel_codes)}): {codes}",
        ]
        msg = "\n".join(summary_lines)
        notify_push_channels(cfg, "🟢 Tracking started", msg)
        _log("[start] start notifications sent (enabled channels)")
    except Exception as e:
        _log(f"[start] start notifications error: {e}")


def _format_offer_lines_for_push(r: HotelResult) -> List[str]:
    """
    Build multi-offer lines for notifications. Prefer r.offers_display (already filtered by budget/room requirement),
    fall back to single-offer fields if necessary.
    """
    lines: List[str] = []
    membership = getattr(_CONFIG, "membership_status", DEFAULT_MEMBERSHIP_STATUS)

    def _push_price(non_member: Optional[str], member: Optional[str]) -> str:
        if membership == "member":
            return member or non_member or "-"
        if membership == "non_member":
            return non_member or "-"
        if member:
            return f"{non_member or '-'} (Member: {member})"
        return non_member or "-"

    # Use all qualifying offers when present
    offers = getattr(r, "offers_display", None)
    if isinstance(offers, list) and offers:
        for o in offers:
            room = o.get("room_title_zh") or o.get("room_title") or "-"
            price = _push_price(o.get("price_text"), o.get("member_price_text"))
            left = o.get("remaining_norm") or "-"
            lines.append(f"• {room} | {price} | Left: {left}")
        return lines
    # Fallback to single fields (legacy)
    price = _push_price(r.min_price_text, r.min_member_price_text)
    room = r.min_price_room or "-"
    left = r.min_remaining or "-"
    lines.append(f"• {room} | {price} | Left: {left}")
    return lines

def process_notifications(cfg: AppConfig, results: List[HotelResult], start_date: str, end_date: str) -> None:
    for r in results:
        if getattr(r, "requirement_unmet", False):
            continue
        key = f"{r.code}|{start_date}|{end_date}"
        st = _ALERT_STATE.get(key, {"available": False, "sent": 0, "last": 0.0})
        was_available = bool(st.get("available", False))
        is_available = bool(r.available)
        now = time.time()

        if is_available and not was_available:
            title = r.name or "(Hotel name not found)"
            lines = [
                "✅ Toyoko Inn Available room(s)",
                f"HotelName: {title}",
                f"Date: {start_date} → {end_date}",
            ]
            # Append all qualifying room offers (multiple lines)
            offer_lines = _format_offer_lines_for_push(r)
            if offer_lines:
                lines.append("Offers:")
                lines.extend(offer_lines)
            # Always include URL at the end
            lines.append(f"URL: {r.url}")
            msg = "\n".join([x for x in lines if x])
            notify_push_channels(cfg, "✅ Toyoko Inn Available room(s)", msg, r.url)
            st = {"available": True, "sent": 1, "last": now}

        elif is_available and was_available:
            repeat_limit = max(1, min(11, int(cfg.available_alert_repeat)))
            interval = max(60, int(cfg.available_alert_repeat_interval_sec))
            sent = int(st.get("sent", 0) or 0)
            reminders_sent = max(0, sent - 1)
            repeat_forever = repeat_limit >= 11
            if (repeat_forever or reminders_sent < repeat_limit) and (now - st.get("last", 0)) >= interval:
                title = r.name or "(Hotel name not found)"
                lines = [
                    "✅ Toyoko Inn Available room(s) — reminder",
                    f"HotelName: {title}",
                    f"Date: {start_date} → {end_date}",
                ]
                offer_lines = _format_offer_lines_for_push(r)
                if offer_lines:
                    lines.append("Offers:")
                    lines.extend(offer_lines)
                lines.append(f"URL: {r.url}")
                msg = "\n".join(lines)
                notify_push_channels(cfg, "✅ Toyoko Inn Available room(s) — reminder", msg, r.url)
                st["sent"] = sent + 1
                st["last"] = now

        elif (not is_available) and was_available:
            title = r.name or "(Hotel name not found)"
            lines = [
                "❌ Toyoko Inn no longer available",
                f"HotelName: {title}",
                f"Date: {start_date} → {end_date}",
                f"URL: {r.url}",
            ]
            msg = "\n".join(lines)
            notify_push_channels(cfg, "❌ Toyoko Inn no longer available", msg, r.url)
            st = {"available": False, "sent": 0, "last": now}

        st["available"] = is_available
        _ALERT_STATE[key] = st


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
        cfg = _CONFIG
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
        round_tick_start = _now_mono()

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

        try:
            process_notifications(cfg, results, start, end)
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
        if _stop_event.wait(timeout=wait_s):
            break

    if isinstance(renderer, PlaywrightRenderer):
        renderer.close()
    _log("Worker loop stopped.")

# ========= Flask Application & Route =========
app = Flask(__name__)

@app.route("/")
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
    html = f"""
    <html><head><meta charset='utf-8'><title>Toyoko Inn Checker</title>
    <style>
          *{{box-sizing:border-box;}}
          html{{background:#edf3fa;}}
          body{{font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;padding:24px;max-width:1180px;margin:0 auto;background:radial-gradient(circle at 20% 0%,#ffffff 0,#f6f9fd 28%,#edf3fa 72%);color:#132033;}}
          table{{border-collapse:collapse;width:100%;margin-top:12px;}}
          th,td{{border:1px solid #ddd;padding:8px;text-align:center;}}
          th{{background:#f5f5f5;}}
          code{{background:#f6f8fa;padding:2px 4px;border-radius:4px;}}
          .mono{{font-family: ui-monospace,SFMono-Regular,Menlo,monospace;}}
          fieldset{{border:0;padding:0;margin:0 0 14px;min-width:0;}}
          fieldset > legend{{font-weight:800;color:#17324d;margin:0 0 8px;padding:0;}}
          label{{display:block;margin:6px 0 4px;font-size:14px;color:#29384c;}}
          input[type=text],input[type=number],input[type=date],input[type=password],select{{width:100%;padding:8px 10px;border:1px solid #cfd9e6;border-radius:8px;background:#fff;color:#132033;box-shadow:inset 0 1px 1px rgba(16,24,40,.03);}}
          input:focus,select:focus,textarea:focus{{outline:2px solid rgba(13,110,253,.16);border-color:#7baaf7;}}
          input[type=range]{{width:100%;height:28px;}}
          textarea{{width:100%;min-height:70px;padding:8px 10px;border:1px solid #cfd9e6;border-radius:8px;}}
          .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
          .btns{{display:flex;gap:10px;margin:12px 0;flex-wrap:wrap;justify-content:center;}}
          button{{padding:8px 14px;border:0;border-radius:10px;cursor:pointer;font-weight:700;background:#edf2f7;color:#1d2c3f;box-shadow:0 1px 2px rgba(16,24,40,.08);transition:transform .12s ease,box-shadow .12s ease,background .12s ease;}}
          button:hover{{transform:translateY(-1px);box-shadow:0 6px 16px rgba(16,24,40,.12);}}
          .primary{{background:linear-gradient(135deg,#0d6efd,#0a58ca);color:white;}}
          .danger{{background:linear-gradient(135deg,#f05b61,#d83b42);color:white;}}
          .muted{{color:#666;font-size:12px;}}
          .pill{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;}}
          .on{{background:#e6f4ea;color:#1f7a1f;}}
          .off{{background:#fbeaea;color:#a33a3a;}}
          .status{{margin-left:8px;}}
          #msg{{margin-top:8px;color:#2f6f2f;}}
          #err{{margin-top:8px;color:#a33a3a;}}
          footer{{margin-top:16px;color:#777;font-size:12px;text-align:center;}}

          /* nested setting boxes */
          .box{{background:#fafafa;border:1px solid #e5e5e5;border-radius:10px;padding:12px;margin:12px 0;}}
          .box legend{{font-size:13px;color:#555;padding:0 6px;}}
          .box .row{{grid-template-columns:1fr 1fr;gap:10px;}}
          .inline{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}}
          .help{{font-size:12px;color:#777;}}
          .topbar{{display:flex;align-items:center;justify-content:center;gap:16px;margin:0 0 18px;}}
          .topbar h2{{margin:0;text-align:center;font-size:26px;color:#132b46;letter-spacing:0;}}
          .area-toolbar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;}}
          .area-toolbar button{{padding:6px 10px;font-size:13px;}}
          .hotel-picker{{border:1px solid #e5e5e5;border-radius:8px;margin-top:10px;max-height:260px;overflow:auto;background:#fff;}}
          .hotel-picker-empty{{padding:14px;color:#777;text-align:center;font-size:13px;}}
          .hotel-item{{display:grid;grid-template-columns:auto 70px 1fr;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid #eee;text-align:left;}}
          .hotel-item:last-child{{border-bottom:0;}}
          .hotel-item label{{margin:0;display:contents;}}
          .hotel-code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#444;}}
          .hotel-name{{overflow-wrap:anywhere;}}
          .hotel-actions{{display:flex;gap:10px;align-items:center;justify-content:flex-start;}}
          .hotel-map{{white-space:nowrap;font-size:13px;}}
          .hotel-filter{{margin-top:8px;}}
          .search-panel{{background:rgba(255,255,255,.92);border:1px solid #dce7f5;border-radius:16px;padding:14px;box-shadow:0 10px 30px rgba(21,55,90,.07);}}
          .search-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px;}}
          .search-title{{font-weight:700;color:#17324d;font-size:16px;}}
          .search-subtitle{{font-size:12px;color:#667085;margin-top:2px;}}
          .search-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;}}
          .search-grid .wide{{grid-column:span 2;}}
          .control-box{{border:1px solid #e4eaf2;border-radius:12px;padding:10px;background:linear-gradient(180deg,#fff,#fbfdff);}}
          .control-box label{{margin-top:0;font-size:12px;color:#526071;}}
          .quick-actions{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}}
          .quick-actions button{{padding:6px 10px;font-size:12px;background:#eef4ff;color:#0d4f9f;}}
          .history-list{{border:1px solid #e5e5e5;border-radius:8px;background:#fff;max-height:180px;overflow:auto;margin-top:8px;}}
          .history-item{{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:8px 10px;border-bottom:1px solid #eee;}}
          .history-item:last-child{{border-bottom:0;}}
          .history-title{{font-size:13px;font-weight:600;color:#27364a;}}
          .history-meta{{font-size:12px;color:#777;margin-top:2px;}}
          .history-empty{{padding:12px;text-align:center;color:#777;font-size:13px;}}
          .history-use{{background:#0d6efd;color:#fff;padding:6px 10px;font-size:12px;white-space:nowrap;}}
          .settings-panel{{background:rgba(248,251,255,.92);border:1px solid #dce7f5;border-radius:14px;padding:14px;box-shadow:0 8px 24px rgba(21,55,90,.05);}}
          .settings-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}}
          .settings-card{{background:#fff;border:1px solid #e4eaf2;border-radius:12px;padding:12px;}}
          .settings-card h3{{font-size:14px;margin:0 0 8px;color:#17324d;}}
          .settings-card .row{{grid-template-columns:1fr 1fr;}}
          .info-title{{position:relative;display:inline-flex;align-items:center;gap:6px;cursor:help;}}
          .info-title::after{{content:'?';display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;background:#eef4ff;color:#0d4f9f;font-size:11px;font-weight:800;}}
          .info-title[data-tip]:hover::before,.info-title[data-tip]:focus::before{{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 8px);z-index:20;width:min(360px,80vw);white-space:normal;line-height:1.45;background:#132b46;color:#fff;border-radius:10px;padding:10px 12px;font-size:12px;font-weight:600;box-shadow:0 14px 34px rgba(16,24,40,.22);}}
          .info-title[data-tip]:hover::after,.info-title[data-tip]:focus::after{{background:#0d6efd;color:#fff;}}
          .settings-note{{font-size:12px;color:#667085;margin-bottom:8px;}}
          .settings-panel summary{{cursor:pointer;font-weight:700;color:#17324d;list-style:none;}}
          .settings-panel summary::-webkit-details-marker{{display:none;}}
          .settings-panel summary::before{{content:'⚙ ';}}
          details.box > summary{{cursor:pointer;font-weight:700;color:#17324d;}}
          .run-panel{{border:1px solid #cfe1f6;border-radius:18px;padding:18px;margin:18px 0;background:linear-gradient(135deg,#ffffff 0%,#f8fbff 58%,#eef6ff 100%);box-shadow:0 16px 38px rgba(21,55,90,.10);}}
          .run-top{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;}}
          .run-title{{font-size:18px;font-weight:800;color:#132b46;}}
          .run-subtitle{{font-size:12px;color:#667085;margin-top:4px;}}
          .run-actions{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;}}
          .run-actions button{{min-height:36px;padding:8px 12px;}}
          .run-actions .primary,.run-actions .danger{{min-width:88px;}}
          .status-grid{{display:grid;grid-template-columns:1.2fr 1fr 1fr 1fr;gap:10px;margin-top:14px;}}
          .metric{{border:1px solid #e0e9f5;border-radius:14px;padding:12px;background:rgba(255,255,255,.9);min-width:0;box-shadow:0 4px 14px rgba(21,55,90,.04);}}
          .metric span{{display:block;font-size:12px;color:#667085;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
          .metric b{{display:block;font-size:19px;color:#132b46;margin-top:4px;line-height:1.2;overflow-wrap:anywhere;}}
          .progress-track{{height:12px;background:#eef2f7;border-radius:999px;overflow:hidden;margin-top:14px;}}
          .progress-fill{{height:100%;width:0%;background:linear-gradient(90deg,#0d6efd,#19a7ce);border-radius:999px;transition:width .25s ease;}}
          .progress-fill.waiting{{background:linear-gradient(90deg,#f6b73c,#ffd166);}}
          .run-meta{{display:grid;grid-template-columns:1fr 1fr 1.4fr;gap:8px;margin-top:10px;color:#667085;font-size:12px;}}
          .notice{{margin-top:10px;padding:8px 10px;border-radius:8px;font-size:13px;display:none;}}
          .notice:not(:empty){{display:block;}}
          .notice.success{{background:#edf8ef;color:#246b37;border:1px solid #cfead6;}}
          .notice.error{{background:#fff1f1;color:#a33a3a;border:1px solid #f3caca;}}
          .results-panel{{margin:18px 0 0;border:1px solid #d9e5f2;border-radius:18px;background:#fff;overflow:hidden;box-shadow:0 16px 38px rgba(21,55,90,.09);}}
          .results-head{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;padding:18px;border-bottom:1px solid #edf1f5;background:linear-gradient(180deg,#fbfdff,#f6f9fd);}}
          .results-title{{font-size:18px;font-weight:800;color:#132b46;}}
          #summary-line{{margin-top:5px;color:#667085;font-size:12px;}}
          .results-summary{{display:grid;grid-template-columns:repeat(4,minmax(86px,1fr));gap:8px;min-width:390px;}}
          .result-stat{{border:1px solid #e0e9f5;border-radius:14px;padding:10px;background:#fff;text-align:center;box-shadow:0 4px 14px rgba(21,55,90,.04);}}
          .result-stat span{{display:block;font-size:11px;color:#667085;white-space:nowrap;}}
          .result-stat b{{display:block;font-size:20px;color:#132b46;margin-top:3px;}}
          .result-stat.good b{{color:#1f7a1f;}}
          .result-stat.bad b{{color:#a33a3a;}}
          .result-stat.warn b{{color:#b76a00;}}
          .results-table-wrap{{overflow:auto;}}
          table.result-table{{border-collapse:separate;border-spacing:0;width:100%;margin:0;}}
          .result-table th,.result-table td{{border:0;border-bottom:1px solid #edf1f5;padding:10px 12px;text-align:left;vertical-align:middle;}}
          .result-table th{{background:#f6f8fb;color:#27364a;font-size:13px;position:sticky;top:0;z-index:1;}}
          .result-table td{{font-size:13px;color:#27364a;}}
          .result-table tbody tr:hover{{background:#fbfdff;}}
          .hotel-cell a{{font-weight:700;color:#0d4f9f;text-decoration:none;}}
          .hotel-cell a:hover{{text-decoration:underline;}}
          .result-table td a{{color:#0d4f9f;text-decoration:none;font-weight:700;}}
          .result-table td a:hover{{text-decoration:underline;}}
          .code-cell{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#526071;white-space:nowrap;}}
          .price-cell{{font-weight:700;color:#132b46;white-space:nowrap;}}
          .price-cell div{{font-weight:500;color:#667085;font-size:12px;margin-top:2px;}}
          .center-cell{{text-align:center!important;}}
          .status-badge{{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 9px;font-weight:700;font-size:12px;white-space:nowrap;}}
          .status-badge.available{{background:#eaf7ef;color:#1f7a1f;}}
          .status-badge.unavailable{{background:#fbeaea;color:#a33a3a;}}
          .status-badge.warn{{background:#fff4df;color:#9a5a00;}}
          .status-badge.unknown{{background:#eef2f7;color:#526071;}}
          .row-available{{background:#fcfffd;}}
          .row-unavailable{{background:#fffdfd;}}
          .empty-results{{padding:26px!important;text-align:center!important;color:#777!important;font-size:14px!important;}}
          .push-status-panel{{border-top:1px solid #edf1f5;background:#fbfdff;padding:16px 18px;}}
          .push-status-head{{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:10px;}}
          .push-title{{font-weight:800;color:#132b46;font-size:15px;}}
          .push-subtitle{{font-size:12px;color:#667085;margin-top:3px;}}
          .push-grid{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;}}
          .push-card{{border:1px solid #e0e9f5;border-radius:14px;background:#fff;padding:11px;min-width:0;box-shadow:0 4px 14px rgba(21,55,90,.04);}}
          .push-name{{font-weight:800;color:#27364a;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
          .push-enabled{{font-size:11px;color:#667085;margin-top:3px;}}
          .push-chip{{display:inline-flex;align-items:center;border-radius:999px;padding:4px 9px;margin-top:9px;font-size:12px;font-weight:800;}}
          .push-chip.waiting{{background:#eef4ff;color:#0d4f9f;}}
          .push-chip.pushing{{background:#fff4df;color:#9a5a00;}}
          .push-chip.success{{background:#eaf7ef;color:#1f7a1f;}}
          .push-chip.failed{{background:#fbeaea;color:#a33a3a;}}
          .push-chip.disabled{{background:#eef2f7;color:#667085;}}
          .push-message{{font-size:11px;color:#667085;margin-top:6px;min-height:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
          @media (max-width: 720px){{
            .topbar{{display:block;}}
            .topbar h2{{text-align:left;margin-bottom:10px;}}
            .search-head{{display:block;}}
            .search-grid{{grid-template-columns:1fr;}}
            .search-grid .wide{{grid-column:auto;}}
            .settings-grid{{grid-template-columns:1fr;}}
            .run-top,.results-head{{display:block;}}
            .run-actions{{justify-content:flex-start;margin-top:12px;}}
            .status-grid{{grid-template-columns:1fr 1fr;}}
            .run-meta{{grid-template-columns:1fr;}}
            .results-summary{{grid-template-columns:1fr 1fr;min-width:0;margin-top:12px;}}
            .push-status-head{{display:block;}}
            .push-grid{{grid-template-columns:1fr;}}
            .row,.box .row{{grid-template-columns:1fr;}}
          }}
        </style></head>
        <body>
          <div class="topbar">
            <h2>{APP_NAME}</h2>
          </div>

          <fieldset>
            <legend>运行配置 Run Settings</legend>

           <fieldset class="box search-panel">
             <legend>搜索 Search</legend>
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
                 <input id='start_date' type='date' value='{cfg.start_date}'>
               </div>
               <div class="control-box">
                 <label>退房 Check-out</label>
                 <input id='end_date' type='date' value='{cfg.end_date}'>
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

             <fieldset class="box">
               <legend>区域酒店搜索 Area Hotel Picker</legend>
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
                 <button id="btn_area_all">全选 Select All</button>
                 <button id="btn_area_none">全不选 Select None</button>
                 <span class="help" id="area_status">选择大区域；详细区域可不选，默认加载整个大区域。勾选酒店后直接点击 Start 搜索。</span>
               </div>
               <input id="area_filter" class="hotel-filter" type="text" placeholder="过滤酒店中文/英文名或编号 Filter by Chinese/English hotel name or code">
               <div id="area_hotels" class="hotel-picker">
                 <div class="hotel-picker-empty">尚未加载酒店 No hotels loaded yet</div>
               </div>
             </fieldset>

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
           </fieldset>

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
                </div>

              </div>
            </details>

            <details class="box settings-panel">
              <summary>推送设定 Push Settings</summary>
              <div class="settings-note">空房、重复提醒、无房变化和启动通知会发送到所有已启用渠道。</div>
              <div class="settings-grid">
                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="控制发现空房后的重复提醒。重复提醒次数为首次提醒后的追加提醒次数；最右侧 INF 表示持续提醒。冷却时间用于避免同一酒店短时间反复推送，建议 300 秒以上。">提醒策略 Reminder Policy</h3>
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
                  <input id='bark_key' type='text' value='{getattr(cfg, "bark_key", "")}' placeholder='Bark device key'>
                  <label>Bark Server</label>
                  <input id='bark_server' type='text' value='{getattr(cfg, "bark_server", DEFAULT_BARK_SERVER)}' placeholder='https://api.day.app'>
                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="适合微信推送。步骤：1. 打开 Server 酱官网并用微信登录。2. 绑定微信推送通道。3. 在 SendKey 页面复制 SCT 开头的 SendKey。4. 粘贴到这里。5. 勾选启用后启动搜索。推送失败时请检查 SendKey、账号额度和网络连通性。">Server 酱</h3>
                  <label class="inline"><input id='enable_serverchan' type='checkbox' {'checked' if getattr(cfg, "enable_serverchan", False) else ''}> 启用 Server 酱 Enable ServerChan</label>
                  <label>SendKey</label>
                  <input id='serverchan_sendkey' type='text' value='{getattr(cfg, "serverchan_sendkey", "")}' placeholder='SCT...'>
                </div>

                <div class="settings-card">
                  <h3 class="info-title" tabindex="0" data-tip="步骤：1. 在 Telegram 搜索 BotFather。2. 使用 /newbot 创建机器人并复制 Bot Token。3. 给机器人发一条消息，或把机器人加入群组。4. 获取 Chat ID 后填入。5. 勾选启用后启动搜索。群组通常需要允许机器人发送消息。">Telegram Bot</h3>
                  <label class="inline"><input id='enable_telegram' type='checkbox' {'checked' if cfg.enable_telegram else ''}> 启用 Telegram Enable</label>
                  <label>Bot Token</label>
                  <input id='bot_token' type='text' value='{cfg.bot_token}' placeholder='BOT_TOKEN'>
                  <label>Chat ID</label>
                  <input id='chat_id' type='text' value='{cfg.chat_id}' placeholder='CHAT_ID'>
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
                      <input id='smtp_host' type='text' value='{cfg.smtp_host}' placeholder='smtp.example.com'>
                    </div>
                    <div>
                      <label>SMTP Port</label>
                      <input id='smtp_port' type='number' min='1' step='1' value='{cfg.smtp_port}'>
                    </div>
                  </div>
                  <label class="inline"><input id='smtp_tls' type='checkbox' {'checked' if cfg.smtp_tls else ''}> Use SSL / TLS</label>
                  <label>SMTP Username</label>
                  <input id='smtp_user' type='text' value='{cfg.smtp_user}' placeholder='user@example.com'>
                  <label>SMTP Password</label>
                  <input id='smtp_pass' type='password' value='{cfg.smtp_pass}' placeholder='app password'>
                  <label>From</label>
                  <input id='email_from' type='text' value='{cfg.email_from}' placeholder='sender@example.com'>
                  <label>To (comma separated)</label>
                  <input id='email_to' type='text' value='{cfg.email_to}' placeholder='a@b.com, c@d.com'>
                </div>
              </div>
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
                <div id="summary-line">
                  日期 Dates: <b>{cfg.start_date}</b> → <b>{cfg.end_date}</b> |
                  会员 Membership: <b>{current_membership_status}</b> |
                  引擎 Engine: <b>{cfg.engine}</b> |
                  酒店 Hotels: <b>{len(cfg.hotel_codes)}</b>
                </div>
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

          <footer>
            {APP_NAME} — Version: <b>{APP_VERSION}</b> · Author: <b>{APP_AUTHOR}</b>
          </footer>
        """

    html += """
          <script>
            // 防止 /status 覆盖用户正在编辑的表单
            let BLOCK_REMOTE_OVERWRITE = false;
            const EDIT_TS = {};
            function markEdited(id){ EDIT_TS[id] = Date.now(); }
            function recentlyEdited(id, ms=10000){ return EDIT_TS[id] && (Date.now() - EDIT_TS[id] < ms); }

            function renderProgress(p){
              if (!p) return;
              const total = Math.max(0, Number(p.total||0));
              const done = Math.max(0, Math.min(Number(p.done||0), total));
              const waiting = p.phase === 'waiting';
              const waitTotal = Math.max(0, Number(p.wait_total_sec || 0));
              const waitElapsed = Math.max(0, Math.min(Number(p.wait_elapsed_sec || 0), waitTotal));
              const pct = waiting && waitTotal > 0 ? Math.round(waitElapsed*100/waitTotal) : (total>0 ? Math.round(done*100/total) : 0);
              document.getElementById('round-num').textContent = String(p.round||0);
              const bar = document.getElementById('prog-bar');
              bar.style.width = pct + '%';
              bar.className = 'progress-fill' + (waiting ? ' waiting' : '');
              document.getElementById('prog-text').textContent = waiting
                ? `等待下一轮 Waiting next round: ${Math.max(0, waitTotal - waitElapsed)}s (${pct}%)`
                : `进度 Progress: ${done} / ${total} (${pct}%)`;
              const ratioEl = document.getElementById('progress-ratio');
              if (ratioEl) ratioEl.textContent = `${done} / ${total}`;
              const relH = (p && p.round_elapsed_human) ? p.round_elapsed_human : (Number(p.round_elapsed_sec||0) + 's');
              const upH  = (p && p.uptime_human) ? p.uptime_human : (Number(p.uptime_sec||0) + 's');
              document.getElementById('time-text').textContent = `耗时 Loop elapsed: ${relH} | 总耗时 Uptime: ${upH}`;
              const uptimeEl = document.getElementById('uptime-text');
              if (uptimeEl) uptimeEl.textContent = upH;
            }

            function renderSummary(cfg){
              if (!cfg) return;
              // escape helper to avoid breaking HTML while still allowing bold tags we add
              const esc = (s) => String(s).replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
              }[m]));
              const html =
                `日期 Dates: <b>${esc(cfg.start_date)}</b> → <b>${esc(cfg.end_date)}</b> | ` +
                `会员 Membership: <b>${esc(cfg.membership_status || 'member')}</b> | ` +
                `引擎 Engine: <b>${esc(cfg.engine || 'http')}</b> | ` +
                `并行 Parallel: <b>${cfg.smart_parallel_enabled ? esc(cfg.smart_parallel_workers || 1) + ' lines' : 'OFF'}</b> | ` +
                `每轮间隔 Round: <b>${esc(cfg.loop_interval_seconds || '')}s</b> | ` +
                `单店间隔 Delay: <b>${esc(cfg.per_hotel_delay_seconds || '')}s ±${esc(cfg.request_jitter_percent || 0)}%</b>`;
              const el = document.getElementById('summary-line');
              if (el) el.innerHTML = html;
            }

            function pad2(n){ return (n<10? '0':'') + n; }
            function todayStr(){ const d=new Date(); return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
            function plusOneDayStr(){ const d=new Date(); d.setDate(d.getDate()+1); return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
            function dateStrFrom(d){ return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
            function setDateRange(start, nights=1){
              const s = new Date(start);
              const e = new Date(start);
              e.setDate(e.getDate() + Math.max(1, Number(nights)||1));
              document.getElementById('start_date').value = dateStrFrom(s);
              document.getElementById('end_date').value = dateStrFrom(e);
              ['start_date','end_date'].forEach(markEdited);
              BLOCK_REMOTE_OVERWRITE = true;
            }
            function setNextWeekend(){
              const d = new Date();
              const day = d.getDay();
              let add = 0;
              if (day === 5 || day === 6 || day === 0) {
                add = 0;
              } else {
                add = (5 - day + 7) % 7;
              }
              d.setDate(d.getDate() + add);
              setDateRange(d, 1);
            }

            function selectedAreaCodes(){
              return Array.from(document.querySelectorAll('.area-hotel-check:checked')).map(el => el.value);
            }
            function selectedAreaHotels(){
              const selected = new Set(selectedAreaCodes());
              return AREA_HOTELS.filter(h => selected.has(String(h.code))).map(h => ({
                code: String(h.code || ''),
                name: h.name || '',
                name_zh: h.name_zh || '',
                name_en: h.name_en || h.name || '',
                url: h.url || '',
                map_url: h.map_url || ''
              }));
            }
            function selectedOptionText(id){
              const el = document.getElementById(id);
              if (!el || el.selectedIndex < 0) return '';
              return el.options[el.selectedIndex]?.textContent || '';
            }
            function collectPayload(){
              const selectedCodes = selectedAreaCodes();
              return {
                start_date: document.getElementById('start_date').value,
                end_date: document.getElementById('end_date').value,
                people: Number(document.getElementById('people').value),
                rooms: Number(document.getElementById('rooms').value),
                smoking: document.getElementById('smoking').value,
                room_requirement: document.getElementById('room_requirement').value,
                membership_status: document.getElementById('membership_status').value,
                hotel_codes: selectedCodes,
                hotel_codes_raw: '',
                selected_hotels: selectedAreaHotels(),
                area_region: document.getElementById('area_region') ? document.getElementById('area_region').value : '',
                area_detail: document.getElementById('area_detail') ? document.getElementById('area_detail').value : '',
                area_region_label: selectedOptionText('area_region'),
                area_detail_label: selectedOptionText('area_detail'),
                enable_telegram: document.getElementById('enable_telegram').checked,
                bot_token: document.getElementById('bot_token').value,
                chat_id: document.getElementById('chat_id').value,
                enable_bark: document.getElementById('enable_bark').checked,
                bark_key: document.getElementById('bark_key').value,
                bark_server: document.getElementById('bark_server').value,
                enable_serverchan: document.getElementById('enable_serverchan').checked,
                serverchan_sendkey: document.getElementById('serverchan_sendkey').value,
                enable_local: document.getElementById('enable_local').checked,
                enable_email: document.getElementById('enable_email').checked,
                smtp_host: document.getElementById('smtp_host').value,
                smtp_port: Number(document.getElementById('smtp_port').value),
                smtp_tls: document.getElementById('smtp_tls').checked,
                smtp_user: document.getElementById('smtp_user').value,
                smtp_pass: document.getElementById('smtp_pass').value,
                email_from: document.getElementById('email_from').value,
                email_to: document.getElementById('email_to').value,
                available_alert_repeat: Number(document.getElementById('alert_repeat').value),
                available_alert_repeat_interval_sec: Number(document.getElementById('alert_interval').value),
                loop_interval_seconds: Number(document.getElementById('loop_interval').value),
                per_hotel_delay_seconds: Number(document.getElementById('per_hotel_delay').value),
                request_jitter_percent: Number(document.getElementById('request_jitter').value),
                smart_parallel_enabled: document.getElementById('smart_parallel_enabled').checked,
                smart_parallel_workers: Number(document.getElementById('smart_parallel_workers').value),
                engine: (document.getElementById('engine') ? document.getElementById('engine').value : 'http')
              };
            }

            function setIfNotFocused(id, value){
              if (BLOCK_REMOTE_OVERWRITE) return;
              const el = document.getElementById(id);
              if (!el) return;
              if (document.activeElement === el) return;
              if (recentlyEdited(id)) return;
              if (id === 'smtp_pass') return;
              el.value = value;
            }

            ['start_date','end_date','people','rooms','smoking','room_requirement','membership_status','engine',
             'smart_parallel_enabled','smart_parallel_workers',
             'enable_telegram','bot_token','chat_id','enable_bark','bark_key','bark_server','enable_serverchan','serverchan_sendkey',
             'enable_local','enable_email','smtp_host','smtp_port','smtp_tls','smtp_user','smtp_pass','email_from','email_to',
             'alert_repeat','alert_interval','loop_interval','per_hotel_delay','request_jitter','area_region','area_detail','area_filter'
            ].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
              el.addEventListener('change', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
            });

            ['alert_repeat','alert_interval','loop_interval','per_hotel_delay','request_jitter','smart_parallel_workers'].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', syncDisplayValues);
              el.addEventListener('change', syncDisplayValues);
            });
            // Initial sync
            syncDisplayValues();
            function syncDisplayValues(){
              const ar = document.getElementById('alert_repeat');
              const ai = document.getElementById('alert_interval');
              const li = document.getElementById('loop_interval');
              const rj = document.getElementById('request_jitter');
              const spw = document.getElementById('smart_parallel_workers');
              const arv = document.getElementById('alert_repeat_val');
              const aiv = document.getElementById('alert_interval_val');
              const liv = document.getElementById('loop_interval_val');
              const phd = document.getElementById('per_hotel_delay');
              const phdv = document.getElementById('per_hotel_delay_val');
              const rjv = document.getElementById('request_jitter_val');
              const spwv = document.getElementById('smart_parallel_workers_val');
              if (ar && arv) arv.textContent = Number(ar.value) >= 11 ? 'INF' : String(ar.value);
              if (ai && aiv) aiv.textContent = String(ai.value);
              if (li && liv) liv.textContent = String(li.value);
              if (phd && phdv) phdv.textContent = String(phd.value);
              if (rj && rjv) rjv.textContent = String(rj.value);
              if (spw && spwv) spwv.textContent = String(spw.value);
            }

            let AREA_INDEX = null;
            let AREA_HOTELS = [];
            function escText(s){
              return String(s == null ? '' : s).replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
              }[m]));
            }
            function setAreaStatus(text, isError=false){
              const el = document.getElementById('area_status');
              if (!el) return;
              el.textContent = text;
              el.style.color = isError ? '#a33a3a' : '#777';
            }
            async function initAreaPicker(){
              try{
                const r = await fetch('/area_index');
                const j = await r.json();
                if (!j.ok) throw new Error('area index failed');
                AREA_INDEX = j.data || {regions: []};
                const region = document.getElementById('area_region');
                if (!region) return;
                const regions = Array.isArray(AREA_INDEX.regions) ? AREA_INDEX.regions : [];
                region.innerHTML = '<option value="">请选择 Select Region</option>' + regions.map(x =>
                  `<option value="${escText(x.id)}">${escText(x.label_zh ? x.label_zh + ' / ' + x.name : x.name)}</option>`
                ).join('');
              }catch(e){
                setAreaStatus('区域索引加载失败 Area index failed: ' + e, true);
              }
            }
            function populateAreaDetails(){
              const regionSel = document.getElementById('area_region');
              const detailSel = document.getElementById('area_detail');
              if (!regionSel || !detailSel || !AREA_INDEX) return;
              const regionId = Number(regionSel.value || 0);
              const region = (AREA_INDEX.regions || []).find(x => Number(x.id) === regionId);
              AREA_HOTELS = [];
              renderAreaHotels();
              if (!region){
                detailSel.disabled = true;
                detailSel.innerHTML = '<option value="">先选择大区域 Select a region first</option>';
              setAreaStatus('选择大区域；详细区域可不选，默认加载整个大区域。勾选酒店后直接点击 Start 搜索。');
                return;
              }
              const options = [`<option value="">全部 ${escText(region.label_zh || region.name)} / All of ${escText(region.name)}</option>`];
              const showPrefAll = (region.prefectures || []).length > 1;
              (region.prefectures || []).forEach(pref => {
                const prefLabel = pref.name_zh ? `${pref.name_zh} / ${pref.name}` : pref.name;
                if (showPrefAll) {
                  options.push(`<option value="pref-${escText(pref.id)}">全部 ${escText(prefLabel)} / All of ${escText(pref.name)}</option>`);
                }
                (pref.areas || []).forEach(area => {
                  const areaLabel = area.name_zh ? `${area.name_zh} / ${area.name}` : area.name;
                  options.push(`<option value="area-${escText(area.id)}">${escText(prefLabel)} - ${escText(areaLabel)}</option>`);
                });
              });
              detailSel.disabled = false;
              detailSel.innerHTML = options.join('');
              setAreaStatus('已选择大区域；可直接加载全部，或选择详细区域。勾选酒店后直接点击 Start 搜索。');
            }
            function renderAreaHotels(){
              const wrap = document.getElementById('area_hotels');
              const filter = (document.getElementById('area_filter')?.value || '').trim().toLowerCase();
              if (!wrap) return;
              const hotels = AREA_HOTELS.filter(h => {
                if (!filter) return true;
                return String(h.code || '').toLowerCase().includes(filter)
                  || String(h.name || '').toLowerCase().includes(filter)
                  || String(h.name_en || '').toLowerCase().includes(filter)
                  || String(h.name_zh || '').toLowerCase().includes(filter);
              });
              if (!hotels.length){
                wrap.innerHTML = '<div class="hotel-picker-empty">没有匹配酒店 No matching hotels</div>';
                return;
              }
              wrap.innerHTML = hotels.map(h => `
                <div class="hotel-item">
                  <label>
                    <input class="area-hotel-check" type="checkbox" value="${escText(h.code)}" checked>
                    <span class="hotel-code">${escText(h.code)}</span>
                    <span class="hotel-name hotel-actions">
                      <span>
                        <a href="${escText(h.url || '#')}" target="_blank" rel="noreferrer noopener">${escText(h.name_zh || h.name || '(Hotel name not found)')}</a>
                        <span class="help">${escText(h.name_en || h.name || '')}</span>
                      </span>
                      <a class="hotel-map" href="${escText(h.map_url || '#')}" target="_blank" rel="noreferrer noopener">打开地图 / Open Map</a>
                    </span>
                  </label>
                </div>
              `).join('');
            }
            async function loadAreaHotels(){
              const regionSel = document.getElementById('area_region');
              const detailSel = document.getElementById('area_detail');
              const regionId = Number(regionSel?.value || 0);
              if (!regionId){
                setAreaStatus('请先选择大区域 Please select a region first.', true);
                return;
              }
              setAreaStatus('正在加载酒店 Loading hotels...');
              try{
                const r = await fetch('/area_hotels', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({region_id: regionId, detail_id: detailSel?.value || ''})
                });
                const j = await r.json();
                if (!j.ok) throw new Error(j.error || 'load failed');
                AREA_HOTELS = Array.isArray(j.hotels) ? j.hotels : [];
                renderAreaHotels();
                setAreaStatus(`已加载 ${AREA_HOTELS.length} 家酒店 Loaded ${AREA_HOTELS.length} hotels.`);
              }catch(e){
                AREA_HOTELS = [];
                renderAreaHotels();
                setAreaStatus('酒店加载失败 Hotel loading failed: ' + e, true);
              }
            }
            function setAreaHotelChecks(checked){
              document.querySelectorAll('.area-hotel-check').forEach(el => { el.checked = checked; });
            }
            initAreaPicker();

            function historyHotelList(record){
              const hotels = Array.isArray(record.selected_hotels) ? record.selected_hotels : [];
              if (hotels.length) return hotels.map(h => ({
                code: String(h.code || ''),
                name: h.name || h.name_en || h.name_zh || '',
                name_zh: h.name_zh || '',
                name_en: h.name_en || h.name || '',
                url: h.url || `https://www.toyoko-inn.com/eng/search/detail/${String(h.code || '').padStart(5,'0')}/`,
                map_url: h.map_url || ''
              })).filter(h => h.code);
              return (Array.isArray(record.hotel_codes) ? record.hotel_codes : []).map(code => ({
                code: String(code),
                name: '',
                name_zh: '',
                name_en: '',
                url: `https://www.toyoko-inn.com/eng/search/detail/${String(code).padStart(5,'0')}/`,
                map_url: ''
              }));
            }
            function renderSearchHistory(records){
              const wrap = document.getElementById('search_history');
              if (!wrap) return;
              if (!Array.isArray(records) || records.length === 0){
                wrap.innerHTML = '<div class="history-empty">暂无搜索记录 No history yet</div>';
                return;
              }
              wrap.innerHTML = records.slice(0, 10).map((r, idx) => {
                const count = Array.isArray(r.hotel_codes) ? r.hotel_codes.length : 0;
                const region = r.area_region_label || (r.area_region ? `Region ${r.area_region}` : '未选择区域 / No region');
                const detail = r.area_detail_label || (r.area_detail ? r.area_detail : '全部区域 / All areas');
                const title = `${escText(r.start_date || '')} → ${escText(r.end_date || '')} · ${count} 家酒店 / ${count} hotels`;
                const meta = `${escText(region)} · ${escText(detail)}`;
                const params = `${escText(r.people || 1)}人 / ${escText(r.people || 1)} guest · ${escText(r.rooms || 1)}房 / ${escText(r.rooms || 1)} room · ${escText(r.smoking || 'all')} · ${escText(r.room_requirement || 'any')} · ${escText(r.membership_status || 'member')}`;
                return `<div class="history-item">
                  <div>
                    <div class="history-title">${title}</div>
                    <div class="history-meta">${meta}</div>
                    <div class="history-meta">${params}</div>
                    <div class="history-meta">${escText(r.created_at || '')}</div>
                  </div>
                  <button class="history-use" data-history-index="${idx}">调用 Use</button>
                </div>`;
              }).join('');
              wrap.querySelectorAll('[data-history-index]').forEach(btn => {
                btn.addEventListener('click', (e) => {
                  e.preventDefault();
                  const record = records[Number(btn.getAttribute('data-history-index'))];
                  applySearchHistory(record);
                });
              });
            }
            async function refreshSearchHistory(){
              try{
                const r = await fetch('/search_history');
                const j = await r.json();
                renderSearchHistory(j.records || []);
              }catch(e){
                renderSearchHistory([]);
              }
            }
            async function clearSearchHistory(){
              try{
                await fetch('/search_history/clear', {method:'POST'});
                await refreshSearchHistory();
              }catch(e){
                document.getElementById('err').textContent = String(e);
              }
            }
            function applySearchHistory(record){
              if (!record) return;
              const setValue = (id, value) => { const el = document.getElementById(id); if (el) el.value = value; };
              setValue('start_date', record.start_date || todayStr());
              setValue('end_date', record.end_date || plusOneDayStr());
              setValue('people', record.people || 1);
              setValue('rooms', record.rooms || 1);
              setValue('smoking', record.smoking || 'all');
              setValue('room_requirement', record.room_requirement || 'any');
              setValue('membership_status', record.membership_status || 'member');
              setValue('engine', record.engine || 'http');
              const parallelEl = document.getElementById('smart_parallel_enabled');
              if (parallelEl) parallelEl.checked = !!record.smart_parallel_enabled;
              setValue('smart_parallel_workers', record.smart_parallel_workers || 1);
              setValue('loop_interval', record.loop_interval_seconds || 30);
              setValue('per_hotel_delay', record.per_hotel_delay_seconds || 1);
              setValue('request_jitter', record.request_jitter_percent == null ? 40 : record.request_jitter_percent);
              setValue('alert_repeat', record.available_alert_repeat || 1);
              setValue('alert_interval', record.available_alert_repeat_interval_sec || 300);
              const region = document.getElementById('area_region');
              if (region && record.area_region) {
                region.value = record.area_region;
                populateAreaDetails();
                const detail = document.getElementById('area_detail');
                if (detail && record.area_detail) detail.value = record.area_detail;
              }
              AREA_HOTELS = historyHotelList(record);
              renderAreaHotels();
              syncDisplayValues();
              setAreaStatus(`已调用搜索记录 Loaded history: ${AREA_HOTELS.length} hotels.`);
              Object.keys(EDIT_TS).forEach(k => delete EDIT_TS[k]);
              BLOCK_REMOTE_OVERWRITE = true;
            }

            function restoreAreaFromConfig(cfg){
              if (!cfg || BLOCK_REMOTE_OVERWRITE) return;
              const hotels = Array.isArray(cfg.selected_hotels) ? cfg.selected_hotels : [];
              if (hotels.length && AREA_HOTELS.length === 0){
                const region = document.getElementById('area_region');
                if (region && cfg.area_region) {
                  region.value = cfg.area_region;
                  populateAreaDetails();
                  const detail = document.getElementById('area_detail');
                  if (detail && cfg.area_detail) detail.value = cfg.area_detail;
                }
                AREA_HOTELS = historyHotelList({
                  selected_hotels: hotels,
                  hotel_codes: cfg.hotel_codes || []
                });
                renderAreaHotels();
                setAreaStatus(`已恢复上次搜索酒店列表 Restored ${AREA_HOTELS.length} hotels from last run.`);
              }
            }

            async function callStart(){
              const payload = collectPayload();
              if (!Array.isArray(payload.hotel_codes) || payload.hotel_codes.length === 0){
                document.getElementById('err').textContent = '请先在区域酒店搜索中加载并勾选酒店。Please load and select hotels in Area Hotel Picker first.';
                document.getElementById('msg').textContent = '';
                return;
              }
              try {
                const r = await fetch('/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const j = await r.json();
                if (j.ok) {
                  document.getElementById('msg').textContent = j.restarted ? 'Restarted.' : 'Started.';
                  document.getElementById('err').textContent = '';
                  document.getElementById('running-pill').textContent = 'RUNNING 运行中';
                  document.getElementById('running-pill').className = 'pill on';
                  refreshSearchHistory();
                } else {
                  document.getElementById('err').textContent = 'Failed to start';
                  document.getElementById('msg').textContent = '';
                }
                refreshStatus();
              } catch(e) {
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              }
            }
            async function callStop(){
              try {
                const r = await fetch('/stop', {method:'POST'});
                const j = await r.json();
                if (j.ok) {
                  document.getElementById('msg').textContent = 'Stopped.';
                  document.getElementById('err').textContent = '';
                  document.getElementById('running-pill').textContent = 'STOPPED 已停止';
                  document.getElementById('running-pill').className = 'pill off';
                } else {
                  document.getElementById('err').textContent = 'Failed to stop';
                  document.getElementById('msg').textContent = '';
                }
              } catch(e) {
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              }
            }
            async function callLocalTest(){
              try{
                const payload = collectPayload();
                const r = await fetch('/local_notify_test', {
                  method:'POST',
                  headers:{'Content-Type':'application/json'},
                  body: JSON.stringify(payload)
                });
                const j = await r.json();
                if (j.ok){
                  document.getElementById('msg').textContent = 'Test notification sent. 如果没看到，请检查 macOS 通知权限。';
                  document.getElementById('err').textContent = '';
                } else {
                  document.getElementById('err').textContent = j.error || 'Test notification failed';
                  document.getElementById('msg').textContent = '';
                }
              }catch(e){
                document.getElementById('err').textContent = String(e);
                document.getElementById('msg').textContent = '';
              }
            }

            function setRunning(is){
              const pill = document.getElementById('running-pill');
              pill.textContent = is ? 'RUNNING 运行中' : 'STOPPED 已停止';
              pill.className = 'pill ' + (is ? 'on' : 'off');
            }

            function statusInfo(r, status){
                if (status === '✅' || r.available === true) return {cls:'available', row:'row-available', label:'有房 Available'};
                if (status === '❌' || r.available === false) return {cls:'unavailable', row:'row-unavailable', label:'无房 Unavailable'};
                if (status === '❗' || r.requirement_unmet) return {cls:'warn', row:'', label:'需确认 Check'};
                return {cls:'unknown', row:'', label:'未知 Unknown'};
            }

            function setResultStats(results){
                const stats = {available:0, unavailable:0, unknown:0, total:0};
                if (Array.isArray(results)){
                    results.forEach(r => {
                        stats.total += 1;
                        if (r.available === true && !r.requirement_unmet) stats.available += 1;
                        else if (r.available === false && !r.requirement_unmet) stats.unavailable += 1;
                        else stats.unknown += 1;
                    });
                }
                const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = String(val); };
                set('stat-available', stats.available);
                set('stat-unavailable', stats.unavailable);
                set('stat-unknown', stats.unknown);
                set('stat-total', stats.total);
            }

            function renderPushStatus(items){
                const grid = document.getElementById('push-status-grid');
                if (!grid) return;
                const stateLabel = {
                    waiting: '等待 Waiting',
                    pushing: '推送中 Pushing',
                    success: '推送成功 Success',
                    failed: '推送失败 Failed',
                    disabled: '未启用 Disabled'
                };
                const safe = (s) => String(s || '').replace(/[&<>"']/g, (m) => ({
                    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                }[m]));
                if (!Array.isArray(items) || items.length === 0){
                    grid.innerHTML = '<div class="push-card"><div class="push-name">暂无推送方式 No channels</div><div class="push-enabled">未配置 Not configured</div><span class="push-chip disabled">未启用 Disabled</span></div>';
                    return;
                }
                grid.innerHTML = items.map(item => {
                    const state = item.state || (item.enabled ? 'waiting' : 'disabled');
                    const enabledText = item.enabled ? '已启用 Enabled' : '未启用 Disabled';
                    const age = (typeof item.age_sec === 'number' && item.state !== 'disabled') ? ` · ${item.age_sec}s ago` : '';
                    const msg = item.message ? `${safe(item.message)}${age}` : (item.enabled ? `等待触发 Waiting${age}` : '未启用 Not enabled');
                    return `<div class="push-card">
                        <div class="push-name">${safe(item.label_zh)} <span class="muted">${safe(item.label_en)}</span></div>
                        <div class="push-enabled">${enabledText}</div>
                        <span class="push-chip ${safe(state)}">${stateLabel[state] || stateLabel.waiting}</span>
                        <div class="push-message" title="${safe(msg)}">${msg}</div>
                    </div>`;
                }).join('');
            }

            function renderRows(results){
                const tbody = document.getElementById('results-body');
                const membership = document.getElementById('membership_status')?.value || 'member';
                const safe = (s) => String(s || '').replace(/[&<>"']/g, (m) => ({
                    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                }[m]));
                const hotelNameHtml = (r) => {
                    const zh = r.name_zh || '';
                    const en = r.name_en || r.name || '(Hotel name not found)';
                    const inner = zh ? `${safe(zh)}<div class="muted">${safe(en)}</div>` : safe(en);
                    return `<a href="${safe(r.url)}" target="_blank">${inner}</a>`;
                };
                const roomTitleZh = (title) => {
                    const t = String(title || '').toLowerCase();
                    if (t.includes('economy') && t.includes('single')) return '经济单人房';
                    if (t.includes('single')) return '单人房';
                    if (t.includes('economy') && t.includes('double')) return '经济大床房';
                    if (t.includes('double')) return '大床房';
                    if (t.includes('economy') && t.includes('twin')) return '经济双床房';
                    if (t.includes('twin')) return '双床房';
                    if (t.includes('heartful') || t.includes('accessible')) return '无障碍房';
                    return '';
                };
                const roomSmokingLabel = (title, parsedSmoking) => {
                    if (parsedSmoking === 'smoking') return ' 🚬';
                    if (parsedSmoking === 'non_smoking') return ' 🚭';
                    const raw = String(title || '');
                    const t = raw.toLowerCase();
                    if (t.includes('non-smoking') || t.includes('non smoking') || t.includes('nonsmoking') || t.includes('no smoking') || raw.includes('禁煙') || raw.includes('禁烟')) {
                        return ' 🚭';
                    }
                    if (t.includes('smoking') || raw.includes('喫煙') || raw.includes('吸烟')) {
                        return ' 🚬';
                    }
                    const selectedSmoking = document.getElementById('smoking')?.value || 'all';
                    if (selectedSmoking === 'Smoking') return ' 🚬';
                    if (selectedSmoking === 'noSmoking') return ' 🚭';
                    return '';
                };
                const priceHtmlFor = (nonMemberText, memberText) => {
                    if (membership === 'member') return memberText ? `${safe(memberText)}<div>会员价 Member</div>` : `${safe(nonMemberText || '-')}<div>会员价未知 Member price unknown</div>`;
                    if (membership === 'non_member') return `${safe(nonMemberText || '-')}<div>非会员价 Non-member</div>`;
                    let out = `${safe(nonMemberText || '-')}`;
                    if (memberText) out += `<div>会员价 Member: ${safe(memberText)}</div>`;
                    return out;
                };
                const roomHtmlFor = (roomEn, roomZh, url, parsedSmoking) => {
                    if (!roomEn || String(roomEn).trim() === '-') return '-';
                    const zh = roomZh || roomTitleZh(roomEn);
                    const en = roomEn;
                    const smoke = roomSmokingLabel(roomEn, parsedSmoking);
                    const label = zh ? `${safe(zh)}${safe(smoke)}<div class="muted">${safe(en)}</div>` : `${safe(en)}${safe(smoke)}`;
                    return `<a href="${safe(url || '#')}" target="_blank">${label}</a>`;
                };
                setResultStats(results);
                if (!Array.isArray(results) || results.length === 0){
                    tbody.innerHTML = '<tr><td colspan="6" class="empty-results">暂无结果 No data yet</td></tr>';
                    return;
                }

                const rows = [];

                results.forEach(r => {
                    const nameHtml  = hotelNameHtml(r);

                    // 生成一行的帮助函数：是否显示Code/Name由首行决定
                    const addRow = (showCode, showName, status, priceHtml, leftHtml, roomHtml) => {
                        const info = statusInfo(r, status);
                        const statusHtml = status ? `<span class="status-badge ${info.cls}">${status} ${info.label}</span>` : '';
                        rows.push(
                            `<tr class="${info.row}">
                              <td class="code-cell">${showCode ? safe(r.code) : ''}</td>
                              <td class="hotel-cell">${showName ? nameHtml : ''}</td>
                              <td>${statusHtml}</td>
                              <td class="price-cell">${priceHtml}</td>
                              <td class="center-cell">${safe(leftHtml)}</td>
                              <td>${roomHtml}</td>
                            </tr>`
                        );
                    };

                    // 情况 A：要求的房型不存在 → 只渲染一行，显示❗，其余列为 "-"
                    if (r.requirement_unmet){
                        addRow(true, true, '❗', '-', '-', '-');
                        return;
                    }

                    // 情况 B：后端提供了符合条件的房型列表 → 每个房型单独一行
                    if (Array.isArray(r.offers_display) && r.offers_display.length > 0){
                        r.offers_display.forEach((o, idx) => {
                            const price = priceHtmlFor(o.price_text, o.member_price_text);
                            const left = o.remaining_norm || '-';
                            const room = roomHtmlFor(o.room_title, '', r.url, o.room_smoking || '');
                            const st   = (idx === 0 ? '✅' : '');
                            addRow(idx === 0, idx === 0, st, price, left, room);
                        });
                        return;
                    }

                    // 情况 C：回退到单值字段（兼容旧结构）
                    const status = (r.available === true ? '✅' : (r.available === false ? '❌' : '❓'));
                    const price = priceHtmlFor(r.min_price_text, r.min_member_price_text);
                    const left = r.min_remaining   || '-';
                    const room = roomHtmlFor(r.min_price_room, '', r.url);
                    addRow(true, true, status, price, left, room);
                });

                tbody.innerHTML = rows.join('');
            }

            async function refreshStatus(){
              try{
                const r = await fetch('/status');
                const j = await r.json();
                setRunning(!!j.running);
                renderProgress(j.progress);
                if (j && j.config){
                  setIfNotFocused('start_date', j.config.start_date);
                  setIfNotFocused('end_date', j.config.end_date);
                  setIfNotFocused('people', j.config.people);
                  setIfNotFocused('rooms', j.config.rooms);
                  setIfNotFocused('smoking', j.config.smoking);
                  setIfNotFocused('room_requirement', (j.config.room_requirement || j.config.om_requirement || 'any'));
                  setIfNotFocused('membership_status', j.config.membership_status || 'member');
                  setIfNotFocused('engine', j.config.engine || 'http');
                  setIfNotFocused('smart_parallel_workers', j.config.smart_parallel_workers || 1);
                  const elParallel = document.getElementById('smart_parallel_enabled');
                  if (elParallel && !recentlyEdited('smart_parallel_enabled') && !BLOCK_REMOTE_OVERWRITE) elParallel.checked = !!j.config.smart_parallel_enabled;

                  const elLocal = document.getElementById('enable_local');
                  if (elLocal && !recentlyEdited('enable_local') && !BLOCK_REMOTE_OVERWRITE) elLocal.checked = !!j.config.enable_local;

                  const elEmail = document.getElementById('enable_email');
                  if (elEmail && !recentlyEdited('enable_email') && !BLOCK_REMOTE_OVERWRITE) elEmail.checked = !!j.config.enable_email;

                  const elTg = document.getElementById('enable_telegram');
                  if (elTg && !recentlyEdited('enable_telegram') && !BLOCK_REMOTE_OVERWRITE) elTg.checked = !!j.config.enable_telegram;
                  const elBark = document.getElementById('enable_bark');
                  if (elBark && !recentlyEdited('enable_bark') && !BLOCK_REMOTE_OVERWRITE) elBark.checked = !!j.config.enable_bark;
                  const elServerChan = document.getElementById('enable_serverchan');
                  if (elServerChan && !recentlyEdited('enable_serverchan') && !BLOCK_REMOTE_OVERWRITE) elServerChan.checked = !!j.config.enable_serverchan;

                  setIfNotFocused('smtp_host', j.config.smtp_host);
                  if ('smtp_port' in j.config) setIfNotFocused('smtp_port', j.config.smtp_port);
                  const elTls = document.getElementById('smtp_tls');
                  if (elTls && !recentlyEdited('smtp_tls') && !BLOCK_REMOTE_OVERWRITE) elTls.checked = !!j.config.smtp_tls;
                  setIfNotFocused('smtp_user', j.config.smtp_user);
                  setIfNotFocused('email_from', j.config.email_from);
                  setIfNotFocused('email_to', j.config.email_to);

                  setIfNotFocused('bot_token', j.config.bot_token);
                  setIfNotFocused('chat_id', j.config.chat_id);
                  setIfNotFocused('bark_key', j.config.bark_key);
                  setIfNotFocused('bark_server', j.config.bark_server || 'https://api.day.app');
                  setIfNotFocused('serverchan_sendkey', j.config.serverchan_sendkey);

                  if ('available_alert_repeat' in j.config) setIfNotFocused('alert_repeat', j.config.available_alert_repeat);
                  if ('available_alert_repeat_interval_sec' in j.config) setIfNotFocused('alert_interval', j.config.available_alert_repeat_interval_sec);
                  if ('loop_interval_seconds' in j.config) setIfNotFocused('loop_interval', j.config.loop_interval_seconds);
                  if ('per_hotel_delay_seconds' in j.config) setIfNotFocused('per_hotel_delay', j.config.per_hotel_delay_seconds);
                  if ('request_jitter_percent' in j.config) setIfNotFocused('request_jitter', j.config.request_jitter_percent);
                  // keep numeric displays in sync
                  syncDisplayValues();
                  restoreAreaFromConfig(j.config);

                renderSummary(j.config);
              }
                renderRows(j.results || []);
                renderPushStatus(j.notification_status || []);
                const act = (j && j.action) ? j.action : '(idle)';
                const age = (j && (typeof j.action_age_sec === 'number')) ? j.action_age_sec : null;
                const actLine = '状态 Current: ' + act + (age!=null ? ` (${age}s ago)` : '');
                const actEl = document.getElementById('action-text');
                if (actEl) actEl.textContent = actLine;
              }catch(e){
                // ignore
              }
            }

            function setIfNotFocused(id, value){
              if (BLOCK_REMOTE_OVERWRITE) return;
              const el = document.getElementById(id);
              if(!el) return;
              if(document.activeElement === el) return;
              if(recentlyEdited(id)) return;
              if (id === 'smtp_pass') return;
              el.value = value;
            }

            document.getElementById('btn_start').addEventListener('click', (e)=>{e.preventDefault(); callStart();});
            document.getElementById('btn_stop').addEventListener('click', (e)=>{e.preventDefault(); callStop();});
            document.getElementById('btn_today').addEventListener('click', (e)=>{e.preventDefault(); setDateRange(new Date(), 1);});
            document.getElementById('btn_tomorrow').addEventListener('click', (e)=>{e.preventDefault(); const d=new Date(); d.setDate(d.getDate()+1); setDateRange(d, 1);});
            document.getElementById('btn_weekend').addEventListener('click', (e)=>{e.preventDefault(); setNextWeekend();});
            document.getElementById('btn_history_refresh').addEventListener('click', (e)=>{e.preventDefault(); refreshSearchHistory();});
            document.getElementById('btn_history_clear').addEventListener('click', (e)=>{e.preventDefault(); clearSearchHistory();});
            document.getElementById('btn_local_test').addEventListener('click', (e)=>{e.preventDefault(); callLocalTest();});
            const areaRegion = document.getElementById('area_region');
            if (areaRegion) areaRegion.addEventListener('change', populateAreaDetails);
            const areaDetail = document.getElementById('area_detail');
            if (areaDetail) areaDetail.addEventListener('change', ()=>{ AREA_HOTELS = []; renderAreaHotels(); });
            const areaFilter = document.getElementById('area_filter');
            if (areaFilter) areaFilter.addEventListener('input', renderAreaHotels);
            const btnAreaLoad = document.getElementById('btn_area_load');
            if (btnAreaLoad) btnAreaLoad.addEventListener('click', (e)=>{ e.preventDefault(); loadAreaHotels(); });
            const btnAreaAll = document.getElementById('btn_area_all');
            if (btnAreaAll) btnAreaAll.addEventListener('click', (e)=>{ e.preventDefault(); setAreaHotelChecks(true); });
            const btnAreaNone = document.getElementById('btn_area_none');
            if (btnAreaNone) btnAreaNone.addEventListener('click', (e)=>{ e.preventDefault(); setAreaHotelChecks(false); });
            document.getElementById('btn_default').addEventListener('click', (e)=>{e.preventDefault();
              // 恢复默认（不会立刻写磁盘）
              document.getElementById('start_date').value = todayStr();
              document.getElementById('end_date').value   = plusOneDayStr();
              document.getElementById('people').value     = 1;
              document.getElementById('rooms').value      = 1;
              document.getElementById('smoking').value    = 'all';
              document.getElementById('room_requirement').value = 'any';
              document.getElementById('membership_status').value = 'member';
              const engineEl = document.getElementById('engine');
              if (engineEl) engineEl.value = 'http';
              AREA_HOTELS = [];
              renderAreaHotels();
              ['enable_telegram','enable_local','enable_email','enable_bark','enable_serverchan','smart_parallel_enabled'].forEach(id=>{
                const c = document.getElementById(id); if (c) c.checked = false;
              });
              ['bot_token','chat_id','smtp_host','smtp_port','smtp_user','smtp_pass','email_from','email_to','bark_key','serverchan_sendkey']
                .forEach(id=>{ const el=document.getElementById(id); if (el) el.value=''; });
              document.getElementById('bark_server').value = 'https://api.day.app';
              document.getElementById('loop_interval').value = 30;
              document.getElementById('per_hotel_delay').value = 1;
              document.getElementById('request_jitter').value = 40;
              document.getElementById('smart_parallel_workers').value = 1;
              document.getElementById('alert_repeat').value = 1;
              document.getElementById('alert_interval').value = 300;
              syncDisplayValues();
              BLOCK_REMOTE_OVERWRITE = true;
            });
            refreshStatus();
            refreshSearchHistory();
            setInterval(refreshStatus, 2000);
          </script>
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


def _hotel_names_by_code(code: str, fallback: Optional[str] = None) -> Dict[str, str]:
    try:
        _load_hotel_name_index()
        row = (_HOTEL_NAME_CACHE or {}).get("by_code", {}).get(str(code).zfill(5), {})
        zh = row.get("name_full_zh_cn") or row.get("name_zh_cn") or ""
        en = row.get("name_full_en") or row.get("name_en") or fallback or ""
        display = zh and en and f"{zh} / {en}" or zh or en or fallback or ""
        return {"zh": zh, "en": en, "display": display}
    except Exception:
        return {"zh": "", "en": fallback or "", "display": fallback or ""}

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
                seen.add(code); out.append(code)
            continue
        if len(digits) == 5 and digits.isdigit():
            code = digits
            if code not in seen:
                seen.add(code); out.append(code)
            continue
        key = _normalize_name(token)
        # exact field match first
        code = exact.get(key)
        if code and code not in seen:
            seen.add(code); out.append(code)
            continue
        # substring search across concatenated names
        if key:
            for c, joined in search_list:
                if key in joined and c not in seen:
                    seen.add(c); out.append(c)
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
    resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
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
        h["name_en"] = h.get("name_en") or h.get("name") or ""
        h["name_zh"] = zh.get("name") or ""
        hotels.append(h)
    _AREA_HOTELS_CACHE[cache_key] = hotels
    return hotels


def _hotels_for_area_selection(region_id: Optional[int], detail_id: str) -> List[Dict[str, Any]]:
    selection_key, selectors = _find_area_selection(region_id, detail_id)
    cached = _AREA_HOTELS_CACHE.get(selection_key)
    if cached is not None:
        return cached
    merged: Dict[str, Dict[str, Any]] = {}
    for kind, selector_id in selectors:
        for hotel in _fetch_hotels_for_selector(kind, selector_id):
            merged.setdefault(hotel["code"], hotel)
    hotels = sorted(merged.values(), key=lambda x: x["code"])
    _AREA_HOTELS_CACHE[selection_key] = hotels
    return hotels


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
    selected_hotels = _clean_selected_hotels(payload.get("selected_hotels"))
    if selected_hotels:
        cfg.selected_hotels = selected_hotels
    elif cfg.hotel_codes:
        cfg.selected_hotels = [{"code": str(code).zfill(5)} for code in cfg.hotel_codes]

    cfg.loop_interval_seconds = _int_from_payload(payload, "loop_interval_seconds", cfg.loop_interval_seconds, 30, 3600)
    cfg.per_hotel_delay_seconds = _int_from_payload(payload, "per_hotel_delay_seconds", cfg.per_hotel_delay_seconds, 1, 60)
    cfg.request_jitter_percent = _int_from_payload(
        payload,
        "request_jitter_percent",
        getattr(cfg, "request_jitter_percent", DEFAULT_REQUEST_JITTER_PERCENT),
        0,
        100,
    )
    cfg.available_alert_repeat = _int_from_payload(payload, "available_alert_repeat", cfg.available_alert_repeat, 1, 11)
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

    for key in ("enable_telegram", "enable_local", "enable_email", "enable_bark", "enable_serverchan"):
        if key in payload:
            setattr(cfg, key, bool(payload[key]))

    for key in (
        "bot_token", "smtp_host", "smtp_user", "smtp_pass", "email_from", "email_to",
        "bark_key", "bark_server", "serverchan_sendkey",
    ):
        if key in payload:
            setattr(cfg, key, payload[key])
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


@app.route("/start", methods=["POST"])
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

        with _CONFIG_LOCK:
            _apply_payload_to_config(_CONFIG, payload)
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
        _ALERT_STATE.clear()

        _worker_thread = threading.Thread(target=_worker_loop, name="checker-thread", daemon=True)
        _worker_thread.start()
        _log("Started worker.")
        _log(f"{APP_NAME} {APP_VERSION} · Author: {APP_AUTHOR}")

        try:
            _send_start_notifications(_CONFIG)
        except Exception as e:
            _log(f"[start] could not send start notifications: {e}")

        return jsonify({"ok": True, "message": "restarted" if restarted else "started", "restarted": restarted, "config": asdict(_CONFIG)})

@app.route("/stop", methods=["POST"])
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
        return jsonify({"ok": True, "message": "stopped"})


@app.route("/local_notify_test", methods=["POST"])
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
        return jsonify({"ok": True, "message": "test notification sent", "config": asdict(_CONFIG)})

@app.route("/status")
def status() -> Response:
        with _CONFIG_LOCK:
            cfg = asdict(_CONFIG)
        with _RESULTS_LOCK:
            results = [asdict(r) for r in _LAST_RESULTS]
        with _LOG_LOCK:
            logs = list(_LOG_LINES[-300:])
        with _PROGRESS_LOCK:
            progress = dict(_PROGRESS)

        now_ts = _now_wall()
        now_mono = _now_mono()

        rs_wall = float(progress.get("round_started") or 0.0)
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
            if d: parts.append(f"{d}d")
            if h or d: parts.append(f"{h}h")
            if m or h or d: parts.append(f"{m}m")
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
            "notification_status": _notification_status_snapshot(cfg),
        })

@app.route("/area_index")
def area_index() -> Response:
        return jsonify({"ok": True, "data": _load_area_index()})


@app.route("/search_history")
def search_history() -> Response:
        return jsonify({"ok": True, "records": _load_search_history()})


@app.route("/search_history/clear", methods=["POST"])
def search_history_clear() -> Response:
        _save_search_history([])
        return jsonify({"ok": True})


@app.route("/area_hotels", methods=["POST"])
def area_hotels() -> Response:
        payload = request.get_json(force=True, silent=True) or {}
        try:
            region_id = int(payload.get("region_id"))
        except Exception:
            return jsonify({"ok": False, "error": "region_id is required"}), 400
        detail_id = str(payload.get("detail_id") or "")
        try:
            hotels = _hotels_for_area_selection(region_id, detail_id)
            return jsonify({"ok": True, "hotels": hotels, "count": len(hotels)})
        except Exception as e:
            _log(f"[area] load hotels failed: {e}")
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

# ========= Application Entry Point =========
def main() -> None:
        try:
            logging.getLogger('werkzeug').setLevel(logging.ERROR)
        except Exception:
            pass

        # Load auto_save.json Before Startup (Override Default Config if Present)
        try:
            if _load_config_with_legacy(AUTO_SAVE_PATH, LEGACY_AUTO_SAVE_PATH):
                _save_config_to_file(AUTO_SAVE_PATH)
        except Exception as e:
            _log(f"[boot] auto-load skipped: {e}")

        host = "127.0.0.1"
        port = _find_free_port(4170)
        url = f"http://{host}:{port}"

        try:
            threading.Thread(target=_open_browser_when_ready, args=(url, host, port), daemon=True).start()
        except Exception:
            pass

        app.run(host=host, port=port, debug=False)

if __name__ == "__main__":
    main()
# Ensure required imports
import os
import sys
import subprocess
