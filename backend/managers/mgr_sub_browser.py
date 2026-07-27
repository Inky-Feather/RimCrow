import json
import threading
import time

import webview

from backend.browser_runtime import WorkshopPageRenderer
from backend.i18n.messages import tr
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
            logger.debug(f"跳过子浏览器创意工坊渲染：{e}")

    def _delayed_load_url(self, url: str):
        if not self.window: return
        time.sleep(0.6)
        try:
            if self.window and self._mode == "external":
                self.window.load_url(url)
        except Exception as e:
            logger.debug(f"跳过子浏览器延迟加载：{e}")

    def _on_loaded(self):
        if not self.window: return
        try:
            current_url = self.window.get_current_url() or self._current_url
            if WorkshopPageRenderer.is_steamcommunity_url(current_url):
                self._current_url = current_url
                self.window.set_title(current_url)
                self._inject_workshop_toolbar(current_url)
                return
            if self._mode == "external":
                self.window.set_title(current_url)
        except Exception as e:
            logger.debug(f"跳过子浏览器加载钩子：{e}")

    def _on_closing(self):
        self.window = None
        self._mode = "external"
        self._current_url = ""

    def _inject_workshop_toolbar(self, url: str):
        if not self.window or not hasattr(self.window, "evaluate_js"): return
        workshop_id = WorkshopPageRenderer.extract_workshop_id(url)
        if not workshop_id: return

        messages = {
            "workshop_id": tr("common.field.workshop_id", "工坊 ID"),
            "unknown_id": tr("browser.workshop.toolbar.unknown_id", "未识别"),
            "open_original": tr("browser.workshop.toolbar.open_original", "打开原网页"),
            "open_in_steam": tr("browser.workshop.toolbar.open_in_steam", "在 Steam 打开"),
            "subscribe": tr("browser.workshop.toolbar.subscribe", "订阅"),
            "unsubscribe": tr("browser.workshop.toolbar.unsubscribe", "取消订阅"),
            "download": tr("browser.workshop.toolbar.download", "SteamCMD 下载"),
            "close": tr("common.action.close", "关闭"),
            "bridge_not_ready": tr("browser.workshop.script.bridge_not_ready", "页面桥接尚未就绪，请稍后重试。"),
            "action_done": tr("browser.workshop.script.action_done", "操作已完成"),
            "action_failed": tr("browser.workshop.script.action_failed", "操作失败"),
            "opening_steam": tr("browser.workshop.script.opening_steam", "正在尝试在 Steam 中打开当前页面..."),
            "subscribing": tr("browser.workshop.script.subscribing", "正在发送订阅请求..."),
            "unsubscribing": tr("browser.workshop.script.unsubscribing", "正在发送取消订阅请求..."),
            "downloading": tr("browser.workshop.script.downloading", "正在启动 SteamCMD 下载..."),
        }
        payload = json.dumps({"url": url, "workshopId": workshop_id, "messages": messages}, ensure_ascii=False).replace("</", "<\\/")
        script = f"""
(() => {{
  const config = {payload};
  const toolbarId = 'rimcrow-direct-workshop-toolbar';
  const styleId = 'rimcrow-direct-workshop-toolbar-style';
  const oldToolbar = document.getElementById(toolbarId);
  if (oldToolbar) oldToolbar.remove();
  if (!document.getElementById(styleId)) {{
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      #${{toolbarId}} {{
        position: fixed; left: 16px; right: 16px; top: 12px; z-index: 2147483647;
        min-height: 52px; box-sizing: border-box; display: flex; align-items: center; gap: 14px;
        padding: 10px 12px; border: 1px solid rgba(148, 163, 184, .35); border-radius: 8px;
        background: rgba(15, 23, 42, .94); color: #e5e7eb; box-shadow: 0 14px 40px rgba(0,0,0,.35);
        font: 13px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      #${{toolbarId}} * {{ box-sizing: border-box; }}
      #${{toolbarId}} .rimcrow-direct-title {{ min-width: 0; flex: 1; display: grid; gap: 2px; }}
      #${{toolbarId}} .rimcrow-direct-name {{ font-size: 13px; font-weight: 700; color: #f8fafc; }}
      #${{toolbarId}} .rimcrow-direct-url {{ max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #94a3b8; font-size: 12px; }}
      #${{toolbarId}} .rimcrow-direct-actions {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
      #${{toolbarId}} button {{
        height: 30px; padding: 0 11px; border: 0; border-radius: 7px; cursor: pointer;
        background: #38bdf8; color: #082f49; font: inherit; font-weight: 700;
      }}
      #${{toolbarId}} button.secondary {{ background: #334155; color: #e5e7eb; }}
      #${{toolbarId}} button.warn {{ background: #f59e0b; color: #451a03; }}
      #${{toolbarId}} .rimcrow-direct-status {{ min-width: 150px; max-width: 260px; color: #cbd5e1; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
      #${{toolbarId}} .rimcrow-direct-close {{ width: 30px; padding: 0; background: transparent; color: #94a3b8; border: 1px solid rgba(148, 163, 184, .35); }}
      body.rimcrow-direct-workshop-toolbar-active {{ padding-top: max(var(--rimcrow-original-padding-top, 0px), 76px) !important; }}
      @media (max-width: 720px) {{
        #${{toolbarId}} {{ left: 8px; right: 8px; top: 8px; align-items: stretch; flex-direction: column; }}
        #${{toolbarId}} .rimcrow-direct-actions {{ justify-content: flex-start; }}
        #${{toolbarId}} .rimcrow-direct-status {{ max-width: 100%; }}
        body.rimcrow-direct-workshop-toolbar-active {{ padding-top: max(var(--rimcrow-original-padding-top, 0px), 150px) !important; }}
      }}
    `;
    document.head.appendChild(style);
  }}
  document.body.style.setProperty('--rimcrow-original-padding-top', getComputedStyle(document.body).paddingTop || '0px');
  document.body.classList.add('rimcrow-direct-workshop-toolbar-active');

  const toolbar = document.createElement('section');
  toolbar.id = toolbarId;
  toolbar.innerHTML = `
    <div class="rimcrow-direct-title">
      <div class="rimcrow-direct-name"><span data-label="workshop_id"></span>: <strong></strong></div>
      <div class="rimcrow-direct-url"></div>
    </div>
    <div class="rimcrow-direct-actions">
      <button type="button" data-action="open_original" class="secondary"></button>
      <button type="button" data-action="open_in_steam" class="secondary"></button>
      <button type="button" data-action="subscribe"></button>
      <button type="button" data-action="unsubscribe" class="warn"></button>
      <button type="button" data-action="download" class="secondary"></button>
      <button type="button" class="rimcrow-direct-close" data-close="1"></button>
    </div>
    <div class="rimcrow-direct-status"></div>
  `;
  toolbar.querySelector('[data-label="workshop_id"]').textContent = config.messages.workshop_id;
  toolbar.querySelector('strong').textContent = config.workshopId || config.messages.unknown_id;
  toolbar.querySelector('.rimcrow-direct-url').textContent = config.url || window.location.href;
  const closeButton = toolbar.querySelector('button[data-close]');
  closeButton.textContent = '×';
  closeButton.title = config.messages.close;
  closeButton.setAttribute('aria-label', config.messages.close);
  for (const button of toolbar.querySelectorAll('button[data-action]')) {{
    button.textContent = config.messages[button.dataset.action] || button.dataset.action;
  }}
  const statusEl = toolbar.querySelector('.rimcrow-direct-status');
  const setStatus = (message, isError = false) => {{
    statusEl.textContent = message || '';
    statusEl.style.color = isError ? '#fca5a5' : '#cbd5e1';
  }};
  const pendingMessages = {{
    open_original: config.messages.open_original,
    open_in_steam: config.messages.opening_steam,
    subscribe: config.messages.subscribing,
    unsubscribe: config.messages.unsubscribing,
    download: config.messages.downloading,
  }};
  toolbar.addEventListener('click', async (event) => {{
    const closeButton = event.target.closest('button[data-close]');
    if (closeButton) {{
      toolbar.remove();
      document.body.classList.remove('rimcrow-direct-workshop-toolbar-active');
      document.body.style.removeProperty('--rimcrow-original-padding-top');
      return;
    }}
    const actionButton = event.target.closest('button[data-action]');
    if (!actionButton) return;
    const action = actionButton.dataset.action;
    const api = window.pywebview && window.pywebview.api;
    if (!api || !api.workshop_browser_action) {{
      setStatus(config.messages.bridge_not_ready, true);
      return;
    }}
    try {{
      setStatus(pendingMessages[action] || '');
      const result = await api.workshop_browser_action(action, config.workshopId, config.url || window.location.href);
      if (result && result.status === 'error') {{
        setStatus(result.user_message || result.message || config.messages.action_failed, true);
      }} else {{
        setStatus((result && (result.user_message || result.message)) || config.messages.action_done);
      }}
    }} catch (error) {{
      setStatus((error && error.message) || config.messages.action_failed, true);
    }}
  }});
  document.body.prepend(toolbar);
}})();
"""
        try:
            self.window.evaluate_js(script)
        except Exception as e:
            logger.debug(f"注入工坊悬浮工具栏失败：{e}")


class SteamWindowBridge:
    """专门用于子窗口的 JS API 桥接器"""

    def __init__(self, manager):
        self._mgr = manager

    def workshop_browser_action(self, action, workshop_id='', target_url=''):
        return self._mgr.main_api.workshop_browser_action(action, workshop_id, target_url)

    def workshop_browser_navigate(self, url=''):
        return self._mgr.navigate_workshop(url)
