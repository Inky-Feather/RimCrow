import webview
import re
from backend.static_page import LOADING_HTML
from backend.utils.logger import logger


    
class SubBrowserManager:
    """浏览器子窗口管理器"""
    
    def __init__(self, main_api):
        self.main_api = main_api  # 引用主 API 以便调用通用逻辑
        self.window = None
        
    def open(self, url='', title = '正在加载...'):
        """打开窗口或跳转 URL"""
        if self.window:
            try:
                # 如果窗口还活着，直接加载新 URL
                self.window.load_url(url)
                self.window.show() # 确保可见并置顶
                return
            except:
                # 窗口可能已被用户关闭，重置引用
                self.window = None

        # 创建轻量级桥接对象，仅暴露动作方法，杜绝递归报错
        bridge = SteamWindowBridge(self)
        # 创建新窗口
        self.window = webview.create_window(
            title=title,
            html=LOADING_HTML, # 立即加载本地 HTML
            width=1200,
            height=800,
            js_api=bridge,
        )
        if not self.window: return
         # 2. 窗口显示后，再在后台启动真正的 URL 加载
        # 使用定时器或直接调用，让本地 HTML 有机会渲染出来
        import threading
        def delayed_load():
            if not self.window: return
            import time
            time.sleep(1) # 给渲染引擎一点喘息时间
            self.window.load_url(url)
        threading.Thread(target=delayed_load).start()
        
        # 注册加载完成事件，用于注入 JS 悬浮球
        self.window.events.loaded += self._on_loaded
        self.window.events.closing += self._on_closing

    def _on_loaded(self):
        """页面加载完成，执行注入"""
        if not self.window: return
        try:
            url = self.window.get_current_url() or ""
            self.window.set_title(url)
            # 仅在 steamcommunity.com 域名下注入
            if 'steamcommunity.com/sharedfiles/filedetails' in url:
                self.window.evaluate_js(self._get_injection_js())
        except Exception as e:
            logger.error(f"Injection skipped: {e}")

    def _on_closing(self):
        """窗口关闭时清理引用"""
        self.window = None

    def execute_action(self, action, url):
        """执行具体的业务逻辑 (订阅/下载等)"""
        workshop_id = self._extract_id(url)
        logger.info(f"Steam Action: {action} | ID: {workshop_id}")
        
        if not workshop_id:
            return {"status": "error", "message": "无法识别模组ID"}

        # 具体的业务实现
        if action == 'subscribe':
            # 这里调用订阅逻辑
            self.main_api.steam_subscribe(workshop_id)
        elif action == 'unsubscribe':
            # 取消订阅逻辑
            self.main_api.steam_unsubscribe(workshop_id)
        elif action == 'download':
            # 下载逻辑 (例如通过 steamcmd 或 第三方 API)
            pass
            
        return {"action": action, "id": workshop_id}

    def _extract_id(self, url):
        match = re.search(r'id=(\d+)', url)
        return match.group(1) if match else None

    def _get_injection_js(self):
        """返回悬浮球的 JS 代码 (逻辑同前，保持高级感)"""
        # 这里建议将之前的 JS 字符串单独放在一个 .js 文件中读取，或者保持在这里
        return """
        (function() {
            if (document.getElementById('rim-steam-helper')) return;
            const style = document.createElement('style');
            style.innerHTML = `
                #rim-steam-helper { position: fixed; bottom: 30px; right: 30px; z-index: 999999; display: flex; flex-direction: column-reverse; align-items: flex-end; }
                .rim-ball { width: 48px; height: 48px; border-radius: 24px; background: rgba(6, 182, 212, 0.85); backdrop-filter: blur(10px); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); border: 1px solid rgba(255,255,255,0.2); box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
                .rim-ball:hover { transform: scale(1.1) rotate(90deg); background: #06b6d4; }
                .rim-menu { margin-bottom: 12px; display: none; flex-direction: column; gap: 6px; background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(20px); padding: 8px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 12px 40px rgba(0,0,0,0.6); }
                .rim-menu.show { display: flex; animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
                .rim-btn { padding: 8px 16px; border-radius: 8px; border: none; background: transparent; color: #cbd5e1; font-size: 13px; text-align: left; cursor: pointer; transition: all 0.2s; white-space: nowrap; font-weight: 600; display: flex; align-items: center; gap: 8px; }
                .rim-btn:hover { background: rgba(255,255,255,0.05); color: #22d3ee; }
                .rim-btn.danger:hover { color: #ef4444; }
                @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
            `;
            document.head.appendChild(style);
            const container = document.createElement('div');
            container.id = 'rim-steam-helper';
            container.innerHTML = `
                <div class="rim-ball"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path></svg></div>
                <div class="rim-menu" id="rim-menu">
                    <button class="rim-btn" onclick="rimAction('subscribe')">✨ 订阅模组</button>
                    <button class="rim-btn danger" onclick="rimAction('unsubscribe')">🚫 取消订阅</button>
                    <div style="height:1px; background: rgba(255,255,255,0.05); margin: 2px 4px;"></div>
                    <button class="rim-btn" onclick="rimAction('download')">📥 下载文件</button>
                </div>
            `;
            document.body.appendChild(container);
            const ball = container.querySelector('.rim-ball');
            const menu = container.querySelector('#rim-menu');
            ball.onclick = () => menu.classList.toggle('show');
            window.rimAction = (action) => {
                window.pywebview.api.steam_workshop_action(action, window.location.href).then(res => {
                    menu.classList.remove('show');
                });
            };
        })();
        """

class SteamWindowBridge:
    """专门用于子窗口的 JS API 桥接器"""
    # 只保留对父级 api 的引用，但不直接暴露给 JS 扫描
    def __init__(self, manager):
        self._mgr = manager

    def steam_workshop_action(self, action, url):
        # 转发请求给管理器
        return self._mgr.execute_action(action, url)