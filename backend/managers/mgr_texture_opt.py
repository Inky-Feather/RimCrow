from __future__ import annotations

import concurrent.futures
import os
import platform
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from backend.settings import TOOLS_DIR, settings
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger
from backend.utils.tools import current_ms

TEXTURE_TASK_TYPE = "texture-opt"
TEXTURE_ANALYSIS_TASK_TYPE = "texture-opt-analyze"
TEXTURE_TASK_RETENTION_SECONDS = 120
TODDS_WINDOWS_ASSET_PREFIX = "todds_Windows_"
TODDS_FALLBACK_VERSION = "0.4.1"
TODDS_FALLBACK_FILENAME = f"todds_Windows_{TODDS_FALLBACK_VERSION}.zip"
SOURCE_IMAGE_EXTENSIONS = (".png",)
SCALE_STEP_SEQUENCE = (20, 25, 40, 50, 60, 75, 80)
SCALE_STEP_RATIONALS = {
    20: (1, 5),
    25: (1, 4),
    40: (2, 5),
    50: (1, 2),
    60: (3, 5),
    75: (3, 4),
    80: (4, 5),
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
    def run_command(
        command: list[str],
        cancel_event: threading.Event,
        timeout_seconds: float | None = None,
        *,
        tool_name: str = "todds",
    ) -> None:
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
        return data.decode("utf-8", errors="replace").strip() if data else ""

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

    def encode_batch(
        self,
        cancel_event: threading.Event,
        *,
        source_paths: list[str],
        overwrite_existing: bool,
        scale_percent: int | None,
    ) -> None:
        normalized_sources = [str(Path(path)) for path in source_paths if path]
        if not normalized_sources:
            return

        command = [
            str(self.resolve_executable()),
            "-f",
            self.OPAQUE_FORMAT,
            "-af",
            self.ALPHA_FORMAT,
            "-o" if overwrite_existing else "-on",
            "-vf",
            "-r",
            "Textures",
            "-t",
            "-p",
        ]
        if not bool(self.options.get("generate_mipmaps", True)):
            command.append("-nm")
        if scale_percent is None:
            command.append("-fs")
        else:
            command.extend(["-sc", str(int(scale_percent))])

        timeout_seconds = max(300, int(self.options.get("encode_batch_timeout_seconds", 480) or 480))
        file_list = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, suffix=".txt") as handle:
                file_list = Path(handle.name)
                for source_path in normalized_sources:
                    handle.write(f"{source_path}\n")
            command.append(str(file_list))
            _ToolProcessRunner.run_command(
                command,
                cancel_event,
                timeout_seconds=timeout_seconds,
                tool_name="todds",
            )
        finally:
            if file_list and file_list.exists():
                try:
                    file_list.unlink()
                except OSError:
                    pass


