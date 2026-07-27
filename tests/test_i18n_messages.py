import json
from pathlib import Path

import pytest

from backend.i18n.messages import deep_merge, localized_key, localized_params, tr


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
