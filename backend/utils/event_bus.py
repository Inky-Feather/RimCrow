# backend/utils/event_bus.py
from webview import Window

class EventBus:
    _window = None

    @classmethod
    def set_window(cls, window: Window):
        cls._window = window

    @classmethod
    def emit(cls, event_name, data=None):
        """
        向前端发送事件。
        前端监听: window.addEventListener('pywebview-event', (e) => { ... })
        或者使用 pywebview 专用的 window.pywebview.api 订阅机制（如果实现了）。
        这里推荐使用 evaluate_js 原生 CustomEvent，兼容性好。
        """
        if cls._window:
            import json
            # 构造 JS 代码触发 CustomEvent
            # 前端监听: window.addEventListener('scan-progress', (e) => console.log(e.detail))
            js_payload = json.dumps(data)
            js_code = f"""
                window.dispatchEvent(new CustomEvent('{event_name}', {{ detail: {js_payload} }}));
            """
            # 在主线程执行 JS (pywebview 可以在任意线程调用 evaluate_js，它内部会处理线程安全)
            cls._window.evaluate_js(js_code)