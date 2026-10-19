import json
from pathlib import Path

import pytest

from backend.i18n.messages import deep_merge, localized_key, localized_params, tr
from backend.i18n.language_registry import get_language_english_name, get_language_label, get_language_options, normalize_language_code, normalize_language_codes, to_external_language, to_steam_elanguage


def test_initial_language_choices_match_builtin_locale_files():
    from backend.settings import _BUILTIN_UI_LANGUAGE_CODES

    locales = Path(__file__).resolve().parents[1] / "frontend" / "src" / "locales"
    codes = {json.loads(path.read_text(encoding="utf-8"))["_meta"]["language"] for path in locales.glob("*.json")}
    assert _BUILTIN_UI_LANGUAGE_CODES == codes


@pytest.mark.parametrize("language, expected", [
    ("zh_CN", "zh-CN"), ("zh_SG", "zh-CN"), ("zh_TW", "zh-TW"),
    ("zh_HK", "zh-TW"), ("zh_MO", "zh-TW"), ("zh-Hant-CN", "zh-TW"),
    ("zh-Hans-HK", "zh-CN"), ("en_GB", "en"), ("de_AT.UTF-8", "de"),
    ("ko_KR.UTF-8", "ko"), ("ru_RU.UTF-8", "ru"), ("ja_JP", "en"),
    ("fr_FR", "en"), ("C.UTF-8", "en"), ("", "en"),
])
def test_initial_language_matches_available_ui_languages(monkeypatch, language, expected):
    import backend.settings as settings_module

    monkeypatch.setattr(settings_module.sys, "platform", "linux")
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(settings_module.locale, "getlocale", lambda: (language, None))
    assert settings_module._detect_initial_language() == expected


def test_initial_language_uses_message_locale_priority(monkeypatch):
    import backend.settings as settings_module

    monkeypatch.setattr(settings_module.sys, "platform", "linux")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LC_MESSAGES", "ko_KR.UTF-8")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    assert settings_module._detect_initial_language() == "ko"
    monkeypatch.setenv("LC_ALL", "ru_RU.UTF-8")
    assert settings_module._detect_initial_language() == "ru"


def test_initial_language_reads_windows_ui_language_and_handles_failure(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    import backend.settings as settings_module

    monkeypatch.setattr(settings_module.sys, "platform", "win32")
    kernel32 = SimpleNamespace(GetUserDefaultUILanguage=lambda: 0x0404)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)
    assert settings_module._detect_initial_language() == "zh-TW"
    kernel32.GetUserDefaultUILanguage = lambda: 0
    assert settings_module._detect_initial_language() == "en"

    def fail():
        raise OSError("UI language unavailable")

    kernel32.GetUserDefaultUILanguage = fail
    assert settings_module._detect_initial_language() == "en"


@pytest.mark.parametrize("current, backup, detected, expected, enabled", [
    (None, None, "de", "de", False), (None, None, "zh-CN", "zh-CN", True),
    (None, None, "zh-TW", "zh-TW", False), (None, None, "en", "en", False),
    ({"language": "zh-CN", "network": {"github_hosts_auto_update": False}}, None, None, "zh-CN", False),
    (None, {"language": "ko"}, None, "ko", False),
    ({"language": "ja"}, {"language": "en"}, None, "ja", False),
    ({"run_count": 1}, None, None, "zh-CN", False),
])
def test_initial_language_and_hosts_only_apply_without_saved_config(monkeypatch, current, backup, detected, expected, enabled):
    import backend.settings as settings_module

    manager = object.__new__(settings_module.SettingsManager)
    manager.config = settings_module.AppConfig()
    manager.last_relocation = None
    monkeypatch.setattr(manager, "_read_config_fragment", lambda _path, source: current if source == "current" else backup)
    monkeypatch.setattr(manager, "_normalize_config", lambda: None)
    monkeypatch.setattr(manager, "_sync_derived_paths", lambda: None)
    monkeypatch.setattr(manager, "_is_config_valid", lambda: True)
    monkeypatch.setattr(manager, "save", lambda: None)

    def detect():
        assert current is None and backup is None
        return detected

    monkeypatch.setattr(settings_module, "_detect_initial_language", detect)
    manager._load_to_config()
    assert manager.config.language == expected
    assert manager.config.network.github_hosts_enabled is enabled
    assert manager.config.network.github_hosts_auto_update is (current or {}).get("network", {}).get("github_hosts_auto_update", True)


