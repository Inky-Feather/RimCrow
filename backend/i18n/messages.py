from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.i18n.language_registry import get_language_label, normalize_language_code
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


def _locale_meta(payload: Mapping[str, Any]) -> dict[str, Any]:
    meta = payload.get("_meta") if isinstance(payload, Mapping) else {}
    return dict(meta) if isinstance(meta, Mapping) else {}


def _is_user_locale_payload(payload: Mapping[str, Any]) -> bool:
    meta_type = str(_locale_meta(payload).get("type") or "").strip()
    return meta_type == "user_locale"


def list_user_locale_options() -> list[dict[str, Any]]:
    """列出 data/locales 下的用户语言包；内置语言包由前端从已打包语言文件推导。"""
    options: dict[str, dict[str, Any]] = {}
    if USER_LOCALES_DIR.exists():
        for path in sorted(USER_LOCALES_DIR.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception:
                continue
            if not isinstance(payload, Mapping) or not _is_user_locale_payload(payload):
                continue
            meta = _locale_meta(payload)
            code = normalize_language_code(meta.get("language") or path.stem)
            if not code:
                continue
            label = str(meta.get("label") or get_language_label(code, code)).strip() or code
            options[code] = {"label": label, "value": code, "code": code, "name": str(meta.get("name") or code), "user": True}
    return list(options.values())


def create_user_locale(language: str, label: str = "") -> dict[str, Any]:
    """创建或更新用户语言包元数据；不写入任何翻译正文，正文由覆盖文件逐步保存。"""
    code = normalize_language_code(language)
    if not code:
        raise ValueError("语言代码不能为空")
    payload = load_user_locale(code)
    meta = _locale_meta(payload)
    meta["language"] = code
    meta["label"] = str(label or meta.get("label") or get_language_label(code, code)).strip() or code
    meta.setdefault("type", "user_locale")
    payload["_meta"] = meta
    write_json(USER_LOCALES_DIR / f"{code}.json", payload)
    return {"language": code, "label": meta["label"], "path": str(USER_LOCALES_DIR / f"{code}.json")}


def set_nested(payload: dict[str, Any], dotted_key: str, value: str) -> None:
    parts = [part for part in str(dotted_key or "").split(".") if part]
    if not parts:
        raise ValueError("语言包 key 不能为空")
    current = payload
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = str(value or "")


def delete_nested(payload: dict[str, Any], dotted_key: str) -> bool:
    parts = [part for part in str(dotted_key or "").split(".") if part]
    if not parts:
        raise ValueError("语言包 key 不能为空")
    current = payload
    parents: list[tuple[dict[str, Any], str]] = []
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            return False
        parents.append((current, part))
        current = child
    if parts[-1] not in current:
        return False
    del current[parts[-1]]
    for parent, part in reversed(parents):
        child = parent.get(part)
        if isinstance(child, dict) and not child:
            del parent[part]
        else:
            break
    return True


def save_user_locale_message(language: str, key: str, value: str) -> dict[str, str]:
    """保存单条用户语言覆盖；只写 data/locales，不改内置语言包。"""
    code = normalize_language_code(language, default=DEFAULT_LOCALE) or DEFAULT_LOCALE
    normalized_key = str(key or "").strip()
    if not normalized_key:
        raise ValueError("语言包 key 不能为空")
    payload = load_user_locale(code)
    set_nested(payload, normalized_key, value)
    write_json(USER_LOCALES_DIR / f"{code}.json", payload)
    return {"language": code, "key": normalized_key}


def delete_user_locale_message(language: str, key: str) -> dict[str, Any]:
    """删除单条用户语言覆盖；用于把空白编辑恢复为内置语言包文本。"""
    code = normalize_language_code(language, default=DEFAULT_LOCALE) or DEFAULT_LOCALE
    normalized_key = str(key or "").strip()
    if not normalized_key:
        raise ValueError("语言包 key 不能为空")
    payload = load_user_locale(code)
    deleted = delete_nested(payload, normalized_key)
    if deleted:
        write_json(USER_LOCALES_DIR / f"{code}.json", payload)
    return {"language": code, "key": normalized_key, "deleted": deleted}


def save_user_locale_messages(language: str, messages: Mapping[str, Any]) -> dict[str, Any]:
    """批量保存用户语言覆盖；一次读取和写入，避免逐条保存反复改同一个文件。"""
    code = normalize_language_code(language, default=DEFAULT_LOCALE) or DEFAULT_LOCALE
    if not isinstance(messages, Mapping) or not messages:
        raise ValueError("语言包内容不能为空")
    payload = load_user_locale(code)
    saved_keys: list[str] = []
    for key, value in messages.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("语言包 key 不能为空")
        set_nested(payload, normalized_key, str(value or ""))
        saved_keys.append(normalized_key)
    write_json(USER_LOCALES_DIR / f"{code}.json", payload)
    return {"language": code, "count": len(saved_keys), "keys": saved_keys}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
