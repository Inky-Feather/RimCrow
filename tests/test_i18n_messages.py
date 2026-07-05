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


def test_extract_locale_payload_overwrites_existing_key():
    from scripts.extract_i18n_messages import build_locale_payload

    payload = build_locale_payload(
        {"ui": {"demo": {"title": "旧标题", "kept": "保留"}}},
        {"ui.demo.title": "新标题"},
    )

    assert payload["ui"]["demo"]["title"] == "新标题"
    assert payload["ui"]["demo"]["kept"] == "保留"
