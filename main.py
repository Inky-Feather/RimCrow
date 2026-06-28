
try:
    import pip_system_certs # type: ignore
    # 该模块一旦被导入，就会自动为 ssl, requests, httpx, urllib3 打补丁
except ImportError:
    pass

import glob
import sys
import ctypes
import threading

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
import webbrowser
from backend._version import __version__
from backend.utils.logger import logger 
from backend.settings import settings, BASE_RESOURCE_DIR, HOME_DIR
from backend.utils.event_bus import EventBus
from backend.utils.tools import current_ms
from validate_environment import (
    get_entrypoint,
    get_local_frontend_root,
    is_port_available,
    show_native_error,
    validate_environment,
)

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
    persist_exit_state()

def persist_exit_state():
    """统一持久化退出状态"""
    settings.set('last_run_time', current_ms())
    settings.set('run_count', settings.get('run_count') + 1)
    settings.set('last_version', __version__)
    settings.save()  # 保存配置

def get_launch_mode():
    if "--browser" in sys.argv:
        return "browser"
    return "browser" if bool(getattr(settings.config, "browser_mode", False)) else "desktop"

def cleanup_update_remnants():
    """清理热更新遗留的 .old 文件"""
    if getattr(sys, 'frozen', False):
        # 查找当前目录下所有的 .old 文件
        for old_file in glob.glob(os.path.join(HOME_DIR, "*.old")):
            try:
                os.remove(old_file)
                # logger.info(f"Cleaned up old update file: {old_file}")
            except Exception:
                pass # 如果删不掉说明刚启动还被系统短暂占用，下次启动再删即可


