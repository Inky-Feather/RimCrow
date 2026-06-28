# backend/managers/mgr_update.py
import glob
import json
import shutil
import sys
import os
import subprocess
from dataclasses import asdict, dataclass
from typing import Dict, Optional, List
from abc import ABC, abstractmethod
import zipfile
from packaging import version
from backend._version import __version__
from backend.utils.lanzou_parser import LanzouParser
from backend.utils.logger import logger
from backend.utils.restart import PYINSTALLER_ENV_VARS_TO_CLEAR, launch_new_application
from backend.settings import settings, UPDATE_DIR, backup_config_for_update
from backend.managers.mgr_download import DownloadManager, DownloadTask
from backend.utils.event_bus import EventBus

# 确保缓存目录存在
os.makedirs(UPDATE_DIR, exist_ok=True)

def _build_env_cleanup_commands() -> str:
    """生成批处理中用于清理/重置运行时环境变量的命令。"""
    lines = ['set "PYINSTALLER_RESET_ENVIRONMENT=1"']
    lines.extend(f'set "{key}="' for key in PYINSTALLER_ENV_VARS_TO_CLEAR)
    return "\n".join(lines)

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
    def to_dict(self): return asdict(self)
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
        if not os.path.exists(UPDATE_DIR): return None
        
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
        if not data or 'latest' not in data: return None
        
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
        
        if not best_remote: return UpdateInfo(False, __version__, "", "", "None")

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
                    if path and os.path.exists(path): return path
            except: pass
        
        # 方案 B: 盲猜文件名
        potential_names = [f"update_v{version_str}.zip", f"RimModManager_v{version_str}.zip"]
        for name in potential_names:
            p = os.path.join(UPDATE_DIR, name)
            if os.path.exists(p): return p
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
            EventBus.emit_progress(
                f"update-ready-{info.version}",
                "update",
                status="success",
                progress=100,
                message=f"更新包已就绪 v{info.version}",
                metrics={"path": info.local_file_path, "version": info.version, "ready_to_install": True, "title": "软件更新"},
            )
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
            on_error=self._on_download_error,
            task_type="update",
            title="软件更新",
            metadata={"version": info.version, "source_name": info.source_name, "ready_to_install": False},
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
        EventBus.emit_progress(
            task.task_id,
            "update",
            status="success",
            progress=100,
            message=f"更新包已就绪 v{info.version if info else 'unknown'}",
            metrics={
                "path": task.dest_path,
                "version": info.version if info else "unknown",
                "ready_to_install": True,
                "title": "软件更新",
            },
        )

    def _on_download_error(self, task: DownloadTask):
        logger.error(f"Update download error: {task.error_msg}")
        EventBus.emit_progress(
            task.task_id,
            "update",
            status="failed",
            progress=0,
            message=f"更新失败: {task.error_msg}",
            metrics={"error": task.error_msg, "title": "软件更新"},
        )
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
        纯 Python 优雅热更新（防杀软误报方案）
        """
        debug = settings.config.debug_mode or False
        if not zip_path:
            if self.current_update_info and self.current_update_info.local_file_path and self.current_update_info.local_status == "ready":
                zip_path = self.current_update_info.local_file_path
            else:
                raise ValueError("未指定更新包路径且无就绪更新")

        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Update package not found: {zip_path}")

        current_exe = os.path.abspath(sys.executable)
        exe_name = os.path.basename(current_exe)
        install_root = os.path.dirname(current_exe)
        
        extract_path = os.path.join(install_root, "update_tmp_dir")
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path, ignore_errors=True)
        os.makedirs(extract_path, exist_ok=True)

        try:
            logger.info("Extracting update package...")
            # 1. 解压 Zip
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for member in zf.infolist():
                    try:
                        filename = member.filename.encode('cp437').decode('gbk')
                    except:
                        filename = member.filename
                    
                    target_path = os.path.join(extract_path, filename)
                    if member.is_dir():
                        os.makedirs(target_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with zf.open(member) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)

            # 2. 定位新版本 Payload
            payload_dir = None
            for root, dirs, files in os.walk(extract_path):
                if exe_name in files:
                    payload_dir = root
                    break
            
            if not payload_dir:
                if os.path.exists(os.path.join(extract_path, exe_name)):
                    payload_dir = extract_path
                else:
                    raise Exception("无法在更新包中找到主程序文件")

            logger.info("Performing Pure Python Hot Swap...")
            
            backup_config_for_update()
            
            # 3. 处理旧的残余文件
            old_exe_path = current_exe + ".old"
            if os.path.exists(old_exe_path):
                try:
                    os.remove(old_exe_path)
                except:
                    pass

            # 4. 将当前正在运行的 exe 重命名为 .old
            # Windows 允许重命名正在运行的执行文件！这样就把原本的文件名空出来了
            try:
                os.rename(current_exe, old_exe_path)
            except Exception as e:
                raise Exception(f"无法重命名正在运行的文件 (可能被杀毒软件硬锁定): {e}")

            # 5. 把新版本的文件全部复制过来 (覆盖旧数据)
            for item in os.listdir(payload_dir):
                s_path = os.path.join(payload_dir, item)
                d_path = os.path.join(install_root, item)
                if os.path.isdir(s_path):
                    shutil.copytree(s_path, d_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(s_path, d_path)

            # 6. 清理临时解压目录
            try:
                shutil.rmtree(extract_path, ignore_errors=True)
            except:
                pass

            logger.info("Launching new version...")
            launch_new_application()

            # 8. 当前旧进程功成身退，立即退出
            logger.info("Exiting old application instance.")
            os._exit(0)

        except Exception as e:
            logger.error(f"Failed to prepare update: {e}", exc_info=True)
            # 如果中途失败了（比如复制了一半），尽量把名字改回来防止软件损坏
            if os.path.exists(current_exe + ".old") and not os.path.exists(current_exe):
                try: os.rename(current_exe + ".old", current_exe)
                except: pass
            raise e
        
        
