from __future__ import annotations

import json
import logging
import ssl

import httpx
import pytest
import requests
from openai import AuthenticationError
from pydantic import BaseModel

from backend.ai.ai_tools import AIToolExecutor, ToolDefinition, ToolSpec
from backend.api import ApiResponse
from backend.i18n.messages import tr
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.utils.error_contract import AppError, InvalidResponseError, build_error_payload, classify_exception
from backend.utils.event_bus import EventBus
from backend.database.runtime import validate_database_file
from backend.managers.mgr_files import FileManager, PathChecker
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_steamcmd_core import SteamCMDController
from backend.managers.mgr_texture_opt import TextureOptimizationManager, TextureTask
from backend.utils.logger import JSONFormatter


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
    assert response["detail"]["exception_type"] == "RuntimeError"
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
        (InvalidResponseError("checksum mismatch"), "NETWORK", "NETWORK.INVALID_RESPONSE"),
        (requests.exceptions.ChunkedEncodingError("truncated"), "NETWORK", "NETWORK.INVALID_RESPONSE"),
        (requests.exceptions.ContentDecodingError("invalid encoding"), "NETWORK", "NETWORK.INVALID_RESPONSE"),
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


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [(400, "REQUEST_INVALID"), (401, "AUTH_FAILED"), (403, "ACCESS_DENIED"),
     (404, "NOT_FOUND"), (407, "PROXY_AUTH"), (408, "TIMEOUT"), (429, "RATE_LIMIT"),
     (422, "REQUEST_FAILED"), (451, "REQUEST_FAILED"), (502, "SERVICE_UNAVAILABLE")],
)
def test_http_errors_use_shared_codes(status, expected_code):
    response = requests.Response()
    response.status_code = status
    response.url = "https://example.test/"
    with pytest.raises(requests.HTTPError) as captured:
        response.raise_for_status()
    result = classify_exception(captured.value)
    assert result.error_code == f"NETWORK.{expected_code}"
    assert result.user_message
    assert result.message_key.startswith("errors.network.")


@pytest.mark.parametrize("method", ["_request_json", "_request_text"])
@pytest.mark.parametrize("status", [403, 429, 503])
def test_steam_requests_preserve_status_for_shared_classification(monkeypatch, method, status):
    from unittest.mock import MagicMock

    response = requests.Response()
    response.status_code = status
    response.url = "https://api.steampowered.com/test"
    session = MagicMock()
    session.__enter__.return_value.request.return_value = response
    monkeypatch.setattr("backend.managers.mgr_steam_api.build_retry_session", lambda **kwargs: session)
    with pytest.raises(requests.HTTPError) as captured:
        getattr(SteamWebAPI, method)("GET", response.url)
    assert captured.value.response is response
    result = classify_exception(captured.value)
    assert result.error_code == {403: "NETWORK.ACCESS_DENIED", 429: "NETWORK.RATE_LIMIT", 503: "NETWORK.SERVICE_UNAVAILABLE"}[status]
    if status == 403:
        assert "API Key" in result.user_message


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [(requests.exceptions.SSLError("certificate verify failed"), "NETWORK.TLS"),
     (ssl.SSLError(1, "handshake failed"), "NETWORK.TLS"),
     (requests.exceptions.ProxyError("proxy failed"), "NETWORK.PROXY"),
     (__import__("openai").APITimeoutError(request=httpx.Request("GET", "https://example.test")), "NETWORK.TIMEOUT")],
)
def test_transport_errors_keep_precise_shared_codes(exc, expected_code):
    assert classify_exception(exc).error_code == expected_code


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


class _DummyToolArgs(BaseModel):
    value: int


def test_ai_tool_executor_hides_raw_handler_exception():
    executor = AIToolExecutor.__new__(AIToolExecutor)

    def failing_handler(_args):
        raise RuntimeError("SECRET_BACKEND_PATH")

    definition = ToolDefinition(
        name="dummy",
        label="测试工具",
        llm_description="",
        ui_description="",
        args_model=_DummyToolArgs,
        handler_name="",
    )
    executor.registry = {"dummy": ToolSpec(definition=definition, handler=failing_handler)}

    result = executor.execute_structured("dummy", '{"value": 1}')

    assert result.ok is False
    assert result.error == "工具执行失败，请稍后重试。"
    assert "SECRET_BACKEND_PATH" not in result.model_output
    assert "SECRET_BACKEND_PATH" not in str(result.data)
    assert "SECRET_BACKEND_PATH" not in result.summary


