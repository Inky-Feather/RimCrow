import os
import shutil
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from backend._version import __version__
from backend.database.dao import ModDAO, _ProfilePathScope
from backend.database.models import ModInterlock
from backend.load_order.package_tokens import build_steam_package_token, parse_package_token
from backend.utils.bundle_io import (
    create_sibling_stage_dir,
    estimate_disk_space_requirement,
    extract_prefix_to_dir,
    normalize_zip_compresslevel,
    replace_dir_atomically,
    summarize_zip_members,
    write_tree_to_zip,
)
from backend.managers.mgr_data_bundle import DataBundleManager
from backend.managers.mgr_files import FileManager
from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_profile import ProfileManager
from backend.settings import settings
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger
from backend.utils.tools import normalize_package_id


class ModPackageManager:
    """
    模组实体包管理器。

    职责：
    1. 导出实体模组目录 + manifest
    2. 可选附带环境 user_data
    3. 预检导入冲突
    4. 执行导入，并复用 DataBundle 的环境导入能力
    """

    FORMAT = "rimcrow.mod.package"
    LEGACY_FORMATS = ("rmm.mod.package",)
    SCHEMA_VERSION = 1
    FILE_EXTENSION = ".rimcrowmods.zip"
    LEGACY_FILE_EXTENSIONS = (".rmmmods.zip",)
    EXPORT_TASK_TYPE = "mod-export"
    IMPORT_TASK_TYPE = "mod-import"
    EXPORT_FOLDER_NAME_TYPES = {"default", "workshop_id", "package_id", "name", "alias_name"}
    RESERVED_WINDOWS_NAMES = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }

    def __init__(
        self,
        profile_mgr: ProfileManager,
        data_bundle_mgr: DataBundleManager,
        load_order_mgr_provider: Callable[[], Any],
        rule_mgr_provider: Callable[[], Any] | None = None,
    ):
        self.profile_mgr = profile_mgr
        self.data_bundle_mgr = data_bundle_mgr
        self.load_order_mgr_provider = load_order_mgr_provider
        self.rule_mgr_provider = rule_mgr_provider or (lambda: None)
        self._export_cancel_lock = threading.Lock()
        self._export_cancel_events: dict[str, threading.Event] = {}
        self._import_cancel_lock = threading.Lock()
        self._import_cancel_events: dict[str, threading.Event] = {}

    def get_schema(self) -> dict[str, Any]:
        return {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "file_extension": self.FILE_EXTENSION,
            "legacy_file_extensions": list(self.LEGACY_FILE_EXTENSIONS),
            "profiles": self.profile_mgr.get_all_profiles(),
            "available_installs": self.data_bundle_mgr.get_available_install_choices(),
            "self_mods_path": str(settings.config.self_mods_path or ""),
        }

    def inspect_bundle(self, bundle_path: str) -> dict[str, Any]:
        path = Path(str(bundle_path or "").strip())
        if not path.is_file():
            raise FileNotFoundError(f"未找到模组包文件: {path}")
        if not zipfile.is_zipfile(path):
            raise ValueError("无法识别的模组包格式")

        with zipfile.ZipFile(path, "r") as bundle:
            manifest = self._read_json_from_zip(bundle, "manifest.json", {})
            archive_stats = summarize_zip_members(bundle)
            mod_payload_stats = summarize_zip_members(bundle, ["mods"])
            environment_payload_stats = summarize_zip_members(bundle, ["environments"])
        if not isinstance(manifest, dict) or str(manifest.get("format") or "") not in {self.FORMAT, *self.LEGACY_FORMATS}:
            raise ValueError("无法识别的模组包格式")

        profiles = manifest.get("profiles", [])
        return {
            "format": manifest.get("format"),
            "schema_version": manifest.get("schema_version"),
            "app_version": manifest.get("app_version"),
            "exported_at": manifest.get("exported_at"),
            "export_scope": manifest.get("export_scope", "custom"),
            "mods": manifest.get("mods", []),
            "profiles": profiles if isinstance(profiles, list) else [],
            "has_environment_data": bool(manifest.get("has_environment_data")),
            "bundle_size_bytes": int(path.stat().st_size),
            "archive_stats": archive_stats,
            "mod_payload_stats": mod_payload_stats,
            "environment_payload_stats": environment_payload_stats,
            "profile_conflicts": self.data_bundle_mgr._build_profile_conflict_entries(  # noqa: SLF001
                profiles if isinstance(profiles, list) else []
            ),
            "available_installs": self.data_bundle_mgr.get_available_install_choices(),
        }

    def prepare_import(self, bundle_path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        inspect = self.inspect_bundle(bundle_path)
        target_root = self._resolve_import_target_root(payload)
        mod_entries = list(inspect.get("mods") or [])
        mod_conflicts = self._build_mod_conflicts(target_root, mod_entries) if target_root else []
        target_disk_space = (
            estimate_disk_space_requirement(
                target_root,
                int((inspect.get("mod_payload_stats") or {}).get("uncompressed_bytes") or 0),
            )
            if target_root else None
        )
        return {
            **inspect,
            "target_root": target_root,
            "mod_conflicts": mod_conflicts,
            "target_disk_space": target_disk_space,
        }

    def export_bundle(self, target_path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        export_plan = self.preview_export(payload)
        return self._write_export_bundle(target_path, payload, export_plan)

    def start_export_task(self, target_path: str, payload: dict[str, Any] | None = None) -> str:
        payload = dict(payload or {})
        task_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        EventBus.resume()
        with self._export_cancel_lock:
            self._export_cancel_events[task_id] = cancel_event
        self._emit_export_progress(task_id, "pending", 0, "准备导出模组包...", phase="prepare")
        worker = threading.Thread(
            target=self._run_export_task,
            args=(task_id, str(target_path or "").strip(), payload, cancel_event),
            daemon=True,
            name=f"ModExport-{task_id[:8]}",
        )
        worker.start()
        return task_id

    def cancel_export_task(self, task_id: str) -> bool:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return False
        with self._export_cancel_lock:
            cancel_event = self._export_cancel_events.get(normalized_task_id)
        if not cancel_event:
            return False
        cancel_event.set()
        return True

    def _run_export_task(self, task_id: str, target_path: str, payload: dict[str, Any], cancel_event: threading.Event) -> None:
        try:
            self._check_export_cancelled(cancel_event)
            self._emit_export_progress(task_id, "running", 4, "正在整理导出内容...", phase="prepare")
            export_plan = self.preview_export(payload)
            self._check_export_cancelled(cancel_event)
            result = self._write_export_bundle(target_path, payload, export_plan, cancel_event=cancel_event, task_id=task_id)
            self._emit_export_progress(
                task_id,
                "success",
                100,
                "模组包导出完成",
                metrics={
                    "title": "导出模组包",
                    "target_path": target_path,
                    "mod_count": len(result.get("mods") or []),
                    "warning_count": len(result.get("warnings") or []),
                    "phase": "done",
                },
                phase="done",
            )
        except InterruptedError:
            self._cleanup_partial_export(target_path)
            self._emit_export_progress(task_id, "cancelled", 0, "模组包导出已取消", phase="cancelled")
        except Exception as e:
            logger.error("MOD 包导出任务失败：%s", e, exc_info=True)
            self._cleanup_partial_export(target_path)
            self._emit_export_progress(
                task_id,
                "failed",
                0,
                f"模组包导出失败: {e}",
                metrics={"title": "导出模组包", "error": str(e), "phase": "failed"},
                phase="failed",
            )
        finally:
            with self._export_cancel_lock:
                self._export_cancel_events.pop(task_id, None)

    def preview_export(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        profile_id = str(payload.get("profile_id") or settings.config.current_profile_id or "default").strip() or "default"
        context = self.profile_mgr.build_profile_context(profile_id)
        visible_mods = list(ModDAO.get_profile_mods(context) or [])
        path_scope = _ProfilePathScope.from_context(context)
        exportable_visible_mods = [mod for mod in visible_mods if self._is_exportable_mod_asset(mod, path_scope)]
        rule_mgr = self.rule_mgr_provider()
        if rule_mgr:
            for mod in visible_mods:
                mod["rules"] = rule_mgr.get_effective_mod_rules(mod.get("package_id"), mod)
        active_tokens = self._read_active_tokens(profile_id, context)
        active_token_set = {str(token or "").strip().lower() for token in active_tokens if str(token or "").strip()}
        requested_ids = self._resolve_requested_mod_ids(payload, exportable_visible_mods, active_tokens)
        folder_name_type = self._normalize_export_folder_name_type(
            payload.get("folder_name_type") or getattr(settings.config, "bundle_mod_folder_name_type", "default")
        )
        expanded_ids = self._expand_mod_ids(
            requested_ids,
            visible_mods,
            include_dependencies=bool(payload.get("include_dependencies")),
            include_interlocks=bool(payload.get("include_interlocks")),
            include_language_packs=bool(payload.get("include_language_packs")),
        )
        export_mods, warnings = self._resolve_export_mods(visible_mods, expanded_ids, active_token_set, path_scope, folder_name_type)
        return {
            "profile_id": profile_id,
            "folder_name_type": folder_name_type,
            "selected_count": len(requested_ids),
            "mod_count": len(export_mods),
            "extra_count": max(0, len(export_mods) - len(requested_ids)),
            "mods": export_mods,
            "warnings": warnings,
        }

    def get_profile_export_summary(self, profile_id: str | None = None) -> dict[str, Any]:
        normalized_profile_id = str(profile_id or settings.config.current_profile_id or "default").strip() or "default"
        context = self.profile_mgr.build_profile_context(normalized_profile_id)
        visible_mods = list(ModDAO.get_profile_mods(context) or [])
        path_scope = _ProfilePathScope.from_context(context)
        exportable_visible_mods = [mod for mod in visible_mods if self._is_exportable_mod_asset(mod, path_scope)]
        exportable_ids = {
            normalize_package_id(mod.get("package_id"))
            for mod in exportable_visible_mods
            if normalize_package_id(mod.get("package_id"))
        }
        active_count = 0
        for token in self._read_active_tokens(normalized_profile_id, context):
            canonical_id = parse_package_token(token).canonical_package_id
            if canonical_id and canonical_id in exportable_ids:
                active_count += 1
        return {
            "profile_id": normalized_profile_id,
            "effective_count": len(exportable_visible_mods),
            "active_count": active_count,
        }

    def start_import_task(self, bundle_path: str, payload: dict[str, Any] | None = None) -> str:
        payload = dict(payload or {})
        task_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        EventBus.resume()
        with self._import_cancel_lock:
            self._import_cancel_events[task_id] = cancel_event
        self._emit_import_progress(task_id, "pending", 0, "准备导入模组包...", phase="prepare")
        worker = threading.Thread(
            target=self._run_import_task,
            args=(task_id, str(bundle_path or "").strip(), payload, cancel_event),
            daemon=True,
            name=f"ModImport-{task_id[:8]}",
        )
        worker.start()
        return task_id

    def cancel_import_task(self, task_id: str) -> bool:
        normalized_task_id = str(task_id or "").strip()
        if not normalized_task_id:
            return False
        with self._import_cancel_lock:
            cancel_event = self._import_cancel_events.get(normalized_task_id)
        if not cancel_event:
            return False
        cancel_event.set()
        return True

    def import_bundle(
        self,
        bundle_path: str,
        payload: dict[str, Any] | None = None,
        *,
        cancel_event: threading.Event | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        self._check_import_cancelled(cancel_event)
        inspect = self.inspect_bundle(bundle_path)
        path = Path(str(bundle_path or "").strip())
        target_root = self._resolve_import_target_root(payload)
        if payload.get("import_mods", True) and not target_root:
            raise ValueError("未选择有效的模组导入目标")
        if payload.get("import_mods", True):
            target_disk_space = estimate_disk_space_requirement(
                target_root,
                int((inspect.get("mod_payload_stats") or {}).get("uncompressed_bytes") or 0),
            )
            if not bool(target_disk_space.get("enough")):
                raise ValueError(
                    "模组导入目标剩余空间不足，"
                    f"至少建议保留 {self._format_bytes(int(target_disk_space.get('recommended_bytes') or 0))}，"
                    f"当前仅剩 {self._format_bytes(int(target_disk_space.get('free_bytes') or 0))}"
                )

        result = {
            "imported_mods": [],
            "skipped_mods": [],
            "renamed_mods": [],
            "warnings": [],
            "profiles": [],
        }
        conflict_plan = self._normalize_mod_conflict_plan(payload.get("mod_conflict_plan"))
        profile_import_plan = payload.get("profile_import_plan")
        current_profile_id = str(payload.get("current_profile_id") or "").strip()
        current_local_mods_path = str(payload.get("current_local_mods_path") or "").strip()

        with zipfile.ZipFile(path, "r") as bundle:
            profile_entries = list(inspect.get("profiles") or []) if inspect.get("has_environment_data") else []
            mod_entries = list(inspect.get("mods") or [])
            profile_total = len(profile_entries) if bool(payload.get("apply_environment_data")) and inspect.get("has_environment_data") else 0
            mod_total = len(mod_entries) if payload.get("import_mods", True) else 0
            total_steps = max(1, profile_total + mod_total)
            completed_steps = 0
            if bool(payload.get("apply_environment_data")) and inspect.get("has_environment_data"):
                imported_profiles, warnings = self.data_bundle_mgr._import_profiles_from_bundle(  # noqa: SLF001
                    bundle,
                    profile_entries,
                    profile_import_plan=profile_import_plan,
                    progress_callback=lambda current, total, profile_entry: self._emit_import_progress(
                        task_id,
                        "running",
                        self._compute_import_progress(completed_steps, total_steps),
                        f'正在应用环境数据 ({current}/{total}): {str((profile_entry or {}).get("name") or (profile_entry or {}).get("archive_key") or "未命名环境")}',
                        metrics={"title": "导入模组包", "phase": "profiles", "current": current, "total": total},
                        phase="profiles",
                    ),
                    cancel_check=lambda: self._check_import_cancelled(cancel_event),
                )
                result["profiles"] = imported_profiles
                result["warnings"].extend(warnings)
                completed_steps += profile_total

            if payload.get("import_mods", True):
                imported = self._import_mod_directories(
                    bundle,
                    mod_entries,
                    target_root,
                    conflict_plan,
                    cancel_event=cancel_event,
                    progress_callback=lambda current, total, item: self._emit_import_progress(
                        task_id,
                        "running",
                        self._compute_import_progress(completed_steps + current - 1, total_steps),
                        f'正在导入模组 ({current}/{total}): {str((item or {}).get("name") or (item or {}).get("folder_name") or "未知模组")}',
                        metrics={"title": "导入模组包", "phase": "mods", "current": current, "total": total},
                        phase="mods",
                    ),
                )
                result["imported_mods"] = imported["imported_mods"]
                result["skipped_mods"] = imported["skipped_mods"]
                result["renamed_mods"] = imported["renamed_mods"]
                result["warnings"].extend(imported["warnings"])
                completed_steps += mod_total

        should_scan_after_import = self.should_scan_after_import(
            payload,
            current_local_mods_path=current_local_mods_path,
        )
        current_profile_overwritten = current_profile_id in {
            str(profile.get("profile_id") or "").strip()
            for profile in (result.get("profiles") or [])
            if str(profile.get("mode") or "").strip().lower() == "overwrite"
        }
        result["post_actions"] = { # type: ignore
            "scan_current_view": bool(should_scan_after_import),
            "refresh_current_profile": bool(current_profile_overwritten),
            "refresh_profile_list": bool(result.get("profiles")),
        }

        return result

    def _run_import_task(self, task_id: str, bundle_path: str, payload: dict[str, Any], cancel_event: threading.Event) -> None:
        try:
            self._check_import_cancelled(cancel_event)
            result = self.import_bundle(bundle_path, payload, cancel_event=cancel_event, task_id=task_id)
            self._emit_import_progress(
                task_id,
                "success",
                100,
                "模组包导入完成",
                metrics={
                    "title": "导入模组包",
                    "phase": "done",
                    "warnings": list(result.get("warnings") or []),
                    "post_actions": dict(result.get("post_actions") or {}),
                    "imported_mod_count": len(result.get("imported_mods") or []),
                    "imported_profile_count": len(result.get("profiles") or []),
                },
                phase="done",
            )
        except InterruptedError:
            self._emit_import_progress(task_id, "cancelled", 0, "模组包导入已取消", phase="cancelled")
        except Exception as e:
            logger.error("MOD 包导入任务失败：%s", e, exc_info=True)
            self._emit_import_progress(
                task_id,
                "failed",
                0,
                f"模组包导入失败: {e}",
                metrics={"title": "导入模组包", "error": str(e), "phase": "failed"},
                phase="failed",
            )
        finally:
            with self._import_cancel_lock:
                self._import_cancel_events.pop(task_id, None)

    def should_scan_after_import(self, payload: dict[str, Any] | None = None, current_local_mods_path: str = "") -> bool:
        payload = payload or {}
        if not payload.get("import_mods", True):
            return False

        target_root = self._resolve_import_target_root(payload)
        if not target_root:
            return False

        normalized_target_root = self._normalize_compare_path(target_root)
        if not normalized_target_root:
            return False

        self_mods_root = self._normalize_compare_path(str(settings.config.self_mods_path or "").strip())
        if self_mods_root and normalized_target_root == self_mods_root:
            return True

        current_local_root = self._normalize_compare_path(current_local_mods_path)
        return bool(current_local_root and normalized_target_root == current_local_root)

    def _resolve_requested_mod_ids(
        self,
        payload: dict[str, Any],
        exportable_visible_mods: list[dict[str, Any]],
        active_tokens: list[str],
    ) -> list[str]:
        explicit_ids = [str(item or "").strip() for item in (payload.get("mod_ids") or []) if str(item or "").strip()]
        if explicit_ids:
            return explicit_ids
        export_scope = str(payload.get("export_scope") or "").strip().lower()
        if export_scope == "profile-active":
            return list(active_tokens)
        if export_scope == "profile-effective":
            return [
                str(mod.get("package_id") or "").strip()
                for mod in exportable_visible_mods
                if str(mod.get("package_id") or "").strip()
            ]
        return [
            str(mod.get("package_id") or "").strip()
            for mod in exportable_visible_mods
            if str(mod.get("package_id") or "").strip()
        ]

    def _expand_mod_ids(
        self,
        base_ids: list[str],
        visible_mods: list[dict[str, Any]],
        *,
        include_dependencies: bool = False,
        include_interlocks: bool = False,
        include_language_packs: bool = False,
    ) -> list[str]:
        ordered_ids: list[str] = []
        seen: set[str] = set()
        visible_map = {
            normalize_package_id(mod.get("package_id")): mod
            for mod in visible_mods
            if normalize_package_id(mod.get("package_id"))
        }
        language_pack_map = self._build_language_pack_map(visible_mods) if include_language_packs else {}
        interlock_map = self._build_interlock_map() if include_interlocks else {}

        def _push(raw_id: str):
            token_info = parse_package_token(raw_id)
            key = token_info.normalized_token or token_info.canonical_package_id
            if not key or key in seen:
                return
            seen.add(key)
            ordered_ids.append(raw_id)

        def _visit_dependency(raw_id: str):
            token_info = parse_package_token(raw_id)
            canonical_id = token_info.canonical_package_id
            if not canonical_id:
                return
            mod = visible_map.get(canonical_id)
            if not mod:
                return
            for dep in self._extract_dependency_ids(mod):
                dep_id = normalize_package_id(dep)
                if not dep_id:
                    continue
                _push(dep_id)
                if include_dependencies:
                    _visit_dependency(dep_id)

        for raw_id in base_ids:
            _push(raw_id)

        if include_dependencies:
            for raw_id in list(ordered_ids):
                _visit_dependency(raw_id)

        if include_interlocks:
            for raw_id in list(ordered_ids):
                canonical_id = parse_package_token(raw_id).canonical_package_id
                for interlock_id in self._extract_interlock_ids(visible_map.get(canonical_id), interlock_map):
                    _push(interlock_id)

        if include_language_packs:
            for raw_id in list(ordered_ids):
                canonical_id = parse_package_token(raw_id).canonical_package_id
                for pack_id in language_pack_map.get(canonical_id, []):
                    _push(pack_id)

        return ordered_ids

    def _resolve_export_mods(
        self,
        visible_mods: list[dict[str, Any]],
        requested_ids: list[str],
        active_token_set: set[str],
        path_scope: _ProfilePathScope,
        folder_name_type: str = "default",
    ) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        normalized_folder_name_type = self._normalize_export_folder_name_type(folder_name_type)
        visible_map = {
            normalize_package_id(mod.get("package_id")): mod
            for mod in visible_mods
            if normalize_package_id(mod.get("package_id"))
        }
        export_mods: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        seen_folder_names: set[str] = set()

        for raw_id in requested_ids:
            token_info = parse_package_token(raw_id)
            canonical_id = token_info.canonical_package_id
            if not canonical_id:
                continue
            mod = visible_map.get(canonical_id)
            if not mod:
                warnings.append(f"未找到模组 {raw_id}，已跳过")
                continue
            chosen = self._select_export_asset(mod, token_info, active_token_set)
            mod_path = str(chosen.get("path") or "").strip()
            if not self._is_exportable_mod_asset(chosen, path_scope):
                continue
            if not mod_path or not os.path.isdir(mod_path):
                warnings.append(f'模组 "{chosen.get("name") or canonical_id}" 文件夹无效，已跳过')
                continue
            if self._is_deployed_workshop_link(mod_path):
                workshop_variant = chosen.get("coexist_workshop_variant") or mod.get("coexist_workshop_variant")
                if workshop_variant:
                    chosen = workshop_variant
                    mod_path = str(chosen.get("path") or "").strip()
                if not self._is_exportable_mod_asset(chosen, path_scope):
                    continue
                if not mod_path or self._is_deployed_workshop_link(mod_path):
                    continue
            normalized_path = os.path.normcase(os.path.normpath(mod_path))
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            original_folder_name = Path(mod_path).name
            folder_name, folder_warnings = self._resolve_export_folder_name(
                chosen,
                mod,
                original_folder_name,
                normalized_folder_name_type,
                seen_folder_names,
            )
            warnings.extend(folder_warnings)
            export_mods.append({
                **chosen,
                "folder_name": folder_name,
                "original_folder_name": original_folder_name,
                "folder_name_type": normalized_folder_name_type,
            })

        return export_mods, warnings

    @classmethod
    def _normalize_export_folder_name_type(cls, value: Any) -> str:
        normalized = str(value or "default").strip().lower()
        return normalized if normalized in cls.EXPORT_FOLDER_NAME_TYPES else "default"

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            normalized = str(value or "").strip()
            if normalized:
                return normalized
        return ""

    @classmethod
    def _export_folder_name_candidates(
        cls,
        selected: dict[str, Any],
        original: dict[str, Any],
        original_folder_name: str,
        folder_name_type: str,
    ) -> list[str]:
        def field(name: str) -> str:
            return cls._first_text(selected.get(name), original.get(name))

        if folder_name_type == "alias_name":
            return [field("alias_name"), field("name"), original_folder_name]
        if folder_name_type == "name":
            return [field("name"), original_folder_name]
        if folder_name_type == "workshop_id":
            return [field("workshop_id"), field("package_id"), original_folder_name]
        if folder_name_type == "package_id":
            return [field("package_id"), original_folder_name]
        return [original_folder_name]

    @classmethod
    def _sanitize_export_folder_name(cls, value: Any) -> str:
        raw_name = str(value or "").strip()
        if not raw_name:
            return ""
        # 包内路径最终仍可能落到 Windows 文件系统，统一替换路径分隔符、控制字符和 Windows 禁用字符。
        sanitized = "".join("_" if ord(ch) < 32 or ch in '<>:"/\\|?*' else ch for ch in raw_name).strip(" .")
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        if sanitized in {"", ".", ".."}:
            return ""
        if sanitized.upper() in cls.RESERVED_WINDOWS_NAMES:
            sanitized = f"{sanitized}_"
        return sanitized[:160].rstrip(" .") or ""

    @classmethod
    def _dedupe_export_folder_name(cls, base_name: str, seen_folder_names: set[str]) -> str:
        name = base_name
        index = 2
        while name.lower() in seen_folder_names:
            suffix = f"_{index}"
            suffix_base = base_name.rstrip(" _") or base_name
            name = f"{suffix_base[: max(1, 160 - len(suffix))]}{suffix}"
            index += 1
        seen_folder_names.add(name.lower())
        return name

    def _resolve_export_folder_name(
        self,
        selected: dict[str, Any],
        original: dict[str, Any],
        original_folder_name: str,
        folder_name_type: str,
        seen_folder_names: set[str],
    ) -> tuple[str, list[str]]:
        warnings: list[str] = []
        display_name = self._first_text(selected.get("name"), original.get("name"), selected.get("package_id"), original_folder_name, "未知模组")
        raw_candidates = self._export_folder_name_candidates(selected, original, original_folder_name, folder_name_type)
        raw_name = self._first_text(*raw_candidates)
        safe_name = ""
        for candidate in raw_candidates:
            safe_name = self._sanitize_export_folder_name(candidate)
            if safe_name:
                raw_name = str(candidate or "").strip()
                break
        if not safe_name:
            safe_name = "mod"
        if raw_name and safe_name != raw_name.strip(" ."):
            warnings.append(f'模组 "{display_name}" 的包内文件夹名包含非法字符，已改为 "{safe_name}"')
        folder_name = self._dedupe_export_folder_name(safe_name, seen_folder_names)
        if folder_name != safe_name:
            warnings.append(f'模组 "{display_name}" 的包内文件夹名 "{safe_name}" 重名，已改为 "{folder_name}"')
        return folder_name, warnings

    def _select_export_asset(
        self,
        mod: dict[str, Any],
        token_info,
        active_token_set: set[str],
    ) -> dict[str, Any]:
        workshop_variant = mod.get("coexist_workshop_variant")
        if token_info.source_preference == "steam" and workshop_variant:
            return dict(workshop_variant)

        canonical_id = token_info.canonical_package_id
        active_steam_token = build_steam_package_token(canonical_id)
        if workshop_variant and active_steam_token in active_token_set:
            return dict(workshop_variant)

        if token_info.normalized_token and token_info.normalized_token in active_token_set:
            return dict(mod)

        if workshop_variant:
            local_time = max(int(mod.get("file_modify_time") or 0), int(mod.get("file_create_time") or 0))
            workshop_time = max(
                int(workshop_variant.get("file_modify_time") or 0),
                int(workshop_variant.get("file_create_time") or 0),
            )
            if workshop_time > local_time:
                return dict(workshop_variant)

        return dict(mod)

    def _build_language_pack_map(self, visible_mods: list[dict[str, Any]]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for mod in visible_mods:
            package_id = normalize_package_id(mod.get("package_id"))
            if not package_id:
                continue
            owner_result = mod.get("language_pack_owner_result") or {}
            for owner in owner_result.get("owners", []) or []:
                owner_id = normalize_package_id(owner.get("package_id"))
                if not owner_id:
                    continue
                result.setdefault(owner_id, [])
                if package_id not in result[owner_id]:
                    result[owner_id].append(package_id)
        return result

    def _build_interlock_map(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for item in ModInterlock.select().dicts():
            result[str(item.get("id") or "").strip()] = [
                normalize_package_id(mod_id)
                for mod_id in (item.get("chain") or [])
                if normalize_package_id(mod_id)
            ]
        return result

    def _extract_interlock_ids(self, mod: dict[str, Any] | None, interlock_map: dict[str, list[str]]) -> list[str]:
        if not mod:
            return []
        interlock_id = str(mod.get("interlock_id") or "").strip()
        if not interlock_id:
            return []
        return list(interlock_map.get(interlock_id, []))

    def _extract_dependency_ids(self, mod: dict[str, Any]) -> list[str]:
        rules = mod.get("rules") or {}
        result: list[str] = []
        for dep in rules.get("dependencies", []) or []:
            dep_id = normalize_package_id(dep.get("package_id"))
            if dep_id and dep_id not in result:
                result.append(dep_id)
        if result:
            return result
        for dep in mod.get("dependencies_mods", []) or []:
            dep_id = normalize_package_id(dep.get("package_id"))
            if dep_id and dep_id not in result:
                result.append(dep_id)
        return result

    def _write_export_bundle(
        self,
        target_path: str,
        payload: dict[str, Any],
        export_plan: dict[str, Any],
        *,
        cancel_event: threading.Event | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        export_mods = list(export_plan.get("mods") or [])
        warnings = list(export_plan.get("warnings") or [])
        if not export_mods:
            raise ValueError("没有可导出的有效模组目录")

        include_environment_data = bool(payload.get("include_environment_data"))
        total_steps = len(export_mods) + (1 if include_environment_data else 0) + 1
        completed_steps = 0
        profile_entries: list[dict[str, Any]] = []
        with zipfile.ZipFile(
            target_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=normalize_zip_compresslevel(getattr(settings.config, "bundle_compress_level", 6)),
            allowZip64=True,
        ) as bundle:
            for index, mod_entry in enumerate(export_mods, start=1):
                self._check_export_cancelled(cancel_event)
                self._emit_export_progress(
                    task_id,
                    "running",
                    self._compute_export_progress(completed_steps, total_steps),
                    f'正在打包模组 ({index}/{len(export_mods)}): {mod_entry.get("name") or mod_entry.get("folder_name") or mod_entry.get("package_id") or "未知模组"}',
                    metrics={
                        "title": "导出模组包",
                        "phase": "mods",
                        "current": index,
                        "total": len(export_mods),
                        "target_path": target_path,
                    },
                    phase="mods",
                )
                write_tree_to_zip(
                    mod_entry["path"],
                    bundle,
                    f"mods/{mod_entry['folder_name']}",
                    cancel_check=lambda: self._check_export_cancelled(cancel_event),
                )
                completed_steps += 1

            if include_environment_data:
                self._check_export_cancelled(cancel_event)
                self._emit_export_progress(
                    task_id,
                    "running",
                    self._compute_export_progress(completed_steps, total_steps),
                    "正在附带环境数据...",
                    metrics={"title": "导出模组包", "phase": "profile", "target_path": target_path},
                    phase="profile",
                )
                profile_entries = self._write_profile_to_bundle(
                    bundle,
                    str(export_plan.get("profile_id") or "default"),
                    cancel_event=cancel_event,
                )
                completed_steps += 1

            self._check_export_cancelled(cancel_event)
            self._emit_export_progress(
                task_id,
                "running",
                self._compute_export_progress(completed_steps, total_steps),
                "正在写入清单...",
                metrics={"title": "导出模组包", "phase": "manifest", "target_path": target_path},
                phase="manifest",
            )
            manifest = {
                "format": self.FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "app_version": __version__,
                "exported_at": datetime.now().astimezone().isoformat(),
                "export_scope": str(payload.get("export_scope") or "custom"),
                "has_environment_data": bool(profile_entries),
                "profiles": profile_entries,
                "mods": [self._serialize_mod_manifest_entry(item) for item in export_mods],
            }
            bundle.writestr("manifest.json", self._to_json(manifest))

        return {
            "path": target_path,
            "mods": [self._serialize_mod_manifest_entry(item) for item in export_mods],
            "profiles": profile_entries,
            "warnings": warnings,
        }

    def _write_profile_to_bundle(
        self,
        bundle: zipfile.ZipFile,
        profile_id: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> list[dict[str, Any]]:
        profile = self.profile_mgr.get_profile(profile_id)
        source_root = Path(str(profile.user_data_path or "").strip())
        if not source_root.is_dir():
            raise ValueError(f'环境 "{profile.name}" 的用户数据目录不存在，无法导出')
        archive_key = profile.id
        profile_meta = self.data_bundle_mgr._serialize_profile_for_export(profile)  # noqa: SLF001
        bundle.writestr(
            f"environments/{archive_key}/profile.json",
            self._to_json(profile_meta),
        )
        write_tree_to_zip(
            source_root,
            bundle,
            f"environments/{archive_key}/user_data",
            cancel_check=lambda: self._check_export_cancelled(cancel_event),
        )
        return [{
            "archive_key": archive_key,
            "original_profile_id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "game_version": profile.game_version,
            "is_default": profile.id == "default",
        }]

    def _resolve_import_target_root(self, payload: dict[str, Any]) -> str:
        target_kind = str(payload.get("target_kind") or "").strip().lower()
        if target_kind == "self_mods":
            root = str(settings.config.self_mods_path or "").strip()
            return root if root else ""
        if target_kind == "game_install":
            install_path = str(payload.get("game_install_path") or "").strip()
            if not install_path:
                return ""
            return os.path.join(os.path.normpath(install_path), "Mods")
        return ""

    def _build_mod_conflicts(self, target_root: str, mod_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not target_root or not os.path.isdir(target_root):
            return []
        result = []
        existing_names = {entry.name.lower(): entry.path for entry in os.scandir(target_root)}
        for item in mod_entries:
            folder_name = str(item.get("folder_name") or "").strip()
            if not folder_name:
                continue
            existing_path = existing_names.get(folder_name.lower())
            if not existing_path:
                continue
            result.append({
                "folder_name": folder_name,
                "existing_path": existing_path,
            })
        return result

    def _normalize_mod_conflict_plan(self, items: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in items or []:
            if not isinstance(item, dict):
                continue
            folder_name = str(item.get("folder_name") or "").strip()
            mode = str(item.get("mode") or "").strip().lower()
            rename_to = str(item.get("rename_to") or "").strip()
            if not folder_name or mode not in {"overwrite", "skip", "rename"}:
                continue
            result[folder_name.lower()] = {
                "mode": mode,
                "rename_to": rename_to,
            }
        return result

    def _import_mod_directories(
        self,
        bundle: zipfile.ZipFile,
        mod_entries: list[dict[str, Any]],
        target_root: str,
        conflict_plan: dict[str, dict[str, Any]],
        *,
        cancel_event: threading.Event | None = None,
        progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not target_root:
            raise ValueError("未指定有效的模组导入目标")
        os.makedirs(target_root, exist_ok=True)
        warnings: list[str] = []
        imported_mods: list[dict[str, Any]] = []
        skipped_mods: list[dict[str, Any]] = []
        renamed_mods: list[dict[str, Any]] = []
        normalized_entries = [item for item in mod_entries if str(item.get("folder_name") or "").strip()]
        total_mods = len(normalized_entries)

        for index, item in enumerate(normalized_entries, start=1):
            self._check_import_cancelled(cancel_event)
            if progress_callback:
                progress_callback(index, total_mods, item)
            folder_name = str(item.get("folder_name") or "").strip()
            plan = conflict_plan.get(folder_name.lower(), {"mode": "overwrite", "rename_to": ""})
            destination_name = folder_name
            destination_path = os.path.join(target_root, destination_name)
            if os.path.exists(destination_path):
                mode = plan.get("mode", "overwrite")
                if mode == "skip":
                    skipped_mods.append({"folder_name": folder_name, "path": destination_path})
                    continue
                if mode == "rename":
                    destination_name = plan.get("rename_to") or self._build_unique_import_name(target_root, folder_name)
                    destination_path = os.path.join(target_root, destination_name)
                    renamed_mods.append({"from": folder_name, "to": destination_name})
            staging_root = self._extract_mod_directory_to_staging(
                bundle,
                folder_name,
                destination_path,
                cancel_event=cancel_event,
            )
            try:
                replace_dir_atomically(destination_path, staging_root)
            finally:
                shutil.rmtree(staging_root, ignore_errors=True)
            imported_mods.append({"folder_name": destination_name, "path": destination_path})
            if destination_name != folder_name:
                warnings.append(f'模组 "{folder_name}" 已另存为 "{destination_name}"')

        return {
            "warnings": warnings,
            "imported_mods": imported_mods,
            "skipped_mods": skipped_mods,
            "renamed_mods": renamed_mods,
        }

    def _extract_mod_directory_to_staging(
        self,
        bundle: zipfile.ZipFile,
        folder_name: str,
        destination_path: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> Path:
        staging_root = create_sibling_stage_dir(destination_path, "mod-import-")
        extract_prefix_to_dir(
            bundle,
            f"mods/{folder_name}",
            staging_root,
            cancel_check=lambda: self._check_import_cancelled(cancel_event),
        )
        return staging_root

    def _build_unique_import_name(self, target_root: str, folder_name: str) -> str:
        index = 1
        while True:
            candidate = f"{folder_name}_imported_{index}"
            if not os.path.exists(os.path.join(target_root, candidate)):
                return candidate
            index += 1

    def _read_active_tokens(self, profile_id: str, context) -> list[str]:
        current_mgr = self.load_order_mgr_provider() if self.load_order_mgr_provider else None
        if current_mgr and getattr(current_mgr, "context", None) and getattr(current_mgr.context, "profile_id", None) == profile_id:
            return list((current_mgr.read_active_mods() or {}).get("active_mods", []) or [])
        mgr = LoadOrderManager(context)
        return list((mgr.read_active_mods() or {}).get("active_mods", []) or [])

    def _serialize_mod_manifest_entry(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "folder_name": item.get("folder_name"),
            "original_folder_name": item.get("original_folder_name") or item.get("folder_name"),
            "package_id": item.get("package_id"),
            "name": item.get("name"),
            "store": item.get("store"),
            "workshop_id": item.get("workshop_id"),
            "path_hash": item.get("path_hash"),
            "file_modify_time": int(item.get("file_modify_time") or 0),
        }

    @staticmethod
    def _is_exportable_mod_asset(mod: dict[str, Any] | None, path_scope: _ProfilePathScope | None) -> bool:
        if not mod or not path_scope:
            return False
        path = str(mod.get("path") or "").strip()
        if not path:
            return False
        return path_scope.domain_for_path(path) in {"local", "self", "workshop"}

    @staticmethod
    def _read_json_from_zip(bundle: zipfile.ZipFile, member_name: str, default: Any = None) -> Any:
        try:
            with bundle.open(member_name, "r") as handle:
                import json
                return json.loads(handle.read().decode("utf-8"))
        except KeyError:
            return default

    @staticmethod
    def _to_json(payload: dict[str, Any]) -> str:
        import json
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @staticmethod
    def _normalize_compare_path(path: str) -> str:
        normalized_path = str(path or "").strip()
        if not normalized_path:
            return ""
        return os.path.normcase(os.path.normpath(normalized_path))

    @staticmethod
    def _format_bytes(size_bytes: int) -> str | None:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(max(0, int(size_bytes or 0)))
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
            value /= 1024

    def _emit_export_progress(
        self,
        task_id: str | None,
        status: str,
        progress: int,
        message: str,
        metrics: dict[str, Any] | None = None,
        *,
        phase: str = "",
    ) -> None:
        if not task_id:
            return
        payload_metrics = {
            "title": "导出模组包",
            "phase": phase,
            **dict(metrics or {}),
        }
        EventBus.emit_progress(task_id, self.EXPORT_TASK_TYPE, status=status, progress=progress, message=message, metrics=payload_metrics)

    def _emit_import_progress(
        self,
        task_id: str | None,
        status: str,
        progress: int,
        message: str,
        metrics: dict[str, Any] | None = None,
        *,
        phase: str = "",
    ) -> None:
        if not task_id:
            return
        payload_metrics = {
            "title": "导入模组包",
            "phase": phase,
            **dict(metrics or {}),
        }
        EventBus.emit_progress(task_id, self.IMPORT_TASK_TYPE, status=status, progress=progress, message=message, metrics=payload_metrics)

    @staticmethod
    def _compute_export_progress(completed_steps: int, total_steps: int) -> int:
        if total_steps <= 0:
            return 0
        return max(1, min(99, int((completed_steps / total_steps) * 100)))

    @staticmethod
    def _compute_import_progress(completed_steps: int, total_steps: int) -> int:
        if total_steps <= 0:
            return 0
        return max(1, min(99, int((completed_steps / total_steps) * 100)))

    @staticmethod
    def _check_export_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("模组包导出已取消")

    @staticmethod
    def _check_import_cancelled(cancel_event: threading.Event | None) -> None:
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("模组包导入已取消")

    @staticmethod
    def _cleanup_partial_export(target_path: str) -> None:
        normalized_path = str(target_path or "").strip()
        if normalized_path and os.path.exists(normalized_path):
            try:
                os.remove(normalized_path)
            except OSError:
                logger.warning("清理未完成的导出包失败：%s", normalized_path, exc_info=True)

    @staticmethod
    def _is_deployed_workshop_link(path: str) -> bool:
        normalized_path = str(path or "").strip()
        if not normalized_path or not os.path.exists(normalized_path):
            return False
        if os.path.islink(normalized_path):
            return True
        return bool(os.name == "nt" and FileManager._is_junction_windows(normalized_path))  # noqa: SLF001
