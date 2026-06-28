
import os
import re
import ipaddress
import uuid
import shutil
import hashlib
import mimetypes
import tempfile
import threading
import subprocess
import platform
import time
from PIL import Image
from pathlib import Path
from typing import Any, Dict
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import webview # 引入 webview 库
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_network import build_retry_session, merge_headers, network_mgr
from backend.settings import GALLERY_CACHE_DIR, THUMBNAIL_CACHE_DIR, settings
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger
from backend.utils.text_decode import decode_text_bytes
from backend.utils.tools import delete_fs_path
from backend.utils.shortcuts import (
    create_shortcut,
    format_shortcut_arguments,
    get_desktop_directory,
    get_platform_shortcut_kind,
    get_shortcut_suffix,
    remove_shortcut_variants,
)


class LocalAssetHandler(SimpleHTTPRequestHandler):
    """
    统一动态资源处理器：
    1. /local?path=...  -> 读取本地原图
    2. /thumb?id=...&path=... -> 动态生成并返回缩略图
    3. /remote?url=... -> 代理下载缓存网络图片
    """
    REMOTE_ALLOWED_SCHEMES = {"http", "https"}
    REMOTE_IMAGE_CONTENT_TYPES = {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/x-ms-bmp",
    }
    REMOTE_MAX_FILE_SIZE = 15 * 1024 * 1024
    REMOTE_FAILURE_COOLDOWN_SECONDS = 300
    _remote_failure_cache: dict[str, float] = {}
    _remote_failure_lock = threading.Lock()
    
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
                remote_url = self._normalize_remote_url(urllib.parse.unquote(qs.get('url', [''])[0]))
                if not remote_url:
                    self.send_error(400, "Missing URL")
                    return
                cache_path = self._resolve_remote_cache_path(remote_url)
                if cache_path and os.path.exists(cache_path):
                    self._serve_local_file(cache_path)
                    return

                downloaded_cache_path = self._download_remote_to_cache(remote_url, cache_path)
                if downloaded_cache_path and os.path.exists(downloaded_cache_path):
                    self._serve_local_file(downloaded_cache_path)
                    return

                self._fallback_to_browser(remote_url)
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

    def _normalize_remote_host(self, remote_url: str) -> str:
        parsed = urllib.parse.urlparse(remote_url)
        return str(parsed.hostname or "").strip().lower()

    def _normalize_remote_url(self, remote_url: str) -> str:
        """
        统一整理远程图片地址，确保白名单判断与缓存键都基于稳定格式。
        """
        normalized_url = str(remote_url or "").strip()
        if not normalized_url: return ""
        # 富文本中常见协议后带空格的脏链接，如 `https: //host/path`。
        normalized_url = re.sub(r'^(https?):\s*//', r'\1://', normalized_url, flags=re.IGNORECASE)
        # 去掉零宽字符，避免同一链接因隐藏字符产生不同缓存键。
        normalized_url = re.sub(r'[\u200b\u200c\u200d\ufeff]+', '', normalized_url)
        return normalized_url

    def _is_allowed_remote_url(self, remote_url: str) -> bool:
        """过滤明显危险或无效的目标，其他公网图片地址统一允许走缓存。"""
        try:
            parsed = urllib.parse.urlparse(remote_url)
        except Exception:
            return False

        if str(parsed.scheme or "").strip().lower() not in self.REMOTE_ALLOWED_SCHEMES:
            return False

        host = self._normalize_remote_host(remote_url)
        if not host:
            return False

        # 只阻止字面量本机/私网地址，域名统一交给后续请求层处理，避免维护白名单。
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return host not in {"localhost"}

        return not any([
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        ])

    def _is_remote_failure_cooled_down(self, remote_url: str) -> bool:
        """短时间内重复失败的地址直接跳过下载，避免坏链持续打远端。"""
        current_time = time.time()
        with self._remote_failure_lock:
            last_failed_at = self._remote_failure_cache.get(remote_url)
            if last_failed_at is None: return False
            if current_time - last_failed_at < self.REMOTE_FAILURE_COOLDOWN_SECONDS: return True
            self._remote_failure_cache.pop(remote_url, None)
            return False

    def _mark_remote_failure(self, remote_url: str) -> None:
        with self._remote_failure_lock:
            self._remote_failure_cache[remote_url] = time.time()

    def _resolve_remote_cache_path(self, remote_url: str) -> str:
        """
        按 URL 哈希定位缓存文件。

        网络图片默认按“内容基本不会在同一链接下变化”处理，
        因此直接长期复用本地缓存，不再引入额外 TTL。
        """
        url_hash = hashlib.md5(remote_url.encode('utf-8')).hexdigest()
        existing_candidates = sorted(Path(GALLERY_CACHE_DIR).glob(f"{url_hash}.*"))
        if existing_candidates: return str(existing_candidates[0])

        guessed_ext = self._guess_remote_extension(remote_url, content_type="")
        return os.path.join(GALLERY_CACHE_DIR, f"{url_hash}{guessed_ext}")

    def _guess_remote_extension(self, remote_url: str, content_type: str = "") -> str:
        """优先根据响应类型判断扩展名，缺失时再回退到 URL 后缀。"""
        normalized_content_type = str(content_type or "").split(";")[0].strip().lower()
        if normalized_content_type:
            guessed_from_type = mimetypes.guess_extension(normalized_content_type, strict=False)
            if guessed_from_type: return ".jpg" if guessed_from_type == ".jpe" else guessed_from_type

        parsed = urllib.parse.urlparse(remote_url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
            return ".jpg" if suffix == ".jpeg" else suffix
        return ".img"

    def _download_remote_to_cache(self, remote_url: str, cache_path: str) -> str | None:
        """
        下载远程图片到缓存目录。

        下载失败时不抛出异常，交给调用方决定是否回退到原始链接。
        """
        if not self._is_allowed_remote_url(remote_url):
            logger.debug(f"Rejected remote image by safety policy: {remote_url}")
            return None
        if self._is_remote_failure_cooled_down(remote_url): return None

        try:
            with build_retry_session(total=2, connect=2, read=2, allowed_methods=("GET", "HEAD")) as session:
                request_kwargs = {
                    "headers": merge_headers({"Accept": "image/*"}),
                    "timeout": (5, 12),
                    "stream": True,
                }
                proxy_url = network_mgr.get_proxy_url()
                if proxy_url:
                    request_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}

                response = session.get(remote_url, **request_kwargs)
                if response.status_code != 200:
                    logger.debug(f"Remote image download failed with status {response.status_code}: {remote_url}")
                    self._mark_remote_failure(remote_url)
                    return None

                content_type = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if content_type and content_type not in self.REMOTE_IMAGE_CONTENT_TYPES:
                    logger.debug(f"Remote image content-type rejected: {content_type} ({remote_url})")
                    self._mark_remote_failure(remote_url)
                    return None

                declared_length = int(response.headers.get("Content-Length") or 0)
                if declared_length > self.REMOTE_MAX_FILE_SIZE:
                    logger.debug(f"Remote image too large by content-length: {declared_length} ({remote_url})")
                    self._mark_remote_failure(remote_url)
                    return None

                final_cache_path = cache_path
                expected_ext = self._guess_remote_extension(remote_url, content_type)
                current_ext = Path(cache_path).suffix.lower()
                if expected_ext and current_ext != expected_ext:
                    final_cache_path = str(Path(cache_path).with_suffix(expected_ext))

                temp_path = f"{final_cache_path}.{uuid.uuid4().hex}.tmp"
                total_bytes = 0
                with open(temp_path, 'wb') as handle:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        total_bytes += len(chunk)
                        if total_bytes > self.REMOTE_MAX_FILE_SIZE:
                            handle.close()
                            delete_fs_path(temp_path)
                            logger.debug(f"Remote image exceeded size limit while streaming: {remote_url}")
                            self._mark_remote_failure(remote_url)
                            return None
                        handle.write(chunk)

                if total_bytes <= 0:
                    delete_fs_path(temp_path)
                    self._mark_remote_failure(remote_url)
                    return None

                os.replace(temp_path, final_cache_path)
                return final_cache_path
        except Exception as e:
            logger.debug(f"Proxy download failed, fallback to original URL: {e}")
            self._mark_remote_failure(remote_url)
            return None

    def _serve_local_file(self, file_path):
        """发送本地文件流并设置强缓存"""
        ext = os.path.splitext(file_path)[1].lower()
        ctype = 'application/octet-stream'
        if ext == '.png': ctype = 'image/png'
        elif ext in ['.jpg', '.jpeg']: ctype = 'image/jpeg'
        elif ext == '.webp': ctype = 'image/webp'
        elif ext == '.gif': ctype = 'image/gif'
        elif ext == '.bmp': ctype = 'image/bmp'

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
    # 本地化复制属于后台线程任务，这里集中维护取消令牌，供 API 全局任务栏复用。
    _localize_lock = threading.Lock()
    _localize_cancel_events: Dict[str, threading.Event] = {}
    @staticmethod
    def _open_with_system(target_path: str, action_label: str):
        """
        统一走系统默认的打开行为。

        “打开文件”和“打开所在目录”语义不同，但底层平台分发逻辑完全一致，
        这里集中封装，避免后续平台兼容修补时两边漂移。
        """
        system_name = platform.system()
        try:
            if system_name == 'Windows':
                os.startfile(target_path)
            elif system_name == 'Darwin':
                subprocess.call(['open', target_path])
            else:
                subprocess.call(['xdg-open', target_path])
            return None
        except Exception as e:
            raise Exception(f"{action_label}时出错: {e}")
    
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

    def get_remote_cache_stats(self) -> dict[str, int]:
        """统计网络图片缓存数量与总占用。"""
        total_files = 0
        total_bytes = 0
        for entry in Path(GALLERY_CACHE_DIR).iterdir():
            if not entry.is_file():
                continue
            try:
                total_files += 1
                total_bytes += entry.stat().st_size
            except OSError:
                continue
        return {
            "file_count": total_files,
            "total_bytes": total_bytes,
        }

    def clear_remote_cache(self) -> dict[str, int]:
        """清空网络图片缓存，并返回清理前统计。"""
        cleared_stats = self.get_remote_cache_stats()
        for entry in Path(GALLERY_CACHE_DIR).iterdir():
            if entry.is_file():
                delete_fs_path(str(entry))
        with LocalAssetHandler._remote_failure_lock:
            LocalAssetHandler._remote_failure_cache.clear()
        return cleared_stats
    
    def get_asset_url(self, local_path):
        """
        将本地绝对路径转换为前端可访问的 HTTP URL
        例如: C:/Mod/Preview.png -> http://127.0.0.1:xxxxx/image?path=C%3A%2FMod%2FPreview.png
        """
        if not local_path or not self._port: return ""
        # 对路径进行 URL 编码
        safe_path = urllib.parse.quote(local_path)
        return f"http://127.0.0.1:{self._port}/image?path={safe_path}"

    # =========================================================
    #  2. 缩略图管理 (Thumbnail)
    # =========================================================
    def get_gallery_url(self, workshop_id, remote_url):
        """生成指向本地服务器的代理 URL"""
        if not remote_url: return ""
        safe_url = urllib.parse.quote(remote_url)
        return f"http://127.0.0.1:{self._port}/gallery?wid={workshop_id}&url={safe_url}"
    
    @staticmethod
    def get_thumbnail_path(package_id):
        """
        获取某个 Mod 已生成的缩略图路径 (物理路径)。
        如果不存在返回 None。
        """
        target_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{package_id}.webp")
        if os.path.exists(target_path): return target_path
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

        return FileManager._open_with_system(path, "打开路径")

    @staticmethod
    def open_file(path):
        """
        使用系统默认程序直接打开文件。

        这里单独保留一个入口，而不是复用 open_in_explorer，
        是为了让“打开文件”和“打开所在目录”在前后端语义上彻底分离。
        """
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"文件不存在：{path}")

        return FileManager._open_with_system(path, "打开文件")

    @staticmethod
    def read_text_file(path: str, max_bytes: int = 2 * 1024 * 1024) -> dict[str, Any]:
        """
        只读文本文件内容，供前端文件阅读器使用。

        限制最大读取体积，避免把超大文件一次性推给前端。
        """
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"文件不存在：{path}")

        file_path = Path(path).resolve()
        file_size = file_path.stat().st_size
        normalized_max_bytes = max(0, int(max_bytes or 0)) if max_bytes else None
        read_size = min(normalized_max_bytes, file_size) if normalized_max_bytes is not None else file_size
        if read_size <= 0:
            return {
                "path": str(file_path),
                "encoding": "utf-8",
                "truncated": False,
                "file_size": file_size,
                "content": "",
            }

        # 只多读 1 个字节用于判断是否截断，避免大文件被整块载入内存。
        probe_size = read_size + 1 if normalized_max_bytes is not None and read_size < file_size else read_size
        with file_path.open("rb") as handle:
            raw = handle.read(probe_size)

        truncated = len(raw) > read_size
        if truncated:
            raw = raw[:read_size]

        content, used_encoding = decode_text_bytes(raw)

        return {
            "path": str(file_path),
            "encoding": used_encoding,
            "truncated": truncated,
            "file_size": file_size,
            "content": content,
        }

    @staticmethod
    def delete_path(path, force: bool = False):
        """删除文件/文件夹。默认移入回收站，force=True 时彻底删除。"""
        try:
            return delete_fs_path(path, force=force)
        except Exception as e:
            raise Exception(f"删除路径时出错: {e}")
    
    @staticmethod
    def delete_paths(paths: list, force: bool = False):
        """
        批量删除文件/文件夹。
        :param paths: 路径列表
        :return: (success_count, error_list)
        """
        success_count = 0
        error_list = []
        if not paths: return 0, []
        for path in paths:
            if not path: continue
            try:
                deleted = delete_fs_path(path, force=force)
                # 路径不存在时维持历史行为，视为已处理
                if deleted or not os.path.exists(os.path.abspath(path)):
                    success_count += 1
            except Exception as e:
                logger.error(f"批量删除出错: {path} -> {e}")
                error_list.append(f"删除失败 ({os.path.basename(path)}): {str(e)}")

        return success_count, error_list
    
    @staticmethod
    def _parse_dialog_file_types(file_types):
        parsed_types = []
        for item in file_types or []:
            text = str(item or "").strip()
            if not text:
                continue
            match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", text)
            if match:
                label = match.group(1).strip() or "文件"
                patterns = " ".join(part.strip() for part in match.group(2).split(';') if part.strip())
                parsed_types.append((label, patterns or "*.*"))
            else:
                parsed_types.append((text, "*.*"))
        return parsed_types or [("所有文件", "*.*")]

    @staticmethod
    def _run_tk_dialog(dialog_callback):
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            root.update()
            try:
                return dialog_callback(filedialog)
            finally:
                root.destroy()
        except Exception as e:
            logger.warning(f"Fallback file dialog failed: {e}")
            return None

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
            try:
                # 调用原生对话框
                # allow_multiple=False: 单选
                result = window.create_file_dialog(
                    webview.FileDialog.FOLDER, 
                    directory=path, 
                    allow_multiple=False
                )
                # 在 pywebview 环境里，取消选择应直接返回，不要再额外弹 Tk 对话框。
                if result and len(result) > 0: return result[0]
                return None
            except Exception as e:
                logger.warning(f"Webview folder dialog failed: {e}")
                return None
        return FileManager._run_tk_dialog(
            lambda filedialog: filedialog.askdirectory(initialdir=path or os.getcwd()) or None
        )

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
            try:
                result = window.create_file_dialog(
                    webview.FileDialog.OPEN, 
                    directory=path, 
                    allow_multiple=False,
                    file_types=file_types
                )
                # 在 pywebview 环境里，取消选择应直接返回，不要再额外弹 Tk 对话框。
                if result and len(result) > 0: return result[0]
                return None
            except Exception as e:
                logger.warning(f"Webview open dialog failed: {e}")
                return None
        tk_file_types = FileManager._parse_dialog_file_types(file_types)
        return FileManager._run_tk_dialog(
            lambda filedialog: filedialog.askopenfilename(
                initialdir=path or os.getcwd(),
                filetypes=tk_file_types,
            ) or None
        )
    
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
            try:
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
                # 在 pywebview 环境里，取消选择应直接返回，不要再额外弹 Tk 对话框。
                if result and len(result) > 0: return result[0]
                return None
            except Exception as e:
                logger.warning(f"Webview save dialog failed: {e}")
                return None

        tk_file_types = FileManager._parse_dialog_file_types(file_types)
        return FileManager._run_tk_dialog(
            lambda filedialog: filedialog.asksaveasfilename(
                initialdir=path or os.getcwd(),
                initialfile=default_filename,
                filetypes=tk_file_types,
                defaultextension=os.path.splitext(default_filename)[1] or None,
            ) or None
        )

    # =========================================================
    #  3.1 快捷方式
    # =========================================================

    @staticmethod
    def _resolve_profile_shortcut_context(
        profile: Any,
        *,
        for_url: bool,
        destination_dir: str | None = None,
    ) -> tuple[str, str]:
        """统一解析环境快捷方式的目标目录和文件后缀。"""
        profile_name = FileManager.sanitize_filename(getattr(profile, 'name', None) or getattr(profile, 'id', 'Profile'))
        shortcut_kind = get_platform_shortcut_kind(for_url=for_url)
        shortcut_dir = destination_dir or get_desktop_directory()
        if not shortcut_dir:
            raise FileNotFoundError("无法解析桌面目录")
        shortcut_path = os.path.join(
            shortcut_dir,
            f"RimWorld [{profile_name}]{get_shortcut_suffix(shortcut_kind)}",
        )
        return shortcut_kind, shortcut_path

    @staticmethod
    def build_browser_mode_shortcut_spec(app_exe_path: str) -> Dict[str, str]:
        """生成管理器 Browser mode 快捷方式定义。"""
        if platform.system() != 'Windows':
            raise OSError("Browser mode 快捷方式仅支持 Windows")

        target_path = os.path.abspath(str(app_exe_path or '').strip())
        if not target_path or not os.path.isfile(target_path):
            raise FileNotFoundError(f"程序入口不存在: {target_path}")

        exe_stem = Path(target_path).stem
        shortcut_path = str(Path(target_path).with_name(f"{exe_stem} [Browser mode].lnk"))
        return {
            "shortcut_path": shortcut_path,
            "target_path": target_path,
            "arguments": "--browser",
            "working_directory": str(Path(target_path).parent),
            "icon_location": target_path,
            "description": f"{exe_stem} Browser mode",
            "shortcut_kind": "lnk",
        }

    @staticmethod
    def ensure_browser_mode_shortcut(app_exe_path: str) -> Dict[str, Any]:
        """仅在缺失时创建 Browser mode 快捷方式，避免启动阶段做重校验。"""
        spec = FileManager.build_browser_mode_shortcut_spec(app_exe_path)
        shortcut_path = str(spec.get("shortcut_path") or '').strip()
        if shortcut_path and os.path.exists(shortcut_path):
            return {
                "changed": False,
                "reason": "exists",
                "shortcut": spec,
            }

        return {
            "changed": True,
            "reason": "missing",
            "shortcut": create_shortcut(spec),
        }

    @staticmethod
    def build_profile_shortcut_spec(
        profile: Any,
        extra_args: list[str] | None = None,
        prefer_steam_launch: bool = True,
        steam_exe_path: str | None = None,
        destination_dir: str | None = None,
        steam_app_id: str = "294100",
    ) -> Dict[str, str]:
        """
        根据环境启动逻辑构造桌面快捷方式定义。
        这里复用后端现有的启动参数，而不是前端重复拼命令，避免两边逻辑漂移。
        """
        game_install_path = os.path.abspath(str(getattr(profile, 'game_install_path', '') or '').strip())
        if not game_install_path or not os.path.isdir(game_install_path):
            raise FileNotFoundError(f"游戏安装目录无效: {game_install_path}")

        game_exe = GameManager.detect_executable(game_install_path)
        if not game_exe:
            raise FileNotFoundError(f"在安装目录下找不到游戏可执行文件: {game_install_path}")

        shortcut_kind, shortcut_path = FileManager._resolve_profile_shortcut_context(
            profile,
            for_url=False,
            destination_dir=destination_dir,
        )
        launch_args = [str(arg or '').strip() for arg in (extra_args or []) if str(arg or '').strip()]
        use_steam_launch = bool(prefer_steam_launch)
        target_path = os.path.abspath(game_exe)
        working_directory = game_install_path
        icon_location = target_path
        description = f"RimWorld 环境快捷方式：{getattr(profile, 'name', getattr(profile, 'id', ''))}"
        arguments = format_shortcut_arguments(launch_args)

        if use_steam_launch:
            resolved_steam_exe = os.path.abspath(str(steam_exe_path or '').strip()) if str(steam_exe_path or '').strip() else ''
            if resolved_steam_exe and os.path.isfile(resolved_steam_exe):
                target_path = resolved_steam_exe
                working_directory = str(Path(resolved_steam_exe).parent)
                # Steam 启动参数必须保持与当前环境运行逻辑一致。
                arguments = format_shortcut_arguments(["-applaunch", str(steam_app_id), *launch_args])
                # 使用游戏图标更直观，点击目标仍然是 Steam.exe。
                icon_location = os.path.abspath(game_exe)

        return {
            "shortcut_path": shortcut_path,
            "target_path": target_path,
            "arguments": arguments,
            "working_directory": working_directory,
            "icon_location": icon_location,
            "description": description,
            "shortcut_kind": shortcut_kind,
        }

    @staticmethod
    def create_profile_desktop_shortcut(
        profile: Any,
        extra_args: list[str] | None = None,
        prefer_steam_launch: bool = True,
        steam_exe_path: str | None = None,
        steam_app_id: str = "294100",
    ) -> Dict[str, Any]:
        """为指定环境在桌面创建快捷方式。"""
        spec = FileManager.build_profile_shortcut_spec(
            profile=profile,
            extra_args=extra_args,
            prefer_steam_launch=prefer_steam_launch,
            steam_exe_path=steam_exe_path,
            steam_app_id=steam_app_id,
        )
        return create_shortcut(spec)

    @staticmethod
    def build_profile_url_shortcut_spec(
        profile: Any,
        launch_url: str,
        destination_dir: str | None = None,
        icon_location: str = '',
    ) -> Dict[str, str]:
        """
        生成 Steam 协议快捷方式定义。
        统一交给平台适配层决定具体是 `.url`、`.desktop` 还是 `.command`。
        """
        shortcut_kind, shortcut_path = FileManager._resolve_profile_shortcut_context(
            profile,
            for_url=True,
            destination_dir=destination_dir,
        )
        return {
            "shortcut_path": shortcut_path,
            "url": str(launch_url or '').strip(),
            "icon_location": str(icon_location or '').strip(),
            "shortcut_kind": shortcut_kind,
        }

    @staticmethod
    def create_profile_desktop_url_shortcut(
        profile: Any,
        launch_url: str,
        icon_location: str = '',
    ) -> Dict[str, Any]:
        """为指定环境创建基于启动 URL 的桌面快捷方式。"""
        spec = FileManager.build_profile_url_shortcut_spec(
            profile=profile,
            launch_url=launch_url,
            icon_location=icon_location,
        )
        return create_shortcut(spec)

    @staticmethod
    def remove_existing_shortcut_variants(shortcut_path: str):
        """删除同名不同后缀的旧快捷方式，避免用户继续点到旧入口。"""
        remove_shortcut_variants(shortcut_path)

    @staticmethod
    def sync_managed_links(local_mods_path: str, deploy_paths: list[str]):
        """
        将本地 Mods 目录中的管理器链接收敛到 deploy_paths。
        这里复用既有同步逻辑，避免手写删除规则误伤 Self/Tool 链接。
        """
        if settings.config.link_deployment_mode_full:
            return FileManager.sync_links_full(local_mods_path, deploy_paths)
        return FileManager.sync_links(local_mods_path, deploy_paths)
    
    @staticmethod
    def localize_workshop_mods(query, local_root: str, folder_name_type: str = 'workshop_id'):
        """
        将工坊模组转为本地模组，并推送实时进度
        :param query: 包含工坊模组信息的查询结果
        :param local_root: 本地模组存储根目录
        :param folder_name_type: 文件夹命名类型，可选 'alias_name', 'name', 'package_id', 'workshop_id'
        """
        tasks = []
        task_id = uuid.uuid4().hex
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
        cancel_event = threading.Event()
        with FileManager._localize_lock:
            FileManager._localize_cancel_events[task_id] = cancel_event
        EventBus.emit_progress(
            task_id,
            "localize",
            status="pending",
            progress=0,
            message="准备本地化任务...",
            metrics={"total": len(tasks), "current": 0, "title": "本地化模组"},
        )
            
        # 2. 定义进度回调函数，通过 EventBus 发送到前端
        def on_progress(current, total, label):
            percent = int((current / total) * 100)
            EventBus.emit_progress(
                task_id,
                "localize",
                status="running",
                progress=percent,
                message=f"正在本地化 ({current}/{total}): {label}",
                metrics={"current": current, "total": total, "label": label, "title": "本地化模组"},
            )
        # 3. 在后台线程执行，避免阻塞 UI（如果是大批量复制）
        def run_task():
            success = []
            errors = []
            total = len(tasks)
            final_status = "success"
            final_message = "本地化完成"
            try:
                success, errors, total = FileManager.copy_folders_with_progress(
                    tasks,
                    on_progress,
                    cancel_event=cancel_event,
                )
                success_count = len(success)
                error_count = len(errors)
                if cancel_event.is_set():
                    final_status = "cancelled"
                    final_message = "本地化已取消"
                elif success_count == 0 and error_count > 0:
                    final_status = "failed"
                    final_message = "本地化失败"
            except InterruptedError:
                final_status = "cancelled"
                final_message = "本地化已取消"
            except Exception as e:
                logger.error(f"Localize task failed: {e}", exc_info=True)
                errors.append(str(e))
                final_status = "failed"
                final_message = "本地化失败"
            finally:
                with FileManager._localize_lock:
                    FileManager._localize_cancel_events.pop(task_id, None)

            success_count = len(success)
            error_count = len(errors)
            EventBus.emit_progress(
                task_id,
                "localize",
                status=final_status,
                progress=100 if total else 0,
                message=final_message,
                metrics={
                    "current": total,
                    "total": total,
                    "success_count": success_count,
                    "error_count": error_count,
                    "errors": errors,
                    "title": "本地化模组",
                },
            )
            # 这里无论成功、失败还是取消都发完成事件，让前端决定是否刷新视图。
            EventBus.emit('localize-complete', {
                'task_id': task_id,
                'success_count': success_count,
                'error_count': error_count,
                'errors': errors,
                'status': final_status,
            })
        threading.Thread(target=run_task, daemon=True).start()
        return task_id

    @staticmethod
    def cancel_localize_task(task_id: str) -> bool:
        """请求取消本地化复制任务。"""
        normalized_task_id = str(task_id or '').strip()
        if not normalized_task_id: return False
        with FileManager._localize_lock:
            cancel_event = FileManager._localize_cancel_events.get(normalized_task_id)
        if not cancel_event: return False
        cancel_event.set()
        return True
    
    @staticmethod
    def copy_folders_with_progress(tasks, progress_callback=None, cancel_event: threading.Event | None = None):
        """
        带进度回调的批量复制
        :param tasks: [{'src': '...', 'dst': '...', 'label': '...'}]
        :param progress_callback: 函数，接收 (current, total, label)
        """
        total = len(tasks)
        success_list = []
        error_list = []

        for i, task in enumerate(tasks):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Localize task cancelled by user")
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

                def copy_with_cancel(source_file, dest_file, *, follow_symlinks=True):
                    # 复制过程只能做到“文件粒度”的中断，至少保证不会继续复制后续文件。
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Localize task cancelled by user")
                    return shutil.copy2(source_file, dest_file, follow_symlinks=follow_symlinks)

                shutil.copytree(src, final_dst, copy_function=copy_with_cancel)
                success_list.append(final_dst)
            except InterruptedError:
                try:
                    if os.path.exists(final_dst):
                        delete_fs_path(final_dst)
                except Exception as cleanup_error:
                    logger.debug(f"Cleanup cancelled localize folder failed: {final_dst} - {cleanup_error}")
                raise
            except Exception as e:
                logger.error(f"Copy failed: {src} -> {dst}: {e}")
                error_list.append(f"模组 {label} 复制失败: {str(e)}")

        return success_list, error_list, total
    
    @staticmethod
    def sanitize_filename(name):
        """清理文件名，确保路径合法"""
        if not name: return "Unknown_Mod"
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
        if not local_mods_path or not os.path.exists(local_mods_path): return False

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
        normalized_path = os.path.normpath(os.path.abspath(path_str))
        # 哪怕目录不存在，只要父目录存在且有写入权限，我们就认为合法（因为我们可以创建它）
        parent_dir = os.path.dirname(normalized_path)
        if parent_dir and not os.path.exists(parent_dir):
            return cls._format_res(False, msg=f"父目录不存在: {parent_dir}")
        if parent_dir and not os.access(parent_dir, os.W_OK):
            return cls._format_res(False, msg="目录无写入权限，请以管理员身份运行或更换路径")

        config_dir = os.path.join(normalized_path, "Config")
        mods_config_file = os.path.join(config_dir, "ModsConfig.xml")

        if not os.path.exists(normalized_path):
            return cls._format_res(
                True,
                msg=f"用户数据目录 {normalized_path} 当前不存在，但父目录可写；保存或激活环境时会自动创建目录结构。",
                msg_type="warn",
            )
        if not os.path.exists(config_dir):
            return cls._format_res(
                True,
                msg=f"用户数据路径 {normalized_path} 下无 Config 目录；程序会在保存或激活环境时自动生成。",
                msg_type="warn",
            )
        if not os.path.exists(mods_config_file):
            return cls._format_res(
                True,
                msg=f"用户数据路径 {normalized_path} 下未检测到 Config/ModsConfig.xml；路径仍可使用，游戏首次写入配置后会自动生成。",
                msg_type="warn",
            )

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
        if path.exists(): return cls._format_res(True, data=str(path), msg=f"Mods 配置文件：{path}")
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
        if exe_path.exists(): return cls._format_res(True, data=path_str, msg=f"Steam 客户端：{exe_path}")
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
        if exe_path.exists(): return cls._format_res(True, data=path_str, msg=f"SteamCMD 客户端：{exe_path}")
        return cls._format_res(False, msg="路径下未找到 steamcmd.exe", msg_type="warn")

    @classmethod
    def check_texture_tools_path(cls, path_str: str) -> Dict:
        """
        检查贴图工具目录是否有效。
        这里统一按“目录中是否存在 todds.exe”判断，和 SteamCMD 的目录检查风格保持一致。
        """
        if not path_str:
            return cls._format_res(False, msg="未指定贴图工具目录")
        path = Path(path_str)
        if not path.exists():
            return cls._format_res(False, msg="贴图工具目录不存在")
        if not path.is_dir():
            return cls._format_res(False, msg="贴图工具路径必须是目录")

        exe_path = path / "todds.exe"
        if exe_path.exists():
            return cls._format_res(True, data=path_str, msg=f"贴图工具：{exe_path}")
        return cls._format_res(False, msg="目录下未找到 todds.exe，可在外部工具检查中下载安装", msg_type="warn")

    @classmethod
    def check_ripgrep_path(cls, path_str: str) -> Dict:
        """
        检查 ripgrep 工具路径是否有效。

        兼容“直接指向 rg.exe”与“指向包含 rg.exe 的目录”两种输入，
        但前端仍建议用户选择目录，以便后续自动更新时保持一致。
        """
        if not path_str:
            return cls._format_res(False, msg="未指定 ripgrep 目录")
        path = Path(path_str)
        if not path.exists():
            return cls._format_res(False, msg="ripgrep 路径不存在")
        if not path.is_file() and not path.is_dir():
            return cls._format_res(False, msg="ripgrep 路径必须是目录")

        from backend.text_search.tooling import get_ripgrep_status, resolve_ripgrep_root

        status = get_ripgrep_status(path_str, strict=True)
        if status.available:
            return cls._format_res(
                True,
                data=str(resolve_ripgrep_root(path_str)),
                msg=f"ripgrep：{status.resolved_path}",
            )

        if path.is_file():
            return cls._format_res(False, msg="请选择 rg.exe 或其所在目录", msg_type="warn")
        return cls._format_res(False, msg="目录下未找到 rg.exe，可在外部工具检查中下载安装", msg_type="warn")
        
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
            if "ripgrep_path" in paths_data:
                results["ripgrep_path"] = cls.check_ripgrep_path(paths_data["ripgrep_path"])
            if "texture_tools_path" in paths_data:
                results["texture_tools_path"] = cls.check_texture_tools_path(paths_data["texture_tools_path"])
            if "user_data_path" in paths_data:
                results["user_data_path"] = cls.check_user_data_path(paths_data["user_data_path"])
            # 5. 其他路径
            for key, path in paths_data.items():
                if key in ["game_install_path", "game_config_path", "workshop_mods_path", "steam_path", "steamcmd_path", "ripgrep_path", "texture_tools_path", "user_data_path"]: continue
                results[key] = cls.check_normal_path(path)

            return results
        except Exception as e:
            logger.error(f"Check Paths Error: {e}", exc_info=True)
            return {}
        
    
file_mgr = FileManager()



