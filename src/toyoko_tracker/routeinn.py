from __future__ import annotations

import hashlib
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from .settings import HEADERS

ROUTEINN_HOTEL_LIST_URL = "https://www.route-inn.co.jp/hotel_list/"
ROUTEINN_STORELOCATOR_API_URL = "https://route-inn.storelocator.jp/api/point/"
TRIPLA_API_URL = "https://concierge.tripla.ai"
TRIPLA_IDP_URL = "https://idp.tripla.ai/api/client_sessions"

# These public widget credentials are shipped in Tripla's browser bundle.
TRIPLA_CLIENT_KEY = "c8c604a2d81f7b2fe901"
TRIPLA_CLIENT_SECRET = "1882351c176e635f5c64"

_CACHE_LOCK = threading.RLock()
_TOKEN_LOCK = threading.Lock()
_AREA_CACHE: Dict[str, Tuple[float, str, str]] = {}
_COORDINATE_CACHE: Tuple[float, List[Dict[str, Any]]] = (0.0, [])
_BOOKING_CODE_CACHE: Dict[str, str] = {}
_HOTEL_NAME_CACHE: Dict[Tuple[str, str], str] = {}
_SESSION_TOKEN = ""
_SESSION_TOKEN_AT = 0.0

_TRIPLA_LOCALES = {
    "zh_cn": "zh_Hans",
    "zh_tw": "zh_Hant",
    "ja": "ja",
    "ko": "ko",
    "en": "en",
}


def _brand_of(name: str) -> Optional[str]:
    if "アークホテル" in name:
        return "ark"
    if "グランヴィリオ" in name:
        return "grandvrio"
    if "ルートイングランティア" in name:
        return "grandia"
    if "ホテルルートイン" in name:
        return "routeinn"
    return None


def _brand_names(name: str, brand: str) -> Dict[str, str]:
    prefixes = {
        "routeinn": {
            "ja": "ホテルルートイン",
            "zh_cn": "露樱酒店",
            "zh_tw": "露櫻飯店",
            "ko": "호텔 루트인",
            "en": "Hotel Route-Inn",
        },
        "grandia": {
            "ja": "ルートイングランティア",
            "zh_cn": "露樱Grandia",
            "zh_tw": "露櫻Grandia",
            "ko": "루트인 Grandia",
            "en": "Route-Inn Grandia",
        },
        "grandvrio": {
            "ja": "グランヴィリオ",
            "zh_cn": "Grandvrio",
            "zh_tw": "Grandvrio",
            "ko": "그랑비리오",
            "en": "Grandvrio",
        },
        "ark": {
            "ja": "アークホテル",
            "zh_cn": "ARK酒店",
            "zh_tw": "ARK飯店",
            "ko": "ARK 호텔",
            "en": "ARK Hotel",
        },
    }
    markers = {
        "routeinn": ["ホテルルートイン"],
        "grandia": ["ルートイングランティア"],
        "grandvrio": ["グランヴィリオホテル", "グランヴィリオ"],
        "ark": ["アークホテル"],
    }
    suffix = name
    for marker in markers[brand]:
        suffix = suffix.replace(marker, "", 1)
    suffix = suffix.strip()
    return {
        language: f"{label} {suffix}".strip()
        for language, label in prefixes[brand].items()
    }


def _internal_code(detail_url: str, reservation_url: str) -> Tuple[str, str]:
    match = re.search(r"index_hotel_id_(\d+)", detail_url)
    if match:
        hotel_id = match.group(1)
        return f"routeinn:{hotel_id}", f"RI-{hotel_id}"
    query = parse_qs(urlsplit(reservation_url).query)
    booking_code = str((query.get("code") or [""])[0])
    if booking_code:
        return f"routeinn:{booking_code}", f"RI-{booking_code[:6].upper()}"
    slug = re.sub(r"[^a-z0-9]+", "-", urlsplit(detail_url).netloc + urlsplit(detail_url).path, flags=re.I).strip("-")
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:6].upper()
    return f"routeinn:{slug}", f"RI-{digest}"


