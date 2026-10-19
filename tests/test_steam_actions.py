import json
import subprocess
import tarfile
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import vdf

from backend.managers.mgr_steam import SteamManager, TaskStatus, _collect_workshop_item_state
from backend.paths.game_locations import (
    get_default_steam_data_root_candidates,
    get_default_steam_root_candidates,
    normalize_steam_root,
)
from backend.settings import settings


class TestSteamcmdStorageLock(unittest.TestCase):
    def test_queued_workers_refresh_paths_before_running_batch(self):
        for run in (SteamManager._run_steamcmd_process, SteamManager._run_steamcmd_workshop_repair_process):
            with self.subTest(worker=run.__name__):
                manager = Mock(spec=SteamManager)
                manager.steamcmd_dir = "old"
                manager._steamcmd_lock = threading.Lock()
                manager._steamcmd_processes = {}
                manager._steamcmd_cancelled = set()
                manager._is_steamcmd_task_cancelled.return_value = False
                calls = []
                def reload():
                    calls.append("reload")
                    manager.steamcmd_dir = "new"
                def batch(**kwargs):
                    calls.append("batch")
                    self.assertEqual(kwargs["workshop_log_path"], Path("new/logs/workshop_log.txt"))
                    raise OSError("stop before process launch")
                manager.reload_paths_from_settings.side_effect = reload
                manager._run_single_steamcmd_batch.side_effect = batch
                run(manager, ["1001"], "probe")
                self.assertEqual(calls, ["reload", "batch"])
                manager.reload_paths_from_settings.assert_called_once_with()


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

    def test_unsubscribe_requires_steam_confirmation_and_updated_local_state(self):
        cases = [
            # 实际订阅、本地状态、目录存在、经过秒数、期望结果
            (True, True, False, 0, TaskStatus.RUNNING),
            (True, True, False, 4, TaskStatus.RUNNING),
            (True, True, True, 31, TaskStatus.ERROR),
            (None, False, False, 31, TaskStatus.ERROR),
            (False, True, False, 4, TaskStatus.RUNNING),
            (False, False, True, 4, TaskStatus.COMPLETED),
            (False, None, False, 4, TaskStatus.COMPLETED),
        ]
        for subscribed, local_subscribed, folder_exists, elapsed, expected in cases:
            with self.subTest(subscribed=subscribed, local=local_subscribed, elapsed=elapsed):
                manager = self.make_manager()
                manager._active_tasks = {'task': {'targets': ['1001'], 'total': 1, 'action': 'unsubscribe', 'start_time': 0}}
                manager.workshop_merged_data = Mock(return_value={} if local_subscribed is None else {
                    '1001': {'is_subscribed': local_subscribed, 'is_installed': folder_exists}})
                manager.query_workshop_item_states = Mock(return_value={'ready': True, 'states': {'1001': {'is_subscribed': subscribed}}})
                events = []
                def emit(**event):
                    events.append(event)
                    manager._active_tasks.clear()
                manager._emit_progress_event = emit
                with patch('backend.managers.mgr_steam.time.time', return_value=elapsed), \
                     patch('backend.managers.mgr_steam.time.sleep'), \
                     patch('backend.managers.mgr_steam.os.path.exists', return_value=folder_exists):
                    manager._master_monitor_loop()
                self.assertEqual(events[0]['status'], expected)
                if expected == TaskStatus.ERROR:
                    self.assertEqual(events[0]['target_details']['1001']['complete_reason'], 'request_failed')

    def test_item_state_failure_is_not_unsubscribe_confirmation(self):
        steam = Mock()
        steam.Workshop.GetItemState.side_effect = RuntimeError('Steam unavailable')
        steam.Workshop.GetItemInstallInfo.return_value = {}
        steam.Workshop.GetItemDownloadInfo.return_value = {}
        self.assertIsNone(_collect_workshop_item_state(steam, '1001')['is_subscribed'])

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

    def test_default_steam_root_candidates_include_common_linux_roots(self):
        with patch("backend.paths.game_locations.platform.system", return_value="Linux"), \
             patch("backend.paths.game_locations.os.path.expanduser", return_value="/home/test"), \
             patch("backend.paths.game_locations.os.getenv", return_value="/xdg"):
            candidates = get_default_steam_root_candidates()

        self.assertEqual(candidates[:4], [
            "/home/test/.steam/steam",
            "/home/test/.steam/root",
            "/home/test/.steam/debian-installation",
            "/home/test/.local/share/Steam",
        ])
        self.assertIn("/xdg/Steam", candidates)

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


