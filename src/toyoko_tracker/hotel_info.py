from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, Tuple
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .i18n import normalize_primary_language
from .parsing import _extract_next_data
from .settings import HEADERS, TIMEOUT


_LOCALE_PATHS = {
    "zh_cn": "china_cn",
    "zh_tw": "china",
    "ja": "",
    "ko": "korea",
}
_CACHE_TTL_SEC = 24 * 60 * 60
_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def official_hotel_url(code: str, primary_language: str) -> str:
    language = normalize_primary_language(primary_language)
    locale = _LOCALE_PATHS.get(language, "eng")
    prefix = f"/{locale}" if locale else ""
    return f"https://www.toyoko-inn.com{prefix}/search/detail/{code}/"


def _hotel_data(page_props: Dict[str, Any], code: str) -> Dict[str, Any]:
    queries = (((page_props.get("trpcState") or {}).get("json") or {}).get("queries") or [])
    for query in queries:
        data = ((query.get("state") or {}).get("data")) if isinstance(query, dict) else None
        if isinstance(data, dict) and str(data.get("hotelCode") or "").zfill(5) == code:
            return data
    raise ValueError("official hotel data not found")


def _schema_hotel(soup: BeautifulSoup) -> Dict[str, Any]:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("@type") == "Hotel":
            return payload
    return {}


def _formatted_address(schema: Dict[str, Any], hotel: Dict[str, Any], language: str) -> str:
    address = schema.get("address") if isinstance(schema.get("address"), dict) else {}
    postal = str(address.get("postalCode") or hotel.get("zipcode") or "").strip()
    region = str(address.get("addressRegion") or "").strip()
    locality = str(address.get("addressLocality") or hotel.get("city") or "").strip()
    street = str(address.get("streetAddress") or hotel.get("address") or "").strip()
    if language == "ja":
        return " ".join(part for part in [f"〒{postal}" if postal else "", f"{region}{locality}{street}"] if part)
    location = ", ".join(part for part in [street, locality] if part)
    region_postal = " ".join(part for part in [region, postal] if part)
    return " ".join(part for part in [location + ("," if location and region_postal else ""), region_postal, "Japan"] if part)


def parse_hotel_info_html(html_text: str, code: str, primary_language: str, source_url: str) -> Dict[str, Any]:
    code = str(code).zfill(5)
    language = normalize_primary_language(primary_language)
    soup = BeautifulSoup(html_text, "html.parser")
    next_data = _extract_next_data(html_text)
    if not next_data:
        raise ValueError("official page data is missing")
    page_props = ((next_data.get("props") or {}).get("pageProps") or {})
    hotel = _hotel_data(page_props, code)
    schema = _schema_hotel(soup)
    access_image = hotel.get("accessImage") if isinstance(hotel.get("accessImage"), dict) else {}
    map_image_url = str(access_image.get("image") or "").strip()
    if map_image_url and not re.match(r"^https://toyoko-inn\.imagewave\.pictures/", map_image_url):
        map_image_url = ""
    return {
        "code": code,
        "language": language,
        "name": str(hotel.get("name") or (page_props.get("metaData") or {}).get("name") or "").strip(),
        "address": _formatted_address(schema, hotel, language),
        "map_image_url": map_image_url,
        "google_map_url": str(hotel.get("googleMapUrl") or schema.get("hasMap") or "").strip(),
        "train_access": hotel.get("trainAccess") if isinstance(hotel.get("trainAccess"), list) else [],
        "car_access": hotel.get("carAccess") if isinstance(hotel.get("carAccess"), list) else [],
        "plane_access": hotel.get("planeAccess") if isinstance(hotel.get("planeAccess"), list) else [],
        "access_remarks": str(hotel.get("accessRemarks") or "").strip(),
        "official_url": source_url,
    }