def parse_hotel_list_html(page_html: str, source_url: str, primary_language: str = "zh_cn") -> List[Dict[str, Any]]:
    soup = BeautifulSoup(page_html or "", "html.parser")
    roots = soup.select(".p-hotel")
    root = roots[0] if roots else soup
    hotels: List[Dict[str, Any]] = []
    seen = set()
    for name_node in root.select("p.name"):
        name_ja = name_node.get_text(" ", strip=True)
        brand = _brand_of(name_ja)
        if not brand:
            continue
        card = name_node.find_parent("li")
        if card is None:
            continue
        detail_link = card.select_one("ul.btns li.c-btn1:not(.c-btn1--black):not(.c-btn1--rsv) a[href]")
        map_link = card.select_one("ul.btns li.c-btn1--black a[href]")
        reservation_link = card.select_one("ul.btns li.c-btn1--rsv a[href]")
        if not detail_link or not reservation_link:
            continue
        detail_url = urljoin(source_url, detail_link.get("href"))
        reservation_url = urljoin(source_url, reservation_link.get("href"))
        code, display_code = _internal_code(detail_url, reservation_url)
        if code in seen:
            continue
        seen.add(code)
        names = _brand_names(name_ja, brand)
        address_node = card.select_one(".txt_address")
        access_node = card.select_one(".txt_information")
        address = address_node.get_text(" ", strip=True) if address_node else ""
        access = access_node.get_text(" ", strip=True) if access_node else ""
        language = primary_language if primary_language in {"zh_cn", "zh_tw", "ja", "ko", "en"} else "zh_cn"
        hotels.append({
            "code": code,
            "display_code": display_code,
            "provider": "routeinn",
            "brand": brand,
            "name": names[language],
            "name_primary": names[language],
            "name_en": names["en"],
            "name_ja": name_ja,
            "name_zh_cn": names["zh_cn"],
            "name_zh_tw": names["zh_tw"],
            "name_ko": names["ko"],
            "url": detail_url,
            "reservation_url": reservation_url,
            "map_url": urljoin(source_url, map_link.get("href")) if map_link else "",
            "address": address,
            "access": access,
        })
    return hotels


