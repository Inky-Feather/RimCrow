import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.load_order.models import ParsedLoadOrderData
from backend.managers.mgr_load_order import LoadOrderManager


class TestLoadOrderManagerImportCheck(unittest.TestCase):
    def test_import_check_uses_visible_profile_mods_as_installed_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=False,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)
            parsed = ParsedLoadOrderData(
                format="modlist",
                list_name="Demo",
                package_ids=["author.package"],
                mod_names=["Demo Mod"],
                workshop_ids=["1234567890"],
            )
            visible_mods = [
                {
                    "package_id": "author.package",
                    "workshop_id": "1234567890",
                    "name": "Visible Mod",
                    "path": "X:/Visible/Mod",
                    "store": "workshop",
                }
            ]

            with patch("backend.managers.mgr_load_order.ModDAO.get_profile_mods", return_value=visible_mods) as get_profile_mods_mock, \
                 patch("backend.managers.mgr_load_order.ExtDAO.get_workshop_details_by_package_ids", return_value={}), \
                 patch("backend.managers.mgr_load_order.ExtDAO.get_workshop_details_by_workshop_ids", return_value={}), \
                 patch("backend.managers.mgr_load_order.build_import_check_report", return_value={"summary": {}, "items": []}) as build_report_mock:
                manager._build_import_check(parsed)

            get_profile_mods_mock.assert_called_once_with(context)
            self.assertEqual(build_report_mock.call_args.kwargs["installed_mods"], visible_mods)

    def test_build_entries_from_parsed_keeps_steam_token_and_collapses_local_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=False,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)
            parsed = ParsedLoadOrderData(
                format="modsconfig",
                list_name="Demo",
                package_ids=["author.steammod", "author.localmod"],
                package_tokens=["author.steammod_steam", "author.localmod_local"],
                mod_names=["Steam Mod", "Local Mod"],
                workshop_ids=["123", "0"],
            )

            result = manager._build_entries_from_parsed(parsed)

            self.assertEqual(result["active_mods"], ["author.steammod_steam", "author.localmod"])
            self.assertEqual(result["mods"][0]["package_token"], "author.steammod_steam")
            self.assertEqual(result["mods"][1]["package_token"], "author.localmod")

    def test_build_entries_from_parsed_rewrites_legacy_companion_and_dedupes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=False,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)
            parsed = ParsedLoadOrderData(
                format="modsconfig",
                list_name="Demo",
                package_ids=["ludeon.rimworld", "rmm.companion", "rimcrow.companion", "after.mod"],
            )

            result = manager._build_entries_from_parsed(parsed)

            self.assertEqual(result["active_mods"], ["ludeon.rimworld", "rimcrow.companion", "after.mod"])
            self.assertEqual(result["mods"][1]["package_id"], "rimcrow.companion")

    def test_build_entries_from_parsed_drops_stale_steam_token_when_no_coexist_workshop_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=True,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)
            parsed = ParsedLoadOrderData(
                format="modsconfig",
                list_name="Demo",
                package_ids=["author.steammod"],
                package_tokens=["author.steammod_steam"],
                mod_names=["Steam Mod"],
                workshop_ids=["123"],
            )
            visible_mods = [
                {
                    "package_id": "author.steammod",
                    "package_id_raw": "Author.SteamMod",
                    "name": "Local Winner",
                    "display_name": "Local Winner",
                    "workshop_id": "",
                    "url": "",
                }
            ]

            with patch.object(manager, "_get_visible_installed_mods", return_value=visible_mods), \
                 patch("backend.database.models.ModAsset.select") as select_mock, \
                 patch("backend.managers.mgr_load_order.ExtDAO.get_workshop_details_by_package_ids", return_value={}):
                select_mock.return_value.where.return_value.dicts.return_value = []
                result = manager._build_entries_from_parsed(parsed)

            self.assertEqual(result["active_mods"], ["author.steammod"])
            self.assertEqual(result["mods"][0]["package_token"], "author.steammod")

    def test_build_export_entries_strips_suffixes_for_non_modsconfig_exports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=False,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)

            with patch.object(manager, "_enrich_mod_entries", side_effect=lambda entries: entries):
                entries = manager._build_export_entries(
                    ["author.steammod_steam", "author.localmod_local"],
                    export_format="modlist",
                )

            self.assertEqual([entry["package_id"] for entry in entries], ["author.steammod", "author.localmod"])
            self.assertEqual([entry["package_token"] for entry in entries], ["author.steammod", "author.localmod"])
            self.assertEqual([entry["package_id_raw"] for entry in entries], ["author.steammod", "author.localmod"])

    def test_build_export_entries_rewrites_legacy_companion_to_current_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=False,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)

            with patch.object(manager, "_enrich_mod_entries", side_effect=lambda entries: entries):
                entries = manager._build_export_entries(["before.mod", "rmm.companion", "rimcrow.companion"])

            self.assertEqual([entry["package_id"] for entry in entries], ["before.mod", "rimcrow.companion"])


if __name__ == "__main__":
    unittest.main()
