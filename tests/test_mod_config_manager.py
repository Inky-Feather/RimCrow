import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.managers.mgr_mod_config import ModSettingsManager
from backend.managers.mgr_profile import ProfileContext


class TestModSettingsManager(unittest.TestCase):
    def _create_context(self, temp_dir: str) -> ProfileContext:
        game_dir = Path(temp_dir) / "game"
        user_dir = Path(temp_dir) / "user"
        game_dir.mkdir(parents=True, exist_ok=True)
        user_dir.mkdir(parents=True, exist_ok=True)
        context = ProfileContext(
            profile_id="default",
            game_version="1.5.4069",
            game_install_path=str(game_dir),
            user_data_path=str(user_dir),
            prefer_steam_launch=False,
            use_workshop_mods=True,
            use_self_mods=False,
        )
        context.ensure_directories()
        return context

    def _build_triple_domain_assets(self, *assets: dict) -> dict[str, list[dict]]:
        grouped = {"local": [], "self": [], "workshop": [], "missing": [], "unknown": []}
        for asset in assets:
            store = str(asset.get("store") or "").strip().lower()
            grouped[store if store in grouped else "unknown"].append(dict(asset))
        return grouped

    def _write_settings(self, path: Path, settings_class: str | None, content: str = "value") -> None:
        if settings_class is None:
            path.write_text(f"<settings>{content}</settings>", encoding="utf-8")
            return
        path.write_text(
            f'<SettingsBlock><ModSettings Class="{settings_class}">{content}</ModSettings></SettingsBlock>',
            encoding="utf-8",
        )

    def test_get_overview_groups_by_mod_then_settings_class_and_marks_active_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            local_file = config_dir / "Mod_LocalCopy_DemoSettings.xml"
            workshop_file = config_dir / "Mod_2876543210_DemoSettings.xml"
            self._write_settings(local_file, "Author.Demo.Settings", "local")
            self._write_settings(workshop_file, "Author.Demo.Settings", "workshop")

            visible_mod = {
                "package_id": "author.demo",
                "name": "Demo Mod",
                "path": str(Path(temp_dir) / "mods" / "LocalCopy"),
                "store": "local",
                "workshop_id": "",
                "coexist_workshop_variant": {
                    "package_id": "author.demo",
                    "name": "Demo Mod",
                    "path": str(Path(temp_dir) / "workshop" / "2876543210"),
                    "store": "workshop",
                    "workshop_id": "2876543210",
                },
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod, visible_mod["coexist_workshop_variant"]),
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["author.demo_steam"])

            self.assertEqual(overview["total_files"], 2)
            self.assertEqual(overview["matched_mod_count"], 1)
            self.assertEqual(overview["unknown_file_count"], 0)
            mod_group = overview["mod_groups"][0]
            self.assertEqual(mod_group["package_id"], "author.demo")
            self.assertEqual(mod_group["status"], "enabled")
            self.assertEqual(mod_group["setting_count"], 1)
            setting_group = mod_group["setting_groups"][0]
            self.assertEqual(setting_group["class"], "Author.Demo.Settings")
            self.assertEqual(setting_group["identity"], "class")
            self.assertTrue(setting_group["can_cover_active"])
            self.assertEqual(setting_group["active_file_path"], str(workshop_file.resolve()))
            self.assertEqual(
                [item["name"] for item in setting_group["files"]],
                ["Mod_2876543210_DemoSettings.xml", "Mod_LocalCopy_DemoSettings.xml"],
            )

    def test_get_overview_splits_same_mod_by_real_settings_class_not_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            same_name_local = config_dir / "Mod_LocalCopy_SameFileName.xml"
            same_name_workshop = config_dir / "Mod_1841354677_SameFileName.xml"
            other_file = config_dir / "Mod_1841354677_OtherName.xml"
            self._write_settings(same_name_local, "Alpha.Settings.Main", "local")
            self._write_settings(same_name_workshop, "Alpha.Settings.Main", "workshop")
            self._write_settings(other_file, "Alpha.Settings.Odyssey", "other")

            visible_mod = {
                "package_id": "alpha.biomes",
                "name": "Alpha Biomes",
                "path": str(Path(temp_dir) / "mods" / "LocalCopy"),
                "store": "local",
                "workshop_id": "",
                "coexist_workshop_variant": {
                    "package_id": "alpha.biomes",
                    "name": "Alpha Biomes",
                    "path": str(Path(temp_dir) / "workshop" / "1841354677"),
                    "store": "workshop",
                    "workshop_id": "1841354677",
                },
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod, visible_mod["coexist_workshop_variant"]),
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["alpha.biomes_steam"])

            setting_groups = overview["mod_groups"][0]["setting_groups"]
            self.assertEqual({group["class"] for group in setting_groups}, {"Alpha.Settings.Main", "Alpha.Settings.Odyssey"})
            main_group = next(group for group in setting_groups if group["class"] == "Alpha.Settings.Main")
            self.assertEqual(main_group["file_count"], 2)
            self.assertTrue(main_group["can_cover_active"])

    def test_get_overview_uses_filename_fallback_only_within_same_fallback_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            local_file = config_dir / "Mod_LocalCopy_DemoSettings.xml"
            workshop_file = config_dir / "Mod_2876543210_DemoSettings.xml"
            other_file = config_dir / "Mod_2876543210_OtherSettings.xml"
            self._write_settings(local_file, None, "local")
            self._write_settings(workshop_file, None, "workshop")
            self._write_settings(other_file, None, "other")

            visible_mod = {
                "package_id": "author.demo",
                "name": "Demo Mod",
                "path": str(Path(temp_dir) / "mods" / "LocalCopy"),
                "store": "local",
                "workshop_id": "",
                "coexist_workshop_variant": {
                    "package_id": "author.demo",
                    "name": "Demo Mod",
                    "path": str(Path(temp_dir) / "workshop" / "2876543210"),
                    "store": "workshop",
                    "workshop_id": "2876543210",
                },
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod, visible_mod["coexist_workshop_variant"]),
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["author.demo_steam"])

            setting_groups = overview["mod_groups"][0]["setting_groups"]
            self.assertEqual({group["fallback_name"] for group in setting_groups}, {"DemoSettings", "OtherSettings"})
            fallback_group = next(group for group in setting_groups if group["fallback_name"] == "DemoSettings")
            self.assertEqual(fallback_group["identity"], "filename")
            self.assertTrue(fallback_group["can_cover_active"])
            self.assertEqual(fallback_group["parse_status"], "missing_class")

    def test_settings_class_only_uses_root_settings_block_direct_mod_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            file_path = Path(context.game_config_path) / "Mod_LocalCopy_DemoSettings.xml"
            file_path.write_text(
                '<Root><SettingsBlock><ModSettings Class="Should.Not.Match" /></SettingsBlock></Root>',
                encoding="utf-8",
            )

            visible_mod = {
                "package_id": "author.demo",
                "name": "Demo Mod",
                "path": str(Path(temp_dir) / "mods" / "LocalCopy"),
                "store": "local",
                "workshop_id": "",
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod),
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["author.demo"])

            setting_group = overview["mod_groups"][0]["setting_groups"][0]
            self.assertEqual(setting_group["identity"], "filename")
            self.assertEqual(setting_group["class"], "")
            self.assertEqual(setting_group["fallback_name"], "DemoSettings")

    def test_unknown_mod_filename_guess_extracts_workshop_id_without_breaking_underscores(self):
        cases = [
            ("Mod_3520130671_NiceBillTabMod.xml", "3520130671", "NiceBillTabMod"),
            ("Mod_3231909012_Mod_CeilingUtilities.xml", "3231909012", "Mod_CeilingUtilities"),
            ("Mod__730936602__Achtung.xml", "730936602", "Achtung"),
            ("Mod_3526354009_Mod.xml", "3526354009", ""),
        ]
        for name, workshop_id, guessed_name in cases:
            with self.subTest(name=name):
                identity = ModSettingsManager._parse_file_identity(name)
                self.assertEqual(identity["workshop_id_guess"], workshop_id)
                self.assertEqual(identity["guessed_mod_name"], guessed_name)
                self.assertIn(identity["match_confidence"], {"medium", "low"})

    def test_unknown_workshop_files_are_grouped_as_uninstalled_cleanup_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            file_path = config_dir / "Mod__730936602__Achtung.xml"
            self._write_settings(file_path, "Achtung.Settings")

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[]),
                patch("backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets", return_value={}),
            ):
                overview = ModSettingsManager.get_overview(context, [])

            self.assertEqual(overview["unknown_file_count"], 1)
            self.assertEqual(overview["cleanup_candidate_paths"], [str(file_path.resolve())])
            mod_group = overview["mod_groups"][0]
            self.assertEqual(mod_group["status"], "uninstalled")
            self.assertEqual(mod_group["workshop_id"], "730936602")
            self.assertEqual(mod_group["mod_name"], "Achtung")

    def test_external_database_package_merges_file_into_installed_same_package_mod(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            file_path = config_dir / "Mod_3226502149_SettingsController.xml"
            self._write_settings(file_path, "CallTradeShips.Settings")

            visible_mod = {
                "package_id": "calltradeships.cavenaugh.rw",
                "name": "[KV] Call Trade Ships [1.6 Patched]",
                "path": str(Path(temp_dir) / "mods" / "CallTradeShipsLocal"),
                "store": "local",
                "workshop_id": "",
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod),
                ),
                patch(
                    "backend.managers.mgr_mod_config.ExtDAO.get_workshop_details_by_workshop_ids",
                    return_value={
                        "3226502149": {
                            "workshop_id": "3226502149",
                            "package_id": "calltradeships.cavenaugh.rw",
                            "name": "[KV] Call Trade Ships [1.6 Patched]",
                        }
                    },
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["calltradeships.cavenaugh.rw"])

            self.assertEqual(overview["unknown_file_count"], 0)
            mod_group = overview["mod_groups"][0]
            self.assertEqual(mod_group["status"], "enabled")
            self.assertEqual(mod_group["package_id"], "calltradeships.cavenaugh.rw")
            setting_group = mod_group["setting_groups"][0]
            self.assertEqual(setting_group["active_file_path"], "")
            self.assertEqual(setting_group["files"][0]["source_label"], "同包名")
            self.assertEqual(setting_group["files"][0]["folder_name"], "3226502149")

    def test_external_database_package_keeps_uninstalled_group_with_real_name_and_package_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            file_path = config_dir / "Mod_3226502149_SettingsController.xml"
            self._write_settings(file_path, "CallTradeShips.Settings")

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[]),
                patch("backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets", return_value={}),
                patch(
                    "backend.managers.mgr_mod_config.ExtDAO.get_workshop_details_by_workshop_ids",
                    return_value={
                        "3226502149": {
                            "workshop_id": "3226502149",
                            "package_id": "calltradeships.cavenaugh.rw",
                            "name": "[KV] Call Trade Ships [1.6 Patched]",
                        }
                    },
                ),
            ):
                overview = ModSettingsManager.get_overview(context, [])

            mod_group = overview["mod_groups"][0]
            self.assertEqual(mod_group["status"], "uninstalled")
            self.assertEqual(mod_group["package_id"], "calltradeships.cavenaugh.rw")
            self.assertEqual(mod_group["mod_name"], "[KV] Call Trade Ships [1.6 Patched]")
            self.assertEqual(mod_group["workshop_id"], "3226502149")
            self.assertEqual(overview["cleanup_candidate_paths"], [str(file_path.resolve())])

    def test_active_file_uses_visible_workshop_path_for_plain_active_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            active_file = config_dir / "Mod_730936602_Achtung.xml"
            self._write_settings(active_file, "Achtung.Settings", "workshop")

            visible_mod = {
                "package_id": "brrainz.achtung",
                "name": "Achtung!",
                "path": str(Path(temp_dir) / "workshop" / "730936602"),
                "store": "workshop",
                "workshop_id": "730936602",
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod),
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["brrainz.achtung"])

            mod_group = overview["mod_groups"][0]
            self.assertEqual(mod_group["status"], "enabled")
            setting_group = mod_group["setting_groups"][0]
            self.assertEqual(setting_group["active_file_path"], str(active_file.resolve()))
            self.assertTrue(setting_group["files"][0]["active"])

    def test_coexist_local_active_uses_effective_instance_folder_to_pick_active_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            standard_file = config_dir / "Mod_730936602_Achtung.xml"
            padded_file = config_dir / "Mod__730936602__Achtung.xml"
            self._write_settings(standard_file, "AchtungMod.AchtungSettings", "standard")
            self._write_settings(padded_file, "AchtungMod.AchtungSettings", "padded")

            visible_mod = {
                "package_id": "brrainz.achtung",
                "name": "Achtung!",
                "path": str(Path(temp_dir) / "mods" / "_730936602_"),
                "store": "local",
                "workshop_id": "",
                "coexist_workshop_variant": {
                    "package_id": "brrainz.achtung",
                    "name": "Achtung!",
                    "path": str(Path(temp_dir) / "workshop" / "730936602"),
                    "store": "workshop",
                    "workshop_id": "730936602",
                },
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod, visible_mod["coexist_workshop_variant"]),
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["brrainz.achtung"])

            mod_group = overview["mod_groups"][0]
            self.assertEqual(mod_group["status"], "enabled")
            self.assertTrue(mod_group["is_active_mod"])
            setting_group = mod_group["setting_groups"][0]
            self.assertEqual(setting_group["file_count"], 2)
            self.assertEqual(setting_group["active_file_path"], str(padded_file.resolve()))
            self.assertTrue(setting_group["can_cover_active"])
            self.assertEqual(
                [(item["name"], item["active"]) for item in setting_group["files"]],
                [("Mod__730936602__Achtung.xml", True), ("Mod_730936602_Achtung.xml", False)],
            )

    def test_active_file_prefers_exact_active_folder_pattern_when_duplicate_names_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            standard_file = config_dir / "Mod_730936602_Achtung.xml"
            padded_file = config_dir / "Mod__730936602__Achtung.xml"
            self._write_settings(standard_file, "Achtung.Settings", "standard")
            self._write_settings(padded_file, "Achtung.Settings", "padded")

            visible_mod = {
                "package_id": "brrainz.achtung",
                "name": "Achtung!",
                "path": str(Path(temp_dir) / "workshop" / "730936602"),
                "store": "workshop",
                "workshop_id": "730936602",
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod),
                ),
            ):
                overview = ModSettingsManager.get_overview(context, ["brrainz.achtung_steam"])

            setting_group = overview["mod_groups"][0]["setting_groups"][0]
            self.assertEqual(setting_group["file_count"], 2)
            self.assertEqual(setting_group["active_file_path"], str(standard_file.resolve()))
            self.assertEqual(
                [(item["name"], item["active"]) for item in setting_group["files"]],
                [("Mod_730936602_Achtung.xml", True), ("Mod__730936602__Achtung.xml", False)],
            )

    def test_sync_group_instance_copies_other_file_to_active_file_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            local_file = config_dir / "Mod_LocalCopy_DemoSettings.xml"
            workshop_file = config_dir / "Mod_2876543210_DemoSettings.xml"
            self._write_settings(local_file, "Author.Demo.Settings", "local-old")
            self._write_settings(workshop_file, "Author.Demo.Settings", "workshop-new")

            visible_mod = {
                "package_id": "author.demo",
                "name": "Demo Mod",
                "path": str(Path(temp_dir) / "mods" / "LocalCopy"),
                "store": "local",
                "workshop_id": "",
                "coexist_workshop_variant": {
                    "package_id": "author.demo",
                    "name": "Demo Mod",
                    "path": str(Path(temp_dir) / "workshop" / "2876543210"),
                    "store": "workshop",
                    "workshop_id": "2876543210",
                },
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod, visible_mod["coexist_workshop_variant"]),
                ),
            ):
                result = ModSettingsManager.sync_group_instance(context, ["author.demo_steam"], str(local_file), str(workshop_file))

            self.assertEqual(local_file.read_text(encoding="utf-8").count("local-old"), 1)
            self.assertEqual(workshop_file.read_text(encoding="utf-8"), local_file.read_text(encoding="utf-8"))
            self.assertEqual(result["class"], "Author.Demo.Settings")

    def test_sync_group_instance_rejects_overwriting_non_active_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            local_file = config_dir / "Mod_LocalCopy_DemoSettings.xml"
            workshop_file = config_dir / "Mod_2876543210_DemoSettings.xml"
            self._write_settings(local_file, "Author.Demo.Settings", "local")
            self._write_settings(workshop_file, "Author.Demo.Settings", "workshop")

            visible_mod = {
                "package_id": "author.demo",
                "name": "Demo Mod",
                "path": str(Path(temp_dir) / "mods" / "LocalCopy"),
                "store": "local",
                "workshop_id": "",
                "coexist_workshop_variant": {
                    "package_id": "author.demo",
                    "name": "Demo Mod",
                    "path": str(Path(temp_dir) / "workshop" / "2876543210"),
                    "store": "workshop",
                    "workshop_id": "2876543210",
                },
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=[visible_mod]),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(visible_mod, visible_mod["coexist_workshop_variant"]),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "目标文件不是当前激活配置"):
                    ModSettingsManager.sync_group_instance(context, ["author.demo_steam"], str(workshop_file), str(local_file))


if __name__ == "__main__":
    unittest.main()
