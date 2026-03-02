# backend/managers/mgr_steam.py
from datetime import datetime
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
from dateutil import parser
from typing import Optional, cast
from json_repair import repair_json
from pathlib import Path
import requests

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

# RimWorld App ID
RIMWORLD_APP_ID = "294100"

# =========================================================
#  独立 Worker 函数 (由 main.py 在子进程调用)
# =========================================================
def run_steam_worker(action: str, payload: str):
    """
    独立进程运行的 Steam API 代理。
    支持处理单个 ID 或以逗号分隔的批量 ID。
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
        # 生成一个 Task ID 并返回给前端，以便前端监听
        task_id = "steamcmd_batch_" + str(time.time_ns() // 1000000)
        
        commands = ["login anonymous"]
        for mid in workshop_ids:
            commands.append(f"workshop_download_item {RIMWORLD_APP_ID} {mid}")
        commands.append("quit")
        t = threading.Thread(target=self._run_steamcmd_process, args=(commands, workshop_ids, task_id))
        t.start()
        return t

    def _run_steamcmd_process(self, commands, mod_ids, task_id):
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
        self._emit_progress_event(task_id, "正在连接Steam服务器...", 0, TaskStatus.RUNNING, target_dir, "SteamCMD")

        try:
            args = [self.steamcmd_exe]
            for cmd in commands:
                args.append(f"+{cmd}")
            # Windows 下隐藏控制台窗口
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=current_env,    # 传递合并后的环境变量
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                cwd=self.steamcmd_dir,
                bufsize=1 # 行缓冲
            )

            # 增强版正则：SteamCMD 的输出格式多样
            progress_pattern = re.compile(r"progress: (\d+\.\d+)")
            # 也可以匹配 [ 25%] 这种格式
            bracket_pattern = re.compile(r"\[\s*(\d+)%\]")
            success_pattern = re.compile(r"Success\. Downloaded item (\d+)")

            current_item_idx = 0
            total_items = len(mod_ids)
            
            while True:
                line = process.stdout.readline() # type: ignore
                if not line and process.poll() is not None: break
                if not line: continue
                line = line.strip()

                # 解析百分比进度
                percent_val = 0
                m_prog = progress_pattern.search(line)
                m_bracket = bracket_pattern.search(line)
                
                if m_prog:
                    percent_val = float(m_prog.group(1))
                elif m_bracket:
                    percent_val = float(m_bracket.group(1))

                if percent_val > 0:
                    # 整体百分比 = (已完成数 + 当前项进度) / 总数
                    total_percent = ((current_item_idx + percent_val / 100) / total_items) * 100
                    self._emit_progress_event(
                        task_id, 
                        f"正在下载 ({current_item_idx + 1}/{total_items})", 
                        int(total_percent), 
                        TaskStatus.RUNNING, 
                        target_dir, "SteamCMD"
                    )

                item_id = success_pattern.search(line)
                if item_id: item_id = item_id.group(1)
                
                # 解析成功单项
                if item_id:
                    current_item_idx += 1
                    # 每完成一个，强制刷新一次进度
                    total_percent = (current_item_idx / total_items) * 100
                    logger.info(f"SteamCMD finished one item: {item_id}. ({current_item_idx}/{total_items}) ")
                    self._emit_progress_event(
                        task_id, 
                        f"正在下载 ({current_item_idx}/{total_items})", 
                        int(total_percent), 
                        TaskStatus.RUNNING if current_item_idx < total_items else TaskStatus.COMPLETED, 
                        target_dir, "SteamCMD"
                    )

            if process.returncode == 0:
                self._emit_progress_event(task_id, f"全部下载完成 ({total_items})", 100, TaskStatus.COMPLETED, target_dir, "SteamCMD")
            else:
                self._emit_progress_event(task_id, f"SteamCMD 异常退出: {process.returncode}", 0, TaskStatus.ERROR, target_dir, "SteamCMD")

        except Exception as e:
            logger.error(f"SteamCMD execution failed: {e}")
            self._emit_progress_event(task_id, str(e), 0, TaskStatus.ERROR, target_dir, "SteamCMD")
            

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
        current_exe = sys.executable
        is_frozen = getattr(sys, 'frozen', False)
        for i in range(0, len(id_list), BATCH_SIZE):
            batch = id_list[i : i + BATCH_SIZE]
            payload = ",".join(batch)
            cmd = [current_exe]
            if not is_frozen:
                cmd.append(str(BASE_RESOURCE_DIR / "main.py"))
            cmd.extend(["--steam-worker", action, payload])
            try:
                # 统一使用隐藏窗口启动
                si = None
                if platform.system() == "Windows":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(
                    cmd, cwd=self.agent_dir, capture_output=True, 
                    text=True, startupinfo=si, encoding='utf-8'
                )
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
                if item and item.get('is_installed') or folder_exists:
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
                "start_time": time.time()
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
                self._active_tasks.pop(task_id)
                logger.info(f"主动终止了对任务的监控: {task_id}")
                
                # 给前端发送一个被终止的状态，让 Promise 能够 Reject
                self._emit_progress_event(
                    tid=task_id,
                    msg="任务已取消",
                    percent=0,
                    status=TaskStatus.ERROR,
                    file_path=settings.config.workshop_mods_path, 
                    title="Steam 托管",
                    error="用户主动取消了任务监控"
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
                                # 条件1：完美移除 (物理消失 + Steam记录消失)
                                if not is_installed_acf and not folder_exists:
                                    finished_count += 1
                                # 条件2：容错放行 (物理已经消失，且指令发出了超过 3 秒)
                                # 对付手动删文件导致 Steam 装死不更新 ACF 的情况
                                elif not folder_exists and (time.time() - start_time > 3):
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
                        error="; ".join(errors) if errors else None
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
    
    def _emit_progress_event(self, tid, msg, percent, status, file_path='', title='', error=None):
        """对接 EventBus 格式"""
        payload = {
            "id": tid,
            "filename": msg,
            "file_path": file_path, # Steam 模组路径由前端根据 ID 自行推断或暂不填
            "status": status.value,
            "total": 100,
            "current": percent,
            "percent": percent,
            "speed": title,
            "error": error
        }
        EventBus.emit("download-progress", payload)


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
        installed = acf_json_data.get("WorkshopItemsInstalled", {})
        details = acf_json_data.get("WorkshopItemDetails", {})
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
                "is_installed": item_id in installed
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
        all_item_ids = set(log_data.keys()).union(acf_data.keys())
        merged_dict = {}
        for item_id in sorted(all_item_ids, key=lambda x: int(x)): # 按ID排序方便查看
            item_log = log_data.get(item_id, {})
            item_acf = acf_data.get(item_id, {})
            # 构建合理的最终字典
            merged_item = {
                "workshop_id": item_id,
                "is_subscribed": item_log.get("is_subscribed"),    # 从日志推断的订阅状态
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
        log_data = self.parse_workshop_log()
        acf_json = self.get_acf_json()
        acf_data = self.parse_acf_data(acf_json)
        # 合并数据
        return self._merge_acf_and_log(acf_data, log_data)
        
    def steamcmd_merged_data(self) -> dict:
        """
        获取 steamcmd 下载的创意工坊模组的ACF数据
        返回格式与 workshop_merged_data 相同
        """
        steamcmd_acf_path = Path(self.steamcmd_dir) / "steamapps" / "workshop" / f"appworkshop_{RIMWORLD_APP_ID}.vdf"
        steamcmd_log_path = Path(self.steamcmd_dir) / "logs" / "workshop_log.txt"
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
        return self._merge_acf_and_log(acf_data, log_data)
    
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
    # data = steam_mgr.workshop_merged_data()
    # if data:
    #     print(f"Total items: {len(data)} First item:\n", data)
    # data2 = steam_mgr.steamcmd_merged_data()
    # if data2:
    #     print(f"Total items: {len(data2)} First item:\n", data2)

    # 测试获取一个合集的内容
    # url = "https://steamcommunity.com/sharedfiles/filedetails/?id=3670074636"
    # mod_ids = steam_mgr.get_collection_items(url)
    # print(f"该合集包含以下模组: {mod_ids}")
    timeline = steam_mgr.get_item_timeline("3424068498")
    print(timeline)
