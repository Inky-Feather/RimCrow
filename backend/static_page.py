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