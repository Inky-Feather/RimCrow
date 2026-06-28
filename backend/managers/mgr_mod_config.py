import os
import re
import shutil
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from backend.database.dao import ModDAO
from backend.database.dao_ext import ExtDAO
from backend.load_order.package_tokens import parse_package_token
from backend.managers.mgr_profile import ProfileContext
from backend.utils.tools import normalize_package_id, normalize_workshop_id


class ModSettingsManager:
    """管理当前环境下官方 ModSettings 配置文件。"""

    OFFICIAL_PREFIX = "Mod_"
    OFFICIAL_SUFFIX = ".xml"

    @classmethod
    def get_overview(cls, context: ProfileContext | None, active_tokens: list[str] | None = None) -> dict[str, Any]:
        if not context:
            raise ValueError("环境配置上下文缺失")

        config_path = Path(str(context.game_config_path or "").strip())
        if not str(config_path):
            raise ValueError("未指定游戏配置路径")

        files = cls._scan_official_files(config_path)
        candidate_map = cls._build_instance_candidates(context, active_tokens or [])

        grouped_mods: dict[str, dict[str, Any]] = {}
        unknown_file_count = 0

        file_records = []
        for file_info in files:
            file_identity = cls._parse_file_identity(file_info["file_name"])
            settings_identity = cls._read_settings_identity(Path(file_info["file_path"]))
            file_records.append({
                "file_info": file_info,
                "file_identity": file_identity,
                "settings_identity": settings_identity,
            })

        cls._apply_external_file_details([record["file_identity"] for record in file_records])
        package_candidate_map = cls._build_candidate_package_map(candidate_map)

        for record in file_records:
            file_info = record["file_info"]
            file_identity = record["file_identity"]
            settings_identity = record["settings_identity"]
            candidate = (
                cls._match_candidate(file_info["file_name"], candidate_map)
                or cls._match_external_package_candidate(file_identity, package_candidate_map)
            )
            if candidate:
                mod_group = cls._ensure_mod_group(grouped_mods, {
                    "group_key": f"mod:{candidate['package_id']}",
                    "package_id": candidate["package_id"],
                    "mod_name": candidate["mod_name"],
                    "status": "enabled" if candidate.get("is_active_package") else "disabled",
                    "match_confidence": "high",
                    "workshop_id": candidate["workshop_id"],
                    "is_active_mod": bool(candidate.get("is_active_package")),
                })
            else:
                unknown_file_count += 1
                mod_group = cls._ensure_mod_group(grouped_mods, cls._build_unknown_mod_group(file_identity))

            cls._append_config_instance(mod_group, file_info, file_identity, settings_identity, candidate)

        mod_groups = list(grouped_mods.values())
        for mod_group in mod_groups:
            cls._finalize_mod_group(mod_group)

        mod_groups.sort(
            key=lambda item: (
                {"enabled": 0, "disabled": 1, "uninstalled": 2, "unknown": 3}.get(str(item.get("status") or ""), 9),
                0 if item.get("is_active_mod") else 1,
                cls._confidence_sort_key(item.get("match_confidence") or ""),
                str(item.get("mod_name") or "").lower(),
                str(item.get("workshop_id") or "").lower(),
                str(item.get("package_id") or "").lower(),
            )
        )

        return {
            "config_path": str(config_path),
            "total_files": len(files),
            "matched_mod_count": sum(1 for item in mod_groups if item.get("status") in {"enabled", "disabled"}),
            "unknown_file_count": unknown_file_count,
            "cleanup_candidate_paths": [
                item["file_path"]
                for group in mod_groups
                if group.get("status") in {"uninstalled", "unknown"}
                for setting_group in group.get("setting_groups", [])
                for item in setting_group.get("files", [])
            ],
            "mod_groups": mod_groups,
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
        entry_map: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
        for mod_group in overview["mod_groups"]:
            for setting_group in mod_group.get("setting_groups", []):
                for item in setting_group["files"]:
                    entry_map[cls._normalize_path(item.get("file_path"))] = (mod_group, setting_group, item)

        if normalized_source not in entry_map:
            normalized_source = cls._resolve_entry_key(source_path, entry_map)
        if normalized_source not in entry_map:
            raise ValueError("源文件不在当前环境的配置列表中")
        if normalized_target not in entry_map:
            normalized_target = cls._resolve_entry_key(target_path, entry_map)
        if normalized_target not in entry_map:
            raise ValueError("目标文件不在当前环境的配置列表中")

        source_mod_group, source_setting_group, source_item = entry_map[normalized_source]
        target_mod_group, target_setting_group, target_item = entry_map[normalized_target]

        if source_mod_group.get("group_key") != target_mod_group.get("group_key"):
            raise ValueError("只能在同一个模组的同一种配置之间互相覆盖")
        if not source_setting_group.get("key") or source_setting_group.get("key") != target_setting_group.get("key"):
            raise ValueError("只能在同一种配置之间互相覆盖")
        if not bool(target_item.get("active")):
            raise ValueError("目标文件不是当前激活配置")

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
            "package_id": str(source_mod_group.get("package_id") or ""),
            "class": str(source_setting_group.get("class") or ""),
            "fallback_name": str(source_setting_group.get("fallback_name") or ""),
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
        active_package_ids = set(active_path_map.keys())
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
                "is_active_package": package_id in active_package_ids,
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
        best_score = -1
        for folder_key in candidate_map.keys():
            score = cls._score_candidate_filename_match(normalized_name, folder_key)
            if score > best_score or (score == best_score and len(folder_key) > len(best_folder_key)):
                best_score = score
                best_folder_key = folder_key

        if not best_folder_key or best_score <= 0:
            return None

        matched_candidates = candidate_map.get(best_folder_key) or []
        if not matched_candidates:
            return None

        return cls._pick_preferred_candidate(matched_candidates)

    @classmethod
    def _read_settings_identity(cls, file_path: Path) -> dict[str, Any]:
        result = {
            "settings_class": "",
            "parse_status": "missing",
            "parse_message": "",
            "identity_kind": "filename",
        }
        try:
            root = ElementTree.parse(file_path).getroot()
        except ElementTree.ParseError as exc:
            result["parse_status"] = "invalid_xml"
            result["parse_message"] = f"XML 解析失败: {exc}"
            return result
        except OSError as exc:
            result["parse_status"] = "read_failed"
            result["parse_message"] = f"读取失败: {exc}"
            return result

        mod_settings = root.find("./ModSettings") if root.tag == "SettingsBlock" else None
        settings_class = str(mod_settings.get("Class") or "").strip() if mod_settings is not None else ""
        if settings_class:
            result.update({
                "settings_class": settings_class,
                "parse_status": "ok",
                "identity_kind": "class",
                "parse_message": "",
            })
            return result
        result["parse_status"] = "missing_class"
        result["parse_message"] = "未找到 SettingsBlock/ModSettings Class，已按文件名兜底识别"
        return result

    @classmethod
    def _parse_file_identity(cls, file_name: str) -> dict[str, Any]:
        normalized_name = str(file_name or "").strip()
        body = normalized_name
        if cls._is_official_config_filename(normalized_name):
            body = normalized_name[len(cls.OFFICIAL_PREFIX) : -len(cls.OFFICIAL_SUFFIX)]
        compact_body = body.strip("_")
        parts = [part for part in re.split(r"_+", compact_body) if part]
        workshop_id = ""
        for part in parts:
            workshop_id = normalize_workshop_id(part, digits_only=True, min_length=6, max_length=20)
            if workshop_id:
                break
        folder_hint = parts[0] if parts else compact_body
        name_parts = list(parts)
        if workshop_id in name_parts:
            name_parts = name_parts[name_parts.index(workshop_id) + 1 :]
        guessed_name = "_".join(name_parts).strip("_")
        if guessed_name.lower() == "mod":
            guessed_name = ""
        confidence = "unknown"
        if workshop_id and guessed_name:
            confidence = "medium"
        elif workshop_id:
            confidence = "medium"
        elif guessed_name:
            confidence = "low"
        return {
            "file_config_name": guessed_name or compact_body or normalized_name,
            "folder_hint": folder_hint,
            "workshop_id_guess": workshop_id,
            "guessed_mod_name": guessed_name,
            "match_confidence": confidence,
            "external_package_id": "",
            "external_mod_name": "",
            "external_preview_url": "",
            "external_detail_source": "",
            "raw_body": body,
        }

    @classmethod
    def _apply_external_file_details(cls, file_identities: list[dict[str, Any]]) -> None:
        workshop_ids = []
        seen_ids = set()
        for identity in file_identities:
            workshop_id = normalize_workshop_id(identity.get("workshop_id_guess"), digits_only=True, min_length=6, max_length=20)
            if not workshop_id or workshop_id in seen_ids:
                continue
            seen_ids.add(workshop_id)
            workshop_ids.append(workshop_id)
        if not workshop_ids:
            return
        try:
            details = ExtDAO.get_workshop_details_by_workshop_ids(workshop_ids) or {}
        except Exception:
            return

        for identity in file_identities:
            workshop_id = str(identity.get("workshop_id_guess") or "").strip()
            detail = details.get(workshop_id) or {}
            package_id = normalize_package_id(detail.get("package_id"))
            mod_name = str(detail.get("name") or "").strip()
            if not package_id and not mod_name:
                continue
            identity["external_package_id"] = package_id
            identity["external_mod_name"] = mod_name
            identity["external_preview_url"] = str(detail.get("preview_url") or "").strip()
            identity["external_detail_source"] = "database"
            if package_id:
                identity["match_confidence"] = "high"

    @staticmethod
    def _build_candidate_package_map(candidate_map: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        package_map: dict[str, list[dict[str, Any]]] = {}
        seen_paths: set[str] = set()
        for candidates in candidate_map.values():
            for candidate in candidates:
                package_id = normalize_package_id(candidate.get("package_id"))
                path_key = str(candidate.get("mod_path") or "").lower()
                if not package_id or path_key in seen_paths:
                    continue
                seen_paths.add(path_key)
                package_map.setdefault(package_id, []).append(candidate)
        return package_map

    @classmethod
    def _match_external_package_candidate(
        cls,
        file_identity: dict[str, Any],
        package_candidate_map: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        package_id = normalize_package_id(file_identity.get("external_package_id"))
        if not package_id:
            return None
        candidates = package_candidate_map.get(package_id) or []
        if not candidates:
            return None

        result = cls._pick_preferred_candidate(candidates)
        if not result:
            return None
        result["_match_kind"] = "external_package"
        return result

    @staticmethod
    def _pick_preferred_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        active_instances = [item for item in candidates if item.get("is_active_instance")]
        if active_instances:
            return dict(active_instances[0])
        active_packages = [item for item in candidates if item.get("is_active_package")]
        if active_packages:
            return dict(active_packages[0])
        return dict(candidates[0])

    @classmethod
    def _score_candidate_filename_match(cls, file_name: str, folder_key: str) -> int:
        normalized_name = str(file_name or "").strip()
        folder_name = str(folder_key or "").strip()
        normalized_folder = folder_name.lower()
        if not normalized_name or not normalized_folder or not cls._is_official_config_filename(normalized_name):
            return 0
        body = normalized_name[len(cls.OFFICIAL_PREFIX) : -len(cls.OFFICIAL_SUFFIX)]
        lowered_body = body.lower()
        if lowered_body == normalized_folder or lowered_body.startswith(f"{normalized_folder}_"):
            return 200 + len(normalized_folder)

        trimmed_body = body.strip("_").lower()
        if trimmed_body.startswith(f"{normalized_folder}_") or trimmed_body == normalized_folder:
            return 100 + len(normalized_folder)

        trimmed_folder = normalized_folder.strip("_")
        if trimmed_folder and trimmed_folder != normalized_folder and (
            trimmed_body.startswith(f"{trimmed_folder}_") or trimmed_body == trimmed_folder
        ):
            return 90 + len(trimmed_folder)

        parts = [part.lower() for part in re.split(r"_+", trimmed_body) if part]
        if parts and parts[0] == normalized_folder:
            return 80 + len(normalized_folder)
        if normalized_folder.isdigit() and normalized_folder in parts:
            return 60 + len(normalized_folder)
        if trimmed_folder.isdigit() and trimmed_folder in parts:
            return 50 + len(trimmed_folder)
        return 0

    @classmethod
    def _extract_config_name_for_candidate(cls, file_name: str, folder_name: str) -> str:
        normalized_name = str(file_name or "").strip()
        normalized_folder = str(folder_name or "").strip()
        if not normalized_name or not normalized_folder or not cls._is_official_config_filename(normalized_name):
            return ""
        body = normalized_name[len(cls.OFFICIAL_PREFIX) : -len(cls.OFFICIAL_SUFFIX)]
        lowered_body = body.lower()
        lowered_folder = normalized_folder.lower()
        if lowered_body.startswith(f"{lowered_folder}_"):
            return body[len(normalized_folder):].lstrip("_")
        body = body.strip("_")
        lowered_body = body.lower()
        parts = [part for part in re.split(r"_+", body) if part]
        lowered_parts = [part.lower() for part in parts]
        if lowered_parts and lowered_parts[0] == lowered_folder:
            return "_".join(parts[1:]).strip("_")
        compare_folder = lowered_folder.strip("_")
        if compare_folder and compare_folder in lowered_parts:
            return "_".join(parts[lowered_parts.index(compare_folder) + 1:]).strip("_")
        return body

    @classmethod
    def _active_file_score(cls, file_name: str, folder_name: str, fallback_name: str) -> int:
        normalized_name = str(file_name or "").strip()
        normalized_folder = str(folder_name or "").strip()
        normalized_fallback = str(fallback_name or "").strip()
        if not normalized_name or not normalized_folder or not cls._is_official_config_filename(normalized_name):
            return 0

        body = normalized_name[len(cls.OFFICIAL_PREFIX) : -len(cls.OFFICIAL_SUFFIX)]
        raw_canonical_body = f"{normalized_folder}_{normalized_fallback}".rstrip("_")
        if normalized_fallback and body == raw_canonical_body:
            return 300

        trimmed_body = body.strip("_")
        canonical_body = f"{normalized_folder}_{normalized_fallback}".strip("_")
        if normalized_fallback and trimmed_body == canonical_body:
            return 200

        parts = [part for part in re.split(r"_+", trimmed_body) if part]
        if not parts:
            return 0
        lowered_parts = [part.lower() for part in parts]
        lowered_folder = normalized_folder.lower()
        if lowered_parts[0] == lowered_folder:
            return 120 if normalized_fallback and "_".join(parts[1:]) == normalized_fallback else 100
        if lowered_folder in lowered_parts:
            return 60
        return 0

    @staticmethod
    def _choose_active_file(files: list[dict[str, Any]]) -> dict[str, Any] | None:
        active_files = [item for item in files if item.get("_source_is_active")]
        if not active_files:
            return None
        active_files.sort(
            key=lambda item: (
                -int(item.get("_active_score") or 0),
                str(item.get("name") or "").lower(),
                str(item.get("file_path") or "").lower(),
            )
        )
        return active_files[0]

    @classmethod
    def _ensure_mod_group(cls, grouped_mods: dict[str, dict[str, Any]], base: dict[str, Any]) -> dict[str, Any]:
        group_key = str(base.get("group_key") or "").strip()
        group = grouped_mods.setdefault(group_key, {
            **base,
            "setting_groups": [],
            "_setting_group_map": {},
        })
        group["is_active_mod"] = bool(group.get("is_active_mod")) or bool(base.get("is_active_mod"))
        if not group.get("workshop_id") and base.get("workshop_id"):
            group["workshop_id"] = base.get("workshop_id")
        if group.get("package_id") and group.get("status") in {"enabled", "disabled"}:
            group["status"] = "enabled" if group.get("is_active_mod") else "disabled"
        return group

    @classmethod
    def _build_unknown_mod_group(cls, file_identity: dict[str, Any]) -> dict[str, Any]:
        workshop_id = str(file_identity.get("workshop_id_guess") or "").strip()
        package_id = normalize_package_id(file_identity.get("external_package_id"))
        external_name = str(file_identity.get("external_mod_name") or "").strip()
        guessed_name = str(file_identity.get("guessed_mod_name") or "").strip()
        folder_hint = str(file_identity.get("folder_hint") or "").strip()
        if package_id:
            group_key = f"uninstalled:package:{package_id}"
            status = "uninstalled"
            mod_name = external_name or guessed_name or package_id
            source_label = "已卸载"
        elif workshop_id:
            group_key = f"uninstalled:workshop:{workshop_id}"
            status = "uninstalled"
            mod_name = guessed_name or f"Workshop {workshop_id}"
            source_label = "已卸载"
        else:
            group_key = f"unknown:file:{folder_hint.lower() or file_identity.get('raw_body')}"
            status = "unknown"
            mod_name = guessed_name or "未知模组"
            source_label = "未知"
        return {
            "group_key": group_key,
            "package_id": package_id,
            "mod_name": mod_name,
            "status": status,
            "match_confidence": file_identity.get("match_confidence") or "unknown",
            "workshop_detail": {
                "workshop_id": workshop_id,
                "title": external_name,
                "preview_url": file_identity.get("external_preview_url") or "",
                "detail_source": file_identity.get("external_detail_source") or "",
                "available": bool(external_name or file_identity.get("external_preview_url")),
            } if file_identity.get("external_detail_source") else None,
            "source_label": source_label,
            "workshop_id": workshop_id,
            "is_active_mod": False,
        }

    @classmethod
    def _append_config_instance(
        cls,
        mod_group: dict[str, Any],
        file_info: dict[str, Any],
        file_identity: dict[str, Any],
        settings_identity: dict[str, Any],
        candidate: dict[str, Any] | None,
    ) -> None:
        settings_class = str(settings_identity.get("settings_class") or "").strip()
        fallback_name = (
            cls._extract_config_name_for_candidate(str(file_info.get("file_name") or ""), str(candidate.get("folder_name") or ""))
            if candidate else str(file_identity.get("file_config_name") or "").strip()
        )
        identity_kind = "class" if settings_class else "filename"
        setting_identity = settings_class or fallback_name or str(file_info.get("file_name") or "")
        setting_key = cls._build_group_key(str(mod_group.get("group_key") or ""), setting_identity)
        setting_map = mod_group["_setting_group_map"]
        setting_group = setting_map.setdefault(setting_key, {
            "key": setting_key,
            "label": settings_class or fallback_name or "未识别设置",
            "identity": identity_kind,
            "class": settings_class,
            "fallback_name": fallback_name,
            "parse_status": settings_identity.get("parse_status"),
            "parse_message": settings_identity.get("parse_message"),
            "files": [],
        })
        active_score = cls._active_file_score(
            str(file_info.get("file_name") or ""),
            str(candidate.get("folder_name") or "") if candidate else "",
            fallback_name,
        ) if candidate and candidate.get("is_active_instance") else 0
        matched_by_external_package = bool(candidate and candidate.get("_match_kind") == "external_package")
        folder_name = str(file_identity.get("folder_hint") or "") if matched_by_external_package else (
            candidate["folder_name"] if candidate else str(file_identity.get("folder_hint") or "")
        )
        source_label = "同包名" if matched_by_external_package else (
            cls._source_label(candidate["source_kind"]) if candidate else str(mod_group.get("source_label") or "未知")
        )
        item = {
            "key": file_info["file_path"],
            "name": file_info["file_name"],
            "file_path": file_info["file_path"],
            "folder_name": folder_name,
            "source_label": source_label,
            "match_confidence": "high" if candidate else file_identity.get("match_confidence"),
            "file_size": file_info["file_size"],
            "modified_time": file_info["modified_time"],
            "active": False,
            "_source_is_active": bool(candidate and candidate.get("is_active_instance") and active_score > 0),
            "_source_sort": cls._source_sort_key(candidate["source_kind"] if candidate else "unknown"),
            "_active_score": active_score,
        }
        setting_group["files"].append(item)

    @classmethod
    def _finalize_mod_group(cls, mod_group: dict[str, Any]) -> None:
        setting_groups = list(mod_group.pop("_setting_group_map", {}).values())
        file_count = 0
        for setting_group in setting_groups:
            active_item = cls._choose_active_file(setting_group["files"])
            if active_item:
                active_item["active"] = True
            setting_group["files"].sort(
                key=lambda item: (
                    0 if item.get("active") else 1,
                    item.get("_source_sort", 9),
                    str(item.get("name") or "").lower(),
                )
            )
            setting_group["active_file_path"] = active_item.get("file_path") if active_item else ""
            setting_group["file_count"] = len(setting_group["files"])
            setting_group["duplicate_count"] = max(0, len(setting_group["files"]) - 1)
            setting_group["can_cover_active"] = bool(active_item and len(setting_group["files"]) > 1)
            file_count += len(setting_group["files"])
            for item in setting_group["files"]:
                item.pop("_source_is_active", None)
                item.pop("_source_sort", None)
                item.pop("_active_score", None)
        setting_groups.sort(
            key=lambda item: (
                0 if item.get("active_file_path") else 1,
                0 if item.get("identity") == "class" else 1,
                str(item.get("label") or "").lower(),
            )
        )
        mod_group["setting_groups"] = setting_groups
        mod_group["file_count"] = file_count
        mod_group["setting_count"] = len(setting_groups)
        mod_group["cleanup_candidate_paths"] = [
            item["file_path"]
            for setting_group in setting_groups
            for item in setting_group["files"]
            if mod_group.get("status") in {"uninstalled", "unknown"} or not item.get("active")
        ]
        if mod_group.get("package_id") and mod_group.get("status") in {"enabled", "disabled"}:
            mod_group["status"] = "enabled" if mod_group.get("is_active_mod") else "disabled"
        mod_group.pop("source_label", None)

    @classmethod
    def _build_active_preference_map(cls, active_tokens: list[str]) -> dict[str, str]:
        preference_map: dict[str, str] = {}
        priority = {"any": 1, "local": 2, "steam": 3}
        for raw_token in active_tokens or []:
            token_info = parse_package_token(raw_token)
            if not token_info.canonical_package_id:
                continue
            source_preference = token_info.source_preference if token_info.source_preference in priority else "any"
            current = preference_map.get(token_info.canonical_package_id, "")
            if priority[source_preference] > priority.get(current, 0):
                preference_map[token_info.canonical_package_id] = source_preference
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
            # 裸包名只说明“这个模组已启用”，不说明来源；此时以 get_profile_mods()
            # 已经仲裁出的当前可见副本为准，避免把纯工坊模组误判为本地副本。
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
        entry_map: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    ) -> str:
        normalized_path = cls._normalize_path(raw_path)
        if normalized_path in entry_map:
            return normalized_path
        if not normalized_path:
            return ""
        for candidate_key, (_mod_group, _config_group, item) in entry_map.items():
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

    @staticmethod
    def _confidence_sort_key(confidence: str) -> int:
        return {
            "high": 0,
            "medium": 1,
            "low": 2,
            "unknown": 3,
        }.get(str(confidence or "").strip().lower(), 3)

    @classmethod
    def _build_group_key(cls, package_id: str, settings_class_name: str) -> str:
        normalized_package_id = str(package_id or "").strip().lower()
        normalized_class_name = str(settings_class_name or "").strip().lower()
        if normalized_package_id and normalized_class_name:
            return f"{normalized_package_id}::{normalized_class_name}"
        return normalized_package_id or normalized_class_name
