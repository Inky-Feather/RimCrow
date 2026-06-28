# backend/managers/mgr_download.py
import os
import re
import time
import uuid
import hashlib
import shutil
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Callable, Any
from urllib.parse import urlparse, unquote

from backend.utils.logger import logger
from backend.utils.event_bus import EventBus
from backend.settings import settings

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
    created_at: float = field(default_factory=time.time)
    speed: str = "0 B/s"
    # 校验相关
    expected_hash: Optional[str] = None
    hash_algorithm: str = "md5"
    # 回调函数 (接收 Task 对象)
    on_complete: Optional[Callable[['DownloadTask'], Any]] = None
    on_error: Optional[Callable[['DownloadTask'], Any]] = None
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

    def add_task(self, 
                 url: str, 
                 dest_dir: str, 
                 filename: Optional[str] = None,
                 expected_hash: Optional[str] = None,
                 hash_algorithm: str = "md5",
                 on_complete: Optional[Callable[[DownloadTask], Any]] = None,
                 on_error: Optional[Callable[[DownloadTask], Any]] = None
                 ) -> str:
        """
        添加下载任务
        :param url: 下载地址
        :param dest_dir: 目标文件夹 (注意：现在要求传入目录，文件名自动探测或指定)
        :param filename: 强制指定文件名 (可选)
        :param expected_hash: 期望的 Hash 值 (可选，若提供则会自动校验)
        :param hash_algorithm: Hash 算法 (md5, sha1, sha256)
        :param on_complete: 完成后的回调函数 (在子线程执行，请勿操作 GUI)
        :param on_error: 失败后的回调函数
        """
        real_url = self._sanitize_url(url)
        EventBus.resume()   # 恢复事件总线，确保下载任务能够正常执行
        
        # 确保目标目录存在
        os.makedirs(dest_dir, exist_ok=True)

        # 文件名解析逻辑
        if not filename:
            filename = self._resolve_filename(real_url)
        
        final_path = os.path.join(dest_dir, filename)

        # 创建任务对象
        task = DownloadTask(
            url=real_url, 
            dest_path=final_path, 
            filename=filename,
            expected_hash=expected_hash,
            hash_algorithm=hash_algorithm,
            on_complete=on_complete,
            on_error=on_error
        )
        with self._lock:
            self.tasks[task.task_id] = task
        
        logger.info(f"Task added: {filename} (ID: {task.task_id}) [HashCheck: {bool(expected_hash)}]")
        
        # 提交到线程池并保存 future
        task._future = self.executor.submit(self._download_worker, task)
        return task.task_id

    def _resolve_filename(self, url: str) -> str:
        """
        全能型文件名解析器
        """
        try:
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
                    if k.lower() == param:
                        return self._clean_filename(unquote(qs[k][0]))

            # --- 策略 C: 预检 HTTP Headers (最专业的方法) ---
            # 注意：这会发起一次同步请求，如果对响应速度要求极高，可以跳过此步
            # 使用 HEAD 请求只读取 Header，不下载内容，速度极快
            # allow_redirects=True 必须开启，因为很多下载是 302 跳转
            with requests.head(url, timeout=3, allow_redirects=True) as r:
                # 检查 Content-Disposition
                cd = r.headers.get('Content-Disposition')
                if cd:
                    # 匹配 filename="abc.exe" 或 filename=abc.exe
                    fname = re.findall(r'filename=["\']?(.*?)["\']?$', cd)
                    if fname: return self._clean_filename(unquote(fname[0]))
                    
                    # 匹配 RFC 5987 标准的 filename*=UTF-8''%e4%bd%a0%e5%a5%bd.txt
                    fname_rfc = re.findall(r"filename\s*=.*''(.+)", cd)
                    if fname_rfc: return self._clean_filename(unquote(fname_rfc[0]))

                # 如果 HEAD 请求没拿到结果，尝试从路径名判断
                if path_filename: return self._clean_filename(path_filename)
        except Exception as e:
            logger.warning(f"无法通过网络预检获取文件名: {e}")

        # --- 策略 D: 兜底逻辑 ---
        if path_filename:
            return self._clean_filename(path_filename)
        
        return "downloaded_file_" + os.urandom(4).hex()

    def _clean_filename(self, filename: str) -> str:
        """清理文件名中的非法字符，防止系统报错"""
        # 移除 Windows 下非法的路径字符 \ / : * ? " < > |
        return re.sub(r'[\\/:*?"<>|]', '_', filename).strip()

    def cancel_task(self, task_id: str):
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.VERIFYING]:
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
        
        # 使用临时文件：filename.downloading
        temp_path = task.dest_path + ".downloading"
        start_time = time.time()
        last_emit_time = 0
        
        try:
            # 1. 准备 Session (应用代理)
            session = requests.Session()
            # 这里的代理配置复用了 requests 对环境变量的支持
            # mgr_network.py 已经设置了 os.environ['HTTP_PROXY']
            # 但为了保险，也可以显式读取 settings
            # proxies = {}
            # proxy_cfg = settings.config.network.proxy
            # if proxy_cfg.enabled and proxy_cfg.host:
            #     p_str = f"{proxy_cfg.type}://{proxy_cfg.host}:{proxy_cfg.port}"
            #     proxies = {"http": p_str, "https": p_str}
            
            # 2. 发起请求 (Stream模式)
            # with session.get(task.url, stream=True, proxies=proxies, timeout=15) as response:
            # 模拟浏览器 Header，防止某些 CDN 拦截
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            with session.get(task.url, stream=True, timeout=20, headers=headers) as response:
                response.raise_for_status()
                # 获取文件大小
                total_length = response.headers.get('content-length')
                task.total_size = int(total_length) if total_length else 0
                
                # 增大 chunk_size 减少循环次数，降低 CPU 占用
                chunk_size = 64 * 1024 # 64KB
                # 3. 写入文件
                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        # 检查取消信号
                        if task._cancel_event.is_set():
                            raise InterruptedError("Task cancelled by user")
                        
                        if chunk:
                            f.write(chunk)
                            task.downloaded_size += len(chunk)
                            
                            # 计算速度与回调 (限制频率: 每 0.1s 更新一次)
                            curr_time = time.time()
                            # 【优化】降低节流阈值到 0.1s，保证 UI 流畅度
                            if curr_time - last_emit_time > 0.1:
                                elapsed = curr_time - start_time
                                if elapsed > 0:
                                    # 简单平均速度
                                    task.speed = self._fmt_speed(task.downloaded_size / elapsed)
                                self._emit_progress(task)
                                last_emit_time = curr_time
            
            # 【关键】循环结束后，强制发送一次“下载完成，正在处理”的状态
            # 确保前端收到 downloaded_size == total_size
            if task.total_size > 0:
                task.downloaded_size = task.total_size # 修正可能的字节偏差
            # --- 校验阶段 ---
            if task.expected_hash:
                task.status = TaskStatus.VERIFYING
                task.speed = "Verifying..."
                self._emit_progress(task)
                
                logger.debug(f"Verifying hash for {task.filename}...")
                if not self._verify_hash(temp_path, task.expected_hash, task.hash_algorithm):
                    raise ValueError("File hash mismatch! The file may be corrupted.")
            
            # --- 文件移动 ---
            if os.path.exists(task.dest_path):
                os.remove(task.dest_path) # 覆盖旧文件
            shutil.move(temp_path, task.dest_path)
            
            # 最后发送 COMPLETED，确保 100%
            task.status = TaskStatus.COMPLETED
            task.speed = "Done"
            self._emit_progress(task)
            logger.info(f"Download success: {task.dest_path}")
            
            # 执行回调
            if task.on_complete:
                try:
                    task.on_complete(task)
                except Exception as cb_e:
                    logger.error(f"Callback error in task {task.task_id}: {cb_e}")
        except InterruptedError:
            # 取消时不视为错误
            task.status = TaskStatus.CANCELLED
            self._cleanup(temp_path)
            self._emit_progress(task)
        except Exception as e:
            task.status = TaskStatus.ERROR
            task.error_msg = str(e)
            self._cleanup(temp_path)
            self._emit_progress(task)
            logger.error(f"Download failed [{task.url}]: {e}")
            # 执行失败回调
            if task.on_error:
                try:
                    task.on_error(task)
                except: pass

    def _verify_hash(self, file_path: str, expected: str, algo: str = "md5") -> bool:
        """校验文件 Hash"""
        try:
            h = hashlib.new(algo)
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            calculated = h.hexdigest().lower()
            expected = expected.lower()
            
            if calculated != expected:
                logger.warning(f"Hash mismatch: calculated={calculated}, expected={expected}")
                return False
            return True
        except Exception as e:
            logger.error(f"Hash check failed: {e}")
            return False
    def _cleanup(self, path):
        if os.path.exists(path):
            try: os.remove(path)
            except: pass

    def _emit_progress(self, task: DownloadTask):
        """发送事件到前端"""
        payload = {
            "id": task.task_id,
            "filename": task.filename,
            "file_path": task.dest_path,
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