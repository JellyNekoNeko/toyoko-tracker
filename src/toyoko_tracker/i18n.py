from __future__ import annotations

from typing import Any

from .settings import DEFAULT_PRIMARY_LANGUAGE

LANGUAGE_OPTIONS = {
    "zh_cn": {"label": "中文(简体)", "english": "Simplified Chinese", "name_key": "name_full_zh_cn", "short_key": "name_zh_cn"},
    "zh_tw": {"label": "中文(繁體)", "english": "Traditional Chinese", "name_key": "name_full_zh_tw", "short_key": "name_zh_tw"},
    "ja": {"label": "日本語", "english": "Japanese", "name_key": "name_full_ja", "short_key": "name_ja"},
    "ko": {"label": "한국어", "english": "Korean", "name_key": "name_full_ko", "short_key": "name_ko"},
    "en": {"label": "English", "english": "English", "name_key": "name_full_en", "short_key": "name_en"},
}


def normalize_primary_language(value: Any) -> str:
    value = str(value or DEFAULT_PRIMARY_LANGUAGE)
    return value if value in LANGUAGE_OPTIONS else DEFAULT_PRIMARY_LANGUAGE
