import os
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
import html
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse

import requests
from backend.database.models import GithubModRecord, GithubTimeline, db
from backend.managers.mgr_download import DownloadManager, DownloadTask
from backend.managers.mgr_network import build_retry_session, merge_headers
from backend.settings import HOME_DIR, settings
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger
from backend.utils.tools import current_ms, extract_zip

GITHUB_API_BASE = "https://api.github.com/repos"
GITHUB_WEB_BASE = "https://github.com"
GITHUB_ACCEPT_HEADER = "application/vnd.github+json"
GITHUB_API_CACHE_TTL_SECONDS = 180
GITHUB_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 RimModManager/1.0"
)

GITHUB_ARTIFACT_RELEASE_ASSET = "release_asset"
GITHUB_ARTIFACT_SOURCE_ARCHIVE = "source_archive"

GITHUB_INSTALL_DOWNLOAD_ONLY = "download_only"
GITHUB_INSTALL_EXTRACT = "extract"
GITHUB_INSTALL_EXTRACT_THEN_MOVE = "extract_then_move"
GITHUB_INSTALL_RUN_INSTALLER = "run_installer"

GITHUB_SOURCE_BRANCH = "branch"
GITHUB_SOURCE_TAG = "tag"

GITHUB_RESOLVER_ARCHIVE_ROOT = "archive_root"
GITHUB_RESOLVER_MOD_ROOT = "mod_root"


@dataclass
class GithubArtifactRequest:
    """描述“从 GitHub 拿什么”，只负责产物选择，不负责安装动作。"""
    kind: str = GITHUB_ARTIFACT_SOURCE_ARCHIVE
    release_tag: str = ""
    source_ref: str = ""
    source_ref_type: str = GITHUB_SOURCE_BRANCH
    asset_name: str = ""
    asset_name_prefix: str = ""
    asset_name_suffix: str = ""
    asset_name_pattern: str = ""
    fallback_download_url: str = ""
    fallback_filename: str = ""
    fallback_version: str = ""
    fallback_asset_name: str = ""


@dataclass
class GithubInstallPlan:
    """描述“拿到压缩包后怎么处理”，把安装策略和下载来源解耦。"""
    action: str = GITHUB_INSTALL_DOWNLOAD_ONLY
    download_dir: str = str(HOME_DIR / "Downloads")
    extract_dir: str = ""
    move_target_dir: str = ""
    final_name: str = ""
    source_resolver: str = GITHUB_RESOLVER_ARCHIVE_ROOT
    source_subpath: str = ""
    overwrite_existing: bool = True
    cleanup_archive: bool = True


@dataclass
class GithubInstallResult:
    """安装阶段的统一结果对象，方便后置钩子和上层业务读取。"""
    repo_url: str
    owner: str
    repo: str
    version: str
    download_url: str
    download_path: str
    filename: str
    artifact_kind: str
    installed_path: str = ""
    extracted_path: str = ""
    asset_name: str = ""


@dataclass
class GithubInstallRequest:
    """GitHub 安装总请求：来源、安装计划、提示文案和后置回调都在这里声明。"""
    repo_url: str = ""
    owner: str = ""
    repo: str = ""
    artifact: GithubArtifactRequest = field(default_factory=GithubArtifactRequest)
    install: GithubInstallPlan = field(default_factory=GithubInstallPlan)
    expected_hash: str = ""
    hash_algorithm: str = "md5"
    timeline_repo_url: str = ""
    download_start_message: str = ""
    install_start_message: str = ""
    success_message: str = ""
    success_toast: str = ""
    failure_toast: str = ""
    post_install: Callable[[GithubInstallResult], Any] | None = None
    on_install_error: Callable[[Exception, DownloadTask, "GithubResolvedArtifact"], Any] | None = None


@dataclass
class GithubResolvedArtifact:
    """把“逻辑请求”解析成一个可直接下载的具体产物。"""
    repo_url: str
    owner: str
    repo: str
    kind: str
    version: str
    download_url: str
    filename: str
    asset_name: str = ""


class GithubApiError(RuntimeError):
    """GitHub 远端访问失败。"""


class GithubRateLimitError(GithubApiError):
    """GitHub API 限流。"""


