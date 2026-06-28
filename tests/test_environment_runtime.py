import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from backend.managers.mgr_game_monitor import GameMonitor


class TestGameMonitorRuntimeSession(unittest.TestCase):
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
