from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .settings import BASE_URL


class RenderedPage:
    def __init__(self, soup: BeautifulSoup, visible_text: str):
        self.soup = soup
        self.visible_text = visible_text


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
    offers: List[Dict[str, Any]] = []
    had_any_offer = False
    had_any_non_ignored_offer = False
    had_any_ignored_offer = False

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
            offer_url = urljoin(BASE_URL, link_el.get("href"))

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

        remaining_text = None
        block_text = child.get_text(" ", strip=True)
        m = re.search(r"Only\s+\d+\s+Rooms?\s+Left", block_text, re.I)
        if m:
            remaining_text = m.group(0)
        elif re.search(r"\bReserve\b", block_text, re.I):
            remaining_text = "Reserve"

        has_price = (price_val is not None)
        if has_price:
            nonlocal had_any_offer
            had_any_offer = True

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

    return offers, {
        "had_any_offer": had_any_offer,
        "had_any_non_ignored_offer": had_any_non_ignored_offer,
        "had_any_ignored_offer": had_any_ignored_offer,
    }


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
    if "single" in t:
        return "single"
    if "double" in t:
        return "double"
    if "twin" in t:
        return "twin"
    return None


def _offer_matches_smoking_preference(offer: Dict[str, Any], smoking_preference: Optional[str]) -> bool:
    pref = str(smoking_preference or "all")
    if pref == "all":
        return True
    room_smoking = offer.get("room_smoking")
    if pref == "noSmoking":
        return room_smoking == "non_smoking"
    if pref == "Smoking":
        return room_smoking == "smoking"
    return True


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

    return offers, {
        "had_any_offer": had_any_offer,
        "had_any_non_ignored_offer": had_any_non_ignored_offer,
        "had_any_ignored_offer": had_any_ignored_offer,
    }