@pytest.mark.parametrize("last, current, language, initially_enabled, should_enable", [
    ("0.24.11", "0.24.13", "zh-CN", False, True),
    ("v0.24.12", "0.25.0", "zh-CN", False, True),
    ("0.24.12", "0.24.13", "zh_CN", False, True),
    ("0.24.12", "0.24.13", "zh-TW", False, False),
    ("0.24.12", "0.24.13", "en", False, False),
    ("0.24.13", "0.25.0", "zh-CN", False, False),
    ("0.24.12", "0.24.12", "zh-CN", False, False),
    ("0.24.12", "0.24.11", "zh-CN", False, False),
    ("0.24.12", "0.24.13", "zh-CN", True, True),
])
def test_hosts_upgrade_migration_respects_version_and_language(monkeypatch, last, current, language, initially_enabled, should_enable):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import backend.migrations.app_upgrade as app_upgrade
    import backend.managers.mgr_network as network_module
    from backend.settings import AppConfig

    config = AppConfig(language=language)
    config.network.github_hosts_enabled = initially_enabled
    config.network.github_hosts_auto_update = False
    mock_settings = SimpleNamespace(config=config, save=Mock())
    mock_network = Mock()
    monkeypatch.setattr(app_upgrade, "settings", mock_settings)
    monkeypatch.setattr(network_module, "network_mgr", mock_network)

    app_upgrade.run_app_upgrade_migrations(last, current)
    assert config.network.github_hosts_enabled is should_enable
    assert config.network.github_hosts_auto_update is False
    assert config.network.write_to_system_hosts is False
    changed = should_enable and not initially_enabled
    assert mock_settings.save.call_count == int(changed)
    assert mock_network.apply.call_count == int(changed)

    # 新版本已记录后，后续升级不能重新打开用户手动关闭的开关。
    config.network.github_hosts_enabled = False
    app_upgrade.run_app_upgrade_migrations("0.24.13", "0.25.0")
    assert config.network.github_hosts_enabled is False


def test_tr_keeps_default_text_and_message_meta():
    message = tr("tasks.demo.progress", "处理 {count} 项", {"count": 3})

    assert str(message) == "处理 3 项"
    assert localized_key(message) == "tasks.demo.progress"
    assert localized_params(message) == {"count": 3}


def test_deep_merge_allows_partial_user_locale_override():
    base = {"ui": {"title": "标题", "button": {"save": "保存", "cancel": "取消"}}}
    override = {"ui": {"button": {"save": "立即保存"}}}

    assert deep_merge(base, override) == {
        "ui": {"title": "标题", "button": {"save": "立即保存", "cancel": "取消"}}
    }


def test_api_response_attaches_message_key_and_params():
    from backend.api import ApiResponse

    response = ApiResponse.success(
        message=tr("api.demo.done", "{name}已完成", {"name": "任务"})
    )

    assert response["status"] == "success"
    assert response["message"] == "任务已完成"
    assert response["message_key"] == "api.demo.done"
    assert response["message_params"] == {"name": "任务"}


def test_api_response_serializes_dataclass_localized_text_field():
    from dataclasses import dataclass
    from backend.api import ApiResponse

    @dataclass
    class DemoPayload:
        message: str

    response = ApiResponse.success(data={"payload": DemoPayload(tr("api.demo.started", "已开始"))})

    assert response["data"]["payload"]["message"] == "已开始"


def test_extract_locale_payload_is_generated_from_source_keys():
    from scripts.extract_i18n_messages import build_locale_payload, flatten_string_values

    payload = build_locale_payload(
        {"_meta": {"language": "zh-CN", "label": "简体中文"}, "ui": {"demo": {"title": "旧标题", "kept": "保留"}}},
        {"ui.demo.title": "新标题"},
    )

    assert payload["_meta"] == {"language": "zh-CN", "label": "简体中文"}
    assert payload["ui"]["demo"]["title"] == "新标题"
    assert list(payload) == ["_meta", "ui"]
    assert "ui.demo.kept" not in flatten_string_values(payload)


def test_flatten_string_values_ignores_namespace_only_nodes():
    from scripts.extract_i18n_messages import flatten_string_values

    assert set(flatten_string_values({"ui": {"title": "标题", "empty": {}}, "logs": {}})) == {"ui.title"}


