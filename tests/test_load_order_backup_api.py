import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

from backend.api import API


class TestLoadOrderBackupApi(unittest.TestCase):
    def _create_api(self, context=None):
        api = object.__new__(API)
        api.active_context = SimpleNamespace(profile_id="current")
        api.load_order_mgr = object()
        api._resolve_load_order_scope = Mock(
            return_value=(context or SimpleNamespace(profile_id="other", backup_dir=""), SimpleNamespace(name="Other"))
        )
        return api

    def test_backup_listing_uses_read_only_manager(self):
        context = SimpleNamespace(
            profile_id="other",
            backup_dir="C:/backups/other",
            is_healthy=True,
        )
        api = self._create_api(context)
        api._resolve_load_order_scope.return_value = (context, SimpleNamespace(name="Other"))

        with patch("backend.api.LoadOrderManager") as manager_cls:
            manager_cls.return_value.get_all_backups.return_value = {
                "today": [], "earlier": [], "other": [], "last_backup": [],
            }
            result = api.backups_get_all("other")

        self.assertEqual(result.get("status"), "success")
        manager_cls.assert_called_once_with(context, rotate_backups=False)

    def test_bootstrap_current_profile_rotates_backups(self):
        context = SimpleNamespace(
            profile_id="next",
            backup_dir="C:/backups/next",
            is_healthy=True,
        )
        api = object.__new__(API)
        api.game_log_mgr = None
        api.scanner = None
        api.profile_mgr = Mock()
        api.profile_mgr.activate_profile.return_value = context

        with tempfile.TemporaryDirectory() as temp_dir, \
             patch("backend.api.settings.config.self_mods_path", temp_dir), \
             patch("backend.api.ModScanner"), \
             patch("backend.api.GameLogManager") as game_log_mgr_cls, \
             patch("backend.api.OrderSorter"), \
             patch("backend.api.LoadOrderManager") as load_order_mgr_cls:
            game_log_mgr_cls.return_value.start_realtime_monitor = Mock()

            api._bootstrap_context("next")

        load_order_mgr_cls.assert_called_once_with(context, rotate_backups=True)

    def test_save_returns_warning_when_backup_failed_but_main_file_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            api = self._create_api()
            api.active_context.game_config_path = temp_dir
            api.load_order_mgr = Mock()
            api.load_order_mgr.is_version_token_stale.return_value = (False, {"mtime": 1})
            api.load_order_mgr.save_active_mods.return_value = True
            api.load_order_mgr.read_active_mods.return_value = {
                "version_token": {"mtime": 2},
                "modify_time": 2000,
                "active_mods": ["new.mod"],
            }
            api.load_order_mgr.last_backup_error = "自动备份失败：磁盘空间不足"

            result = api.load_order_save_with_token(["new.mod"], is_dirty=True, base_version_token={"mtime": 1})

        self.assertEqual(result.get("status"), "warning")
        self.assertTrue(result["data"]["saved"])
        self.assertIn("备份", result.get("message", ""))

    def test_import_empty_load_order_returns_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "empty.txt"
            path.write_text("", encoding="utf-8")
            api = self._create_api()
            api.load_order_mgr = Mock()
            api.load_order_mgr.read_active_mods.return_value = {
                "active_mods": [],
                "workshop_ids": [],
                "mods": [],
                "errors": [],
            }

            result = api.load_order_file_open(str(path))

        self.assertEqual(result.get("status"), "warning")
        self.assertEqual(result["data"]["active_ids"], [])


if __name__ == "__main__":
    unittest.main()
