from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .settings import (
    DEFAULT_AVAILABLE_ALERT_REPEAT,
    DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC,
    DEFAULT_ADAPTIVE_BACKOFF_ENABLED,
    DEFAULT_BARK_KEY,
    DEFAULT_BARK_SERVER,
    DEFAULT_BARK_CRITICAL_ENABLED,
    DEFAULT_BARK_CRITICAL_SOUND,
    DEFAULT_BARK_CRITICAL_VOLUME,
    DEFAULT_BOT_TOKEN,
    DEFAULT_BUDGET_ENABLED,
    DEFAULT_BUDGET_LIMIT,
    DEFAULT_CHAT_ID,
    DEFAULT_EMAIL_FROM,
    DEFAULT_EMAIL_TO,
    DEFAULT_ENABLE_BARK,
    DEFAULT_ENABLE_EMAIL,
    DEFAULT_ENABLE_LOCAL,
    DEFAULT_ENABLE_SERVERCHAN,
    DEFAULT_ENABLE_TELEGRAM,
    DEFAULT_END_DATE,
    DEFAULT_ENABLED_PROVIDERS,
    DEFAULT_ENGINE,
    DEFAULT_HOTEL_CODES,
    DEFAULT_LOOP_INTERVAL_SECONDS,
    DEFAULT_MEMBERSHIP_STATUS,
    DEFAULT_PEOPLE,
    DEFAULT_PER_HOTEL_DELAY_SECONDS,
    DEFAULT_PRIMARY_LANGUAGE,
    DEFAULT_RADIUS_KM,
    DEFAULT_REQUEST_JITTER_PERCENT,
    DEFAULT_ROOMS,
    DEFAULT_ROOM_REQUIREMENT,
    DEFAULT_SEARCH_MODE,
    DEFAULT_SERVERCHAN_SENDKEY,
    DEFAULT_NOTIFY_AVAILABLE,
    DEFAULT_NOTIFY_AVAILABILITY_COUNT_CHANGE,
    DEFAULT_NOTIFY_SEARCH_ERROR,
    DEFAULT_NOTIFY_START,
    DEFAULT_NOTIFY_STOP,
    DEFAULT_NOTIFY_UNAVAILABLE,
    DEFAULT_SMART_PARALLEL_ENABLED,
    DEFAULT_SMART_PARALLEL_WORKERS,
    DEFAULT_SMOKING,
    DEFAULT_SMTP_HOST,
    DEFAULT_SMTP_PASS,
    DEFAULT_SMTP_PORT,
    DEFAULT_SMTP_TLS,
    DEFAULT_SMTP_USER,
    DEFAULT_START_DATE,
)


@dataclass
class HotelResult:
    code: str
    url: str
    name: Optional[str]
    available: Optional[bool]
    min_price: Optional[int] = None
    min_price_text: Optional[str] = None
    min_price_room: Optional[str] = None
    min_price_plan: Optional[str] = None
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    name_primary: Optional[str] = None
    primary_language: str = DEFAULT_PRIMARY_LANGUAGE
    min_member_price_text: Optional[str] = None
    min_remaining: Optional[str] = None
    offers_display: Optional[List[Dict[str, Any]]] = None
    requirement_unmet: bool = False
    checked_at: Optional[str] = None
    elapsed_ms: Optional[int] = None
    engine_used: Optional[str] = None
    error_summary: Optional[str] = None
    http_status: Optional[int] = None
    retry_after_sec: Optional[int] = None
    from_cache: bool = False
    cache_age_sec: Optional[int] = None
    cache_validated: bool = False
    cache_fallback: bool = False
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    provider: str = "toyoko"
    display_code: Optional[str] = None


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
    budget_enabled: bool = DEFAULT_BUDGET_ENABLED
    budget_limit: int = DEFAULT_BUDGET_LIMIT
    smoking: str = DEFAULT_SMOKING
    membership_status: str = DEFAULT_MEMBERSHIP_STATUS
    primary_language: str = DEFAULT_PRIMARY_LANGUAGE
    om_requirement: str = DEFAULT_ROOM_REQUIREMENT
    enable_telegram: bool = DEFAULT_ENABLE_TELEGRAM
    bot_token: str = DEFAULT_BOT_TOKEN
    chat_id: str = DEFAULT_CHAT_ID
    enable_bark: bool = DEFAULT_ENABLE_BARK
    bark_key: str = DEFAULT_BARK_KEY
    bark_server: str = DEFAULT_BARK_SERVER
    bark_critical_enabled: bool = DEFAULT_BARK_CRITICAL_ENABLED
    bark_critical_volume: int = DEFAULT_BARK_CRITICAL_VOLUME
    bark_critical_sound: str = DEFAULT_BARK_CRITICAL_SOUND
    enable_serverchan: bool = DEFAULT_ENABLE_SERVERCHAN
    serverchan_sendkey: str = DEFAULT_SERVERCHAN_SENDKEY
    notify_available: bool = DEFAULT_NOTIFY_AVAILABLE
    notify_unavailable: bool = DEFAULT_NOTIFY_UNAVAILABLE
    notify_availability_count_change: bool = DEFAULT_NOTIFY_AVAILABILITY_COUNT_CHANGE
    notify_start: bool = DEFAULT_NOTIFY_START
    notify_stop: bool = DEFAULT_NOTIFY_STOP
    notify_search_error: bool = DEFAULT_NOTIFY_SEARCH_ERROR
    enable_local: bool = DEFAULT_ENABLE_LOCAL
    enable_email: bool = DEFAULT_ENABLE_EMAIL
    smtp_host: str = DEFAULT_SMTP_HOST
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_tls: bool = DEFAULT_SMTP_TLS
    smtp_user: str = DEFAULT_SMTP_USER
    smtp_pass: str = DEFAULT_SMTP_PASS
    email_from: str = DEFAULT_EMAIL_FROM
    email_to: str = DEFAULT_EMAIL_TO
    available_alert_repeat: int = DEFAULT_AVAILABLE_ALERT_REPEAT
    available_alert_repeat_interval_sec: int = DEFAULT_AVAILABLE_ALERT_REPEAT_INTERVAL_SEC
    engine: str = DEFAULT_ENGINE
    smart_parallel_enabled: bool = DEFAULT_SMART_PARALLEL_ENABLED
    smart_parallel_workers: int = DEFAULT_SMART_PARALLEL_WORKERS
    adaptive_backoff_enabled: bool = DEFAULT_ADAPTIVE_BACKOFF_ENABLED
    area_region: str = ""
    area_detail: str = ""
    area_region_label: str = ""
    area_detail_label: str = ""
    search_mode: str = DEFAULT_SEARCH_MODE
    enabled_providers: List[str] = None
    radius_query: str = ""
    radius_lat: Optional[float] = None
    radius_lng: Optional[float] = None
    radius_km: int = DEFAULT_RADIUS_KM
    selected_hotels: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.hotel_codes is None:
            self.hotel_codes = list(DEFAULT_HOTEL_CODES)
        if self.selected_hotels is None:
            self.selected_hotels = []
        if self.enabled_providers is None:
            self.enabled_providers = list(DEFAULT_ENABLED_PROVIDERS)
