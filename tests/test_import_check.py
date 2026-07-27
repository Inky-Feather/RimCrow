import unittest

from backend.load_order.import_check import build_import_check_report
from backend.load_order.models import ParsedLoadOrderData


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


if __name__ == "__main__":
    unittest.main()
