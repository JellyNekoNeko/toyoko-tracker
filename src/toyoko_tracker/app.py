from __future__ import annotations

"""
Toyoko Inn Vacancy Tracker — Web version (Flask + Selenium, visible-UI based)

Relay：
  pip install flask selenium beautifulsoup4 webdriver-manager requests

（Optional）Windows Local Notification：
  pip install win10toast
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

APP_NAME    = "Toyoko Inn Vacancy Tracker"
APP_AUTHOR  = "bilibili @果冻猫猫丶"
APP_VERSION = f"v{__version__}"


# ========= Constants (Configuration and Defaults)=========
DEFAULT_START_DATE = "2025-10-11"
DEFAULT_END_DATE   = "2025-10-12"
DEFAULT_HOTEL_CODES: List[str] = [
    "00061", "00051", "00159", "00357", "00182", "00050",
    "00120", "00075", "00073", "00901", "00340", "00353",
]
DEFAULT_LOOP_INTERVAL_SECONDS = 15
DEFAULT_PEOPLE = 1
DEFAULT_ROOMS = 1
DEFAULT_SMOKING = "noSmoking"
DEFAULT_AVAILABLE_ALERT_REPEAT = 1
DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC = 1
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
DEFAULT_SMTP_PORT = 587       # 587=STARTTLS; 465=SSL
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


@dataclass
class AppConfig:
    start_date: str = DEFAULT_START_DATE
    end_date: str = DEFAULT_END_DATE
    hotel_codes: List[str] = None
    loop_interval_seconds: int = DEFAULT_LOOP_INTERVAL_SECONDS
    people: int = DEFAULT_PEOPLE
    rooms: int = DEFAULT_ROOMS
    smoking: str = DEFAULT_SMOKING
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

    def __post_init__(self):
        if self.hotel_codes is None:
            self.hotel_codes = list(DEFAULT_HOTEL_CODES)


# ========= Global Status =========
_ALERT_STATE: Dict[str, Dict[str, Any]] = {}
_LOG_LINES: List[str] = []
_LOG_LOCK = threading.Lock()
_LAST_RESULTS: List[HotelResult] = []
_RESULTS_LOCK = threading.Lock()
_START_TIME = time.time()
_PROGRESS = {"round": 0, "done": 0, "total": 0, "round_started": 0.0}
_UPTIME_STARTED: Optional[float] = None
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
            cfg.available_alert_repeat = int(data.get('available_alert_repeat', cfg.available_alert_repeat))
            cfg.available_alert_repeat_interval_sec = int(data.get('available_alert_repeat_interval_sec', cfg.available_alert_repeat_interval_sec))
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
                'available_alert_repeat': cfg.available_alert_repeat,
                'available_alert_repeat_interval_sec': cfg.available_alert_repeat_interval_sec,
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


def fetch_rendered(driver: webdriver.Chrome, url: str) -> RenderedPage:
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


def extract_offers(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Extract All Sub-Cards（offer）：
      room_title, plan_name, price_text(Non-Member)、price_val、member_price_text、remaining_text/remaining_norm
    """
    offers: List[Dict[str, Any]] = []

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

        if _is_ignored_room(room_title):
            return

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

    return offers


def detect_price_available(visible_text: str) -> bool:
    text = " ".join(visible_text.split())
    if re.search(r"¥\s*\d", text):
        return True
    if re.search(r"\b\d{1,3}(?:,\d{3})+\b", text):
        return True
    return False