def _storelocator_hotel(point: Dict[str, Any], primary_language: str) -> Optional[Dict[str, Any]]:
    if not point.get("is_active", True):
        return None
    name_ja = str(point.get("name") or "").strip()
    brand = _brand_of(name_ja)
    if not brand:
        return None
    try:
        lat = float(point.get("latitude"))
        lng = float(point.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    extra = point.get("extra_fields") if isinstance(point.get("extra_fields"), dict) else {}
    detail_url = str(extra.get("詳細ページへのリンク") or "").strip()
    if not detail_url:
        detail_url = f"https://route-inn.storelocator.jp/detail/{point.get('key') or point.get('id')}/"
    reservation_url = str(
        extra.get("予約ページURL（PC）")
        or extra.get("予約ページURL（SP）")
        or ""
    ).strip()
    code, display_code = _internal_code(detail_url, reservation_url)
    names = _brand_names(name_ja, brand)
    language = primary_language if primary_language in {"zh_cn", "zh_tw", "ja", "ko", "en"} else "zh_cn"
    return {
        "code": code,
        "display_code": display_code,
        "provider": "routeinn",
        "brand": brand,
        "name": names[language],
        "name_primary": names[language],
        "name_en": str(extra.get("name.en") or names["en"]).strip(),
        "name_ja": name_ja,
        "name_zh_cn": names["zh_cn"],
        "name_zh_tw": names["zh_tw"],
        "name_ko": names["ko"],
        "url": detail_url,
        "reservation_url": reservation_url,
        "map_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
        "address": str(point.get("address") or "").strip(),
        "address_en": str(extra.get("address.en") or "").strip(),
        "access": "",
        "lat": lat,
        "lng": lng,
    }


def fetch_coordinate_hotels(primary_language: str = "zh_cn", force: bool = False) -> List[Dict[str, Any]]:
    global _COORDINATE_CACHE
    with _CACHE_LOCK:
        cached_at, cached_hotels = _COORDINATE_CACHE
        if cached_hotels and not force and time.time() - cached_at < 6 * 60 * 60:
            source = cached_hotels
        else:
            source = []
    if not source:
        response = requests.get(
            ROUTEINN_STORELOCATOR_API_URL,
            params={"backend_filters": "{}"},
            headers={**HEADERS, "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        parsed = []
        for point in payload.get("items") or []:
            if not isinstance(point, dict):
                continue
            hotel = _storelocator_hotel(point, "zh_cn")
            if hotel:
                parsed.append(hotel)
        source = sorted(parsed, key=lambda hotel: str(hotel.get("display_code") or hotel.get("code") or ""))
        with _CACHE_LOCK:
            _COORDINATE_CACHE = (time.time(), source)
    localized = []
    for hotel in source:
        item = dict(hotel)
        language = primary_language if primary_language in {"zh_cn", "zh_tw", "ja", "ko", "en"} else "zh_cn"
        item["name_primary"] = item.get(f"name_{language}") or item.get("name") or item.get("name_en") or ""
        item["name"] = item["name_primary"]
        localized.append(item)
    return localized


def _attach_coordinates(hotels: List[Dict[str, Any]], primary_language: str) -> List[Dict[str, Any]]:
    coordinate_hotels = fetch_coordinate_hotels(primary_language)
    by_code = {str(hotel.get("code") or ""): hotel for hotel in coordinate_hotels}
    for hotel in hotels:
        match = by_code.get(str(hotel.get("code") or ""))
        if not match:
            continue
        for key in ("lat", "lng", "address_en"):
            if match.get(key) not in (None, ""):
                hotel[key] = match[key]
        hotel["map_url"] = match.get("map_url") or hotel.get("map_url") or ""
        hotel["reservation_url"] = hotel.get("reservation_url") or match.get("reservation_url") or ""
    return hotels


def fetch_area_hotels(
    region_id: int,
    prefecture_id: Optional[int] = None,
    primary_language: str = "zh_cn",
) -> List[Dict[str, Any]]:
    params = {"area": int(region_id)}
    if prefecture_id:
        params["pref"] = int(prefecture_id)
    cache_key = urlencode(params)
    with _CACHE_LOCK:
        cached = _AREA_CACHE.get(cache_key)
        if cached and time.time() - cached[0] < 30 * 60:
            return _attach_coordinates(parse_hotel_list_html(cached[1], cached[2], primary_language), primary_language)
    response = requests.get(ROUTEINN_HOTEL_LIST_URL, params=params, headers=HEADERS, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    with _CACHE_LOCK:
        _AREA_CACHE[cache_key] = (time.time(), response.text, response.url)
    return _attach_coordinates(parse_hotel_list_html(response.text, response.url, primary_language), primary_language)


def _tripla_headers(locale: str, *, refresh_token: bool = False) -> Dict[str, str]:
    token = _tripla_session_token(force=refresh_token)
    return {
        **HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "App-Version": "tripla-booking-widget/1.0",
        "Client-Session": token,
        "Tripla-Locale": _TRIPLA_LOCALES.get(locale, locale),
    }


def _tripla_session_token(force: bool = False) -> str:
    global _SESSION_TOKEN, _SESSION_TOKEN_AT
    with _TOKEN_LOCK:
        if _SESSION_TOKEN and not force and time.time() - _SESSION_TOKEN_AT < 6 * 60 * 60:
            return _SESSION_TOKEN
        response = requests.post(
            TRIPLA_IDP_URL,
            headers={
                **HEADERS,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "App-Version": "tripla-booking-widget/1.0",
            },
            json={"key": TRIPLA_CLIENT_KEY, "secret": TRIPLA_CLIENT_SECRET},
            timeout=15,
        )
        response.raise_for_status()
        token = str(((response.json().get("data") or {}).get("client_session")) or "")
        if not token:
            raise RuntimeError("Tripla did not return a client session")
        _SESSION_TOKEN = token
        _SESSION_TOKEN_AT = time.time()
        return token


def _api_get(path: str, locale: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{TRIPLA_API_URL}{path}"
    response = requests.get(url, headers=_tripla_headers(locale), params=params, timeout=25)
    if response.status_code == 401:
        response = requests.get(url, headers=_tripla_headers(locale, refresh_token=True), params=params, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("errors"):
        raise RuntimeError(str((payload["errors"][0] or {}).get("title") or "Tripla API error"))
    return payload


def resolve_booking_code(hotel: Dict[str, Any]) -> str:
    internal_code = str(hotel.get("code") or "")
    with _CACHE_LOCK:
        cached = _BOOKING_CODE_CACHE.get(internal_code)
        if cached:
            return cached
    reservation_url = str(hotel.get("reservation_url") or "")
    query = parse_qs(urlsplit(reservation_url).query)
    booking_code = str((query.get("code") or [""])[0])
    if not booking_code:
        response = requests.get(reservation_url, headers=HEADERS, timeout=20, allow_redirects=True)
        response.raise_for_status()
        booking_code = str((parse_qs(urlsplit(response.url).query).get("code") or [""])[0])
    if not booking_code:
        raise RuntimeError("Route Inn booking code could not be resolved")
    with _CACHE_LOCK:
        _BOOKING_CODE_CACHE[internal_code] = booking_code
    return booking_code


def build_booking_url(hotel: Dict[str, Any], start: str, end: str, adults: int, rooms: int) -> str:
    base = str(hotel.get("reservation_url") or hotel.get("url") or ROUTEINN_HOTEL_LIST_URL)
    parts = urlsplit(base)
    query = parse_qs(parts.query)
    query.update({
        "checkin_date": [start],
        "checkout_date": [end],
        "adults": [str(max(1, int(adults)))],
        "children": ["0"],
        "rooms": [str(max(1, int(rooms)))],
    })
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))


def _localized_hotel_name(booking_code: str, locale: str) -> str:
    cache_key = (booking_code, locale)
    with _CACHE_LOCK:
        if cache_key in _HOTEL_NAME_CACHE:
            return _HOTEL_NAME_CACHE[cache_key]
    payload = _api_get(f"/hotels/{booking_code}/settings/booking_widget", locale)
    name = str((payload.get("booking_widget_setting_attributes") or {}).get("hotel_name") or "")
    with _CACHE_LOCK:
        _HOTEL_NAME_CACHE[cache_key] = name
    return name


def _normalized_hotel_name(name: str, brand: str, locale: str) -> str:
    labels = {
        "routeinn": {"zh_cn": "露樱酒店", "zh_tw": "露櫻飯店", "ja": "ホテルルートイン", "ko": "호텔 루트인", "en": "Hotel Route-Inn"},
        "grandia": {"zh_cn": "露樱Grandia", "zh_tw": "露櫻Grandia", "ja": "ルートイングランティア", "ko": "루트인 Grandia", "en": "Route-Inn Grandia"},
        "grandvrio": {"zh_cn": "Grandvrio", "zh_tw": "Grandvrio", "ja": "グランヴィリオ", "ko": "그랑비리오", "en": "Grandvrio"},
        "ark": {"zh_cn": "ARK酒店", "zh_tw": "ARK飯店", "ja": "アークホテル", "ko": "ARK 호텔", "en": "ARK Hotel"},
    }
    known_prefixes = {
        "routeinn": ["ホテルルートイン", "Hotel Route-Inn", "Route Inn", "호텔 루트인", "루트 인"],
        "grandia": ["ルートイングランティア", "Route-Inn Grandia", "Route Inn Grantia", "Route Inn Grandia", "루트인 그란티아"],
        "grandvrio": ["グランヴィリオホテル", "グランヴィリオ", "Grandvrio Hotel", "Grandvrio", "그랑비리오 호텔", "그랑비리오"],
        "ark": ["アークホテル", "ARK Hotel", "Ark Hotel", "아크 호텔"],
    }
    suffix = str(name or "").strip()
    for prefix in known_prefixes.get(brand, []):
        if suffix.lower().startswith(prefix.lower()):
            suffix = suffix[len(prefix):].strip()
            break
    label = labels.get(brand, labels["routeinn"]).get(locale, labels.get(brand, labels["routeinn"])["en"])
    return f"{label} {suffix}".strip()


def _room_map(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rooms: Dict[str, Dict[str, Any]] = {}
    for plan in payload.get("plans") or []:
        if not isinstance(plan, dict):
            continue
        for room in plan.get("rooms") or []:
            if not isinstance(room, dict):
                continue
            key = str(room.get("room_plan_code") or f"{room.get('room_type_code')}:{room.get('hotel_plan_code')}")
            item = dict(room)
            item["_plan_name"] = plan.get("name") or room.get("room_plan_name") or ""
            rooms[key] = item
    return rooms


def fetch_offers(
    hotel: Dict[str, Any],
    start: str,
    end: str,
    adults: int,
    rooms: int,
    primary_language: str,
) -> Tuple[str, str, str, List[Dict[str, Any]], Dict[str, bool]]:
    booking_code = resolve_booking_code(hotel)
    locale = primary_language if primary_language in _TRIPLA_LOCALES else "zh_cn"
    params = {
        "checkin_date": start,
        "checkout_date": end,
        "adults": max(1, int(adults)),
        "children": 0,
        "rooms": max(1, int(rooms)),
    }
    primary_payload = _api_get(f"/hotels/{booking_code}/rooms", locale, params)
    english_payload = primary_payload if locale == "en" else _api_get(f"/hotels/{booking_code}/rooms", "en", params)
    primary_rooms = _room_map(primary_payload)
    english_rooms = _room_map(english_payload)
    offers: List[Dict[str, Any]] = []
    for key, room in primary_rooms.items():
        if str(room.get("availability") or "").lower() != "available":
            continue
        english = english_rooms.get(key, {})
        try:
            price = int(room.get("total_price") or 0) + int(room.get("tax") or 0) + int(room.get("accommodation_tax") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        discount = room.get("sign_in_discount") or {}
        member_price = None
        try:
            discounted = discount.get("total_price_after_discount")
            if discounted is not None:
                member_price = int(discounted) + int(discount.get("total_price_after_discount_tax") or 0) + int(discount.get("total_accommodation_tax") or 0)
        except (TypeError, ValueError):
            member_price = None
        inventory = room.get("inventory")
        remaining = str(inventory) if isinstance(inventory, int) and inventory >= 0 else "≥1"
        is_smoking = room.get("is_smoking")
        offers.append({
            "price_val": price,
            "price_text": f"¥{price:,}",
            "member_price_val": member_price,
            "member_price_text": f"¥{member_price:,}" if member_price is not None else None,
            "remaining_norm": remaining,
            "room_title": english.get("room_type_name") or room.get("room_type_name") or "Room",
            "room_title_primary": room.get("room_type_name") or "",
            "room_smoking": "smoking" if is_smoking is True else "non_smoking" if is_smoking is False else None,
            "plan_name": english.get("_plan_name") or room.get("_plan_name") or "",
        })
    brand = str(hotel.get("brand") or "routeinn")
    raw_primary = _localized_hotel_name(booking_code, locale) or str(hotel.get("name_primary") or hotel.get("name") or "")
    raw_english = _localized_hotel_name(booking_code, "en") or str(hotel.get("name_en") or raw_primary)
    name_primary = _normalized_hotel_name(raw_primary, brand, locale)
    name_en = _normalized_hotel_name(raw_english, brand, "en")
    booking_url = build_booking_url(hotel, start, end, adults, rooms)
    stats = {
        "had_any_offer": bool(primary_rooms),
        "had_any_non_ignored_offer": bool(primary_rooms),
        "had_any_ignored_offer": False,
    }
    return name_primary, name_en, booking_url, offers, stats
