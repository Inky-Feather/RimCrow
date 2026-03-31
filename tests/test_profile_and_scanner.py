import shutil
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.managers.mgr_profile import ProfileContext, ProfileManager
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


if __name__ == "__main__":
    unittest.main()
