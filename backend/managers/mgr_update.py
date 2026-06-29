# backend/managers/mgr_update.py
import glob
import json
import shutil
import sys
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, List
from abc import ABC, abstractmethod
import zipfile
import requests
from packaging import version
from backend._version import __version__
from backend.utils.lanzou_parser import LanzouParser
from backend.utils.logger import logger
from backend.utils.restart import PYINSTALLER_ENV_VARS_TO_CLEAR, launch_new_application
from backend.settings import BASE_RESOURCE_DIR, HOME_DIR, settings, UPDATE_DIR, backup_config_for_update
from backend.managers.mgr_download import DownloadManager, DownloadTask
from backend.managers.mgr_github import GithubApiError, GithubManager
from backend.utils.event_bus import EventBus
from backend.utils.tools import get_current_package_platform_keywords, get_package_platform_match, has_supported_update_package_name

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
    hash_algorithm: str = "md5"
    publish_time: Optional[str] = None
    
    # 本地状态控制
    # 'remote': 仅远程存在，需下载
    # 'downloading': 正在下载中
    # 'ready': 本地已存在且校验通过，可安装
    local_status: str = "remote" 
    local_file_path: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    check_status: str = "ok"
    source_results: Optional[List[Dict[str, Any]]] = None

    def to_source_dict(self):
        data = asdict(self)
        data.pop("sources", None)
        data.pop("check_status", None)
        data.pop("source_results", None)
        return data

    def to_dict(self): return asdict(self)


