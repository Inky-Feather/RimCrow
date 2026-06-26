import unittest
from unittest.mock import patch

from backend.managers.mgr_download import DownloadTask
from backend.managers.mgr_update import GithubSource, UpdateInfo, UpdateManager, UpdateSourceError


class StubUpdateSource:
    def __init__(self, info):
        self.info = info

    def check(self):
        return self.info


class FailingUpdateSource:
    def check(self):
        raise UpdateSourceError("更新源不可用")


class StubDownloadManager:
    def __init__(self):
        self.tasks = []

    def add_task(self, **kwargs):
        self.tasks.append(kwargs)
        return f"task-{len(self.tasks)}"


class TestGithubUpdateSource(unittest.TestCase):
    def test_check_returns_github_release_asset_update(self):
        source = GithubSource("Ink-Feather-362/RimModManager")
        releases = [
            {
                "tag_name": "v0.22.7",
                "name": "v0.22.7",
                "draft": False,
                "prerelease": False,
                "body": "修复问题",
                "published_at": "2026-06-25T00:00:00Z",
                "assets": [
                    {"name": "source.zip", "browser_download_url": "https://example.invalid/source.zip", "size": 10},
                    {
                        "name": "RimModManager-v0.22.7-windows.zip",
                        "browser_download_url": "https://example.invalid/app.zip",
                        "size": 67227285,
                        "digest": "sha256:abc123",
                    },
                ],
            }
        ]

        with patch("backend.managers.mgr_update.__version__", "0.22.6"), \
            patch("backend.managers.mgr_update.platform.system", return_value="Windows"), \
            patch.object(source.github_mgr, "fetch_release", return_value=releases[0]):
            info = source.check()

        self.assertIsNotNone(info)
        self.assertEqual(info.version, "0.22.7")
        self.assertEqual(info.download_url, "https://example.invalid/app.zip")
        self.assertEqual(info.source_name, "GitHub")
        self.assertEqual(info.file_hash, "abc123")
        self.assertEqual(info.hash_algorithm, "sha256")
        self.assertEqual(info.file_size, "64.1 MB")

    def test_check_ignores_same_version_release(self):
        source = GithubSource("Ink-Feather-362/RimModManager")
        releases = [
            {
                "tag_name": "v0.22.6",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "RimModManager-v0.22.6-windows.zip",
                        "browser_download_url": "https://example.invalid/app.zip",
                    }
                ],
            }
        ]

        with patch("backend.managers.mgr_update.__version__", "0.22.6"), patch.object(source.github_mgr, "fetch_release", return_value=releases[0]):
            info = source.check()

        self.assertIsNone(info)

    def test_check_ignores_prerelease_by_default(self):
        source = GithubSource("Ink-Feather-362/RimModManager")
        releases = [
            {
                "tag_name": "v0.22.7",
                "draft": False,
                "prerelease": True,
                "assets": [
                    {
                        "name": "RimModManager-v0.22.7-windows.zip",
                        "browser_download_url": "https://example.invalid/app.zip",
                    }
                ],
            }
        ]

        with patch("backend.managers.mgr_update.__version__", "0.22.6"), patch.object(source.github_mgr, "fetch_release", return_value=releases[0]):
            info = source.check()

        self.assertIsNone(info)

    def test_select_asset_prefers_current_system(self):
        source = GithubSource("Ink-Feather-362/RimModManager")
        assets = [
            {"name": "RimModManager-v0.22.7-windows.zip", "browser_download_url": "https://example.invalid/windows.zip"},
            {"name": "RimModManager-v0.22.7-linux.zip", "browser_download_url": "https://example.invalid/linux.zip"},
            {"name": "RimModManager-v0.22.7.zip", "browser_download_url": "https://example.invalid/generic.zip"},
        ]

        with patch("backend.managers.mgr_update.platform.system", return_value="Linux"):
            asset = source._select_asset(assets)

        self.assertIsNotNone(asset)
        self.assertEqual(asset["browser_download_url"], "https://example.invalid/linux.zip")


