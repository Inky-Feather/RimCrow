import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
