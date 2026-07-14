from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import List

from .desktop_version import DESKTOP_VERSION

try:
    PYPI_VERSION = version("toyoko-tracker")
except PackageNotFoundError:
    PYPI_VERSION = "0.0.0+local"

__version__ = DESKTOP_VERSION if getattr(sys, "frozen", False) else PYPI_VERSION

APP_NAME = "东横酱 Toyoko Chan"
APP_AUTHOR = "bilibili @果冻猫猫丶"
APP_VERSION = f"v{__version__}"

DEFAULT_START_DATE = datetime.now().strftime("%Y-%m-%d")
DEFAULT_END_DATE = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
DEFAULT_HOTEL_CODES: List[str] = [
    "00001", "00003", "00005", "00007", "00009"
]
DEFAULT_LOOP_INTERVAL_SECONDS = 30
DEFAULT_PER_HOTEL_DELAY_SECONDS = 1
DEFAULT_REQUEST_JITTER_PERCENT = 40
DEFAULT_ROOM_REQUIREMENT = "any"
DEFAULT_PEOPLE = 1
DEFAULT_ROOMS = 1
DEFAULT_SMOKING = "noSmoking"
DEFAULT_MEMBERSHIP_STATUS = "member"
DEFAULT_PRIMARY_LANGUAGE = "zh_cn"
DEFAULT_SEARCH_MODE = "area"
SUPPORTED_PROVIDERS = ("toyoko", "routeinn", "dormy", "mystays", "daiwa")
DEFAULT_ENABLED_PROVIDERS = ["toyoko"]
DEFAULT_RADIUS_KM = 5
DEFAULT_AVAILABLE_ALERT_REPEAT = 0
DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC = 300
DEFAULT_BUDGET_ENABLED = False
DEFAULT_BUDGET_LIMIT = 30000
DEFAULT_ENABLE_TELEGRAM = False
DEFAULT_BOT_TOKEN = ""
DEFAULT_CHAT_ID = ""
DEFAULT_ENABLE_BARK = False
DEFAULT_BARK_KEY = ""
DEFAULT_BARK_SERVER = "https://api.day.app"
DEFAULT_BARK_CRITICAL_ENABLED = False
DEFAULT_BARK_CRITICAL_VOLUME = 5
DEFAULT_BARK_CRITICAL_SOUND = "alarm"
DEFAULT_ENABLE_SERVERCHAN = False
DEFAULT_SERVERCHAN_SENDKEY = ""
DEFAULT_NOTIFY_AVAILABLE = True
DEFAULT_NOTIFY_UNAVAILABLE = True
DEFAULT_NOTIFY_AVAILABILITY_COUNT_CHANGE = True
DEFAULT_NOTIFY_START = True
DEFAULT_NOTIFY_STOP = True
DEFAULT_NOTIFY_SEARCH_ERROR = False
DEFAULT_SMART_PARALLEL_ENABLED = False
DEFAULT_SMART_PARALLEL_WORKERS = 1
DEFAULT_ADAPTIVE_BACKOFF_ENABLED = True
ADAPTIVE_BACKOFF_THRESHOLD_PERCENT = 50
ADAPTIVE_BACKOFF_MAX_MULTIPLIER = 4
DEFAULT_ENGINE = "http"
DEFAULT_ENABLE_LOCAL = False
DEFAULT_ENABLE_EMAIL = False
DEFAULT_SMTP_HOST = ""
DEFAULT_SMTP_PORT = 465
DEFAULT_SMTP_TLS = True
DEFAULT_SMTP_USER = ""
DEFAULT_SMTP_PASS = ""
DEFAULT_EMAIL_FROM = ""
DEFAULT_EMAIL_TO = ""

SAVE_FILENAME = "save.json"
AUTO_SAVE_FILENAME = "auto_save.json"
SEARCH_HISTORY_FILENAME = "search_history.json"
RADIUS_HOTELS_CACHE_FILENAME = "radius_hotels_cache.json"
HOTEL_CATALOG_SNAPSHOT_FILENAME = "hotel_catalog_snapshot.json"
CHAIN_PROVIDER_CACHE_FILENAME = "chain_provider_cache.json"
HOTEL_DATABASE_FILENAME = "hotel_database.sqlite3"
INSTANCE_STATE_FILENAME = "instance.json"
MOBILE_ACCESS_FILENAME = "mobile_access.json"
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
RADIUS_HOTELS_CACHE_PATH = os.path.join(CONFIG_DIR, RADIUS_HOTELS_CACHE_FILENAME)
HOTEL_CATALOG_SNAPSHOT_PATH = os.path.join(CONFIG_DIR, HOTEL_CATALOG_SNAPSHOT_FILENAME)
CHAIN_PROVIDER_CACHE_PATH = os.path.join(CONFIG_DIR, CHAIN_PROVIDER_CACHE_FILENAME)
HOTEL_DATABASE_PATH = os.path.join(CONFIG_DIR, HOTEL_DATABASE_FILENAME)
INSTANCE_STATE_PATH = os.path.join(CONFIG_DIR, INSTANCE_STATE_FILENAME)
MOBILE_ACCESS_PATH = os.path.join(CONFIG_DIR, MOBILE_ACCESS_FILENAME)

HOTEL_CATALOG_URL = "https://www.toyoko-inn.com/eng/hotel_list/"
HOTEL_CATALOG_CHECK_INTERVAL_SECONDS = 6 * 60 * 60
HOTEL_COORDINATE_CACHE_TTL_SECONDS = 24 * 60 * 60

BASE_URL = "https://www.toyoko-inn.com/eng/search/result/room_plan/"
TIMEOUT = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
