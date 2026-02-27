# backend/managers/mgr_update.py
import glob
import json
import shutil
import sys
import os
import subprocess
from dataclasses import asdict, dataclass
from typing import Optional, List, Dict
from abc import ABC, abstractmethod
import zipfile
from packaging import version
from backend._version import __version__
from backend.utils.lanzou_parser import LanzouParser
from backend.utils.logger import logger
from backend.settings import settings, UPDATE_DIR
from backend.managers.mgr_download import DownloadManager, TaskStatus, DownloadTask
from backend.utils.event_bus import EventBus

# 确保缓存目录存在
os.makedirs(UPDATE_DIR, exist_ok=True)
@dataclass
class UpdateInfo:
    has_update: bool
    version: str
    changelog: str
    download_url: str
    source_name: str  # "Local", "Lanzou", "GitHub"
    # 校验与元数据
    file_size: Optional[str] = None
    file_hash: Optional[str] = None      # MD5/SHA256
    publish_time: Optional[str] = None
    
    # 本地状态控制
    # 'remote': 仅远程存在，需下载
    # 'downloading': 正在下载中
    # 'ready': 本地已存在且校验通过，可安装
    local_status: str = "remote" 
    local_file_path: Optional[str] = None
    def to_dict(self):
        return asdict(self)
class UpdateSource(ABC):
    @abstractmethod
    def check(self) -> Optional[UpdateInfo]:
        pass

# --- 1. 本地缓存源 ---
class LocalSource(UpdateSource):
    """
    检查 updates/ 目录下是否有已经下载好且版本高于当前版本的安装包。
    用于离线更新或避免重复下载。
    """
    def check(self) -> Optional[UpdateInfo]:
        if not os.path.exists(UPDATE_DIR):
            return None
        
        # 扫描所有元数据文件
        json_files = glob.glob(os.path.join(UPDATE_DIR, "*.json"))
        best_candidate: Optional[UpdateInfo] = None
        
        for jf in json_files:
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 检查对应的 zip 是否存在
                # 元数据中记录了 path，或者按惯例推断
                local_path = data.get('local_file_path')
                if not local_path or not os.path.exists(local_path):
                    # 尝试推断
                    assumed_zip = jf.replace('.json', '.zip')
                    if os.path.exists(assumed_zip):
                        local_path = assumed_zip
                    else:
                        continue # 元数据对应的文件丢失，无效

                remote_v = data.get('version', '0.0.0')
                # 只有当本地缓存的版本 > 当前版本才算有效更新
                if version.parse(remote_v) > version.parse(__version__):
                    # 如果有多个本地版本，取最新的
                    if best_candidate is None or version.parse(remote_v) > version.parse(best_candidate.version):
                        best_candidate = UpdateInfo(
                            has_update=True,
                            version=remote_v,
                            changelog=data.get('changelog', '本地缓存包'),
                            download_url=data.get('download_url', ''),
                            source_name="本地缓存",
                            file_size=data.get('file_size'),
                            publish_time=data.get('publish_time'),
                            local_status="ready",  # 本地源默认为 ready
                            local_file_path=local_path
                        )
            except Exception as e:
                logger.warning(f"Error reading local cache {jf}: {e}")
                continue
        
        return best_candidate
# --- 蓝奏云源实现 ---
class LanzouSource(UpdateSource):
    def __init__(self, folder_url: str, password: str = ""):
        self.url = folder_url
        self.pwd = password
        self.parser = LanzouParser()

    def check(self):
        data = self.parser.get_all_files(self.url, self.pwd)
        if not data or 'latest' not in data:
            return None
        
        latest = data['latest']
        remote_v = latest['version']
        
        if version.parse(remote_v) > version.parse(__version__):
            return UpdateInfo(
                has_update=True,
                version=remote_v,
                changelog=latest.get('note', "无更新日志"),
                download_url=latest.get('download_url', ""),
                source_name="蓝奏云",
                file_size=latest.get('size'),
                publish_time=latest.get('time'),
                # 蓝奏云通常不直接提供 hash，除非写在文件名或备注里
                file_hash=None, 
                local_status="remote"
            )
        return None

