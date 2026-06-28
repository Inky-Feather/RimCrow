import tempfile
import unittest
from pathlib import Path

from backend.database.dao import GroupDAO
from backend.database.models import GroupData, GroupMod, UserModData, db


class TestGroupDAO(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        db_path = str(Path(self.temp_dir.name) / "group-dao-test.db")
        db.init(db_path)
        db.connect(reuse_if_open=True)
        db.create_tables([UserModData, GroupData, GroupMod])

    def tearDown(self):
        if not db.is_closed():
            db.close()

    def _seed_group(self, group_id="g1", mod_ids=None):
        GroupData.create(group_id=group_id, name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        for index, mod_id in enumerate(mod_ids or []):
            UserModData.create(mod_id=mod_id)
            GroupMod.create(group_id=group_id, mod_id=mod_id, sort_index=index)

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

    def test_reorder_mods_in_group_keeps_hidden_members_and_positions(self):
        self._seed_group(mod_ids=["visible.a", "hidden.x", "visible.b", "hidden.y"])

        GroupDAO.reorder_mods_in_group("g1", ["visible.b", "visible.a"])

        ordered_ids = [
            row.mod_id.mod_id
            for row in GroupMod.select(GroupMod.mod_id).where(GroupMod.group_id == "g1").order_by(GroupMod.sort_index, GroupMod.mod_id)
        ]
        self.assertEqual(ordered_ids, ["visible.b", "hidden.x", "visible.a", "hidden.y"])

    def test_reorder_mods_in_group_rejects_unknown_member(self):
        self._seed_group(mod_ids=["visible.a", "visible.b"])

        with self.assertRaisesRegex(ValueError, "包含无效成员"):
            GroupDAO.reorder_mods_in_group("g1", ["visible.b", "missing.mod"])

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
