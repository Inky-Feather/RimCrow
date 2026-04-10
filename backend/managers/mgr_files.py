import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import subprocess
import platform
import time
from typing import Any, Dict
from urllib.parse import quote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image
import requests
import urllib.parse
import webview # 引入 webview 库
from send2trash import send2trash
from backend.managers.mgr_game import GameManager
from backend.settings import GALLERY_CACHE_DIR, THUMBNAIL_CACHE_DIR
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger


class LocalAssetHandler(SimpleHTTPRequestHandler):
    """
    统一动态资源处理器：
    1. /local?path=...  -> 读取本地原图
    2. /thumb?id=...&path=... -> 动态生成并返回缩略图
    3. /remote?url=... -> 代理下载缓存网络图片
    """
    
    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            # --- 路由 1：获取本地原图 ---
            if parsed.path == '/local':
                local_path = urllib.parse.unquote(qs.get('path', [''])[0])
                if os.path.isfile(local_path):
                    self._serve_local_file(local_path)
                else:
                    self.send_error(404, "File not found")
                return
            # --- 路由 2：动态生成缩略图 (核心重构) ---
            elif parsed.path == '/thumb':
                pkg_id = qs.get('id', [''])[0]
                src_path = urllib.parse.unquote(qs.get('path', [''])[0])
                if not pkg_id or not os.path.isfile(src_path):
                    self.send_error(404, "Source not found")
                    return
                target_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{pkg_id}.webp")
                # 检查缓存是否有效
                need_generate = True
                if os.path.exists(target_path):
                    if os.path.getmtime(src_path) <= os.path.getmtime(target_path):
                        need_generate = False
                # 即时生成
                if need_generate:
                    try:
                        with Image.open(src_path) as img:
                            if img.mode not in ('RGB', 'RGBA'):
                                img = img.convert('RGBA')
                            img.thumbnail((64, 64), Image.Resampling.LANCZOS)
                            img.save(target_path, 'WEBP', quality=80)
                    except Exception as e:
                        logger.warning(f"Thumbnail gen failed for {pkg_id}, serving original. Error: {e}")
                        self._serve_local_file(src_path) # 生成失败，直接降级返回原图
                        return
                self._serve_local_file(target_path)
                return
            # --- 路由 3：代理缓存网络图片 (完美降级) ---
            elif parsed.path == '/remote':
                remote_url = urllib.parse.unquote(qs.get('url', [''])[0])
                if not remote_url:
                    self.send_error(400, "Missing URL")
                    return
                # MD5 生成缓存文件名
                url_hash = hashlib.md5(remote_url.encode('utf-8')).hexdigest()
                ext = ".png" if ".png" in remote_url.lower() else ".jpg"
                cache_path = os.path.join(GALLERY_CACHE_DIR, f"{url_hash}{ext}")
                # 如果没有缓存，则尝试下载
                if not os.path.exists(cache_path):
                    try:
                        # 加上超时限制，避免阻塞线程
                        resp = requests.get(remote_url, timeout=5)
                        if resp.status_code == 200:
                            # 写入缓存
                            with open(cache_path, 'wb') as f:
                                f.write(resp.content)
                        else:
                            self._fallback_to_browser(remote_url)
                            return
                    except Exception as e:
                        logger.debug(f"Proxy download failed, fallback to original URL: {e}")
                        self._fallback_to_browser(remote_url)
                        return
                self._serve_local_file(cache_path)
                return
            else:
                self.send_error(404, "Invalid route")
                
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass # 忽略前端快速滚动取消请求的错误
        except Exception as e:
            logger.error(f"Asset Handler Error: {e}")
            try: self.send_error(500)
            except: pass

    def _fallback_to_browser(self, original_url):
        """【神级降级】：告诉浏览器我下载失败了，你自己去直接请求原网址吧"""
        self.send_response(302) # Found / Redirect
        self.send_header('Location', original_url)
        self.end_headers()

    def _serve_local_file(self, file_path):
        """发送本地文件流并设置强缓存"""
        ext = os.path.splitext(file_path)[1].lower()
        ctype = 'application/octet-stream'
        if ext == '.png': ctype = 'image/png'
        elif ext in ['.jpg', '.jpeg']: ctype = 'image/jpeg'
        elif ext == '.webp': ctype = 'image/webp'
        elif ext == '.gif': ctype = 'image/gif'
        
        self.send_response(200)
        self.send_header('Content-type', ctype)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'max-age=2592000') # 让浏览器缓存 30 天
        self.end_headers()
        
        with open(file_path, 'rb') as f:
            self.wfile.write(f.read())

    def log_message(self, format, *args):
        pass # 屏蔽控制台刷屏



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
        if not os.path.exists(THUMBNAIL_CACHE_DIR):
            os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
        if not os.path.exists(GALLERY_CACHE_DIR):
            os.makedirs(GALLERY_CACHE_DIR, exist_ok=True)
            
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
            # server = HTTPServer(('127.0.0.1', 0), LocalAssetHandler)
            server = ThreadingHTTPServer(('127.0.0.1', 0), LocalAssetHandler)   # 使用多线程服务器，避免阻塞主线程
            self._port = server.server_address[1]
            
            self._server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            self._server_thread.start()
            logger.info(f"File Manager: Asset Server started on port {self._port}")
        except Exception as e:
            logger.error(f"File Manager: Failed to start asset server: {e}")

    def get_port(self):
        """返回当前 HTTP 服务器端口"""
        return self._port
    
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
    def get_gallery_url(self, workshop_id, remote_url):
        """生成指向本地服务器的代理 URL"""
        if not remote_url: return ""
        from urllib.parse import quote
        safe_url = quote(remote_url)
        return f"http://127.0.0.1:{self._port}/gallery?wid={workshop_id}&url={safe_url}"
    
    @staticmethod
    def get_thumbnail_path(package_id):
        """
        获取某个 Mod 已生成的缩略图路径 (物理路径)。
        如果不存在返回 None。
        """
        target_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{package_id}.webp")
        if os.path.exists(target_path):
            return target_path
        return None

    def ensure_thumbnail(self, package_id, original_path, max_size=64):
        """
        检查并生成缩略图。
        如果缩略图已存在且未过期，直接返回路径；否则重新生成。
        :return: 缩略图的绝对路径 (str) 或 None
        """
        if not original_path or not os.path.exists(original_path): return None
        target_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{package_id}.webp")
        # 检查是否需要重新生成 (存在性 + 修改时间)
        need_generate = True
        if os.path.exists(target_path):
            try:
                # 如果原图修改时间比缩略图早，说明缩略图是最新的
                if os.path.getmtime(original_path) <= os.path.getmtime(target_path):
                    need_generate = False
            except OSError:
                pass
        if not need_generate: return target_path
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
            raise FileNotFoundError(f"路径不存在：{path}")

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
            return False
        except Exception as e:
            raise Exception(f"删除路径时出错: {e}")
    
    @staticmethod
    def delete_paths(paths: list):
        """
        批量删除文件/文件夹到回收站
        :param paths: 路径列表
        :return: (success_count, error_list)
        """
        success_count = 0
        error_list = []
        if not paths: return 0, []
        for path in paths:
            if not path: continue
            try:
                # 1. 转换为绝对路径
                abs_path = os.path.abspath(path)
                # 2. 检查是否存在
                if os.path.exists(abs_path):
                    # 3. 移至回收站 (比直接删除更安全)
                    send2trash(abs_path)
                    success_count += 1
                else:
                    # 如果路径本来就不存在，可以视为删除成功的一种
                    # 或者记录为跳过，这里直接累加成功，减少用户困惑
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"批量删除出错: {path} -> {e}")
                error_list.append(f"删除失败 ({os.path.basename(path)}): {str(e)}")

        return success_count, error_list
    
    @staticmethod
    def select_folder_dialog(initial_dir=''):
        """
        打开系统原生的文件夹选择框
        """
        # 如果是文件路径则取目录，不是则设为空字符串
        path = os.path.dirname(initial_dir) if os.path.isfile(initial_dir) else initial_dir
        # 检查路径是否有效
        if not os.path.exists(path): path = ''
        
        # 获取当前活动窗口
        if len(webview.windows) > 0:
            window = webview.windows[0]
            # 调用原生对话框
            # allow_multiple=False: 单选
            result = window.create_file_dialog(
                webview.FileDialog.FOLDER, 
                directory=path, 
                allow_multiple=False
            )
            # result 返回的是一个列表 (因为可能多选)，或者 None (取消)
            if result and len(result) > 0:
                return result[0]
        return None

    @staticmethod
    def select_file_dialog(
        initial_dir='',
        file_types=(
            'Load Order Files (*.xml;*.rws;*.rml;*.json;*.txt;*.list)',
            'XML Files (*.xml;*.rws;*.rml)',
            'JSON Files (*.json)',
            'Text Files (*.txt;*.list)',
            'All Files (*.*)',
        ),
    ):
        """
        打开系统原生的文件选择框
        file_types 示例:
        (
            'Load Order Files (*.xml;*.rws;*.rml;*.json;*.txt;*.list)',
            'All Files (*.*)'
        )
        """
        # 如果是文件路径则取目录，不是则设为空字符串
        path = os.path.dirname(initial_dir) if os.path.isfile(initial_dir) else initial_dir
        # 检查路径是否有效
        if not os.path.exists(path): path = ''
        
        if len(webview.windows) > 0:
            window = webview.windows[0]
            result = window.create_file_dialog(
                webview.FileDialog.OPEN, 
                directory=path, 
                allow_multiple=False,
                file_types=file_types
            )
            if result and len(result) > 0:
                return result[0]
        return None
    
    @staticmethod
    def save_file_dialog(
        initial_dir='',
        default_filename='ModsConfig.xml',
        file_types=('XML Files (*.xml)', 'RML Files (*.rml)', 'All Files (*.*)'),
    ):
        """
        打开系统原生的文件保存框
        """
        # 如果是文件路径则取目录，不是则设为空字符串
        path = os.path.dirname(initial_dir) if os.path.isfile(initial_dir) else initial_dir
        # 检查路径是否有效
        if not os.path.exists(path): path = ''
        
        if len(webview.windows) > 0:
            window = webview.windows[0]
            # pywebview 的 create_file_dialog 参数：
            # dialog_type, directory, allow_multiple, save_filename, file_types
            result = window.create_file_dialog(
                webview.FileDialog.SAVE, 
                directory=path, 
                save_filename=default_filename, # 设置默认文件名
                allow_multiple=False,
                file_types=file_types
            )
            logger.info(f"用户选择保存路径: {result}")
            if result and len(result) > 0:
                return result[0]
                
        return None
    
    @staticmethod
    def localize_workshop_mods(query, local_root: str, folder_name_type: str = 'workshop_id'):
        """
        将工坊模组转为本地模组，并推送实时进度
        :param query: 包含工坊模组信息的查询结果
        :param local_root: 本地模组存储根目录
        :param folder_name_type: 文件夹命名类型，可选 'alias_name', 'name', 'package_id', 'workshop_id'
        """
        tasks = []
        EventBus.resume()   # 恢复事件总线
        for mod_data in query:
            # 核心退回逻辑：alias_name > name > package_id > workshop_id
            display_name = mod_data.get('workshop_id')
            if(folder_name_type=='alias_name'): display_name = ( mod_data.get('alias_name') or mod_data.get('name') or mod_data.get('package_id') or mod_data.get('workshop_id') )
            elif(folder_name_type=='name'): display_name = ( mod_data.get('name') or mod_data.get('package_id') or mod_data.get('workshop_id') )
            elif( folder_name_type=='package_id' ): display_name = ( mod_data.get('package_id') or mod_data.get('workshop_id') )
            else: display_name = mod_data.get('workshop_id')
            
            # 净化文件名
            safe_name = FileManager.sanitize_filename(display_name)
            folder_name = f"_{safe_name}_"
            tasks.append({
                'src': mod_data['path'],
                'dst': os.path.join(local_root, folder_name),
                'label': display_name # 用于进度显示
            })
        if not tasks: return False
            
        # 2. 定义进度回调函数，通过 EventBus 发送到前端
        def on_progress(current, total, label):
            percent = int((current / total) * 100)
            EventBus.emit('localize-progress', {
                'current': current,
                'total': total,
                'percent': percent,
                'message': f"正在本地化 ({current}/{total}): {label}"
            })
        # 3. 在后台线程执行，避免阻塞 UI（如果是大批量复制）
        def run_task():
            success, errors, total = FileManager.copy_folders_with_progress(tasks, on_progress)
            # 执行完成后触发扫描以更新数据库和软链接
            # 强制发送 100% 进度
            EventBus.emit('scan-progress', {
                'stage': 'finished',
                'current': total,
                'total': total,
                'percent': 100,
                'message': '本地化完成'
            })
            
            # 给前端一点点时间处理 100% 的状态，再发送 complete
            time.sleep(0.2) 
            # 发送完成事件
            EventBus.emit('localize-complete', {
                'success_count': len(success),
                'error_count': len(errors),
                'errors': errors
            })
        threading.Thread(target=run_task, daemon=True).start()
        return True
    
    @staticmethod
    def copy_folders_with_progress(tasks, progress_callback=None):
        """
        带进度回调的批量复制
        :param tasks: [{'src': '...', 'dst': '...', 'label': '...'}]
        :param progress_callback: 函数，接收 (current, total, label)
        """
        total = len(tasks)
        success_list = []
        error_list = []

        for i, task in enumerate(tasks):
            src = task['src']
            dst = task['dst']
            label = task.get('label', os.path.basename(src))

            # 触发进度回调
            if progress_callback:
                progress_callback(i + 1, total, label)

            try:
                # 自动处理重名
                final_dst = dst
                counter = 1
                while os.path.exists(final_dst):
                    final_dst = f"{dst}_{counter}"
                    counter += 1
                
                shutil.copytree(src, final_dst)
                success_list.append(final_dst)
            except Exception as e:
                logger.error(f"Copy failed: {src} -> {dst}: {e}")
                error_list.append(f"模组 {label} 复制失败: {str(e)}")

        return success_list, error_list, total
    
    @staticmethod
    def sanitize_filename(name):
        """清理文件名，确保路径合法"""
        if not name:
            return "Unknown_Mod"
        # 1. 替换 Windows/Linux 非法字符为下划线
        name = re.sub(r'[\\/:*?"<>|]', '_', str(name))
        # 2. 移除不可见字符
        name = "".join(ch for ch in name if ch.isprintable())
        # 3. 限制长度防止路径过长报错 (Windows 建议总路径 < 260)
        return name.strip()[:64]
    
    
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
        # logger.debug(f"Sync links: local_mods_path={local_mods_path}, workshop_mod_paths={workshop_mod_paths}")
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
        # 遍历目录下的所有内容，只要命中前缀且不在 target_map 中，就是删除目标
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
    def sync_links_full(local_mods_path, workshop_mod_paths: list):
        """全量重建链接：删除所有旧链接后重新创建目标集合"""
        if not local_mods_path or not os.path.exists(local_mods_path):
            return False

        # 1. 准备目标清单 (统一转小写进行防呆匹配)
        target_map = {}
        for src in workshop_mod_paths:
            if not src: continue
            wid = os.path.basename(os.path.normpath(src))
            link_name = f"{FileManager.LINK_PREFIX}{wid}"
            target_map[link_name.lower()] = {
                'raw_name': link_name,
                'src_path': os.path.normpath(os.path.abspath(src))
            }

        to_delete_paths = []
        links_to_create = []

        # 2. 全量扫描现有链接
        try:
            with os.scandir(local_mods_path) as it:
                for entry in it:
                    if not entry.name.startswith(FileManager.LINK_PREFIX): continue
                    to_delete_paths.append(entry.path)
        except OSError as e:
            logger.error(f"Scan links failed: {e}")

        # 3. 计算需要重建的全部链接
        for _, info in target_map.items():
            dst_path = os.path.join(local_mods_path, info['raw_name'])
            links_to_create.append((info['src_path'], dst_path))

        # 4. 执行全量删除 (os.rmdir 对于 Junction 是瞬间且安全的，不会删除原文件)
        for path in to_delete_paths:
            try:
                # 尝试用 unlink (适用于软链接)，如果报错则用 rmdir (适用于 Junction/目录)
                if os.path.islink(path): os.unlink(path)
                else: os.rmdir(path)
            except Exception:
                pass # 忽略占用等特殊情况

        # 5. 执行极速创建
        if links_to_create:
            FileManager._create_links_fast(links_to_create)

        logger.info(f"Sync Full Result -> Created: {len(links_to_create)}, Deleted: {len(to_delete_paths)}")
        return True

    @staticmethod
    def _is_link_correct(link_path, expected_src):
        """判断链接是否有效且指向正确"""
        try:
            # lexists 用于检测路径是否存在（包括断头链接）
            if not os.path.lexists(link_path): return False
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
    
    @staticmethod
    def _create_links_fast(link_tasks: list):
        """调用底层 API 极速创建链接"""
        is_windows = platform.system() == 'Windows'
        if is_windows:
            try:
                import _winapi # 导入 Windows 底层 API
            except ImportError:
                is_windows = False

        for src, dst in link_tasks:
            try:
                if is_windows:
                    # 使用底层 CreateJunction，速度极快且不需要管理员权限
                    _winapi.CreateJunction(src, dst)
                else:
                    os.symlink(src, dst)
            except Exception as e:
                from backend.utils.logger import logger
                logger.error(f"Failed to link {dst} -> {src}: {e}")
    
    # =========================================================
    #  5. SteamCMD 根目录重定向 (Root Redirect)
    # =========================================================

    @staticmethod
    def sync_steamcmd_root_link(old_mods_path: str|None = None, move_old_data: bool = False):
        """
        同步 SteamCMD 下载根目录到自定义存储目录的软链接。
        
        :param old_mods_path: 变更前的 mods_path，用于数据迁移
        :param move_old_data: 如果 mods_path 变了，是否把旧路径的数据搬过来
        """
        from backend.settings import settings
        
        # 1. 获取最新配置
        # 实际物理存储路径 (Target)
        real_storage_path = os.path.normpath(os.path.abspath(settings.config.self_mods_path))
        # SteamCMD 期望的下载路径 (Link Location, 通常是 .../294100)
        steamcmd_link_path = os.path.normpath(os.path.abspath(settings.config.steamcmd_mods_path))
        
        os.makedirs(os.path.dirname(steamcmd_link_path), exist_ok=True)
        os.makedirs(real_storage_path, exist_ok=True)

        logger.info(f"Redirecting SteamCMD: {steamcmd_link_path} -> {real_storage_path}")

        # ---------------------------------------------------------
        # 步骤 A: 处理 mods_path 变更导致的数据迁移
        # ---------------------------------------------------------
        if move_old_data and old_mods_path:
            old_mods_path = os.path.normpath(os.path.abspath(old_mods_path))
            if old_mods_path != real_storage_path and os.path.exists(old_mods_path):
                logger.info(f"Moving data from OLD mods_path: {old_mods_path} -> {real_storage_path}")
                FileManager._merge_and_delete_folder(old_mods_path, real_storage_path)

        # 确保实际物理目录存在
        os.makedirs(real_storage_path, exist_ok=True)

        # ---------------------------------------------------------
        # 步骤 B: 处理 SteamCMD 链接位置 (Link Location)
        # ---------------------------------------------------------
        
        # 如果该位置已经存在
        if os.path.lexists(steamcmd_link_path):
            # 情况 1: 它已经是一个链接了
            if os.path.islink(steamcmd_link_path) or FileManager._is_junction_windows(steamcmd_link_path):
                # 检查它指向的是不是我们现在的物理路径
                if FileManager._is_link_correct(steamcmd_link_path, real_storage_path):
                    logger.info("SteamCMD link is already correct. Skipping.")
                    return True
                else:
                    # 指向了错误的路径，或者是旧的路径，删掉这个链接（不会删掉源文件）
                    logger.info("Removing stale or incorrect SteamCMD link.")
                    FileManager._remove_link_safe(steamcmd_link_path)
            
            # 情况 2: 它是一个真实的文件夹 (里面可能有 SteamCMD 之前下的 Mod)
            elif os.path.isdir(steamcmd_link_path):
                logger.info(f"Found real folder at SteamCMD path. Merging to {real_storage_path}...")
                # 把里面的 Mod 搬到物理路径
                FileManager._merge_and_delete_folder(steamcmd_link_path, real_storage_path)
                # 搬完后删掉这个空壳文件夹，为创建链接腾位置
                shutil.rmtree(steamcmd_link_path, ignore_errors=True)

        # ---------------------------------------------------------
        # 步骤 C: 创建新的链接
        # ---------------------------------------------------------
        # 再次确保父目录存在 (steamapps/workshop/content/)
        os.makedirs(os.path.dirname(steamcmd_link_path), exist_ok=True)
        
        try:
            if platform.system() == 'Windows':
                # 使用 Junction (mklink /j)，不需要管理员权限，且对磁盘 IO 最友好
                subprocess.run(f'mklink /j "{steamcmd_link_path}" "{real_storage_path}"', 
                               shell=True, check=True, capture_output=True)
            else:
                os.symlink(real_storage_path, steamcmd_link_path)
            
            logger.info("Successfully created SteamCMD redirection link.")
            return True
        except Exception as e:
            logger.error(f"Failed to create SteamCMD link: {e}")
            return False

    # =========================================================
    #  辅助私有方法
    # =========================================================

    @staticmethod
    def _is_junction_windows(path):
        """判断 Windows 下是否为联接点"""
        if platform.system() != 'Windows': return False
        try:
            # Junction 在 Windows 下通过特定属性识别
            output = subprocess.check_output(['dir', '/ad', os.path.dirname(path)], shell=True).decode('gbk', errors='ignore')
            return f"<JUNCTION>     {os.path.basename(path)}" in output
        except:
            return False

    @staticmethod
    def _remove_link_safe(path):
        """安全移除链接而不伤及目标"""
        try:
            if platform.system() == 'Windows':
                # 对于 Junction，使用 rmdir 是安全的，它只删链接不删内容
                subprocess.run(f'rd "{os.path.normpath(path)}"', shell=True, check=True)
            else:
                os.unlink(path)
        except Exception as e:
            logger.error(f"Failed to remove link {path}: {e}")

    @staticmethod
    def _merge_and_delete_folder(src, dst):
        """
        合并两个文件夹的内容并删除源文件夹。
        如果目标位置已存在同名 Mod，则覆盖。
        """
        if not os.path.exists(src): return
        os.makedirs(dst, exist_ok=True)
        
        try:
            for item in os.listdir(src):
                s_path = os.path.join(src, item)
                d_path = os.path.join(dst, item)
                
                if os.path.isdir(s_path):
                    if os.path.exists(d_path):
                        shutil.rmtree(d_path, ignore_errors=True)
                    shutil.move(s_path, d_path)
                else:
                    if os.path.exists(d_path):
                        os.remove(d_path)
                    shutil.move(s_path, d_path)
            
            # 清理残留空目录
            if os.path.exists(src):
                shutil.rmtree(src, ignore_errors=True)
        except Exception as e:
            logger.error(f"Merge folder failed: {e}")
    
    
    
