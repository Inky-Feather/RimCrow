# backend/managers/mgr_download.py
import os
import re
import time
import uuid
import hashlib
import shutil
import threading
import copy
import requests
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Callable, Any, Iterable
from urllib.parse import urlparse, unquote
from pathlib import Path
from email.message import Message

from backend.i18n.messages import tr
from backend.utils.error_contract import InvalidResponseError, classify_exception
from backend.utils.logger import logger
from backend.utils.event_bus import EventBus
from backend.managers.mgr_network import build_retry_session, merge_headers

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    VERIFYING = "verifying"  # 校验中状态
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

@dataclass
class DownloadTask:
    url: str
    dest_path: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    filename: str = ""
    total_size: int = 0
    downloaded_size: int = 0
    status: TaskStatus = TaskStatus.PENDING
    error_msg: str = ""
    user_message: str = ""
    error_type: str = ""
    error_code: str = ""
    error_id: str = ""
    message_key: str = ""
    message_params: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    speed: str = "0 B/s"
    # 校验相关
    expected_hash: Optional[str] = None
    hash_algorithm: str = "md5"
    # 回调函数 (接收 Task 对象)
    on_complete: Optional[Callable[['DownloadTask'], Any]] = None
    on_post_download: Optional[Callable[['DownloadTask'], Any]] = None
    on_error: Optional[Callable[['DownloadTask'], Any]] = None
    # 业务层内容校验；失败时当前候选源应继续回退。
    validate_download: Optional[Callable[[str], Any]] = None
    # 需要在长校验过程中观察任务取消时使用；保留单参数回调兼容现有调用方。
    validate_download_with_cancel: Optional[Callable[[str, Callable[[], None]], Any]] = None
    # 备用源由业务层生成；下载器只按顺序尝试，不识别来源类型。
    source_urls: list[str] = field(default_factory=list)
    on_source_result: Optional[Callable[[str, bool], Any]] = None
    # managed 走应用路由；direct 不注入应用代理或环境代理。
    network_mode: str = "managed"
    network_override: Optional[Dict[str, Any]] = None
    destination_key: str = ""
    use_response_filename: bool = False
    network_attempts: list[dict[str, Any]] = field(default_factory=list)
    task_type: str = "download"
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 内部控制
    _cancel_event: threading.Event = field(default_factory=threading.Event)
    _future: Optional[Future] = None  # 存储线程池的 Future 对象

