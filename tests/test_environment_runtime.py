import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.managers.mgr_game import GameManager
from backend.managers.mgr_game_monitor import GameMonitor
from backend.utils.restart import _build_restart_environment, _resolve_restart_command


class TestGameMonitorRuntimeSession(unittest.TestCase):
    def test_game_monitor_initializes_without_windll_on_non_windows(self):
        api = SimpleNamespace(profile_mgr=SimpleNamespace(update_profile=Mock()))

        with patch("backend.managers.mgr_game_monitor.monitoring_mode", return_value="disabled"), \
             patch("backend.managers.mgr_game_monitor.supports_win32_ctypes", return_value=False), \
             patch.object(GameMonitor, "_create_idle_pages"):
            monitor = GameMonitor(api)

        self.assertEqual(monitor.monitoring_mode, "disabled")
        self.assertIsNone(monitor.psapi)
        self.assertIsNone(monitor.kernel32)

    def test_game_monitor_start_is_noop_when_monitoring_disabled(self):
        api = SimpleNamespace(profile_mgr=SimpleNamespace(update_profile=Mock()))

        with patch("backend.managers.mgr_game_monitor.monitoring_mode", return_value="disabled"), \
             patch("backend.managers.mgr_game_monitor.supports_win32_ctypes", return_value=False), \
             patch.object(GameMonitor, "_create_idle_pages"):
            monitor = GameMonitor(api)

        monitor.start()

        self.assertFalse(monitor.running)

    def test_begin_launch_creates_launching_session_with_deadline(self):
        api = SimpleNamespace(profile_mgr=SimpleNamespace(update_profile=Mock()))
        monitor = GameMonitor.__new__(GameMonitor)
        monitor.api = api
        monitor.runtime_session = monitor.get_runtime_session() if hasattr(monitor, "runtime_session") else None
        if monitor.runtime_session is None:
            from backend.managers.mgr_game_monitor import RuntimeSession
            monitor.runtime_session = RuntimeSession()

        session = monitor.begin_launch("profile-a", "direct")

        self.assertEqual(session.profile_id, "profile-a")
        self.assertEqual(session.state, "launching")
        self.assertEqual(session.launch_mode, "direct")
        self.assertIsNotNone(session.requested_at)
        self.assertEqual(session.deadline_at - session.requested_at, 60000)

    def test_mark_running_from_trusted_launch_updates_last_played_time(self):
        api = SimpleNamespace(profile_mgr=SimpleNamespace(update_profile=Mock()))
        monitor = GameMonitor.__new__(GameMonitor)
        monitor.api = api
        from backend.managers.mgr_game_monitor import RuntimeSession
        monitor.runtime_session = RuntimeSession()

        monitor.begin_launch("profile-a", "direct")
        session, payload = monitor.mark_running()

        self.assertEqual(session.state, "running")
        self.assertEqual(session.profile_id, "profile-a")
        self.assertEqual(session.source, "manager")
        self.assertEqual(payload["profile_id"], "profile-a")
        self.assertGreater(payload["last_played_time"], 0)
        api.profile_mgr.update_profile.assert_called_once()

    def test_mark_running_without_trusted_launch_attaches_external_default(self):
        api = SimpleNamespace(profile_mgr=SimpleNamespace(update_profile=Mock()))
        monitor = GameMonitor.__new__(GameMonitor)
        monitor.api = api
        from backend.managers.mgr_game_monitor import RuntimeSession
        monitor.runtime_session = RuntimeSession()

        session, payload = monitor.mark_running()

        self.assertEqual(session.state, "running")
        self.assertEqual(session.profile_id, "default")
        self.assertEqual(session.source, "external")
        self.assertEqual(payload["profile_id"], "default")
        self.assertEqual(payload["source"], "external")
        api.profile_mgr.update_profile.assert_not_called()

    def test_expire_launch_if_needed_clears_stale_launching_session(self):
        api = SimpleNamespace(profile_mgr=SimpleNamespace(update_profile=Mock()))
        monitor = GameMonitor.__new__(GameMonitor)
        monitor.api = api
        from backend.managers.mgr_game_monitor import RuntimeSession
        monitor.runtime_session = RuntimeSession()

        session = monitor.begin_launch("profile-a", "steam")

        expired = monitor.expire_launch_if_needed(now_ms=int(session.deadline_at or 0) + 1)

        self.assertIsNotNone(expired)
        self.assertEqual(expired.state, "idle")
        self.assertEqual(expired.failure_reason, "launch_timeout")
        self.assertEqual(expired.message, "启动超时，未检测到游戏进程。")

    def test_is_target_process_matches_supported_rimworld_names(self):
        monitor = GameMonitor.__new__(GameMonitor)

        self.assertTrue(monitor._is_target_process("RimWorldWin64.exe"))
        self.assertTrue(monitor._is_target_process("rimworldwin.exe"))
        self.assertTrue(monitor._is_target_process("RimWorldLinux.x86_64"))
        self.assertTrue(monitor._is_target_process("RimWorldMac"))
        self.assertFalse(monitor._is_target_process("Steam.exe"))

    def test_detect_game_process_checks_all_supported_names(self):
        monitor = GameMonitor.__new__(GameMonitor)
        processes = [
            SimpleNamespace(info={"name": "Steam.exe"}),
            SimpleNamespace(info={"name": "RimWorldWin.exe"}),
        ]

        self.assertTrue(monitor._detect_game_process(processes))

    def test_detect_game_process_skips_inaccessible_processes(self):
        monitor = GameMonitor.__new__(GameMonitor)

        class BrokenProcess:
            @property
            def info(self):
                raise RuntimeError("denied")

        self.assertFalse(monitor._detect_game_process([BrokenProcess()]))

    def test_trim_memory_skips_when_windows_api_is_unavailable(self):
        monitor = GameMonitor.__new__(GameMonitor)
        monitor.psapi = None
        monitor.kernel32 = None

        monitor._trim_memory()

    def test_linux_detect_executable_accepts_proton_windows_binary(self):
        with TemporaryDirectory() as tmp:
            install_root = Path(tmp)
            exe_path = install_root / "RimWorldWin64.exe"
            exe_path.write_text("", encoding="utf-8")

            with patch("backend.managers.mgr_game.platform.system", return_value="Linux"):
                self.assertEqual(GameManager.detect_executable(str(install_root)), str(exe_path))

    def test_linux_detect_executable_accepts_steam_launcher_script(self):
        with TemporaryDirectory() as tmp:
            install_root = Path(tmp)
            launcher_path = install_root / "start_RimWorld.sh"
            launcher_path.write_text("#!/bin/sh\n", encoding="utf-8")

            with patch("backend.managers.mgr_game.platform.system", return_value="Linux"):
                self.assertEqual(GameManager.detect_executable(str(install_root)), str(launcher_path))

    def test_linux_launch_game_rejects_proton_windows_binary_for_direct_launch(self):
        with TemporaryDirectory() as tmp:
            install_root = Path(tmp)
            exe_path = install_root / "RimWorldWin64.exe"
            exe_path.write_text("", encoding="utf-8")

            with patch("backend.managers.mgr_game.platform.system", return_value="Linux"), \
                 patch("backend.managers.mgr_game.subprocess.Popen") as popen:
                with self.assertRaisesRegex(Exception, "Steam/Proton"):
                    GameManager.launch_game(str(install_root))

        popen.assert_not_called()

class TestRestartRuntime(unittest.TestCase):
    def test_restart_command_uses_current_python_on_non_windows(self):
        fake_python = Path("/tmp/fake-venv/bin/python3")
        with patch("backend.platform.runtime.is_windows", return_value=False), \
             patch("backend.platform.runtime.Path.exists", return_value=False), \
             patch("sys.executable", str(fake_python)):
            command = _resolve_restart_command()

        self.assertEqual(command[0], str(fake_python.resolve()))
        self.assertNotIn("pythonw.exe", command[0].lower())

    def test_restart_environment_keeps_general_env_on_non_windows(self):
        with patch("backend.utils.restart.is_windows", return_value=False), \
             patch.dict("os.environ", {"PATH": "/usr/bin", "PYTHONPATH": "/tmp/old", "HOME": "/Users/test"}, clear=True):
            env = _build_restart_environment()

        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["HOME"], "/Users/test")
        self.assertNotIn("PYTHONPATH", env)
        self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")
