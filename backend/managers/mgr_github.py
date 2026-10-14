import json
import base64
import os
import re
import shutil
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
import html
import hashlib
import threading
import zipfile
from copy import deepcopy
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse

import requests
from backend.database.models import GithubModRecord, GithubTimeline, SystemInfo, db
from backend.i18n.messages import localized_key, localized_params, tr
from backend.managers.mgr_download import DownloadManager, DownloadTask
from backend.managers.mgr_network import build_retry_session, merge_headers
from backend.settings import GIT_PROVIDER_CATALOG_DIR, HOME_DIR, settings
from backend.utils.event_bus import EventBus
from backend.utils.bundle_io import replace_dir_atomically
from backend.utils.logger import logger
from backend.utils.tools import current_ms, normalize_package_id, normalize_package_ids


@dataclass(frozen=True)
class GitRepoIdentity:
    """统一描述一个公开 Git 仓库，避免后续逻辑继续按固定域名猜测。"""
    provider: str
    host: str
    owner: str
    repo: str
    path: str
    url: str


GITHUB_API_BASE = "https://api.github.com/repos"
GITHUB_WEB_BASE = "https://github.com"
GITHUB_ACCEPT_HEADER = "application/vnd.github+json"
GITHUB_API_CACHE_TTL_SECONDS = 180
GITHUB_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 RimCrow/1.0"
)

GIT_PROVIDER_GITHUB = "github"
GIT_PROVIDER_GITLAB = "gitlab"
GITLAB_SUPPORTED_HOSTS = {"gitlab.com", "gitgud.io"}
GITLAB_API_CACHE_TTL_SECONDS = 180
RJW_PROVIDER_CATALOG_URL = "https://gitgud.io/api/v4/projects/AblativeAbsolute%2Flibidinous_loader_providers/packages/generic/provider_nopin/latest/providers.json"
GITHUB_OWNER_CATALOG_MAX_REPOS = 300
BUILTIN_GITHUB_OWNER_SOURCES = [
    {
        "id": "mlie",
        "label": "Mlie",
        "type": "github_owner",
        "owner": "emipa606",
        "catalog_kind": "discovery",
        "match": {
            "description": [r"Repository for the Rimworld mod", r"https?://steamcommunity\.com/"],
            "homepage": [r"https?://steamcommunity\.com/"],
            "name": [],
            "topics": [],
            "about_xml": True,
        },
    },
]

GITHUB_ARTIFACT_RELEASE_ASSET = "release_asset"
GITHUB_ARTIFACT_SOURCE_ARCHIVE = "source_archive"

GITHUB_INSTALL_DOWNLOAD_ONLY = "download_only"
GITHUB_INSTALL_EXTRACT = "extract"
GITHUB_INSTALL_EXTRACT_THEN_MOVE = "extract_then_move"
GITHUB_INSTALL_RUN_INSTALLER = "run_installer"

GITHUB_SOURCE_BRANCH = "branch"
GITHUB_SOURCE_TAG = "tag"
GITHUB_SOURCE_COMMIT = "commit"

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
    installed_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class GithubInstallRequest:
    """GitHub 安装总请求：来源、安装计划、提示文案和后置回调都在这里声明。"""
    repo_url: str = ""
    provider: str = GIT_PROVIDER_GITHUB
    host: str = "github.com"
    project_path: str = ""
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
    tracking: dict[str, Any] = field(default_factory=dict)


def _clean_request_text(value: Any) -> Any:
    return value if localized_key(value) else str(value or "").strip()


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
    provider: str = GIT_PROVIDER_GITHUB
    host: str = "github.com"
    project_path: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


class GithubApiError(RuntimeError):
    """GitHub 远端访问失败。"""


class GithubRateLimitError(GithubApiError):
    """GitHub API 限流。"""


