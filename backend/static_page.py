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
            background-color: #0f172a; /* 保持深色背景 */
            color: #475569;
            font-family: sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            user-select: none;
        }
        .status {  margin: 0; vertical-align: middle; line-height: 1;}
        /* 简单的呼吸动画 */
        .dot {
            width: 15px; height: 15px; margin-right: 8px; margin-top: 5px;
            background-color: #06b6d4; /* accent-primary */
            border-radius: 50%;
            animation: pulse 2s infinite;
            vertical-align: middle;
        }
        @keyframes pulse {
            0% { opacity: 0.2; transform: scale(0.8); }
            50% { opacity: 1; transform: scale(1.2); }
            100% { opacity: 0.2; transform: scale(0.8); }
        }
    </style>
</head>
<body>
    <div style="display: flex; align-items: center; margin: 10px;">
        <span class="dot"></span>
        <h1 class="status">游戏运行中...</h1>
    </div>
    <h2 style="margin-top: 5px; opacity: 0.5">管理器进入静默状态降低内存占用，资源已释放……</h2>
</body>
</html>
"""