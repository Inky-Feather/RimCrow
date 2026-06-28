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
from backend.settings import TOOLS_DIR, settings


RIPGREP_TOOL_DIR = TOOLS_DIR / "ripgrep"
RIPGREP_EXECUTABLE_NAMES = ("rg.exe", "rg")
RIPGREP_WINDOWS_ASSET_PREFIX = "ripgrep-"
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


def resolve_ripgrep_root(raw_path: str | None = None) -> Path:
    configured = str(raw_path or "").strip()
    if configured:
        candidate = Path(configured)
        return candidate.parent if candidate.is_file() else candidate
    fallback = str(getattr(settings.config, "ripgrep_path", "") or "").strip()
    if fallback:
        return resolve_ripgrep_root(fallback)
    return RIPGREP_TOOL_DIR


def resolve_ripgrep_executable(raw_path: str | None = None, *, include_fallback: bool = True) -> Path | None:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add_candidate(path_like: str | Path | None):
        if not path_like:
            return
        try:
            path = Path(path_like)
        except TypeError:
            return
        normalized = str(path).lower()
        if normalized in seen:
            return
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
        for nested_path in sorted(candidate.rglob("rg.exe"), key=lambda item: str(item).lower()):
            if not nested_path.is_file():
                continue
            normalized = str(nested_path.resolve()).lower()
            if normalized in resolved_seen:
                continue
            resolved_seen.add(normalized)
            resolved_files.append(nested_path.resolve())

    if not resolved_files:
        return None

    runnable_candidates: list[tuple[tuple[int, ...], int, Path]] = []
    for path in resolved_files:
        version = probe_ripgrep_version(path)
        if not version:
            continue
        runnable_candidates.append((
            _version_key(version),
            int(path.stat().st_mtime_ns) if path.exists() else 0,
            path,
        ))

    if runnable_candidates:
        return max(runnable_candidates, key=lambda item: (item[0], item[1], -len(str(item[2]))))[2]
    return None


def probe_ripgrep_version(executable: str | Path | None) -> str:
    if not executable:
        return ""
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return ""

    first_line = str(result.stdout or "").splitlines()[0] if result.stdout else ""
    match = RIPGREP_VERSION_PATTERN.search(first_line.strip())
    return match.group(1) if match else ""


def _version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version or "").split(".") if part.strip())
    except ValueError:
        return (0,)


def get_ripgrep_status(raw_path: str | None = None, *, strict: bool = False) -> RipgrepStatus:
    executable = resolve_ripgrep_executable(raw_path, include_fallback=not strict)
    if not executable:
        return RipgrepStatus(
            available=False,
            resolved_path="",
            current_version="",
            message="未找到 ripgrep，可在外部工具检查中下载安装。",
        )

    version = probe_ripgrep_version(executable)
    return RipgrepStatus(
        available=True,
        resolved_path=str(executable),
        current_version=version,
        message=f"已找到 ripgrep{f' v{version}' if version else ''}",
    )


def prepare_ripgrep_download(download_mgr, raw_path: str | None = None) -> dict[str, bool]:
    if platform.system() != "Windows":
        raise RuntimeError("当前自动下载 ripgrep 仅支持 Windows 平台。")

    status = get_ripgrep_status(raw_path)
    if status.available:
        return {"already_ready": True}

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
                asset_name_prefix=RIPGREP_WINDOWS_ASSET_PREFIX,
                asset_name_suffix=RIPGREP_WINDOWS_ASSET_SUFFIX,
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
            download_start_message="开始下载 ripgrep 工具包",
            install_start_message="ripgrep 工具包获取成功，正在解压...",
            success_toast=f"ripgrep 下载完成: {install_dir}",
            failure_toast="ripgrep 下载失败",
        ),
    )
    return {"already_ready": False}
