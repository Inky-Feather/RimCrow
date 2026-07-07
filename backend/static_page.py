import html
import json

from backend.i18n.messages import tr


def _html_text(key: str, default: str, **params) -> str:
    return html.escape(str(tr(key, default, **params)))


def _plain_text(key: str, default: str, **params) -> str:
    return str(tr(key, default, **params))


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


def build_idle_home_html() -> str:
    """
    静默主页保持接近原样，只增加一个查看日志按钮。
    """
    title = _html_text("static.idle_home.title", "RimCrow - 挂起中")
    running = _html_text("static.idle_home.running", "RimWorld 正在运行")
    suspended = _html_text("static.idle_home.suspended", "管理器已释放内存并进入静默休眠状态。")
    view_logs = _html_text("static.idle_home.view_logs", "查看游戏日志")
    wake = _html_text("static.idle_home.wake", "退出静默")
    js_messages = json.dumps({
        "connecting": _plain_text("static.idle_home.connecting", "正在建立连接..."),
        "wake": _plain_text("static.idle_home.wake", "退出静默"),
        "retry": _plain_text("static.idle_home.retry", "请稍后重试"),
    }, ensure_ascii=False)
    return """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
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
        .actions {
            margin-top: 40px;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .action-btn {
            padding: 10px 20px; border-radius: 8px;
            background: rgba(6, 182, 212, 0.1); border: 1px solid rgba(6, 182, 212, 0.3);
            color: #06b6d4; font-size: 14px; font-weight: bold; cursor: pointer;
            transition: all 0.2s; display: flex; align-items: center; gap: 8px;
        }
        .action-btn:hover { background: rgba(6, 182, 212, 0.2); transform: translateY(-1px); }
        .action-btn:active { transform: translateY(0); }
    </style>
</head>
<body>
    <div style="display: flex; align-items: center; margin: 10px;">
        <span class="dot"></span>
        <h1 class="status">{running}</h1>
    </div>
    <h3 style="margin-top: 10px; opacity: 0.6; font-weight: normal;">{suspended}</h3>

    <div class="actions">
        <button class="action-btn" onclick="openLogPage()">{view_logs}</button>
        <button class="action-btn" id="wake-btn" onclick="forceWake()">{wake}</button>
    </div>

    <script>
        const I18N = {js_messages};
        function forceWake() {
            if (window.pywebview && window.pywebview.api) {
                const button = document.getElementById('wake-btn');
                button.innerText = I18N.connecting;
                button.disabled = true;
                window.pywebview.api.monitor_force_wake().catch(() => {
                    button.innerText = I18N.wake;
                    button.disabled = false;
                    alert(I18N.retry);
                });
            } else {
                alert(I18N.retry);
            }
        }
        function openLogPage() {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.monitor_open_silent_logs().catch(() => {
                    alert(I18N.retry);
                });
            } else {
                alert(I18N.retry);
            }
        }
    </script>
</body>
</html>
""".replace("{title}", title) \
        .replace("{running}", running) \
        .replace("{suspended}", suspended) \
        .replace("{view_logs}", view_logs) \
        .replace("{wake}", wake) \
        .replace("{js_messages}", js_messages)