# --- GitHub 源实现 (预留) ---
class GithubSource(UpdateSource):
    def __init__(self, repo: str):
        self.repo = repo
    def check(self):
        # 实际实现需调用 GitHub API
        return None

# --- 更新总管 ---
class UpdateManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UpdateManager, cls).__new__(cls)
        return cls._instance
    def __init__(self):
        self.sources: List[UpdateSource] = [
            # 优先级：本地文件最先，蓝奏云优先（国内快），GitHub 兜底
	        LocalSource(),  
            LanzouSource("https://wwbns.lanzouu.com/b00mq4tqgf", "aite"),
            # GithubSource("YourName/Repo") 
        ]
        self.download_mgr = DownloadManager()
        # 内存中暂存当前的更新信息，避免反复 Check
        self.current_update_info: Optional[UpdateInfo] = None

    def check_all(self) -> UpdateInfo:
        """
        遍历所有源直到找到一个有效的返回结果。
        聚合检查逻辑：
        1. 检查远程源是否有新版本。
        2. 如果有远程新版本，检查本地 Cache 是否已经下载了该版本。
        3. 如果远程无更新，但本地 Cache 有比当前高版本的包（离线包），也视为有更新。
        """
        best_remote: Optional[UpdateInfo] = None
        
        # 1. 遍历所有源，找到版本最高的那个
        for src in self.sources:
            try:
                info = src.check()
                if info and info.has_update:
                    if best_remote is None or version.parse(info.version) > version.parse(best_remote.version):
                        best_remote = info
            except Exception as e:
                logger.error(f"Update Source {src.__class__.__name__} failed: {e}")
                continue
        
        if not best_remote:
            return UpdateInfo(False, __version__, "", "", "None")

        # 2. 智能缓存匹配
        # 如果来源是远程的，检查一下本地是否其实已经有了
        if best_remote.source_name != "本地缓存":
            cached_path = self._find_cached_file(best_remote.version)
            if cached_path:
                logger.info(f"Hit local cache for version {best_remote.version}")
                best_remote.local_status = "ready"
                best_remote.local_file_path = cached_path
                best_remote.source_name += " (已缓存)"

        self.current_update_info = best_remote
        return best_remote
    def _find_cached_file(self, version_str: str) -> Optional[str]:
        """在缓存目录查找特定版本的 zip"""
        # 假设文件名包含版本号，或者通过 json 查找
        # 方案 A: 查 JSON (更准确)
        json_path = os.path.join(UPDATE_DIR, f"update_v{version_str}.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    path = data.get('local_file_path')
                    if path and os.path.exists(path):
                        return path
            except: pass
        
        # 方案 B: 盲猜文件名
        potential_names = [f"update_v{version_str}.zip", f"RimModManager_v{version_str}.zip"]
        for name in potential_names:
            p = os.path.join(UPDATE_DIR, name)
            if os.path.exists(p):
                return p
        return None

    
    def perform_update_download(self, target_version: str = '') -> Dict:
        """
        执行更新下载流程 (前端点击‘立即更新’后调用)
        """
        # 如果没有指定版本，使用当前检测到的
        info = self.current_update_info
        if not info or (target_version and info.version != target_version):
            # 重新检查一遍，防止状态不同步
            info = self.check_all()
        
        if not info.has_update:
            raise Exception("没有可用的更新")

        # 如果已经是 Ready 状态，直接通知
        if info.local_status == "ready" and info.local_file_path:
            EventBus.emit("update-status", {"status": "ready", "path": info.local_file_path})
            return {"status": "ready", "task_id": None}

        # 开始下载
        # 构造文件名
        filename = f"update_v{info.version}.zip"
        
        # 调用 DownloadManager
        # 注意：这里传入回调函数，让 DownloadManager 在完成后通知
        task_id = self.download_mgr.add_task(
            url=info.download_url,
            dest_dir=str(UPDATE_DIR),
            filename=filename,
            expected_hash=info.file_hash, # 如果源提供了 Hash，这里会自动校验
            on_complete=self._on_download_complete,
            on_error=self._on_download_error
        )
        
        # 标记当前 info 状态
        info.local_status = "downloading"
        return {"status": "downloading", "task_id": task_id}

    def _on_download_complete(self, task: DownloadTask):
        """下载完成后的内部回调（由 DownloadManager 线程调用）"""
        logger.info(f"Update package downloaded: {task.dest_path}")
        
        # 1. 再次确认文件存在
        if not os.path.exists(task.dest_path):
            self._on_download_error(task)
            return

        # 2. 生成/保存元数据 (Manifest)
        # 需要从 current_update_info 恢复数据，或者从 task 中传递上下文
        # 简单起见，假设 current_update_info 仍然是有效的
        info = self.current_update_info
        if info:
            info.local_file_path = task.dest_path
            info.local_status = "ready"
            self._save_metadata_file(info)
        
        # 3. 清理旧版本
        self._clean_old_cache()

        # 4. 通知前端：准备就绪
        EventBus.emit("update-status", {
            "status": "ready", 
            "version": info.version if info else "unknown",
            "path": task.dest_path
        })

    def _on_download_error(self, task: DownloadTask):
        logger.error(f"Update download error: {task.error_msg}")
        EventBus.emit("update-status", {
            "status": "error",
            "msg": task.error_msg
        })
        if self.current_update_info:
            self.current_update_info.local_status = "remote"

    def _save_metadata_file(self, info: UpdateInfo):
        """保存 update_vX.X.X.json"""
        try:
            filename = f"update_v{info.version}.json"
            path = os.path.join(UPDATE_DIR, filename)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(info.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save update metadata: {e}")

    def _clean_old_cache(self):
        """保留最近2个版本，删除其他的"""
        try:
            files = glob.glob(os.path.join(UPDATE_DIR, "*.json"))
            if len(files) <= 2: return
            # 按时间排序
            files.sort(key=os.path.getmtime)
            for old_json in files[:-2]:
                try:
                    os.remove(old_json)
                    old_zip = old_json.replace('.json', '.zip')
                    if os.path.exists(old_zip):
                        os.remove(old_zip)
                except: pass
        except: pass
    
    def execute_hot_swap(self, zip_path: str = ''):
        """
        执行热更新：
        1. 解压 Zip 到临时目录
        2. 生成 Bat 脚本
        3. 启动 Bat 并退出当前进程
        """
        debug = settings.config.debug_mode or False
        if not zip_path:
            # 如果没传路径，尝试使用当前就绪的
            if self.current_update_info and self.current_update_info.local_file_path and self.current_update_info.local_status == "ready":
                zip_path = self.current_update_info.local_file_path
            else:
                raise ValueError("未指定更新包路径且无就绪更新")

        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Update package not found: {zip_path}")

        # 获取环境信息
        current_exe = os.path.abspath(sys.executable)
        exe_name = os.path.basename(current_exe)
        install_root = os.path.dirname(current_exe)
        
        # 临时解压目录
        extract_path = os.path.join(install_root, "update_tmp_dir")
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path, ignore_errors=True)
        os.makedirs(extract_path, exist_ok=True)

        try:
            logger.info("Extracting update package...")
            # 解压逻辑 (处理编码，防止中文乱码)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.infolist():
                    # 关键：手动处理编码转换
                    try:
                        # 修正 Zip 乱码 尝试将文件名从 cp437 转回原始字节，再按 gbk 解码
                        filename = member.filename.encode('cp437').decode('gbk')
                    except:
                        filename = member.filename # 兜底使用原始
                    
                    # 构造目标路径
                    target_path = os.path.join(extract_path, filename)
                    
                    # 如果是目录
                    if member.is_dir():
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        # 确保父目录存在
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zf.open(member) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)

            # 4. 定位新版本 Payload
            payload_dir = None
            for root, dirs, files in os.walk(extract_path):
                if exe_name in files:
                    payload_dir = root
                    break
            
            if not payload_dir:
                # 尝试根目录
                if os.path.exists(os.path.join(extract_path, exe_name)):
                    payload_dir = extract_path
                else:
                    raise Exception("无法在更新包中找到主程序文件")

            # 5. 生成高兼容性批处理
            bat_path = os.path.join(install_root, "_finish_update.bat")
            
            # --- 【调试修改点 1】: 根据 debug 模式调整 BAT 内容 ---
            if debug:
                # 调试模式：显示回显，不自删除，暂停查看结果
                echo_cmd = "@echo on"
                pause_cmd = "pause"
                del_self_cmd = ":: Debug mode - script kept"
                exit_cmd = ":: exit skipped for debug"
            else:
                # 生产模式：关闭回显，自删除，退出
                echo_cmd = "@echo off"
                pause_cmd = ""
                del_self_cmd = '(goto) 2>nul & del "%~f0"'
                exit_cmd = "exit"
            # 1. chcp 65001 -> 处理 UTF-8 (Python 写入的文件)
            # 2. set "_MEIPASS=" -> 极其重要！清除单文件模式的临时路径变量，防止 DLL 加载错误
            # 3. taskkill -> 确保进程彻底杀掉
            bat_content = f"""{echo_cmd}
chcp 65001 > nul
setlocal
title RimModManager Updater

echo [DEBUG] Current PID: %PID% 
echo [DEBUG] Install Root: "{install_root}" 
echo [DEBUG] Payload Dir: "{payload_dir}" 

echo Waiting for the main program to exit... 
timeout /t 2 /nobreak > nul
:kill_process
taskkill /f /im "{exe_name}" >nul 2>&1
timeout /t 1 /nobreak > nul

:retry_move
echo Replacing the file...
:: Using robocopy can better handle file occupation and permissions. 
robocopy "{payload_dir}" "{install_root}" /E /IS /IT /MOVE /R:5 /W:2 /XF "{os.path.basename(bat_path)}"

:: A Robocopy exit code < 8 indicates success 
if %ERRORLEVEL% GEQ 8 (
    echo [ERROR] Robocopy failed with code %ERRORLEVEL% 
    timeout /t 3
    goto retry_move
)

echo Cleaning up temporary files... 
:: Before starting the program, delete the directory 
if exist "{extract_path}" (
    rd /s /q "{extract_path}"
)
:: If deletion fails, try waiting a moment (in case robocopy handles are not released) 
if exist "{extract_path}" (
    timeout /t 1 /nobreak > nul
    rd /s /q "{extract_path}"
)

echo Update successful, cleaning up environment and restarting... 

:: Clear PyInstaller environment remnants to prevent DLL not found errors 
set _MEIPASS=
set _MEIPASS2=
set PYI_EXPLODE_PATH=
set PYTHONPATH=
set PYTHONHOME=

echo [DEBUG] Attempting to start: "{install_root}\\{exe_name}" 
echo [DEBUG] Working Directory: "{install_root}" 

:: Launch a new program (Use the /i parameter to make start ignore the current cmd window environment) 
start "" /i /d "{install_root}" "{exe_name}" 

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to restart application! 
    echo Please manually start: {exe_name} 
)

:: Ensure that the script deletes itself after exiting. 
{del_self_cmd}
{pause_cmd}
{exit_cmd}
"""
            # 写入批处理（注意编码）
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)
                
            cmd_arg = "/k" if debug else "/c"
            
            # 6. 运行脚本
            subprocess.Popen(
                ["cmd.exe", cmd_arg, bat_path],
                cwd=install_root,
                shell=not debug,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            # 立即彻底结束 Python 进程
            logger.info("Exiting application for update.")
            os._exit(0)

        except Exception as e:
            logger.error(f"Failed to prepare update: {e}")
            raise e
        
        