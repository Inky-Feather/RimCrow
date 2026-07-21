from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from backend.ai.ai_tools import AIToolExecutor, ToolDefinition, ToolSpec
from backend.browser_runtime import WorkshopPageRenderer
from backend.database.runtime import validate_database_file
from backend.managers.mgr_files import FileManager, PathChecker
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_steamcmd_core import SteamCMDController
from backend.managers.mgr_texture_opt import TextureOptimizationManager, TextureTask
from backend.utils.event_bus import EventBus
from backend.utils.logger import JSONFormatter


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


def test_workshop_proxy_error_page_hides_raw_request_exception(monkeypatch):
    def fail_request(*_args, **_kwargs):
        raise RuntimeError("SECRET_PROXY_FAILURE")

    monkeypatch.setattr("backend.browser_runtime.requests.get", fail_request)

    html = WorkshopPageRenderer().render("https://steamcommunity.com/sharedfiles/filedetails/?id=123456")

    assert "加载页面失败" in html
    assert "SECRET_PROXY_FAILURE" not in html


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
