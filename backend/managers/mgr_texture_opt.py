# backend/managers/mgr_texture_opt.py
from __future__ import annotations

import copy
import json
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import uuid
import platform
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from backend.settings import CACHE_DIR, TOOLS_DIR, settings
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger
from backend.utils.tools import current_ms, generate_path_hash

TEXTURE_TASK_TYPE = "texture-opt"
TEXTURE_ANALYSIS_TASK_TYPE = "texture-opt-analyze"
TEXTURE_MANIFEST_VERSION = 2  # 升级清单版本
TEXTURE_SCAN_SCHEMA_VERSION = 2
TEXTURE_TASK_RETENTION_SECONDS = 120
TODDS_WINDOWS_ASSET_PREFIX = "todds_Windows_"
TODDS_FALLBACK_VERSION = "0.4.1"
TODDS_FALLBACK_FILENAME = f"todds_Windows_{TODDS_FALLBACK_VERSION}.zip"
SOURCE_IMAGE_EXTENSIONS = (".png",)

# =========================================================
#  RimWorld 贴图开发规范字典 (核心排雷)
# =========================================================
SPECIAL_SUFFIXES = {
    # 遮罩图必须保留极高的通道精度，绝对不能用 BC1/BC3 压缩，否则游戏内染色会产生严重马赛克。
    "_m": {"action": "skip", "reason": "遮罩图(Mask)需保持原画质，跳过压缩"},
    "_mask": {"action": "skip", "reason": "遮罩图(Mask)需保持原画质，跳过压缩"},
}


class TextureOptError(RuntimeError):
    pass


class TextureOptCancelled(TextureOptError):
    pass


def resolve_texture_tools_path(options: dict[str, Any]) -> Path:
    raw_texture_tools_path = str(options.get("texture_tools_path") or "").strip()
    if raw_texture_tools_path:
        candidate = Path(raw_texture_tools_path)
        return candidate.parent if candidate.suffix.lower() == ".exe" else candidate
    return TOOLS_DIR / "texture_tools"


@dataclass
class TextureTask:
    id: str
    action: str
    mod_paths: list[str]
    options: dict[str, Any]
    status: str = "pending"
    progress: int = 0
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=current_ms)
    updated_at: int = field(default_factory=current_ms)
    summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.id,
            "action": self.action,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "metrics": dict(self.metrics),
            "summary": dict(self.summary),
            "error": self.error,
            "mod_paths": list(self.mod_paths),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class _ToolProcessRunner:
    @staticmethod
    def run_command( command: list[str], cancel_event: threading.Event, timeout_seconds: float | None = None, *, tool_name: str = "todds" ) -> None:
        creationflags = 0
        startupinfo = None
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        log_path: Path | None = None
        process = None
        started_at = time.monotonic()
        was_cancelled = False
        timeout_detail = ""
        try:
            with tempfile.NamedTemporaryFile("w+b", delete=False, suffix=".log") as log_file:
                log_path = Path(log_file.name)
                process = subprocess.Popen(
                    command,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                    startupinfo=startupinfo,
                )

                while True:
                    if cancel_event.is_set():
                        _ToolProcessRunner.terminate_process(process)
                        was_cancelled = True
                        break
                    if process.poll() is not None:
                        break
                    if timeout_seconds and (time.monotonic() - started_at) > float(timeout_seconds):
                        _ToolProcessRunner.terminate_process(process)
                        timeout_detail = "__timeout__"
                        break
                    time.sleep(0.1)
        finally:
            if process and process.poll() is None:
                _ToolProcessRunner.terminate_process(process)

        if not process:
            raise TextureOptError(f"{tool_name} 进程未能启动")

        elapsed = round(time.monotonic() - started_at, 3)
        detail = _ToolProcessRunner.read_process_log(log_path)

        if was_cancelled:
            _ToolProcessRunner.cleanup_log_file(log_path)
            raise TextureOptCancelled("贴图优化任务已取消")

        if timeout_detail:
            preserved_log = _ToolProcessRunner.preserve_process_log(log_path, tool_name)
            raise TextureOptError(
                f"{tool_name} 执行超时（{int(timeout_seconds or 0)}秒）: {detail or '无输出'}"
                + (f" [日志: {preserved_log}]" if preserved_log else "")
            )

        if process.returncode != 0:
            preserved_log = _ToolProcessRunner.preserve_process_log(log_path, tool_name)
            logger.error(
                "TextureOpt %s failed: code=%s elapsed=%ss detail=%s log=%s",
                tool_name,
                process.returncode,
                elapsed,
                detail or "未知错误",
                preserved_log or "",
            )
            raise TextureOptError(
                f"{tool_name} 执行失败: {detail or '未知错误'}"
                + (f" [日志: {preserved_log}]" if preserved_log else "")
            )
        _ToolProcessRunner.cleanup_log_file(log_path)

    @staticmethod
    def terminate_process(process: subprocess.Popen) -> None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        except OSError:
            pass

    @staticmethod
    def read_process_log(log_path: Path | None, limit: int = 2000) -> str:
        if not log_path or not log_path.exists():
            return ""
        try:
            with log_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - max(1, int(limit))), os.SEEK_SET)
                data = handle.read()
        except OSError:
            return ""
        if not data:
            return ""
        return data.decode("utf-8", errors="replace").strip()

    @staticmethod
    def cleanup_log_file(log_path: Path | None) -> None:
        if not log_path:
            return
        try:
            log_path.unlink()
        except OSError:
            pass

    @staticmethod
    def preserve_process_log(log_path: Path | None, tool_name: str) -> str:
        if not log_path or not log_path.exists():
            return ""
        preserved_path = log_path.with_name(f"{tool_name}_{log_path.stem}.log")
        try:
            if preserved_path.exists():
                preserved_path.unlink()
            log_path.replace(preserved_path)
            return str(preserved_path)
        except OSError:
            return str(log_path)


class ToddsEncoder:
    tool_name = "todds"
    OPAQUE_FORMAT = "BC1"
    ALPHA_FORMAT = "BC7"

    def __init__(self, options: dict[str, Any]):
        self.options = options

    def resolve_executable(self) -> Path:
        if platform.system() != "Windows":
            raise TextureOptError("todds 后端当前仅支持 Windows 自动集成。")

        texture_tools_path = resolve_texture_tools_path(self.options)
        candidates = [
            str(self.options.get("todds_path") or "").strip(),
            str(texture_tools_path / "todds.exe"),
            str(TOOLS_DIR / "texture_tools" / "todds.exe"),
            shutil.which("todds.exe") or "",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return Path(candidate)
        raise TextureOptError("未找到 todds.exe。请在贴图优化中心下载 todds。")

    def encode_mod(
        self,
        cancel_event: threading.Event,
        *,
        overwrite_existing: bool | None = None,
        source_paths: list[str],
    ) -> None:
        overwrite_flag = bool(self.options.get("overwrite_existing", False)) if overwrite_existing is None else bool(overwrite_existing)
        scale_factor = float(self.options.get("scale_factor", 1.0) or 1.0)
        max_size = int(self.options.get("max_size", 0) or 0)
        needs_resize = (scale_factor > 0 and abs(scale_factor - 1.0) > 1e-6) or max_size > 0

        command = [
            str(self.resolve_executable()),
            "-f", self.OPAQUE_FORMAT,
            "-af", self.ALPHA_FORMAT,
            "-o" if overwrite_flag else "-on",
            "-vf",
        ]
        if not needs_resize:
            command.append("-fs")
        if not bool(self.options.get("generate_mipmaps", True)):
            command.append("-nm")
        if scale_factor > 0 and abs(scale_factor - 1.0) > 1e-6:
            command.extend(["-sc", str(int(round(scale_factor * 100)))])
        if max_size > 0:
            command.extend(["-ms", str(max_size)])
        timeout_seconds = max(300, int(self.options.get("encode_batch_timeout_seconds", 480) or 480))
        normalized_sources = [str(Path(path)) for path in source_paths if path]
        if not normalized_sources:
            raise TextureOptError("没有可交给 todds 的 PNG 源图")
        file_list = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                delete=False,
                suffix=".txt",
            ) as handle:
                file_list = Path(handle.name)
                for source_path in normalized_sources:
                    handle.write(f"{source_path}\n")
            command.append(str(file_list))
            self._run_todds_command(
                command,
                cancel_event,
                timeout_seconds=timeout_seconds,
            )
        finally:
            if file_list and file_list.exists():
                try:
                    file_list.unlink()
                except OSError:
                    pass

    @staticmethod
    def _run_todds_command(command: list[str], cancel_event: threading.Event, timeout_seconds: float | None = None) -> None:
        _ToolProcessRunner.run_command(
            command,
            cancel_event,
            timeout_seconds=timeout_seconds,
            tool_name="todds",
        )


# =========================================================
#  贴图优化主管理器
# =========================================================

