import json

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

    errors = extractor.check_builtin_locale_keys({"ui.title": "标题"}, ["ui", "ui.title"], {"ui.title": "标题"})

    assert any("en.json 缺少 _meta" in error for error in errors)
    assert any("zz-copy.json _meta.language" in error and "重复" in error for error in errors)


def test_translated_locale_payload_follows_default_order():
    from scripts.extract_i18n_messages import build_translated_locale_payload, flatten_string_values

    payload, reset_count = build_translated_locale_payload(
        {"_meta": {"language": "en"}, "ui": {"second": "Second", "first": "First"}},
        {"ui.first": "第一", "ui.second": "第二"},
        {"ui.first": "第一", "ui.second": "第二"},
    )

    assert reset_count == 0
    assert list(flatten_string_values(payload)) == ["ui.first", "ui.second"]


def test_extract_placeholders_reads_named_params():
    from scripts.extract_i18n_messages import extract_placeholders

    assert extract_placeholders("{name}处理中，已完成 {count}") == {"name", "count"}


def test_extract_locale_markers_reads_text_markers_without_visible_placeholders():
    from scripts.extract_i18n_messages import extract_locale_markers

    assert extract_locale_markers("C:/Users/{用户名} ^^提示^^ [[复制]]") == ["^^", "^^", "[[", "]]"]


def test_user_locale_options_skip_translation_workfiles(tmp_path, monkeypatch):
    import backend.i18n.messages as messages

    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    (locales_dir / "ja.json").write_text(json.dumps({"_meta": {"type": "user_locale", "language": "ja", "label": "日本語"}}), encoding="utf-8")
    (locales_dir / "legacy.json").write_text(json.dumps({"ui": {"demo": "旧语言包"}}), encoding="utf-8")
    (locales_dir / "rimcrow-locale-ko.work.json").write_text(json.dumps({"_meta": {"type": "translation_workfile", "language": "ko"}}), encoding="utf-8")

    monkeypatch.setattr(messages, "USER_LOCALES_DIR", locales_dir)

    values = {item["value"] for item in messages.list_user_locale_options()}
    assert "ja" in values
    assert "legacy" in values
    assert "ko" not in values