class TestSteamcmdAcfRepair(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manager = object.__new__(SteamManager)
        self.manager.steamcmd_dir = str(self.root)
        self.manager._steamcmd_lock = threading.Lock()
        self.manager._steamcmd_processes = {}
        self.manager._steamcmd_cancelled = set()
        self.acf = self.manager._get_steamcmd_acf_path()
        self.acf.parent.mkdir(parents=True)
        self.content = self.manager._get_steamcmd_content_root()
        (self.content / "1001").mkdir(parents=True)
        (self.content / "1001" / "content.txt").write_text("keep", encoding="utf-8")

    def payload(self):
        return {"AppWorkshop": {
            "appid": "294100", "NeedsUpdate": "1", "SizeOnDisk": "4",
            "WorkshopItemsInstalled": {"1001": {"manifest": "18446744073709551615", "size": "4", "timeupdated": "0"}},
            "WorkshopItemDetails": {"1001": {"manifest": "11", "latest_manifest": "12", "timetouched": "0"}},
            "FutureField": {"text": 'keep "quotes" and \\paths'},
        }}

    def write_payload(self, payload=None):
        self.acf.write_text(vdf.dumps(payload or self.payload(), pretty=True), encoding="utf-8")

    def test_missing_acf_does_not_register_unrecorded_directories(self):
        self.assertFalse(self.manager.reconcile_steamcmd_acf()["updated"])
        self.assertFalse(self.acf.exists())

    def test_normalize_preserves_unknown_fields_updates_and_cache_only_entries(self):
        payload = self.payload()
        payload["AppWorkshop"]["WorkshopItemDetails"]["1002"] = {"manifest": "13"}
        source = b"\xef\xbb\xbf" + vdf.dumps(payload, pretty=True).replace("\n", "\r\n").encode("utf-8")
        self.acf.write_bytes(source)
        result = self.manager.reconcile_steamcmd_acf()
        self.assertTrue(result["updated"])
        self.assertEqual(result["removed_ids"], [])
        self.assertEqual(self.manager._parse_workshop_acf(self.acf.read_bytes()), payload)
        self.assertEqual(self.acf.with_suffix(".acf.rimcrow.bak").read_bytes(), source)
        self.assertFalse(self.manager.reconcile_steamcmd_acf()["updated"])
        self.assertEqual(self.manager.parse_acf_data(payload["AppWorkshop"])["1001"]["local_manifest"], "18446744073709551615")

    def test_invalid_installed_manifest_is_removed_without_deleting_content(self):
        for manifest in (None, "", "0", "-1", "1.5", "18446744073709551616", "rimcrow-123-4", "rmm-123-4"):
            with self.subTest(manifest=manifest):
                payload = self.payload()
                entry = payload["AppWorkshop"]["WorkshopItemsInstalled"]["1001"]
                if manifest is None:
                    del entry["manifest"]
                else:
                    entry["manifest"] = manifest
                self.write_payload(payload)
                result = self.manager.reconcile_steamcmd_acf()
                app = self.manager._parse_workshop_acf(self.acf.read_bytes())["AppWorkshop"]
                self.assertEqual(result["removed_ids"], ["1001"])
                self.assertNotIn("1001", app["WorkshopItemsInstalled"])
                self.assertIn("1001", app["WorkshopItemDetails"])
                self.assertEqual((self.content / "1001" / "content.txt").read_text(), "keep")

    def test_synthetic_cache_and_bad_numeric_fields_are_not_preserved(self):
        for section, field, value in (
            ("WorkshopItemDetails", "manifest", "rimcrow-123-4"),
            ("WorkshopItemDetails", "latest_manifest", "0"),
            ("WorkshopItemsInstalled", "size", "-1"),
            ("WorkshopItemsInstalled", "timeupdated", "not-a-time"),
        ):
            with self.subTest(section=section, field=field):
                payload = self.payload()
                payload["AppWorkshop"][section]["1001"][field] = value
                self.write_payload(payload)
                self.assertTrue(self.manager.reconcile_steamcmd_acf()["updated"])
                app = self.manager._parse_workshop_acf(self.acf.read_bytes())["AppWorkshop"]
                self.assertNotIn("1001", app[section])

    def test_orphan_install_is_removed_but_details_and_unrecorded_directory_remain(self):
        payload = self.payload()
        payload["AppWorkshop"]["WorkshopItemsInstalled"]["1002"] = {"manifest": "13"}
        payload["AppWorkshop"]["WorkshopItemDetails"]["1002"] = {"manifest": "14"}
        (self.content / "1003").mkdir()
        self.write_payload(payload)
        self.assertEqual(self.manager.reconcile_steamcmd_acf()["removed_ids"], ["1002"])
        app = self.manager._parse_workshop_acf(self.acf.read_bytes())["AppWorkshop"]
        self.assertEqual(set(app["WorkshopItemsInstalled"]), {"1001"})
        self.assertIn("1002", app["WorkshopItemDetails"])
        self.assertNotIn("1003", app["WorkshopItemDetails"])

    def test_ambiguous_or_broken_structure_is_not_guessed_or_overwritten(self):
        source = vdf.dumps(self.payload(), pretty=True).encode("utf-8")
        for invalid in (
            b"", source[:-3], source.replace(b'"294100"', b'"123"'),
            source.replace(b'"AppWorkshop"', b'"Other"'),
            source.replace(b'"appid" "294100"', b'"appid" "294100"\n"appid" "294100"'),
            source.replace(b'"WorkshopItemsInstalled"\n', b'"WorkshopItemsInstalled" "bad"\n'),
            source + b"\xff",
        ):
            with self.subTest(invalid=invalid[:70]):
                self.acf.write_bytes(invalid)
                result = self.manager.reconcile_steamcmd_acf()
                self.assertIn("error", result)
                self.assertFalse(result["updated"])
                self.assertEqual(self.acf.read_bytes(), invalid)
                self.assertEqual(self.manager.get_acf_json(self.acf), {})

    def test_backup_or_replace_failure_keeps_original_and_cleans_temp_file(self):
        for target in ("shutil.copy2", "os.replace"):
            with self.subTest(target=target):
                original = b"\xef\xbb\xbf" + vdf.dumps(self.payload(), pretty=True).encode("utf-8")
                self.acf.write_bytes(original)
                with patch(f"backend.managers.mgr_steam.{target}", side_effect=PermissionError("locked")):
                    self.assertIn("error", self.manager.reconcile_steamcmd_acf())
                self.assertEqual(self.acf.read_bytes(), original)
                self.assertEqual(list(self.acf.parent.glob("*.tmp")), [])

    def test_changed_file_is_not_replaced(self):
        self.acf.write_bytes(b"\xef\xbb\xbf" + vdf.dumps(self.payload(), pretty=True).encode("utf-8"))
        with patch("backend.managers.mgr_steam.os.fsync", side_effect=lambda fd: self.acf.write_bytes(b"external write")):
            self.assertIn("error", self.manager.reconcile_steamcmd_acf())
        self.assertEqual(self.acf.read_bytes(), b"external write")
        self.assertEqual(list(self.acf.parent.glob("*.tmp")), [])

    def test_running_process_skips_repair(self):
        self.write_payload()
        original = self.acf.read_bytes()
        self.manager._steamcmd_processes["task"] = Mock(poll=Mock(return_value=None))
        self.assertEqual(self.manager.reconcile_steamcmd_acf()["skipped"], "steamcmd_running")
        self.assertEqual(self.acf.read_bytes(), original)

    def test_external_steamcmd_in_same_directory_also_blocks_repair(self):
        self.write_payload()
        process = SimpleNamespace(info={"name": "steamcmd.exe", "exe": str(self.root / "steamcmd.exe")})
        with patch("backend.managers.mgr_steam.psutil.process_iter", return_value=[process]):
            self.assertEqual(self.manager.reconcile_steamcmd_acf()["skipped"], "steamcmd_running")

    def test_details_manifest_is_not_a_local_installed_manifest(self):
        payload = self.payload()["AppWorkshop"]
        del payload["WorkshopItemsInstalled"]["1001"]["manifest"]
        self.assertIsNone(self.manager.parse_acf_data(payload)["1001"]["local_manifest"])

    def test_download_stops_before_process_start_if_acf_cannot_be_repaired(self):
        self.acf.write_bytes(b"broken")
        self.manager.steamcmd_ready = True
        with patch("backend.managers.mgr_steam.EventBus.resume"), patch("backend.managers.mgr_steam.threading.Thread") as thread:
            with self.assertRaises(RuntimeError):
                self.manager.download_workshop_items(["1001"])
            thread.assert_not_called()

    def test_workshop_repair_does_not_use_details_as_an_installed_record(self):
        payload = self.payload()
        payload["AppWorkshop"]["WorkshopItemsInstalled"] = {}
        self.write_payload(payload)
        steam_acf = self.root / "steam.acf"
        steam_acf.write_bytes(vdf.dumps(self.payload(), pretty=True).encode("utf-8"))
        original = steam_acf.read_bytes()
        self.manager._get_acf_path = Mock(return_value=str(steam_acf))
        self.manager.is_steam_running = Mock(return_value=False)
        with patch.object(settings.config, "workshop_mods_path", str(self.root / "steam_content")):
            result = self.manager._apply_steamcmd_repair_items(["1001"], "task", "steamcmd-workshop-repair")
        self.assertEqual(result["repaired_ids"], [])
        self.assertEqual(steam_acf.read_bytes(), original)
        self.assertTrue((self.content / "1001" / "content.txt").exists())

    def test_cleanup_does_not_delete_content_if_acf_write_fails(self):
        self.write_payload()
        original = self.acf.read_bytes()
        with patch.object(self.manager, "_write_workshop_acf", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                self.manager._cleanup_steamcmd_repair_sources(["1001"], self.payload(), self.acf)
        self.assertEqual(self.acf.read_bytes(), original)
        self.assertTrue((self.content / "1001" / "content.txt").exists())


if __name__ == "__main__":
    unittest.main()