def test_flatten_string_values_ignores_locale_meta():
    from scripts.extract_i18n_messages import flatten_string_values

    assert set(flatten_string_values({"_meta": {"language": "de", "label": "Deutsch"}, "ui": {"title": "标题"}})) == {"ui.title"}


def test_flatten_structure_paths_keeps_empty_nodes():
    from scripts.extract_i18n_messages import flatten_structure_paths

    assert flatten_structure_paths({"_meta": {"language": "en"}, "ui": {"title": "Title"}, "logs": {}}) == ["ui", "ui.title", "logs"]


def test_align_locale_structure_keeps_scope_and_empty_nodes():
    from scripts.extract_i18n_messages import align_locale_structure

    payload = align_locale_structure(
        {"ui": {"title": "标题"}, "logs": {}},
        {"_meta": {"language": "en"}, "title": "Wrong scope", "ui": {"title": "Title"}},
    )

    assert list(payload) == ["_meta", "ui", "logs", "title"]
    assert payload["ui"]["title"] == "Title"
    assert payload["logs"] == {}
    assert payload["title"] == "Wrong scope"


def test_builtin_locale_check_validates_file_meta_without_fixed_registry(tmp_path, monkeypatch):
    import scripts.extract_i18n_messages as extractor

    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    (locales_dir / "zh-CN.json").write_text(json.dumps({"_meta": {"type": "builtin_locale", "language": "zh-CN", "label": "简体中文", "name": "ChineseSimplified"}, "ui": {"title": "标题"}}), encoding="utf-8")
    (locales_dir / "en.json").write_text(json.dumps({"ui": {"title": "Title"}}), encoding="utf-8")
    (locales_dir / "zz-copy.json").write_text(json.dumps({"_meta": {"type": "builtin_locale", "language": "zh-CN", "label": "English Copy", "name": "EnglishCopy"}, "ui": {"title": "Title"}}), encoding="utf-8")

    monkeypatch.setattr(extractor, "ROOT", tmp_path)
    monkeypatch.setattr(extractor, "BUILTIN_LOCALES_DIR", locales_dir)
    monkeypatch.setattr(extractor, "DEFAULT_LOCALE_PATH", locales_dir / "zh-CN.json")

    errors = extractor.check_builtin_locale_keys({"ui.title": "标题"}, {"ui.title": "标题"})

    assert any("en.json 缺少 _meta" in error for error in errors)
    assert any("zz-copy.json _meta.language" in error and "重复" in error for error in errors)


def test_translated_locale_payload_preserves_existing_order_and_appends_new_keys():
    from scripts.extract_i18n_messages import build_translated_locale_payload, flatten_string_values

    payload, reset_count = build_translated_locale_payload(
        {"_meta": {"language": "en"}, "ui": {"second": "Second", "first": "First"}},
        {"ui.first": "第一", "ui.second": "第二"},
        {"ui.first": "第一", "ui.second": "第二", "ui.third": "第三"},
    )

    assert reset_count == 1
    assert list(flatten_string_values(payload)) == ["ui.second", "ui.first", "ui.third"]


def test_translated_locale_payload_can_use_canonical_order_without_resetting_unchanged_text():
    from scripts.extract_i18n_messages import build_translated_locale_payload, flatten_string_values

    payload, reset_count = build_translated_locale_payload(
        {"_meta": {"language": "en"}, "ui": {"second": "Second", "first": "First"}},
        {"ui.first": "第一", "ui.second": "第二"},
        {"ui.first": "第一", "ui.second": "第二"},
        preserve_existing_order=False,
    )

    assert reset_count == 0
    assert flatten_string_values(payload) == {"ui.first": "First", "ui.second": "Second"}
    assert list(flatten_string_values(payload)) == ["ui.first", "ui.second"]


def test_translated_locale_payload_resets_marker_mismatch():
    from scripts.extract_i18n_messages import UNTRANSLATED_PREFIX, build_translated_locale_payload

    payload, reset_count = build_translated_locale_payload(
        {"ui": {"tip": "^^Broken"}},
        {"ui.tip": "^^提示^^"},
        {"ui.tip": "^^提示^^"},
    )

    assert reset_count == 1
    assert payload["ui"]["tip"] == f"{UNTRANSLATED_PREFIX}^^提示^^"


