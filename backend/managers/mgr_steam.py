# backend/managers/mgr_steam.py
import os
import re
import sys
import platform
import subprocess
import threading
import time
import shutil
import importlib.util
from typing import Optional
from backend.utils.logger import logger

# 注意：不要在文件顶层 import steamworks，防止主进程意外加载
# 只在 run_steam_worker 函数内部 import

from backend.utils.logger import logger
from backend.settings import settings
from backend.utils.event_bus import EventBus
from backend.managers.mgr_download import TaskStatus

# RimWorld App ID
RIMWORLD_APP_ID = "294100"

# =========================================================
#  独立 Worker 函数 (由 main.py 在子进程调用)
# =========================================================
def run_steam_worker(action: str, mod_id: int):
    """
    这是在一个独立的、短命的进程中运行的。
    它负责初始化 SteamAPI，执行操作，然后结束。
    """
    try:
        # 在这里才导入库，确保主进程干净
        from steamworks.steamworks import STEAMWORKS
    except ImportError:
        logger.error("ERROR: steamworks-py not found in bundle")
        return

    # 这里的 cwd 已经被主进程设置为了 tools/steam_agent
    # 所以直接初始化即可读取到旁边的 steam_appid.txt 和 DLL
    try:
        steam = STEAMWORKS()
        steam.initialize()
    except Exception as e:
        logger.error(f"ERROR: Steam init failed: {e}")
        return

    if not steam:
        logger.error("ERROR: Steam API not loaded")
        return

    # 定义回调
    def callback(res):
        logger.info(f"Callback: {res}")

    success = False
    try:
        if action == "subscribe":
            steam.Workshop.SubscribeItem(mod_id, callback)
            success = True
            logger.info("SUCCESS: Subscription request sent")
        elif action == "unsubscribe":
            steam.Workshop.UnsubscribeItem(mod_id, callback)
            success = True
            logger.info("SUCCESS: Unsubscription request sent")
        else:
            logger.error(f"ERROR: Unknown action {action}")
    except Exception as e:
        logger.error(f"ERROR: Action failed: {e}")

    # 给 Steam 客户端一点时间处理请求
    if success:
        # 必须稍作等待，让 Steam 客户端接收到 IPC 消息
        time.sleep(1)


class SteamManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SteamManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True

        self.project_root = os.getcwd()
        self.tools_dir = os.path.join(self.project_root, "tools")
        
        # SteamCMD 路径
        self.steamcmd_dir = os.path.join(self.tools_dir, "steamcmd")
        self.steamcmd_exe = self._get_steamcmd_exe_path()
        
        # Steam Agent 路径 (隔离环境)
        self.agent_dir = os.path.join(self.tools_dir, "steam_agent")
        
        # 确保目录存在
        os.makedirs(self.steamcmd_dir, exist_ok=True)
        os.makedirs(self.agent_dir, exist_ok=True)
        
        # 状态
        self.steamcmd_ready = os.path.exists(self.steamcmd_exe)
        
        # 准备环境 (只复制 DLL 和 txt，不再生成 py 脚本)
        self._ensure_agent_environment()

    def _get_steamcmd_exe_path(self):
        system = platform.system()
        if system == "Windows":
            return os.path.join(self.steamcmd_dir, "steamcmd.exe")
        elif system == "Linux": # Linux/Mac 逻辑保持不变
            return os.path.join(self.steamcmd_dir, "steamcmd.sh")
        elif system == "Darwin":
            return os.path.join(self.steamcmd_dir, "steamcmd.sh")
        return ""

    # =========================================================
    #  1. 环境准备
    # =========================================================

    def _ensure_agent_environment(self):
        """
        初始化 Agent 环境：
        1. 写入 steam_appid.txt
        2. 写入 steam_worker.py (从字符串生成)
        3. 复制 DLLs
        """
        # 1. 创建 steam_appid.txt
        appid_path = os.path.join(self.agent_dir, "steam_appid.txt")
        if not os.path.exists(appid_path):
            with open(appid_path, "w") as f:
                f.write(RIMWORLD_APP_ID)

        # 2. 检查并复制 DLL (逻辑同上一次修改，保持不变)
        target_dll = "SteamworksPy64.dll" if platform.system() == "Windows" else "libSteamworksPy.so"
        target_api = "steam_api64.dll" if platform.system() == "Windows" else "libsteam_api.so"
        
        dst_dll = os.path.join(self.agent_dir, target_dll)
        dst_api = os.path.join(self.agent_dir, target_api)

        # 如果目标不存在，或者处于开发环境(可能DLL更新了)，尝试复制
        # 这里简单判断不存在则复制
        if not os.path.exists(dst_dll) or not os.path.exists(dst_api):
            logger.info("Initializing Steam Agent DLLs...")
            self._copy_dlls_to_agent(target_dll, target_api)

    def _copy_dlls_to_agent(self, dll_name, api_name):
        """
        在开发环境和打包环境中查找并复制 DLL
        """
        search_dirs = []
        # 1. 确定搜索路径列表
        if getattr(sys, 'frozen', False):
            # === 打包环境 (PyInstaller) ===
            # sys.executable: exe 文件所在目录
            exe_dir = os.path.dirname(sys.executable)
            # sys._MEIPASS: PyInstaller 解压临时目录
            base_dir = getattr(sys, '_MEIPASS', exe_dir)
            # 添加可能的搜索位置：
            # A. _MEIPASS 根目录 (如果 spec 文件配置为 binary 放在根目录)
            search_dirs.append(base_dir)
            # B. _MEIPASS/steamworks (如果使用了 collect_all 或 add_data 保持了目录结构)
            search_dirs.append(os.path.join(base_dir, "steamworks"))
            # C. EXE 同级目录 (用户手动放置 DLL 作为补救)
            search_dirs.append(exe_dir)
        else:
            # === 开发环境 ===
            try:
                spec = importlib.util.find_spec("steamworks")
                if spec and spec.origin:
                    search_dirs.append(os.path.dirname(spec.origin))
            except: pass
            search_dirs.append(self.project_root)

        # 2. 遍历查找并复制
        for name in [dll_name, api_name]:
            found = False
            for directory in search_dirs:
                src = os.path.join(directory, name)
                if os.path.exists(src):
                    try:
                        shutil.copy2(src, os.path.join(self.agent_dir, name))
                        logger.info(f"Copied {name} from {directory}")
                        found = True
                        break # 找到了就停止当前文件的搜索，处理下一个文件
                    except Exception as e:
                        logger.error(f"Copy error: {e}")
            if not found:
                logger.warning(f"Could not find {name} in search paths: {search_dirs}")

    def ensure_tools(self, download_mgr):
        """前端调用的检查接口 (只查 SteamCMD 即可，Agent DLL 自动处理)"""
        tasks = []
        if not os.path.exists(self.steamcmd_exe):
            logger.info("SteamCMD not found, adding download task...")
            url = ""
            if platform.system() == "Windows":
                url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
            elif platform.system() == "Darwin":
                url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz"
            else:
                url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
            
            tid = download_mgr.add_task(url, self.steamcmd_dir, "steamcmd_package.zip")
            tasks.append({"type": "steamcmd", "id": tid})
        return tasks
        
    def post_download_setup(self, task_type, file_path):
        """下载完成后的解压/配置回调"""
        if task_type == "steamcmd":
             try:
                import zipfile
                if file_path.endswith('.zip'):
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(self.steamcmd_dir)
                    os.remove(file_path)
                    self.steamcmd_ready = True
                    logger.info("SteamCMD installed.")
             except Exception as e:
                logger.error(f"Failed to extract SteamCMD: {e}")

    # =========================================================
    #  2. SteamCMD 功能
    # =========================================================
    def download_workshop_items(self, mod_ids: list):
        EventBus.resume()   # 恢复事件总线
        if not self.steamcmd_ready:
            raise Exception("SteamCMD is not installed.")
        
        commands = ["login anonymous"]
        for mid in mod_ids:
            commands.append(f"workshop_download_item {RIMWORLD_APP_ID} {mid}")
        commands.append("quit")
        
        t = threading.Thread(target=self._run_steamcmd_process, args=(commands, mod_ids))
        t.start()
        return t

    def _run_steamcmd_process(self, commands, mod_ids):
        fake_task_id = "steamcmd_batch_" + str(time.time_ns() // 1000000)
        self._emit_progress(fake_task_id, "Connecting to Steam...", 0, TaskStatus.RUNNING)

        try:
            args = [self.steamcmd_exe]
            for cmd in commands:
                args.append(f"+{cmd}")
            
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                cwd=self.steamcmd_dir
            )

            progress_pattern = re.compile(r"progress: (\d+\.\d+)")
            success_pattern = re.compile(r"Success\. Downloaded item (\d+)")

            current_item_idx = 0
            total_items = len(mod_ids)
            
            while True:
                line = process.stdout.readline() # type: ignore
                if not line and process.poll() is not None:
                    break
                if not line: continue
                line = line.strip()

                match = progress_pattern.search(line)
                if match:
                    percent = float(match.group(1))
                    total_percent = ((current_item_idx + percent / 100) / total_items) * 100
                    self._emit_progress(fake_task_id, f"Downloading item {current_item_idx+1}/{total_items}", int(total_percent), TaskStatus.RUNNING)

                if success_pattern.search(line):
                    current_item_idx += 1
                    logger.info(f"SteamCMD finished one item. ({current_item_idx}/{total_items})")

            if process.returncode == 0:
                self._emit_progress(fake_task_id, "All downloads completed", 100, TaskStatus.COMPLETED)
            else:
                self._emit_progress(fake_task_id, f"SteamCMD exited with code {process.returncode}", 0, TaskStatus.ERROR)

        except Exception as e:
            logger.error(f"SteamCMD execution failed: {e}")
            self._emit_progress(fake_task_id, str(e), 0, TaskStatus.ERROR)

    def _emit_progress(self, tid, msg, percent, status):
        EventBus.emit("download-progress", {
            "id": tid,
            "filename": msg,
            "status": status.value,
            "percent": percent,
            "speed": "SteamCMD",
            "total": 100,
            "current": percent
        })
    # =========================================================
    #  3. 自我调用 (Re-entry) 逻辑
    # =========================================================

    def _run_agent(self, action: str, mod_id: int) -> bool:
        """
        调用自身 EXE 作为 Worker
        """
        # 获取当前运行的可执行文件路径
        # 在打包环境中，这是 .exe 的路径
        # 在开发环境中，这是 python.exe 的路径
        current_exe = sys.executable
        
        # 构造命令: [exe, "--steam-worker", action, mod_id]
        cmd = [current_exe]
        
        # 开发环境需要补上 main.py
        if not getattr(sys, 'frozen', False):
            # 获取 main.py 的绝对路径
            main_script = os.path.join(self.project_root, "main.py")
            cmd.append(main_script)
            
        cmd.extend(["--steam-worker", action, str(mod_id)])
        
        try:
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # 关键：cwd 必须设为 agent_dir，这样子进程初始化 Steamworks 时
            # 才能读取到该目录下的 steam_appid.txt 和 DLL
            result = subprocess.run(
                cmd,
                cwd=self.agent_dir,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                encoding='utf-8'
            )
            
            stdout = result.stdout
            if "SUCCESS" in stdout:
                logger.info(f"Agent {action} success: {mod_id}")
                return True
            else:
                logger.error(f"Agent failed. STDOUT: {stdout} \nSTDERR: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to run steam agent: {e}")
            return False

    def subscribe_item(self, published_file_id: int):
        return self._run_agent("subscribe", published_file_id)

    def unsubscribe_item(self, published_file_id: int):
        return self._run_agent("unsubscribe", published_file_id)

    def _get_acf_path(self):
        """获取 appworkshop_294100.acf 的路径"""
        # 依赖 settings 中的 workshop_mods_path
        # 典型路径: .../steamapps/workshop/content/294100
        # ACF 路径: .../steamapps/workshop/appworkshop_294100.acf
        ws_path = settings.config.workshop_mods_path
        if not ws_path or not os.path.exists(ws_path):
            return None
        
        try:
            # 回退两级找到 workshop 目录
            workshop_root = os.path.dirname(os.path.dirname(ws_path))
            acf_file = os.path.join(workshop_root, f"appworkshop_{RIMWORLD_APP_ID}.acf")
            if os.path.exists(acf_file):
                return acf_file
        except:
            pass
        return None

    def get_installed_workshop_ids(self) -> set:
        """
        解析 ACF 文件，获取所有已安装的 Workshop Mod ID
        返回: set(int)
        """
        acf_path = self._get_acf_path()
        if not acf_path:
            return set()

        installed_ids = set()
        try:
            with open(acf_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # VDF 格式解析
            # 结构: "WorkshopItemsInstalled" { "123" { ... } "456" { ... } }
            # 我们只需要提取 "WorkshopItemsInstalled" 块里的 Key
            
            # 1. 找到 WorkshopItemsInstalled 块
            # 使用简单的字符串查找或者正则
            # 正则非贪婪匹配块内容
            block_match = re.search(r'"WorkshopItemsInstalled"\s*\{(.*?)\}', content, re.DOTALL)
            if block_match:
                block_content = block_match.group(1)
                # 2. 提取所有 ID (即块中的键)
                # 格式: "ModID" { ... }
                ids = re.findall(r'"(\d+)"\s*\{', block_content)
                for i in ids:
                    installed_ids.add(int(i))
                    
        except Exception as e:
            logger.error(f"Failed to parse ACF for validation: {e}")
            
        return installed_ids

    def is_subscribed(self, published_file_id: int) -> bool:
        """
        检查是否已订阅且已安装 (通过本地 ACF 文件验证)
        这是最快且最准确的方法
        """
        # 注意：这里判断的是“本地已安装”，Steam 客户端认为“下载完”才算安装。
        # 如果只是点了订阅但还没下载完，这里会返回 False。
        # 这其实更符合用户的期望：只有下载完了才能用。
        ids = self.get_installed_workshop_ids()
        return int(published_file_id) in ids