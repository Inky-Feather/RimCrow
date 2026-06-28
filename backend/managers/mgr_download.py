# backend/managers/mgr_download.py
import os
import time
import uuid
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Callable
from urllib.parse import urlparse

from backend.utils.logger import logger
from backend.utils.event_bus import EventBus
from backend.settings import settings

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
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
    created_at: float = field(default_factory=time.time)
    speed: str = "0 B/s"
    # 内部控制
    _cancel_event: threading.Event = field(default_factory=threading.Event)
    _completion_event: threading.Event = field(default_factory=threading.Event)

class DownloadManager:
    _instance = None
    
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
        logger.info("DownloadManager initialized.")

    def _sanitize_url(self, url: str) -> str:
        """
        智能清洗 URL，处理特殊站点的链接规则
        """
        # 规则1: GitHub Blob -> Raw
        # 输入: https://github.com/user/repo/blob/main/file.json
        # 输出: https://raw.githubusercontent.com/user/repo/main/file.json
        if "github.com" in url and "/blob/" in url:
            new_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            logger.debug(f"Sanitized GitHub URL: {url} -> {new_url}")
            return new_url
        return url

    def add_task(self, url: str, dest_path: str, filename= None) -> str:
        """
        添加下载任务
        :param url: 下载链接
        :param dest_path: 目标文件夹路径 或 完整文件路径
        :param filename: (可选) 如果 dest_path 是文件夹，需指定文件名
        :return: task_id
        """
        real_url = self._sanitize_url(url)
        
        # 路径处理逻辑
        if os.path.isdir(dest_path):
            if not filename:
                # 尝试从 URL 猜测文件名
                parsed = urlparse(real_url)
                filename = os.path.basename(parsed.path) or "downloaded_file"
            final_path = os.path.join(dest_path, filename)
        else:
            final_path = dest_path
            filename = os.path.basename(final_path)

        task = DownloadTask(url=real_url, dest_path=final_path, filename=filename)
        self.tasks[task.task_id] = task
        logger.info(f"Download task added: {filename} ({task.task_id})")
        
        # 提交到线程池
        self.executor.submit(self._download_worker, task)
        return task.task_id

    def cancel_task(self, task_id: str):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                task._cancel_event.set()
                task.status = TaskStatus.CANCELLED
                self._emit_progress(task)
                logger.info(f"Task cancelled: {task_id}")

    def get_tasks_info(self):
        """获取所有任务的简要信息 (供前端轮询或初始化)"""
        return [
            {
                "id": t.task_id,
                "filename": t.filename,
                "status": t.status.value,
                "progress": self._calc_percent(t),
                "speed": t.speed,
                "error": t.error_msg
            }
            for t in self.tasks.values()
        ]

    def _download_worker(self, task: DownloadTask):
        """实际下载执行逻辑"""
        task.status = TaskStatus.RUNNING
        # 初始状态发送
        self._emit_progress(task)
        
        temp_path = task.dest_path + ".tmp"
        start_time = time.time()
        last_emit_time = 0
        
        try:
            # 1. 准备 Session (应用代理)
            session = requests.Session()
            # 这里的代理配置复用了 requests 对环境变量的支持
            # mgr_network.py 已经设置了 os.environ['HTTP_PROXY']
            # 但为了保险，也可以显式读取 settings
            proxies = {}
            proxy_cfg = settings.config.network.proxy
            if proxy_cfg.enabled and proxy_cfg.host:
                p_str = f"{proxy_cfg.type}://{proxy_cfg.host}:{proxy_cfg.port}"
                proxies = {"http": p_str, "https": p_str}
            
            # 2. 发起请求 (Stream模式)
            # with session.get(task.url, stream=True, proxies=proxies, timeout=15) as response:
            with session.get(task.url, stream=True, timeout=15) as response:
                response.raise_for_status()
                # 获取文件大小
                total_length = response.headers.get('content-length')
                task.total_size = int(total_length) if total_length else 0
                
                # 增大 chunk_size 减少循环次数，降低 CPU 占用
                chunk_size = 32 * 1024 
                # 3. 写入文件
                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        # 检查取消信号
                        if task._cancel_event.is_set():
                            raise InterruptedError("Task cancelled")
                        
                        if chunk:
                            f.write(chunk)
                            task.downloaded_size += len(chunk)
                            
                            # 计算速度与回调 (限制频率: 每 0.1s 更新一次)
                            current_time = time.time()
                            # 【优化】降低节流阈值到 0.1s，保证 UI 流畅度
                            if current_time - last_emit_time > 0.1:
                                elapsed = current_time - start_time
                                if elapsed > 0:
                                    # 简单平均速度
                                    task.speed = self._fmt_speed(task.downloaded_size / elapsed)
                                self._emit_progress(task)
                                last_emit_time = current_time
            
            # 【关键】循环结束后，强制发送一次“下载完成，正在处理”的状态
            # 确保前端收到 downloaded_size == total_size
            if task.total_size > 0:
                task.downloaded_size = task.total_size # 修正可能的字节偏差
            task.speed = "Processing..."
            self._emit_progress(task) 

            # 文件重命名操作
            if os.path.exists(task.dest_path):
                os.remove(task.dest_path) # 覆盖旧文件
            os.rename(temp_path, task.dest_path)
            
            # 【关键】最后发送 COMPLETED，确保 100%
            task.status = TaskStatus.COMPLETED
            task.speed = "Done"
            self._emit_progress(task)
            logger.info(f"Download completed: {task.dest_path}")
            
        except InterruptedError:
            # 取消时不视为错误
            task.status = TaskStatus.CANCELLED
            self._cleanup_temp(temp_path)
            self._emit_progress(task)
        except Exception as e:
            task.status = TaskStatus.ERROR
            task.error_msg = str(e)
            self._cleanup_temp(temp_path)
            self._emit_progress(task)
            logger.error(f"Download failed [{task.url}]: {e}")
        finally:
            # 无论成功失败，触发完成信号
            task._completion_event.set()

    def _cleanup_temp(self, path):
        if os.path.exists(path):
            try: os.remove(path)
            except: pass

    def _emit_progress(self, task: DownloadTask):
        """发送事件到前端"""
        payload = {
            "id": task.task_id,
            "filename": task.filename,
            "status": task.status.value,
            "total": task.total_size,
            "current": task.downloaded_size,
            "percent": self._calc_percent(task), # 计算百分比
            "speed": task.speed,
            "error": task.error_msg
        }
        EventBus.emit("download-progress", payload)

    def _calc_percent(self, task) -> int:
        # 如果是完成状态，强制返回 100
        if task.status == TaskStatus.COMPLETED:
            return 100
        if task.total_size <= 0: 
            return 0
        p = int((task.downloaded_size / task.total_size) * 100)
        return min(p, 100) # 封顶 100

    def _fmt_speed(self, bytes_per_sec: float) -> str:
        if bytes_per_sec > 1024 * 1024:
            return f"{bytes_per_sec / 1024 / 1024:.1f} MB/s"
        if bytes_per_sec > 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        return f"{int(bytes_per_sec)} B/s"
    
    # 同步等待方法
    def wait_for_task(self, task_id: str, timeout: int = 60) -> bool:
        """
        阻塞直到任务完成或超时
        :return: True if success, False if failed/timeout
        """
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        # 阻塞等待信号
        is_set = task._completion_event.wait(timeout)
        
        if not is_set:
            return False # 超时
        
        return task.status == TaskStatus.COMPLETED