def main():
    # 1. Windows 打包后的多进程支持 (必须放在最前面)
    multiprocessing.freeze_support()
    # 2. 清理热更新遗留的 .old 文件
    cleanup_update_remnants()

    # 加载启动屏
    try:
        import pyi_splash # type: ignore
    except ImportError:
        pyi_splash = None

    splash_state = {'module': pyi_splash}
    desktop_startup_state = {
        'window_shown': False,
        'page_loaded': False,
        'timeout_reported': False,
    }

    def close_startup_splash():
        """关闭启动屏，重复调用时自动忽略。"""
        splash_module = splash_state.get('module')
        if not splash_module: return

        try:
            splash_module.close()
        except Exception:
            logger.debug("Close splash failed", exc_info=True)
        finally:
            splash_state['module'] = None

    def mark_desktop_window_shown():
        """
        标记桌面窗口已经真正显示出来，并立即关闭 PyInstaller splash。

        设计原因：
        1. PyInstaller 启动画面的职责是“遮住程序尚未出现的瞬间”，不是“代替应用内加载动画”；
        2. 过去把 splash 关闭完全绑定到 `window.events.loaded`，一旦 WebView2 首屏没有触发 loaded，
           用户就只能一直看到启动图，误以为程序根本没启动；
        3. 因此这里改成：窗口一旦 shown，就立刻关闭 splash；后续页面仍可继续加载，但那属于应用内阶段。
        """
        desktop_startup_state['window_shown'] = True
        close_startup_splash()

    def mark_desktop_page_loaded():
        """
        标记桌面首屏页面已完成加载。

        这个信号仍然保留，因为它可以区分：
        - 窗口已经出现，但页面迟迟未完成 loaded；
        - 页面真正就绪。
        这样超时处理时就能给出更准确的错误提示。
        """
        desktop_startup_state['page_loaded'] = True
        close_startup_splash()

    def report_desktop_startup_timeout():
        """
        桌面模式首屏加载超时兜底。

        原理：
        - 如果窗口一直没有 shown，大概率是 WebView / GUI 内核本身没起来；
        - 如果窗口 shown 了但页面始终没 loaded，更像是 file:// 资源加载失败、WebView2 渲染异常、
          杀软/显卡/代理导致的页面初始化问题；
        - 无论哪种情况，PyInstaller splash 都不能继续占着屏幕，必须先关闭，再把原因告诉用户。
        """
        if desktop_startup_state['page_loaded'] or desktop_startup_state['timeout_reported']:
            return

        desktop_startup_state['timeout_reported'] = True
        close_startup_splash()

        if desktop_startup_state['window_shown']:
            show_native_error(
                "桌面模式加载超时",
                "桌面窗口已经打开，但首页长时间未完成加载。\n\n"
                "这通常与 WebView2 本地页面加载失败、显卡兼容性、代理设置或安全软件拦截有关。\n\n"
                "您可以先尝试使用网页模式启动；如果问题反复出现，请检查日志并反馈。"
            )
        else:
            show_native_error(
                "桌面窗口启动失败",
                "程序初始化已开始，但桌面窗口长时间未显示。\n\n"
                "这通常与 WebView2 / 图形界面初始化失败有关。\n\n"
                "您可以先尝试使用网页模式启动；如果问题反复出现，请检查日志并反馈。"
            )

    def start_desktop_startup_timeout_guard(timeout_seconds: float = 12.0):
        """
        启动桌面模式首屏超时守护线程。

        说明：
        - 这里不主动终止进程，只负责关闭 splash 并给用户明确提示；
        - 这样既避免“看起来永远卡在启动图”，也保留了程序后续自行恢复的可能。
        """
        def guard():
            threading.Event().wait(timeout_seconds)
            report_desktop_startup_timeout()

        threading.Thread(
            target=guard,
            name="rmm-desktop-startup-timeout",
            daemon=True,
        ).start()

    # 2. 检测是否为 Steam Worker 模式
    if len(sys.argv) > 1 and sys.argv[1] == "--steam-worker":
        close_startup_splash()
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

    # 捕获启动阶段未处理异常，确保异常弹窗前启动屏已经关闭
    try:
        # 0. 先校验环境，有问题直接弹原生框并退出
        launch_mode = get_launch_mode()
        validate_environment(on_error=close_startup_splash, require_webview2=launch_mode != "browser")

        # 只有主进程才会执行到这里，此时再导入 GUI 库
        # 避免 Worker 进程加载浏览器内核，节省内存并防止冲突
        from backend.api import API
        
        # 记录启动信息
        logger.info(f"Starting RimModManager... Ver: {__version__ or 'Dev'}")
        logger.debug(f"Debug Mode: {settings.config.debug_mode}")
        logger.info(f"Launch Mode: {launch_mode}")
        
        api = API(runtime_mode=launch_mode)
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
        additional_args.append("--disable-features=RendererCodeIntegrity") 
        # 某些环境下需要这个来允许本地文件交互
        additional_args.append('--allow-file-access-from-files') 
        
        # 设置环境变量传给 WebView2
        os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = " ".join(additional_args)
        entrypoint = get_entrypoint()
        
        if launch_mode == "browser":
            from backend.browser_runtime import BrowserAppServer

            static_root = get_local_frontend_root()
            browser_runtime = BrowserAppServer(
                api=api,
                static_root=static_root,
                use_dev_server=(not getattr(sys, 'frozen', False) and is_port_available("localhost", 5173)),
            )
            browser_runtime.start()
            api.set_browser_base_url(browser_runtime.base_url)
            EventBus.set_browser_dispatcher(browser_runtime.broadcast)
            close_startup_splash()
            launch_url = browser_runtime.get_launch_url()
            logger.info(f"Browser launch URL: {launch_url}")
            webbrowser.open(launch_url)
            browser_runtime.wait_for_shutdown()
            browser_runtime.stop()
            api.cleanup()
            persist_exit_state()
            return

        import webview
        # 创建窗口
        window = webview.create_window(
            'RimModManager', 
            url=entrypoint,
            js_api=api,
            width=window_width, # 读取记忆的窗口大小
            height=window_height,
            resizable=True,
            background_color='#0f172a', # 与前端背景色一致，防止白屏闪烁
            frameless=False, # 可以选择开启无边框模式来实现完全自定义标题栏
        )
        logger.info(f"Entrypoint: {entrypoint}")
        if window: 
            api.set_window(window)
            # `shown` 是“窗口可见”的信号，用它来结束 PyInstaller 启动画面；
            # `loaded` 仍然保留，用于区分页面是否真正完成加载，并配合超时提示给用户更准确的信息。
            window.events.shown += mark_desktop_window_shown
            window.events.loaded += mark_desktop_page_loaded
            window.events.resized += on_resized            # 窗口尺寸变化时触发
            window.events.closed += api.cleanup
            window.events.closed += on_main_window_closed  # 窗口关闭时退出应用
        # 注册窗口到事件总线
        EventBus.set_window(window) # type: ignore
        start_desktop_startup_timeout_guard()
        # 捕获全局未处理异常
        webview.start(debug=settings.config.debug_mode) # debug=True 允许在窗口里按 F12 看控制台
    except Exception as e:
        close_startup_splash()
        logger.critical("Application crashed!", exc_info=True)
        raise e


if __name__ == '__main__':
    main()
