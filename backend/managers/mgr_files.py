from concurrent.futures import ThreadPoolExecutor
import os
import shutil
import tempfile
import threading
import subprocess
import platform
from urllib.parse import unquote, quote
from http.server import HTTPServer, SimpleHTTPRequestHandler
from PIL import Image
import webview # 引入 webview 库
from send2trash import send2trash
from backend.settings import CACHE_DIR
from backend.utils.logger import logger


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
                logger.error(f"Asset Server Error ({local_path if 'local_path' in locals() else 'unknown'}): {e}")
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
    # 定义内部常量，统一管理链接目录名
    LINK_PREFIX = "_Link_" # 使用统一前缀识别由管理器创建的链接
    
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
            logger.info(f"File Manager: Asset Server started on port {self._port}")
        except Exception as e:
            logger.error(f"File Manager: Failed to start asset server: {e}")

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
            logger.error(f"Thumbnail error for {package_id}: {e}")
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
            logger.info(f"用户选择保存路径: {result}")
            if result and len(result) > 0:
                return result[0]
                
        return None
    
    
    # =========================================================
    #  4. 动态链接部署 (Junction/Symlink)
    # =========================================================

    @staticmethod
    def sync_links(local_mods_path, workshop_mod_paths: list):
        """
        极致增量同步逻辑：
        1. 只要不在 workshop_mod_paths 里的链接，全部物理删除。
        2. 指向路径错误的链接，全部删除并重建。
        3. 已经正确指向的链接，绝对不动（0操作）。
        """
        # logger.info(f"Sync links: local_mods_path={local_mods_path}, workshop_mod_paths={workshop_mod_paths}")
        if not local_mods_path or not os.path.exists(local_mods_path):
            logger.error("Sync links failed: Local mods path does not exist.")
            return False

        # --- 1. 准备目标清单 (使用小写 Key 解决 Windows 大小写不敏感问题) ---
        target_map = {}
        for src in workshop_mod_paths:
            if not src: continue
            wid = os.path.basename(src)
            link_name = f"{FileManager.LINK_PREFIX}{wid}"
            # 存入规范化的绝对路径用于比对
            target_map[link_name.lower()] = {
                'raw_name': link_name,
                'src_path': os.path.normpath(os.path.abspath(src))
            }

        # --- 2. 扫描磁盘并识别“必须删除”的项 ---
        # 我们遍历目录下的所有内容，只要命中前缀且不在 target_map 中，就是删除目标
        to_delete_paths = []
        existing_valid_keys = set()

        try:
            for name in os.listdir(local_mods_path):
                # 仅处理由本管理器管理的文件夹/链接 (带前缀)
                if name.startswith(FileManager.LINK_PREFIX):
                    name_lower = name.lower()
                    full_path = os.path.normpath(os.path.join(local_mods_path, name))
                    
                    # 判定逻辑：
                    # A. 这个名字在目标清单里吗？
                    if name_lower in target_map:
                        expected_src = target_map[name_lower]['src_path']
                        # B. 它是否已经正确指向了目标？
                        if FileManager._is_link_correct(full_path, expected_src):
                            # 完全正确，记录下来，后续不需要重复创建
                            existing_valid_keys.add(name_lower)
                            continue 
                    
                    # 如果运行到这里，说明：
                    # 1. 名字不在目标清单 (不再需要的 Mod)
                    # 2. 名字在清单但指向错误 (需要重建)
                    # 3. 这是一个断头链接 (指向的源已删)
                    to_delete_paths.append(full_path)
        except OSError as e:
            logger.error(f"Scan directory failed: {e}")

        # --- 3. 执行物理删除 (针对 Windows Junction 的强力清除) ---
        if to_delete_paths:
            logger.info(f"Cleaning {len(to_delete_paths)} stale links...")
            # 关键优化点：不再循环调用 subprocess，而是批量处理
            FileManager._remove_entries_windows_batch(to_delete_paths)

        # --- 4. 计算需要补齐的链接 ---
        links_to_create = []
        for key, info in target_map.items():
            if key not in existing_valid_keys:
                dst_path = os.path.join(local_mods_path, info['raw_name'])
                links_to_create.append((info['src_path'], dst_path))

        # --- 5. 执行闪电创建 ---
        if links_to_create:
            logger.info(f"Creating {len(links_to_create)} missing links...")
            FileManager._create_links_windows_batch(links_to_create)

        logger.info(f"Sync Result -> Kept: {len(existing_valid_keys)}, Created: {len(links_to_create)}, Deleted: {len(to_delete_paths)}")
        return True

    @staticmethod
    def _is_link_correct(link_path, expected_src):
        """判断链接是否有效且指向正确"""
        try:
            # lexists 用于检测路径是否存在（包括断头链接）
            if not os.path.lexists(link_path): 
                return False
            # samefile 会抛出异常如果路径不存在，所以这里必须配合 try
            # 它能跨越斜杠差异和大小写差异判断物理底层是否一致
            return os.path.samefile(link_path, expected_src)
        except:
            return False

    @staticmethod
    def _remove_entries_windows_batch(paths: list):
        """
        最高效的 Windows 删除方式：
        将所有 rd 指令写入一个批处理文件，一次性调用。
        """
        if not paths: return
        
        if platform.system() != 'Windows':
            # 非 Windows 系统，Python 原生 unlink 极快，不需要批处理
            for path in paths:
                try:
                    if os.path.islink(path): os.unlink(path)
                    else: shutil.rmtree(path, ignore_errors=True)
                except: pass
            return

        # 构造批量删除指令
        # rd /s /q 强制删除目录或 Junction
        lines = [f'rd /s /q "{os.path.normpath(p)}"' for p in paths]
        batch_content = "@echo off\n" + "\n".join(lines)

        with tempfile.NamedTemporaryFile(delete=False, suffix="_del.bat", mode="w", encoding="gbk") as tf:
            tf.write(batch_content)
            temp_path = tf.name

        try:
            # 只启动一个进程，执行成百上千条删除指令
            subprocess.run(temp_path, shell=True, capture_output=True, check=True)
        except Exception as e:
            logger.error(f"Batch delete failed: {e}")
            # 如果批处理失败，尝试最后的原生备份方案
            for p in paths:
                try: os.rmdir(p)
                except: pass
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)
    
    @staticmethod
    def _create_links_windows_batch(link_tasks: list):
        """批处理创建逻辑 (保持之前的高效实现)"""
        if not link_tasks: return
        if platform.system() != 'Windows':
            for src, dst in link_tasks:
                try: os.symlink(src, dst)
                except: pass
            return

        lines = [f'mklink /j "{dst}" "{src}"' for src, dst in link_tasks]
        batch_content = "@echo off\n" + "\n".join(lines)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".bat", mode="w", encoding="gbk") as tf:
            tf.write(batch_content)
            temp_path = tf.name

        try:
            subprocess.run(temp_path, shell=True, capture_output=True, check=True)
        finally:
            if os.path.exists(temp_path): os.remove(temp_path)
    
    
    