class UpdateSourceError(Exception):
    pass


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
                            file_hash=data.get('file_hash'),
                            hash_algorithm=data.get('hash_algorithm', 'md5'),
                            publish_time=data.get('publish_time'),
                            local_status="ready",  # 本地源默认为 ready
                            local_file_path=local_path
                        )
            except Exception as e:
                logger.warning(f"读取本地更新缓存失败: {jf}, error={e}")
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
        if not data:
            raise UpdateSourceError("蓝奏云更新源未返回有效数据")
        if not data.get('latest'): return None
        
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
        self.github_mgr = GithubManager()

    def check(self) -> Optional[UpdateInfo]:
        try:
            owner, repo = self._parse_repo()
            release = self.github_mgr.fetch_release(owner, repo, missing_ok=True)
            if not release: return None
            if release.get("draft") or release.get("prerelease"): return None

            remote_v = self._normalize_version(release.get("tag_name") or release.get("name") or "")
            if not remote_v or version.parse(remote_v) <= version.parse(__version__): return None

            asset = self._select_asset(release.get("assets") or [])
            if not asset:
                logger.warning(f"GitHub 更新源未找到适合当前系统的 zip 附件: repo={self.repo}, version={remote_v}")
                return None

            hash_algorithm, file_hash = self._parse_asset_digest(asset.get("digest"))
            return UpdateInfo(
                has_update=True,
                version=remote_v,
                changelog=str(release.get("body") or "无更新日志"),
                download_url=str(asset.get("browser_download_url") or ""),
                source_name="GitHub",
                file_size=self._format_size(asset.get("size")),
                file_hash=file_hash,
                hash_algorithm=hash_algorithm,
                publish_time=str(release.get("published_at") or release.get("created_at") or ""),
                local_status="remote",
            )
        except (GithubApiError, requests.RequestException) as e:
            raise UpdateSourceError(f"GitHub 更新源请求失败: {e}") from e
        except Exception as e:
            raise UpdateSourceError(f"GitHub 更新源解析失败: {e}") from e

    def _parse_repo(self) -> tuple[str, str]:
        parts = [part for part in str(self.repo or "").strip().strip("/").split("/") if part]
        if len(parts) != 2:
            raise ValueError(f"无效的 GitHub 仓库标识: {self.repo}")
        return parts[0], parts[1]

    def _select_asset(self, assets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        candidates: List[tuple[int, Dict[str, Any]]] = []
        repo_name = self.repo.rsplit("/", 1)[-1].lower()
        current_platform, _ = self._asset_platform_keywords()
        for asset in assets:
            name = str(asset.get("name") or "").strip()
            download_url = str(asset.get("browser_download_url") or "").strip()
            if not name or not download_url: continue

            lower_name = name.lower()
            if not lower_name.endswith(".zip"): continue
            if not has_supported_update_package_name(lower_name): continue
            matches_current_platform, has_known_platform = get_package_platform_match(lower_name)
            if current_platform and not matches_current_platform and has_known_platform: continue

            score = 0
            if repo_name in lower_name: score += 20
            if matches_current_platform: score += 10
            if "source" in lower_name or "src" in lower_name: score -= 20
            candidates.append((score, asset))

        if not candidates: return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    @staticmethod
    def _asset_platform_keywords() -> tuple[tuple[str, ...], tuple[str, ...]]:
        return get_current_package_platform_keywords()

    @staticmethod
    def _normalize_version(raw_version: str) -> str:
        text = str(raw_version or "").strip()
        return text[1:] if text.lower().startswith("v") else text

    @staticmethod
    def _parse_asset_digest(raw_digest: Any) -> tuple[str, Optional[str]]:
        text = str(raw_digest or "").strip()
        if ":" not in text: return "md5", None
        algorithm, digest = text.split(":", 1)
        algorithm = algorithm.strip().lower()
        digest = digest.strip()
        if algorithm in {"md5", "sha1", "sha256"} and digest:
            return algorithm, digest
        return "md5", None

    @staticmethod
    def _format_size(raw_size: Any) -> Optional[str]:
        try:
            size = int(raw_size or 0)
        except (TypeError, ValueError):
            return None
        if size <= 0: return None
        if size >= 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"


def _project_meta_candidate_paths() -> List[str]:
    return [
        os.path.join(HOME_DIR, "frontend", "public", "project-meta.json"),
        os.path.join(HOME_DIR, "frontend", "dist", "project-meta.json"),
        os.path.join(str(BASE_RESOURCE_DIR), "project-meta.json"),
        os.path.join(str(BASE_RESOURCE_DIR), "frontend", "dist", "project-meta.json"),
    ]


def _load_project_meta() -> Dict[str, Any]:
    for path in _project_meta_candidate_paths():
        try:
            if not os.path.exists(path): continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.warning(f"项目元数据格式无效，已忽略: path={path}")
        except Exception as e:
            logger.warning(f"读取项目元数据失败，已忽略: path={path}, error={e}")
    return {}


def _create_configured_update_source(config: Dict[str, Any], default_github_repo: str = "") -> Optional[UpdateSource]:
    source_type = str(config.get("type") or "").strip().lower()
    if source_type == "lanzou":
        folder_url = str(config.get("url") or "").strip()
        if not folder_url:
            logger.warning("项目元数据中的蓝奏云更新源缺少 url，已跳过")
            return None
        return LanzouSource(folder_url, str(config.get("password") or "").strip())
    if source_type == "github":
        repo = str(config.get("repo") or default_github_repo or "").strip()
        if not repo:
            logger.warning("项目元数据中的 GitHub 更新源缺少 repo，已跳过")
            return None
        return GithubSource(repo)
    if source_type:
        logger.warning(f"项目元数据中的更新源类型不支持，已跳过: type={source_type}")
    return None


def _build_configured_update_sources(project_meta: Optional[Dict[str, Any]] = None) -> List[UpdateSource]:
    meta = project_meta if isinstance(project_meta, dict) else _load_project_meta()
    project_repo = str((meta.get("project") or {}).get("github_repo") or "").strip()
    remote_sources: List[UpdateSource] = []
    for config in (meta.get("update") or {}).get("sources") or []:
        if not isinstance(config, dict): continue
        source = _create_configured_update_source(config, project_repo)
        if source:
            remote_sources.append(source)

    if not remote_sources:
        fallback_repo = project_repo or "Inky-Feather/RimCrow"
        remote_sources = [
            LanzouSource("https://wwbns.lanzouu.com/b00mq4tqgf", "aite"),
            GithubSource(fallback_repo),
        ]

    return [LocalSource(), *remote_sources]

# --- 更新总管 ---
class UpdateManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UpdateManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        # 优先级：本地缓存最先；远程源顺序由项目元数据控制，默认仍保持蓝奏云优先、GitHub 兜底。
        self.sources: List[UpdateSource] = _build_configured_update_sources()
        self.download_mgr = DownloadManager()
        # 内存中暂存当前的更新信息，避免反复 Check
        self.current_update_info: Optional[UpdateInfo] = None
        self.active_download_task_id: Optional[str] = None
        self.active_download_version: Optional[str] = None
        self.download_contexts: Dict[str, Dict[str, Any]] = {}

    def check_all(self) -> UpdateInfo:
        """
        遍历所有源直到找到一个有效的返回结果。
        聚合检查逻辑：
        1. 检查远程源是否有新版本。
        2. 如果有远程新版本，检查本地 Cache 是否已经下载了该版本。
        3. 如果远程无更新，但本地 Cache 有比当前高版本的包（离线包），也视为有更新。
        """
        candidates: List[tuple[Any, UpdateInfo]] = []
        source_results: List[Dict[str, Any]] = []
        remote_source_count = 0
        remote_success_count = 0
        remote_failure_count = 0
        
        # 1. 遍历所有源，收集可用更新。只有最高版本相同的来源才会合并展示。
        for src in self.sources:
            source_name = self._source_display_name(src)
            is_remote_source = not isinstance(src, LocalSource)
            if is_remote_source:
                remote_source_count += 1
            try:
                info = src.check()
                if info and info.has_update:
                    parsed_version = version.parse(info.version)
                    candidates.append((parsed_version, info))
                    source_results.append({"source_name": source_name, "status": "update", "version": info.version})
                else:
                    source_results.append({"source_name": source_name, "status": "no_update"})
                if is_remote_source:
                    remote_success_count += 1
            except Exception as e:
                logger.error(f"检查更新源失败: source={src.__class__.__name__}, error={e}")
                source_results.append({"source_name": source_name, "status": "failed", "error": str(e)})
                if is_remote_source:
                    remote_failure_count += 1
                continue
        
        if not candidates:
            if remote_source_count > 0 and remote_success_count == 0 and remote_failure_count > 0:
                raise UpdateSourceError("所有远程更新源都检查失败")
            no_update = UpdateInfo(False, __version__, "", "", "None")
            no_update.check_status = "partial" if remote_failure_count else "ok"
            no_update.source_results = source_results
            return no_update

        latest_parsed_version = max(parsed_version for parsed_version, _ in candidates)
        latest_sources = [info for parsed_version, info in candidates if parsed_version == latest_parsed_version]
        latest_version = latest_sources[0].version

        # 2. 智能缓存匹配：缓存包也作为同版本来源参与展示，且优先安装。
        if not any(item.source_name == "本地缓存" and item.local_status == "ready" for item in latest_sources):
            cached_path = self._find_cached_file(latest_version)
            if cached_path:
                logger.info(f"命中本地更新缓存: version={latest_version}, path={cached_path}")
                cached_info = UpdateInfo(
                    has_update=True,
                    version=latest_version,
                    changelog=latest_sources[0].changelog,
                    download_url=latest_sources[0].download_url,
                    source_name="本地缓存",
                    file_size=latest_sources[0].file_size,
                    file_hash=latest_sources[0].file_hash,
                    hash_algorithm=latest_sources[0].hash_algorithm,
                    publish_time=latest_sources[0].publish_time,
                    local_status="ready",
                    local_file_path=cached_path,
                )
                latest_sources.insert(0, cached_info)

        selected = latest_sources[0]
        selected.sources = [item.to_source_dict() for item in latest_sources]
        selected.check_status = "partial" if remote_failure_count else "ok"
        selected.source_results = source_results
        self.current_update_info = selected
        return selected

    @staticmethod
    def _source_display_name(source: UpdateSource) -> str:
        if isinstance(source, LocalSource): return "本地缓存"
        if isinstance(source, LanzouSource): return "蓝奏云"
        if isinstance(source, GithubSource): return "GitHub"
        return source.__class__.__name__

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
        potential_names = [f"update_v{version_str}.zip", f"RimCrow_v{version_str}.zip", f"RimModManager_v{version_str}.zip"]
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

        if self.active_download_task_id and self.active_download_version == info.version:
            return {"status": "downloading", "task_id": self.active_download_task_id}

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

        return self._start_update_download(info, [])

    def _start_update_download(self, info: UpdateInfo, attempted_source_keys: List[str]) -> Dict:
        """按当前来源启动下载，失败回调会继续尝试同版本候补来源。"""
        if not info.download_url:
            raise Exception(f"{info.source_name} 没有可用的更新包下载地址")

        sources = self._sources_for_info(info)
        source_key = self._source_key(info.to_source_dict())
        attempted_keys = [key for key in attempted_source_keys if key]
        if source_key not in attempted_keys:
            attempted_keys.append(source_key)
        has_fallback_source = self._next_fallback_source(attempted_keys, sources, info.version) is not None

        task_id = self.download_mgr.add_task(
            url=info.download_url,
            dest_dir=str(UPDATE_DIR),
            filename=f"update_v{info.version}.zip",
            expected_hash=info.file_hash, # 如果源提供了 Hash，这里会自动校验
            hash_algorithm=info.hash_algorithm,
            on_complete=self._on_download_complete,
            on_error=self._on_download_error,
            task_type="update",
            title="软件更新",
            metadata={
                "version": info.version,
                "source_name": info.source_name,
                "source_key": source_key,
                "attempted_source_keys": attempted_keys,
                "has_fallback_source": has_fallback_source,
                "ready_to_install": False,
            },
        )
        
        info.local_status = "downloading"
        self.active_download_task_id = task_id
        self.active_download_version = info.version
        self.download_contexts[task_id] = {
            "info": info.to_source_dict(),
            "sources": sources,
            "attempted_source_keys": attempted_keys,
        }
        return {"status": "downloading", "task_id": task_id}

    def _on_download_complete(self, task: DownloadTask):
        """下载完成后的内部回调（由 DownloadManager 线程调用）"""
        logger.info(f"更新包下载完成: path={task.dest_path}")
        
        # 1. 再次确认文件存在
        if not os.path.exists(task.dest_path):
            self._on_download_error(task)
            return

        # 2. 生成/保存元数据 (Manifest)
        context = self.download_contexts.pop(task.task_id, {})
        info = self._update_info_from_source(context.get("info") or {})
        if info:
            info.sources = context.get("sources") or info.sources
            info.local_file_path = task.dest_path
            info.local_status = "ready"
            self.current_update_info = info
            self._save_metadata_file(info)
        self._clear_active_download(task.task_id)
        
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
        logger.error(f"更新包下载失败: task_id={task.task_id}, error={task.error_msg}")
        context = self.download_contexts.pop(task.task_id, {})
        attempted_keys = list(context.get("attempted_source_keys") or task.metadata.get("attempted_source_keys") or [])
        current_key = task.metadata.get("source_key")
        if current_key and current_key not in attempted_keys:
            attempted_keys.append(current_key)

        current_info = context.get("info") or {}
        sources = context.get("sources") or self._sources_for_info(self.current_update_info)
        target_version = current_info.get("version", "") or task.metadata.get("version", "")
        next_source = self._next_fallback_source(attempted_keys, sources, target_version)
        if next_source:
            failed_source = task.metadata.get("source_name") or "当前来源"
            next_name = str(next_source.get("source_name") or "候补来源")
            next_info = self._update_info_from_source(next_source, sources)
            if not next_info:
                self._emit_final_download_error(task, "候补更新源无效")
                return
            self.current_update_info = next_info
            logger.warning(f"更新源下载失败，尝试候补来源: failed={failed_source}, next={next_name}, version={next_source.get('version')}")
            EventBus.emit_progress(
                task.task_id,
                "update",
                status="running",
                progress=0,
                message=f"{failed_source} 下载失败，正在尝试 {next_name}",
                metrics={"error": task.error_msg, "title": "软件更新", "source_name": next_name, "fallback": True},
            )
            try:
                self._start_update_download(next_info, attempted_keys)
            except Exception as e:
                logger.error(f"启动候补更新源下载失败: source={next_name}, error={e}", exc_info=True)
                self._emit_final_download_error(task, f"候补来源启动失败: {e}")
            return

        self._emit_final_download_error(task, task.error_msg)

    def _emit_final_download_error(self, task: DownloadTask, message: str):
        EventBus.emit_progress(
            task.task_id,
            "update",
            status="failed",
            progress=0,
            message=f"更新失败: {message}",
            metrics={"error": message, "title": "软件更新"},
        )
        if self.current_update_info:
            self.current_update_info.local_status = "remote"
        self._clear_active_download(task.task_id)

    def _clear_active_download(self, task_id: str):
        if self.active_download_task_id == task_id:
            self.active_download_task_id = None
            self.active_download_version = None

    @staticmethod
    def _source_key(source: Dict[str, Any]) -> str:
        return f"{source.get('source_name') or ''}|{source.get('download_url') or ''}"

    def _next_fallback_source(self, attempted_source_keys: List[str], sources: Optional[List[Dict[str, Any]]] = None, version_str: str = "") -> Optional[Dict[str, Any]]:
        if not sources:
            return None

        attempted = set(attempted_source_keys)
        for source in sources:
            if version_str and source.get("version") != version_str: continue
            if source.get("local_status") == "ready": continue
            if not source.get("download_url"): continue
            if self._source_key(source) not in attempted:
                return source
        return None

    @staticmethod
    def _sources_for_info(info: Optional[UpdateInfo]) -> List[Dict[str, Any]]:
        if not info:
            return []
        if info.sources:
            return [dict(source) for source in info.sources]
        return [info.to_source_dict()]

    @staticmethod
    def _update_info_from_source(source: Dict[str, Any], sources: Optional[List[Dict[str, Any]]] = None) -> Optional[UpdateInfo]:
        if not source:
            return None
        return UpdateInfo(
            has_update=bool(source.get("has_update", True)),
            version=str(source.get("version") or ""),
            changelog=str(source.get("changelog") or ""),
            download_url=str(source.get("download_url") or ""),
            source_name=str(source.get("source_name") or ""),
            file_size=source.get("file_size"),
            file_hash=source.get("file_hash"),
            hash_algorithm=str(source.get("hash_algorithm") or "md5"),
            publish_time=source.get("publish_time"),
            local_status=str(source.get("local_status") or "remote"),
            local_file_path=source.get("local_file_path"),
            sources=sources,
        )

    def _save_metadata_file(self, info: UpdateInfo):
        """保存 update_vX.X.X.json"""
        try:
            filename = f"update_v{info.version}.json"
            path = os.path.join(UPDATE_DIR, filename)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(info.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存更新元数据失败: version={info.version}, error={e}")

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
            logger.info("正在解压更新包。")
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
            payload_exe_name = exe_name
            exe_candidates = [exe_name]
            if os.name == "nt" and exe_name.lower() == "rimmodmanager.exe":
                exe_candidates.insert(0, "RimCrow.exe")
            for root, dirs, files in os.walk(extract_path):
                payload_exe_name = next((name for name in exe_candidates if name in files), "")
                if payload_exe_name:
                    payload_dir = root
                    break
            
            if not payload_dir:
                payload_exe_name = next((name for name in exe_candidates if os.path.exists(os.path.join(extract_path, name))), "")
                if payload_exe_name:
                    payload_dir = extract_path
                else:
                    raise Exception("无法在更新包中找到主程序文件")

            logger.info("正在执行 Python 热更新替换流程。")
            
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

            logger.info("正在启动新版本。")
            launch_new_application(os.path.join(install_root, payload_exe_name))

            # 8. 当前旧进程功成身退，立即退出
            logger.info("旧版本进程准备退出。")
            os._exit(0)

        except Exception as e:
            logger.error(f"准备安装更新失败: zip_path={zip_path}, error={e}", exc_info=True)
            # 如果中途失败了（比如复制了一半），尽量把名字改回来防止软件损坏
            if os.path.exists(current_exe + ".old") and not os.path.exists(current_exe):
                try: os.rename(current_exe + ".old", current_exe)
                except: pass
            raise e
        
        
