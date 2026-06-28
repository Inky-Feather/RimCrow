import os
import time
import threading
import psutil
import ctypes
from backend.settings import DATA_DIR
from backend.utils.logger import logger
from backend.utils.event_bus import EventBus

from backend.static_page import IDLE_HTML # 不再使用字符串注入，改用文件


class GameMonitor:
    def __init__(self, api):
        self.api = api
        self.running = False
        self.game_process_name = "RimWorldWin64.exe" 
        self.is_game_running = False
        self.resume_url = None
        # 手动覆写标志，True 表示玩家强制要求唤醒，即使游戏在运行
        self.manual_override_idle = False 
        # Windows API
        self.psapi = ctypes.windll.psapi
        self.kernel32 = ctypes.windll.kernel32

        # 准备静默页面的路径 (生成一个真实的 html 文件)
        self.idle_page_path = str(DATA_DIR / 'idle.html')
        self._create_idle_page()

    def _create_idle_page(self):
        """生成一个极简的静态文件，比 load_html 字符串更节省内存且稳定"""
        content = IDLE_HTML
        try:
            with open(self.idle_page_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except: pass

    def start(self):
        self.running = True
        EventBus.resume()   # 恢复事件总线
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        while self.running:
            try:
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
                    EventBus.emit('game-status-changed', {'running': True})
                    if not self.manual_override_idle:
                        self._enter_idle_mode()
                        
                elif not game_found and self.is_game_running:
                    self.is_game_running = False
                    EventBus.emit('game-status-changed', {'running': False})
                    
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
        if hasattr(self.api, 'is_browser_runtime') and self.api.is_browser_runtime():
            try:
                EventBus.emit('app-suspending')
                EventBus.pause()
                if hasattr(self.api, 'scanner'):
                    self.api.scanner.stop_scan()
            except Exception as e:
                logger.error(f"[Monitor] Browser silent mode failed: {e}")
                EventBus.resume()
            return

        window = self.api.get_window()
        if not window: return
        try:
            curr = window.get_current_url()
            if curr and 'idle.html' not in curr and 'data:text' not in curr:
                self.resume_url = curr
            
            EventBus.emit('app-suspending')
            EventBus.pause()
            
            if hasattr(self.api, 'scanner'): self.api.scanner.stop_scan() 
            
            window.load_url(f"file://{self.idle_page_path}")
            time.sleep(0.5) 
            self._trim_memory()
        except Exception as e:
            logger.error(f"[Monitor] Enter silent mode failed: {e}")
            EventBus.resume()

    def _exit_idle_mode(self):
        """恢复主界面"""
        logger.info("[Monitor] 恢复主界面")
        if hasattr(self.api, 'is_browser_runtime') and self.api.is_browser_runtime():
            try:
                EventBus.resume()
                EventBus.emit('app-resuming')
                EventBus.emit('game-status-changed', {'running': self.is_game_running})
                logger.info("[Monitor] 浏览器模式已恢复主界面")
            except Exception as e:
                logger.error(f"[Monitor] Browser resume failed: {e}")
            return

        window = self.api.get_window()
        if not window: return
        
        try:
            # 【核心修复2】：防御性检查。如果当前不是 idle.html，说明已经在主界面了，绝对不要 load_url
            curr = window.get_current_url()
            if curr and 'idle.html' not in curr:
                logger.info("[Monitor] 当前已是主界面，无需重载 URL")
                return
            
            from main import get_entrypoint
            target_url = self.resume_url if self.resume_url else get_entrypoint()
            logger.info(f"[Monitor] 正在重载主界面: {target_url}")
            window.load_url(target_url)
            # 让前端在 onMounted 时主动调用 API 恢复
            logger.info("[Monitor] 等待前端 UI 唤醒确认...")
        except Exception as e:
            logger.error(f"[Monitor] Resume failed: {e}")
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


