import threading
import time

import webview

from backend.browser_runtime import WorkshopPageRenderer
from backend.static_page import LOADING_HTML
from backend.utils.logger import logger


class SubBrowserManager:
    """浏览器子窗口管理器"""

    def __init__(self, main_api):
        self.main_api = main_api
        self.window = None
        self._mode = "external"
        self._current_url = ""

    def open(self, url='', title='正在加载...'):
        normalized_url = str(url or '').strip()
        is_workshop_page = WorkshopPageRenderer.is_steamcommunity_url(normalized_url)

        if self.window:
            try:
                if is_workshop_page:
                    self._mode = "workshop_proxy"
                    self._current_url = normalized_url
                    self.window.set_title(normalized_url or title)
                    threading.Thread(target=self._async_render_workshop, args=(normalized_url,), daemon=True).start()
                else:
                    self._mode = "external"
                    self._current_url = normalized_url
                    self.window.load_url(normalized_url)
                    self.window.set_title(title)
                self.window.show()
                return
            except Exception:
                self.window = None

        bridge = SteamWindowBridge(self)
        self._mode = "workshop_proxy" if is_workshop_page else "external"
        self._current_url = normalized_url

        self.window = webview.create_window(
            title=normalized_url if is_workshop_page else title,
            html=LOADING_HTML,
            width=1200,
            height=800,
            js_api=bridge,
        )
        if not self.window: return

        if is_workshop_page:
            threading.Thread(target=self._async_render_workshop, args=(normalized_url,), daemon=True).start()
        else:
            threading.Thread(target=self._delayed_load_url, args=(normalized_url,), daemon=True).start()

        self.window.events.loaded += self._on_loaded
        self.window.events.closing += self._on_closing

    def navigate_workshop(self, url=''):
        normalized_url = str(url or '').strip()
        if not normalized_url: return {"status": "error", "message": "未提供目标页面地址"}
        if not self.window:
            self.open(normalized_url, normalized_url)
            return {"status": "success"}

        self._mode = "workshop_proxy"
        self._current_url = normalized_url
        try:
            self.window.set_title(f"加载中 - {normalized_url}")
            self.window.show()
        except Exception:
            pass
        threading.Thread(target=self._async_render_workshop, args=(normalized_url, 0.08), daemon=True).start()
        return {"status": "success"}

    def _render_workshop_html(self, url: str):
        renderer = WorkshopPageRenderer(navigation_mode="webview")
        return renderer.render(url)

    def _async_render_workshop(self, url: str, delay: float = 0.0):
        if delay > 0:
            time.sleep(delay)
        html = self._render_workshop_html(url)
        try:
            if self.window and self._mode == "workshop_proxy" and self._current_url == url:
                self.window.load_html(html)
                self.window.set_title(url)
        except Exception as e:
            logger.debug(f"Sub browser workshop render skipped: {e}")

    def _delayed_load_url(self, url: str):
        if not self.window: return
        time.sleep(0.6)
        try:
            if self.window and self._mode == "external":
                self.window.load_url(url)
        except Exception as e:
            logger.debug(f"Sub browser delayed load skipped: {e}")

    def _on_loaded(self):
        if not self.window: return
        try:
            if self._mode == "external":
                current_url = self.window.get_current_url() or self._current_url
                self.window.set_title(current_url)
        except Exception as e:
            logger.debug(f"Sub browser load hook skipped: {e}")

    def _on_closing(self):
        self.window = None
        self._mode = "external"
        self._current_url = ""


class SteamWindowBridge:
    """专门用于子窗口的 JS API 桥接器"""

    def __init__(self, manager):
        self._mgr = manager

    def workshop_browser_action(self, action, workshop_id='', target_url=''):
        return self._mgr.main_api.workshop_browser_action(action, workshop_id, target_url)

    def workshop_browser_navigate(self, url=''):
        return self._mgr.navigate_workshop(url)
