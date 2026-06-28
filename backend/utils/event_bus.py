# backend/utils/event_bus.py
import threading

from webview import WebViewException, Window

from backend.utils.tools import current_ms

class EventBus:
    _instance = None   # 存储单例实例的变量
    _window = None
    _browser_dispatcher = None
    _paused = False  # 暂停标志
    _frontend_ready = False  # 新增：前端是否彻底就绪的标志
    _lock = threading.Lock() # 线程锁
    
    
    def __new__(cls):
        '''创建单例实例'''
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    @classmethod
    def set_window(cls, window: Window):
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
        cls._frontend_ready = True
        
    @classmethod
    def pause(cls):
        """暂停事件发送"""
        cls._paused = True

    @classmethod
    def resume(cls):
        """恢复事件发送"""
        cls._paused = False

    @classmethod
    def emit(cls, event_name, data=None):
        """
        向前端发送事件。
        前端监听: window.addEventListener('pywebview-event', (e) => { ... })
        使用 evaluate_js 原生 CustomEvent，兼容性好。
        """
        with cls._lock:
            if cls._browser_dispatcher and cls._frontend_ready and not cls._paused:
                try:
                    cls._browser_dispatcher(event_name, data)
                except Exception:
                    pass
                return
            # 增加 _frontend_ready 的严格判断，前端没准备好时，静默丢弃事件，不引发报错
            if cls._paused or not cls._window or not cls._frontend_ready:  return
            # 增加窗口就绪状态的预检
            # 如果窗口正在加载 URL (idle <-> vue 切换中)，evaluate_js 会抛出不可逆异常
            if not hasattr(cls._window, 'evaluate_js'): return
            
            # 如果暂停或窗口不存在，直接丢弃事件
            if cls._paused or not cls._window: 
                print(f"[EventBus] Event {event_name} dropped: paused={cls._paused}, window={cls._window}")
                return
        
            import json
            try:
                # 构造 JS 代码触发 CustomEvent
                # 前端监听: window.addEventListener('global-progress', (e) => console.log(e.detail))
                js_payload = json.dumps(data)
                # 使用 setTimeout 0 异步执行，减少对 Python 线程的阻塞
                js_code = f"""
                    setTimeout(() => {{
                        if (window.dispatchEvent) {{
                            const detail = JSON.parse({json.dumps(js_payload)});
                            window.dispatchEvent(new CustomEvent('{event_name}', {{ detail: detail }}));
                        }}
                    }}, 0);
                """
                # 在主线程执行 JS (pywebview 可以在任意线程调用 evaluate_js，它内部会处理线程安全)
                cls._window.evaluate_js(js_code)
            except WebViewException:
                # 窗口可能还没准备好，或者已经关闭
                # 这种情况下，静默失败，只在控制台打印简单的 stderr，防止递归调用 logger
                # 捕获异常后，将就绪状态置为 False，防止后续事件继续撞墙
                cls._frontend_ready = False
                import sys
                # print(f"[EventBus Error] Window not ready for event: {event_name}", file=sys.stderr)
            except Exception as e:
                import sys
                # print(f"[EventBus Error] Unknown error: {e}", file=sys.stderr)

    @classmethod
    def send_toast(cls, message: str, type: str = 'info', duration: int = 3000):
        """快捷发送 Toast"""
        print(f"[EventBus] send_toast: {message}")
        cls.emit('backend-popup', {
            'mode': 'toast',
            'message': message,
            'type': type,
            'duration': duration
        })

    @classmethod
    def send_alert(cls, title: str, message: str, type: str = 'info'):
        """快捷发送 Modal/Alert"""
        cls.emit('backend-popup', {
            'mode': 'modal',
            'title': title,
            'message': message,
            'type': type
        })

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
    def emit_progress(cls, task_id, task_type, status="running", progress=0, message="", metrics=None):
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
        payload = {
            "id": task_id,
            "type": str(task_type or "").strip().lower(),
            "status": cls._normalize_progress_status(status),
            "progress": max(0, min(100, int(progress or 0))),
            "message": message,
            "metrics": dict(metrics or {}),
            "timestamp": now
        }
        payload["metrics"].setdefault("task_created_at", now)
        cls.emit('global-progress', payload)
        
