import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.managers.mgr_mod_residue import ModResidueManager


class TestModResidueManager(unittest.TestCase):
    def _patch_whitelist_path(self, temp_root: Path):
        return patch("backend.managers.mgr_mod_residue.MOD_RESIDUE_WHITELIST_PATH", temp_root / "mod_residue_whitelist.json")

    def test_scan_residue_directories_skips_valid_mods_and_tries_all_workshop_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            mods_root = temp_root / "Mods"
            mods_root.mkdir()
            residue_dir = mods_root / "Mod_1111111_2222222"
            residue_dir.mkdir()
            (residue_dir / "Textures").mkdir()
            (residue_dir / "Textures" / "a.png").write_bytes(b"1234")

            valid_mod = mods_root / "ValidMod"
            (valid_mod / "About").mkdir(parents=True)
            (valid_mod / "About" / "About.xml").write_text("<ModMetaData />", encoding="utf-8")

            with self._patch_whitelist_path(temp_root), \
                patch("backend.managers.mgr_mod_residue.SteamWebAPI.get_workshop_details", return_value={
                    "2222222": {
                        "workshop_id": "2222222",
                        "package_id": "author.resolved",
                        "title": "Resolved Mod",
                        "name": "Cached Name",
                        "preview_url": "https://example.test/preview.png",
                        "available": True,
                    }
                }):
                overview = ModResidueManager.get_overview([str(mods_root)])

            self.assertEqual(overview["summary"]["directory_count"], 1)
            self.assertEqual(overview["summary"]["item_count"], 1)
            group = overview["groups"][0]
            self.assertEqual(group["workshop_id"], "2222222")
            self.assertEqual(group["package_id"], "author.resolved")
            self.assertEqual(group["mod_name"], "Resolved Mod")
            self.assertEqual(group["items"][0]["file_count"], 1)
            self.assertEqual(group["items"][0]["total_size"], 4)

    def test_whitelist_skips_directory_residue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            mods_root = temp_root / "Mods"
            residue_dir = mods_root / "UnknownResidue"
            residue_dir.mkdir(parents=True)
            (residue_dir / "leftover.txt").write_text("x", encoding="utf-8")

            with self._patch_whitelist_path(temp_root), \
                patch("backend.managers.mgr_mod_residue.SteamWebAPI.get_workshop_details", return_value={}):
                ModResidueManager.add_whitelist_paths([str(residue_dir)])
                overview = ModResidueManager.get_overview([str(mods_root)])

            self.assertEqual(overview["summary"]["directory_count"], 0)
            self.assertEqual(overview["summary"]["item_count"], 0)
            self.assertEqual(overview["summary"]["whitelist_count"], 1)

    def test_whitelist_skips_settings_file_residue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            mods_root = temp_root / "Mods"
            mods_root.mkdir()
            settings_file = temp_root / "Config" / "Mod_Unknown_Settings.xml"
            settings_file.parent.mkdir()
            settings_file.write_text("<SettingsBlock />", encoding="utf-8")

            fake_settings_overview = {
                "mod_groups": [
                    {
                        "group_key": "unknown:file:unknown",
                        "status": "unknown",
                        "package_id": "",
                        "mod_name": "Unknown Settings",
                        "workshop_id": "",
                        "match_confidence": "unknown",
                        "setting_groups": [
                            {
                                "files": [
                                    {
                                        "file_path": str(settings_file),
                                        "name": settings_file.name,
                                        "folder_name": "Unknown",
                                        "file_size": settings_file.stat().st_size,
                                        "modified_time": 456,
                                        "source_label": "未知",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }

            with self._patch_whitelist_path(temp_root), \
                patch("backend.managers.mgr_mod_residue.ModSettingsManager.get_overview", return_value=fake_settings_overview), \
                patch("backend.managers.mgr_mod_residue.SteamWebAPI.get_workshop_details", return_value={}):
                added = ModResidueManager.add_whitelist_paths([str(settings_file)])
                overview = ModResidueManager.get_overview([str(mods_root)], context=object())

            self.assertEqual(added["whitelist"][0]["type"], "file")
            self.assertEqual(overview["summary"]["settings_file_count"], 0)
            self.assertEqual(overview["summary"]["item_count"], 0)
            self.assertEqual(overview["summary"]["whitelist_count"], 1)

    def test_settings_residue_associates_with_matching_folder_residue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            mods_root = temp_root / "Mods"
            residue_dir = mods_root / "FooResidue"
            residue_dir.mkdir(parents=True)
            settings_file = temp_root / "Config" / "Mod_FooResidue_Settings.xml"
            settings_file.parent.mkdir()
            settings_file.write_text("<SettingsBlock />", encoding="utf-8")

            fake_settings_overview = {
                "mod_groups": [
                    {
                        "group_key": "unknown:file:fooresidue",
                        "status": "unknown",
                        "package_id": "",
                        "mod_name": "Foo Residue",
                        "workshop_id": "",
                        "match_confidence": "low",
                        "setting_groups": [
                            {
                                "files": [
                                    {
                                        "file_path": str(settings_file),
                                        "name": settings_file.name,
                                        "folder_name": "FooResidue",
                                        "file_size": settings_file.stat().st_size,
                                        "modified_time": 123,
                                        "source_label": "未知",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }

            with self._patch_whitelist_path(temp_root), \
                patch("backend.managers.mgr_mod_residue.ModSettingsManager.get_overview", return_value=fake_settings_overview), \
                patch("backend.managers.mgr_mod_residue.SteamWebAPI.get_workshop_details", return_value={}):
                overview = ModResidueManager.get_overview([str(mods_root)], context=object())

            self.assertEqual(overview["summary"]["group_count"], 1)
            self.assertEqual(overview["summary"]["directory_count"], 1)
            self.assertEqual(overview["summary"]["settings_file_count"], 1)
            item_types = {item["type"] for item in overview["groups"][0]["items"]}
            self.assertEqual(item_types, {"directory", "settings_file"})


if __name__ == "__main__":
    unittest.main()