def test_texture_task_failure_payload_hides_raw_exception(monkeypatch):
    manager = TextureOptimizationManager.__new__(TextureOptimizationManager)
    manager._tasks = {}
    manager._analysis_tasks = {}
    manager._analysis_started_at = {}
    manager._last_todds_log_path = ""

    captured_progress = []
    monkeypatch.setattr(EventBus, "emit_progress", classmethod(lambda cls, *args, **kwargs: captured_progress.append((args, kwargs))))
    monkeypatch.setattr(manager, "_schedule_task_cleanup", lambda _task_id: None)
    monkeypatch.setattr(manager, "_optimize", lambda _task: (_ for _ in ()).throw(RuntimeError("SECRET_TEXTURE_FAILURE")))

    task = TextureTask(id="task-1", action="optimize", mod_paths=[], options={})
    manager._run_task(task)

    failed_events = [kwargs for _args, kwargs in captured_progress if kwargs.get("status") == "failed"]
    assert task.status == "failed"
    assert "SECRET_TEXTURE_FAILURE" not in task.message
    assert "SECRET_TEXTURE_FAILURE" not in task.error
    assert failed_events
    assert "SECRET_TEXTURE_FAILURE" not in failed_events[-1]["message"]




def test_file_delete_result_hides_raw_exception(monkeypatch):
    monkeypatch.setattr(EventBus, "emit_progress", classmethod(lambda cls, *args, **kwargs: None))
    monkeypatch.setattr("backend.managers.mgr_files.delete_fs_path", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("SECRET_DELETE_FAILURE")))

    success_count, errors = FileManager.delete_paths(["C:\\tmp\\demo.txt"], force=True)

    assert success_count == 0
    assert errors
    assert "SECRET_DELETE_FAILURE" not in errors[0]


def test_path_checker_hides_raw_validation_exception(monkeypatch):
    monkeypatch.setattr("backend.managers.mgr_files.GameManager.get_default_user_data_paths", staticmethod(lambda: []))
    monkeypatch.setattr("backend.managers.mgr_files.UserDataRoot.from_raw", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("SECRET_USER_DATA_PATH")))

    result = PathChecker.check_user_data_path("bad-path")

    assert result["pass"] is False
    assert "SECRET_USER_DATA_PATH" not in result["msg"]


def test_database_validation_hides_missing_path():
    ok, message = validate_database_file("C:\\SECRET_DB_PATH\\missing.sqlite")

    assert ok is False
    assert "SECRET_DB_PATH" not in message


def test_steam_launch_result_hides_raw_subprocess_exception(monkeypatch, tmp_path):
    steam_exe = tmp_path / "Steam.exe"
    steam_exe.write_text("", encoding="utf-8")

    def fail_popen(*_args, **_kwargs):
        raise RuntimeError("SECRET_STEAM_FAILURE")

    monkeypatch.setattr("backend.managers.mgr_steam.subprocess.Popen", fail_popen)

    manager = SteamManager.__new__(SteamManager)
    manager.steam_exe = str(steam_exe)

    result = manager.launch_via_steam_client()

    assert result["ok"] is False
    assert "SECRET_STEAM_FAILURE" not in result["error"]


def test_load_order_read_active_mods_hides_raw_parse_exception(monkeypatch, tmp_path):
    mods_config = tmp_path / "ModsConfig.xml"
    mods_config.write_text("<ModsConfigData />", encoding="utf-8")

    monkeypatch.setattr("backend.managers.mgr_load_order.parse_load_order_file", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("SECRET_LOAD_ORDER_FAILURE")))

    manager = LoadOrderManager.__new__(LoadOrderManager)
    manager.context = type("Ctx", (), {"mods_config_file": str(mods_config)})()
    manager._build_version_token = lambda *args, **kwargs: "token"

    result = manager.read_active_mods(str(mods_config))

    assert result["errors"] == ["排序文件解析失败，请检查文件格式是否正确。"]
    assert "SECRET_LOAD_ORDER_FAILURE" not in result["errors"][0]


def test_steamcmd_core_hides_raw_monitor_exception(monkeypatch, tmp_path):
    controller = SteamCMDController(str(tmp_path / "steamcmd.exe"))

    def fail_popen(*_args, **_kwargs):
        raise RuntimeError("SECRET_STEAMCMD_CORE_FAILURE")

    monkeypatch.setattr("backend.managers.mgr_steamcmd_core.subprocess.Popen", fail_popen)

    ok, message = controller._run_and_monitor(["steamcmd.exe"], "初始化", timeout=1)

    assert ok is False
    assert "SECRET_STEAMCMD_CORE_FAILURE" not in message


def test_json_log_context_drops_raw_error_fields():
    record = logging.makeLogRecord({
        "name": "RimCrow",
        "levelno": logging.ERROR,
        "levelname": "ERROR",
        "msg": "操作失败",
        "args": (),
        "error_code": "TEST.FAILED",
        "extra_context": {
            "task_id": "task-1",
            "original_error": "SECRET_RAW_ERROR",
            "nested": {"fallback_error": "SECRET_FALLBACK_ERROR", "url": "https://example.test"},
        },
    })

    payload = json.loads(JSONFormatter().format(record))

    assert payload["extra_context"] == {"task_id": "task-1", "nested": {"url": "https://example.test"}}
    assert "SECRET_RAW_ERROR" not in json.dumps(payload, ensure_ascii=False)
    assert "SECRET_FALLBACK_ERROR" not in json.dumps(payload, ensure_ascii=False)
