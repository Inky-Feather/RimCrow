import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.managers.mgr_steam import SteamManager
from backend.settings import settings


class TestSteamActionReadiness(unittest.TestCase):
    def make_manager(self):
        manager = object.__new__(SteamManager)
        manager._monitor_lock = threading.Lock()
        manager._active_tasks = {}
        manager._monitor_running = False
        return manager

    @patch("backend.managers.mgr_steam.platform.system", return_value="Windows")
    def test_registry_login_does_not_mark_ready_when_steamworks_probe_failed(self, _platform_system):
        manager = self.make_manager()
        manager.is_steam_running = lambda: True
        manager._read_windows_active_process_status = lambda: {
            "pid": 123,
            "active_user": 456,
            "running": True,
            "logged_in": True,
        }
        manager._probe_steamworks_status = lambda: {
            "available": False,
            "running": False,
            "logged_in": False,
            "ready": False,
            "detail": "steamworks_probe_timeout",
        }

        status = manager.get_steam_client_status()

        self.assertTrue(status["running"])
        self.assertTrue(status["logged_in"])
        self.assertFalse(status["ready"])
        self.assertEqual(status["detail"], "active_process_waiting_steamworks")

    def test_submit_task_does_not_register_monitor_when_steam_action_fails(self):
        manager = self.make_manager()
        manager.workshop_merged_data = lambda: {"1001": {"is_subscribed": True, "is_installed": True}}
        manager._execute_steam_action = lambda action, ids: False

        task_id = manager._submit_task("unsubscribe", ["1001"])

        self.assertIsNone(task_id)
        self.assertEqual(manager._active_tasks, {})
        self.assertFalse(manager._monitor_running)

    @patch("backend.managers.mgr_steam.platform.system", return_value="Windows")
    def test_reload_paths_from_settings_refreshes_cached_paths(self, _platform_system):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_root, ignore_errors=True))
        steam_root = temp_root / "Steam"
        steamcmd_root = temp_root / "steamcmd"
        steam_root.mkdir()
        steamcmd_root.mkdir()

        manager = object.__new__(SteamManager)
        manager.steamcmd_dir = "old"
        manager._cached_cmd_map = {"old": True}
        manager._last_cmd_log_mtime = 1
        manager._last_cmd_acf_mtime = 1
        manager._last_acf_mtime = 1
        manager._last_log_mtime = 1
        manager._cached_merged_data = [{"old": True}]
        manager.get_steam_path = lambda exe=False: ""

        with patch.object(settings.config, "steam_path", str(steam_root)), \
             patch.object(settings.config, "steamcmd_path", str(steamcmd_root)):
            result = manager.reload_paths_from_settings()

        self.assertEqual(result["steam_dir"], str(steam_root))
        self.assertEqual(result["steamcmd_dir"], str(steamcmd_root))
        self.assertEqual(manager.steamcmd_exe, str(steamcmd_root / "steamcmd.exe"))
        self.assertIsNone(manager._cached_cmd_map)
        self.assertEqual(manager._last_cmd_log_mtime, 0)


if __name__ == "__main__":
    unittest.main()
