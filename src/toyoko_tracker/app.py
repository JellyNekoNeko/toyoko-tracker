from __future__ import annotations

"""
东横高手 Toyoko Inn Vacancy Tracker — Web version (Flask + Selenium, visible-UI based)

Relay：
  pip install flask selenium beautifulsoup4 webdriver-manager requests

"""

import json
import re
import time
import threading
import logging
import os
import sys
import webbrowser
import socket
import subprocess
import shutil
import queue
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

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException

# ---- precise timing helpers (monotonic) ----
def _now_wall() -> float:
    return time.time()

def _now_mono() -> float:
    return time.perf_counter()

# ---- Optional: Playwright (Driverless/Recommandation) ----
try:
    from playwright.sync_api import sync_playwright
    _HAS_PLAYWRIGHT = True
except Exception:
    _HAS_PLAYWRIGHT = False

try:
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager  # 自动下载 chromedriver（可选）
    _HAS_WDM = True
except Exception:
    _HAS_WDM = False


# ========= Version number and application metadata =========
try:
    __version__ = version("toyoko-tracker")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

APP_NAME    = "东横高手 Toyoko Inn Vacancy Tracker"
APP_AUTHOR  = "bilibili @果冻猫猫丶"
APP_VERSION = f"v{__version__}"


# ========= Constants (Configuration and Defaults)=========
DEFAULT_START_DATE = datetime.now().strftime("%Y-%m-%d")
DEFAULT_END_DATE   = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
DEFAULT_HOTEL_CODES: List[str] = [
    "00001", "00003", "00005", "00007", "00009"
]
DEFAULT_LOOP_INTERVAL_SECONDS = 30
DEFAULT_PER_HOTEL_DELAY_SECONDS = 3
DEFAULT_ROOM_REQUIREMENT = "any"  # any|single|double|twin
DEFAULT_PEOPLE = 1
DEFAULT_ROOMS = 1
DEFAULT_SMOKING = "noSmoking"
DEFAULT_AVAILABLE_ALERT_REPEAT = 0
DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC = 30
DEFAULT_BUDGET_ENABLED = False
DEFAULT_BUDGET_LIMIT = 30000  # non-member price, JPY
DEFAULT_ENABLE_TELEGRAM = False
DEFAULT_BOT_TOKEN = ""
DEFAULT_CHAT_ID = ""
DEFAULT_ENABLE_PROXY = False
DEFAULT_PROXY_URL = "http://127.0.0.1:7890"

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
BASE_DIR = os.path.dirname(__file__)
SAVE_PATH = os.path.join(BASE_DIR, SAVE_FILENAME)
AUTO_SAVE_PATH = os.path.join(BASE_DIR, AUTO_SAVE_FILENAME)

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
    people: int = DEFAULT_PEOPLE
    rooms: int = DEFAULT_ROOMS
    # Budget
    budget_enabled: bool = DEFAULT_BUDGET_ENABLED
    budget_limit: int = DEFAULT_BUDGET_LIMIT
    smoking: str = DEFAULT_SMOKING
    om_requirement: str = DEFAULT_ROOM_REQUIREMENT  # any|single|double|twin
    # Proxy
    enable_proxy: bool = DEFAULT_ENABLE_PROXY
    proxy_url: str = DEFAULT_PROXY_URL
    # Telegram
    enable_telegram: bool = DEFAULT_ENABLE_TELEGRAM
    bot_token: str = DEFAULT_BOT_TOKEN
    chat_id: str = DEFAULT_CHAT_ID
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
    # Rendering engine: "selenium" or "playwright"
    engine: str = "playwright" if _HAS_PLAYWRIGHT else "selenium"

    def __post_init__(self):
        if self.hotel_codes is None:
            self.hotel_codes = list(DEFAULT_HOTEL_CODES)


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
_CONFIG = AppConfig()
_CONFIG_LOCK = threading.Lock()

_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_driver: Optional[webdriver.Chrome] = None
_DRIVER_LOCK = threading.Lock()
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
            cfg.people = int(data.get('people', cfg.people))
            cfg.rooms = int(data.get('rooms', cfg.rooms))
            sm = str(data.get('smoking', cfg.smoking))
            if sm in {"Smoking", "noSmoking", "all"}:
                cfg.smoking = sm
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
            cfg.enable_proxy = bool(data.get('enable_proxy', cfg.enable_proxy))
            cfg.proxy_url = data.get('proxy_url', cfg.proxy_url)
            cfg.enable_telegram = bool(data.get('enable_telegram', cfg.enable_telegram))
            cfg.bot_token = data.get('bot_token', cfg.bot_token)
            cfg.chat_id = str(data.get('chat_id', cfg.chat_id))
            cfg.enable_local = bool(data.get('enable_local', cfg.enable_local))
            cfg.enable_email = bool(data.get('enable_email', cfg.enable_email))
            cfg.smtp_host = data.get('smtp_host', cfg.smtp_host)
            cfg.smtp_port = int(data.get('smtp_port', cfg.smtp_port))
            cfg.smtp_tls = bool(data.get('smtp_tls', cfg.smtp_tls))
            cfg.smtp_user = data.get('smtp_user', cfg.smtp_user)
            cfg.smtp_pass = data.get('smtp_pass', cfg.smtp_pass)
            cfg.email_from = data.get('email_from', cfg.email_from)
            cfg.email_to = data.get('email_to', cfg.email_to)
            cfg.loop_interval_seconds = int(data.get('loop_interval_seconds', cfg.loop_interval_seconds))
            cfg.per_hotel_delay_seconds = max(1, min(30, int(data.get(
                'per_hotel_delay_seconds',
                getattr(cfg, 'per_hotel_delay_seconds', DEFAULT_PER_HOTEL_DELAY_SECONDS)
            ))))
            cfg.available_alert_repeat = int(data.get('available_alert_repeat', cfg.available_alert_repeat))
            cfg.available_alert_repeat_interval_sec = int(data.get('available_alert_repeat_interval_sec', cfg.available_alert_repeat_interval_sec))
            eng = str(data.get('engine', getattr(cfg, 'engine', 'selenium')))
            if eng not in {'selenium','playwright'}:
                eng = 'selenium'
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
        _log(f"Loaded config from {path}")
        return True
    except Exception as e:
        _log(f"[error] load config from {path}: {e}")
        return False


def _save_config_to_file(path: str) -> bool:
    try:
        with _CONFIG_LOCK:
            cfg = _CONFIG
            data = {
                'start_date': cfg.start_date,
                'end_date': cfg.end_date,
                'hotel_codes': list(cfg.hotel_codes),
                'people': cfg.people,
                'rooms': cfg.rooms,
                'smoking': cfg.smoking,
                'room_requirement': getattr(cfg, 'room_requirement',
                                            getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT)),
                'enable_proxy': cfg.enable_proxy,
                'proxy_url': cfg.proxy_url,
                'enable_telegram': cfg.enable_telegram,
                'bot_token': cfg.bot_token,
                'chat_id': cfg.chat_id,
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
                'available_alert_repeat': cfg.available_alert_repeat,
                'available_alert_repeat_interval_sec': cfg.available_alert_repeat_interval_sec,
                'engine': cfg.engine,
                'budget_enabled': getattr(cfg, 'budget_enabled', DEFAULT_BUDGET_ENABLED),
                'budget_limit': getattr(cfg, 'budget_limit', DEFAULT_BUDGET_LIMIT),
            }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _log(f"Saved config to {path}")
        return True
    except Exception as e:
        _log(f"[error] save config to {path}: {e}")
        return False


