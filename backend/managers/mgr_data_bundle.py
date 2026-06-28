import json
import os
import shutil
import tempfile
import uuid
import zipfile
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from backend._version import __version__
from backend.ai.ai_service import AIManager
from backend.database.dao import CollectionDAO
from backend.database.models import GameProfile, GithubModRecord, db
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_profile import ProfileManager
from backend.settings import DATA_DIR, settings


class DataBundleManager:
    """
    统一的软件数据导入导出管理器。

    目标：
    1. 为设置页提供全局/自定义模块导入导出
    2. 为规则中心提供固定预设的统一格式导入导出
    3. 把模块依赖、包格式、导入策略集中到一处管理
    """

    FORMAT = "rmm.data.bundle"
    SCHEMA_VERSION = 1
    FILE_EXTENSION = ".rmmdata"
    RULE_PRESET = ["rules", "user_custom", "groups"]

    MODULE_DEFINITIONS = [
        {
            "key": "settings",
            "label": "软件设置",
            "description": "导出软件的全局设置。不会包含目录路径、敏感信息和当前激活环境。",
            "dependencies": [],
            "supports_profiles": False,
        },
        {
            "key": "ai_definitions",
            "label": "AI 定义",
            "description": "包含 AI 模板、助手设置和任务设置。导入后会替换当前 AI 定义。",
            "dependencies": [],
            "supports_profiles": False,
        },
        {
            "key": "rules",
            "label": "规则",
            "description": "包含用户规则、动态规则和规则设置。导入时会尽量合并。",
            "dependencies": ["user_custom", "groups"],
            "supports_profiles": False,
        },
        {
            "key": "user_custom",
            "label": "用户自定义信息",
            "description": "包含别名、备注、标签、颜色、自定义类型和联锁数据。导入时会尽量合并。",
            "dependencies": [],
            "supports_profiles": False,
        },
        {
            "key": "groups",
            "label": "分组",
            "description": "包含分组本身和分组里的模组关系。导入时会尽量合并。",
            "dependencies": [],
            "supports_profiles": False,
        },
        {
            "key": "profiles",
            "label": "环境数据",
            "description": "按环境导出完整的用户数据目录，并附带环境基本信息。",
            "dependencies": [],
            "supports_profiles": True,
        },
        {
            "key": "subscriptions",
            "label": "订阅数据",
            "description": "包含 GitHub 订阅记录和 Steam 合集记录，不包含缓存和历史状态。",
            "dependencies": [],
            "supports_profiles": False,
        },
    ]

    _SETTINGS_EXCLUDED_KEYS = {
        "workshop_mods_path",
        "steam_path",
        "home_path",
        "steamcmd_path",
        "steamcmd_mods_path",
        "self_mods_path",
        "load_order_import_dir_mode",
        "load_order_import_custom_path",
        "load_order_import_last_path",
        "load_order_export_dir_mode",
        "load_order_export_custom_path",
        "load_order_export_last_path",
        "current_profile_id",
        "community_workshop_db_path",
        "community_instead_db_path",
        "community_rules_path",
        "user_rules_path",
        "ignored_update_version",
        "last_update_check_time",
        "last_tool_check_time",
        "last_external_data_update_check_time",
        "last_steamcmd_mod_update_check_time",
        "last_run_time",
        "run_count",
    }

    def __init__(
        self,
        profile_mgr: ProfileManager,
        ai_mgr: AIManager,
        rule_mgr_provider: Callable[[], Any],
    ):
        self.profile_mgr = profile_mgr
        self.ai_mgr = ai_mgr
        self.rule_mgr_provider = rule_mgr_provider
        self.game_mgr = GameManager()

    @classmethod
    def module_definitions(cls) -> list[dict[str, Any]]:
        return deepcopy(cls.MODULE_DEFINITIONS)

    @classmethod
    def get_module_definition(cls, key: str) -> dict[str, Any] | None:
        for item in cls.MODULE_DEFINITIONS:
            if item["key"] == key: return deepcopy(item)
        return None

    @classmethod
    def expand_module_dependencies(cls, module_keys: list[str] | None) -> list[str]:
        requested = []
        for key in module_keys or []:
            normalized = str(key or "").strip()
            if normalized and normalized not in requested:
                requested.append(normalized)

        dependency_map = {
            item["key"]: list(item.get("dependencies", []))
            for item in cls.MODULE_DEFINITIONS
        }
        resolved: list[str] = []

        def _visit(target_key: str):
            if target_key in resolved or target_key not in dependency_map: return
            for dep_key in dependency_map[target_key]:
                _visit(dep_key)
            resolved.append(target_key)

        for module_key in requested:
            _visit(module_key)
        return resolved

    def get_schema(self) -> dict[str, Any]:
        profiles = []
        for profile in self.profile_mgr.get_all_profiles():
            user_data_path = str(profile.get("user_data_path") or "").strip()
            profiles.append({
                "id": profile.get("id"),
                "name": profile.get("name"),
                "description": profile.get("description"),
                "game_version": profile.get("game_version"),
                "is_default": str(profile.get("id")) == "default",
                "has_user_data": bool(user_data_path and os.path.isdir(user_data_path)),
            })

        return {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "file_extension": self.FILE_EXTENSION,
            "modules": self.module_definitions(),
            "presets": {
                "rules": {
                    "label": "规则中心预设",
                    "module_keys": list(self.RULE_PRESET),
                }
            },
            "profiles": profiles,
        }

    def write_bundle(
        self,
        target_path: str,
        module_keys: list[str],
        profile_ids: list[str] | None = None,
        preset: str = "custom",
        dynamic_rule_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_modules = self.expand_module_dependencies(module_keys)
        if not normalized_modules:
            raise ValueError("未选择任何可导出的数据模块")

        module_payloads = self._collect_modules_payload(normalized_modules, dynamic_rule_ids)
        profile_entries: list[dict[str, Any]] = []

        with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for module_key, payload in module_payloads.items():
                bundle.writestr(
                    f"modules/{module_key}.json",
                    json.dumps(payload, indent=2, ensure_ascii=False),
                )

            if "profiles" in normalized_modules:
                profile_entries = self._write_profiles_to_bundle(bundle, profile_ids or [])

            manifest = {
                "format": self.FORMAT,
                "schema_version": self.SCHEMA_VERSION,
                "app_version": __version__,
                "exported_at": datetime.now().astimezone().isoformat(),
                "preset": str(preset or "custom"),
                "modules": [
                    {
                        "key": module_key,
                        "label": self.get_module_definition(module_key).get("label", module_key),  # type: ignore[union-attr]
                    }
                    for module_key in normalized_modules
                ],
                "profiles": profile_entries,
            }
            bundle.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )

        return {
            "path": target_path,
            "modules": normalized_modules,
            "profiles": profile_entries,
        }

    def inspect_bundle(self, bundle_path: str) -> dict[str, Any]:
        path = Path(str(bundle_path or "").strip())
        if not path.is_file():
            raise FileNotFoundError(f"未找到数据包文件: {path}")

        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as bundle:
                manifest = self._read_json_from_zip(bundle, "manifest.json")
                if not isinstance(manifest, dict):
                    raise ValueError("数据包缺少有效的 manifest.json")

            module_entries = manifest.get("modules", [])
            profiles = manifest.get("profiles", [])
            return {
                "format": manifest.get("format"),
                "schema_version": manifest.get("schema_version"),
                "app_version": manifest.get("app_version"),
                "exported_at": manifest.get("exported_at"),
                "preset": manifest.get("preset", "custom"),
                "modules": module_entries if isinstance(module_entries, list) else [],
                "profiles": profiles if isinstance(profiles, list) else [],
                "has_default_profile": any(
                    str(profile.get("original_profile_id")) == "default"
                    for profile in profiles
                    if isinstance(profile, dict)
                ),
                "legacy_rule_bundle": False,
            }

        with open(path, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if self._is_legacy_rule_bundle(payload):
            return {
                "format": "legacy.rule.bundle",
                "schema_version": 0,
                "app_version": payload.get("version", ""),
                "exported_at": payload.get("export_date", ""),
                "preset": "rules",
                "modules": [
                    {"key": "rules", "label": "规则"},
                    {"key": "user_custom", "label": "用户自定义信息"},
                    {"key": "groups", "label": "分组"},
                ],
                "profiles": [],
                "has_default_profile": False,
                "legacy_rule_bundle": True,
            }
        raise ValueError("无法识别的数据包格式")

    def import_bundle(
        self,
        bundle_path: str,
        module_keys: list[str] | None = None,
        default_profile_mode: str = "clone",
    ) -> dict[str, Any]:
        path = Path(str(bundle_path or "").strip())
        if not path.is_file():
            raise FileNotFoundError(f"未找到数据包文件: {path}")

        selected_modules = self.expand_module_dependencies(module_keys) if module_keys else []
        result = {
            "imported_modules": [],
            "warnings": [],
            "profiles": [],
        }

        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as bundle:
                manifest = self._read_json_from_zip(bundle, "manifest.json")
                included_modules: list[str] = [
                    str(item.get("key"))
                    for item in manifest.get("modules", [])
                    if isinstance(item, dict) and str(item.get("key") or "").strip()
                ]
                active_modules: list[str] = included_modules if not selected_modules else [
                    module_key for module_key in included_modules if module_key in selected_modules
                ]
                if not active_modules:
                    raise ValueError("导入包中没有可处理的数据模块")

                module_payloads: dict[str, Any] = {
                    module_key: self._read_json_from_zip(bundle, f"modules/{module_key}.json", {})
                    for module_key in active_modules
                    if module_key != "profiles"
                }
                self._apply_module_payloads(module_payloads, result)

                if "profiles" in active_modules:
                    imported_profiles, warnings = self._import_profiles_from_bundle(
                        bundle,
                        manifest.get("profiles", []),
                        default_profile_mode=default_profile_mode,
                    )
                    result["profiles"] = imported_profiles
                    result["warnings"].extend(warnings)

                result["imported_modules"] = active_modules
                return result

        with open(path, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if not self._is_legacy_rule_bundle(payload):
            raise ValueError("无法识别的数据包格式")

        requested = selected_modules or list(self.RULE_PRESET)
        self._import_rule_related_bundle(payload, requested, result)
        result["imported_modules"] = [module for module in requested if module in self.RULE_PRESET]
        return result

    def _collect_modules_payload(
        self,
        module_keys: list[str],
        dynamic_rule_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        payloads: dict[str, Any] = {}
        rule_mgr = self.rule_mgr_provider()
        rule_bundle = None

        if any(module in module_keys for module in ("rules", "user_custom", "groups")):
            if not rule_mgr:
                raise ValueError("规则引擎未初始化，无法导出规则相关数据")
            rule_bundle = rule_mgr.create_export_bundle(dynamic_rule_ids)

        if "settings" in module_keys:
            payloads["settings"] = self._collect_sanitized_settings()
        if "ai_definitions" in module_keys:
            payloads["ai_definitions"] = self.ai_mgr.definition_manager.export_definition_store()
        if "rules" in module_keys:
            payloads["rules"] = {
                "settings": deepcopy(rule_mgr.settings),  # type: ignore[union-attr]
                "mod_rules": deepcopy((rule_bundle or {}).get("user_rules", {}).get("mod_rules", {})),
                "dynamic_rules": deepcopy((rule_bundle or {}).get("user_rules", {}).get("dynamic_rules", [])),
            }
        if "user_custom" in module_keys:
            payloads["user_custom"] = {
                "user_mod_data": deepcopy((rule_bundle or {}).get("environment", {}).get("user_mod_data", [])),
                "interlocks": deepcopy((rule_bundle or {}).get("environment", {}).get("interlocks", [])),
            }
        if "groups" in module_keys:
            payloads["groups"] = {
                "groups": deepcopy((rule_bundle or {}).get("environment", {}).get("groups", [])),
            }
        if "subscriptions" in module_keys:
            payloads["subscriptions"] = self._collect_subscriptions_payload()
        return payloads

    def _collect_sanitized_settings(self) -> dict[str, Any]:
        config = asdict(settings.config)
        for key in list(self._SETTINGS_EXCLUDED_KEYS):
            config.pop(key, None)

        ai_config = config.get("ai", {})
        if isinstance(ai_config, dict):
            ai_config.pop("api_key", None)

        network_config = config.get("network", {})
        proxy_config = network_config.get("proxy", {}) if isinstance(network_config, dict) else {}
        if isinstance(proxy_config, dict):
            proxy_config.pop("username", None)
            proxy_config.pop("password", None)

        texture_config = config.get("texture_opt", {})
        if isinstance(texture_config, dict):
            texture_config.pop("texture_tools_path", None)

        return config

    def _collect_subscriptions_payload(self) -> dict[str, Any]:
        github_records = []
        for record in GithubModRecord.select().dicts():
            github_records.append({
                "repo_url": record.get("repo_url"),
                "owner": record.get("owner"),
                "repo_name": record.get("repo_name"),
                "install_type": record.get("install_type") or "source",
                "target_branch": record.get("target_branch") or "main",
            })

        collections = []
        for item in CollectionDAO.get_all():
            collections.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "description": item.get("description"),
                "preview_url": item.get("preview_url"),
                "total": item.get("total", 0),
                "time_updated": item.get("time_updated", 0),
                "children": item.get("children", []),
            })

        return {
            "github_repos": github_records,
            "collections": collections,
        }

    def _write_profiles_to_bundle(self, bundle: zipfile.ZipFile, profile_ids: list[str]) -> list[dict[str, Any]]:
        normalized_ids = [str(profile_id or "").strip() for profile_id in profile_ids if str(profile_id or "").strip()]
        if not normalized_ids:
            raise ValueError("已选择环境数据模块，但没有勾选任何环境")

        profile_entries = []
        for profile_id in normalized_ids:
            profile = self.profile_mgr.get_profile(profile_id)
            source_root_str = str(profile.user_data_path or "").strip()
            source_root = Path(source_root_str)
            if not source_root_str or not source_root.is_dir():
                raise ValueError(f'环境 "{profile.name}" 的用户数据目录不存在，无法导出')

            archive_key = profile.id
            profile_meta = self._serialize_profile_for_export(profile)
            profile_entries.append({
                "archive_key": archive_key,
                "original_profile_id": profile.id,
                "name": profile.name,
                "description": profile.description,
                "game_version": profile.game_version,
                "is_default": profile.id == "default",
            })

            bundle.writestr(
                f"environments/{archive_key}/profile.json",
                json.dumps(profile_meta, indent=2, ensure_ascii=False),
            )

            for root, _, files in os.walk(source_root):
                for filename in files:
                    file_path = Path(root) / filename
                    rel_path = file_path.relative_to(source_root).as_posix()
                    bundle.write(
                        file_path,
                        arcname=f"environments/{archive_key}/user_data/{rel_path}",
                    )

        return profile_entries

    def _serialize_profile_for_export(self, profile: GameProfile) -> dict[str, Any]:
        return {
            "original_profile_id": profile.id,
            "name": profile.name,
            "description": profile.description,
            "game_version": profile.game_version,
            "prefer_steam_launch": bool(profile.prefer_steam_launch),
            "use_workshop_mods": bool(profile.use_workshop_mods),
            "use_self_mods": bool(profile.use_self_mods),
            "run_commands": list(profile.run_commands or []),
            "inactive_mods_order": list(profile.inactive_mods_order or []),
            "last_played_time": int(profile.last_played_time or 0),
            "is_default": profile.id == "default",
        }

    def _apply_module_payloads(self, module_payloads: dict[str, Any], result: dict[str, Any]) -> None:
        settings_payload = module_payloads.get("settings")
        if isinstance(settings_payload, dict):
            settings.update_from_dict(settings_payload)

        ai_definitions_payload = module_payloads.get("ai_definitions")
        if isinstance(ai_definitions_payload, dict):
            self.ai_mgr.definition_manager.save_definition_store(ai_definitions_payload)

        if any(module_key in module_payloads for module_key in ("rules", "user_custom", "groups")):
            legacy_bundle = {
                "user_rules": {
                    "settings": deepcopy(module_payloads.get("rules", {}).get("settings", {})) if isinstance(module_payloads.get("rules"), dict) else {},
                    "mod_rules": deepcopy(module_payloads.get("rules", {}).get("mod_rules", {})) if isinstance(module_payloads.get("rules"), dict) else {},
                    "dynamic_rules": deepcopy(module_payloads.get("rules", {}).get("dynamic_rules", [])) if isinstance(module_payloads.get("rules"), dict) else [],
                },
                "environment": {
                    "user_mod_data": deepcopy(module_payloads.get("user_custom", {}).get("user_mod_data", [])) if isinstance(module_payloads.get("user_custom"), dict) else [],
                    "interlocks": deepcopy(module_payloads.get("user_custom", {}).get("interlocks", [])) if isinstance(module_payloads.get("user_custom"), dict) else [],
                    "groups": deepcopy(module_payloads.get("groups", {}).get("groups", [])) if isinstance(module_payloads.get("groups"), dict) else [],
                },
            }
            self._import_rule_related_bundle(legacy_bundle, list(module_payloads.keys()), result)

        subscriptions_payload = module_payloads.get("subscriptions")
        if isinstance(subscriptions_payload, dict):
            warnings = self._import_subscriptions_payload(subscriptions_payload)
            result["warnings"].extend(warnings)

    def _import_rule_related_bundle(
        self,
        legacy_bundle: dict[str, Any],
        active_modules: list[str],
        result: dict[str, Any],
    ) -> None:
        rule_mgr = self.rule_mgr_provider()
        if not rule_mgr:
            raise ValueError("规则引擎未初始化，无法导入规则相关数据")

        import_payload = {
            "user_rules": {},
            "environment": {},
        }
        if "rules" in active_modules:
            import_payload["user_rules"]["mod_rules"] = deepcopy(legacy_bundle.get("user_rules", {}).get("mod_rules", {}))
            import_payload["user_rules"]["dynamic_rules"] = deepcopy(legacy_bundle.get("user_rules", {}).get("dynamic_rules", []))
        if "user_custom" in active_modules:
            import_payload["environment"]["user_mod_data"] = deepcopy(legacy_bundle.get("environment", {}).get("user_mod_data", []))
            import_payload["environment"]["interlocks"] = deepcopy(legacy_bundle.get("environment", {}).get("interlocks", []))
        if "groups" in active_modules:
            import_payload["environment"]["groups"] = deepcopy(legacy_bundle.get("environment", {}).get("groups", []))

        import_result = rule_mgr.process_import_bundle(import_payload) or {}
        result["warnings"].extend(import_result.get("warnings", []))

        if "rules" in active_modules:
            imported_rule_settings = deepcopy(legacy_bundle.get("user_rules", {}).get("settings", {}))
            if imported_rule_settings:
                rule_mgr.settings.update(imported_rule_settings)
                rule_mgr.save_user_rules()

    def _import_subscriptions_payload(self, payload: dict[str, Any]) -> list[str]:
        warnings: list[str] = []

        github_repos = payload.get("github_repos", [])
        if isinstance(github_repos, list):
            for repo in github_repos:
                if not isinstance(repo, dict):
                    continue
                repo_url = str(repo.get("repo_url") or "").strip()
                if not repo_url:
                    continue
                existing = GithubModRecord.get_or_none(GithubModRecord.repo_url == repo_url)
                values = {
                    "repo_url": repo_url,
                    "owner": str(repo.get("owner") or "").strip(),
                    "repo_name": str(repo.get("repo_name") or "").strip(),
                    "install_type": str(repo.get("install_type") or "source").strip() or "source",
                    "target_branch": str(repo.get("target_branch") or "main").strip() or "main",
                }
                if existing:
                    GithubModRecord.update(
                        owner=values["owner"],
                        repo_name=values["repo_name"],
                        install_type=values["install_type"],
                        target_branch=values["target_branch"],
                    ).where(GithubModRecord.repo_url == repo_url).execute()
                else:
                    GithubModRecord.create(**values)

        collections = payload.get("collections", [])
        if isinstance(collections, list):
            for item in collections:
                if not isinstance(item, dict):
                    continue
                coll_id = str(item.get("id") or "").strip()
                if not coll_id:
                    continue
                try:
                    CollectionDAO.upsert_collection(
                        coll_id,
                        {
                            "title": item.get("title"),
                            "description": item.get("description"),
                            "preview_url": item.get("preview_url"),
                            "time_updated": int(item.get("time_updated") or 0),
                        },
                        list(item.get("children") or []),
                        int(item.get("total") or 0),
                    )
                except Exception as exc:
                    warnings.append(f"导入合集 {coll_id} 失败: {exc}")
        return warnings

    def _import_profiles_from_bundle(
        self,
        bundle: zipfile.ZipFile,
        profile_entries: list[Any],
        default_profile_mode: str = "clone",
    ) -> tuple[list[dict[str, Any]], list[str]]:
        imported_profiles: list[dict[str, Any]] = []
        warnings: list[str] = []

        for profile_entry in profile_entries:
            if not isinstance(profile_entry, dict):
                continue
            archive_key = str(profile_entry.get("archive_key") or "").strip()
            if not archive_key:
                continue

            profile_meta = self._read_json_from_zip(bundle, f"environments/{archive_key}/profile.json", {})
            source_dir = self._extract_profile_user_data(bundle, archive_key)
            try:
                if bool(profile_meta.get("is_default")) and default_profile_mode == "overwrite":
                    imported_profiles.append(self._overwrite_default_profile(profile_meta, source_dir))
                else:
                    imported_profiles.append(self._create_imported_profile(profile_meta, source_dir))
            except Exception as exc:
                warnings.append(f'导入环境 "{profile_meta.get("name", archive_key)}" 失败: {exc}')
            finally:
                shutil.rmtree(source_dir.parent, ignore_errors=True)

        return imported_profiles, warnings

    def _extract_profile_user_data(self, bundle: zipfile.ZipFile, archive_key: str) -> Path:
        temp_root = Path(tempfile.mkdtemp(prefix="rmm-import-profile-"))
        target_root = temp_root / "user_data"
        prefix = f"environments/{archive_key}/user_data/"
        matched_names = [name for name in bundle.namelist() if name.startswith(prefix)]
        if not matched_names:
            raise ValueError("数据包中缺少 user_data 目录内容")

        for member_name in matched_names:
            relative_path = member_name[len(prefix):]
            if not relative_path:
                continue
            target_path = target_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member_name, "r") as source_handle:
                with open(target_path, "wb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle)
        return target_root

    def _overwrite_default_profile(self, profile_meta: dict[str, Any], source_dir: Path) -> dict[str, Any]:
        default_profile = self.profile_mgr.get_profile("default")
        target_root_str = str(default_profile.user_data_path or "").strip()
        target_root = Path(target_root_str)
        if not target_root_str:
            raise ValueError("当前默认环境缺少用户数据目录，无法覆盖")
        target_root.mkdir(parents=True, exist_ok=True)
        self._replace_directory_contents(target_root, source_dir)

        resolved_install_path = self._resolve_game_install_path(profile_meta.get("game_version"))
        default_profile.name = str(profile_meta.get("name") or default_profile.name)
        default_profile.description = profile_meta.get("description",'')
        default_profile.game_install_path = resolved_install_path
        default_profile.game_version = GameManager.get_game_version(resolved_install_path) if resolved_install_path else str(profile_meta.get("game_version") or "")
        default_profile.prefer_steam_launch = bool(profile_meta.get("prefer_steam_launch", True))
        default_profile.use_workshop_mods = True
        default_profile.use_self_mods = bool(profile_meta.get("use_self_mods", False))
        default_profile.run_commands = list(profile_meta.get("run_commands") or [])
        default_profile.inactive_mods_order = list(profile_meta.get("inactive_mods_order") or [])
        default_profile.last_played_time = int(profile_meta.get("last_played_time") or 0)
        default_profile.save()
        self.profile_mgr._sync_profile_to_disk(default_profile)

        return {
            "profile_id": "default",
            "name": default_profile.name,
            "mode": "overwrite-default",
            "game_install_path": default_profile.game_install_path,
            "game_version": default_profile.game_version,
        }

    def _create_imported_profile(self, profile_meta: dict[str, Any], source_dir: Path) -> dict[str, Any]:
        profile_id = uuid.uuid4().hex
        target_root = DATA_DIR / "profiles" / profile_id
        target_root.mkdir(parents=True, exist_ok=True)
        self._replace_directory_contents(target_root, source_dir)

        resolved_install_path = self._resolve_game_install_path(profile_meta.get("game_version"))
        game_version = GameManager.get_game_version(resolved_install_path) if resolved_install_path else str(profile_meta.get("game_version") or "")

        with db.atomic():
            profile = GameProfile.create(
                id=profile_id,
                name=str(profile_meta.get("name") or "Imported Profile"),
                description=profile_meta.get("description"),
                user_data_path=str(target_root),
                game_install_path=resolved_install_path,
                game_version=game_version,
                prefer_steam_launch=bool(profile_meta.get("prefer_steam_launch", True)),
                use_workshop_mods=bool(profile_meta.get("use_workshop_mods", True)),
                use_self_mods=bool(profile_meta.get("use_self_mods", False)),
                is_steam=bool(resolved_install_path and os.path.normpath(resolved_install_path).lower().find(os.path.join("steamapps", "common")) != -1),
                run_commands=list(profile_meta.get("run_commands") or []),
                inactive_mods_order=list(profile_meta.get("inactive_mods_order") or []),
                last_played_time=int(profile_meta.get("last_played_time") or 0),
            )

        self.profile_mgr._sync_profile_to_disk(profile)
        return {
            "profile_id": profile.id,
            "name": profile.name,
            "mode": "create",
            "game_install_path": profile.game_install_path,
            "game_version": profile.game_version,
        }

    def _resolve_game_install_path(self, expected_version: Any) -> str:
        version = str(expected_version or "").strip()
        if not version: return ""

        candidate_paths: list[str] = []
        seen_paths: set[str] = set()
        for profile in GameProfile.select().dicts():
            install_path = str(profile.get("game_install_path") or "").strip()
            if not install_path or not GameManager.detect_executable(install_path):
                continue
            if str(profile.get("game_version") or "").strip() != version:
                continue
            normalized = os.path.normcase(os.path.normpath(install_path))
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            candidate_paths.append(install_path)

        if len(candidate_paths) == 1: return candidate_paths[0]

        auto_detect = self.game_mgr.auto_detect_paths() or {}
        detected_path = str(auto_detect.get("game_install_path") or "").strip()
        if detected_path and GameManager.get_game_version(detected_path) == version: return detected_path
        return ""

    def _replace_directory_contents(self, target_root: Path, source_root: Path) -> None:
        target_root.mkdir(parents=True, exist_ok=True)
        for child in list(target_root.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        for source_path in source_root.rglob("*"):
            relative_path = source_path.relative_to(source_root)
            target_path = target_root / relative_path
            if source_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)

    @staticmethod
    def _read_json_from_zip(bundle: zipfile.ZipFile, member_name: str, default: Any = None) -> Any:
        try:
            with bundle.open(member_name, "r") as handle:
                return json.loads(handle.read().decode("utf-8"))
        except KeyError:
            return deepcopy(default)

    @staticmethod
    def _is_legacy_rule_bundle(payload: Any) -> bool:
        return isinstance(payload, dict) and "user_rules" in payload and "environment" in payload
