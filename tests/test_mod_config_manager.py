import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.managers.mgr_mod_config import ModConfigManager
from backend.managers.mgr_profile import ProfileContext


class TestModConfigManager(unittest.TestCase):
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

    def test_get_overview_groups_instances_by_package_and_marks_active_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            local_file = config_dir / "Mod_LocalCopy_DemoSettings.xml"
            workshop_file = config_dir / "Mod_2876543210_DemoSettings.xml"
            orphan_file = config_dir / "Mod_MissingMod_OldSettings.xml"
            local_file.write_text("<settings>local</settings>", encoding="utf-8")
            workshop_file.write_text("<settings>workshop</settings>", encoding="utf-8")
            orphan_file.write_text("<settings>orphan</settings>", encoding="utf-8")

            visible_mods = [
                {
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
            ]

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=visible_mods),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(
                        visible_mods[0],
                        visible_mods[0]["coexist_workshop_variant"],
                    ),
                ),
            ):
                overview = ModConfigManager.get_overview(context, ["author.demo_steam"])

            self.assertEqual(overview["total_files"], 3)
            self.assertEqual(overview["matched_group_count"], 1)
            self.assertEqual(overview["orphan_file_count"], 1)
            self.assertEqual(len(overview["groups"]), 2)

            matched_group = overview["groups"][0]
            self.assertEqual(matched_group["package_id"], "author.demo")
            self.assertTrue(matched_group["is_active_group"])
            self.assertTrue(matched_group["can_sync"])
            self.assertEqual(matched_group["instance_count"], 2)
            self.assertEqual(matched_group["instances"][0]["file_name"], "Mod_2876543210_DemoSettings.xml")
            self.assertTrue(matched_group["instances"][0]["is_active_instance"])
            self.assertEqual(matched_group["instances"][0]["source_kind"], "workshop")
            self.assertEqual(matched_group["instances"][1]["file_name"], "Mod_LocalCopy_DemoSettings.xml")
            self.assertFalse(matched_group["instances"][1]["is_active_instance"])
            self.assertEqual(matched_group["instances"][1]["source_kind"], "local")

            orphan_group = overview["groups"][1]
            self.assertEqual(orphan_group["status"], "orphan")
            self.assertEqual(orphan_group["mod_name"], "未识别模组")
            self.assertFalse(orphan_group["can_sync"])

    def test_get_overview_splits_same_package_by_settings_class_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            files = [
                config_dir / "Mod_LocalCopy_AlphaBiomes_Mod.xml",
                config_dir / "Mod_1841354677_AlphaBiomes_Mod.xml",
                config_dir / "Mod_LocalCopy_AlphaBiomes_Mod_Odyssey.xml",
                config_dir / "Mod_1841354677_AlphaBiomes_Mod_Odyssey.xml",
            ]
            for item in files:
                item.write_text("<settings />", encoding="utf-8")

            visible_mods = [
                {
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
            ]

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=visible_mods),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(
                        visible_mods[0],
                        visible_mods[0]["coexist_workshop_variant"],
                    ),
                ),
            ):
                overview = ModConfigManager.get_overview(context, ["alpha.biomes_steam"])

            matched_groups = [group for group in overview["groups"] if group["status"] == "matched"]
            self.assertEqual(len(matched_groups), 2)
            self.assertEqual(
                {group["settings_class_name"] for group in matched_groups},
                {"AlphaBiomes_Mod", "AlphaBiomes_Mod_Odyssey"},
            )
            self.assertTrue(all(group["can_sync"] for group in matched_groups))
            self.assertTrue(all(group["instance_count"] == 2 for group in matched_groups))
            self.assertEqual(
                {item["file_name"] for item in matched_groups[0]["instances"]} |
                {item["file_name"] for item in matched_groups[1]["instances"]},
                {path.name for path in files},
            )

    def test_get_overview_keeps_all_real_instances_in_same_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            files = [
                config_dir / "Mod_LocalCopy_DemoSettings.xml",
                config_dir / "Mod_SelfCopy_DemoSettings.xml",
                config_dir / "Mod_2876543210_DemoSettings.xml",
            ]
            for index, item in enumerate(files, start=1):
                item.write_text(f"<settings>{index}</settings>", encoding="utf-8")

            visible_mods = [
                {
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
            ]
            triple_domain_assets = {
                "local": [{
                    "package_id": "author.demo",
                    "name": "Demo Mod",
                    "path": str(Path(temp_dir) / "mods" / "LocalCopy"),
                    "store": "local",
                    "workshop_id": "",
                }],
                "self": [{
                    "package_id": "author.demo",
                    "name": "Demo Mod",
                    "path": str(Path(temp_dir) / "self_mods" / "SelfCopy"),
                    "store": "self",
                    "workshop_id": "",
                }],
                "workshop": [{
                    "package_id": "author.demo",
                    "name": "Demo Mod",
                    "path": str(Path(temp_dir) / "workshop" / "2876543210"),
                    "store": "workshop",
                    "workshop_id": "2876543210",
                }],
                "missing": [],
                "unknown": [],
            }

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=visible_mods),
                patch("backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets", return_value=triple_domain_assets),
            ):
                overview = ModConfigManager.get_overview(context, ["author.demo_steam"])

            self.assertEqual(overview["matched_group_count"], 1)
            self.assertEqual(overview["orphan_file_count"], 0)
            matched_group = overview["groups"][0]
            self.assertEqual(matched_group["instance_count"], 3)
            self.assertEqual(
                [item["source_kind"] for item in matched_group["instances"]],
                ["workshop", "local", "self"],
            )

    def test_sync_group_instance_copies_content_within_same_package_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            local_file = config_dir / "Mod_LocalCopy_DemoSettings.xml"
            workshop_file = config_dir / "Mod_2876543210_DemoSettings.xml"
            local_file.write_text("<settings>local-old</settings>", encoding="utf-8")
            workshop_file.write_text("<settings>workshop-new</settings>", encoding="utf-8")

            visible_mods = [
                {
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
            ]

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=visible_mods),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(
                        visible_mods[0],
                        visible_mods[0]["coexist_workshop_variant"],
                    ),
                ),
            ):
                result = ModConfigManager.sync_group_instance(
                    context,
                    ["author.demo_steam"],
                    str(workshop_file),
                    str(local_file),
                )

            self.assertEqual(local_file.read_text(encoding="utf-8"), "<settings>workshop-new</settings>")
            self.assertEqual(result["package_id"], "author.demo")
            self.assertEqual(result["settings_class_name"], "DemoSettings")
            self.assertTrue(Path(result["source_path"]).samefile(workshop_file))
            self.assertTrue(Path(result["target_path"]).samefile(local_file))
            refreshed_group = result["overview"]["groups"][0]
            self.assertEqual(refreshed_group["instance_count"], 2)

    def test_sync_group_instance_rejects_different_settings_class_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_dir = Path(context.game_config_path)
            local_file = config_dir / "Mod_LocalCopy_LocalSettings.xml"
            workshop_file = config_dir / "Mod_2876543210_WorkshopSettings.xml"
            local_file.write_text("<settings>local-old</settings>", encoding="utf-8")
            workshop_file.write_text("<settings>workshop-new</settings>", encoding="utf-8")

            visible_mods = [
                {
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
            ]

            with (
                patch("backend.managers.mgr_mod_config.ModDAO.get_profile_mods", return_value=visible_mods),
                patch(
                    "backend.managers.mgr_mod_config.ModDAO.get_triple_domain_assets",
                    return_value=self._build_triple_domain_assets(
                        visible_mods[0],
                        visible_mods[0]["coexist_workshop_variant"],
                    ),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "只能在同一种配置之间互相覆盖"):
                    ModConfigManager.sync_group_instance(
                        context,
                        ["author.demo_steam"],
                        str(workshop_file),
                        str(local_file),
                    )


if __name__ == "__main__":
    unittest.main()
