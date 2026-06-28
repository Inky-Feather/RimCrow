import shutil
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.api import API
from backend.database.dao import ModDAO
from backend.managers.mgr_profile import ProfileContext, ProfileManager
from backend.scanner.analyzer import ModAnalyzer
from backend.scanner.mod_scanner import ModScanner


class TestProfileManager(unittest.TestCase):
    def test_build_profile_context_keeps_inactive_order(self):
        manager = ProfileManager.__new__(ProfileManager)
        manager.get_profile = Mock(
            return_value=SimpleNamespace(
                id="profile-a",
                game_version="1.5.4100",
                game_install_path="C:/Games/RimWorld",
                user_data_path="C:/Profiles/profile-a",
                use_workshop_mods=True,
                use_self_mods=False,
                inactive_mods_order=["mod.b", "mod.a"],
            )
        )

        with patch.object(ProfileContext, "validate_health", autospec=True, return_value=None):
            context = manager.build_profile_context("profile-a")

        self.assertEqual(context.profile_id, "profile-a")
        self.assertEqual(context.inactive_mods_order, ["mod.b", "mod.a"])

    def test_create_profile_copies_from_current_profile_userdata_config(self):
        manager = ProfileManager.__new__(ProfileManager)
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        current_user_data = temp_root / "current"
        (current_user_data / "Config").mkdir(parents=True)
        target_user_data = temp_root / "target"

        manager.current_profile = SimpleNamespace(user_data_path=str(current_user_data))
        manager._clone_user_data = Mock()
        manager._sync_profile_to_disk = Mock()

        fake_profile = SimpleNamespace(id="new-profile")
        payload = {
            "name": "Test Profile",
            "game_install_path": str(temp_root / "install"),
            "user_data_path": str(target_user_data),
            "use_workshop_mods": False,
            "use_self_mods": False,
            "run_commands": [],
        }

        with patch("backend.managers.mgr_profile.GameManager.detect_executable", return_value="RimWorldWin64.exe"), \
             patch("backend.managers.mgr_profile.GameManager.get_game_version", return_value="1.5.4100"), \
             patch("backend.managers.mgr_profile.GameProfile.create", return_value=fake_profile), \
             patch("backend.managers.mgr_profile.db.atomic", return_value=nullcontext()):
            profile = manager.create_profile(payload, copy_current_data=True)

        self.assertIs(profile, fake_profile)
        manager._clone_user_data.assert_called_once_with(
            str(current_user_data / "Config"),
            str(target_user_data),
        )


class TestModAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = ModAnalyzer()
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def _build_info(self, **file_stats):
        stats = {
            "code_dll": 0,
            "game_xml": 0,
            "patch_xml": 0,
            "lang_xml": 0,
            "image": 0,
            "audio": 0,
        }
        stats.update(file_stats)
        return {
            "mod_type": "Unknown",
            "supported_languages": set(),
            "file_stats": stats,
            "has_assemblies": False,
            "has_defs": stats["game_xml"] > 0,
            "has_tip": False,
        }

    def _write_file(self, relative_path, content="<root />"):
        path = self.temp_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_finalize_keeps_tip_based_language_pack(self):
        info = self._build_info(game_xml=1, lang_xml=3)
        info["has_tip"] = True

        result = self.analyzer._finalize(info)

        self.assertEqual(result["mod_type"], "LanguagePack")

    def test_finalize_mixed_requires_game_xml_image_and_audio(self):
        mixed_info = self._build_info(game_xml=2, image=6, audio=3)
        resource_only_info = self._build_info(image=6, audio=3)

        mixed_result = self.analyzer._finalize(mixed_info)
        resource_only_result = self.analyzer._finalize(resource_only_info)

        self.assertEqual(mixed_result["mod_type"], "Mixed")
        self.assertEqual(resource_only_result["mod_type"], "Unknown")

    def test_analyze_prefers_loadfolders_max_version_and_broadest_path(self):
        self._write_file("mod/Defs/base.xml")
        self._write_file("mod/Cont/Common/Patches/common.xml")
        self._write_file("mod/Cont/1.5/Patches/legacy.xml")
        self._write_file("mod/Cont/1.6/NotDLC/Patches/not_dlc.xml")
        self._write_file("mod/Cont/1.6/DLC/Patches/dlc.xml")
        self._write_file("mod/Cont/1.6/NotDLC/Languages/English/Keyed/lang.xml")
        self._write_file("mod/Cont/1.6/DLC/Languages/ChineseSimplified/Keyed/lang.xml")
        self._write_file(
            "mod/LoadFolders.xml",
            """<?xml version="1.0" encoding="utf-8"?>
<loadFolders>
    <v1.5>
        <li>/</li>
        <li>Cont</li>
        <li IfModActive="Example.Old">Cont/1.5</li>
    </v1.5>
    <v1.6>
        <li>/</li>
        <li>Cont</li>
        <li IfModNotActive="Ludeon.RimWorld.Odyssey">Cont/1.6/NotDLC</li>
        <li IfModActive="Ludeon.RimWorld.Odyssey">Cont/1.6/DLC</li>
    </v1.6>
</loadFolders>
""",
        )

        result = self.analyzer.analyze(str(self.temp_root / "mod"))

        self.assertEqual(result["file_stats"]["game_xml"], 1)
        self.assertEqual(result["file_stats"]["patch_xml"], 2)
        self.assertEqual(result["file_stats"]["lang_xml"], 1)
        self.assertIn("en", result["supported_languages"])
        self.assertNotIn("zh-cn", result["supported_languages"])

    def test_analyze_falls_back_to_real_directory_versions_when_loadfolders_invalid(self):
        self._write_file("broken/Defs/base.xml")
        self._write_file("broken/1.5/Patches/legacy.xml")
        self._write_file("broken/1.6/Patches/current.xml")
        self._write_file("broken/LoadFolders.xml", "<loadFolders>")

        result = self.analyzer.analyze(str(self.temp_root / "broken"))

        self.assertEqual(result["file_stats"]["game_xml"], 1)
        self.assertEqual(result["file_stats"]["patch_xml"], 1)


class TestModScanner(unittest.TestCase):
    def test_dlc_without_package_id_uses_fallback_id(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        install_dir = temp_root / "install"
        dlc_dir = install_dir / "Data" / "Core"
        dlc_dir.mkdir(parents=True)

        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(install_dir),
            user_data_path=str(temp_root / "userdata"),
            use_workshop_mods=False,
            use_self_mods=False,
        )
        scanner = ModScanner(context)
        scanner.xml_parser = Mock()
        scanner.xml_parser.parse.return_value = {"package_id": "", "url": "", "icon_path": ""}
        scanner.analyzer = Mock()
        scanner.analyzer.analyze.return_value = {
            "supported_languages": [],
            "file_stats": {},
            "mod_type": "expansion",
        }
        scanner._resolve_workshop_id = Mock(return_value=None)
        scanner._resolve_images = Mock(return_value=("", ""))

        about_state = SimpleNamespace(resolved_path=None, is_disabled=False)
        with patch("backend.scanner.mod_scanner.ModAnalyzer.resolve_mod_about_state", return_value=about_state):
            mod_data = scanner._process_single_mod(
                str(dlc_dir),
                True,
                existing_snapshots={},
                dlc_parser=None,
                forced_update=False,
            )

        self.assertIsNotNone(mod_data)
        self.assertEqual(mod_data["package_id"], "ludeon.rimworld")
        self.assertEqual(mod_data["source"], "core")