def test_translated_locale_payload_keeps_same_text_as_valid_translation():
    from scripts.extract_i18n_messages import build_translated_locale_payload

    payload, reset_count = build_translated_locale_payload(
        {"ui": {"symbol": "^^|^^", "title": "简体中文"}},
        {"ui.symbol": "^^|^^", "ui.title": "简体中文"},
        {"ui.symbol": "^^|^^", "ui.title": "简体中文"},
    )

    assert reset_count == 0
    assert payload["ui"]["symbol"] == "^^|^^"
    assert payload["ui"]["title"] == "简体中文"


def test_ensure_builtin_locale_meta_uses_language_registry(tmp_path):
    from scripts.extract_i18n_messages import ensure_builtin_locale_meta

    payload = ensure_builtin_locale_meta(tmp_path / "ko.json", {"ui": {"title": "Title"}})

    assert payload["_meta"] == {
        "type": "builtin_locale",
        "language": "ko",
        "label": "한국어",
        "name": "Korean",
    }


def test_ensure_builtin_locale_meta_keeps_meta_first(tmp_path):
    from scripts.extract_i18n_messages import ensure_builtin_locale_meta

    payload = ensure_builtin_locale_meta(tmp_path / "en.json", {"ui": {"title": "Title"}, "_meta": {"language": "en"}})

    assert list(payload)[:2] == ["_meta", "ui"]


def test_extract_placeholders_reads_named_params():
    from scripts.extract_i18n_messages import extract_placeholders

    assert extract_placeholders("{name}处理中，已完成 {count}") == {"name", "count"}


def test_extract_locale_markers_reads_text_markers_without_visible_placeholders():
    from scripts.extract_i18n_messages import extract_locale_markers

    assert extract_locale_markers("C:/Users/{用户名} ^^提示^^ [[复制]]") == ["^^", "^^", "[[", "]]"]


def test_bare_chinese_report_ignores_inline_block_comment():
    from scripts.extract_i18n_messages import CHINESE_PATTERN, strip_inline_comment

    code_line = strip_inline_comment("width: 0; /* 初始宽度 */", ".vue")

    assert not CHINESE_PATTERN.search(code_line)


def test_bare_chinese_report_ignores_language_registry():
    from scripts.extract_i18n_messages import ROOT, is_bare_chinese_candidate

    path = ROOT / "backend" / "i18n" / "language_registry.py"

    assert not is_bare_chinese_candidate(path, 'LanguageSpec("zh-CN", "ChineseSimplified", "简体中文")')


def test_bare_chinese_report_ignores_diagnostic_files():
    from scripts.extract_i18n_messages import ROOT, is_bare_chinese_candidate

    assert not is_bare_chinese_candidate(ROOT / "backend" / "database" / "runtime.py", 'return False, "数据库文件不存在"')
    assert not is_bare_chinese_candidate(ROOT / "backend" / "managers" / "mgr_game_logs.py", 'return {"error": "文件不存在"}')


def test_bare_chinese_report_tracks_multiline_i18n_call_depth():
    from scripts.extract_i18n_messages import I18N_CALL_LINE_PATTERN, paren_delta

    lines = [
        'message = tr(',
        '    "api.example",',
        '    "已经接入多语言",',
        ')',
    ]
    depth = 0
    reported = []
    for line in lines:
        if depth > 0:
            depth = max(0, depth + paren_delta(line))
            continue
        if I18N_CALL_LINE_PATTERN.search(line):
            depth = max(0, paren_delta(line))
            continue
        reported.append(line)

    assert reported == []


def test_user_locale_options_only_accept_user_locale_files(tmp_path, monkeypatch):
    import backend.i18n.messages as messages

    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    (locales_dir / "ja.json").write_text(json.dumps({"_meta": {"type": "user_locale", "language": "ja", "label": "日本語"}}), encoding="utf-8")
    (locales_dir / "legacy.json").write_text(json.dumps({"ui": {"demo": "旧语言包"}}), encoding="utf-8")
    (locales_dir / "rimcrow-locale-ko.work.json").write_text(json.dumps({"_meta": {"type": "translation_workfile", "language": "ko"}}), encoding="utf-8")

    monkeypatch.setattr(messages, "USER_LOCALES_DIR", locales_dir)

    values = {item["value"] for item in messages.list_user_locale_options()}
    assert "ja" in values
    assert "legacy" not in values
    assert "ko" not in values


