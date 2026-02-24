# backend/managers/mgr_steam.py
import os
import re
import sys
import platform
import winreg
import subprocess
import threading
import time
import shutil
import importlib.util
from typing import Optional, cast

from json_repair import repair_json
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
    def download_workshop_items(self, workshop_ids: list):
        EventBus.resume()   # 恢复事件总线
        if not self.steamcmd_ready:
            raise Exception("SteamCMD is not installed.")
        
        commands = ["login anonymous"]
        for mid in workshop_ids:
            commands.append(f"workshop_download_item {RIMWORLD_APP_ID} {mid}")
        commands.append("quit")
        
        t = threading.Thread(target=self._run_steamcmd_process, args=(commands, workshop_ids))
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
        """订阅 Workshop Mod"""
        return self._run_agent("subscribe", published_file_id)

    def unsubscribe_item(self, published_file_id: int):
        """取消订阅 Workshop Mod"""
        return self._run_agent("unsubscribe", published_file_id)


    # =========================================================
    #  4. Steam本体操作
    # =========================================================
    
    def get_steam_path(self):
        """从注册表获取 Steam 安装路径"""
        try:
            # 尝试读取 64位 注册表
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            return os.path.join(path, "steam.exe")
        except:
            try:
                # 尝试读取 32位 注册表
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
                path, _ = winreg.QueryValueEx(key, "InstallPath")
                return os.path.join(path, "steam.exe")
            except:
                return None

    def launch_via_steam_cmd(self, app_id=RIMWORLD_APP_ID, extra_args=None):
        steam_exe = settings.config.steam_exe_path or self.get_steam_path()
        # 如果找不到 Steam.exe，回退到原来的 URL 方式
        if not steam_exe or not os.path.exists(steam_exe):
            steam_exe = self.get_steam_path()
            if not steam_exe or not os.path.exists(steam_exe):
                logger.warning("未找到 Steam.exe，回退到 URL 协议启动")
                # os.startfile(f"steam://rungameid/{app_id}")
                os.startfile(f"steam://run/{app_id}")
                return
        # 构建命令: Steam.exe -applaunch <AppID> [Arguments]
        cmd = [steam_exe, "-applaunch", str(app_id)]
        # 如果你的管理器本身也有需要注入的参数（例如隔离配置文件的参数）
        # 注意：这里传递的参数会追加在 Steam 内部设置的参数后面
        if extra_args:
            # 确保参数是列表形式
            if isinstance(extra_args, list):
                cmd.extend(extra_args)
            else:
                cmd.append(extra_args)
        # 启动
        subprocess.Popen(cmd)
        logger.debug(f"通过 Steam 命令启动 RimWorld: {cmd}")
    
    
    # =========================================================
    #  5. ACF 文件解析
    # =========================================================

    def _get_acf_path(self):
        """获取 appworkshop_294100.acf 的路径"""
        # 依赖 settings 中的 workshop_mods_path
        # 典型路径: .../steamapps/workshop/content/294100
        # ACF 路径: .../steamapps/workshop/appworkshop_294100.acf
        ws_path = settings.config.workshop_mods_path
        if not ws_path or not os.path.exists(ws_path): return None
        
        try:
            # 回退两级找到 workshop 目录
            workshop_root = os.path.dirname(os.path.dirname(ws_path))
            acf_file = os.path.join(workshop_root, f"appworkshop_{RIMWORLD_APP_ID}.acf")
            if os.path.exists(acf_file):
                return acf_file
        except:
            pass
        return None
    
    def get_acf_json(self) -> dict:
        """
        解析 ACF 文件，返回 JSON 格式数据
        返回: dict
        {
            "appid": "294100",
            "SizeOnDisk": "7959848359",
            "NeedsUpdate": "0",
            "NeedsDownload": "0",
            "TimeLastUpdated": "1771947626",
            "TimeLastAppRan": "1771885460",
            "LastBuildID": "20659247",
            "WorkshopItemsInstalled": {
                "704181221": {
                    "size": "2280283",
                    "timeupdated": "1752526039",
                    "manifest": "9102468959570688452"
                },
                ......
            },
            "WorkshopItemDetails": {
                "704181221": {
                    "manifest": "9102468959570688452",
                    "timeupdated": "1752526039",
                    "timetouched": "1771879580",
                    "subscribedby": "448102596",
                    "latest_timeupdated": "1752526039",
                    "latest_manifest": "9102468959570688452"
                },
                ......
            }
        }
        """
        acf_path = self._get_acf_path()
        if not acf_path: return {}
        try:
            with open(acf_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # VDF 格式解析
            # 结构: "WorkshopItemsInstalled" { "123" { ... } "456" { ... } }
            # print("ACF文件内容：\n",content[:1000])
            # 正则替换：将所有非 JSON 格式的键值对转换为 JSON 格式
            json_content = re.sub(r'(^\s*"[^"]+")', r'\1:', content, flags=re.M)
            json_content = re.sub(r'(["\}]$)', r'\1,', json_content, flags=re.M)
            # print("转换后的JSON内容：\n",json_content[:1000])
            json_data = cast(dict, repair_json('{'+json_content+'}', return_objects=True))
            # print("解析后的JSON数据：\n",json_data.get('AppWorkshop',{}).get('WorkshopItemsInstalled',{}).keys())
            return json_data.get('AppWorkshop',{})
        
        except Exception as e:
            logger.error(f"[get_acf_json] Failed to parse ACF for validation: {e}")
            
        return {}

    def get_installed_workshop_ids(self) -> set:
        """
        解析 ACF 文件，获取所有已安装的 Workshop Mod ID
        返回: set(int)
        """
        acf_json = self.get_acf_json()
        if not acf_json: return set()
        try:
            installed_ids = set()
            installed_ids.update(map(int,acf_json.get('WorkshopItemsInstalled',{}).keys()))
        except Exception as e:
            logger.error(f"Failed to parse installed Workshop IDs from ACF: {e}")
            
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
    
    
    def get_steam_log_path(self):
        """
        推断 Steam 客户端日志路径
        通常在 Steam 安装目录/logs/workshop_log.txt
        """
        # 尝试从游戏安装目录反推 Steam 目录
        # 典型路径: .../Steam/steamapps/common/RimWorld -> .../Steam/logs
        if not settings.config.game_install_path:
            return None
            
        try:
            # 向上找 3 层: RimWorld -> common -> steamapps -> Steam
            steam_root = os.path.abspath(os.path.join(settings.config.game_install_path, "../../.."))
            log_dir = os.path.join(steam_root, "logs")
            log_file = os.path.join(log_dir, "workshop_log.txt")
            
            if os.path.exists(log_file):
                return log_file
            
            # 如果反推失败，尝试默认路径 (Windows)
            if platform.system() == "Windows":
                default_path = r"C:\Program Files (x86)\Steam\logs\workshop_log.txt"
                if os.path.exists(default_path):
                    return default_path
        except:
            pass
        return None

    def parse_local_download_history(self, mod_id: str = '') :
        """
        解析 workshop_log.txt 获取下载历史
        :param mod_id: 如果提供，只返回该 Mod 的记录
        """
        log_path = self.get_steam_log_path()
        if not log_path:
            logger.warning("Steam workshop_log.txt not found.")
            return []

        history = []
        # 正则匹配示例: 
        # [2023-10-27 10:00:00] [AppID 294100] Download complete: 123456789
        # 注意：日志格式可能随 Steam 版本微调，以下通过匹配关键字段提取
        
        # 匹配时间戳和操作
        # 格式通常是: [YYYY-MM-DD HH:MM:SS] ...
        line_pattern = re.compile(r'^\[(.*?)\] (.*)')
        
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 倒序读取，获取最新的记录
                lines = f.readlines()
                for line in reversed(lines):
                    match = line_pattern.match(line)
                    if not match: continue
                    
                    timestamp_str = match.group(1)
                    content = match.group(2)
                    
                    # 过滤只看 RimWorld (294100)
                    if RIMWORLD_APP_ID not in content:
                        continue
                        
                    # 提取 Mod ID
                    # 常见日志: "Download complete: 818773962" 或 "Update complete"
                    # 我们寻找包含 Mod ID 的行
                    id_match = re.search(r'\b(\d{9,10})\b', content)
                    if not id_match: continue
                    
                    found_id = id_match.group(1)
                    
                    if mod_id and found_id != str(mod_id):
                        continue

                    # 判定操作类型
                    action = "Unknown"
                    if "Download complete" in content:
                        action = "Downloaded"
                    elif "Update complete" in content or "downloading" in content.lower():
                        action = "Updated"
                    elif "Download started" in content:
                        action = "Started"
                    else:
                        continue # 忽略不重要的行

                    history.append({
                        "mod_id": found_id,
                        "time": timestamp_str,
                        "action": action,
                        "raw": content
                    })
                    
                    # 限制返回数量，防止过多
                    if len(history) > 100 and not mod_id:
                        break
                        
        except Exception as e:
            logger.error(f"Failed to parse steam log: {e}")
            
        return history
    
    
