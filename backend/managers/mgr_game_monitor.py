import os
import time
import threading
from dataclasses import asdict, dataclass

import ctypes
import psutil
from backend.settings import DATA_DIR
from backend.settings import settings
from backend.utils.logger import logger
from backend.utils.event_bus import EventBus
from backend.static_page import build_idle_home_html, build_idle_logs_html


@dataclass
class RuntimeSession:
    """记录当前游戏运行态，供前后端共享最小事实。"""

    profile_id: str = ""
    state: str = "idle"
    source: str = "manager"
    launch_mode: str = "unknown"
    requested_at: int | None = None
    deadline_at: int | None = None
    started_at: int | None = None
    failure_reason: str = ""
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class GameMonitor:
    LAUNCH_TIMEOUT_SECONDS = 60

    def __init__(self, api):
        self.api = api
        self.running = False
        self.game_process_name = "RimWorldWin64.exe" 
        self.is_game_running = False
        self.runtime_session = RuntimeSession()
        self.resume_url = None
        # 手动覆写标志，True 表示玩家强制要求唤醒，即使游戏在运行
        self.manual_override_idle = False 
        # Windows API
        self.psapi = ctypes.windll.psapi
        self.kernel32 = ctypes.windll.kernel32

        # 准备静默页面的路径 (生成真实 html 文件，避免长字符串常驻内存)
        self.idle_home_page_path = str(DATA_DIR / 'idle.html')
        self.idle_logs_page_path = str(DATA_DIR / 'idle_logs.html')
        self._create_idle_pages()

    def _write_page(self, filepath: str, content: str):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass

    def _create_idle_pages(self):
        """生成静默主页和静默日志页。"""
        self._write_page(self.idle_home_page_path, build_idle_home_html())
        self._write_page(
            self.idle_logs_page_path,
            build_idle_logs_html(),
        )

    def _get_default_idle_page_path(self) -> str:
        if str(settings.config.silent_mode_default_view).strip().lower() == 'logs':
            return self.idle_logs_page_path
        return self.idle_home_page_path

    def _is_idle_page_url(self, url: str | None) -> bool:
        """统一识别静默主页和静默日志页，避免误判为主界面。"""
        value = str(url or '').lower()
        return 'idle.html' in value or 'idle_logs.html' in value

    def _load_url_deferred(self, target_url: str, delay: float = 0.05):
        """
        轻微延后切页，让 pywebview 先把 API 返回值送回当前页面，
        避免页面已切走时回调函数丢失。
        """
        window = self.api.get_window()
        if not window or not target_url: return

        def _worker():
            try:
                time.sleep(max(0.0, delay))
                window.load_url(target_url)
            except Exception as e:
                logger.error(f"[Monitor] 延迟切换页面失败: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def get_runtime_session(self) -> RuntimeSession:
        return self.runtime_session

    def get_runtime_session_data(self) -> dict:
        return self.runtime_session.to_dict()

    def begin_launch(self, profile_id: str, launch_mode: str, *, message: str = "") -> RuntimeSession:
        now_ms = int(time.time() * 1000)
        self.runtime_session = RuntimeSession(
            profile_id=str(profile_id or "").strip(),
            state="launching",
            source="manager",
            launch_mode=str(launch_mode or "unknown").strip() or "unknown",
            requested_at=now_ms,
            deadline_at=now_ms + self.LAUNCH_TIMEOUT_SECONDS * 1000,
            message=message,
        )
        return self.runtime_session

    def mark_launch_failed(self, reason: str, message: str = "") -> RuntimeSession:
        self.runtime_session = RuntimeSession(
            state="idle",
            failure_reason=str(reason or "").strip(),
            message=message,
        )
        return self.runtime_session

    def expire_launch_if_needed(self, now_ms: int | None = None) -> RuntimeSession | None:
        session = self.runtime_session
        if session.state != "launching" or not session.deadline_at:
            return None

        current = int(time.time() * 1000) if now_ms is None else int(now_ms)
        if current < int(session.deadline_at):
            return None

        return self.mark_launch_failed("launch_timeout", "启动超时，未检测到游戏进程。")

    def _mark_running_from_launch(self) -> tuple[RuntimeSession, dict]:
        session = self.runtime_session
        now_ms = int(time.time() * 1000)
        profile_id = str(session.profile_id or "").strip()
        self.runtime_session = RuntimeSession(
            profile_id=profile_id,
            state="running",
            source="manager",
            launch_mode=session.launch_mode,
            requested_at=session.requested_at,
            deadline_at=session.deadline_at,
            started_at=now_ms,
            message=session.message,
        )
        if profile_id:
            self.api.profile_mgr.update_profile(profile_id, {"last_played_time": now_ms})
        return self.runtime_session, {
            "running": True,
            "profile_id": profile_id,
            "last_played_time": now_ms,
            "source": "manager",
            "runtime_session": self.runtime_session.to_dict(),
        }

    def _attach_external_runtime(self) -> tuple[RuntimeSession, dict]:
        now_ms = int(time.time() * 1000)
        self.runtime_session = RuntimeSession(
            profile_id="default",
            state="running",
            source="external",
            launch_mode="unknown",
            started_at=now_ms,
            message="外部启动，已按 default 接管",
        )
        return self.runtime_session, {
            "running": True,
            "profile_id": "default",
            "source": "external",
            "message": self.runtime_session.message,
            "runtime_session": self.runtime_session.to_dict(),
        }

    def mark_running(self) -> tuple[RuntimeSession, dict]:
        session = self.runtime_session
        if session.state == "launching" and session.source == "manager" and str(session.profile_id or "").strip():
            return self._mark_running_from_launch()
        return self._attach_external_runtime()

    def mark_stopped(self) -> tuple[RuntimeSession, dict]:
        self.runtime_session = RuntimeSession()
        return self.runtime_session, {"running": False, "runtime_session": self.runtime_session.to_dict()}

    def start(self):
        self.running = True
        EventBus.resume()   # 恢复事件总线
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        while self.running:
            try:
                expired_session = self.expire_launch_if_needed()
                if expired_session:
                    EventBus.emit(
                        'game-status-changed',
                        {
                            'running': False,
                            'runtime_session': expired_session.to_dict(),
                            'failure_reason': expired_session.failure_reason,
                            'message': expired_session.message,
                        },
                    )

                game_found = False
                # 优化：使用 process_iter 的过滤器减少性能消耗
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'] == self.game_process_name:
                        game_found = True
                        break
                
                # 状态机跃迁逻辑更新
                if game_found and not self.is_game_running:
                    self.is_game_running = True
                    # 通知前端游戏开始了（无论是否静默，前端都需要知道这个状态）
                    payload: dict[str, object] = {'running': True}
                    try:
                        session, payload = self.mark_running()
                    except Exception as e:
                        logger.warning(f"[Monitor] 记录游戏启动时间失败: {e}", exc_info=True)
                    EventBus.emit('game-status-changed', payload)
                    if settings.config.auto_enter_silent_mode and not self.manual_override_idle:
                        self._enter_idle_mode()
                        
                elif not game_found and self.is_game_running:
                    self.is_game_running = False
                    session, payload = self.mark_stopped()
                    EventBus.emit('game-status-changed', payload)
                    
                    # 【核心修复1】：如果用户已经手动唤醒了，不要再去强刷页面！
                    if self.manual_override_idle:
                        logger.info("[Monitor] 游戏退出，但用户已在主界面，跳过页面重载")
                        self.manual_override_idle = False # 仅重置标志位即可
                    else:
                        self._exit_idle_mode()
                
                time.sleep(5 if game_found else 2)
            except Exception as e:
                # print(f"[Monitor] Error: {e}")
                time.sleep(5)

    def _enter_idle_mode(self):
        """进入静默模式 (原 _on_game_start)"""
        logger.info("[Monitor] 游戏运行中，进入静默模式")
        # 进入前重新生成静态页，确保最新设置立即生效。
        self._create_idle_pages()
        if hasattr(self.api, 'is_browser_runtime') and self.api.is_browser_runtime():
            try:
                EventBus.emit('app-suspending')
                EventBus.pause()
                if hasattr(self.api, 'scanner'):
                    self.api.scanner.stop_scan()
            except Exception as e:
                logger.error(f"[Monitor] 浏览器静默模式设置失败：{e}")
                EventBus.resume()
            return

        window = self.api.get_window()
        if not window: return
        try:
            curr = window.get_current_url()
            if curr and not self._is_idle_page_url(curr) and 'data:text' not in curr:
                self.resume_url = curr
            
            EventBus.emit('app-suspending')
            EventBus.pause()
            
            if hasattr(self.api, 'scanner'): self.api.scanner.stop_scan() 
            
            window.load_url(f"file://{self._get_default_idle_page_path()}")
            time.sleep(0.5) 
            self._trim_memory()
        except Exception as e:
            logger.error(f"[Monitor] 进入静默模式失败：{e}")
            EventBus.resume()

    def _exit_idle_mode(self):
        """恢复主界面"""
        logger.info("[Monitor] 恢复主界面")
        if hasattr(self.api, 'is_browser_runtime') and self.api.is_browser_runtime():
            try:
                EventBus.resume()
                EventBus.emit('app-resuming')
                EventBus.emit('game-status-changed', {'running': self.is_game_running, 'runtime_session': self.get_runtime_session_data()})
                logger.info("[Monitor] 浏览器模式已恢复主界面")
            except Exception as e:
                logger.error(f"[Monitor] 浏览器恢复失败：{e}")
            return

        window = self.api.get_window()
        if not window: return
        
        try:
            curr = window.get_current_url()
            if curr and not self._is_idle_page_url(curr):
                logger.info("[Monitor] 当前已是主界面，无需重载 URL")
                return
            
            from main import get_entrypoint
            target_url = self.resume_url if self.resume_url else get_entrypoint()
            logger.info(f"[Monitor] 正在重载主界面: {target_url}")
            self._load_url_deferred(target_url)
            # 让前端在 onMounted 时主动调用 API 恢复
            logger.info("[Monitor] 等待前端 UI 唤醒确认...")
        except Exception as e:
            logger.error(f"[Monitor] 恢复失败：{e}")
            EventBus.resume()

    def _trim_memory(self):
        try:
            pid = os.getpid()
            handle = self.kernel32.OpenProcess(0x001F0FFF, False, pid)
            if handle:
                self.psapi.EmptyWorkingSet(handle)
                self.kernel32.CloseHandle(handle)
                logger.info("[Monitor] 内存物理占用已强制释放")
        except: pass
        
    def force_wake(self):
        """玩家在 idle.html 点击了强制唤醒"""
        if self.is_game_running:
            logger.info("[Monitor] 玩家强制唤醒主界面")
            self.manual_override_idle = True
            self._exit_idle_mode()
            
    def force_sleep(self):
        """玩家在主界面点击了重新进入静默"""
        if self.is_game_running:
            logger.info("[Monitor] 玩家手动返回静默模式")
            self.manual_override_idle = False
            self._enter_idle_mode()

    def open_idle_home(self):
        """静默模式下切回主页。"""
        self._create_idle_pages()
        self._load_url_deferred(f"file://{self.idle_home_page_path}")

    def open_idle_logs(self):
        """静默模式下打开日志页。"""
        self._create_idle_pages()
        self._load_url_deferred(f"file://{self.idle_logs_page_path}")


