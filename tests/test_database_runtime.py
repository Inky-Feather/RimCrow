import tempfile
import unittest
from pathlib import Path

from backend._version import __db_version__, __version__
from backend.database.models import GameProfile, GroupData, ModAsset, SystemInfo, UserModData, all_models, db
from backend.database.runtime import clear_db


class TestDatabaseRuntime(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        db_path = str(Path(self.temp_dir.name) / "runtime-test.db")
        db.init(db_path)
        db.connect(reuse_if_open=True)
        db.create_tables(all_models)

    def tearDown(self):
        if not db.is_closed():
            db.close()

    def test_clear_db_rebuilds_to_clean_startup_state(self):
        SystemInfo.insert_many([
            {"key": "db_version", "value": "old"},
            {"key": "app_version", "value": "old"},
            {"key": "steamdb_version", "value": "old-cache-version"},
        ]).execute()
        GameProfile.create(id="profile-a", name="Profile A", description="", game_install_path="", user_data_path="", game_version="")
        GroupData.create(group_id="g1", name="Group 1", color="#ffffff", sort_index=0, is_expanded=True)
        UserModData.create(mod_id="demo.mod", notes="note")
        ModAsset.create(path_hash="asset-a", package_id="demo.mod", package_id_raw="demo.mod", name="Demo", path="D:/Mods/Demo")

        self.assertTrue(clear_db())

        self.assertEqual(GameProfile.select().count(), 1)
        self.assertIsNotNone(GameProfile.get_or_none(GameProfile.id == "default"))
        self.assertEqual(GroupData.select().count(), 0)
        self.assertEqual(UserModData.select().count(), 0)
        self.assertEqual(ModAsset.select().count(), 0)
        self.assertEqual(SystemInfo.get_by_id("db_version").value, __db_version__)
        self.assertEqual(SystemInfo.get_by_id("app_version").value, __version__)
        self.assertIsNone(SystemInfo.get_or_none(SystemInfo.key == "steamdb_version"))


if __name__ == "__main__":
    unittest.main()
