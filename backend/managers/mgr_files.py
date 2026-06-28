import os
import shutil
import threading
import subprocess
import platform
from urllib.parse import unquote, quote
from http.server import HTTPServer, SimpleHTTPRequestHandler
from PIL import Image
import webview # 引入 webview 库
from send2trash import send2trash
from backend.settings import CACHE_DIR


class LocalAssetHandler(SimpleHTTPRequestHandler):
    """
    内部类：HTTP 请求处理器
    拦截 /image?path=... 请求并返回文件流
    """
    def do_GET(self):
        # 只处理 /image 路径
        if self.path.startswith('/image?path='):
            try:
                # 1. 解析参数
                query_part = self.path.split('path=', 1)[1]
                local_path = unquote(query_part) # 解码 URL

                # 2. 安全与存在性检查
                if os.path.exists(local_path) and os.path.isfile(local_path):
                    self.send_response(200)
                    
                    # 3. 设置 MIME 类型
                    ext = os.path.splitext(local_path)[1].lower()
                    ctype = 'application/octet-stream'
                    if ext == '.png': ctype = 'image/png'
                    elif ext in ['.jpg', '.jpeg']: ctype = 'image/jpeg'
                    elif ext == '.webp': ctype = 'image/webp'
                    elif ext == '.gif': ctype = 'image/gif'
                    
                    self.send_header('Content-type', ctype)
                    self.send_header('Access-Control-Allow-Origin', '*') # 允许跨域
                    self.send_header('Cache-Control', 'max-age=604800') # 强缓存7天(本地文件很少变)
                    self.end_headers()
                    
                    # 4. 写入文件流 (零拷贝传输)
                    with open(local_path, 'rb') as f:
                        # shutil.copyfileobj(f, self.wfile) # 这种方式更高效
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_error(404, "File not found")
                    return
            # 忽略连接中断错误 ---
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                # 客户端断开了连接（通常是列表快速滚动导致的），无需处理，直接返回
                return
            except Exception as e:
                # 在控制台打印详细中文错误方便调试
                print(f"Asset Server Error ({local_path if 'local_path' in locals() else 'unknown'}): {e}")
                # 发送给客户端的必须是 ASCII 字符，不要发送 str(e) 因为可能包含中文
                try:
                    self.send_error(500, "Internal Server Error")
                except:
                    pass # 如果发送错误信息时连接也断了，就彻底忽略
                return
        
        # 其他请求直接 400
        self.send_error(400, "Invalid Request Path")

    def log_message(self, format, *args):
        # 重写此方法以屏蔽控制台日志输出，保持清爽
        pass


