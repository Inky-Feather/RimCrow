from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
import re
import shutil
import subprocess

from backend.managers.mgr_github import (
    GITHUB_ARTIFACT_RELEASE_ASSET,
    GITHUB_INSTALL_EXTRACT_THEN_MOVE,
    GithubArtifactRequest,
    GithubInstallPlan,
    GithubInstallRequest,
    GithubManager,
)
from backend.i18n.messages import tr
from backend.settings import TOOLS_DIR, settings


RIPGREP_TOOL_DIR = TOOLS_DIR / "ripgrep"
RIPGREP_EXECUTABLE_NAMES = ("rg.exe", "rg")
RIPGREP_ASSET_PREFIX = "ripgrep-"
# 旧常量保留给外部引用；实际资产按运行平台选择。
RIPGREP_WINDOWS_ASSET_PREFIX = RIPGREP_ASSET_PREFIX
RIPGREP_WINDOWS_ASSET_SUFFIX = "-x86_64-pc-windows-msvc.zip"
RIPGREP_VERSION_PATTERN = re.compile(r"^ripgrep\s+([0-9]+(?:\.[0-9]+)*)", re.IGNORECASE)


@dataclass(frozen=True)
class RipgrepStatus:
    available: bool
    resolved_path: str
    current_version: str
    message: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "available": self.available,
            "resolved_path": self.resolved_path,
            "current_version": self.current_version,
            "message": self.message,
        }
def get_ripgrep_asset_suffix(system_name: str | None = None, machine: str | None = None) -> str:
    """返回当前平台对应的 GitHub Release 资产后缀；不支持时返回空字符串。"""
    system = str(system_name or platform.system()).strip().lower()
    arch = str(machine or platform.machine()).strip().lower()
    if system == "windows":
        return "-x86_64-pc-windows-msvc.zip"
    if system == "darwin":
        return "-aarch64-apple-darwin.tar.gz" if arch in {"arm64", "aarch64"} else "-x86_64-apple-darwin.tar.gz"
    if system == "linux":
        if arch in {"x86_64", "amd64"}:
            return "-x86_64-unknown-linux-musl.tar.gz"
        if arch in {"aarch64", "arm64"}:
            return "-aarch64-unknown-linux-gnu.tar.gz"
        if arch.startswith("armv7"):
            return "-armv7-unknown-linux-gnueabihf.tar.gz"
    return ""


def resolve_ripgrep_root(raw_path: str | None = None) -> Path:
    configured = str(raw_path or "").strip()
    if configured:
        candidate = Path(configured)
        return candidate.parent if candidate.is_file() else candidate
    fallback = str(getattr(settings.config, "ripgrep_path", "") or "").strip()
    if fallback: return resolve_ripgrep_root(fallback)
    return RIPGREP_TOOL_DIR


def resolve_ripgrep_executable(raw_path: str | None = None, *, include_fallback: bool = True) -> Path | None:
    executable, _ = resolve_ripgrep_executable_with_version(raw_path, include_fallback=include_fallback)
    return executable


def resolve_ripgrep_executable_with_version(
    raw_path: str | None = None,
    *,
    include_fallback: bool = True,
) -> tuple[Path | None, str]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add_candidate(path_like: str | Path | None):
        if not path_like: return
        try: path = Path(path_like)
        except TypeError: return
        normalized = str(path).lower()
        if normalized in seen: return
        seen.add(normalized)
        candidates.append(path)

    configured = str(raw_path or "").strip()
    if configured:
        add_candidate(configured)
    elif include_fallback:
        add_candidate(str(getattr(settings.config, "ripgrep_path", "") or "").strip())
    if include_fallback:
        add_candidate(RIPGREP_TOOL_DIR)
        add_candidate(shutil.which("rg.exe") or shutil.which("rg"))

    resolved_files: list[Path] = []
    resolved_seen: set[str] = set()
    for candidate in candidates:
        if candidate.is_file():
            if candidate.name.lower() in RIPGREP_EXECUTABLE_NAMES and candidate.exists():
                normalized = str(candidate.resolve()).lower()
                if normalized not in resolved_seen:
                    resolved_seen.add(normalized)
                    resolved_files.append(candidate.resolve())
            continue

        if not candidate.exists() or not candidate.is_dir():
            continue

        for executable_name in RIPGREP_EXECUTABLE_NAMES:
            direct_path = candidate / executable_name
            if direct_path.exists():
                normalized = str(direct_path.resolve()).lower()
                if normalized not in resolved_seen:
                    resolved_seen.add(normalized)
                    resolved_files.append(direct_path.resolve())

        # ripgrep Release 压缩包自带一层版本目录，因此这里允许递归查找一次工具目录。
        nested_candidates = []
        for executable_name in RIPGREP_EXECUTABLE_NAMES:
            nested_candidates.extend(candidate.rglob(executable_name))
        for nested_path in sorted(nested_candidates, key=lambda item: str(item).lower()):
            if not nested_path.is_file():
                continue
            normalized = str(nested_path.resolve()).lower()
            if normalized in resolved_seen:
                continue
            resolved_seen.add(normalized)
            resolved_files.append(nested_path.resolve())

    if not resolved_files: return None, ""

    runnable_candidates: list[tuple[tuple[int, ...], int, Path, str]] = []
    for path in resolved_files:
        version = probe_ripgrep_version(path)
        if not version:
            continue
        runnable_candidates.append((
            _version_key(version),
            int(path.stat().st_mtime_ns) if path.exists() else 0,
            path,
            version,
        ))

    if runnable_candidates:
        _, _, executable, version = max(
            runnable_candidates,
            key=lambda item: (item[0], item[1], -len(str(item[2]))),
        )
        return executable, version
    return None, ""