def test_save_user_locale_message_creates_listed_user_locale(tmp_path, monkeypatch):
    import backend.i18n.messages as messages

    locales_dir = tmp_path / "locales"
    monkeypatch.setattr(messages, "USER_LOCALES_DIR", locales_dir)

    messages.save_user_locale_message("ja", "ui.title", "タイトル")

    payload = json.loads((locales_dir / "ja.json").read_text(encoding="utf-8"))
    assert payload["_meta"] == {"language": "ja", "label": "日本語", "type": "user_locale"}
    assert {item["value"] for item in messages.list_user_locale_options()} == {"ja"}


def test_save_user_locale_messages_creates_listed_user_locale(tmp_path, monkeypatch):
    import backend.i18n.messages as messages

    locales_dir = tmp_path / "locales"
    monkeypatch.setattr(messages, "USER_LOCALES_DIR", locales_dir)

    messages.save_user_locale_messages("ko", {"ui.title": "제목"})

    payload = json.loads((locales_dir / "ko.json").read_text(encoding="utf-8"))
    assert payload["_meta"] == {"language": "ko", "label": "한국어", "type": "user_locale"}
    assert {item["value"] for item in messages.list_user_locale_options()} == {"ko"}


def test_write_json_keeps_existing_file_when_write_fails(tmp_path, monkeypatch):
    import backend.i18n.messages as messages

    target = tmp_path / "locale.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    original_write_text = Path.write_text

    def fail_after_write(path, *args, **kwargs):
        original_write_text(path, *args, **kwargs)
        raise OSError("simulated write failure")

    monkeypatch.setattr(Path, "write_text", fail_after_write)

    with pytest.raises(OSError, match="simulated write failure"):
        messages.write_json(target, {"new": True})

    assert target.read_text(encoding="utf-8") == '{"old": true}\n'


def test_locale_load_user_messages_separates_meta_from_messages(monkeypatch):
    from backend.api import API
    import backend.api as api

    monkeypatch.setattr(api, "load_user_locale", lambda _: {
        "_meta": {"type": "user_locale", "language": "ja", "label": "日本語"},
        "ui": {"title": "タイトル"},
    })

    response = API.__new__(API).locale_load_user_messages("ja")

    assert response["status"] == "success"
    assert response["data"]["language"] == "ja"
    assert response["data"]["meta"] == {"type": "user_locale", "language": "ja", "label": "日本語"}
    assert response["data"]["messages"] == {"ui": {"title": "タイトル"}}


def test_locale_export_workfile_builds_meta_in_backend(tmp_path, monkeypatch):
    from backend.api import API
    import backend.api as api

    target = tmp_path / "locale.work.json"
    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(api.file_mgr, "save_file_dialog", lambda **_: str(target))

    response = API.__new__(API).locale_export_workfile("ja", {"ui.title": {"source": "标题", "target": ""}}, "")
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert response["status"] == "success"
    assert payload["_meta"]["type"] == "translation_workfile"
    assert payload["_meta"]["language"] == "ja"
    assert payload["messages"] == {"ui.title": {"source": "标题", "target": ""}}


def test_locale_import_workfile_does_not_return_meta(tmp_path, monkeypatch):
    from backend.api import API
    import backend.api as api

    source = tmp_path / "locale.work.json"
    source.write_text(json.dumps({
        "_meta": {"type": "translation_workfile", "language": "ja"},
        "messages": {"ui.title": {"source": "标题", "target": "Title"}},
    }), encoding="utf-8")
    monkeypatch.setattr(api, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(api.file_mgr, "select_file_dialog", lambda **_: str(source))

    response = API.__new__(API).locale_import_workfile()

    assert response["status"] == "success"
    assert response["data"]["language"] == "ja"
    assert response["data"]["messages"] == {"ui.title": {"source": "标题", "target": "Title"}}
    assert "_meta" not in response["data"]


def test_locale_workfile_keeps_same_text_as_valid_translation():
    from scripts.locale_workfile import extract_messages

    language, messages, errors = extract_messages({
        "_meta": {"language": "en"},
        "messages": {"ui.symbol": {"source": "^^|^^", "target": "^^|^^"}},
    })

    assert language == "en"
    assert errors == []
    assert messages == {"ui.symbol": "^^|^^"}


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
