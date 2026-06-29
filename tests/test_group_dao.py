import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from backend.database.dao import GroupDAO
from backend.database.models import GameProfile, GroupData, GroupMod, ModAsset, UserModData, db
from backend.migrations.app_upgrade import normalize_duplicate_group_names_on_load, run_app_upgrade_migrations


class TestGroupDAO(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        db_path = str(Path(self.temp_dir.name) / "group-dao-test.db")
        db.init(db_path)
        db.connect(reuse_if_open=True)
        db.create_tables([UserModData, GroupData, GroupMod, ModAsset, GameProfile])

    def tearDown(self):
        if not db.is_closed():
            db.close()

    def _create_asset(self, package_id, path_hash=None, path=None, source="workshop", store="workshop"):
        normalized_hash = path_hash or f"hash-{package_id.replace('.', '-')}"
        normalized_path = path or f"/mods/{package_id.replace('.', '_')}"
        return ModAsset.create(
            path_hash=normalized_hash,
            package_id=package_id,
            name=package_id,
            path=normalized_path,
            source=source,
            store=store,
        )

    def _seed_group(self, group_id="g1", mod_ids=None):
        GroupData.create(group_id=group_id, name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        for index, mod_id in enumerate(mod_ids or []):
            UserModData.create(mod_id=mod_id)
            GroupMod.create(group_id=group_id, mod_id=mod_id, sort_index=index)

    def test_create_group_starts_at_zero_and_normalizes_name(self):
        first_group = GroupDAO.create_group("  A  ")
        second_group = GroupDAO.create_group("B")

        self.assertEqual(first_group.name, "A")
        self.assertEqual(first_group.sort_index, 0)
        self.assertEqual(second_group.sort_index, 1)

    def test_create_group_rejects_blank_or_duplicate_name(self):
        GroupDAO.create_group("UI")

        with self.assertRaisesRegex(ValueError, "分组名称不能为空"):
            GroupDAO.create_group("   ")
        with self.assertRaisesRegex(ValueError, "分组名称已存在"):
            GroupDAO.create_group(" UI ")

    def test_reorder_groups_rejects_partial_payload(self):
        GroupData.create(group_id="g1", name="A", color="#ffffff", sort_index=0, is_expanded=True)
        GroupData.create(group_id="g2", name="B", color="#ffffff", sort_index=1, is_expanded=True)

        with self.assertRaisesRegex(ValueError, "数量与当前数据不一致"):
            GroupDAO.reorder_groups(["g1"])

        ordered_ids = [
            row.group_id
            for row in GroupData.select(GroupData.group_id).order_by(GroupData.sort_index, GroupData.group_id)
        ]
        self.assertEqual(ordered_ids, ["g1", "g2"])

    def test_update_group_info_rejects_invalid_payload(self):
        GroupData.create(group_id="g1", name="A", color="#ffffff", sort_index=0, is_expanded=True)

        with self.assertRaisesRegex(ValueError, "未提供有效字段"):
            GroupDAO.update_group_info("g1", sort_index=99)
        with self.assertRaisesRegex(ValueError, "分组名称不能为空"):
            GroupDAO.update_group_info("g1", name="   ")

        group = GroupData.get_by_id("g1")
        self.assertEqual(group.name, "A")
        self.assertEqual(group.sort_index, 0)

    def test_update_group_info_rejects_missing_or_duplicate_group_name(self):
        GroupData.create(group_id="g1", name="A", color="#ffffff", sort_index=0, is_expanded=True)
        GroupData.create(group_id="g2", name="B", color="#ffffff", sort_index=1, is_expanded=True)

        with self.assertRaisesRegex(ValueError, "目标分组不存在"):
            GroupDAO.update_group_info("missing", name="C")
        with self.assertRaisesRegex(ValueError, "分组名称已存在"):
            GroupDAO.update_group_info("g2", name=" A ")

    def test_delete_group_rejects_missing_group(self):
        with self.assertRaisesRegex(ValueError, "目标分组不存在"):
            GroupDAO.delete_group("missing")

    def test_add_mods_to_group_appends_only_valid_new_members(self):
        self._seed_group(mod_ids=["visible.a"])
        self._create_asset("visible.a")
        self._create_asset("visible.b")

        inserted_count = GroupDAO.add_mods_to_group("g1", ["visible.a", "visible.b", "visible.b_steam"])

        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id)
            .where(GroupMod.group_id == "g1")
            .order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(inserted_count, 1)
        self.assertEqual(ordered_ids, ["visible.a", "visible.b"])

    def test_add_mods_to_group_rejects_missing_group_or_invalid_member(self):
        GroupData.create(group_id="g1", name="A", color="#ffffff", sort_index=0, is_expanded=True)
        self._create_asset("visible.a")

        with self.assertRaisesRegex(ValueError, "目标分组不存在"):
            GroupDAO.add_mods_to_group("missing", ["visible.a"])
        with self.assertRaisesRegex(ValueError, "包含无效成员"):
            GroupDAO.add_mods_to_group("g1", ["missing.mod"])

    def test_remove_mods_from_group_rejects_missing_group(self):
        with self.assertRaisesRegex(ValueError, "目标分组不存在"):
            GroupDAO.remove_mods_from_group("missing", ["visible.a"])

    def test_get_groups_structured_dedupes_normalized_legacy_members(self):
        GroupData.create(group_id="g1", name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        UserModData.create(mod_id="mod.alpha")
        UserModData.create(mod_id="mod.alpha_steam")
        GroupMod.insert_many([
            {"group_id": "g1", "mod_id": "mod.alpha", "sort_index": 0},
            {"group_id": "g1", "mod_id": "mod.alpha_steam", "sort_index": 1},
        ]).execute()

        groups = GroupDAO.get_all_groups_structured()

        self.assertEqual(groups[0]["mod_ids"], ["mod.alpha"])

    def test_reorder_mods_in_group_appends_hidden_members_to_tail(self):
        self._seed_group(mod_ids=["visible.a", "hidden.x", "visible.b", "hidden.y"])

        GroupDAO.reorder_mods_in_group("g1", ["visible.b", "visible.a"])

        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id).where(GroupMod.group_id == "g1").order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(ordered_ids, ["visible.b", "visible.a", "hidden.x", "hidden.y"])

    def test_reorder_mods_in_group_appends_new_members_only_once(self):
        self._seed_group(mod_ids=["visible.a", "hidden.x"])
        self._create_asset("visible.a")
        self._create_asset("hidden.x")
        self._create_asset("visible.b")

        GroupDAO.reorder_mods_in_group("g1", ["visible.b", "visible.a"])

        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id)
            .where(GroupMod.group_id == "g1")
            .order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(ordered_ids, ["visible.b", "visible.a", "hidden.x"])

    def test_reorder_mods_in_group_dedupes_hidden_legacy_variants_before_appending(self):
        GroupData.create(group_id="g1", name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        UserModData.create(mod_id="visible.a")
        UserModData.create(mod_id="legacy.hidden")
        UserModData.create(mod_id="legacy.hidden_steam")
        GroupMod.insert_many([
            {"group_id": "g1", "mod_id": "visible.a", "sort_index": 0},
            {"group_id": "g1", "mod_id": "legacy.hidden", "sort_index": 1},
            {"group_id": "g1", "mod_id": "legacy.hidden_steam", "sort_index": 2},
        ]).execute()

        GroupDAO.reorder_mods_in_group("g1", ["visible.a"])

        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id)
            .where(GroupMod.group_id == "g1")
            .order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(ordered_ids, ["visible.a", "legacy.hidden"])

    def test_reorder_mods_in_group_rejects_unknown_member(self):
        self._seed_group(mod_ids=["visible.a", "visible.b"])
        self._create_asset("visible.a")
        self._create_asset("visible.b")

        with self.assertRaisesRegex(ValueError, "包含无效成员"):
            GroupDAO.reorder_mods_in_group("g1", ["visible.b", "missing.mod"])

    def test_reorder_mods_in_group_rejects_duplicates_after_normalization(self):
        self._seed_group(mod_ids=["visible.a"])
        self._create_asset("visible.a")

        with self.assertRaisesRegex(ValueError, "存在重复项"):
            GroupDAO.reorder_mods_in_group("g1", ["visible.a", "visible.a_steam"])

    def test_reorder_mods_in_group_heals_orphan_group_rows(self):
        GroupData.create(group_id="g1", name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        UserModData.create(mod_id="visible.a")
        GroupMod.insert_many([
            {"group_id": "g1", "mod_id": "visible.a", "sort_index": 0},
            {"group_id": "g1", "mod_id": "orphan.mod", "sort_index": 1},
        ]).execute()

        GroupDAO.reorder_mods_in_group("g1", ["visible.a"])

        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id).where(GroupMod.group_id == "g1").order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(ordered_ids, ["visible.a", "orphan.mod"])
        self.assertIsNotNone(UserModData.get_or_none(UserModData.mod_id == "orphan.mod"))

    def test_reorder_mods_in_group_allows_first_insert_into_empty_group(self):
        GroupData.create(group_id="g1", name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        self._create_asset("visible.a")

        GroupDAO.reorder_mods_in_group("g1", ["visible.a"])

        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id)
            .where(GroupMod.group_id == "g1")
            .order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(ordered_ids, ["visible.a"])
        self.assertIsNotNone(UserModData.get_or_none(UserModData.mod_id == "visible.a"))

    def test_upgrade_migration_repairs_legacy_path_hash_group_rows(self):
        GroupData.create(group_id="g1", name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        self._create_asset("mod.alpha", path_hash="deadbeefdeadbeefdeadbeefdeadbeef")
        GroupMod.insert_many([
            {
                "group_id": "g1",
                "mod_id": "deadbeefdeadbeefdeadbeefdeadbeef",
                "sort_index": 0,
            }
        ]).execute()

        result = run_app_upgrade_migrations("0.20.4", "0.21.0")

        self.assertTrue(any("分组数据修复" in message for message in result.messages))
        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id)
            .where(GroupMod.group_id == "g1")
            .order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(ordered_ids, ["mod.alpha"])
        self.assertIsNotNone(UserModData.get_or_none(UserModData.mod_id == "mod.alpha"))

    def test_upgrade_migration_moves_companion_to_rimcrow_id_and_removes_old_tool_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_root = Path(temp_dir) / "toolmods"
            old_tool_dir = tool_root / "RMM_Companion"
            old_tool_dir.mkdir(parents=True)
            kept_old_asset_path = Path(temp_dir) / "external" / "RMM_Companion"
            kept_old_asset_path.mkdir(parents=True)
            user_data_path = Path(temp_dir) / "user"
            game_config_path = user_data_path / "Config"
            game_config_path.mkdir(parents=True)
            mods_config_path = game_config_path / "ModsConfig.xml"
            mods_config_path.write_text(
                "<ModsConfigData><activeMods>"
                "<li>before.mod</li><li>rmm.companion</li><li>rimcrow.companion</li><li>after.mod</li>"
                "</activeMods></ModsConfigData>",
                encoding="utf-8",
            )
            self._create_asset("rmm.companion", path_hash="old-tool", path=str(old_tool_dir), source="local", store="self")
            self._create_asset("rmm.companion", path_hash="external-tool", path=str(kept_old_asset_path), source="local", store="self")
            GameProfile.create(
                id="profile-a",
                name="Profile A",
                game_version="1.5",
                game_install_path=str(Path(temp_dir) / "game"),
                user_data_path=str(user_data_path),
                inactive_mods_order=["before.mod", "rmm.companion", "rimcrow.companion", "after.mod"],
                temp_mods_order=["rmm.companion", "temp.mod"],
            )

            import backend.migrations.app_upgrade as app_upgrade
            with patch.object(app_upgrade, "TOOL_MODS_DIR", tool_root):
                run_app_upgrade_migrations("0.23.0", "0.23.1")

            profile = GameProfile.get_by_id("profile-a")
            self.assertEqual(profile.inactive_mods_order, ["before.mod", "rimcrow.companion", "after.mod"])
            self.assertEqual(profile.temp_mods_order, ["rimcrow.companion", "temp.mod"])
            active_mods = [node.text for node in ET.parse(mods_config_path).getroot().findall("./activeMods/li")]
            self.assertEqual(active_mods, ["before.mod", "rimcrow.companion", "after.mod"])
            self.assertFalse(old_tool_dir.exists())
            self.assertIsNone(ModAsset.get_or_none(ModAsset.path_hash == "old-tool"))
            self.assertIsNotNone(ModAsset.get_or_none(ModAsset.path_hash == "external-tool"))

    def test_startup_normalization_renames_duplicate_group_names_with_suffix(self):
        GroupData.create(group_id="g1", name="UI", color="#ffffff", sort_index=0, is_expanded=True)
        GroupData.create(group_id="g2", name="UI", color="#ffffff", sort_index=1, is_expanded=True)
        GroupData.create(group_id="g3", name="UI-1", color="#ffffff", sort_index=2, is_expanded=True)
        GroupData.create(group_id="g4", name="UI ", color="#ffffff", sort_index=3, is_expanded=True)

        renamed = normalize_duplicate_group_names_on_load()

        self.assertEqual(
            renamed,
            [
                ("g2", "UI", "UI-2"),
                ("g4", "UI ", "UI-3"),
            ],
        )
        ordered_names = [
            row.name
            for row in GroupData.select().order_by(GroupData.sort_index, GroupData.group_id)
        ]
        self.assertEqual(ordered_names, ["UI", "UI-2", "UI-1", "UI-3"])