class GitSelectionRequired(ValueError):
    def __init__(self, message: str, kind: str, candidates: list[str]):
        super().__init__(message)
        self.kind, self.candidates = kind, candidates


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
    _install_locks: dict[str, threading.Lock] = {}
    _install_lock_guard = threading.Lock()

    def __init__(self):
        if GithubManager._cache_lock is None:
            import threading

            GithubManager._cache_lock = threading.Lock()

    def parse_git_repo_url(self, url: str) -> GitRepoIdentity | None:
        """解析当前支持的 Git 仓库地址。

        第一版只支持公开 GitHub、GitLab.com 和 GitGud；GitLab 支持多级 namespace。
        """
        raw_url = str(url or "").strip()
        if not raw_url:
            return None
        try:
            parsed = urlparse(raw_url if re.match(r"^[a-z]+://", raw_url, re.I) else f"https://{raw_url}")
            port = parsed.port
        except Exception:
            return None

        if parsed.scheme.lower() not in {"http", "https"} or parsed.username or parsed.password or port not in (None, 80, 443):
            return None
        host = parsed.hostname.lower() if parsed.hostname else ""
        path = parsed.path.strip("/")
        parts = [segment for segment in path.split("/") if segment]
        project_parts = parts[:2] if host == "github.com" else parts[:parts.index("-")] if "-" in parts else parts
        if len(project_parts) < 2:
            return None
        if project_parts[-1].endswith(".git"):
            project_parts[-1] = project_parts[-1][:-4]
        if any(not re.fullmatch(r"[\w.-]+", segment) or segment in {".", ".."} for segment in project_parts):
            return None
        if host == "github.com" and len(parts) >= 2:
            owner, repo = project_parts
            return GitRepoIdentity(
                provider=GIT_PROVIDER_GITHUB,
                host=host,
                owner=owner,
                repo=repo,
                path=f"{owner}/{repo}",
                url=f"https://github.com/{owner}/{repo}".lower(),
            )
        if host in GITLAB_SUPPORTED_HOSTS and len(parts) >= 2:
            if len(project_parts) < 2:
                return None
            repo = project_parts[-1]
            owner = "/".join(project_parts[:-1])
            full_path = "/".join(project_parts)
            return GitRepoIdentity(
                provider=GIT_PROVIDER_GITLAB,
                host=host,
                owner=owner,
                repo=repo,
                path=full_path,
                url=f"https://{host}/{full_path}",
            )
        return None

    def fetch_repo_branches(self, url: str, *, ref_type: str = GITHUB_SOURCE_BRANCH) -> list[str]:
        """显式探测远端分支，完整读取分页；失败时不返回不完整列表。"""
        identity = self.parse_git_repo_url(url)
        if not identity:
            raise ValueError(tr("api.github.invalid_url", "无效的 Git 仓库链接"))
        resource = "tags" if ref_type == GITHUB_SOURCE_TAG else "branches"
        if identity.provider == GIT_PROVIDER_GITLAB:
            endpoint = f"https://{identity.host}/api/v4/projects/{quote(identity.path, safe='')}/repository/{resource}"
        else:
            endpoint = f"{GITHUB_API_BASE}/{identity.path}/{resource}"
        branches: list[str] = []
        seen: set[str] = set()
        page = 1
        with build_retry_session() as session:
            while True:
                response = session.get(endpoint, params={"per_page": 100, "page": page}, headers=self._build_git_headers({"Accept": "application/json"}), timeout=(5, 20))
                self._raise_for_git_status(response, f"{identity.host}/{identity.path}/branches")
                payload = response.json()
                if not isinstance(payload, list) or any(not isinstance(item, dict) or not item.get("name") for item in payload):
                    raise GithubApiError("Git 分支列表响应格式不正确")
                names = [str(item["name"]) for item in payload]
                new_names = [name for name in names if name not in seen]
                if names and not new_names:
                    raise GithubApiError("Git 分支分页返回重复数据")
                branches.extend(new_names)
                seen.update(names)
                if len(payload) < 100:
                    return branches
                page += 1
                if page > 30:
                    raise GithubApiError("分支数量超出探测上限，请直接填写分支名称")

    def resolve_repo_location(self, url: str, ref: str = "", ref_type: str = GITHUB_SOURCE_BRANCH) -> tuple[GitRepoIdentity, str, str, str]:
        """目录链接只在引用边界明确时拆分；分支与标签重名时要求显式选择。"""
        identity = self.parse_git_repo_url(url)
        if not identity:
            raise ValueError("无效的 Git 仓库链接")
        raw = urlparse(url if "://" in url else f"https://{url}").path.strip("/").split("/")
        suffix = "/".join(raw[len(identity.path.split("/")):])
        marker = "-/tree/" if identity.provider == GIT_PROVIDER_GITLAB else "tree/"
        if not suffix:
            return identity, ref, ref_type, ""
        if not suffix.startswith(marker):
            raise ValueError("请使用仓库首页或目录链接")
        tail = unquote(suffix[len(marker):]).strip("/")
        if ref:
            subpath = tail[len(ref) + 1:] if tail.startswith(f"{ref}/") else ""
            return identity, ref, ref_type, subpath
        matches = []
        for kind in (GITHUB_SOURCE_BRANCH, GITHUB_SOURCE_TAG):
            names = self.fetch_repo_branches(identity.url, ref_type=kind)
            for name in names:
                if tail == name or tail.startswith(f"{name}/"):
                    matches.append((name, kind, tail[len(name):].lstrip("/")))
        if not matches and re.fullmatch(r"[0-9a-fA-F]{40}(?:/.*)?", tail):
            ref, _, subpath = tail.partition("/")
            return identity, ref, GITHUB_SOURCE_COMMIT, subpath
        if len(matches) != 1:
            raise ValueError("链接中的分支、标签或目录存在歧义，请显式填写引用名称与类型")
        return identity, *matches[0]

    def fetch_ref_commit(self, identity: GitRepoIdentity, ref: str, ref_type: str = GITHUB_SOURCE_BRANCH, *, force_refresh: bool = False) -> dict[str, Any] | None:
        """先验证精确引用类型，再解析提交；不能把同名标签当成分支。"""
        if ref_type not in {GITHUB_SOURCE_BRANCH, GITHUB_SOURCE_TAG, GITHUB_SOURCE_COMMIT}:
            raise ValueError("无效的 Git 引用类型")
        if not ref:
            return None
        if ref_type == GITHUB_SOURCE_COMMIT:
            if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
                raise ValueError("提交引用必须是完整的 40 位 SHA")
        else:
            resource = "tags" if ref_type == GITHUB_SOURCE_TAG else "branches"
            key = ("ref", identity.host, identity.path, ref_type, ref)
            cached = self._cache_miss if force_refresh else self._get_cached_payload(key)
            if cached is self._cache_miss:
                endpoint = (f"https://{identity.host}/api/v4/projects/{quote(identity.path, safe='')}/repository/{resource}/{quote(ref, safe='')}"
                            if identity.provider == GIT_PROVIDER_GITLAB else
                            f"{GITHUB_API_BASE}/{identity.path}/git/ref/tags/{quote(ref, safe='')}" if ref_type == GITHUB_SOURCE_TAG else
                            f"{GITHUB_API_BASE}/{identity.path}/branches/{quote(ref, safe='')}")
                with build_retry_session() as session:
                    response = session.get(endpoint, headers=self._build_git_headers({"Accept": GITHUB_ACCEPT_HEADER}), timeout=(5, 20))
                    if response.status_code == 404:
                        return None
                    self._raise_for_git_status(response, identity.url)
                    cached = response.json()
                self._store_cached_payload(key, cached)
            if identity.provider == GIT_PROVIDER_GITHUB and ref_type == GITHUB_SOURCE_TAG:
                obj = cached.get("object") or {}
                with build_retry_session() as session:
                    for _ in range(8):
                        if obj.get("type") == "commit": break
                        if obj.get("type") != "tag" or not re.fullmatch(r"[0-9a-fA-F]{40}", str(obj.get("sha") or "")):
                            raise GithubApiError("无效的标签引用")
                        response = session.get(f"{GITHUB_API_BASE}/{identity.path}/git/tags/{obj['sha']}", headers=self._build_git_headers({"Accept": GITHUB_ACCEPT_HEADER}), timeout=(5, 20))
                        self._raise_for_git_status(response, identity.url)
                        obj = response.json().get("object") or {}
                    if obj.get("type") != "commit": raise GithubApiError("标签引用层数超出解析上限")
                ref = str(obj.get("sha") or "")
            else:
                ref = str((cached.get("commit") or {}).get("sha") or (cached.get("commit") or {}).get("id") or "")
            if not re.fullmatch(r"[0-9a-fA-F]{40}", ref):
                raise GithubApiError("远端未返回完整的引用提交 SHA")
        result = (self.fetch_gitlab_commit(identity, ref=ref, force_refresh=force_refresh, missing_ok=True)
                if identity.provider == GIT_PROVIDER_GITLAB else
                self.fetch_commit(identity.owner, identity.repo, ref=ref, force_refresh=force_refresh, missing_ok=True))
        if result and not re.fullmatch(r"[0-9a-fA-F]{40}", str(result.get("sha") or result.get("id") or "")):
            raise GithubApiError("远端提交信息缺少完整 SHA")
        return result

    def detect_repo_provider(self, url: str) -> tuple[str, str]:
        """返回订阅记录可落库的 provider/host，解析失败时保持旧 GitHub 默认。"""
        identity = self.parse_git_repo_url(url)
        if identity:
            return identity.provider, identity.host
        return GIT_PROVIDER_GITHUB, "github.com"

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
        if not normalized_path: return None

        cache_key = ("path_commit", owner.lower(), repo.lower(), normalized_ref or "latest", normalized_path)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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
        if not normalized_path: return None

        cache_key = ("file_meta", owner.lower(), repo.lower(), normalized_ref or "latest", normalized_path)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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

    def fetch_repo(self, owner: str, repo: str, *, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False, force_refresh: bool = False) -> dict[str, Any] | None:
        """读取仓库基础信息。

        这里单独保留仓库查询，是因为默认分支等信息既会用于 UI 展示，也会用于源码包解析。
        """
        cache_key = ("repo", owner.lower(), repo.lower())
        cached = self._cache_miss if force_refresh else self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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

    def fetch_release(self, owner: str, repo: str, *, tag: str = "", timeout: tuple[int, int] = (5, 20), missing_ok: bool = False, force_refresh: bool = False) -> dict[str, Any] | None:
        """读取 Release 元数据。

        `tag` 为空时走 latest；不为空时按指定 tag 查。
        `missing_ok` 允许调用方把 404 当成“没有 Release”而不是异常。
        """
        endpoint = "releases/latest" if not tag else f"releases/tags/{quote(tag, safe='')}"
        cache_key = ("release", owner.lower(), repo.lower(), tag or "latest")
        cached = self._cache_miss if force_refresh else self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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

    def fetch_commit(self, owner: str, repo: str, *, ref: str = "", timeout: tuple[int, int] = (5, 20), missing_ok: bool = False, force_refresh: bool = False) -> dict[str, Any] | None:
        """读取指定分支或标签当前指向的提交信息。

        这里专门拉 commit，是为了给源码包模式生成稳定的“已部署版本”标识，
        避免继续把 `main`/`master` 这种分支名误当作具体版本。
        """
        normalized_ref = str(ref or "").strip()
        endpoint = f"commits/{quote(normalized_ref, safe='')}" if normalized_ref else "commits"
        cache_key = ("commit", owner.lower(), repo.lower(), normalized_ref or "latest")
        cached = self._cache_miss if force_refresh else self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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

    def fetch_repo_page(self, owner: str, repo: str, *, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False) -> str | None:
        """读取仓库网页 HTML。

        这条链路不走 GitHub API 配额，适合在 rate limit 时退化获取基础元数据。
        """
        cache_key = ("repo_page", owner.lower(), repo.lower())
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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
        if cached is not self._cache_miss: return cached

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
        if not resolved_tag: return None

        cache_key = ("release_assets_web", owner.lower(), repo.lower(), resolved_tag)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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
        if not normalized_ref: return None

        cache_key = ("commit_web", owner.lower(), repo.lower(), normalized_ref)
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

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

    def fetch_gitlab_project(self, identity: GitRepoIdentity, *, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False, force_refresh: bool = False) -> dict[str, Any] | None:
        """读取 GitLab/GitGud 项目基础信息。"""
        project_id = quote(identity.path, safe="")
        cache_key = ("gitlab_project", identity.host, identity.path.lower())
        cached = self._cache_miss if force_refresh else self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

        with build_retry_session() as session:
            response = session.get(
                f"https://{identity.host}/api/v4/projects/{project_id}",
                headers=self._build_git_headers({"Accept": "application/json"}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            self._raise_for_git_status(response, f"{identity.host}/{identity.path}")
            payload = response.json()
            self._store_cached_payload(cache_key, payload, ttl_seconds=GITLAB_API_CACHE_TTL_SECONDS)
            return payload

    def fetch_gitlab_release(self, identity: GitRepoIdentity, *, tag: str = "", timeout: tuple[int, int] = (5, 20), missing_ok: bool = False, force_refresh: bool = False) -> dict[str, Any] | None:
        """读取 GitLab/GitGud Release；tag 为空时取 released_at 最新的一条。"""
        project_id = quote(identity.path, safe="")
        normalized_tag = str(tag or "").strip()
        cache_key = ("gitlab_release", identity.host, identity.path.lower(), normalized_tag or "latest")
        cached = self._cache_miss if force_refresh else self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

        endpoint = f"releases/{quote(normalized_tag, safe='')}" if normalized_tag else "releases"
        params = None if normalized_tag else {"per_page": 1, "order_by": "released_at", "sort": "desc"}
        with build_retry_session() as session:
            response = session.get(
                f"https://{identity.host}/api/v4/projects/{project_id}/{endpoint}",
                params=params,
                headers=self._build_git_headers({"Accept": "application/json"}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            self._raise_for_git_status(response, f"{identity.host}/{identity.path}/{endpoint}")
            payload = response.json()
            if isinstance(payload, list):
                payload = payload[0] if payload else None
            self._store_cached_payload(cache_key, payload, ttl_seconds=GITLAB_API_CACHE_TTL_SECONDS)
            return payload

    def fetch_gitlab_commit(self, identity: GitRepoIdentity, *, ref: str, timeout: tuple[int, int] = (5, 20), missing_ok: bool = False, force_refresh: bool = False) -> dict[str, Any] | None:
        """读取 GitLab/GitGud 分支或标签当前提交，用于 Source 模式版本判断。"""
        normalized_ref = str(ref or "").strip()
        if not normalized_ref:
            return None
        project_id = quote(identity.path, safe="")
        ref_id = quote(normalized_ref, safe="")
        cache_key = ("gitlab_commit", identity.host, identity.path.lower(), normalized_ref)
        cached = self._cache_miss if force_refresh else self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

        with build_retry_session() as session:
            response = session.get(
                f"https://{identity.host}/api/v4/projects/{project_id}/repository/commits/{ref_id}",
                headers=self._build_git_headers({"Accept": "application/json"}),
                timeout=timeout,
            )
            if missing_ok and response.status_code == 404:
                self._store_cached_payload(cache_key, None, ttl_seconds=60)
                return None
            self._raise_for_git_status(response, f"{identity.host}/{identity.path}/commits/{normalized_ref}")
            payload = response.json()
            self._store_cached_payload(cache_key, payload, ttl_seconds=GITLAB_API_CACHE_TTL_SECONDS)
            return payload

    def fetch_repo_readme(self, url: str, *, ref: str = "", timeout: tuple[int, int] = (8, 25)) -> dict[str, Any]:
        """读取公开仓库 README，供推荐列表点击详情懒加载。"""
        identity = self.parse_git_repo_url(url)
        if not identity:
            raise ValueError("无效的 Git 仓库链接")
        normalized_ref = str(ref or "").strip()
        if identity.provider == GIT_PROVIDER_GITLAB:
            return self._fetch_gitlab_readme(identity, ref=normalized_ref, timeout=timeout)
        return self._fetch_github_readme(identity, ref=normalized_ref, timeout=timeout)

    def _fetch_github_readme(self, identity: GitRepoIdentity, *, ref: str, timeout: tuple[int, int]) -> dict[str, Any]:
        cache_key = ("github_readme", identity.owner.lower(), identity.repo.lower(), ref or "_default")
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

        repo_info = self.fetch_repo(identity.owner, identity.repo, missing_ok=True)
        target_ref = ref or str((repo_info or {}).get("default_branch") or "").strip()
        if not target_ref: raise GithubApiError("无法确定仓库默认分支")
        with build_retry_session() as session:
            for filename in ("README.md", "Readme.md", "readme.md"):
                response = session.get(
                    f"{GITHUB_API_BASE}/{identity.owner}/{identity.repo}/contents/{filename}",
                    params={"ref": target_ref},
                    headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                    timeout=timeout,
                )
                if response.status_code == 404:
                    continue
                self._raise_for_github_status(response, f"{identity.owner}/{identity.repo}/{filename}")
                payload = response.json()
                content = base64.b64decode(str(payload.get("content") or "")).decode("utf-8", errors="replace")
                result = {"content": content, "path": filename, "ref": target_ref, "url": str(payload.get("html_url") or "")}
                self._store_cached_payload(cache_key, result, ttl_seconds=GITHUB_API_CACHE_TTL_SECONDS)
                return result
        logger.warning("未找到 Git 仓库 README: %s ref=%s", identity.url, target_ref)
        result = {"content": "", "path": "", "ref": target_ref, "url": "", "found": False}
        self._store_cached_payload(cache_key, result, ttl_seconds=GITHUB_API_CACHE_TTL_SECONDS)
        return result

    def _fetch_gitlab_readme(self, identity: GitRepoIdentity, *, ref: str, timeout: tuple[int, int]) -> dict[str, Any]:
        cache_key = ("gitlab_readme", identity.host, identity.path.lower(), ref or "_default")
        cached = self._get_cached_payload(cache_key)
        if cached is not self._cache_miss: return cached

        project = self.fetch_gitlab_project(identity, missing_ok=True)
        target_ref = ref or str((project or {}).get("default_branch") or "").strip()
        if not target_ref: raise GithubApiError("无法确定仓库默认分支")
        project_id = quote(identity.path, safe="")
        with build_retry_session() as session:
            for filename in ("README.md", "Readme.md", "readme.md"):
                response = session.get(
                    f"https://{identity.host}/api/v4/projects/{project_id}/repository/files/{quote(filename, safe='')}/raw",
                    params={"ref": target_ref},
                    headers=self._build_git_headers({"Accept": "text/markdown,text/plain"}),
                    timeout=timeout,
                )
                if response.status_code == 404:
                    continue
                self._raise_for_git_status(response, f"{identity.host}/{identity.path}/{filename}")
                result = {
                    "content": response.text,
                    "path": filename,
                    "ref": target_ref,
                    "url": f"https://{identity.host}/{identity.path}/-/blob/{quote(target_ref, safe='')}/{filename}",
                }
                self._store_cached_payload(cache_key, result, ttl_seconds=GITLAB_API_CACHE_TTL_SECONDS)
                return result
        logger.warning("未找到 Git 仓库 README: %s ref=%s", identity.url, target_ref)
        result = {"content": "", "path": "", "ref": target_ref, "url": "", "found": False}
        self._store_cached_payload(cache_key, result, ttl_seconds=GITLAB_API_CACHE_TTL_SECONDS)
        return result

    def fetch_repo_info(self, url: str, *, source_branch: str = "", source_ref_type: str = GITHUB_SOURCE_BRANCH, force_refresh: bool = False) -> dict[str, Any]:
        """获取仓库基础信息、默认分支、最新 Release 和源码分支版本信息。

        优先使用 GitHub API；如果命中限流或 API 不可用，再退化到网页/直链/本地缓存。
        """
        try:
            identity, source_branch, source_ref_type, subpath = self.resolve_repo_location(url, source_branch, source_ref_type)
        except ValueError as exc:
            return {"error": str(exc)}
        url = identity.url
        if identity.provider == GIT_PROVIDER_GITLAB:
            payload = self._fetch_repo_info_via_api(identity.owner, identity.repo, source_branch=source_branch, identity=identity, source_ref_type=source_ref_type, force_refresh=force_refresh)
            payload.update(source_ref_type=source_ref_type, source_subpath=subpath)
            return payload

        owner, repo = identity.owner, identity.repo
        normalized_source_branch = str(source_branch or "").strip()
        cache_key = ("repo_info", owner.lower(), repo.lower(), source_ref_type, normalized_source_branch or "_auto")
        cached = self._cache_miss if force_refresh else self._get_cached_payload(cache_key)
        if cached is not self._cache_miss:
            cached.update(source_ref_type=source_ref_type, source_subpath=subpath)
            return cached

        primary_error: Exception | None = None
        try:
            payload = self._fetch_repo_info_via_api(owner, repo, source_branch=normalized_source_branch, identity=identity, source_ref_type=source_ref_type, force_refresh=force_refresh)
            payload.update(source_ref_type=source_ref_type, source_subpath=subpath)
            self._store_cached_payload(cache_key, payload)
            return payload
        except (GithubApiError, requests.RequestException) as exc:
            primary_error = exc
            logger.debug("GitHub 仓库信息 API 预取失败，将回退到网页或缓存：repo=%s/%s error=%s", owner, repo, exc)

        web_payload = self._fetch_repo_info_via_web(owner, repo, source_branch=normalized_source_branch)
        if web_payload:
            web_payload.update(source_status="stale", source_ref_type=source_ref_type, source_subpath=subpath)
            if primary_error:
                web_payload["fetch_warning"] = str(primary_error)
            self._store_cached_payload(cache_key, web_payload, ttl_seconds=120)
            return web_payload

        record_payload = self._fetch_repo_info_from_record_cache(url, owner, repo, source_branch=normalized_source_branch)
        if record_payload:
            record_payload.update(source_ref_type=source_ref_type, source_subpath=subpath)
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
            minimal_payload.update(source_status="error", release_status="error")
            self._store_cached_payload(cache_key, minimal_payload, ttl_seconds=60)
            return minimal_payload

        if primary_error:
            raise primary_error
        return {"error": "找不到该仓库"}

    def fetch_repo_browser_info(self, url: str, *, source_branch: str = "", source_ref_type: str = GITHUB_SOURCE_BRANCH) -> dict[str, Any]:
        """一次读取仓库浏览页需要的仓库信息与 README；README 故障不阻断其它信息。"""
        info = self.fetch_repo_info(url, source_branch=source_branch, source_ref_type=source_ref_type)
        if "error" in info:
            return {"error": info["error"]}
        ref = str(info.get("latest_source_branch") or info.get("default_branch") or source_branch or "").strip()
        try:
            readme = self.fetch_repo_readme(str(info.get("repo_url") or url), ref=ref)
            return {"info": info, "readme": readme, "readme_error": ""}
        except (GithubApiError, requests.RequestException, ValueError) as exc:
            logger.warning("读取 Git 仓库 README 失败，继续展示仓库信息: repo=%s ref=%s error=%s", info.get("repo_url") or url, ref, exc)
            return {"info": info, "readme": {}, "readme_error": str(exc)}

    def fetch_provider_catalog(self, catalog_url: str = "", *, force_refresh: bool = False) -> dict[str, Any]:
        """读取全部推荐清单源并合并为前端列表。

        配置仍保持简单文本：provider JSON 每行一个，GitHub owner 每行一个。每个源独立缓存，
        避免 RJW 清单和 Mlie 动态清单互相污染，也方便以后继续添加清单源。
        """
        sources = self._provider_catalog_sources(catalog_url)
        cache_key = ("provider_catalog", self._provider_catalog_sources_key(sources))
        if not force_refresh:
            cached = self._get_cached_payload(cache_key)
            if cached is not self._cache_miss: return cached

        items: list[dict[str, Any]] = []
        source_results: list[dict[str, Any]] = []
        warnings: list[str] = []
        for source in sources:
            try:
                source_catalog = self._fetch_provider_catalog_source(source, force_refresh=force_refresh)
                items.extend(source_catalog.get("items") or [])
                source_results.append(source_catalog.get("source") or source)
                if source_catalog.get("warning"):
                    warnings.append(str(source_catalog["warning"]))
            except Exception as exc:
                warnings.append(f"{source.get('label') or source.get('id')}: {exc}")
                logger.warning("Git 推荐清单源读取失败: %s", exc, exc_info=True)

        merged_items = self._merge_provider_catalog_items(items)
        catalog = {
            "source_url": "",
            "sources": source_results,
            "total": len(merged_items),
            "items": merged_items,
            "fetched_at": current_ms(),
            "is_stale": any(bool(source.get("is_stale")) for source in source_results),
            "warning": "；".join(warnings),
        }
        self._store_cached_payload(cache_key, catalog, ttl_seconds=GITLAB_API_CACHE_TTL_SECONDS)
        return catalog

    def check_provider_catalog_updates(self, catalog_url: str = "") -> dict[str, Any]:
        """检查 Git 推荐清单源是否和本地缓存一致，不刷新缓存。

        provider_json 没有本地文件路径，真正的“本地版本”是已缓存的清单内容；
        因此这里比较缓存清单和远端清单的内容签名，而不是拿请求头或时间戳猜测。
        """
        sources = self._provider_catalog_sources(catalog_url)
        items: list[dict[str, Any]] = []
        for source in sources:
            source_id = str(source.get("id") or "").strip()
            cached = self._load_provider_catalog_source_cache(source) if source_id else None
            local_signature = self._provider_catalog_source_signature(cached)
            local_count = len(cached.get("items") or []) if isinstance(cached, dict) else 0
            try:
                remote_catalog = self._fetch_provider_catalog_source_remote(source)
                remote_signature = self._provider_catalog_source_signature(remote_catalog)
                remote_count = len(remote_catalog.get("items") or []) if isinstance(remote_catalog, dict) else 0
                exists = bool(cached)
                items.append({
                    "source_id": source_id,
                    "label": source.get("label") or source_id,
                    "type": source.get("type") or "",
                    "exists": exists,
                    "remote_available": True,
                    "needs_update": (not exists) or (local_signature != remote_signature),
                    "local_signature": local_signature,
                    "remote_signature": remote_signature,
                    "local_count": local_count,
                    "remote_count": remote_count,
                })
            except Exception as exc:
                logger.warning("Git 推荐清单检查失败: %s", source.get("label") or source_id, exc_info=True)
                items.append({
                    "source_id": source_id,
                    "label": source.get("label") or source_id,
                    "type": source.get("type") or "",
                    "exists": bool(cached),
                    "remote_available": False,
                    "needs_update": False,
                    "local_signature": local_signature,
                    "remote_signature": "",
                    "local_count": local_count,
                    "remote_count": 0,
                    "message": f"获取远端清单失败: {exc}",
                })

        available_items = [item for item in items if item.get("remote_available")]
        return {
            "sources": items,
            "source_count": len(items),
            "available_count": len(available_items),
            "local_signature": self._provider_catalog_sources_signature(items, "local_signature"),
            "remote_signature": self._provider_catalog_sources_signature(available_items, "remote_signature"),
            "local_count": sum(int(item.get("local_count") or 0) for item in items),
            "remote_count": sum(int(item.get("remote_count") or 0) for item in available_items),
            "needs_update": any(bool(item.get("needs_update")) for item in items),
            "remote_available": len(available_items) == len(items) if items else False,
        }

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
        Path(normalized.install.download_dir).mkdir(parents=True, exist_ok=True)
        is_temporary = normalized.install.action != GITHUB_INSTALL_DOWNLOAD_ONLY and normalized.install.cleanup_archive
        download_dir = tempfile.mkdtemp(prefix="git-task-", dir=normalized.install.download_dir) if is_temporary else normalized.install.download_dir
        try:
            return download_mgr.add_task(
                url=resolved.download_url,
                dest_dir=download_dir,
                filename=resolved.filename,
                expected_hash=normalized.expected_hash or None,
                hash_algorithm=normalized.hash_algorithm,
                on_complete=on_download_complete,
                on_error=on_download_error,
                metadata={"complete_after_callback": True, **({"temporary_dir": download_dir} if is_temporary else {})},
            )
        except Exception:
            if is_temporary: shutil.rmtree(download_dir, ignore_errors=True)
            raise

    def install_repo_mod(self, download_mgr: DownloadManager, repo_url: str, install_type: str = "source", target_version: str = "", *, install_options: dict[str, Any]) -> str:
        """Git 仓库模组安装的便捷封装。

        这是一个“薄封装”：只负责把旧的 source/release 语义翻译成通用安装请求，
        真正的下载与安装流程仍走 `install_from_github()`。
        """
        identity = self.parse_git_repo_url(repo_url)
        if not identity:
            raise ValueError("无效的 Git 仓库链接")
        owner, repo = identity.owner, identity.repo
        repo_url = identity.url
        record = GithubModRecord.get_or_none(repo_url=repo_url)
        options = dict(install_options)
        ref_type = str(options.get("ref_type") or "").strip()
        if ref_type not in {GITHUB_SOURCE_BRANCH, GITHUB_SOURCE_TAG, GITHUB_SOURCE_COMMIT}:
            raise ValueError("无效的 Git 引用类型")
        local_folder = str(record.local_folder or "") if record else ""
        if local_folder and GithubModRecord.select().where((GithubModRecord.local_folder == local_folder) & (GithubModRecord.repo_url != repo_url)).exists():
            raise ValueError("多个仓库绑定了同一个本地目录，请先重新绑定后再部署")
        if local_folder and (Path(local_folder).name != local_folder or Path(local_folder).is_absolute()):
            raise ValueError("本地绑定目录不在管理器模组目录内，请先重新绑定")
        final_name = local_folder or f"_GH_{repo}_{hashlib.sha256(repo_url.encode()).hexdigest()[:12]}"

        is_release_mode = install_type == "release"
        source_ref = str(target_version or "").strip()
        self_mods_path = str(settings.config.self_mods_path or "").strip()
        if not self_mods_path:
            raise ValueError("未配置管理器 Mod 目录，无法部署 Git 仓库模组")
        if not source_ref and not is_release_mode:
            # Source 模式默认跟随仓库默认分支，而不是硬编码 main/master。
            if identity.provider == GIT_PROVIDER_GITLAB:
                project = self.fetch_gitlab_project(identity, missing_ok=True)
                source_ref = str((project or {}).get("default_branch") or "").strip()
            else:
                source_ref = self._resolve_default_branch(owner, repo, repo_url=repo_url)

        artifact_request = self._build_repo_artifact_request(
            owner,
            repo,
            repo_url=repo_url,
            identity=identity,
            is_release_mode=is_release_mode,
            target_version=source_ref,
        )
        artifact_request.source_ref_type = ref_type
        artifact_request.asset_name = str(options.get("asset_name") or "")
        request = GithubInstallRequest(
            repo_url=repo_url,
            provider=identity.provider,
            host=identity.host,
            project_path=identity.path,
            owner=owner,
            repo=repo,
            artifact=artifact_request,
            install=GithubInstallPlan(
                action=GITHUB_INSTALL_EXTRACT_THEN_MOVE,
                download_dir=str(HOME_DIR / "Downloads"),
                move_target_dir=self_mods_path,
                final_name=final_name,
                source_subpath=str(options.get("source_subpath") or ""),
                source_resolver=GITHUB_RESOLVER_MOD_ROOT,
                overwrite_existing=True,
                cleanup_archive=True,
            ),
            timeline_repo_url=repo_url,
            download_start_message=tr("tasks.github.download_start", "开始获取压缩包"),
            install_start_message=tr("tasks.github.install_start", "压缩包获取成功，正在解压..."),
            success_toast=tr("toast.github.deploy_done", "{repo} 部署完成", repo=repo),
            failure_toast=tr("toast.github.deploy_failed", "{repo} 部署失败", repo=repo),
            post_install=lambda result: self._update_mod_record(repo_url, result.version, final_name, installed_info=result.installed_info, tracking=request.tracking),
            tracking={"install_type": install_type, "target_branch": str(record.target_branch or ""), "install_options": options} if record else {},
        )
        return self.install_from_github(download_mgr, request)

    def install_catalog_zip_mod(self, download_mgr: DownloadManager, catalog_url: str) -> str:
        """部署清单里的 zip 直链项。

        zip 清单项没有仓库 API 可查，部署参数完全来自订阅时保存的清单元数据。
        """
        record = GithubModRecord.get_or_none(repo_url=catalog_url)
        if not record:
            raise ValueError("未找到对应的清单项订阅")
        item = self._refresh_catalog_zip_signature(record.online_info_cache or {})
        download_url = str(item.get("raw_url") or item.get("url") or catalog_url).strip()
        if not download_url:
            raise ValueError("清单项缺少下载地址")
        self_mods_path = str(settings.config.self_mods_path or "").strip()
        if not self_mods_path:
            raise ValueError("未配置管理器 Mod 目录，无法部署清单项")

        name = str(item.get("name") or record.repo_name or "catalog_mod").strip()
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" ._") or "catalog_mod"
        filename = Path(urlparse(download_url).path).name or f"{name}.zip"
        version = str(item.get("catalog_signature") or current_ms())
        request = GithubInstallRequest(
            repo_url=catalog_url,
            provider=str(item.get("provider") or "catalog_zip"),
            host=str(item.get("host") or urlparse(download_url).hostname or ""),
            owner=str(item.get("source_id") or record.owner or ""),
            repo=safe_name,
            install=GithubInstallPlan(
                action=GITHUB_INSTALL_EXTRACT_THEN_MOVE,
                download_dir=str(HOME_DIR / "Downloads"),
                move_target_dir=self_mods_path,
                final_name=str(record.local_folder or f"_GH_{safe_name}_{hashlib.sha256(catalog_url.encode()).hexdigest()[:12]}"),
                source_resolver=GITHUB_RESOLVER_MOD_ROOT,
                source_subpath=str((record.install_options or {}).get("source_subpath") or item.get("subdir") or "").strip(),
                overwrite_existing=True,
                cleanup_archive=True,
            ),
            timeline_repo_url=catalog_url,
            install_start_message=tr("tasks.github.catalog_install_start", "清单压缩包获取成功，正在解压..."),
            success_toast=tr("toast.github.catalog_deploy_done", "{name} 部署完成", name=name),
            failure_toast=tr("toast.github.catalog_deploy_failed", "{name} 部署失败", name=name),
            post_install=lambda result: self._update_mod_record(catalog_url, version, request.install.final_name, installed_info=result.installed_info, tracking=request.tracking),
            tracking={"install_type": "zip", "target_branch": str(record.target_branch or ""), "install_options": dict(record.install_options or {})},
        )
        resolved = GithubResolvedArtifact(
            repo_url=catalog_url,
            owner=request.owner,
            repo=safe_name,
            kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE,
            version=version,
            download_url=download_url,
            filename=filename,
            provider=request.provider,
            host=request.host,
        )
        self.record_timeline(catalog_url, "download", f"开始获取清单压缩包: {filename}")

        def on_download_complete(task: DownloadTask):
            self._handle_install(task, request, resolved)

        def on_download_error(task: DownloadTask):
            self._handle_download_error(task, request, resolved)

        Path(request.install.download_dir).mkdir(parents=True, exist_ok=True)
        download_dir = tempfile.mkdtemp(prefix="git-task-", dir=request.install.download_dir)
        try:
            return download_mgr.add_task(
                url=download_url,
                dest_dir=download_dir,
                filename=filename,
                on_complete=on_download_complete,
                on_error=on_download_error,
                metadata={"complete_after_callback": True, "temporary_dir": download_dir},
            )
        except Exception:
            shutil.rmtree(download_dir, ignore_errors=True)
            raise

    def resolve_catalog_subscription_info(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """从最新清单中找回已订阅 zip 项，用于刷新更新状态。"""
        cached_info = record.get("online_info_cache") or {}
        repo_url = str(record.get("repo_url") or "").strip()
        catalog = self.fetch_provider_catalog(force_refresh=False)
        for item in catalog.get("items") or []:
            if str(item.get("url") or "").strip() == repo_url or str(item.get("raw_url") or "").strip() == repo_url:
                return self._refresh_catalog_zip_signature(item)
            if cached_info.get("source_id") and cached_info.get("key"):
                if item.get("source_id") == cached_info.get("source_id") and item.get("key") == cached_info.get("key"):
                    return self._refresh_catalog_zip_signature(item)
        return None

    def get_cached_provider_catalog_install_sources_by_package_ids(self, package_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """只从本地 Git 推荐清单缓存按包名读取可用安装来源。"""
        normalized_package_ids = set(normalize_package_ids(package_ids))
        if not normalized_package_ids:
            return {}

        result: dict[str, list[dict[str, Any]]] = {}
        seen_keys: set[str] = set()
        for source in self._provider_catalog_sources():
            cached = self._load_provider_catalog_source_cache(source)
            if not isinstance(cached, dict):
                continue
            for item in cached.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("not_recommended") or item.get("disabled"):
                    continue
                package_id = normalize_package_id(item.get("package_id"))
                if package_id not in normalized_package_ids:
                    continue
                item_type = str(item.get("type") or "git").strip().lower()
                install_type = "zip" if item_type == "zip" else str(item.get("install_type") or "source").strip() or "source"
                url = str(item.get("url") or item.get("raw_url") or item.get("info_url") or "").strip()
                if not url:
                    continue
                key = f"{package_id}|{url.lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                result.setdefault(package_id, []).append({
                    "package_id": package_id,
                    "source_kind": "git",
                    "install_type": install_type,
                    "default_branch": str(item.get("branch") or item.get("default_branch") or "").strip(),
                    "url": url,
                    "name": str(item.get("name") or package_id).strip() or package_id,
                    "supported_versions": list(item.get("game_versions") or []),
                    "source_origin": "git_catalog",
                    "info": item,
                })
        return result

    def _build_repo_artifact_request(self, owner: str, repo: str, *, repo_url: str, identity: GitRepoIdentity | None = None, is_release_mode: bool, target_version: str) -> GithubArtifactRequest:
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
            if identity and identity.provider == GIT_PROVIDER_GITLAB:
                fallback_download_url = self._build_gitlab_archive_url(identity, normalized_version)
            else:
                fallback_download_url = f"https://github.com/{owner}/{repo}/archive/refs/tags/{quote(normalized_version, safe='')}.zip"
            fallback_filename = f"{repo}_{normalized_version.replace('/', '_')}.zip"

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

    def _normalize_install_request(self, request: GithubInstallRequest) -> GithubInstallRequest:
        """把调用方输入标准化。

        目的不是“校验漂亮”，而是保证后续解析阶段只面对一套稳定字段，减少分支判断。
        """
        owner = str(request.owner or "").strip()
        repo = str(request.repo or "").strip()
        repo_url = str(request.repo_url or "").strip()
        identity = self.parse_git_repo_url(repo_url) if repo_url else None

        if identity:
            owner, repo = identity.owner, identity.repo
        if not owner or not repo:
            raise ValueError("缺少有效的 Git 仓库信息")

        provider = identity.provider if identity else str(request.provider or GIT_PROVIDER_GITHUB)
        host = identity.host if identity else str(request.host or "github.com")
        project_path = str(request.project_path or (identity.path if identity else f"{owner}/{repo}")).strip()

        artifact = request.artifact or GithubArtifactRequest()
        install = request.install or GithubInstallPlan()
        download_dir = str(install.download_dir or HOME_DIR / "Downloads")

        return GithubInstallRequest(
            repo_url=identity.url if identity else repo_url or f"https://github.com/{owner}/{repo}",
            provider=provider,
            host=host,
            project_path=project_path,
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
            download_start_message=_clean_request_text(request.download_start_message),
            install_start_message=_clean_request_text(request.install_start_message),
            success_message=_clean_request_text(request.success_message),
            success_toast=_clean_request_text(request.success_toast),
            failure_toast=_clean_request_text(request.failure_toast),
            post_install=request.post_install,
            on_install_error=request.on_install_error,
            tracking=deepcopy(request.tracking),
        )

    def _resolve_artifact(self, request: GithubInstallRequest) -> GithubResolvedArtifact:
        """根据产物类型把请求解析成具体下载对象。"""
        if request.artifact.kind == GITHUB_ARTIFACT_RELEASE_ASSET:
            return self._resolve_release_asset(request)
        if request.artifact.kind == GITHUB_ARTIFACT_SOURCE_ARCHIVE:
            return self._resolve_source_archive(request)
        raise ValueError(f"不支持的 Git 仓库产物类型: {request.artifact.kind}")

    def _resolve_release_asset(self, request: GithubInstallRequest) -> GithubResolvedArtifact:
        """解析 Release 资产。

        先取 Release，再按名称规则选资产。这样调用方只描述筛选条件，不必自己遍历 assets。
        """
        if request.provider == GIT_PROVIDER_GITLAB:
            return self._resolve_gitlab_release_asset(request)

        try:
            release = self.fetch_release(
                request.owner,
                request.repo,
                tag=request.artifact.release_tag,
                missing_ok=True,
                force_refresh=True,
            )
            if release and not request.artifact.release_tag:
                request.artifact.release_tag = str(release.get("tag_name") or "")
            resolved = self._build_release_asset_from_payload(request, release)
            if resolved: return resolved
        except (GithubApiError, requests.RequestException) as exc:
            try:
                web_release = self.fetch_release_assets_web(
                    request.owner,
                    request.repo,
                    tag=request.artifact.release_tag,
                )
                resolved = self._build_release_asset_from_payload(request, web_release)
                if resolved:
                    logger.debug(
                        "已通过 GitHub 网页资源回退解析 release：repo=%s/%s tag=%s error=%s",
                        request.owner,
                        request.repo,
                        request.artifact.release_tag or "latest",
                        exc,
                    )
                    return resolved
            except (GithubApiError, requests.RequestException) as web_exc:
                logger.debug(
                    "GitHub release 网页资源回退失败：repo=%s/%s tag=%s error=%s",
                    request.owner,
                    request.repo,
                    request.artifact.release_tag or "latest",
                    web_exc,
                )
            fallback = self._build_release_fallback(request, exc)
            if fallback: return fallback
            raise
        fallback = self._build_release_fallback(request, ValueError("未找到符合条件的 GitHub Release 资产"))
        if fallback:
            return fallback
        raise ValueError("未找到符合条件的 GitHub Release 资产")

    def _resolve_gitlab_release_asset(self, request: GithubInstallRequest) -> GithubResolvedArtifact:
        """解析 GitLab/GitGud Release 资产，失败时回退到 tag 源码 zip。"""
        identity = self._identity_from_request(request)
        try:
            release = self.fetch_gitlab_release(identity, tag=request.artifact.release_tag, missing_ok=True, force_refresh=True)
        except (GithubApiError, requests.RequestException) as exc:
            fallback = self._build_release_fallback(request, exc)
            if fallback:
                return fallback
            raise
        normalized_release = self._normalize_gitlab_release_payload(release, include_sources=False)
        if normalized_release and not request.artifact.release_tag:
            request.artifact.release_tag = str(normalized_release.get("tag_name") or "")
        resolved = self._build_release_asset_from_payload(request, normalized_release)
        if resolved:
            return resolved

        fallback = self._build_release_fallback(request, ValueError("未找到符合条件的 GitLab Release 资产"))
        if fallback:
            return fallback
        raise ValueError("未找到符合条件的 GitLab Release 资产")

    def _resolve_source_archive(self, request: GithubInstallRequest) -> GithubResolvedArtifact:
        """固定引用对应的完整 SHA，使下载内容与已部署证据一致。"""
        identity = self._identity_from_request(request)
        source_ref_type = request.artifact.source_ref_type or GITHUB_SOURCE_BRANCH
        source_ref = str(request.artifact.source_ref or "").strip()
        if source_ref_type == GITHUB_SOURCE_BRANCH and not source_ref:
            if request.provider == GIT_PROVIDER_GITLAB:
                source_ref = str((self.fetch_gitlab_project(identity) or {}).get("default_branch") or "")
            else:
                source_ref = self._resolve_default_branch(request.owner, request.repo, repo_url=request.repo_url)
        if not source_ref:
            raise ValueError("Git 仓库源码包缺少目标分支或标签")
        commit = self.fetch_ref_commit(identity, source_ref, source_ref_type, force_refresh=True)
        commit_sha = str((commit or {}).get("sha") or (commit or {}).get("id") or "")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
            raise GithubApiError(f"无法解析 Git 引用对应的完整提交: {source_ref}")
        download_url = (self._build_gitlab_archive_url(identity, commit_sha) if request.provider == GIT_PROVIDER_GITLAB else
                        f"https://github.com/{request.owner}/{request.repo}/archive/{commit_sha}.zip")
        return GithubResolvedArtifact(
            repo_url=request.repo_url,
            owner=request.owner,
            repo=request.repo,
            kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE,
            version=self._build_source_version(source_ref, commit_sha),
            download_url=download_url,
            filename=f"{request.repo}_{commit_sha[:12]}_source.zip",
            provider=request.provider,
            host=request.host,
            project_path=request.project_path,
            evidence={"ref": source_ref, "ref_type": source_ref_type, "commit_sha": commit_sha.lower()},
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

        matches = []
        for asset in assets:
            name = str(asset.get("name") or "")
            name_lower = name.lower()
            if request_asset_name and name_lower != request_asset_name_lower:
                continue
            if not request_asset_name and request_prefix and not name_lower.startswith(request_prefix_lower):
                continue
            if request_suffix and not name_lower.endswith(request_suffix_lower):
                continue
            if regex and not regex.search(name):
                continue
            if not str(asset.get("browser_download_url") or "").strip():
                continue
            matches.append(asset)
        if len(matches) > 1:
            raise GitSelectionRequired("发行版包含多个匹配资源，请选择要安装的文件", "asset_name", [str(a["name"]) for a in matches])
        if matches:
            return matches[0]
        if request_asset_name:
            raise ValueError(f"发行版中未找到指定资源: {request_asset_name}")

        # 兼容通用 release 模式：如果没给精确规则，但 Release 下只有一个 zip 资产，就直接用它。
        if not request_asset_name and request_suffix_lower == ".zip":
            zip_assets = [
                asset for asset in assets
                if str(asset.get("name") or "").lower().endswith(".zip")
                and str(asset.get("browser_download_url") or "").strip()
            ]
            if len(zip_assets) == 1: return zip_assets[0]
            if len(zip_assets) > 1:
                raise GitSelectionRequired("发行版包含多个压缩包，请选择要安装的文件", "asset_name", [str(a["name"]) for a in zip_assets])
        return None

    def _build_release_asset_from_payload(self, request: GithubInstallRequest, release: dict[str, Any] | None) -> GithubResolvedArtifact | None:
        if not release: return None

        asset = self._select_release_asset(release.get("assets", []), request.artifact)
        if not asset: return None

        return GithubResolvedArtifact(
            repo_url=request.repo_url,
            owner=request.owner,
            repo=request.repo,
            kind=GITHUB_ARTIFACT_RELEASE_ASSET,
            version=str(release.get("tag_name") or request.artifact.release_tag or "latest"),
            download_url=str(asset.get("browser_download_url") or ""),
            filename=str(asset.get("name") or ""),
            asset_name=str(asset.get("name") or ""),
            provider=request.provider,
            host=request.host,
            project_path=request.project_path,
            evidence={"release_tag": str(release.get("tag_name") or request.artifact.release_tag),
                      "asset_name": str(asset.get("name") or ""), "asset_fingerprint": self._release_asset_fingerprint(asset)},
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
        target = str((Path(request.install.move_target_dir) / request.install.final_name).resolve()) if request.install.move_target_dir else request.install.extract_dir or task.dest_path
        with self._install_lock_guard:
            install_lock = self._install_locks.setdefault(target, threading.Lock())
        while not install_lock.acquire(timeout=0.1):
            self._check_install_cancelled(task)
        try:
            self._check_install_cancelled(task)
            if timeline_repo_url and request.install.action != GITHUB_INSTALL_DOWNLOAD_ONLY:
                self.record_timeline(
                    timeline_repo_url,
                    "extract",
                    request.install_start_message or "压缩包获取成功，正在执行安装计划...",
                )
            result = self._execute_install_plan(task, request, resolved)
            if request.post_install and request.install.action != GITHUB_INSTALL_EXTRACT_THEN_MOVE:
                request.post_install(result)
            try:
                if timeline_repo_url:
                    self.record_timeline(timeline_repo_url, "success", request.success_message or f"部署成功！已安装版本: {resolved.version}")
                if request.success_toast:
                    EventBus.send_toast(request.success_toast, type="success", duration=4000)
                if request.tracking:
                    EventBus.emit("github-deployed", {"repo_url": request.repo_url, "installed_path": result.installed_path})
            except Exception:
                logger.warning("Git 部署已完成，结果通知失败: %s", request.repo_url, exc_info=True)
        except InterruptedError:
            logger.info("Git 部署已取消: %s", request.repo_url)
            raise
        except Exception as exc:
            error_id = getattr(task, "error_id", "") or uuid.uuid4().hex[:10]
            user_message = getattr(task, "user_message", "") or request.failure_toast or tr("errors.git.install_failed", "Git 仓库安装失败。请检查仓库地址、分支和访问权限。")
            logger.error(
                "Git 仓库安装失败：%s",
                request.repo_url,
                exc_info=True,
                extra={
                    "error_type": getattr(task, "error_type", ""),
                    "error_code": getattr(task, "error_code", "") or "GIT.INSTALL_FAILED",
                    "error_id": error_id,
                    "user_message": user_message,
                    "message_key": getattr(task, "message_key", ""),
                    "message_params": dict(getattr(task, "message_params", {}) or {}),
                    "extra_context": {"repo_url": request.repo_url, "owner": request.owner, "repo": request.repo},
                },
            )
            if timeline_repo_url:
                # 安装阶段已经归属并记录了 Git 错误，下载器回调不应再次追加“下载失败”。
                task.metadata["github_install_error_recorded"] = True
                self.record_timeline(timeline_repo_url, "error", f"部署失败: {user_message}")
            if request.failure_toast:
                EventBus.send_toast(
                    {
                        "message": request.failure_toast,
                        "user_message": user_message,
                        "error_type": getattr(task, "error_type", ""),
                        "error_code": getattr(task, "error_code", "") or "GIT.INSTALL_FAILED",
                        "error_id": error_id,
                        "message_key": getattr(task, "message_key", "") or localized_key(request.failure_toast),
                        "message_params": dict(getattr(task, "message_params", {}) or localized_params(request.failure_toast) or {}),
                    },
                    type="error",
                    duration=6000,
                )
            if request.on_install_error:
                request.on_install_error(exc, task, resolved)
            if isinstance(exc, GitSelectionRequired):
                EventBus.emit("github-install-selection", {"repo_url": request.repo_url, "kind": exc.kind, "candidates": exc.candidates})
            raise
        finally:
            install_lock.release()

    def _handle_download_error(self, task: DownloadTask, request: GithubInstallRequest, _resolved: GithubResolvedArtifact) -> None:
        """下载失败时补 GitHub 域内反馈。"""
        timeline_repo_url = request.timeline_repo_url or request.repo_url
        if task.metadata.get("github_install_error_recorded"):
            return
        download_user_message = task.user_message or tr("errors.git.download_failed", "Git 仓库下载失败。请检查仓库地址、分支、网络连接和访问权限。")
        if timeline_repo_url:
            self.record_timeline(timeline_repo_url, "error", f"下载失败: {download_user_message}")

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
            installed_info={**resolved.evidence, "artifact_kind": resolved.kind, "install_id": uuid.uuid4().hex, "source_subpath": plan.source_subpath},
        )

        if plan.action == GITHUB_INSTALL_DOWNLOAD_ONLY:
            result.installed_path = str(download_path)
            return result

        if plan.action == GITHUB_INSTALL_EXTRACT:
            # 直接解压适合 todds 这类工具链资源，目录结构就是最终结果。
            extract_dir = Path(plan.extract_dir or plan.download_dir)
            extract_dir.mkdir(parents=True, exist_ok=True)
            self._extract_install_archive(download_path, extract_dir, task)
            result.extracted_path = str(extract_dir)
            result.installed_path = str(extract_dir)
            self._cleanup_archive(download_path, plan)
            return result

        if plan.action == GITHUB_INSTALL_EXTRACT_THEN_MOVE:
            # 先解压到临时目录，再解析出真正要部署的根目录，避免把 GitHub 外层包裹目录直接搬进目标位置。
            move_target_dir = Path(plan.move_target_dir)
            if not plan.move_target_dir:
                raise ValueError("extract_then_move 缺少 move_target_dir")
            move_target_dir.mkdir(parents=True, exist_ok=True)

            if request.tracking:
                for pending in move_target_dir.glob(".github-pending-*.json"):
                    if json.loads(pending.read_text(encoding="utf-8")).get("target") == plan.final_name:
                        raise RuntimeError("该目录仍有未完成的部署恢复记录，请重启软件完成恢复后再部署")

            with tempfile.TemporaryDirectory(prefix=".github-stage-", dir=move_target_dir) as temp_dir:
                temp_root = Path(temp_dir)
                self._extract_install_archive(download_path, temp_root, task)
                source_path = self._resolve_install_source(temp_root, plan)
                if plan.source_resolver == GITHUB_RESOLVER_MOD_ROOT:
                    result.installed_info["package_id"] = self._validate_mod_source(source_path, temp_root, request)
                final_name = plan.final_name or source_path.name
                if Path(final_name).name != final_name or final_name in {"", ".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', final_name):
                    raise ValueError("无效的安装目录名")
                dest_path = move_target_dir / final_name
                if dest_path.is_symlink():
                    raise ValueError("安装目标不能是符号链接")
                if dest_path.exists() and request.tracking:
                    bound = GithubModRecord.get_or_none(repo_url=request.repo_url)
                    if not bound or bound.local_folder != final_name:
                        raise FileExistsError("安装目录已被其它内容占用，请选择新的绑定目录")
                if dest_path.exists() and not plan.overwrite_existing:
                    raise FileExistsError(f"目标路径已存在: {dest_path}")
                result.installed_path = str(dest_path)
                result.extracted_path = str(source_path)
                self._check_install_cancelled(task)
                if request.tracking:
                    self._check_tracking(request.repo_url, request.tracking)
                journal = None
                backup_path = None
                if plan.source_resolver == GITHUB_RESOLVER_MOD_ROOT:
                    token = result.installed_info["install_id"]
                    journal = move_target_dir / f".github-pending-{token}.json"
                    backup_path = move_target_dir / f".github-backup-{token}"
                    journal.write_text(json.dumps({"repo_url": request.repo_url, "install_id": token, "target": final_name,
                                                   "stage": temp_root.name, "backup": backup_path.name, "had_target": dest_path.exists()}), encoding="utf-8")
                try:
                    replace_dir_atomically(
                        dest_path,
                        source_path,
                        on_replace=(lambda: request.post_install(result)) if request.post_install else None,
                        backup_path=backup_path,
                    )
                    if journal:
                        try:
                            journal.unlink()
                        except OSError:
                            logger.warning("部署已提交，但恢复文件清理失败: %s", journal, exc_info=True)
                except Exception:
                    if journal and (not backup_path or not backup_path.exists()):
                        journal.unlink(missing_ok=True)
                    raise

            self._cleanup_archive(download_path, plan)
            return result

        if plan.action == GITHUB_INSTALL_RUN_INSTALLER:
            raise NotImplementedError("run_installer 安装动作尚未实现")

        raise ValueError(f"不支持的安装动作: {plan.action}")

    def _build_release_fallback(self, request: GithubInstallRequest, exc: Exception) -> GithubResolvedArtifact | None:
        """当 GitHub API 不可用时，允许调用方提供一个兜底直链。"""
        fallback_url = str(request.artifact.fallback_download_url or "").strip()
        fallback_filename = str(request.artifact.fallback_filename or "").strip()
        if request.artifact.release_tag and (request.install.source_resolver == GITHUB_RESOLVER_MOD_ROOT or "/archive/" in fallback_url or "/repository/archive.zip" in fallback_url):
            source = deepcopy(request)
            source.artifact = GithubArtifactRequest(kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE, source_ref=request.artifact.release_tag, source_ref_type=GITHUB_SOURCE_TAG)
            resolved = self._resolve_source_archive(source)
            resolved.version = request.artifact.release_tag
            resolved.evidence["release_tag"] = request.artifact.release_tag
            return resolved
        if not fallback_url or not fallback_filename: return None

        logger.debug(
            "GitHub release 解析失败，将回退到直接下载：repo=%s/%s error=%s",
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
            provider=request.provider,
            host=request.host,
            project_path=request.project_path,
        )

    def _fetch_repo_info_via_api(self, owner: str, repo: str, *, source_branch: str = "", identity: GitRepoIdentity | None = None, source_ref_type: str = GITHUB_SOURCE_BRANCH, force_refresh: bool = False) -> dict[str, Any]:
        """仓库基础信息必需，发行版与分支提交独立读取，互不阻断。"""
        is_gitlab = identity is not None and identity.provider == GIT_PROVIDER_GITLAB
        identity = identity or GitRepoIdentity(GIT_PROVIDER_GITHUB, "github.com", owner, repo, f"{owner}/{repo}", f"https://github.com/{owner}/{repo}")
        repo_res = self.fetch_gitlab_project(identity, missing_ok=True, force_refresh=force_refresh) if is_gitlab else self.fetch_repo(owner, repo, missing_ok=True, force_refresh=force_refresh)
        if not repo_res: return {"error": "找不到该仓库"}

        default_branch = str(repo_res.get("default_branch") or "").strip()
        resolved_source_branch = str(source_branch or (default_branch if source_ref_type == GITHUB_SOURCE_BRANCH else "")).strip()
        metadata: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for name, fetch in (
            ("release", lambda: self.fetch_gitlab_release(identity, missing_ok=True, force_refresh=force_refresh) if is_gitlab else self.fetch_release(owner, repo, missing_ok=True, force_refresh=force_refresh)),
            ("source", lambda: self.fetch_ref_commit(identity, resolved_source_branch, source_ref_type, force_refresh=force_refresh)),
        ):
            try:
                metadata[name] = fetch() if name != "source" or resolved_source_branch else None
            except (GithubApiError, requests.RequestException) as exc:
                errors[name] = str(exc)
                logger.warning("Git 仓库部分信息读取失败：repo=%s/%s section=%s error=%s", owner, repo, name, exc)
                if not is_gitlab and name == "release":
                    try:
                        metadata[name] = (self.fetch_release_web(owner, repo, missing_ok=True) if name == "release" else
                                          self.fetch_commit_web(owner, repo, ref=resolved_source_branch, missing_ok=True))
                        if metadata[name]:
                            errors.pop(name)
                    except (GithubApiError, requests.RequestException, ET.ParseError) as web_exc:
                        logger.debug("Git 网页部分信息读取失败: section=%s error=%s", name, web_exc)
        release_info = metadata.get("release")
        if is_gitlab:
            release_info = self._normalize_gitlab_release_payload(release_info, include_sources=False)
        payload = self._build_repo_info_payload(
            owner,
            repo,
            default_branch,
            resolved_source_branch,
            release_info,
            metadata.get("source"),
            info_source="api",
            degraded=bool(errors),
            provider=identity.provider if identity else GIT_PROVIDER_GITHUB,
            host=identity.host if identity else "github.com",
            errors=errors,
        )
        tag = str((release_info or {}).get("tag_name") or "")
        if tag and not any(str(asset.get("name") or "").lower().endswith(".zip") for asset in payload.get("release_assets") or []):
            try:
                commit = (metadata.get("source") if source_ref_type == GITHUB_SOURCE_TAG and resolved_source_branch == tag else
                          self.fetch_ref_commit(identity, tag, GITHUB_SOURCE_TAG, force_refresh=force_refresh))
                payload["latest_release_commit_sha"] = str((commit or {}).get("sha") or (commit or {}).get("id") or "")
            except (GithubApiError, requests.RequestException) as exc:
                logger.warning("发行版标签提交读取失败: repo=%s tag=%s error=%s", identity.url, tag, exc)
        return payload

    def _fetch_repo_info_via_web(self, owner: str, repo: str, *, source_branch: str = "") -> dict[str, Any] | None:
        """使用 GitHub 网页链路组装仓库信息。

        这里不依赖 API quota，适合作为 `github_fetch_info` 的替代信息源。
        """
        try:
            repo_page = self.fetch_repo_page(owner, repo, missing_ok=True)
            if repo_page is None: return None
            default_branch = self._parse_default_branch_from_html(repo_page)
            resolved_source_branch = str(source_branch or default_branch).strip() or default_branch
            errors: dict[str, str] = {}
            try:
                release_info = self.fetch_release_web(owner, repo, missing_ok=True)
            except (GithubApiError, requests.RequestException) as exc:
                release_info = None
                errors["release"] = str(exc)
            try:
                source_commit = self.fetch_commit_web(owner, repo, ref=resolved_source_branch, missing_ok=True) if resolved_source_branch else None
            except (GithubApiError, requests.RequestException, ET.ParseError) as exc:
                source_commit = None
                errors["source"] = str(exc)
            return self._build_repo_info_payload(
                owner,
                repo,
                default_branch,
                resolved_source_branch,
                release_info,
                source_commit,
                info_source="web",
                degraded=True,
                errors=errors,
            )
        except Exception as exc:
            logger.debug("GitHub 网页兜底失败：repo=%s/%s error=%s", owner, repo, exc)
            return None

    def _fetch_repo_info_from_record_cache(self, repo_url: str, owner: str, repo: str, *, source_branch: str = "") -> dict[str, Any] | None:
        """从本地订阅记录缓存中恢复仓库信息。

        这是最后一道兜底，主要服务于“已订阅仓库在离线或限流时仍可继续部署”。
        """
        record = GithubModRecord.get_or_none(repo_url=repo_url)
        if not record: return None

        online_info = record.online_info_cache or {}
        default_branch = str(online_info.get("default_branch") or "")
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
        same_ref = resolved_source_branch == online_info.get("latest_source_branch")
        payload = self._build_repo_info_payload(
            owner,
            repo,
            default_branch,
            resolved_source_branch,
            release_info if release_info["tag_name"] else None,
            source_commit if same_ref and source_commit.get("sha") else None,
            info_source="record_cache",
            degraded=True,
        )
        payload.update(release_status="stale", source_status="stale")
        return payload

    @staticmethod
    def _normalize_gitlab_release_payload(release: dict[str, Any] | None, *, include_sources: bool) -> dict[str, Any] | None:
        """把 GitLab Release 结构映射成内部统一的 Release 结构。"""
        if not release:
            return None
        assets_payload = release.get("assets") if isinstance(release, dict) else {}
        links = assets_payload.get("links", []) if isinstance(assets_payload, dict) else []
        sources = assets_payload.get("sources", []) if isinstance(assets_payload, dict) else []

        assets: list[dict[str, Any]] = []
        for link in links if isinstance(links, list) else []:
            if not isinstance(link, dict):
                continue
            name = str(link.get("name") or "").strip()
            url = str(link.get("url") or "").strip()
            if name and url:
                assets.append({**link, "name": name, "browser_download_url": url})

        zip_source_url = ""
        if isinstance(sources, list):
            for source in sources:
                if not isinstance(source, dict):
                    continue
                if str(source.get("format") or "").lower() == "zip":
                    zip_source_url = str(source.get("url") or "").strip()
                    if include_sources and zip_source_url:
                        assets.append({
                            "name": f"{release.get('tag_name') or 'source'}.zip",
                            "browser_download_url": zip_source_url,
                        })
                    break

        return {
            "tag_name": str(release.get("tag_name") or "").strip(),
            "name": str(release.get("name") or release.get("tag_name") or "").strip(),
            "zipball_url": zip_source_url,
            "published_at": str(release.get("released_at") or release.get("created_at") or "").strip(),
            "assets": assets,
        }

    def _normalize_provider_catalog_payload(self, payload: dict[str, Any], *, source_url: str) -> dict[str, Any]:
        """把 provider 清单压平为前端推荐列表。

        原始清单按 category -> mod_key 分层，并允许作者信息单独存放。前端更需要一组
        可搜索的行数据，所以这里保留 category，并把名称、包名、作者和版本字段统一到项目内格式。
        """
        if not isinstance(payload, dict):
            raise ValueError("provider 清单格式错误")
        providers = payload.get("providers")
        if not isinstance(providers, dict):
            raise ValueError("provider 清单缺少 providers")
        authors = payload.get("authors", {}) if isinstance(payload.get("authors"), dict) else {}

        items: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {}
        for category, mods in providers.items():
            if not isinstance(mods, dict):
                continue
            category_name = str(category or "other").strip() or "other"
            for mod_key, metadata in mods.items():
                if not isinstance(metadata, dict):
                    continue
                item = self._normalize_provider_catalog_item(category_name, str(mod_key or ""), metadata, authors)
                items.append(item)
                category_counts[category_name] = category_counts.get(category_name, 0) + 1

        items.sort(key=lambda item: (item["category"].lower(), item["name"].lower()))
        return {
            "source_url": source_url,
            "version": payload.get("version"),
            "total": len(items),
            "categories": [{"name": name, "count": count} for name, count in sorted(category_counts.items())],
            "items": items,
        }

    def _fetch_provider_catalog_source(self, source: dict[str, Any], *, force_refresh: bool) -> dict[str, Any]:
        source_id = str(source.get("id") or "").strip()
        if not source_id:
            raise ValueError("清单源缺少 id")
        if not force_refresh:
            cached = self._load_provider_catalog_source_cache(source)
            if cached:
                return cached

        try:
            catalog = self._fetch_provider_catalog_source_remote(source)
        except Exception:
            cached = self._load_provider_catalog_source_cache(source)
            if cached:
                cached["warning"] = f"{source.get('label') or source_id} 远程读取失败，已使用本地缓存"
                cached["source"]["is_stale"] = True
                return cached
            raise
        self._save_provider_catalog_source_cache(source, catalog)
        return catalog

    def _fetch_provider_catalog_source_remote(self, source: dict[str, Any]) -> dict[str, Any]:
        if source.get("type") == "provider_json":
            return self._fetch_provider_json_catalog_source(source)
        if source.get("type") == "github_owner":
            return self._fetch_github_owner_catalog_source(source)
        raise ValueError(f"不支持的清单源类型: {source.get('type')}")

    def _fetch_provider_json_catalog_source(self, source: dict[str, Any]) -> dict[str, Any]:
        url = str(source.get("url") or "").strip()
        if not url:
            raise ValueError("provider_json 清单源缺少 url")
        with build_retry_session() as session:
            response = session.get(
                url,
                headers=self._build_git_headers({"Accept": "application/json"}),
                timeout=(10, 30),
            )
            self._raise_for_git_status(response, url)
            payload = response.json()

        catalog = self._normalize_provider_catalog_payload(payload, source_url=url)
        for item in catalog["items"]:
            item["source_id"] = source["id"]
            if item.get("type") == "zip":
                item["catalog_signature"] = self._catalog_item_signature(item)
        return {
            "source": {
                "id": source["id"],
                "label": source["label"],
                "type": source["type"],
                "url": url,
                "count": len(catalog["items"]),
                "fetched_at": current_ms(),
                "is_stale": False,
            },
            "items": catalog["items"],
        }

    def _fetch_github_owner_catalog_source(self, source: dict[str, Any]) -> dict[str, Any]:
        owner = str(source.get("owner") or "").strip()
        if not owner:
            raise ValueError("github_owner 清单源缺少 owner")
        items = self._fetch_github_owner_catalog(owner, source)
        return {
            "source": {
                "id": source["id"],
                "label": source["label"],
                "type": source["type"],
                "owner": owner,
                "count": len(items),
                "fetched_at": current_ms(),
                "is_stale": False,
            },
            "items": items,
        }

    def _fetch_github_owner_catalog(self, owner: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """读取某个 GitHub 开发者的公开仓库并筛出 RimWorld Mod 仓库。"""
        items: list[dict[str, Any]] = []
        page = 1
        checked_about_count = 0
        with build_retry_session() as session:
            while len(items) < GITHUB_OWNER_CATALOG_MAX_REPOS:
                response = session.get(
                    f"https://api.github.com/users/{owner}/repos",
                    params={"per_page": 100, "page": page, "type": "owner", "sort": "updated", "direction": "desc"},
                    headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                    timeout=(10, 30),
                )
                self._raise_for_github_status(response, f"users/{owner}/repos?page={page}")
                repos = response.json()
                if not isinstance(repos, list) or not repos:
                    break
                for repo_payload in repos:
                    item, checked_about = self._normalize_github_owner_repo_item(repo_payload, session=session, checked_about_count=checked_about_count, source=source)
                    checked_about_count += 1 if checked_about else 0
                    if item:
                        items.append(item)
                    if len(items) >= GITHUB_OWNER_CATALOG_MAX_REPOS:
                        break
                page += 1
        return items

    def _normalize_github_owner_repo_item(self, repo_payload: dict[str, Any], *, session, checked_about_count: int, source: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, bool]:
        if not isinstance(repo_payload, dict) or repo_payload.get("fork") or repo_payload.get("archived"):
            return None, False
        owner_login = str(((repo_payload.get("owner") or {}).get("login")) or "").strip()
        repo_name = str(repo_payload.get("name") or "").strip()
        if not owner_login or not repo_name:
            return None, False

        description = str(repo_payload.get("description") or "").strip()
        homepage = str(repo_payload.get("homepage") or "").strip()
        topics = [str(topic).strip() for topic in repo_payload.get("topics") or [] if str(topic).strip()]
        steam_url = self._extract_steam_workshop_url(" ".join([description, homepage]))
        source = source or BUILTIN_GITHUB_OWNER_SOURCES[0]
        reason = self._match_github_owner_repo(repo_payload, source.get("match") or {})

        checked_about = False
        if not reason and checked_about_count < 80:
            checked_about = True
            match_config = source.get("match") or {}
            if match_config.get("about_xml") and self._github_repo_has_about_xml(session, owner_login, repo_name, str(repo_payload.get("default_branch") or "main")):
                reason = "about_xml"
        if not reason:
            return None, checked_about

        updated_at = str(repo_payload.get("updated_at") or "").strip()
        item = {
            "key": f"github:{owner_login}/{repo_name}",
            "source_id": source.get("id") or owner_login.lower(),
            "category": source.get("label") or owner_login,
            "type": "git",
            "name": repo_name,
            "description": description,
            "info_url": str(repo_payload.get("html_url") or f"https://github.com/{owner_login}/{repo_name}"),
            "url": f"https://github.com/{owner_login}/{repo_name}",
            "raw_url": str(repo_payload.get("clone_url") or f"https://github.com/{owner_login}/{repo_name}.git"),
            "branch": str(repo_payload.get("default_branch") or "").strip(),
            "tags": topics,
            "author": [owner_login],
            "workshop_url": steam_url,
        }
        if updated_at:
            item["updated_at"] = updated_at
        return item, checked_about

    @staticmethod
    def _match_github_owner_repo(repo_payload: dict[str, Any], match_config: dict[str, Any]) -> str:
        """按内置作者规则筛选仓库；规则在常量里配置，避免为单个作者写死判断。"""
        field_values = {
            "description": [str(repo_payload.get("description") or "")],
            "homepage": [str(repo_payload.get("homepage") or "")],
            "name": [str(repo_payload.get("name") or "")],
            "topics": [str(topic or "") for topic in repo_payload.get("topics") or []],
        }
        for field_name, values in field_values.items():
            patterns = match_config.get(field_name) or []
            for pattern in patterns:
                try:
                    regex = re.compile(str(pattern), re.I)
                except re.error:
                    logger.warning("Git 作者列表规则正则无效: field=%s pattern=%s", field_name, pattern)
                    continue
                if any(regex.search(value or "") for value in values):
                    return field_name
        return ""

    def _normalize_provider_catalog_item(self, category: str, mod_key: str, metadata: dict[str, Any], authors: dict[str, Any]) -> dict[str, Any]:
        provider_type = str(metadata.get("type") or "").strip().lower()
        raw_url = str(metadata.get("url") or "").strip()
        identity = self.parse_git_repo_url(raw_url) if provider_type == "git" else None
        author_names = []
        for author_key in metadata.get("authors") or []:
            author_meta = authors.get(author_key) if isinstance(authors, dict) else None
            if isinstance(author_meta, dict):
                author_names.append(str(author_meta.get("display_name") or author_key).strip())
            else:
                author_names.append(str(author_key).strip())

        # RJW 原清单的 display_name 才是用户能识别的名称，name 更接近安装目录名。
        install_name = str(metadata.get("name") or mod_key).strip() or mod_key
        display_name = str(metadata.get("display_name") or install_name).strip() or install_name
        repo_url = identity.url if identity else raw_url
        item = {
            "key": mod_key,
            "category": category,
            "type": provider_type,
            "name": display_name,
            "description": str(metadata.get("description") or "").strip(),
            "info_url": str(metadata.get("info_url") or raw_url).strip(),
            "url": repo_url,
            "raw_url": raw_url,
            "branch": str(metadata.get("branch") or "").strip(),
            "subdir": str(metadata.get("subdir") or "").strip(),
            "package_id": str(metadata.get("mod_id") or "").strip(),
            "depends": [str(item).strip() for item in metadata.get("depends") or [] if str(item).strip()],
            "author": [name for name in author_names if name],
        }
        if "tags" in metadata:
            item["tags"] = [str(value).strip() for value in metadata.get("tags") or [] if str(value).strip()]
        if "rimworld_versions" in metadata:
            item["game_versions"] = [str(value).strip() for value in metadata.get("rimworld_versions") or [] if str(value).strip()]
        if metadata.get("disabled") is True:
            item["not_recommended"] = True
        return item

    def _load_provider_catalog_source_cache(self, source: dict[str, Any] | str) -> dict[str, Any] | None:
        cache_path = self._provider_catalog_cache_path(source)
        payload = self._read_provider_catalog_cache(cache_path)
        if self._provider_catalog_cache_matches_source(payload, source):
            return payload

        legacy_path = self._legacy_provider_catalog_cache_path(source)
        if legacy_path and legacy_path != cache_path:
            legacy_payload = self._read_provider_catalog_cache(legacy_path)
            if isinstance(legacy_payload, dict) and self._provider_catalog_cache_matches_source(legacy_payload, source):
                self._save_provider_catalog_source_cache(source, legacy_payload)
                return legacy_payload
        return None

    def _read_provider_catalog_cache(self, cache_path: Path) -> dict[str, Any] | None:
        if not cache_path.exists():
            return None
        try:
            with open(cache_path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            payload["from_file_cache"] = True
            return payload
        except Exception as exc:
            logger.warning("读取 Git 推荐清单缓存失败: %s", exc)
            return None

    @staticmethod
    def _provider_catalog_cache_matches_source(payload: dict[str, Any] | None, source: dict[str, Any] | str) -> bool:
        if not isinstance(payload, dict):
            return False
        if not isinstance(source, dict):
            return True
        expected_id = str(source.get("id") or "").strip()
        cached_source = payload.get("source")
        cached_id = str(cached_source.get("id") or "").strip() if isinstance(cached_source, dict) else ""
        return not expected_id or not cached_id or cached_id == expected_id

    def _legacy_provider_catalog_cache_path(self, source: dict[str, Any] | str) -> Path | None:
        if not isinstance(source, dict):
            return None
        source_id = str(source.get("id") or "").strip()
        cache_id = str(source.get("cache_id") or "").strip()
        if not source_id or source_id == cache_id:
            return None
        return self._provider_catalog_cache_path(source_id)

    def _save_provider_catalog_source_cache(self, source: dict[str, Any] | str, catalog: dict[str, Any]) -> None:
        cache_path = self._provider_catalog_cache_path(source)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as handle:
                json.dump(catalog, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("保存 Git 推荐清单缓存失败: %s", exc)

    def _provider_catalog_cache_path(self, source: dict[str, Any] | str) -> Path:
        source_key = (source.get("cache_id") or source.get("id")) if isinstance(source, dict) else source
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(source_key or "catalog")).strip("_") or "catalog"
        return GIT_PROVIDER_CATALOG_DIR / f"{safe_id}.json"

    def _provider_catalog_sources(self, override_url: str = "") -> list[dict[str, Any]]:
        provider_text = str(override_url or getattr(settings.config, "git_provider_catalog_url", "") or RJW_PROVIDER_CATALOG_URL)
        provider_sources = self._parse_provider_json_sources(provider_text)
        return [*provider_sources, *[dict(source) for source in BUILTIN_GITHUB_OWNER_SOURCES]]

    def _parse_provider_json_sources(self, text: str) -> list[dict[str, Any]]:
        rows = self._split_catalog_config_rows(text)
        if not rows:
            rows = [f"RJW|{RJW_PROVIDER_CATALOG_URL}"]
        sources = []
        for idx, row in enumerate(rows):
            label, url = self._split_catalog_label_value(row, default_label="RJW" if idx == 0 else f"清单{idx + 1}")
            if not url:
                continue
            sources.append({
                "id": self._catalog_source_id(label, "provider_json", url),
                "cache_id": self._catalog_source_cache_id(label, "provider_json", url),
                "label": label,
                "type": "provider_json",
                "url": url,
            })
        return sources

    @staticmethod
    def _split_catalog_config_rows(text: str) -> list[str]:
        return [part.strip() for part in re.split(r"[\r\n,]+", str(text or "")) if part.strip()]

    @staticmethod
    def _split_catalog_label_value(row: str, *, default_label: str) -> tuple[str, str]:
        if "|" in row:
            label, value = row.split("|", 1)
            return label.strip() or default_label, value.strip()
        return default_label, row.strip()

    @staticmethod
    def _catalog_source_id(label: str, source_type: str, value: str) -> str:
        base = GithubManager._catalog_source_cache_id(label, source_type, value)
        digest = hashlib.sha1(str(value or "").strip().encode("utf-8")).hexdigest()[:8]
        return f"{base or source_type}_{digest}"

    @staticmethod
    def _catalog_source_cache_id(label: str, source_type: str, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(label or value or source_type).strip().lower()).strip("_") or source_type

    @staticmethod
    def _provider_catalog_sources_key(sources: list[dict[str, Any]]) -> str:
        return json.dumps(sources, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _provider_catalog_source_signature(catalog: dict[str, Any] | None) -> str:
        if not isinstance(catalog, dict):
            return ""
        raw_items = catalog.get("items")
        items: list[Any] = raw_items if isinstance(raw_items, list) else []
        def sort_key(item: Any) -> str:
            if not isinstance(item, dict):
                return f"1\x1f{item}"
            parts = [str(item.get(key) or "") for key in ("source_id", "key", "url", "name")]
            return "0\x1f" + "\x1f".join(parts)

        normalized_items = sorted(items, key=sort_key)
        payload = json.dumps(normalized_items, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _provider_catalog_sources_signature(items: list[dict[str, Any]], signature_key: str) -> str:
        payload = [
            {
                "source_id": item.get("source_id") or "",
                "signature": item.get(signature_key) or "",
                "count": int(item.get("remote_count" if signature_key == "remote_signature" else "local_count") or 0),
            }
            for item in items
        ]
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha1(text.encode("utf-8")).hexdigest() if payload else ""

    def _github_repo_has_about_xml(self, session, owner: str, repo: str, default_branch: str) -> bool:
        """轻量检查仓库根目录是否有 RimWorld About/About.xml。"""
        try:
            response = session.get(
                f"{GITHUB_API_BASE}/{owner}/{repo}/contents/About/About.xml",
                params={"ref": default_branch or "main"},
                headers=self._build_github_headers({"Accept": GITHUB_ACCEPT_HEADER}),
                timeout=(5, 15),
            )
            if response.status_code == 404:
                return False
            self._raise_for_github_status(response, f"{owner}/{repo}/contents/About/About.xml")
            payload = response.json()
            return str(payload.get("type") or "").lower() == "file"
        except Exception as exc:
            logger.debug("检查 GitHub 仓库 About.xml 失败: %s/%s %s", owner, repo, exc)
            return False

    @staticmethod
    def _extract_steam_workshop_url(text: str) -> str:
        match = re.search(r"https?://steamcommunity\.com/sharedfiles/filedetails/\?id=\d+", str(text or ""), re.I)
        return match.group(0) if match else ""

    @staticmethod
    def _catalog_item_signature(item: dict[str, Any]) -> str:
        # 直链清单通常没有语义版本，使用关键安装字段生成稳定签名作为更新判断依据。
        payload = {
            "url": item.get("raw_url") or item.get("url"),
            "subdir": item.get("subdir"),
            "branch": item.get("branch"),
            "name": item.get("name"),
            "source_id": item.get("source_id"),
            "updated_at": item.get("updated_at"),
            "remote_etag": item.get("remote_etag"),
            "remote_last_modified": item.get("remote_last_modified"),
            "remote_content_length": item.get("remote_content_length"),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _refresh_catalog_zip_signature(self, item: dict[str, Any]) -> dict[str, Any]:
        """为已订阅 zip 补充远端文件指纹。

        推荐清单加载时不批量探测直链，避免 UI 被大量 HEAD 请求拖慢；只在订阅刷新/部署时检查。
        """
        payload = dict(item or {})
        download_url = str(payload.get("raw_url") or payload.get("url") or "").strip()
        if not download_url:
            return payload
        try:
            with build_retry_session() as session:
                response = session.head(
                    download_url,
                    headers=self._build_git_headers({"Accept": "*/*"}),
                    timeout=(5, 15),
                    allow_redirects=True,
                )
                self._raise_for_git_status(response, download_url)
            payload["remote_etag"] = str(response.headers.get("ETag") or "").strip()
            payload["remote_last_modified"] = str(response.headers.get("Last-Modified") or "").strip()
            payload["remote_content_length"] = str(response.headers.get("Content-Length") or "").strip()
            payload["catalog_signature"] = self._catalog_item_signature(payload)
        except Exception as exc:
            logger.debug("刷新清单 zip 远端指纹失败: %s %s", download_url, exc)
        return payload

    @staticmethod
    def _merge_provider_catalog_items(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for group in groups:
            for item in group or []:
                url = str(item.get("url") or item.get("raw_url") or item.get("key") or "").strip().lower()
                if not url:
                    continue
                merged[url] = item
        return sorted(merged.values(), key=lambda item: (str(item.get("source_id") or ""), str(item.get("category") or ""), str(item.get("name") or "").lower()))

    def _build_repo_info_payload(self, owner: str, repo: str, default_branch: str, resolved_source_branch: str, release_info: dict[str, Any] | None, source_commit: dict[str, Any] | None, *, info_source: str, degraded: bool, provider: str = GIT_PROVIDER_GITHUB, host: str = "github.com", errors: dict[str, str] | None = None) -> dict[str, Any]:
        """把不同来源的数据统一整理成前端可消费的结构。"""
        source_commit_sha = str((source_commit or {}).get("sha") or (source_commit or {}).get("id") or "")
        source_commit_at = self._extract_commit_timestamp(source_commit)
        has_release = bool(release_info and str(release_info.get("tag_name") or "").strip())
        payload = {
            "repo_url": f"https://{host}/{owner}/{repo}",
            "provider": provider,
            "host": host,
            "owner": owner,
            "repo": repo,
            "default_branch": str(default_branch or "").strip(),
            "has_release": has_release,
            "latest_release_tag": str((release_info or {}).get("tag_name") or "").strip(),
            "latest_release_name": str((release_info or {}).get("name") or "").strip(),
            "release_zip_url": str((release_info or {}).get("zipball_url") or "").strip(),
            "latest_release_published_at": str((release_info or {}).get("published_at") or (release_info or {}).get("released_at") or "").strip(),
            "latest_source_branch": str(resolved_source_branch or default_branch or "").strip(),
            "latest_source_commit_sha": source_commit_sha,
            "latest_source_commit_at": source_commit_at,
            "latest_source_version": self._build_source_version(resolved_source_branch or default_branch, source_commit_sha),
            "release_assets": list((release_info or {}).get("assets") or []),
            "info_source": str(info_source or "unknown").strip() or "unknown",
            "is_degraded": bool(degraded),
            "release_status": "error" if (errors or {}).get("release") else "available" if has_release else "missing",
            "source_status": "error" if (errors or {}).get("source") else "available" if source_commit else "missing",
        }
        if errors:
            payload["fetch_warning"] = "; ".join(f"{name}: {error}" for name, error in errors.items())
            # 失败不是空结果，只保留失败部分的旧证据；切换分支不继承其它分支的提交。
            record = GithubModRecord.get_or_none(repo_url=payload["repo_url"])
            cached = (record.online_info_cache or {}) if record else {}
            for key, value in cached.items():
                if "release" in errors and (key.startswith("latest_release_") or key in ("has_release", "release_zip_url")):
                    payload[key] = value
                if "source" in errors and cached.get("latest_source_branch") == resolved_source_branch and key.startswith("latest_source_"):
                    payload[key] = value
        return payload

    def _resolve_default_branch(self, owner: str, repo: str, *, repo_url: str = "") -> str:
        """解析仓库默认分支。

        默认分支只是安装的入口参数，不值得因为它查不到就阻断下载，所以这里必须允许多级降级。
        """
        try:
            repo_info = self.fetch_repo(owner, repo, missing_ok=True)
            if repo_info:
                default_branch = str(repo_info.get("default_branch") or "").strip()
                if default_branch: return default_branch
        except Exception as exc:
            # 默认分支可从网页、缓存和 main 兜底，预解析失败不应形成用户可见告警。
            logger.debug("GitHub 默认分支预解析失败，将继续使用降级来源：repo=%s/%s error=%s", owner, repo, exc)

        web_info = self._fetch_repo_info_via_web(owner, repo)
        if web_info:
            default_branch = str(web_info.get("default_branch") or "").strip()
            if default_branch: return default_branch

        record_info = self._fetch_repo_info_from_record_cache(repo_url or f"{GITHUB_WEB_BASE}/{owner}/{repo}", owner, repo)
        if record_info:
            default_branch = str(record_info.get("default_branch") or "").strip()
            if default_branch: return default_branch

        raise GithubApiError("无法确定仓库默认分支，请显式选择分支")

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
            if match: return str(match.group(1) or "").strip()
        return ""

    @staticmethod
    def _parse_commit_atom_payload(xml_text: str) -> dict[str, Any] | None:
        """解析 GitHub commits Atom feed 的首条记录。"""
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None: return None

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
        if not commit_payload: return ""
        for key in ("committed_date", "authored_date", "created_at"):
            value = str(commit_payload.get(key) or "").strip()
            if value:
                return value
        commit_info = commit_payload.get("commit") if isinstance(commit_payload, dict) else {}
        committer_info = commit_info.get("committer", {}) if isinstance(commit_info, dict) else {}
        author_info = commit_info.get("author", {}) if isinstance(commit_info, dict) else {}
        return str(committer_info.get("date") or author_info.get("date") or "").strip()

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
    def _build_source_version(branch_name: str, commit_sha: str) -> str:
        """把源码分支部署版本编码成可读且可比较的稳定字符串。"""
        normalized_branch = str(branch_name or "").strip() or "source"
        normalized_sha = str(commit_sha or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40}", normalized_sha): return ""
        return f"{normalized_branch}@{normalized_sha}"

    @staticmethod
    def _release_asset_fingerprint(asset: dict[str, Any]) -> str:
        keys = ("id", "size", "updated_at", "digest", "browser_download_url")
        if not any(asset.get(key) for key in keys[:-1]):
            return ""
        return hashlib.sha256(json.dumps({key: asset.get(key) for key in keys}, sort_keys=True).encode()).hexdigest()

    def _resolve_install_source(self, temp_root: Path, plan: GithubInstallPlan) -> Path:
        """决定“解压后到底哪一层目录才是要安装的源目录”。"""
        if plan.source_subpath:
            normalized_subpath = Path(plan.source_subpath.replace("\\", "/"))
            if normalized_subpath.anchor or ".." in normalized_subpath.parts or ":" in str(normalized_subpath):
                raise ValueError("压缩包内部路径必须是相对目录，不能包含上级路径")
            roots = [temp_root, self._find_archive_root(temp_root)]
            candidates = { (root / normalized_subpath).resolve() for root in roots if root }
            candidates = {path for path in candidates if path.is_dir() and temp_root.resolve() in path.parents}
            if len(candidates) == 1:
                return candidates.pop()
            if len(candidates) > 1:
                raise ValueError("压缩包内部路径存在歧义，请指定完整的相对目录")
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
        if len(entries) == 1: return entries[0]
        directories = [entry for entry in entries if entry.is_dir()]
        if len(directories) == 1: return directories[0]
        return None

    @staticmethod
    def _find_mod_root(temp_root: Path) -> Path | None:
        """在解压结果里定位 RimWorld Mod 根目录。

        判断依据是 `About/About.xml`，这是现有工程里最稳定的 Mod 根特征。
        """
        candidates = []
        for root, dirs, _files in os.walk(temp_root):
            if "About" in dirs:
                about_xml = Path(root) / "About" / "About.xml"
                if about_xml.is_file(): candidates.append(Path(root))
        if len(candidates) > 1:
            archive_root = GithubManager._find_archive_root(temp_root) or temp_root
            paths = [str(path.relative_to(archive_root)).replace("\\", "/") if path.is_relative_to(archive_root) else str(path.relative_to(temp_root)).replace("\\", "/") for path in candidates]
            raise GitSelectionRequired("压缩包包含多个模组，请选择要部署的目录", "source_subpath", paths)
        return candidates[0] if candidates else None

    @staticmethod
    def _cleanup_archive(download_path: Path, plan: GithubInstallPlan) -> None:
        """按计划决定是否清理下载包。"""
        if not plan.cleanup_archive: return
        try: download_path.unlink()
        except OSError: pass

    @staticmethod
    def _update_mod_record(repo_url: str, version: str, local_folder: str, *, installed_info: dict[str, Any] | None = None, tracking: dict[str, Any] | None = None) -> None:
        """更新 GitHub 订阅记录。

        这一步保留在 GitHub manager 内，是因为它属于 GitHub 订阅域的数据，而不是通用安装器职责。
        """
        with db.atomic():
            record = GithubModRecord.get_or_none(repo_url=repo_url)
            if tracking:
                GithubManager._check_tracking(repo_url, tracking)
            if record:
                record.installed_version = version
                record.local_folder = local_folder
                record.installed_info = dict(installed_info or {})
                record.save()

    @staticmethod
    def _check_tracking(repo_url: str, tracking: dict[str, Any]) -> None:
        record = GithubModRecord.get_or_none(repo_url=repo_url)
        if not record or any(getattr(record, key) != value for key, value in tracking.items()):
            raise InterruptedError("仓库跟踪设置已改变，旧部署任务已取消")

    @staticmethod
    def _check_install_cancelled(task: DownloadTask) -> None:
        if task._cancel_event.is_set():
            raise InterruptedError("Task cancelled by user")

    def _extract_install_archive(self, archive_path: Path, target: Path, task: DownloadTask) -> None:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if sum(entry.file_size for entry in entries) > shutil.disk_usage(target).free:
                raise OSError("磁盘空间不足，无法准备安装目录")
            for entry in entries:
                self._check_install_cancelled(task)
                path = (target / entry.filename.replace("\\", "/")).resolve()
                if not path.is_relative_to(target.resolve()) or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("压缩包包含非法路径或符号链接")
                if entry.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, path.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        self._check_install_cancelled(task)
                        output.write(chunk)

    def _validate_mod_source(self, root: Path, archive_root: Path, request: GithubInstallRequest) -> str:
        xml_root = ET.parse(root / "About" / "About.xml").getroot()
        package_id = normalize_package_id(xml_root.findtext("packageId") or "")
        if not package_id:
            raise ValueError("模组 About.xml 缺少有效 packageId")
        record = GithubModRecord.get_or_none(repo_url=request.repo_url)
        expected = str((record.installed_info or {}).get("package_id") or (record.online_info_cache or {}).get("package_id") or "") if record else ""
        if not expected and record and record.local_folder and Path(record.local_folder).name == record.local_folder:
            previous_about = Path(settings.config.self_mods_path) / record.local_folder / "About" / "About.xml"
            if previous_about.is_file():
                expected = ET.parse(previous_about).getroot().findtext("packageId") or ""
        if expected and normalize_package_id(expected) != package_id:
            raise ValueError("下载内容的模组标识与原安装不一致")
        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_size < 1024:
                with path.open("rb") as handle:
                    if handle.read(50).startswith(b"version https://git-lfs.github.com/spec/v1"):
                        raise ValueError("源码包包含未下载的 Git LFS 文件，请使用完整发行包")
        if any(root.rglob("*.cs")) and not any(root.rglob("*.dll")):
            raise ValueError("源码包包含未编译的 C# 代码，请选择已编译的发行包")
        for modules in archive_root.rglob(".gitmodules"):
            import configparser
            config = configparser.ConfigParser(interpolation=None)
            config.read(modules, encoding="utf-8")
            for section in config.sections():
                path = (modules.parent / config.get(section, "path", fallback="")).resolve()
                if path.is_relative_to(root.resolve()) and (not path.is_dir() or not any(path.iterdir())):
                    raise ValueError("源码包缺少 Git 子模块内容，请使用完整发行包")
        return package_id

    def recover_pending_installs(self) -> None:
        """启动时按数据库提交标识恢复中断的部署；只处理受控的同级路径。"""
        if not settings.config.self_mods_path:
            return
        parent = Path(settings.config.self_mods_path).resolve()
        for journal in parent.glob(".github-pending-*.json"):
            try:
                data = json.loads(journal.read_text(encoding="utf-8"))
                token = data["install_id"]
                if not re.fullmatch(r"[0-9a-f]{32}", token) or journal.name != f".github-pending-{token}.json":
                    raise ValueError("无效的恢复标识")
                names = [data["target"], data["stage"], data["backup"]]
                if any(Path(name).name != name or name in {"", ".", ".."} for name in names):
                    raise ValueError("无效的恢复目录")
                target, stage, backup = [parent / name for name in names]
                if not stage.name.startswith(".github-stage-") or backup.name != f".github-backup-{token}":
                    raise ValueError("无效的恢复暂存目录")
                if any(path.is_symlink() or path.resolve().parent != parent for path in (target, stage, backup)):
                    raise ValueError("恢复目录超出安装边界")
                record = GithubModRecord.get_or_none(repo_url=data["repo_url"])
                committed = bool(record and (record.installed_info or {}).get("install_id") == token)
                if committed:
                    if backup.exists(): shutil.rmtree(backup)
                elif backup.exists():
                    if target.exists(): shutil.rmtree(target)
                    backup.replace(target)
                elif not data["had_target"] and target.exists():
                    shutil.rmtree(target)
                if stage.exists(): shutil.rmtree(stage)
                journal.unlink()
                logger.info("已恢复中断的 Git 部署: repo=%s committed=%s", data["repo_url"], committed)
            except Exception:
                logger.error("Git 部署恢复失败，保留恢复文件: %s", journal, exc_info=True)

    def migrate_subscription_records(self) -> None:
        marker = "git_subscription_identity_v1"
        if SystemInfo.get_or_none(key=marker):
            return
        with db.atomic():
            for snapshot in list(GithubModRecord.select()):
                record = GithubModRecord.get_or_none(repo_url=snapshot.repo_url)
                if not record: continue
                if record.install_type == "zip": continue
                identity = self.parse_git_repo_url(record.repo_url)
                if not identity: continue
                canonical = identity.url
                duplicate = GithubModRecord.get_or_none(repo_url=canonical) if canonical != record.repo_url else None
                if duplicate and record.local_folder and duplicate.local_folder and record.local_folder != duplicate.local_folder:
                    logger.warning("Git 重复订阅绑定不同本地目录，保留记录等待重新绑定: %s", record.repo_url)
                    continue
                installed = dict(record.installed_info or {})
                ref, _, sha = str(record.installed_version or "").partition("@")
                if not installed and record.installed_version:
                    installed = ({"ref": ref, "ref_type": GITHUB_SOURCE_BRANCH, "commit_sha": sha.lower(), "artifact_kind": GITHUB_ARTIFACT_SOURCE_ARCHIVE}
                                 if record.install_type == "source" and re.fullmatch(r"[0-9a-fA-F]{40}", sha) else
                                 {"legacy_version": record.installed_version})
                if duplicate:
                    if not duplicate.local_folder and record.local_folder:
                        duplicate.local_folder, duplicate.installed_version, duplicate.installed_info = record.local_folder, record.installed_version, installed
                        duplicate.save()
                elif canonical != record.repo_url:
                    values = record.__data__.copy()
                    values.update(repo_url=canonical, provider=identity.provider, host=identity.host, installed_info=installed)
                    GithubModRecord.create(**values)
                else:
                    record.installed_info = installed
                    record.save()
                    continue
                GithubTimeline.update(repo_url=canonical).where(GithubTimeline.repo_url == record.repo_url).execute()
                record.delete_instance()
            SystemInfo.create(key=marker, value="1")

    @staticmethod
    def subscription_status(record: dict[str, Any]) -> str:
        """状态统一来自真实部署证据；时间戳和降级缓存不证明版本相同。"""
        info = record.get("online_info") or record.get("online_info_cache") or {}
        installed = record.get("installed_info") or {}
        version = str(record.get("installed_version") or "")
        if record.get("local_folder") and record.get("local_exists") is False: return "missing"
        if not version: return "not_deployed"
        options = record.get("install_options") or {}
        if (installed.get("source_subpath") or "") != (options.get("source_subpath") or ""): return "branch_changed"
        install_type = record.get("install_type") or "source"
        if install_type == "zip":
            latest = info.get("catalog_signature")
            return "unknown" if not latest else "current" if latest == version else "upgrade"
        section = "release" if install_type == "release" else "source"
        if info.get(f"{section}_status") != "available" or info.get("info_source") in {"record_cache", "minimal"}: return "unknown"
        if install_type == "source":
            ref_type = (record.get("install_options") or {}).get("ref_type") or GITHUB_SOURCE_BRANCH
            if installed.get("ref") and (installed["ref"] != record.get("target_branch") or installed.get("ref_type", GITHUB_SOURCE_BRANCH) != ref_type): return "branch_changed"
            sha = installed.get("commit_sha")
            latest = info.get("latest_source_commit_sha")
            if not sha or not latest or info.get("latest_source_branch") != record.get("target_branch") or info.get("source_ref_type", "branch") != ref_type: return "unknown"
            return "current" if sha == latest else "upgrade"
        tag = info.get("latest_release_tag")
        if not installed.get("release_tag") or not tag: return "unknown"
        if installed["release_tag"] != tag: return "upgrade"
        if installed.get("artifact_kind") == GITHUB_ARTIFACT_SOURCE_ARCHIVE:
            sha, latest = installed.get("commit_sha"), info.get("latest_release_commit_sha")
            return "unknown" if not sha or not latest else "current" if sha == latest else "upgrade"
        if options.get("asset_name") and options["asset_name"] != installed.get("asset_name"): return "branch_changed"
        asset = next((a for a in info.get("release_assets") or [] if a.get("name") == installed.get("asset_name")), None)
        fingerprint = GithubManager._release_asset_fingerprint(asset or {})
        if not fingerprint or not installed.get("asset_fingerprint"): return "unknown"
        return "current" if fingerprint == installed["asset_fingerprint"] else "upgrade"

    def _identity_from_request(self, request: GithubInstallRequest) -> GitRepoIdentity:
        """从安装请求恢复 provider 解析结果。"""
        identity = self.parse_git_repo_url(request.repo_url)
        if identity:
            return identity
        host = str(request.host or "github.com").strip() or "github.com"
        path = str(request.project_path or f"{request.owner}/{request.repo}").strip()
        return GitRepoIdentity(
            provider=str(request.provider or GIT_PROVIDER_GITHUB).strip() or GIT_PROVIDER_GITHUB,
            host=host,
            owner=request.owner,
            repo=request.repo,
            path=path,
            url=f"https://{host}/{path}",
        )

    @staticmethod
    def _build_gitlab_archive_url(identity: GitRepoIdentity, ref: str) -> str:
        """构造 GitLab/GitGud 公开源码 zip 下载地址。"""
        project_id = quote(identity.path, safe="")
        return f"https://{identity.host}/api/v4/projects/{project_id}/repository/archive.zip?sha={quote(str(ref or '').strip(), safe='')}"

    def _build_github_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """GitHub API 单独使用浏览器风格 UA。

        这样做不是为了解决 rate limit，而是为了减少被某些网关按“非浏览器默认脚本”特殊对待的概率。
        """
        return merge_headers(headers, user_agent=GITHUB_BROWSER_USER_AGENT)

    def _build_git_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """公开 Git 托管站请求统一使用浏览器风格 UA。"""
        return merge_headers(headers, user_agent=GITHUB_BROWSER_USER_AGENT)

    def _raise_for_git_status(self, response, request_label: str) -> None:
        """把 GitLab/GitGud HTTP 错误转换成更可读的异常。"""
        if response.status_code < 400: return

        if response.status_code == 404:
            raise GithubApiError(f"Git 仓库资源不存在: {request_label}")

        response_text = ""
        try:
            payload = response.json()
            response_text = str(payload.get("message") or "")
        except Exception:
            response_text = response.text or ""

        if response.status_code in (403, 429) and "rate" in response_text.lower():
            raise GithubRateLimitError(f"Git 仓库 API 限流: {request_label}")

        response.raise_for_status()

    def _raise_for_github_status(self, response, request_label: str) -> None:
        """把 GitHub 的 HTTP 错误转换成更可读的异常。"""
        if response.status_code < 400: return

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
        if cache_lock is None: return self._cache_miss

        now = time.time()
        with cache_lock:
            cached = GithubManager._response_cache.get(cache_key)
            if not cached: return self._cache_miss
            expires_at, payload = cached
            if expires_at < now:
                GithubManager._response_cache.pop(cache_key, None)
                return self._cache_miss
            return deepcopy(payload)

    def _store_cached_payload(self, cache_key: tuple[str, ...], payload: Any, *, ttl_seconds: int = GITHUB_API_CACHE_TTL_SECONDS) -> None:
        """写入共享缓存。"""
        cache_lock = GithubManager._cache_lock
        if cache_lock is None: return
        with cache_lock:
            GithubManager._response_cache[cache_key] = (time.time() + max(1, int(ttl_seconds)), deepcopy(payload))
