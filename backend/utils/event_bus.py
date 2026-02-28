# backend/utils/event_bus.py
from webview import WebViewException, Window

from backend.utils.tools import current_ms

class EventBus:
    _instance = None   # 存储单例实例的变量
    _window = None
    _paused = False  # 暂停标志
    
    
    def __new__(cls):
        '''创建单例实例'''
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    @classmethod
    def set_window(cls, window: Window):
        cls._window = window

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
        # 如果暂停或窗口不存在，直接丢弃事件
        if cls._paused or not cls._window: 
            print(f"[EventBus] Event {event_name} dropped: paused={cls._paused}, window={cls._window}")
            return
        
        import json
        try:
            # 构造 JS 代码触发 CustomEvent
            # 前端监听: window.addEventListener('scan-progress', (e) => console.log(e.detail))
            js_payload = json.dumps(data)
            # 使用 setTimeout 0 异步执行，减少对 Python 线程的阻塞
            js_code = f"""
                setTimeout(() => {{
                    if (window.dispatchEvent) window.dispatchEvent(new CustomEvent('{event_name}', {{ detail: {js_payload} }}));
                }}, 0);
            """
            # 在主线程执行 JS (pywebview 可以在任意线程调用 evaluate_js，它内部会处理线程安全)
            cls._window.evaluate_js(js_code)
        except WebViewException:
            # 窗口可能还没准备好，或者已经关闭
            # 这种情况下，静默失败，只在控制台打印简单的 stderr，防止递归调用 logger
            import sys
            print(f"[EventBus Error] Window not ready for event: {event_name}", file=sys.stderr)
        except Exception as e:
            import sys
            print(f"[EventBus Error] Unknown error: {e}", file=sys.stderr)

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
        payload = {
            "id": task_id,
            "type": task_type,
            "status": status,
            "progress": progress,
            "message": message,
            "metrics": metrics or {},
            "timestamp": current_ms()
        }
        cls.emit('global-progress', payload)
        