def probe_ripgrep_version(executable: str | Path | None) -> str:
    if not executable: return ""
    creationflags = 0
    startupinfo = None
    if platform.system() == "Windows" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    except Exception: return ""

    first_line = str(result.stdout or "").splitlines()[0] if result.stdout else ""
    match = RIPGREP_VERSION_PATTERN.search(first_line.strip())
    return match.group(1) if match else ""


def _version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version or "").split(".") if part.strip())
    except ValueError:
        return (0,)


def get_ripgrep_status(raw_path: str | None = None, *, strict: bool = False) -> RipgrepStatus:
    executable, version = resolve_ripgrep_executable_with_version(raw_path, include_fallback=not strict)
    if not executable:
        return RipgrepStatus(
            available=False,
            resolved_path="",
            current_version="",
            message=tr("text_search.ripgrep.status_missing", "未找到 ripgrep，可在外部工具检查中下载安装。"),
        )

    found_message = (
        tr("text_search.ripgrep.status_found_with_version", "已找到 ripgrep v{version}", version=version)
        if version
        else tr("text_search.ripgrep.status_found", "已找到 ripgrep")
    )
    return RipgrepStatus(
        available=True,
        resolved_path=str(executable),
        current_version=version,
        message=found_message,
    )


def prepare_ripgrep_download(download_mgr, raw_path: str | None = None, *, force: bool = False) -> dict[str, bool]:
    asset_suffix = get_ripgrep_asset_suffix()
    if not asset_suffix:
        raise RuntimeError(tr("text_search.ripgrep.download_unsupported", "当前平台暂不支持自动下载 ripgrep。"))

    status = get_ripgrep_status(raw_path)
    # 普通安装只补缺失；维护检查判定为 outdated 时会传 force=True，复用同一套下载/覆盖流程升级。
    if status.available and not force: return {"already_ready": True}

    install_dir = resolve_ripgrep_root(raw_path)
    install_dir.mkdir(parents=True, exist_ok=True)
    GithubManager().install_from_github(
        download_mgr,
        GithubInstallRequest(
            repo_url="https://github.com/BurntSushi/ripgrep",
            owner="BurntSushi",
            repo="ripgrep",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                asset_name_prefix=RIPGREP_ASSET_PREFIX,
                asset_name_suffix=asset_suffix,
            ),
            install=GithubInstallPlan(
                # Release 压缩包外层自带版本目录，这里改成“解压后整体搬运并重命名”，
                # 目标目录稳定保持为 tools/ripgrep，后续更新可以直接覆盖升级。
                action=GITHUB_INSTALL_EXTRACT_THEN_MOVE,
                download_dir=str(install_dir),
                move_target_dir=str(install_dir.parent),
                final_name=install_dir.name,
                overwrite_existing=True,
                cleanup_archive=True,
            ),
            download_start_message=tr("text_search.ripgrep.download_start", "开始下载 ripgrep 工具包"),
            install_start_message=tr("text_search.ripgrep.install_start", "ripgrep 工具包获取成功，正在解压..."),
            success_toast=tr("text_search.ripgrep.download_done", "ripgrep 下载完成: {install_dir}", install_dir=str(install_dir)),
            failure_toast=tr("text_search.ripgrep.download_failed", "ripgrep 下载失败"),
        ),
    )
    return {"already_ready": False}
