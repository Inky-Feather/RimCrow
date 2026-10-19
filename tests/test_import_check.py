import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.load_order.import_check import build_import_check_report
from backend.load_order.models import ParsedLoadOrderData
from backend.managers.mgr_load_order import LoadOrderManager


class TestImportCheckReport(unittest.TestCase):
    def test_invalid_import_workshop_id_falls_back_to_database_and_counts_as_package_match(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["brrainz.harmony"],
            mod_names=["Harmony"],
            workshop_ids=["0"],
        )
        installed_mods = [
            {
                "package_id": "brrainz.harmony",
                "workshop_id": "2009463077",
                "name": "Harmony",
                "path": "X:/Mods/Harmony",
                "store": "workshop",
            }
        ]
        details = {
            "brrainz.harmony": {
                "workshop_id": "2009463077",
                "name": "Harmony",
            }
        }

        report = build_import_check_report(parsed, installed_mods, details_by_package_id=details)
        item = report["items"][0]
        self.assertEqual(item["status"], "package_match")
        self.assertEqual(item["resolved_workshop_id"], "2009463077")
        self.assertEqual(item["resolved_from"], "external_db")

    def test_different_workshop_id_without_replacement_is_other_version(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["author.samepackage"],
            mod_names=["Some Mod"],
            workshop_ids=["1111111111"],
        )
        installed_mods = [
            {
                "package_id": "author.samepackage",
                "workshop_id": "2222222222",
                "name": "Some Mod Local",
                "path": "X:/Mods/SomeMod",
                "store": "workshop",
            }
        ]

        report = build_import_check_report(parsed, installed_mods)
        item = report["items"][0]
        self.assertEqual(item["status"], "other_version")
        self.assertEqual(item["target_workshop_id"], "1111111111")

    def test_replacement_match_is_classified_separately(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["legacy.mod"],
            mod_names=["Legacy Mod"],
            workshop_ids=["1111111111"],
        )
        installed_mods = [
            {
                "package_id": "legacy.mod",
                "workshop_id": "3333333333",
                "name": "Replacement Mod",
                "path": "X:/Mods/Replacement",
                "store": "workshop",
            }
        ]
        replacements_by_wid = {
            "1111111111": {
                "old_workshop_id": "1111111111",
                "old_package_id": "legacy.mod",
                "new_workshop_id": "3333333333",
                "new_name": "Replacement Mod",
                "new_versions": [],
            }
        }

        report = build_import_check_report(parsed, installed_mods, replacements_by_old_workshop_id=replacements_by_wid)
        item = report["items"][0]
        self.assertEqual(item["status"], "replacement")
        self.assertEqual(item["resolved_workshop_id"], "3333333333")

    def test_missing_item_with_resolved_workshop_id_is_missing(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["missing.mod"],
            mod_names=["Missing Mod"],
            workshop_ids=["0"],
        )
        details = {
            "missing.mod": {
                "workshop_id": "4444444444",
                "name": "Missing Mod",
            }
        }

        report = build_import_check_report(parsed, installed_mods=[], details_by_package_id=details)
        item = report["items"][0]
        self.assertEqual(item["status"], "missing")
        self.assertEqual(item["target_workshop_id"], "4444444444")

    def test_item_without_any_resolvable_workshop_id_is_unknown(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["unknown.mod"],
            mod_names=["Unknown Mod"],
            workshop_ids=["0"],
        )

        report = build_import_check_report(parsed, installed_mods=[])
        item = report["items"][0]
        self.assertEqual(item["status"], "unknown")
        self.assertEqual(item["target_workshop_id"], "")

    def test_missing_item_uses_install_source_fallback_for_git_url(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["git.only"],
            mod_names=["Git Only"],
            workshop_ids=["0"],
        )
        install_sources = {
            "git.only": {
                "original_sources": [
                    {
                        "package_id": "git.only",
                        "url": "https://gitgud.io/team/git-only",
                        "name": "Git Only",
                        "source_origin": "git_catalog",
                    }
                ],
                "replacement_sources": [],
            }
        }

        report = build_import_check_report(parsed, installed_mods=[], install_sources_by_package_id=install_sources)
        item = report["items"][0]

        self.assertEqual(item["status"], "missing")
        self.assertEqual(item["target_workshop_id"], "")
        self.assertEqual(item["target_source"]["kind"], "url")
        self.assertEqual(item["target_source"]["source_origin"], "git_catalog")

    def test_missing_item_uses_install_source_fallback_for_catalog_workshop_url(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["catalog.workshop"],
            mod_names=["Catalog Workshop"],
            workshop_ids=["0"],
        )
        install_sources = {
            "catalog.workshop": {
                "original_sources": [
                    {
                        "package_id": "catalog.workshop",
                        "workshop_id": "7777777777",
                        "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=7777777777",
                        "name": "Catalog Workshop",
                        "source_origin": "git_catalog",
                    }
                ],
                "replacement_sources": [],
            }
        }

        report = build_import_check_report(parsed, installed_mods=[], install_sources_by_package_id=install_sources)
        item = report["items"][0]

        self.assertEqual(item["status"], "missing")
        self.assertEqual(item["target_workshop_id"], "7777777777")
        self.assertEqual(item["target_source"]["kind"], "workshop")
        self.assertEqual(item["resolved_from"], "install_source")

    def test_valid_workshop_id_match_prevents_false_missing_even_when_package_id_differs(self):
        parsed = ParsedLoadOrderData(
            format="modlist",
            list_name="Demo",
            package_ids=["legacy.alias.package"],
            mod_names=[""],
            workshop_ids=["5555555555"],
        )
        installed_mods = [
            {
                "package_id": "actual.package.id",
                "workshop_id": "5555555555",
                "name": "Installed Mod",
                "path": "X:/Mods/Installed",
                "store": "workshop",
            }
        ]

        report = build_import_check_report(parsed, installed_mods=installed_mods)
        item = report["items"][0]
        self.assertEqual(item["status"], "exact_match")
        self.assertIn("Workshop ID", item["warning"])

    def test_workshop_only_import_uses_reverse_lookup_package_label(self):
        parsed = ParsedLoadOrderData(
            format="workshop_ids",
            list_name="Demo",
            package_ids=[],
            mod_names=[],
            workshop_ids=["6666666666"],
        )
        details_by_workshop_id = {
            "6666666666": {
                "workshop_id": "6666666666",
                "package_id": "author.packageid",
                "name": "Readable Name",
            }
        }

        report = build_import_check_report(
            parsed,
            installed_mods=[],
            details_by_workshop_id=details_by_workshop_id,
        )
        item = report["items"][0]
        self.assertEqual(item["status"], "missing")
        self.assertEqual(item["name"], "<author.packageid>")


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
                 patch("backend.managers.mgr_load_order.ExtDAO.get_install_sources_by_package_ids", return_value={"author.package": {"original_sources": []}}), \
                 patch("backend.managers.mgr_load_order.ExtDAO.get_workshop_details_by_workshop_ids", return_value={}), \
                 patch("backend.managers.mgr_load_order.build_import_check_report", return_value={"summary": {}, "items": []}) as build_report_mock:
                manager._build_import_check(parsed)

            get_profile_mods_mock.assert_called_once_with(context)
            self.assertEqual(build_report_mock.call_args.kwargs["installed_mods"], visible_mods)
            self.assertEqual(build_report_mock.call_args.kwargs["install_sources_by_package_id"], {"author.package": {"original_sources": []}})

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

    def test_build_export_entries_uses_coexist_workshop_metadata_for_steam_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = SimpleNamespace(
                is_healthy=True,
                backup_dir=str(Path(temp_dir) / "backups"),
                game_config_path=str(Path(temp_dir) / "config"),
                game_version="1.5.4069",
            )
            manager = LoadOrderManager(context)
            visible_mods = [
                {
                    "package_id": "author.steammod",
                    "package_id_raw": "Author.SteamMod",
                    "name": "Local Winner",
                    "display_name": "Local Winner",
                    "workshop_id": "111",
                    "url": "https://local.example/mod",
                    "coexist_workshop_variant": {
                        "package_id": "author.steammod",
                        "package_id_raw": "Author.SteamMod.Workshop",
                        "name": "Workshop Winner",
                        "display_name": "Workshop Winner",
                        "workshop_id": "222",
                        "url": "https://steamcommunity.com/sharedfiles/filedetails/?id=222",
                    },
                }
            ]

            with patch.object(manager, "_get_visible_installed_mods", return_value=visible_mods), \
                 patch("backend.database.models.ModAsset.select") as select_mock, \
                 patch("backend.managers.mgr_load_order.ExtDAO.get_workshop_details_by_package_ids", return_value={}):
                select_mock.return_value.where.return_value.dicts.return_value = []
                entries = manager._build_export_entries(["author.steammod_steam"], export_format="rml")

            self.assertEqual(entries[0]["export_package_id"], "author.steammod_steam")
            self.assertEqual(entries[0]["package_id_raw"], "Author.SteamMod.Workshop")
            self.assertEqual(entries[0]["name"], "Workshop Winner")
            self.assertEqual(entries[0]["workshop_id"], "222")
            self.assertEqual(entries[0]["source_url"], "https://steamcommunity.com/sharedfiles/filedetails/?id=222")

    def test_build_export_entries_preserves_suffixes_for_non_modsconfig_exports(self):
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
            self.assertEqual([entry["package_token"] for entry in entries], ["author.steammod_steam", "author.localmod"])
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
