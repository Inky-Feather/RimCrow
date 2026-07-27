from __future__ import annotations

import concurrent.futures
import errno
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from PIL import Image

from backend.i18n.messages import localized_key, localized_params, tr
from backend.load_order.package_tokens import parse_package_token
from backend.paths.core import path_key
from backend.settings import DATA_DIR, TOOLS_DIR, settings
from backend.utils.event_bus import EventBus
from backend.utils.json_io import write_json_atomic
from backend.utils.logger import logger
from backend.utils.tools import current_ms, generate_path_hash, normalize_package_id

TEXTURE_TASK_TYPE = "texture-opt"
TEXTURE_ANALYSIS_TASK_TYPE = "texture-opt-analyze"
TEXTURE_TASK_RETENTION_SECONDS = 120
TEXTURE_SCAN_SNAPSHOT_SCHEMA_VERSION = 3
TEXTURE_RESULT_HISTORY_LIMIT = 3
TEXTURE_BASE_SCAN_CACHE_TTL_MS = 10 * 60 * 1000
TEXTURE_PROGRESS_EMIT_INTERVAL_SECONDS = 1.0
TEXTURE_ENCODE_BATCH_SIZE = 10000
TEXTURE_RETRY_BATCH_SIZE = 64
ZSTD_COMPRESS_RETRY_DELAYS_SECONDS = (0.1, 0.3)
TODDS_WINDOWS_ASSET_PREFIX = "todds_Windows_"
TODDS_FALLBACK_VERSION = "0.4.1"
TODDS_FALLBACK_FILENAME = f"todds_Windows_{TODDS_FALLBACK_VERSION}.zip"
SOURCE_IMAGE_EXTENSIONS = (".png",)
SOURCE_REFERENCE_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".psd")
TEXTURE_OUTPUT_DDS_EXT = ".dds"
TEXTURE_OUTPUT_ZSTD_EXT = ".dds.zstd"
TEXTURE_OUTPUT_EXTENSIONS = (TEXTURE_OUTPUT_DDS_EXT, TEXTURE_OUTPUT_ZSTD_EXT)
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
TODDS_PROGRESS_PATTERN = re.compile(r"Progress:\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)

TEXTURE_EXCLUSIONS_PATH = DATA_DIR / "texture_opt_exclusions.json"
TEXTURE_RESULTS_DIR = DATA_DIR / "logs" / "texture-opt" / "results"


def _safe_json_load(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback

class TextureOptError(RuntimeError):
    pass


class TextureOptCancelled(TextureOptError):
    pass


class TextureTargetResolver:
    """将前端选择的模组范围解析为贴图任务可处理的真实模组实例。"""

    def __init__(self, active_context: Any | None = None):
        self.active_context = active_context

    @staticmethod
    def build_target_from_asset(mod: dict[str, Any], *, default_store: str = "") -> dict[str, Any] | None:
        path = os.path.abspath(str(mod.get("path") or "").strip())
        if not path or not os.path.isdir(path):
            return None
        package_id = normalize_package_id(mod.get("package_id", ""))
        path_hash = str(mod.get("path_hash") or "").strip() or generate_path_hash(path)
        return {
            "mod_path": path,
            "mod_name": str(mod.get("alias_name") or mod.get("display_name") or mod.get("name") or Path(path).name).strip() or Path(path).name,
            "package_id": package_id,
            "path_hash": path_hash,
            "mod_instance_key": path_hash,
            "store": str(mod.get("store") or default_store or "").strip().lower(),
        }

    def collect_inventory_roots(self) -> list[tuple[str, str]]:
        roots: list[tuple[str, str]] = []
        if self.active_context:
            local_root = str(getattr(self.active_context, "local_mods_path", "") or "").strip()
            if local_root:
                roots.append(("local", local_root))
        self_root = str(settings.config.self_mods_path or "").strip()
        if self_root:
            roots.append(("self", self_root))
        workshop_root = str(settings.config.workshop_mods_path or "").strip()
        if workshop_root:
            roots.append(("workshop", workshop_root))

        normalized: list[tuple[str, str]] = []
        seen: set[str] = set()
        for store, root in roots:
            root_key = self._path_key(root)
            if not root_key or root_key in seen or not os.path.isdir(root):
                continue
            seen.add(root_key)
            normalized.append((store, root))
        return normalized

    def collect_all_targets(self) -> list[dict[str, Any]]:
        return self.collect_installed_targets(include_disabled=True)

    def collect_installed_targets(self, *, include_disabled: bool) -> list[dict[str, Any]]:
        from backend.database.dao import ModDAO

        assets: list[dict[str, Any]] = []
        for asset in ModDAO.get_profile_mods(self.active_context):
            assets.append(asset)
            coexist_variant = asset.get("coexist_workshop_variant")
            if isinstance(coexist_variant, dict):
                assets.append(coexist_variant)
        if include_disabled:
            assets.extend(ModDAO.get_profile_disabled_mods(self.active_context))
        targets: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for asset in assets:
            target = self.build_target_from_asset(asset, default_store=str(asset.get("store") or ""))
            if not target:
                continue
            path_key = self._path_key(str(target.get("mod_path") or ""))
            if not path_key or path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            targets.append(target)
        return targets

    def collect_residue_targets(
        self,
        installed_path_keys: set[str] | None = None,
        *,
        include_zstd: bool = False,
    ) -> list[dict[str, Any]]:
        roots = self.collect_inventory_roots()
        if not roots:
            return []
        installed_keys = installed_path_keys if installed_path_keys is not None else self._path_keys_from_targets(
            self.collect_installed_targets(include_disabled=True)
        )
        targets: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for store, root in roots:
            if not root or not os.path.isdir(root):
                continue
            try:
                with os.scandir(root) as iterator:
                    for entry in iterator:
                        try:
                            if not entry.is_dir():
                                continue
                        except OSError:
                            continue
                        mod_path = os.path.abspath(entry.path)
                        path_key = self._path_key(mod_path)
                        if not path_key or path_key in seen_paths:
                            continue
                        seen_paths.add(path_key)
                        if path_key in installed_keys:
                            continue
                        if not self._has_texture_output(mod_path, include_zstd=include_zstd):
                            continue
                        path_hash = generate_path_hash(mod_path)
                        targets.append({
                            "mod_path": mod_path,
                            "mod_name": entry.name,
                            "package_id": "",
                            "path_hash": path_hash,
                            "mod_instance_key": path_hash,
                            "store": store,
                            "residue": True,
                            "requires_png_source": False,
                        })
            except OSError as exc:
                logger.warning("扫描贴图残留目标失败：root=%s error=%s", root, exc)
        return targets

    def resolve_clean_targets(
        self,
        package_ids: list[str],
        target_scope: str,
        *,
        residue_only: bool,
        include_zstd: bool = False,
    ) -> list[dict[str, Any]]:
        scope = str(target_scope or "active").strip().lower()
        if scope != "all" and not residue_only:
            installed_targets = self.resolve(package_ids, "active")
            for target in installed_targets:
                target["residue"] = False
                target["requires_png_source"] = True
            return installed_targets

        all_installed_targets = self.collect_installed_targets(include_disabled=True)
        if residue_only:
            return self.collect_residue_targets(
                self._path_keys_from_targets(all_installed_targets),
                include_zstd=include_zstd,
            )

        installed_targets = all_installed_targets
        for target in installed_targets:
            target["residue"] = False
            target["requires_png_source"] = True
        installed_path_keys = self._path_keys_from_targets(all_installed_targets)
        return [*installed_targets, *self.collect_residue_targets(installed_path_keys, include_zstd=include_zstd)]

    def _path_keys_from_targets(self, targets: list[dict[str, Any]]) -> set[str]:
        path_keys: set[str] = set()
        for target in targets:
            path_key = self._path_key(str(target.get("mod_path") or ""))
            if path_key:
                path_keys.add(path_key)
        return path_keys

    @staticmethod
    def _path_key(path: str) -> str:
        value = str(path or "").strip()
        return path_key(os.path.abspath(value) if value else "", system_name=platform.system())

    @staticmethod
    def _has_texture_output(mod_path: str, *, include_zstd: bool = False) -> bool:
        for texture_root in TextureOptimizationManager._iter_texture_root_dirs(mod_path):
            for _current_root, _dirs, files in os.walk(texture_root):
                for name in files:
                    lower_name = name.lower()
                    if lower_name.endswith(TEXTURE_OUTPUT_DDS_EXT) or (
                        include_zstd and lower_name.endswith(TEXTURE_OUTPUT_ZSTD_EXT)
                    ):
                        return True
        return False

    def resolve(self, package_ids: list[str], target_scope: str = "active") -> list[dict[str, Any]]:
        if str(target_scope or "").strip().lower() == "all":
            return self.collect_all_targets()

        target_tokens = [parse_package_token(pid) for pid in (package_ids or []) if pid]
        if not target_tokens:
            return []

        from backend.database.dao import ModDAO

        context_mods = ModDAO.get_profile_mods(self.active_context)
        mod_map = {
            normalize_package_id(m.get("package_id", "")): m
            for m in context_mods
            if normalize_package_id(m.get("package_id", ""))
        }
        targets: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for token_info in target_tokens:
            mod = mod_map.get(token_info.canonical_package_id)
            if not mod:
                continue
            target_mod = (mod.get("coexist_workshop_variant") or mod) if token_info.source_preference == "steam" else mod
            target = self.build_target_from_asset(target_mod)
            if not target:
                continue
            path_key = str(target["mod_path"]).lower()
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            targets.append(target)
        return targets


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
    mod_targets: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    progress: int = 0
    message: str = ""
    message_key: str = ""
    message_params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=current_ms)
    updated_at: int = field(default_factory=current_ms)
    summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    user_message: str = ""
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def __post_init__(self) -> None:
        self.mod_paths = [os.path.abspath(str(path or "").strip()) for path in self.mod_paths if str(path or "").strip()]
        if self.mod_targets:
            return
        seen_keys: set[str] = set()
        for mod_path in self.mod_paths:
            if not os.path.isdir(mod_path):
                continue
            path_hash = generate_path_hash(mod_path)
            if path_hash in seen_keys:
                continue
            seen_keys.add(path_hash)
            self.mod_targets.append(
                {
                    "mod_path": mod_path,
                    "mod_name": Path(mod_path).name,
                    "package_id": "",
                    "store": "",
                    "path_hash": path_hash,
                    "mod_instance_key": path_hash,
                }
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.id,
            "action": self.action,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "message_key": self.message_key,
            "message_params": dict(self.message_params),
            "metrics": dict(self.metrics),
            "summary": dict(self.summary),
            "error": self.error,
            "user_message": self.user_message,
            "mod_paths": list(self.mod_paths),
            "mod_targets": [dict(item) for item in self.mod_targets],
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
        output_callback: Callable[[str], None] | None = None,
    ) -> None:
        creationflags = 0
        startupinfo = None
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        log_path: Path | None = None
        process = None
        last_activity_at = time.monotonic()
        was_cancelled = False
        timeout_detail = ""
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, suffix=".log") as log_file:
                log_path = Path(log_file.name)
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                    startupinfo=startupinfo,
                )
                reader_error: Exception | None = None

                def consume_output() -> None:
                    nonlocal last_activity_at, reader_error
                    if not process or not process.stdout: return
                    try:
                        for line in process.stdout:
                            last_activity_at = time.monotonic()
                            log_file.write(line)
                            if output_callback:
                                output_callback(line.rstrip("\r\n"))
                    except Exception as exc:
                        reader_error = exc

                reader = threading.Thread(target=consume_output, daemon=True, name=f"{tool_name}-output")
                reader.start()
                while True:
                    if cancel_event.is_set():
                        _ToolProcessRunner.terminate_process(process)
                        was_cancelled = True
                        break
                    if process.poll() is not None:
                        break
                    if timeout_seconds and (time.monotonic() - last_activity_at) > float(timeout_seconds):
                        _ToolProcessRunner.terminate_process(process)
                        timeout_detail = "__timeout__"
                        break
                    if reader_error is not None:
                        _ToolProcessRunner.terminate_process(process)
                        raise TextureOptError(f"{tool_name} 输出读取失败: {reader_error}")
                    time.sleep(0.1)
                reader.join(timeout=2)
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
                f"{tool_name} 执行超时（连续 {int(timeout_seconds or 0)} 秒无输出）: {detail or '无输出'}"
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
        if not log_path or not log_path.exists(): return ""
        try:
            with log_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - max(1, int(limit))), os.SEEK_SET)
                data = handle.read()
        except OSError: return ""
        return data.decode("utf-8", errors="replace").strip() if data else ""

    @staticmethod
    def cleanup_log_file(log_path: Path | None) -> None:
        if not log_path: return
        try: log_path.unlink()
        except OSError: pass

    @staticmethod
    def preserve_process_log(log_path: Path | None, tool_name: str) -> str:
        if not log_path or not log_path.exists(): return ""
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
            if candidate and Path(candidate).exists(): return Path(candidate)
        raise TextureOptError("未找到 todds.exe。请在贴图优化中心下载 todds。")

    def encode_batch(
        self,
        cancel_event: threading.Event,
        *,
        source_paths: list[str],
        overwrite_existing: bool,
        scale_percent: int | None,
        max_size: int | None = None,
        output_callback: Callable[[str], None] | None = None,
    ) -> None:
        normalized_sources = [str(Path(path)) for path in source_paths if path]
        if not normalized_sources: return
        resolved_max_size = int(self.options.get("max_size", 0) or 0) if max_size is None else int(max_size or 0)

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
        if resolved_max_size > 0:
            command.extend(["-ms", str(resolved_max_size)])

        timeout_seconds = max(300, int(self.options.get("encode_batch_timeout_seconds", 600) or 600))
        file_list = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, suffix=".txt") as handle:
                file_list = Path(handle.name)
                for source_path in normalized_sources:
                    handle.write(f"{source_path}\n")
            command.append(str(file_list))
            run_kwargs = {
                "timeout_seconds": timeout_seconds,
                "tool_name": "todds",
            }
            if output_callback is not None:
                run_kwargs["output_callback"] = output_callback
            _ToolProcessRunner.run_command(
                command,
                cancel_event,
                **run_kwargs,
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
        self._base_scan_cache: dict[str, dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        self._last_todds_log_path = ""
        TEXTURE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_rel_path(path_value: str) -> str:
        return str(path_value or "").replace("\\", "/").strip("/")

    @staticmethod
    def _normalize_store(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _normalize_mod_targets(cls, mod_targets: list[dict[str, Any]] | list[str]) -> list[dict[str, Any]]:
        targets: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for item in mod_targets or []:
            if isinstance(item, str):
                target = cls._build_target_from_path(item)
            elif isinstance(item, dict):
                target = cls._build_target_from_mapping(item)
            else:
                continue
            if not target:
                continue
            target_key = str(target.get("mod_instance_key") or "")
            if target_key in seen_keys:
                continue
            seen_keys.add(target_key)
            targets.append(target)
        return targets

    @classmethod
    def _build_target_from_path(cls, mod_path: str) -> dict[str, Any] | None:
        raw_path = str(mod_path or "").strip()
        if not raw_path:
            return None
        abs_path = os.path.abspath(raw_path)
        if not os.path.isdir(abs_path):
            return None
        path_hash = generate_path_hash(abs_path)
        return {
            "mod_path": abs_path,
            "mod_name": Path(abs_path).name,
            "package_id": "",
            "store": "",
            "path_hash": path_hash,
            "mod_instance_key": path_hash,
        }

    @classmethod
    def _build_target_from_mapping(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        target = cls._build_target_from_path(str(item.get("mod_path") or item.get("path") or ""))
        if not target:
            return None
        package_id = normalize_package_id(item.get("package_id", ""))
        path_hash = str(item.get("path_hash") or target["path_hash"]).strip() or target["path_hash"]
        target.update(
            {
                "mod_name": str(item.get("mod_name") or item.get("name") or target["mod_name"]).strip() or target["mod_name"],
                "package_id": package_id,
                "store": cls._normalize_store(item.get("store")),
                "path_hash": path_hash,
                "mod_instance_key": str(item.get("mod_instance_key") or path_hash or target["mod_path"].lower()).strip() or target["mod_path"].lower(),
            }
        )
        if "requires_png_source" in item:
            target["requires_png_source"] = cls._normalize_bool(item.get("requires_png_source"), True)
        if "residue" in item:
            target["residue"] = cls._normalize_bool(item.get("residue"), False)
        return target

    @staticmethod
    def _load_exclusions() -> dict[str, Any]:
        payload = _safe_json_load(
            TEXTURE_EXCLUSIONS_PATH,
            {"schema_version": 1, "mods": [], "files": []},
        )
        if not isinstance(payload, dict):
            return {"schema_version": 1, "mods": [], "files": []}
        payload["schema_version"] = 1
        payload["mods"] = [item for item in payload.get("mods", []) if isinstance(item, dict)]
        payload["files"] = [item for item in payload.get("files", []) if isinstance(item, dict)]
        return payload

    @classmethod
    def _save_exclusions(cls, payload: dict[str, Any]) -> None:
        normalized = {
            "schema_version": 1,
            "mods": [item for item in payload.get("mods", []) if isinstance(item, dict)],
            "files": [item for item in payload.get("files", []) if isinstance(item, dict)],
        }
        write_json_atomic(TEXTURE_EXCLUSIONS_PATH, normalized, indent=2)

    @classmethod
    def _build_exclusion_indexes(cls) -> tuple[set[str], set[tuple[str, str]]]:
        payload = cls._load_exclusions()
        mod_ids = {
            str(item.get("package_id") or "").strip().lower()
            for item in payload.get("mods", [])
            if str(item.get("package_id") or "").strip()
        }
        file_keys = {
            (
                os.path.abspath(str(item.get("mod_path") or "")).lower(),
                cls._normalize_rel_path(str(item.get("rel_path") or "")).lower(),
            )
            for item in payload.get("files", [])
            if str(item.get("mod_path") or "").strip() and str(item.get("rel_path") or "").strip()
        }
        return mod_ids, file_keys

    def get_exclusions(self) -> dict[str, Any]:
        payload = self._load_exclusions()
        payload["mods"].sort(key=lambda item: str(item.get("package_id") or ""))
        payload["files"].sort(key=lambda item: (str(item.get("mod_path") or ""), str(item.get("rel_path") or "")))
        return payload

    def set_mod_exclusion(self, package_id: str, excluded: bool) -> dict[str, Any]:
        normalized_id = str(package_id or "").strip().lower()
        if not normalized_id:
            raise TextureOptError("package_id 不能为空")
        payload = self._load_exclusions()
        mods = [item for item in payload["mods"] if str(item.get("package_id") or "").strip().lower() != normalized_id]
        if excluded:
            mods.append({"package_id": normalized_id, "updated_at": current_ms()})
        payload["mods"] = mods
        self._save_exclusions(payload)
        return self.get_exclusions()

    def set_file_exclusion(self, mod_path: str, rel_path: str, excluded: bool) -> dict[str, Any]:
        normalized_mod_path = os.path.abspath(str(mod_path or "").strip())
        normalized_rel_path = self._normalize_rel_path(rel_path)
        if not normalized_mod_path or not normalized_rel_path:
            raise TextureOptError("mod_path 和 rel_path 不能为空")
        payload = self._load_exclusions()
        files = [
            item
            for item in payload["files"]
            if not (
                os.path.abspath(str(item.get("mod_path") or "")).lower() == normalized_mod_path.lower()
                and self._normalize_rel_path(str(item.get("rel_path") or "")).lower() == normalized_rel_path.lower()
            )
        ]
        if excluded:
            files.append(
                {
                    "mod_path": normalized_mod_path,
                    "rel_path": normalized_rel_path,
                    "updated_at": current_ms(),
                }
            )
        payload["files"] = files
        self._save_exclusions(payload)
        return self.get_exclusions()

    def list_result_history(self, limit: int = TEXTURE_RESULT_HISTORY_LIMIT) -> list[dict[str, Any]]:
        files = sorted(
            TEXTURE_RESULTS_DIR.glob("*.json"),
            key=lambda item: item.stat().st_mtime_ns if item.exists() else 0,
            reverse=True,
        )
        results: list[dict[str, Any]] = []
        for path in files[:max(1, int(limit or TEXTURE_RESULT_HISTORY_LIMIT))]:
            payload = _safe_json_load(path, {})
            if not isinstance(payload, dict):
                continue
            payload["result_path"] = str(path)
            results.append(payload)
        return results

    @staticmethod
    def _signature_payload(options: dict[str, Any]) -> dict[str, Any]:
        scale_factor = float(options.get("scale_factor", 1.0) or 1.0)
        scale_percent = TextureOptimizationManager._get_scale_factor_percent({"scale_factor": scale_factor})
        return {
            "process_mode": str(options.get("process_mode", "")),
            "output_format": TextureOptimizationManager._normalize_output_format(options.get("output_format")),
            "generate_mipmaps": bool(options.get("generate_mipmaps", True)),
            "scale_factor": scale_factor,
            "max_size": int(options.get("max_size", 0) or 0) if scale_percent is not None else 0,
            "skip_small_textures": bool(options.get("skip_small_textures", True)),
            "min_dimension": int(options.get("min_dimension", 128) or 128),
            "max_source_dimension": int(options.get("max_source_dimension", 2048) or 2048),
        }

    @classmethod
    def _build_signature(cls, options: dict[str, Any]) -> str:
        payload = json.dumps(cls._signature_payload(options), ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_source_signature(records: list[tuple[str, int, int]]) -> str:
        digest = hashlib.sha1()
        for rel_path, source_size, mtime_ns in sorted(records, key=lambda item: item[0]):
            digest.update(rel_path.encode("utf-8", errors="ignore"))
            digest.update(b"\0")
            digest.update(str(int(source_size)).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(int(mtime_ns)).encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _collect_source_files(
        self,
        mod_path: str,
        cancel_event: threading.Event | None = None,
    ) -> list[tuple[Path, str, os.stat_result]]:
        source_files: list[tuple[Path, str, os.stat_result]] = []
        for texture_root in self._iter_texture_root_dirs(mod_path):
            if cancel_event and cancel_event.is_set():
                raise TextureOptCancelled("贴图扫描任务已取消")
            for current_root, dirs, files in os.walk(texture_root):
                dirs.sort()
                if cancel_event and cancel_event.is_set():
                    raise TextureOptCancelled("贴图扫描任务已取消")
                current_path = Path(current_root)
                for name in sorted(files):
                    if Path(name).suffix.lower() not in SOURCE_IMAGE_EXTENSIONS:
                        continue
                    source = current_path / name
                    try:
                        source_stat = source.stat()
                    except OSError:
                        continue
                    rel_path = Path(os.path.relpath(source, mod_path)).as_posix()
                    source_files.append((source, rel_path, source_stat))
        return source_files

    @staticmethod
    def _strip_projection_fields(entry: dict[str, Any]) -> dict[str, Any]:
        base_entry = dict(entry)
        for field_name in [
            "output_exists",
            "output_size",
            "output_mtime_ns",
            "dds_vram",
            "small_skipped",
            "needs_action",
            "plan_kind",
            "plan_label",
            "scale_percent",
            "action_status",
            "is_mask_source",
            "excluded",
            "last_error",
            "overwrite_existing",
            "zstd_had_dds_before_task",
            "zstd_backup_path",
        ]:
            base_entry.pop(field_name, None)
        return base_entry

    def _bind_base_index_metadata(self, base_index: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        bound = dict(base_index)
        bound["mod_path"] = str(target.get("mod_path") or bound.get("mod_path") or "")
        bound["mod_name"] = str(target.get("mod_name") or bound.get("mod_name") or Path(bound["mod_path"]).name)
        bound["package_id"] = normalize_package_id(target.get("package_id", ""))
        bound["store"] = self._normalize_store(target.get("store"))
        bound["path_hash"] = str(target.get("path_hash") or generate_path_hash(bound["mod_path"])).strip()
        bound["mod_instance_key"] = str(target.get("mod_instance_key") or bound["path_hash"]).strip() or bound["path_hash"]
        bound["entries"] = []
        for raw_entry in base_index.get("entries", []):
            entry = dict(raw_entry)
            entry["mod_path"] = bound["mod_path"]
            entry["mod_name"] = bound["mod_name"]
            entry["package_id"] = bound["package_id"]
            entry["store"] = bound["store"]
            entry["path_hash"] = bound["path_hash"]
            entry["mod_instance_key"] = bound["mod_instance_key"]
            bound["entries"].append(entry)
        return bound

    def _store_base_scan_cache(self, base_index: dict[str, Any]) -> None:
        cache_key = str(base_index.get("mod_instance_key") or "")
        if not cache_key:
            return
        generated_at = current_ms()
        with self._cache_lock:
            # 缓存只在内存中使用；写入新结果时顺便清理过期项，避免长期运行后积累不再访问的模组索引。
            expired_keys = [
                key
                for key, snapshot in self._base_scan_cache.items()
                if generated_at - int(snapshot.get("generated_at", 0) or 0) > TEXTURE_BASE_SCAN_CACHE_TTL_MS
            ]
            for expired_key in expired_keys:
                self._base_scan_cache.pop(expired_key, None)
            self._base_scan_cache[cache_key] = {
                "schema_version": TEXTURE_SCAN_SNAPSHOT_SCHEMA_VERSION,
                "generated_at": generated_at,
                "mod_path": str(base_index.get("mod_path") or ""),
                "mod_name": str(base_index.get("mod_name") or ""),
                "package_id": normalize_package_id(base_index.get("package_id", "")),
                "store": self._normalize_store(base_index.get("store")),
                "path_hash": str(base_index.get("path_hash") or ""),
                "mod_instance_key": cache_key,
                "source_signature": str(base_index.get("source_signature") or ""),
                "entries": [self._strip_projection_fields(entry) for entry in base_index.get("entries", []) if isinstance(entry, dict)],
            }

    def _get_cached_base_scan(self, target: dict[str, Any]) -> dict[str, Any] | None:
        cache_key = str(target.get("mod_instance_key") or "")
        if not cache_key:
            return None
        with self._cache_lock:
            cached = self._base_scan_cache.get(cache_key)
        if not isinstance(cached, dict):
            return None
        if int(cached.get("schema_version", 0) or 0) != TEXTURE_SCAN_SNAPSHOT_SCHEMA_VERSION:
            return None
        cache_generated_at = int(cached.get("generated_at", 0) or 0)
        if cache_generated_at <= 0 or (current_ms() - cache_generated_at) > TEXTURE_BASE_SCAN_CACHE_TTL_MS:
            with self._cache_lock:
                current_cached = self._base_scan_cache.get(cache_key)
                if current_cached is cached:
                    self._base_scan_cache.pop(cache_key, None)
            return None
        return self._bind_base_index_metadata(cached, target)

    def _remember_todds_log_path(self, exc: Exception) -> str:
        match = re.search(r"\[日志:\s*(.*?)\]$", str(exc or ""))
        self._last_todds_log_path = match.group(1).strip() if match else ""
        return self._last_todds_log_path

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
                if not self._analysis_tasks: return True
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

    def resolve_targets(self, package_ids: list[str], target_scope: str = "active", active_context: Any | None = None) -> list[dict[str, Any]]:
        return TextureTargetResolver(active_context).resolve(package_ids, target_scope)

    def resolve_clean_targets(
        self,
        package_ids: list[str],
        target_scope: str = "active",
        *,
        residue_only: bool = False,
        include_zstd: bool = False,
        active_context: Any | None = None,
    ) -> list[dict[str, Any]]:
        return TextureTargetResolver(active_context).resolve_clean_targets(
            package_ids,
            target_scope,
            residue_only=residue_only,
            include_zstd=include_zstd,
        )

    def start_analysis_task(self, mod_targets: list[dict[str, Any]] | list[str], options: dict[str, Any] | None = None) -> dict[str, str]:
        normalized_targets = self._normalize_mod_targets(mod_targets)
        if not normalized_targets:
            raise TextureOptError("没有可分析的 Mod 路径")

        task_id = uuid.uuid4().hex
        cancel_event = self.register_analysis_task(task_id)

        def background_analyze() -> None:
            try:
                self.analyze_mods(
                    normalized_targets,
                    options,
                    task_id=task_id,
                    cancel_event=cancel_event,
                )
            except TextureOptCancelled:
                logger.info("后台贴图分析任务已取消")
                self._emit_analysis_progress(
                    task_id,
                    status="cancelled",
                    progress=0,
                    message=tr("tasks.texture.scan_cancelled", "贴图扫描任务已取消"),
                    processed_mods=0,
                    total_mods=len(normalized_targets),
                    summary=self._create_empty_stat(include_mod_count=True, mod_count=len(normalized_targets)),
                )
            except Exception as exc:
                logger.error("后台贴图分析任务执行失败: %s", exc, exc_info=True)
                failed_message = tr("tasks.texture.scan_failed", "贴图扫描任务失败。请检查 Mod 路径、贴图文件和工具配置后重试。")
                self._emit_analysis_progress(
                    task_id,
                    status="failed",
                    progress=0,
                    message=tr("tasks.texture.scan_failed_title", "贴图扫描失败"),
                    user_message=failed_message,
                    processed_mods=0,
                    total_mods=len(normalized_targets),
                    summary=self._create_empty_stat(include_mod_count=True, mod_count=len(normalized_targets)),
                )
            finally:
                self.finish_analysis_task(task_id)

        threading.Thread(target=background_analyze, daemon=True, name=f"TextureAnalyze-{task_id[:8]}").start()
        return {"task_id": task_id}

    def start_task(self, mod_targets: list[dict[str, Any]] | list[str], action: str = "optimize", options: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_action = str(action or "optimize").strip() or "optimize"
        if normalized_action not in {"optimize", "clean_generated"}:
            raise TextureOptError(f"未知贴图任务类型: {normalized_action}")
        normalized_targets = self._normalize_mod_targets(mod_targets)
        mod_paths = [str(item.get("mod_path") or "") for item in normalized_targets]
        if not normalized_targets:
            raise TextureOptError("没有可处理的 Mod 路径")

        task_id = uuid.uuid4().hex
        task = TextureTask(
            id=task_id,
            action=normalized_action,
            mod_paths=mod_paths,
            mod_targets=normalized_targets,
            options=self._build_options(options),
        )
        with self._lock:
            self._tasks[task_id] = task

        worker = threading.Thread(target=self._run_task, args=(task,), daemon=True, name=f"TextureOpt-{task_id[:8]}")
        worker.start()
        self._emit_progress(task, status="pending", progress=0, message=tr("tasks.texture.prepare_task", "准备任务..."))
        return task.to_payload()

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        task = self._tasks.get(task_id)
        if task:
            task._cancel_event.set()
            if task.status == "pending":
                self._set_task_state(task, status="cancelled", message=tr("tasks.texture.cancelled", "贴图优化任务已取消"))
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
            message = tr("api.texture.todds_found", "已找到 todds 可执行文件")
            return {
                "available": True,
                "resolved_path": str(executable),
                "message": str(message),
                "message_key": localized_key(message),
                "message_params": localized_params(message),
            }
        except TextureOptError as exc:
            logger.warning("贴图工具不可用: %s", exc)
            message = tr("api.texture.tool_unavailable", "贴图工具暂不可用。请检查工具配置、下载状态或文件权限。")
            return {
                "available": False,
                "resolved_path": "",
                "message": str(message),
                "message_key": localized_key(message),
                "message_params": localized_params(message),
            }

    def prepare_tool_download(self, download_mgr, options: dict[str, Any] | None = None) -> dict[str, Any]:
        if platform.system() != "Windows":
            raise TextureOptError("当前自动下载工具链仅支持 Windows 平台。")

        merged_options = self._build_options(options)
        status = self.get_backend_status(merged_options)
        if status["available"]: return {"already_ready": True}

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
                download_start_message=tr("tasks.texture.tool_download_start", "开始下载 todds 工具包"),
                install_start_message=tr("tasks.texture.tool_install_start", "todds 工具包获取成功，正在解压..."),
                success_toast=tr("toast.texture.tool_download_done", "贴图工具下载完成: {path}", path=str(texture_tools_path)),
                failure_toast=tr("toast.texture.tool_download_failed", "贴图工具下载失败"),
            ),
        )
        return {"already_ready": False}

    def analyze_mods(
        self,
        mod_targets: list[dict[str, Any]] | list[str],
        options: dict[str, Any] | None = None,
        task_id: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        normalized_targets = self._normalize_mod_targets(mod_targets)
        if not normalized_targets:
            raise TextureOptError("没有可分析的 Mod 路径")

        analysis_task_id = task_id or uuid.uuid4().hex
        merged_options = self._build_options(options)
        tool_status = self.get_backend_status(merged_options)
        summary, mods = self._scan_mods(
            normalized_targets,
            merged_options,
            cancel_event,
            analysis_task_id=analysis_task_id,
        )
        scan_failed = int(summary.get("scan_failed_count", 0) or 0)
        elapsed_ms = max(0, current_ms() - int(self._analysis_started_at.get(analysis_task_id, current_ms())))
        self._emit_analysis_progress(
            analysis_task_id,
            status="failed" if scan_failed > 0 else "success",
            progress=100,
            message=(
                tr(
                    "tasks.texture.analysis_completed_with_failed",
                    "统计完成，{failed_count} 个模组扫描失败，用时 {elapsed}",
                    {"failed_count": scan_failed, "elapsed": self._format_elapsed_ms(elapsed_ms)},
                )
                if scan_failed > 0
                else tr("tasks.texture.analysis_completed_elapsed", "统计完成，用时 {elapsed}", {"elapsed": self._format_elapsed_ms(elapsed_ms)})
            ),
            user_message=(
                tr(
                    "tasks.texture.analysis_completed_with_failed",
                    "统计完成，{failed_count} 个模组扫描失败，用时 {elapsed}",
                    {"failed_count": scan_failed, "elapsed": self._format_elapsed_ms(elapsed_ms)},
                )
                if scan_failed > 0
                else None
            ),
            processed_mods=len(normalized_targets),
            total_mods=len(normalized_targets),
            summary=summary,
            final_mods=mods,
        )
        return {
            "task_id": analysis_task_id,
            "tool_status": tool_status,
            "summary": summary,
            "mods": mods,
            "options": merged_options,
            "mod_targets": [dict(item) for item in normalized_targets],
            "generated_at": current_ms(),
        }

    def _run_task(self, task: TextureTask) -> None:
        try:
            self._set_task_state(task, status="running", message=tr("tasks.texture.queue_running", "正在执行贴图队列..."))
            summary = self._clean_generated(task) if task.action == "clean_generated" else self._optimize(task)
            success_message = str(summary.pop("message", "贴图优化任务完成"))
            final_status = str(summary.pop("final_status", "success") or "success")
            final_summary = summary.pop("final_summary", None)
            final_mods = summary.pop("final_mods", None)
            refresh_after_analyze = bool(summary.pop("refresh_after_analyze", True))
            failed_count = int(summary.get("failed_count", 0) or 0)
            if failed_count <= 0:
                failed_count = sum(int(summary.get(key, 0) or 0) for key in ("failed", "scan_failed", "delete_failed"))
            summary["failed_count"] = failed_count
            elapsed_ms = max(0, current_ms() - int(task.created_at))
            metrics = self._build_metrics(summary)
            if isinstance(final_summary, dict):
                metrics["summary"] = final_summary
            if isinstance(final_mods, list):
                metrics["final_mods"] = final_mods
            failed_items = summary.get("failed_items")
            if isinstance(failed_items, list) and failed_items:
                metrics["failed_items"] = failed_items
            if self._last_todds_log_path:
                metrics["todds_log_path"] = self._last_todds_log_path
            result_path = ""
            if isinstance(final_summary, dict) and isinstance(final_mods, list):
                write_metrics = {key: value for key, value in metrics.items() if key != "final_mods"}
                self._emit_progress(
                    task,
                    status="running",
                    progress=max(int(task.progress or 0), 99),
                    message=tr("tasks.texture.write_result", "写入任务结果"),
                    metrics={
                        **write_metrics,
                        "phase": "finalize",
                        "phase_label": "收尾阶段",
                        "phase_percent": 90,
                        "phase_done": 3,
                        "phase_total": 3,
                        "phase_unit": "步",
                        "refresh_after_analyze": refresh_after_analyze,
                    },
                )
                try:
                    result_path = self._write_task_result_file(
                        task,
                        task.options,
                        final_summary,
                        final_mods,
                        failed_items if isinstance(failed_items, list) else [],
                        failed_count,
                    )
                    metrics["result_path"] = result_path
                except OSError as exc:
                    logger.warning("写入贴图优化任务结果失败：task_id=%s error=%s", task.id, exc)
                    metrics["result_write_failed"] = True
                    metrics["result_write_error"] = str(exc)
                    success_message = f"{success_message}，{tr('tasks.texture.result_write_failed', '结果记录写入失败')}"
            if task.action == "optimize":
                metrics["phase"] = "finalize"
                metrics["phase_label"] = "收尾阶段"
                metrics["phase_percent"] = 100
                metrics["phase_done"] = 3
                metrics["phase_total"] = 3
                metrics["phase_unit"] = "步"
            metrics["refresh_after_analyze"] = refresh_after_analyze
            metrics["elapsed_ms"] = elapsed_ms
            self._set_task_state(
                task,
                status=final_status,
                progress=100,
                message=tr("tasks.texture.completed_elapsed", "{message}，用时 {elapsed}", {"message": success_message, "elapsed": self._format_elapsed_ms(elapsed_ms)}),
                summary=summary,
                metrics=metrics,
            )
        except TextureOptCancelled:
            logger.warning("贴图优化任务已取消：id=%s action=%s", task.id, task.action)
            self._set_task_state(task, status="cancelled", message=tr("tasks.texture.cancelled", "贴图优化任务已取消"), error="")
        except Exception:
            logger.error("贴图优化任务失败", exc_info=True)
            failed_message = tr("tasks.texture.failed", "贴图优化失败。请检查工具配置、贴图文件和输出目录权限后重试。")
            self._set_task_state(task, status="failed", message=tr("tasks.texture.failed_title", "贴图优化失败"), error=failed_message)

    def _optimize(self, task: TextureTask) -> dict[str, Any]:
        options = self._build_options(task.options)
        task.options = options
        self._last_todds_log_path = ""
        encoder = ToddsEncoder(options)
        scan_results = self._scan_targets_for_optimize(task, options)
        final_mods_by_path = {str(item["mod_path"]): dict(item["stat"]) for item in scan_results}
        entries_by_mod_path = {str(item["mod_path"]): list(item["entries"]) for item in scan_results}
        output_stats_by_mod_path = {
            str(item["mod_path"]): dict(item.get("output_stats") or {})
            for item in scan_results
        }
        all_entries = [entry for item in scan_results for entry in item["entries"]]
        batches = self._build_encode_batches(all_entries)
        total_pending = sum(len(batch["entries"]) for batch in batches)
        skipped = self._count_skipped_entries(all_entries, options)
        optimized = 0
        failed = 0
        successful_entries: list[dict[str, Any]] = []
        successful_mod_paths: set[str] = set()
        scan_failed_items = [
            {
                "package_id": str(item.get("stat", {}).get("package_id") or ""),
                "mod_path": str(item.get("mod_path") or ""),
                "mod_name": str(item.get("mod_name") or item.get("stat", {}).get("mod_name") or ""),
                "rel_path": "",
                "error": str(item.get("stat", {}).get("last_error") or "扫描失败"),
                "todds_log_path": "",
            }
            for item in scan_results
            if str(item.get("stat", {}).get("scan_status") or "") == "failed"
        ]
        scan_failed = len(scan_failed_items)
        failed_items: list[dict[str, Any]] = scan_failed_items[:20]
        retry_candidates: list[tuple[dict[str, Any], bool, int | None]] = []
        zstd_output_mode = self._is_zstd_output_mode(options)
        zstd_clean_old_dds = bool(options.get("zstd_clean_old_dds", False))
        output_label = "ZSTD" if zstd_output_mode else "DDS"
        if zstd_output_mode:
            for batch in batches:
                for entry in batch["entries"]:
                    source_text = str(entry.get("source_path") or "")
                    entry["zstd_had_dds_before_task"] = bool(source_text and Path(source_text).with_suffix(TEXTURE_OUTPUT_DDS_EXT).exists())

        def is_recoverable_encode_error(exc: Exception) -> bool:
            if not isinstance(exc, TextureOptError):
                return False
            message = str(exc or "")
            return message.startswith("todds 执行失败") or message.startswith("todds 执行超时")

        def remember_failed_entry(entry: dict[str, Any], exc: Exception) -> None:
            logger.warning("贴图条目处理失败：rel_path=%s error=%s", entry.get("rel_path"), exc)
            error_text = str(exc or "").strip() or str(tr("tasks.texture.item_failed", "贴图处理失败。请检查贴图文件、工具配置和输出目录权限。"))
            entry["last_error"] = error_text
            if len(failed_items) < 20:
                failed_items.append(
                    {
                        "package_id": str(entry.get("package_id") or ""),
                        "mod_path": str(entry.get("mod_path") or ""),
                        "mod_name": str(entry.get("mod_name") or ""),
                        "rel_path": str(entry.get("rel_path") or ""),
                        "error": error_text,
                        "todds_log_path": self._last_todds_log_path,
                    }
                )

        def queue_retry_entry(entry: dict[str, Any], *, overwrite_existing: bool, scale_percent: int | None) -> None:
            retry_candidates.append((entry, overwrite_existing, scale_percent))

        def refresh_mod_stats(mod_paths: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            for mod_path in mod_paths:
                entries = entries_by_mod_path.get(mod_path, [])
                mod_name = str(entries[0].get("mod_name") or Path(mod_path).name) if entries else Path(mod_path).name
                final_mods_by_path[mod_path] = self._build_mod_stat(
                    mod_path,
                    mod_name,
                    entries,
                    output_stats_by_mod_path.get(mod_path, {}),
                )
            return self._compose_progress_snapshot(task.mod_paths, final_mods_by_path)

        def encode_phase_percent(done: int) -> int:
            if total_pending <= 0:
                return 0
            return min(99, int((done / total_pending) * 100))

        def run_encode_batch(
            entries: list[dict[str, Any]],
            *,
            overwrite_existing: bool,
            scale_percent: int | None,
            output_callback: Callable[[str], None] | None = None,
        ) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], Exception]]]:
            failed_pairs: list[tuple[dict[str, Any], Exception]] = []
            process_entries = entries
            backups: dict[str, tuple[dict[str, Any], Path, Path]] = {}
            if zstd_output_mode:
                backups, failed_pairs = self._prepare_zstd_dds_backups(entries)
                failed_ids = {id(entry) for entry, _exc in failed_pairs}
                process_entries = [entry for entry in entries if id(entry) not in failed_ids]
            source_paths = [str(entry.get("source_path") or "") for entry in process_entries]
            if not source_paths:
                return [], failed_pairs
            try:
                encoder.encode_batch(
                    task._cancel_event,
                    overwrite_existing=True if zstd_output_mode else overwrite_existing,
                    source_paths=source_paths,
                    scale_percent=scale_percent,
                    max_size=0,
                    output_callback=output_callback,
                )
                if zstd_output_mode:
                    successful_entries, finalize_failed_pairs = self._finalize_zstd_batch_results(process_entries)
                    failed_pairs.extend(finalize_failed_pairs)
                    successful_dds_keys = {
                        os.path.normcase(str(Path(str(entry.get("source_path") or "")).with_suffix(TEXTURE_OUTPUT_DDS_EXT).resolve()))
                        for entry in successful_entries
                        if str(entry.get("source_path") or "")
                    }
                    failed_pairs.extend(self._cleanup_generated_zstd_dds(process_entries, backups))
                    failed_pairs.extend(self._restore_zstd_dds_backups(
                        backups,
                        keep_old_dds=not zstd_clean_old_dds,
                        successful_dds_keys=successful_dds_keys,
                    ))
                    failed_ids = {id(entry) for entry, _exc in failed_pairs}
                    successful_entries = [entry for entry in successful_entries if id(entry) not in failed_ids]
                    successful_entries, verify_failed_pairs = self._verify_generated_entries(
                        successful_entries,
                        must_change=True,
                        output_stats_by_mod=output_stats_by_mod_path,
                    )
                    failed_pairs.extend(verify_failed_pairs)
                    failed_by_entry: dict[int, tuple[dict[str, Any], Exception]] = {}
                    for failed_entry, entry_error in failed_pairs:
                        failed_by_entry.setdefault(id(failed_entry), (failed_entry, entry_error))
                    successful_entries = [entry for entry in successful_entries if id(entry) not in failed_by_entry]
                    return successful_entries, list(failed_by_entry.values())
                successful_entries, verify_failed_pairs = self._verify_generated_entries(
                    process_entries,
                    must_change=overwrite_existing,
                    output_stats_by_mod=output_stats_by_mod_path,
                )
                failed_pairs.extend(verify_failed_pairs)
                return successful_entries, failed_pairs
            except Exception:
                if zstd_output_mode:
                    self._cleanup_generated_zstd_dds(process_entries, backups)
                    self._restore_zstd_dds_backups(backups, keep_old_dds=True)
                raise

        final_summary, final_mods = self._compose_progress_snapshot(task.mod_paths, final_mods_by_path)
        self._emit_progress(
            task,
            status="running",
            progress=25,
            message=tr("tasks.texture.encode_start", "开始生成 {output_label}", {"output_label": output_label}),
            metrics={
                "done": 0,
                "total": total_pending,
                "optimized": 0,
                "skipped": skipped,
                "failed": 0,
                "phase": "encode",
                "phase_label": "生成阶段",
                "phase_percent": 0,
                "phase_done": 0,
                "phase_total": total_pending,
                "phase_unit": "张",
                "summary": final_summary,
                "final_mods": final_mods,
                "refresh_after_analyze": False,
            },
        )

        for batch_index, batch in enumerate(batches, start=1):
            if task._cancel_event.is_set():
                raise TextureOptCancelled("DDS 生成任务已取消")
            batch_size = len(batch["entries"])
            batch_completed_base = optimized + failed
            last_batch_progress = 0
            batch_total_hint = batch_size
            last_live_emit_at = 0.0
            scale_percent = batch.get("scale_percent")
            scale_label = f"{int(scale_percent)}%" if scale_percent is not None else "原尺寸"

            def handle_todds_output(line: str) -> None:
                nonlocal last_batch_progress, batch_total_hint, last_live_emit_at
                match = TODDS_PROGRESS_PATTERN.search(str(line or ""))
                if not match:
                    return
                current = max(0, int(match.group(1)))
                total = max(1, int(match.group(2)))
                batch_total_hint = total
                current = min(current, batch_size)
                if current <= last_batch_progress:
                    return
                now = time.monotonic()
                if current < batch_size and (now - last_live_emit_at) < TEXTURE_PROGRESS_EMIT_INTERVAL_SECONDS:
                    return
                last_batch_progress = current
                last_live_emit_at = now
                cumulative_done = batch_completed_base + current
                batch_finishing = current >= batch_size
                self._emit_progress(
                    task,
                    status="running",
                    progress=min(90, max(25, 25 + int((cumulative_done / max(1, total_pending)) * 65))),
                    message=(
                        tr(
                            "tasks.texture.encode_batch_wait",
                            "等待 todds 完成本批写入: 第 {batch_index}/{batch_total} 批 ({scale_label})",
                            {"batch_index": batch_index, "batch_total": max(1, len(batches)), "scale_label": scale_label},
                        )
                        if batch_finishing
                        else tr(
                            "tasks.texture.encode_batch",
                            "生成 {output_label}: 第 {batch_index}/{batch_total} 批 ({scale_label})",
                            {"output_label": output_label, "batch_index": batch_index, "batch_total": max(1, len(batches)), "scale_label": scale_label},
                        )
                    ),
                    metrics={
                        "done": cumulative_done,
                        "total": total_pending,
                        "optimized": optimized + current,
                        "skipped": skipped,
                        "failed": failed,
                        "phase": "encode_wait" if batch_finishing else "encode",
                        "phase_label": "批次收尾" if batch_finishing else "生成阶段",
                        "phase_percent": encode_phase_percent(cumulative_done),
                        "phase_done": cumulative_done,
                        "phase_total": total_pending,
                        "phase_unit": "张",
                        "current_batch_index": batch_index,
                        "current_batch_total": len(batches),
                        "current_batch_size": batch_size,
                        "current_batch_scale": scale_percent,
                        "current_batch_done": current,
                        "current_batch_progress_total": max(batch_total_hint, batch_size),
                        "refresh_after_analyze": False,
                    },
                )

            try:
                batch_successful_entries, batch_failed_pairs = run_encode_batch(
                    batch["entries"],
                    overwrite_existing=bool(batch["overwrite_existing"]),
                    scale_percent=batch["scale_percent"],
                    output_callback=handle_todds_output,
                )
            except TextureOptCancelled:
                raise
            except Exception as exc:
                self._remember_todds_log_path(exc)
                if not is_recoverable_encode_error(exc):
                    raise
                already_done: list[dict[str, Any]] = []
                if not zstd_output_mode:
                    already_done, _verify_failed_pairs = self._verify_generated_entries(
                        batch["entries"],
                        must_change=bool(batch["overwrite_existing"]),
                        output_stats_by_mod=output_stats_by_mod_path,
                    )
                    if already_done:
                        optimized += len(already_done)
                        successful_entries.extend(already_done)
                        successful_mod_paths.update(
                            str(entry.get("mod_path") or "")
                            for entry in already_done
                            if str(entry.get("mod_path") or "")
                        )
                done_ids = {id(entry) for entry in already_done}
                pending_retry_count = len(batch["entries"]) - len(done_ids)
                logger.warning("贴图批次进入重试：count=%s scale=%s error=%s", pending_retry_count, batch["scale_percent"], exc)
                for entry in batch["entries"]:
                    if id(entry) not in done_ids:
                        queue_retry_entry(entry, overwrite_existing=bool(batch["overwrite_existing"]), scale_percent=batch["scale_percent"])
            else:
                batch_done = batch_completed_base + batch_size
                self._emit_progress(
                    task,
                    status="running",
                    progress=min(95, max(25, 25 + int((batch_done / max(1, total_pending)) * 65))),
                    message=tr(
                        "tasks.texture.encode_record_batch",
                        "登记生成结果: 第 {batch_index}/{batch_total} 批 ({scale_label})",
                        {"batch_index": batch_index, "batch_total": max(1, len(batches)), "scale_label": scale_label},
                    ),
                    metrics={
                        "done": batch_completed_base,
                        "total": total_pending,
                        "optimized": optimized,
                        "skipped": skipped,
                        "failed": failed,
                        "phase": "record",
                        "phase_label": "登记阶段",
                        "phase_percent": min(99, int((batch_index / max(1, len(batches))) * 100)),
                        "phase_done": batch_index,
                        "phase_total": len(batches),
                        "phase_unit": "批",
                        "current_batch_index": batch_index,
                        "current_batch_total": len(batches),
                        "current_batch_size": batch_size,
                        "current_batch_scale": scale_percent,
                        "refresh_after_analyze": False,
                    },
                )
                for entry, _entry_error in batch_failed_pairs:
                    queue_retry_entry(entry, overwrite_existing=bool(batch["overwrite_existing"]), scale_percent=batch["scale_percent"])
                if batch_failed_pairs:
                    logger.warning(
                        "贴图批次存在未确认结果，进入重试：count=%s scale=%s first_error=%s",
                        len(batch_failed_pairs),
                        batch["scale_percent"],
                        batch_failed_pairs[0][1],
                    )
                optimized += len(batch_successful_entries)
                successful_entries.extend(batch_successful_entries)
                successful_mod_paths.update(
                    str(entry.get("mod_path") or "")
                    for entry in batch_successful_entries
                    if str(entry.get("mod_path") or "")
                )

            processed_done = optimized + failed
            self._emit_progress(
                task,
                status="running",
                progress=min(90, max(25, 25 + int((processed_done / max(1, total_pending)) * 65))),
                message=tr(
                    "tasks.texture.encode_batch",
                    "生成 {output_label}: 第 {batch_index}/{batch_total} 批 ({scale_label})",
                    {"output_label": output_label, "batch_index": batch_index, "batch_total": max(1, len(batches)), "scale_label": scale_label},
                ),
                metrics={
                    "done": processed_done,
                    "total": total_pending,
                    "optimized": optimized,
                    "skipped": skipped,
                    "failed": failed,
                    "phase": "encode",
                    "phase_label": "生成阶段",
                    "phase_percent": encode_phase_percent(processed_done),
                    "phase_done": processed_done,
                    "phase_total": total_pending,
                    "phase_unit": "张",
                    "current_batch_index": batch_index,
                    "current_batch_total": len(batches),
                    "current_batch_size": batch_size,
                    "current_batch_scale": scale_percent,
                    "current_batch_done": batch_size if processed_done >= batch_completed_base + batch_size else last_batch_progress,
                    "current_batch_progress_total": max(batch_total_hint, batch_size),
                    "refresh_after_analyze": False,
                },
            )

        retry_done = 0
        if retry_candidates:
            self._emit_progress(
                task,
                status="running",
                progress=90,
                message=tr("tasks.texture.retry_start", "主批次完成，开始统一重试可恢复失败项"),
                metrics={
                    "done": optimized + failed,
                    "total": total_pending,
                    "optimized": optimized,
                    "skipped": skipped,
                    "failed": failed,
                    "phase": "retry",
                    "phase_label": "重试阶段",
                    "phase_percent": 0,
                    "phase_done": 0,
                    "phase_total": len(retry_candidates),
                    "phase_unit": "张",
                    "refresh_after_analyze": False,
                },
            )
            grouped_retries: dict[tuple[bool, int | None], list[dict[str, Any]]] = {}
            for entry, overwrite_existing, retry_scale_percent in retry_candidates:
                grouped_retries.setdefault((overwrite_existing, retry_scale_percent), []).append(entry)

            retry_batches: list[tuple[list[dict[str, Any]], bool, int | None]] = []
            for (overwrite_existing, retry_scale_percent), grouped_entries in grouped_retries.items():
                for offset in range(0, len(grouped_entries), TEXTURE_RETRY_BATCH_SIZE):
                    retry_batches.append((grouped_entries[offset : offset + TEXTURE_RETRY_BATCH_SIZE], overwrite_existing, retry_scale_percent))

            for retry_entries, overwrite_existing, retry_scale_percent in retry_batches:
                if task._cancel_event.is_set():
                    raise TextureOptCancelled("DDS 生成任务已取消")
                single_retry_entries: list[dict[str, Any]] = []
                try:
                    retry_successful_entries, retry_failed_pairs = run_encode_batch(
                        retry_entries,
                        overwrite_existing=overwrite_existing,
                        scale_percent=retry_scale_percent,
                    )
                except TextureOptCancelled:
                    raise
                except Exception as exc:
                    self._remember_todds_log_path(exc)
                    if not is_recoverable_encode_error(exc):
                        raise
                    single_retry_entries = retry_entries
                else:
                    optimized += len(retry_successful_entries)
                    retry_done += len(retry_successful_entries)
                    successful_entries.extend(retry_successful_entries)
                    successful_mod_paths.update(
                        str(successful_entry.get("mod_path") or "")
                        for successful_entry in retry_successful_entries
                        if str(successful_entry.get("mod_path") or "")
                    )
                    single_retry_entries = [failed_entry for failed_entry, _entry_error in retry_failed_pairs]

                process_failures = 0
                last_process_error: Exception | None = None
                for entry in single_retry_entries:
                    if task._cancel_event.is_set():
                        raise TextureOptCancelled("DDS 生成任务已取消")
                    try:
                        single_successes, single_failures = run_encode_batch(
                            [entry],
                            overwrite_existing=overwrite_existing,
                            scale_percent=retry_scale_percent,
                        )
                    except TextureOptCancelled:
                        raise
                    except Exception as exc:
                        self._remember_todds_log_path(exc)
                        if not is_recoverable_encode_error(exc):
                            raise
                        process_failures += 1
                        last_process_error = exc
                        failed += 1
                        retry_done += 1
                        remember_failed_entry(entry, exc)
                    else:
                        for failed_entry, entry_error in single_failures:
                            failed += 1
                            retry_done += 1
                            remember_failed_entry(failed_entry, entry_error)
                        optimized += len(single_successes)
                        retry_done += len(single_successes)
                        successful_entries.extend(single_successes)
                        successful_mod_paths.update(
                            str(successful_entry.get("mod_path") or "")
                            for successful_entry in single_successes
                            if str(successful_entry.get("mod_path") or "")
                        )

                # 整个重试子批次都出现相同层级的进程失败时，继续启动后续进程只会重复失败。
                if len(single_retry_entries) > 1 and process_failures == len(single_retry_entries) and last_process_error is not None:
                    raise last_process_error
                self._emit_progress(
                    task,
                    status="running",
                    progress=min(95, 90 + int((retry_done / max(1, len(retry_candidates))) * 5)),
                    message=tr("tasks.texture.retry_recoverable", "统一重试可恢复失败项"),
                    metrics={
                        "done": optimized + failed,
                        "total": total_pending,
                        "optimized": optimized,
                        "skipped": skipped,
                        "failed": failed,
                        "phase": "retry",
                        "phase_label": "重试阶段",
                        "phase_percent": int((retry_done / max(1, len(retry_candidates))) * 100),
                        "phase_done": retry_done,
                        "phase_total": len(retry_candidates),
                        "phase_unit": "张",
                        "refresh_after_analyze": False,
                    },
                )

        if successful_entries:
            self._emit_progress(
                task,
                status="running",
                progress=96,
                message=tr("tasks.texture.update_encode_state", "更新生成状态"),
                metrics={
                    "done": optimized + failed,
                    "total": total_pending,
                    "optimized": optimized,
                    "skipped": skipped,
                    "failed": failed,
                    "phase": "finalize",
                    "phase_label": "收尾阶段",
                    "phase_percent": 35,
                    "phase_done": 1,
                    "phase_total": 3,
                    "phase_unit": "步",
                    "refresh_after_analyze": False,
                },
            )
            self._emit_progress(
                task,
                status="running",
                progress=98,
                message=tr("tasks.texture.summarize_encode_result", "统计生成结果"),
                metrics={
                    "done": optimized + failed,
                    "total": total_pending,
                    "optimized": optimized,
                    "skipped": skipped,
                    "failed": failed,
                    "phase": "finalize",
                    "phase_label": "收尾阶段",
                    "phase_percent": 70,
                    "phase_done": 2,
                    "phase_total": 3,
                    "phase_unit": "步",
                    "refresh_after_analyze": False,
                },
            )
            final_summary, final_mods = refresh_mod_stats(successful_mod_paths)
        else:
            final_summary, final_mods = self._compose_progress_snapshot(task.mod_paths, final_mods_by_path)
        message_parts = [
            part
            for part in [
                self._format_scale_counts(final_summary),
                f"失败 {failed} 张" if failed > 0 else "",
                f"扫描失败 {scan_failed} 个" if scan_failed > 0 else "",
            ]
            if part
        ]
        return {
            "optimized": optimized,
            "skipped": skipped,
            "failed": failed,
            "scan_failed": scan_failed,
            "failed_count": failed + scan_failed,
            "failed_items": failed_items,
            "final_status": "failed" if failed > 0 or scan_failed > 0 else "success",
            "preexisting_dds": int(final_summary.get("current_output_count", 0)),
            "orphan_deleted": 0,
            "total_jobs": len(task.mod_paths),
            "output_format": str(options.get("output_format") or "dds"),
            "final_summary": final_summary,
            "final_mods": final_mods,
            "refresh_after_analyze": False,
            "message": tr(
                "tasks.texture.encode_completed",
                "{output_label} 生成完成{details}",
                {"output_label": output_label, "details": f"，{', '.join(message_parts)}" if message_parts else ""},
            ),
        }

    @staticmethod
    def _zstd_backup_path(dds_path: Path) -> Path:
        return dds_path.with_name(f"{dds_path.name}.zstd-backup-{uuid.uuid4().hex}")

    @classmethod
    def _run_zstd_file_operation(cls, operation: Callable[[], Any], *, action: str, path: Path) -> None:
        for attempt in range(len(ZSTD_COMPRESS_RETRY_DELAYS_SECONDS) + 1):
            try:
                operation()
                return
            except OSError as exc:
                if attempt >= len(ZSTD_COMPRESS_RETRY_DELAYS_SECONDS) or not cls._is_retryable_zstd_io_error(exc):
                    raise
                logger.warning("贴图 zstd 文件操作失败，准备重试：action=%s path=%s attempt=%s error=%s", action, path, attempt + 1, exc)
                time.sleep(ZSTD_COMPRESS_RETRY_DELAYS_SECONDS[attempt])

    def _prepare_zstd_dds_backups(self, entries: list[dict[str, Any]]) -> tuple[dict[str, tuple[dict[str, Any], Path, Path]], list[tuple[dict[str, Any], Exception]]]:
        backups: dict[str, tuple[dict[str, Any], Path, Path]] = {}
        failed_pairs: list[tuple[dict[str, Any], Exception]] = []
        seen_paths: set[str] = set()
        for entry in entries:
            source_text = str(entry.get("source_path") or "")
            if not source_text:
                continue
            try:
                source_path = Path(source_text)
                dds_path = source_path.with_suffix(TEXTURE_OUTPUT_DDS_EXT)
                path_key = os.path.normcase(str(dds_path.resolve()))
                if path_key in seen_paths:
                    continue
                seen_paths.add(path_key)
                existing_backup_text = str(entry.get("zstd_backup_path") or "")
                existing_backup = Path(existing_backup_text) if existing_backup_text else None
                if existing_backup and existing_backup.exists():
                    if dds_path.exists():
                        self._run_zstd_file_operation(lambda: dds_path.unlink(missing_ok=True), action="cleanup_retry_dds", path=dds_path)
                    backups[path_key] = (entry, dds_path, existing_backup)
                    continue
                entry.pop("zstd_backup_path", None)
                if not dds_path.exists():
                    continue
                if not bool(entry.get("zstd_had_dds_before_task")):
                    self._run_zstd_file_operation(lambda: dds_path.unlink(missing_ok=True), action="cleanup_generated_dds", path=dds_path)
                    continue
                backup_path = self._zstd_backup_path(dds_path)
                self._run_zstd_file_operation(lambda: dds_path.replace(backup_path), action="backup_old_dds", path=dds_path)
                entry["zstd_backup_path"] = str(backup_path)
                backups[path_key] = (entry, dds_path, backup_path)
            except OSError as exc:
                error = TextureOptError(f"准备 ZSTD 临时文件失败: {source_text}，{exc}")
                logger.warning("准备贴图 zstd DDS 备份失败：source=%s error=%s", source_text, exc)
                failed_pairs.append((entry, error))
        return backups, failed_pairs

    @classmethod
    def _cleanup_generated_zstd_dds(
        cls,
        entries: list[dict[str, Any]],
        backups: dict[str, tuple[dict[str, Any], Path, Path]],
    ) -> list[tuple[dict[str, Any], Exception]]:
        failed_pairs: list[tuple[dict[str, Any], Exception]] = []
        for entry in entries:
            source_text = str(entry.get("source_path") or "")
            if not source_text:
                continue
            dds_path = Path(source_text).with_suffix(TEXTURE_OUTPUT_DDS_EXT)
            try:
                path_key = os.path.normcase(str(dds_path.resolve()))
                if path_key not in backups and dds_path.exists():
                    cls._run_zstd_file_operation(lambda: dds_path.unlink(missing_ok=True), action="cleanup_generated_dds", path=dds_path)
            except OSError as exc:
                logger.warning("清理本次生成的临时 DDS 失败：dds=%s error=%s", dds_path, exc)
                failed_pairs.append((entry, TextureOptError(f"清理 ZSTD 临时 DDS 失败: {dds_path}，{exc}")))
        return failed_pairs

    @classmethod
    def _restore_zstd_dds_backups(
        cls,
        backups: dict[str, tuple[dict[str, Any], Path, Path]],
        *,
        keep_old_dds: bool,
        successful_dds_keys: set[str] | None = None,
    ) -> list[tuple[dict[str, Any], Exception]]:
        failed_pairs: list[tuple[dict[str, Any], Exception]] = []
        for entry, dds_path, backup_path in backups.values():
            try:
                restore_old = keep_old_dds
                if not restore_old and successful_dds_keys is not None:
                    try:
                        restore_old = os.path.normcase(str(dds_path.resolve())) not in successful_dds_keys
                    except OSError:
                        restore_old = True
                if restore_old:
                    if dds_path.exists():
                        cls._run_zstd_file_operation(lambda: dds_path.unlink(missing_ok=True), action="cleanup_generated_dds", path=dds_path)
                    if backup_path.exists():
                        cls._run_zstd_file_operation(lambda: backup_path.replace(dds_path), action="restore_old_dds", path=backup_path)
                elif backup_path.exists():
                    if dds_path.exists():
                        cls._run_zstd_file_operation(lambda: dds_path.unlink(missing_ok=True), action="cleanup_generated_dds", path=dds_path)
                    cls._run_zstd_file_operation(lambda: backup_path.unlink(missing_ok=True), action="remove_old_dds_backup", path=backup_path)
                entry.pop("zstd_backup_path", None)
            except OSError as exc:
                logger.warning("恢复贴图 zstd DDS 失败：dds=%s backup=%s error=%s", dds_path, backup_path, exc)
                failed_pairs.append((entry, TextureOptError(f"恢复原 DDS 失败: {dds_path}，{exc}")))
        return failed_pairs

    @staticmethod
    def _is_retryable_zstd_io_error(exc: OSError) -> bool:
        retryable_errno = {errno.EACCES, errno.EPERM, errno.EBUSY, errno.EAGAIN}
        retryable_winerror = {32, 33}  # Windows 文件共享/锁定冲突
        return getattr(exc, "errno", None) in retryable_errno or getattr(exc, "winerror", None) in retryable_winerror

    @staticmethod
    def _compress_dds_to_zstd(dds_path: Path, zstd_path: Path) -> int:
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise TextureOptError("当前环境缺少 zstandard，无法生成 ZSTD 贴图。") from exc
        compressor_class = getattr(zstd, "ZstdCompressor", None)
        if compressor_class is None:
            try:
                from zstandard.backend_c import ZstdCompressor as compressor_class
            except ImportError as exc:
                raise TextureOptError("当前 zstandard 安装不完整，无法生成 ZSTD 贴图。") from exc

        if not dds_path.exists():
            raise TextureOptError(f"todds 未生成临时 DDS，无法压缩为 ZSTD: {dds_path}")
        zstd_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = zstd_path.with_name(f"{zstd_path.name}.tmp-{uuid.uuid4().hex}")
        try:
            compressor = compressor_class(level=0)
            with dds_path.open("rb") as source, temp_path.open("wb") as target:
                compressor.copy_stream(source, target)
            temp_path.replace(zstd_path)
            return int(zstd_path.stat().st_size)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _verify_generated_entries(
        entries: list[dict[str, Any]],
        *,
        must_change: bool = False,
        output_stats_by_mod: dict[str, dict[str, dict[str, Any]]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], Exception]]]:
        successful_entries: list[dict[str, Any]] = []
        failed_pairs: list[tuple[dict[str, Any], Exception]] = []
        for entry in entries:
            output_text = str(entry.get("output_path") or "").strip()
            if not output_text:
                failed_pairs.append((entry, TextureOptError("生成结果缺少输出路径")))
                continue
            output_path = Path(output_text)
            try:
                output_stat = output_path.stat()
            except OSError as exc:
                failed_pairs.append((entry, TextureOptError(f"生成结果未写出: {output_path}，{exc}")))
                continue
            output_size = int(output_stat.st_size)
            if output_size <= 0:
                failed_pairs.append((entry, TextureOptError(f"生成结果为空: {output_path}")))
                continue
            output_mtime_ns = int(output_stat.st_mtime_ns)
            if must_change and bool(entry.get("output_exists")) and output_size == int(entry.get("output_size", 0) or 0) and output_mtime_ns == int(entry.get("output_mtime_ns", 0) or 0):
                failed_pairs.append((entry, TextureOptError(f"生成结果未更新: {output_path}")))
                continue
            entry["output_exists"] = True
            entry["output_size"] = output_size
            entry["output_mtime_ns"] = output_mtime_ns
            entry["needs_action"] = False
            entry["action_status"] = "up_to_date"
            mod_path = str(entry.get("mod_path") or "")
            output_rel_path = str(entry.get("output_rel_path") or "")
            if output_stats_by_mod is not None and mod_path and output_rel_path:
                output_stats_by_mod.setdefault(mod_path, {})[output_rel_path] = {
                    "path": str(output_path),
                    "size": output_size,
                    "mtime_ns": output_mtime_ns,
                    "format": TextureOptimizationManager._output_format_for_path(output_path),
                }
            successful_entries.append(entry)
        return successful_entries, failed_pairs

    def _finalize_zstd_batch_results(self, entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], Exception]]]:
        def compress_entry(entry: dict[str, Any]) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], Exception] | None]:
            source_text = str(entry.get("source_path") or "")
            if not source_text:
                return None, None
            source_path = Path(source_text)
            dds_path = source_path.with_suffix(TEXTURE_OUTPUT_DDS_EXT)
            zstd_path = source_path.with_suffix(TEXTURE_OUTPUT_ZSTD_EXT)
            # ZSTD 模式复用 todds 的 DDS 编码结果，再压缩成 Image Opt 可读取的同名文件。
            try:
                self._run_zstd_file_operation(lambda: self._compress_dds_to_zstd(dds_path, zstd_path), action="compress_zstd", path=zstd_path)
            except TextureOptError as exc:
                message = str(exc or "")
                if message.startswith("当前环境缺少 zstandard") or message.startswith("当前 zstandard 安装不完整"):
                    raise
                return None, (entry, exc)
            except OSError as exc:
                return None, (entry, TextureOptError(f"压缩 ZSTD 失败: {dds_path}，{exc}"))
            entry["output_path"] = str(zstd_path)
            entry["output_rel_path"] = str(PurePosixPath(str(entry.get("rel_path") or "")).with_suffix(TEXTURE_OUTPUT_ZSTD_EXT))
            entry["output_format"] = "zstd"
            return entry, None

        # 压缩器和临时文件按条目独立，使用少量线程并行可利用多核，同时避免过多并发争用磁盘。
        workers = max(1, min(len(entries), 4, os.cpu_count() or 1))
        if workers == 1:
            results = [compress_entry(entry) for entry in entries]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="TextureZstd") as executor:
                results = list(executor.map(compress_entry, entries))

        successful_entries = [entry for entry, _failure in results if entry is not None]
        failed_pairs = [failure for _entry, failure in results if failure is not None]
        return successful_entries, failed_pairs

    def _scan_targets_for_optimize(self, task: TextureTask, options: dict[str, Any]) -> list[dict[str, Any]]:
        plan = self._build_texture_plan(
            task.mod_targets,
            options,
            task._cancel_event,
            progress_task=task,
            progress_kind="optimize",
        )
        return list(plan["results"])

    def _build_texture_plan(
        self,
        mod_targets: list[dict[str, Any]] | list[str],
        options: dict[str, Any],
        cancel_event: threading.Event | None,
        *,
        progress_task: TextureTask | None = None,
        analysis_task_id: str | None = None,
        progress_kind: str = "analysis",
    ) -> dict[str, Any]:
        normalized_targets = self._normalize_mod_targets(mod_targets)
        ordered_paths = [str(target.get("mod_path") or "") for target in normalized_targets]
        total_mods = max(1, len(normalized_targets))
        workers = self._resolve_scan_workers(total_mods, options)
        scan_results: list[dict[str, Any] | None] = [None] * len(normalized_targets)
        partial_by_path: dict[str, dict[str, Any]] = {}
        excluded_indexes = self._build_exclusion_indexes()
        last_emit_at = 0.0

        def build_target_plan(target: dict[str, Any]) -> dict[str, Any]:
            if cancel_event and cancel_event.is_set():
                raise TextureOptCancelled("贴图扫描任务已取消")
            base_index = self._load_or_build_base_index(
                target,
                cancel_event=cancel_event,
            )
            if cancel_event and cancel_event.is_set():
                raise TextureOptCancelled("贴图扫描任务已取消")
            result = self._project_mod_index(
                base_index,
                options,
                apply_exclusions=True,
                excluded_indexes=excluded_indexes,
            )
            return result

        def emit_plan_progress(result: dict[str, Any], completed: int, *, force: bool = False) -> None:
            nonlocal last_emit_at
            if not progress_task and not analysis_task_id:
                return
            now = time.monotonic()
            if not force and completed > 1 and completed < total_mods and (now - last_emit_at) < TEXTURE_PROGRESS_EMIT_INTERVAL_SECONDS:
                return
            last_emit_at = now
            partial_summary, _partial_mods = self._compose_progress_snapshot(ordered_paths, partial_by_path)
            phase_percent = int((completed / total_mods) * 100)
            stat = dict(result["stat"])
            if analysis_task_id:
                self._emit_analysis_progress(
                    analysis_task_id,
                    status="running",
                    progress=min(99, phase_percent),
                    message=tr("tasks.texture.scanned_mod", "已扫描 {mod_name}", {"mod_name": result["mod_name"]}),
                    processed_mods=completed,
                    total_mods=total_mods,
                    summary=partial_summary,
                    current_entry=stat,
                )
                return
            if progress_task:
                self._emit_progress(
                    progress_task,
                    status="running",
                    progress=min(24, max(1, int((completed / total_mods) * 24))),
                    message=(
                        tr("tasks.texture.prepare_generate_mod", "准备生成: {mod_name}", {"mod_name": result["mod_name"]})
                        if progress_kind == "optimize"
                        else tr("tasks.texture.scanned_mod", "已扫描 {mod_name}", {"mod_name": result["mod_name"]})
                    ),
                    metrics={
                        "done": completed,
                        "total": len(normalized_targets),
                        "optimized": 0,
                        "skipped": 0,
                        "failed": 0,
                        "phase": "prepare" if progress_kind == "optimize" else "scan",
                        "phase_label": "生成准备阶段" if progress_kind == "optimize" else "统计规划阶段",
                        "phase_percent": phase_percent,
                        "phase_done": completed,
                        "phase_total": total_mods,
                        "phase_unit": "模组",
                        "processed_mods": completed,
                        "total_mods": len(normalized_targets),
                        "current_mod_sources": len(result["entries"]),
                        "current_mod_pending": int(result["stat"].get("generate_required_count", 0)),
                        "summary": partial_summary,
                        "current_entry": stat,
                        "refresh_after_analyze": False,
                    },
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="TexturePlan") as executor:
            future_map = {
                executor.submit(build_target_plan, target): index
                for index, target in enumerate(normalized_targets)
            }
            completed = 0
            for future in concurrent.futures.as_completed(future_map):
                if cancel_event and cancel_event.is_set():
                    raise TextureOptCancelled("贴图扫描任务已取消")
                index = future_map[future]
                try:
                    result = future.result()
                except TextureOptCancelled:
                    raise
                except Exception as exc:
                    target = normalized_targets[index]
                    mod_path = str(target.get("mod_path") or "")
                    mod_name = str(target.get("mod_name") or Path(mod_path).name)
                    logger.warning("扫描贴图 Mod 失败：mod_path=%s error=%s", mod_path, exc)
                    stat = self._create_empty_stat(mod_path=mod_path, mod_name=mod_name)
                    stat["package_id"] = str(target.get("package_id") or "")
                    stat["store"] = self._normalize_store(target.get("store"))
                    stat["path_hash"] = str(target.get("path_hash") or generate_path_hash(mod_path))
                    stat["mod_instance_key"] = str(target.get("mod_instance_key") or stat["path_hash"]).strip()
                    stat["scan_status"] = "failed"
                    stat["scan_failed_count"] = 1
                    stat["last_error"] = str(exc or "").strip() or "扫描失败"
                    result = {"mod_path": mod_path, "mod_name": mod_name, "entries": [], "stat": stat, "output_stats": {}}
                scan_results[index] = result
                partial_by_path[str(result["mod_path"])] = dict(result["stat"])
                completed += 1
                emit_plan_progress(result, completed, force=completed == 1 or completed == total_mods)

        results = [result for result in scan_results if isinstance(result, dict)]
        stats_by_path = {str(result["mod_path"]): dict(result["stat"]) for result in results}
        summary, rows = self._compose_progress_snapshot(ordered_paths, stats_by_path)
        return {
            "targets": normalized_targets,
            "ordered_paths": ordered_paths,
            "summary": summary,
            "rows": rows,
            "results": results,
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

    def _clean_generated(self, task: TextureTask) -> dict[str, Any]:
        options = self._build_options(task.options)
        task.options = options
        residue_only = bool(options.get("clean_uninstalled_residue_only", False))
        clean_output_format = self._normalize_clean_output_format(options)
        clean_without_source = bool(options.get("clean_without_source", False))
        output_label = "ZSTD" if clean_output_format == "zstd" else "DDS"
        clean_target_label = (
            f"无源 {output_label}"
            if clean_without_source
            else (f"卸载残留 {output_label}" if residue_only else output_label)
        )
        deleted = 0
        checked = 0
        delete_failed = 0
        failed_items: list[dict[str, Any]] = []
        total_mods = max(1, len(task.mod_targets))
        last_emit_at = 0.0

        def remember_delete_failed(mod_target: dict[str, Any], output_path: Path, exc: OSError) -> None:
            mod_path = str(mod_target.get("mod_path") or "")
            mod_name = str(mod_target.get("mod_name") or Path(mod_path).name)
            try:
                rel_path = output_path.resolve().relative_to(Path(mod_path).resolve()).as_posix()
            except (OSError, ValueError):
                rel_path = output_path.name
            logger.warning("删除贴图清理输出失败：mod_path=%s rel_path=%s path=%s error=%s", mod_path, rel_path, output_path, exc)
            if len(failed_items) < 20:
                failed_items.append(
                    {
                        "package_id": str(mod_target.get("package_id") or ""),
                        "mod_path": mod_path,
                        "mod_name": mod_name,
                        "rel_path": rel_path,
                        "file_path": str(output_path),
                        "error": f"删除 {output_label} 失败: {output_path}，{exc}",
                        "todds_log_path": "",
                    }
                )

        def emit_clean_progress(index: int, mod_name: str, *, force: bool = False) -> None:
            nonlocal last_emit_at
            now = time.monotonic()
            if not force and (now - last_emit_at) < TEXTURE_PROGRESS_EMIT_INTERVAL_SECONDS:
                return
            last_emit_at = now
            phase_percent = min(99, int((max(0, index - 1) / total_mods) * 100))
            self._emit_progress(
                task,
                status="running",
                progress=max(1, min(99, phase_percent)),
                message=tr(
                    "tasks.texture.clean_progress",
                    "清理{target_label}: {mod_name}，已检查 {checked} 个，已删除 {deleted} 个",
                    {"target_label": clean_target_label, "mod_name": mod_name, "checked": checked, "deleted": deleted},
                ),
                metrics={
                    "checked_outputs": checked,
                    "orphan_deleted": deleted,
                    "delete_failed": delete_failed,
                    "total_mods": total_mods,
                    "processed_mods": max(0, index - 1),
                    "phase": "clean",
                    "phase_label": "清理阶段",
                    "phase_percent": phase_percent,
                    "phase_done": checked,
                    "phase_total": 0,
                    "phase_unit": "个",
                    "clean_uninstalled_residue_only": residue_only,
                    "clean_output_format": clean_output_format,
                    "clean_without_source": clean_without_source,
                    "refresh_after_analyze": clean_without_source,
                },
            )

        self._emit_progress(
            task,
            status="running",
            progress=1,
            message=tr("tasks.texture.clean_start", "开始清理{target_label}", {"target_label": clean_target_label}),
            metrics={
                "checked_outputs": 0,
                "orphan_deleted": 0,
                "delete_failed": 0,
                "total_mods": total_mods,
                "processed_mods": 0,
                "phase": "clean",
                "phase_label": "清理阶段",
                "phase_percent": 0,
                "phase_done": 0,
                "phase_total": 0,
                "phase_unit": "个",
                "clean_uninstalled_residue_only": residue_only,
                "clean_output_format": clean_output_format,
                "clean_without_source": clean_without_source,
                "refresh_after_analyze": clean_without_source,
            },
        )

        for index, mod_target in enumerate(task.mod_targets, start=1):
            mod_path = str(mod_target.get("mod_path") or "")
            mod_name = str(mod_target.get("mod_name") or Path(mod_path).name)
            if task._cancel_event.is_set():
                raise TextureOptCancelled("清理 DDS 任务已取消")
            emit_clean_progress(index, mod_name, force=True)
            if clean_without_source:
                targets = self._iter_texture_output_paths_without_source(
                    mod_path,
                    cancel_event=task._cancel_event,
                    output_format=clean_output_format,
                )
            elif bool(mod_target.get("requires_png_source", True)):
                targets = self._iter_texture_output_paths_with_source(
                    mod_path,
                    cancel_event=task._cancel_event,
                    output_format=clean_output_format,
                )
            else:
                targets = self._iter_texture_output_paths(mod_path, output_format=clean_output_format)
            for output_path in targets:
                if task._cancel_event.is_set():
                    raise TextureOptCancelled("清理 DDS 任务已取消")
                checked += 1
                if not output_path.exists():
                    emit_clean_progress(index, mod_name)
                    continue
                try:
                    output_path.unlink()
                    deleted += 1
                except OSError as exc:
                    delete_failed += 1
                    remember_delete_failed(mod_target, output_path, exc)
                emit_clean_progress(index, mod_name)
        self._emit_progress(
            task,
            status="running",
            progress=99,
            message=tr("tasks.texture.clean_finishing", "清理完成，正在结束任务"),
            metrics={
                "checked_outputs": checked,
                "orphan_deleted": deleted,
                "delete_failed": delete_failed,
                "total_mods": total_mods,
                "processed_mods": len(task.mod_targets),
                "phase": "finalize",
                "phase_label": "收尾阶段",
                "phase_percent": 90,
                "phase_done": checked,
                "phase_total": 0,
                "phase_unit": "个",
                "clean_uninstalled_residue_only": residue_only,
                "clean_output_format": clean_output_format,
                "clean_without_source": clean_without_source,
                "refresh_after_analyze": clean_without_source,
            },
        )
        clean_message = (
            tr(
                "tasks.texture.clean_completed_with_failed",
                "{target_label} 清理完成，已删除 {deleted} 个，失败 {failed} 个",
                {"target_label": clean_target_label, "deleted": deleted, "failed": delete_failed},
            )
            if delete_failed > 0
            else tr("tasks.texture.clean_completed", "{target_label} 清理完成", {"target_label": clean_target_label})
        )
        return {
            "optimized": 0,
            "skipped": 0,
            "failed": delete_failed,
            "failed_count": delete_failed,
            "failed_items": failed_items,
            "final_status": "failed" if delete_failed > 0 else "success",
            "preexisting_dds": 0,
            "orphan_deleted": deleted,
            "checked_outputs": checked,
            "delete_failed": delete_failed,
            "total_jobs": 0,
            "clean_output_format": clean_output_format,
            "clean_without_source": clean_without_source,
            "refresh_after_analyze": clean_without_source,
            "message": clean_message,
        }

    def _scan_mods(
        self,
        mod_targets: list[dict[str, Any]] | list[str],
        options: dict[str, Any],
        cancel_event: threading.Event | None,
        *,
        analysis_task_id: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        plan = self._build_texture_plan(
            mod_targets,
            options,
            cancel_event,
            analysis_task_id=analysis_task_id,
            progress_kind="analysis",
        )
        return dict(plan["summary"]), list(plan["rows"])

    def _load_or_build_base_index(
        self,
        target: dict[str, Any],
        *,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        cached = self._get_cached_base_scan(target)
        source_files: list[tuple[Path, str, os.stat_result]] | None = None
        if cached:
            source_files = self._collect_source_files(str(target.get("mod_path") or ""), cancel_event)
            current_signature = self._build_source_signature(
                [(rel_path, int(source_stat.st_size), int(source_stat.st_mtime_ns)) for _source, rel_path, source_stat in source_files]
            )
            if current_signature == str(cached.get("source_signature") or ""):
                return cached

        base_index = self._build_mod_base_index(target, cancel_event=cancel_event, source_files=source_files)
        self._store_base_scan_cache(base_index)
        return base_index

    def _build_mod_base_index(
        self,
        target: dict[str, Any],
        *,
        cancel_event: threading.Event | None = None,
        source_files: list[tuple[Path, str, os.stat_result]] | None = None,
    ) -> dict[str, Any]:
        mod_path = str(target.get("mod_path") or "")
        mod_name = str(target.get("mod_name") or Path(mod_path).name)
        package_id = normalize_package_id(target.get("package_id", ""))
        store = self._normalize_store(target.get("store"))
        path_hash = str(target.get("path_hash") or generate_path_hash(mod_path)).strip()
        mod_instance_key = str(target.get("mod_instance_key") or path_hash).strip()
        records: list[tuple[str, int, int]] = []
        base_entries: list[dict[str, Any]] = []
        if source_files is None:
            source_files = self._collect_source_files(mod_path, cancel_event)

        for source, rel_path, source_stat in source_files:
            if cancel_event and cancel_event.is_set():
                raise TextureOptCancelled("贴图扫描任务已取消")
            output_path = source.with_suffix(TEXTURE_OUTPUT_DDS_EXT)
            output_rel_path = str(PurePosixPath(rel_path).with_suffix(TEXTURE_OUTPUT_DDS_EXT))
            records.append((rel_path, int(source_stat.st_size), int(source_stat.st_mtime_ns)))
            entry = {
                "mod_path": mod_path,
                "mod_name": mod_name,
                "package_id": package_id,
                "store": store,
                "path_hash": path_hash,
                "mod_instance_key": mod_instance_key,
                "rel_path": rel_path,
                "source_path": str(source),
                "source_mtime_ns": int(source_stat.st_mtime_ns),
                "output_path": str(output_path),
                "output_rel_path": output_rel_path,
                "source_readable": False,
                "width": 0,
                "height": 0,
                "has_alpha": False,
                "source_size": int(source_stat.st_size),
                "source_vram": 0,
                "supported_scale_percents": (),
                "engine_unsupported": False,
                "engine_unsupported_reason": "",
            }
            try:
                capability = self._get_source_capability(source, source_stat)
            except Exception as exc:
                entry["engine_unsupported"] = True
                entry["engine_unsupported_reason"] = f"PNG 文件无法解析: {exc}"
                base_entries.append(entry)
                continue

            entry.update(
                {
                    "source_readable": True,
                    "width": int(capability.get("width", 0) or 0),
                    "height": int(capability.get("height", 0) or 0),
                    "has_alpha": bool(capability.get("has_alpha")),
                    "source_size": int(capability.get("source_size", 0) or 0),
                    "source_vram": int(capability.get("source_vram", 0) or 0),
                    "supported_scale_percents": tuple(capability.get("supported_scale_percents", ())),
                    "engine_unsupported": bool(capability.get("engine_unsupported")),
                    "engine_unsupported_reason": str(capability.get("engine_unsupported_reason") or ""),
                }
            )
            base_entries.append(entry)

        return {
            "mod_path": mod_path,
            "mod_name": mod_name,
            "package_id": package_id,
            "store": store,
            "path_hash": path_hash,
            "mod_instance_key": mod_instance_key,
            "source_signature": self._build_source_signature(records),
            "entries": base_entries,
        }

    def _project_mod_index(
        self,
        base_index: dict[str, Any],
        options: dict[str, Any],
        *,
        apply_exclusions: bool,
        excluded_indexes: tuple[set[str], set[tuple[str, str]]] | None = None,
    ) -> dict[str, Any]:
        mod_path = str(base_index.get("mod_path") or "")
        mod_name = str(base_index.get("mod_name") or Path(mod_path).name)
        output_stats = self._collect_output_stats(mod_path)
        process_mode = str(options.get("process_mode", "scaled_only_overwrite"))
        preferred_scale = self._get_scale_factor_percent(options)
        min_output_size = self._get_scale_target_size(options) if preferred_scale is not None else 0
        generate_mipmaps = bool(options.get("generate_mipmaps", True))
        scale_candidates = set(self._iter_scale_step_candidates(options)) if preferred_scale is not None else set()
        package_id = normalize_package_id(base_index.get("package_id", ""))
        if apply_exclusions and excluded_indexes is None:
            excluded_indexes = self._build_exclusion_indexes()
        excluded_mod_ids, excluded_file_keys = excluded_indexes if apply_exclusions and excluded_indexes is not None else (set(), set())
        entries: list[dict[str, Any]] = []

        for source_entry in base_index.get("entries", []):
            entry = dict(source_entry)
            source_path = Path(str(entry.get("source_path") or ""))
            output_path = self._source_output_path(source_path, options)
            entry["output_path"] = str(output_path)
            output_ext = TEXTURE_OUTPUT_ZSTD_EXT if self._is_zstd_output_mode(options) else TEXTURE_OUTPUT_DDS_EXT
            entry["output_rel_path"] = str(PurePosixPath(str(entry.get("rel_path") or "")).with_suffix(output_ext))
            entry["output_format"] = str(options.get("output_format") or "dds")
            output_rel = str(entry.get("output_rel_path") or "")
            output_info = output_stats.get(output_rel) or {}
            entry["output_exists"] = bool(output_info)
            entry["output_size"] = int(output_info.get("size", 0))
            entry["output_mtime_ns"] = int(output_info.get("mtime_ns", 0))
            entry["dds_vram"] = 0
            entry["small_skipped"] = False
            entry["needs_action"] = False
            entry["plan_kind"] = "keep_original"
            entry["plan_label"] = "不缩放"
            entry["scale_percent"] = None
            entry["action_status"] = "unreadable"
            entry["is_mask_source"] = str(entry.get("rel_path") or "").lower().endswith("_m.png")
            entry["package_id"] = package_id
            entry["excluded"] = False

            if not bool(entry.get("source_readable")):
                entries.append(entry)
                continue

            width = int(entry.get("width", 0) or 0)
            height = int(entry.get("height", 0) or 0)
            has_alpha = bool(entry.get("has_alpha"))
            oversize_or_small = self._is_outside_recommended_source_range(width, height, options)
            supported_scales = tuple(
                int(scale)
                for scale in entry.get("supported_scale_percents", ())
                if int(scale) in scale_candidates
            )
            scale_percent = None if preferred_scale is None or oversize_or_small else self._pick_scale_step_percent_from_supported(
                width,
                height,
                supported_scales,
                min_output_size,
            )
            if bool(entry.get("is_mask_source")):
                scale_percent = None

            entry["small_skipped"] = oversize_or_small
            entry["scale_percent"] = scale_percent
            if oversize_or_small:
                entry["plan_label"] = "超范围不缩放"
            if bool(entry.get("is_mask_source")):
                entry["plan_label"] = "遮罩贴图不缩放"
            is_excluded = apply_exclusions and (
                bool(package_id and package_id in excluded_mod_ids)
                or (
                    os.path.abspath(mod_path).lower(),
                    self._normalize_rel_path(str(entry.get("rel_path") or "")).lower(),
                ) in excluded_file_keys
            )
            entry["excluded"] = is_excluded
            if bool(entry.get("engine_unsupported")):
                entry["action_status"] = "unsupported"
                entries.append(entry)
                continue
            if is_excluded:
                entry["action_status"] = "excluded"
                entries.append(entry)
                continue
            if scale_percent is None:
                entry["dds_vram"] = self._estimate_dds_vram(
                    width,
                    height,
                    has_alpha,
                    None,
                    generate_mipmaps=generate_mipmaps,
                )
            else:
                entry["dds_vram"] = self._estimate_dds_vram(
                    width,
                    height,
                    has_alpha,
                    scale_percent,
                    generate_mipmaps=generate_mipmaps,
                )
                entry["plan_kind"] = "scaled" if scale_percent == preferred_scale else "fallback"
                entry["plan_label"] = f"{scale_percent}%"

            entry["needs_action"] = self._entry_needs_action(entry, process_mode)
            entry["overwrite_existing"] = process_mode != "all_skip_existing"
            if entry["needs_action"]:
                entry["action_status"] = "pending"
            elif bool(entry.get("output_exists")):
                entry["action_status"] = "up_to_date"
            else:
                entry["action_status"] = "no_output"
            entries.append(entry)

        stat = self._build_mod_stat(mod_path, mod_name, entries, output_stats)
        return {"mod_path": mod_path, "mod_name": mod_name, "entries": entries, "stat": stat, "output_stats": output_stats}

    @staticmethod
    def _entry_needs_action(entry: dict[str, Any], process_mode: str) -> bool:
        output_exists = bool(entry.get("output_exists"))
        scale_percent = entry.get("scale_percent")
        if process_mode == "all_skip_existing":
            return not output_exists
        if process_mode == "scaled_only_overwrite":
            if bool(entry.get("is_mask_source")):
                return True
            return scale_percent is not None
        return True

    @staticmethod
    def _count_skipped_entries(entries: list[dict[str, Any]], options: dict[str, Any]) -> int:
        skipped = 0
        for entry in entries:
            if not bool(entry.get("needs_action")):
                skipped += 1
        return skipped

    def _build_encode_batches(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[bool, int | None], dict[str, Any]] = {}
        for entry in entries:
            if not bool(entry.get("needs_action")):
                continue
            overwrite_existing = bool(entry.get("overwrite_existing", bool(entry.get("output_exists"))))
            batch_key = (overwrite_existing, entry.get("scale_percent"))
            batch = grouped.setdefault(
                batch_key,
                {
                    "overwrite_existing": overwrite_existing,
                    "scale_percent": entry.get("scale_percent"),
                    "entries": [],
                },
            )
            batch["entries"].append(entry)

        grouped_batches = list(grouped.values())
        grouped_batches.sort(
            key=lambda item: (
                item.get("scale_percent") is None,
                int(item.get("scale_percent") or 999),
                not bool(item.get("overwrite_existing")),
            )
        )
        batches: list[dict[str, Any]] = []
        for batch in grouped_batches:
            entries_batch = list(batch["entries"])
            for offset in range(0, len(entries_batch), TEXTURE_ENCODE_BATCH_SIZE):
                batches.append(
                    {
                        "overwrite_existing": bool(batch["overwrite_existing"]),
                        "scale_percent": batch["scale_percent"],
                        "entries": entries_batch[offset : offset + TEXTURE_ENCODE_BATCH_SIZE],
                    }
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
        stat["package_id"] = str(entries[0].get("package_id") or "") if entries else ""
        stat["store"] = str(entries[0].get("store") or "") if entries else ""
        stat["path_hash"] = str(entries[0].get("path_hash") or "") if entries else ""
        stat["mod_instance_key"] = str(entries[0].get("mod_instance_key") or stat["path_hash"] or "") if entries else ""
        stat["output_total_count"] = len(output_stats)
        stat["output_total_bytes"] = sum(int(item.get("size", 0)) for item in output_stats.values())
        for output_info in output_stats.values():
            output_format = str(output_info.get("format") or "")
            if output_format == "zstd":
                stat["zstd_output_count"] += 1
                stat["zstd_output_bytes"] += int(output_info.get("size", 0) or 0)
            elif output_format == "dds":
                stat["dds_output_count"] += 1
                stat["dds_output_bytes"] += int(output_info.get("size", 0) or 0)
        scale_buckets: dict[tuple[str, str], int] = {}
        seen_output_keys: set[str] = set()

        for entry in entries:
            output_rel = str(entry.get("output_rel_path") or "")
            output_size = int(entry.get("output_size", 0) or 0)
            source_rel_path = PurePosixPath(str(entry.get("rel_path") or ""))
            for output_ext in TEXTURE_OUTPUT_EXTENSIONS:
                seen_output_keys.add(str(source_rel_path.with_suffix(output_ext)))
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
                            "mod_name": mod_name,
                            "rel_path": str(entry.get("rel_path") or ""),
                            "reason": str(entry.get("engine_unsupported_reason") or ""),
                        }
                    )
                continue
            if bool(entry.get("excluded")):
                stat["excluded_count"] += 1
                continue
            plan_kind = str(entry.get("plan_kind") or "keep_original")
            if plan_kind == "fallback":
                stat["fallback_scaled_count"] += 1
            elif plan_kind == "keep_original":
                stat["keep_original_count"] += 1
                if bool(entry.get("is_mask_source")):
                    stat["keep_original_mask_count"] += 1
                elif bool(entry.get("small_skipped")):
                    stat["keep_original_range_count"] += 1
                else:
                    stat["keep_original_normal_count"] += 1
            else:
                stat["scaled_count"] += 1

            TextureOptimizationManager._append_scale_bucket(
                scale_buckets,
                kind=plan_kind,
                label=str(entry.get("plan_label") or "原尺寸"),
            )

            if bool(entry.get("output_exists")):
                stat["current_output_count"] += 1
                stat["current_output_bytes"] += output_size
            if bool(entry.get("needs_action")):
                stat["generate_required_count"] += 1
                stat["action_required_count"] += 1

        for output_rel, output_info in output_stats.items():
            if output_rel in seen_output_keys:
                continue
            stat["external_orphan_output_count"] += 1
            stat["external_orphan_output_bytes"] += int(output_info.get("size", 0) or 0)

        stat["projection_basis"] = []
        stat["scale_breakdown"] = TextureOptimizationManager._finalize_scale_breakdown(scale_buckets)
        stat["combined_total_bytes"] = int(stat["source_total_bytes"]) + int(stat["output_total_bytes"])
        stat["vram_saving_bytes_est"] = int(stat["source_vram_bytes_est"]) - int(stat["output_vram_bytes_est"])
        return stat

    def _get_source_capability(self, source: Path, source_stat: os.stat_result) -> dict[str, Any]:
        image_info = self._inspect_source_image(source, precise_alpha=False)
        width = int(image_info.get("width", 0) or 0)
        height = int(image_info.get("height", 0) or 0)
        has_alpha = bool(image_info.get("has_alpha"))
        source_size = int(source_stat.st_size)
        source_vram = width * height * 4
        supported_scale_percents = self._collect_supported_scale_percents(width, height)
        unsupported_reason = self._get_todds_unsupported_reason(source, image_info)
        capability = {
            "path": str(source),
            "width": width,
            "height": height,
            "has_alpha": has_alpha,
            "source_size": source_size,
            "source_vram": source_vram,
            "supported_scale_percents": supported_scale_percents,
            "engine_unsupported": bool(unsupported_reason),
            "engine_unsupported_reason": unsupported_reason,
        }
        return capability

    @staticmethod
    def _collect_supported_scale_percents(width: int, height: int) -> tuple[int, ...]:
        supported: list[int] = []
        for scale_percent in SCALE_STEP_SEQUENCE:
            numerator, denominator = SCALE_STEP_RATIONALS[scale_percent]
            required_divisor = (4 * denominator) // TextureOptimizationManager._gcd(numerator, 4 * denominator)
            if (width % required_divisor) == 0 and (height % required_divisor) == 0:
                supported.append(scale_percent)
        return tuple(supported)

    @staticmethod
    def _get_scale_factor_percent(options: dict[str, Any]) -> int | None:
        scale_factor = float(options.get("scale_factor", 1.0) or 1.0)
        if scale_factor <= 0:
            return None
        if scale_factor > 1.0:
            return 100
        if abs(scale_factor - 1.0) <= 1e-6:
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
        if preferred not in SCALE_STEP_SEQUENCE: return tuple()
        start_index = SCALE_STEP_SEQUENCE.index(preferred)
        return SCALE_STEP_SEQUENCE[start_index:]

    @staticmethod
    def _pick_scale_step_percent_from_supported(
        width: int,
        height: int,
        scale_candidates: tuple[int, ...],
        min_output_size: int,
    ) -> int | None:
        for scale_percent in scale_candidates:
            numerator, denominator = SCALE_STEP_RATIONALS[int(scale_percent)]
            if (min(width, height) * numerator) < (min_output_size * denominator):
                continue
            return int(scale_percent)
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
        if not mod_root.exists(): return
        for current_root, dirs, _files in os.walk(mod_root):
            # Source 目录是作者工程素材，游戏不会按普通贴图资源加载，避免误扫和误清理。
            dirs[:] = [name for name in dirs if name.lower() != "source"]
            current_path = Path(current_root)
            if current_path.name.lower() == "textures":
                yield current_path
                dirs[:] = []

    @staticmethod
    def _inspect_source_image(path: Path, *, precise_alpha: bool = True) -> dict[str, Any]:
        if not precise_alpha and path.suffix.lower() == ".png":
            fast_info = TextureOptimizationManager._inspect_png_header(path)
            if fast_info is not None: return fast_info
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
                if fallback is not None: return fallback
            raise

    @staticmethod
    def _inspect_png_header(path: Path) -> dict[str, Any] | None:
        try:
            with path.open("rb") as handle:
                signature = handle.read(8)
                if signature != b"\x89PNG\r\n\x1a\n": return None
                has_trns = False
                width = 0
                height = 0
                color_type = None
                while True:
                    length_bytes = handle.read(4)
                    if len(length_bytes) < 4: return None
                    chunk_length = struct.unpack(">I", length_bytes)[0]
                    chunk_type = handle.read(4)
                    if len(chunk_type) < 4: return None
                    chunk_data = handle.read(chunk_length)
                    if len(chunk_data) < chunk_length: return None
                    crc = handle.read(4)
                    if len(crc) < 4: return None
                    if chunk_type == b"IHDR":
                        if len(chunk_data) < 13: return None
                        width = struct.unpack(">I", chunk_data[0:4])[0]
                        height = struct.unpack(">I", chunk_data[4:8])[0]
                        color_type = chunk_data[9]
                    if chunk_type == b"tRNS":
                        has_trns = True
                    if chunk_type == b"IDAT":
                        if not width or not height or color_type is None: return None
                        return {
                            "width": width,
                            "height": height,
                            "has_alpha": color_type in {4, 6} or has_trns,
                            "image_format": "PNG",
                        }
                    if chunk_type == b"IEND": return None
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
        if image_format == "PNG": return ""
        if source.suffix.lower() == ".png": return "文件扩展名为 PNG，但实际内容不是 PNG"
        return ""

    @staticmethod
    def _iter_texture_output_paths(
        mod_path: str,
        *,
        include_zstd: bool = False,
        output_format: str = "",
        source_presence: bool | None = None,
    ):
        normalized_format = str(output_format or ("all" if include_zstd else "dds")).strip().lower()
        for texture_root in TextureOptimizationManager._iter_texture_root_dirs(mod_path):
            for current_root, _dirs, files in os.walk(texture_root):
                lower_names = {name.lower() for name in files} if source_presence is not None else set()
                for name in files:
                    lower_name = name.lower()
                    path = Path(current_root) / name
                    is_zstd = lower_name.endswith(TEXTURE_OUTPUT_ZSTD_EXT)
                    is_dds = lower_name.endswith(TEXTURE_OUTPUT_DDS_EXT) and not is_zstd
                    if not is_dds and not is_zstd:
                        continue
                    if source_presence is not None:
                        output_ext = TEXTURE_OUTPUT_ZSTD_EXT if is_zstd else TEXTURE_OUTPUT_DDS_EXT
                        source_stem = lower_name[: -len(output_ext)]
                        has_source = any(f"{source_stem}{ext}" in lower_names for ext in SOURCE_REFERENCE_IMAGE_EXTENSIONS)
                        if has_source != source_presence:
                            continue
                    if is_dds and normalized_format in {"dds", "all"}:
                        yield path
                    elif is_zstd and normalized_format in {"zstd", "all"}:
                        yield path

    @staticmethod
    def _iter_texture_output_paths_with_source(
        mod_path: str,
        cancel_event: threading.Event | None = None,
        *,
        include_zstd: bool = False,
        output_format: str = "",
    ):
        for output_path in TextureOptimizationManager._iter_texture_output_paths(
            mod_path,
            include_zstd=include_zstd,
            output_format=output_format,
            source_presence=True,
        ):
            if cancel_event and cancel_event.is_set():
                raise TextureOptCancelled("清理 DDS 任务已取消")
            yield output_path

    @staticmethod
    def _iter_texture_output_paths_without_source(
        mod_path: str,
        cancel_event: threading.Event | None = None,
        *,
        include_zstd: bool = False,
        output_format: str = "",
    ):
        for output_path in TextureOptimizationManager._iter_texture_output_paths(
            mod_path,
            include_zstd=include_zstd,
            output_format=output_format,
            source_presence=False,
        ):
            if cancel_event and cancel_event.is_set():
                raise TextureOptCancelled("清理 DDS 任务已取消")
            yield output_path

    @staticmethod
    def _collect_output_stats(mod_path: str) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        for output_path in TextureOptimizationManager._iter_texture_output_paths(mod_path, include_zstd=True):
            try:
                output_stat = output_path.stat()
            except OSError:
                continue
            output_rel_path = Path(os.path.relpath(output_path, mod_path)).as_posix()
            stats[output_rel_path] = {
                "path": str(output_path),
                "size": int(output_stat.st_size),
                "mtime_ns": int(output_stat.st_mtime_ns),
                "format": TextureOptimizationManager._output_format_for_path(output_path),
            }
        return stats

    @staticmethod
    def _resolve_scan_workers(total_mods: int, options: dict[str, Any]) -> int:
        configured_workers = int(options.get("scan_workers", 0) or 0)
        if configured_workers > 0: return max(1, min(total_mods, configured_workers))
        cpu_count = os.cpu_count() or 4
        return max(1, min(total_mods, min(8, cpu_count)))

    @staticmethod
    def _normalize_output_format(value: Any) -> str:
        normalized = str(value or "dds").strip().lower()
        return "zstd" if normalized == "zstd" else "dds"

    @staticmethod
    def _normalize_clean_output_format(options: dict[str, Any]) -> str:
        normalized = str(options.get("clean_output_format") or "").strip().lower()
        return "zstd" if normalized == "zstd" else "dds"

    @staticmethod
    def _is_zstd_output_mode(options: dict[str, Any]) -> bool:
        return TextureOptimizationManager._normalize_output_format(options.get("output_format")) == "zstd"

    @staticmethod
    def _source_output_path(source: Path, options: dict[str, Any]) -> Path:
        return source.with_suffix(
            TEXTURE_OUTPUT_ZSTD_EXT
            if TextureOptimizationManager._is_zstd_output_mode(options)
            else TEXTURE_OUTPUT_DDS_EXT
        )

    @staticmethod
    def _output_format_for_path(path: Path) -> str:
        lower_name = path.name.lower()
        if lower_name.endswith(TEXTURE_OUTPUT_ZSTD_EXT):
            return "zstd"
        if lower_name.endswith(TEXTURE_OUTPUT_DDS_EXT):
            return "dds"
        return ""

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
        merged.setdefault("output_format", "dds")
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
        merged["output_format"] = TextureOptimizationManager._normalize_output_format(merged.get("output_format"))
        merged["scale_factor"] = float(merged.get("scale_factor", 0.5) or 0.5)
        merged["max_size"] = int(merged.get("max_size", 128) or 128)
        merged["min_dimension"] = int(merged.get("min_dimension", 128) or 128)
        merged["max_source_dimension"] = int(merged.get("max_source_dimension", 2048) or 2048)
        merged["skip_small_textures"] = TextureOptimizationManager._normalize_bool(merged.get("skip_small_textures", True), True)
        merged["clean_uninstalled_residue_only"] = TextureOptimizationManager._normalize_bool(merged.get("clean_uninstalled_residue_only", False), False)
        merged["clean_without_source"] = TextureOptimizationManager._normalize_bool(merged.get("clean_without_source", False), False)
        merged["clean_output_format"] = TextureOptimizationManager._normalize_clean_output_format(merged)
        merged["zstd_clean_old_dds"] = TextureOptimizationManager._normalize_bool(merged.get("zstd_clean_old_dds", False), False)
        merged["texture_tools_path"] = str(resolve_texture_tools_path(merged))
        return merged

    @staticmethod
    def _build_metrics(summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "optimized": summary.get("optimized", 0),
            "skipped": summary.get("skipped", 0),
            "failed": summary.get("failed", 0),
            "failed_count": summary.get("failed_count", 0),
            "scan_failed": summary.get("scan_failed", 0),
            "orphan_deleted": summary.get("orphan_deleted", 0),
            "checked_outputs": summary.get("checked_outputs", 0),
            "delete_failed": summary.get("delete_failed", 0),
            "total_jobs": summary.get("total_jobs", 0),
            "scaled_count": summary.get("scaled_count", 0),
            "fallback_scaled_count": summary.get("fallback_scaled_count", 0),
            "keep_original_count": summary.get("keep_original_count", 0),
            "output_format": summary.get("output_format", ""),
            "clean_output_format": summary.get("clean_output_format", ""),
            "clean_without_source": summary.get("clean_without_source", False),
        }

    @staticmethod
    def _results_file_path(task_id: str) -> Path:
        return TEXTURE_RESULTS_DIR / f"{str(task_id or '').strip() or uuid.uuid4().hex}.json"

    def _write_task_result_file(
        self,
        task: TextureTask,
        options: dict[str, Any],
        final_summary: dict[str, Any],
        final_mods: list[dict[str, Any]],
        failed_items: list[dict[str, Any]],
        failed_count: int = 0,
    ) -> str:
        path = self._results_file_path(task.id)
        write_json_atomic(
            path,
            {
                "task_id": task.id,
                "action": task.action,
                "created_at": int(task.created_at),
                "updated_at": current_ms(),
                "options_signature": self._build_signature(options),
                "mod_paths": list(task.mod_paths),
                "mod_targets": [dict(item) for item in task.mod_targets],
                "summary": final_summary,
                "mods": final_mods,
                "failed_items": failed_items,
                "failed_count": int(failed_count),
                "todds_log_path": self._last_todds_log_path,
            },
            indent=2,
        )
        self._prune_result_history()
        return str(path)

    def _prune_result_history(self) -> None:
        files = sorted(
            TEXTURE_RESULTS_DIR.glob("*.json"),
            key=lambda item: item.stat().st_mtime_ns if item.exists() else 0,
            reverse=True,
        )
        for stale in files[TEXTURE_RESULT_HISTORY_LIMIT:]:
            try:
                stale.unlink()
            except OSError:
                continue

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
    def _normalize_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return bool(default)

    @staticmethod
    def _create_empty_stat(*, mod_path: str = "", mod_name: str = "", include_mod_count: bool = False, mod_count: int = 0) -> dict[str, Any]:
        stat = {
            "mod_path": mod_path,
            "mod_name": mod_name,
            "package_id": "",
            "store": "",
            "path_hash": "",
            "mod_instance_key": "",
            "source_total_count": 0,
            "source_total_bytes": 0,
            "output_total_count": 0,
            "output_total_bytes": 0,
            "dds_output_count": 0,
            "dds_output_bytes": 0,
            "zstd_output_count": 0,
            "zstd_output_bytes": 0,
            "current_output_count": 0,
            "current_output_bytes": 0,
            "external_orphan_output_count": 0,
            "external_orphan_output_bytes": 0,
            "generate_required_count": 0,
            "excluded_count": 0,
            "action_required_count": 0,
            "skip_small_count": 0,
            "skipped_mask_count": 0,
            "unsupported_source_count": 0,
            "unreadable_source_count": 0,
            "scan_failed_count": 0,
            "scaled_count": 0,
            "fallback_scaled_count": 0,
            "keep_original_count": 0,
            "keep_original_normal_count": 0,
            "keep_original_mask_count": 0,
            "keep_original_range_count": 0,
            "combined_total_bytes": 0,
            "scale_breakdown": [],
            "projection_basis": [],
            "engine_unsupported_preview": [],
            "source_vram_bytes_est": 0,
            "output_vram_bytes_est": 0,
            "vram_saving_bytes_est": 0,
            "source_bytes_share_pct": 0.0,
            "output_bytes_share_pct": 0.0,
            "dds_output_bytes_share_pct": 0.0,
            "zstd_output_bytes_share_pct": 0.0,
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
        items.sort(key=lambda item: (
            order.get(str(item["kind"]), 99),
            TextureOptimizationManager._scale_label_sort_value(str(item["label"])),
            str(item["label"]),
        ))
        return items

    @staticmethod
    def _scale_label_sort_value(label: str) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", str(label or ""))
        return float(match.group(1)) if match else float("inf")

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
            if key in {
                "mod_path",
                "mod_name",
                "package_id",
                "store",
                "path_hash",
                "mod_instance_key",
                "scale_breakdown",
                "projection_basis",
                "engine_unsupported_preview",
            }:
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
        total_dds_output = max(1, int(summary.get("dds_output_bytes", 0)))
        total_zstd_output = max(1, int(summary.get("zstd_output_bytes", 0)))
        total_combined = max(1, int(summary.get("combined_total_bytes", 0)))
        for item in mod_stats:
            item["source_bytes_share_pct"] = round((int(item.get("source_total_bytes", 0)) / total_source) * 100, 2)
            item["output_bytes_share_pct"] = round((int(item.get("output_total_bytes", 0)) / total_output) * 100, 2)
            item["dds_output_bytes_share_pct"] = round((int(item.get("dds_output_bytes", 0)) / total_dds_output) * 100, 2)
            item["zstd_output_bytes_share_pct"] = round((int(item.get("zstd_output_bytes", 0)) / total_zstd_output) * 100, 2)
            item["combined_bytes_share_pct"] = round((int(item.get("combined_total_bytes", 0)) / total_combined) * 100, 2)

    def _set_task_state(
        self,
        task: TextureTask,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: Any | None = None,
        metrics: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        error: Any | None = None,
    ) -> None:
        if summary is not None:
            task.summary = summary
        if error is not None:
            task.error = str(error or "")
            task.user_message = str(error or "")
        final_status = status or task.status
        self._emit_progress(
            task,
            final_status,
            task.progress if progress is None else progress,
            task.message if message is None else message,
            task.metrics if metrics is None else metrics,
            user_message=task.user_message if error is not None else None,
        )
        if final_status in {"success", "failed", "cancelled"} and not getattr(task, "_cleanup_scheduled", False):
            setattr(task, "_cleanup_scheduled", True)
            self._schedule_task_cleanup(task.id)

    def _emit_progress(self, task: TextureTask, status: str, progress: int, message: Any, metrics: dict[str, Any] | None = None, user_message: Any | None = None) -> None:
        updated_at = current_ms()
        key = localized_key(message)
        params = localized_params(message)
        task.status = status
        task.progress = progress
        task.message = str(message or "")
        task.user_message = str(user_message if user_message is not None else message or "")
        task.message_key = key
        task.message_params = params
        task.metrics = metrics or {}
        task.updated_at = updated_at
        task_created_at = int(getattr(task, "created_at", updated_at))
        task.metrics.setdefault("task_created_at", task_created_at)
        task.metrics["task_updated_at"] = updated_at
        task.metrics.setdefault("task_action", str(getattr(task, "action", "")))
        task.metrics["task_status"] = status
        EventBus.emit_progress(
            task.id,
            TEXTURE_TASK_TYPE,
            status=status,
            progress=progress,
            message=task.message,
            metrics=task.metrics,
            message_key=key,
            message_params=params,
            user_message=task.user_message,
        )

    def _emit_analysis_progress(
        self,
        task_id: str,
        *,
        status: str,
        progress: int,
        message: Any,
        user_message: Any | None = None,
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
        EventBus.emit_progress(
            task_id,
            TEXTURE_ANALYSIS_TASK_TYPE,
            status=status,
            progress=progress,
            message=str(message or ""),
            metrics=metrics,
            message_key=localized_key(message),
            message_params=localized_params(message),
            user_message=str(user_message or ""),
        )

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
        if hours > 0: return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
