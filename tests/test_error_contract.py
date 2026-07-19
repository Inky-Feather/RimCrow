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
    assert response["detail"]["context"] == {"module": "demo", "action": "load"}
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
    assert captured[0][1]["error_type"] == "AI.AUTH"
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
            "AI.AUTH",
            "AI.AUTH",
        ),
        (requests.Timeout("timed out"), "NETWORK.TIMEOUT", "NETWORK.TIMEOUT"),
        (PermissionError("denied"), "SYSTEM.PERMISSION", "SYSTEM.PERMISSION"),
    ],
)
def test_classify_exception_maps_stable_primary_categories(exc, expected_type, expected_code):
    result = classify_exception(exc, module="demo", action="call", context={"task_id": "t1"})

    assert result.error_type == expected_type
    assert result.error_code == expected_code