def check_hotel(cfg: AppConfig, driver: webdriver.Chrome, code: str, start: str, end: str) -> HotelResult:
    url = build_url(cfg, code, start, end)
    try:
        rendered = fetch_rendered(driver, url)
    except Exception:
        return HotelResult(code=code, url=url, name=None, available=None)

    name = extract_hotel_name(rendered.soup)

    offers = extract_offers(rendered.soup)
    best = None
    for o in offers:
        if o.get("price_val") is not None:
            if best is None or int(o["price_val"]) < int(best["price_val"]):
                best = o

    if best:
        available = True
        min_price = int(best["price_val"])
        min_price_text = best.get("price_text")
        min_room = best.get("room_title")
        min_plan = best.get("plan_name")
        min_member_price_text = best.get("member_price_text")
        min_remaining = best.get("remaining_norm")
    else:
        min_price = None
        min_price_text = None
        min_room = None
        min_plan = None
        min_member_price_text = None
        min_remaining = None
        available = detect_price_available(rendered.visible_text)

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
            try:
                from win10toast import ToastNotifier  # type: ignore
                toaster = ToastNotifier()
                toaster.show_toast(title, body, duration=5, threaded=True)
                _log("[local] win10toast invoked")
            except Exception:
                ps_cmd = (
                    "$t={title};$m={body};"
                    "[void][Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                    "[System.Windows.Forms.MessageBox]::Show($m,$t)"
                ).format(title=json.dumps(title), body=json.dumps(body))
                try:
                    subprocess.Popen(
                        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    _log("[local] powershell MessageBox fallback invoked")
                except Exception as _e3:
                    _log(f"[local] powershell fallback failed: {_e3}")
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


def notify_email(cfg: AppConfig, subject: str, body: str) -> None:
    if not _email_enabled(cfg):
        return
    try:
        _set_action("[mail] sending message...")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg.email_from
        tos = [x.strip() for x in str(cfg.email_to).split(",") if x.strip()]
        msg["To"] = ", ".join(tos) if tos else cfg.email_to
        msg.set_content(body)

        host = cfg.smtp_host
        port = int(cfg.smtp_port)

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            if cfg.smtp_tls:
                try:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                except Exception:
                    pass

        if cfg.smtp_user and cfg.smtp_pass:
            server.login(cfg.smtp_user, cfg.smtp_pass)
        server.send_message(msg)
        try:
            server.quit()
        except Exception:
            server.close()

        _set_action("[mail] sent OK")
        _log("[mail] sent OK")
    except Exception as e:
        _set_action(f"[mail] exception: {e}")
        _log(f"[mail] exception: {e}")


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


def process_notifications(cfg: AppConfig, results: List[HotelResult], start_date: str, end_date: str) -> None:
    for r in results:
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
                f"Room: {r.min_price_room or '(unknown)'}",
                f"Plan: {r.min_price_plan or '(unknown)'}",
                f"Price (non-member): {r.min_price_text or '(unknown)'}",
                f"Member price: {r.min_member_price_text or '(unknown)'}",
                f"Rooms left: {r.min_remaining or '(unknown)'}",
                f"URL: {r.url}",
            ]
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
                    f"Room: {r.min_price_room or '(unknown)'}",
                    f"Plan: {r.min_price_plan or '(unknown)'}",
                    f"Price (non-member): {r.min_price_text or '(unknown)'}",
                    f"Member price: {r.min_member_price_text or '(unknown)'}",
                    f"Rooms left: {r.min_remaining or '(unknown)'}",
                    f"URL: {r.url}",
                ]
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
    global _driver, _LAST_RESULTS, _PROGRESS, _UPTIME_STARTED
    _log("Worker loop started.")
    _set_action("Worker loop started.")
    _UPTIME_STARTED = time.time()
    with _CONFIG_LOCK:
        cfg = _CONFIG
        start, end = cfg.start_date, cfg.end_date

    with _DRIVER_LOCK:
        if _driver is None:
            _driver = build_driver(cfg)
    driver = _driver

    while not _stop_event.is_set():
        with _PROGRESS_LOCK:
            _PROGRESS["round"] += 1
            _PROGRESS["done"] = 0
            _PROGRESS["total"] = len(cfg.hotel_codes)
            _PROGRESS["round_started"] = time.time()
        current_round = _PROGRESS["round"]

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
            time.sleep(2)

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

        _set_action(f"Round {current_round} complete. Sleeping {max(1, int(cfg.loop_interval_seconds))}s...")
        if _stop_event.wait(timeout=max(1, int(cfg.loop_interval_seconds))):
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
        status = "✅" if r.available else ("❌" if r.available is False else "❓")
        price = r.min_price_text or "-"
        left = r.min_remaining or "-"
        room = r.min_price_room or "-"
        rows.append(
            f"<tr>"
            f"<td>{r.code}</td>"
            f"<td>{(r.name or '(Hotel name not found)')}</td>"
            f"<td>{status}</td>"
            f"<td>{price}</td>"
            f"<td>{left}</td>"
            f"<td>{room}</td>"
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
                  <option value='noSmoking' {'selected' if cfg.smoking == 'noSmoking' else ''}>noSmoking</option>
                  <option value='Smoking'   {'selected' if cfg.smoking == 'Smoking' else ''}>Smoking</option>
                  <option value='all'       {'selected' if cfg.smoking == 'all' else ''}>all</option>
                </select>
              </div>
            </div>

            <label>酒店编号（5位用空格或逗号隔开） Hotel Codes (5-digit, comma or space separated)</label>
            <textarea id='hotel_codes' placeholder='e.g. 00061 00159 00357'>{', '.join(cfg.hotel_codes)}</textarea>

            <!-- Proxy box -->
            <fieldset class="box">
              <legend>代理 Proxy</legend>
              <div class="inline">
                <label><input id='enable_proxy' type='checkbox' {'checked' if cfg.enable_proxy else ''}> 启用代理 Enable Proxy</label>
              </div>
              <label>Proxy URL</label>
              <input id='proxy_url' type='text' value='{cfg.proxy_url}' placeholder='http://127.0.0.1:7890'>
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
            </fieldset>

            <!-- Email box -->
            <fieldset class="box">
              <legend>邮件推送 Email Notification</legend>
              <label><input id='enable_email' type='checkbox' {'checked' if cfg.enable_email else ''}> 启用邮件推送 Enable Email Notification</label>
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
              <div class="inline" style="margin-top:6px;">
                <label><input id='smtp_tls' type='checkbox' {'checked' if cfg.smtp_tls else ''}> Use SSL / TLS</label>
              </div>
              <div class="row">
                <div>
                  <label>SMTP Username</label>
                  <input id='smtp_user' type='text' value='{cfg.smtp_user}' placeholder='user@example.com'>
                </div>
                <div>
                  <label>SMTP Password</label>
                  <input id='smtp_pass' type='password' value='{cfg.smtp_pass}' placeholder='app password'>
                </div>
              </div>
              <div class="row">
                <div>
                  <label>From</label>
                  <input id='email_from' type='text' value='{cfg.email_from}' placeholder='sender@example.com'>
                </div>
                <div>
                  <label>To (comma separated)</label>
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
              <span class='status'>状态 Status: <span class='pill {('on' if (_worker_thread and _worker_thread.is_alive()) else 'off')}' id='running-pill'>{('RUNNING 运行中' if (_worker_thread and _worker_thread.is_alive()) else 'STOPPED 已停止')}</span></span>
            </div>

            <div style='margin:8px 0;text-align:center'>
              <span>追踪次数 Round: <b id='round-num'>0</b></span>
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

          <p class='muted' style="text-align:center">
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
              document.getElementById('prog-text').textContent = `Progress: ${done} / ${total} (${pct}%)`;
              const relH = (p && p.round_elapsed_human) ? p.round_elapsed_human : (Number(p.round_elapsed_sec||0) + 's');
              const upH  = (p && p.uptime_human) ? p.uptime_human : (Number(p.uptime_sec||0) + 's');
              document.getElementById('time-text').textContent = `Round elapsed: ${relH} | Uptime: ${upH}`;
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
                hotel_codes: parseCodes(document.getElementById('hotel_codes').value),
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

            ['start_date','end_date','people','rooms','smoking','hotel_codes',
             'enable_proxy','proxy_url','enable_telegram','bot_token','chat_id',
             'enable_local','enable_email','smtp_host','smtp_port','smtp_tls','smtp_user','smtp_pass','email_from','email_to'
            ].forEach(id=>{
              const el = document.getElementById(id);
              if(!el) return;
              el.addEventListener('input', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
              el.addEventListener('change', ()=>{ markEdited(id); BLOCK_REMOTE_OVERWRITE = true; });
            });

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
                  document.getElementById('err').textContent = 'Load failed';
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
              if (!results || results.length===0){
                tbody.innerHTML = '<tr><td colspan=6 style="text-align:center;color:#888">(no data yet)</td></tr>';
                return;
              }
              const cells = results.map(r=>{
                const name  = r.name || '(Hotel name not found)';
                const stat  = (r.available===true ? '✅' : (r.available===false ? '❌' : '❓'));
                const price = r.min_price_text || '-';
                const left  = r.min_remaining || '-';
                const room  = r.min_price_room || '-';
                return `<tr>
                  <td>${r.code}</td>
                  <td>${name}</td>
                  <td>${stat}</td>
                  <td>${price}</td>
                  <td>${left}</td>
                  <td>${room}</td>
                </tr>`;
              }).join('');
              tbody.innerHTML = cells;
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

                  const hc = document.getElementById('hotel_codes');
                  if (hc && !BLOCK_REMOTE_OVERWRITE && document.activeElement !== hc) {
                    const arr = Array.isArray(j.config.hotel_codes) ? j.config.hotel_codes : [];
                    hc.value = arr.join(', ');
                  }
                }
                renderRows(j.results || []);
                const act = (j && j.action) ? j.action : '(idle)';
                const age = (j && (typeof j.action_age_sec === 'number')) ? j.action_age_sec : null;
                const actLine = 'Current: ' + act + (age!=null ? ` (${age}s ago)` : '');
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

            refreshStatus();
            setInterval(refreshStatus, 2000);
          </script>
        </body></html>
        """
    return Response(html, mimetype="text/html")

@app.route("/start", methods=["POST"])
def start() -> Response:
        global _worker_thread, _driver
        payload = request.get_json(force=True, silent=True) or {}

        with _CONFIG_LOCK:
            cfg = _CONFIG
            cfg.start_date = payload.get("start_date", cfg.start_date)
            cfg.end_date = payload.get("end_date", cfg.end_date)
            codes = payload.get("hotel_codes")
            if isinstance(codes, list) and all(isinstance(x, str) for x in codes):
                cfg.hotel_codes = codes
            cfg.loop_interval_seconds = int(payload.get("loop_interval_seconds", DEFAULT_LOOP_INTERVAL_SECONDS))
            p = int(payload.get("people", cfg.people))
            cfg.people = max(1, min(5, p))
            r = int(payload.get("rooms", cfg.rooms))
            cfg.rooms = max(1, min(9, r))
            sm = str(payload.get("smoking", cfg.smoking))
            if sm not in {"Smoking", "noSmoking", "all"}:
                sm = cfg.smoking
            cfg.smoking = sm
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
        global _worker_thread
        _stop_event.set()
        if _worker_thread and _worker_thread.is_alive():
            _worker_thread.join(timeout=2)
        with _DRIVER_LOCK:
            global _driver
            if _driver is not None:
                try:
                    _driver.quit()
                except Exception:
                    pass
                _driver = None
        with _PROGRESS_LOCK:
            _PROGRESS["round_started"] = 0.0
            _PROGRESS["done"] = 0
            _PROGRESS["total"] = 0
        global _UPTIME_STARTED
        _UPTIME_STARTED = None
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

        now_ts = time.time()
        rs = float(progress.get("round_started") or 0)
        running = _worker_thread is not None and _worker_thread.is_alive()
        if running and _UPTIME_STARTED:
            progress["uptime_sec"] = int(now_ts - _UPTIME_STARTED)
        else:
            progress["uptime_sec"] = 0
        progress["round_elapsed_sec"] = int(now_ts - rs) if (running and rs > 0) else 0

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

        ok = _save_config_to_file(SAVE_PATH)
        return jsonify({"ok": ok, "path": SAVE_PATH})

@app.route("/load", methods=["POST"])
def load() -> Response:
        ok = _load_config_from_file(SAVE_PATH)
        with _CONFIG_LOCK:
            cfg = asdict(_CONFIG)
        return jsonify({"ok": ok, "config": cfg, "path": SAVE_PATH})

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