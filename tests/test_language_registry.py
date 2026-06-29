from backend.i18n.language_registry import (
    get_language_english_name,
    get_language_label,
    get_language_options,
    normalize_language_code,
    normalize_language_codes,
    to_external_language,
    to_steam_elanguage,
)


def test_language_registry_normalizes_common_aliases():
    assert normalize_language_code("ChineseSimplified") == "zh-CN"
    assert normalize_language_code("Simplified_Chinese") == "zh-CN"
    assert normalize_language_code("schinese") == "zh-CN"
    assert normalize_language_code("PortugueseBrazilian") == "pt-BR"
    assert normalize_language_codes(["zh", "zh-CN", "English"]) == ["zh-CN", "en"]


def test_language_registry_exposes_unified_names_and_labels():
    assert get_language_english_name("zh-CN") == "ChineseSimplified"
    assert get_language_label("zh-CN") == "简体中文"
    assert to_external_language("zh-CN", "english_name") == "ChineseSimplified"
    assert to_external_language("zh-CN", "label") == "简体中文"


def test_language_registry_maps_steam_elanguage():
    assert to_steam_elanguage("en") == 0
    assert to_steam_elanguage("zh-CN") == 6
    assert to_steam_elanguage("Traditional_Chinese") == 7
    assert to_steam_elanguage("PortugueseBrazilian") == 22
    assert to_steam_elanguage("none") == -1


def test_language_registry_builds_options():
    options = get_language_options(steam_only=True)
    assert options[0]["value"] == ""
    assert any(option["value"] == 6 and option["code"] == "zh-CN" for option in options)
