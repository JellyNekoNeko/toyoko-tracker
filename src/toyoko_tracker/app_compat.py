from __future__ import annotations

import sys
from typing import Any, Optional

from . import runtime as _runtime
from .models import AppConfig, HotelResult
from .parsing import RenderedPage, _parse_price_int, parse_remaining


def _sync_patchable_runtime_symbols() -> None:
    app_module = sys.modules.get("toyoko_tracker.app")
    for name in (
        "fetch_rendered_any",
        "_all_hotels_for_radius",
        "_geocode_nominatim",
        "_geocode_google_maps",
        "_geocode_location",
    ):
        if app_module is not None and hasattr(app_module, name):
            setattr(_runtime, name, getattr(app_module, name))
        elif name in globals():
            setattr(_runtime, name, globals()[name])


def check_hotel(cfg: AppConfig, renderer: Optional[Any], code: str, start: str, end: str) -> HotelResult:
    _sync_patchable_runtime_symbols()
    return _runtime.check_hotel(cfg, renderer, code, start, end)


def check_hotel_http(cfg: AppConfig, code: str, start: str, end: str) -> HotelResult:
    _sync_patchable_runtime_symbols()
    return _runtime.check_hotel_http(cfg, code, start, end)


def check_hotel_playwright(cfg: AppConfig, renderer: Optional[Any], code: str, start: str, end: str) -> HotelResult:
    _sync_patchable_runtime_symbols()
    return _runtime.check_hotel_playwright(cfg, renderer, code, start, end)


def _hotels_within_radius(query: str, radius_km: int, primary_language: Optional[str] = None):
    _sync_patchable_runtime_symbols()
    return _runtime._hotels_within_radius(query, radius_km, primary_language)


def __getattr__(name: str) -> Any:
    return getattr(_runtime, name)


requests = _runtime.requests
json = _runtime.json
BeautifulSoup = _runtime.BeautifulSoup
fetch_rendered_any = _runtime.fetch_rendered_any
_all_hotels_for_radius = _runtime._all_hotels_for_radius
_geocode_nominatim = _runtime._geocode_nominatim
_geocode_google_maps = _runtime._geocode_google_maps
_geocode_location = _runtime._geocode_location
_parse_coordinate_query = _runtime._parse_coordinate_query
_extract_maps_coordinates = _runtime._extract_maps_coordinates
_haversine_km = _runtime._haversine_km

__all__ = [
    "AppConfig",
    "HotelResult",
    "RenderedPage",
    "_parse_price_int",
    "parse_remaining",
    "check_hotel",
    "check_hotel_http",
    "check_hotel_playwright",
    "_hotels_within_radius",
    "requests",
    "json",
    "BeautifulSoup",
    "fetch_rendered_any",
    "_all_hotels_for_radius",
    "_geocode_nominatim",
    "_geocode_google_maps",
    "_geocode_location",
    "_parse_coordinate_query",
    "_extract_maps_coordinates",
    "_haversine_km",
]
