import mimetypes
import os
import socket
import sys
import ctypes
import webbrowser # 这个库用来打开浏览器
from pathlib import Path
from urllib.parse import unquote, urlparse
from backend.settings import HOME_DIR, BASE_RESOURCE_DIR

if sys.platform == "win32":
    import winreg
else:
    winreg = None

DEV_SERVER_HOST = "127.0.0.1"
DEV_SERVER_PORT = 5173
DEV_SERVER_URL = f"http://{DEV_SERVER_HOST}:{DEV_SERVER_PORT}"


def _is_windows():
    return sys.platform == "win32"


def _path_from_file_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return Path(uri)

    path = unquote(parsed.path)
    if _is_windows():
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        elif len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
    return Path(path)


def is_port_available(host: str = DEV_SERVER_HOST, port: int = DEV_SERVER_PORT, timeout: float = 0.5) -> bool:
    """
    检测指定主机的端口是否可达（用于判断前端开发服务器是否启动）
    :param host: 主机地址
    :param port: 端口号
    :param timeout: 超时时间（秒），避免阻塞
    :return: 端口可达返回 True，否则 False
    """
    try:
        # 创建 socket 连接，检测端口是否开放
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        # 超时/连接拒绝/系统错误，均视为端口不可用
        return False

# 部分用户的 Windows 注册表中缺少 .js 或 .css 的 MIME 类型定义。
# WebView2 处于安全考虑，如果收到的文件类型是 text/plain 而不是 application/javascript，会拒绝执行该脚本。
def fix_mime_types():
    # 强制让 Python 识别这些扩展名
    mimetypes.add_type('application/javascript', '.js')
    mimetypes.add_type('text/css', '.css')
    mimetypes.add_type('image/svg+xml', '.svg')

# 获取前端文件的路径
def get_entrypoint():
    """
    获取前端入口地址
    支持：开发模式、PyInstaller 标准模式、PyInstaller lib 归拢模式
    """
    fix_mime_types()
    # 定义前端开发服务器地址
    dev_server = DEV_SERVER_URL
    
    # 1. 获取程序根目录 (Base Directory)
    if not getattr(sys, 'frozen', False) and is_port_available(DEV_SERVER_HOST, DEV_SERVER_PORT):
        print(f"[Debug] 开发服务器端口可用，使用: {dev_server}")
        return dev_server
            
    # 2. 定义探测路径优先级
    # 优先级 1: PyInstaller 内部解压目录 (lib 文件夹内部)
    path_internal = BASE_RESOURCE_DIR / "frontend" / "dist" / "index.html"
    # 优先级 2: 外部根目录下的 dist (方便手动替换或更新)
    path_external = HOME_DIR / "frontend" / "dist" / "index.html"
    # 优先级 3: EXE 同级目录 (如果打包时把 index.html 移动到了顶层)
    path_root = HOME_DIR / "index.html"
    
    # 如果用户的 Windows 用户名包含中文、空格，或者软件安装路径包含特殊字符，
    # WebView2 在解析本地 file:// 链接时可能会因为没有正确转义而失败。
    # 使用 pathlib 的 as_uri() 方法强制转换为标准的 URI 格式。同时在vite.config.js中设置base: './'。
    # 3. 按优先级执行探测
    if path_internal.exists():
        return path_internal.absolute().as_uri()
    if path_root.exists():
        # 这里必须和其它 file:// 分支保持一致，统一返回标准 URI。
        # 原因：
        # 1. 原始本地路径字符串在中文、空格、#、% 等字符存在时，WebView2 的解析行为不稳定；
        # 2. 桌面模式的首屏黑屏往往不是 index.html 本身不存在，而是入口路径被浏览器内核错误解释；
        # 3. 统一走 as_uri() 后，所有本地入口都按同一规则编码，便于排除“路径分支不一致”导致的偶发问题。
        return path_root.absolute().as_uri()
    if path_external.exists():
        return path_external.absolute().as_uri() 
    # 4. 兜底回退：本地开发服务器
    from backend.utils.logger import logger 
    logger.debug(f"[Debug] Local assets not found. Searched in:\n - {path_external}\n - {path_internal}")
    if is_port_available(DEV_SERVER_HOST, DEV_SERVER_PORT): return dev_server
    return path_external.absolute().as_uri()

def get_local_frontend_root():
    candidates = [
        BASE_RESOURCE_DIR / "frontend" / "dist",
        HOME_DIR / "frontend" / "dist",
        HOME_DIR,
    ]
    for root in candidates:
        if (root / "index.html").exists(): return root
    return None