def build_idle_logs_html(refresh_seconds: int = 2) -> str:
    """
    静默日志页使用紧凑布局，不引入无意义卡片和重装饰。
    """
    safe_refresh = max(1, int(refresh_seconds or 2))
    title = _html_text("static.idle_logs.title", "RimCrow - 游戏日志")
    page_title = _html_text("static.idle_logs.page_title", "游戏日志")
    search_placeholder = _html_text("static.idle_logs.search_placeholder", "搜索日志内容")
    refresh_seconds_label = _html_text("static.idle_logs.refresh_seconds", "刷新秒数")
    auto_refresh = _html_text("static.idle_logs.auto_refresh", "自动刷新")
    copy_selected = _html_text("static.idle_logs.copy_selected", "复制选中")
    back = _html_text("common.action.back", "返回")
    wake = _html_text("static.idle_home.wake", "退出静默")
    ready = _html_text("common.status.ready", "准备就绪")
    js_messages = json.dumps({
        "apiNotReady": _plain_text("static.idle_logs.api_not_ready", "接口尚未准备好"),
        "autoRefresh": _plain_text("static.idle_logs.auto_refresh", "自动刷新"),
        "paused": _plain_text("static.idle_logs.paused", "已暂停"),
        "emptyLogs": _plain_text("static.idle_logs.empty_logs", "当前没有可显示的日志。"),
        "collapseDetails": _plain_text("static.idle_logs.collapse_details", "收起详情"),
        "expandDetails": _plain_text("static.idle_logs.expand_details", "展开详情"),
        "copy": _plain_text("common.action.copy", "复制"),
        "copyCurrentSuccess": _plain_text("static.idle_logs.copy_current_success", "已复制当前日志"),
        "copyFailed": _plain_text("toast.common.copy_failed", "复制失败"),
        "loadFilesFailed": _plain_text("static.idle_logs.load_files_failed", "获取日志文件失败"),
        "noGameLogFiles": _plain_text("static.idle_logs.no_game_log_files", "当前未检测到游戏日志文件。"),
        "readingLogs": _plain_text("static.idle_logs.reading_logs", "正在读取日志..."),
        "readLogsFailed": _plain_text("static.idle_logs.read_logs_failed", "读取日志失败"),
        "refreshed": _plain_text("static.idle_logs.refreshed", "已刷新 {file}"),
        "backFailed": _plain_text("static.idle_logs.back_failed", "返回失败"),
        "connecting": _plain_text("static.idle_home.connecting", "正在建立连接..."),
        "wake": _plain_text("static.idle_home.wake", "退出静默"),
        "wakeFailed": _plain_text("static.idle_logs.wake_failed", "唤醒失败"),
        "refreshIntervalChanged": _plain_text("static.idle_logs.refresh_interval_changed", "刷新间隔已调整为 {seconds} 秒"),
        "autoRefreshResumed": _plain_text("static.idle_logs.auto_refresh_resumed", "已恢复自动刷新"),
        "autoRefreshPaused": _plain_text("static.idle_logs.auto_refresh_paused", "已暂停自动刷新"),
        "selectLogsFirst": _plain_text("static.idle_logs.select_logs_first", "请先选择日志"),
        "copyLogsSuccess": _plain_text("static.idle_logs.copy_logs_success", "已复制 {count} 条日志"),
        "loadFailed": _plain_text("static.idle_logs.load_failed", "加载失败"),
    }, ensure_ascii=False)
    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg: #0f172a;
            --bg-2: #111827;
            --line: rgba(148, 163, 184, 0.16);
            --line-strong: rgba(6, 182, 212, 0.32);
            --text: #e2e8f0;
            --text-dim: #94a3b8;
            --accent: #06b6d4;
            --error: #fb7185;
            --warn: #fbbf24;
            --ok: #34d399;
            --mono: Consolas, "Cascadia Code", "Microsoft YaHei UI", monospace;
        }}
        * {{
            box-sizing: border-box;
        }}
        html, body {{
            margin: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            background: linear-gradient(160deg, var(--bg) 0%, var(--bg-2) 100%);
            color: var(--text);
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
        }}
        button, input, select {{
            font: inherit;
        }}
        button {{
            cursor: pointer;
        }}
        .page {{
            display: grid;
            grid-template-rows: auto 1fr;
            width: 100%;
            height: 100%;
        }}
        .toolbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 10px 12px;
            border-bottom: 1px solid var(--line);
            background: rgba(2, 6, 23, 0.35);
        }}
        .toolbar-left,
        .toolbar-right {{
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
        }}
        .toolbar-left {{
            flex: 1;
        }}
        .title {{
            color: var(--text);
            font-size: 14px;
            font-weight: 700;
            white-space: nowrap;
        }}
        .meta {{
            color: var(--text-dim);
            font-size: 12px;
            white-space: nowrap;
        }}
        .toolbar select,
        .toolbar input {{
            height: 30px;
            padding: 0 8px;
            color: var(--text);
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid var(--line);
            outline: none;
        }}
        .toolbar input[type="number"] {{
            width: 64px;
        }}
        .toolbar input[type="text"] {{
            width: 220px;
        }}
        .tool-btn {{
            height: 30px;
            padding: 0 10px;
            border: 1px solid var(--line);
            background: rgba(15, 23, 42, 0.9);
            color: var(--text);
        }}
        .tool-btn:hover {{
            border-color: var(--line-strong);
            color: var(--accent);
        }}
        .tool-btn.primary {{
            color: var(--accent);
            border-color: rgba(6, 182, 212, 0.3);
        }}
        .tool-btn.active {{
            color: var(--ok);
            border-color: rgba(52, 211, 153, 0.3);
        }}
        .content {{
            min-height: 0;
            overflow: auto;
            padding: 8px 10px;
            font-family: var(--mono);
            user-select: text;
        }}
        .log-row {{
            display: grid;
            grid-template-columns: 24px 72px minmax(0, 1fr) auto;
            gap: 8px;
            align-items: start;
            padding: 4px 0;
            border-bottom: 1px solid rgba(148, 163, 184, 0.05);
            line-height: 1.6;
            font-size: 12px;
        }}
        .log-row.selected {{
            background: rgba(6, 182, 212, 0.08);
        }}
        .log-row input {{
            margin-top: 2px;
        }}
        .log-time {{
            color: var(--text-dim);
            white-space: nowrap;
        }}
        .log-main {{
            min-width: 0;
        }}
        .log-text {{
            min-width: 0;
            white-space: pre-wrap;
            word-break: break-word;
            color: var(--text);
        }}
        .log-actions {{
            display: flex;
            align-items: center;
            gap: 6px;
            padding-top: 1px;
        }}
        .inline-btn {{
            height: 24px;
            padding: 0 8px;
            border: 1px solid var(--line);
            background: rgba(15, 23, 42, 0.85);
            color: var(--text-dim);
            font-size: 11px;
            white-space: nowrap;
        }}
        .inline-btn:hover {{
            color: var(--accent);
            border-color: var(--line-strong);
        }}
        .log-details {{
            grid-column: 3 / 5;
            margin-top: -2px;
            padding: 6px 8px;
            border-left: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(2, 6, 23, 0.28);
            color: #cbd5e1;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .log-text.error {{
            color: var(--error);
        }}
        .log-text.warning {{
            color: var(--warn);
        }}
        .status {{
            padding: 4px 10px 0;
            color: var(--text-dim);
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="page">
        <div>
            <div class="toolbar">
                <div class="toolbar-left">
                    <span class="title">{page_title}</span>
                    <select id="file-select"></select>
                    <span class="meta" id="file-meta"></span>
                    <input id="search-input" type="text" placeholder="{search_placeholder}">
                </div>
                <div class="toolbar-right">
                    <span class="meta">{refresh_seconds_label}</span>
                    <input id="refresh-seconds" type="number" min="1" max="60" value="{safe_refresh}">
                    <button id="toggle-refresh" class="tool-btn active" type="button">{auto_refresh}</button>
                    <button id="copy-selected" class="tool-btn primary" type="button">{copy_selected}</button>
                    <button id="back-home" class="tool-btn" type="button">{back}</button>
                    <button id="wake-btn" class="tool-btn" type="button">{wake}</button>
                </div>
            </div>
            <div class="status" id="status-text">{ready}</div>
        </div>
        <div id="log-list" class="content"></div>
    </div>

    <script>
        const I18N = {js_messages};
        const formatMessage = (template, params = {{}}) => String(template || '').replace(/\\{{(\\w+)\\}}/g, (_, key) => params[key] ?? '');
        const REFRESH_DEFAULT = {safe_refresh};
        const state = {{
            files: [],
            selectedFile: '',
            logs: [],
            selectedIds: new Set(),
            refreshSeconds: REFRESH_DEFAULT,
            autoRefresh: true,
            timer: null,
            lastSignature: '',
            anchorIndex: -1,
            dragSelecting: false,
            shouldStickToBottom: true,
            expandedIds: new Set(),
            searchQuery: '',
        }};

        const fileSelect = document.getElementById('file-select');
        const fileMeta = document.getElementById('file-meta');
        const logList = document.getElementById('log-list');
        const statusText = document.getElementById('status-text');
        const searchInput = document.getElementById('search-input');
        const refreshInput = document.getElementById('refresh-seconds');
        const toggleRefresh = document.getElementById('toggle-refresh');
        const copySelected = document.getElementById('copy-selected');
        const backHome = document.getElementById('back-home');
        const wakeBtn = document.getElementById('wake-btn');

        function setStatus(text) {{
            statusText.textContent = text;
        }}

        function formatFileSize(bytes) {{
            const value = Number(bytes || 0);
            if (!value) return '0 B';
            if (value < 1024) return `${{value}} B`;
            if (value < 1024 * 1024) return `${{(value / 1024).toFixed(1)}} KB`;
            return `${{(value / 1024 / 1024).toFixed(1)}} MB`;
        }}

        function formatTime(value) {{
            if (!value) return '--:--:--';
            const text = String(value);
            return text.includes(' ') ? text.split(' ')[1] : text;
        }}

        function escapeHtml(text) {{
            return String(text || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }}

        function getLevelClass(block) {{
            const level = String(block.level || '').toUpperCase();
            if (level.includes('ERROR') || level.includes('EXCEPTION')) return 'error';
            if (level.includes('WARN')) return 'warning';
            return '';
        }}

        function getSignature(blocks) {{
            if (!Array.isArray(blocks) || !blocks.length) return '';
            const last = blocks[blocks.length - 1];
            return JSON.stringify([blocks.length, last.id || '', last.timestamp || '', last.count || 0]);
        }}

        async function waitForApi() {{
            if (window.pywebview && window.pywebview.api) return window.pywebview.api;
            return new Promise((resolve, reject) => {{
                const timer = setTimeout(() => reject(new Error(I18N.apiNotReady)), 15000);
                window.addEventListener('pywebviewready', () => {{
                    clearTimeout(timer);
                    resolve(window.pywebview.api);
                }}, {{ once: true }});
            }});
        }}

        function updateRefreshUi() {{
            toggleRefresh.classList.toggle('active', state.autoRefresh);
            toggleRefresh.textContent = state.autoRefresh ? I18N.autoRefresh : I18N.paused;
            refreshInput.value = String(state.refreshSeconds);
        }}

        function stopTimer() {{
            if (state.timer) {{
                clearInterval(state.timer);
                state.timer = null;
            }}
        }}

        function startTimer() {{
            stopTimer();
            if (!state.autoRefresh || !state.selectedFile) return;
            state.timer = setInterval(() => {{
                void loadLogs(false);
            }}, state.refreshSeconds * 1000);
        }}

        function isNearBottom() {{
            const remaining = logList.scrollHeight - logList.scrollTop - logList.clientHeight;
            return remaining <= 48;
        }}

        function syncStickToBottom() {{
            state.shouldStickToBottom = isNearBottom();
        }}

        function scrollToBottom() {{
            logList.scrollTop = logList.scrollHeight;
        }}

        function composeLogText(blocks) {{
            return blocks.map((block) => {{
                const parts = [];
                if (block.timestamp) parts.push(`[${{block.timestamp}}]`);
                if (block.level) parts.push(`[${{block.level}}]`);
                parts.push(block.message || '');
                if (block.details) parts.push(`\\n${{block.details}}`);
                return parts.join(' ');
            }}).join('\\n\\n------\\n\\n');
        }}

        function hasDetails(block) {{
            return Boolean((block.details || '').trim());
        }}

        function getSearchMatcher() {{
            const query = String(state.searchQuery || '').trim();
            if (!query) return null;
            try {{
                const regex = new RegExp(query, 'i');
                return (text) => regex.test(text);
            }} catch {{
                const lowered = query.toLowerCase();
                return (text) => String(text || '').toLowerCase().includes(lowered);
            }}
        }}

        function getVisibleLogs() {{
            const matcher = getSearchMatcher();
            if (!matcher) return state.logs;
            return state.logs.filter((block) => matcher(block.message || '') || matcher(block.details || ''));
        }}

        async function copyText(text) {{
            const value = String(text || '').trim();
            if (!value) return false;
            try {{
                await navigator.clipboard.writeText(value);
                return true;
            }} catch {{
                const textarea = document.createElement('textarea');
                textarea.value = value;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                const ok = document.execCommand('copy');
                document.body.removeChild(textarea);
                return ok;
            }}
        }}

        function renderFiles() {{
            fileSelect.innerHTML = '';
            state.files.forEach((file) => {{
                const option = document.createElement('option');
                option.value = file.name;
                option.textContent = file.name;
                if (file.name === state.selectedFile) option.selected = true;
                fileSelect.appendChild(option);
            }});
            const currentFile = state.files.find((item) => item.name === state.selectedFile);
            fileMeta.textContent = currentFile ? `${{currentFile.mtime}} · ${{formatFileSize(currentFile.size)}}` : '';
        }}

        function renderLogs(keepBottom = false) {{
            logList.innerHTML = '';
            const visibleLogs = getVisibleLogs();
            if (!visibleLogs.length) {{
                logList.innerHTML = `<div style="color:#94a3b8;padding:8px 0;">${{escapeHtml(I18N.emptyLogs)}}</div>`;
                return;
            }}

            const fragment = document.createDocumentFragment();
            visibleLogs.forEach((block, index) => {{
                const row = document.createElement('div');
                row.className = `log-row${{state.selectedIds.has(block.id) ? ' selected' : ''}}`;
                row.dataset.index = String(index);
                row.dataset.id = String(block.id || '');

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = state.selectedIds.has(block.id);
                checkbox.addEventListener('click', (event) => event.stopPropagation());
                checkbox.addEventListener('change', (event) => {{
                    toggleSelection(index, event.shiftKey, checkbox.checked);
                }});

                const time = document.createElement('div');
                time.className = 'log-time';
                time.textContent = formatTime(block.timestamp);

                const main = document.createElement('div');
                main.className = 'log-main';

                const text = document.createElement('div');
                text.className = `log-text ${{getLevelClass(block)}}`.trim();
                text.innerHTML = escapeHtml(block.message || '');
                main.appendChild(text);

                const actions = document.createElement('div');
                actions.className = 'log-actions';

                if (hasDetails(block)) {{
                    const detailBtn = document.createElement('button');
                    detailBtn.type = 'button';
                    detailBtn.className = 'inline-btn';
                    detailBtn.textContent = state.expandedIds.has(block.id) ? I18N.collapseDetails : I18N.expandDetails;
                    detailBtn.addEventListener('click', (event) => {{
                        event.stopPropagation();
                        toggleDetails(block.id);
                    }});
                    actions.appendChild(detailBtn);
                }}

                const copyOneBtn = document.createElement('button');
                copyOneBtn.type = 'button';
                copyOneBtn.className = 'inline-btn';
                copyOneBtn.textContent = I18N.copy;
                copyOneBtn.addEventListener('click', async (event) => {{
                    event.stopPropagation();
                    const ok = await copyText(composeLogText([block]));
                    setStatus(ok ? I18N.copyCurrentSuccess : I18N.copyFailed);
                }});
                actions.appendChild(copyOneBtn);

                row.appendChild(checkbox);
                row.appendChild(time);
                row.appendChild(main);
                row.appendChild(actions);

                row.addEventListener('click', (event) => {{
                    if (window.getSelection && String(window.getSelection()).trim()) return;
                    if (event.target === checkbox) return;
                    toggleSelection(index, event.shiftKey, !state.selectedIds.has(block.id));
                }});
                row.addEventListener('mousedown', (event) => {{
                    if (event.button !== 0) return;
                    state.dragSelecting = true;
                }});
                row.addEventListener('mouseenter', () => {{
                    if (!state.dragSelecting) return;
                    const currentId = state.logs[index]?.id;
                    if (currentId) {{
                        state.selectedIds.add(currentId);
                        row.classList.add('selected');
                        checkbox.checked = true;
                    }}
                }});

                fragment.appendChild(row);

                if (hasDetails(block) && state.expandedIds.has(block.id)) {{
                    const details = document.createElement('div');
                    details.className = `log-details ${{getLevelClass(block)}}`.trim();
                    details.textContent = block.details || '';
                    fragment.appendChild(details);
                }}
            }});
            logList.appendChild(fragment);
            if (keepBottom) {{
                scrollToBottom();
            }}
        }}

        function toggleDetails(blockId) {{
            if (!blockId) return;
            if (state.expandedIds.has(blockId)) state.expandedIds.delete(blockId);
            else state.expandedIds.add(blockId);
            renderLogs();
        }}

        function toggleSelection(index, useRange, checked) {{
            const visibleLogs = getVisibleLogs();
            const current = visibleLogs[index];
            if (!current) return;
            if (useRange && state.anchorIndex >= 0) {{
                const start = Math.min(state.anchorIndex, index);
                const end = Math.max(state.anchorIndex, index);
                for (let i = start; i <= end; i += 1) {{
                    const blockId = visibleLogs[i]?.id;
                    if (!blockId) continue;
                    if (checked) state.selectedIds.add(blockId);
                    else state.selectedIds.delete(blockId);
                }}
            }} else {{
                if (checked) state.selectedIds.add(current.id);
                else state.selectedIds.delete(current.id);
                state.anchorIndex = index;
            }}
            renderLogs();
        }}

        async function loadFiles() {{
            const api = await waitForApi();
            const res = await api.get_log_files('game', 'runtime');
            if (!res || res.status !== 'success') {{
                throw new Error(res?.message || I18N.loadFilesFailed);
            }}
            const rawFiles = Array.isArray(res.data) ? res.data : [];
            const preferredOrder = ['RimCrow_Realtime.log', 'Player.log'];
            state.files = preferredOrder
                .map((name) => rawFiles.find((file) => file.name === name))
                .filter(Boolean);
            if (!state.files.length) {{
                state.selectedFile = '';
                renderFiles();
                renderLogs();
                setStatus(I18N.noGameLogFiles);
                return;
            }}
            if (!state.selectedFile || !state.files.some((file) => file.name === state.selectedFile)) {{
                const preferred = state.files.find((file) => file.name === 'RimCrow_Realtime.log') || state.files[0];
                state.selectedFile = preferred.name;
            }}
            renderFiles();
        }}

        async function loadLogs(forceStatus = true) {{
            if (!state.selectedFile) return;
            if (forceStatus) setStatus(I18N.readingLogs);
            const api = await waitForApi();
            const res = await api.read_log_page('game', state.selectedFile, 1, 500, 'runtime');
            if (!res || res.status !== 'success') {{
                throw new Error(res?.message || I18N.readLogsFailed);
            }}
            const blocks = Array.isArray(res.data?.blocks) ? res.data.blocks : [];
            const signature = getSignature(blocks);
            const shouldStick = forceStatus ? true : state.shouldStickToBottom;
            if (signature !== state.lastSignature || forceStatus) {{
                state.logs = blocks;
                state.lastSignature = signature;
                state.selectedIds.clear();
                state.anchorIndex = -1;
                const nextExpanded = new Set();
                state.logs.forEach((block) => {{
                    if (state.expandedIds.has(block.id)) nextExpanded.add(block.id);
                }});
                state.expandedIds = nextExpanded;
                renderLogs(shouldStick);
            }}
            setStatus(formatMessage(I18N.refreshed, {{ file: state.selectedFile }}));
        }}

        async function reloadAll() {{
            await loadFiles();
            await loadLogs(true);
            startTimer();
        }}

        async function openHome() {{
            backHome.disabled = true;
            try {{
                const api = await waitForApi();
                await api.monitor_open_silent_home();
            }} catch (error) {{
                backHome.disabled = false;
                setStatus(error.message || I18N.backFailed);
            }}
        }}

        async function wakeMainUi() {{
            const api = await waitForApi();
            wakeBtn.textContent = I18N.connecting;
            wakeBtn.disabled = true;
            try {{
                await api.monitor_force_wake();
            }} catch (error) {{
                wakeBtn.textContent = I18N.wake;
                wakeBtn.disabled = false;
                setStatus(error.message || I18N.wakeFailed);
            }}
        }}

        fileSelect.addEventListener('change', async () => {{
            state.selectedFile = fileSelect.value;
            state.selectedIds.clear();
            state.expandedIds.clear();
            state.anchorIndex = -1;
            await loadLogs(true);
            startTimer();
        }});

        searchInput.addEventListener('input', () => {{
            state.searchQuery = searchInput.value || '';
            state.anchorIndex = -1;
            renderLogs();
        }});

        refreshInput.addEventListener('change', () => {{
            state.refreshSeconds = Math.max(1, Math.min(60, Number(refreshInput.value || REFRESH_DEFAULT)));
            updateRefreshUi();
            startTimer();
            setStatus(formatMessage(I18N.refreshIntervalChanged, {{ seconds: state.refreshSeconds }}));
        }});

        toggleRefresh.addEventListener('click', () => {{
            state.autoRefresh = !state.autoRefresh;
            updateRefreshUi();
            startTimer();
            setStatus(state.autoRefresh ? I18N.autoRefreshResumed : I18N.autoRefreshPaused);
        }});

        copySelected.addEventListener('click', async () => {{
            const blocks = state.logs.filter((block) => state.selectedIds.has(block.id));
            if (!blocks.length) {{
                setStatus(I18N.selectLogsFirst);
                return;
            }}
            const ok = await copyText(composeLogText(blocks));
            setStatus(ok ? formatMessage(I18N.copyLogsSuccess, {{ count: blocks.length }}) : I18N.copyFailed);
        }});

        backHome.addEventListener('click', () => {{
            void openHome();
        }});

        wakeBtn.addEventListener('click', () => {{
            void wakeMainUi();
        }});

        logList.addEventListener('mouseleave', () => {{
            state.dragSelecting = false;
        }});

        logList.addEventListener('scroll', () => {{
            syncStickToBottom();
        }});

        window.addEventListener('mouseup', () => {{
            state.dragSelecting = false;
        }});

        document.addEventListener('visibilitychange', () => {{
            if (document.hidden) stopTimer();
            else startTimer();
        }});

        updateRefreshUi();
        reloadAll().catch((error) => {{
            setStatus(error.message || I18N.loadFailed);
        }});
    </script>
</body>
</html>
"""


IDLE_HTML = build_idle_home_html()


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
      --rimcrow-toolbar-bg: rgba(17, 24, 39, 0.96);
      --rimcrow-toolbar-line: rgba(255, 255, 255, 0.08);
      --rimcrow-toolbar-text: #f8fafc;
      --rimcrow-toolbar-dim: rgba(248, 250, 252, 0.72);
      --rimcrow-toolbar-accent: #38bdf8;
      --rimcrow-toolbar-danger: #f87171;
      --rimcrow-toolbar-ok: #34d399;
    }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      padding-top: 80px;
      background: #171717;
    }}
    .rimcrow-workshop-toolbar {{
      position: fixed;
      inset: 0 0 auto 0;
      z-index: 2147483647;
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      padding: 6px 12px;
      color: var(--rimcrow-toolbar-text);
      background:
        radial-gradient(circle at top right, rgba(56, 189, 248, 0.12), transparent 24%),
        linear-gradient(135deg, rgba(17, 24, 39, 0.98), var(--rimcrow-toolbar-bg));
      border-bottom: 1px solid var(--rimcrow-toolbar-line);
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.24);
      font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    }}
    .rimcrow-toolbar-left {{
      min-width: 0;
      flex: 1 1 auto;
    }}
    .rimcrow-toolbar-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 2px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--rimcrow-toolbar-accent);
    }}
    .rimcrow-toolbar-badge::before {{
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: currentColor;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.55);
    }}
    .rimcrow-toolbar-title {{
      font-size: 15px;
      font-weight: 800;
      line-height: 1.15;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .rimcrow-toolbar-url {{
      margin-top: 1px;
      font-size: 10px;
      font-family: Consolas, "Courier New", monospace;
      color: var(--rimcrow-toolbar-dim);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .rimcrow-toolbar-right {{
      display: grid;
      gap: 5px;
      min-width: 400px;
      max-width: 58vw;
      justify-items: end;
    }}
    .rimcrow-toolbar-id {{
      font-size: 10px;
      color: var(--rimcrow-toolbar-dim);
      text-align: right;
    }}
    .rimcrow-toolbar-actions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 6px;
    }}
    .rimcrow-toolbar-actions button {{
      border: 0;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      color: #03111a;
      background: var(--rimcrow-toolbar-accent);
      box-shadow: 0 6px 14px rgba(56, 189, 248, 0.22);
    }}
    .rimcrow-toolbar-actions button.secondary {{
      background: var(--rimcrow-toolbar-ok);
      box-shadow: 0 6px 14px rgba(52, 211, 153, 0.18);
    }}
    .rimcrow-toolbar-actions button.warn {{
      color: #fff;
      background: var(--rimcrow-toolbar-danger);
      box-shadow: 0 6px 14px rgba(248, 113, 113, 0.18);
    }}
    .rimcrow-toolbar-actions button.ghost {{
      color: var(--rimcrow-toolbar-text);
      background: rgba(255, 255, 255, 0.08);
      box-shadow: none;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .rimcrow-toolbar-actions button:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
      box-shadow: none;
    }}
    .rimcrow-toolbar-status {{
      min-height: 16px;
      font-size: 10px;
      color: var(--rimcrow-toolbar-dim);
      text-align: right;
    }}
    .rimcrow-toolbar-status[data-error="1"] {{
      color: #fca5a5;
    }}
    .rimcrow-proxy-page {{
      position: relative;
      z-index: 1;
    }}
    @media (max-width: 960px) {{
      body {{ padding-top: 120px; }}
      .rimcrow-workshop-toolbar {{
        align-items: flex-start;
        flex-direction: column;
      }}
      .rimcrow-toolbar-right {{
        min-width: 0;
        max-width: none;
        width: 100%;
        justify-items: start;
      }}
      .rimcrow-toolbar-id,
      .rimcrow-toolbar-status,
      .rimcrow-toolbar-actions {{
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
    safe_message = html.escape(message or _plain_text("browser.workshop.error.load_failed_short", "加载失败"))
    safe_url = html.escape(target_url or "")
    fallback_url = _html_text("browser.workshop.error.missing_target_url", "未提供目标地址")
    original_tip = _html_text("browser.workshop.error.open_original_tip", "如果原网页能正常访问，可以直接打开原地址继续浏览。")
    open_original = _html_text("browser.workshop.toolbar.open_original", "打开原网页")
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
    <p>{original_tip}</p>
    <code>{safe_url or fallback_url}</code>
    <button id="open-original">{open_original}</button>
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
    safe_title = html.escape(title or "RimCrow")
    safe_url = html.escape(target_url or "")
    js_target_url = json.dumps(target_url or "", ensure_ascii=False)
    js_title = json.dumps(title or "RimCrow", ensure_ascii=False)
    fallback_url = _html_text("browser.helper.missing_target_url", "未提供目标 URL")
    open_original = _html_text("browser.helper.open_original", "打开原页面")
    open_in_steam = _html_text("browser.workshop.toolbar.open_in_steam", "在 Steam 打开")
    subscribe = _html_text("browser.workshop.toolbar.subscribe", "订阅")
    unsubscribe = _html_text("browser.workshop.toolbar.unsubscribe", "取消订阅")
    download = _html_text("browser.workshop.toolbar.download", "SteamCMD 下载")
    footnote = _html_text("browser.helper.iframe_footnote", "如果目标站点禁止 iframe 预览，下面区域会空白，但操作按钮仍可正常工作。")
    js_messages = json.dumps({
        "requestUnfinished": _plain_text("browser.helper.request_unfinished", "请求未完成，状态码：{status}。请检查后端服务是否仍在运行。"),
        "actionDone": _plain_text("browser.workshop.script.action_done", "操作已完成"),
        "actionFailed": _plain_text("browser.workshop.script.action_failed", "操作失败"),
        "missingPage": _plain_text("browser.helper.missing_page", "未提供可打开的页面"),
        "idMissingWithUrl": _plain_text("browser.helper.id_missing_with_url", "未识别到 Workshop ID，仅保留打开页面。"),
        "idMissing": _plain_text("browser.helper.id_missing", "未识别到可操作内容。"),
        "openingSteam": _plain_text("browser.workshop.script.opening_steam", "正在尝试在 Steam 中打开当前页面..."),
        "subscribing": _plain_text("browser.workshop.script.subscribing", "正在发送订阅请求..."),
        "unsubscribing": _plain_text("browser.workshop.script.unsubscribing", "正在发送取消订阅请求..."),
        "downloading": _plain_text("browser.workshop.script.downloading", "正在启动 SteamCMD 下载..."),
    }, ensure_ascii=False)
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
      <div class="url">{safe_url or fallback_url}</div>
      <div class="actions">
        <button id="open-original">{open_original}</button>
        <button id="open-in-steam" class="ghost">{open_in_steam}</button>
        <button id="subscribe" class="secondary">{subscribe}</button>
        <button id="unsubscribe" class="warn">{unsubscribe}</button>
        <button id="download" class="secondary">{download}</button>
      </div>
      <div id="status" class="status"></div>
      <div class="footnote">{footnote}</div>
    </section>
    <section class="panel preview">
      <iframe id="preview" referrerpolicy="no-referrer"></iframe>
    </section>
  </main>
  <script>
    const I18N = {js_messages};
    const formatMessage = (template, params = {{}}) => String(template || '').replace(/\{{(\w+)\}}/g, (_, key) => params[key] ?? '');
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
        throw new Error(payload?.message || formatMessage(I18N.requestUnfinished, {{ status: response.status }}));
      }}
      return payload;
    }};

    const withAction = async (message, action) => {{
      try {{
        setStatus(message);
        const payload = await action();
        setStatus(payload?.message || I18N.actionDone);
      }} catch (error) {{
        setStatus(error?.message || I18N.actionFailed, true);
      }}
    }};

    if (targetUrl) {{
      document.title = title;
      previewEl.src = targetUrl;
    }} else {{
      setStatus(I18N.missingPage, true);
      openOriginalBtn.disabled = true;
    }}

    if (!workshopId) {{
      subscribeBtn.disabled = true;
      unsubscribeBtn.disabled = true;
      downloadBtn.disabled = true;
      openInSteamBtn.disabled = true;
      setStatus(targetUrl ? I18N.idMissingWithUrl : I18N.idMissing);
    }}

    openOriginalBtn.addEventListener('click', () => {{
      if (!targetUrl) return;
      window.open(targetUrl, '_blank', 'noopener,noreferrer');
    }});
    openInSteamBtn.addEventListener('click', () => withAction(I18N.openingSteam, () => callApi('workshop_browser_action', ['open_in_steam', workshopId, targetUrl])));
    subscribeBtn.addEventListener('click', () => withAction(I18N.subscribing, () => callApi('workshop_browser_action', ['subscribe', workshopId, targetUrl])));
    unsubscribeBtn.addEventListener('click', () => withAction(I18N.unsubscribing, () => callApi('workshop_browser_action', ['unsubscribe', workshopId, targetUrl])));
    downloadBtn.addEventListener('click', () => withAction(I18N.downloading, () => callApi('workshop_browser_action', ['download', workshopId, targetUrl])));
  </script>
</body>
</html>"""