class PathChecker:

    @classmethod
    def _format_res(cls, is_pass: bool, data: Any = None, msg: str = "", msg_type: str = "success"):
        """统一返回格式"""
        return {
            'pass': is_pass,
            'data': data,
            'type': msg_type if is_pass else ("error" if msg_type == "success" else msg_type),
            'msg': msg
        }
    
    @classmethod
    def check_normal_path(cls, path_str: str) -> Dict:
        """
        检查普通路径是否有效
        返回：{
            'pass': True,
            'data': {},
            'type': 'success',
            'msg': ''
        }
        """
        if not path_str: return cls._format_res(False, msg="路径不能为空")
        path = Path(path_str)
        # 文件路径只警告，检查其父路径是否存在
        if len(os.path.splitext(path_str.strip())[1]) > 0:
            if path.parent.exists():
                if path.is_file(): return cls._format_res(True, data=str(path), msg=f"路径有效：{path}")
                return cls._format_res(True, msg=f"父路径下不存在该文件，软件会按需生成该文件。", msg_type="warning")
            return cls._format_res(False, msg=f"{path_str}\n父路径不存在！")
        
        if not path.exists(): return cls._format_res(False, msg=f"{path_str}\n路径不存在！")
        return cls._format_res(True, data=str(path), msg=f"路径有效：{path}")
    
    @classmethod
    def check_install_path(cls, path_str: str) -> Dict:
        """
        检查游戏安装路径是否有效
        返回：{
            'pass': True,
            'data': {},
            'type': 'success',
            'msg': ''
        }
        """
        if not path_str: return cls._format_res(False, msg="安装路径不能为空")
        path = Path(path_str)
        if not path.exists(): return cls._format_res(False, msg="游戏安装路径不存在！")
        res = {}
        # 1. 检查执行文件
        exe = GameManager.detect_executable(str(path))
        if exe:
            res = cls._format_res(True, data={}, msg=f"游戏安装路径: {path}")
            res['data']["game_exe"] = str(exe)
        else:
            res = cls._format_res(False, msg="无法检测到游戏程序")
            return res
        # 2. 检查版本
        version = GameManager.get_game_version(str(path))
        res['data']["game_version"] = version if version else "未知"
        # 3. Steam 判定 (优化判定逻辑)
        is_steam = "steamapps" in path.parts and "common" in path.parts
        res['data']["is_steam"] = is_steam
        res['msg'] = f"游戏本体：{exe}\n游戏版本：{version}\n{'是' if is_steam else '非'}Steam版"
        
        return res
    
    @classmethod
    def check_user_data_path(cls, path_str:str) -> Dict:
        if not path_str: return cls._format_res(False, msg="用户数据路径不能为空")
        # 哪怕目录不存在，只要父目录存在且有写入权限，我们就认为合法（因为我们可以创建它）
        parent_dir = os.path.dirname(path_str)
        if parent_dir and not os.path.exists(parent_dir):
            return cls._format_res(False, msg=f"父目录不存在: {parent_dir}")
        if parent_dir and not os.access(parent_dir, os.W_OK):
            return cls._format_res(False, msg="目录无写入权限，请以管理员身份运行或更换路径")
        # 检查是否有Config目录和Saves目录，不存在则警告
        config_dir = os.path.join(path_str, "Config")
        saves_dir = os.path.join(path_str, "Saves")
        if not os.path.exists(config_dir):
            return cls._format_res(True, msg=f"用户数据路径 {path_str} 下无 Config 目录（自定义环境可忽视此警告，程序会自动生成）", msg_type="warn")
        if not os.path.exists(saves_dir):
            return cls._format_res(True, msg=f"用户数据路径 {path_str} 下无 Saves 目录（自定义环境可忽视此警告，程序会自动生成）", msg_type="warn")
        
        return cls._format_res(True, msg="校验通过")
    
    @classmethod
    def check_mods_config(cls, path_str: str) -> Dict:
        """
        检查 Mods 配置文件是否存在
        返回：{
            'pass': True,
            'data': {},
            'type': 'success',
            'msg': ''
        }
        """
        path = Path(path_str) / "ModsConfig.xml"
        if path.exists():
            return cls._format_res(True, data=str(path), msg=f"Mods 配置文件：{path}")
        return cls._format_res(False, msg="未找到 ModsConfig.xml", msg_type="warn")

    @classmethod
    def check_workshop_path(cls, path_str: str) -> Dict:
        """
        检查 Workshop 路径是否有效
        返回：{
            'pass': True,
            'data': {},
            'type': 'success',
            'msg': ''
        }
        """
        if not path_str or not Path(path_str).exists():
            return cls._format_res(False, msg="Workshop 路径不存在")
        
        is_valid = "steamapps" in Path(path_str).parts and "workshop" in Path(path_str).parts
        return cls._format_res(is_valid, data=path_str, 
                               msg=f"Workshop 路径：{path_str}" if is_valid else "路径不在 Steam 库中",
                               msg_type="success" if is_valid else "warn")
        
    @classmethod
    def check_steam_path(cls, path_str: str) -> Dict:
        """
        检查 Steam 客户端路径是否有效
        返回：{
            'pass': True,
            'data': {},
            'type': 'success',
            'msg': ''
        }
        """
        if not path_str: return cls._format_res(False, msg="未指定 Steam 路径")
        exe_path = Path(path_str) / "steam.exe"
        if exe_path.exists():
            return cls._format_res(True, data=path_str, msg=f"Steam 客户端：{exe_path}")
        return cls._format_res(False, msg="路径下未找到 steam.exe", msg_type="warn")
    
    @classmethod
    def check_steamcmd_path(cls, path_str: str) -> Dict:
        """
        检查 SteamCMD 路径是否有效
        返回：{
            'pass': True,
            'data': {},
            'type': 'success',
            'msg': ''
        }
        """
        if not path_str: return cls._format_res(False, msg="未指定 SteamCMD 路径")
        # 中文路经检查，steamcmd路径不能包含任何中文
        pattern = re.compile(r'[\u4e00-\u9fff]')
        result = pattern.search(path_str)
        if result: return cls._format_res(False, msg="SteamCMD 路径不能包含中文")
        
        exe_path = Path(path_str) / "steamcmd.exe"
        if exe_path.exists():
            return cls._format_res(True, data=path_str, msg=f"SteamCMD 客户端：{exe_path}")
        return cls._format_res(False, msg="路径下未找到 steamcmd.exe", msg_type="warn")
        
    @classmethod
    def paths_check(cls, paths_data: Dict[str, str]) -> Dict:
        """
        主入口：支持全量检测
        """
        if not paths_data: return {}
        results = {}
        try:
            # 1. 安装路径相关 (包含 exe, version, steam 判定)
            if "game_install_path" in paths_data:
                results["game_install_path"] = cls.check_install_path(paths_data["game_install_path"])
            # 2. 配置文件 
            if "game_config_path" in paths_data:
                results["game_config_path"] = cls.check_mods_config(paths_data["game_config_path"])
            # 3. Workshop
            if "workshop_mods_path" in paths_data:
                results["workshop_mods_path"] = cls.check_workshop_path(paths_data["workshop_mods_path"])
            # 4. Steam 主程序
            if "steam_path" in paths_data:
                results["steam_path"] = cls.check_steam_path(paths_data["steam_path"])
            if "steamcmd_path" in paths_data:
                results["steamcmd_path"] = cls.check_steamcmd_path(paths_data["steamcmd_path"])
            if "user_data_path" in paths_data:
                results["user_data_path"] = cls.check_user_data_path(paths_data["user_data_path"])
            # 5. 其他路径
            for key, path in paths_data.items():
                if key in ["game_install_path", "game_config_path", "workshop_mods_path", "steam_path", "steamcmd_path", "user_data_path"]: continue
                results[key] = cls.check_normal_path(path)

            return results
        except Exception as e:
            logger.error(f"Check Paths Error: {e}", exc_info=True)
            return {}
        
    
file_mgr = FileManager()



