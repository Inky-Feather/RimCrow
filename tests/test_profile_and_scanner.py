import os
import json
import shutil
import tempfile
import threading
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.api import API
from backend.database.dao import ModDAO
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_game_install import GameInstallFacts, GameInstallInspector, GameInstallRegistry, detect_is_steam_managed_install
from backend.managers.mgr_files import PathChecker
from backend.managers.mgr_profile import ProfileContext, ProfileManager
from backend.managers.mgr_steam import SteamManager
from backend.utils.profile_runtime import normalize_profile_runtime_flags, resolve_profile_runtime_capabilities
from backend.migrations.app_upgrade import AppUpgradeResult, _migrate_profile_steam_runtime_flags
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
        manager._get_install_inspector = Mock(return_value=SimpleNamespace(
            inspect=Mock(return_value=SimpleNamespace(is_steam=False, game_version="1.5.4100"))
        ))

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

    def test_get_launch_args_includes_savedatafolder_for_default_profile(self):
        manager = ProfileManager.__new__(ProfileManager)
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        profile = SimpleNamespace(
            id="default",
            game_install_path=str(temp_root),
            user_data_path=str(temp_root / "userdata")
        )
        manager.current_profile = profile

        with patch("backend.managers.mgr_profile.GameProfile.get_or_none", return_value=profile), \
             patch("backend.managers.mgr_profile.GameManager.detect_executable", return_value=str(temp_root / "RimWorldWin64.exe")):
            args = manager.get_launch_args("default")

        self.assertIn(f"-savedatafolder={os.path.abspath(profile.user_data_path)}", args)

    def test_import_profile_from_disk_re_normalizes_runtime_flags(self):
        manager = ProfileManager.__new__(ProfileManager)
        imported_profile = {
            "id": "profile-a",
            "name": "Profile A",
            "game_install_path": "D:/Games/RimWorld",
            "game_version": "1.5.0",
            "prefer_steam_launch": True,
            "use_workshop_mods": True,
            "user_data_path": "D:/Profiles/profile-a",
        }

        inserted_rows = []

        class _InsertQuery:
            def __init__(self, payload):
                self.payload = payload

            def on_conflict_replace(self):
                return self

            def execute(self):
                inserted_rows.append(self.payload)
                return 1

        manager._get_install_inspector = Mock(return_value=SimpleNamespace(
            inspect=Mock(return_value=SimpleNamespace(is_steam=False, game_version="1.6.4100"))
        ))

        with patch("backend.managers.mgr_profile.GameProfile.insert", side_effect=lambda **payload: _InsertQuery(payload)), \
             patch("backend.managers.mgr_profile.db.atomic", return_value=nullcontext()):
            ok, _ = manager.import_profile_from_disk(imported_profile)

        self.assertTrue(ok)
        self.assertEqual(len(inserted_rows), 1)
        self.assertFalse(inserted_rows[0]["prefer_steam_launch"])
        self.assertTrue(inserted_rows[0]["use_workshop_mods"])
        self.assertFalse(inserted_rows[0]["is_steam"])
        self.assertEqual(inserted_rows[0]["game_version"], "1.6.4100")


