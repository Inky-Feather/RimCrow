# backend/managers/mgr_steam.py
import json
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
import uuid
import struct
from dateutil import parser
from typing import Any, cast
from json_repair import repair_json
from pathlib import Path

# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[2]
    # 调试打印，确保路径正确
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

# 注意：不要在文件顶层 import steamworks，防止主进程意外加载
# 只在 run_steam_worker 函数内部 import
from backend.utils.logger import logger
from backend.settings import BASE_RESOURCE_DIR, HOME_DIR, TOOLS_DIR, settings
from backend.managers.mgr_network import network_mgr
from backend.utils.event_bus import EventBus
from backend.managers.mgr_download import TaskStatus
from backend.managers.mgr_steamcmd_core import SteamCMDController
from backend.managers.mgr_game import GameManager
from backend.utils.tools import extract_zip

# RimWorld App ID
RIMWORLD_APP_ID = "294100"

# =========================================================
#  独立 Worker 函数 (由 main.py 在子进程调用)
# =========================================================
def run_steam_worker(action: str, payload: str):
    """
    独立进程运行的 Steam API 代理。
    支持两类场景：
    1. 订阅/取消订阅：payload 为单个 ID 或逗号分隔的批量 ID。
    2. 状态探测：action=probe_status，只短暂附着到 Steam 读取一次状态。
    """
    try:
        # 在这里才导入库，确保主进程干净
        from steamworks.steamworks import STEAMWORKS
    except ImportError:
        logger.error("ERROR: steamworks-py not found in bundle")
        return

    if action == "probe_status":
        # 探测模式只短暂附着到 Steam，拿到状态后立即退出。
        result = {
            "available": True,
            "running": False,
            "logged_in": False,
            "ready": False,
            "detail": "",
        }
        steam = None
        try:
            steam = STEAMWORKS()
            if not steam:
                result["detail"] = "steamworks_not_loaded"
                print(f"STEAM_STATUS_JSON:{json.dumps(result, ensure_ascii=False)}")
                return
            # IsSteamRunning 不是类里显式定义的方法，而是运行时动态 setattr(self, method_name, f) 挂上去的 ctypes 函数。
            result["running"] = bool(steam.IsSteamRunning())  # type: ignore
            if not result["running"]:
                result["detail"] = "steamworks_not_running"
            else:
                steam.initialize()
                logged_on = True
                if getattr(steam, "Users", None) and hasattr(steam.Users, "LoggedOn"):
                    logged_on = bool(steam.Users.LoggedOn())
                result["logged_in"] = logged_on
                result["ready"] = bool(result["running"] and result["logged_in"])
                result["detail"] = "steamworks_ready" if result["ready"] else "steamworks_not_logged_in"
        except Exception as e:
            result["detail"] = f"steamworks_probe_failed: {e}"
        finally:
            try:
                if steam and steam.loaded():
                    steam.unload()
            except Exception:
                pass
        print(f"STEAM_STATUS_JSON:{json.dumps(result, ensure_ascii=False)}")
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

    # 解析传入的 payload（支持单个 ID 整数或逗号分隔的字符串）
    mod_ids =[int(x.strip()) for x in str(payload).split(',') if x.strip().isdigit()]
    if not mod_ids:
        logger.error("ERROR: No valid mod IDs provided")
        return

    completed_callbacks = 0
    total_requests = len(mod_ids)

    # 闭包回调函数：记录 Steam 客户端的响应
    def callback(res):
        nonlocal completed_callbacks
        completed_callbacks += 1
        logger.info(f"Callback ({completed_callbacks}/{total_requests}): {res}")

    success = False
    try:
        for mod_id in mod_ids:
            if action in ("subscribe", "subscribe_batch"):
                steam.Workshop.SubscribeItem(mod_id, callback)
            elif action in ("unsubscribe", "unsubscribe_batch"):
                steam.Workshop.UnsubscribeItem(mod_id, callback)
            else:
                logger.error(f"ERROR: Unknown action {action}")
                return
        success = True
        logger.info(f"SUCCESS: {action} request sent for {total_requests} items")
    except Exception as e:
        logger.error(f"ERROR: Action failed: {e}")

    # 智能等待机制：等待回调完成，而不是死等固定的时间
    if success:
        # 每项最多给 0.5 秒缓冲，总超时下限为 2 秒，上限 15 秒
        timeout = max(2.0, min(15.0, total_requests * 0.5))
        start_time = time.time()
        
        while completed_callbacks < total_requests:
            if time.time() - start_time > timeout:
                logger.warning(f"TIMEOUT: Only received {completed_callbacks}/{total_requests} callbacks.")
                break
            time.sleep(0.1) # 短暂休眠，防止 CPU 空转
            
        # 在退出前额外给 Steam 客户端 0.5 秒处理底层的 IPC 状态
        time.sleep(0.5)

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
        # Steam 安装目录
        self.steam_dir = settings.config.steam_path or self.get_steam_path()
        self.steam_exe = str(Path(self.steam_dir) / "steam.exe") if self.steam_dir else self.get_steam_path(True) 
        # SteamCMD 路径
        self.steamcmd_dir = settings.config.steamcmd_path or str(TOOLS_DIR / "steamcmd")
        self.steamcmd_exe = self._get_steamcmd_exe_path()
        # Steam Agent 路径 (隔离环境)
        self.agent_dir = str(TOOLS_DIR / "steam_agent")
        # 确保目录存在
        os.makedirs(self.steamcmd_dir, exist_ok=True)
        os.makedirs(self.agent_dir, exist_ok=True)
        # 状态
        self.steamcmd_ready = os.path.exists(self.steamcmd_exe)
        # 文件修改时间记录，减少磁盘 IO
        self._last_acf_mtime = 0
        self._last_log_mtime = 0
        self._cached_merged_data = []
        # 中央任务调度器状态
        self._monitor_lock = threading.Lock()
        self._active_tasks = {}          # 存放所有正在执行的任务 { task_id: dict }
        self._monitor_running = False    # 标记主监控线程是否存活
        # SteamCMD 下载和初始化都依赖外部进程，这里单独维护可取消的进程表。
        self._steamcmd_lock = threading.Lock()
        self._steamcmd_processes: dict[str, subprocess.Popen] = {}
        self._steamcmd_cancelled: set[str] = set()
        self._steamcmd_controllers: dict[str, SteamCMDController] = {}
        # 添加内存缓存
        self._cached_ws_map = None
        self._last_ws_log_mtime = 0
        self._last_ws_acf_mtime = 0
        # 添加内存缓存
        self._cached_cmd_map = None
        self._last_cmd_log_mtime = 0
        self._last_cmd_acf_mtime = 0
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
            # 添加可能的搜索位置：
            # A. _MEIPASS 根目录 (如果 spec 文件配置为 binary 放在根目录)
            search_dirs.append(str(BASE_RESOURCE_DIR))
            # B. _MEIPASS/steamworks (如果使用了 collect_all 或 add_data 保持了目录结构)
            search_dirs.append(str(BASE_RESOURCE_DIR / "steamworks"))
            # C. EXE 同级目录 (用户手动放置 DLL 作为补救)
            search_dirs.append(str(HOME_DIR))
        else:
            # === 开发环境 ===
            try:
                spec = importlib.util.find_spec("steamworks")
                if spec and spec.origin:
                    search_dirs.append(os.path.dirname(spec.origin))
            except: pass

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
            
        is_initialized = (Path(settings.config.steamcmd_path) / "public").exists()
        
        if os.path.exists(self.steamcmd_exe) and not is_initialized:
            controller = SteamCMDController(self.steamcmd_exe)
            steamcmd_task_id = str(uuid.uuid4())
            EventBus.emit_progress(
                steamcmd_task_id,
                "steamcmd-init",
                status="pending",
                progress=0,
                message="准备初始化 SteamCMD...",
                metrics={"title": "SteamCMD 初始化"},
            )
            
            def on_progress(percent, msg):
                if self._is_steamcmd_task_cancelled(steamcmd_task_id):
                    controller.kill_all()
                    return
                # 将进度推给前端
                from backend.utils.event_bus import EventBus
                EventBus.emit_progress(
                    steamcmd_task_id,
                    "steamcmd-init",
                    status="running",
                    progress=percent,
                    message=msg,
                    metrics={"title": "SteamCMD 初始化"},
                )
            self._register_steamcmd_controller(steamcmd_task_id, controller)
            success, msg = controller.initialize_steamcmd(on_progress)
            self._clear_steamcmd_controller(steamcmd_task_id)
            if self._is_steamcmd_task_cancelled(steamcmd_task_id):
                EventBus.emit_progress(steamcmd_task_id, "steamcmd-init", status="cancelled", progress=0, message="SteamCMD 初始化已取消", metrics={"title": "SteamCMD 初始化"})
                with self._steamcmd_lock:
                    self._steamcmd_cancelled.discard(steamcmd_task_id)
                return tasks
            if not success:
                EventBus.emit_progress(steamcmd_task_id, "steamcmd-init", status="failed", progress=0, message=msg, metrics={"title": "SteamCMD 初始化"})
                logger.error(f"SteamCMD 初始化彻底失败: {msg}")
            else:
                EventBus.emit_progress(steamcmd_task_id, "steamcmd-init", status="success", progress=100, message="SteamCMD 初始化完成", metrics={"title": "SteamCMD 初始化"})
            
        return tasks
    
    def post_download_setup(self, task_type, file_path):
        """下载完成后的解压/配置回调"""
        if task_type == "steamcmd":
            try:
                if file_path.endswith('.zip'):
                    extract_zip(file_path, self.steamcmd_dir)
                    os.remove(file_path)
                    self.steamcmd_ready = True
                    logger.info("SteamCMD installed.")
            except Exception as e:
                logger.error(f"Failed to extract SteamCMD: {e}")

    def is_steam_running(self) -> bool:
        """跨平台检测 Steam 进程是否存活"""
        try:
            sys_name = platform.system()
            if sys_name == "Windows":
                # 隐藏控制台窗口
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                # 使用内置 tasklist 过滤，/NH 去掉表头提升解析速度
                res = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq steam.exe', '/NH'], 
                    capture_output=True, text=True, startupinfo=si
                )
                return 'steam.exe' in res.stdout.lower()
            elif sys_name == "Darwin": # MacOS
                res = subprocess.run(['ps', '-A'], capture_output=True, text=True)
                return 'steam.app' in res.stdout.lower()
            else: # Linux
                res = subprocess.run(['ps', '-A'], capture_output=True, text=True)
                return 'steam' in res.stdout.lower()
        except Exception as e:
            logger.error(f"Check steam process failed: {e}")
            return False

    def _read_windows_active_process_status(self) -> dict:
        """
        读取 Steam ActiveProcess 注册表状态。
        ActiveUser 非 0 时，可作为 Windows 下“客户端已登录”的兜底依据。
        """
        result = {
            "pid": 0,
            "active_user": 0,
            "running": False,
            "logged_in": False,
        }
        if platform.system() != "Windows":
            return result

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess")
            pid, _ = winreg.QueryValueEx(key, "pid")
            active_user, _ = winreg.QueryValueEx(key, "ActiveUser")
            result["pid"] = int(pid or 0)
            result["active_user"] = int(active_user or 0)
            result["running"] = result["pid"] > 0
            result["logged_in"] = result["active_user"] > 0
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"Read Steam ActiveProcess failed: {e}")
        return result

    def _probe_steamworks_status(self, timeout_seconds: float = 8.0) -> dict:
        """
        使用短命 worker 子进程探测 Steamworks 状态。
        主进程不直接加载 Steamworks，避免被 Steam 识别为挂载中的游戏进程。
        """
        result = {
            "available": False,
            "running": False,
            "logged_in": False,
            "ready": False,
            "detail": "",
        }

        try:
            worker = self._run_steam_worker("probe_status", "_", timeout_seconds=timeout_seconds)
        except subprocess.TimeoutExpired:
            result["detail"] = "steamworks_probe_timeout"
            return result
        except Exception as e:
            result["detail"] = f"steamworks_probe_failed: {e}"
            return result

        stdout_text = str(worker.stdout or "")
        for line in reversed(stdout_text.splitlines()):
            marker = "STEAM_STATUS_JSON:"
            if line.startswith(marker):
                try:
                    payload = json.loads(line[len(marker):].strip())
                    if isinstance(payload, dict):
                        result.update(payload)
                        return result
                except Exception as e:
                    result["detail"] = f"steamworks_probe_parse_failed: {e}"
                    return result

        stderr_text = str(worker.stderr or "").strip()
        if worker.returncode != 0:
            result["detail"] = f"steamworks_probe_exit_{worker.returncode}"
            if stderr_text:
                result["detail"] += f": {stderr_text}"
            return result

        result["detail"] = "steamworks_probe_no_result"
        return result

    def _run_steam_worker(self, action: str, payload: str, timeout_seconds: float = 20.0):
        """
        统一拉起短命 Steam worker。
        这样可以复用子进程启动细节，避免订阅/退订与状态探测各自重复拼命令。
        """
        current_exe = sys.executable
        is_frozen = getattr(sys, 'frozen', False)
        cmd = [current_exe]
        if not is_frozen:
            cmd.append(str(BASE_RESOURCE_DIR / "main.py"))
        cmd.extend(["--steam-worker", str(action), str(payload)])

        current_env = os.environ.copy()
        current_env["_PYI_SPLASH_IPC"] = "0"
        startupinfo = None
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        return subprocess.run(
            cmd,
            cwd=self.agent_dir,
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            encoding='utf-8',
            env=current_env,
            timeout=max(1.0, float(timeout_seconds or 0)),
        )

    def get_steam_client_status(self) -> dict:
        """
        返回 Steam 客户端状态。
        优先使用 Steamworks API 判断“已登录/可用”，Windows 下再用 ActiveProcess 注册表兜底。
        """
        process_running = self.is_steam_running()
        status = {
            "running": process_running,
            "logged_in": False,
            "ready": False,
            "source": "process",
            "detail": "process_only",
            "pid": 0,
            "active_user": 0,
        }

        registry_status = self._read_windows_active_process_status()
        if registry_status:
            status["pid"] = int(registry_status.get("pid", 0) or 0)
            status["active_user"] = int(registry_status.get("active_user", 0) or 0)

        # 只有进程层面看起来 Steam 确实活着时，才值得再拉起一次短命 worker 去探测 Steamworks。
        # 这样能避免 Steam 明明没开时仍然多余地创建子进程。
        if bool(process_running or registry_status.get("running")):
            steamworks_status = self._probe_steamworks_status()
            if steamworks_status.get("available"):
                status["running"] = bool(steamworks_status.get("running"))
                status["logged_in"] = bool(steamworks_status.get("logged_in"))
                status["ready"] = bool(steamworks_status.get("ready"))
                status["source"] = "steamworks"
                status["detail"] = str(steamworks_status.get("detail") or "steamworks")
                if status["ready"] or status["detail"] in {"steamworks_not_running", "steamworks_not_logged_in"}:
                    return status

        if platform.system() == "Windows":
            status["running"] = bool(process_running or registry_status.get("running"))
            status["logged_in"] = bool(registry_status.get("logged_in"))
            status["ready"] = bool(status["running"] and status["logged_in"])
            status["source"] = "registry_fallback"
            status["detail"] = "active_process_ready" if status["ready"] else "active_process_not_ready"

        return status

    def start_steam(self) -> bool:
        """尝试启动 Steam 客户端"""
        if self.is_steam_running():
            return True
            
        steam_exe = str(self.steam_exe) if self.steam_exe else None
        
        # 找不到执行文件时的兜底策略：使用系统协议唤醒
        if not steam_exe or not os.path.exists(steam_exe):
            try:
                if platform.system() == "Windows":
                    os.startfile("steam://open/main")
                    return True
            except:
                pass
            return False
            
        try:
            # 独立进程启动，绝不阻塞当前程序的运行
            if platform.system() == "Windows":
                subprocess.Popen([steam_exe])
            else:
                subprocess.Popen([steam_exe])
            return True
        except Exception as e:
            logger.error(f"Failed to start Steam: {e}")
            return False
    
    
    # =========================================================
    #  2. SteamCMD 功能
    # =========================================================
    def download_workshop_items(self, workshop_ids: list, on_success=None):
        EventBus.resume()   # 恢复事件总线
        if not self.steamcmd_ready:
            raise Exception("SteamCMD is not installed.")
        # SteamCMD 下载目录当前与管理器自管目录共用物理数据。
        # 若用户从文件管理流程中删掉了实际目录，但 ACF 里仍残留“已安装”记录，
        # SteamCMD 后续下载会在全量校验阶段报 Missing game files。
        # 因此在每次发起下载前先收敛一次 ACF，仅移除“目录已不存在”的陈旧记录。
        self.reconcile_steamcmd_acf()
        # 生成一个 Task ID 并返回给前端，以便前端监听
        task_id = "steamcmd_batch_" + str(time.time_ns() // 1000000)
        
        commands = ["login anonymous"]
        for mid in workshop_ids:
            commands.append(f"workshop_download_item {RIMWORLD_APP_ID} {mid}")
        commands.append("quit")
        t = threading.Thread(target=self._run_steamcmd_process, args=(commands, workshop_ids, task_id, on_success))
        t.start()
        return task_id

    def _run_steamcmd_process(self, commands, mod_ids, task_id, on_success=None):
        # 1. 复制当前主进程的环境变量
        current_env = os.environ.copy()
        # 2. 检查开关：如果开启了 SteamCMD 代理，则合并代理环境变量
        if settings.config.network.use_proxy_on_steamcmd:
            proxy_env = network_mgr.get_proxy_env()
            current_env.update(proxy_env)
            logger.info("SteamCMD will run WITH proxy.")
        else:
            # 如果关闭代理，确保环境变量里没有残留的代理设置
            current_env.pop("HTTP_PROXY", None)
            current_env.pop("HTTPS_PROXY", None)
            current_env.pop("ALL_PROXY", None)
            logger.info("SteamCMD will run WITHOUT proxy.")
        
        target_dir = settings.config.steamcmd_mods_path
        # 初始化状态
        self._emit_progress_event(task_id, "正在连接 Steam 服务器...", 0, TaskStatus.RUNNING, target_dir, "SteamCMD", task_type="steamcmd-download")

        try:
            args = [self.steamcmd_exe]
            for cmd in commands:
                args.append(f"+{cmd}")
            # 调试模式下给 SteamCMD 新建独立控制台窗口，直接观察真实输出；
            # 非调试模式仍通过管道解析输出并静默运行。
            debug_show_console = platform.system() == "Windows" and bool(settings.config.debug_mode)
            startupinfo = None
            creationflags = 0
            if platform.system() == "Windows":
                if debug_show_console:
                    creationflags = subprocess.CREATE_NEW_CONSOLE
                else:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                args,
                stdout=None if debug_show_console else subprocess.DEVNULL,
                stderr=None if debug_show_console else subprocess.DEVNULL,
                env=current_env,    # 传递合并后的环境变量
                text=False,
                startupinfo=startupinfo,
                creationflags=creationflags,
                cwd=self.steamcmd_dir,
                bufsize=1 # 行缓冲
            )
            with self._steamcmd_lock:
                self._steamcmd_processes[task_id] = process

            current_item_idx = 0
            total_items = len(mod_ids)
            completed_ids: set[str] = set()
            failed_ids: set[str] = set()
            workshop_log_path = Path(self.steamcmd_dir) / "logs" / "workshop_log.txt"
            log_read_offset = workshop_log_path.stat().st_size if workshop_log_path.exists() else 0

            while process.poll() is None:
                if self._is_steamcmd_task_cancelled(task_id):
                    self._terminate_steamcmd_process(task_id, process)
                    self._emit_progress_event(
                        task_id,
                        "SteamCMD 下载已取消",
                        int((current_item_idx / max(total_items, 1)) * 100),
                        TaskStatus.CANCELLED,
                        target_dir,
                        "SteamCMD",
                        task_type="steamcmd-download",
                    )
                    return
                log_read_offset, current_item_idx, _ = self._consume_steamcmd_log_progress(
                    workshop_log_path=workshop_log_path,
                    start_offset=log_read_offset,
                    completed_ids=completed_ids,
                    failed_ids=failed_ids,
                    current_item_idx=current_item_idx,
                    total_items=total_items,
                    task_id=task_id,
                    target_dir=target_dir,
                )
                time.sleep(0.2)

            log_read_offset, current_item_idx, _ = self._consume_steamcmd_log_progress(
                workshop_log_path=workshop_log_path,
                start_offset=log_read_offset,
                completed_ids=completed_ids,
                failed_ids=failed_ids,
                current_item_idx=current_item_idx,
                total_items=total_items,
                task_id=task_id,
                target_dir=target_dir,
            )

            if self._is_steamcmd_task_cancelled(task_id):
                self._emit_progress_event(task_id, "SteamCMD 下载已取消", int((current_item_idx / max(total_items, 1)) * 100), TaskStatus.CANCELLED, target_dir, "SteamCMD", task_type="steamcmd-download")
            elif failed_ids:
                failed_text = ", ".join(sorted(failed_ids)[:5])
                if len(failed_ids) > 5:
                    failed_text += " ..."
                self._emit_progress_event(
                    task_id,
                    f"SteamCMD 下载失败 ({current_item_idx}/{total_items})",
                    int((current_item_idx / max(total_items, 1)) * 100),
                    TaskStatus.ERROR,
                    target_dir,
                    "SteamCMD",
                    error=f"失败项: {failed_text}",
                    task_type="steamcmd-download",
                )
            elif process.returncode == 0:
                self._emit_progress_event(task_id, f"全部下载完成 ({total_items})", 100, TaskStatus.COMPLETED, target_dir, "SteamCMD", task_type="steamcmd-download")
                if callable(on_success):
                    try:
                        on_success()
                    except Exception as refresh_error:
                        logger.warning(f"SteamCMD 下载完成后自动刷新失败: {refresh_error}")
            else:
                self._emit_progress_event(task_id, f"SteamCMD 异常退出: {process.returncode}", 0, TaskStatus.ERROR, target_dir, "SteamCMD", task_type="steamcmd-download")

        except Exception as e:
            logger.error(f"SteamCMD execution failed: {e}")
            self._emit_progress_event(task_id, str(e), 0, TaskStatus.ERROR, target_dir, "SteamCMD", task_type="steamcmd-download")
        finally:
            with self._steamcmd_lock:
                self._steamcmd_processes.pop(task_id, None)
                self._steamcmd_cancelled.discard(task_id)

    def _consume_steamcmd_log_progress(
        self,
        workshop_log_path: Path,
        start_offset: int,
        completed_ids: set[str],
        failed_ids: set[str],
        current_item_idx: int,
        total_items: int,
        task_id: str,
        target_dir: str,
    ) -> tuple[int, int, str | None]:
        """
        调试窗口模式下无法再从 stdout 管道读取 SteamCMD 输出，
        这里退而求其次改为消费 workshop_log.txt 的新增内容来驱动进度。
        """
        if not workshop_log_path.exists():
            return start_offset, current_item_idx, None

        log_start_pattern = re.compile(r"Download item (\d+) requested by app")
        log_success_pattern = re.compile(r"Download item (\d+) result : OK")
        log_failure_pattern = re.compile(r"Download item (\d+) result : Failure")

        try:
            file_size = workshop_log_path.stat().st_size
            if start_offset > file_size:
                start_offset = 0

            with open(workshop_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(start_offset)
                chunk = f.read()
                new_offset = f.tell()
        except Exception as e:
            logger.debug(f"Read SteamCMD workshop log failed: {e}")
            return start_offset, current_item_idx, None

        if not chunk:
            return new_offset, current_item_idx, None

        active_item_id: str | None = None
        for raw_line in chunk.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            start_matches = [match.group(1) for match in log_start_pattern.finditer(line)]
            success_matches = [match.group(1) for match in log_success_pattern.finditer(line)]
            failure_matches = [match.group(1) for match in log_failure_pattern.finditer(line)]

            if start_matches:
                active_item_id = start_matches[-1]
                self._emit_progress_event(
                    task_id,
                    f"下载中 ({current_item_idx}/{total_items})",
                    int((current_item_idx / max(total_items, 1)) * 100),
                    TaskStatus.RUNNING,
                    target_dir,
                    "SteamCMD",
                    task_type="steamcmd-download",
                )

            for item_id in success_matches:
                if item_id in completed_ids:
                    continue
                completed_ids.add(item_id)
                failed_ids.discard(item_id)
                current_item_idx += 1
                total_percent = (current_item_idx / max(total_items, 1)) * 100
                self._emit_progress_event(
                    task_id,
                    f"下载中 ({current_item_idx}/{total_items})",
                    int(total_percent),
                    TaskStatus.RUNNING if current_item_idx < total_items else TaskStatus.COMPLETED,
                    target_dir,
                    "SteamCMD",
                    task_type="steamcmd-download",
                )

            for item_id in failure_matches:
                if item_id in completed_ids:
                    continue
                failed_ids.add(item_id)

        return new_offset, current_item_idx, active_item_id
            

    # =========================================================
    #  3. 自我调用 (Re-entry) 逻辑
    # =========================================================
    
    def _execute_steam_action(self, action: str, ids: int | str | list) -> bool:
        """
        核心执行器：支持 int, str 或 list 类型的输入
        """
        # 1. 类型检查与归一化，兼容 "12345" 或 12345
        if isinstance(ids, (int, str)): id_list = [str(ids)]
        elif isinstance(ids, list): id_list = [str(i) for i in ids]
        else:
            logger.error(f"Invalid ID type: {type(ids)}")
            return False
        if not id_list: return True

        # 2. 分块处理 (避免命令行超长)
        BATCH_SIZE = 50
        all_success = True
        for i in range(0, len(id_list), BATCH_SIZE):
            batch = id_list[i : i + BATCH_SIZE]
            payload = ",".join(batch)
            try:
                result = self._run_steam_worker(action, payload, timeout_seconds=20.0)
                if "SUCCESS" not in result.stdout:
                    logger.error(f"Steam Agent Error: {result.stdout}")
                    all_success = False
            except Exception as e:
                logger.error(f"Failed to run steam agent: {e}")
                all_success = False

        return all_success


    def subscribe_items(self, ids: int | str | list):
        """订阅模组入口"""
        return self._submit_task("subscribe", ids)

    def unsubscribe_items(self, ids: int | str | list):
        """取消订阅模组入口"""
        return self._submit_task("unsubscribe", ids)

    def _submit_task(self, action: str, ids: int | str | list):
        """统一的任务提交器：包含去重发送、冲突修剪、并注册到中央监控池"""
        task_type = "steam-subscribe" if action == "subscribe" else "steam-unsubscribe"
        target_ids = [str(ids)] if isinstance(ids, (int, str)) else [str(i) for i in ids]
        target_ids = list(set(target_ids)) # 去重
        
        # --- 新增核心逻辑：冲突修剪 (Target Pruning) ---
        with self._monitor_lock:
            for tid, existing_task in list(self._active_tasks.items()):
                # 如果遇到动作相反的任务（例如：旧任务正在订阅，新任务要移除）
                if existing_task["action"] != action:
                    # 计算有冲突的 Mod ID 交集
                    overlap = set(existing_task["targets"]).intersection(set(target_ids))
                    if overlap:
                        # 从旧任务的目标列表中剔除冲突的 ID
                        existing_task["targets"] =[x for x in existing_task["targets"] if x not in overlap]
                        existing_task["total"] = len(existing_task["targets"])
                        logger.info(f"冲突拦截: 从任务 {tid} 中移除了 {len(overlap)} 个冲突项。")
                        # 妙手：如果旧任务的目标被扣光了(total=0)，下一次轮询时进度会自动变成 100% 并自我销毁！

        # 1. 发送 Steam 指令 (过滤掉已经完美的项)
        data_dict = self.workshop_merged_data()
        to_action =[]
        ws_base_path = settings.config.workshop_mods_path
        for mid in target_ids:
            item = data_dict.get(mid)
            folder_exists = bool(ws_base_path and os.path.exists(os.path.join(ws_base_path, mid)))
            
            if action == "subscribe":
                is_perfect = item and item.get('is_installed') and not item.get('needs_update') and folder_exists
                if not is_perfect:
                    to_action.append(mid)
            else: # unsubscribe
                # 【核心修复】：只要物理存在、ACF记录存在、或者日志说它还订阅着，都要去退订！
                is_sub = item.get('is_subscribed') if item else False
                if folder_exists or (item and item.get('is_installed')) or is_sub:
                    to_action.append(mid)

        if to_action:
            self._execute_steam_action(action, to_action)

        # 2. 生成唯一 Task ID
        task_id = f"steam_{action}_{int(time.time() * 1000)}"
        
        # 3. 注册新任务并唤醒监控线程
        with self._monitor_lock:
            # 即便 target_ids 全部都是 is_perfect，也建一个空任务让监控线程秒回 100%
            # 这能保证前端的 Promise 必然被 Resolve！
            self._active_tasks[task_id] = {
                "targets": target_ids,
                "total": len(target_ids),
                "action": action,
                "start_time": time.time(),
                "task_type": task_type,
            }
            
            if not self._monitor_running:
                self._monitor_running = True
                threading.Thread(target=self._master_monitor_loop, daemon=True).start()
                
        return task_id

    def abort_monitor_task(self, task_id: str):
        """
        供前端 UI '取消任务' 按钮调用。
        仅仅是从监控列表中移除该任务（不再发送进度事件），
        注意：这不会停止 Steam 本身的下载，若要停止下载请调用 unsubscribe_item。
        """
        with self._monitor_lock:
            if task_id in self._active_tasks:
                existing_task = dict(self._active_tasks.pop(task_id))
                logger.info(f"主动终止了对任务的监控: {task_id}")
                
                # 给前端发送一个被终止的状态，让 Promise 能够 Reject
                self._emit_progress_event(
                    tid=task_id,
                    msg="任务已取消",
                    percent=0,
                    status=TaskStatus.CANCELLED,
                    file_path=settings.config.workshop_mods_path, 
                    title="Steam 托管",
                    error="用户主动取消了任务监控",
                    task_type=str(existing_task.get("task_type") or "steam-subscribe"),
                )
                return True
        return False
    
    def _master_monitor_loop(self):
        ws_base_path = settings.config.workshop_mods_path
        
        while True:
            with self._monitor_lock:
                if not self._active_tasks:
                    self._monitor_running = False
                    break
                current_tasks = dict(self._active_tasks)
            try:
                data_dict = self.workshop_merged_data()
                tasks_to_remove =[]
                for tid, task in current_tasks.items():
                    targets = task["targets"]
                    total = task["total"]
                    action = task["action"]
                    start_time = task["start_time"]
                    
                    finished_count = 0
                    errors =[]
                    
                    # 如果目标被全部修剪光了 (total == 0)
                    if total == 0:
                        percent = 100
                        status = TaskStatus.COMPLETED
                        msg = "任务已被取消或覆盖"
                    else:
                        for mid in targets:
                            item = data_dict.get(mid)
                            folder_exists = bool(ws_base_path and os.path.exists(os.path.join(ws_base_path, mid)))
                            
                            if action == "subscribe":
                                if item and item.get('is_installed') and not item.get('needs_update') and folder_exists:
                                    finished_count += 1
                                elif item and item.get('has_error') and item.get('error_detail'):
                                    errors.append(f"Mod {mid}: {item.get('error_detail')}")
                                    
                            elif action == "unsubscribe":
                                is_installed_acf = item.get('is_installed') if item else False
                                is_subscribed = item.get('is_subscribed') if item else False
                                # 条件1：完美移除 (物理消失 + Steam记录消失)
                                if not is_installed_acf and not folder_exists:
                                    finished_count += 1
                                # 条件2：容错放行 (物理已经消失，且指令发出了超过 3 秒)
                                # 对付手动删文件导致 Steam 装死不更新 ACF 的情况
                                elif not folder_exists and (time.time() - start_time > 3):
                                    finished_count += 1
                                # 条件3：日志明确表示已经退订 
                                # (应对 Steam 延迟删文件，或游戏运行中锁定文件的情况)
                                elif item and is_subscribed is False:
                                    finished_count += 1
                                # 条件4：兜底超时放行 
                                # (如果向 Steam 发出退订指令超过 10 秒，强行认定完成，防止卡 0%)
                                elif time.time() - start_time > 10:
                                    finished_count += 1

                        # 计算独立进度
                        percent = int((finished_count / total) * 100)
                        status = TaskStatus.RUNNING
                        
                        if finished_count == total:
                            status = TaskStatus.COMPLETED
                        elif errors and (len(errors) + finished_count >= total):
                            status = TaskStatus.ERROR
                        elif time.time() - start_time > 1800:
                            status = TaskStatus.ERROR
                            errors.append("Steam 响应超时")

                        # 修复这里的越界报错！
                        action_zh = "订阅" if action == "subscribe" else "移除"
                        if total > 1:
                            msg = f"Steam {action_zh} 完成 ({finished_count}/{total})" if (finished_count==total) else f"Steam {action_zh}中 ({finished_count}/{total})"
                        else:
                            msg = f"{action_zh}模组 {targets[0]}"

                    # 发送独立的事件给前端
                    self._emit_progress_event(
                        tid=tid,
                        msg=msg,
                        percent=percent,
                        status=status,
                        file_path=settings.config.workshop_mods_path, 
                        title="Steam 托管",
                        error="; ".join(errors) if errors else None,
                        task_type=str(task.get("task_type") or "steam-subscribe"),
                    )

                    if status in[TaskStatus.COMPLETED, TaskStatus.ERROR]:
                        tasks_to_remove.append(tid)

                if tasks_to_remove:
                    with self._monitor_lock:
                        for tid in tasks_to_remove:
                            self._active_tasks.pop(tid, None)

            except Exception as e:
                logger.error(f"[Master Monitor Loop] 轮询时遇到波动: {e}", exc_info=True)
                
            time.sleep(3)
    
    def _emit_progress_event(self, tid, msg, percent, status, file_path='', title='', error=None, task_type='steam-subscribe'):
        """对接 EventBus 格式"""
        status_map = {
            TaskStatus.COMPLETED: "success",
            TaskStatus.ERROR: "failed",
            TaskStatus.CANCELLED: "cancelled",
        }
        EventBus.emit_progress(
            tid,
            task_type,
            status=status_map.get(status, "running"),
            progress=percent,
            message=msg,
            metrics={
                "file_path": file_path,
                "current": percent,
                "total": 100,
                "error": error,
                "provider": "steamcmd" if str(task_type).startswith("steamcmd-") else "steam",
                "title": title or "Steam 任务",
            },
        )

    def cancel_steamcmd_task(self, task_id: str) -> bool:
        """请求取消 SteamCMD 下载或初始化任务。"""
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return False
        with self._steamcmd_lock:
            process = self._steamcmd_processes.get(normalized_task_id)
            controller = self._steamcmd_controllers.get(normalized_task_id)
            self._steamcmd_cancelled.add(normalized_task_id)
        if controller:
            controller.kill_all()
        if process:
            self._terminate_steamcmd_process(normalized_task_id, process)
        return True

    def cleanup_runtime(self) -> None:
        """应用退出时统一回收 SteamCMD 相关子进程与控制器。"""
        with self._steamcmd_lock:
            task_ids = list(set(self._steamcmd_processes.keys()) | set(self._steamcmd_controllers.keys()))
        for task_id in task_ids:
            try:
                self.cancel_steamcmd_task(task_id)
            except Exception as e:
                logger.debug(f"Cleanup SteamCMD task failed: task_id={task_id} error={e}")

    def _is_steamcmd_task_cancelled(self, task_id: str) -> bool:
        with self._steamcmd_lock:
            return task_id in self._steamcmd_cancelled

    def _terminate_steamcmd_process(self, task_id: str, process: subprocess.Popen | None = None) -> None:
        """统一终止 SteamCMD 进程树，避免不同调用点各自重复拼终止逻辑。"""
        active_process = process
        with self._steamcmd_lock:
            if active_process is None:
                active_process = self._steamcmd_processes.get(task_id)
        if not active_process:
            return
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(active_process.pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                active_process.kill()
        except Exception as e:
            logger.debug(f"Terminate SteamCMD task failed: task_id={task_id} error={e}")

    def _register_steamcmd_controller(self, task_id: str, controller: SteamCMDController) -> None:
        with self._steamcmd_lock:
            self._steamcmd_controllers[task_id] = controller

    def _clear_steamcmd_controller(self, task_id: str) -> None:
        with self._steamcmd_lock:
            self._steamcmd_controllers.pop(task_id, None)



    # =========================================================
    #  4. Steam本体操作
    # =========================================================
    
    def get_steam_path(self, with_exe=False):
        """从注册表获取 Steam 安装路径"""
        try:
            # 尝试读取 64位 注册表
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            return os.path.join(path, "steam.exe") if with_exe else path
        except:
            try:
                # 尝试读取 32位 注册表
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
                path, _ = winreg.QueryValueEx(key, "InstallPath")
                return os.path.join(path, "steam.exe") if with_exe else path
            except:
                return None

    def launch_via_steam_cmd(self, app_id=RIMWORLD_APP_ID, extra_args=None):
        steam_exe = str(self.steam_exe) if self.steam_exe else None
        # 如果找不到 Steam.exe，回退到原来的 URL 方式
        if not steam_exe or not os.path.exists(steam_exe):
            logger.warning("未找到 Steam.exe，回退到 URL 协议启动")
            # os.startfile(f"steam://rungameid/{app_id}")
            os.startfile(f"steam://run/{app_id}")
            return
        # 构建命令: Steam.exe -applaunch <AppID> [Arguments]
        cmd = [steam_exe, "-applaunch", str(app_id)]
        # 如果管理器本身也有需要注入的参数（例如隔离配置文件的参数）
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

    def _steam64_to_account_id(self, steam64_id: str | int | None) -> str:
        """将 Steam64 ID 转成 userdata 目录使用的 account id（32 位）。"""
        try:
            value = int(str(steam64_id or '').strip())
            account_id = value - 76561197960265728
            return str(account_id) if account_id >= 0 else ''
        except Exception:
            return ''

    def _get_userdata_root(self) -> Path:
        steam_dir = Path(str(self.steam_dir or '').strip())
        if not steam_dir:
            raise FileNotFoundError("未配置 Steam 安装目录")
        return steam_dir / "userdata"

    def _load_loginusers_map(self) -> dict[str, dict[str, Any]]:
        """
        读取 loginusers.vdf，整理出 account id -> 用户信息映射。
        这里优先为 shortcuts.vdf 写入选出最合理的目标 Steam 用户。
        """
        loginusers_path = Path(str(self.steam_dir or '').strip()) / "config" / "loginusers.vdf"
        if not loginusers_path.exists():
            return {}

        try:
            import vdf

            with open(loginusers_path, 'r', encoding='utf-8', errors='ignore') as f:
                payload = vdf.load(f) or {}
        except Exception as e:
            logger.warning(f"读取 loginusers.vdf 失败: {e}")
            return {}

        users_map = payload.get("users") if isinstance(payload, dict) else {}
        if not isinstance(users_map, dict):
            return {}

        result: dict[str, dict[str, Any]] = {}
        for steam64_id, raw_info in users_map.items():
            account_id = self._steam64_to_account_id(steam64_id)
            if not account_id:
                continue
            info = raw_info if isinstance(raw_info, dict) else {}
            result[account_id] = {
                "steam64_id": str(steam64_id),
                "account_id": account_id,
                "account_name": str(info.get("AccountName") or '').strip(),
                "persona_name": str(info.get("PersonaName") or '').strip(),
                "most_recent": str(info.get("MostRecent") or '0').strip() == '1',
                "timestamp": int(str(info.get("Timestamp") or '0').strip() or 0),
            }
        return result

    def resolve_shortcuts_user(self) -> dict[str, Any]:
        """
        为 shortcuts.vdf 选出目标 Steam 用户。
        选择顺序：
        1. 当前已登录的 ActiveUser
        2. loginusers.vdf 中标记 MostRecent 的用户
        3. 本地唯一 userdata 用户
        4. loginusers.vdf 中时间最新的用户
        """
        userdata_root = self._get_userdata_root()
        if not userdata_root.exists():
            raise FileNotFoundError(f"未找到 Steam userdata 目录: {userdata_root}")

        user_dirs = sorted(
            item.name for item in userdata_root.iterdir()
            if item.is_dir() and item.name.isdigit()
        )
        if not user_dirs:
            raise FileNotFoundError("未找到任何 Steam 用户数据目录")

        loginusers_map = self._load_loginusers_map()
        active_status = self._read_windows_active_process_status()
        active_user = str(int(active_status.get("active_user") or 0)) if int(active_status.get("active_user") or 0) > 0 else ""

        selected_user = ""
        source = ""
        if active_user and active_user in user_dirs:
            selected_user = active_user
            source = "active_process"
        else:
            recent_users = [
                user_id for user_id in user_dirs
                if bool((loginusers_map.get(user_id) or {}).get("most_recent"))
            ]
            if recent_users:
                selected_user = recent_users[0]
                source = "loginusers_recent"
            elif len(user_dirs) == 1:
                selected_user = user_dirs[0]
                source = "single_userdata"
            else:
                sorted_candidates = sorted(
                    user_dirs,
                    key=lambda user_id: int((loginusers_map.get(user_id) or {}).get("timestamp") or 0),
                    reverse=True,
                )
                selected_user = sorted_candidates[0]
                source = "loginusers_timestamp"

        user_info = loginusers_map.get(selected_user, {})
        persona_name = str(user_info.get("persona_name") or '').strip()
        account_name = str(user_info.get("account_name") or '').strip()
        display_name = persona_name or account_name or selected_user
        if persona_name and account_name and persona_name != account_name:
            display_name = f"{persona_name} ({account_name})"

        shortcuts_path = userdata_root / selected_user / "config" / "shortcuts.vdf"
        return {
            "user_id": selected_user,
            "display_name": display_name,
            "source": source,
            "shortcuts_path": str(shortcuts_path),
        }

    @staticmethod
    def _normalize_shortcuts_payload(shortcuts: dict | None) -> dict[str, Any]:
        payload = shortcuts if isinstance(shortcuts, dict) else {}
        container = payload.get("shortcuts")
        if isinstance(container, list):
            payload["shortcuts"] = {
                str(index): item for index, item in enumerate(container)
                if isinstance(item, dict)
            }
        elif not isinstance(container, dict):
            payload["shortcuts"] = {}
        return payload

    @staticmethod
    def _get_shortcut_field(entry: dict[str, Any], field_name: str, default: Any = ""):
        for key, value in entry.items():
            if str(key).strip().lower() == str(field_name).strip().lower():
                return value
        return default

    @staticmethod
    def _normalize_shortcut_path_value(value: Any) -> str:
        text = str(value or '').strip().strip('"')
        return os.path.normcase(os.path.normpath(text)) if text else ''

    def _load_shortcuts_file(self, shortcuts_path: str) -> dict[str, Any]:
        try:
            import vdf

            if os.path.exists(shortcuts_path):
                with open(shortcuts_path, 'rb') as f:
                    return self._normalize_shortcuts_payload(vdf.binary_load(f))
        except Exception as e:
            logger.warning(f"读取 shortcuts.vdf 失败，将使用空结构继续: {e}")
        return {"shortcuts": {}}

    def _save_shortcuts_file(self, shortcuts_path: str, payload: dict[str, Any]):
        import vdf

        target_path = Path(shortcuts_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path = target_path.with_suffix(".vdf.rmm.bak")
        had_original = target_path.exists()

        if had_original:
            shutil.copy2(target_path, backup_path)

        try:
            with open(target_path, 'wb') as f:
                vdf.binary_dump(self._normalize_shortcuts_payload(payload), f)
        except Exception:
            if had_original and backup_path.exists():
                shutil.copy2(backup_path, target_path)
            elif target_path.exists():
                target_path.unlink(missing_ok=True)
            raise

    def _build_managed_shortcut_entry(self, profile: Any, game_exe: str, game_dir: str, launch_options: str, existing_entry: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        构造管理器维护的非 Steam 游戏条目。
        关键点：
        1. `ShortcutPath` 不再写真实文件路径，而是写内部标记，方便后续幂等更新；
        2. 已存在的 `appid` 与 `tags` 会尽量保留，避免 Steam 重新生成后桌面协议变化。
        """
        profile_name = str(getattr(profile, 'name', None) or getattr(profile, 'id', 'Profile')).strip()
        marker = f"rmm://profile/{getattr(profile, 'id', '')}"
        existing = existing_entry or {}
        entry = {
            # Steam 当前 shortcuts.vdf 主流字段名以 AppName/Exe/StartDir 为准；
            # 这里按官方文档和现有客户端实际写回格式保持一致，避免因字段名漂移导致客户端不回写 appid。
            "AppName": f"RimWorld [{profile_name}]",
            "Exe": f'"{game_exe}"',
            "StartDir": f'"{game_dir}"',
            "icon": game_exe,
            "ShortcutPath": marker,
            "LaunchOptions": str(launch_options or ''),
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": self._get_shortcut_field(existing, "LastPlayTime", 0),
            "FlatpakAppID": "",
            "SortAs": self._get_shortcut_field(existing, "SortAs", ""),
            "tags": self._get_shortcut_field(existing, "tags", {}) or {},
        }
        existing_appid = self._get_shortcut_field(existing, "appid", None)
        if existing_appid not in (None, ""):
            entry["appid"] = existing_appid
        return entry

    def _find_managed_shortcut_entry(self, shortcuts: dict[str, Any], profile: Any, game_exe: str) -> tuple[str | None, dict[str, Any] | None]:
        container = self._normalize_shortcuts_payload(shortcuts).get("shortcuts", {})
        if not isinstance(container, dict):
            return None, None

        marker = f"rmm://profile/{getattr(profile, 'id', '')}"
        expected_name = f"RimWorld [{str(getattr(profile, 'name', None) or getattr(profile, 'id', 'Profile')).strip()}]"
        normalized_exe = self._normalize_shortcut_path_value(game_exe)

        for key, entry in container.items():
            if not isinstance(entry, dict):
                continue
            if str(self._get_shortcut_field(entry, "ShortcutPath", "")).strip() == marker:
                return str(key), entry

        for key, entry in container.items():
            if not isinstance(entry, dict):
                continue
            entry_name = str(self._get_shortcut_field(entry, "appname", "")).strip()
            entry_exe = self._normalize_shortcut_path_value(self._get_shortcut_field(entry, "exe", ""))
            if entry_name == expected_name and entry_exe == normalized_exe:
                return str(key), entry

        return None, None

    @staticmethod
    def _allocate_shortcut_index(shortcuts: dict[str, Any]) -> str:
        container = shortcuts.get("shortcuts", {})
        next_index = 0
        while str(next_index) in container:
            next_index += 1
        return str(next_index)

    @staticmethod
    def _shortcut_entry_to_launch_url(entry: dict[str, Any] | None) -> str:
        """
        将 shortcuts.vdf 中已有的非 Steam `appid` 转成 `steam://rungameid/...`。
        这里只在条目已拥有稳定 appid 时返回 URL；首次注册的新条目通常要等 Steam 重载后才会写回该值。
        """
        if not isinstance(entry, dict):
            return ""

        raw_appid = SteamManager._get_shortcut_field(entry, "appid", None)
        if raw_appid in (None, ""):
            return ""

        try:
            signed_appid = int(str(raw_appid).strip())
            unsigned_appid = struct.unpack("<I", struct.pack("<i", signed_appid))[0]
            rungameid = (unsigned_appid << 32) | 0x02000000
            return f"steam://rungameid/{rungameid}"
        except Exception:
            return ""

    @staticmethod
    def _appid_to_rungameid(appid: int | str | None) -> str:
        """将 Steam shortcut appid 转成 `steam://rungameid/...`。"""
        if appid in (None, ""):
            return ""
        try:
            raw_value = int(str(appid).strip())
            # Steam 日志中的 sanitize app id 是无符号 32 位整数；
            # shortcuts.vdf 旧格式里也可能出现有符号整数。
            # 这里统一折叠到 32 位无符号空间，兼容两种来源。
            unsigned_appid = raw_value & 0xFFFFFFFF
            rungameid = (unsigned_appid << 32) | 0x02000000
            return f"steam://rungameid/{rungameid}"
        except Exception:
            return ""

    def _get_console_log_path(self) -> str:
        steam_dir = str(self.steam_dir or '').strip()
        if not steam_dir:
            return ""
        return str(Path(steam_dir) / "logs" / "console_log.txt")

    def get_shortcut_log_probe(self, profile: Any, extra_args: list[str] | None = None) -> dict[str, Any]:
        """
        生成本次非 Steam 快捷方式 ID 解析所需的探针信息。
        由于 Steam 当前不会稳定把 shortcut appid 回写到 shortcuts.vdf，
        这里改为从 console_log.txt 中匹配本次 sanitize 记录。
        """
        game_dir = os.path.abspath(str(getattr(profile, 'game_install_path', '') or '').strip())
        game_exe = GameManager.detect_executable(game_dir)
        if not game_exe:
            raise FileNotFoundError(f"在安装目录下找不到游戏可执行文件: {game_dir}")

        launch_args = [str(item or '').strip() for item in (extra_args or []) if str(item or '').strip()]
        launch_options = subprocess.list2cmdline(launch_args) if launch_args else ""
        log_path = self._get_console_log_path()
        start_size = 0
        if log_path and os.path.exists(log_path):
            try:
                start_size = os.path.getsize(log_path)
            except OSError:
                start_size = 0

        return {
            "profile_id": str(getattr(profile, 'id', '') or '').strip(),
            "exe": os.path.abspath(game_exe),
            "launch_options": launch_options,
            "log_path": log_path,
            "log_start_offset": int(start_size),
            "registered_at_ms": int(time.time() * 1000),
        }

    def resolve_shortcut_launch_url_from_log_probe(self, probe: dict[str, Any]) -> dict[str, Any]:
        """
        从 Steam console_log.txt 中解析本次新注册 shortcut 的 appid。
        依据当前 Steam 实测行为：
        - Steam 会在日志里输出 sanitize shortcut app id ...
        - 但不会稳定地把 appid 回写进 shortcuts.vdf
        """
        log_path = str((probe or {}).get("log_path") or '').strip()
        exe_path = os.path.normcase(os.path.normpath(str((probe or {}).get("exe") or '').strip()))
        start_offset = int((probe or {}).get("log_start_offset") or 0)
        if not log_path or not os.path.exists(log_path):
            return {
                "ready": False,
                "appid": None,
                "launch_url": "",
                "source": "console_log_missing",
            }

        latest_appid = None
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                if start_offset > 0:
                    try:
                        f.seek(start_offset)
                    except OSError:
                        pass

                for raw_line in f:
                    line = str(raw_line or '').strip()
                    if 'sanitize shortcut app id' not in line.lower():
                        continue
                    match = re.search(r'sanitize shortcut app id "([^"]+)": replacing \d+ with (\d+)', line, flags=re.I)
                    if not match:
                        continue
                    candidate_exe = os.path.normcase(os.path.normpath(str(match.group(1) or '').strip()))
                    if candidate_exe != exe_path:
                        continue
                    latest_appid = int(match.group(2))
        except Exception as e:
            logger.debug(f"读取 Steam console_log 失败: {e}")
            return {
                "ready": False,
                "appid": None,
                "launch_url": "",
                "source": "console_log_read_failed",
            }

        launch_url = self._appid_to_rungameid(latest_appid)
        return {
            "ready": bool(launch_url),
            "appid": latest_appid,
            "launch_url": launch_url,
            "source": "console_log",
        }

    def register_profile_non_steam_shortcut(self, profile: Any, extra_args: list[str] | None = None) -> dict[str, Any]:
        """
        将指定环境登记为 Steam 非 Steam 游戏条目。
        注意：
        1. 该流程只负责维护 shortcuts.vdf；
        2. 首次创建条目时，Steam 往往要在下次读取后才会补全稳定 appid，因此桌面 `.url` 可能需要二次创建。
        """
        if platform.system() != "Windows":
            raise OSError("Steam 非 Steam 快捷方式仅支持 Windows")
        if self.is_steam_running():
            raise RuntimeError("Steam 正在运行，修改 shortcuts.vdf 可能在退出时被覆盖，请先完全退出 Steam。")

        game_dir = os.path.abspath(str(getattr(profile, 'game_install_path', '') or '').strip())
        game_exe = GameManager.detect_executable(game_dir)
        if not game_exe:
            raise FileNotFoundError(f"在安装目录下找不到游戏可执行文件: {game_dir}")

        launch_args = [str(item or '').strip() for item in (extra_args or []) if str(item or '').strip()]
        launch_options = subprocess.list2cmdline(launch_args) if launch_args else ""
        user_target = self.resolve_shortcuts_user()
        shortcuts_path = str(user_target["shortcuts_path"])
        shortcuts = self._load_shortcuts_file(shortcuts_path)
        entry_index, existing_entry = self._find_managed_shortcut_entry(shortcuts, profile, game_exe)
        is_new_entry = existing_entry is None
        if entry_index is None:
            entry_index = self._allocate_shortcut_index(shortcuts)

        new_entry = self._build_managed_shortcut_entry(
            profile=profile,
            game_exe=os.path.abspath(game_exe),
            game_dir=game_dir,
            launch_options=launch_options,
            existing_entry=existing_entry,
        )
        shortcuts["shortcuts"][entry_index] = new_entry
        self._save_shortcuts_file(shortcuts_path, shortcuts)
        logger.info(
            "已写入 Steam 非 Steam 环境条目: profile=%s, user=%s, index=%s, shortcuts=%s",
            getattr(profile, 'id', ''),
            user_target["user_id"],
            entry_index,
            shortcuts_path,
        )

        log_probe = self.get_shortcut_log_probe(profile, extra_args=extra_args)
        return {
            "user_id": user_target["user_id"],
            "user_display_name": user_target["display_name"],
            "shortcuts_vdf_path": shortcuts_path,
            "entry_index": entry_index,
            "entry_name": str(self._get_shortcut_field(new_entry, "AppName", "")).strip(),
            "is_new_entry": is_new_entry,
            "launch_url": "",
            "log_probe": log_probe,
            "requires_restart": True,
        }

    def get_registered_profile_non_steam_shortcut(self, profile: Any, log_probe: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        读取管理器维护的非 Steam 条目当前状态。
        该方法不会写文件，主要供“Steam 启动后轮询是否已生成稳定 shortcut id”使用。
        """
        if platform.system() != "Windows":
            raise OSError("Steam 非 Steam 快捷方式仅支持 Windows")

        game_dir = os.path.abspath(str(getattr(profile, 'game_install_path', '') or '').strip())
        game_exe = GameManager.detect_executable(game_dir)
        if not game_exe:
            raise FileNotFoundError(f"在安装目录下找不到游戏可执行文件: {game_dir}")

        user_target = self.resolve_shortcuts_user()
        shortcuts_path = str(user_target["shortcuts_path"])
        shortcuts = self._load_shortcuts_file(shortcuts_path)
        entry_index, entry = self._find_managed_shortcut_entry(shortcuts, profile, game_exe)
        log_status = self.resolve_shortcut_launch_url_from_log_probe(log_probe or {})
        launch_url = str(log_status.get("launch_url") or '').strip()

        return {
            "user_id": user_target["user_id"],
            "user_display_name": user_target["display_name"],
            "shortcuts_vdf_path": shortcuts_path,
            "entry_index": entry_index,
            "entry_name": str(self._get_shortcut_field(entry or {}, "AppName", "") or self._get_shortcut_field(entry or {}, "appname", "")).strip(),
            "launch_url": launch_url,
            "appid": log_status.get("appid"),
            "exists": bool(entry),
            "ready": bool(log_status.get("ready")),
            "source": log_status.get("source"),
            "log_probe": log_probe or {},
        }
    
    
    # =========================================================
    #  5. ACF & workshop_log 文件解析
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
    
    def _get_steamcmd_acf_path(self) -> Path:
        """返回 SteamCMD 专用的 appworkshop_294100.acf 路径。"""
        return Path(self.steamcmd_dir) / "steamapps" / "workshop" / f"appworkshop_{RIMWORLD_APP_ID}.acf"

    def _get_steamcmd_content_root(self) -> Path:
        """返回 SteamCMD 认定的 workshop 内容根目录。"""
        return Path(self.steamcmd_dir) / "steamapps" / "workshop" / "content" / RIMWORLD_APP_ID

    def _invalidate_steamcmd_cache(self) -> None:
        """SteamCMD ACF 被修正后，清空对应缓存，避免后续继续读到旧状态。"""
        self._cached_cmd_map = None
        self._last_cmd_log_mtime = 0
        self._last_cmd_acf_mtime = 0

    def reconcile_steamcmd_acf(self) -> dict[str, Any]:
        """
        收敛 SteamCMD 的 ACF 与磁盘实际状态。

        只处理一种高确定性脏状态：
        - ACF 中存在某个 workshop_id 的状态记录
        - 但对应的内容目录已经不存在

        扫描阶段只做这类“失效记录删除”，不尝试推导缺失目录以外的复杂状态。
        """
        acf_path = self._get_steamcmd_acf_path()
        content_root = self._get_steamcmd_content_root()
        if not acf_path.exists():
            return {"updated": False, "removed_ids": [], "acf_path": str(acf_path)}

        if self._has_running_steamcmd_process():
            logger.debug("Skip SteamCMD ACF reconcile because SteamCMD process is still running.")
            return {"updated": False, "removed_ids": [], "acf_path": str(acf_path), "skipped": "steamcmd_running"}

        try:
            import vdf

            with open(acf_path, 'r', encoding='utf-8', errors='ignore') as f:
                payload = cast(dict[str, Any], vdf.load(f) or {})
        except Exception as e:
            logger.warning(f"读取 SteamCMD ACF 失败，跳过收敛: {e}")
            return {"updated": False, "removed_ids": [], "acf_path": str(acf_path), "error": str(e)}

        app_workshop = cast(dict[str, Any], payload.get("AppWorkshop") or {})
        installed = cast(dict[str, Any], app_workshop.get("WorkshopItemsInstalled") or {})
        details = cast(dict[str, Any], app_workshop.get("WorkshopItemDetails") or {})
        if not installed and not details:
            return {"updated": False, "removed_ids": [], "acf_path": str(acf_path)}

        removed_ids: set[str] = set()
        normalized_installed = {str(item_id): data for item_id, data in installed.items()}
        normalized_details = {str(item_id): data for item_id, data in details.items()}

        all_item_ids = set(normalized_installed.keys()).union(normalized_details.keys())
        for item_id in all_item_ids:
            if not item_id.isdigit():
                # ACF 里若出现非数字键，说明状态已经异常，直接删掉避免后续解析炸掉。
                normalized_installed.pop(item_id, None)
                normalized_details.pop(item_id, None)
                removed_ids.add(item_id)
                continue
            if (content_root / item_id).exists():
                continue
            normalized_installed.pop(item_id, None)
            normalized_details.pop(item_id, None)
            removed_ids.add(item_id)

        if not removed_ids:
            return {"updated": False, "removed_ids": [], "acf_path": str(acf_path)}

        app_workshop["WorkshopItemsInstalled"] = normalized_installed
        app_workshop["WorkshopItemDetails"] = normalized_details
        payload["AppWorkshop"] = app_workshop

        backup_path = acf_path.with_suffix(".acf.rmm.bak")
        try:
            shutil.copy2(acf_path, backup_path)
        except Exception as e:
            logger.debug(f"创建 SteamCMD ACF 备份失败，将继续尝试直接写回: {e}")

        try:
            with open(acf_path, 'w', encoding='utf-8', newline='\n') as f:
                vdf.dump(payload, f, pretty=True)
        except Exception as e:
            if backup_path.exists():
                try:
                    shutil.copy2(backup_path, acf_path)
                except Exception as restore_error:
                    logger.error(f"恢复 SteamCMD ACF 备份失败: {restore_error}")
            raise RuntimeError(f"写回 SteamCMD ACF 失败: {e}") from e

        self._invalidate_steamcmd_cache()
        removed_ids_list = sorted(removed_ids)
        logger.info(
            "SteamCMD ACF 收敛完成: 移除 %s 条失效安装记录 (%s)",
            len(removed_ids_list),
            ", ".join(removed_ids_list[:10]) + (" ..." if len(removed_ids_list) > 10 else ""),
        )
        return {"updated": True, "removed_ids": removed_ids_list, "acf_path": str(acf_path)}

    def _has_running_steamcmd_process(self) -> bool:
        """判断当前管理器是否仍持有 SteamCMD 子进程，避免与其同时改写 ACF。"""
        with self._steamcmd_lock:
            for process in self._steamcmd_processes.values():
                try:
                    if process and process.poll() is None:
                        return True
                except Exception:
                    continue
        return False

    def get_acf_json(self, acf_path: str|Path|None=None) -> dict:
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
        acf_path = acf_path or self._get_acf_path()
        if not acf_path: return {}
        try:
            import vdf

            with open(acf_path, 'r', encoding='utf-8', errors='ignore') as f:
                payload = cast(dict[str, Any], vdf.load(f) or {})
            app_workshop = payload.get("AppWorkshop", {})
            if isinstance(app_workshop, dict):
                return cast(dict, app_workshop)
        except Exception as e:
            logger.debug(f"[get_acf_json] vdf 解析失败，将回退到兼容解析: {e}")
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

    def parse_acf_data(self, acf_json_data: dict) -> dict:
        """
        解析acf转成的json数据，提取模组当前的安装详情并标准化字段名。
        """
        installed = {
            str(item_id): data
            for item_id, data in cast(dict[str, Any], acf_json_data.get("WorkshopItemsInstalled", {})).items()
            if str(item_id).isdigit()
        }
        details = {
            str(item_id): data
            for item_id, data in cast(dict[str, Any], acf_json_data.get("WorkshopItemDetails", {})).items()
            if str(item_id).isdigit()
        }
        # 汇总所有的 item_id (可能有的已下载但在details里，有的在installed里)
        all_item_ids = set(installed.keys()).union(details.keys())
        
        parsed_acf = {}
        
        def format_timestamp(ts_str):
            """将Steam的Unix时间戳字符串转为毫秒级时间戳"""
            if not ts_str or ts_str == "0": return None
            return int(ts_str)*1000

        for item_id in all_item_ids:
            inst = installed.get(item_id, {})
            det = details.get(item_id, {})
            parsed_acf[item_id] = {
                "workshop_id": item_id,
                "size_bytes": int(inst.get("size", 0)),
                # 本地实际落地文件的清单ID
                "local_manifest": inst.get("manifest") or det.get("manifest"),
                # 线上(或缓存的最新)目标清单ID
                "remote_manifest": det.get("latest_manifest", det.get("manifest")),
                # 模组作者发布版本的真实时间
                "installed_version_time": format_timestamp(inst.get("timeupdated") or det.get("timeupdated")),
                "latest_version_time": format_timestamp(det.get("latest_timeupdated") or det.get("timeupdated")),
                # Steam客户端最后一次检查该Mod状态的时间
                "last_checked_time": format_timestamp(det.get("timetouched")),
                # 是否确实安装在硬盘上
                "is_installed": item_id in installed,
                "is_subscribed": item_id in details 
            }
            # 衍生判断：是否需要更新 (本地与线上清单不一致，且都存在)
            loc_man = parsed_acf[item_id]["local_manifest"]
            rem_man = parsed_acf[item_id]["remote_manifest"]
            parsed_acf[item_id]["needs_update"] = bool(loc_man and rem_man and loc_man != rem_man)
        
        return parsed_acf

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

    def _get_steam_log_path(self, use_steamcmd: bool = False):
        """
        推断 Steam 客户端日志路径
        通常在 Steam 安装目录/logs/workshop_log.txt
        """
        if use_steamcmd: 
            return str(Path(self.steamcmd_dir) / "logs" / "workshop_log.txt")
        
        # 确保有 Steam 安装目录
        if not self.steam_dir: return None
            
        try:
            log_dir = os.path.join(self.steam_dir, "logs")
            log_file = os.path.join(log_dir, "workshop_log.txt")
            if os.path.exists(log_file): return log_file
            # 如果反推失败，尝试默认路径 (Windows)
            if platform.system() == "Windows":
                default_path = r"C:\Program Files (x86)\Steam\logs\workshop_log.txt"
                if os.path.exists(default_path):
                    return str(default_path)
        except Exception as e:
            logger.error(f"Failed to parse Steam log path: {e}")
            
        return None

    def parse_workshop_log(self, log_path: str|Path|None=None, target_appid: str=RIMWORLD_APP_ID) -> dict:
        """
        解析 Steam workshop_log.txt，提取指定 AppID 的模组操作历史。
        归并相似动作，智能识别【订阅、取订、更新、同步】的最新时间。
        """
        log_path = log_path or self._get_steam_log_path()
        if not log_path or not os.path.exists(log_path): return {}
        # 预编译正则：匹配时间、AppID、以及包含 item 或 handle 的消息
        log_pattern = re.compile(r'\[(.*?)\] \[AppID (\d+)\] (.*)')
        id_pattern = re.compile(r'(?:item|handle) (\d+)')
        target_appid_str = str(target_appid)
        items_history = {}
        # 定义动作组关键词，用于智能归类
        GROUP_SUBSCRIBE = ["Subscribed to item", "added subscribed item"]
        GROUP_UNSUBSCRIBE = ["Unsubscribed from item", "removing unsubscribed", "removing unused item"]
        GROUP_SYNC = ["changed cached item"]
        GROUP_ERROR = ["failed :", "skipping item", "error"]
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    match = log_pattern.match(line)
                    if not match: continue
                    time_str, appid, msg = match.groups()
                    if appid != target_appid_str: continue
                    # 提取 Workshop ID
                    id_match = id_pattern.search(msg)
                    if not id_match: continue
                    item_id = id_match.group(1)
                    # 初始化记录项
                    if item_id not in items_history:
                        items_history[item_id] = {
                            "workshop_id": item_id,
                            "log_last_download_time": None,      # 下载完成时间
                            "log_last_subscribed_time": None,    # 订阅时间 (含创建订阅)
                            "log_last_unsubscribed_time": None,  # 取订时间 (含移除项目)
                            "log_last_sync_time": None,          # 元数据同步时间
                            "log_last_manifest": None,           # 清单 ID
                            "log_last_error": None,              # 错误信息
                            "is_subscribed": None                # 逻辑订阅状态
                        }
                    item = items_history[item_id]
                    time_stamp = int(parser.parse(time_str).timestamp() * 1000)
                    # --- 智能归类解析 ---
                    # 1. 订阅动作组
                    if any(k in msg for k in GROUP_SUBSCRIBE):
                        item["log_last_subscribed_time"] = time_stamp
                        item["is_subscribed"] = True
                    # 2. 取订/移除动作组
                    elif any(k in msg for k in GROUP_UNSUBSCRIBE):
                        item["log_last_unsubscribed_time"] = time_stamp
                        item["is_subscribed"] = False
                    # 3. 同步/缓存变动组 (新增)
                    elif any(k in msg for k in GROUP_SYNC):
                        item["log_last_sync_time"] = time_stamp
                    # 4. 下载成功逻辑
                    if "result : OK" in msg:
                        item["log_last_download_time"] = time_stamp
                        item["log_last_error"] = None # 成功时清理旧错误
                    # 5. 错误识别组
                    elif any(k in msg for k in GROUP_ERROR):
                        error_match = re.search(r'(?:failed :|result =|error)\s*(.*)', msg, re.I)
                        if error_match:
                            item["log_last_error"] = error_match.group(1).strip()
                    # 6. 提取清单 ID
                    manifest_match = re.search(r'new (?:manifest|handle) (\d+)', msg)
                    if manifest_match:
                        item["log_last_manifest"] = manifest_match.group(1)
            return items_history
        except Exception as e:
            from backend.utils.logger import logger
            logger.error(f"解析全量日志失败: {e}", exc_info=True)
            return {}
    
    def _merge_acf_and_log(self, acf_data: dict, log_data: dict) -> dict:
        """
        合并 ACF 数据和日志数据，填充缺失字段。
        """
        # 取并集：有的模组可能被删了只在历史日志里有，有的只在ACF里有
        all_item_ids = {
            str(item_id)
            for item_id in set(log_data.keys()).union(acf_data.keys())
            if str(item_id).isdigit()
        }
        merged_dict = {}
        for item_id in sorted(all_item_ids, key=lambda x: int(x)): # 按ID排序方便查看
            item_log = log_data.get(item_id, {})
            item_acf = acf_data.get(item_id, {})
            # 构建合理的最终字典
            merged_item = {
                "workshop_id": item_id,
                "is_subscribed": item_acf.get("is_subscribed"),    # 从日志推断的订阅状态
                "is_installed": item_acf.get("is_installed", False), # 文件是否真实存在
                "needs_update": item_acf.get("needs_update", False), # 是否有更新等待下载
                "has_error": bool(item_log.get("log_last_error")),   # 下载/校验是否报错
                "error_detail": item_log.get("log_last_error"),
                
                # --- 物理信息 (以 ACF 为准) ---
                "size_bytes": item_acf.get("size_bytes", 0),
                "local_manifest": item_acf.get("local_manifest") or item_log.get("log_last_manifest"),
                "remote_manifest": item_acf.get("remote_manifest"),

                # Steam本地实际下载完毕的时间 (提取自日志)
                "time_downloaded": item_log.get("log_last_download_time"),
                # 玩家行为时间
                "time_subscribed": item_log.get("log_last_subscribed_time"),
                "time_unsubscribed": item_log.get("log_last_unsubscribed_time"),
                
                # 模组作者最后一次在创意工坊上传更新的时间 (当前安装版 与 线上最新版)
                "installed_version_time": item_acf.get("installed_version_time"),
                "latest_version_time": item_acf.get("latest_version_time"),
                
                # Steam客户端最后一次验证该Mod状态的时间
                "time_last_checked": item_acf.get("last_checked_time"),
                "time_last_sync": item_log.get("log_last_sync_time"),
            }
            # 容错：如果日志里记录没有订阅，但ACF显示安装，则有可能处于“孤儿”状态(退订未删)
            # 容错：有些刚发起的下载，在ACF里还没生成，但在日志里存在
            merged_dict[item_id] = merged_item
            
        return merged_dict
    
    def _get_merged_data_efficiently(self):
        """带有脏检查的高效数据获取"""
        acf_path = self._get_acf_path()
        log_path = self._get_steam_log_path()
        
        # 检查文件是否变动
        acf_mtime = os.path.getmtime(acf_path) if acf_path and os.path.exists(acf_path) else 0
        log_mtime = os.path.getmtime(log_path) if log_path and os.path.exists(log_path) else 0
        
        if acf_mtime == self._last_acf_mtime and log_mtime == self._last_log_mtime:
            return self._cached_merged_data
        
        # 只有变动时才解析
        self._cached_merged_data = self.workshop_merged_data()
        self._last_acf_mtime = acf_mtime
        self._last_log_mtime = log_mtime
        return self._cached_merged_data
    
    def workshop_merged_data(self) -> dict:
        """
        合并日志和ACF数据，并生成一份极其详尽的 JSON 列表供管理器直接使用。
        返回格式：
        [
            {
                "workshop_id": "123456789",
                "is_subscribed": true,
                "is_installed": true,
                "needs_update": false,
                "has_error": false,
                "error_detail": null,
                "size_bytes": 123456789,
                "local_manifest": "12345678901234567890",
                "remote_manifest": "12345678901234567890",
                "time_downloaded": "2023-01-01 00:00:00",
                "time_subscribed": "2023-01-01 00:00:00",
                "time_unsubscribed": null,
                "installed_version_time": "2023-01-01 00:00:00",
                "latest_version_time": "2023-01-01 00:00:00",
                "time_last_checked": "2023-01-01 00:00:00",
            }
        ]
        """
        # 获取分别解析后的字典结构
        log_path = self._get_steam_log_path()
        acf_path = self._get_acf_path()
        # 获取文件的最新修改时间 (os.path.getmtime 非常快)
        log_mtime = os.path.getmtime(log_path) if log_path and os.path.exists(log_path) else 0
        acf_mtime = os.path.getmtime(acf_path) if acf_path and os.path.exists(acf_path) else 0
        # 命中缓存，直接返回内存数据 (0 开销！)
        if self._cached_ws_map is not None and \
           log_mtime == self._last_ws_log_mtime and \
           acf_mtime == self._last_ws_acf_mtime:
            return self._cached_ws_map
        # 只有文件真变了，才去跑耗时的正则和 JSON 解析
        log_data = self.parse_workshop_log()
        acf_json = self.get_acf_json()
        acf_data = self.parse_acf_data(acf_json)
        
        self._cached_ws_map = self._merge_acf_and_log(acf_data, log_data)
        self._last_ws_log_mtime = log_mtime
        self._last_ws_acf_mtime = acf_mtime
        
        return self._cached_ws_map
        
    def steamcmd_merged_data(self) -> dict:
        """
        获取 steamcmd 下载的创意工坊模组的ACF数据
        返回格式与 workshop_merged_data 相同
        """
        steamcmd_acf_path = self._get_steamcmd_acf_path()
        steamcmd_log_path = Path(self.steamcmd_dir) / "logs" / "workshop_log.txt"
        
        # 获取文件的最新修改时间 (os.path.getmtime 非常快)
        log_mtime = os.path.getmtime(steamcmd_log_path) if steamcmd_log_path and os.path.exists(steamcmd_log_path) else 0
        acf_mtime = os.path.getmtime(steamcmd_acf_path) if steamcmd_acf_path and os.path.exists(steamcmd_acf_path) else 0
        # 命中缓存，直接返回内存数据 (0 开销！)
        if self._cached_cmd_map is not None and \
           log_mtime == self._last_cmd_log_mtime and \
           acf_mtime == self._last_cmd_acf_mtime:
            return self._cached_cmd_map
        if steamcmd_acf_path.exists():
            acf_json = self.get_acf_json(steamcmd_acf_path)
            acf_data = self.parse_acf_data(acf_json)
        else:
            acf_data = {}
        if steamcmd_log_path.exists():
            log_data = self.parse_workshop_log(log_path=steamcmd_log_path)
        else:
            log_data = {}
        # 合并数据
        self._cached_cmd_map = self._merge_acf_and_log(acf_data, log_data)
        self._last_cmd_log_mtime = log_mtime
        self._last_cmd_acf_mtime = acf_mtime
        
        # 合并数据
        return self._cached_cmd_map
    
    def get_item_timeline(self, workshop_id: str, is_steamcmd: bool = False) -> list:
        """
        解析 workshop_log.txt，提取特定 Mod 的所有历史轨迹
        逻辑：时间倒序为主，同时间按 ACTION_MAP 顺序倒序（显示该时刻最后的动作），并去重
        """
        log_path = self._get_steam_log_path(is_steamcmd)
        if not log_path or not os.path.exists(log_path): return []
        
        target_id_str = str(workshop_id)
        raw_events = []
        
        # 预编译正则
        log_pattern = re.compile(r'\[(.*?)\] \[AppID 294100\] (.*)')
        
        # 动作映射：顺序代表了在同一时间点发生的逻辑先后顺序
        # 我们给每个动作一个数字优先级 (index)
        ACTION_MAP = {
            "Subscribed to item": {"action": "subscribe", "title": "订阅成功", "color": "primary"},
            "added subscribed item": {"action": "subscribe", "title": "创建项目", "color": "primary"},
            "changed cached item": {"action": "update", "title": "检测更新", "color": "success"},
            "requested by App": {"action": "download", "title": "请求下载", "color": "primary"},
            "Starting Workshop download": {"action": "download", "title": "开始下载", "color": "primary"},
            "Unsubscribed from item": {"action": "unsubscribe", "title": "取消订阅", "color": "danger"},
            "removing unsubscribed": {"action": "remove", "title": "移除项目", "color": "danger"},
            "removing unused item": {"action": "remove", "title": "清理冗余", "color": "danger"},
            "failed": {"action": "error", "title": "操作失败", "color": "danger"}
        }
        
        # 将 key 提取为列表，方便获取优先级 index
        PRIORITY_KEYS = list(ACTION_MAP.keys())

        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or target_id_str not in line: continue
                    
                    match = log_pattern.match(line)
                    if not match: continue
                    
                    time_str, msg = match.groups()
                    
                    # 判定行为
                    event_type = "info"
                    event_title = "未知动作"
                    event_color = "text-dim"
                    priority = -1 # 默认优先级
                    
                    # 匹配定义好的动作
                    for idx, key in enumerate(PRIORITY_KEYS):
                        if key in msg:
                            meta = ACTION_MAP[key]
                            event_type = meta["action"]
                            event_title = meta["title"]
                            event_color = meta["color"]
                            priority = idx
                            break
                    # 特殊逻辑：下载/更新成功 (这是逻辑上的最后一步)
                    if "result : OK" in msg and ("Download" in msg or "download" in msg):
                        event_type = "download_ok"
                        event_title = "下载成功"
                        event_color = "success"
                        priority = 100 # 极高优先级，确保在同一秒内排在最前
                    # 如果依然没匹配到关键动作，且不是我们要找的 ID 相关消息，则丢弃
                    if priority == -1 and not ("result : OK" in msg):
                        continue
                    time_stamp = int(parser.parse(time_str).timestamp() * 1000)
                    raw_events.append({
                        "time": time_stamp,
                        "type": event_type,
                        "title": event_title,
                        "desc": msg,
                        "color": event_color,
                        "priority": priority # 仅用于内部排序
                    })
            if not raw_events: return []

            # --- 核心排序逻辑 ---
            # 1. 时间倒序 (x['time'] 越大越靠前)
            # 2. 优先级倒序 (x['priority'] 越大越靠前，代表同一秒内的最终状态)
            raw_events.sort(key=lambda x: (-x['time'], -x['priority']))

            # --- 流式去重 ---
            final_timeline = []
            for e in raw_events:
                if not final_timeline:
                    final_timeline.append(e)
                    continue
                
                last = final_timeline[-1]
                # 如果【时间一致】且【标题一致】，视为重复动作（例如重复的请求），只保留最高优先级的那个
                # if e['time'] == last['time'] and e['title'] == last['title']:
                #     continue
                
                # 如果时间一致但动作不同，由于上面已经按 priority 排过序了，
                # 此时 e 的优先级一定低于 last，且由于是不同动作，我们会保留它们（形成精细的时间线）
                # 但如果用户希望一秒内只报一个最关键的，可以去掉标题判断。这里建议保留标题判断。
                final_timeline.append(e)

            # 格式化输出：将时间戳转回可读字符串发送给前端，或者由前端处理
            # 这里建议保留时间戳，增加一个 human_time 字段
            for item in final_timeline:
                # 移除内部使用的 priority 字段
                item.pop("priority")
                
            return final_timeline
            
        except Exception as e:
            logger.error(f"解析 Mod {target_id_str} 时间线失败: {e}", exc_info=True)
            return []
    
if __name__ == "__main__":
    steam_mgr = SteamManager()
    data = steam_mgr.workshop_merged_data()
    installed_mods = { id: da for id, da in data.items() if da.get('is_installed') }
    not_installed_mods = { id: da for id, da in data.items() if not da.get('is_installed') }
    if data:
        # print(f"Total items: {len(data)} First item:\n", data)
        print(f"Total items: {len(data)} Installed items: {len(installed_mods)} Uninstall items: {len(not_installed_mods)}")
        print(not_installed_mods)
    # data2 = steam_mgr.steamcmd_merged_data()
    # if data2:
    #     print(f"Total items: {len(data2)} First item:\n", data2)

    # 测试获取一个合集的内容
    # url = "https://steamcommunity.com/sharedfiles/filedetails/?id=3670074636"
    # mod_ids = steam_mgr.get_collection_items(url)
    # print(f"该合集包含以下模组: {mod_ids}")
    timeline = steam_mgr.get_item_timeline("3424068498")
    print(timeline)
