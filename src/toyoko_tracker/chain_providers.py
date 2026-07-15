from __future__ import annotations

import base64
import html
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .http_client import get as _http_get
from .routeinn import _api_get as _tripla_api_get
from .settings import CHAIN_PROVIDER_CACHE_PATH, HEADERS

DORMY_API_URL = "https://dormy-hotels.com/reserve/api"
DORMY_RESERVE_URL = "https://dormy-hotels.com/reserve/search-plan"
MYSTAYS_HOTELS_URL = "https://iconia.co.jp/en-us/hotels"
DAIWA_HOTELS_URL = "https://www.daiwaroynet.jp/hotelist/"

_CACHE_LOCK = threading.RLock()
_PROVIDER_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_CACHE_TTL = 6 * 60 * 60

_DORMY_HEADERS = {
    **HEADERS,
    "Accept": "application/json",
    "Authorization": "Basic " + base64.b64encode(b"username:hotel-reserves").decode("ascii"),
}

_PREFECTURE_REGION = {
    "北海道": 1,
    "青森": 2, "岩手": 2, "宮城": 2, "秋田": 2, "山形": 2, "福島": 2,
    "茨城": 3, "栃木": 3, "群馬": 3, "埼玉": 3, "千葉": 3, "東京": 3, "神奈川": 3,
    "新潟": 4, "富山": 4, "石川": 4, "福井": 4, "山梨": 4, "長野": 4,
    "岐阜": 4, "静岡": 4, "愛知": 4, "三重": 4,
    "滋賀": 5, "京都": 5, "大阪": 5, "兵庫": 5, "奈良": 5, "和歌山": 5,
    "鳥取": 6, "島根": 6, "岡山": 6, "広島": 6, "山口": 6,
    "徳島": 6, "香川": 6, "愛媛": 6, "高知": 6,
    "福岡": 7, "佐賀": 7, "長崎": 7, "熊本": 7, "大分": 7,
    "宮崎": 7, "鹿児島": 7, "沖縄": 7,
}
_PREFECTURES = (
    "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島", "茨城", "栃木", "群馬",
    "埼玉", "千葉", "東京", "神奈川", "新潟", "富山", "石川", "福井", "山梨", "長野",
    "岐阜", "静岡", "愛知", "三重", "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山",
    "鳥取", "島根", "岡山", "広島", "山口", "徳島", "香川", "愛媛", "高知", "福岡",
    "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島", "沖縄",
)


def _prefecture_name(value: str) -> str:
    text = re.sub(r"[\[\]【】\s]", "", str(value or ""))
    for suffix in ("北海道", "東京都", "京都府", "大阪府", "県", "府", "都"):
        if text.endswith(suffix):
            return text[:-len(suffix)] or suffix.replace("府", "").replace("都", "")
    return text


def _region_id(prefecture: str) -> Optional[int]:
    raw = str(prefecture or "")
    if "北海道" in raw:
        return 1
    normalized = _prefecture_name(raw)
    return _PREFECTURE_REGION.get(normalized)


def _prefecture_id(prefecture: str) -> Optional[int]:
    raw = str(prefecture or "")
    normalized = "北海道" if "北海道" in raw else _prefecture_name(raw)
    try:
        return _PREFECTURES.index(normalized) + 1
    except ValueError:
        return None


def prefecture_id_from_text(value: str) -> Optional[int]:
    raw = str(value or "")
    for index, prefecture in enumerate(_PREFECTURES, 1):
        if prefecture in raw:
            return index
    return _prefecture_id(raw)


def region_id_for_prefecture_id(prefecture_id: Optional[int]) -> Optional[int]:
    try:
        prefecture = _PREFECTURES[int(prefecture_id) - 1]
    except (IndexError, TypeError, ValueError):
        return None
    return _PREFECTURE_REGION.get(prefecture)


def _cache_timestamp_is_fresh(cached_at: float, *, now: Optional[float] = None) -> bool:
    age = (time.time() if now is None else float(now)) - float(cached_at)
    return -300 <= age < _CACHE_TTL


