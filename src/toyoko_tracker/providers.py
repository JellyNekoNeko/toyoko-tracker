from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple


@dataclass(frozen=True)
class ProviderCapabilities:
    area_search: bool = True
    radius_search: bool = True
    availability: bool = True
    room_inventory: bool = True
    room_type: bool = True
    smoking: bool = True
    member_price: bool = False
    hotel_info: bool = True
    coordinates: bool = True
    conditional_http: bool = False


@dataclass(frozen=True)
class ProviderPlugin:
    provider_id: str
    name: str
    name_en: str
    color: str
    scan_strategy: str
    catalog_strategy: str
    code_prefix: str = ""
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["id"] = data.pop("provider_id")
        return data


_LOCK = threading.RLock()
_REGISTRY: Dict[str, ProviderPlugin] = {}


def register_provider(plugin: ProviderPlugin, *, replace: bool = False) -> None:
    provider_id = str(plugin.provider_id or "").strip().lower()
    if not provider_id or provider_id != plugin.provider_id:
        raise ValueError("provider_id must be lowercase and non-empty")
    with _LOCK:
        if provider_id in _REGISTRY and not replace:
            raise ValueError(f"provider already registered: {provider_id}")
        _REGISTRY[provider_id] = plugin


def get_provider(provider_id: str) -> Optional[ProviderPlugin]:
    with _LOCK:
        return _REGISTRY.get(str(provider_id or "").strip().lower())


def providers() -> Tuple[ProviderPlugin, ...]:
    with _LOCK:
        return tuple(_REGISTRY.values())


def capability_matrix(enabled: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    enabled_set = set(enabled or ())
    items = []
    for plugin in providers():
        data = plugin.public_dict()
        data["enabled"] = plugin.provider_id in enabled_set if enabled is not None else True
        items.append(data)
    capability_names = list(ProviderCapabilities.__dataclass_fields__)
    return {"providers": items, "capabilities": capability_names}


def _install_builtin_plugins() -> None:
    builtins = (
        ProviderPlugin(
            "toyoko", "东横", "Toyoko Inn", "#2f73e8", "toyoko", "toyoko", "",
            ProviderCapabilities(member_price=True, conditional_http=True),
        ),
        ProviderPlugin(
            "routeinn", "露樱", "Route Inn Hotels", "#3b985c", "routeinn", "routeinn", "RI-",
            ProviderCapabilities(member_price=True),
        ),
        ProviderPlugin(
            "dormy", "多美迎", "Dormy Inn", "#d7822b", "dormy", "chain", "DM-",
            ProviderCapabilities(member_price=False),
        ),
        ProviderPlugin(
            "mystays", "MYSTAYS", "MYSTAYS Hotel", "#8255bd", "tripla", "chain", "MS-",
            ProviderCapabilities(member_price=False),
        ),
        ProviderPlugin(
            "daiwa", "大和ROYNET", "Daiwa Roynet", "#b58c31", "tripla", "chain", "DR-",
            ProviderCapabilities(member_price=False),
        ),
    )
    for plugin in builtins:
        register_provider(plugin)


_install_builtin_plugins()
