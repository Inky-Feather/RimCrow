import builtins
import sys
import webview
import os
from backend.utils.logger import logger 


from icecream import ic
builtins.print = ic  # 重定向 print 到 logger.debug
# from icecream.builtins import install as ic_install
# ic_install()    # 全局启用 icecream，利用 Python 的动态特性实现“一次安装，到处运行”。


from backend.api import API
from backend.settings import settings
from backend.utils.event_bus import EventBus


def get_webview_proxy_args():
    """生成 WebView2 的启动参数"""
    cfg = settings.config.network.proxy
    if not cfg.enabled:
        return {}
    
    # 构造代理服务器字符串
    # WebView2 (Chromium) 格式: --proxy-server="http://user:pass@1.2.3.4:8080"
    # 注意：Chromium 对带密码的代理支持有限，通常建议本地无密码代理
    proxy_str = f"{cfg.type}://{cfg.host}:{cfg.port}"
    
    # 构造 bypass 规则
    # Chromium 格式: --proxy-bypass-list="foobar.com;*baz.com"
    bypass_str = ";".join(cfg.bypass_list)
    
    return {
        "proxy_server": proxy_str,
        "proxy_bypass_list": bypass_str
    }

# 获取前端文件的路径
def get_entrypoint():
    # 调试模式：如果是开发环境，直接加载 Vue 的开发服务器地址
    # 正式打包后，会加载 dist 目录下的 html
    if os.path.exists(os.path.join(os.getcwd(), "frontend/dist/index.html")):
         return os.path.join(os.getcwd(), "frontend/dist/index.html")
    else:
        # 正式打包前，确保先启动了 frontend 的 npm run dev
        return "http://localhost:5173"
    
def on_main_window_closed():
    # 这里的 0 是返回码，表示正常退出
    os._exit(0)

if __name__ == '__main__':
    # 记录启动信息
    logger.info(f"Starting RimModManager... Ver: {settings.config.game_version or 'Dev'}")
    logger.debug(f"Debug Mode: {settings.config.debug_mode}")
    
    api = API()
    window_width = int(settings.config.window_width)  # 默认1400px
    window_height = int(settings.config.window_height)  # 默认900px
    
     # 获取代理参数
    # Pywebview 目前对代理的直接支持有限，通常需要通过底层 flag 传递
    # 对于 WebView2 (Windows)，可以通过 os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']
    
    proxy_args = get_webview_proxy_args()
    if proxy_args:
        args = []
        if 'proxy_server' in proxy_args:
            args.append(f"--proxy-server={proxy_args['proxy_server']}")
        if 'proxy_bypass_list' in proxy_args:
            args.append(f"--proxy-bypass-list={proxy_args['proxy_bypass_list']}")
            
        # 设置环境变量传给 WebView2
        os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = " ".join(args)
    
    # 创建窗口
    window = webview.create_window(
        'RimModManager', 
        url=get_entrypoint(),
        js_api=api,
        width=window_width, # 读取记忆的窗口大小
        height=window_height,
        resizable=True,
        background_color='#0f172a', # 与前端背景色一致，防止白屏闪烁
        frameless=False, # 可以选择开启无边框模式来实现完全自定义标题栏
    )
    if window: window.events.closed += on_main_window_closed  # 窗口关闭时退出应用
    # 注册窗口到事件总线
    EventBus.set_window(window) # type: ignore
    # 捕获全局未处理异常
    try: # 启动
        webview.start(debug=settings.config.debug_mode) # debug=True 允许在窗口里按 F12 看控制台
    except Exception as e:
        logger.critical("Application crashed!", exc_info=True)
        raise e