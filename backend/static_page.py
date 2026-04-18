import html
import json


# backend/static_page.py
# 定义缓冲页面的 HTML (磨砂质感 + 呼吸灯动画)
LOADING_HTML = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {
            background-color: #0f172a;
            margin: 0; padding: 0;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            height: 100vh; overflow: hidden;
            font-family: 'Segoe UI', sans-serif;
            color: #06b6d4;
        }
        .loader {
            width: 60px; height: 60px;
            border: 3px solid rgba(6, 182, 212, 0.1);
            border-top: 3px solid #06b6d4;
            border-radius: 50%;
            animation: spin 1s cubic-bezier(0.4, 0, 0.2, 1) infinite;
            filter: drop-shadow(0 0 10px #06b6d4);
        }
        .text {
            margin-top: 20px;
            font-size: 12px;
            font-weight: bold;
            letter-spacing: 2px;
            text-transform: uppercase;
            animation: breathe 2s ease-in-out infinite;
            opacity: 0.8;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes breathe { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="loader"></div>
    <div class="text">Connecting to Webpage</div>
</body>
</html>
"""


IDLE_HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>RimModManager - 挂起中</title>
    <style>
        body {
            background-color: #0f172a; color: #475569; font-family: sans-serif;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            height: 100vh; margin: 0; user-select: none;
        }
        .status { margin: 0; vertical-align: middle; line-height: 1; color: #94a3b8; }
        .dot {
            width: 15px; height: 15px; margin-right: 12px; margin-top: 2px;
            background-color: #06b6d4; border-radius: 50%;
            animation: pulse 2s infinite; vertical-align: middle;
            box-shadow: 0 0 15px rgba(6, 182, 212, 0.6);
        }
        @keyframes pulse {
            0% { opacity: 0.4; transform: scale(0.8); }
            50% { opacity: 1; transform: scale(1.2); }
            100% { opacity: 0.4; transform: scale(0.8); }
        }
        /* 强制唤醒按钮样式 */
        .wake-btn {
            margin-top: 40px; padding: 10px 24px; border-radius: 8px;
            background: rgba(6, 182, 212, 0.1); border: 1px solid rgba(6, 182, 212, 0.3);
            color: #06b6d4; font-size: 14px; font-weight: bold; cursor: pointer;
            transition: all 0.3s; display: flex; align-items: center; gap: 8px;
        }
        .wake-btn:hover { background: rgba(6, 182, 212, 0.2); transform: translateY(-2px); }
        .wake-btn:active { transform: translateY(0); }
    </style>
</head>
<body>
    <div style="display: flex; align-items: center; margin: 10px;">
        <span class="dot"></span>
        <h1 class="status">RimWorld 正在运行</h1>
    </div>
    <h3 style="margin-top: 10px; opacity: 0.6; font-weight: normal;">管理器已释放内存并进入静默休眠状态。</h3>
    
    <button class="wake-btn" onclick="forceWake()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg>
        唤醒管理界面
    </button>

    <script>
        function forceWake() {
            if (window.pywebview && window.pywebview.api) {
                // 调用后端接口
                window.pywebview.api.monitor_force_wake();
                // 给用户一点点击反馈
                document.querySelector('.wake-btn').innerHTML = '正在建立连接...';
            } else {
                alert('API 未就绪，请重试');
            }
        }
    </script>
</body>
</html>
"""

def build_workshop_page_html(page_title: str, target_url: str, head_html: str, body_html: str, bridge_script: str) -> str:
    safe_title = html.escape(page_title or "Steam Workshop")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  {head_html}
  <style>
    :root {{
      --rmm-toolbar-bg: rgba(17, 24, 39, 0.96);
      --rmm-toolbar-line: rgba(255, 255, 255, 0.08);
      --rmm-toolbar-text: #f8fafc;
      --rmm-toolbar-dim: rgba(248, 250, 252, 0.72);
      --rmm-toolbar-accent: #38bdf8;
      --rmm-toolbar-danger: #f87171;
      --rmm-toolbar-ok: #34d399;
    }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      padding-top: 80px;
      background: #171717;
    }}
    .rmm-workshop-toolbar {{
      position: fixed;
      inset: 0 0 auto 0;
      z-index: 2147483647;
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      padding: 6px 12px;
      color: var(--rmm-toolbar-text);
      background:
        radial-gradient(circle at top right, rgba(56, 189, 248, 0.12), transparent 24%),
        linear-gradient(135deg, rgba(17, 24, 39, 0.98), var(--rmm-toolbar-bg));
      border-bottom: 1px solid var(--rmm-toolbar-line);
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.24);
      font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    }}
    .rmm-toolbar-left {{
      min-width: 0;
      flex: 1 1 auto;
    }}
    .rmm-toolbar-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 2px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--rmm-toolbar-accent);
    }}
    .rmm-toolbar-badge::before {{
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: currentColor;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.55);
    }}
    .rmm-toolbar-title {{
      font-size: 15px;
      font-weight: 800;
      line-height: 1.15;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .rmm-toolbar-url {{
      margin-top: 1px;
      font-size: 10px;
      font-family: Consolas, "Courier New", monospace;
      color: var(--rmm-toolbar-dim);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .rmm-toolbar-right {{
      display: grid;
      gap: 5px;
      min-width: 400px;
      max-width: 58vw;
      justify-items: end;
    }}
    .rmm-toolbar-id {{
      font-size: 10px;
      color: var(--rmm-toolbar-dim);
      text-align: right;
    }}
    .rmm-toolbar-actions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 6px;
    }}
    .rmm-toolbar-actions button {{
      border: 0;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      color: #03111a;
      background: var(--rmm-toolbar-accent);
      box-shadow: 0 6px 14px rgba(56, 189, 248, 0.22);
    }}
    .rmm-toolbar-actions button.secondary {{
      background: var(--rmm-toolbar-ok);
      box-shadow: 0 6px 14px rgba(52, 211, 153, 0.18);
    }}
    .rmm-toolbar-actions button.warn {{
      color: #fff;
      background: var(--rmm-toolbar-danger);
      box-shadow: 0 6px 14px rgba(248, 113, 113, 0.18);
    }}
    .rmm-toolbar-actions button.ghost {{
      color: var(--rmm-toolbar-text);
      background: rgba(255, 255, 255, 0.08);
      box-shadow: none;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .rmm-toolbar-actions button:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
      box-shadow: none;
    }}
    .rmm-toolbar-status {{
      min-height: 16px;
      font-size: 10px;
      color: var(--rmm-toolbar-dim);
      text-align: right;
    }}
    .rmm-toolbar-status[data-error="1"] {{
      color: #fca5a5;
    }}
    .rmm-proxy-page {{
      position: relative;
      z-index: 1;
    }}
    @media (max-width: 960px) {{
      body {{ padding-top: 120px; }}
      .rmm-workshop-toolbar {{
        align-items: flex-start;
        flex-direction: column;
      }}
      .rmm-toolbar-right {{
        min-width: 0;
        max-width: none;
        width: 100%;
        justify-items: start;
      }}
      .rmm-toolbar-id,
      .rmm-toolbar-status,
      .rmm-toolbar-actions {{
        text-align: left;
        justify-content: flex-start;
      }}
    }}
  </style>
</head>
<body>
  {body_html}
  {bridge_script}
</body>
</html>"""


def build_workshop_error_html(message: str, target_url: str) -> str:
    safe_message = html.escape(message or "加载失败")
    safe_url = html.escape(target_url or "")
    js_target_url = json.dumps(target_url or "", ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Workshop Browser</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: linear-gradient(160deg, #0f172a, #111827);
      color: #e5eefc;
      font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    }}
    .panel {{
      width: min(720px, calc(100vw - 32px));
      padding: 24px;
      border-radius: 18px;
      background: rgba(15, 23, 42, 0.88);
      border: 1px solid rgba(148, 163, 184, 0.2);
      box-shadow: 0 24px 54px rgba(0, 0, 0, 0.32);
    }}
    h1 {{ margin: 0 0 10px; font-size: 26px; }}
    p {{ margin: 0 0 12px; line-height: 1.7; color: rgba(226, 232, 240, 0.82); }}
    code {{
      display: block;
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 12px;
      background: rgba(2, 6, 23, 0.75);
      color: #93c5fd;
      word-break: break-all;
    }}
    button {{
      margin-top: 18px;
      border: 0;
      border-radius: 999px;
      padding: 10px 16px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      color: #03111a;
      background: #38bdf8;
    }}
  </style>
</head>
<body>
  <section class="panel">
    <h1>Workshop Browser</h1>
    <p>{safe_message}</p>
    <p>如果原网页能正常访问，可以直接打开原地址继续浏览。</p>
    <code>{safe_url or "未提供目标地址"}</code>
    <button id="open-original">打开原网页</button>
  </section>
  <script>
    const targetUrl = {js_target_url};
    document.getElementById('open-original').addEventListener('click', () => {{
      if (!targetUrl) return;
      window.open(targetUrl, '_blank', 'noopener,noreferrer');
    }});
  </script>
</body>
</html>"""


def build_sub_browser_helper_html(target_url: str, title: str) -> str:
    safe_title = html.escape(title or "RimModManager")
    safe_url = html.escape(target_url or "")
    js_target_url = json.dumps(target_url or "", ensure_ascii=False)
    js_title = json.dumps(title or "RimModManager", ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4efe7;
      --panel: rgba(255,255,255,0.88);
      --line: rgba(61, 44, 31, 0.12);
      --text: #24170f;
      --muted: #7b6657;
      --accent: #b4562d;
      --accent-2: #2f6a62;
      --danger: #a63f34;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top right, rgba(180, 86, 45, 0.2), transparent 28%),
        radial-gradient(circle at left bottom, rgba(47, 106, 98, 0.18), transparent 30%),
        linear-gradient(160deg, #f7f0e7 0%, #efe5d8 100%);
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 18px;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--panel);
      backdrop-filter: blur(14px);
      box-shadow: 0 18px 50px rgba(53, 33, 19, 0.12);
    }}
    .header {{
      padding: 18px;
      display: grid;
      gap: 10px;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--accent);
    }}
    .eyebrow::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: currentColor;
      box-shadow: 0 0 18px rgba(180, 86, 45, 0.55);
    }}
    h1 {{
      margin: 0;
      font-size: clamp(22px, 3vw, 32px);
      line-height: 1.05;
    }}
    .url {{
      font-family: Consolas, "Courier New", monospace;
      word-break: break-all;
      color: var(--muted);
      font-size: 12px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      color: #fff;
      background: var(--accent);
      box-shadow: 0 10px 24px rgba(180, 86, 45, 0.22);
    }}
    button.secondary {{
      background: var(--accent-2);
      box-shadow: 0 10px 24px rgba(47, 106, 98, 0.18);
    }}
    button.ghost {{
      color: var(--text);
      background: rgba(36, 23, 15, 0.08);
      box-shadow: none;
    }}
    button.warn {{
      background: var(--danger);
      box-shadow: 0 10px 24px rgba(166, 63, 52, 0.18);
    }}
    button:disabled {{
      cursor: not-allowed;
      opacity: 0.45;
      box-shadow: none;
    }}
    .status {{
      min-height: 18px;
      color: var(--muted);
      font-size: 12px;
    }}
    .preview {{
      margin-top: 14px;
      overflow: hidden;
    }}
    iframe {{
      width: 100%;
      height: min(70vh, 820px);
      border: 0;
      background: #fff;
    }}
    .footnote {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel header">
      <div class="eyebrow">Browser Helper</div>
      <h1>{safe_title}</h1>
      <div class="url">{safe_url or "未提供目标 URL"}</div>
      <div class="actions">
        <button id="open-original">打开原页面</button>
        <button id="open-in-steam" class="ghost">在Steam打开</button>
        <button id="subscribe" class="secondary">订阅</button>
        <button id="unsubscribe" class="warn">取消订阅</button>
        <button id="download" class="secondary">SteamCMD 下载</button>
      </div>
      <div id="status" class="status"></div>
      <div class="footnote">如果目标站点禁止 iframe 预览，下面区域会空白，但操作按钮仍可正常工作。</div>
    </section>
    <section class="panel preview">
      <iframe id="preview" referrerpolicy="no-referrer"></iframe>
    </section>
  </main>
  <script>
    const targetUrl = {js_target_url};
    const title = {js_title};
    const workshopMatch = targetUrl.match(/[?&]id=(\\d+)/);
    const workshopId = workshopMatch ? workshopMatch[1] : '';
    const statusEl = document.getElementById('status');
    const previewEl = document.getElementById('preview');
    const openOriginalBtn = document.getElementById('open-original');
    const subscribeBtn = document.getElementById('subscribe');
    const unsubscribeBtn = document.getElementById('unsubscribe');
    const downloadBtn = document.getElementById('download');
    const openInSteamBtn = document.getElementById('open-in-steam');

    const setStatus = (message, isError = false) => {{
      statusEl.textContent = message || '';
      statusEl.style.color = isError ? 'var(--danger)' : 'var(--muted)';
    }};

    const callApi = async (method, args = []) => {{
      const response = await fetch(`/api/call/${{encodeURIComponent(method)}}`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ args, kwargs: {{}} }}),
      }});
      const payload = await response.json();
      if (!response.ok || payload?.status === 'error') {{
        throw new Error(payload?.message || `Request failed: ${{response.status}}`);
      }}
      return payload;
    }};

    const withAction = async (message, action) => {{
      try {{
        setStatus(message);
        const payload = await action();
        setStatus(payload?.message || '操作已完成');
      }} catch (error) {{
        setStatus(error?.message || '操作失败', true);
      }}
    }};

    if (targetUrl) {{
      document.title = title;
      previewEl.src = targetUrl;
    }} else {{
      setStatus('未提供可打开的页面', true);
      openOriginalBtn.disabled = true;
    }}

    if (!workshopId) {{
      subscribeBtn.disabled = true;
      unsubscribeBtn.disabled = true;
      downloadBtn.disabled = true;
      openInSteamBtn.disabled = true;
      setStatus(targetUrl ? '未识别到 Workshop ID，仅保留打开页面。' : '未识别到可操作内容。');
    }}

    openOriginalBtn.addEventListener('click', () => {{
      if (!targetUrl) return;
      window.open(targetUrl, '_blank', 'noopener,noreferrer');
    }});
    openInSteamBtn.addEventListener('click', () => withAction('正在尝试在 Steam 中打开当前页面...', () => callApi('workshop_browser_action', ['open_in_steam', workshopId, targetUrl])));
    subscribeBtn.addEventListener('click', () => withAction('正在发送订阅请求...', () => callApi('workshop_browser_action', ['subscribe', workshopId, targetUrl])));
    unsubscribeBtn.addEventListener('click', () => withAction('正在发送取消订阅请求...', () => callApi('workshop_browser_action', ['unsubscribe', workshopId, targetUrl])));
    downloadBtn.addEventListener('click', () => withAction('正在启动 SteamCMD 下载...', () => callApi('workshop_browser_action', ['download', workshopId, targetUrl])));
  </script>
</body>
</html>"""

