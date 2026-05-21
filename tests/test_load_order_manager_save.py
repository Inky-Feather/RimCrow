import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_profile import ProfileContext


class TestLoadOrderManagerSave(unittest.TestCase):
    def _create_context(self, temp_dir: str) -> ProfileContext:
        game_dir = Path(temp_dir) / "game"
        user_dir = Path(temp_dir) / "user"
        game_dir.mkdir(parents=True, exist_ok=True)
        user_dir.mkdir(parents=True, exist_ok=True)
        context = ProfileContext(
            profile_id="test-profile",
            game_version="1.5.4069",
            game_install_path=str(game_dir),
            user_data_path=str(user_dir),
            prefer_steam_launch=False,
            use_workshop_mods=True,
            use_self_mods=False,
        )
        context.ensure_directories()
        return context

    def test_save_active_mods_rebuilds_empty_modsconfig_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            mods_config = Path(context.mods_config_file)
            mods_config.write_text("", encoding="utf-8")
            manager = LoadOrderManager(context)

            entries = [
                {"package_id": "ludeon.rimworld", "package_token": "ludeon.rimworld"},
                {"package_id": "brrainz.harmony", "package_token": "brrainz.harmony"},
            ]

            with patch.object(manager, "_build_export_entries", return_value=entries), \
                 patch.object(manager, "_write_rml_file"):
                result = manager.save_active_mods(["ludeon.rimworld", "brrainz.harmony"], is_dirty=False)

            self.assertTrue(result)
            content = mods_config.read_text(encoding="utf-8")
            self.assertIn("<ModsConfigData>", content)
            self.assertIn("<li>ludeon.rimworld</li>", content)
            self.assertIn("<li>brrainz.harmony</li>", content)

    def test_save_active_mods_backs_up_broken_modsconfig_before_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            mods_config = Path(context.mods_config_file)
            broken_content = "<ModsConfigData>"
            mods_config.write_text(broken_content, encoding="utf-8")
            manager = LoadOrderManager(context)
            before_files = set(Path(manager.other_dir).glob("ModsConfig_broken_*.xml"))

            entries = [
                {"package_id": "ludeon.rimworld", "package_token": "ludeon.rimworld"},
            ]

            with patch.object(manager, "_build_export_entries", return_value=entries), \
                 patch.object(manager, "_write_rml_file"):
                result = manager.save_active_mods(["ludeon.rimworld"], is_dirty=False)

            self.assertTrue(result)
            after_files = set(Path(manager.other_dir).glob("ModsConfig_broken_*.xml"))
            new_files = list(after_files - before_files)
            self.assertEqual(len(new_files), 1)
            self.assertEqual(new_files[0].read_text(encoding="utf-8"), broken_content)
            self.assertIn("<li>ludeon.rimworld</li>", mods_config.read_text(encoding="utf-8"))

    def test_save_active_mods_preserves_known_expansions_when_existing_xml_is_valid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            mods_config = Path(context.mods_config_file)
            mods_config.write_text(
                """<?xml version="1.0" encoding="utf-8"?>
<ModsConfigData>
  <version>1.5.4069</version>
  <activeMods>
    <li>old.mod</li>
  </activeMods>
  <knownExpansions>
    <li>ludeon.rimworld.royalty</li>
  </knownExpansions>
</ModsConfigData>""",
                encoding="utf-8",
            )
            manager = LoadOrderManager(context)

            entries = [
                {"package_id": "ludeon.rimworld", "package_token": "ludeon.rimworld"},
            ]

            with patch.object(manager, "_build_export_entries", return_value=entries), \
                 patch.object(manager, "_write_rml_file"):
                result = manager.save_active_mods(["ludeon.rimworld"], is_dirty=False)

            self.assertTrue(result)
            content = mods_config.read_text(encoding="utf-8")
            self.assertIn("<knownExpansions>", content)
            self.assertIn("<li>ludeon.rimworld.royalty</li>", content)
            self.assertIn("<li>ludeon.rimworld</li>", content)
            self.assertNotIn("<li>old.mod</li>", content)


if __name__ == "__main__":
    unittest.main()
