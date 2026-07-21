from __future__ import annotations

import httpx
import pytest
import requests

from backend.api import ApiResponse
from backend.i18n.messages import tr
from backend.utils.error_contract import classify_exception
from backend.utils.event_bus import EventBus


def test_api_response_error_exposes_structured_error_envelope():
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        captured_exc = exc

    response = ApiResponse.error(
        "接口调用失败",
        detail=captured_exc,
        context={"module": "demo", "action": "load"},
        user_message=tr("api.demo.failed", "操作失败，请稍后重试。"),
    )

    assert response["status"] == "error"
    assert response["error_id"]
    assert response["error_type"]
    assert response["error_code"]
    assert response["message_key"] == "api.demo.failed"
    assert "traceback" in response["detail"]
    assert "context" not in response["detail"]
    assert "error_id" not in response["detail"]
    assert "操作失败" not in str(response["detail"])
    assert "message_key" not in response["detail"]


def test_event_bus_transmits_structured_error_payload(monkeypatch):
    captured = []

    def fake_emit(event_name, data=None):
        captured.append((event_name, data))

    structured = {
        "message": "访问失败",
        "error_type": "AI.AUTH",
        "error_code": "AI.AUTH",
        "message_key": "api.ai.auth_failed",
        "message_params": {"provider": "openai"},
        "error_id": "err_123",
    }

    monkeypatch.setattr(EventBus, "emit", classmethod(lambda cls, event_name, data=None: fake_emit(event_name, data)))
    EventBus.send_toast(structured, type="error", duration=5000)
    EventBus.send_alert("认证失败", structured, type="error")

    assert [event_name for event_name, _ in captured] == ["backend-popup", "backend-popup"]
    assert captured[0][1]["message_key"] == "api.ai.auth_failed"
    assert captured[0][1]["error_type"] == "AI"
    assert captured[1][1]["message_params"] == {"provider": "openai"}
    assert captured[1][1]["error_code"] == "AI.AUTH"
    assert captured[1][1]["error_id"] == "err_123"


@pytest.mark.parametrize(
    ("exc", "expected_type", "expected_code"),
    [
        (
            __import__("openai").AuthenticationError(
                "unauthorized",
                response=httpx.Response(401, request=httpx.Request("GET", "https://example.com")),
                body={"error": "unauthorized"},
            ),
            "AI",
            "AI.AUTH_FAILED",
        ),
        (requests.Timeout("timed out"), "NETWORK", "NETWORK.TIMEOUT"),
        (PermissionError("denied"), "SYSTEM", "SYSTEM.PERMISSION"),
    ],
)
def test_classify_exception_maps_stable_primary_categories(exc, expected_type, expected_code):
    result = classify_exception(exc, module="demo", action="call", context={"task_id": "t1"})

    assert result.error_type == expected_type
    assert result.error_code == expected_code


def test_classify_exception_preserves_precise_cause_for_wrapped_ai_auth_error():
    auth_error = __import__("openai").AuthenticationError(
        "Error code: 401 - {'msg': 'user token expired'}",
        response=httpx.Response(401, request=httpx.Request("GET", "https://api.example.test/v1/chat/completions")),
        body={"msg": "user token expired"},
    )
    try:
        raise RuntimeError("AI 服务没有返回可用结果") from auth_error
    except RuntimeError as exc:
        result = classify_exception(exc, module="ai", action="test_chat")

    assert result.error_type == "AI"
    assert result.error_code == "AI.AUTH_EXPIRED"
    assert "过期" in result.user_message


def test_classify_exception_maps_gitgud_404_to_git_not_found():
    response = requests.Response()
    response.status_code = 404
    response.url = "https://gitgud.io/api/v4/projects/Teacher%2Fultimate-animation-pack/repository/archive.zip?sha=main"
    error = requests.HTTPError("404 Client Error: Not Found for url: " + response.url)
    error.response = response

    result = classify_exception(error, module="download", action="git_download", context={"url": response.url})

    assert result.error_type == "GIT"
    assert result.error_code == "GIT.NOT_FOUND"
    assert "仓库资源不存在" in result.user_message


@pytest.mark.parametrize(
    ("error_text", "expected_code"),
    [
        ("unknown provider for model gpt-5-test", "AI.ROUTING_FAILED"),
        ("temperature is unsupported by this model", "AI.PARAM_UNSUPPORTED"),
        ("choices empty in non OpenAI Chat Completions response", "AI.RESPONSE_FORMAT"),
    ],
)
def test_classify_exception_maps_ai_text_only_inside_ai_domain(error_text, expected_code):
    ai_result = classify_exception(RuntimeError(error_text), module="ai", action="test_chat")
    non_ai_result = classify_exception(RuntimeError(error_text), module="download", action="fetch")

    assert ai_result.error_type == "AI"
    assert ai_result.error_code == expected_code
    assert non_ai_result.error_code == "SYSTEM.UNKNOWN"