class TextureOptimizationManager:
    def __init__(self):
        self._tasks: dict[str, TextureTask] = {}
        self._analysis_tasks: dict[str, threading.Event] = {}
        self._analysis_started_at: dict[str, int] = {}
        self._scan_cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._manifest_root = Path(CACHE_DIR) / "texture_opt" / "manifests"
        self._manifest_root.mkdir(parents=True, exist_ok=True)

    def start_task(self, mod_paths: list[str], action: str = "optimize", options: dict[str, Any] | None = None) -> dict[str, Any]:
        mod_paths = self._normalize_mod_paths(mod_paths)
        if not mod_paths:
            raise TextureOptError("没有可处理的 Mod 路径")

        merged_options = self._build_options(options)
        task_id = uuid.uuid4().hex
        task = TextureTask(id=task_id, action=action, mod_paths=mod_paths, options=merged_options)
        
        with self._lock:
            self._tasks[task_id] = task

        worker = threading.Thread(
            target=self._run_task, args=(task,), daemon=True, name=f"TextureOpt-{task_id[:8]}"
        )
        worker.start()
        self._emit_progress(task, status="pending", progress=0, message="准备任务...")
        return task.to_payload()

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        task = self._tasks.get(task_id)
        if task:
            task._cancel_event.set()
            if task.status == "pending":
                self._set_task_state(task, status="cancelled", message="贴图优化任务已取消")
            return task.to_payload()

        analysis_event = self._analysis_tasks.get(task_id)
        if analysis_event:
            analysis_event.set()
            return {
                "id": task_id,
                "task_id": task_id,
                "action": "analyze",
                "status": "cancelling",
            }

        raise TextureOptError("未找到对应的贴图优化任务")

    def get_backend_status(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        merged_options = self._build_options(options)
        
        try:
            encoder = ToddsEncoder(merged_options)
            executable = encoder.resolve_executable()
            return {
                "available": True,
                "resolved_path": str(executable),
                "message": "已找到 todds 可执行文件",
            }
        except TextureOptError as exc:
            return {
                "available": False,
                "resolved_path": "",
                "message": str(exc),
            }

    def prepare_tool_download(self, download_mgr, options: dict[str, Any] | None = None) -> dict[str, Any]:
        if platform.system() != "Windows":
            raise TextureOptError("当前自动下载工具链仅支持 Windows 平台。")
            
        merged_options = self._build_options(options)
        status = self.get_backend_status(merged_options)
        if status["available"]:
            return {"already_ready": True}

        from backend.managers.mgr_github import (
            GITHUB_ARTIFACT_RELEASE_ASSET,
            GITHUB_INSTALL_EXTRACT,
            GithubArtifactRequest,
            GithubInstallPlan,
            GithubInstallRequest,
            GithubManager,
        )

        texture_tools_path = resolve_texture_tools_path(merged_options)
        texture_tools_path.mkdir(parents=True, exist_ok=True)
        github = GithubManager()
        github.install_from_github(
            download_mgr,
            GithubInstallRequest(
                owner="todds-encoder",
                repo="todds",
                artifact=GithubArtifactRequest(
                    kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                    asset_name_prefix=TODDS_WINDOWS_ASSET_PREFIX,
                    asset_name_suffix=".zip",
                    fallback_download_url=f"https://github.com/todds-encoder/todds/releases/download/{TODDS_FALLBACK_VERSION}/{TODDS_FALLBACK_FILENAME}",
                    fallback_filename=TODDS_FALLBACK_FILENAME,
                    fallback_version=TODDS_FALLBACK_VERSION,
                    fallback_asset_name=TODDS_FALLBACK_FILENAME,
                ),
                install=GithubInstallPlan(
                    action=GITHUB_INSTALL_EXTRACT,
                    download_dir=str(texture_tools_path),
                    extract_dir=str(texture_tools_path),
                    cleanup_archive=True,
                ),
                download_start_message="开始下载 todds 工具包",
                install_start_message="todds 工具包获取成功，正在解压...",
                success_toast=f"贴图工具下载完成: {texture_tools_path}",
                failure_toast="贴图工具下载失败",
            ),
        )
        return {"already_ready": False}

    def _build_scan_cache_key(self, mod_paths: list[str], options: dict[str, Any]) -> str:
        payload = json.dumps(
            {
                "schema_version": TEXTURE_SCAN_SCHEMA_VERSION,
                "mod_paths": list(mod_paths),
                "signature": self._build_signature(options),
                "skip_small_textures": bool(options.get("skip_small_textures", True)),
                "min_dimension": int(options.get("min_dimension", 64)),
                "overwrite_existing": bool(options.get("overwrite_existing", False)),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return generate_path_hash(payload)

    def _get_cached_scan_snapshot(self, mod_paths: list[str], options: dict[str, Any]) -> dict[str, Any] | None:
        cache_key = self._build_scan_cache_key(mod_paths, options)
        with self._lock:
            snapshot = self._scan_cache.get(cache_key)
        if not snapshot:
            return None
        if not self._is_valid_scan_snapshot(snapshot):
            with self._lock:
                self._scan_cache.pop(cache_key, None)
            return None
        return snapshot

    def _store_scan_snapshot(self, snapshot: dict[str, Any]) -> None:
        cache_key = str(snapshot.get("cache_key") or "")
        if not cache_key:
            return
        with self._lock:
            self._scan_cache[cache_key] = snapshot

    def _invalidate_scan_cache(
        self,
        mod_paths: list[str],
        *,
        keep_cache_key: str | None = None,
    ) -> int:
        target_paths = {os.path.abspath(path).lower() for path in mod_paths if path}
        if not target_paths:
            return 0

        removed = 0
        with self._lock:
            stale_keys: list[str] = []
            for cache_key, snapshot in self._scan_cache.items():
                if keep_cache_key and cache_key == keep_cache_key:
                    continue
                snapshot_paths = {
                    os.path.abspath(str(path)).lower()
                    for path in snapshot.get("mod_paths", [])
                    if path
                }
                if snapshot_paths & target_paths:
                    stale_keys.append(cache_key)
            for cache_key in stale_keys:
                self._scan_cache.pop(cache_key, None)
            removed = len(stale_keys)
        return removed

    def _replace_scan_snapshot(self, snapshot: dict[str, Any]) -> None:
        cache_key = str(snapshot.get("cache_key") or "")
        mod_paths = [str(path) for path in snapshot.get("mod_paths", [])]
        self._invalidate_scan_cache(mod_paths, keep_cache_key=cache_key)
        self._store_scan_snapshot(snapshot)

    def _get_or_build_scan_snapshot(
        self,
        mod_paths: list[str],
        options: dict[str, Any],
        *,
        analysis_task_id: str | None = None,
        task: TextureTask | None = None,
        cancel_event: threading.Event | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        if use_cache:
            cached = self._get_cached_scan_snapshot(mod_paths, options)
            if cached: return cached

        snapshot = self._scan_mods_snapshot(
            mod_paths,
            options,
            analysis_task_id=analysis_task_id,
            task=task,
            cancel_event=cancel_event,
        )
        self._store_scan_snapshot(snapshot)
        return snapshot

    def _scan_mods_snapshot(
        self,
        mod_paths: list[str],
        options: dict[str, Any],
        *,
        analysis_task_id: str | None = None,
        task: TextureTask | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        signature = self._build_signature(options)
        summary = self._create_empty_stat(include_mod_count=True, mod_count=len(mod_paths))
        mod_snapshots: list[dict[str, Any]] = []
        total_mods = max(1, len(mod_paths))
        last_emit_time = 0.0

        for index, mod_path in enumerate(mod_paths, start=1):
            if cancel_event and cancel_event.is_set():
                raise TextureOptCancelled("贴图扫描任务已取消")

            mod_snapshot = self._scan_single_mod_snapshot(mod_path, options)
            mod_snapshots.append(mod_snapshot)
            self._merge_stat(summary, mod_snapshot["stat"])

            now = time.monotonic()
            if now - last_emit_time >= 0.1 or index == total_mods:
                if analysis_task_id:
                    self._emit_analysis_progress(
                        analysis_task_id,
                        status="running",
                        progress=min(99, int((index / total_mods) * 100)),
                        message=f"已扫描 {mod_snapshot['stat']['mod_name']}",
                        processed_mods=index,
                        total_mods=total_mods,
                        summary=summary,
                        current_entry=mod_snapshot["stat"],
                    )
                elif task:
                    self._emit_progress(
                        task,
                        status="running",
                        progress=min(5, max(1, int((index / total_mods) * 5))),
                        message=f"扫描模组 {index}/{total_mods}",
                        metrics={
                            "planned_mods": index,
                            "total_mods": total_mods,
                            "planned_jobs": sum(int(mod["plan"]["actionable_count"]) for mod in mod_snapshots),
                            "summary": copy.deepcopy(summary),
                            "current_entry": copy.deepcopy(mod_snapshot["stat"]),
                        },
                    )
                last_emit_time = now

        mod_stats = [dict(mod["stat"]) for mod in mod_snapshots]
        self._finalize_stat_shares(summary, mod_stats)
        mod_stats.sort(key=lambda item: (-int(item["combined_total_bytes"]), item["mod_name"].lower()))

        stat_by_path = {item["mod_path"]: item for item in mod_stats}
        for mod_snapshot in mod_snapshots:
            next_stat = stat_by_path.get(mod_snapshot["mod_path"], mod_snapshot["stat"])
            mod_snapshot["stat"] = dict(next_stat) if isinstance(next_stat, dict) else {}

        snapshot = {
            "id": uuid.uuid4().hex,
            "schema_version": TEXTURE_SCAN_SCHEMA_VERSION,
            "cache_key": self._build_scan_cache_key(mod_paths, options),
            "signature": signature,
            "generated_at": current_ms(),
            "mod_paths": list(mod_paths),
            "summary": dict(summary),
            "mods": mod_snapshots,
        }
        return snapshot

    def _scan_single_mod_snapshot(self, mod_path: str, options: dict[str, Any]) -> dict[str, Any]:
        manifest = self._load_manifest(mod_path)
        files_manifest = dict(manifest.get("files") or {})
        manifest_preset_signature = str(manifest.get("preset_signature") or "")
        mod_name = Path(mod_path).name
        entries: list[dict[str, Any]] = []
        output_stats = self._collect_output_stats(mod_path)
        associated_outputs: set[str] = set()
        managed_output_rel_paths = {
            str((entry or {}).get("output_rel_path") or "").strip()
            for entry in files_manifest.values()
            if str((entry or {}).get("output_rel_path") or "").strip()
        }
        current_signature = self._build_signature(options)

        for source_path in self._iter_texture_source_images(mod_path):
            source = Path(source_path)
            rel_path = self._to_rel_path(source_path, mod_path)
            output_rel = self._to_rel_path(self._build_output_path(source), mod_path)
            entry = self._build_scan_entry(
                mod_path,
                source_path,
                output_stats,
                options,
                current_signature=current_signature,
                manifest_entry=files_manifest.get(rel_path) or {},
                manifest_preset_signature=manifest_preset_signature,
                is_managed_output=output_rel in managed_output_rel_paths,
            )
            entries.append(entry)
            output_rel = str(entry.get("output_rel_path") or "")
            if output_rel and bool(entry.get("output_exists")):
                associated_outputs.add(output_rel)

        managed_orphan_output_count = 0
        managed_orphan_output_bytes = 0
        external_orphan_output_count = 0
        external_orphan_output_bytes = 0
        for output_rel, output_info in output_stats.items():
            if output_rel in associated_outputs:
                continue
            output_size = int(output_info.get("size", 0))
            if output_rel in managed_output_rel_paths:
                managed_orphan_output_count += 1
                managed_orphan_output_bytes += output_size
            else:
                external_orphan_output_count += 1
                external_orphan_output_bytes += output_size

        stat = self._recompute_mod_stat_from_entries(
            mod_path,
            mod_name,
            entries,
            managed_orphan_output_count=managed_orphan_output_count,
            managed_orphan_output_bytes=managed_orphan_output_bytes,
            external_orphan_output_count=external_orphan_output_count,
            external_orphan_output_bytes=external_orphan_output_bytes,
        )
        plan = self._build_mod_plan(entries)
        return {
            "mod_path": mod_path,
            "mod_name": mod_name,
            "manifest": manifest,
            "entries": entries,
            "managed_orphan_output_count": managed_orphan_output_count,
            "managed_orphan_output_bytes": managed_orphan_output_bytes,
            "external_orphan_output_count": external_orphan_output_count,
            "external_orphan_output_bytes": external_orphan_output_bytes,
            "current_keys": list(plan["current_keys"]),
            "plan": plan,
            "stat": stat,
        }

    def _build_scan_entry(
        self,
        mod_path: str,
        source_path: str,
        output_stats: dict[str, dict[str, Any]],
        options: dict[str, Any],
        *,
        current_signature: str = "",
        manifest_entry: dict[str, Any] | None = None,
        manifest_preset_signature: str = "",
        is_managed_output: bool = False,
    ) -> dict[str, Any]:
        source = Path(source_path)
        rel_path = self._to_rel_path(source_path, mod_path)
        output_path = self._build_output_path(source)
        output_rel = self._to_rel_path(output_path, mod_path)
        output_info = output_stats.get(output_rel) or {}
        output_exists = bool(output_info)
        output_origin_kind = "managed" if output_exists and is_managed_output else "external" if output_exists else "none"
        recorded_signature = str(
            (manifest_entry or {}).get("preset_signature")
            or manifest_preset_signature
            or ""
        )
        base_entry = {
            "mod_path": mod_path,
            "mod_name": Path(mod_path).name,
            "source_path": source_path,
            "rel_path": rel_path,
            "source_readable": False,
            "current_key_included": False,
            "source_size": 0,
            "source_mtime_ns": 0,
            "width": 0,
            "height": 0,
            "has_alpha": False,
            "small_skipped": False,
            "skip_reason": "",
            "blocked": False,
            "engine_unsupported": False,
            "engine_unsupported_reason": "",
            "current_output": False,
            "stale_output": False,
            "missing_output": False,
            "needs_action": False,
            "needs_generate": False,
            "needs_regenerate": False,
            "action_status": "none",
            "processable": False,
            "output_path": output_path,
            "output_rel_path": output_rel,
            "output_exists": output_exists,
            "output_size": int(output_info.get("size", 0)),
            "output_origin_kind": output_origin_kind,
            "current_preset_signature": current_signature,
            "recorded_preset_signature": recorded_signature,
            "signature_status": "missing" if not output_exists else "unknown",
            "source_vram": 0,
            "dds_vram": 0,
        }

        try:
            image_info = self._inspect_source_image(source, precise_alpha=False)
            source_stat = source.stat()
        except Exception as exc:
            try:
                source_stat = source.stat()
            except OSError:
                return base_entry
            return {
                **base_entry,
                "source_size": int(source_stat.st_size),
                "source_mtime_ns": int(source_stat.st_mtime_ns),
                "current_key_included": True,
                "engine_unsupported": True,
                "engine_unsupported_reason": f"PNG 文件无法解析: {exc}",
            }

        w, h = image_info["width"], image_info["height"]
        source_vram = w * h * 4
        suffix_rule = self._check_special_suffix(source.stem)
        small_skipped = self._should_skip_texture(image_info, options)

        has_alpha = bool(image_info["has_alpha"])
        tw, th = self._calculate_target_dimensions(w, h, options)
        vram_multiplier = 1.0 if has_alpha else 0.5
        dds_vram = int(tw * th * vram_multiplier)
        if options.get("generate_mipmaps", True):
            dds_vram = int(dds_vram * 1.333)

        blocked = False
        engine_unsupported = False
        engine_unsupported_reason = ""
        overwrite_existing = bool(options.get("overwrite_existing", False))
        skip_reason = ""
        current_key_included = not small_skipped
        current_output = False
        stale_output = False
        missing_output = False
        action_status = "none"
        signature_status = "missing" if not output_exists else "unknown"

        if suffix_rule and suffix_rule["action"] == "skip":
            skip_reason = suffix_rule["reason"]

        if not small_skipped and not skip_reason:
            engine_unsupported_reason = self._get_todds_unsupported_reason(source, image_info)
            engine_unsupported = bool(engine_unsupported_reason)
        if not small_skipped and not skip_reason and not engine_unsupported:
            output_mtime_ns = int(output_info.get("mtime_ns", 0) or 0)
            if not output_exists:
                missing_output = True
                signature_status = "missing"
            else:
                if output_origin_kind != "managed":
                    signature_status = "unknown"
                elif recorded_signature:
                    signature_status = "matched" if recorded_signature == current_signature else "mismatched"
                else:
                    signature_status = "missing"

                if overwrite_existing:
                    stale_output = True
                elif output_origin_kind == "managed" and signature_status == "mismatched":
                    stale_output = True
                elif output_mtime_ns >= int(source_stat.st_mtime_ns):
                    current_output = True
                else:
                    stale_output = True

        needs_action = (not small_skipped) and (not blocked) and (not skip_reason) and (not engine_unsupported) and (missing_output or stale_output)
        needs_generate = needs_action and missing_output
        needs_regenerate = needs_action and stale_output
        if needs_generate:
            action_status = "generate"
        elif needs_regenerate:
            action_status = "regenerate"
        elif small_skipped:
            action_status = "skip_small"
        elif skip_reason:
            action_status = "skip_mask"
        elif engine_unsupported:
            action_status = "unsupported"
        elif blocked:
            action_status = "blocked"

        return {
            **base_entry,
            "source_readable": True,
            "current_key_included": current_key_included,
            "source_size": int(source_stat.st_size),
            "source_mtime_ns": int(source_stat.st_mtime_ns),
            "width": w,
            "height": h,
            "has_alpha": has_alpha,
            "small_skipped": small_skipped,
            "skip_reason": skip_reason,
            "blocked": blocked,
            "engine_unsupported": engine_unsupported,
            "engine_unsupported_reason": engine_unsupported_reason,
            "current_output": current_output,
            "stale_output": stale_output,
            "missing_output": missing_output,
            "needs_action": needs_action,
            "needs_generate": needs_generate,
            "needs_regenerate": needs_regenerate,
            "action_status": action_status,
            "processable": (not small_skipped) and (not engine_unsupported),
            "output_path": output_path,
            "output_rel_path": output_rel,
            "output_exists": output_exists,
            "output_size": int(output_info.get("size", 0)),
            "output_origin_kind": output_origin_kind,
            "current_preset_signature": current_signature,
            "recorded_preset_signature": recorded_signature,
            "signature_status": signature_status,
            "source_vram": source_vram,
            "dds_vram": source_vram if small_skipped or skip_reason else dds_vram,
        }

    def _collect_output_stats(self, mod_path: str) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        for output_path in self._iter_texture_output_paths(mod_path):
            try:
                output_stat = output_path.stat()
            except OSError:
                continue
            stats[self._to_rel_path(str(output_path), mod_path)] = {
                "path": str(output_path),
                "size": int(output_stat.st_size),
                "mtime_ns": int(output_stat.st_mtime_ns),
            }
        return stats

    def _recompute_mod_stat_from_entries(
        self,
        mod_path: str,
        mod_name: str,
        entries: list[dict[str, Any]],
        *,
        managed_orphan_output_count: int,
        managed_orphan_output_bytes: int,
        external_orphan_output_count: int,
        external_orphan_output_bytes: int,
    ) -> dict[str, Any]:
        stat = self._create_empty_stat(mod_path=mod_path, mod_name=mod_name)
        stat["output_total_count"] += int(managed_orphan_output_count) + int(external_orphan_output_count)
        stat["output_total_bytes"] += int(managed_orphan_output_bytes) + int(external_orphan_output_bytes)
        stat["managed_output_count"] += int(managed_orphan_output_count)
        stat["managed_output_bytes"] += int(managed_orphan_output_bytes)
        stat["external_output_count"] += int(external_orphan_output_count)
        stat["external_output_bytes"] += int(external_orphan_output_bytes)
        stat["orphan_output_count"] += int(managed_orphan_output_count) + int(external_orphan_output_count)
        stat["orphan_output_bytes"] += int(managed_orphan_output_bytes) + int(external_orphan_output_bytes)
        stat["managed_orphan_output_count"] += int(managed_orphan_output_count)
        stat["managed_orphan_output_bytes"] += int(managed_orphan_output_bytes)
        stat["external_orphan_output_count"] += int(external_orphan_output_count)
        stat["external_orphan_output_bytes"] += int(external_orphan_output_bytes)
        stat["engine_unsupported_preview"] = []
        for entry in entries:
            if not bool(entry.get("source_readable")):
                stat["unreadable_source_count"] += 1
                continue

            source_size = int(entry.get("source_size", 0))
            source_vram = int(entry.get("source_vram", 0))
            dds_vram = int(entry.get("dds_vram", 0))
            stat["source_total_count"] += 1
            stat["source_total_bytes"] += source_size
            stat["source_vram_bytes_est"] += source_vram
            stat["output_vram_bytes_est"] += dds_vram

            if bool(entry.get("output_exists")):
                output_size = int(entry.get("output_size", 0))
                stat["output_total_count"] += 1
                stat["output_total_bytes"] += output_size
                if str(entry.get("output_origin_kind") or "") == "managed":
                    stat["managed_output_count"] += 1
                    stat["managed_output_bytes"] += output_size
                else:
                    stat["external_output_count"] += 1
                    stat["external_output_bytes"] += output_size

            if bool(entry.get("small_skipped")):
                stat["skip_small_count"] += 1
                continue

            if bool(entry.get("engine_unsupported")):
                stat["unsupported_source_count"] += 1
                if len(stat["engine_unsupported_preview"]) < 8:
                    preview_item = {
                        "rel_path": str(entry.get("rel_path") or ""),
                        "reason": str(entry.get("engine_unsupported_reason") or ""),
                    }
                    stat["engine_unsupported_preview"].append(preview_item)
                continue

            if str(entry.get("skip_reason") or ""):
                stat["skip_mask_count"] += 1
                continue
            if bool(entry.get("blocked")):
                stat["blocked_source_count"] += 1
                continue
            if bool(entry.get("current_output")):
                output_size = int(entry.get("output_size", 0))
                stat["current_output_count"] += 1
                stat["current_output_bytes"] += output_size
                continue
            if bool(entry.get("stale_output")):
                stat["stale_output_count"] += 1
                stat["stale_output_bytes"] += int(entry.get("output_size", 0))
                stat["regenerate_required_count"] += 1
                stat["action_required_count"] += 1
                continue
            if bool(entry.get("missing_output")):
                stat["missing_output_count"] += 1
                stat["generate_required_count"] += 1
                stat["action_required_count"] += 1

        stat["combined_total_bytes"] = int(stat["source_total_bytes"]) + int(stat["output_total_bytes"])
        stat["vram_saving_bytes_est"] = int(stat["source_vram_bytes_est"]) - int(stat["output_vram_bytes_est"])
        return stat

    def _recompute_snapshot_summary(self, snapshot: dict[str, Any]) -> None:
        summary = self._create_empty_stat(include_mod_count=True, mod_count=len(snapshot.get("mods", [])))
        summary_preview: list[dict[str, str]] = []
        for mod_snapshot in snapshot.get("mods", []):
            mod_snapshot["stat"] = self._recompute_mod_stat_from_entries(
                mod_snapshot["mod_path"],
                mod_snapshot["mod_name"],
                mod_snapshot["entries"],
                managed_orphan_output_count=int(mod_snapshot.get("managed_orphan_output_count", 0)),
                managed_orphan_output_bytes=int(mod_snapshot.get("managed_orphan_output_bytes", 0)),
                external_orphan_output_count=int(mod_snapshot.get("external_orphan_output_count", 0)),
                external_orphan_output_bytes=int(mod_snapshot.get("external_orphan_output_bytes", 0)),
            )
            mod_snapshot["plan"] = self._build_mod_plan(mod_snapshot["entries"])
            mod_snapshot["current_keys"] = list(mod_snapshot["plan"]["current_keys"])
            self._merge_stat(summary, mod_snapshot["stat"])
            for item in mod_snapshot["stat"].get("engine_unsupported_preview", []):
                if len(summary_preview) >= 12:
                    break
                summary_preview.append({
                    "mod_name": str(mod_snapshot["mod_name"]),
                    "rel_path": str(item.get("rel_path") or ""),
                    "reason": str(item.get("reason") or ""),
                })

        mod_stats = [dict(mod["stat"]) for mod in snapshot.get("mods", [])]
        self._finalize_stat_shares(summary, mod_stats)
        summary["engine_unsupported_preview"] = summary_preview
        mod_stats.sort(key=lambda item: (-int(item["combined_total_bytes"]), item["mod_name"].lower()))
        stat_by_path = {item["mod_path"]: item for item in mod_stats}
        for mod_snapshot in snapshot.get("mods", []):
            next_stat = stat_by_path.get(mod_snapshot["mod_path"], mod_snapshot["stat"])
            mod_snapshot["stat"] = dict(next_stat) if isinstance(next_stat, dict) else {}
        snapshot["summary"] = dict(summary)

    @staticmethod
    def _build_mod_plan(entries: list[dict[str, Any]]) -> dict[str, Any]:
        current_keys: list[str] = []
        skipped_rel_paths: list[str] = []
        encode_source_paths: list[str] = []
        plan = {
            "source_count": len(entries),
            "pending_count": 0,
            "up_to_date_count": 0,
            "skipped_small_count": 0,
            "skipped_mask_count": 0,
            "unsupported_count": 0,
            "actionable_count": 0,
            "blocked_count": 0,
            "current_keys": [],
            "skipped_rel_paths": [],
            "encode_source_paths": [],
        }
        for entry in entries:
            rel_path = str(entry.get("rel_path") or "")
            if bool(entry.get("current_key_included")) and rel_path:
                current_keys.append(rel_path)
            if bool(entry.get("small_skipped")):
                plan["skipped_small_count"] += 1
                if rel_path:
                    skipped_rel_paths.append(rel_path)
                continue
            if str(entry.get("skip_reason") or ""):
                plan["skipped_mask_count"] += 1
                if rel_path:
                    skipped_rel_paths.append(rel_path)
                continue
            if bool(entry.get("engine_unsupported")):
                plan["unsupported_count"] += 1
                continue
            if bool(entry.get("blocked")):
                plan["blocked_count"] += 1
                continue
            if bool(entry.get("current_output")):
                plan["up_to_date_count"] += 1
                continue
            if bool(entry.get("needs_action")):
                plan["actionable_count"] += 1
            if bool(entry.get("needs_generate")) or bool(entry.get("needs_regenerate")):
                plan["pending_count"] += 1
                source_path = str(entry.get("source_path") or "")
                if source_path:
                    encode_source_paths.append(source_path)
        plan["current_keys"] = current_keys
        plan["skipped_rel_paths"] = skipped_rel_paths
        plan["encode_source_paths"] = encode_source_paths
        return plan

    def _refresh_snapshot_summary_if_due(
        self,
        snapshot: dict[str, Any],
        last_refresh_at: float,
        *,
        force: bool = False,
        min_interval_seconds: float = 0.35,
    ) -> tuple[float, bool]:
        now = time.monotonic()
        if force or (now - last_refresh_at) >= min_interval_seconds:
            self._recompute_snapshot_summary(snapshot)
            return now, True
        return last_refresh_at, False

    def _get_sorted_mod_stats(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [dict(mod["stat"]) for mod in snapshot.get("mods", [])]
        rows.sort(key=lambda item: (-int(item["combined_total_bytes"]), item["mod_name"].lower()))
        return rows

    def analyze_mods(
        self,
        mod_paths: list[str],
        options: dict[str, Any] | None = None,
        task_id: str | None = None,
        cancel_event: threading.Event | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        mod_paths = self._normalize_mod_paths(mod_paths)
        if not mod_paths: raise TextureOptError("没有可分析的 Mod 路径")

        analysis_task_id = task_id or uuid.uuid4().hex
        merged_options = self._build_options(options)
        tool_status = self.get_backend_status(merged_options)

        self._emit_analysis_progress(
            analysis_task_id, status="running", progress=0,
            message="正在智能分析贴图与测算显存...", processed_mods=0, total_mods=len(mod_paths), summary=self._create_empty_stat(include_mod_count=True, mod_count=len(mod_paths))
        )

        try:
            snapshot = self._get_or_build_scan_snapshot(
                mod_paths,
                merged_options,
                analysis_task_id=analysis_task_id,
                cancel_event=cancel_event,
                use_cache=use_cache,
            )
            summary = copy.deepcopy(snapshot["summary"])
            mod_stats = self._get_sorted_mod_stats(snapshot)
            elapsed_ms = max(0, current_ms() - int(self._analysis_started_at.get(analysis_task_id, current_ms())))
            self._emit_analysis_progress(
                analysis_task_id, status="success", progress=100,
                message=f"统计完成，用时 {self._format_elapsed_ms(elapsed_ms)}", processed_mods=len(mod_paths),
                total_mods=len(mod_paths), summary=summary, final_mods=mod_stats
            )

        except TextureOptCancelled as exc:
            self._emit_analysis_progress(
                analysis_task_id, status="cancelled", progress=0, message=str(exc),
                processed_mods=0, total_mods=len(mod_paths), summary=self._create_empty_stat(include_mod_count=True, mod_count=len(mod_paths))
            )
            raise
        except Exception as exc:
            self._emit_analysis_progress(
                analysis_task_id, status="failed", progress=0, message=f"分析失败: {exc}",
                processed_mods=0, total_mods=len(mod_paths), summary=self._create_empty_stat(include_mod_count=True, mod_count=len(mod_paths))
            )
            raise

        return {
            "task_id": analysis_task_id,
            "tool_status": tool_status,
            "summary": summary,
            "mods": mod_stats,
            "options": merged_options,
            "generated_at": current_ms(),
        }

    def _emit_analysis_progress(
        self, task_id: str, *, status: str, progress: int, message: str, 
        processed_mods: int, total_mods: int, summary: dict[str, Any], 
        current_entry: dict[str, Any] | None = None,
        final_mods: list[dict[str, Any]] | None = None
    ) -> None:
        started_at = int(self._analysis_started_at.get(task_id, current_ms()))
        updated_at = current_ms()
        metrics = {
            "processed_mods": processed_mods, "total_mods": total_mods,
            "summary": {key: value for key, value in summary.items()},
            "task_created_at": started_at,
            "task_updated_at": updated_at,
            "task_status": status,
        }
        if status in {"success", "failed", "cancelled"}:
            metrics["elapsed_ms"] = max(0, updated_at - started_at)
        if current_entry:
            # 【核心修复】传输字典全貌，而不是只传 mod_name
            metrics["current_entry"] = current_entry
        if final_mods is not None:
            # 传输最终排序好的列表
            metrics["final_mods"] = final_mods

        EventBus.emit_progress(task_id, TEXTURE_ANALYSIS_TASK_TYPE, status=status, progress=progress, message=message, metrics=metrics)

    # =========================================================
    #  核心处理逻辑
    # =========================================================

    def _run_task(self, task: TextureTask) -> None:
        try:
            self._set_task_state(task, status="running", message="正在执行贴图队列...")
            if task.action == "clean_generated":
                summary = self._clean_generated(task)
            else:
                summary = self._optimize(task)

            success_message = str(summary.pop("message", "贴图优化任务完成"))
            final_summary = summary.pop("final_summary", None)
            final_mods = summary.pop("final_mods", None)
            refresh_after_analyze = bool(summary.pop("refresh_after_analyze", True))
            elapsed_ms = max(0, current_ms() - int(task.created_at))
            metrics = self._build_metrics(summary)
            if isinstance(final_summary, dict):
                metrics["summary"] = final_summary
            if isinstance(final_mods, list):
                metrics["final_mods"] = final_mods
            metrics["refresh_after_analyze"] = refresh_after_analyze
            metrics["elapsed_ms"] = elapsed_ms
            self._set_task_state(
                task,
                status="success",
                progress=100,
                message=f"{success_message}，用时 {self._format_elapsed_ms(elapsed_ms)}",
                summary=summary,
                metrics=metrics,
            )
        except TextureOptCancelled as exc:
            logger.warning("TextureOpt task cancelled: id=%s action=%s", task.id, task.action)
            self._set_task_state(task, status="cancelled", message=str(exc), error="")
        except Exception as exc:
            logger.error("Texture optimization task failed", exc_info=True)
            self._set_task_state(task, status="failed", message="贴图优化失败", error=str(exc))

    def _optimize(self, task: TextureTask) -> dict[str, Any]:
        return self._optimize_todds_fast(task, ToddsEncoder(task.options))

    def _optimize_todds_fast(self, task: TextureTask, encoder: ToddsEncoder) -> dict[str, Any]:
        signature = self._build_signature(task.options)
        total_mods = max(1, len(task.mod_paths))
        optimized = 0
        orphan_deleted = 0
        skipped = 0
        failed = 0
        final_summary = self._create_empty_stat(include_mod_count=True, mod_count=len(task.mod_paths))
        mod_snapshots: list[dict[str, Any]] = []
        cached_snapshot = self._get_cached_scan_snapshot(task.mod_paths, task.options)

        initial_summary = copy.deepcopy(cached_snapshot["summary"]) if cached_snapshot else copy.deepcopy(final_summary)
        initial_rows = self._get_sorted_mod_stats(cached_snapshot) if cached_snapshot else []
        self._emit_progress(
            task,
            status="running",
            progress=1,
            message="开始生成 DDS",
            metrics={
                "done": 0,
                "total": len(task.mod_paths),
                "optimized": 0,
                "skipped": 0,
                "failed": 0,
                "summary": initial_summary,
                "final_mods": initial_rows,
                "refresh_after_analyze": False,
            },
        )

        for index, mod_path in enumerate(task.mod_paths, start=1):
            if task._cancel_event.is_set():
                raise TextureOptCancelled("DDS 生成任务已取消")

            mod_name = Path(mod_path).name
            manifest = self._load_manifest(mod_path)
            signature_mismatch = str(manifest.get("preset_signature") or "") != signature
            force_overwrite = bool(task.options.get("overwrite_existing", False)) or signature_mismatch
            plan_options = dict(task.options)
            plan_options["overwrite_existing"] = force_overwrite
            plan_snapshot = self._scan_single_mod_snapshot(mod_path, plan_options)
            plan = self._build_mod_plan(plan_snapshot["entries"])
            skipped += (
                int(plan["up_to_date_count"])
                + int(plan.get("skipped_small_count", 0))
                + int(plan.get("skipped_mask_count", 0))
                + int(plan.get("unsupported_count", 0))
            )
            self._emit_progress(
                task,
                status="running",
                progress=max(1, self._calc_progress(index - 1, total_mods)),
                message=f"生成 DDS: {mod_name}",
                metrics={
                    "done": index - 1,
                    "total": len(task.mod_paths),
                    "optimized": optimized,
                    "skipped": skipped,
                    "failed": failed,
                    "current_mod_sources": int(plan["source_count"]),
                    "current_mod_pending": int(plan["pending_count"]),
                    "refresh_after_analyze": False,
                },
            )

            files_manifest = dict(manifest.get("files") or {})
            skipped_rel_paths = [str(rel_path) for rel_path in plan.get("skipped_rel_paths", [])]
            for rel_path in skipped_rel_paths:
                entry = files_manifest.get(rel_path) or {}
                if entry:
                    orphan_deleted += self._retire_managed_outputs(
                        mod_path,
                        entry,
                        keep_path=None,
                    )
                    files_manifest.pop(rel_path, None)
            if task.options.get("clean_orphaned_dds", True):
                orphan_deleted += self._cleanup_orphaned_outputs(mod_path, files_manifest, set(plan["current_keys"]))

            encode_source_paths = [str(path) for path in plan.get("encode_source_paths", [])]
            planned_rel_paths = {self._to_rel_path(path, mod_path) for path in encode_source_paths}
            if int(plan["source_count"]) > 0 and int(plan["pending_count"]) > 0 and encode_source_paths:
                encoder.encode_mod(
                    task._cancel_event,
                    overwrite_existing=force_overwrite,
                    source_paths=encode_source_paths,
                )

            mod_snapshot = self._scan_single_mod_snapshot(mod_path, task.options)
            manifest["version"] = TEXTURE_MANIFEST_VERSION
            manifest["preset_signature"] = signature
            manifest["updated_at"] = current_ms()
            manifest["files"] = self._build_manifest_files_from_entries(mod_snapshot.get("entries", []), task.options)
            self._write_manifest(mod_path, manifest)
            mod_snapshot["manifest"] = manifest
            mod_snapshots.append(mod_snapshot)

            completed_rel_paths = {
                str(entry.get("rel_path") or "")
                for entry in mod_snapshot.get("entries", [])
                if str(entry.get("rel_path") or "") in planned_rel_paths and bool(entry.get("current_output"))
            }
            optimized += len(completed_rel_paths)
            failed += max(0, len(planned_rel_paths) - len(completed_rel_paths))
            snapshot = {
                "id": task.id,
                "schema_version": TEXTURE_SCAN_SCHEMA_VERSION,
                "cache_key": self._build_scan_cache_key(task.mod_paths, task.options),
                "signature": signature,
                "generated_at": current_ms(),
                "mod_paths": list(task.mod_paths),
                "summary": {},
                "mods": mod_snapshots,
            }
            self._recompute_snapshot_summary(snapshot)
            final_summary = dict(snapshot["summary"])
            final_rows = self._get_sorted_mod_stats(snapshot)

            self._emit_progress(
                task,
                status="running",
                progress=self._calc_progress(index, total_mods),
                message=f"生成 DDS: {mod_name}",
                metrics={
                    "done": index,
                    "total": len(task.mod_paths),
                    "optimized": optimized,
                    "skipped": skipped,
                    "failed": failed,
                    "summary": final_summary,
                    "current_entry": dict(mod_snapshot["stat"]),
                    "final_mods": final_rows,
                    "refresh_after_analyze": False,
                },
            )

        snapshot = {
            "id": task.id,
            "schema_version": TEXTURE_SCAN_SCHEMA_VERSION,
            "cache_key": self._build_scan_cache_key(task.mod_paths, task.options),
            "signature": signature,
            "generated_at": current_ms(),
            "mod_paths": list(task.mod_paths),
            "summary": final_summary,
            "mods": mod_snapshots,
        }
        self._replace_scan_snapshot(snapshot)
        return {
            "optimized": optimized,
            "skipped": skipped,
            "failed": failed,
            "preexisting_dds": 0,
            "orphan_deleted": orphan_deleted,
            "total_jobs": len(task.mod_paths),
            "final_summary": final_summary,
            "final_mods": self._get_sorted_mod_stats(snapshot),
            "refresh_after_analyze": False,
            "message": "DDS 生成完成",
        }

    def _clean_generated(self, task: TextureTask) -> dict[str, Any]:
        deleted = 0
        checked = 0
        delete_failed = 0
        total_mods = max(1, len(task.mod_paths))
        clean_only = task.options.get("clean_generated_only") or False
        changed_mod_paths: list[str] = []
        for index, mod_path in enumerate(task.mod_paths, start=1):
            if task._cancel_event.is_set():
                raise TextureOptCancelled("清理 DDS 任务已取消")
            manifest = self._load_manifest(mod_path)
            files_manifest = dict(manifest.get("files") or {})
            mod_deleted = 0
            output_paths = (
                self._collect_managed_output_paths(mod_path, files_manifest)
                if clean_only
                else list(self._iter_texture_output_paths_with_source(mod_path))
            )
            total_outputs = max(1, len(output_paths))
            self._emit_progress(
                task,
                status="running",
                progress=max(1, self._calc_progress(index - 1, total_mods)),
                message=f"清理 DDS: {Path(mod_path).name}",
                metrics={
                    "checked_outputs": checked,
                    "orphan_deleted": deleted,
                    "delete_failed": delete_failed,
                    "total_mods": total_mods,
                    "processed_mods": index - 1,
                },
            )
            for output_index, output_path in enumerate(output_paths, start=1):
                if task._cancel_event.is_set():
                    raise TextureOptCancelled("清理 DDS 任务已取消")
                checked += 1
                try:
                    output_path.unlink()
                    deleted += 1
                    mod_deleted += 1
                except OSError as exc:
                    delete_failed += 1
                    logger.warning("Texture clean delete failed: mode=%s path=%s error=%s", clean_only, output_path, exc)
                    continue
                if output_index % 50 == 0 or output_index == total_outputs:
                    self._emit_progress(
                        task,
                        status="running",
                        progress=max(
                            self._calc_progress(index - 1, total_mods),
                            self._calc_progress(int(((index - 1) + (output_index / total_outputs)) * 1000), total_mods * 1000),
                        ),
                        message=f"清理 DDS: {Path(mod_path).name}",
                        metrics={
                            "checked_outputs": checked,
                            "orphan_deleted": deleted,
                            "delete_failed": delete_failed,
                            "total_mods": total_mods,
                            "processed_mods": index,
                        },
                    )

            pruned_count = self._prune_deleted_manifest_entries(mod_path, files_manifest)
            if mod_deleted > 0 or pruned_count > 0:
                changed_mod_paths.append(mod_path)
                manifest["files"] = files_manifest
                manifest["updated_at"] = current_ms()
                self._write_manifest(mod_path, manifest)
        if changed_mod_paths:
            self._invalidate_scan_cache(changed_mod_paths)
        return {
            "optimized": 0,
            "skipped": 0,
            "failed": 0,
            "preexisting_dds": 0,
            "orphan_deleted": deleted,
            "checked_outputs": checked,
            "delete_failed": delete_failed,
            "total_jobs": 0,
            "refresh_after_analyze": bool(changed_mod_paths),
            "message": "DDS 清理完成",
        }

    # =========================================================
    #  工具与辅助函数
    # =========================================================
    @staticmethod
    def _check_special_suffix(stem: str) -> dict | None:
        """检查文件名是否符合特殊的 RimWorld 后缀规范"""
        stem_lower = stem.lower()
        for sfx, rule in SPECIAL_SUFFIXES.items():
            if stem_lower.endswith(sfx):
                return rule
        return None

    @staticmethod
    def _calculate_target_dimensions(w: int, h: int, options: dict) -> tuple[int, int]:
        """计算目标缩放尺寸，确保是 4 的倍数 (BCn 格式规范)"""
        scale_factor = float(options.get("scale_factor", 1.0))
        max_size = int(options.get("max_size", 0))
        
        tw, th = w, h
        if scale_factor > 0 and abs(scale_factor - 1.0) > 1e-6:
            tw, th = int(tw * scale_factor), int(th * scale_factor)
            
        if max_size > 0:
            if tw > max_size or th > max_size:
                ratio = max_size / max(tw, th)
                tw, th = int(tw * ratio), int(th * ratio)
                
        def _align_to_4(val: int) -> int:
            return max(4, (val // 4) * 4)
            
        return _align_to_4(tw), _align_to_4(th)

    def _build_manifest_files_from_entries(
        self,
        entries: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        files_manifest: dict[str, Any] = {}
        signature = self._build_signature(options)
        for entry in entries:
            if not bool(entry.get("source_readable")) or not bool(entry.get("output_exists")):
                continue
            rel_path = str(entry.get("rel_path") or "")
            output_rel_path = str(entry.get("output_rel_path") or "")
            if not rel_path or not output_rel_path:
                continue
            files_manifest[rel_path] = {
                "output_rel_path": output_rel_path,
                "source_size": int(entry.get("source_size", 0)),
                "source_mtime_ns": int(entry.get("source_mtime_ns", 0)),
                "output_size": int(entry.get("output_size", 0)),
                "preset_signature": signature,
            }
        return files_manifest

    def _cleanup_orphaned_outputs(self, mod_path: str, files_manifest: dict[str, Any], current_keys: set[str]) -> int:
        deleted = 0
        stale_keys = [key for key in files_manifest.keys() if key not in current_keys]
        for rel_path in stale_keys:
            entry = files_manifest.get(rel_path) or {}
            output_rel = str(entry.get("output_rel_path") or "")
            if output_rel:
                output_path = Path(mod_path) / output_rel
                if output_path.exists():
                    output_path.unlink()
                    deleted += 1
            files_manifest.pop(rel_path, None)
        return deleted

    def _collect_managed_output_paths(self, mod_path: str, files_manifest: dict[str, Any]) -> list[Path]:
        outputs: list[Path] = []
        seen: set[Path] = set()
        for entry in files_manifest.values():
            output_rel = str((entry or {}).get("output_rel_path") or "").strip()
            if not output_rel:
                continue
            output_path = (Path(mod_path) / output_rel).resolve()
            if output_path in seen or not output_path.exists():
                continue
            seen.add(output_path)
            outputs.append(output_path)
        return outputs

    def _iter_texture_output_paths_with_source(self, mod_path: str):
        for output_path in self._iter_texture_output_paths(mod_path):
            source_path = self._resolve_output_source(output_path)
            if source_path.exists():
                yield output_path

    def _prune_deleted_manifest_entries(self, mod_path: str, files_manifest: dict[str, Any]) -> int:
        stale_keys: list[str] = []
        for rel_path, entry in files_manifest.items():
            output_rel = str((entry or {}).get("output_rel_path") or "").strip()
            if not output_rel:
                stale_keys.append(rel_path)
                continue
            if not (Path(mod_path) / output_rel).exists():
                stale_keys.append(rel_path)
        for rel_path in stale_keys:
            files_manifest.pop(rel_path, None)
        return len(stale_keys)

    def _retire_managed_outputs(self, mod_path: str, entry: dict[str, Any], keep_path: str | None) -> int:
        deleted = 0
        candidates: set[Path] = set()
        output_rel = str(entry.get("output_rel_path") or "").strip()
        if output_rel:
            candidates.add(Path(mod_path) / output_rel)

        keep_resolved = Path(keep_path).resolve() if keep_path else None
        for candidate in candidates:
            try:
                if keep_resolved and candidate.resolve() == keep_resolved:
                    continue
            except OSError:
                pass
            if not candidate.exists():
                continue
            try:
                candidate.unlink()
                deleted += 1
            except OSError:
                continue
        return deleted

    def register_analysis_task(self, task_id: str) -> threading.Event:
        cancel_event = threading.Event()
        with self._lock:
            self._analysis_tasks[task_id] = cancel_event
            self._analysis_started_at[task_id] = current_ms()
        return cancel_event

    def finish_analysis_task(self, task_id: str) -> None:
        with self._lock:
            self._analysis_tasks.pop(task_id, None)
            self._analysis_started_at.pop(task_id, None)

    @staticmethod
    def _iter_texture_root_dirs(mod_path: str):
        mod_root = Path(mod_path)
        if not mod_root.exists():
            return
        for current_root, dirs, _files in os.walk(mod_root):
            current_path = Path(current_root)
            if current_path.name.lower() == "textures":
                yield current_path
                dirs[:] = []

    @staticmethod
    def _inspect_source_image(path: Path, *, precise_alpha: bool = True) -> dict[str, Any]:
        """读取图片尺寸，并按需要精确或快速判断透明通道。"""
        try:
            with Image.open(path) as image:
                width, height = image.size
                image_format = str(image.format or "").upper()
                has_alpha = False
                if image.mode in {"RGBA", "LA"}:
                    if precise_alpha:
                        alpha = image.getchannel("A")
                        extrema = alpha.getextrema()
                        first_extrema = extrema[0] if isinstance(extrema, tuple) and extrema else None
                        has_alpha = isinstance(first_extrema, (int, float)) and first_extrema < 255
                    else:
                        has_alpha = True
                elif image.mode == "P":
                    has_alpha = "transparency" in image.info
                return {
                    "width": width,
                    "height": height,
                    "has_alpha": has_alpha,
                    "image_format": image_format,
                }
        except Exception:
            if path.suffix.lower() == ".png":
                fallback = TextureOptimizationManager._inspect_png_header(path)
                if fallback is not None:
                    return fallback
            raise

    @staticmethod
    def _inspect_png_header(path: Path) -> dict[str, Any] | None:
        try:
            with path.open("rb") as handle:
                signature = handle.read(8)
                if signature != b"\x89PNG\r\n\x1a\n":
                    return None

                has_trns = False
                width = 0
                height = 0
                color_type = None
                while True:
                    length_bytes = handle.read(4)
                    if len(length_bytes) < 4:
                        return None
                    chunk_length = struct.unpack(">I", length_bytes)[0]
                    chunk_type = handle.read(4)
                    if len(chunk_type) < 4:
                        return None
                    chunk_data = handle.read(chunk_length)
                    if len(chunk_data) < chunk_length:
                        return None
                    crc = handle.read(4)
                    if len(crc) < 4:
                        return None

                    if chunk_type == b"IHDR":
                        if len(chunk_data) < 13:
                            return None
                        width = struct.unpack(">I", chunk_data[0:4])[0]
                        height = struct.unpack(">I", chunk_data[4:8])[0]
                        color_type = chunk_data[9]

                    if chunk_type == b"tRNS":
                        has_trns = True
                    if chunk_type == b"IDAT":
                        if not width or not height or color_type is None:
                            return None
                        has_alpha = color_type in {4, 6} or has_trns
                        return {
                            "width": width,
                            "height": height,
                            "has_alpha": has_alpha,
                            "image_format": "PNG",
                        }
                    if chunk_type == b"IEND":
                        return None
        except OSError:
            return None

    @staticmethod
    def _should_skip_texture(image_info: dict[str, Any], options: dict[str, Any]) -> bool:
        if not options.get("skip_small_textures", True): return False
        min_dimension = max(1, int(options.get("min_dimension", 64))) # 默认 64x64 以下忽略
        return image_info["width"] < min_dimension or image_info["height"] < min_dimension

    @staticmethod
    def _get_todds_unsupported_reason(source: Path, image_info: dict[str, Any] | None) -> str:
        image_format = str((image_info or {}).get("image_format") or "").upper()
        if image_format == "PNG":
            return ""
        if source.suffix.lower() == ".png":
            return "文件扩展名为 PNG，但实际内容不是 PNG"
        return ""

    @staticmethod
    def _iter_texture_source_images(mod_path: str):
        for texture_root in TextureOptimizationManager._iter_texture_root_dirs(mod_path):
            for current_root, _dirs, files in os.walk(texture_root):
                for name in files:
                    if Path(name).suffix.lower() in SOURCE_IMAGE_EXTENSIONS:
                        yield str(Path(current_root) / name)

    @staticmethod
    def _iter_texture_output_paths(mod_path: str):
        for texture_root in TextureOptimizationManager._iter_texture_root_dirs(mod_path):
            for current_root, _dirs, files in os.walk(texture_root):
                for name in files:
                    path = Path(current_root) / name
                    name_lower = name.lower()
                    if path.suffix.lower() == ".dds" or name_lower.endswith(".dds.zstd"):
                        yield path

    @staticmethod
    def _to_rel_path(path: str, root: str) -> str:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()

    def _load_manifest(self, mod_path: str) -> dict[str, Any]:
        path = self._manifest_path(mod_path)
        if not path.exists(): return {"version": TEXTURE_MANIFEST_VERSION, "files": {}}
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception: return {"version": TEXTURE_MANIFEST_VERSION, "files": {}}

    def _write_manifest(self, mod_path: str, data: dict[str, Any]) -> None:
        path = self._manifest_path(mod_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _manifest_path(self, mod_path: str) -> Path:
        return self._manifest_root / f"{generate_path_hash(mod_path)}.json"

    @staticmethod
    def _build_signature(options: dict[str, Any]) -> str:
        relevant = {
            "generate_mipmaps": bool(options.get("generate_mipmaps", True)),
            "scale_factor": float(options.get("scale_factor", 1.0)),
            "max_size": int(options.get("max_size", 0)),
            "skip_small_textures": bool(options.get("skip_small_textures", True)),
            "min_dimension": int(options.get("min_dimension", 64)),
        }
        return json.dumps(relevant, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _build_output_path(source: Path) -> str:
        return str(source.with_suffix(".dds"))

    @staticmethod
    def _resolve_output_source(path: Path) -> Path:
        name_lower = path.name.lower()
        if name_lower.endswith(".dds.zstd"):
            stem = path.name[:-9]
        elif path.suffix.lower() == ".dds":
            stem = path.stem
        else:
            return path

        for ext in SOURCE_IMAGE_EXTENSIONS:
            candidate = path.with_name(stem + ext)
            if candidate.exists():
                return candidate
        return path.with_name(stem + SOURCE_IMAGE_EXTENSIONS[0])

    @staticmethod
    def _normalize_mod_paths(mod_paths: list[str]) -> list[str]:
        normalized =[]
        seen = set()
        for path in mod_paths:
            if not path: continue
            abs_path = os.path.abspath(path)
            lower = abs_path.lower()
            if lower in seen or not os.path.isdir(abs_path): continue
            seen.add(lower)
            normalized.append(abs_path)
        return normalized

    @staticmethod
    def _build_options(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        texture_opt = getattr(settings.config, "texture_opt", {})
        if is_dataclass(texture_opt) and not isinstance(texture_opt, type): base = asdict(texture_opt)
        elif isinstance(texture_opt, dict): base = dict(texture_opt)
        else: base = {}

        merged = dict(base)
        merged.update(overrides or {})

        # 默认参数兜底
        merged.setdefault("texture_tools_path", "")
        merged.setdefault("generate_mipmaps", True)
        merged.setdefault("scale_factor", 1.0)
        merged.setdefault("max_size", 0)
        merged.setdefault("skip_small_textures", True)
        merged.setdefault("min_dimension", 64)
        merged.setdefault("clean_orphaned_dds", True)
        merged.setdefault("overwrite_existing", False)
        merged.setdefault("encode_batch_timeout_seconds", 480)
        merged.setdefault("clean_generated_only", True)

        clean_generated_only = merged.get("clean_generated_only", True)
        if isinstance(clean_generated_only, str):
            merged["clean_generated_only"] = clean_generated_only.strip().lower() in {"1", "true", "yes", "on"}
        else:
            merged["clean_generated_only"] = bool(clean_generated_only)
        merged["texture_tools_path"] = str(resolve_texture_tools_path(merged))
        return merged

    @staticmethod
    def _calc_progress(current: int, total: int) -> int:
        if total <= 0: return 0
        if current <= 0:
            return 0
        if current >= total:
            return 99
        return min(99, max(1, int((current / total) * 100)))

    @staticmethod
    def _build_metrics(summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "optimized": summary.get("optimized", 0),
            "skipped": summary.get("skipped", 0),
            "failed": summary.get("failed", 0),
            "orphan_deleted": summary.get("orphan_deleted", 0),
            "checked_outputs": summary.get("checked_outputs", 0),
            "delete_failed": summary.get("delete_failed", 0),
            "total_jobs": summary.get("total_jobs", 0),
        }

    @staticmethod
    def _create_empty_stat(*, mod_path: str = "", mod_name: str = "", include_mod_count: bool = False, mod_count: int = 0) -> dict[str, Any]:
        stat = {
            "mod_path": mod_path, "mod_name": mod_name,
            "source_total_count": 0, "source_total_bytes": 0,
            "output_total_count": 0, "output_total_bytes": 0,
            "managed_output_count": 0, "managed_output_bytes": 0,
            "external_output_count": 0, "external_output_bytes": 0,
            "current_output_count": 0, "current_output_bytes": 0,
            "stale_output_count": 0, "stale_output_bytes": 0,
            "missing_output_count": 0,
            "generate_required_count": 0, "regenerate_required_count": 0, "action_required_count": 0,
            "skip_small_count": 0, "skip_mask_count": 0,
            "unsupported_source_count": 0, "unreadable_source_count": 0, "blocked_source_count": 0,
            "orphan_output_count": 0, "orphan_output_bytes": 0,
            "managed_orphan_output_count": 0, "managed_orphan_output_bytes": 0,
            "external_orphan_output_count": 0, "external_orphan_output_bytes": 0,
            "combined_total_bytes": 0,
            "engine_unsupported_preview": [],
            "source_vram_bytes_est": 0, "output_vram_bytes_est": 0, "vram_saving_bytes_est": 0,
            "source_bytes_share_pct": 0.0, "output_bytes_share_pct": 0.0, "combined_bytes_share_pct": 0.0,
        }
        if include_mod_count: 
            stat["mod_count"] = mod_count
        return stat

    @staticmethod
    def _merge_stat(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if key in {"mod_path", "mod_name"}: continue
            if key == "mod_count":
                continue
            if isinstance(value, (int, float)):
                target[key] = int(target.get(key, 0)) + int(value)
        target["combined_total_bytes"] = int(target.get("source_total_bytes", 0)) + int(target.get("output_total_bytes", 0))
        target["vram_saving_bytes_est"] = int(target.get("source_vram_bytes_est", 0)) - int(target.get("output_vram_bytes_est", 0))

    @staticmethod
    def _finalize_stat_shares(summary: dict[str, Any], mod_stats: list[dict[str, Any]]) -> None:
        summary["combined_total_bytes"] = int(summary.get("source_total_bytes", 0)) + int(summary.get("output_total_bytes", 0))
        summary["vram_saving_bytes_est"] = int(summary.get("source_vram_bytes_est", 0)) - int(summary.get("output_vram_bytes_est", 0))
        total_source = max(1, int(summary.get("source_total_bytes", 0)))
        total_output = max(1, int(summary.get("output_total_bytes", 0)))
        total_combined = max(1, int(summary.get("combined_total_bytes", 0)))
        for item in mod_stats:
            item["source_bytes_share_pct"] = round((int(item.get("source_total_bytes", 0)) / total_source) * 100, 2)
            item["output_bytes_share_pct"] = round((int(item.get("output_total_bytes", 0)) / total_output) * 100, 2)
            item["combined_bytes_share_pct"] = round((int(item.get("combined_total_bytes", 0)) / total_combined) * 100, 2)

    def _set_task_state(self, task: TextureTask, *, status: str | None = None, progress: int | None = None, message: str | None = None, metrics: dict[str, Any] | None = None, summary: dict[str, Any] | None = None, error: str | None = None) -> None:
        if summary is not None:
            task.summary = summary
        if error is not None: task.error = error
        final_status = status or task.status
        self._emit_progress(
            task,
            final_status,
            task.progress if progress is None else progress,
            task.message if message is None else message,
            task.metrics if metrics is None else metrics,
        )
        if final_status in {"success", "failed", "cancelled"} and not getattr(task, "_cleanup_scheduled", False):
            setattr(task, "_cleanup_scheduled", True)
            self._schedule_task_cleanup(task.id)

    def _emit_progress(self, task: TextureTask, status: str, progress: int, message: str, metrics: dict[str, Any] | None = None) -> None:
        updated_at = current_ms()
        task.status = status; task.progress = progress; task.message = message; task.metrics = metrics or {}; task.updated_at = updated_at
        task_created_at = int(getattr(task, "created_at", updated_at))
        task.metrics.setdefault("task_created_at", task_created_at)
        task.metrics["task_updated_at"] = updated_at
        task.metrics.setdefault("task_action", str(getattr(task, "action", "")))
        task.metrics["task_status"] = status
        EventBus.emit_progress(task.id, TEXTURE_TASK_TYPE, status=status, progress=progress, message=message, metrics=task.metrics)

    def _schedule_task_cleanup(self, task_id: str, delay_seconds: float = TEXTURE_TASK_RETENTION_SECONDS) -> None:
        def _cleanup() -> None:
            with self._lock:
                self._tasks.pop(task_id, None)

        timer = threading.Timer(delay_seconds, _cleanup)
        timer.daemon = True
        timer.start()

    @staticmethod
    def _is_valid_stat_payload(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        required_keys = {
            "source_total_count",
            "source_total_bytes",
            "output_total_count",
            "output_total_bytes",
            "managed_output_count",
            "current_output_count",
            "generate_required_count",
            "regenerate_required_count",
            "action_required_count",
            "combined_total_bytes",
            "source_vram_bytes_est",
            "output_vram_bytes_est",
        }
        return required_keys.issubset(payload.keys())

    def _is_valid_scan_snapshot(self, snapshot: Any) -> bool:
        if not isinstance(snapshot, dict):
            return False
        if int(snapshot.get("schema_version", 0) or 0) != TEXTURE_SCAN_SCHEMA_VERSION:
            return False
        if not self._is_valid_stat_payload(snapshot.get("summary")):
            return False
        mods = snapshot.get("mods")
        if not isinstance(mods, list):
            return False
        for mod_snapshot in mods:
            if not isinstance(mod_snapshot, dict):
                return False
            if not self._is_valid_stat_payload(mod_snapshot.get("stat")):
                return False
        return True

    @staticmethod
    def _format_elapsed_ms(elapsed_ms: int) -> str:
        total_seconds = max(0, elapsed_ms // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
