from backend.api import ApiResponse
from backend.utils.error_contract import AppError, build_error_payload
import httpx
from openai import AuthenticationError


def test_error_response_carries_error_id_in_payload_only():
    response = ApiResponse.error(
        "测试失败",
        code="TEST.FAIL",
        detail=RuntimeError("boom"),
    )

    assert response["status"] == "error"
    assert response["error_id"]
    assert "error_id" not in response["detail"]
    assert response["detail"]["exception_type"] == "RuntimeError"


def test_error_payload_detail_keeps_only_public_debug_fields():
    payload = build_error_payload(
        AppError(
            error_type="TEST",
            error_code="TEST.FAIL",
            user_message="测试失败",
            message="测试失败",
            error_id="err_123",
            detail={
                "traceback": "stack",
                "exception_type": "RuntimeError",
                "exception_module": "builtins",
                "context": {"action": "demo"},
                "error_id": "err_123",
                "original_error": "secret raw error",
                "business_id": "should-not-leak",
            },
        )
    )

    assert payload["detail"] == {
        "traceback": "stack",
        "exception_type": "RuntimeError",
        "exception_module": "builtins",
    }


def test_error_response_hides_technical_message_text():
    response = ApiResponse.error(
        "FileNotFoundError: [Errno 2] C:\\secret\\missing.xml",
        code="TEST.TECHNICAL",
        detail={"original_error": "FileNotFoundError: C:\\secret\\missing.xml"},
    )

    assert "FileNotFoundError" not in response["message"]
    assert "C:\\secret" not in response["message"]
    assert "detail" not in response


def test_error_response_uses_classified_exception_before_operation_code():
    auth_error = AuthenticationError(
        "Error code: 401 - {'msg': 'user token expired'}",
        response=httpx.Response(401, request=httpx.Request("POST", "https://api.example.test/v1/chat/completions")),
        body={"msg": "user token expired"},
    )
    try:
        raise RuntimeError("AI test chat failed") from auth_error
    except RuntimeError as exc:
        response = ApiResponse.error("AI 测试请求失败", code="AI.TEST_CHAT.FAILED", detail=exc, context={"module": "ai", "action": "test_chat"})

    assert response["error_type"] == "AI"
    assert response["error_code"] == "AI.AUTH_EXPIRED"
    assert response["message_key"] == "errors.ai.auth_expired"
    assert response["message"] == "AI 测试请求失败"
    assert "过期" in response["user_message"]
    assert "AI 服务没有返回可用结果" not in response["detail"]["traceback"]