class FileManager:
    """
    统一文件管理器
    职责：
    1. 启动本地 HTTP 资源服务器
    2. 生成和管理缩略图
    3. 提供文件/文件夹打开操作
    4. 提供本地路径到 URL 的转换
    """
    
    def __init__(self):
        # 1. 确保存储目录存在
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR, exist_ok=True)
            
        # 2. 启动 HTTP Server
        self._port = 0
        self._server_thread = None
        self._start_asset_server()

    # =========================================================
    #  1. HTTP Server 管理
    # =========================================================
    
    def _start_asset_server(self):
        """在后台线程启动极简 HTTP 服务器"""
        try:
            # 端口设为 0，让 OS 自动分配空闲端口
            server = HTTPServer(('127.0.0.1', 0), LocalAssetHandler)
            self._port = server.server_address[1]
            
            self._server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            self._server_thread.start()
            print(f"File Manager: Asset Server started on port {self._port}")
        except Exception as e:
            print(f"File Manager: Failed to start asset server: {e}")

    def get_asset_url(self, local_path):
        """
        将本地绝对路径转换为前端可访问的 HTTP URL
        例如: C:/Mod/Preview.png -> http://127.0.0.1:xxxxx/image?path=C%3A%2FMod%2FPreview.png
        """
        if not local_path or not self._port:
            return ""
        # 对路径进行 URL 编码
        safe_path = quote(local_path)
        return f"http://127.0.0.1:{self._port}/image?path={safe_path}"

    # =========================================================
    #  2. 缩略图管理 (Thumbnail)
    # =========================================================

    def get_thumbnail_path(self, package_id):
        """
        获取某个 Mod 已生成的缩略图路径 (物理路径)。
        如果不存在返回 None。
        """
        target_path = os.path.join(CACHE_DIR, f"{package_id}.webp")
        if os.path.exists(target_path):
            return target_path
        return None

    def ensure_thumbnail(self, package_id, original_path, max_size=64):
        """
        检查并生成缩略图。
        如果缩略图已存在且未过期，直接返回路径；否则重新生成。
        :return: 缩略图的绝对路径 (str) 或 None
        """
        if not original_path or not os.path.exists(original_path):
            return None

        target_path = os.path.join(CACHE_DIR, f"{package_id}.webp")

        # 检查是否需要重新生成 (存在性 + 修改时间)
        need_generate = True
        if os.path.exists(target_path):
            try:
                # 如果原图修改时间比缩略图早，说明缩略图是最新的
                if os.path.getmtime(original_path) <= os.path.getmtime(target_path):
                    need_generate = False
            except OSError:
                pass

        if not need_generate:
            return target_path

        # 开始生成
        try:
            with Image.open(original_path) as img:
                # 预处理：处理调色板模式、RGBA 等
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    # 创建白色背景处理透明度 (或者保留透明度转为 RGBA，WebP 支持透明)
                    # 这里为了列表显示统一，建议转为 RGB 或保留 RGBA
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                else:
                    img = img.convert('RGB')
                
                # 缩放 (长宽最大 128px)
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # 保存 (WEBP 格式，体积小速度快)
                img.save(target_path, 'WEBP', quality=80)
                return target_path
        except Exception as e:
            # print(f"Thumbnail error for {package_id}: {e}")
            return None

    # =========================================================
    #  3. 常规文件操作
    # =========================================================

    @staticmethod
    def open_in_explorer(path):
        """在资源管理器中打开"""
        if not path or not os.path.exists(path):
            raise FileNotFoundError('路径不存在！')

        if os.path.isfile(path):
            path = os.path.dirname(path)

        system_name = platform.system()
        try:
            if system_name == 'Windows':
                os.startfile(path)
            elif system_name == 'Darwin':
                subprocess.call(['open', path])
            else:
                subprocess.call(['xdg-open', path])
            return None
        except Exception as e:
            raise Exception(f"打开路径时出错: {e}")

    @staticmethod
    def delete_path(path):
        """删除文件/文件夹"""
        try:
            # 转换为绝对路径，避免相对路径问题
            abs_path = os.path.abspath(path)
            if os.path.isfile(abs_path) or os.path.isdir(abs_path):
                send2trash(abs_path)
                return True
        except Exception as e:
            raise Exception(f"删除路径时出错: {e}")
    
    @staticmethod
    def select_folder_dialog(initial_dir=''):
        """
        打开系统原生的文件夹选择框
        """
        # 获取当前活动窗口
        if len(webview.windows) > 0:
            window = webview.windows[0]
            # 调用原生对话框
            # allow_multiple=False: 单选
            result = window.create_file_dialog(
                webview.FileDialog.FOLDER, 
                directory=initial_dir if initial_dir else '', 
                allow_multiple=False
            )
            # result 返回的是一个列表 (因为可能多选)，或者 None (取消)
            if result and len(result) > 0:
                return result[0]
        return None

    @staticmethod
    def select_file_dialog(initial_dir='', file_types=('XML Files (*.xml;*.rws)', 'All Files (*.*)')):
        """
        打开系统原生的文件选择框
        file_types 示例: ('XML Files (*.xml;*.rws)', 'All Files (*.*)')
        """
        if len(webview.windows) > 0:
            window = webview.windows[0]
            result = window.create_file_dialog(
                webview.FileDialog.OPEN, 
                directory=initial_dir if initial_dir else '', 
                allow_multiple=False,
                file_types=file_types
            )
            if result and len(result) > 0:
                return result[0]
        return None
    
    @staticmethod
    def save_file_dialog(initial_dir='', default_filename='ModsConfig.xml', file_types=('XML Files (*.xml;*.rws)', 'All Files (*.*)')):
        """
        打开系统原生的文件保存框
        """
        if len(webview.windows) > 0:
            window = webview.windows[0]
            # pywebview 的 create_file_dialog 参数：
            # dialog_type, directory, allow_multiple, save_filename, file_types
            result = window.create_file_dialog(
                webview.FileDialog.SAVE, 
                directory=initial_dir, 
                save_filename=default_filename, # 设置默认文件名
                allow_multiple=False,
                file_types=file_types
            )
            print(f"用户选择保存路径: {result}")
            if result and len(result) > 0:
                return result[0]
                
        return None
    
    