# ========= Selenium/Page Parsing =========
def build_driver(cfg: AppConfig) -> webdriver.Chrome:
    _log("Launching headless Chrome...")
    _set_action("Launching headless Chrome...")
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,1600")
    opts.add_argument("--lang=en-US,en;q=0.9")
    opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    if cfg.enable_proxy and cfg.proxy_url:
        _log(f"Using proxy for Chrome: {cfg.proxy_url}")
        _set_action(f"Using proxy for Chrome: {cfg.proxy_url}")
        opts.add_argument(f"--proxy-server={cfg.proxy_url}")
    try:
        if _HAS_WDM:
            _log("Using webdriver-manager to locate ChromeDriver...")
            _set_action("Using webdriver-manager to locate ChromeDriver...")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        else:
            driver = webdriver.Chrome(options=opts)
    except WebDriverException:
        _log("[error] Failed to start ChromeDriver. Try: pip install webdriver-manager")
        raise
    driver.set_page_load_timeout(TIMEOUT)
    _set_action("ChromeDriver is ready.")
    _log("ChromeDriver is ready.")
    return driver


def build_url(cfg: AppConfig, code: str, start: str, end: str) -> str:
    return (
        f"{BASE_URL}?hotel={code}"
        f"&people={cfg.people}&room={cfg.rooms}&smoking={cfg.smoking}"
        f"&start={start}&end={end}"
    )


class RenderedPage:
    def __init__(self, soup: BeautifulSoup, visible_text: str):
        self.soup = soup
        self.visible_text = visible_text


def fetch_rendered_selenium(driver: webdriver.Chrome, url: str) -> RenderedPage:
    driver.get(url)

    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "main")))
    except Exception:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span[class*="SearchResultRoomPlanChildCard_value"]'))
        )
    except Exception:
        pass

    time.sleep(1.5)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    visible_text = driver.find_element(By.TAG_NAME, "body").text or ""
    return RenderedPage(soup, visible_text)


# ---- Playwright-based renderer ----
def fetch_rendered_playwright(cfg: AppConfig, url: str) -> RenderedPage:
    """
    Use Playwright (Chromium) to render without needing ChromeDriver.
    This runs headless and returns BeautifulSoup + visible body text, similar to Selenium path.
    """
    if not _HAS_PLAYWRIGHT:
        raise RuntimeError("Playwright is not available")
    # Launch with optional proxy and custom UA
    def _launch_args():
        args = []
        if cfg.enable_proxy and cfg.proxy_url:
            # Playwright proxy can also be provided via launch(proxy=...), but args works for http/https too
            args.append(f"--proxy-server={cfg.proxy_url}")
        args.append("--lang=en-US,en;q=0.9")
        args.append("--no-sandbox")
        args.append("--disable-dev-shm-usage")
        args.append("--disable-gpu")
        args.append("--window-size=1280,1600")
        return args

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=_launch_args())
        context = browser.new_context(user_agent=HEADERS.get("User-Agent", None), viewport={"width":1280, "height":1600})
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
        # Wait for either main or body, then for possible price value span (best-effort)
        try:
            page.wait_for_selector("main", timeout=5000)
        except Exception:
            try:
                page.wait_for_selector("body", timeout=5000)
            except Exception:
                pass
        try:
            page.wait_for_selector('span[class*="SearchResultRoomPlanChildCard_value"]', timeout=5000)
        except Exception:
            pass
        # Small settle
        try:
            page.wait_for_timeout(1200)
        except Exception:
            pass
        html = page.content()
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""
        try:
            context.close()
        finally:
            browser.close()
    soup = BeautifulSoup(html, "html.parser")
    return RenderedPage(soup, body_text)


def fetch_rendered_any(cfg: AppConfig, driver: Optional[webdriver.Chrome], url: str) -> RenderedPage:
    """
    Dispatch to Playwright or Selenium based on cfg.engine.
    """
    eng = getattr(cfg, "engine", "selenium")
    if eng == "playwright" and _HAS_PLAYWRIGHT:
        return fetch_rendered_playwright(cfg, url)
    # default to selenium
    if driver is None:
        raise RuntimeError("Selenium driver is None")
    return fetch_rendered_selenium(driver, url)


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


def extract_offers(soup: BeautifulSoup) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    """
    Extract All Sub-Cards（offer）：
      room_title, plan_name, price_text(Non-Member)、price_val、member_price_text、remaining_text/remaining_norm
    """
    offers: List[Dict[str, Any]] = []
    had_any_offer = False                 # any offer with a numeric price
    had_any_non_ignored_offer = False     # any non-ignored offer with price
    had_any_ignored_offer = False         # any ignored (heartful/accessible) offer with price

    def _extract_one_child(child, room_title):
        plan_name = None
        plan_el = child.select_one('[class*="SearchResultRoomPlanChildCard_title"]')
        if plan_el:
            plan_name = plan_el.get_text(strip=True) or None

        price_text = None
        price_val: Optional[int] = None
        member_price_text = None

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
        if not member_price_text:
            txt = child.get_text(" ", strip=True)
            m = re.search(r"Club\s*Card\s*Member\s*Price\s*(¥\s*[\d,]+)", txt, re.I)
            if m:
                member_price_text = m.group(1).strip()

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

        offers.append({
            "room_title": room_title,
            "plan_name": plan_name,
            "price_text": price_text,
            "price_val": price_val,
            "member_price_text": member_price_text,
            "remaining_text": remaining_text,
            "remaining_norm": parse_remaining(remaining_text) if remaining_text else None,
        })

    # Ordinary Parent/Child Structure
    for room_card in soup.select('div[class*="SearchResultRoomPlanParentCard_card"]'):
        room_title = None
        title_el = room_card.select_one('[class*="SearchResultRoomPlanParentCard_title"]')
        if title_el:
            room_title = title_el.get_text(strip=True)
        for child in room_card.select('div[class*="SearchResultRoomPlanChildCard_card-wrapper"]'):
            _extract_one_child(child, room_title)

    for child in soup.select('div[class*="SearchResultRoomPlanChildCard_card-wrapper"]'):
        anc = child.find_parent(attrs={"class": re.compile("SearchResultRoomPlanParentCard_card")})
        if anc:
            continue
        room_title = None
        title_parent = child.find_previous(attrs={"class": re.compile("SearchResultRoomPlanParentCard_title")})
        if title_parent:
            room_title = title_parent.get_text(strip=True)
        _extract_one_child(child, room_title)

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