class TestUpdateManagerSources(unittest.TestCase):
    def _manager_with_sources(self, infos):
        manager = UpdateManager()
        manager.sources = [StubUpdateSource(info) for info in infos]
        manager.download_mgr = StubDownloadManager()
        manager.current_update_info = None
        manager.active_download_task_id = None
        manager.active_download_version = None
        manager.download_contexts = {}
        return manager

    def test_check_all_keeps_same_latest_version_sources_in_priority_order(self):
        lanzou = UpdateInfo(True, "0.22.7", "蓝奏云更新", "https://example.invalid/lanzou.zip", "蓝奏云", file_size="64 MB")
        github = UpdateInfo(True, "0.22.7", "## GitHub 更新", "https://example.invalid/github.zip", "GitHub", file_size="64.1 MB")
        manager = self._manager_with_sources([lanzou, github])

        with patch("backend.managers.mgr_update.__version__", "0.22.6"), patch.object(manager, "_find_cached_file", return_value=None):
            info = manager.check_all()

        self.assertEqual(info.source_name, "蓝奏云")
        self.assertEqual(info.version, "0.22.7")
        self.assertEqual([source["source_name"] for source in info.sources], ["蓝奏云", "GitHub"])

    def test_check_all_only_keeps_highest_version_sources(self):
        lanzou = UpdateInfo(True, "0.22.7", "蓝奏云更新", "https://example.invalid/lanzou.zip", "蓝奏云")
        github = UpdateInfo(True, "0.22.8", "## GitHub 更新", "https://example.invalid/github.zip", "GitHub")
        manager = self._manager_with_sources([lanzou, github])

        with patch("backend.managers.mgr_update.__version__", "0.22.6"), patch.object(manager, "_find_cached_file", return_value=None):
            info = manager.check_all()

        self.assertEqual(info.source_name, "GitHub")
        self.assertEqual(info.version, "0.22.8")
        self.assertEqual([source["source_name"] for source in info.sources], ["GitHub"])

    def test_download_error_tries_next_same_version_source(self):
        manager = self._manager_with_sources([])
        manager.current_update_info = UpdateInfo(
            True,
            "0.22.7",
            "蓝奏云更新",
            "https://example.invalid/lanzou.zip",
            "蓝奏云",
            sources=[
                UpdateInfo(True, "0.22.7", "蓝奏云更新", "https://example.invalid/lanzou.zip", "蓝奏云").to_source_dict(),
                UpdateInfo(True, "0.22.7", "## GitHub 更新", "https://example.invalid/github.zip", "GitHub", file_hash="abc", hash_algorithm="sha256").to_source_dict(),
            ],
        )
        first = manager.perform_update_download()
        failed_task = DownloadTask(url="https://example.invalid/lanzou.zip", dest_path="")
        failed_task.task_id = first["task_id"]
        failed_task.error_msg = "网络错误"
        failed_task.metadata = manager.download_mgr.tasks[0]["metadata"]

        with patch("backend.managers.mgr_update.EventBus.emit_progress"):
            manager._on_download_error(failed_task)

        self.assertEqual(len(manager.download_mgr.tasks), 2)
        self.assertTrue(manager.download_mgr.tasks[0]["metadata"]["has_fallback_source"])
        self.assertEqual(manager.current_update_info.source_name, "GitHub")
        self.assertEqual(manager.download_mgr.tasks[1]["url"], "https://example.invalid/github.zip")
        self.assertEqual(manager.download_mgr.tasks[1]["expected_hash"], "abc")
        self.assertEqual(manager.download_mgr.tasks[1]["hash_algorithm"], "sha256")
        self.assertFalse(manager.download_mgr.tasks[1]["metadata"]["has_fallback_source"])

    def test_check_all_raises_when_all_remote_sources_fail(self):
        manager = self._manager_with_sources([])
        manager.sources = [FailingUpdateSource(), FailingUpdateSource()]

        with patch("backend.managers.mgr_update.__version__", "0.22.6"):
            with self.assertRaises(UpdateSourceError):
                manager.check_all()

    def test_check_all_marks_partial_when_no_update_but_one_source_failed(self):
        manager = self._manager_with_sources([])
        manager.sources = [StubUpdateSource(None), FailingUpdateSource()]

        with patch("backend.managers.mgr_update.__version__", "0.22.6"):
            info = manager.check_all()

        self.assertFalse(info.has_update)
        self.assertEqual(info.check_status, "partial")
        self.assertEqual([result["status"] for result in info.source_results], ["no_update", "failed"])

    def test_repeated_download_returns_active_task(self):
        manager = self._manager_with_sources([])
        manager.current_update_info = UpdateInfo(True, "0.22.7", "更新", "https://example.invalid/lanzou.zip", "蓝奏云")

        first = manager.perform_update_download()
        second = manager.perform_update_download()

        self.assertEqual(first["task_id"], second["task_id"])
        self.assertEqual(len(manager.download_mgr.tasks), 1)

    def test_download_complete_uses_task_snapshot(self):
        manager = self._manager_with_sources([])
        original = UpdateInfo(True, "0.22.7", "蓝奏云更新", "https://example.invalid/lanzou.zip", "蓝奏云")
        manager.current_update_info = original
        started = manager.perform_update_download()
        manager.current_update_info = UpdateInfo(True, "0.22.8", "GitHub 更新", "https://example.invalid/github.zip", "GitHub")

        task = DownloadTask(url="https://example.invalid/lanzou.zip", dest_path="F:/tmp/update_v0.22.7.zip")
        task.task_id = started["task_id"]

        with patch("backend.managers.mgr_update.os.path.exists", return_value=True), \
            patch.object(manager, "_save_metadata_file"), \
            patch.object(manager, "_clean_old_cache"), \
            patch("backend.managers.mgr_update.EventBus.emit_progress"):
            manager._on_download_complete(task)

        self.assertEqual(manager.current_update_info.version, "0.22.7")
        self.assertEqual(manager.current_update_info.source_name, "蓝奏云")
        self.assertEqual(manager.current_update_info.local_status, "ready")


if __name__ == "__main__":
    unittest.main()