class GithubManager:
    """GitHub 下载/安装编排器。

    职责边界：
    1. 负责 GitHub 仓库、Release、源码包的解析。
    2. 负责把结构化请求转成 DownloadManager 可执行的下载任务。
    3. 负责下载完成后的通用安装动作，以及 GitHub 域内的时间线/订阅记录更新。

    它不负责底层下载执行本身，那部分仍由 DownloadManager 处理。
    """

    _cache_lock = None
    _cache_miss = object()
    _response_cache: dict[tuple[str, ...], tuple[float, Any]] = {}

    def __init__(self):
        if GithubManager._cache_lock is None:
            import threading

            GithubManager._cache_lock = threading.Lock()

    def parse_repo_url(self, url: str):
        """解析 GitHub URL 提取 owner 和 repo"""
        match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
        if not match:
            return None, None
        owner = match.group(1)
        repo = match.group(2).replace(".git", "")
        return owner, repo

    def parse_content_url(self, url: str) -> dict[str, str] | None:
        """解析 GitHub 单文件 URL，统一供“外部库检查”等场景复用。"""
        try:
            parsed = urlparse(str(url or "").strip())
        except Exception:
            return None

        host = parsed.netloc.lower()
        path = parsed.path.strip("/")
        parts = [segment for segment in path.split("/") if segment]

        if host == "raw.githubusercontent.com" and len(parts) >= 4:
            owner, repo, ref = parts[:3]
            remote_path = "/".join(parts[3:])
            return {"owner": owner, "repo": repo, "ref": ref, "remote_path": remote_path}

        if host == "github.com" and len(parts) >= 5 and parts[2] == "blob":
            owner, repo, _, ref = parts[:4]
            remote_path = "/".join(parts[4:])
            return {"owner": owner, "repo": repo, "ref": ref, "remote_path": remote_path}
        return None

    def fetch_path_commit(self, owner: str, repo: str, *, ref: str, remote_path: str, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> dict[str, Any] | None:
        """读取某个文件路径最近一次提交，用于判断单文件更新时间。"""
        normalized_ref = str(ref or "").strip()
        normalized_path = str(remote_path or "").strip().lstrip("/")
        if not normalized_path:
            return None

        cache_key = ("path_commit", owner.lower(), repo.lower(), normalized_ref or "latest", normalized_path)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_API_BASE}/{owner}/{repo}/commits",
                params={"path": normalized_path, "sha": normalized_ref, "per_page": 1},
                headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            self._raise_for_github_status(response, f"{owner}/{repo}/commits?path={normalized_path}")
            payload = response.json()
            if isinstance(payload, list):
                payload = payload[0] if payload else None
            self._store_cached_payload(cache_key, payload)
            return payload

    def fetch_file_metadata(self, owner: str, repo: str, *, ref: str, remote_path: str, timeout: tuple[int, int] = (8, 25), missing_ok: bool = False) -> dict[str, Any] | None:
        """读取 GitHub 单文件元数据，并尽量补齐最近更新时间。"""
        normalized_ref = str(ref or "").strip()
        normalized_path = str(remote_path or "").strip().lstrip("/")
        if not normalized_path:
            return None

        cache_key = ("file_meta", owner.lower(), repo.lower(), normalized_ref or "latest", normalized_path)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_API_BASE}/{owner}/{repo}/contents/{quote(normalized_path)}",
                params={"ref": normalized_ref},
                headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            self._raise_for_github_status(response, f"{owner}/{repo}/contents/{normalized_path}")
            payload = response.json()

        latest_commit = self.fetch_path_commit(
            owner,
            repo,
            ref=normalized_ref,
            remote_path=normalized_path,
            timeout=timeout,
            missing_ok=True,
        )
        updated_at = self._parse_iso_datetime_to_ms(self._extract_commit_timestamp(latest_commit))
        result = {
            "signature": str(payload.get("sha") or ""),
            "size": int(payload.get("size") or 0),
            "download_url": str(payload.get("download_url") or f"https://raw.githubusercontent.com/{owner}/{repo}/{normalized_ref}/{normalized_path}"),
            # 外部库没有稳定语义版本，这里把短 SHA 作为远端版本提示。
            "version": str(payload.get("sha") or "")[:12],
            "updated_at": updated_at,
        }
        self._store_cached_payload(cache_key, result)
        return result

    def fetch_repo(self, owner: str, repo: str, *, timeout: tuple[int, int] = (10, 30), missing_ok: bool = False) -> dict[str, Any] | None:
        """读取仓库基础信息。

        这里单独保留仓库查询，是因为默认分支等信息既会用于 UI 展示，也会用于源码包解析。
        """
        cache_key = ("repo", owner.lower(), repo.lower())
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_API_BASE}/{owner}/{repo}",
                headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=30)
                return None
            self._raise_for_github_status(response, f"{owner}/{repo}")
            payload = response.json()
            self._store_cached_payload(cache_key, payload)
            return payload

    def fetch_release(self, owner: str, repo: str, *, tag: str = "", timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> dict[str, Any] | None:
        """读取 Release 元数据。

        `tag` 为空时走 latest；不为空时按指定 tag 查。
        `missing_ok` 允许调用方把 404 当成“没有 Release”而不是异常。
        """
        endpoint = "releases/latest" if not tag else f"releases/tags/{tag}"
        cache_key = ("release", owner.lower(), repo.lower(), tag or "latest")
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_API_BASE}/{owner}/{repo}/{endpoint}",
                headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            self._raise_for_github_status(response, f"{owner}/{repo}/{endpoint}")
            payload = response.json()
            self._store_cached_payload(cache_key, payload)
            return payload

    def fetch_commit(self, owner: str, repo: str, *, ref: str = "", timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> dict[str, Any] | None:
        """读取指定分支或标签当前指向的提交信息。

        这里专门拉 commit，是为了给源码包模式生成稳定的“已部署版本”标识，
        避免继续把 `main`/`master` 这种分支名误当作具体版本。
        """
        normalized_ref = str(ref or "").strip()
        endpoint = f"commits/{normalized_ref}" if normalized_ref else "commits"
        cache_key = ("commit", owner.lower(), repo.lower(), normalized_ref or "latest")
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_API_BASE}/{owner}/{repo}/{endpoint}",
                headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            self._raise_for_github_status(response, f"{owner}/{repo}/{endpoint}")
            payload = response.json()
            if isinstance(payload, list):
                payload = payload[0] if payload else None
            self._store_cached_payload(cache_key, payload)
            return payload

    def fetch_latest_release(self, owner: str, repo: str, *, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> dict[str, Any] | None:
        """兼容旧接口，内部统一复用 `fetch_release()`。"""
        return self.fetch_release(owner, repo, timeout=timeout, missing_ok=missing_ok)

    def fetch_repo_page(self, owner: str, repo: str, *, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> str | None:
        """读取仓库网页 HTML。

        这条链路不走 GitHub API 配额，适合在 rate limit 时退化获取基础元数据。
        """
        cache_key = ("repo_page", owner.lower(), repo.lower())
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_WEB_BASE}/{owner}/{repo}",
                headers=self._build_github_headers({"Accept": "text/html,application/xhtml+xml"}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            response.raise_for_status()
            payload = response.text
            self._store_cached_payload(cache_key, payload, ttl_seconds=120)
            return payload

    def fetch_release_web(self, owner: str, repo: str, *, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> dict[str, Any] | None:
        """通过 `releases/latest` 的跳转位置解析最新 Release tag。

        这个方案不依赖 GitHub REST API，适合和直链策略组合。
        """
        cache_key = ("release_web", owner.lower(), repo.lower())
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_WEB_BASE}/{owner}/{repo}/releases/latest",
                headers=self._build_github_headers({"Accept": "text/html,application/xhtml+xml"}),
                timeout=timeout,
                allow_redirects=False,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=120)
                return None
            if response.status_code in (301, 302, 303, 307, 308):
                location = str(response.headers.get("Location") or "").strip()
                tag_match = re.search(r"/releases/tag/([^/?#]+)", location)
                tag_name = unquote(tag_match.group(1)) if tag_match else ""
                payload = {
                    "tag_name": tag_name,
                    "name": tag_name,
                    "zipball_url": f"{GITHUB_WEB_BASE}/{owner}/{repo}/archive/refs/tags/{tag_name}.zip" if tag_name else "",
                    "html_url": location,
                }
                self._store_cached_payload(cache_key, payload, ttl_seconds=120)
                return payload
            response.raise_for_status()
            self._store_cached_payload(cache_key, None, ttl_seconds=120)
            return None

    def fetch_release_assets_web(self, owner: str, repo: str, *, tag: str = "", timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> dict[str, Any] | None:
        """通过 GitHub 网页的 expanded_assets 片段读取 Release 资产列表。

        这条链路不依赖 REST API 配额，适合在 release API 被限流时继续拿真实附件 URL。
        """
        resolved_tag = str(tag or "").strip()
        if not resolved_tag:
            latest_release = self.fetch_release_web(owner, repo, timeout=timeout, missing_ok=missing_ok)
            resolved_tag = str((latest_release or {}).get("tag_name") or "").strip()
        if not resolved_tag:
            return None

        cache_key = ("release_assets_web", owner.lower(), repo.lower(), resolved_tag)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_WEB_BASE}/{owner}/{repo}/releases/expanded_assets/{resolved_tag}",
                headers=self._build_github_headers({"Accept": "text/html,application/xhtml+xml"}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=120)
                return None
            response.raise_for_status()
            assets = self._parse_release_assets_from_html(response.text)
            payload = {
                "tag_name": resolved_tag,
                "name": resolved_tag,
                "assets": assets,
                "html_url": f"{GITHUB_WEB_BASE}/{owner}/{repo}/releases/tag/{resolved_tag}",
            }
            self._store_cached_payload(cache_key, payload, ttl_seconds=120)
            return payload

    def fetch_commit_web(self, owner: str, repo: str, *, ref: str, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> dict[str, Any] | None:
        """通过 GitHub commits Atom feed 获取最新提交时间。

        Atom feed 是公开网页链路的一部分，通常比 REST API 更适合做限流时的补位信息源。
        """
        normalized_ref = str(ref or "").strip()
        if not normalized_ref:
            return None

        cache_key = ("commit_web", owner.lower(), repo.lower(), normalized_ref)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        with build_retry_session() as session:
            response = session.get(
                f"{GITHUB_WEB_BASE}/{owner}/{repo}/commits/{normalized_ref}.atom",
                headers=self._build_github_headers({"Accept": "application/atom+xml,text/xml"}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=120)
                return None
            response.raise_for_status()
            payload = self._parse_commit_atom_payload(response.text)
            self._store_cached_payload(cache_key, payload, ttl_seconds=120)
            return payload

    def fetch_repo_info(self, url: str, *, source_branch: str = ""):
        """获取仓库基础信息、默认分支、最新 Release 和源码分支版本信息。

        优先使用 GitHub API；如果命中限流或 API 不可用，再退化到网页/直链/本地缓存。
        """
        owner, repo = self.parse_repo_url(url)
        if not owner or not repo:
            return {"error": "无效的 GitHub 链接"}
        normalized_source_branch = str(source_branch or "").strip()
        cache_key = ("repo_info", owner.lower(), repo.lower(), normalized_source_branch or "_auto")
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            return cached

        primary_error: Exception | None = None
        try:
            payload = self._fetch_repo_info_via_api(owner, repo, source_branch=normalized_source_branch)
            self._store_cached_payload(cache_key, payload)
            return payload
        except (GithubApiError, requests.RequestException) as exc:
            primary_error = exc
            logger.warning("GitHub repo info API failed, fallback to web/cache: repo=%s/%s error=%s", owner, repo, exc)

        web_payload = self._fetch_repo_info_via_web(owner, repo, source_branch=normalized_source_branch)
        if web_payload:
            if primary_error:
                web_payload["fetch_warning"] = str(primary_error)
            self._store_cached_payload(cache_key, web_payload, ttl_seconds=120)
            return web_payload

        record_payload = self._fetch_repo_info_from_record_cache(url, owner, repo, source_branch=normalized_source_branch)
        if record_payload:
            if primary_error:
                record_payload["fetch_warning"] = str(primary_error)
            self._store_cached_payload(cache_key, record_payload, ttl_seconds=120)
            return record_payload

        if primary_error and normalized_source_branch:
            minimal_payload = self._build_repo_info_payload(
                owner,
                repo,
                normalized_source_branch,
                normalized_source_branch,
                None,
                None,
                info_source="minimal",
                degraded=True,
            )
            minimal_payload["fetch_warning"] = str(primary_error)
            self._store_cached_payload(cache_key, minimal_payload, ttl_seconds=60)
            return minimal_payload

        if primary_error:
            raise primary_error
        return {"error": "找不到该仓库"}

    def record_timeline(self, repo_url: str, action: str, message: str):
        """主动记录操作轨迹"""
        with db.atomic():
            GithubTimeline.create(repo_url=repo_url, action=action, message=message)

    def install_from_github(self, download_mgr: DownloadManager, request: GithubInstallRequest) -> str:
        """统一入口：把结构化请求编排成“解析 -> 下载 -> 安装”。

        这里故意不把逻辑拆散给调用方，避免各业务模块重复拼 GitHub URL、重复写下载回调。
        """
        normalized = self._normalize_install_request(request)
        resolved = self._resolve_artifact(normalized)
        timeline_repo_url = normalized.timeline_repo_url or normalized.repo_url

        if timeline_repo_url:
            self.record_timeline(
                timeline_repo_url,
                "download",
                normalized.download_start_message or f"开始获取压缩包: {resolved.filename}",
            )

        def on_download_complete(task: DownloadTask):
            self._handle_install(task, normalized, resolved)

        def on_download_error(task: DownloadTask):
            self._handle_download_error(task, normalized, resolved)

        # DownloadManager 只关心“下载什么”和“完成后回调什么”，不需要知道 GitHub 语义。
        return download_mgr.add_task(
            url=resolved.download_url,
            dest_dir=normalized.install.download_dir,
            filename=resolved.filename,
            expected_hash=normalized.expected_hash or None,
            hash_algorithm=normalized.hash_algorithm,
            on_complete=on_download_complete,
            on_error=on_download_error,
        )

    def install_repo_mod(self, download_mgr: DownloadManager, repo_url: str, install_type: str = "source", target_version: str = "") -> str:
        """GitHub 模组安装的便捷封装。

        这是一个“薄封装”：只负责把旧的 source/release 语义翻译成通用安装请求，
        真正的下载与安装流程仍走 `install_from_github()`。
        """
        owner, repo = self.parse_repo_url(repo_url)
        if not owner or not repo:
            raise ValueError("无效的 GitHub 仓库链接")

        is_release_mode = install_type == "release"
        source_ref = str(target_version or "").strip()
        self_mods_path = str(settings.config.self_mods_path or "").strip()
        if not self_mods_path:
            raise ValueError("未配置管理器 Mod 目录，无法部署 GitHub 模组")
        if not source_ref and not is_release_mode:
            # Source 模式默认跟随仓库默认分支，而不是硬编码 main/master。
            source_ref = self._resolve_default_branch(owner, repo, repo_url=repo_url)

        artifact_request = self._build_repo_artifact_request(
            owner,
            repo,
            repo_url=repo_url,
            is_release_mode=is_release_mode,
            target_version=source_ref,
        )
        request = GithubInstallRequest(
            repo_url=repo_url,
            owner=owner,
            repo=repo,
            artifact=artifact_request,
            install=GithubInstallPlan(
                action=GITHUB_INSTALL_EXTRACT_THEN_MOVE,
                download_dir=str(HOME_DIR / "Downloads"),
                move_target_dir=self_mods_path,
                final_name=f"_GH_{repo}",
                source_resolver=GITHUB_RESOLVER_MOD_ROOT,
                overwrite_existing=True,
                cleanup_archive=True,
            ),
            timeline_repo_url=repo_url,
            download_start_message="开始获取压缩包",
            install_start_message="压缩包获取成功，正在解压...",
            success_toast=f"{repo} 部署完成",
            failure_toast=f"{repo} 部署失败",
            post_install=lambda result: self._update_mod_record(repo_url, result.version, f"_GH_{repo}"),
        )
        return self.install_from_github(download_mgr, request)

    def _build_repo_artifact_request(self, owner: str, repo: str, *, repo_url: str, is_release_mode: bool, target_version: str) -> GithubArtifactRequest:
        normalized_version = str(target_version or "").strip()
        if not is_release_mode:
            return GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE,
                source_ref=normalized_version,
                source_ref_type=GITHUB_SOURCE_BRANCH,
            )

        fallback_download_url = ""
        fallback_filename = ""
        if normalized_version:
            fallback_download_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{normalized_version}.zip"
            fallback_filename = f"{repo}_{normalized_version}.zip"

        return GithubArtifactRequest(
            kind=GITHUB_ARTIFACT_RELEASE_ASSET,
            release_tag=normalized_version,
            asset_name_prefix=repo,
            asset_name_suffix=".zip",
            fallback_download_url=fallback_download_url,
            fallback_filename=fallback_filename,
            fallback_version=normalized_version,
            fallback_asset_name=fallback_filename,
        )

    def trigger_download(self, download_mgr: DownloadManager, repo_url: str, install_type: str = "source", target_version: str = ""):
        """兼容旧调用名，内部统一走安装计划路径"""
        return self.install_repo_mod(download_mgr, repo_url, install_type, target_version)

    def _normalize_install_request(self, request: GithubInstallRequest) -> GithubInstallRequest:
        """把调用方输入标准化。

        目的不是“校验漂亮”，而是保证后续解析阶段只面对一套稳定字段，减少分支判断。
        """
        owner = str(request.owner or "").strip()
        repo = str(request.repo or "").strip()
        repo_url = str(request.repo_url or "").strip()

        if (not owner or not repo) and repo_url:
            owner, repo = self.parse_repo_url(repo_url)

        if not owner or not repo:
            raise ValueError("缺少有效的 GitHub 仓库信息")

        artifact = request.artifact or GithubArtifactRequest()
        install = request.install or GithubInstallPlan()
        download_dir = str(install.download_dir or HOME_DIR / "Downloads")

        return GithubInstallRequest(
            repo_url=repo_url or f"https://github.com/{owner}/{repo}",
            owner=owner,
            repo=repo,
            artifact=GithubArtifactRequest(
                kind=str(artifact.kind or GITHUB_ARTIFACT_SOURCE_ARCHIVE),
                release_tag=str(artifact.release_tag or "").strip(),
                source_ref=str(artifact.source_ref or "").strip(),
                source_ref_type=str(artifact.source_ref_type or GITHUB_SOURCE_BRANCH).strip(),
                asset_name=str(artifact.asset_name or "").strip(),
                asset_name_prefix=str(artifact.asset_name_prefix or "").strip(),
                asset_name_suffix=str(artifact.asset_name_suffix or "").strip(),
                asset_name_pattern=str(artifact.asset_name_pattern or "").strip(),
                fallback_download_url=str(artifact.fallback_download_url or "").strip(),
                fallback_filename=str(artifact.fallback_filename or "").strip(),
                fallback_version=str(artifact.fallback_version or "").strip(),
                fallback_asset_name=str(artifact.fallback_asset_name or "").strip(),
            ),
            install=GithubInstallPlan(
                action=str(install.action or GITHUB_INSTALL_DOWNLOAD_ONLY),
                download_dir=download_dir,
                extract_dir=str(install.extract_dir or "").strip(),
                move_target_dir=str(install.move_target_dir or "").strip(),
                final_name=str(install.final_name or "").strip(),
                source_resolver=str(install.source_resolver or GITHUB_RESOLVER_ARCHIVE_ROOT).strip(),
                source_subpath=str(install.source_subpath or "").strip(),
                overwrite_existing=bool(install.overwrite_existing),
                cleanup_archive=bool(install.cleanup_archive),
            ),
            expected_hash=str(request.expected_hash or "").strip(),
            hash_algorithm=str(request.hash_algorithm or "md5").strip(),
            timeline_repo_url=str(request.timeline_repo_url or repo_url or "").strip(),
            download_start_message=str(request.download_start_message or "").strip(),
            install_start_message=str(request.install_start_message or "").strip(),
            success_message=str(request.success_message or "").strip(),
            success_toast=str(request.success_toast or "").strip(),
            failure_toast=str(request.failure_toast or "").strip(),
            post_install=request.post_install,
            on_install_error=request.on_install_error,
        )

    def _resolve_artifact(self, request: GithubInstallRequest) -> GithubResolvedArtifact:
        """根据产物类型把请求解析成具体下载对象。"""
        if request.artifact.kind == GITHUB_ARTIFACT_RELEASE_ASSET:
            return self._resolve_release_asset(request)
        if request.artifact.kind == GITHUB_ARTIFACT_SOURCE_ARCHIVE:
            return self._resolve_source_archive(request)
        raise ValueError(f"不支持的 GitHub 产物类型: {request.artifact.kind}")

    def _resolve_release_asset(self, request: GithubInstallRequest) -> GithubResolvedArtifact:
        """解析 Release 资产。

        先取 Release，再按名称规则选资产。这样调用方只描述筛选条件，不必自己遍历 assets。
        """
        try:
            release = self.fetch_release(
                request.owner,
                request.repo,
                tag=request.artifact.release_tag,
            )
            resolved = self._build_release_asset_from_payload(request, release)
            if resolved:
                return resolved
        except Exception as exc:
            try:
                web_release = self.fetch_release_assets_web(
                    request.owner,
                    request.repo,
                    tag=request.artifact.release_tag,
                )
                resolved = self._build_release_asset_from_payload(request, web_release)
                if resolved:
                    logger.warning(
                        "GitHub release resolved via web assets fallback: repo=%s/%s tag=%s error=%s",
                        request.owner,
                        request.repo,
                        request.artifact.release_tag or "latest",
                        exc,
                    )
                    return resolved
            except Exception as web_exc:
                logger.warning(
                    "GitHub release web assets fallback failed: repo=%s/%s tag=%s error=%s",
                    request.owner,
                    request.repo,
                    request.artifact.release_tag or "latest",
                    web_exc,
                )
            fallback = self._build_release_fallback(request, exc)
            if fallback:
                return fallback
            raise
        raise ValueError("未找到符合条件的 GitHub Release 资产")

    def _resolve_source_archive(self, request: GithubInstallRequest) -> GithubResolvedArtifact:
        """解析源码包下载链接。

        GitHub 对 branch 和 tag 的归档 URL 规则不同，所以这里统一封装掉。
        """
        source_ref_type = request.artifact.source_ref_type or GITHUB_SOURCE_BRANCH
        source_ref = str(request.artifact.source_ref or "").strip()
        resolved_version = source_ref

        if source_ref_type == GITHUB_SOURCE_BRANCH and not source_ref:
            source_ref = self._resolve_default_branch(request.owner, request.repo, repo_url=request.repo_url)
        if not source_ref:
            raise ValueError("GitHub 源码包缺少目标分支或标签")

        if source_ref_type == GITHUB_SOURCE_TAG:
            download_url = f"https://github.com/{request.owner}/{request.repo}/archive/refs/tags/{source_ref}.zip"
            filename = f"{request.repo}_{source_ref}.zip"
        else:
            # 分支模式优先拿 commit 时间生成版本；拿不到时降级为 branch，不阻断源码包下载。
            resolved_version = self._resolve_source_branch_version(
                request.owner,
                request.repo,
                source_ref,
                repo_url=request.repo_url,
            )
            download_url = f"https://github.com/{request.owner}/{request.repo}/archive/refs/heads/{source_ref}.zip"
            filename = f"{request.repo}_{source_ref}_source.zip"

        return GithubResolvedArtifact(
            repo_url=request.repo_url,
            owner=request.owner,
            repo=request.repo,
            kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE,
            version=resolved_version,
            download_url=download_url,
            filename=filename,
        )

    def _select_release_asset(self, assets: list[dict[str, Any]], request: GithubArtifactRequest) -> dict[str, Any] | None:
        """按声明式规则筛资产。

        这里按“精确名 -> 前缀 -> 后缀 -> 正则”的组合过滤，足够通用，也便于业务层表达选择条件。
        """
        pattern = str(request.asset_name_pattern or "").strip()
        regex = re.compile(pattern) if pattern else None
        request_asset_name = str(request.asset_name or "")
        request_prefix = str(request.asset_name_prefix or "")
        request_suffix = str(request.asset_name_suffix or "")
        request_asset_name_lower = request_asset_name.lower()
        request_prefix_lower = request_prefix.lower()
        request_suffix_lower = request_suffix.lower()

        for asset in assets:
            name = str(asset.get("name") or "")
            name_lower = name.lower()
            if request_asset_name and name_lower != request_asset_name_lower:
                continue
            if request_prefix and not name_lower.startswith(request_prefix_lower):
                continue
            if request_suffix and not name_lower.endswith(request_suffix_lower):
                continue
            if regex and not regex.search(name):
                continue
            if not str(asset.get("browser_download_url") or "").strip():
                continue
            return asset

        # 兼容通用 release 模式：如果没给精确规则，但 Release 下只有一个 zip 资产，就直接用它。
        if not request_asset_name and request_suffix_lower == ".zip":
            zip_assets = [
                asset for asset in assets
                if str(asset.get("name") or "").lower().endswith(".zip")
                and str(asset.get("browser_download_url") or "").strip()
            ]
            if len(zip_assets) == 1:
                return zip_assets[0]
        return None

    def _build_release_asset_from_payload(self, request: GithubInstallRequest, release: dict[str, Any] | None) -> GithubResolvedArtifact | None:
        if not release:
            return None

        asset = self._select_release_asset(release.get("assets", []), request.artifact)
        if not asset:
            return None

        return GithubResolvedArtifact(
            repo_url=request.repo_url,
            owner=request.owner,
            repo=request.repo,
            kind=GITHUB_ARTIFACT_RELEASE_ASSET,
            version=str(release.get("tag_name") or request.artifact.release_tag or "latest"),
            download_url=str(asset.get("browser_download_url") or ""),
            filename=str(asset.get("name") or ""),
            asset_name=str(asset.get("name") or ""),
        )

    @staticmethod
    def _parse_release_assets_from_html(html_text: str) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        pattern = re.compile(
            r'<a[^>]+href="(?P<href>/[^"]+/releases/download/[^"]+)"[^>]*>'
            r'(?P<body>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        name_pattern = re.compile(
            r'<span[^>]*class="[^"]*Truncate-text text-bold[^"]*"[^>]*>(?P<name>.*?)</span>',
            re.IGNORECASE | re.DOTALL,
        )

        for match in pattern.finditer(html_text or ""):
            href = str(match.group("href") or "").strip()
            if not href:
                continue
            download_url = href if href.startswith("http") else f"{GITHUB_WEB_BASE}{href}"
            if download_url in seen_urls:
                continue
            name_match = name_pattern.search(match.group("body") or "")
            name = html.unescape(re.sub(r"<[^>]+>", "", name_match.group("name") if name_match else "")).strip()
            if not name:
                continue
            seen_urls.add(download_url)
            assets.append({
                "name": name,
                "browser_download_url": download_url,
            })
        return assets

    def _handle_install(self, task: DownloadTask, request: GithubInstallRequest, resolved: GithubResolvedArtifact) -> None:
        """下载成功后的安装总入口。

        这里统一处理时间线、toast、后置钩子和错误落盘，避免每个业务模块自己组装这套收尾逻辑。
        """
        timeline_repo_url = request.timeline_repo_url or request.repo_url
        try:
            if timeline_repo_url and request.install.action != GITHUB_INSTALL_DOWNLOAD_ONLY:
                self.record_timeline(
                    timeline_repo_url,
                    "extract",
                    request.install_start_message or "压缩包获取成功，正在执行安装计划...",
                )
            result = self._execute_install_plan(task, request, resolved)
            if request.post_install:
                request.post_install(result)
            if timeline_repo_url:
                self.record_timeline(
                    timeline_repo_url,
                    "success",
                    request.success_message or f"部署成功！已安装版本: {resolved.version}",
                )
            if request.success_toast:
                EventBus.send_toast(request.success_toast, type="success", duration=4000)
        except Exception as exc:
            logger.error("GitHub install failed: %s", exc, exc_info=True)
            if timeline_repo_url:
                self.record_timeline(timeline_repo_url, "error", f"部署失败: {exc}")
            if request.failure_toast:
                EventBus.send_toast(f"{request.failure_toast}: {exc}", type="error", duration=6000)
            if request.on_install_error:
                request.on_install_error(exc, task, resolved)

    def _handle_download_error(self, task: DownloadTask, request: GithubInstallRequest, _resolved: GithubResolvedArtifact) -> None:
        """下载失败时补 GitHub 域内反馈。"""
        timeline_repo_url = request.timeline_repo_url or request.repo_url
        if timeline_repo_url:
            self.record_timeline(timeline_repo_url, "error", f"下载失败: {task.error_msg}")
        if request.failure_toast:
            EventBus.send_toast(
                f"{request.failure_toast}: {task.error_msg or task.filename}",
                type="error",
                duration=6000,
            )

    def _execute_install_plan(self, task: DownloadTask, request: GithubInstallRequest, resolved: GithubResolvedArtifact) -> GithubInstallResult:
        """执行通用安装动作。

        这里是这次抽象的核心：不同业务只改 plan，不再自己写“解压到哪、移动到哪、是否删包”等过程代码。
        """
        download_path = Path(task.dest_path)
        plan = request.install
        result = GithubInstallResult(
            repo_url=request.repo_url,
            owner=request.owner,
            repo=request.repo,
            version=resolved.version,
            download_url=resolved.download_url,
            download_path=str(download_path),
            filename=resolved.filename,
            artifact_kind=resolved.kind,
            asset_name=resolved.asset_name,
        )

        if plan.action == GITHUB_INSTALL_DOWNLOAD_ONLY:
            result.installed_path = str(download_path)
            return result

        if plan.action == GITHUB_INSTALL_EXTRACT:
            # 直接解压适合 todds 这类工具链资源，目录结构就是最终结果。
            extract_dir = Path(plan.extract_dir or plan.download_dir)
            extract_dir.mkdir(parents=True, exist_ok=True)
            extract_zip(str(download_path), str(extract_dir))
            result.extracted_path = str(extract_dir)
            result.installed_path = str(extract_dir)
            self._cleanup_archive(download_path, plan)
            return result

        if plan.action == GITHUB_INSTALL_EXTRACT_THEN_MOVE:
            # 先解压到临时目录，再解析出真正要部署的根目录，避免把 GitHub 外层包裹目录直接搬进目标位置。
            move_target_dir = Path(plan.move_target_dir)
            if not str(move_target_dir).strip():
                raise ValueError("extract_then_move 缺少 move_target_dir")
            move_target_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory(prefix="github_install_") as temp_dir:
                temp_root = Path(temp_dir)
                extract_zip(str(download_path), temp_dir)
                source_path = self._resolve_install_source(temp_root, plan)
                final_name = plan.final_name or source_path.name
                dest_path = move_target_dir / final_name
                self._prepare_destination(dest_path, overwrite_existing=plan.overwrite_existing)
                shutil.move(str(source_path), str(dest_path))
                result.extracted_path = str(source_path)
                result.installed_path = str(dest_path)

            self._cleanup_archive(download_path, plan)
            return result

        if plan.action == GITHUB_INSTALL_RUN_INSTALLER:
            raise NotImplementedError("run_installer 安装动作尚未实现")

        raise ValueError(f"不支持的安装动作: {plan.action}")

    def _build_release_fallback(self, request: GithubInstallRequest, exc: Exception) -> GithubResolvedArtifact | None:
        """当 GitHub API 不可用时，允许调用方提供一个兜底直链。"""
        fallback_url = str(request.artifact.fallback_download_url or "").strip()
        fallback_filename = str(request.artifact.fallback_filename or "").strip()
        if not fallback_url or not fallback_filename:
            return None

        logger.warning(
            "GitHub release resolve failed, fallback to direct download: repo=%s/%s error=%s",
            request.owner,
            request.repo,
            exc,
        )
        return GithubResolvedArtifact(
            repo_url=request.repo_url,
            owner=request.owner,
            repo=request.repo,
            kind=GITHUB_ARTIFACT_RELEASE_ASSET,
            version=str(request.artifact.fallback_version or request.artifact.release_tag or "fallback"),
            download_url=fallback_url,
            filename=fallback_filename,
            asset_name=str(request.artifact.fallback_asset_name or fallback_filename),
        )

    def _fetch_repo_info_via_api(self, owner: str, repo: str, *, source_branch: str = "") -> dict[str, Any]:
        """使用 GitHub API 组装完整的仓库信息。"""
        repo_res = self.fetch_repo(owner, repo, missing_ok=True)
        if not repo_res:
            return {"error": "找不到该仓库"}

        default_branch = str(repo_res.get("default_branch") or "main")
        resolved_source_branch = str(source_branch or default_branch).strip() or default_branch
        release_info = self.fetch_latest_release(owner, repo, missing_ok=True)
        source_commit = self.fetch_commit(owner, repo, ref=resolved_source_branch, missing_ok=True)
        return self._build_repo_info_payload(
            owner,
            repo,
            default_branch,
            resolved_source_branch,
            release_info,
            source_commit,
            info_source="api",
            degraded=False,
        )

    def _fetch_repo_info_via_web(self, owner: str, repo: str, *, source_branch: str = "") -> dict[str, Any] | None:
        """使用 GitHub 网页链路组装仓库信息。

        这里不依赖 API quota，适合作为 `github_fetch_info` 的替代信息源。
        """
        try:
            repo_page = self.fetch_repo_page(owner, repo, missing_ok=True)
            if repo_page is None:
                return None
            default_branch = self._parse_default_branch_from_html(repo_page) or "main"
            resolved_source_branch = str(source_branch or default_branch).strip() or default_branch
            release_info = self.fetch_release_web(owner, repo, missing_ok=True)
            source_commit = self.fetch_commit_web(owner, repo, ref=resolved_source_branch, missing_ok=True)
            return self._build_repo_info_payload(
                owner,
                repo,
                default_branch,
                resolved_source_branch,
                release_info,
                source_commit,
                info_source="web",
                degraded=True,
            )
        except Exception as exc:
            logger.warning("GitHub web fallback failed: repo=%s/%s error=%s", owner, repo, exc)
            return None

    def _fetch_repo_info_from_record_cache(self, repo_url: str, owner: str, repo: str, *, source_branch: str = "") -> dict[str, Any] | None:
        """从本地订阅记录缓存中恢复仓库信息。

        这是最后一道兜底，主要服务于“已订阅仓库在离线或限流时仍可继续部署”。
        """
        record = GithubModRecord.get_or_none(repo_url=repo_url)
        if not record:
            return None

        online_info = record.online_info_cache or {}
        default_branch = str(record.target_branch or online_info.get("default_branch") or source_branch or "main")
        resolved_source_branch = str(source_branch or online_info.get("latest_source_branch") or default_branch).strip() or default_branch
        release_info = {
            "tag_name": str(online_info.get("latest_release_tag") or "").strip(),
            "name": str(online_info.get("latest_release_name") or "").strip(),
            "zipball_url": str(online_info.get("release_zip_url") or "").strip(),
        }
        source_commit = {
            "sha": str(online_info.get("latest_source_commit_sha") or "").strip(),
            "commit": {
                "author": {
                    "date": str(online_info.get("latest_source_commit_at") or "").strip(),
                }
            },
        }
        return self._build_repo_info_payload(
            owner,
            repo,
            default_branch,
            resolved_source_branch,
            release_info if release_info["tag_name"] else None,
            source_commit if self._extract_commit_timestamp(source_commit) else None,
            info_source="record_cache",
            degraded=True,
        )

    def _build_repo_info_payload(self, owner: str, repo: str, default_branch: str, resolved_source_branch: str, release_info: dict[str, Any] | None, source_commit: dict[str, Any] | None, *, info_source: str, degraded: bool) -> dict[str, Any]:
        """把不同来源的数据统一整理成前端可消费的结构。"""
        source_commit_sha = str((source_commit or {}).get("sha") or "")
        source_commit_at = self._extract_commit_timestamp(source_commit)
        has_release = bool(release_info and str(release_info.get("tag_name") or "").strip())
        return {
            "owner": owner,
            "repo": repo,
            "default_branch": str(default_branch or "main").strip() or "main",
            "has_release": has_release,
            "latest_release_tag": str((release_info or {}).get("tag_name") or "").strip(),
            "latest_release_name": str((release_info or {}).get("name") or "").strip(),
            "release_zip_url": str((release_info or {}).get("zipball_url") or "").strip(),
            "latest_source_branch": str(resolved_source_branch or default_branch or "main").strip() or "main",
            "latest_source_commit_sha": source_commit_sha,
            "latest_source_commit_at": source_commit_at,
            "latest_source_version": self._build_source_version(resolved_source_branch or default_branch or "main", source_commit_at),
            "info_source": str(info_source or "unknown").strip() or "unknown",
            "is_degraded": bool(degraded),
        }

    def _resolve_default_branch(self, owner: str, repo: str, *, repo_url: str = "") -> str:
        """解析仓库默认分支。

        默认分支只是安装的入口参数，不值得因为它查不到就阻断下载，所以这里必须允许多级降级。
        """
        try:
            repo_info = self.fetch_repo(owner, repo, missing_ok=True)
            if repo_info:
                default_branch = str(repo_info.get("default_branch") or "").strip()
                if default_branch:
                    return default_branch
        except Exception as exc:
            logger.warning("Resolve default branch via API failed: repo=%s/%s error=%s", owner, repo, exc)

        web_info = self._fetch_repo_info_via_web(owner, repo)
        if web_info:
            default_branch = str(web_info.get("default_branch") or "").strip()
            if default_branch:
                return default_branch

        record_info = self._fetch_repo_info_from_record_cache(repo_url or f"{GITHUB_WEB_BASE}/{owner}/{repo}", owner, repo)
        if record_info:
            default_branch = str(record_info.get("default_branch") or "").strip()
            if default_branch:
                return default_branch

        return "main"

    def _resolve_source_branch_version(self, owner: str, repo: str, branch_name: str, *, repo_url: str = "") -> str:
        """解析源码分支的部署版本。

        优先拿 commit 时间；若 API 限流，则退化到网页 feed；再不行就回退为裸分支名。
        """
        normalized_branch = str(branch_name or "").strip() or "main"
        try:
            source_commit = self.fetch_commit(owner, repo, ref=normalized_branch, missing_ok=True)
            return self._build_source_version(normalized_branch, self._extract_commit_timestamp(source_commit))
        except Exception as exc:
            logger.warning("Resolve source commit via API failed, fallback to web/cache: repo=%s/%s branch=%s error=%s", owner, repo, normalized_branch, exc)

        try:
            source_commit = self.fetch_commit_web(owner, repo, ref=normalized_branch, missing_ok=True)
            if source_commit:
                return self._build_source_version(normalized_branch, self._extract_commit_timestamp(source_commit))
        except Exception as exc:
            logger.warning("Resolve source commit via web failed: repo=%s/%s branch=%s error=%s", owner, repo, normalized_branch, exc)

        record_info = self._fetch_repo_info_from_record_cache(repo_url or f"{GITHUB_WEB_BASE}/{owner}/{repo}", owner, repo, source_branch=normalized_branch)
        if record_info:
            cached_version = str(record_info.get("latest_source_version") or "").strip()
            if cached_version:
                return cached_version

        return normalized_branch

    @staticmethod
    def _parse_default_branch_from_html(html: str) -> str:
        """从仓库页面 HTML 中提取默认分支。

        GitHub 页面内嵌的 JSON 字段可能随时间微调，所以这里保留多组正则作为兼容兜底。
        """
        patterns = (
            r'"defaultBranch"\s*:\s*"([^"]+)"',
            r'"default_branch"\s*:\s*"([^"]+)"',
            r'"defaultBranchRef"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"',
            r'octolytics-dimension-repository_default_branch"\s+content="([^"]+)"',
        )
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return str(match.group(1) or "").strip()
        return ""

    @staticmethod
    def _parse_commit_atom_payload(xml_text: str) -> dict[str, Any] | None:
        """解析 GitHub commits Atom feed 的首条记录。"""
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None

        updated = str(entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
        commit_id = str(entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        commit_link = ""
        for link in entry.findall("atom:link", ns):
            href = str(link.get("href") or "").strip()
            if "/commit/" in href:
                commit_link = href
                break
        sha_match = re.search(r"/commit/([0-9a-f]{7,40})", commit_link or commit_id)
        sha = sha_match.group(1) if sha_match else ""
        return {
            "sha": sha,
            "commit": {
                "author": {
                    "date": updated,
                }
            },
        }

    @staticmethod
    def _extract_commit_timestamp(commit_payload: dict[str, Any] | None) -> str:
        """从 GitHub commit 响应里提取稳定的 UTC 时间戳字符串。"""
        if not commit_payload:
            return ""
        commit_info = commit_payload.get("commit") if isinstance(commit_payload, dict) else {}
        author_info = commit_info.get("author", {}) if isinstance(commit_info, dict) else {}
        committer_info = commit_info.get("committer", {}) if isinstance(commit_info, dict) else {}
        return str(author_info.get("date") or committer_info.get("date") or "").strip()

    @staticmethod
    def _parse_iso_datetime_to_ms(value: str) -> int:
        raw = str(value or "").strip()
        if not raw:
            return 0
        try:
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            return 0

    @staticmethod
    def _build_source_version(branch_name: str, commit_timestamp: str) -> str:
        """把源码分支部署版本编码成可读且可比较的稳定字符串。"""
        normalized_branch = str(branch_name or "").strip() or "source"
        normalized_time = str(commit_timestamp or "").strip()
        if not normalized_time:
            return normalized_branch
        return f"{normalized_branch}@{normalized_time}"

    def _resolve_install_source(self, temp_root: Path, plan: GithubInstallPlan) -> Path:
        """决定“解压后到底哪一层目录才是要安装的源目录”。"""
        if plan.source_subpath:
            candidate = temp_root / plan.source_subpath
            if candidate.exists():
                return candidate
            raise FileNotFoundError(f"未找到指定的压缩包内部路径: {plan.source_subpath}")

        if plan.source_resolver == GITHUB_RESOLVER_MOD_ROOT:
            mod_root = self._find_mod_root(temp_root)
            if not mod_root:
                raise FileNotFoundError("未能在压缩包中找到合法的 Mod 结构 (缺少 About.xml)")
            return mod_root

        archive_root = self._find_archive_root(temp_root)
        return archive_root or temp_root

    @staticmethod
    def _find_archive_root(temp_root: Path) -> Path | None:
        """优先取 GitHub 常见的单一外层目录，避免把临时解压根目录误认为真实内容目录。"""
        entries = [entry for entry in temp_root.iterdir()]
        if len(entries) == 1:
            return entries[0]
        directories = [entry for entry in entries if entry.is_dir()]
        if len(directories) == 1:
            return directories[0]
        return None

    @staticmethod
    def _find_mod_root(temp_root: Path) -> Path | None:
        """在解压结果里定位 RimWorld Mod 根目录。

        判断依据是 `About/About.xml`，这是现有工程里最稳定的 Mod 根特征。
        """
        for root, dirs, _files in os.walk(temp_root):
            if "About" in dirs:
                about_xml = Path(root) / "About" / "About.xml"
                if about_xml.exists():
                    return Path(root)
        return None

    @staticmethod
    def _prepare_destination(dest_path: Path, *, overwrite_existing: bool) -> None:
        """处理目标路径覆盖策略。

        统一在这里做删除/阻止覆盖，避免不同安装动作各自实现一套。
        """
        if not dest_path.exists():
            return
        if not overwrite_existing:
            raise FileExistsError(f"目标路径已存在: {dest_path}")
        if dest_path.is_dir():
            shutil.rmtree(dest_path)
        else:
            dest_path.unlink()

    @staticmethod
    def _cleanup_archive(download_path: Path, plan: GithubInstallPlan) -> None:
        """按计划决定是否清理下载包。"""
        if not plan.cleanup_archive:
            return
        try:
            download_path.unlink()
        except OSError:
            pass

    @staticmethod
    def _update_mod_record(repo_url: str, version: str, local_folder: str) -> None:
        """更新 GitHub 订阅记录。

        这一步保留在 GitHub manager 内，是因为它属于 GitHub 订阅域的数据，而不是通用安装器职责。
        """
        with db.atomic():
            record = GithubModRecord.get_or_none(repo_url=repo_url)
            if record:
                record.installed_version = version
                record.local_folder = local_folder
                record.last_sync_time = current_ms()
                record.save()

    def _build_github_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """GitHub API 单独使用浏览器风格 UA。

        这样做不是为了解决 rate limit，而是为了减少被某些网关按“非浏览器默认脚本”特殊对待的概率。
        """
        return merge_headers(headers, user_agent=GITHUB_BROWSER_USER_AGENT)

    def _raise_for_github_status(self, response, request_label: str) -> None:
        """把 GitHub 的 HTTP 错误转换成更可读的异常。"""
        if response.status_code < 400:
            return

        if response.status_code == 404:
            raise GithubApiError(f"GitHub 资源不存在: {request_label}")

        response_text = ""
        try:
            payload = response.json()
            response_text = str(payload.get("message") or "")
        except Exception:
            response_text = response.text or ""

        remaining = str(response.headers.get("X-RateLimit-Remaining") or "").strip()
        reset_at = str(response.headers.get("X-RateLimit-Reset") or "").strip()
        is_rate_limited = response.status_code == 403 and (
            remaining == "0" or "rate limit" in response_text.lower()
        )
        if is_rate_limited:
            reset_hint = ""
            if reset_at.isdigit():
                reset_hint = f"，预计重置时间戳: {reset_at}"
            raise GithubRateLimitError(f"GitHub API 限流: {request_label}{reset_hint}")

        response.raise_for_status()

    def _get_cached_payload(self, cache_key: tuple[str, ...]) -> Any:
        """读取共享缓存。

        这里用类级缓存，是因为项目里会临时 new 多个 GithubManager，需要让 todds 和 GitHub 页面共享结果。
        """
        cache_lock = GithubManager._cache_lock
        if cache_lock is None:
            return self._cache_miss

        now = time.time()
        with cache_lock:
            cached = GithubManager._response_cache.get(cache_key)
            if not cached:
                return self._cache_miss
            expires_at, payload = cached
            if expires_at < now:
                GithubManager._response_cache.pop(cache_key, None)
                return self._cache_miss
            return payload

    def _store_cached_payload(self, cache_key: tuple[str, ...], payload: Any, *, ttl_seconds: int = GITHUB_API_CACHE_TTL_SECONDS) -> None:
        """写入共享缓存。"""
        cache_lock = GithubManager._cache_lock
        if cache_lock is None:
            return
        with cache_lock:
            GithubManager._response_cache[cache_key] = (time.time() + max(1, int(ttl_seconds)), payload)
