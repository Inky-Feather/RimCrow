import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.managers.mgr_download import DownloadTask
from backend.managers.mgr_update import GithubSource, LanzouSource, LocalSource, UpdateInfo, UpdateManager, UpdateSourceError, _build_configured_update_sources
from backend.utils.lanzou_parser import LanzouParser


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
        source = GithubSource("Inky-Feather/RimCrow")
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
                        "name": "RimCrow-v0.22.7-windows.zip",
                        "browser_download_url": "https://example.invalid/app.zip",
                        "size": 67227285,
                        "digest": "sha256:abc123",
                    },
                ],
            }
        ]

        with patch("backend.managers.mgr_update.__version__", "0.22.6"), \
            patch("backend.utils.tools.platform.system", return_value="Windows"), \
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
        source = GithubSource("Inky-Feather/RimCrow")
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
        source = GithubSource("Inky-Feather/RimCrow")
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
        source = GithubSource("Inky-Feather/RimCrow")
        assets = [
            {"name": "RimModManager-v0.22.7-windows.zip", "browser_download_url": "https://example.invalid/windows.zip"},
            {"name": "RimCrow-v0.22.7-linux.zip", "browser_download_url": "https://example.invalid/linux.zip"},
            {"name": "RimCrow-v0.22.7.zip", "browser_download_url": "https://example.invalid/generic.zip"},
        ]

        with patch("backend.utils.tools.platform.system", return_value="Linux"):
            asset = source._select_asset(assets)

        self.assertIsNotNone(asset)
        self.assertEqual(asset["browser_download_url"], "https://example.invalid/linux.zip")


class TestLanzouUpdatePackageNames(unittest.TestCase):
    def _file(self, name, file_id):
        return {"id": file_id, "name_all": name, "size": "64 MB", "time": "2026-06-26"}

    def test_select_latest_accepts_old_name_without_platform(self):
        parser = LanzouParser()
        files = [
            parser._build_file_info(self._file("RimModManager_v0.22.7.zip", "old")),
            parser._build_file_info(self._file("readme.txt", "txt")),
        ]

        with patch("backend.utils.tools.platform.system", return_value="Windows"):
            latest = parser._select_latest_update_file(files)

        self.assertIsNotNone(latest)
        self.assertEqual(latest["id"], "old")
        self.assertEqual(latest["version"], "0.22.7")
        self.assertFalse(latest["platform_matched"])

    def test_select_latest_prefers_current_system_for_new_name(self):
        parser = LanzouParser()

        with patch("backend.utils.tools.platform.system", return_value="Windows"):
            files = [
                parser._build_file_info(self._file("RimCrow-v0.22.8-linux.zip", "linux")),
                parser._build_file_info(self._file("RimCrow-v0.22.7-windows.zip", "windows")),
                parser._build_file_info(self._file("RimModManager_v0.22.6.zip", "old")),
            ]
            latest = parser._select_latest_update_file(files)

        self.assertIsNotNone(latest)
        self.assertEqual(latest["id"], "windows")
        self.assertEqual(latest["version"], "0.22.7")
        self.assertTrue(latest["platform_matched"])

    def test_select_latest_supports_new_name_without_v_prefix(self):
        parser = LanzouParser()

        with patch("backend.utils.tools.platform.system", return_value="Windows"):
            info = parser._build_file_info(self._file("RimCrow-0.22.8-win64.zip", "win64"))

        self.assertTrue(info["is_update_package"])
        self.assertTrue(info["platform_compatible"])
        self.assertEqual(info["version"], "0.22.8")

    def test_select_latest_ignores_unknown_zip_with_version(self):
        parser = LanzouParser()

        with patch("backend.utils.tools.platform.system", return_value="Windows"):
            files = [
                parser._build_file_info(self._file("OtherTool-v9.9.9-windows.zip", "other")),
                parser._build_file_info(self._file("RimCrow-v0.22.8-windows.zip", "rimcrow")),
            ]
            latest = parser._select_latest_update_file(files)

        self.assertIsNotNone(latest)
        self.assertEqual(latest["id"], "rimcrow")
        self.assertEqual(latest["version"], "0.22.8")


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

    def test_hot_swap_from_rimmodmanager_launches_rimcrow_exe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            install_root = root / "app"
            install_root.mkdir()
            current_exe = install_root / "RimModManager.exe"
            current_exe.write_text("old", encoding="utf-8")
            zip_path = root / "update.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("RimCrow/RimCrow.exe", "new")

            manager = self._manager_with_sources([])
            with patch("backend.managers.mgr_update.sys.executable", str(current_exe)), \
                patch("backend.managers.mgr_update.backup_config_for_update"), \
                patch("backend.managers.mgr_update.launch_new_application") as launch_mock, \
                patch("backend.managers.mgr_update.os._exit", side_effect=SystemExit):
                with self.assertRaises(SystemExit):
                    manager.execute_hot_swap(str(zip_path))

            new_exe = install_root / "RimCrow.exe"
            self.assertTrue(new_exe.exists())
            self.assertTrue((install_root / "RimModManager.exe.old").exists())
            launch_mock.assert_called_once_with(str(new_exe))


class TestConfiguredUpdateSources(unittest.TestCase):
    def test_build_configured_update_sources_reads_project_meta(self):
        sources = _build_configured_update_sources({
            "project": {"github_repo": "Inky-Feather/RimCrow"},
            "update": {
                "sources": [
                    {"type": "lanzou", "url": "https://example.invalid/lanzou", "password": "abcd"},
                    {"type": "github"},
                ]
            },
        })

        self.assertEqual(len(sources), 3)
        self.assertIsInstance(sources[0], LocalSource)
        self.assertIsInstance(sources[1], LanzouSource)
        self.assertEqual(sources[1].url, "https://example.invalid/lanzou")
        self.assertEqual(sources[1].pwd, "abcd")
        self.assertIsInstance(sources[2], GithubSource)
        self.assertEqual(sources[2].repo, "Inky-Feather/RimCrow")

    def test_build_configured_update_sources_falls_back_when_meta_missing(self):
        sources = _build_configured_update_sources({})

        self.assertEqual(len(sources), 3)
        self.assertIsInstance(sources[0], LocalSource)
        self.assertIsInstance(sources[1], LanzouSource)
        self.assertIsInstance(sources[2], GithubSource)


if __name__ == "__main__":
    unittest.main()
