import json
import subprocess
import tarfile
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.managers.mgr_steam import SteamManager
from backend.paths.game_locations import (
    get_default_steam_data_root_candidates,
    get_default_steam_root_candidates,
    normalize_steam_root,
)
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

    @patch("backend.managers.mgr_steam.platform.system", return_value="Linux")
    def test_reload_paths_from_settings_uses_platform_steam_executable(self, _platform_system):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_root, ignore_errors=True))
        steam_root = temp_root / "Steam"
        steamcmd_root = temp_root / "steamcmd"
        steam_root.mkdir()
        steamcmd_root.mkdir()
        (steam_root / "steam").write_text("", encoding="utf-8")

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

        self.assertEqual(result["steam_exe"], str(steam_root / "steam"))
        self.assertEqual(manager.steamcmd_exe, str(steamcmd_root / "steamcmd.sh"))

    @patch("backend.managers.mgr_steam.platform.system", return_value="Darwin")
    def test_reload_paths_from_settings_normalizes_macos_app_bundle_to_root(self, _platform_system):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_root, ignore_errors=True))
        steam_root = temp_root / "Steam"
        steam_app = steam_root / "Steam.app"
        steam_exe = steam_app / "Contents" / "MacOS" / "steam_osx"
        steamcmd_root = temp_root / "steamcmd"
        steam_exe.parent.mkdir(parents=True, exist_ok=True)
        steam_exe.write_text("", encoding="utf-8")
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

        with patch.object(settings.config, "steam_path", str(steam_app)), \
             patch.object(settings.config, "steamcmd_path", str(steamcmd_root)):
            result = manager.reload_paths_from_settings()

        self.assertEqual(result["steam_dir"], str(steam_root))
        self.assertEqual(result["steam_exe"], str(steam_exe))

    @patch("backend.managers.mgr_steam.platform.system", return_value="Darwin")
    def test_reload_paths_from_settings_normalizes_macos_executable_to_root(self, _platform_system):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_root, ignore_errors=True))
        steam_root = temp_root / "Steam"
        steam_exe = steam_root / "Steam.app" / "Contents" / "MacOS" / "steam_osx"
        steamcmd_root = temp_root / "steamcmd"
        steam_exe.parent.mkdir(parents=True, exist_ok=True)
        steam_exe.write_text("", encoding="utf-8")
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

        with patch.object(settings.config, "steam_path", str(steam_exe)), \
             patch.object(settings.config, "steamcmd_path", str(steamcmd_root)):
            result = manager.reload_paths_from_settings()

        self.assertEqual(result["steam_dir"], str(steam_root))
        self.assertEqual(result["steam_exe"], str(steam_exe))

    def test_normalize_steam_root_accepts_macos_app_bundle_and_executable(self):
        app_path = "/Applications/Steam.app"
        exe_path = "/Applications/Steam.app/Contents/MacOS/steam_osx"

        with patch("backend.paths.game_locations.platform.system", return_value="Darwin"):
            self.assertEqual(normalize_steam_root(app_path), "/Applications")
            self.assertEqual(normalize_steam_root(exe_path), "/Applications")

    def test_default_steam_root_candidates_prefer_macos_applications_dirs(self):
        with patch("backend.paths.game_locations.platform.system", return_value="Darwin"), \
             patch("backend.paths.game_locations.os.path.expanduser", return_value="/Users/test"):
            candidates = get_default_steam_root_candidates()

        self.assertEqual(candidates, ["/Applications", "/Users/test/Applications"])

    def test_default_steam_data_root_candidates_use_macos_application_support(self):
        with patch("backend.paths.game_locations.platform.system", return_value="Darwin"), \
             patch("backend.paths.game_locations.os.path.expanduser", return_value="/Users/test"):
            candidates = get_default_steam_data_root_candidates()

        self.assertEqual(candidates, ["/Users/test/Library/Application Support/Steam"])

    @patch("backend.managers.mgr_steam.platform.system", return_value="Linux")
    def test_ensure_tools_uses_linux_steamcmd_archive(self, _platform_system):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_root, ignore_errors=True))
        manager = object.__new__(SteamManager)
        manager.steamcmd_dir = str(temp_root)
        manager.steamcmd_exe = str(temp_root / "steamcmd.sh")
        captured = {}

        class DownloadManager:
            def add_task(self, url, target_dir, filename):
                captured.update({"url": url, "target_dir": target_dir, "filename": filename})
                return "task-a"

        with patch.object(settings.config, "steamcmd_path", str(temp_root)):
            tasks = manager.ensure_tools(DownloadManager())

        self.assertEqual(tasks, [{"type": "steamcmd", "id": "task-a"}])
        self.assertTrue(captured["url"].endswith("steamcmd_linux.tar.gz"))
        self.assertEqual(captured["filename"], "steamcmd_linux.tar.gz")

    @patch("backend.managers.mgr_steam.platform.system", return_value="Linux")
    def test_post_download_setup_extracts_linux_steamcmd_archive(self, _platform_system):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_root, ignore_errors=True))
        archive_path = temp_root / "steamcmd_linux.tar.gz"
        source_file = temp_root / "steamcmd.sh"
        source_file.write_text("#!/bin/sh\n", encoding="utf-8")
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(source_file, arcname="steamcmd.sh")
        source_file.unlink()

        manager = object.__new__(SteamManager)
        manager.steamcmd_dir = str(temp_root)
        manager.steamcmd_exe = str(temp_root / "steamcmd.sh")
        manager.steamcmd_ready = False

        manager.post_download_setup("steamcmd", str(archive_path))

        self.assertTrue((temp_root / "steamcmd.sh").exists())
        self.assertTrue(manager.steamcmd_ready)
        self.assertFalse(archive_path.exists())

    @patch("backend.managers.mgr_steam.psutil.process_iter")
    @patch("backend.managers.mgr_steam.platform.system", return_value="Darwin")
    def test_is_steam_running_uses_platform_process_names(self, _platform_system, process_iter):
        manager = self.make_manager()
        process_iter.return_value = [SimpleNamespace(info={"name": "steam_osx"})]

        self.assertTrue(manager.is_steam_running())

    @patch("backend.managers.mgr_steam.open_system_uri", return_value=True)
    def test_start_steam_uses_url_fallback_on_non_windows(self, open_system_uri):
        manager = self.make_manager()
        manager.is_steam_running = lambda: False
        manager.steam_exe = ""

        result = manager.start_steam()

        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "steam_url")
        open_system_uri.assert_called_once_with("steam://open/main")

    def test_steamworks_download_wrapper_uses_worker_payload_and_marker(self):
        manager = self.make_manager()
        captured = {}

        def fake_worker(action, payload, timeout_seconds=0):
            captured["action"] = action
            captured["payload"] = json.loads(payload)
            captured["timeout_seconds"] = timeout_seconds
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='STEAM_WORKSHOP_DOWNLOAD_JSON:{"ready": true, "detail": "steamworks_download_finished", "items": {"1001": {"completed": true}}}\n',
                stderr="",
            )

        manager._run_steam_worker = fake_worker

        result = manager.download_workshop_items_via_steamworks(["1001", "bad", "1001"], wait_seconds=3)

        self.assertEqual(captured["action"], "download_workshop_items")
        self.assertEqual(captured["payload"]["ids"], ["1001"])
        self.assertTrue(captured["payload"]["high_priority"])
        self.assertEqual(captured["payload"]["wait_seconds"], 3.0)
        self.assertEqual(captured["timeout_seconds"], 13.0)
        self.assertEqual(result["detail"], "steamworks_download_finished")
        self.assertTrue(result["items"]["1001"]["completed"])

    def test_steamworks_details_wrapper_uses_worker_payload_and_marker(self):
        manager = self.make_manager()
        captured = {}

        def fake_worker(action, payload, timeout_seconds=0):
            captured["action"] = action
            captured["payload"] = json.loads(payload)
            captured["timeout_seconds"] = timeout_seconds
            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='STEAM_WORKSHOP_DETAILS_JSON:{"ready": true, "detail": "steamworks_details_ready", "details": {"1001": {"title": "Demo"}}}\n',
                stderr="",
            )

        manager._run_steam_worker = fake_worker

        result = manager.query_workshop_item_details("1001, bad,1002", wait_seconds=4)

        self.assertEqual(captured["action"], "query_workshop_details")
        self.assertEqual(captured["payload"]["ids"], ["1001", "1002"])
        self.assertEqual(captured["payload"]["wait_seconds"], 4.0)
        self.assertEqual(captured["timeout_seconds"], 14.0)
        self.assertEqual(result["detail"], "steamworks_details_ready")
        self.assertEqual(result["details"]["1001"]["title"], "Demo")


if __name__ == "__main__":
    unittest.main()
