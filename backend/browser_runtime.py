import json
import mimetypes
import os
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import html

from backend.static_page import (
    build_sub_browser_helper_html,
    build_workshop_error_html,
    build_workshop_page_html,
)
from backend.utils.logger import logger
from validate_environment import is_port_available


SESSION_TTL_SECONDS = 30.0
PRIMARY_CLOSE_GRACE_SECONDS = 3.0
DEV_SERVER_URL = "http://localhost:5173"
REMOTE_FETCH_TIMEOUT_SECONDS = 20
REMOTE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)


def build_sub_browser_target_url(base_url: str, url: str = "", title: str = "RimModManager") -> str:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return ""

    normalized_base_url = str(base_url or "").rstrip("/")
    if not normalized_base_url:
        return normalized_url

    parsed = urlparse(normalized_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower().endswith("steamcommunity.com"):
        return f"{normalized_base_url}/workshop-view?url={quote(normalized_url, safe='')}"

    helper_title = str(title or "RimModManager").strip() or "RimModManager"
    return (
        f"{normalized_base_url}/sub-browser-helper"
        f"?url={quote(normalized_url, safe='')}"
        f"&title={quote(helper_title, safe='')}"
    )


class WorkshopPageRenderer:
    def __init__(self, navigation_mode: str = "browser", browser_base_url: str = ""):
        self.navigation_mode = str(navigation_mode or "browser").strip().lower() or "browser"
        self.browser_base_url = str(browser_base_url or "").rstrip("/")

    @staticmethod
    def is_steamcommunity_url(target_url: str):
        try:
            parsed = urlparse(str(target_url or "").strip())
        except Exception:
            return False
        return parsed.scheme in {"http", "https"} and parsed.netloc.lower().endswith("steamcommunity.com")

    @staticmethod
    def extract_workshop_id(target_url: str):
        parsed = urlparse(str(target_url or "").strip())
        return str(parse_qs(parsed.query).get("id", [""])[0] or "").strip()

    def render(self, target_url: str):
        normalized_url = str(target_url or "").strip()
        if not normalized_url:
            return build_workshop_error_html("未提供目标工坊页面地址", "")
        if not self.is_steamcommunity_url(normalized_url):
            return build_workshop_error_html("当前仅代理 Steam 创意工坊相关页面", normalized_url)

        try:
            response = requests.get(
                normalized_url,
                timeout=REMOTE_FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": REMOTE_USER_AGENT},
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning(f"Workshop proxy fetch failed: {normalized_url} -> {exc}")
            return build_workshop_error_html(f"加载页面失败: {exc}", normalized_url)

        final_url = response.url or normalized_url
        soup = BeautifulSoup(response.text, "html.parser")
        self._sanitize_remote_soup(soup, final_url)
        page_title = str(soup.title.string).strip() if soup.title and soup.title.string else "Steam Workshop"

        head_html = soup.head.decode_contents() if soup.head else ""
        remote_body_html = soup.body.decode_contents() if soup.body else str(soup)
        bridge_script = self._build_bridge_script(final_url)
        combined_body = f"{self._build_toolbar_html(page_title, final_url)}<main class=\"rmm-proxy-page\">{remote_body_html}</main>"
        return build_workshop_page_html(page_title, final_url, head_html, combined_body, bridge_script)

    def _sanitize_remote_soup(self, soup: BeautifulSoup, base_url: str):
        for tag in soup.find_all("script"):
            tag.decompose()
        for tag in soup.find_all("noscript"):
            tag.decompose()
        for tag in soup.find_all("base"):
            tag.decompose()
        for tag in soup.find_all("meta"):
            http_equiv = str(tag.get("http-equiv") or "").strip().lower()
            if http_equiv in {"content-security-policy", "x-frame-options"}:
                tag.decompose()

        for tag in soup.find_all(True):
            for attr_name in list(tag.attrs.keys()):
                if str(attr_name).lower().startswith("on"):
                    tag.attrs.pop(attr_name, None)

        for tag in soup.find_all("a", href=True):
            href = str(tag.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "steam://")):
                continue
            absolute_url = urljoin(base_url, href)
            if self.is_steamcommunity_url(absolute_url):
                tag["href"] = absolute_url
                tag["data-rmm-proxy-url"] = absolute_url
            else:
                tag["href"] = absolute_url
                tag["target"] = "_blank"
                tag["rel"] = "noopener noreferrer"

        for tag_name, attr_name in (
            ("img", "src"),
            ("img", "data-src"),
            ("source", "src"),
            ("video", "src"),
            ("video", "poster"),
            ("audio", "src"),
            ("link", "href"),
            ("button", "formaction"),
            ("input", "formaction"),
            ("iframe", "src"),
        ):
            for tag in soup.find_all(tag_name):
                self._rewrite_resource_attr(tag, attr_name, base_url)

        for form in soup.find_all("form"):
            absolute_action = urljoin(base_url, str(form.get("action") or "").strip() or base_url)
            form["action"] = absolute_action
            if self.is_steamcommunity_url(absolute_action):
                form["data-rmm-proxy-form"] = absolute_action
                form["data-rmm-proxy-method"] = str(form.get("method") or "get").strip().lower() or "get"

        for tag in soup.find_all(["img", "source"]):
            self._rewrite_srcset(tag, "srcset", base_url)

    @staticmethod
    def _rewrite_resource_attr(tag, attr_name: str, base_url: str):
        attr_value = str(tag.get(attr_name) or "").strip()
        if not attr_value or attr_value.startswith(("data:", "javascript:", "#")):
            return
        tag[attr_name] = urljoin(base_url, attr_value)

    @staticmethod
    def _rewrite_srcset(tag, attr_name: str, base_url: str):
        raw_value = str(tag.get(attr_name) or "").strip()
        if not raw_value:
            return
        rewritten_parts = []
        for candidate in raw_value.split(","):
            token = candidate.strip()
            if not token:
                continue
            pieces = token.split()
            if not pieces:
                continue
            pieces[0] = urljoin(base_url, pieces[0])
            rewritten_parts.append(" ".join(pieces))
        if rewritten_parts:
            tag[attr_name] = ", ".join(rewritten_parts)

    def _build_toolbar_html(self, page_title: str, target_url: str):
        workshop_id = self.extract_workshop_id(target_url)
        safe_title = html.escape(page_title or "Steam Workshop")
        safe_url = html.escape(target_url or "")
        safe_workshop_id = html.escape(workshop_id or "未识别")
        return f"""
<section class="rmm-workshop-toolbar">
  <div class="rmm-toolbar-left">
    <div class="rmm-toolbar-badge">Workshop Browser</div>
    <div class="rmm-toolbar-title">{safe_title}</div>
    <div class="rmm-toolbar-url">{safe_url}</div>
  </div>
  <div class="rmm-toolbar-right">
    <div class="rmm-toolbar-id">Workshop ID: <strong>{safe_workshop_id}</strong></div>
    <div class="rmm-toolbar-actions">
      <button id="rmm-open-original" class="ghost">打开原网页</button>
      <button id="rmm-open-in-steam" class="ghost">在Steam打开</button>
      <button id="rmm-subscribe">订阅</button>
      <button id="rmm-unsubscribe" class="warn">取消订阅</button>
      <button id="rmm-download" class="secondary">SteamCMD 下载</button>
    </div>
    <div id="rmm-toolbar-status" class="rmm-toolbar-status"></div>
  </div>
</section>"""

    def _build_bridge_script(self, target_url: str):
        workshop_id = self.extract_workshop_id(target_url)
        js_target_url = json.dumps(target_url, ensure_ascii=False)
        js_workshop_id = json.dumps(workshop_id, ensure_ascii=False)
        js_navigation_mode = json.dumps(self.navigation_mode, ensure_ascii=False)
        js_proxy_base_url = json.dumps(self.browser_base_url, ensure_ascii=False)
        return f"""<script>
(() => {{
  const targetUrl = {js_target_url};
  const workshopId = {js_workshop_id};
  const navigationMode = {js_navigation_mode};
  const proxyBaseUrl = {js_proxy_base_url};
  const statusEl = document.getElementById('rmm-toolbar-status');
  const subscribeBtn = document.getElementById('rmm-subscribe');
  const unsubscribeBtn = document.getElementById('rmm-unsubscribe');
  const downloadBtn = document.getElementById('rmm-download');
  const openInSteamBtn = document.getElementById('rmm-open-in-steam');
  const openOriginalBtn = document.getElementById('rmm-open-original');

  const setStatus = (message, isError = false) => {{
    statusEl.textContent = message || '';
    statusEl.dataset.error = isError ? '1' : '0';
  }};

  const buildProxyUrl = (url) => {{
    if (!proxyBaseUrl) return url;
    return `${{proxyBaseUrl}}/workshop-view?url=${{encodeURIComponent(url)}}`;
  }};

  const waitForWebviewApi = async () => {{
    if (navigationMode !== 'webview') return null;
    const currentApi = window.pywebview?.api;
    if (currentApi) return currentApi;

    return await new Promise((resolve, reject) => {{
      const onReady = () => {{
        const readyApi = window.pywebview?.api;
        if (!readyApi) return;
        cleanup();
        resolve(readyApi);
      }};
      const cleanup = () => {{
        window.removeEventListener('pywebviewready', onReady);
        window.clearTimeout(timer);
      }};
      const timer = window.setTimeout(() => {{
        cleanup();
        reject(new Error('页面桥接尚未就绪，请稍后重试。'));
      }}, 2000);

      window.addEventListener('pywebviewready', onReady, {{ once: true }});
    }});
  }};

  const navigateTo = async (url) => {{
    if (!url) return;
    if (navigationMode === 'webview') {{
      const api = await waitForWebviewApi();
      if (!api?.workshop_browser_navigate) {{
        throw new Error('页面桥接尚未就绪，请稍后重试。');
      }}
      await api.workshop_browser_navigate(url);
      return;
    }}
    window.location.href = buildProxyUrl(url);
  }};

  const buildFormNavigation = (form, submitter) => {{
    const rawAction =
      submitter?.getAttribute('formaction') ||
      form.getAttribute('action') ||
      targetUrl ||
      window.location.href;
    const rawMethod =
      submitter?.getAttribute('formmethod') ||
      form.dataset.rmmProxyMethod ||
      form.getAttribute('method') ||
      'get';

    const method = String(rawMethod || 'get').trim().toLowerCase() || 'get';
    const nextUrl = new URL(rawAction, targetUrl || window.location.href);
    const formData = new FormData(form);

    if (submitter?.name) {{
      formData.append(submitter.name, submitter.value || '');
    }}

    if (method !== 'get') {{
      return {{ url: nextUrl.toString(), method }};
    }}

    for (const [key, value] of formData.entries()) {{
      if (value instanceof File) continue;
      nextUrl.searchParams.append(key, typeof value === 'string' ? value : String(value || ''));
    }}

    return {{ url: nextUrl.toString(), method }};
  }};

  const callAction = async (action) => {{
    if (navigationMode === 'webview') {{
      const api = await waitForWebviewApi();
      if (!api?.workshop_browser_action) {{
        throw new Error('页面桥接尚未就绪，请稍后重试。');
      }}
      return await api.workshop_browser_action(action, workshopId, targetUrl);
    }}

    const response = await fetch('/api/call/workshop_browser_action', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ args: [action, workshopId, targetUrl], kwargs: {{}} }}),
    }});
    const payload = await response.json();
    if (!response.ok || payload?.status === 'error') {{
      throw new Error(payload?.message || `Request failed: ${{response.status}}`);
    }}
    return payload;
  }};

  const withAction = async (pendingMessage, action) => {{
    try {{
      setStatus(pendingMessage);
      const payload = await callAction(action);
      setStatus(payload?.message || '操作已完成');
    }} catch (error) {{
      setStatus(error?.message || '操作失败', true);
    }}
  }};

  if (!workshopId) {{
    subscribeBtn.disabled = true;
    unsubscribeBtn.disabled = true;
    downloadBtn.disabled = true;
    openInSteamBtn.disabled = true;
    setStatus('当前页面未识别到 Workshop ID，可继续浏览其它工坊页面。');
  }}

  openOriginalBtn.addEventListener('click', () => {{
    if (!targetUrl) return;
    window.open(targetUrl, '_blank', 'noopener,noreferrer');
  }});
  openInSteamBtn.addEventListener('click', () => withAction('正在尝试在 Steam 中打开当前页面...', 'open_in_steam'));
  subscribeBtn.addEventListener('click', () => withAction('正在发送订阅请求...', 'subscribe'));
  unsubscribeBtn.addEventListener('click', () => withAction('正在发送取消订阅请求...', 'unsubscribe'));
  downloadBtn.addEventListener('click', () => withAction('正在启动 SteamCMD 下载...', 'download'));

  document.addEventListener('click', (event) => {{
    const anchor = event.target.closest('a[data-rmm-proxy-url]');
    if (!anchor) return;
    const nextUrl = anchor.dataset.rmmProxyUrl || '';
    if (!nextUrl) return;
    event.preventDefault();
    void navigateTo(nextUrl).catch((error) => {{
      setStatus(error?.message || '页面跳转失败', true);
    }});
  }}, true);

  document.addEventListener('submit', (event) => {{
    const form = event.target.closest('form[data-rmm-proxy-form]');
    if (!form) return;

    const navigation = buildFormNavigation(form, event.submitter || null);
    if (!navigation?.url) return;
    if (navigation.method !== 'get') {{
      setStatus('当前仅接管 GET 导航表单，已保留原页面行为。');
      return;
    }}

    event.preventDefault();
    void navigateTo(navigation.url).catch((error) => {{
      setStatus(error?.message || '页面跳转失败', true);
    }});
  }}, true);
}})();
</script>"""


class BrowserSessionManager:
    def __init__(self, on_shutdown):
        self._on_shutdown = on_shutdown
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._primary_session_id: str | None = None
        self._shutdown_deadline = 0.0
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    def start(self):
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop(self):
        self._stop_event.set()

    def open_session(self):
        session_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            self._sessions[session_id] = {"last_seen": now, "streams": set()}
            is_primary = False
            if self._primary_session_id is None or self._shutdown_deadline > 0:
                self._primary_session_id = session_id
                self._shutdown_deadline = 0.0
                is_primary = True
        return session_id, is_primary

    def heartbeat(self, session_id: str):
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session["last_seen"] = time.time()
            return True

    def close_session(self, session_id: str):
        should_schedule_shutdown = False
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return False
            if session_id == self._primary_session_id:
                should_schedule_shutdown = True
                self._shutdown_deadline = time.time() + PRIMARY_CLOSE_GRACE_SECONDS
        if should_schedule_shutdown:
            logger.info("Browser primary session closed, waiting for grace window before shutdown")
        return True

    def register_stream(self, session_id: str, stream_queue: queue.Queue):
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            session["streams"].add(stream_queue)
            return True

    def unregister_stream(self, session_id: str, stream_queue: queue.Queue):
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["streams"].discard(stream_queue)

    def broadcast(self, event_name: str, data: Any = None):
        with self._lock:
            queues = [stream_queue for session in self._sessions.values() for stream_queue in session["streams"]]

        payload = {"event": event_name, "data": data}
        for stream_queue in queues:
            try:
                stream_queue.put_nowait(payload)
            except Exception:
                pass

    def _monitor_loop(self):
        while not self._stop_event.wait(1.0):
            should_shutdown = False
            now = time.time()
            with self._lock:
                expired_ids = [
                    session_id
                    for session_id, session in self._sessions.items()
                    if now - float(session["last_seen"]) > SESSION_TTL_SECONDS
                ]
                for session_id in expired_ids:
                    self._sessions.pop(session_id, None)
                    if session_id == self._primary_session_id:
                        self._shutdown_deadline = now + PRIMARY_CLOSE_GRACE_SECONDS

                if self._shutdown_deadline > 0 and now >= self._shutdown_deadline:
                    should_shutdown = True
                    self._shutdown_deadline = 0.0

            if should_shutdown:
                logger.info("Browser primary session expired, requesting application shutdown")
                try:
                    self._on_shutdown()
                except Exception:
                    logger.error("Browser session shutdown callback failed", exc_info=True)
                return


class BrowserAppServer:
    def __init__(self, api, static_root: Path | None, use_dev_server: bool = False):
        self.api = api
        self.static_root = static_root
        self.use_dev_server = use_dev_server
        self._shutdown_event = threading.Event()
        self._serve_thread: threading.Thread | None = None
        self._session_manager = BrowserSessionManager(self.request_shutdown)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._create_handler())
        self.base_url = f"http://127.0.0.1:{self._httpd.server_address[1]}"

    @staticmethod
    def resolve_static_root():
        candidates = [Path(os.getcwd()) / "frontend" / "dist", Path(os.getcwd())]
        for root in candidates:
            if (root / "index.html").exists():
                return root
        return None

    @staticmethod
    def should_use_dev_server():
        return not getattr(__import__("sys"), "frozen", False) and is_port_available("localhost", 5173)

    def get_launch_url(self):
        api_base = quote(self.base_url, safe="")
        if self.use_dev_server:
            separator = "&" if "?" in DEV_SERVER_URL else "?"
            return f"{DEV_SERVER_URL}{separator}rmm_api_base={api_base}"
        return f"{self.base_url}/?rmm_api_base={api_base}"

    def get_available_methods(self):
        blocked = {"cleanup", "get_window", "set_window"}
        return sorted(
            name
            for name in dir(self.api)
            if not name.startswith("_") and name not in blocked and callable(getattr(self.api, name))
        )

    def start(self):
        self._session_manager.start()
        self._serve_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._serve_thread.start()
        logger.info(f"Browser server started at {self.base_url}")

    def stop(self):
        self._shutdown_event.set()
        self._session_manager.stop()
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        try:
            self._httpd.server_close()
        except Exception:
            pass

    def wait_for_shutdown(self):
        self._shutdown_event.wait()

    def request_shutdown(self):
        self._shutdown_event.set()

    def broadcast(self, event_name: str, data: Any = None):
        self._session_manager.broadcast(event_name, data)

    @staticmethod
    def is_steamcommunity_url(target_url: str):
        return WorkshopPageRenderer.is_steamcommunity_url(target_url)

    def _create_handler(self):
        outer = self

        class BrowserRequestHandler(BaseHTTPRequestHandler):
            server_version = "RimModManagerBrowser/1.0"

            def do_OPTIONS(self):
                self.send_response(204)
                self._send_common_headers()
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/meta":
                    return self._send_json({
                        "status": "success",
                        "data": {"runtime_mode": "browser", "available_methods": outer.get_available_methods()},
                    })
                if parsed.path == "/workshop-view":
                    return self._serve_workshop_view(parsed)
                if parsed.path == "/sub-browser-helper":
                    return self._serve_sub_browser_helper(parsed)
                if parsed.path == "/events":
                    return self._handle_events(parsed)
                return self._serve_static(parsed)

            def do_POST(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/session/open":
                    session_id, is_primary = outer._session_manager.open_session()
                    return self._send_json({"status": "success", "data": {"client_id": session_id, "is_primary": is_primary}})
                if parsed.path == "/api/session/heartbeat":
                    payload = self._read_json_body()
                    session_id = str(payload.get("client_id", "")).strip()
                    ok = outer._session_manager.heartbeat(session_id)
                    return self._send_json({"status": "success" if ok else "warning", "message": "" if ok else "Session not found"})
                if parsed.path == "/api/session/close":
                    payload = self._read_json_body()
                    session_id = str(payload.get("client_id", "")).strip()
                    outer._session_manager.close_session(session_id)
                    return self._send_json({"status": "success"})
                if parsed.path.startswith("/api/call/"):
                    method_name = unquote(parsed.path.removeprefix("/api/call/")).strip()
                    return self._handle_api_call(method_name)
                self.send_error(404, "Not Found")

            def log_message(self, format, *args):
                return

            def _handle_api_call(self, method_name: str):
                if method_name not in outer.get_available_methods():
                    return self._send_json({"status": "error", "message": f"Unknown API method: {method_name}"}, status_code=404)

                payload = self._read_json_body()
                args = payload.get("args", [])
                kwargs = payload.get("kwargs", {})
                method = getattr(outer.api, method_name)
                try:
                    result = method(*args, **kwargs)
                except Exception as exc:
                    logger.error(f"Browser API call failed: {method_name}", exc_info=True)
                    return self._send_json({"status": "error", "message": str(exc)}, status_code=500)

                if not isinstance(result, dict) or "status" not in result:
                    result = {"status": "success", "data": result}
                return self._send_json(result)

            def _handle_events(self, parsed):
                query = parse_qs(parsed.query)
                session_id = str(query.get("client_id", [""])[0]).strip()
                if not session_id:
                    return self._send_json({"status": "error", "message": "Missing client_id"}, status_code=400)

                stream_queue: queue.Queue = queue.Queue()
                if not outer._session_manager.register_stream(session_id, stream_queue):
                    return self._send_json({"status": "error", "message": "Session not found"}, status_code=404)

                self.send_response(200)
                self._send_common_headers(content_type="text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                try:
                    while not outer._shutdown_event.is_set():
                        try:
                            payload = stream_queue.get(timeout=1.0)
                            chunk = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
                        except queue.Empty:
                            chunk = b": keep-alive\n\n"
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        outer._session_manager.heartbeat(session_id)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    outer._session_manager.unregister_stream(session_id, stream_queue)

            def _serve_static(self, parsed):
                if outer.use_dev_server:
                    return self._send_json(
                        {"status": "error", "message": "Static assets are served by the frontend dev server in browser mode"},
                        status_code=404,
                    )

                if not outer.static_root:
                    return self._send_json({"status": "error", "message": "Frontend assets not found"}, status_code=500)

                request_path = parsed.path or "/"
                relative_path = request_path.lstrip("/")
                candidate = (outer.static_root / relative_path).resolve()
                root_resolved = outer.static_root.resolve()

                if request_path == "/" or not relative_path:
                    candidate = root_resolved / "index.html"

                if not str(candidate).startswith(str(root_resolved)):
                    self.send_error(403, "Forbidden")
                    return

                if candidate.is_dir():
                    candidate = candidate / "index.html"
                if not candidate.exists() or not candidate.is_file():
                    candidate = root_resolved / "index.html"

                content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
                with open(candidate, "rb") as file_handle:
                    content = file_handle.read()

                self.send_response(200)
                self._send_common_headers(content_type=content_type)
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)

            def _serve_sub_browser_helper(self, parsed):
                query = parse_qs(parsed.query)
                target_url = str(query.get("url", [""])[0] or "").strip()
                title = str(query.get("title", ["RimModManager"])[0] or "RimModManager").strip() or "RimModManager"
                body = build_sub_browser_helper_html(target_url, title).encode("utf-8")
                self.send_response(200)
                self._send_common_headers(content_type="text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def _serve_workshop_view(self, parsed):
                query = parse_qs(parsed.query)
                target_url = str(query.get("url", [""])[0] or "").strip()
                renderer = WorkshopPageRenderer(navigation_mode="browser", browser_base_url=outer.base_url)
                body = renderer.render(target_url).encode("utf-8")
                self.send_response(200)
                self._send_common_headers(content_type="text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def _read_json_body(self):
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                if content_length <= 0:
                    return {}
                raw_body = self.rfile.read(content_length)
                if not raw_body:
                    return {}
                try:
                    return json.loads(raw_body.decode("utf-8"))
                except Exception:
                    return {}

            def _send_common_headers(self, content_type="application/json; charset=utf-8"):
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

            def _send_json(self, payload, status_code=200):
                body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status_code)
                self._send_common_headers()
                self.end_headers()
                self.wfile.write(body)

        return BrowserRequestHandler