def check_hotel(cfg: AppConfig, driver: Optional[webdriver.Chrome], code: str, start: str, end: str) -> HotelResult:
    url = build_url(cfg, code, start, end)
    try:
        rendered = fetch_rendered_any(cfg, driver, url)
    except Exception:
        return HotelResult(code=code, url=url, name=None, available=None)

    name = extract_hotel_name(rendered.soup)

    offers, offer_stats = extract_offers(rendered.soup)
    # ---- Room requirement filtering (single/double/twin) ----
    rr = getattr(cfg, 'room_requirement', getattr(cfg, 'om_requirement', 'any')) or 'any'
    rr = rr.lower()

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

    filtered_offers = offers
    requirement_unmet = False
    if rr in {"single", "double", "twin"}:
        filtered_offers = [o for o in offers if _room_type_of(o.get("room_title")) == rr]
        if (len(offers) > 0) and (len(filtered_offers) == 0):
            requirement_unmet = True

    # ---- Budget filtering (non-member price) ----
    budget_enabled = bool(getattr(cfg, 'budget_enabled', False))
    budget_limit = int(getattr(cfg, 'budget_limit', 30000) or 30000)
    budget_unmet = False
    if budget_enabled:
        priced = [o for o in filtered_offers if o.get("price_val") is not None]
        filtered_offers = [o for o in priced if int(o["price_val"]) <= budget_limit]
        if (len(priced) > 0) and (len(filtered_offers) == 0):
            budget_unmet = True

    if budget_unmet:
        requirement_unmet = True

    # Build display list for UI: include every matching priced offer
    # Deduplicate by room_title (case-insensitive), keeping the lowest price for each
    best_by_room: Dict[str, Dict[str, Any]] = {}
    for o in filtered_offers:
        if o.get("price_val") is None:
            continue
        title_raw = (o.get("room_title") or "").strip()
        key = title_raw.lower()
        prev = best_by_room.get(key)
        if (prev is None) or (int(o["price_val"]) < int(prev.get("price_val") or 10**12)):
            best_by_room[key] = o

    # Use only the cheapest offer per room title
    dedup_offers: List[Dict[str, Any]] = list(best_by_room.values())
    # Optional: sort by price ascending for a stable, nice UI
    dedup_offers.sort(key=lambda x: int(x.get("price_val") or 0))

    offers_display: List[Dict[str, Any]] = []
    for o in dedup_offers:
        offers_display.append({
            "price_text": o.get("price_text"),
            "member_price_text": o.get("member_price_text"),
            "remaining_norm": o.get("remaining_norm"),
            "room_title": o.get("room_title"),
        })

    offers_for_best = dedup_offers
    best = None
    for o in offers_for_best:
        if o.get("price_val") is not None:
            if best is None or int(o["price_val"]) < int(best["price_val"]):
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
            available = detect_price_available(rendered.visible_text)
        min_price = None
        min_price_text = None
        min_room = None
        min_plan = None
        min_member_price_text = None
        min_remaining = None

    return HotelResult(
        code=code,
        url=url,
        name=name,
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


# ========= Notification（Telegram/Local/Mail）=========
def _tg_enabled(cfg: AppConfig) -> bool:
    return cfg.enable_telegram and bool(cfg.bot_token) and bool(cfg.chat_id)


def notify_telegram(cfg: AppConfig, message: str) -> None:
    if not _tg_enabled(cfg):
        return
    try:
        _set_action("[tg] sending message...")
        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        payload = {"chat_id": cfg.chat_id, "text": message}
        proxies = None
        if cfg.enable_proxy and cfg.proxy_url:
            proxies = {"http": cfg.proxy_url, "https": cfg.proxy_url}
        resp = requests.post(url, data=payload, timeout=15, proxies=proxies)
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
            _log("[tg] sent OK")
        else:
            _set_action(f"[tg] failed: {err or 'unknown error'}")
            _log(f"[tg] failed: {err or 'unknown error'}")
    except Exception as e:
        _set_action(f"[tg] exception: {e}")
        _log(f"[tg] exception: {e}")


def notify_local(cfg: AppConfig, title: str, body: str) -> None:
    if not getattr(cfg, "enable_local", False):
        _log("[local] skipped: enable_local = False")
        return
    try:
        _set_action("[local] notifying...")
        # Windows consoles/toasters may not render emoji properly — sanitize to ASCII
        if os.name == "nt":
            def _sanitize_win(s: str) -> str:
                if not isinstance(s, str):
                    return s
                return (s
                        .replace("🟢", "[START]")
                        .replace("✅", "[OK]")
                        .replace("❌", "[NO]")
                        .replace("→", "->"))
            title = _sanitize_win(title)
            body = _sanitize_win(body)
        if sys.platform == "darwin":
            #  terminal-notifier
            tn = shutil.which("terminal-notifier")
            sent = False
            if tn:
                try:
                    subprocess.Popen(
                        [tn, "-title", title, "-message", body, "-group", "toyoko-inn-tracker"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    sent = True
                    _log("[local] terminal-notifier invoked")
                except Exception as _tn_e:
                    _log(f"[local] terminal-notifier failed: {_tn_e}")
            if not sent:
                script = f'display notification {json.dumps(body)} with title {json.dumps(title)}'
                try:
                    subprocess.Popen(["osascript", "-e", script],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    _log("[local] osascript notification invoked")
                except Exception as _e2:
                    _log(f"[local] osascript failed: {_e2}")
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
                _log("[local] powershell NotifyIcon balloon shown (non-blocking)")
            except Exception as _e_win_balloon:
                _log(f"[local] NotifyIcon balloon failed: {_e_win_balloon}")
        else:
            try:
                subprocess.Popen(["notify-send", title, body],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _log("[local] notify-send invoked")
            except Exception as _e4:
                _log(f"[local] notify-send failed: {_e4}")
    except Exception as e:
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
    except Exception as e:
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
        _log("[mail] queued")
    except Exception as e:
        _set_action(f"[mail] queue exception: {e}")
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
        notify_telegram(cfg, msg)
        notify_email(cfg, "🟢 Tracking started", msg)
        notify_local(cfg, "🟢 Tracking started", f"{cfg.start_date} → {cfg.end_date}\n{codes}")
        _log("[start] start notifications sent (tg/email/local where enabled)")
    except Exception as e:
        _log(f"[start] start notifications error: {e}")


def _format_offer_lines_for_push(r: HotelResult) -> List[str]:
    """
    Build multi-offer lines for notifications. Prefer r.offers_display (already filtered by budget/room requirement),
    fall back to single-offer fields if necessary.
    """
    lines: List[str] = []
    # Use all qualifying offers when present
    offers = getattr(r, "offers_display", None)
    if isinstance(offers, list) and offers:
        for o in offers:
            room = o.get("room_title") or "-"
            price = o.get("price_text") or "-"
            mp = o.get("member_price_text")
            left = o.get("remaining_norm") or "-"
            # Compose: Room | Price (Member) | Left
            if mp:
                lines.append(f"• {room} | {price} ({mp}) | Left: {left}")
            else:
                lines.append(f"• {room} | {price} | Left: {left}")
        return lines
    # Fallback to single fields (legacy)
    price = r.min_price_text or "-"
    mp = r.min_member_price_text
    room = r.min_price_room or "-"
    left = r.min_remaining or "-"
    if price and mp:
        lines.append(f"• {room} | {price} ({mp}) | Left: {left}")
    else:
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
            notify_telegram(cfg, msg)
            notify_email(cfg, "✅ Toyoko Inn Available room(s)", msg)
            notify_local(cfg, "✅ Toyoko Inn Available",
                         f"{title}\n{r.min_price_text or ''} {r.min_price_room or ''}\n{start_date} → {end_date}")
            st = {"available": True, "sent": 1, "last": now}

        elif is_available and was_available:
            max_times = max(1, int(cfg.available_alert_repeat))
            interval = max(1, int(cfg.available_alert_repeat_interval_sec))
            if st.get("sent", 0) < max_times and (now - st.get("last", 0)) >= interval:
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
                notify_telegram(cfg, msg)
                notify_email(cfg, "✅ Toyoko Inn Available room(s) — reminder", msg)
                notify_local(cfg, "✅ Available — reminder",
                             f"{title}\n{r.min_price_text or ''} {r.min_price_room or ''}\n{start_date} → {end_date}")
                st["sent"] = st.get("sent", 0) + 1
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
            notify_telegram(cfg, msg)
            notify_email(cfg, "❌ Toyoko Inn no longer available", msg)
            notify_local(cfg, "❌ No longer available", f"{title}\n{start_date} → {end_date}")
            st = {"available": False, "sent": 0, "last": now}

        st["available"] = is_available
        _ALERT_STATE[key] = st


# ========= Worker Loop =========
def _worker_loop():
    global _driver, _LAST_RESULTS, _PROGRESS, _UPTIME_STARTED, _UPTIME_STARTED_MONO
    _log("Worker loop started.")
    _set_action("Worker loop started.")
    _UPTIME_STARTED = _now_wall()
    _UPTIME_STARTED_MONO = _now_mono()
    with _CONFIG_LOCK:
        cfg = _CONFIG
        start, end = cfg.start_date, cfg.end_date

    driver = None
    if getattr(cfg, "engine", "selenium") == "selenium":
        with _DRIVER_LOCK:
            if _driver is None:
                _driver = build_driver(cfg)
        driver = _driver

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
            _PROGRESS["round_started"] = _now_wall()
            _PROGRESS["round_started_mono"] = _now_mono()
        current_round = _PROGRESS["round"]
        round_tick_start = _now_mono()

        results: List[HotelResult] = []
        for code in cfg.hotel_codes:
            if _stop_event.is_set():
                break
            _set_action(f"[search] Checking hotel {code} for {start} → {end}...")
            _log(f"[search] Checking hotel {code} for {start} → {end}...")
            try:
                result = check_hotel(cfg, driver, code, start, end)
            except Exception as e:
                _log(f"[error] check {code}: {e}")
                result = HotelResult(code=code, url=build_url(cfg, code, start, end), name=None, available=None)
            results.append(result)
            with _PROGRESS_LOCK:
                _PROGRESS["done"] = min(_PROGRESS["done"] + 1, _PROGRESS["total"])
            time.sleep(max(1, min(30, int(cfg.per_hotel_delay_seconds))))

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
        wait_s = float(max(1, int(cfg.loop_interval_seconds)))
        _set_action(f"Round {current_round} complete. Waiting {wait_s:.1f}s...")
        if _stop_event.wait(timeout=wait_s):
            break

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

    html = f"""
    <html><head><meta charset='utf-8'><title>Toyoko Inn Checker</title>
    <style>
          body{{font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;padding:20px;max-width:1100px;margin:0 auto;}}
          table{{border-collapse:collapse;width:100%;margin-top:12px;}}
          th,td{{border:1px solid #ddd;padding:8px;text-align:center;}}
          th{{background:#f5f5f5;}}
          code{{background:#f6f8fa;padding:2px 4px;border-radius:4px;}}
          .mono{{font-family: ui-monospace,SFMono-Regular,Menlo,monospace;}}
          fieldset{{border:1px solid #e5e5e5;padding:12px;margin:10px 0;border-radius:10px;}}
          legend{{font-weight:600;color:#444;}}
          label{{display:block;margin:6px 0 2px;font-size:14px;color:#333;}}
          input[type=text],input[type=number],input[type=date]{{width:100%;padding:6px 8px;border:1px solid #ccc;border-radius:6px;}}
          input[type=range]{{width:100%;height:28px;}}
          textarea{{width:100%;min-height:70px;padding:6px 8px;border:1px solid #ccc;border-radius:6px;}}
          .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
          .btns{{display:flex;gap:10px;margin:12px 0;flex-wrap:wrap;justify-content:center;}}
          button{{padding:8px 14px;border:0;border-radius:8px;cursor:pointer;font-weight:600;}}
          .primary{{background:#0d6efd;color:white;}}
          .danger{{background:#e55353;color:white;}}
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
        </style></head>
        <body>
          <h2 style="text-align:center">{APP_NAME}</h2>

          <fieldset>
            <legend>运行配置 Run Settings</legend>

           <fieldset class="box">
             <legend>搜索设定 Search</legend>

             <div class='row'>
               <div>
                 <label>入住日期 Check-in Date</label>
                 <input id='start_date' type='date' value='{cfg.start_date}'>
               </div>
               <div>
                 <label>退房日期 Check-out Date</label>
                 <input id='end_date' type='date' value='{cfg.end_date}'>
               </div>
             </div>

             <div class='row'>
               <div>
                 <label>人数 People (1-5)</label>
                 <input id='people' type='number' min='1' max='5' step='1' value='{cfg.people}'>
               </div>
               <div>
                 <label>房间数 Rooms (1-9)</label>
                 <input id='rooms' type='number' min='1' max='9' step='1' value='{cfg.rooms}'>
               </div>
             </div>

             <div class='row'>
               <div>
                 <label>无烟房需求 Smoking</label>
                 <select id='smoking'>
                   <option value='noSmoking' {'selected' if cfg.smoking == 'noSmoking' else ''}>无烟房 noSmoking</option>
                   <option value='Smoking'   {'selected' if cfg.smoking == 'Smoking' else ''}>吸烟房 Smoking</option>
                   <option value='all'       {'selected' if cfg.smoking == 'all' else ''}>不限制 all</option>
                 </select>
               </div>
             </div>
             <div>
              <label>房型需求 Room Requirement</label>
               <select id="room_requirement">
               <option value="any"   {{'selected' if getattr(cfg,'room_requirement',getattr(cfg,'om_requirement','any'))=='any' else ''}}>不限制 No Limit</option>
               <option value="single"{{'selected' if getattr(cfg,'room_requirement',getattr(cfg,'om_requirement','any'))=='single' else ''}}>单人房 Single</option>
               <option value="double"{{'selected' if getattr(cfg,'room_requirement',getattr(cfg,'om_requirement','any'))=='double' else ''}}>大床房 Double</option>
               <option value="twin"  {{'selected' if getattr(cfg,'room_requirement',getattr(cfg,'om_requirement','any'))=='twin' else ''}}>双床房 Twin</option>
              </select>
             </div>

             <label>酒店编号/名称（可混输，逗号或换行分隔） Hotel Codes or Names (mix available, comma/newline separated)</label>
             <div class='help'>支持 Support：00001 / 東横INN蒲田1 / 蒲田1 / Tokyo Kamata No.1 / 도쿄 카마타1 / 东京蒲田1号店 / 東京蒲田1號店 ... （请使用官网名字 Use Official Name）</div>
             <textarea id='hotel_codes' placeholder='e.g. 00001, 00009, 00159, Tokyo Kamata No.1, 横浜駅西口, 横浜桜木町...'>{', '.join(cfg.hotel_codes)}</textarea>
             <div style="margin-top:10px;">
               <label class="inline">
                 <input id="budget_enabled" type="checkbox" {'checked' if getattr(cfg,'budget_enabled', False) else ''}>
                 预算限制 Budget Limit (基于非会员价 non-member price)
               </label>
               <div style="margin-top:6px;">
                 <input id="budget_limit" type="range" min="0" max="30000" step="1000" value="{getattr(cfg,'budget_limit', 30000)}" style="width:100%;height:28px;">
                 <div class='help'>当前 Current: <b><span id="budget_limit_val">{getattr(cfg,'budget_limit', 30000)}</span></b> JPY</div>
               </div>
             </div>
           </fieldset>

           <fieldset class="box">
              <legend>渲染引擎 Rendering Engine</legend>
              <div class="row">
                <div>
                  <label>选择引擎 Engine</label>
                  <select id='engine'>
                    <option value='playwright' {'selected' if getattr(cfg,'engine','selenium') == 'playwright' else ''} {'disabled' if not _HAS_PLAYWRIGHT else ''}>Playwright (推荐/Recommend)</option>
                    <option value='selenium' {'selected' if getattr(cfg,'engine','selenium') == 'selenium' else ''}>Selenium (ChromeDriver)</option>
                  </select>
                  <div class='help'>首次使用 Playwright 需安装浏览器内核 (Install Chromium to use Playwright)</div>
                  <div class='help'>安装 Install: <code>playwright install chromium</code></div>
                </div>
              </div>
            </fieldset>

            <!-- Proxy box -->
            <fieldset class="box">
              <legend>代理 Proxy</legend>
              <div class="inline">
                <label><input id='enable_proxy' type='checkbox' {'checked' if cfg.enable_proxy else ''}> 启用代理 Enable Proxy</label>
              </div>
              <label>Proxy URL</label>
              <input id='proxy_url' type='text' value='{cfg.proxy_url}' placeholder='http://127.0.0.1:7890'>
              <div class='help'>当前版本某地区用户暂不需要调用代理</div>
            </fieldset>

            <!-- Notification Rules box -->
            <fieldset class="box">
              <legend>推送规则 Notification Rules</legend>
              <div class="row">
                <div>
                  <label>最大重复提醒次数 Max Repeat Count</label>
                  <input id='alert_repeat' type='range' min='0' max='99' step='1' value='{cfg.available_alert_repeat}'>
                  <div class='help'>当前 Current: <b><span id="alert_repeat_val">{cfg.available_alert_repeat}</span></b> 次 Time(s) (0 表示不重复 / 0 means no repeat)</div>
                </div>
                <div>
                  <label>最短重复提醒间隔（秒） Min Interval (seconds)</label>
                  <input id='alert_interval' type='range' min='30' max='3600' step='30' value='{cfg.available_alert_repeat_interval_sec}'>
                  <div class='help'>当前 Current: <b><span id="alert_interval_val">{cfg.available_alert_repeat_interval_sec}</span></b> 秒 sec</div>
                </div>
              </div>
              <div class="row">
                <div>
                  <label>每轮检索间隔 Loop Interval (seconds)</label>
                  <input id='loop_interval' type='range' min='5' max='3600' step='5' value='{cfg.loop_interval_seconds}'>
                  <div class='help'>当前 Current: <b><span id="loop_interval_val">{cfg.loop_interval_seconds}</span></b> 秒 sec（过短可能被网站拒绝 Too short may be blocked）</div>
                </div>
              
                 <div>
                  <label>每家酒店间隔 Per-hotel Delay (seconds)</label>
                  <input id='per_hotel_delay' type='range' min='1' max='30' step='1' value='{cfg.per_hotel_delay_seconds}'>
                  <div class='help'>当前 Current: <b><span id="per_hotel_delay_val">{cfg.per_hotel_delay_seconds}</span></b> 秒 sec</div>
               </div>
              </div>
            </fieldset>

            <!-- Telegram box -->
            <fieldset class="box">
              <legend>Telegram机器人 Telegram Bot</legend>
              <label><input id='enable_telegram' type='checkbox' {'checked' if cfg.enable_telegram else ''}> 启用Telegram机器人推送 Enable Telegram Bot Notification</label>
              <div class="row">
                <div>
                  <label>Bot Token</label>
                  <input id='bot_token' type='text' value='{cfg.bot_token}' placeholder='BOT_TOKEN'>
                </div>
                <div>
                  <label>Chat ID</label>
                  <input id='chat_id' type='text' value='{cfg.chat_id}' placeholder='CHAT_ID'>
                </div>
              </div>
            </fieldset>

            <!-- Local notification box -->
            <fieldset class="box">
              <legend>本地通知 Local Notifications</legend>
              <label class="inline"><input id='enable_local' type='checkbox' {'checked' if cfg.enable_local else ''}> 启用本地通知 Enable Local Notifications</label>
              <div class='help'><code>暂不支持MacOS (MacOS not Supported)</code></div>
            </fieldset>

            <!-- Email box -->
            <fieldset class="box">
              <legend>邮件推送 Email Notification</legend>
              <label><input id='enable_email' type='checkbox' {'checked' if cfg.enable_email else ''}> 启用邮件推送 Enable Email Notification</label>
              <div class="row">
                <div>
                  <label>SMTP服务器 SMTP Host</label>
                  <input id='smtp_host' type='text' value='{cfg.smtp_host}' placeholder='smtp.example.com'>
                </div>
                <div>
                  <label>SMTP端口 SMTP Port</label>
                  <input id='smtp_port' type='number' min='1' step='1' value='{cfg.smtp_port}'>
                </div>
              </div>
              <div class="inline" style="margin-top:6px;">
                <label><input id='smtp_tls' type='checkbox' {'checked' if cfg.smtp_tls else ''}> Use SSL / TLS</label>
              </div>
              <div class="row">
                <div>
                  <label>SMTP用户名 SMTP Username</label>
                  <input id='smtp_user' type='text' value='{cfg.smtp_user}' placeholder='user@example.com'>
                </div>
                <div>
                  <label>SMTP密码 SMTP Password</label>
                  <input id='smtp_pass' type='password' value='{cfg.smtp_pass}' placeholder='app password'>
                </div>
              </div>
              <div class="row">
                <div>
                  <label>寄件人 From</label>
                  <input id='email_from' type='text' value='{cfg.email_from}' placeholder='sender@example.com'>
                </div>
                <div>
                  <label>收件人（逗号隔开） To (comma separated)</label>
                  <input id='email_to' type='text' value='{cfg.email_to}' placeholder='a@b.com, c@d.com'>
                </div>
              </div>
            </fieldset>

            <div class='btns'>
              <button class='primary' id='btn_start'>启动 Start</button>
              <button class='danger' id='btn_stop'>停止 Stop</button>
              <button id='btn_default'>默认 Default</button>
              <button id='btn_save'>保存 Save</button>
              <button id='btn_load'>读取 Load</button>
              <button id='btn_hotel_lib_update'>酒店库更新 HotelNameLibUpdate</button>
              <span class='status'>状态 Status: <span class='pill {('on' if (_worker_thread and _worker_thread.is_alive()) else 'off')}' id='running-pill'>{('RUNNING 运行中' if (_worker_thread and _worker_thread.is_alive()) else 'STOPPED 已停止')}</span></span>
            </div>

            <div style='margin:8px 0;text-align:center'>
              <span>追踪次数 Loop: <b id='round-num'>0</b></span>
              <div style='height:10px;background:#eee;border-radius:6px;overflow:hidden;margin-top:6px;max-width:600px;margin-left:auto;margin-right:auto;'>
                <div id='prog-bar' style='height:10px;width:0%;background:#0d6efd;'></div>
              </div>
              <div class='muted' id='prog-text' style='margin-top:4px;'>追踪进度 Progress: 0 / 0</div>
              <div class='muted' id='time-text' style='margin-top:4px;'>用时 Elapsed: 0s | 总用时 Uptime: 0s</div>
              <div class='muted' id='action-text' style='margin-top:4px;'>状态 Current: (idle)</div>
            </div>
            <div id='msg'></div>
            <div id='err'></div>
          </fieldset>

          <p id="summary-line" class='muted' style="text-align:center">
            日期 Dates: <b>{cfg.start_date}</b> → <b>{cfg.end_date}</b> |
            代理 Proxy: <b>{'ON' if cfg.enable_proxy else 'OFF'}</b> |
            Tg机器人推送 Telegram: <b>{'ON' if cfg.enable_telegram else 'OFF'}</b> |
            本地推送 Local: <b>{'ON' if cfg.enable_local else 'OFF'}</b> |
            邮件推送 Email: <b>{'ON' if cfg.enable_email else 'OFF'}</b>
          </p>

          <table>
            <thead>
              <tr>
                <th style="width:120px">编号 Code</th>
                <th>酒店名 HotelName</th>
                <th style="width:100px">结果 Result</th>
                <th style="width:120px">最低价 MinPrice</th>
                <th style="width:80px">剩余 Left</th>
                <th style="width:160px">对应房型 AssocType</th>
              </tr>
            </thead>
            <tbody id='results-body'>{''.join(rows) or '<tr><td colspan=6 style="text-align:center;color:#888">(no data yet)</td></tr>'}</tbody>
          </table>

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
              const pct = total>0 ? Math.round(done*100/total) : 0;
              document.getElementById('round-num').textContent = String(p.round||0);
              document.getElementById('prog-bar').style.width = pct + '%';
              document.getElementById('prog-text').textContent = `进度 Progress: ${done} / ${total} (${pct}%)`;
              const relH = (p && p.round_elapsed_human) ? p.round_elapsed_human : (Number(p.round_elapsed_sec||0) + 's');
              const upH  = (p && p.uptime_human) ? p.uptime_human : (Number(p.uptime_sec||0) + 's');
              document.getElementById('time-text').textContent = `耗时 Loop elapsed: ${relH} | 总耗时 Uptime: ${upH}`;
            }

            function renderSummary(cfg){
              if (!cfg) return;
              // escape helper to avoid breaking HTML while still allowing bold tags we add
              const esc = (s) => String(s).replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
              }[m]));
              const on = v => (v ? 'ON' : 'OFF');
              const html =
                `日期 Dates: <b>${esc(cfg.start_date)}</b> → <b>${esc(cfg.end_date)}</b> | ` +
                `代理 Proxy: <b>${on(cfg.enable_proxy)}</b> | ` +
                `Tg机器人推送 Telegram: <b>${on(cfg.enable_telegram)}</b> | ` +
                `本地推送 Local: <b>${on(cfg.enable_local)}</b> | ` +
                `邮件推送 Email: <b>${on(cfg.enable_email)}</b>`;
              const el = document.getElementById('summary-line');
              if (el) el.innerHTML = html;
            }

            function pad2(n){ return (n<10? '0':'') + n; }
            function todayStr(){ const d=new Date(); return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }
            function plusOneDayStr(){ const d=new Date(); d.setDate(d.getDate()+1); return `${d.getFullYear()}-${pad2(d.getMonth()+1)}-${pad2(d.getDate())}`; }

            function parseCodes(s){
              return s.split(/[^0-9]+/).filter(x=>x.length>0).map(x=>x.padStart(5,'0'));
            }
            function collectPayload(){
              return {
                start_date: document.getElementById('start_date').value,
                end_date: document.getElementById('end_date').value,
                people: Number(document.getElementById('people').value),
                rooms: Number(document.getElementById('rooms').value),
                smoking: document.getElementById('smoking').value,
                room_requirement: document.getElementById('room_requirement').value,
                hotel_codes: parseCodes(document.getElementById('hotel_codes').value),
                hotel_codes_raw: document.getElementById('hotel_codes').value,
                enable_proxy: document.getElementById('enable_proxy').checked,
                proxy_url: document.getElementById('proxy_url').value,
                enable_telegram: document.getElementById('enable_telegram').checked,
                bot_token: document.getElementById('bot_token').value,
                chat_id: document.getElementById('chat_id').value,
                enable_local: document.getElementById('enable_local').checked,
                enable_email: document.getElementById('enable_email').checked,
                smtp_host: document.getElementById('smtp_host').value,
                smtp_port: Number(document.getElementById('smtp_port').value),
                smtp_tls: document.getElementById('smtp_tls').checked,
                smtp_user: document.getElementById('smtp_user').value,
                smtp_pass: document.getElementById('smtp_pass').value,
                email_from: document.getElementById('email_from').value,
                email_to: document.getElementById('email_to').value
                ,
                budget_enabled: document.getElementById('budget_enabled') ? document.getElementById('budget_enabled').checked : false,
                budget_limit: Number(document.getElementById('budget_limit') ? document.getElementById('budget_limit').value : 30000),
                available_alert_repeat: Number(document.getElementById('alert_repeat').value),
                available_alert_repeat_interval_sec: Number(document.getElementById('alert_interval').value),
                loop_interval_seconds: Number(document.getElementById('loop_interval').value),
                per_hotel_delay_seconds: Number(document.getElementById('per_hotel_delay').value),
                engine: (document.getElementById('engine') ? document.getElementById('engine').value : 'selenium')
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

            ['start_date','end_date','people','rooms','smoking','room_requirement','engine','hotel_codes',
             'enable_proxy','proxy_url','enable_telegram','bot_token','chat_id',
             'enable_local','enable_email','smtp_host','smtp_port','smtp_tls','smtp_user','smtp_pass','email_from','email_to',
             'alert_repeat','alert_interval','loop_interval','per_hotel_delay','budget_enabled','budget_limit'
            ].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
              el.addEventListener('change', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
            });

            ['alert_repeat','alert_interval','loop_interval','per_hotel_delay','budget_limit'].forEach(id=>{
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
              const arv = document.getElementById('alert_repeat_val');
              const aiv = document.getElementById('alert_interval_val');
              const liv = document.getElementById('loop_interval_val');
              const phd = document.getElementById('per_hotel_delay');
              const phdv = document.getElementById('per_hotel_delay_val');
              if (ar && arv) arv.textContent = String(ar.value);
              if (ai && aiv) aiv.textContent = String(ai.value);
              if (li && liv) liv.textContent = String(li.value);
              if (phd && phdv) phdv.textContent = String(phd.value);
              const bl  = document.getElementById('budget_limit');
              const blv = document.getElementById('budget_limit_val');
              if (bl && blv) blv.textContent = String(bl.value);
            }

            async function callSave(){
              const payload = collectPayload();
              try{
                const r = await fetch('/save', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const j = await r.json();
                if (j.ok){
                  document.getElementById('msg').textContent = 'Saved.';
                  document.getElementById('err').textContent = '';
                  BLOCK_REMOTE_OVERWRITE = false;
                } else {
                  document.getElementById('err').textContent = 'Save failed';
                  document.getElementById('msg').textContent = '';
                  setIfNotFocused('engine', j.config.engine || 'selenium');
                }
              }catch(e){
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              }
            }
            async function callLoad(){
              try{
                const r = await fetch('/load', {method:'POST'});
                const j = await r.json();
                if (j.ok){
                  Object.keys(EDIT_TS).forEach(k=>delete EDIT_TS[k]);
                  if (document.activeElement) { try { document.activeElement.blur(); } catch(_){} }
                  document.getElementById('msg').textContent = 'Loaded.';
                  document.getElementById('err').textContent = '';
                  BLOCK_REMOTE_OVERWRITE = false;
                  await refreshStatus();
                } else {
                  document.getElementById('err').textContent = '加载失败 Load failed';
                  document.getElementById('msg').textContent = '';
                }
              }catch(e){
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              }
            }
            async function callStart(){
              const payload = collectPayload();
              try {
                const r = await fetch('/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
                const j = await r.json();
                if (j.ok) {
                  document.getElementById('msg').textContent = 'Started.';
                  document.getElementById('err').textContent = '';
                  document.getElementById('running-pill').textContent = 'RUNNING 运行中';
                  document.getElementById('running-pill').className = 'pill on';
                  Object.keys(EDIT_TS).forEach(k=>delete EDIT_TS[k]);
                  BLOCK_REMOTE_OVERWRITE = false;
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
                  Object.keys(EDIT_TS).forEach(k=>delete EDIT_TS[k]);
                } else {
                  document.getElementById('err').textContent = 'Failed to stop';
                  document.getElementById('msg').textContent = '';
                }
              } catch(e) {
                document.getElementById('err').textContent = e;
                document.getElementById('msg').textContent = '';
              }
            }

            function setRunning(is){
              const pill = document.getElementById('running-pill');
              pill.textContent = is ? 'RUNNING 运行中' : 'STOPPED 已停止';
              pill.className = 'pill ' + (is ? 'on' : 'off');
            }

            function renderRows(results){
                const tbody = document.getElementById('results-body');
                if (!Array.isArray(results) || results.length === 0){
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888">(no data yet)</td></tr>';
                    return;
                }

                const rows = [];

                results.forEach(r => {
                    const hotelName = r.name || '(Hotel name not found)';
                    const nameHtml  = `<a href="${r.url}" target="_blank">${hotelName}</a>`;

                    // 生成一行的帮助函数：是否显示Code/Name由首行决定
                    const addRow = (showCode, showName, status, priceHtml, leftHtml, roomHtml) => {
                        rows.push(
                            `<tr>
                              <td>${showCode ? r.code : ''}</td>
                              <td>${showName ? nameHtml : ''}</td>
                              <td>${status}</td>
                              <td>${priceHtml}</td>
                              <td>${leftHtml}</td>
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
                            let price = o.price_text || '-';
                            if (o.member_price_text){
                                // 会员价放在第二行，用 <div> 产生换行
                                price = `${price}<div>(${o.member_price_text})</div>`;
                            }
                            const left = o.remaining_norm || '-';
                            const room = o.room_title     || '-';
                            const st   = (idx === 0 ? '✅' : '');
                            addRow(idx === 0, idx === 0, st, price, left, room);
                        });
                        return;
                    }

                    // 情况 C：回退到单值字段（兼容旧结构）
                    const status = (r.available === true ? '✅' : (r.available === false ? '❌' : '❓'));
                    let price = '-';
                    if (r.min_price_text){
                        price = r.min_price_text;
                        if (r.min_member_price_text){
                            price = `${price}<div>(${r.min_member_price_text})</div>`;
                        }
                    }
                    const left = r.min_remaining   || '-';
                    const room = r.min_price_room  || '-';
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

                  const elLocal = document.getElementById('enable_local');
                  if (elLocal && !recentlyEdited('enable_local') && !BLOCK_REMOTE_OVERWRITE) elLocal.checked = !!j.config.enable_local;

                  const elEmail = document.getElementById('enable_email');
                  if (elEmail && !recentlyEdited('enable_email') && !BLOCK_REMOTE_OVERWRITE) elEmail.checked = !!j.config.enable_email;

                  const elProxy = document.getElementById('enable_proxy');
                  if (elProxy && !recentlyEdited('enable_proxy') && !BLOCK_REMOTE_OVERWRITE) elProxy.checked = !!j.config.enable_proxy;

                  const elTg = document.getElementById('enable_telegram');
                  if (elTg && !recentlyEdited('enable_telegram') && !BLOCK_REMOTE_OVERWRITE) elTg.checked = !!j.config.enable_telegram;

                  setIfNotFocused('smtp_host', j.config.smtp_host);
                  if ('smtp_port' in j.config) setIfNotFocused('smtp_port', j.config.smtp_port);
                  const elTls = document.getElementById('smtp_tls');
                  if (elTls && !recentlyEdited('smtp_tls') && !BLOCK_REMOTE_OVERWRITE) elTls.checked = !!j.config.smtp_tls;
                  setIfNotFocused('smtp_user', j.config.smtp_user);
                  setIfNotFocused('email_from', j.config.email_from);
                  setIfNotFocused('email_to', j.config.email_to);

                  setIfNotFocused('proxy_url', j.config.proxy_url);
                  setIfNotFocused('bot_token', j.config.bot_token);
                  setIfNotFocused('chat_id', j.config.chat_id);

                  if ('available_alert_repeat' in j.config) setIfNotFocused('alert_repeat', j.config.available_alert_repeat);
                  if ('available_alert_repeat_interval_sec' in j.config) setIfNotFocused('alert_interval', j.config.available_alert_repeat_interval_sec);
                  if ('loop_interval_seconds' in j.config) setIfNotFocused('loop_interval', j.config.loop_interval_seconds);
                  if ('per_hotel_delay_seconds' in j.config) setIfNotFocused('per_hotel_delay', j.config.per_hotel_delay_seconds);
                  // keep numeric displays in sync
                  syncDisplayValues();

                  const elBE = document.getElementById('budget_enabled');
                  if (elBE && !recentlyEdited('budget_enabled') && !BLOCK_REMOTE_OVERWRITE) elBE.checked = !!j.config.budget_enabled;

                  if ('budget_limit' in j.config) setIfNotFocused('budget_limit', j.config.budget_limit);
                  const blv = document.getElementById('budget_limit_val');
                  const bl  = document.getElementById('budget_limit');
                  if (bl && blv) blv.textContent = String(bl.value);

                  const hc = document.getElementById('hotel_codes');
                  if (hc && !BLOCK_REMOTE_OVERWRITE && document.activeElement !== hc) {
                    const arr = Array.isArray(j.config.hotel_codes) ? j.config.hotel_codes : [];
                    hc.value = arr.join(', ');
                  }
                  renderSummary(j.config);
                }
                renderRows(j.results || []);
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
            document.getElementById('btn_default').addEventListener('click', (e)=>{e.preventDefault();
              // 恢复默认（不会立刻写磁盘）
              document.getElementById('start_date').value = todayStr();
              document.getElementById('end_date').value   = plusOneDayStr();
              document.getElementById('people').value     = 1;
              document.getElementById('rooms').value      = 1;
              document.getElementById('smoking').value    = 'all';
              const hc = document.getElementById('hotel_codes'); if (hc) hc.value = '';
              ['enable_proxy','enable_telegram','enable_local','enable_email'].forEach(id=>{
                const c = document.getElementById(id); if (c) c.checked = false;
              });
              ['bot_token','chat_id','smtp_host','smtp_port','smtp_user','smtp_pass','email_from','email_to','proxy_url']
                .forEach(id=>{ const el=document.getElementById(id); if (el) el.value=''; });
              BLOCK_REMOTE_OVERWRITE = true;
            });
            document.getElementById('btn_save').addEventListener('click', (e)=>{e.preventDefault(); callSave();});
            document.getElementById('btn_load').addEventListener('click', (e)=>{e.preventDefault(); callLoad();});

            // Launch hotel_scan.py in a new terminal
            async function callHotelLibUpdate(){
              try{
                const r = await fetch('/hotel_lib_update', { method: 'POST' });
                const j = await r.json();
                if (j.ok){
                  document.getElementById('msg').textContent = j.message || 'HotelNameLibUpdate started.';
                  document.getElementById('err').textContent = '';
                }else{
                  document.getElementById('err').textContent = j.error || 'HotelNameLibUpdate failed';
                  document.getElementById('msg').textContent = '';
                }
              }catch(e){
                document.getElementById('err').textContent = String(e);
                document.getElementById('msg').textContent = '';
              }
            }
            const btnHotelLibUpdate = document.getElementById('btn_hotel_lib_update');
            if (btnHotelLibUpdate){
              btnHotelLibUpdate.addEventListener('click', (e)=>{
                e.preventDefault();
                callHotelLibUpdate();
              });
            }

            refreshStatus();
            setInterval(refreshStatus, 2000);
          </script>
        </body></html>
        """
    return Response(html, mimetype="text/html")

 # ---- Hotel name → code mapping (toyoko_hotel_names.json) ----
HOTEL_NAME_JSON = os.path.join(BASE_DIR, "toyoko_hotel_names.json")
_HOTEL_NAME_CACHE = None  # type: Optional[dict]
_HOTEL_NAME_CACHE_MTIME = 0.0

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
    search_list = []
    for row in data:
        code = str(row.get("code") or "").zfill(5)
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
    _HOTEL_NAME_CACHE = {"exact": exact, "list": search_list}
    _HOTEL_NAME_CACHE_MTIME = mtime
    return exact, search_list

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


@app.route("/start", methods=["POST"])
def start() -> Response:
        global _worker_thread, _driver, _RUN_REQUESTED
        payload = request.get_json(force=True, silent=True) or {}

        # If already running, skip creating another thread
        if _worker_thread and _worker_thread.is_alive():
            return jsonify({"ok": True, "message": "already running", "config": asdict(_CONFIG)})

        with _CONFIG_LOCK:
            cfg = _CONFIG
            cfg.start_date = payload.get("start_date", cfg.start_date)
            cfg.end_date = payload.get("end_date", cfg.end_date)
            raw_codes = payload.get("hotel_codes_raw")
            if isinstance(raw_codes, str) and raw_codes.strip():
                cfg.hotel_codes = _codes_from_name_input(raw_codes)
            else:
                codes = payload.get("hotel_codes")
                if isinstance(codes, list) and all(isinstance(x, str) for x in codes):
                    cfg.hotel_codes = codes
            cfg.loop_interval_seconds = int(payload.get("loop_interval_seconds", DEFAULT_LOOP_INTERVAL_SECONDS))
            cfg.per_hotel_delay_seconds = max(1, min(30, int(payload.get(
                'per_hotel_delay_seconds',
                getattr(cfg, 'per_hotel_delay_seconds', DEFAULT_PER_HOTEL_DELAY_SECONDS)
            ))))
            p = int(payload.get("people", cfg.people))
            cfg.people = max(1, min(5, p))
            r = int(payload.get("rooms", cfg.rooms))
            cfg.rooms = max(1, min(9, r))
            sm = str(payload.get("smoking", cfg.smoking))
            if sm not in {"Smoking", "noSmoking", "all"}:
                sm = cfg.smoking
            cfg.smoking = sm
            if "budget_enabled" in payload:
                try:
                    cfg.budget_enabled = bool(payload.get("budget_enabled"))
                except Exception:
                    cfg.budget_enabled = False
            if "budget_limit" in payload:
                try:
                    cfg.budget_limit = int(payload.get("budget_limit"))
                except Exception:
                    cfg.budget_limit = DEFAULT_BUDGET_LIMIT
            rr = str(payload.get(
                "room_requirement",
                getattr(cfg, 'room_requirement', getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT))
            ))
            if rr not in {"any", "single", "double", "twin"}:
                rr = getattr(cfg, 'room_requirement', getattr(cfg, 'om_requirement', DEFAULT_ROOM_REQUIREMENT))
            setattr(cfg, 'room_requirement', rr)
            setattr(cfg, 'om_requirement', rr)
            if "room_requirement" in payload:
                rr = str(payload["room_requirement"])
                if rr in {"any", "single", "double", "twin"}:
                    setattr(cfg, 'room_requirement', rr)
                    setattr(cfg, 'om_requirement', rr)
            cfg.enable_proxy = bool(payload.get("enable_proxy", cfg.enable_proxy))
            cfg.proxy_url = payload.get("proxy_url", cfg.proxy_url)
            cfg.enable_telegram = bool(payload.get("enable_telegram", cfg.enable_telegram))
            cfg.bot_token = payload.get("bot_token", cfg.bot_token)
            cfg.chat_id = str(payload.get("chat_id", cfg.chat_id))
            cfg.enable_local = bool(payload.get("enable_local", cfg.enable_local))
            cfg.enable_email = bool(payload.get("enable_email", cfg.enable_email))
            cfg.smtp_host = payload.get("smtp_host", cfg.smtp_host)
            if "smtp_port" in payload:
                try:
                    cfg.smtp_port = int(payload.get("smtp_port", cfg.smtp_port))
                except Exception:
                    pass
            cfg.smtp_tls = bool(payload.get("smtp_tls", cfg.smtp_tls))
            cfg.smtp_user = payload.get("smtp_user", cfg.smtp_user)
            if "smtp_pass" in payload:
                cfg.smtp_pass = payload.get("smtp_pass", cfg.smtp_pass)
            cfg.email_from = payload.get("email_from", cfg.email_from)
            cfg.email_to = payload.get("email_to", cfg.email_to)
            cfg.available_alert_repeat = int(payload.get("available_alert_repeat", DEFAULT_AVAILABLE_ALERT_REPEAT))
            cfg.available_alert_repeat_interval_sec = int(
                payload.get("available_alert_repeat_interval_sec", DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC))
            eng = str(payload.get("engine", cfg.engine))
            if eng not in {"selenium", "playwright"}:
                eng = cfg.engine
            # If user picked playwright but it's not installed, fallback silently to selenium
            if eng == "playwright" and not _HAS_PLAYWRIGHT:
                eng = "selenium"
            cfg.engine = eng

        # Mark that user explicitly wants the worker to run
        _RUN_REQUESTED = True

        # Start save to auto_save.json
        _save_config_to_file(AUTO_SAVE_PATH)

        # Reset and Restart worker
        _set_action(
            f"[start] hotels={len(_CONFIG.hotel_codes)} | {_CONFIG.start_date} → {_CONFIG.end_date} | people={_CONFIG.people}, rooms={_CONFIG.rooms}, smoking={_CONFIG.smoking}")

        _stop_event.set()
        if _worker_thread and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        _stop_event.clear()

        with _DRIVER_LOCK:
            if _driver is not None:
                try:
                    _driver.quit()
                except Exception:
                    pass
                _driver = None

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

        return jsonify({"ok": True, "message": "started", "config": asdict(_CONFIG)})

@app.route("/stop", methods=["POST"])
def stop() -> Response:
        global _worker_thread, _RUN_REQUESTED
        _RUN_REQUESTED = False  # prevent worker from continuing or restarting
        _stop_event.set()
        if _worker_thread and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        _worker_thread = None
        with _DRIVER_LOCK:
            global _driver
            if _driver is not None:
                try:
                    _driver.quit()
                except Exception:
                    pass
                _driver = None
        with _PROGRESS_LOCK:
            _PROGRESS["round"] = 0
            _PROGRESS["done"] = 0
            _PROGRESS["total"] = 0
            _PROGRESS["round_started"] = 0.0
            _PROGRESS["round_started_mono"] = 0.0
        global _UPTIME_STARTED, _UPTIME_STARTED_MONO
        _UPTIME_STARTED = None
        _UPTIME_STARTED_MONO = None
        _set_action("Stopped worker.")
        _log("Stopped worker.")
        return jsonify({"ok": True, "message": "stopped"})

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
        })

@app.route("/save", methods=["POST"])
def save() -> Response:
    payload = request.get_json(force=True, silent=True) or {}
    with _CONFIG_LOCK:
        cfg = _CONFIG
        cfg.start_date = payload.get("start_date", cfg.start_date)
        cfg.end_date = payload.get("end_date", cfg.end_date)
        raw_codes = payload.get("hotel_codes_raw")
        if isinstance(raw_codes, str) and raw_codes.strip():
            cfg.hotel_codes = _codes_from_name_input(raw_codes)
        else:
            codes = payload.get("hotel_codes")
            if isinstance(codes, list) and all(isinstance(x, str) for x in codes):
                cfg.hotel_codes = codes

        if "people" in payload:
            cfg.people = max(1, min(5, int(payload["people"])))
        if "rooms" in payload:
            cfg.rooms = max(1, min(9, int(payload["rooms"])))
        sm = payload.get("smoking")
        if isinstance(sm, str) and sm in {"Smoking", "noSmoking", "all"}:
            cfg.smoking = sm

        # Budget
        if "budget_enabled" in payload:
            try:
                cfg.budget_enabled = bool(payload["budget_enabled"])
            except Exception:
                pass
        if "budget_limit" in payload:
            try:
                cfg.budget_limit = int(payload["budget_limit"])
            except Exception:
                pass

        if "enable_proxy" in payload:
            cfg.enable_proxy = bool(payload["enable_proxy"])
        if "proxy_url" in payload:
            cfg.proxy_url = payload["proxy_url"]

        if "enable_telegram" in payload:
            cfg.enable_telegram = bool(payload["enable_telegram"])
        if "bot_token" in payload:
            cfg.bot_token = payload["bot_token"]
        if "chat_id" in payload:
            cfg.chat_id = str(payload["chat_id"])

        if "enable_local" in payload:
            cfg.enable_local = bool(payload["enable_local"])
        if "enable_email" in payload:
            cfg.enable_email = bool(payload["enable_email"])
        if "smtp_host" in payload:
            cfg.smtp_host = payload["smtp_host"]
        if "smtp_port" in payload:
            try:
                cfg.smtp_port = int(payload["smtp_port"])
            except Exception:
                pass
        if "smtp_tls" in payload:
            cfg.smtp_tls = bool(payload["smtp_tls"])
        if "smtp_user" in payload:
            cfg.smtp_user = payload["smtp_user"]
        if "smtp_pass" in payload:
            cfg.smtp_pass = payload["smtp_pass"]
        if "email_from" in payload:
            cfg.email_from = payload["email_from"]
        if "email_to" in payload:
            cfg.email_to = payload["email_to"]

        if "engine" in payload:
            eng = str(payload["engine"])
            if eng in {"selenium", "playwright"}:
                if eng == "playwright" and not _HAS_PLAYWRIGHT:
                    eng = "selenium"
                cfg.engine = eng

        if "per_hotel_delay_seconds" in payload:
            try:
                cfg.per_hotel_delay_seconds = max(1, min(30, int(payload["per_hotel_delay_seconds"])))
            except Exception:
                pass

    ok = _save_config_to_file(SAVE_PATH)
    return jsonify({"ok": ok, "path": SAVE_PATH})

@app.route("/load", methods=["POST"])
def load() -> Response:
        ok = _load_config_from_file(SAVE_PATH)
        with _CONFIG_LOCK:
            cfg = asdict(_CONFIG)
        return jsonify({"ok": ok, "config": cfg, "path": SAVE_PATH})

# ---- HotelNameLibUpdate endpoint ----
@app.route("/hotel_lib_update", methods=["POST"])
def hotel_lib_update() -> Response:
        try:
            _launch_terminal_for_hotel_scan()
            return jsonify({"ok": True, "message": "HotelNameLibUpdate started in a new terminal"})
        except Exception as e:
            _log(f"[hotel_lib_update] failed: {e}")
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
            _load_config_from_file(AUTO_SAVE_PATH)
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