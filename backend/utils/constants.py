import re


def _normalize_language_lookup_key(value: str) -> str:
    """
    将语言输入统一整理成可比较的 key。
    这里只做格式整理，不做映射。
    """
    normalized = str(value or "").strip().lower()
    if not normalized: return ""

    normalized = re.sub(r"\s*\(.*?\)\s*", "", normalized)
    normalized = normalized.replace("_", "-")
    normalized = re.sub(r"[\s/]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def _canonicalize_language_tag(normalized: str) -> str:
    """
    将已整理过的语言标记尽量收束到常见 BCP 47 书写形式。

    这里只做大小写层面的标准化：
    - 主语言小写，如 `en`
    - 地区大写，如 `zh-CN`
    - Script 首字母大写，如 `sr-Latn`
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


LANGUAGE_SPECS = (
    # --- 中文与亚洲语言 ---
    ("ChineseSimplified", "zh-CN", ("Chinese", "zh", "zh-Hans", "schinese")),   # 简体中文
    ("ChineseTraditional", "zh-TW", ("zh-Hant", "tchinese")),   # 繁体中文
    ("Japanese", "ja", ("ja-JP",)), # 日语
    ("Korean", "ko", ("ko-KR",)), # 韩语
    # --- 欧洲主要语言 ---
    ("English", "en", ()),  # 英语
    ("French", "fr", ()),   # 法语
    ("German", "de", ()),   # 德语
    ("Italian", "it", ()),   # 意大利语
    ("Russian", "ru", ()),   # 俄语
    ("Spanish", "es", ()),   # 西班牙语
    ("SpanishLatin", "es-419", ("es-la",)),   # 西班牙语（拉丁）
    ("Portuguese", "pt", ()),   # 葡萄牙语
    ("PortugueseBrazilian", "pt-BR", ("pt-br",)),   # 葡萄牙语（巴西）
    ("Polish", "pl", ()),   # 波兰语
    ("Swedish", "sv", ()),   # 瑞典语
    ("Danish", "da", ()),   # 丹麦语    
    ("Norwegian", "no", ()),   # 挪威语
    ("Finnish", "fi", ()),   # 芬兰语
    ("Czech", "cs", ()),   # 捷克语
    ("Ukrainian", "uk", ("ua",)),   # 乌克兰语
    ("Hungarian", "hu", ()),     # 匈牙利语
    ("Romanian", "ro", ()),     # 罗马尼亚语
    ("Slovak", "sk", ()),     # 斯洛伐克语
    ("Estonian", "et", ()),     # 爱沙尼亚语
    ("Turkish", "tr", ()),     # 土耳其语
    ("Dutch", "nl", ()),     # 荷兰语
    ("Greek", "el", ()),     # 希腊语
    ("Catalan", "ca", ()),   # 加泰罗尼亚语
    ("Vietnamese", "vi", ()),   # 越南语
    ("Thai", "th", ()),   # 泰语
    ("Arabic", "ar", ()),   # 阿拉伯语
    ("Hebrew", "he", ()),   # 希伯来语
    ("Bulgarian", "bg", ()),   # 保加利亚语
    ("Indonesian", "id", ()),   # 印尼语
)


def _build_language_maps() -> tuple[dict[str, str], dict[str, str], dict[str, str], set[str]]:
    """
    构建语言别名索引。

    - `LANGUAGE_MAP` 保留“目录名 -> 标准语言码”的主映射，便于扫描 Languages 目录。
    - `_LANGUAGE_CODE_LOOKUP` 额外收纳目录名、标准语言码和历史别名，便于宽松读取旧数据。
    - `_LANGUAGE_FOLDER_LOOKUP` 用于把标准语言码反查回 RimWorld 使用的目录前缀。
    """
    folder_map: dict[str, str] = {}
    code_lookup: dict[str, str] = {}
    folder_lookup: dict[str, str] = {}
    steam_codes: set[str] = set()

    for folder_name, canonical_code, aliases in LANGUAGE_SPECS:
        folder_map[folder_name] = canonical_code
        folder_lookup[canonical_code] = folder_name
        steam_codes.add(canonical_code)

        for candidate in (folder_name, canonical_code, *aliases):
            lookup_key = _normalize_language_lookup_key(candidate)
            if not lookup_key:
                continue
            code_lookup[lookup_key] = canonical_code
            compact_key = lookup_key.replace("-", "")
            if compact_key and compact_key != lookup_key:
                code_lookup[compact_key] = canonical_code

    return folder_map, code_lookup, folder_lookup, steam_codes


LANGUAGE_MAP, _LANGUAGE_CODE_LOOKUP, _LANGUAGE_FOLDER_LOOKUP, STEAM_WEBAPI_LANGUAGE_CODES = _build_language_maps()


def _resolve_canonical_language_code(lookup_key: str) -> str:
    """
    将比较用 key 解析成内部标准语言码。

    优先命中预置语言别名；命不中时，再按通用语言标记规则整理大小写。
    这样既能兼容旧配置，又不会把未知语言码粗暴压成全小写。
    """
    if not lookup_key: return ""

    compact_key = lookup_key.replace("-", "")
    matched = _LANGUAGE_CODE_LOOKUP.get(lookup_key) or _LANGUAGE_CODE_LOOKUP.get(compact_key)
    if matched: return matched
    return _canonicalize_language_tag(lookup_key)


def normalize_language_code(value, default: str = "") -> str:
    """
    将各种语言写法统一成后端内部使用的标准语言码。
    """
    normalized = _normalize_language_lookup_key(value)
    if normalized: return _resolve_canonical_language_code(normalized)

    fallback = _normalize_language_lookup_key(default)
    return _resolve_canonical_language_code(fallback) if fallback else ""


def normalize_language_codes(values) -> list[str]:
    """
    批量归一化并去重，保持原有顺序。
    """
    result = []
    seen = set()
    for value in values or []:
        language_code = normalize_language_code(value)
        if not language_code or language_code in seen:
            continue
        seen.add(language_code)
        result.append(language_code)
    return result


def to_steam_webapi_language_code(value, default: str = "en") -> str:
    """
    将内部语言码转换成 Steamworks Web API 支持的语言码。

    Steam 的语言参数支持集合是有限的，这里先把输入收束成标准语言码，
    再验证是否属于 Steam 支持的值；不支持时统一回退默认语言。
    """
    normalized_default = normalize_language_code(default, default="en") or "en"
    if normalized_default not in STEAM_WEBAPI_LANGUAGE_CODES:
        normalized_default = "en"

    normalized = normalize_language_code(value, default=normalized_default)
    if not normalized: return normalized_default
    return normalized if normalized in STEAM_WEBAPI_LANGUAGE_CODES else normalized_default


def get_lang_by_code(code):
    """
    通过标准语言码反查 RimWorld 语言目录前缀。
    如果找不到，默认返回 English。
    """
    normalized = normalize_language_code(code)
    if not normalized: return "English"
    return _LANGUAGE_FOLDER_LOOKUP.get(normalized, "English")


if __name__ == '__main__':
    print(get_lang_by_code('zh-CN'))
