import json
import os
import platform
import re
import time
from pathlib import Path
from typing import Any

from backend.managers.mgr_mod_settings import ModSettingsManager
from backend.managers.mgr_profile import ProfileContext
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.paths.core import path_key
from backend.settings import DATA_DIR
from backend.utils.logger import logger
from backend.utils.tools import normalize_package_id, normalize_workshop_id


MOD_RESIDUE_WHITELIST_PATH = DATA_DIR / "mod_residue_whitelist.json"


class ModResidueManager:
    """扫描并管理卸载后残留的模组目录和设置文件。"""

    WHITELIST_VERSION = 1

    @classmethod
    def get_overview(
        cls,
        search_paths: list[str] | tuple[str, ...] | None,
        context: ProfileContext | None = None,
        active_tokens: list[str] | None = None,
    ) -> dict[str, Any]:
        roots = cls._normalize_existing_roots(search_paths or [])
        whitelist_entries = cls.get_whitelist()
        whitelist_keys = {cls._path_key(item.get("path")) for item in whitelist_entries if item.get("path")}

        directory_records = cls._scan_residue_directories(roots, whitelist_keys)
        settings_records = cls._scan_residue_settings(context, active_tokens or [], whitelist_keys)

        workshop_ids = cls._collect_workshop_ids(directory_records, settings_records)
        details = cls._load_workshop_details(workshop_ids)
        settings_folder_identity = cls._build_settings_folder_identity(settings_records, details)

        groups: dict[str, dict[str, Any]] = {}
        folder_group_keys: dict[str, str] = {}

        for record in directory_records:
            identity = cls._resolve_directory_identity(record, details, settings_folder_identity)
            group = cls._ensure_group(groups, identity)
            group["items"].append(cls._build_directory_item(record, identity))
            folder_key = str(record.get("folder_name") or "").strip().lower()
            if folder_key:
                folder_group_keys[folder_key] = group["key"]

        for record in settings_records:
            identity = cls._resolve_settings_identity(record, details, folder_group_keys)
            group = cls._ensure_group(groups, identity)
            group["items"].append(cls._build_settings_item(record, identity))

        finalized_groups = cls._finalize_groups(groups)
        summary = cls._build_summary(finalized_groups, whitelist_entries)
        return {
            "summary": summary,
            "groups": finalized_groups,
            "whitelist": whitelist_entries,
            "scan_roots": roots,
        }

    @classmethod
    def get_whitelist(cls) -> list[dict[str, Any]]:
        data = cls._read_whitelist_data()
        entries = []
        seen: set[str] = set()
        for item in data.get("paths") or []:
            path = cls._display_path(item.get("path"))
            key = cls._path_key(path)
            if not path or not key or key in seen:
                continue
            seen.add(key)
            entries.append({
                "path": path,
                "name": str(item.get("name") or Path(path).name or path).strip(),
                "type": cls._resolve_path_type(path, item.get("type")),
                "added_at": int(item.get("added_at") or 0),
            })
        entries.sort(key=lambda item: str(item.get("name") or "").lower())
        return entries

    @classmethod
    def add_whitelist_paths(cls, paths: list[str] | tuple[str, ...] | str | None) -> dict[str, Any]:
        current = cls.get_whitelist()
        by_key = {cls._path_key(item.get("path")): dict(item) for item in current if item.get("path")}
        added = []
        for raw_path in cls._normalize_input_paths(paths):
            path = cls._display_path(raw_path)
            key = cls._path_key(path)
            if not path or not key or key in by_key:
                continue
            entry = {
                "path": path,
                "name": Path(path).name or path,
                "type": cls._resolve_path_type(path),
                "added_at": int(time.time() * 1000),
            }
            by_key[key] = entry
            added.append(entry)
        cls._write_whitelist_data(list(by_key.values()))
        return {"added": added, "whitelist": cls.get_whitelist()}

    @classmethod
    def remove_whitelist_paths(cls, paths: list[str] | tuple[str, ...] | str | None) -> dict[str, Any]:
        remove_keys = {cls._path_key(path) for path in cls._normalize_input_paths(paths)}
        kept = []
        removed = []
        for item in cls.get_whitelist():
            if cls._path_key(item.get("path")) in remove_keys:
                removed.append(item)
            else:
                kept.append(item)
        cls._write_whitelist_data(kept)
        return {"removed": removed, "whitelist": cls.get_whitelist()}

    @classmethod
    def _scan_residue_directories(cls, roots: list[str], whitelist_keys: set[str]) -> list[dict[str, Any]]:
        records = []
        for root in roots:
            try:
                with os.scandir(root) as it:
                    for entry in it:
                        try:
                            if not entry.is_dir(follow_symlinks=False):
                                continue
                        except OSError:
                            continue
                        path = cls._display_path(entry.path)
                        key = cls._path_key(path)
                        if not key or key in whitelist_keys:
                            continue
                        if cls._has_about_file(path):
                            continue
                        stat = cls._safe_stat(path)
                        file_count, total_size = cls._collect_folder_stats(path)
                        records.append({
                            "path": path,
                            "path_key": key,
                            "folder_name": entry.name,
                            "parent_path": root,
                            "file_count": file_count,
                            "total_size": total_size,
                            "modified_time": int((stat.st_mtime if stat else 0) * 1000),
                            "workshop_id_candidates": cls._extract_workshop_id_candidates(entry.name),
                        })
            except OSError as exc:
                logger.warning("扫描残留目录失败: root=%s error=%s", root, exc)
        records.sort(key=lambda item: str(item.get("path") or "").lower())
        return records

    @classmethod
    def _scan_residue_settings(cls, context: ProfileContext | None, active_tokens: list[str], whitelist_keys: set[str]) -> list[dict[str, Any]]:
        if not context:
            return []
        try:
            overview = ModSettingsManager.get_overview(context, active_tokens)
        except Exception as exc:
            logger.debug("扫描 ModSettings 残留失败: %s", exc, exc_info=True)
            return []

        records = []
        for mod_group in overview.get("mod_groups") or []:
            if mod_group.get("status") not in {"uninstalled", "unknown"}:
                continue
            for setting_group in mod_group.get("setting_groups") or []:
                for item in setting_group.get("files") or []:
                    path = cls._display_path(item.get("file_path"))
                    path_key = cls._path_key(path)
                    if not path or path_key in whitelist_keys:
                        continue
                    records.append({
                        "path": path,
                        "path_key": path_key,
                        "name": str(item.get("name") or Path(path).name).strip(),
                        "folder_name": str(item.get("folder_name") or "").strip(),
                        "file_size": int(item.get("file_size") or 0),
                        "modified_time": int(item.get("modified_time") or 0),
                        "source_label": str(item.get("source_label") or "设置文件").strip(),
                        "mod_group_key": str(mod_group.get("group_key") or "").strip(),
                        "package_id": normalize_package_id(mod_group.get("package_id")),
                        "mod_name": str(mod_group.get("mod_name") or "").strip(),
                        "workshop_id": normalize_workshop_id(mod_group.get("workshop_id"), digits_only=True, min_length=6, max_length=20),
                        "match_confidence": str(mod_group.get("match_confidence") or "unknown").strip(),
                    })
        records.sort(key=lambda item: str(item.get("path") or "").lower())
        return records

    @classmethod
    def _collect_workshop_ids(cls, directory_records: list[dict[str, Any]], settings_records: list[dict[str, Any]]) -> list[str]:
        result = []
        seen: set[str] = set()
        for record in directory_records:
            for workshop_id in record.get("workshop_id_candidates") or []:
                if workshop_id and workshop_id not in seen:
                    seen.add(workshop_id)
                    result.append(workshop_id)
        for record in settings_records:
            workshop_id = record.get("workshop_id")
            if workshop_id and workshop_id not in seen:
                seen.add(workshop_id)
                result.append(workshop_id)
        return result

    @classmethod
    def _load_workshop_details(cls, workshop_ids: list[str]) -> dict[str, dict[str, Any]]:
        return SteamWebAPI.get_workshop_details(workshop_ids, trace_label="mod-residue")

    @classmethod
    def _build_settings_folder_identity(
        cls,
        settings_records: list[dict[str, Any]],
        details: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        candidates: dict[str, dict[str, Any] | None] = {}
        for record in settings_records:
            folder_key = str(record.get("folder_name") or "").strip().lower()
            if not folder_key:
                continue
            identity = cls._identity_from_values(
                workshop_id=record.get("workshop_id",""),
                package_id=record.get("package_id",""),
                mod_name=record.get("mod_name",""),
                detail=details.get(record.get("workshop_id") or "", {}),
                fallback_key=f"settings:{record.get('mod_group_key') or folder_key}",
                fallback_name=record.get("mod_name") or record.get("folder_name") or "未知模组",
                confidence=record.get("match_confidence") or "unknown",
            )
            if folder_key not in candidates:
                candidates[folder_key] = identity
                continue
            current = candidates.get(folder_key)
            if current and current.get("key") != identity.get("key"):
                candidates[folder_key] = None
            elif current:
                candidates[folder_key] = identity
        return {key: value for key, value in candidates.items() if value}

    @classmethod
    def _resolve_directory_identity(
        cls,
        record: dict[str, Any],
        details: dict[str, dict[str, Any]],
        settings_folder_identity: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        selected_id = ""
        selected_detail = {}
        for workshop_id in record.get("workshop_id_candidates") or []:
            detail = details.get(workshop_id) or {}
            if detail.get("available"):
                selected_id = workshop_id
                selected_detail = detail
                break
        if not selected_id and record.get("workshop_id_candidates"):
            selected_id = record["workshop_id_candidates"][0]
            selected_detail = details.get(selected_id) or {}

        if selected_id:
            return cls._identity_from_values(
                workshop_id=selected_id,
                package_id=selected_detail.get("package_id",""),
                mod_name=selected_detail.get("title","") or selected_detail.get("name",""),
                detail=selected_detail,
                fallback_key=f"workshop:{selected_id}",
                fallback_name=record.get("folder_name") or f"Workshop {selected_id}",
                confidence="high" if selected_detail.get("available") else "medium",
            )

        folder_key = str(record.get("folder_name") or "").strip().lower()
        if folder_key and settings_folder_identity.get(folder_key):
            return dict(settings_folder_identity[folder_key])

        return cls._identity_from_values(
            workshop_id="",
            package_id="",
            mod_name="",
            detail={},
            fallback_key=f"folder:{record.get('path_key')}",
            fallback_name=record.get("folder_name") or "未知模组",
            confidence="unknown",
        )

    @classmethod
    def _resolve_settings_identity(
        cls,
        record: dict[str, Any],
        details: dict[str, dict[str, Any]],
        folder_group_keys: dict[str, str],
    ) -> dict[str, Any]:
        folder_key = str(record.get("folder_name") or "").strip().lower()
        if not record.get("workshop_id") and not record.get("package_id") and folder_key in folder_group_keys:
            return {
                "key": folder_group_keys[folder_key],
                "mod_name": record.get("mod_name") or record.get("folder_name") or "未知模组",
                "package_id": "",
                "workshop_id": "",
                "workshop_detail": {},
                "match_confidence": record.get("match_confidence") or "unknown",
            }
        detail = details.get(record.get("workshop_id") or "") or {}
        return cls._identity_from_values(
            workshop_id=record.get("workshop_id",""),
            package_id=record.get("package_id",""),
            mod_name=record.get("mod_name",""),
            detail=detail,
            fallback_key=f"settings:{record.get('mod_group_key') or record.get('path_key')}",
            fallback_name=record.get("mod_name") or record.get("folder_name") or "未知模组",
            confidence=record.get("match_confidence") or "unknown",
        )

    @staticmethod
    def _identity_from_values(
        *,
        workshop_id: str,
        package_id: str,
        mod_name: str,
        detail: dict[str, Any],
        fallback_key: str,
        fallback_name: str,
        confidence: str,
    ) -> dict[str, Any]:
        detail = detail or {}
        normalized_workshop_id = normalize_workshop_id(workshop_id, digits_only=True, min_length=6, max_length=20)
        normalized_package_id = normalize_package_id(package_id or detail.get("package_id"))
        if normalized_workshop_id:
            key = f"workshop:{normalized_workshop_id}"
        elif normalized_package_id:
            key = f"package:{normalized_package_id}"
        else:
            key = fallback_key
        title = str(detail.get("title") or mod_name or detail.get("name") or fallback_name or "未知模组").strip()
        return {
            "key": key,
            "mod_name": title or "未知模组",
            "package_id": normalized_package_id,
            "workshop_id": normalized_workshop_id,
            "workshop_detail": detail or {},
            "match_confidence": confidence or "unknown",
        }

    @staticmethod
    def _ensure_group(groups: dict[str, dict[str, Any]], identity: dict[str, Any]) -> dict[str, Any]:
        key = str(identity.get("key") or "").strip()
        group = groups.setdefault(key, {
            "key": key,
            "mod_name": identity.get("mod_name") or "未知模组",
            "package_id": identity.get("package_id") or "",
            "workshop_id": identity.get("workshop_id") or "",
            "workshop_detail": identity.get("workshop_detail") or {},
            "match_confidence": identity.get("match_confidence") or "unknown",
            "items": [],
        })
        if not group.get("workshop_detail") and identity.get("workshop_detail"):
            group["workshop_detail"] = identity.get("workshop_detail")
        if not group.get("package_id") and identity.get("package_id"):
            group["package_id"] = identity.get("package_id")
        if not group.get("workshop_id") and identity.get("workshop_id"):
            group["workshop_id"] = identity.get("workshop_id")
        if group.get("mod_name") == "未知模组" and identity.get("mod_name"):
            group["mod_name"] = identity.get("mod_name")
        return group

    @staticmethod
    def _build_directory_item(record: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"directory:{record.get('path_key')}",
            "type": "directory",
            "type_label": "残留文件夹",
            "path": record.get("path") or "",
            "name": record.get("folder_name") or Path(str(record.get("path") or "")).name,
            "parent_path": record.get("parent_path") or "",
            "file_count": int(record.get("file_count") or 0),
            "total_size": int(record.get("total_size") or 0),
            "modified_time": int(record.get("modified_time") or 0),
            "workshop_id": identity.get("workshop_id") or "",
            "workshop_id_candidates": record.get("workshop_id_candidates") or [],
            "can_whitelist": True,
        }

    @staticmethod
    def _build_settings_item(record: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"settings_file:{record.get('path_key')}",
            "type": "settings_file",
            "type_label": "模组设置文件",
            "path": record.get("path") or "",
            "name": record.get("name") or Path(str(record.get("path") or "")).name,
            "parent_path": str(Path(str(record.get("path") or "")).parent) if record.get("path") else "",
            "folder_name": record.get("folder_name") or "",
            "file_count": 1,
            "total_size": int(record.get("file_size") or 0),
            "modified_time": int(record.get("modified_time") or 0),
            "workshop_id": identity.get("workshop_id") or "",
            "can_whitelist": True,
        }

    @classmethod
    def _finalize_groups(cls, groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for group in groups.values():
            items = group.get("items") or []
            items.sort(key=lambda item: (0 if item.get("type") == "directory" else 1, str(item.get("name") or "").lower()))
            group["items"] = items
            group["item_count"] = len(items)
            group["directory_count"] = sum(1 for item in items if item.get("type") == "directory")
            group["settings_file_count"] = sum(1 for item in items if item.get("type") == "settings_file")
            group["total_size"] = sum(int(item.get("total_size") or 0) for item in items)
            group["file_count"] = sum(int(item.get("file_count") or 0) for item in items)
            result.append(group)
        result.sort(key=lambda item: (
            0 if item.get("workshop_id") else 1,
            str(item.get("mod_name") or "").lower(),
            str(item.get("key") or "").lower(),
        ))
        return result

    @staticmethod
    def _build_summary(groups: list[dict[str, Any]], whitelist_entries: list[dict[str, Any]]) -> dict[str, int]:
        item_count = sum(int(group.get("item_count") or 0) for group in groups)
        return {
            "group_count": len(groups),
            "item_count": item_count,
            "directory_count": sum(int(group.get("directory_count") or 0) for group in groups),
            "settings_file_count": sum(int(group.get("settings_file_count") or 0) for group in groups),
            "total_size": sum(int(group.get("total_size") or 0) for group in groups),
            "file_count": sum(int(group.get("file_count") or 0) for group in groups),
            "whitelist_count": len(whitelist_entries),
        }

    @staticmethod
    def _extract_workshop_id_candidates(name: str) -> list[str]:
        seen: set[str] = set()
        result = []
        for part in re.findall(r"\d+", str(name or "")):
            workshop_id = normalize_workshop_id(part, digits_only=True, min_length=6, max_length=20)
            if workshop_id and workshop_id not in seen:
                seen.add(workshop_id)
                result.append(workshop_id)
        return result

    @staticmethod
    def _has_about_file(path: str) -> bool:
        about_dir = Path(path) / "About"
        return (about_dir / "About.xml").is_file() or (about_dir / "About.xml.disabled").is_file()

    @staticmethod
    def _collect_folder_stats(path: str) -> tuple[int, int]:
        file_count = 0
        total_size = 0
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                file_count += 1
                                total_size += int(entry.stat(follow_symlinks=False).st_size or 0)
                            elif entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)
                        except OSError:
                            continue
            except OSError:
                continue
        return file_count, total_size

    @staticmethod
    def _safe_stat(path: str):
        try:
            return os.stat(path)
        except OSError:
            return None

    @classmethod
    def _normalize_existing_roots(cls, paths: list[str] | tuple[str, ...]) -> list[str]:
        roots = []
        seen: set[str] = set()
        for raw_path in paths:
            path = cls._display_path(raw_path)
            key = cls._path_key(path)
            if not path or not key or key in seen or not os.path.isdir(path):
                continue
            seen.add(key)
            roots.append(path)
        return roots

    @staticmethod
    def _normalize_input_paths(paths: list[str] | tuple[str, ...] | str | None) -> list[str]:
        if not paths:
            return []
        if isinstance(paths, str):
            return [paths] if paths.strip() else []
        return [str(path or "").strip() for path in paths if str(path or "").strip()]

    @staticmethod
    def _display_path(path: Any) -> str:
        value = str(path or "").strip()
        if not value:
            return ""
        return os.path.abspath(value)

    @staticmethod
    def _path_key(path: Any) -> str:
        return path_key(os.path.abspath(str(path or "").strip()) if str(path or "").strip() else "", system_name=platform.system())

    @staticmethod
    def _resolve_path_type(path: Any, fallback: Any = "") -> str:
        value = str(path or "").strip()
        if value:
            if os.path.isfile(value):
                return "file"
            if os.path.isdir(value):
                return "directory"
        fallback_value = str(fallback or "").strip().lower()
        return fallback_value if fallback_value in {"file", "directory"} else "path"

    @classmethod
    def _read_whitelist_data(cls) -> dict[str, Any]:
        if not MOD_RESIDUE_WHITELIST_PATH.exists():
            return {"version": cls.WHITELIST_VERSION, "paths": []}
        try:
            with open(MOD_RESIDUE_WHITELIST_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            logger.warning("读取卸载残留白名单失败，已按空白名单处理: %s", exc)
            return {"version": cls.WHITELIST_VERSION, "paths": []}
        if not isinstance(data, dict):
            return {"version": cls.WHITELIST_VERSION, "paths": []}
        return data

    @classmethod
    def _write_whitelist_data(cls, entries: list[dict[str, Any]]) -> None:
        MOD_RESIDUE_WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": cls.WHITELIST_VERSION,
            "paths": [
                {
                    "path": cls._display_path(item.get("path")),
                    "name": str(item.get("name") or Path(str(item.get("path") or "")).name).strip(),
                    "type": cls._resolve_path_type(item.get("path"), item.get("type")),
                    "added_at": int(item.get("added_at") or 0),
                }
                for item in entries
                if cls._display_path(item.get("path"))
            ],
        }
        with open(MOD_RESIDUE_WHITELIST_PATH, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