class TestPathChecker(unittest.TestCase):
    def test_check_user_data_path_warns_when_mods_config_missing(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        target_root = temp_root / "userdata"
        config_dir = target_root / "Config"
        config_dir.mkdir(parents=True, exist_ok=True)

        result = PathChecker.check_user_data_path(str(target_root))

        self.assertTrue(result["pass"])
        self.assertEqual(result["type"], "warn")
        self.assertIn("ModsConfig.xml", result["msg"])

    def test_check_workshop_path_requires_rimworld_workshop_root(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        valid_root = temp_root / "steamapps" / "workshop" / "content" / "294100"
        invalid_root = temp_root / "steamapps" / "workshop" / "downloads"
        valid_root.mkdir(parents=True, exist_ok=True)
        invalid_root.mkdir(parents=True, exist_ok=True)

        self.assertTrue(PathChecker.check_workshop_path(str(valid_root))["pass"])
        self.assertFalse(PathChecker.check_workshop_path(str(invalid_root))["pass"])


class TestProfileRuntimeHelpers(unittest.TestCase):
    def test_normalize_profile_runtime_flags_forces_workshop_false_when_prefer_steam_enabled(self):
        result = normalize_profile_runtime_flags(
            True,
            prefer_steam_launch=True,
            use_workshop_mods=True,
        )

        self.assertTrue(result["is_steam"])
        self.assertTrue(result["prefer_steam_launch"])
        self.assertFalse(result["use_workshop_mods"])

    def test_normalize_profile_runtime_flags_forces_prefer_false_when_not_steam(self):
        result = normalize_profile_runtime_flags(
            False,
            prefer_steam_launch=True,
            use_workshop_mods=True,
        )

        self.assertFalse(result["is_steam"])
        self.assertFalse(result["prefer_steam_launch"])
        self.assertTrue(result["use_workshop_mods"])

    def test_detect_is_steam_managed_install_keeps_old_path_semantics_separate(self):
        self.assertTrue(detect_is_steam_managed_install("C:/Program Files (x86)/Steam/steamapps/common/RimWorld"))
        self.assertFalse(detect_is_steam_managed_install("D:/Games/RimWorld"))
        self.assertFalse(detect_is_steam_managed_install("D:/Games/steamapps/cache/common/RimWorld"))

    def test_resolve_profile_runtime_capabilities_uses_mutual_exclusion(self):
        context = SimpleNamespace(
            is_steam=True,
            is_steam_managed=False,
            prefer_steam_launch=True,
            use_workshop_mods=True,
        )

        with patch("backend.utils.profile_runtime.settings.config", SimpleNamespace(workshop_mods_path="D:/Workshop", steam_path="C:/Steam")):
            caps = resolve_profile_runtime_capabilities(context)

        self.assertTrue(caps["steam_launch_enabled"])
        self.assertFalse(caps["workshop_deploy_enabled"])
        self.assertTrue(caps["workshop_detection_enabled"])


class TestGameInstallRegistry(unittest.TestCase):
    def test_registry_set_writes_atomically(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)
        registry_path = temp_root / "known_game_installs.json"
        registry = GameInstallRegistry(registry_path)

        registry.set(GameInstallFacts(install_path="D:/Games/RimWorld", is_steam=True, checked_at=123))

        self.assertTrue(registry_path.exists())
        self.assertFalse((temp_root / "known_game_installs.json.tmp").exists())
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        self.assertTrue(payload["installs"])

    def test_registry_load_moves_corrupt_file_aside(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)
        registry_path = temp_root / "known_game_installs.json"
        registry_path.write_text("{broken", encoding="utf-8")
        registry = GameInstallRegistry(registry_path)

        payload = registry._load()

        self.assertEqual(payload, {"installs": {}})
        self.assertFalse(registry_path.exists())
        self.assertTrue((temp_root / "known_game_installs.json.corrupt").exists())

    def test_registry_prune_invalid_entries_removes_missing_install(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)
        registry_path = temp_root / "known_game_installs.json"
        registry_path.write_text(json.dumps({
            "installs": {
                "missing": {
                    "install_path": str(temp_root / "missing-install"),
                    "executable_path": "",
                    "is_steam": True,
                    "is_steam_managed": True,
                    "checked_at": 1,
                }
            }
        }), encoding="utf-8")
        registry = GameInstallRegistry(registry_path)

        removed_count = registry.prune_invalid_entries()

        self.assertEqual(removed_count, 1)
        self.assertEqual(registry._load(), {"installs": {}})

    def test_registry_prune_invalid_entries_normalizes_cached_managed_flag(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)
        install_root = temp_root / "steamapps" / "common" / "RimWorld"
        install_root.mkdir(parents=True, exist_ok=True)
        (install_root / "RimWorldWin64.exe").write_text("", encoding="utf-8")
        registry_path = temp_root / "known_game_installs.json"
        registry_path.write_text(json.dumps({
            "installs": {
                "legacy": {
                    "install_path": str(install_root),
                    "executable_path": "RimWorldWin64.exe",
                    "is_steam": False,
                    "is_steam_managed": True,
                    "checked_at": 1,
                }
            }
        }), encoding="utf-8")
        registry = GameInstallRegistry(registry_path)

        removed_count = registry.prune_invalid_entries()
        normalized = next(iter(registry._load()["installs"].values()))

        self.assertEqual(removed_count, 0)
        self.assertFalse(normalized["is_steam_managed"])
        self.assertTrue(str(normalized["executable_path"]).endswith("RimWorldWin64.exe"))


class TestGameInstallInspector(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        GameInstallInspector._startup_pruned = False

    def test_quick_inspect_requires_is_steam_before_marking_managed(self):
        install_root = self.temp_root / "steamapps" / "common" / "RimWorld"
        install_root.mkdir(parents=True, exist_ok=True)
        (install_root / "RimWorldWin64.exe").write_text("", encoding="utf-8")
        (install_root / "steam_appid.txt").write_text("294100", encoding="utf-8")

        with patch("backend.managers.mgr_game_install.platform.system", return_value="Windows"):
            facts = GameInstallInspector().quick_inspect(str(install_root))

        self.assertFalse(facts.is_steam)
        self.assertFalse(facts.is_steam_managed)

    def test_find_windows_steam_api_in_unity_plugins_directory(self):
        install_root = self.temp_root / "RimWorld"
        plugin_dir = install_root / "RimWorldWin64_Data" / "Plugins" / "x86_64"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (install_root / "RimWorldWin64.exe").write_text("", encoding="utf-8")
        (install_root / "steam_appid.txt").write_text("294100", encoding="utf-8")
        target_dll = plugin_dir / "steam_api64.dll"
        target_dll.write_text("", encoding="utf-8")

        with patch("backend.managers.mgr_game_install.platform.system", return_value="Windows"):
            facts = GameInstallInspector().quick_inspect(str(install_root))

        self.assertEqual(Path(facts.steam_api_path).resolve(), target_dll.resolve())
        self.assertTrue(facts.is_steam)
        self.assertIn("probe_fallback:probe_error", facts.signals)

    def test_find_linux_steam_api_in_unity_plugins_directory(self):
        install_root = self.temp_root / "RimWorld"
        plugin_dir = install_root / "RimWorldLinux_Data" / "Plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (install_root / "RimWorldLinux").write_text("", encoding="utf-8")
        (install_root / "steam_appid.txt").write_text("294100", encoding="utf-8")
        target_lib = plugin_dir / "libsteam_api.so"
        target_lib.write_text("", encoding="utf-8")

        with patch("backend.managers.mgr_game_install.platform.system", return_value="Linux"):
            facts = GameInstallInspector().quick_inspect(str(install_root))

        self.assertEqual(Path(facts.steam_api_path).resolve(), target_lib.resolve())
        self.assertTrue(facts.is_steam)
        self.assertIn("probe_fallback:probe_error", facts.signals)

    def test_find_macos_steam_api_in_bundle_plugins_directory(self):
        install_root = self.temp_root / "RimWorld"
        bundle_root = install_root / "RimWorldMac.app"
        macos_dir = bundle_root / "Contents" / "MacOS"
        plugin_dir = bundle_root / "Contents" / "PlugIns" / "steam_api.bundle" / "Contents" / "MacOS"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        macos_dir.mkdir(parents=True, exist_ok=True)
        (bundle_root / "steam_appid.txt").write_text("294100", encoding="utf-8")
        (bundle_root / "Contents" / "MacOS" / "RimWorldMac").write_text("", encoding="utf-8")
        target_lib = plugin_dir / "libsteam_api.dylib"
        target_lib.write_text("", encoding="utf-8")

        with patch("backend.managers.mgr_game_install.platform.system", return_value="Darwin"):
            facts = GameInstallInspector().quick_inspect(str(install_root))

        self.assertEqual(Path(facts.steam_api_path).resolve(), target_lib.resolve())
        self.assertEqual(Path(facts.steam_appid_path).resolve(), (bundle_root / "steam_appid.txt").resolve())
        self.assertTrue(facts.is_steam)
        self.assertIn("probe_fallback:probe_error", facts.signals)

    def test_quick_inspect_uncached_path_runs_full_inspect_and_persists_result(self):
        install_root = self.temp_root / "RimWorld"
        plugin_dir = install_root / "RimWorldWin64_Data" / "Plugins" / "x86_64"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (install_root / "RimWorldWin64.exe").write_text("", encoding="utf-8")
        (install_root / "steam_appid.txt").write_text("294100", encoding="utf-8")
        (plugin_dir / "steam_api64.dll").write_text("", encoding="utf-8")
        registry_path = self.temp_root / "known_game_installs.json"

        with patch("backend.managers.mgr_game_install.GameInstallRegistry", side_effect=lambda: GameInstallRegistry(registry_path)), \
             patch("backend.managers.mgr_game_install.platform.system", return_value="Windows"), \
             patch.object(GameInstallInspector, "_probe_official_steam_api", return_value="emulator") as probe_mock:
            facts = GameInstallInspector().quick_inspect(str(install_root))
            cached = GameInstallRegistry(registry_path).get(str(install_root))

        self.assertFalse(facts.is_steam)
        self.assertEqual(facts.steam_api_probe, "emulator")
        self.assertEqual(probe_mock.call_count, 1)
        self.assertIsNotNone(cached)
        self.assertFalse(cached.is_steam)

    def test_quick_inspect_uses_cached_result_without_reprobing(self):
        install_root = self.temp_root / "RimWorld"
        registry_path = self.temp_root / "known_game_installs.json"
        plugin_dir = install_root / "RimWorldWin64_Data" / "Plugins" / "x86_64"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (install_root / "RimWorldWin64.exe").write_text("", encoding="utf-8")
        (install_root / "steam_appid.txt").write_text("294100", encoding="utf-8")
        (plugin_dir / "steam_api64.dll").write_text("", encoding="utf-8")
        GameInstallRegistry(registry_path).set(
            GameInstallFacts(
                install_path=str(install_root),
                executable_path=str(install_root / "RimWorldWin64.exe"),
                game_version="1.6.0",
                is_steam=False,
                is_steam_managed=False,
                steam_api_path=str(plugin_dir / "steam_api64.dll"),
                steam_appid_path=str(install_root / "steam_appid.txt"),
                steam_api_probe="emulator",
                signals=["steam_api_emulator"],
                checked_at=123,
            )
        )

        with patch("backend.managers.mgr_game_install.GameInstallRegistry", side_effect=lambda: GameInstallRegistry(registry_path)), \
             patch("backend.managers.mgr_game_install.platform.system", return_value="Windows"), \
             patch.object(GameInstallInspector, "_probe_official_steam_api", side_effect=AssertionError("probe should not run")):
            facts = GameInstallInspector().quick_inspect(str(install_root))

        self.assertFalse(facts.is_steam)
        self.assertEqual(facts.steam_api_probe, "emulator")
        self.assertIn("known_install_cache", facts.signals)

    def test_inspector_init_prunes_invalid_cache_once_on_startup(self):
        registry_path = self.temp_root / "known_game_installs.json"
        registry_path.write_text(json.dumps({
            "installs": {
                "missing": {
                    "install_path": str(self.temp_root / "missing-install"),
                    "checked_at": 1,
                }
            }
        }), encoding="utf-8")

        with patch("backend.managers.mgr_game_install.GameInstallRegistry", side_effect=lambda: GameInstallRegistry(registry_path)):
            GameInstallInspector()

        self.assertEqual(json.loads(registry_path.read_text(encoding="utf-8")), {"installs": {}})


class TestGameManager(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)

    def test_auto_detect_paths_finds_linux_default_steam_install(self):
        fake_home = self.temp_root / "home"
        install_root = fake_home / ".local" / "share" / "Steam" / "steamapps" / "common" / "RimWorld"
        install_root.mkdir(parents=True, exist_ok=True)

        with patch("backend.managers.mgr_game.platform.system", return_value="Linux"), \
             patch("backend.managers.mgr_game.os.path.expanduser", return_value=str(fake_home)), \
             patch.object(GameManager, "_detect_userdata_path", return_value=""), \
             patch.object(GameManager, "detect_executable", return_value=str(install_root / "RimWorldLinux")):
            result = GameManager.auto_detect_paths()

        self.assertEqual(result["game_install_path"], str(install_root))

    def test_auto_detect_paths_finds_macos_default_steam_install(self):
        fake_home = self.temp_root / "home"
        install_root = fake_home / "Library" / "Application Support" / "Steam" / "steamapps" / "common" / "RimWorld"
        install_root.mkdir(parents=True, exist_ok=True)

        with patch("backend.managers.mgr_game.platform.system", return_value="Darwin"), \
             patch("backend.managers.mgr_game.os.path.expanduser", return_value=str(fake_home)), \
             patch.object(GameManager, "_detect_userdata_path", return_value=""), \
             patch.object(GameManager, "detect_executable", return_value=str(install_root / "RimWorldMac.app")):
            result = GameManager.auto_detect_paths()

        self.assertEqual(result["game_install_path"], str(install_root))


class TestSteamManagerPlatformGuards(unittest.TestCase):
    def test_read_windows_active_process_status_returns_default_when_winreg_unavailable(self):
        manager = SteamManager.__new__(SteamManager)

        with patch("backend.managers.mgr_steam.platform.system", return_value="Windows"), \
             patch("backend.managers.mgr_steam.winreg", None):
            result = SteamManager._read_windows_active_process_status(manager)

        self.assertEqual(result, {
            "pid": 0,
            "active_user": 0,
            "running": False,
            "logged_in": False,
        })

    def test_get_steam_path_returns_none_when_winreg_unavailable(self):
        manager = SteamManager.__new__(SteamManager)

        with patch("backend.managers.mgr_steam.platform.system", return_value="Windows"), \
             patch("backend.managers.mgr_steam.winreg", None):
            result = SteamManager.get_steam_path(manager)

        self.assertIsNone(result)


class TestAppUpgradeMigrations(unittest.TestCase):
    def test_migrate_profile_steam_runtime_flags_preserves_opt_out_and_workshop_when_detected_non_steam(self):
        profile = SimpleNamespace(
            id="profile-a",
            game_install_path="D:/Games/RimWorld",
            prefer_steam_launch=False,
            use_workshop_mods=True,
            is_steam=True,
        )
        updated_rows = []

        class _UpdateQuery:
            def __init__(self, payload):
                self.payload = payload

            def where(self, *_args, **_kwargs):
                return self

            def execute(self):
                updated_rows.append(self.payload)
                return 1

        result = AppUpgradeResult()
        with patch("backend.migrations.app_upgrade.settings.config", SimpleNamespace(steam_path="C:/Steam")), \
             patch("backend.migrations.app_upgrade.GameInstallInspector.inspect", return_value=SimpleNamespace(is_steam=False)), \
             patch("backend.migrations.app_upgrade.GameProfile.select", return_value=[profile]), \
             patch("backend.migrations.app_upgrade.GameProfile.update", side_effect=lambda **payload: _UpdateQuery(payload)), \
             patch("backend.migrations.app_upgrade.db.atomic", return_value=nullcontext()):
            _migrate_profile_steam_runtime_flags(result)

        self.assertEqual(len(updated_rows), 1)
        self.assertFalse(updated_rows[0]["is_steam"])
        self.assertFalse(updated_rows[0]["prefer_steam_launch"])
        self.assertTrue(updated_rows[0]["use_workshop_mods"])

    def test_migrate_profile_steam_runtime_flags_defaults_prefer_true_for_detected_steam(self):
        profile = SimpleNamespace(
            id="profile-a",
            game_install_path="D:/Games/RimWorld",
            prefer_steam_launch=None,
            use_workshop_mods=True,
            is_steam=False,
        )
        updated_rows = []

        class _UpdateQuery:
            def __init__(self, payload):
                self.payload = payload

            def where(self, *_args, **_kwargs):
                return self

            def execute(self):
                updated_rows.append(self.payload)
                return 1

        result = AppUpgradeResult()
        with patch("backend.migrations.app_upgrade.settings.config", SimpleNamespace(steam_path="C:/Steam")), \
             patch("backend.migrations.app_upgrade.GameInstallInspector.inspect", return_value=SimpleNamespace(is_steam=True)), \
             patch("backend.migrations.app_upgrade.GameProfile.select", return_value=[profile]), \
             patch("backend.migrations.app_upgrade.GameProfile.update", side_effect=lambda **payload: _UpdateQuery(payload)), \
             patch("backend.migrations.app_upgrade.db.atomic", return_value=nullcontext()):
            _migrate_profile_steam_runtime_flags(result)

        self.assertEqual(len(updated_rows), 1)
        self.assertTrue(updated_rows[0]["is_steam"])
        self.assertTrue(updated_rows[0]["prefer_steam_launch"])
        self.assertFalse(updated_rows[0]["use_workshop_mods"])


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
            prefer_steam_launch=False,
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

    def test_finish_scan_normalizes_terminal_payload(self):
        scanner = ModScanner(SimpleNamespace(profile_id="profile-a"))

        with patch("backend.scanner.mod_scanner.EventBus.emit") as emit:
            scanner._finish_scan({"status": "error", "message": "boom"}, "task-1")

        emit.assert_called_once()
        event_name, payload = emit.call_args.args
        self.assertEqual(event_name, "scan-complete")
        self.assertEqual(payload["task_id"], "task-1")
        self.assertEqual(payload["id"], "task-1")
        self.assertEqual(payload["type"], "scan")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["progress"], 0)
        self.assertEqual(payload["message"], "boom")
        self.assertEqual(payload["metrics"], {})

    def test_handle_interruption_emits_progress_and_standard_complete_payload(self):
        scanner = ModScanner(SimpleNamespace(profile_id="profile-a"))
        scanner._is_scanning = True

        with patch("backend.scanner.mod_scanner.EventBus.emit_progress") as emit_progress, \
             patch("backend.scanner.mod_scanner.EventBus.emit") as emit:
            scanner._handle_interruption("task-2")

        emit_progress.assert_called_once()
        emit.assert_called_once()
        event_name, payload = emit.call_args.args
        self.assertEqual(event_name, "scan-complete")
        self.assertEqual(payload["task_id"], "task-2")
        self.assertEqual(payload["status"], "cancelled")
        self.assertEqual(payload["type"], "scan")
        self.assertEqual(payload["id"], "task-2")
        self.assertEqual(payload["progress"], 0)


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
            prefer_steam_launch=False,
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
            prefer_steam_launch=False,
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

    def test_hard_conflict_defaults_to_no_deploy(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        install_dir = temp_root / "install"
        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(install_dir),
            user_data_path=str(temp_root / "userdata"),
            prefer_steam_launch=False,
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
        self.assertEqual(analysis["deploy_paths"], [])

    def test_prefer_steam_launch_includes_workshop_in_detection_but_not_deploy(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        install_dir = temp_root / "install"
        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(install_dir),
            user_data_path=str(temp_root / "userdata"),
            prefer_steam_launch=True,
            use_workshop_mods=False,
            use_self_mods=False,
            is_steam=True,
        )

        local_root = install_dir / "Mods"
        workshop_root = temp_root / "workshop"
        local_path = local_root / "Author.Mod"
        workshop_path = workshop_root / "123456"

        assets = [
            {
                "package_id": "Author.Mod",
                "path": str(local_path),
                "name": "Local Copy",
                "disabled": False,
            },
            {
                "package_id": "Author.Mod",
                "path": str(workshop_path),
                "name": "Workshop Copy",
                "disabled": False,
            },
        ]

        config = SimpleNamespace(
            workshop_mods_path=str(workshop_root),
            self_mods_path=str(temp_root / "selfmods"),
            enable_tool_mods=False,
        )
        with patch("backend.database.dao.settings.config", config):
            analysis = ModDAO.get_profile_conflict_analysis(context, assets=assets)

        self.assertEqual(analysis["hard_conflicts"], [])
        self.assertEqual(len(analysis["coexistences"]), 1)
        self.assertEqual(analysis["deploy_paths"], [])

    def test_get_profile_mods_attaches_workshop_coexist_variant(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        install_dir = temp_root / "install"
        context = ProfileContext(
            profile_id="profile-a",
            game_version="1.5.4100",
            game_install_path=str(install_dir),
            user_data_path=str(temp_root / "userdata"),
            prefer_steam_launch=False,
            use_workshop_mods=True,
            use_self_mods=False,
        )

        local_root = install_dir / "Mods"
        workshop_root = temp_root / "workshop"
        local_path = local_root / "Author.Mod"
        workshop_path = workshop_root / "123456"

        config = SimpleNamespace(
            workshop_mods_path=str(workshop_root),
            self_mods_path=str(temp_root / "selfmods"),
            enable_tool_mods=False,
        )
        assets = [
            {
                "package_id": "Author.Mod",
                "path": str(local_path),
                "name": "Local Copy",
                "disabled": False,
            },
            {
                "package_id": "Author.Mod",
                "path": str(workshop_path),
                "name": "Workshop Copy",
                "disabled": False,
            },
        ]

        with patch("backend.database.dao.settings.config", config), \
             patch("backend.database.dao._load_group_names_by_mod_id", return_value={}), \
             patch("backend.database.dao.ModAsset.select") as select_mock:
            select_mock.return_value.join.return_value.where.return_value.dicts.return_value = assets
            mods = ModDAO.get_profile_mods(context)

        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]["path"], str(local_path))
        self.assertTrue(mods[0]["is_coexistence"])
        self.assertEqual(mods[0]["coexist_workshop_variant"]["path"], str(workshop_path))


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


class TestApiGameLaunch(unittest.TestCase):
    def test_game_launch_prefers_steam_waits_until_ready_then_direct_launches_game(self):
        api = API.__new__(API)
        api._pending_launch_lock = threading.Lock()
        api._pending_launch_profile_id = ""
        api._pending_launch_deadline_ms = 0
        profile = SimpleNamespace(
            id="default",
            game_install_path="C:/Games/RimWorld",
            prefer_steam_launch=True,
            is_steam=True,
        )
        api.profile_mgr = SimpleNamespace(
            current_profile=profile,
            get_profile=Mock(return_value=profile),
            get_launch_args=Mock(return_value=["-savedatafolder=C:/Profiles/default"]),
        )
        api.steam_mgr = SimpleNamespace(
            get_steam_path=Mock(return_value="C:/Program Files (x86)/Steam"),
            get_steam_client_status=Mock(return_value={"running": False, "ready": False}),
        )
        api._ensure_steam_ready = Mock(return_value=(True, {"running": True, "ready": True, "reason": "ready"}, ""))
        api._launch_profile_with_runtime_links = Mock()
        api._resolve_profile_runtime_caps_from_profile = Mock(return_value={
            "steam_launch_enabled": True,
            "is_steam": True,
            "is_steam_managed": False,
        })

        config = SimpleNamespace(steam_path="C:/Program Files (x86)/Steam")
        with patch("backend.api.settings.config", config), \
             patch("backend.api.PathChecker.check_steam_path", return_value={"pass": True}):
            res = API.game_launch(api, "default")

        self.assertEqual(res["status"], "success")
        api._ensure_steam_ready.assert_called_once_with(timeout_seconds=45)
        api._launch_profile_with_runtime_links.assert_called_once_with(
            "default",
            "C:/Games/RimWorld",
            ["-savedatafolder=C:/Profiles/default"],
            include_workshop=False,
        )

    def test_game_launch_default_steam_profile_uses_url_fallback_when_steam_path_invalid(self):
        api = API.__new__(API)
        api._pending_launch_lock = threading.Lock()
        api._pending_launch_profile_id = ""
        api._pending_launch_deadline_ms = 0
        profile = SimpleNamespace(
            id="default",
            game_install_path="C:/Games/RimWorld",
            prefer_steam_launch=True,
            is_steam=True,
        )
        api.profile_mgr = SimpleNamespace(
            current_profile=profile,
            get_profile=Mock(return_value=profile),
            get_launch_args=Mock(return_value=[]),
        )
        api.steam_mgr = SimpleNamespace(
            get_steam_path=Mock(return_value=""),
            get_steam_client_status=Mock(return_value={"running": False, "ready": False}),
        )
        api._ensure_runtime_links_for_launch = Mock(return_value=True)
        api._resolve_profile_runtime_caps_from_profile = Mock(return_value={
            "steam_launch_enabled": True,
            "is_steam": True,
            "is_steam_managed": True,
        })

        config = SimpleNamespace(steam_path="")
        with patch("backend.api.settings.config", config), \
             patch("backend.api.PathChecker.check_steam_path", return_value={"pass": False}), \
             patch("backend.api.os.startfile") as startfile:
            res = API.game_launch(api, "default")

        self.assertEqual(res["status"], "warning")
        self.assertIn("URL 协议启动", res["message"])
        api._ensure_runtime_links_for_launch.assert_called_once_with("default", include_workshop=False)
        startfile.assert_called_once_with("steam://run/294100")

    def test_game_launch_returns_warning_when_steam_not_ready_for_direct_game_launch(self):
        api = API.__new__(API)
        profile = SimpleNamespace(
            id="default",
            game_install_path="C:/Games/RimWorld",
            prefer_steam_launch=True,
            is_steam=True,
        )
        api.profile_mgr = SimpleNamespace(
            current_profile=profile,
            get_profile=Mock(return_value=profile),
            get_launch_args=Mock(return_value=[]),
        )
        api.steam_mgr = SimpleNamespace(
            get_steam_path=Mock(return_value="C:/Program Files (x86)/Steam"),
            get_steam_client_status=Mock(return_value={"running": False, "ready": False}),
        )
        api._ensure_steam_ready = Mock(return_value=(
            False,
            {"running": True, "ready": False, "reason": "steam_ready_timeout"},
            "Steam 已尝试自动启动，但未能在限定时间内进入已登录可用状态。您可以继续改为游戏本体直启，或先确认 Steam 已登录后重试。",
        ))
        api._resolve_profile_runtime_caps_from_profile = Mock(return_value={
            "steam_launch_enabled": True,
            "is_steam": True,
            "is_steam_managed": False,
        })

        config = SimpleNamespace(steam_path="C:/Program Files (x86)/Steam")
        with patch("backend.api.settings.config", config), \
             patch("backend.api.PathChecker.check_steam_path", return_value={"pass": True}):
            res = API.game_launch(api, "default")

        self.assertEqual(res["status"], "warning")
        self.assertEqual(res["data"]["action"], "confirm_direct_launch")
        self.assertTrue(res["data"]["requires_fallback_confirm"])

    def test_profile_create_desktop_shortcut_returns_vdf_flow_warning_for_diff_install(self):
        api = API.__new__(API)
        profile = SimpleNamespace(
            id="profile-a",
            name="Profile A",
            game_install_path="D:/Games/RimWorld",
            user_data_path="D:/Profiles/profile-a",
            prefer_steam_launch=True,
            is_steam=True,
        )
        default_profile = SimpleNamespace(
            id="default",
            name="Default",
            game_install_path="C:/Steam/steamapps/common/RimWorld",
            user_data_path="C:/Profiles/default",
            prefer_steam_launch=True,
            is_steam=True,
        )
        api.profile_mgr = SimpleNamespace(
            get_profile=Mock(side_effect=lambda profile_id: default_profile if profile_id == "default" else profile),
            get_launch_args=Mock(return_value=["-savedatafolder=D:/Profiles/profile-a"]),
        )
        api.steam_mgr = SimpleNamespace(
            steam_exe="C:/Program Files (x86)/Steam/steam.exe",
            get_steam_path=Mock(return_value="C:/Program Files (x86)/Steam"),
            get_steam_client_status=Mock(return_value={"running": False, "ready": False}),
        )
        api.file_mgr = SimpleNamespace(
            create_profile_desktop_shortcut=Mock(),
            remove_existing_shortcut_variants=Mock(),
        )
        api._resolve_profile_runtime_caps_from_profile = Mock(return_value={
            "steam_launch_enabled": True,
            "is_steam": True,
            "is_steam_managed": False,
        })

        config = SimpleNamespace(steam_path="C:/Program Files (x86)/Steam")
        with patch("backend.api.settings.config", config), \
             patch("backend.api.PathChecker.check_install_path", return_value={"pass": True}), \
             patch("backend.api.PathChecker.check_normal_path", return_value={"pass": True}), \
             patch("backend.api.PathChecker.check_steam_path", return_value={"pass": True}):
            res = API.profile_create_desktop_shortcut(api, "profile-a")

        self.assertEqual(res["status"], "warning")
        self.assertEqual(res["data"]["shortcut_kind"], "steam_vdf_flow_required")
        self.assertEqual(res["data"]["launch_mode"], "Steam VDF")
        api.file_mgr.create_profile_desktop_shortcut.assert_not_called()

    def test_resolve_profile_runtime_caps_from_profile_uses_dynamic_managed_flag(self):
        api = API.__new__(API)
        profile = SimpleNamespace(
            id="profile-a",
            game_install_path="D:/Games/RimWorld",
            prefer_steam_launch=True,
            use_workshop_mods=True,
            is_steam=True,
        )
        with patch("backend.api.GameInstallInspector.quick_inspect", return_value=SimpleNamespace(is_steam_managed=False)):
            caps = API._resolve_profile_runtime_caps_from_profile(api, profile)

        self.assertTrue(caps["steam_launch_enabled"])
        self.assertFalse(caps["is_steam_managed"])
        self.assertFalse(caps["workshop_deploy_enabled"])


class TestApiRuntimeLinkSync(unittest.TestCase):
    def test_refresh_active_profile_context_after_update_light_updates_manager_contexts(self):
        api = API.__new__(API)
        refreshed_context = SimpleNamespace(profile_id="profile-a")
        api.profile_mgr = SimpleNamespace(activate_profile=Mock(return_value=refreshed_context))
        api._bootstrap_context = Mock()
        api.scanner = SimpleNamespace(context=None)
        api.load_order_mgr = SimpleNamespace(context=None)
        api.game_log_mgr = SimpleNamespace(context=None)
        api.sorter = SimpleNamespace(context=None, rule_mgr=SimpleNamespace(context=None))

        mode = API._refresh_active_profile_context_after_update(api, "profile-a", {"use_self_mods": True})

        self.assertEqual(mode, "light")
        api.profile_mgr.activate_profile.assert_called_once_with("profile-a")
        api._bootstrap_context.assert_not_called()
        self.assertIs(api.active_context, refreshed_context)
        self.assertIs(api.scanner.context, refreshed_context)
        self.assertIs(api.load_order_mgr.context, refreshed_context)
        self.assertIs(api.game_log_mgr.context, refreshed_context)
        self.assertIs(api.sorter.context, refreshed_context)
        self.assertIs(api.sorter.rule_mgr.context, refreshed_context)

    def test_refresh_active_profile_context_after_update_rebootstraps_for_path_changes(self):
        api = API.__new__(API)
        api.profile_mgr = SimpleNamespace(activate_profile=Mock())
        api._bootstrap_context = Mock()
        api.scanner = None
        api.load_order_mgr = None
        api.game_log_mgr = None
        api.sorter = None

        mode = API._refresh_active_profile_context_after_update(api, "profile-a", {"user_data_path": "D:/Profiles/A"})

        self.assertEqual(mode, "rebootstrap")
        api._bootstrap_context.assert_called_once_with("profile-a")
        api.profile_mgr.activate_profile.assert_not_called()

    def test_profile_update_current_profile_uses_refresh_helper_instead_of_profile_activate(self):
        api = API.__new__(API)
        api.profile_mgr = SimpleNamespace(update_profile=Mock())
        api._refresh_active_profile_context_after_update = Mock(side_effect=lambda *_args, **_kwargs: setattr(api, "active_context", SimpleNamespace(profile_id="profile-a")) or "light")
        api._sync_runtime_links_for_profile = Mock(return_value=True)
        api.profile_activate = Mock(side_effect=AssertionError("profile_activate should not be called"))

        with patch("backend.api.settings.config", SimpleNamespace(current_profile_id="profile-a")):
            res = API.profile_update(api, "profile-a", {"use_workshop_mods": True})

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["refresh_mode"], "light")
        api.profile_mgr.update_profile.assert_called_once_with("profile-a", {"use_workshop_mods": True})
        api._refresh_active_profile_context_after_update.assert_called_once_with("profile-a", {"use_workshop_mods": True})
        api._sync_runtime_links_for_profile.assert_called_once_with("profile-a", include_workshop=True)

    def test_sync_runtime_links_after_scan_only_runs_for_current_profile(self):
        api = API.__new__(API)
        api.active_context = SimpleNamespace(profile_id="profile-a")
        api._sync_runtime_links_for_profile = Mock(side_effect=lambda *_args, **_kwargs: setattr(api, "_last_runtime_link_sync_result", {"status": "deployed"}) or True)

        deploy_msg = API._sync_runtime_links_after_scan(api, "profile-a")
        stale_msg = API._sync_runtime_links_after_scan(api, "profile-b")

        self.assertEqual(deploy_msg, "Deployed runtime links")
        self.assertEqual(stale_msg, "Skipped runtime link sync for stale profile")
        api._sync_runtime_links_for_profile.assert_called_once_with("profile-a", include_workshop=True)

    def test_bootstrap_context_stops_old_scanner_and_injects_runtime_sync_handler(self):
        api = API.__new__(API)
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        old_scanner = Mock()
        old_log_mgr = Mock()
        context = SimpleNamespace(is_healthy=True, profile_id="profile-a")
        api.scanner = old_scanner
        api.game_log_mgr = old_log_mgr
        api.profile_mgr = SimpleNamespace(activate_profile=Mock(return_value=context))

        config = SimpleNamespace(self_mods_path=str(temp_root / "selfmods"))
        with patch("backend.api.settings.config", config), \
             patch("backend.api.ModScanner") as mock_scanner_cls, \
             patch("backend.api.LoadOrderManager"), \
             patch("backend.api.GameLogManager") as mock_log_mgr_cls, \
             patch("backend.api.OrderSorter"), \
             patch("backend.api.os.makedirs"):
            new_scanner = Mock()
            new_log_mgr = Mock()
            mock_scanner_cls.return_value = new_scanner
            mock_log_mgr_cls.return_value = new_log_mgr

            API._bootstrap_context(api, "profile-a")

        old_log_mgr.stop_realtime_monitor.assert_called_once_with()
        old_scanner.stop_scan.assert_called_once_with()
        old_scanner.wait_until_idle.assert_called_once_with(timeout=2.0)
        mock_scanner_cls.assert_called_once()
        self.assertIs(api.scanner, new_scanner)
        handler = mock_scanner_cls.call_args.kwargs["runtime_link_sync_handler"]
        self.assertIs(handler.__self__, api)
        self.assertIs(handler.__func__, API._sync_runtime_links_after_scan)
        new_log_mgr.start_realtime_monitor.assert_called_once_with()

    def test_profile_activate_reconciles_runtime_links_for_active_profile(self):
        api = API.__new__(API)
        current_profile = SimpleNamespace(id="profile-a", name="Profile A")

        def bootstrap(pid):
            api.active_context = SimpleNamespace(profile_id=pid)

        api._bootstrap_context = Mock(side_effect=bootstrap)
        api._sync_runtime_links_for_profile = Mock(return_value=True)
        api.profile_mgr = SimpleNamespace(get_current_profile=Mock(return_value=current_profile))

        with patch("backend.api.asdict", return_value={}), \
             patch("backend.api.ApiResponse.success", return_value={"status": "success"}) as mock_success:
            res = API.profile_activate(api, "profile-a")

        self.assertEqual(res["status"], "success")
        api._bootstrap_context.assert_called_once_with("profile-a")
        api._sync_runtime_links_for_profile.assert_called_once_with("profile-a", include_workshop=True)
        mock_success.assert_called_once()

    def test_sync_runtime_links_for_profile_skips_duplicate_fingerprint(self):
        api = API.__new__(API)
        api._runtime_link_sync_state = {}
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        local_mods_root = temp_root / "Mods"
        local_mods_root.mkdir(parents=True)
        context = SimpleNamespace(local_mods_path=str(local_mods_root))
        api.profile_mgr = SimpleNamespace(build_profile_context=Mock(return_value=context))
        api.file_mgr = SimpleNamespace(sync_managed_links=Mock(return_value=True))

        runtime_caps = {"workshop_detection_enabled": True, "workshop_deploy_enabled": True}
        runtime_analysis = {"deploy_paths": ["D:/mods/a", "D:/mods/b"]}
        with patch("backend.api.resolve_profile_runtime_capabilities", return_value=runtime_caps), \
             patch("backend.api.ModDAO.get_profile_conflict_analysis", return_value=runtime_analysis):
            first = API._sync_runtime_links_for_profile(api, "profile-a", include_workshop=True)
            second = API._sync_runtime_links_for_profile(api, "profile-a", include_workshop=True)

        self.assertTrue(first)
        self.assertTrue(second)
        api.file_mgr.sync_managed_links.assert_called_once_with(str(local_mods_root), runtime_analysis["deploy_paths"])

    def test_sync_runtime_links_for_profile_redeploys_when_mode_changes(self):
        api = API.__new__(API)
        api._runtime_link_sync_state = {}
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, ignore_errors=True)

        local_mods_root = temp_root / "Mods"
        local_mods_root.mkdir(parents=True)
        context = SimpleNamespace(local_mods_path=str(local_mods_root))
        api.profile_mgr = SimpleNamespace(build_profile_context=Mock(return_value=context))
        api.file_mgr = SimpleNamespace(sync_managed_links=Mock(return_value=True))

        runtime_caps = {"workshop_detection_enabled": True, "workshop_deploy_enabled": True}
        runtime_analysis = {"deploy_paths": ["D:/mods/a"]}
        with patch("backend.api.resolve_profile_runtime_capabilities", return_value=runtime_caps), \
             patch("backend.api.ModDAO.get_profile_conflict_analysis", return_value=runtime_analysis):
            first = API._sync_runtime_links_for_profile(api, "profile-a", include_workshop=True)
            second = API._sync_runtime_links_for_profile(api, "profile-a", include_workshop=False)

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(api.file_mgr.sync_managed_links.call_count, 2)

    def test_ensure_runtime_links_for_launch_skips_when_active_profile_state_matches(self):
        api = API.__new__(API)
        api.active_context = SimpleNamespace(profile_id="profile-a")
        api._runtime_link_sync_state = {
            "profile-a": {
                "profile_id": "profile-a",
                "local_mods_root": "c:/games/rimworld/mods",
                "include_workshop": False,
                "workshop_detection_enabled": True,
                "workshop_deploy_enabled": False,
                "deploy_paths": ("d:/mods/a",),
            }
        }
        api._sync_runtime_links_for_profile = Mock(return_value=True)

        result = API._ensure_runtime_links_for_launch(api, "profile-a", include_workshop=False)

        self.assertTrue(result)
        api._sync_runtime_links_for_profile.assert_not_called()
        self.assertEqual(api._last_runtime_link_sync_result["status"], "noop")

    def test_ensure_runtime_links_for_launch_reconciles_when_mode_differs(self):
        api = API.__new__(API)
        api.active_context = SimpleNamespace(profile_id="profile-a")
        api._runtime_link_sync_state = {
            "profile-a": {
                "profile_id": "profile-a",
                "local_mods_root": "c:/games/rimworld/mods",
                "include_workshop": True,
                "workshop_detection_enabled": True,
                "workshop_deploy_enabled": True,
                "deploy_paths": ("d:/mods/a",),
            }
        }
        api._sync_runtime_links_for_profile = Mock(return_value=True)

        result = API._ensure_runtime_links_for_launch(api, "profile-a", include_workshop=False)

        self.assertTrue(result)
        api._sync_runtime_links_for_profile.assert_called_once_with("profile-a", include_workshop=False)


if __name__ == "__main__":
    unittest.main()
