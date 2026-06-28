import re


# 语言代码映射
LANGUAGE_MAP = {
    # --- 中文与亚洲语言 ---
    "ChineseSimplified": "zh-cn",   # 简体中文
    "Chinese": "zh-cn",             # 中文 (默认/别名)
    "ChineseTraditional": "zh-tw",  # 繁体中文
    "Japanese": "ja",               # 日语
    "Korean": "ko",                 # 韩语
    
    # --- 英语 ---
    "English": "en",                # 英语

    # --- 欧洲主要语言 ---
    "French": "fr",                 # 法语
    "German": "de",                 # 德语
    "Italian": "it",                # 意大利语
    "Russian": "ru",                # 俄语
    "Spanish": "es",                # 西班牙语 (通常指西班牙)
    "SpanishLatin": "es-la",        # 拉美西班牙语
    "Portuguese": "pt",             # 葡萄牙语
    "PortugueseBrazilian": "pt-br", # 巴西葡萄牙语
    "Polish": "pl",                 # 波兰语

    # --- 北欧语言 ---
    "Swedish": "sv",                # 瑞典语
    "Danish": "da",                 # 丹麦语
    "Norwegian": "no",              # 挪威语
    "Finnish": "fi",                # 芬兰语

    # --- 东欧与中欧 ---
    "Czech": "cs",                  # 捷克语
    "Ukrainian": "uk",              # 乌克兰语
    "Hungarian": "hu",              # 匈牙利语
    "Romanian": "ro",               # 罗马尼亚语
    "Slovak": "sk",                 # 斯洛伐克语
    "Estonian": "et",               # 爱沙尼亚语
    
    # --- 其他 ---
    "Turkish": "tr",                # 土耳其语
    "Dutch": "nl",                  # 荷兰语
    "Greek": "el",                  # 希腊语
    "Catalan": "ca",                # 加泰罗尼亚语
    "Vietnamese": "vi",             # 越南语
    "Thai": "th",                   # 泰语
    "Arabic": "ar",                 # 阿拉伯语
    "Hebrew": "he"                  # 希伯来语
}


def _normalize_language_lookup_key(value: str) -> str:
    """
    将语言输入统一整理成可比较的 key。
    这里只做格式整理，不做映射。
    """
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""

    normalized = re.sub(r"\s*\(.*?\)\s*", "", normalized)
    normalized = normalized.replace("_", "-")
    normalized = re.sub(r"[\s/]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized


def normalize_language_code(value, default: str = "") -> str:
    """
    将各种语言写法统一成后端内部使用的标准语言码。
    """
    normalized = _normalize_language_lookup_key(value)
    if not normalized:
        return default

    compact = normalized.replace("-", "")

    # 常见中文别名直接兜住，避免前后端到处散落特殊判断。
    if normalized in ("zh", "zh-cn", "zh-hans") or compact in ("zh", "zhcn", "zhhans", "schinese"):
        return "zh-cn"
    if normalized in ("zh-tw", "zh-hant") or compact in ("zhtw", "zhhant", "tchinese"):
        return "zh-tw"

    # 其它情况优先匹配配置表中的目录名或标准码。
    for folder_name, short_code in LANGUAGE_MAP.items():
        folder_key = _normalize_language_lookup_key(folder_name)
        if normalized == short_code or compact == short_code.replace("-", ""):
            return short_code
        if normalized == folder_key or compact == folder_key.replace("-", ""):
            return short_code

    # 历史上偶尔出现 ua，统一收束到 uk。
    if normalized == "ua":
        return "uk"

    return normalized


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


def get_lang_by_code(code):
    """
    通过简码 (zh-cn) 反查文件夹前缀 (ChineseSimplified)。
    如果找不到，默认返回 English。
    """
    normalized = normalize_language_code(code)
    if not normalized:
        return "English"
    if normalized == "zh-cn":
        return "ChineseSimplified"
    if normalized == "zh-tw":
        return "ChineseTraditional"

    for name, short_code in LANGUAGE_MAP.items():
        if short_code == normalized and name != "Chinese":
            return name
    return "English"


if __name__ == '__main__':
    print(get_lang_by_code('ZH-cn'))