def _cached(provider: str) -> Optional[List[Dict[str, Any]]]:
    with _CACHE_LOCK:
        cached_at, hotels = _PROVIDER_CACHE.get(provider, (0.0, []))
        if hotels and _cache_timestamp_is_fresh(cached_at):
            return [dict(hotel) for hotel in hotels]
        try:
            with open(CHAIN_PROVIDER_CACHE_PATH, "r", encoding="utf-8") as stream:
                document = json.load(stream)
            record = (document.get("providers") or {}).get(provider) or {}
            cached_at = float(record.get("generated_at") or 0.0)
            hotels = record.get("hotels") if isinstance(record.get("hotels"), list) else []
            if hotels and _cache_timestamp_is_fresh(cached_at):
                _PROVIDER_CACHE[provider] = (cached_at, hotels)
                return [dict(hotel) for hotel in hotels]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    return None


def _store(provider: str, hotels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    with _CACHE_LOCK:
        generated_at = time.time()
        stored_hotels = [dict(hotel) for hotel in hotels]
        _PROVIDER_CACHE[provider] = (generated_at, stored_hotels)
        try:
            with open(CHAIN_PROVIDER_CACHE_PATH, "r", encoding="utf-8") as stream:
                document = json.load(stream)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            document = {"providers": {}}
        try:
            providers = document.setdefault("providers", {})
            providers[provider] = {"generated_at": generated_at, "hotels": stored_hotels}
            os.makedirs(os.path.dirname(CHAIN_PROVIDER_CACHE_PATH), exist_ok=True)
            temporary_path = CHAIN_PROVIDER_CACHE_PATH + ".tmp"
            with open(temporary_path, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2)
            os.replace(temporary_path, CHAIN_PROVIDER_CACHE_PATH)
        except OSError:
            pass
    return hotels


def _localized(hotel: Dict[str, Any], primary_language: str) -> Dict[str, Any]:
    item = dict(hotel)
    language = primary_language if primary_language in {"zh_cn", "zh_tw", "ja", "ko", "en"} else "zh_cn"
    item["name_primary"] = item.get(f"name_{language}") or item.get("name_ja") or item.get("name_en") or item.get("name") or ""
    item["name"] = item["name_primary"]
    return item


def _dormy_get(path: str, locale: str = "ja", params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    last_error = None
    for attempt in range(3):
        try:
            response = _http_get(
                f"{DORMY_API_URL}{path}",
                headers={**_DORMY_HEADERS, "X-localization": locale},
                params=params,
                timeout=25,
            )
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.25 * (attempt + 1))
    else:
        raise last_error or RuntimeError("Dormy Inn API request failed")
    payload = response.json()
    if payload.get("message") not in (None, "OK"):
        raise RuntimeError(str(payload.get("message")))
    return payload.get("data") or {}


def _dormy_catalog(force: bool = False) -> List[Dict[str, Any]]:
    cached = None if force else _cached("dormy")
    if cached is not None:
        return cached
    def listing(locale: str) -> Dict[int, Dict[str, Any]]:
        result: Dict[int, Dict[str, Any]] = {}
        page = 1
        while page <= 30:
            payload = _dormy_get("/hotels", locale, {"page": page})
            batch = payload.get("data") or []
            for row in batch:
                if int(row.get("business_category_id") or 0) == 1:
                    result[int(row["id"])] = row
            if not payload.get("next_page") or not batch:
                break
            page += 1
        return result

    rows = listing("ja")
    english_rows = listing("en")

    map_response = requests.get("https://dormy-hotels.com/dormyinn/", headers=HEADERS, timeout=30)
    map_response.raise_for_status()
    map_pattern = re.compile(
        r'"r\.hotel_name":"(?P<name>(?:\\.|[^"])*)".*?'
        r'"r\.access_ido":"(?P<lat>-?\d+(?:\.\d+)?)",'
        r'"r\.access_keido":"(?P<lng>-?\d+(?:\.\d+)?)",'
        r'"r\.url_alias":"(?P<slug>[^"]+)"'
    )
    coordinates = {
        match.group("slug").strip("/"): (float(match.group("lat")), float(match.group("lng")))
        for match in map_pattern.finditer(map_response.text)
    }

    def detail(hotel_id: int) -> Optional[Dict[str, Any]]:
        ja = rows[hotel_id]
        url = str(ja.get("hotel_URL") or "").strip()
        slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        coord = coordinates.get(slug)
        if not coord:
            return None
        lat, lng = coord
        keyword = str(ja.get("short_name") or ja.get("name") or "").strip()
        booking_url = f"{DORMY_RESERVE_URL}?{urlencode({'keyword': keyword, 'search_by_tag': 'plan'})}"
        prefecture = str(ja.get("prefecture") or rows[hotel_id].get("prefecture") or "")
        return {
            "code": f"dormy:{hotel_id}", "display_code": f"DM-{hotel_id}", "provider": "dormy",
            "brand": "dormy", "provider_hotel_id": str(hotel_id), "search_keyword": keyword,
            "name": keyword, "name_ja": keyword,
            "name_en": english_rows.get(hotel_id, {}).get("short_name") or english_rows.get(hotel_id, {}).get("name") or keyword,
            "name_zh_cn": keyword, "name_zh_tw": keyword,
            "name_ko": english_rows.get(hotel_id, {}).get("short_name") or keyword,
            "url": url, "reservation_url": booking_url,
            "map_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
            "address": str(ja.get("prefecture") or ""),
            "access": "", "lat": lat, "lng": lng, "prefecture": prefecture,
            "region_id": _region_id(prefecture), "prefecture_id": _prefecture_id(prefecture),
        }

    hotels = [hotel for hotel in (detail(hotel_id) for hotel_id in sorted(rows)) if hotel]
    return _store("dormy", sorted(hotels, key=lambda hotel: hotel["display_code"]))


def _mystays_catalog(force: bool = False) -> List[Dict[str, Any]]:
    cached = None if force else _cached("mystays")
    if cached is not None:
        return cached
    response = requests.get(MYSTAYS_HOTELS_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    text = html.unescape(response.text).replace('\\"', '"')
    pattern = re.compile(
        r'"name":"(?P<name>[^"]+)","reviewCount":.*?,"rating":.*?'
        r'"city":"(?P<city>[^"]+)".*?"lat":"(?P<lat>-?\d+(?:\.\d+)?)",'
        r'"lng":"(?P<lng>-?\d+(?:\.\d+)?)".{0,10000}?"slug":"(?P<slug>[^"]+)"'
        r'.{0,10000}?"brandItemName":"(?P<brand>[^"]+)".{0,10000}?'
        r'"triplaBookingCode":"(?P<code>[^"]+)"'
    )
    hotels = []
    seen = set()
    for match in pattern.finditer(text):
        data = match.groupdict()
        if data["brand"].lower() != "mystays" or data["code"] in seen:
            continue
        seen.add(data["code"])
        lat, lng = float(data["lat"]), float(data["lng"])
        slug = data["slug"]
        name_en = " ".join(part.upper() if part in {"hotel", "mystays"} else part.title() for part in slug.split("-")[:-1])
        prefecture = data["city"]
        hotels.append({
            "code": f"mystays:{data['code']}", "display_code": f"MS-{data['code'][:6].upper()}",
            "provider": "mystays", "brand": "mystays", "booking_code": data["code"],
            "name": data["name"], "name_ja": data["name"], "name_en": name_en,
            "name_zh_cn": data["name"], "name_zh_tw": data["name"], "name_ko": data["name"],
            "url": f"https://iconia.co.jp/en-us/{slug}",
            "reservation_url": f"https://iconia.co.jp/en-us/{slug}?booking=true",
            "map_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
            "address": prefecture, "access": "", "lat": lat, "lng": lng,
            "prefecture": prefecture, "region_id": _region_id(prefecture), "prefecture_id": _prefecture_id(prefecture),
        })
    return _store("mystays", sorted(hotels, key=lambda hotel: hotel["display_code"]))


def _map_coordinates(url: str) -> Tuple[Optional[float], Optional[float], str]:
    if not url:
        return None, None, ""
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            response.raise_for_status()
            resolved = response.url
            match = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", resolved)
            if not match:
                match = re.search(r"!3d(-?\d+(?:\.\d+)?)[^#]*!4d(-?\d+(?:\.\d+)?)", resolved + response.text)
            if match:
                return float(match.group(1)), float(match.group(2)), resolved
            if attempt < 2:
                time.sleep(0.25 * (attempt + 1))
        except requests.RequestException:
            if attempt < 2:
                time.sleep(0.25 * (attempt + 1))
    return None, None, url


def _daiwa_access_coordinates(official_url: str) -> Tuple[Optional[float], Optional[float]]:
    if not official_url:
        return None, None
    access_url = official_url.rstrip("/") + "/access/"
    try:
        response = requests.get(access_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None, None
    soup = BeautifulSoup(response.text, "html.parser")
    for iframe in soup.select("iframe[src]"):
        source = str(iframe.get("src") or "")
        match = re.search(r"!2d(-?\d+(?:\.\d+)?)!3d(-?\d+(?:\.\d+)?)", source)
        if match:
            return float(match.group(2)), float(match.group(1))
    return None, None


def _parse_daiwa_cards(page_html: str, source_url: str) -> Dict[str, Dict[str, Any]]:
    soup = BeautifulSoup(page_html, "html.parser")
    hotels: Dict[str, Dict[str, Any]] = {}
    for card in soup.select(".inner_list"):
        name_node = card.select_one("h3.name .n")
        booking = card.select_one('a[href*="reserve.daiwaroynet.jp"][href*="code="]')
        if not name_node or not booking:
            continue
        booking_url = urljoin(source_url, booking.get("href"))
        code = str((parse_qs(urlsplit(booking_url).query).get("code") or [""])[0])
        if not code:
            code_match = re.search(r"[?&]code=([^&#]+)", booking_url)
            code = code_match.group(1) if code_match else ""
        if not code or code in hotels:
            continue
        official = next((a for a in card.select(".box_btn a[href]") if "ホテルサイト" in a.get_text()), None)
        map_link = next((a for a in card.select(".box_btn a[href]") if "マップ" in a.get_text()), None)
        prefecture_node = card.select_one("h3.name .pref")
        prefecture = _prefecture_name(prefecture_node.get_text(" ", strip=True) if prefecture_node else "")
        hotels[code] = {
            "code": f"daiwa:{code}", "display_code": f"DR-{code[:6].upper()}",
            "provider": "daiwa", "brand": "daiwa", "booking_code": code,
            "name": name_node.get_text(" ", strip=True), "name_ja": name_node.get_text(" ", strip=True),
            "url": urljoin(source_url, official.get("href")) if official else source_url,
            "reservation_url": booking_url, "map_url": urljoin(source_url, map_link.get("href")) if map_link else "",
            "address": card.select_one("address").get_text(" ", strip=True) if card.select_one("address") else "",
            "access": card.select_one(".access").get_text(" ", strip=True) if card.select_one(".access") else "",
            "prefecture": prefecture, "region_id": _region_id(prefecture), "prefecture_id": _prefecture_id(prefecture),
        }
    return hotels


def _daiwa_catalog(force: bool = False) -> List[Dict[str, Any]]:
    cached = None if force else _cached("daiwa")
    if cached is not None:
        return cached
    ja_response = requests.get(DAIWA_HOTELS_URL, headers=HEADERS, timeout=30)
    ja_response.raise_for_status()
    hotels = _parse_daiwa_cards(ja_response.text, ja_response.url)
    try:
        en_response = requests.get("https://www.daiwaroynet.jp/en/hotelist/", headers=HEADERS, timeout=30)
        en_response.raise_for_status()
        english = _parse_daiwa_cards(en_response.text, en_response.url)
    except requests.RequestException:
        english = {}

    def enrich(item: Tuple[str, Dict[str, Any]]) -> Dict[str, Any]:
        code, hotel = item
        english_hotel = english.get(code, {})
        hotel["name_en"] = english_hotel.get("name_ja") or hotel["name_ja"]
        hotel["name_zh_cn"] = hotel["name_ja"]
        hotel["name_zh_tw"] = hotel["name_ja"]
        hotel["name_ko"] = hotel["name_ja"]
        lat, lng, resolved_map = _map_coordinates(hotel.get("map_url") or "")
        if lat is None or lng is None:
            lat, lng = _daiwa_access_coordinates(hotel.get("url") or "")
        hotel["lat"], hotel["lng"] = lat, lng
        hotel["map_url"] = resolved_map
        return hotel

    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="daiwa-map") as executor:
        result = list(executor.map(enrich, hotels.items()))
    return _store("daiwa", sorted(result, key=lambda hotel: hotel["display_code"]))


def fetch_provider_hotels(
    provider: str,
    primary_language: str = "zh_cn",
    force: bool = False,
) -> List[Dict[str, Any]]:
    if provider == "dormy":
        hotels = _dormy_catalog(force)
    elif provider == "mystays":
        hotels = _mystays_catalog(force)
    elif provider == "daiwa":
        hotels = _daiwa_catalog(force)
    else:
        return []
    return [_localized(hotel, primary_language) for hotel in hotels]


def build_booking_url(hotel: Dict[str, Any], start: str, end: str, adults: int, rooms: int) -> str:
    provider = str(hotel.get("provider") or "")
    if provider == "dormy":
        try:
            nights = max(1, (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days)
        except ValueError:
            nights = 1
        params = {
            "keyword": hotel.get("search_keyword") or hotel.get("name_ja") or hotel.get("name"),
            "checkin": start.replace("-", "/"), "number_of_nights": nights,
            "number_of_adults[]": max(1, int(adults)), "number_of_rooms": max(1, int(rooms)),
            "number_of_children_need_futons[]": 0, "number_of_children_no_need_futons[]": 0,
            "search_by_tag": "plan", "stock_check": "true",
        }
        return f"{DORMY_RESERVE_URL}?{urlencode(params, doseq=True)}"
    base = str(hotel.get("reservation_url") or hotel.get("url") or "")
    separator = "&" if "?" in base else "?"
    params = urlencode({
        "checkin_date": start, "checkout_date": end, "adults": max(1, int(adults)),
        "children": 0, "rooms": max(1, int(rooms)),
    })
    return f"{base}{separator}{params}"


def _tripla_room_map(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rooms: Dict[str, Dict[str, Any]] = {}
    for room in payload.get("rooms") or []:
        if not isinstance(room, dict):
            continue
        for plan in room.get("room_plan") or []:
            if not isinstance(plan, dict):
                continue
            key = str(plan.get("room_plan_code") or f"{room.get('room_type_code')}:{plan.get('hotel_plan_code')}")
            item = dict(plan)
            item["room_type_name"] = room.get("room_type_name") or "Room"
            item["is_smoking"] = room.get("is_smoking")
            item["inventory"] = plan.get("inventory", room.get("room_count"))
            rooms[key] = item
    return rooms


def fetch_tripla_offers(
    hotel: Dict[str, Any], start: str, end: str, adults: int, rooms: int, primary_language: str,
) -> Tuple[str, str, str, List[Dict[str, Any]], Dict[str, bool]]:
    booking_code = str(hotel.get("booking_code") or str(hotel.get("code") or "").split(":", 1)[-1])
    locale_map = {"zh_cn": "zh_Hans", "zh_tw": "zh_Hant", "ja": "ja", "ko": "ko", "en": "en"}
    locale = primary_language if primary_language in locale_map else "zh_cn"
    params = {"checkin_date": start, "checkout_date": end, "adults": max(1, int(adults)), "children": 0, "rooms": max(1, int(rooms))}
    primary_payload = _tripla_api_get(f"/hotels/{booking_code}/rooms", locale, params)
    primary_rooms = _tripla_room_map(primary_payload)
    has_available_room = any(
        str(room.get("availability") or "").lower() == "available"
        for room in primary_rooms.values()
    )
    english_rooms: Dict[str, Dict[str, Any]] = {}
    if locale == "en":
        english_rooms = primary_rooms
    elif has_available_room:
        english_rooms = _tripla_room_map(_tripla_api_get(f"/hotels/{booking_code}/rooms", "en", params))
    offers = []
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
        try:
            member_price = int(discount["total_price_after_discount"]) + int(discount.get("total_price_after_discount_tax") or 0) + int(discount.get("total_accommodation_tax") or 0)
        except (KeyError, TypeError, ValueError):
            member_price = None
        inventory = room.get("inventory")
        offers.append({
            "price_val": price, "price_text": f"¥{price:,}",
            "member_price_val": member_price, "member_price_text": f"¥{member_price:,}" if member_price is not None else None,
            "remaining_norm": str(inventory) if isinstance(inventory, int) else "≥1",
            "room_title": english.get("room_type_name") or room.get("room_type_name") or "Room",
            "room_title_primary": room.get("room_type_name") or "",
            "room_smoking": "smoking" if room.get("is_smoking") is True else "non_smoking" if room.get("is_smoking") is False else None,
            "plan_name": english.get("room_plan_name") or room.get("room_plan_name") or "",
        })
    name_primary = hotel.get(f"name_{primary_language}") or hotel.get("name_primary") or hotel.get("name_ja") or hotel.get("name") or ""
    name_en = hotel.get("name_en") or name_primary
    return name_primary, name_en, build_booking_url(hotel, start, end, adults, rooms), offers, {
        "had_any_offer": bool(primary_rooms), "had_any_non_ignored_offer": bool(primary_rooms), "had_any_ignored_offer": False,
    }


def fetch_dormy_offers(
    hotel: Dict[str, Any], start: str, end: str, adults: int, rooms: int, primary_language: str,
) -> Tuple[str, str, str, List[Dict[str, Any]], Dict[str, bool]]:
    try:
        nights = max(1, (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days)
    except ValueError:
        nights = 1
    params = {
        "keyword": hotel.get("search_keyword") or hotel.get("name_ja") or hotel.get("name"),
        "checkin": start.replace("-", "/"), "number_of_nights": nights,
        "number_of_rooms": max(1, int(rooms)), "number_of_adults[]": max(1, int(adults)),
        "number_of_children_need_futons[]": 0, "number_of_children_no_need_futons[]": 0,
        "stock_check": "true",
    }
    payload = _dormy_get("/rooms", "ja", params)
    hotel_id = int(hotel.get("provider_hotel_id") or str(hotel.get("code") or "").split(":", 1)[-1])
    offers = []
    found = False
    for group in payload.get("data") or []:
        if int((group.get("hotel") or {}).get("id") or 0) != hotel_id:
            continue
        found = True
        for room in group.get("rooms") or []:
            inventory = next((item for item in room.get("inventories") or [] if f"{item.get('year')}/{item.get('month_day')}" == start.replace("-", "/")), None)
            if not inventory or not inventory.get("is_available"):
                continue
            try:
                price = int(inventory.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            tags = {str(tag.get("value") or "") for tag in room.get("tags") or [] if isinstance(tag, dict)}
            title = str(room.get("name") or room.get("room_type_category") or "Room")
            if "禁煙" in title or "禁煙" in tags:
                smoking = "non_smoking"
            elif "喫煙" in title or "喫煙" in tags:
                smoking = "smoking"
            else:
                smoking = None
            offers.append({
                "price_val": price, "price_text": f"¥{price:,}",
                "member_price_val": None, "member_price_text": None,
                "remaining_norm": str(inventory.get("stock")) if inventory.get("stock") is not None else "≥1",
                "room_title": title, "room_title_primary": title,
                "room_smoking": smoking, "plan_name": "",
            })
    return (
        hotel.get("name_primary") or hotel.get("name") or "",
        hotel.get("name_en") or hotel.get("name") or "",
        build_booking_url(hotel, start, end, adults, rooms), offers,
        {"had_any_offer": found, "had_any_non_ignored_offer": found, "had_any_ignored_offer": False},
    )
