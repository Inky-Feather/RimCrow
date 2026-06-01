import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.database.dao import ModDAO, _ProfilePathScope
from backend.managers.mgr_data_bundle import DataBundleManager
from backend.managers.mgr_mod_package import ModPackageManager
from backend.settings import settings


def _make_context(local_mods_path: str, game_dlc_path: str = "", *, use_workshop_mods: bool = True, use_self_mods: bool = True):
    return SimpleNamespace(
        local_mods_path=local_mods_path,
        game_dlc_path=game_dlc_path,
        use_workshop_mods=use_workshop_mods,
        use_self_mods=use_self_mods,
    )


class _StubProfileManager:
    def __init__(self, profiles=None, target_profile=None):
        self._profiles = profiles or []
        self._target_profile = target_profile

    def get_all_profiles(self):
        return list(self._profiles)

    def get_profile(self, profile_id):
        if self._target_profile and self._target_profile.id == profile_id:
            return self._target_profile
        raise KeyError(profile_id)

    def build_profile_context(self, profile_id):
        if self._target_profile and self._target_profile.id == profile_id:
            return self._target_profile
        raise KeyError(profile_id)


class TestDataBundleManager(unittest.TestCase):
    def test_build_profile_conflict_entries_collects_all_same_name_profiles(self):
        profile_mgr = _StubProfileManager([
            {
                "id": "local-a",
                "name": "同名环境",
                "description": "A",
                "game_install_path": "D:/RimWorld-A",
                "user_data_path": "D:/Data-A",
                "game_version": "1.5",
                "last_played_time": 11,
            },
            {
                "id": "local-b",
                "name": "同名环境",
                "description": "B",
                "game_install_path": "D:/RimWorld-B",
                "user_data_path": "D:/Data-B",
                "game_version": "1.6",
                "last_played_time": 22,
            },
        ])
        manager = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)

        entries = manager._build_profile_conflict_entries([  # noqa: SLF001
            {"archive_key": "bundle-a", "name": "同名环境"},
        ])

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["archive_key"], "bundle-a")
        self.assertEqual({item["profile_id"] for item in entries[0]["conflicts"]}, {"local-a", "local-b"})

    def test_overwrite_existing_profile_only_replaces_user_data_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_root = Path(temp_dir) / "target"
            source_root = Path(temp_dir) / "source"
            target_root.mkdir(parents=True)
            source_root.mkdir(parents=True)
            (target_root / "old.txt").write_text("old", encoding="utf-8")
            (source_root / "new.txt").write_text("new", encoding="utf-8")

            target_profile = SimpleNamespace(
                id="profile-1",
                name="本地环境",
                user_data_path=str(target_root),
                game_install_path="D:/RimWorld",
                game_version="1.6",
            )
            manager = DataBundleManager(
                _StubProfileManager(target_profile=target_profile),
                ai_mgr=None,
                rule_mgr_provider=lambda: None,
            )

            result = manager._overwrite_existing_profile("profile-1", {"name": "导入名"}, source_root)  # noqa: SLF001

            self.assertFalse((target_root / "old.txt").exists())
            self.assertEqual((target_root / "new.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual(result["mode"], "overwrite")
            self.assertEqual(result["name"], "本地环境")
            self.assertEqual(result["game_install_path"], "D:/RimWorld")

    def test_create_imported_profile_restores_metadata_but_uses_new_local_root_and_empty_install_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            source_root = temp_root / "source"
            source_root.mkdir(parents=True)
            (source_root / "Config").mkdir()
            (source_root / "Config" / "ModsConfig.xml").write_text("<mods />", encoding="utf-8")

            profile_mgr = _StubProfileManager()
            profile_mgr._get_install_inspector = lambda: SimpleNamespace(inspect=lambda *_args, **_kwargs: None)
            profile_mgr._sync_profile_to_disk = lambda _profile: None
            manager = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)

            created_rows = []

            class _Atomic:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            def _create(**payload):
                created_rows.append(payload)
                return SimpleNamespace(**payload)

            with patch("backend.managers.mgr_data_bundle.DATA_DIR", temp_root / "appdata"), \
                 patch("backend.managers.mgr_data_bundle.uuid.uuid4", return_value=SimpleNamespace(hex="profile-new")), \
                 patch("backend.managers.mgr_data_bundle.GameProfile.create", side_effect=_create), \
                 patch("backend.managers.mgr_data_bundle.db.atomic", return_value=_Atomic()):
                result = manager._create_imported_profile(  # noqa: SLF001
                    {
                        "name": "导入环境",
                        "description": "desc",
                        "game_version": "1.6",
                        "prefer_steam_launch": True,
                        "use_workshop_mods": True,
                        "use_self_mods": False,
                        "run_commands": ["-foo"],
                        "inactive_mods_order": ["a"],
                        "last_played_time": 123,
                    },
                    source_root,
                    selected_install_path="",
                )

            self.assertEqual(result["mode"], "create")
            self.assertEqual(created_rows[0]["game_install_path"], "")
            self.assertEqual(created_rows[0]["user_data_path"], str(temp_root / "appdata" / "profiles" / "profile-new"))
            self.assertEqual(created_rows[0]["name"], "导入环境")


class TestModPackageManager(unittest.TestCase):
    def test_import_bundle_post_actions_keeps_profile_refresh_and_scan_independent(self):
        profile_mgr = _StubProfileManager()
        data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
        manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "mods_export.rmmmods.zip"
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(
                    "manifest.json",
                    '{"has_environment_data": true, "profiles": [{"archive_key": "profile-a"}], "mods": []}',
                )

            with (
                patch.object(
                    manager,
                    "inspect_bundle",
                    return_value={"has_environment_data": True, "profiles": [{"archive_key": "profile-a"}], "mods": []},
                ),
                patch.object(
                    data_bundle_mgr,
                    "_import_profiles_from_bundle",
                    return_value=([{"profile_id": "profile-1", "mode": "overwrite"}], []),
                ),
                patch.object(
                    manager,
                    "_import_mod_directories",
                    return_value={"imported_mods": [], "skipped_mods": [], "renamed_mods": [], "warnings": []},
                ),
                patch.object(manager, "should_scan_after_import", return_value=True),
            ):
                result = manager.import_bundle(
                    str(bundle_path),
                    {
                        "import_mods": True,
                        "apply_environment_data": True,
                        "target_kind": "self_mods",
                        "current_profile_id": "profile-1",
                        "current_local_mods_path": "D:/Game/Mods",
                        "profile_import_plan": [],
                    },
                )

        self.assertTrue(result["post_actions"]["scan_current_view"])
        self.assertTrue(result["post_actions"]["refresh_current_profile"])
        self.assertTrue(result["post_actions"]["refresh_profile_list"])

    def test_export_and_import_bundle_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            local_root = temp_root / "Game" / "Mods"
            workshop_root = temp_root / "WorkshopMods"
            self_root = temp_root / "SelfMods"
            data_root = temp_root / "Game" / "Data"
            user_data_root = temp_root / "UserData"
            for root in (local_root, workshop_root, self_root, data_root, user_data_root):
                root.mkdir(parents=True, exist_ok=True)

            mod_path = local_root / "LocalMod"
            mod_path.mkdir(parents=True, exist_ok=True)
            (mod_path / "About.xml").write_text("<mod />", encoding="utf-8")
            (user_data_root / "mods_config.xml").write_text("config", encoding="utf-8")

            target_profile = SimpleNamespace(
                id="profile-1",
                name="环境一",
                description="desc",
                local_mods_path=str(local_root),
                game_dlc_path=str(data_root),
                user_data_path=str(user_data_root),
                game_install_path="D:/RimWorld",
                game_version="1.6",
                prefer_steam_launch=False,
                use_workshop_mods=True,
                use_self_mods=True,
                run_commands=[],
                inactive_mods_order=[],
                last_played_time=0,
            )
            profile_mgr = _StubProfileManager(target_profile=target_profile)
            data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
            manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)
            bundle_path = temp_root / "mods_export.rmmmods.zip"
            visible_mods = [{"package_id": "local.mod", "name": "Local Mod", "path": str(mod_path)}]

            with (
                patch.object(settings.config, "self_mods_path", str(self_root)),
                patch.object(settings.config, "workshop_mods_path", str(workshop_root)),
                patch.object(settings.config, "bundle_mod_folder_name_type", "default"),
                patch.object(ModDAO, "get_profile_mods", return_value=visible_mods),
                patch.object(manager, "_read_active_tokens", return_value=[]),
            ):
                export_result = manager.export_bundle(str(bundle_path), {
                    "profile_id": "profile-1",
                    "export_scope": "custom",
                    "mod_ids": ["local.mod"],
                    "include_environment_data": True,
                })
                inspect_result = manager.inspect_bundle(str(bundle_path))
                import_result = manager.import_bundle(str(bundle_path), {
                    "target_kind": "self_mods",
                    "import_mods": True,
                    "apply_environment_data": False,
                })

            self.assertTrue(bundle_path.exists())
            self.assertEqual(len(export_result["mods"]), 1)
            self.assertEqual(export_result["profiles"][0]["original_profile_id"], "profile-1")
            self.assertTrue(inspect_result["has_environment_data"])
            self.assertEqual(inspect_result["mods"][0]["folder_name"], "LocalMod")
            self.assertEqual(import_result["imported_mods"][0]["folder_name"], "LocalMod")
            self.assertTrue((self_root / "LocalMod" / "About.xml").exists())

    def test_export_bundle_can_rename_packaged_mod_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            local_root = temp_root / "Game" / "Mods"
            self_root = temp_root / "SelfMods"
            user_data_root = temp_root / "UserData"
            local_root.mkdir(parents=True, exist_ok=True)
            self_root.mkdir(parents=True, exist_ok=True)
            user_data_root.mkdir(parents=True, exist_ok=True)

            first_mod_path = local_root / "OriginalOne"
            second_mod_path = local_root / "OriginalTwo"
            for mod_path in (first_mod_path, second_mod_path):
                mod_path.mkdir(parents=True, exist_ok=True)
                (mod_path / "About.xml").write_text("<mod />", encoding="utf-8")

            target_profile = SimpleNamespace(
                id="profile-1",
                name="环境一",
                description="desc",
                local_mods_path=str(local_root),
                game_dlc_path="",
                user_data_path=str(user_data_root),
                game_install_path="D:/RimWorld",
                game_version="1.6",
                prefer_steam_launch=False,
                use_workshop_mods=False,
                use_self_mods=True,
                run_commands=[],
                inactive_mods_order=[],
                last_played_time=0,
            )
            profile_mgr = _StubProfileManager(target_profile=target_profile)
            data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
            manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)
            bundle_path = temp_root / "mods_export.rmmmods.zip"
            visible_mods = [
                {"package_id": "local.one", "name": "First", "alias_name": "Same:Name?", "path": str(first_mod_path)},
                {"package_id": "local.two", "name": "Second", "alias_name": "Same/Name*", "path": str(second_mod_path)},
            ]

            with (
                patch.object(settings.config, "self_mods_path", str(self_root)),
                patch.object(settings.config, "workshop_mods_path", ""),
                patch.object(ModDAO, "get_profile_mods", return_value=visible_mods),
                patch.object(manager, "_read_active_tokens", return_value=[]),
            ):
                export_result = manager.export_bundle(str(bundle_path), {
                    "profile_id": "profile-1",
                    "export_scope": "custom",
                    "mod_ids": ["local.one", "local.two"],
                    "folder_name_type": "alias_name",
                })

            self.assertTrue(first_mod_path.exists())
            self.assertTrue(second_mod_path.exists())
            self.assertEqual([item["folder_name"] for item in export_result["mods"]], ["Same_Name_", "Same_Name_2"])
            self.assertEqual([item["original_folder_name"] for item in export_result["mods"]], ["OriginalOne", "OriginalTwo"])
            self.assertTrue(any("非法字符" in item for item in export_result["warnings"]))
            self.assertTrue(any("重名" in item for item in export_result["warnings"]))
            with zipfile.ZipFile(bundle_path, "r") as bundle:
                names = set(bundle.namelist())
                self.assertIn("mods/Same_Name_/About.xml", names)
                self.assertIn("mods/Same_Name_2/About.xml", names)
                manifest = manager._read_json_from_zip(bundle, "manifest.json", {})  # noqa: SLF001
            self.assertEqual([item["folder_name"] for item in manifest["mods"]], ["Same_Name_", "Same_Name_2"])
            self.assertEqual([item["original_folder_name"] for item in manifest["mods"]], ["OriginalOne", "OriginalTwo"])

    def test_export_folder_name_type_uses_expected_fallback_chain(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            local_root = temp_root / "Game" / "Mods"
            local_root.mkdir(parents=True, exist_ok=True)
            mod_path = local_root / "OriginalLocal"
            mod_path.mkdir(parents=True, exist_ok=True)
            (mod_path / "About.xml").write_text("<mod />", encoding="utf-8")

            target_profile = SimpleNamespace(
                id="profile-1",
                name="环境一",
                description="desc",
                local_mods_path=str(local_root),
                game_dlc_path="",
                user_data_path=str(temp_root / "UserData"),
                game_install_path="D:/RimWorld",
                game_version="1.6",
                prefer_steam_launch=False,
                use_workshop_mods=False,
                use_self_mods=True,
                run_commands=[],
                inactive_mods_order=[],
                last_played_time=0,
            )
            profile_mgr = _StubProfileManager(target_profile=target_profile)
            data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
            manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)
            visible_mods = [{"package_id": "fallback.package", "name": "", "alias_name": "", "path": str(mod_path)}]

            with (
                patch.object(settings.config, "self_mods_path", str(temp_root / "SelfMods")),
                patch.object(settings.config, "workshop_mods_path", ""),
                patch.object(ModDAO, "get_profile_mods", return_value=visible_mods),
                patch.object(manager, "_read_active_tokens", return_value=[]),
            ):
                alias_plan = manager.preview_export({"profile_id": "profile-1", "mod_ids": ["fallback.package"], "folder_name_type": "alias_name"})
                workshop_plan = manager.preview_export({"profile_id": "profile-1", "mod_ids": ["fallback.package"], "folder_name_type": "workshop_id"})

            self.assertEqual(alias_plan["mods"][0]["folder_name"], "OriginalLocal")
            self.assertEqual(workshop_plan["mods"][0]["folder_name"], "fallback.package")

    def test_prepare_import_returns_payload_stats_and_disk_estimate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            bundle_path = temp_root / "mods_export.rmmmods.zip"
            self_root = temp_root / "SelfMods"
            self_root.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(
                    "manifest.json",
                    '{"format":"rmm.mod.package","schema_version":1,"mods":[{"folder_name":"LocalMod"}],"profiles":[],"has_environment_data":false}',
                )
                bundle.writestr("mods/LocalMod/About/About.xml", "<mod />")

            profile_mgr = _StubProfileManager()
            data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
            manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)

            with patch.object(settings.config, "self_mods_path", str(self_root)):
                result = manager.prepare_import(str(bundle_path), {"target_kind": "self_mods"})

            self.assertEqual(result["mod_payload_stats"]["file_count"], 1)
            self.assertGreater(result["mod_payload_stats"]["uncompressed_bytes"], 0)
            self.assertEqual(result["target_disk_space"]["required_bytes"], result["mod_payload_stats"]["uncompressed_bytes"])
            self.assertTrue(result["target_disk_space"]["enough"])

    def test_import_bundle_rejects_when_target_disk_space_is_insufficient(self):
        profile_mgr = _StubProfileManager()
        data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
        manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "mods_export.rmmmods.zip"
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(
                    "manifest.json",
                    '{"format":"rmm.mod.package","schema_version":1,"mods":[],"profiles":[],"has_environment_data":false}',
                )

            with (
                patch.object(
                    manager,
                    "inspect_bundle",
                    return_value={
                        "mods": [],
                        "profiles": [],
                        "has_environment_data": False,
                        "mod_payload_stats": {"uncompressed_bytes": 1024},
                    },
                ),
                patch("backend.managers.mgr_mod_package.estimate_disk_space_requirement", return_value={
                    "path": "D:/Mods",
                    "free_bytes": 128,
                    "required_bytes": 1024,
                    "headroom_bytes": 256,
                    "recommended_bytes": 1280,
                    "enough": False,
                }),
                patch.object(settings.config, "self_mods_path", "D:/Mods"),
            ):
                with self.assertRaisesRegex(ValueError, "剩余空间不足"):
                    manager.import_bundle(str(bundle_path), {"target_kind": "self_mods", "import_mods": True})

    def test_profile_effective_scope_only_uses_local_self_and_workshop_mods(self):
        profile_mgr = _StubProfileManager()
        data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
        manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)
        context = _make_context("D:/Game/Mods", "D:/Game/Data")
        visible_mods = [
            {"package_id": "local.mod", "path": "D:/Game/Mods/LocalMod"},
            {"package_id": "self.mod", "path": "D:/SelfMods/SelfMod"},
            {"package_id": "workshop.mod", "path": "D:/WorkshopMods/WorkshopMod"},
            {"package_id": "core.mod", "path": "D:/Game/Data/Core"},
            {"package_id": "tool.mod", "path": "D:/ToolMods/ToolMod"},
        ]

        with (
            patch.object(settings.config, "self_mods_path", "D:/SelfMods"),
            patch.object(settings.config, "workshop_mods_path", "D:/WorkshopMods"),
        ):
            path_scope = _ProfilePathScope.from_context(context)
            result = manager._resolve_requested_mod_ids(  # noqa: SLF001
                {"export_scope": "profile-effective"},
                [mod for mod in visible_mods if manager._is_exportable_mod_asset(mod, path_scope)],  # noqa: SLF001
                [],
            )

        self.assertEqual(result, ["local.mod", "self.mod", "workshop.mod"])

    def test_resolve_export_mods_skips_official_and_tool_assets_and_uses_workshop_fallback_for_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            local_root = temp_root / "Game" / "Mods"
            workshop_root = temp_root / "WorkshopMods"
            self_root = temp_root / "SelfMods"
            data_root = temp_root / "Game" / "Data"
            tool_root = temp_root / "ToolMods"
            for root in (local_root, workshop_root, self_root, data_root, tool_root):
                root.mkdir(parents=True, exist_ok=True)

            local_mod_path = local_root / "LocalMod"
            self_mod_path = self_root / "SelfMod"
            link_mod_path = local_root / "LinkMod"
            workshop_link_target = workshop_root / "LinkModWorkshop"
            core_mod_path = data_root / "Core"
            tool_mod_path = tool_root / "HelperTool"
            for path in (local_mod_path, self_mod_path, link_mod_path, workshop_link_target, core_mod_path, tool_mod_path):
                path.mkdir(parents=True, exist_ok=True)

            profile_mgr = _StubProfileManager()
            data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
            manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)
            context = _make_context(str(local_root), str(data_root))
            visible_mods = [
                {"package_id": "local.mod", "name": "Local Mod", "path": str(local_mod_path)},
                {"package_id": "self.mod", "name": "Self Mod", "path": str(self_mod_path)},
                {
                    "package_id": "link.mod",
                    "name": "Link Mod",
                    "path": str(link_mod_path),
                    "coexist_workshop_variant": {
                        "package_id": "link.mod",
                        "name": "Link Mod Workshop",
                        "path": str(workshop_link_target),
                        "file_modify_time": 10,
                        "file_create_time": 10,
                    },
                },
                {"package_id": "core.mod", "name": "Core Mod", "path": str(core_mod_path)},
                {"package_id": "tool.mod", "name": "Tool Mod", "path": str(tool_mod_path)},
            ]

            with (
                patch.object(settings.config, "self_mods_path", str(self_root)),
                patch.object(settings.config, "workshop_mods_path", str(workshop_root)),
                patch.object(manager, "_is_deployed_workshop_link", side_effect=lambda path: path == str(link_mod_path)),
            ):
                path_scope = _ProfilePathScope.from_context(context)
                export_mods, warnings = manager._resolve_export_mods(  # noqa: SLF001
                    visible_mods,
                    ["local.mod", "self.mod", "link.mod", "core.mod", "tool.mod"],
                    set(),
                    path_scope,
                )

        self.assertEqual([item["package_id"] for item in export_mods], ["local.mod", "self.mod", "link.mod"])
        self.assertEqual([item["folder_name"] for item in export_mods], ["LocalMod", "SelfMod", "LinkModWorkshop"])
        self.assertEqual(warnings, [])

    def test_preview_export_without_extra_options_skips_interlock_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            local_root = Path(temp_dir) / "Game" / "Mods"
            data_root = Path(temp_dir) / "Game" / "Data"
            local_root.mkdir(parents=True, exist_ok=True)
            data_root.mkdir(parents=True, exist_ok=True)
            mod_path = local_root / "LocalMod"
            mod_path.mkdir(parents=True, exist_ok=True)
            (mod_path / "About.xml").write_text("<mod />", encoding="utf-8")

            profile = SimpleNamespace(
                id="profile-1",
                local_mods_path=str(local_root),
                game_dlc_path=str(data_root),
                use_workshop_mods=True,
                use_self_mods=True,
            )
            profile_mgr = _StubProfileManager(target_profile=profile)
            data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
            manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)
            visible_mods = [{"package_id": "local.mod", "name": "Local Mod", "path": str(mod_path)}]

            with (
                patch.object(settings.config, "self_mods_path", str(Path(temp_dir) / "SelfMods")),
                patch.object(settings.config, "workshop_mods_path", str(Path(temp_dir) / "WorkshopMods")),
                patch.object(settings.config, "bundle_mod_folder_name_type", "default"),
                patch.object(ModDAO, "get_profile_mods", return_value=visible_mods),
                patch.object(manager, "_read_active_tokens", return_value=[]),
                patch.object(manager, "_build_interlock_map", side_effect=AssertionError("unexpected interlock lookup")),
            ):
                export_plan = manager.preview_export({
                    "profile_id": "profile-1",
                    "export_scope": "custom",
                    "mod_ids": ["local.mod"],
                })

            self.assertEqual(export_plan["mod_count"], 1)
            self.assertEqual(export_plan["mods"][0]["folder_name"], "LocalMod")

    def test_start_export_task_can_cancel_and_emit_cancelled_progress(self):
        profile_mgr = _StubProfileManager()
        data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
        manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)
        progress_events = []
        finished = threading.Event()

        def capture_progress(task_id, task_type, status="running", progress=0, message="", metrics=None):
            progress_events.append({
                "id": task_id,
                "type": task_type,
                "status": status,
                "progress": progress,
                "message": message,
                "metrics": dict(metrics or {}),
            })
            if status in {"success", "failed", "cancelled"}:
                finished.set()

        def blocking_export(*_args, cancel_event=None, **_kwargs):
            while not (cancel_event and cancel_event.is_set()):
                time.sleep(0.01)
            raise InterruptedError("cancelled")

        with (
            patch.object(manager, "preview_export", return_value={"mods": [{"name": "Local Mod"}], "warnings": [], "profile_id": "profile-1"}),
            patch.object(manager, "_write_export_bundle", side_effect=blocking_export),
            patch("backend.managers.mgr_mod_package.EventBus.emit_progress", side_effect=capture_progress),
        ):
            task_id = manager.start_export_task("F:/tmp/test.rmmmods.zip", {"profile_id": "profile-1"})
            self.assertTrue(manager.cancel_export_task(task_id))
            self.assertTrue(finished.wait(timeout=2), "export task did not finish after cancellation")

        self.assertEqual(progress_events[0]["status"], "pending")
        self.assertIn("prepare", progress_events[0]["metrics"].get("phase", ""))
        self.assertEqual(progress_events[-1]["status"], "cancelled")

    def test_import_mod_directories_honors_rename_and_skip_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / "mods.zip"
            target_root = Path(temp_dir) / "target"
            target_root.mkdir(parents=True)
            (target_root / "KeepMe").mkdir()
            (target_root / "KeepMe" / "local.txt").write_text("local", encoding="utf-8")
            (target_root / "SkipMe").mkdir()
            (target_root / "SkipMe" / "local.txt").write_text("skip", encoding="utf-8")

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("mods/KeepMe/About.xml", "<keep />")
                bundle.writestr("mods/SkipMe/About.xml", "<skip />")

            profile_mgr = _StubProfileManager()
            data_bundle_mgr = DataBundleManager(profile_mgr, ai_mgr=None, rule_mgr_provider=lambda: None)
            manager = ModPackageManager(profile_mgr, data_bundle_mgr, load_order_mgr_provider=lambda: None)

            with zipfile.ZipFile(zip_path, "r") as bundle:
                result = manager._import_mod_directories(  # noqa: SLF001
                    bundle,
                    [{"folder_name": "KeepMe"}, {"folder_name": "SkipMe"}],
                    str(target_root),
                    {
                        "keepme": {"mode": "rename", "rename_to": "KeepMe_imported"},
                        "skipme": {"mode": "skip", "rename_to": ""},
                    },
                )

            self.assertEqual(result["skipped_mods"][0]["folder_name"], "SkipMe")
            self.assertEqual(result["renamed_mods"][0]["to"], "KeepMe_imported")
            self.assertTrue((target_root / "KeepMe" / "local.txt").exists())
            self.assertTrue((target_root / "KeepMe_imported" / "About.xml").exists())
            self.assertFalse((target_root / "SkipMe" / "About.xml").exists())


if __name__ == "__main__":
    unittest.main()