def get_webview2_version():
    """
    检测 WebView2 运行时版本。
    参考微软官方文档：https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution
    
    :return: 版本号字符串 (如 '119.0.2151.58')，如果未安装则返回 None
    """
    if not _is_windows() or winreg is None:
        return None

    # 定义需要检查的注册表位置
    # WebView2 运行时（Evergreen Bootstrapper）通常安装在以下位置
    reg_keys = [
        # 64-bit 系统上的 32-bit 视图 或 32-bit 系统 (System-wide)
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        # 纯 64-bit 视图 (System-wide) - 某些非标安装可能在此
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        # 当前用户安装 (User-specific)
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")
    ]

    for hkey, path in reg_keys:
        try:
            # 打开注册表键
            with winreg.OpenKey(hkey, path) as key:
                # 读取 'pv' (Product Version) 值
                version, type_ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0": return version
        except FileNotFoundError:
            continue
        except OSError:
            continue
            
    return None

def check_webview2_runtime():
    """
    包装函数，返回 bool
    """
    if not _is_windows():
        return True

    version = get_webview2_version()
    if version:
        # 在这里打印版本号用于调试
        print(f"Detected WebView2 Version: {version}")
        return True
    return False

def show_native_error(title, message):
    """
    显示启动错误；Windows 用原生 MessageBox，其它系统回退到终端输出。
    """
    if _is_windows() and hasattr(ctypes, "windll"):
        # 0x10 是错误图标 + 确定按钮
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0)
        return

    print(f"{title}\n{message}", file=sys.stderr)
    

def show_webview2_missing_dialog():
    """
    弹出一个带“是/否”按钮的对话框
    """
    title = "系统组件缺失"
    url = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
    message = (
        "检测到您的系统未安装 Microsoft Edge WebView2 runtime。\n\n"
        "这是运行本软件的核心组件。是否现在前往微软官网下载安装？\n\n"
        "安装完成后请重新启动程序。\n\n"
        f"下载地址：{url}"
    )
    if not _is_windows() or not hasattr(ctypes, "windll"):
        show_native_error(title, message)
        return
    
    # 0x10 (错误图标) | 0x4 (是/否按钮) | 0x10000 (置顶)
    # IDYES = 6, IDNO = 7
    res = ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x4 | 0x10000)
    
    if res == 6: # 用户点击了“是”
        webbrowser.open(url)

def _linux_desktop_packages_hint() -> str:
    """按发行版给出最小运行依赖安装命令，避免只报 ImportError。"""
    try:
        release = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        release = ""
    values = {}
    for line in release.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    distro = " ".join([values.get("ID", ""), values.get("ID_LIKE", "")]).lower()
    if any(name in distro for name in ("arch", "cachyos", "manjaro")):
        return "sudo pacman -S --needed gtk3 webkit2gtk-4.1 gobject-introspection"
    if any(name in distro for name in ("debian", "ubuntu", "linuxmint", "pop")):
        return "sudo apt install libgtk-3-0 libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1 python3-gi"
    if any(name in distro for name in ("fedora", "rhel", "centos")):
        return "sudo dnf install gtk3 webkit2gtk4.1 python3-gobject"
    if "suse" in distro:
        return "sudo zypper install gtk3 webkit2gtk-4_1 typelib-1_0-WebKit2-4_1"
    return "请安装 GTK3、WebKit2GTK 4.1 与 GObject Introspection 运行库"


def check_linux_desktop_runtime() -> tuple[bool, str]:
    """检查 GTK3 + WebKit2GTK 4.1 绑定与图形会话。"""
    if not sys.platform.startswith("linux"):
        return True, ""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False, "未检测到图形会话（DISPLAY/WAYLAND_DISPLAY 为空），无法启动桌面窗口。"

    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import Gtk, WebKit2  # noqa: F401
    except Exception as exc:
        return False, (
            "缺少 GTK3 / WebKit2GTK 4.1 的 Python 绑定。\n\n"
            f"当前错误：{exc}\n\n"
            f"请安装运行依赖：{_linux_desktop_packages_hint()}"
        )
    return True, ""


def validate_environment(on_error=None, require_webview2=True):
    """
    启动前的环境全校验
    """
    # 1. 检测组件
    wv2_version = get_webview2_version() if _is_windows() else None
    if require_webview2 and _is_windows() and not wv2_version:
        if on_error:
            on_error()
        show_webview2_missing_dialog()
        sys.exit(1)

    # 2. Linux 桌面模式检查 GTK/WebKit2GTK；浏览器模式不需要。
    if require_webview2 and sys.platform.startswith("linux"):
        desktop_ready, desktop_message = check_linux_desktop_runtime()
        if not desktop_ready:
            if on_error:
                on_error()
            show_native_error("Linux 桌面依赖缺失", desktop_message)
            sys.exit(1)

    # 3. 检测前端入口文件是否存在 (防止打包丢失资源)
    # 这里假设之前的 get_entrypoint 逻辑
    entry = get_entrypoint()
    if not entry.startswith('http'):
        p = _path_from_file_uri(entry)
        if not p.exists():
            if on_error:
                on_error()
            show_native_error(
                "资源加载失败",
                f"找不到前端入口文件：\n{p}\n\n请检查软件安装是否完整或被杀毒软件拦截。"
            )
            sys.exit(1)
