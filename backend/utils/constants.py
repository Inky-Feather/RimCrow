# 语言代码映射
LANGUAGE_MAP = {
    # --- 中文与亚洲语言 ---
    "ChineseSimplified": "zh-cn",   # 简体中文
    "Chinese": "zh-cn",             # 中文 (默认)
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
    "Ukrainian": "uk",              # 乌克兰语 (ISO标准通常是UK或UA，RimWorld社区多用UK)
    "Hungarian": "hu",              # 匈牙利语
    "Romanian": "ro",               # 罗马尼亚语
    "Slovak": "sk",                 # 斯洛伐克语
    "Estonian": "et",               # 爱沙尼亚语
    
    # --- 其他 ---
    "Turkish": "tr",                # 土耳其语
    "Dutch": "nl",                  # 荷兰语
    "Greek": "el",                  # 希腊语
    "Catalan": "ca",                # 加泰罗尼亚语
    "Vietnamese": "vi",             # 越南语 (社区汉化常见)
    "Thai": "th",                   # 泰语
    "Arabic": "ar",                 # 阿拉伯语
    "Hebrew": "he"                  # 希伯来语
}

def get_lang_by_code(code):
    """
    通过简码 (zh-cn) 反查文件夹前缀 (ChineseSimplified)。
    如果找不到，默认返回 English。
    """
    if not code:
        return 'English'
    code = code.lower()
    if code in ['zh-cn', 'zh-hans', 'zh']:
        return 'ChineseSimplified'
    for name, short_code in LANGUAGE_MAP.items():
        if short_code == code:
            return name
    return 'English'

if __name__ == '__main__':
    print(get_lang_by_code('ZH-cn'))