class TestProfileConflictAnalysis(unittest.TestCase):
    def test_conflict_analysis_ignores_disabled_domain_assets(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        install_dir = temp_root / "install"
        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(install_dir),
            user_data_path=str(temp_root / "userdata"),
            use_workshop_mods=True,
            use_self_mods=False,
        )

        workshop_root = temp_root / "workshop"
        self_root = temp_root / "selfmods"
        workshop_path = workshop_root / "123456"
        self_path = self_root / "123456"

        assets = [
            {
                "package_id": "Author.Mod",
                "path": str(workshop_path),
                "name": "Workshop Copy",
                "disabled": False,
            },
            {
                "package_id": "Author.Mod",
                "path": str(self_path),
                "name": "Self Copy",
                "disabled": False,
            },
            {
                "package_id": "Author.Mod",
                "path": str(self_root / "123456_dup"),
                "name": "Self Duplicate",
                "disabled": False,
            },
        ]

        config = SimpleNamespace(
            workshop_mods_path=str(workshop_root),
            self_mods_path=str(self_root),
            enable_tool_mods=False,
        )
        with patch("backend.database.dao.settings.config", config):
            analysis = ModDAO.get_profile_conflict_analysis(context, assets=assets)

        self.assertEqual(analysis["hard_conflicts"], [])
        self.assertEqual(analysis["coexistences"], [])
        self.assertEqual(analysis["deploy_paths"], [str(workshop_path)])

    def test_conflict_analysis_reports_active_coexistence_and_prefers_self_deploy(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        install_dir = temp_root / "install"
        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(install_dir),
            user_data_path=str(temp_root / "userdata"),
            use_workshop_mods=True,
            use_self_mods=True,
        )

        workshop_root = temp_root / "workshop"
        self_root = temp_root / "selfmods"
        workshop_path = workshop_root / "123456"
        self_path = self_root / "123456"

        assets = [
            {
                "package_id": "Author.Mod",
                "path": str(workshop_path),
                "name": "Workshop Copy",
                "disabled": False,
            },
            {
                "package_id": "Author.Mod",
                "path": str(self_path),
                "name": "Self Copy",
                "disabled": False,
            },
        ]

        config = SimpleNamespace(
            workshop_mods_path=str(workshop_root),
            self_mods_path=str(self_root),
            enable_tool_mods=False,
        )
        with patch("backend.database.dao.settings.config", config):
            analysis = ModDAO.get_profile_conflict_analysis(context, assets=assets)

        self.assertEqual(analysis["hard_conflicts"], [])
        self.assertEqual(len(analysis["coexistences"]), 1)
        self.assertEqual(
            [item["path"] for item in analysis["coexistences"][0]["items"]],
            [str(self_path), str(workshop_path)],
        )
        self.assertEqual(analysis["deploy_paths"], [str(self_path)])

    def test_hard_conflict_still_deploys_all_enabled_copies(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        install_dir = temp_root / "install"
        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(install_dir),
            user_data_path=str(temp_root / "userdata"),
            use_workshop_mods=False,
            use_self_mods=True,
        )

        self_root = temp_root / "selfmods"
        same_parent = self_root / "dup_group"
        first_path = same_parent / "copy_a"
        second_path = same_parent / "copy_b"

        assets = [
            {
                "package_id": "Author.Mod",
                "path": str(first_path),
                "name": "Self Copy A",
                "disabled": False,
            },
            {
                "package_id": "Author.Mod",
                "path": str(second_path),
                "name": "Self Copy B",
                "disabled": False,
            },
        ]

        config = SimpleNamespace(
            workshop_mods_path=str(temp_root / "workshop"),
            self_mods_path=str(self_root),
            enable_tool_mods=False,
        )
        with patch("backend.database.dao.settings.config", config):
            analysis = ModDAO.get_profile_conflict_analysis(context, assets=assets)

        self.assertEqual(len(analysis["hard_conflicts"]), 1)
        self.assertEqual(analysis["coexistences"], [])
        self.assertEqual(analysis["deploy_paths"], [str(first_path), str(second_path)])


class TestApiScanMods(unittest.TestCase):
    def test_scan_mods_always_scans_all_configured_domains_for_inventory_sync(self):
        api = API.__new__(API)
        api.active_context = SimpleNamespace(
            game_dlc_path="C:/Games/RimWorld/Data",
            local_mods_path="C:/Games/RimWorld/Mods",
            use_workshop_mods=False,
            use_self_mods=False,
            profile_id="profile-a",
        )
        api.scanner = Mock()
        api.scanner.scan_paths_async.return_value = {"status": "started", "task_id": "task-1"}

        config = SimpleNamespace(
            self_mods_path="D:/RMM/SelfMods",
            workshop_mods_path="D:/Steam/workshop/content/294100",
            enable_tool_mods=False,
        )

        with patch("backend.api.settings.config", config), \
             patch("backend.api.os.path.exists", return_value=True):
            res = API.scan_mods(api)

        self.assertEqual(res["status"], "success")
        api.scanner.scan_paths_async.assert_called_once_with(
            [
                "C:/Games/RimWorld/Data",
                "C:/Games/RimWorld/Mods",
                "D:/RMM/SelfMods",
                "D:/Steam/workshop/content/294100",
            ],
            forced_update=False,
        )


if __name__ == "__main__":
    unittest.main()
