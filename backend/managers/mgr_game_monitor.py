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
                
                if game_found and not self.is_game_running:
                    self._on_game_start()
                elif not game_found and self.is_game_running:
                    self._on_game_exit()
                
                time.sleep(5 if game_found else 2)
            except Exception as e:
                # print(f"[Monitor] Error: {e}")
                time.sleep(5)

    def _on_game_start(self):
        logger.info("[Monitor] 游戏启动，进入静默模式")
        window = self.api.get_window()
        if not window: return
        
        try:
            self.is_game_running = True
            
            # 0. 记忆当前地址 (如果在正常页面)
            curr = window.get_current_url()
            if curr and 'idle.html' not in curr and 'data:text' not in curr:
                self.resume_url = curr
            
            # 1. 通知前端：停止发送请求
            # 这里的事件名可以叫 'app-suspending'
            EventBus.emit('app-suspending')
            # 2. 给 300ms 延时。这足以让绝大多数已经发出的 API 请求完成往返
            # 同时也让前端有时间显示“正在保存配置”之类的提示
            # time.sleep(0.3) 
            # 3. 暂停事件流，防止切换过程中 Logger 发送日志导致报错
            EventBus.pause()
            # 停止后台扫描任务 (如果有)
            if hasattr(self.api, 'scanner'): self.api.scanner.stop_scan() 
            # 4. 执行页面切换
            window.load_url(f"file://{self.idle_page_path}")
            # 5. 最小化并清理内存
            # 延时一点点确保页面已经卸载，避免 WebView2 还在处理 JS
            time.sleep(0.5) 
            # window.minimize()
            self._trim_memory()
            
        except Exception as e:
            logger.error(f"[Monitor] Enter silent mode failed: {e}")
            EventBus.resume() # 失败则恢复

    def _on_game_exit(self):
        logger.info("[Monitor] 游戏关闭，恢复界面")
        window = self.api.get_window()
        if not window: return
        
        try:
            self.is_game_running = False
            
            # 1. 恢复 URL
            # 如果没有记忆的 URL，则通过 main.py 的逻辑获取默认入口
            from main import get_entrypoint
            target_url = self.resume_url if self.resume_url else get_entrypoint()
            
            window.load_url(target_url)
            # window.restore()
            
            # 2. 【关键】延迟恢复事件总线
            # 必须等待 Vue 前端完全加载并重新挂载事件监听器，否则事件会丢失或报错
            def delay_resume():
                time.sleep(3) # 给前端 23 秒钟初始化 Pinia 和 DOM
                EventBus.resume()
                logger.info("[Monitor] EventBus resumed")
                
            threading.Thread(target=delay_resume, daemon=True).start()
                
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