class TextureOptimizationManager:
    def __init__(self):
        self._tasks: dict[str, TextureTask] = {}
        self._analysis_tasks: dict[str, threading.Event] = {}
        self._analysis_started_at: dict[str, int] = {}
        self._lock = threading.Lock()

    def get_active_analysis_task_ids(self) -> list[str]:
        with self._lock:
            return list(self._analysis_tasks.keys())

    def cancel_all_analysis_tasks(self) -> list[str]:
        task_ids = self.get_active_analysis_task_ids()
        for task_id in task_ids:
            event = self._analysis_tasks.get(task_id)
            if event:
                event.set()
        return task_ids

    def wait_for_analysis_idle(self, timeout: float = 10.0, poll_interval: float = 0.1) -> bool:
        deadline = time.time() + max(0.0, timeout)
        while time.time() < deadline:
            with self._lock:
                if not self._analysis_tasks:
                    return True
            time.sleep(max(0.01, poll_interval))
        with self._lock:
            return not self._analysis_tasks

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

    def start_task(self, mod_paths: list[str], action: str = "optimize", options: dict[str, Any] | None = None) -> dict[str, Any]:
        mod_paths = self._normalize_mod_paths(mod_paths)
        if not mod_paths:
            raise TextureOptError("没有可处理的 Mod 路径")

        task_id = uuid.uuid4().hex
        task = TextureTask(id=task_id, action=action, mod_paths=mod_paths, options=self._build_options(options))
        with self._lock:
            self._tasks[task_id] = task

        worker = threading.Thread(target=self._run_task, args=(task,), daemon=True, name=f"TextureOpt-{task_id[:8]}")
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
            executable = ToddsEncoder(merged_options).resolve_executable()
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
        GithubManager().install_from_github(
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

    def analyze_mods(
        self,
        mod_paths: list[str],
        options: dict[str, Any] | None = None,
        task_id: str | None = None,
        cancel_event: threading.Event | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        del use_cache
        mod_paths = self._normalize_mod_paths(mod_paths)
        if not mod_paths:
            raise TextureOptError("没有可分析的 Mod 路径")

        analysis_task_id = task_id or uuid.uuid4().hex
        merged_options = self._build_options(options)
        tool_status = self.get_backend_status(merged_options)
        summary, mods = self._scan_mods(mod_paths, merged_options, cancel_event, analysis_task_id=analysis_task_id)
        elapsed_ms = max(0, current_ms() - int(self._analysis_started_at.get(analysis_task_id, current_ms())))
        self._emit_analysis_progress(
            analysis_task_id,
            status="success",
            progress=100,
            message=f"统计完成，用时 {self._format_elapsed_ms(elapsed_ms)}",
            processed_mods=len(mod_paths),
            total_mods=len(mod_paths),
            summary=summary,
            final_mods=mods,
        )
        return {
            "task_id": analysis_task_id,
            "tool_status": tool_status,
            "summary": summary,
            "mods": mods,
            "options": merged_options,
            "generated_at": current_ms(),
        }

    def _run_task(self, task: TextureTask) -> None:
        try:
            self._set_task_state(task, status="running", message="正在执行贴图队列...")
            summary = self._clean_outputs(task) if task.action == "clean_generated" else self._optimize(task)
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
        options = self._build_options(task.options)
        task.options = options
        encoder = ToddsEncoder(options)
        final_mods_by_path: dict[str, dict[str, Any]] = {}
        final_summary, final_mods = self._compose_progress_snapshot(task.mod_paths, final_mods_by_path)

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
                "summary": final_summary,
                "final_mods": final_mods,
                "refresh_after_analyze": False,
            },
        )

        optimized = 0
        skipped = 0
        failed = 0
        total_mods = max(1, len(task.mod_paths))

        for index, mod_path in enumerate(task.mod_paths, start=1):
            if task._cancel_event.is_set():
                raise TextureOptCancelled("DDS 生成任务已取消")

            scan_result = self._scan_single_mod(mod_path, options)
            entries = scan_result["entries"]
            mod_name = scan_result["mod_name"]
            actionable_entries = [entry for entry in entries if bool(entry.get("needs_action"))]
            skipped += sum(1 for entry in entries if not bool(entry.get("needs_action")))
            final_mods_by_path[mod_path] = dict(scan_result["stat"])
            final_summary, final_mods = self._compose_progress_snapshot(task.mod_paths, final_mods_by_path)

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
                    "current_mod_sources": len(entries),
                    "current_mod_pending": len(actionable_entries),
                    "summary": final_summary,
                    "current_entry": dict(scan_result["stat"]),
                    "final_mods": final_mods,
                    "refresh_after_analyze": False,
                },
            )

            batches = self._build_encode_batches(entries)
            for batch in batches:
                if task._cancel_event.is_set():
                    raise TextureOptCancelled("DDS 生成任务已取消")
                try:
                    encoder.encode_batch(
                        task._cancel_event,
                        source_paths=batch["source_paths"],
                        overwrite_existing=bool(batch["overwrite_existing"]),
                        scale_percent=batch["scale_percent"],
                    )
                except TextureOptCancelled:
                    raise
                except Exception:
                    failed += len(batch["entries"])
                    raise

            optimized += len(actionable_entries)
            refreshed_result = self._scan_single_mod(mod_path, options)
            refreshed_stat = dict(refreshed_result["stat"])
            final_mods_by_path[mod_path] = refreshed_stat
            final_summary, final_mods = self._compose_progress_snapshot(task.mod_paths, final_mods_by_path)

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
                    "current_entry": refreshed_stat,
                    "final_mods": final_mods,
                    "refresh_after_analyze": False,
                },
            )

        scale_summary_text = self._format_scale_counts(final_summary)
        return {
            "optimized": optimized,
            "skipped": skipped,
            "failed": failed,
            "preexisting_dds": int(final_summary.get("current_output_count", 0)),
            "orphan_deleted": 0,
            "total_jobs": len(task.mod_paths),
            "final_summary": final_summary,
            "final_mods": final_mods,
            "refresh_after_analyze": False,
            "message": f"DDS 生成完成{f'，{scale_summary_text}' if scale_summary_text else ''}",
        }

    def _compose_progress_snapshot(
        self,
        ordered_mod_paths: list[str],
        stats_by_path: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rows = [dict(stats_by_path[path]) for path in ordered_mod_paths if path in stats_by_path]
        summary = self._create_empty_stat(include_mod_count=True, mod_count=len(ordered_mod_paths))
        for row in rows:
            self._merge_stat(summary, row)
        self._finalize_stat_shares(summary, rows)
        rows.sort(key=lambda item: (-int(item["combined_total_bytes"]), item["mod_name"].lower()))
        return summary, rows

    def _clean_outputs(self, task: TextureTask) -> dict[str, Any]:
        deleted = 0
        checked = 0
        delete_failed = 0
        total_mods = max(1, len(task.mod_paths))

        for index, mod_path in enumerate(task.mod_paths, start=1):
            if task._cancel_event.is_set():
                raise TextureOptCancelled("清理 DDS 任务已取消")

            output_paths = list(self._iter_texture_output_paths_with_source(mod_path))
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
                except OSError as exc:
                    delete_failed += 1
                    logger.warning("Texture clean delete failed: path=%s error=%s", output_path, exc)
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

        return {
            "optimized": 0,
            "skipped": 0,
            "failed": 0,
            "preexisting_dds": 0,
            "orphan_deleted": deleted,
            "checked_outputs": checked,
            "delete_failed": delete_failed,
            "total_jobs": 0,
            "refresh_after_analyze": True,
            "message": "DDS 清理完成",
        }

    def _scan_mods(
        self,
        mod_paths: list[str],
        options: dict[str, Any],
        cancel_event: threading.Event | None,
        *,
        analysis_task_id: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        summary = self._create_empty_stat(include_mod_count=True, mod_count=len(mod_paths))
        mod_rows: list[dict[str, Any] | None] = [None] * len(mod_paths)
        total_mods = max(1, len(mod_paths))
        workers = self._resolve_scan_workers(total_mods, options)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="TextureScan") as executor:
            future_map = {
                executor.submit(self._scan_single_mod, mod_path, options): index
                for index, mod_path in enumerate(mod_paths)
            }
            completed = 0
            for future in concurrent.futures.as_completed(future_map):
                if cancel_event and cancel_event.is_set():
                    raise TextureOptCancelled("贴图扫描任务已取消")
                index = future_map[future]
                result = future.result()
                mod_rows[index] = result["stat"]
                self._merge_stat(summary, result["stat"])
                completed += 1
                if analysis_task_id:
                    self._emit_analysis_progress(
                        analysis_task_id,
                        status="running",
                        progress=min(99, int((completed / total_mods) * 100)),
                        message=f"已扫描 {result['mod_name']}",
                        processed_mods=completed,
                        total_mods=total_mods,
                        summary=summary,
                        current_entry=result["stat"],
                    )

        rows = [row for row in mod_rows if isinstance(row, dict)]
        self._finalize_stat_shares(summary, rows)
        rows.sort(key=lambda item: (-int(item["combined_total_bytes"]), item["mod_name"].lower()))
        return summary, rows

    def _scan_single_mod(self, mod_path: str, options: dict[str, Any]) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        output_stats = self._collect_output_stats(mod_path)
        process_mode = str(options.get("process_mode", "scaled_only_overwrite"))
        preferred_scale = self._get_scale_factor_percent(options)
        scale_buckets = self._iter_scale_step_candidates(options)
        min_output_size = self._get_scale_target_size(options)
        mod_name = Path(mod_path).name

        for source_path in self._iter_texture_source_images(mod_path):
            source = Path(source_path)
            rel_path = self._to_rel_path(str(source), mod_path)
            output_path = source.with_suffix(".dds")
            output_rel = self._to_rel_path(str(output_path), mod_path)
            output_info = output_stats.get(output_rel) or {}

            entry = {
                "mod_path": mod_path,
                "mod_name": mod_name,
                "rel_path": rel_path,
                "source_path": str(source),
                "output_path": str(output_path),
                "output_rel_path": output_rel,
                "output_exists": bool(output_info),
                "output_size": int(output_info.get("size", 0)),
                "source_readable": False,
                "width": 0,
                "height": 0,
                "has_alpha": False,
                "source_size": 0,
                "source_vram": 0,
                "dds_vram": 0,
                "small_skipped": False,
                "engine_unsupported": False,
                "engine_unsupported_reason": "",
                "processable": False,
                "current_output": False,
                "needs_generate": False,
                "needs_regenerate": False,
                "needs_action": False,
                "plan_kind": "keep_original",
                "plan_label": "原尺寸",
                "scale_percent": None,
            }

            try:
                image_info = self._inspect_source_image(source, precise_alpha=False)
                source_stat = source.stat()
            except Exception as exc:
                try:
                    source_stat = source.stat()
                    entry["source_size"] = int(source_stat.st_size)
                except OSError:
                    pass
                entry["engine_unsupported"] = True
                entry["engine_unsupported_reason"] = f"PNG 文件无法解析: {exc}"
                entries.append(entry)
                continue

            width = int(image_info.get("width", 0) or 0)
            height = int(image_info.get("height", 0) or 0)
            has_alpha = bool(image_info.get("has_alpha"))
            source_size = int(source_stat.st_size)
            source_vram = width * height * 4
            oversize_or_small = self._is_outside_recommended_source_range(width, height, options)
            scale_percent = None if oversize_or_small else self._pick_scale_step_percent(width, height, scale_buckets, min_output_size)
            can_scale = scale_percent is not None

            if can_scale:
                dds_vram = self._estimate_dds_vram(width, height, has_alpha, scale_percent, generate_mipmaps=bool(options.get("generate_mipmaps", True)))
                plan_kind = "scaled" if scale_percent == preferred_scale else "fallback"
                plan_label = f"{scale_percent}%"
            else:
                dds_vram = self._estimate_dds_vram(width, height, has_alpha, None, generate_mipmaps=bool(options.get("generate_mipmaps", True)))
                plan_kind = "keep_original"
                plan_label = "原尺寸"

            entry.update(
                {
                    "source_readable": True,
                    "width": width,
                    "height": height,
                    "has_alpha": has_alpha,
                    "source_size": source_size,
                    "source_vram": source_vram,
                    "dds_vram": dds_vram,
                    "small_skipped": oversize_or_small,
                    "engine_unsupported": bool(self._get_todds_unsupported_reason(source, image_info)),
                    "engine_unsupported_reason": self._get_todds_unsupported_reason(source, image_info),
                    "processable": not bool(self._get_todds_unsupported_reason(source, image_info)),
                    "plan_kind": plan_kind,
                    "plan_label": plan_label,
                    "scale_percent": scale_percent,
                }
            )

            if entry["engine_unsupported"]:
                entries.append(entry)
                continue

            entry["current_output"] = bool(entry["output_exists"])
            needs_action = self._entry_needs_action(entry, process_mode)
            entry["needs_action"] = needs_action
            entry["needs_generate"] = needs_action and not entry["output_exists"]
            entry["needs_regenerate"] = needs_action and entry["output_exists"]
            entries.append(entry)

        stat = self._build_mod_stat(mod_path, mod_name, entries, output_stats)
        return {"mod_path": mod_path, "mod_name": mod_name, "entries": entries, "stat": stat}

    @staticmethod
    def _entry_needs_action(entry: dict[str, Any], process_mode: str) -> bool:
        output_exists = bool(entry.get("output_exists"))
        scale_percent = entry.get("scale_percent")
        if process_mode == "all_skip_existing":
            return not output_exists
        if process_mode == "scaled_only_overwrite":
            return scale_percent is not None
        return True

    def _build_encode_batches(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[bool, int | None], dict[str, Any]] = {}
        for entry in entries:
            if not bool(entry.get("needs_action")):
                continue
            batch_key = (bool(entry.get("output_exists")), entry.get("scale_percent"))
            batch = grouped.setdefault(
                batch_key,
                {
                    "overwrite_existing": bool(entry.get("output_exists")),
                    "scale_percent": entry.get("scale_percent"),
                    "entries": [],
                    "source_paths": [],
                },
            )
            batch["entries"].append(entry)
            batch["source_paths"].append(str(entry.get("source_path") or ""))

        batches = list(grouped.values())
        batches.sort(
            key=lambda item: (
                item.get("scale_percent") is None,
                int(item.get("scale_percent") or 999),
                not bool(item.get("overwrite_existing")),
            )
        )
        return batches

    @staticmethod
    def _build_mod_stat(
        mod_path: str,
        mod_name: str,
        entries: list[dict[str, Any]],
        output_stats: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        stat = TextureOptimizationManager._create_empty_stat(mod_path=mod_path, mod_name=mod_name)
        stat["output_total_count"] = len(output_stats)
        stat["output_total_bytes"] = sum(int(item.get("size", 0)) for item in output_stats.values())
        stat["managed_output_count"] = stat["output_total_count"]
        stat["managed_output_bytes"] = stat["output_total_bytes"]
        scale_buckets: dict[tuple[str, str], int] = {}

        for entry in entries:
            if not bool(entry.get("source_readable")):
                stat["unreadable_source_count"] += 1
                continue

            stat["source_total_count"] += 1
            stat["source_total_bytes"] += int(entry.get("source_size", 0))
            stat["source_vram_bytes_est"] += int(entry.get("source_vram", 0))
            stat["output_vram_bytes_est"] += int(entry.get("dds_vram", 0))

            if bool(entry.get("small_skipped")):
                stat["skip_small_count"] += 1
            if bool(entry.get("engine_unsupported")):
                stat["unsupported_source_count"] += 1
                if len(stat["engine_unsupported_preview"]) < 8:
                    stat["engine_unsupported_preview"].append(
                        {
                            "rel_path": str(entry.get("rel_path") or ""),
                            "reason": str(entry.get("engine_unsupported_reason") or ""),
                        }
                    )
                continue

            plan_kind = str(entry.get("plan_kind") or "keep_original")
            if plan_kind == "fallback":
                stat["fallback_scaled_count"] += 1
            elif plan_kind == "keep_original":
                stat["keep_original_count"] += 1
            else:
                stat["scaled_count"] += 1

            TextureOptimizationManager._append_scale_bucket(
                scale_buckets,
                kind=plan_kind,
                label=str(entry.get("plan_label") or "原尺寸"),
            )

            if bool(entry.get("output_exists")):
                stat["current_output_count"] += 1
                stat["current_output_bytes"] += int(entry.get("output_size", 0))
            if bool(entry.get("needs_generate")):
                stat["generate_required_count"] += 1
                stat["action_required_count"] += 1
            if bool(entry.get("needs_regenerate")):
                stat["regenerate_required_count"] += 1
                stat["action_required_count"] += 1
                stat["stale_output_count"] += 1
                stat["stale_output_bytes"] += int(entry.get("output_size", 0))
            if not bool(entry.get("output_exists")) and not bool(entry.get("needs_generate")) and not bool(entry.get("needs_regenerate")):
                stat["missing_output_count"] += 1

        stat["scale_breakdown"] = TextureOptimizationManager._finalize_scale_breakdown(scale_buckets)
        stat["combined_total_bytes"] = int(stat["source_total_bytes"]) + int(stat["output_total_bytes"])
        stat["vram_saving_bytes_est"] = int(stat["source_vram_bytes_est"]) - int(stat["output_vram_bytes_est"])
        return stat

    @staticmethod
    def _get_scale_factor_percent(options: dict[str, Any]) -> int | None:
        scale_factor = float(options.get("scale_factor", 1.0) or 1.0)
        if scale_factor <= 0 or abs(scale_factor - 1.0) <= 1e-6:
            return None
        scale_percent = int(round(scale_factor * 100))
        return scale_percent if scale_percent in SCALE_STEP_SEQUENCE else None

    @staticmethod
    def _get_scale_target_size(options: dict[str, Any]) -> int:
        configured_max_size = int(options.get("max_size", 0) or 0)
        return configured_max_size if configured_max_size > 0 else 128

    @staticmethod
    def _iter_scale_step_candidates(options: dict[str, Any]) -> tuple[int, ...]:
        preferred = TextureOptimizationManager._get_scale_factor_percent(options)
        if preferred not in SCALE_STEP_SEQUENCE:
            return tuple()
        start_index = SCALE_STEP_SEQUENCE.index(preferred)
        return SCALE_STEP_SEQUENCE[start_index:]

    @staticmethod
    def _pick_scale_step_percent(w: int, h: int, scale_candidates: tuple[int, ...], min_output_size: int) -> int | None:
        for scale_percent in scale_candidates:
            numerator, denominator = SCALE_STEP_RATIONALS[scale_percent]
            required_divisor = (4 * denominator) // TextureOptimizationManager._gcd(numerator, 4 * denominator)
            if (w % required_divisor) != 0 or (h % required_divisor) != 0:
                continue
            if (min(w, h) * numerator) < (min_output_size * denominator):
                continue
            return scale_percent
        return None

    @staticmethod
    def _gcd(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a

    @staticmethod
    def _estimate_dds_vram(
        width: int,
        height: int,
        has_alpha: bool,
        scale_percent: int | None,
        *,
        generate_mipmaps: bool,
    ) -> int:
        target_width = int(width)
        target_height = int(height)
        if scale_percent is not None:
            target_width = int(target_width * int(scale_percent) / 100)
            target_height = int(target_height * int(scale_percent) / 100)
        multiplier = 1.0 if has_alpha else 0.5
        dds_vram = int(max(1, target_width) * max(1, target_height) * multiplier)
        if generate_mipmaps:
            dds_vram = int(dds_vram * 1.333)
        return dds_vram

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
        if not precise_alpha and path.suffix.lower() == ".png":
            fast_info = TextureOptimizationManager._inspect_png_header(path)
            if fast_info is not None:
                return fast_info
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
                        return {
                            "width": width,
                            "height": height,
                            "has_alpha": color_type in {4, 6} or has_trns,
                            "image_format": "PNG",
                        }
                    if chunk_type == b"IEND":
                        return None
        except OSError:
            return None

    @staticmethod
    def _is_outside_recommended_source_range(width: int, height: int, options: dict[str, Any]) -> bool:
        if not options.get("skip_small_textures", True):
            return False
        min_dimension = max(1, int(options.get("min_dimension", 128)))
        max_source_dimension = max(0, int(options.get("max_source_dimension", 2048)))
        if width < min_dimension or height < min_dimension:
            return True
        if max_source_dimension > 0 and max(width, height) > max_source_dimension:
            return True
        return False

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
                    lower_name = name.lower()
                    path = Path(current_root) / name
                    if lower_name.endswith(".dds") or lower_name.endswith(".dds.zstd"):
                        yield path

    @staticmethod
    def _iter_texture_output_paths_with_source(mod_path: str):
        for output_path in TextureOptimizationManager._iter_texture_output_paths(mod_path):
            source_path = TextureOptimizationManager._resolve_output_source(output_path)
            if source_path.exists():
                yield output_path

    @staticmethod
    def _collect_output_stats(mod_path: str) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        for output_path in TextureOptimizationManager._iter_texture_output_paths(mod_path):
            try:
                output_stat = output_path.stat()
            except OSError:
                continue
            stats[TextureOptimizationManager._to_rel_path(str(output_path), mod_path)] = {
                "path": str(output_path),
                "size": int(output_stat.st_size),
                "mtime_ns": int(output_stat.st_mtime_ns),
            }
        return stats

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
    def _to_rel_path(path: str, root: str) -> str:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()

    @staticmethod
    def _normalize_mod_paths(mod_paths: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for path in mod_paths:
            if not path:
                continue
            abs_path = os.path.abspath(path)
            lower = abs_path.lower()
            if lower in seen or not os.path.isdir(abs_path):
                continue
            seen.add(lower)
            normalized.append(abs_path)
        return normalized

    @staticmethod
    def _resolve_scan_workers(total_mods: int, options: dict[str, Any]) -> int:
        configured_workers = int(options.get("scan_workers", 0) or 0)
        if configured_workers > 0:
            return max(1, min(total_mods, configured_workers))
        cpu_count = os.cpu_count() or 4
        return max(1, min(total_mods, min(8, cpu_count)))

    @staticmethod
    def _build_options(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        texture_opt = getattr(settings.config, "texture_opt", {})
        if is_dataclass(texture_opt) and not isinstance(texture_opt, type):
            base = asdict(texture_opt)
        elif isinstance(texture_opt, dict):
            base = dict(texture_opt)
        else:
            base = {}

        merged = dict(base)
        merged.update(overrides or {})
        merged.setdefault("texture_tools_path", "")
        merged.setdefault("process_mode", "scaled_only_overwrite")
        merged.setdefault("generate_mipmaps", True)
        merged.setdefault("scale_factor", 0.5)
        merged.setdefault("max_size", 128)
        merged.setdefault("skip_small_textures", True)
        merged.setdefault("min_dimension", 128)
        merged.setdefault("max_source_dimension", 2048)
        merged.setdefault("encode_batch_timeout_seconds", 480)

        process_mode = str(merged.get("process_mode", "scaled_only_overwrite") or "scaled_only_overwrite").strip()
        if process_mode not in {"all_overwrite", "scaled_only_overwrite", "all_skip_existing"}:
            process_mode = "scaled_only_overwrite"
        merged["process_mode"] = process_mode
        merged["scale_factor"] = float(merged.get("scale_factor", 0.5) or 0.5)
        merged["max_size"] = int(merged.get("max_size", 128) or 128)
        merged["min_dimension"] = int(merged.get("min_dimension", 128) or 128)
        merged["max_source_dimension"] = int(merged.get("max_source_dimension", 2048) or 2048)
        merged["skip_small_textures"] = bool(merged.get("skip_small_textures", True))
        merged["texture_tools_path"] = str(resolve_texture_tools_path(merged))
        return merged

    @staticmethod
    def _calc_progress(current: int, total: int) -> int:
        if total <= 0:
            return 0
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
            "scaled_count": summary.get("scaled_count", 0),
            "fallback_scaled_count": summary.get("fallback_scaled_count", 0),
            "keep_original_count": summary.get("keep_original_count", 0),
        }

    @staticmethod
    def _format_scale_counts(summary: dict[str, Any]) -> str:
        parts: list[str] = []
        scaled_count = int(summary.get("scaled_count", 0) or 0)
        fallback_scaled_count = int(summary.get("fallback_scaled_count", 0) or 0)
        keep_original_count = int(summary.get("keep_original_count", 0) or 0)
        if scaled_count > 0:
            parts.append(f"按当前档位缩放 {scaled_count} 张")
        if fallback_scaled_count > 0:
            parts.append(f"自动回退 {fallback_scaled_count} 张")
        if keep_original_count > 0:
            parts.append(f"保持原尺寸 {keep_original_count} 张")
        return "，".join(parts)

    @staticmethod
    def _create_empty_stat(*, mod_path: str = "", mod_name: str = "", include_mod_count: bool = False, mod_count: int = 0) -> dict[str, Any]:
        stat = {
            "mod_path": mod_path,
            "mod_name": mod_name,
            "source_total_count": 0,
            "source_total_bytes": 0,
            "output_total_count": 0,
            "output_total_bytes": 0,
            "managed_output_count": 0,
            "managed_output_bytes": 0,
            "external_output_count": 0,
            "external_output_bytes": 0,
            "current_output_count": 0,
            "current_output_bytes": 0,
            "stale_output_count": 0,
            "stale_output_bytes": 0,
            "missing_output_count": 0,
            "generate_required_count": 0,
            "regenerate_required_count": 0,
            "action_required_count": 0,
            "skip_small_count": 0,
            "skip_mask_count": 0,
            "unsupported_source_count": 0,
            "unreadable_source_count": 0,
            "blocked_source_count": 0,
            "orphan_output_count": 0,
            "orphan_output_bytes": 0,
            "managed_orphan_output_count": 0,
            "managed_orphan_output_bytes": 0,
            "external_orphan_output_count": 0,
            "external_orphan_output_bytes": 0,
            "scaled_count": 0,
            "fallback_scaled_count": 0,
            "keep_original_count": 0,
            "combined_total_bytes": 0,
            "scale_breakdown": [],
            "engine_unsupported_preview": [],
            "source_vram_bytes_est": 0,
            "output_vram_bytes_est": 0,
            "vram_saving_bytes_est": 0,
            "source_bytes_share_pct": 0.0,
            "output_bytes_share_pct": 0.0,
            "combined_bytes_share_pct": 0.0,
        }
        if include_mod_count:
            stat["mod_count"] = mod_count
        return stat

    @staticmethod
    def _append_scale_bucket(scale_buckets: dict[tuple[str, str], int], *, kind: str, label: str) -> None:
        key = (str(kind or "keep_original"), str(label or "原尺寸"))
        scale_buckets[key] = int(scale_buckets.get(key, 0)) + 1

    @staticmethod
    def _finalize_scale_breakdown(scale_buckets: dict[tuple[str, str], int]) -> list[dict[str, Any]]:
        order = {"scaled": 0, "fallback": 1, "keep_original": 2}
        items = [
            {"kind": kind, "label": label, "count": int(count)}
            for (kind, label), count in scale_buckets.items()
            if int(count) > 0
        ]
        items.sort(key=lambda item: (order.get(str(item["kind"]), 99), -int(item["count"]), str(item["label"])))
        return items

    @staticmethod
    def _merge_stat(target: dict[str, Any], source: dict[str, Any]) -> None:
        target_scale_buckets = {
            (str(item.get("kind") or "keep_original"), str(item.get("label") or "原尺寸")): int(item.get("count", 0))
            for item in target.get("scale_breakdown", [])
            if isinstance(item, dict)
        }
        for item in source.get("scale_breakdown", []):
            if not isinstance(item, dict):
                continue
            current_key = (str(item.get("kind") or "keep_original"), str(item.get("label") or "原尺寸"))
            target_scale_buckets[current_key] = int(target_scale_buckets.get(current_key, 0)) + int(item.get("count", 0))

        for key, value in source.items():
            if key in {"mod_path", "mod_name", "scale_breakdown", "engine_unsupported_preview"}:
                continue
            if key == "mod_count":
                continue
            if isinstance(value, (int, float)):
                target[key] = int(target.get(key, 0)) + int(value)
        target["scale_breakdown"] = TextureOptimizationManager._finalize_scale_breakdown(target_scale_buckets)
        target["combined_total_bytes"] = int(target.get("source_total_bytes", 0)) + int(target.get("output_total_bytes", 0))
        target["vram_saving_bytes_est"] = int(target.get("source_vram_bytes_est", 0)) - int(target.get("output_vram_bytes_est", 0))

        preview = list(target.get("engine_unsupported_preview", []))
        for item in source.get("engine_unsupported_preview", []):
            if len(preview) >= 12:
                break
            preview.append(item)
        target["engine_unsupported_preview"] = preview

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

    def _set_task_state(
        self,
        task: TextureTask,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        metrics: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if summary is not None:
            task.summary = summary
        if error is not None:
            task.error = error
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
        task.status = status
        task.progress = progress
        task.message = message
        task.metrics = metrics or {}
        task.updated_at = updated_at
        task_created_at = int(getattr(task, "created_at", updated_at))
        task.metrics.setdefault("task_created_at", task_created_at)
        task.metrics["task_updated_at"] = updated_at
        task.metrics.setdefault("task_action", str(getattr(task, "action", "")))
        task.metrics["task_status"] = status
        EventBus.emit_progress(task.id, TEXTURE_TASK_TYPE, status=status, progress=progress, message=message, metrics=task.metrics)

    def _emit_analysis_progress(
        self,
        task_id: str,
        *,
        status: str,
        progress: int,
        message: str,
        processed_mods: int,
        total_mods: int,
        summary: dict[str, Any],
        current_entry: dict[str, Any] | None = None,
        final_mods: list[dict[str, Any]] | None = None,
    ) -> None:
        started_at = int(self._analysis_started_at.get(task_id, current_ms()))
        updated_at = current_ms()
        metrics = {
            "processed_mods": processed_mods,
            "total_mods": total_mods,
            "summary": {key: value for key, value in summary.items()},
            "task_created_at": started_at,
            "task_updated_at": updated_at,
            "task_status": status,
        }
        if status in {"success", "failed", "cancelled"}:
            metrics["elapsed_ms"] = max(0, updated_at - started_at)
        if current_entry:
            metrics["current_entry"] = current_entry
        if final_mods is not None:
            metrics["final_mods"] = final_mods
        EventBus.emit_progress(task_id, TEXTURE_ANALYSIS_TASK_TYPE, status=status, progress=progress, message=message, metrics=metrics)

    def _schedule_task_cleanup(self, task_id: str, delay_seconds: float = TEXTURE_TASK_RETENTION_SECONDS) -> None:
        def _cleanup() -> None:
            with self._lock:
                self._tasks.pop(task_id, None)

        timer = threading.Timer(delay_seconds, _cleanup)
        timer.daemon = True
        timer.start()

    @staticmethod
    def _format_elapsed_ms(elapsed_ms: int) -> str:
        total_seconds = max(0, elapsed_ms // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
