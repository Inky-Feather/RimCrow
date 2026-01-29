# backend/managers/mgr_steam.py
import os
import platform
import subprocess
import threading
import time
import re
import zipfile
import shutil
import importlib.util
from typing import Optional

# 尝试导入 steamworks，如果环境没配好暂时忽略，防止启动报错
try:
    from steamworks.steamworks import STEAMWORKS
except ImportError:
    STEAMWORKS = None

from backend.utils.logger import logger
from backend.utils.event_bus import EventBus
from backend.settings import settings
from backend.managers.mgr_download import DownloadManager, TaskStatus

# RimWorld App ID
RIMWORLD_APP_ID = "294100"

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
        
        # Steamworks 路径
        self.steamworks_dir = os.path.join(self.tools_dir, "steamworks")
        self._steam_instance = None
        self._is_steam_initialized = False

        # 确保目录存在
        os.makedirs(self.steamcmd_dir, exist_ok=True)
        os.makedirs(self.steamworks_dir, exist_ok=True)
        
        # 初始化状态
        self.steamcmd_ready = os.path.exists(self.steamcmd_exe)
        
        # 尝试初始化 Steamworks (如果本地有 DLL)
        self._init_steamworks_api()

    def _get_steamcmd_exe_path(self):
        system = platform.system()
        if system == "Windows":
            return os.path.join(self.steamcmd_dir, "steamcmd.exe")
        elif system == "Linux":
            return os.path.join(self.steamcmd_dir, "steamcmd.sh")
        elif system == "Darwin":
            return os.path.join(self.steamcmd_dir, "steamcmd.sh")
        return ""

    # =========================================================
    #  1. 环境准备 (下载工具)
    # =========================================================

    def ensure_tools(self, download_mgr: DownloadManager):
        """
        检查工具状态：
        1. SteamCMD: 不存在则下载
        2. Steamworks DLL: 不存在则尝试从本地库复制
        """
        tasks = []
        
        # 1. 检查 SteamCMD
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

        # 2. 检查 SteamworksPy DLLs (必需文件)
        # 目标文件 (Windows为例)
        target_dll_name = "SteamworksPy64.dll" if platform.system() == "Windows" else "libSteamworksPy.so"
        target_api_name = "steam_api64.dll" if platform.system() == "Windows" else "libsteam_api.so"
        
        # 检查项目根目录是否有这两个文件
        root_dll_path = os.path.join(self.project_root, target_dll_name)
        root_api_path = os.path.join(self.project_root, target_api_name)
        
        if not os.path.exists(root_dll_path) or not os.path.exists(root_api_path):
            logger.info("Steamworks DLLs missing in root, trying to copy from site-packages...")
            success = self._copy_steamworks_from_package(target_dll_name, target_api_name)
            
            if success:
                logger.info("Steamworks DLLs copied successfully.")
                # 立即尝试初始化，不需要等待任务回调
                self._init_steamworks_api()
            else:
                logger.error("Failed to find Steamworks DLLs in site-packages. Please reinstall steamworks-py.")
                # 这里也可以保留原来的下载逻辑作为最后的 fallback，但通常没必要

        return tasks

    def _copy_steamworks_from_package(self, dll_name, api_name):
        """
        尝试找到 pip 安装的 steamworkspy 目录，并将其中的 DLL 复制到项目根目录
        """
        try:
            # 找到 steamworks 包的位置
            spec = importlib.util.find_spec("steamworkspy")
            if not spec or not spec.origin:
                return False
            
            # 获取包所在的文件夹路径 (例如 .../site-packages/steamworkspy/__init__.py -> .../site-packages/steamworks)
            package_dir = os.path.dirname(spec.origin)
            
            # 源文件路径
            src_dll = os.path.join(package_dir, dll_name)
            src_api = os.path.join(package_dir, api_name)
            
            # 目标路径 (项目根目录)
            dst_dll = os.path.join(self.project_root, dll_name)
            dst_api = os.path.join(self.project_root, api_name)
            
            # 执行复制
            if os.path.exists(src_dll):
                shutil.copy2(src_dll, dst_dll)
            else:
                logger.warning(f"Source DLL not found: {src_dll}")
                return False

            if os.path.exists(src_api):
                shutil.copy2(src_api, dst_api)
            else:
                logger.warning(f"Source API not found: {src_api}")
                # 有些版本的包可能只带了 SteamworksPy64.dll 而依赖系统安装 steam_api64，视情况而定
                # 但通常包里两个都有
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error copying Steamworks files: {e}")
            return False

    def post_download_setup(self, task_type, file_path):
        """下载完成后的解压/配置回调"""
        if task_type == "steamcmd":
            # 解压
            try:
                import zipfile
                if file_path.endswith('.zip'):
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(self.steamcmd_dir)
                    os.remove(file_path) # 删除压缩包
                    self.steamcmd_ready = True
                    logger.info("SteamCMD installed successfully.")
                # Linux/Mac 需要 tar 解压和 chmod +x
            except Exception as e:
                logger.error(f"Failed to extract SteamCMD: {e}")

        elif task_type in ["steamworks_lib", "steam_api"]:
            # 将 DLL 复制到项目根目录 (Python 加载动态库通常在运行目录查找)
            try:
                filename = os.path.basename(file_path)
                dest = os.path.join(self.project_root, filename)
                shutil.copy2(file_path, dest)
                logger.info(f"Deployed {filename} to root.")
                # 尝试重新初始化
                self._init_steamworks_api()
            except Exception as e:
                logger.error(f"Failed to deploy Steamworks DLL: {e}")

    # =========================================================
    #  2. SteamCMD 功能 (Workshop 下载)
    # =========================================================

    def download_workshop_items(self, mod_ids: list):
        """
        调用 SteamCMD 下载模组
        :return: Thread object (run in background)
        """
        if not self.steamcmd_ready:
            raise Exception("SteamCMD is not installed.")
        
        # 构造 SteamCMD 脚本
        # 格式:
        # login anonymous
        # workshop_download_item 294100 <id>
        # ...
        # quit
        commands = ["login anonymous"]
        for mid in mod_ids:
            commands.append(f"workshop_download_item {RIMWORLD_APP_ID} {mid}")
        commands.append("quit")
        
        # 启动线程执行
        t = threading.Thread(target=self._run_steamcmd_process, args=(commands, mod_ids))
        t.start()
        return t

    def _run_steamcmd_process(self, commands, mod_ids):
        """执行 SteamCMD 进程并解析输出"""
        # 伪造一个 Task ID 用于前端进度条显示
        fake_task_id = "steamcmd_batch_" + str(int(time.time()))
        
        # 初始事件
        self._emit_progress(fake_task_id, "Connecting to Steam...", 0, TaskStatus.RUNNING)

        try:
            # 构造进程参数
            args = [self.steamcmd_exe]
            for cmd in commands:
                args.append(f"+{cmd}")
            
            # 启动进程 (Windows下隐藏窗口)
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, # 文本模式读取
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                cwd=self.steamcmd_dir # 在 steamcmd 目录运行
            )

            # 正则匹配进度: "Update state (0x61) downloading, progress: 25.50 (1234 / 5678)"
            # 或者 "Redirecting downloading for..."
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
                # logger.debug(f"[SteamCMD] {line}") # 调试用，生产环境可能太吵

                # 1. 匹配进度
                match = progress_pattern.search(line)
                if match:
                    percent = float(match.group(1))
                    # 计算总进度: (当前第几个 + 当前文件进度/100) / 总数
                    total_percent = ((current_item_idx + percent / 100) / total_items) * 100
                    self._emit_progress(fake_task_id, f"Downloading item {current_item_idx+1}/{total_items}", int(total_percent), TaskStatus.RUNNING)

                # 2. 匹配完成一个
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
        # 复用 DownloadManager 的事件格式，以便前端 StatusBar 通用
        EventBus.emit("download-progress", {
            "id": tid,
            "filename": msg, # 借用 filename 字段显示消息
            "status": status.value,
            "percent": percent,
            "speed": "SteamCMD", # 特殊标记
            "total": 100,
            "current": percent
        })

    # =========================================================
    #  3. Steamworks 功能 (本地订阅/取消)
    # =========================================================
    def _workshop_callback(self, res_struct):
        """
        SubscribeItem传入的回调函数（Steam创意工坊订阅完成）
        :param res_struct: 回调结构体对象
        """
        print(f"Workshop callback: {res_struct}")
        
        
    def _init_steamworks_api(self):
        """初始化 SteamworksPy"""
        if self._is_steam_initialized: return
        if not STEAMWORKS: 
            logger.warning("Steamworks API not found. Please ensure it's in the same directory as this script.")
            return

        # SteamworksPy 需要当前目录下有 steam_appid.txt
        appid_path = os.path.join(self.project_root, "steam_appid.txt")
        if not os.path.exists(appid_path):
            with open(appid_path, "w") as f:
                f.write(RIMWORLD_APP_ID)

        try:
            # 这里的 binary_path 指的是 steam_api64.dll 所在路径
            # 如果不传，默认找当前目录。我们在 post_download_setup 中已经复制到根目录了。
            self._steam_instance = STEAMWORKS()
            self._steam_instance.initialize()
            
            my_steam64 = self._steam_instance.Users.GetSteamID()
            my_steam_level = self._steam_instance.Users.GetPlayerSteamLevel()
            print(f'Logged on as {my_steam64}, level: {my_steam_level}')
            
            if self._steam_instance:
                self._is_steam_initialized = True
                logger.info("Steamworks API initialized successfully.")
            else:
                logger.warning("Steamworks API failed to initialize (Is Steam running?)")
        except Exception as e:
            logger.warning(f"Steamworks init error: {e}")

    def subscribe_item(self, published_file_id: int):
        """订阅模组"""
        if not self._check_steam_ready(): return False
        try:
            # SteamworksPy 接口：Workshop.subscribe(id)
            self._steam_instance.Workshop.SubscribeItem(published_file_id, self._workshop_callback) # type: ignore
            logger.info(f"Subscribed to {published_file_id}")
            return True
        except Exception as e:
            logger.error(f"Subscribe failed: {e}")
            return False

    def unsubscribe_item(self, published_file_id: int):
        """取消订阅"""
        if not self._check_steam_ready(): return False
        try:
            self._steam_instance.Workshop.UnsubscribeItem(published_file_id, self._workshop_callback) # type: ignore
            logger.info(f"Unsubscribed from {published_file_id}")
            return True
        except Exception as e:
            logger.error(f"Unsubscribe failed: {e}")
            return False
            
    def is_subscribed(self, published_file_id: int) -> bool:
        """检查是否已订阅 (需要 SteamworksPy 支持相关接口，此处视版本而定)"""
        # 注意：基础版 SteamworksPy 可能没暴露 ItemState 查询接口
        # 这里预留位置，如果库不支持，可能需要扩展 C++ 封装
        return False

    def _check_steam_ready(self):
        if not self._is_steam_initialized:
            # 尝试延迟初始化
            self._init_steamworks_api()
        return self._is_steam_initialized