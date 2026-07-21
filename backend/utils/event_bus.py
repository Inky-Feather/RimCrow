# backend/utils/event_bus.py
import json
import sys
import threading
from collections.abc import Mapping
from typing import Any

from backend.i18n.messages import localized_key, localized_params
from backend.utils.tools import current_ms

# 不在模块导入期导入 webview：日志初始化会导入 EventBus，过早加载 webview 可能在无控制台打包环境触发 nul 启动崩溃。

class EventBus:
    _instance = None   # 存储单例实例的变量
    _window = None
    _browser_dispatcher = None
    _paused = False  # 暂停标志
    _frontend_ready = False  # 新增：前端是否彻底就绪的标志
    _lock = threading.Lock() # 线程锁
    _pending_events: list[tuple[str, Any]] = []
    _max_pending_events = 100
    _dropped_event_count = 0
    _dispatch_error_count = 0
    
    
    def __new__(cls):
        '''创建单例实例'''
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    @classmethod
    def set_window(cls, window: Any):
        cls._window = window
        cls._browser_dispatcher = None
        cls._paused = False
        cls._frontend_ready = False # 绑定窗口时，默认未就绪

    @classmethod
    def set_browser_dispatcher(cls, dispatcher):
        cls._window = None
        cls._browser_dispatcher = dispatcher
        cls._paused = False
        cls._frontend_ready = False # 绑定窗口时，默认未就绪

    @classmethod
    def mark_ready(cls):
        """标记前端已挂载完毕"""
        with cls._lock:
            cls._frontend_ready = True
            pending_events = list(cls._pending_events)
            cls._pending_events.clear()
            dispatcher = cls._browser_dispatcher
            window = cls._window
            paused = cls._paused
        if paused or not pending_events:
            return
        for index, (event_name, data) in enumerate(pending_events):
            if not cls._dispatch_to_target(event_name, data, dispatcher, window):
                with cls._lock:
                    cls._frontend_ready = False
                    cls._dispatch_error_count += 1
                    for queued_event_name, queued_data in pending_events[index:]:
                        cls._queue_pending_event(queued_event_name, queued_data)
                break
        
    @classmethod
    def pause(cls):
        """暂停事件发送"""
        cls._paused = True

    @classmethod
    def resume(cls):
        """恢复事件发送"""
        cls._paused = False

    @classmethod
    def _queue_pending_event(cls, event_name: str, data: Any):
        # Toast/弹窗是即时反馈，前端未就绪后补发容易造成过期提示堆积；状态和日志事件保留最近一批用于恢复。
        if event_name == 'backend-popup':
            cls._dropped_event_count += 1
            return
        cls._pending_events.append((str(event_name), data))
        overflow = len(cls._pending_events) - cls._max_pending_events
        if overflow > 0:
            del cls._pending_events[:overflow]
            cls._dropped_event_count += overflow

    @staticmethod
    def _dispatch_to_target(event_name: str, data: Any, dispatcher, window: Any) -> bool:
        try:
            if dispatcher:
                dispatcher(event_name, data)
                return True
            if not window or not hasattr(window, 'evaluate_js'):
                return False
            js_payload = json.dumps(data, ensure_ascii=False)
            js_code = f"""
                setTimeout(() => {{
                    if (window.dispatchEvent) {{
                        const detail = JSON.parse({json.dumps(js_payload)});
                        window.dispatchEvent(new CustomEvent({json.dumps(str(event_name))}, {{ detail: detail }}));
                    }}
                }}, 0);
            """
            window.evaluate_js(js_code)
            return True
        except Exception as exc:
            print(f"[EventBus] Event dispatch failed: event={event_name}, error={exc}", file=sys.stderr)
            return False

    @classmethod
    def emit(cls, event_name, data=None):
        """
        向前端发送事件。
        前端监听: window.addEventListener('pywebview-event', (e) => { ... })
        使用 evaluate_js 原生 CustomEvent，兼容性好。
        """
        with cls._lock:
            if cls._paused or not cls._frontend_ready:
                cls._queue_pending_event(event_name, data)
                return
            dispatcher = cls._browser_dispatcher
            window = cls._window
            if not dispatcher and (not window or not hasattr(window, 'evaluate_js')):
                cls._queue_pending_event(event_name, data)
                return
        if not cls._dispatch_to_target(event_name, data, dispatcher, window):
            with cls._lock:
                cls._frontend_ready = False
                cls._dispatch_error_count += 1
                cls._queue_pending_event(event_name, data)

    @staticmethod
    def _structured_message_payload(message: Any) -> dict[str, Any]:
        if not isinstance(message, Mapping):
            payload: dict[str, Any] = {"message": str(message or "")}
            key = localized_key(message)
            params = localized_params(message)
            if key:
                payload["message_key"] = key
            if params:
                payload["message_params"] = params
            return payload
        payload = dict(message)
        text = str(payload.get("message") or payload.get("user_message") or "")
        if text:
            payload["message"] = text
        key = localized_key(payload)
        params = localized_params(payload)
        if key:
            payload["message_key"] = key
        if params:
            payload["message_params"] = params
        return payload

    @staticmethod
    def _normalize_error_type(error_type: str = "", error_code: str = "") -> str:
        value = str(error_type or "").strip()
        if value and "." not in value:
            return value
        code = str(error_code or value or "").strip()
        return code.split(".", 1)[0] if code else ""

    @classmethod
    def send_toast(
        cls,
        message: Any,
        type: str = 'info',
        duration: int = 3000,
        *,
        error_type: str = '',
        error_code: str = '',
        error_id: str = '',
        user_message: str = '',
        message_key: str = '',
        message_params: Mapping[str, Any] | None = None,
        extra_context: Mapping[str, Any] | None = None,
    ):
        """快捷发送 Toast"""
        payload: dict[str, Any] = {
            'mode': 'toast',
            'type': type,
            'duration': duration
        }
        payload.update(cls._structured_message_payload(message))
        normalized_type = cls._normalize_error_type(error_type or payload.get("error_type", ""), error_code or payload.get("error_code", ""))
        if normalized_type:
            payload['error_type'] = normalized_type
        if error_code:
            payload['error_code'] = str(error_code)
        if error_id:
            payload['error_id'] = str(error_id)
        if user_message:
            payload['user_message'] = str(user_message)
        if message_key:
            payload['message_key'] = str(message_key)
        if message_params:
            payload['message_params'] = dict(message_params)
        if extra_context:
            payload['extra_context'] = dict(extra_context)
        cls.emit('backend-popup', payload)

    @classmethod
    def send_alert(
        cls,
        title: str,
        message: Any,
        type: str = 'info',
        *,
        error_type: str = '',
        error_code: str = '',
        error_id: str = '',
        user_message: str = '',
        message_key: str = '',
        message_params: Mapping[str, Any] | None = None,
        extra_context: Mapping[str, Any] | None = None,
    ):
        """快捷发送 Modal/Alert"""
        payload: dict[str, Any] = {
            'mode': 'modal',
            'title': title,
            'type': type
        }
        payload.update(cls._structured_message_payload(message))
        normalized_type = cls._normalize_error_type(error_type or payload.get("error_type", ""), error_code or payload.get("error_code", ""))
        if normalized_type:
            payload['error_type'] = normalized_type
        if error_code:
            payload['error_code'] = str(error_code)
        if error_id:
            payload['error_id'] = str(error_id)
        if user_message:
            payload['user_message'] = str(user_message)
        if message_key:
            payload['message_key'] = str(message_key)
        if message_params:
            payload['message_params'] = dict(message_params)
        if extra_context:
            payload['extra_context'] = dict(extra_context)
        cls.emit('backend-popup', payload)

    @staticmethod
    def _normalize_progress_status(status: str) -> str:
        value = str(status or "running").strip().lower()
        mapping = {
            "completed": "success",
            "complete": "success",
            "done": "success",
            "error": "failed",
            "errored": "failed",
            "verifying": "running",
            "paused": "pending",
        }
        normalized = mapping.get(value, value)
        if normalized not in {"pending", "running", "success", "failed", "cancelled"}: return "running"
        return normalized
    
    @classmethod
    def emit_progress(
        cls,
        task_id,
        task_type,
        status="running",
        progress=0,
        message="",
        metrics=None,
        message_key="",
        message_params=None,
        *,
        error_type: str = "",
        error_code: str = "",
        error_id: str = "",
        user_message: str = "",
        extra_context: Mapping[str, Any] | None = None,
    ):
        """
        统一进度发送器
        :param task_id: 任务唯一ID (uuid)
        :param task_type: 任务类型 (SCAN | DOWNLOAD | AI | SYNC | REPAIR)
        :param status: 状态 (pending | running | success | failed | cancelled)
        :param progress: 0-100 的整数
        :param message: 当前处理的具体信息 (如文件名)
        :param metrics: 额外指标数据 (如 {'speed': '2MB/s', 'eta': '10s', 'count': '10/100'})
        """
        now = current_ms()
        key = str(message_key or localized_key(message) or "").strip()
        params = dict(message_params or localized_params(message))
        payload = {
            "id": task_id,
            "type": str(task_type or "").strip().lower(),
            "status": cls._normalize_progress_status(status),
            "progress": max(0, min(100, int(progress or 0))),
            "message": str(message or ""),
            "metrics": dict(metrics or {}),
            "timestamp": now
        }
        # message 保持旧字段兼容；key/params 只在声明时附加，前端可按当前语言即时渲染。
        if key:
            payload["message_key"] = key
        if params:
            payload["message_params"] = params
        normalized_type = cls._normalize_error_type(error_type, error_code)
        if normalized_type:
            payload["error_type"] = normalized_type
        if error_code:
            payload["error_code"] = str(error_code)
        if error_id:
            payload["error_id"] = str(error_id)
        if user_message:
            payload["user_message"] = str(user_message)
        if extra_context:
            payload["extra_context"] = dict(extra_context)
        payload["metrics"].setdefault("task_created_at", now)
        cls.emit('global-progress', payload)
        
