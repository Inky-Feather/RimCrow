import os
import shutil
from pathlib import Path
from typing import Any

from backend.database.dao import ModDAO
from backend.load_order.package_tokens import parse_package_token
from backend.managers.mgr_profile import ProfileContext
from backend.utils.tools import normalize_package_id


class ModConfigManager:
    """管理当前环境下官方 ModSettings 配置文件。"""

    OFFICIAL_PREFIX = "Mod_"
    OFFICIAL_SUFFIX = ".xml"

    @classmethod
    def get_overview(
        cls,
        context: ProfileContext | None,
        active_tokens: list[str] | None = None,
    ) -> dict[str, Any]:
        if not context:
            raise ValueError("环境配置上下文缺失")

        config_path = Path(str(context.game_config_path or "").strip())
        if not str(config_path):
            raise ValueError("未指定游戏配置路径")

        files = cls._scan_official_files(config_path)
        candidate_map = cls._build_instance_candidates(context, active_tokens or [])

        grouped: dict[str, dict[str, Any]] = {}
        orphan_count = 0

        for file_info in files:
            candidate = cls._match_candidate(file_info["file_name"], candidate_map)
            if candidate:
                settings_class_name = cls._extract_settings_class_name(
                    file_info["file_name"],
                    candidate["folder_name"],
                )
                group_key = cls._build_group_key(candidate["package_id"], settings_class_name)
                group = grouped.setdefault(
                    group_key,
                    {
                        "group_key": group_key,
                        "package_id": candidate["package_id"],
                        "mod_name": candidate["mod_name"],
                        "settings_class_name": settings_class_name,
                        "status": "matched",
                        "instances": [],
                    },
                )
                group["instances"].append(
                    {
                        "instance_key": file_info["file_path"],
                        "file_name": file_info["file_name"],
                        "file_path": file_info["file_path"],
                        "settings_class_name": settings_class_name,
                        "folder_name": candidate["folder_name"],
                        "package_id": candidate["package_id"],
                        "mod_name": candidate["mod_name"],
                        "mod_path": candidate["mod_path"],
                        "source_kind": candidate["source_kind"],
                        "source_label": cls._source_label(candidate["source_kind"]),
                        "workshop_id": candidate["workshop_id"],
                        "is_active_instance": candidate["is_active_instance"],
                        "file_size": file_info["file_size"],
                        "modified_time": file_info["modified_time"],
                    }
                )
                continue

            orphan_count += 1
            group_key = f"orphan:{file_info['file_name']}"
            grouped[group_key] = {
                "group_key": group_key,
                "package_id": "",
                "mod_name": "未识别模组",
                "status": "orphan",
                "instances": [
                    {
                        "instance_key": file_info["file_path"],
                        "file_name": file_info["file_name"],
                        "file_path": file_info["file_path"],
                        "settings_class_name": "",
                        "folder_name": "",
                        "package_id": "",
                        "mod_name": "未识别模组",
                        "mod_path": "",
                        "source_kind": "unknown",
                        "source_label": "未知",
                        "workshop_id": "",
                        "is_active_instance": False,
                        "file_size": file_info["file_size"],
                        "modified_time": file_info["modified_time"],
                    }
                ],
            }

        groups = list(grouped.values())
        for group in groups:
            group["instances"].sort(
                key=lambda item: (
                    0 if item.get("is_active_instance") else 1,
                    cls._source_sort_key(item.get("source_kind")),
                    str(item.get("file_name") or "").lower(),
                )
            )
            group["is_active_group"] = any(
                bool(item.get("is_active_instance")) for item in group["instances"]
            )
            group["instance_count"] = len(group["instances"])
            group["can_sync"] = (
                group["status"] == "matched"
                and bool(str(group.get("settings_class_name") or "").strip())
                and len(group["instances"]) > 1
            )

        groups.sort(
            key=lambda item: (
                0 if item.get("status") == "matched" else 1,
                0 if item.get("is_active_group") else 1,
                str(item.get("mod_name") or "").lower(),
                str(item.get("settings_class_name") or "").lower(),
                str(item.get("package_id") or "").lower(),
            )
        )

        return {
            "config_path": str(config_path),
            "total_files": len(files),
            "matched_group_count": sum(1 for item in groups if item.get("status") == "matched"),
            "orphan_file_count": orphan_count,
            "groups": groups,
        }

    @classmethod
    def sync_group_instance(
        cls,
        context: ProfileContext | None,
        active_tokens: list[str] | None,
        source_path: str,
        target_path: str,
    ) -> dict[str, Any]:
        if not context:
            raise ValueError("环境配置上下文缺失")

        normalized_source = cls._normalize_path(source_path)
        normalized_target = cls._normalize_path(target_path)
        if not normalized_source or not normalized_target:
            raise ValueError("源文件或目标文件不能为空")
        if normalized_source == normalized_target:
            raise ValueError("源文件和目标文件不能相同")

        overview = cls.get_overview(context, active_tokens or [])
        entry_map: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for group in overview["groups"]:
            for item in group["instances"]:
                entry_map[cls._normalize_path(item.get("file_path"))] = (group, item)

        if normalized_source not in entry_map:
            normalized_source = cls._resolve_entry_key(source_path, entry_map)
        if normalized_source not in entry_map:
            raise ValueError("源文件不在当前环境的配置列表中")
        if normalized_target not in entry_map:
            normalized_target = cls._resolve_entry_key(target_path, entry_map)
        if normalized_target not in entry_map:
            raise ValueError("目标文件不在当前环境的配置列表中")

        source_group, source_item = entry_map[normalized_source]
        target_group, target_item = entry_map[normalized_target]

        if source_group.get("status") != "matched" or target_group.get("status") != "matched":
            raise ValueError("未识别文件不能互相覆盖")
        if not source_group.get("group_key") or source_group.get("group_key") != target_group.get("group_key"):
            raise ValueError("只能在同一种配置之间互相覆盖")

        source_file = Path(str(source_item["file_path"]))
        target_file = Path(str(target_item["file_path"]))
        if not source_file.is_file():
            raise ValueError("源配置文件不存在")
        if not target_file.is_file():
            raise ValueError("目标配置文件不存在")

        shutil.copyfile(source_file, target_file)

        refreshed = cls.get_overview(context, active_tokens or [])
        return {
            "source_path": str(source_file),
            "target_path": str(target_file),
            "package_id": str(source_group["package_id"]),
            "settings_class_name": str(source_group.get("settings_class_name") or ""),
            "overview": refreshed,
        }

    @classmethod
    def _scan_official_files(cls, config_path: Path) -> list[dict[str, Any]]:
        if not config_path.exists() or not config_path.is_dir():
            return []

        files: list[dict[str, Any]] = []
        for item in config_path.iterdir():
            if not item.is_file():
                continue
            if not cls._is_official_config_filename(item.name):
                continue
            stat = item.stat()
            files.append(
                {
                    "file_name": item.name,
                    "file_path": str(item.resolve()),
                    "file_size": int(stat.st_size or 0),
                    "modified_time": int(stat.st_mtime * 1000),
                }
            )
        files.sort(key=lambda item: str(item["file_name"]).lower())
        return files

    @classmethod
    def _build_instance_candidates(
        cls,
        context: ProfileContext,
        active_tokens: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        active_preference_map = cls._build_active_preference_map(active_tokens)
        visible_mods = ModDAO.get_profile_mods(context)
        active_path_map = cls._build_active_instance_path_map(visible_mods, active_preference_map)
        preferred_names = {
            normalize_package_id(mod.get("package_id")): str(mod.get("name") or "").strip()
            for mod in visible_mods
            if normalize_package_id(mod.get("package_id"))
        }
        runtime_assets = cls._collect_runtime_assets(
            visible_mods,
            ModDAO.get_triple_domain_assets(context),
        )
        candidates: dict[str, list[dict[str, Any]]] = {}
        seen_paths: set[str] = set()

        for instance in runtime_assets:
            package_id = normalize_package_id(instance.get("package_id"))
            if not package_id:
                continue

            mod_path = str(instance.get("path") or "").strip()
            normalized_path = cls._normalize_path(mod_path)
            if not normalized_path or normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)

            folder_name = Path(mod_path).name
            if not folder_name:
                continue
            source_kind = cls._resolve_source_kind(instance)
            candidate = {
                "package_id": package_id,
                "mod_name": str(instance.get("name") or preferred_names.get(package_id) or package_id).strip() or package_id,
                "mod_path": mod_path,
                "folder_name": folder_name,
                "source_kind": source_kind,
                "workshop_id": str(instance.get("workshop_id") or "").strip(),
                "is_active_instance": active_path_map.get(package_id) == normalized_path,
            }
            candidates.setdefault(folder_name.lower(), []).append(candidate)

        return candidates

    @classmethod
    def _match_candidate(
        cls,
        file_name: str,
        candidate_map: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        normalized_name = str(file_name or "").strip()
        if not cls._is_official_config_filename(normalized_name):
            return None

        best_folder_key = ""
        lowered_name = normalized_name.lower()
        for folder_key in candidate_map.keys():
            prefix = f"{cls.OFFICIAL_PREFIX}{folder_key}_"
            if lowered_name.startswith(prefix.lower()) and len(folder_key) > len(best_folder_key):
                best_folder_key = folder_key

        if not best_folder_key:
            return None

        matched_candidates = candidate_map.get(best_folder_key) or []
        if not matched_candidates:
            return None

        active_candidates = [item for item in matched_candidates if item.get("is_active_instance")]
        if active_candidates:
            return dict(active_candidates[0])
        return dict(matched_candidates[0])

    @classmethod
    def _extract_settings_class_name(cls, file_name: str, folder_name: str) -> str:
        normalized_name = str(file_name or "").strip()
        normalized_folder = str(folder_name or "").strip()
        if not normalized_name or not normalized_folder:
            return ""
        prefix = f"{cls.OFFICIAL_PREFIX}{normalized_folder}_"
        lowered_name = normalized_name.lower()
        if not lowered_name.startswith(prefix.lower()) or not lowered_name.endswith(cls.OFFICIAL_SUFFIX.lower()):
            return ""
        return normalized_name[len(prefix) : -len(cls.OFFICIAL_SUFFIX)]

    @classmethod
    def _build_active_preference_map(cls, active_tokens: list[str]) -> dict[str, str]:
        preference_map: dict[str, str] = {}
        for raw_token in active_tokens or []:
            token_info = parse_package_token(raw_token)
            if not token_info.canonical_package_id:
                continue
            if token_info.source_preference == "steam":
                preference_map[token_info.canonical_package_id] = "steam"
                continue
            preference_map.setdefault(token_info.canonical_package_id, "local")
        return preference_map

    @classmethod
    def _build_active_instance_path_map(
        cls,
        visible_mods: list[dict[str, Any]],
        active_preference_map: dict[str, str],
    ) -> dict[str, str]:
        active_path_map: dict[str, str] = {}
        for mod in visible_mods:
            package_id = normalize_package_id(mod.get("package_id"))
            source_preference = active_preference_map.get(package_id)
            if not package_id or not source_preference:
                continue

            selected = mod
            coexist_variant = mod.get("coexist_workshop_variant")
            if (
                source_preference == "steam"
                and isinstance(coexist_variant, dict)
                and coexist_variant
            ):
                selected = coexist_variant

            selected_path = cls._normalize_path(selected.get("path"))
            if selected_path:
                active_path_map[package_id] = selected_path
        return active_path_map

    @classmethod
    def _collect_runtime_assets(
        cls,
        visible_mods: list[dict[str, Any]],
        triple_domain_assets: dict[str, list[dict[str, Any]]] | None,
    ) -> list[dict[str, Any]]:
        runtime_assets: list[dict[str, Any]] = []
        for source_kind in ("local", "self", "workshop", "unknown"):
            for asset in (triple_domain_assets or {}).get(source_kind) or []:
                runtime_assets.append(dict(asset))

        for mod in visible_mods:
            runtime_assets.append(dict(mod))
            coexist_variant = mod.get("coexist_workshop_variant")
            if isinstance(coexist_variant, dict) and coexist_variant:
                runtime_assets.append(dict(coexist_variant))

        return runtime_assets

    @classmethod
    def _resolve_source_kind(cls, mod: dict[str, Any]) -> str:
        store = str(mod.get("store") or mod.get("source") or "").strip().lower()
        if store in {"workshop", "self", "tool", "local", "dlc"}:
            return store
        return "unknown"

    @classmethod
    def _is_official_config_filename(cls, file_name: str) -> bool:
        normalized_name = str(file_name or "").strip()
        return (
            normalized_name.startswith(cls.OFFICIAL_PREFIX)
            and normalized_name.endswith(cls.OFFICIAL_SUFFIX)
            and len(normalized_name) > len(cls.OFFICIAL_PREFIX) + len(cls.OFFICIAL_SUFFIX)
        )

    @staticmethod
    def _normalize_path(path: str | os.PathLike[str] | None) -> str:
        if not path:
            return ""
        return os.path.normcase(os.path.abspath(str(path)))

    @classmethod
    def _resolve_entry_key(
        cls,
        raw_path: str | os.PathLike[str] | None,
        entry_map: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    ) -> str:
        normalized_path = cls._normalize_path(raw_path)
        if normalized_path in entry_map:
            return normalized_path
        if not normalized_path:
            return ""
        for candidate_key, (_group, item) in entry_map.items():
            candidate_path = item.get("file_path")
            try:
                if candidate_path and os.path.samefile(str(raw_path), str(candidate_path)):
                    return candidate_key
            except (FileNotFoundError, OSError, TypeError, ValueError):
                continue
        return ""

    @staticmethod
    def _source_label(source_kind: str) -> str:
        return {
            "local": "本地",
            "workshop": "工坊",
            "self": "管理器目录",
            "tool": "工具",
            "dlc": "DLC",
        }.get(str(source_kind or "").strip().lower(), "未知")

    @staticmethod
    def _source_sort_key(source_kind: str) -> int:
        order = {
            "local": 0,
            "self": 1,
            "workshop": 2,
            "tool": 3,
            "dlc": 4,
            "unknown": 9,
        }
        return order.get(str(source_kind or "").strip().lower(), 9)

    @classmethod
    def _build_group_key(cls, package_id: str, settings_class_name: str) -> str:
        normalized_package_id = str(package_id or "").strip().lower()
        normalized_class_name = str(settings_class_name or "").strip().lower()
        if normalized_package_id and normalized_class_name:
            return f"{normalized_package_id}::{normalized_class_name}"
        return normalized_package_id or normalized_class_name
