import webview
import os
from icecream.builtins import install as ic_install
ic_install()    # 全局启用 icecream，利用 Python 的动态特性实现“一次安装，到处运行”。

from backend.api import API
from backend.settings import settings
from backend.utils.event_bus import EventBus


# 获取前端文件的路径
def get_entrypoint():
    # 调试模式：如果是开发环境，直接加载 Vue 的开发服务器地址
    # 正式打包后，会加载 dist 目录下的 html
    if os.path.exists(os.path.join(os.getcwd(), "frontend/dist/index.html")):
         return os.path.join(os.getcwd(), "frontend/dist/index.html")
    else:
        # 开发时，请确保先启动了 frontend 的 npm run dev
        return "http://localhost:5173"

if __name__ == '__main__':
    api = API()
    window_width = int(settings.config.window_width)  # 默认1400px
    window_height = int(settings.config.window_height)  # 默认900px
    
    # 创建窗口
    window = webview.create_window(
        'RimWorld Mod Manager', 
        url=get_entrypoint(),
        js_api=api,
        width=window_width, # 读取记忆的窗口大小
        height=window_height,
        resizable=True,
        background_color='#0f172a', # 与前端背景色一致，防止白屏闪烁
        frameless=False # 可以选择开启无边框模式来实现完全自定义标题栏
    )
    # 注册窗口到事件总线
    EventBus.set_window(window) # type: ignore
    # 启动
    webview.start(debug=True) # debug=True 允许在窗口里按 F12 看控制台