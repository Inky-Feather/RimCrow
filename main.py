
try:
    import pip_system_certs
    # 该模块一旦被导入，就会自动为 ssl, requests, httpx, urllib3 打补丁
except ImportError:
    pass

import sys
import ctypes

def enable_dpi_awareness():
    """强制开启 Windows DPI 感知，防止多屏缩放导致的窗口拉伸"""
    if sys.platform == 'win32':
        try:
            # 适用于 Windows 10/11
            ctypes.windll.shcore.SetProcessDpiAwareness(1) # PROCESS_SYSTEM_DPI_AWARE
        except Exception:
            try:
                # 适用于老版本 Windows
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
            
# 必须在创建任何窗口前调用
enable_dpi_awareness()

import multiprocessing
import os
from backend._version import __version__
from backend.utils.logger import logger 
from backend.settings import settings, BASE_RESOURCE_DIR, HOME_DIR
from backend.utils.event_bus import EventBus
from backend.utils.tools import current_ms
from validate_environment import get_entrypoint, validate_environment

from icecream import ic
import builtins
# builtins.print = ic  # 重定向 print 到 logger.debug
# from icecream.builtins import install as ic_install
# ic_install()    # 全局启用 icecream，利用 Python 的动态特性实现“一次安装，到处运行”。


# 强制切换工作目录到 exe 所在文件夹
# 解决任务栏启动找不到配置文件的问题
def setup_working_directory():
    os.chdir(HOME_DIR)
    # 顺便把这个路径加到 sys.path，防止导包报错
    sys.path.insert(0, str(HOME_DIR))

# 执行逻辑：如果是 steam-worker 模式，跳过 chdir
if "--steam-worker" not in sys.argv:
    setup_working_directory()
else:
    # Worker 模式下，不需要切换目录（因为主进程已经通过 cwd 指定好了）
    # 但可能仍需要把项目根目录加入 sys.path，以便能 import 后端的模块
    app_path = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        app_path = os.path.dirname(sys.executable)
    if app_path not in sys.path:
        sys.path.insert(0, app_path)
    
def get_webview_proxy_args():
    """生成 WebView2 的启动参数"""
    cfg = settings.config.network.proxy
    if not cfg.enabled: return {}
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


    
def on_resized(width, height):
    """窗口尺寸变化时触发"""
    settings.config.window_width = width
    settings.config.window_height = height
    
def on_main_window_closed():
    """窗口关闭时触发"""
    settings.set('last_run_time', current_ms())
    settings.set('run_count', settings.get('run_count') + 1)
    settings.set('last_version', __version__)
    settings.save()  # 保存配置


def main():
    # 0. 先校验环境，有问题直接弹原生框并退出
    validate_environment()
    
    # 1. Windows 打包后的多进程支持 (必须放在最前面)
    multiprocessing.freeze_support()

    # 2. 检测是否为 Steam Worker 模式
    if len(sys.argv) > 1 and sys.argv[1] == "--steam-worker":
        # 此时是一个短命的子进程
        # 这里的 import 放在内部，避免影响主进程启动速度
        from backend.managers.mgr_steam import run_steam_worker
        try:
            # 解析参数: [exe, --steam-worker, action, mod_id]
            action = sys.argv[2]
            payload  = sys.argv[3]
            run_steam_worker(action, payload)
        except Exception as e:
            logger.error(f"Worker Error: {e}")
        
        # 干完活直接退出，不要启动 GUI
        sys.exit(0)
        
    # 加载启动屏
    try:
        import pyi_splash # type: ignore
    except ImportError:
        pyi_splash = None

    # 只有主进程才会执行到这里，此时再导入 GUI 库
    # 避免 Worker 进程加载浏览器内核，节省内存并防止冲突
    import webview
    from backend.api import API
    
    # 记录启动信息
    logger.info(f"Starting RimModManager... Ver: {__version__ or 'Dev'}")
    logger.debug(f"Debug Mode: {settings.config.debug_mode}")
    
    api = API()
    window_width = int(settings.config.window_width)  # 默认1400px
    window_height = int(settings.config.window_height)  # 默认900px
    
    # 获取代理参数
    # Pywebview 目前对代理的直接支持有限，通常需要通过底层 flag 传递
    # 对于 WebView2 (Windows)，可以通过 os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']
    additional_args = []
    proxy_args = get_webview_proxy_args()
    if proxy_args:
        if 'proxy_server' in proxy_args:
            additional_args.append(f"--proxy-server={proxy_args['proxy_server']}")
        if 'proxy_bypass_list' in proxy_args:
            additional_args.append(f"--proxy-bypass-list={proxy_args['proxy_bypass_list']}")
    
    # [关键] 解决部分机器黑屏/闪退问题
    # --disable-features=RendererCodeIntegrity: 解决部分杀毒软件注入导致渲染进程崩溃
    # --disable-gpu: 最后的手段，解决显卡兼容性
    # additional_args.append("--disable-features=RendererCodeIntegrity") 
    # 某些环境下需要这个来允许本地文件交互
    additional_args.append('--allow-file-access-from-files') 
            
    # 设置环境变量传给 WebView2
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = " ".join(additional_args)
    
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
    logger.info(f"Entrypoint: {get_entrypoint()}")
    if window: 
        api.set_window(window)
        window.events.resized += on_resized            # 窗口尺寸变化时触发
        window.events.closed += api.cleanup
        window.events.closed += on_main_window_closed  # 窗口关闭时退出应用
    # 注册窗口到事件总线
    EventBus.set_window(window) # type: ignore
    # 捕获全局未处理异常
    try: # 启动主窗口
        if pyi_splash: pyi_splash.close()
        webview.start(api.cleanup, debug=settings.config.debug_mode) # debug=True 允许在窗口里按 F12 看控制台
    except Exception as e:
        logger.critical("Application crashed!", exc_info=True)
        raise e


if __name__ == '__main__':
    main()