class DownloadManager:
    _instance = None
    _lock = threading.Lock() # -线程锁
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DownloadManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True
        # 任务存储 {task_id: DownloadTask}
        self.tasks: Dict[str, DownloadTask] = {}
        # 线程池 (默认最大5并发)
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="Downloader")
        logger.info("下载管理器已初始化。")

    @staticmethod
    def _default_title(task_type: str, filename: str) -> str:
        mapping = {
            "download": "下载任务",
            "update": "软件更新",
            "steamcmd-init": "SteamCMD 初始化",
        }
        return mapping.get(str(task_type or "").strip().lower(), filename or "任务")

    def add_task(self, url: str, dest_dir: str, filename: Optional[str] = None, expected_hash: Optional[str] = None, hash_algorithm: str = "md5",
                 on_complete: Optional[Callable[[DownloadTask], Any]] = None,
                 on_error: Optional[Callable[[DownloadTask], Any]] = None,
                 task_type: str = "download", title: str = "", metadata: Optional[Dict[str, Any]] = None,
                 *, fallback_urls: Iterable[str] | None = None,
                 on_post_download: Optional[Callable[[DownloadTask], Any]] = None,
                 on_source_result: Optional[Callable[[str, bool], Any]] = None,
                 validate_download: Optional[Callable[[str], Any]] = None,
                 validate_download_with_cancel: Optional[Callable[[str, Callable[[], None]], Any]] = None,
                 network_mode: str = "managed", network_override: Dict[str, Any] | None = None,
                 destination_key: str = "") -> str:
        """
        添加下载任务
        :param url: 下载地址
        :param dest_dir: 目标文件夹 (注意：现在要求传入目录，文件名自动探测或指定)
        :param filename: 强制指定文件名 (可选)
        :param expected_hash: 期望的 Hash 值 (可选，若提供则会自动校验)
        :param hash_algorithm: Hash 算法 (md5, sha1, sha256)
        :param on_complete: 下载完成后的回调函数 (在子线程执行，请勿操作 GUI)
        :param on_post_download: 完成前执行；外部数据延迟替换时由回调负责提交暂存文件
        :param on_error: 失败后的回调函数
        :param validate_download: 业务层内容校验；返回 False 或抛异常时继续尝试备用源
        """
        real_url = str(url or "").strip()
        EventBus.resume()   # 恢复事件总线，确保下载任务能够正常执行
        
        # 确保目标目录存在
        os.makedirs(dest_dir, exist_ok=True)

        # 文件名只从业务输入和 URL 推断；添加任务不能因为 HEAD 请求阻塞调用方。
        use_response_filename = not filename
        if not filename:
            filename = self._resolve_filename(real_url)
        if Path(filename).name != filename or Path(filename).anchor or filename in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename):
            raise ValueError("下载文件名包含非法路径或字符")
        
        final_path = os.path.join(dest_dir, filename)

        # 创建任务对象
        resolved_title = title or self._default_title(task_type, filename)
        source_urls = [real_url]
        for candidate in fallback_urls or ():
            candidate_url = str(candidate or "").strip()
            if candidate_url and candidate_url not in source_urls:
                source_urls.append(candidate_url)
        task = DownloadTask( url=real_url, dest_path=final_path, filename=filename,
            expected_hash=expected_hash, hash_algorithm=hash_algorithm,
            on_complete=on_complete, on_post_download=on_post_download, on_error=on_error,
            validate_download=validate_download, validate_download_with_cancel=validate_download_with_cancel,
            source_urls=source_urls, on_source_result=on_source_result,
            network_mode="direct" if str(network_mode).strip().lower() == "direct" else "managed",
            network_override=copy.deepcopy(network_override), destination_key=destination_key,
            use_response_filename=use_response_filename,
            task_type=task_type, title=resolved_title, metadata=dict(metadata or {})
        )
        with self._lock:
            if destination_key:
                for active in self.tasks.values():
                    is_terminal = active.status in {TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELLED}
                    is_released = is_terminal and (active._future is None or active._future.done())
                    same_dataset = bool(task.metadata.get("external_data_type")) and task.metadata.get("external_data_type") == active.metadata.get("external_data_type")
                    if (active.destination_key == destination_key or same_dataset) and not is_released:
                        return active.task_id
            self.tasks[task.task_id] = task
        
        logger.info(f"已加入下载任务: filename={filename}, task_id={task.task_id}, hash_check={bool(expected_hash)}")
        self._emit_progress(task)
        
        # 提交到线程池并保存 future
        task._future = self.executor.submit(self._download_worker, task)
        return task.task_id

    def _resolve_filename(self, url: str, content_disposition: str = "") -> str:
        """
        全能型文件名解析器
        """
        path_filename = ""
        try:
            if content_disposition:
                header = Message()
                header["Content-Disposition"] = content_disposition
                if server_filename := header.get_filename():
                    cleaned = self._clean_filename(server_filename)
                    if cleaned:
                        return cleaned
            # --- 策略 A: 从 URL 路径中提取并解码 ---
            parsed = urlparse(url)
            # unquote 处理 URL 编码的中文，如 %E6%B5%8B%E8%AF%95 -> 测试
            path_filename = unquote(os.path.basename(parsed.path))
            
            # --- 策略 B: 从查询参数中寻找常见关键字 (针对网盘/CDN) ---
            # 匹配 ?file=xxx, ?name=xxx, ?fileName=xxx 等
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            for param in ['filename', 'file_name', 'file', 'name']:
                for k in qs.keys():
                    if k.lower() == param: return self._clean_filename(unquote(qs[k][0]))

        except Exception as e:
            logger.debug("下载文件名解析失败，将使用兜底文件名。url=%s error=%s", self._safe_url_marker(url), e.__class__.__name__)

        # --- 策略 D: 兜底逻辑 ---
        if path_filename: return self._clean_filename(path_filename)
        
        return "downloaded_file_" + os.urandom(4).hex()

    def _clean_filename(self, filename: str) -> str:
        """清理文件名中的非法字符，防止系统报错"""
        # 移除 Windows 下非法的路径字符 \ / : * ? " < > |
        return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', filename).strip().rstrip(". ")

    @staticmethod
    def _safe_url_marker(url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc.rsplit('@', 1)[-1]}{parsed.path or ''}"

    @classmethod
    def _task_log_context(cls, task: DownloadTask) -> dict[str, Any]:
        context = {
            "task_id": task.task_id,
            "url": cls._safe_url_marker(task.url),
            "filename": task.filename,
            "dest_name": os.path.basename(task.dest_path or ""),
            "phase": str((task.metadata or {}).get("phase") or ""),
            "network_attempts": list(task.network_attempts),
        }
        metadata = dict(task.metadata or {})
        for key in ("external_data_type", "version", "source_name", "source_key", "attempted_source_keys", "has_fallback_source", "ready_to_install"):
            if key in metadata:
                context[key] = metadata[key]
        return context

    @staticmethod
    def _parse_size_header(value: Any) -> int:
        text = str(value or '').strip()
        if not text.isdigit():
            return 0
        try:
            return int(text)
        except ValueError:
            return 0

    @classmethod
    def _extract_total_size_from_headers(cls, headers, *, trust_content_length: bool = True) -> int:
        content_range = str(headers.get('content-range') or '').strip()
        if content_range:
            match = re.search(r'/(\d+)$', content_range)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass

        # 某些对象存储/CDN 会同时返回“传输层长度”和“原始对象长度”。
        # 当前端展示文件大小时，我们优先要“原始对象长度”。
        preferred_headers = (
            'x-goog-stored-content-length',
            'x-linked-size',
            'x-original-content-length',
            'x-ms-blob-content-length',
            'x-amz-meta-content-length',
        )
        for header_name in preferred_headers:
            size = cls._parse_size_header(headers.get(header_name))
            if size > 0: return size

        if trust_content_length:
            size = cls._parse_size_header(headers.get('content-length'))
            if size > 0: return size
        return 0

    @staticmethod
    def _uses_encoded_transfer(headers) -> bool:
        content_encoding = str(headers.get('content-encoding') or '').strip().lower()
        return bool(content_encoding and content_encoding != 'identity')

    @staticmethod
    def _set_task_phase(task: DownloadTask, phase: str | None):
        task.metadata = dict(task.metadata or {})
        if phase:
            task.metadata['phase'] = phase
        else:
            task.metadata.pop('phase', None)

    def cancel_task(self, task_id: str):
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.VERIFYING]:
                task._cancel_event.set()
                future = task._future
                if task.status == TaskStatus.PENDING and future and future.cancel():
                    self._set_task_phase(task, None)
                    task.status = TaskStatus.CANCELLED
                    task.speed = "已取消"
                    self._cleanup_task_directory(task)
                    self._emit_progress(task)
                    logger.info(f"下载任务在开始前已取消: task_id={task_id}")
                    return

                self._set_task_phase(task, "cancelling")
                self._emit_progress(task)
                logger.info(f"收到下载任务取消请求: task_id={task_id}")

    def get_tasks_info(self):
        """获取所有任务的简要信息 (供前端轮询或初始化)"""
        return [
            {
                "id": t.task_id,
                "filename": t.filename,
                "status": EventBus._normalize_progress_status(t.status.value),
                "progress": self._calc_percent(t),
                "speed": t.speed,
                "error": t.error_msg,
                "user_message": t.user_message,
                "error_type": t.error_type,
                "error_code": t.error_code,
                "error_id": t.error_id,
                "message_key": t.message_key,
                "message_params": dict(t.message_params or {}),
            }
            for t in self.tasks.values()
        ]

    def _download_worker(self, task: DownloadTask):
        """实际下载执行逻辑"""
        if task._cancel_event.is_set():
            self._set_task_phase(task, None)
            task.status = TaskStatus.CANCELLED
            task.speed = "已取消"
            self._cleanup_task_directory(task)
            self._emit_progress(task)
            return

        task.status = TaskStatus.RUNNING
        # 初始状态发送
        self._emit_progress(task)
        
        # 每个任务使用独立临时文件，避免同名并发下载互相覆盖。
        temp_path = f"{task.dest_path}.{task.task_id}.downloading"
        session = None
        
        try:
            # 1. 普通任务走 URL 级路由；直连任务不注入应用或环境代理。
            is_direct = task.network_mode == "direct"
            session = build_retry_session(
                route_manager=False if is_direct else None,
                trust_env=False if is_direct else None,
                network_override=task.network_override,
            )
            
            # 2. 发起请求 (Stream模式)。备用源由业务层传入，下载器不识别来源类型。
            headers = merge_headers({'Accept-Encoding': 'identity'})
            candidate_urls = list(task.source_urls or [task.url])
            if not candidate_urls:
                raise ValueError("下载任务缺少有效地址")

            chunk_size = 64 * 1024
            for attempt_index, active_url in enumerate(candidate_urls):
                if task._cancel_event.is_set():
                    raise InterruptedError("Task cancelled by user")
                task.status = TaskStatus.RUNNING
                task.downloaded_size = 0
                task.total_size = 0
                self._set_task_phase(task, None)
                task.speed = "0 B/s"
                self._emit_progress(task)
                start_time = time.time()
                last_emit_time = 0
                attempt = {"url": self._safe_url_marker(active_url), "source_role": "fallback" if attempt_index else "primary"}
                task.network_attempts.append(attempt)
                try:
                    with session.get(active_url, stream=True, timeout=(15, 120), headers=headers) as response:
                        attempt["http_status"] = response.status_code
                        attempt["final_url"] = self._safe_url_marker(response.url)
                        if route := getattr(session, "_last_route", None):
                            attempt.update({key: route[key] for key in ("route", "proxy_bypassed", "hosts_hit")})
                        response.raise_for_status()
                        if task.use_response_filename:
                            filename = self._resolve_filename(response.url, response.headers.get("Content-Disposition", ""))
                            if task.title == task.filename:
                                task.title = filename
                            task.filename = filename
                            task.dest_path = os.path.join(os.path.dirname(task.dest_path), task.filename)
                        uses_encoded_transfer = self._uses_encoded_transfer(response.headers)
                        # 【关键】只用未编码响应的传输长度校验文件；CDN 对象大小和预探测大小仅用于进度。
                        expected_size = None
                        content_length = str(response.headers.get('content-length') or '').strip()
                        if not uses_encoded_transfer and content_length.isdigit():
                            expected_size = int(content_length)
                        if int(getattr(response, 'status_code', 0) or 0) == 206:
                            content_range = re.fullmatch(r'bytes 0-(\d+)/(\d+)', str(response.headers.get('content-range') or '').strip())
                            if uses_encoded_transfer or not content_range or int(content_range[1]) + 1 != int(content_range[2]):
                                raise requests.exceptions.ChunkedEncodingError("下载服务器只返回了部分文件，请重试或切换下载来源。")
                            if expected_size is not None and expected_size != int(content_range[2]):
                                raise requests.exceptions.ChunkedEncodingError("下载文件长度与服务器声明不一致，请重试或切换下载来源。")
                            expected_size = int(content_range[2])
                        logger.debug(
                            "下载响应信息: final_url=%s content_length=%s content_range=%s transfer_encoding=%s content_encoding=%s stored_length=%s",
                            self._safe_url_marker(response.url),
                            response.headers.get('content-length'),
                            response.headers.get('content-range'),
                            response.headers.get('transfer-encoding'),
                            response.headers.get('content-encoding'),
                            response.headers.get('x-goog-stored-content-length'),
                        )
                        task.total_size = self._extract_total_size_from_headers(
                            response.headers,
                            trust_content_length=not uses_encoded_transfer,
                        )
                        if uses_encoded_transfer and task.total_size <= 0:
                            logger.debug(
                                "下载总大小不可用，响应启用了内容编码: url=%s final_url=%s content_encoding=%s",
                                self._safe_url_marker(active_url),
                                self._safe_url_marker(response.url),
                                response.headers.get('content-encoding'),
                            )

                        with open(temp_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if task._cancel_event.is_set():
                                    raise InterruptedError("Task cancelled by user")
                                if chunk:
                                    f.write(chunk)
                                    task.downloaded_size += len(chunk)
                                    if expected_size is not None and task.downloaded_size > expected_size:
                                        raise requests.exceptions.ChunkedEncodingError("下载文件长度与服务器声明不一致，请重试或切换下载来源。")
                                    if task.total_size > 0:
                                        overflow = task.downloaded_size - task.total_size
                                        overflow_tolerance = max(chunk_size, int(task.total_size * 0.02))
                                        if overflow > overflow_tolerance:
                                            logger.debug(
                                                "下载字节数超过服务器报告大小，已清空总大小用于继续显示进度: url=%s filename=%s current=%s total=%s",
                                                self._safe_url_marker(active_url), task.filename,
                                                task.downloaded_size, task.total_size,
                                            )
                                            task.total_size = 0
                                    curr_time = time.time()
                                    if curr_time - last_emit_time > 0.1:
                                        elapsed = curr_time - start_time
                                        if elapsed > 0:
                                            task.speed = self._fmt_speed(task.downloaded_size / elapsed)
                                        self._emit_progress(task)
                                        last_emit_time = curr_time

                    if expected_size is not None and task.downloaded_size != expected_size:
                        raise requests.exceptions.ChunkedEncodingError(f"下载文件不完整：应收到 {expected_size} 字节，实际收到 {task.downloaded_size} 字节，请重试或切换下载来源。")
                    task.total_size = task.downloaded_size

                    def check_cancel() -> None:
                        if task._cancel_event.is_set():
                            raise InterruptedError("Task cancelled by user")

                    if task.expected_hash:
                        task.status = TaskStatus.VERIFYING
                        task.speed = "正在校验"
                        self._emit_progress(task)
                        logger.debug("正在校验下载文件哈希: filename=%s", task.filename)
                        if not self._verify_hash(temp_path, task.expected_hash, task.hash_algorithm, cancel_check=check_cancel):
                            raise InvalidResponseError("文件哈希不一致，下载内容可能已损坏。")

                    if task.validate_download or task.validate_download_with_cancel:
                        task.status = TaskStatus.VERIFYING
                        task.speed = "正在校验"
                        self._emit_progress(task)
                        try:
                            if task.validate_download_with_cancel:
                                is_valid = task.validate_download_with_cancel(temp_path, check_cancel)
                            else:
                                is_valid = task.validate_download(temp_path)
                        except (InterruptedError, OSError):
                            raise
                        except Exception as validation_error:
                            raise InvalidResponseError("下载内容未通过业务校验。") from validation_error
                        if is_valid is False:
                            raise InvalidResponseError("下载内容未通过业务校验。")

                    if task._cancel_event.is_set():
                        raise InterruptedError("Task cancelled by user")
                    # 外部数据先在暂存文件上完成导入提交；其它任务保持原有替换顺序。
                    deferred_replace = bool(task.metadata.get("defer_replace"))
                    if deferred_replace and task.on_post_download:
                        task.metadata["staged_path"] = temp_path
                    elif deferred_replace:
                        raise ValueError("延迟替换任务缺少提交回调")
                    else:
                        os.replace(temp_path, task.dest_path)
                    if task.on_source_result:
                        try:
                            task.on_source_result(active_url, True)
                        except Exception:
                            logger.debug("下载源成功回调执行失败: url=%s", self._safe_url_marker(active_url), exc_info=True)
                    if attempt_index:
                        logger.info("下载备用源成功: task_id=%s source=%s", task.task_id, self._safe_url_marker(active_url))
                    break
                except InterruptedError:
                    raise
                except Exception as attempt_error:
                    self._cleanup(temp_path)
                    classified = classify_exception(attempt_error, module="download", action=task.task_type, context={"url": active_url})
                    attempt.update(error_type=classified.error_type, error_code=classified.error_code)
                    if task.on_source_result and isinstance(attempt_error, (requests.RequestException, InvalidResponseError)):
                        try:
                            task.on_source_result(active_url, False)
                        except Exception:
                            logger.debug("下载源失败回调执行失败: url=%s", self._safe_url_marker(active_url), exc_info=True)
                    if task._cancel_event.is_set():
                        raise InterruptedError("Task cancelled by user")
                    if not isinstance(attempt_error, (requests.RequestException, InvalidResponseError)) or attempt_index >= len(candidate_urls) - 1:
                        raise
                    logger.warning(
                        "下载源失败，尝试备用地址: task_id=%s failed_url=%s next_url=%s error=%s",
                        task.task_id, self._safe_url_marker(active_url),
                        self._safe_url_marker(candidate_urls[attempt_index + 1]), classified.error_code,
                    )

            if task.on_post_download:
                if task._cancel_event.is_set():
                    raise InterruptedError("Task cancelled by user")
                task.status = TaskStatus.RUNNING
                self._set_task_phase(task, "post_processing")
                task.speed = "正在处理"
                self._emit_progress(task)
                task.on_post_download(task)
                if task.metadata.get("defer_replace") and not os.path.exists(task.dest_path):
                    raise OSError("外部数据提交未生成目标文件")
            
            # 最后发送 COMPLETED，确保 100%
            self._set_task_phase(task, None)
            task.status = TaskStatus.COMPLETED
            task.speed = "完成"
            self._emit_progress(task)
            logger.info(f"下载任务完成: path={task.dest_path}")
            
            # 下载完成回调只表示文件已经落盘；安装等后处理使用 on_post_download。
            if task.on_complete:
                try:
                    task.on_complete(task)
                except Exception as cb_e:
                    logger.error(f"下载完成回调执行失败: task_id={task.task_id}, error={cb_e}")
        except InterruptedError:
            # 取消时不视为错误
            self._set_task_phase(task, None)
            task.status = TaskStatus.CANCELLED
            task.speed = "已取消"
            self._cleanup(temp_path)
            self._emit_progress(task)
        except Exception as e:
            self._set_task_phase(task, None)
            task.status = TaskStatus.ERROR
            task.error_msg = str(e)
            diagnostic_context = self._task_log_context(task)
            classified = classify_exception(
                e,
                module="download",
                action=task.task_type,
                context=diagnostic_context,
            )
            task.user_message = classified.user_message or tr("errors.download.failed", "下载失败。请检查网络连接、代理设置、下载源可用性和目标目录权限。")
            task.error_type = classified.error_type
            task.error_code = classified.error_code
            task.error_id = uuid.uuid4().hex[:10]
            task.message_key = classified.message_key or "errors.download.failed"
            task.message_params = dict(classified.message_params or {})
            task.metadata = {
                **dict(task.metadata or {}),
                "error_type": task.error_type,
                "error_code": task.error_code,
                "error_id": task.error_id,
                "message_key": task.message_key,
                "message_params": dict(task.message_params or {}),
                "user_message": task.user_message,
            }
            self._cleanup(temp_path)
            self._emit_progress(task)
            logger.error(
                "下载任务失败: task_id=%s filename=%s",
                task.task_id,
                task.filename,
                exc_info=True,
                extra={
                    "error_type": task.error_type,
                    "error_code": task.error_code,
                    "error_id": task.error_id,
                    "user_message": task.user_message,
                    "message_key": task.message_key,
                    "message_params": dict(task.message_params or {}),
                    "extra_context": diagnostic_context,
                },
            )
            # 执行失败回调
            if task.on_error:
                try:
                    task.on_error(task)
                except Exception:
                    logger.warning("下载失败回调执行失败: task_id=%s", task.task_id, exc_info=True)
        finally:
            if session:
                session.close()
            self._cleanup_task_directory(task)

    @staticmethod
    def _cleanup_task_directory(task: DownloadTask) -> None:
        temporary_dir = task.metadata.get("temporary_dir")
        if temporary_dir and Path(temporary_dir).name.startswith("git-task-") and Path(temporary_dir).resolve() == Path(task.dest_path).parent.resolve():
            shutil.rmtree(temporary_dir, ignore_errors=True)

    def _verify_hash(self, file_path: str, expected: str, algo: str = "md5",
                     cancel_check: Optional[Callable[[], None]] = None) -> bool:
        """校验文件 Hash"""
        try:
            h = hashlib.new(algo)
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    if cancel_check:
                        cancel_check()
                    h.update(chunk)
            calculated = h.hexdigest().lower()
            expected = expected.lower()
            
            if calculated != expected:
                logger.warning(f"下载文件哈希不一致: calculated={calculated}, expected={expected}")
                return False
            return True
        except InterruptedError:
            raise
        except Exception as e:
            logger.error(f"下载文件哈希校验失败: path={file_path}, error={e}")
            return False
    def _cleanup(self, path):
        if os.path.exists(path):
            try: os.remove(path)
            except: pass

    def _emit_progress(self, task: DownloadTask):
        """发送事件到前端"""
        progress = self._calc_percent(task)
        metrics = {
            "filename": task.filename,
            "total": task.total_size,
            "current": task.downloaded_size,
            "speed": task.speed,
            "title": task.title or task.filename,
            **dict(task.metadata or {}),
        }
        if task.status == TaskStatus.COMPLETED:
            metrics["file_path"] = task.dest_path
        if task.status == TaskStatus.ERROR:
            metrics["error"] = task.user_message or task.error_msg
        if task.status == TaskStatus.VERIFYING:
            metrics["phase"] = "verifying"
        extra_context = self._task_log_context(task) if task.status == TaskStatus.ERROR else None
        EventBus.emit_progress(
            task.task_id,
            task.task_type,
            status=EventBus._normalize_progress_status(task.status.value),
            progress=progress,
            message=task.user_message or task.filename or task.title or tr("tasks.download.running", "下载中..."),
            metrics=metrics,
            message_key=task.message_key,
            message_params=task.message_params,
            error_type=task.error_type,
            error_code=task.error_code,
            error_id=task.error_id,
            user_message=task.user_message,
            extra_context=extra_context,
        )

    def _calc_percent(self, task) -> int:
        # 如果是完成状态，强制返回 100
        if task.status == TaskStatus.COMPLETED: return 100
        if task.total_size <= 0: return 0
        return min(int((task.downloaded_size / task.total_size) * 100), 100) # 封顶 100

    def _fmt_speed(self, bytes_per_sec: float) -> str:
        if bytes_per_sec > 1024 * 1024:
            return f"{bytes_per_sec / 1024 / 1024:.1f} MB/s"
        if bytes_per_sec > 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        return f"{int(bytes_per_sec)} B/s"
    
    # 同步等待方法
    def get_task_future(self, task_id: str) -> Optional[Future]:
        """获取任务的 Future 对象，用于同步等待"""
        task = self.tasks.get(task_id)
        return task._future if task else None