def _schema_objects(soup: BeautifulSoup) -> list[Dict[str, Any]]:
    objects: list[Dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            objects.extend(item for item in candidate.get("@graph") or [] if isinstance(item, dict))
            objects.append(candidate)
    return objects


def _generic_schema_hotel(soup: BeautifulSoup) -> Dict[str, Any]:
    for item in _schema_objects(soup):
        schema_type = item.get("@type")
        types = schema_type if isinstance(schema_type, list) else [schema_type]
        if any(str(value).lower() in {"hotel", "lodgingbusiness", "resort"} for value in types):
            return item
    return {}


def _generic_address(schema: Dict[str, Any]) -> str:
    address = schema.get("address")
    if isinstance(address, str):
        return address.strip()
    if not isinstance(address, dict):
        return ""
    return " ".join(
        str(address.get(key) or "").strip()
        for key in ("postalCode", "addressRegion", "addressLocality", "streetAddress")
        if str(address.get(key) or "").strip()
    )


def _safe_page_asset(value: Any, source_url: str) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl") or ""
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    resolved = urljoin(source_url, raw_value)
    try:
        parsed = urlsplit(resolved)
        return resolved if parsed.scheme == "https" and "." in (parsed.hostname or "") else ""
    except ValueError:
        return ""


def parse_provider_hotel_info_html(
    html_text: str,
    hotel: Dict[str, Any],
    primary_language: str,
    source_url: str,
) -> Dict[str, Any]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    schema = _generic_schema_hotel(soup)
    image = _safe_page_asset(schema.get("image"), source_url)
    if not image:
        image_node = soup.select_one('meta[property="og:image"][content], meta[name="twitter:image"][content]')
        image = _safe_page_asset(image_node.get("content") if image_node else "", source_url)
    language = normalize_primary_language(primary_language)
    name = str(
        hotel.get(f"name_{language}") or hotel.get("name_primary") or schema.get("name")
        or hotel.get("name_ja") or hotel.get("name_en") or hotel.get("name") or ""
    ).strip()
    address = _generic_address(schema)
    if not address:
        address_node = soup.select_one(
            '[itemprop="address"], address, [class*="hotel-address"], a[href*="google.com/maps/dir"]'
        )
        candidate = " ".join(address_node.get_text(" ", strip=True).split()) if address_node else ""
        if 4 <= len(candidate) <= 300:
            address = candidate
    if not address:
        address = str(hotel.get("address") or hotel.get("address_en") or "").strip()
    access = str(hotel.get("access") or "").strip()
    if not access:
        access_node = soup.select_one('[class*="access-info"], [class*="access_detail"], [class*="access-detail"]')
        candidate = " ".join(access_node.get_text(" ", strip=True).split()) if access_node else ""
        if 4 <= len(candidate) <= 600:
            access = candidate
    if not access and str(hotel.get("provider") or "") == "mystays":
        description = soup.select_one('meta[name="description"][content]')
        candidate = " ".join(str(description.get("content") or "").split()) if description else ""
        if 4 <= len(candidate) <= 600 and any(word in candidate.lower() for word in ("walk", "station", "airport")):
            access = candidate
    return {
        "code": str(hotel.get("code") or ""),
        "provider": str(hotel.get("provider") or ""),
        "language": language,
        "name": name,
        "address": address,
        "map_image_url": image,
        "google_map_url": str(hotel.get("map_url") or schema.get("hasMap") or "").strip(),
        "lat": hotel.get("lat"),
        "lng": hotel.get("lng"),
        "train_access": [],
        "car_access": [],
        "plane_access": [],
        "access_remarks": access,
        "official_url": source_url,
    }


def get_provider_hotel_info(hotel: Dict[str, Any], primary_language: str) -> Dict[str, Any]:
    code = str(hotel.get("code") or "").strip()
    provider = str(hotel.get("provider") or "").strip()
    source_url = str(hotel.get("url") or "").strip()
    if not code or provider not in {"routeinn", "dormy", "mystays", "daiwa"}:
        raise ValueError("unsupported hotel provider")
    if urlsplit(source_url).scheme != "https":
        raise ValueError("invalid official hotel URL")
    language = normalize_primary_language(primary_language)
    cache_key = (code, language)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SEC:
            return dict(cached[1])
    try:
        response = requests.get(source_url, headers=HEADERS, timeout=min(TIMEOUT, 12))
        response.raise_for_status()
        info = parse_provider_hotel_info_html(response.text, hotel, language, response.url)
    except requests.RequestException:
        info = parse_provider_hotel_info_html("", hotel, language, source_url)
    with _CACHE_LOCK:
        if len(_CACHE) >= 600:
            oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
            _CACHE.pop(oldest, None)
        _CACHE[cache_key] = (now, dict(info))
    return info


def get_hotel_info(code: str, primary_language: str) -> Dict[str, Any]:
    code = str(code or "").strip().zfill(5)
    if not re.fullmatch(r"\d{5}", code):
        raise ValueError("invalid hotel code")
    language = normalize_primary_language(primary_language)
    cache_key = (code, language)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SEC:
            return dict(cached[1])

    url = official_hotel_url(code, language)
    response = requests.get(url, headers=HEADERS, timeout=min(TIMEOUT, 15))
    response.raise_for_status()
    info = parse_hotel_info_html(response.text, code, language, url)
    with _CACHE_LOCK:
        if len(_CACHE) >= 300:
            oldest = min(_CACHE, key=lambda key: _CACHE[key][0])
            _CACHE.pop(oldest, None)
        _CACHE[cache_key] = (now, dict(info))
    return info
