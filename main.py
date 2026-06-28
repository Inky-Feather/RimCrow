import builtins
import multiprocessing
import sys
import os
from backend.utils.logger import logger 


from icecream import ic
# builtins.print = ic  # 重定向 print 到 logger.debug
# from icecream.builtins import install as ic_install
# ic_install()    # 全局启用 icecream，利用 Python 的动态特性实现“一次安装，到处运行”。

def main():
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
            mod_id = int(sys.argv[3])
            run_steam_worker(action, mod_id)
        except Exception as e:
            logger.error(f"Worker Error: {e}")
        
        # 干完活直接退出，不要启动 GUI
        sys.exit(0)

    import webview
    from pathlib import Path
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
        """
        获取前端入口地址
        支持：开发模式、PyInstaller 标准模式、PyInstaller lib 归拢模式
        """
        # 1. 获取程序根目录 (Base Directory)
        if getattr(sys, 'frozen', False):
            # --- 打包后的环境 ---
            # sys.executable 指向 .exe 文件的绝对路径
            base_dir = Path(sys.executable).parent
            # 额外：处理 --contents-directory lib 情况
            # 如果内部资源在 _MEIPASS 目录下 (即 lib 文件夹内)
            meipass_dir = Path(getattr(sys, '_MEIPASS', base_dir))
        else:
            # __file__ 指向当前 main.py 的位置
            base_dir = Path(__file__).parent.resolve()
            meipass_dir = base_dir
        # 2. 定义探测路径优先级
        # 优先级 1: 外部根目录下的 dist (方便手动替换或更新)
        path_external = base_dir / "frontend" / "dist" / "index.html"
        # 优先级 2: EXE 同级目录 (如果打包时把 index.html 移动到了顶层)
        path_root = base_dir / "index.html"
        # 优先级 3: PyInstaller 内部解压目录 (lib 文件夹内部)
        path_internal = meipass_dir / "frontend" / "dist" / "index.html"
        # 3. 按优先级执行探测
        if path_external.exists():
            return str(path_external)
        if path_root.exists():
            return str(path_root)
        if path_internal.exists():
            return str(path_internal)
        # 4. 兜底回退：本地开发服务器
        logger.debug(f"[Debug] Local assets not found. Searched in:\n - {path_external}\n - {path_internal}")
        return "http://localhost:5173"

        
    def on_resized(width, height):
        """窗口尺寸变化时触发"""
        settings.config.window_width = width
        settings.config.window_height = height
        
    def on_main_window_closed():
        """窗口关闭时触发"""
        settings.save()  # 保存配置
        # 这里的 0 是返回码，表示正常退出
        os._exit(0)

    
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
    logger.info(f"Entrypoint: {get_entrypoint()}")
    if window: 
        window.events.resized += on_resized            # 窗口尺寸变化时触发
        window.events.closed += api.cleanup
        window.events.closed += on_main_window_closed  # 窗口关闭时退出应用
    # 注册窗口到事件总线
    EventBus.set_window(window) # type: ignore
    # 捕获全局未处理异常
    try: # 启动
        webview.start(debug=settings.config.debug_mode) # debug=True 允许在窗口里按 F12 看控制台
    except Exception as e:
        logger.critical("Application crashed!", exc_info=True)
        raise e


if __name__ == '__main__':
    main()