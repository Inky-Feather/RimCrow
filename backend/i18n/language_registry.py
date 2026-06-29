from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class LanguageSpec:
    """
    项目内部统一语言定义。

    字段说明：
    - code: 项目内部标准语言码，使用常见 BCP 47 写法，例如 zh-CN、en、pt-BR。
    - english_name: 英文全名，同时覆盖 RimWorld Languages 目录名等需要英文标识的场景。
    - label: 原生显示名，直接给用户或 AI 使用，不再维护单独 label_zh / ai_label。
    - aliases: 历史写法、Steam 写法、目录别名等宽松输入。
    - steam_elanguage: Steam IPublishedFileService language 参数使用的 ELanguage 整数；None 表示 Steam 暂不支持。
    """

    code: str
    english_name: str
    label: str
    aliases: tuple[str, ...] = ()
    steam_elanguage: int | None = None


def _normalize_language_lookup_key(value: Any) -> str:
    """将语言输入统一整理成可比较 key；这里只做格式整理，不做映射。"""
    normalized = str(value or "").strip().lower()
    if not normalized: return ""
    normalized = re.sub(r"\s*\(.*?\)\s*", "", normalized)
    normalized = normalized.replace("_", "-")
    normalized = re.sub(r"[\s/]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def _canonicalize_language_tag(normalized: str) -> str:
    """
    将未知语言标记尽量整理成 BCP 47 常见大小写：
    主语言小写、地区大写、Script 首字母大写。
    """
    parts = [part for part in str(normalized or "").split("-") if part]
    if not parts: return ""

    canonical_parts = [parts[0].lower()]
    for part in parts[1:]:
        if part.isdigit():
            canonical_parts.append(part)
        elif len(part) == 2 and part.isalpha():
            canonical_parts.append(part.upper())
        elif len(part) == 4 and part.isalpha():
            canonical_parts.append(part.title())
        else:
            canonical_parts.append(part.lower())
    return "-".join(canonical_parts)


LANGUAGE_SPECS: tuple[LanguageSpec, ...] = (
    # --- 中文与亚洲语言 ---
    LanguageSpec("zh-CN", "ChineseSimplified", "简体中文", ("Chinese", "zh", "zh-Hans", "schinese", "Simplified_Chinese"), 6),  # 简体中文
    LanguageSpec("zh-TW", "ChineseTraditional", "繁體中文", ("zh-Hant", "tchinese", "Traditional_Chinese"), 7),  # 繁体中文
    LanguageSpec("ja", "Japanese", "日本語", ("ja-JP",), 10),  # 日语
    LanguageSpec("ko", "Korean", "한국어", ("ko-KR",), 4),  # 韩语
    LanguageSpec("vi", "Vietnamese", "Tiếng Việt", (), 28),  # 越南语
    LanguageSpec("th", "Thai", "ไทย", (), 9),  # 泰语
    LanguageSpec("id", "Indonesian", "Bahasa Indonesia"),  # 印尼语

    # --- 欧洲主要语言 ---
    LanguageSpec("en", "English", "English", (), 0),  # 英语
    LanguageSpec("fr", "French", "Français", (), 2),  # 法语
    LanguageSpec("de", "German", "Deutsch", (), 1),  # 德语
    LanguageSpec("it", "Italian", "Italiano", (), 3),  # 意大利语
    LanguageSpec("ru", "Russian", "Русский", (), 8),  # 俄语
    LanguageSpec("es", "Spanish", "Español", (), 5),  # 西班牙语
    LanguageSpec("es-419", "SpanishLatin", "Español LATAM", ("es-la", "Latam_Spanish"), 27),  # 西班牙语（拉丁）
    LanguageSpec("pt", "Portuguese", "Português", (), 11),  # 葡萄牙语
    LanguageSpec("pt-BR", "PortugueseBrazilian", "Português-BR", ("pt-br", "Brazilian"), 22),  # 葡萄牙语（巴西）
    LanguageSpec("pl", "Polish", "Polski", (), 12),  # 波兰语
    LanguageSpec("sv", "Swedish", "Svenska", (), 17),  # 瑞典语
    LanguageSpec("da", "Danish", "Dansk", (), 13),  # 丹麦语
    LanguageSpec("no", "Norwegian", "Norsk", (), 16),  # 挪威语
    LanguageSpec("fi", "Finnish", "Suomi", (), 15),  # 芬兰语
    LanguageSpec("cs", "Czech", "Čeština", (), 19),  # 捷克语
    LanguageSpec("uk", "Ukrainian", "Українська", ("ua",), 26),  # 乌克兰语
    LanguageSpec("hu", "Hungarian", "Magyar", (), 18),  # 匈牙利语
    LanguageSpec("ro", "Romanian", "Română", (), 20),  # 罗马尼亚语
    LanguageSpec("sk", "Slovak", "Slovenčina"),  # 斯洛伐克语
    LanguageSpec("et", "Estonian", "Eesti"),  # 爱沙尼亚语
    LanguageSpec("tr", "Turkish", "Türkçe", (), 21),  # 土耳其语
    LanguageSpec("nl", "Dutch", "Nederlands", (), 14),  # 荷兰语
    LanguageSpec("el", "Greek", "Ελληνικά", (), 24),  # 希腊语
    LanguageSpec("ca", "Catalan", "Català"),  # 加泰罗尼亚语

    # --- 中东与其它语言 ---
    LanguageSpec("ar", "Arabic", "العربية", (), 25),  # 阿拉伯语
    LanguageSpec("he", "Hebrew", "עברית"),  # 希伯来语
    LanguageSpec("bg", "Bulgarian", "Български", (), 23),  # 保加利亚语
)


def _build_language_indexes():
    by_code: dict[str, LanguageSpec] = {}
    by_lookup: dict[str, LanguageSpec] = {}
    by_steam_elanguage: dict[int, LanguageSpec] = {}

    for spec in LANGUAGE_SPECS:
        by_code[spec.code] = spec
        if spec.steam_elanguage is not None:
            by_steam_elanguage[spec.steam_elanguage] = spec
        for candidate in (spec.code, spec.english_name, spec.label, *spec.aliases):
            lookup_key = _normalize_language_lookup_key(candidate)
            if not lookup_key:
                continue
            by_lookup[lookup_key] = spec
            compact_key = lookup_key.replace("-", "")
            if compact_key and compact_key != lookup_key:
                by_lookup[compact_key] = spec
    return by_code, by_lookup, by_steam_elanguage


LANGUAGE_BY_CODE, LANGUAGE_BY_LOOKUP, LANGUAGE_BY_STEAM_ELANGUAGE = _build_language_indexes()
SUPPORTED_LANGUAGE_CODES = set(LANGUAGE_BY_CODE.keys())


def normalize_language_code(value: Any, default: str = "") -> str:
    """将语言目录名、语言码、Steam 名称等输入统一成项目内部标准语言码。"""
    normalized = _normalize_language_lookup_key(value)
    if normalized:
        compact_key = normalized.replace("-", "")
        matched = LANGUAGE_BY_LOOKUP.get(normalized) or LANGUAGE_BY_LOOKUP.get(compact_key)
        return matched.code if matched else _canonicalize_language_tag(normalized)

    fallback = _normalize_language_lookup_key(default)
    if not fallback:
        return ""
    matched = LANGUAGE_BY_LOOKUP.get(fallback) or LANGUAGE_BY_LOOKUP.get(fallback.replace("-", ""))
    return matched.code if matched else _canonicalize_language_tag(fallback)


def normalize_language_codes(values: Any) -> list[str]:
    """批量归一化语言码并去重，保持原始顺序。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        code = normalize_language_code(value)
        if not code or code in seen: continue
        seen.add(code)
        result.append(code)
    return result


def get_language_spec(value: Any) -> LanguageSpec | None:
    """按任意语言输入获取完整语言定义；未知语言返回 None。"""
    code = normalize_language_code(value)
    return LANGUAGE_BY_CODE.get(code)


def get_language_english_name(value: Any, default: str = "English") -> str:
    """返回统一英文全名，可用于 RimWorld 语言目录、AI 目标语言等场景。"""
    spec = get_language_spec(value)
    return spec.english_name if spec else default


def get_language_label(value: Any, default: str = "English") -> str:
    """返回原生显示名，适合前端下拉和自然语言提示。"""
    spec = get_language_spec(value)
    return spec.label if spec else default


def to_external_language(value: Any, target: str, default: str | int = "en") -> str | int:
    """
    通用外部语言参数转换。

    target:
    - "code": 返回项目标准语言码。
    - "english_name": 返回英文全名。
    - "label": 返回原生显示名。
    - "steam_elanguage": 返回 Steam ELanguage 整数。
    """
    normalized_target = str(target or "").strip().lower()
    if normalized_target == "code":
        return normalize_language_code(value, default=str(default or ""))
    if normalized_target == "english_name":
        return get_language_english_name(value, default=str(default or "English"))
    if normalized_target == "label":
        return get_language_label(value, default=str(default or "English"))
    if normalized_target == "steam_elanguage":
        return to_steam_elanguage(value, default=default)
    raise ValueError(f"不支持的语言转换目标: {target}")


def to_steam_elanguage(value: Any, default: str | int = "en") -> int:
    """将任意语言输入转换成 Steam ELanguage 整数。"""
    lookup_key = _normalize_language_lookup_key(value)
    if lookup_key in {"none", "default", "steam-default"}:
        return -1

    try:
        numeric_value = int(value)
        if numeric_value == -1 or numeric_value in LANGUAGE_BY_STEAM_ELANGUAGE:
            return numeric_value
    except (TypeError, ValueError):
        pass

    spec = get_language_spec(value)
    if spec and spec.steam_elanguage is not None:
        return spec.steam_elanguage

    try:
        default_value = int(default)
        return default_value if default_value == -1 or default_value in LANGUAGE_BY_STEAM_ELANGUAGE else 0
    except (TypeError, ValueError):
        default_spec = get_language_spec(default)
        return default_spec.steam_elanguage if default_spec and default_spec.steam_elanguage is not None else 0


def get_language_options(*, include_follow: bool = True, steam_only: bool = False) -> list[dict[str, object]]:
    """返回前端下拉可用语言选项。"""
    specs = [
        spec for spec in LANGUAGE_SPECS
        if not steam_only or spec.steam_elanguage is not None
    ]
    options = [
        {
            "label": spec.label,
            "value": spec.steam_elanguage if steam_only else spec.code,
            "code": spec.code,
            "name": spec.english_name,
        }
        for spec in specs
    ]
    if include_follow:
        return [{"label": "跟随界面语言", "value": "", "code": "", "name": "Auto"}, *options]
    return options


def get_steam_elanguage_options(include_follow: bool = True) -> list[dict[str, object]]:
    """返回 Steam ELanguage 下拉选项。"""
    return get_language_options(include_follow=include_follow, steam_only=True)
