from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.i18n.language_registry import normalize_language_code
from backend.settings import DATA_DIR


DEFAULT_LOCALE = "zh-CN"
USER_LOCALES_DIR = DATA_DIR / "locales"


class LocalizedText(str):
    """携带 i18n key 的字符串；旧调用仍可按普通字符串使用。"""

    message_key: str
    message_params: dict[str, Any]
    default_text: str

    def __new__(cls, key: str, default_text: str, params: Mapping[str, Any] | None = None):
        normalized_params = dict(params or {})
        rendered = _format_default(default_text, normalized_params)
        value = super().__new__(cls, rendered)
        value.message_key = str(key or "").strip()
        value.message_params = normalized_params
        value.default_text = str(default_text or "")
        return value


def _format_default(default_text: str, params: Mapping[str, Any]) -> str:
    if not params:
        return str(default_text or "")
    try:
        return str(default_text or "").format(**params)
    except (KeyError, ValueError):
        return str(default_text or "")


def tr(key: str, default_text: str, params: Mapping[str, Any] | None = None, **kwargs: Any) -> LocalizedText:
    """声明一条可提取的后端用户可见文案。"""
    merged = dict(params or {})
    merged.update(kwargs)
    return LocalizedText(key, default_text, merged)


def localized_key(value: Any) -> str:
    return str(getattr(value, "message_key", "") or "").strip()


def localized_params(value: Any) -> dict[str, Any]:
    params = getattr(value, "message_params", None)
    return dict(params or {}) if isinstance(params, Mapping) else {}


def deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """递归合并语言包；用户文件只需要写想覆盖的 key。"""
    result = dict(base or {})
    for key, value in dict(override or {}).items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_user_locale(language: str) -> dict[str, Any]:
    code = normalize_language_code(language, default=DEFAULT_LOCALE) or DEFAULT_LOCALE
    path = USER_LOCALES_DIR / f"{code}.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
