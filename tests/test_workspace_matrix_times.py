import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from backend.api import API
from backend.database.models import GithubModRecord, GithubTimeline, ModAsset, UserModData, db
from backend.settings import settings
from backend.utils.tools import normalize_path_for_storage


class TestWorkspaceMatrixTimes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.self_mods_path = Path(self.temp_dir.name) / "SelfMods"
        original_self_mods_path = settings.config.self_mods_path
        self.addCleanup(setattr, settings.config, "self_mods_path", original_self_mods_path)
        settings.config.self_mods_path = str(self.self_mods_path)
        db_path = str(Path(self.temp_dir.name) / "workspace-matrix-times.db")
        db.init(db_path)
        db.connect(reuse_if_open=True)
        db.create_tables([ModAsset, UserModData, GithubModRecord, GithubTimeline])

    def tearDown(self):
        if not db.is_closed():
            db.close()

    def _api(self):
        api = API.__new__(API)
        api.active_context = SimpleNamespace(local_mods_path="", game_dlc_path="", use_workshop_mods=True, use_self_mods=True)
        api.steam_mgr = SimpleNamespace(workshop_merged_data=Mock(return_value={}), steamcmd_merged_data=Mock(return_value={}))
        api.workshop_db_mgr = SimpleNamespace(get_replacements=Mock(return_value=[]))
        api._bg_probe_missing_workshop_items = Mock()
        api._bg_check_online_updates = Mock()
        return api

    def test_workspace_domains_adds_git_download_time_to_self_mod_from_success_timeline(self):
        mod_path = str(self.self_mods_path / "_GH_TestRepo")
        ModAsset.create(
            path_hash="git-hash",
            package_id="author.gitmod",
            name="Git Mod",
            path=mod_path,
            source="github",
            store="self",
        )
        GithubModRecord.create(
            repo_url="https://github.com/user/TestRepo",
            provider="github",
            host="github.com",
            owner="user",
            repo_name="TestRepo",
            install_type="source",
            target_branch="main",
            installed_version="main@2026-01-02T03:04:05Z",
            local_folder="_GH_TestRepo",
            last_sync_time=111,
        )
        GithubTimeline.create(
            repo_url="https://github.com/user/TestRepo",
            action="success",
            message="部署成功",
            time=222,
        )

        res = self._api().workspace_get_all_domains()

        mod = res["data"]["self"][0]
        self.assertEqual(mod["download_status"]["download_time"], 222)
        self.assertEqual(mod["download_status"]["source"], "github_timeline_success")
        self.assertEqual(mod["download_status"]["installed_version"], "main@2026-01-02T03:04:05Z")

    def test_github_get_subscribed_returns_normalized_local_path(self):
        local_path = self.self_mods_path / "_GH_TestRepo"
        local_path.mkdir(parents=True)
        GithubModRecord.create(
            repo_url="https://github.com/user/TestRepo",
            provider="github",
            host="github.com",
            owner="user",
            repo_name="TestRepo",
            install_type="source",
            target_branch="main",
            local_folder="_GH_TestRepo",
        )
        api = self._api()
        api.github_mgr = SimpleNamespace(detect_repo_provider=Mock(return_value=("github", "github.com")), record_timeline=Mock())
        api._schedule_github_subs_refresh = Mock(return_value=False)

        res = API.github_get_subscribed(api)

        record = res["data"][0]
        self.assertEqual(record["local_path"], normalize_path_for_storage(local_path))
        self.assertTrue(record["local_exists"])

    def test_workspace_domains_uses_steamcmd_sync_time_as_download_time(self):
        ModAsset.create(
            path_hash="cmd-hash",
            package_id="author.cmdmod",
            name="SteamCMD Mod",
            path=str(Path(self.temp_dir.name) / "SelfMods" / "123"),
            source="workshop",
            store="self",
            workshop_id="123",
        )
        api = self._api()
        api.steam_mgr.steamcmd_merged_data.return_value = {
            "123": {
                "workshop_id": "123",
                "time_downloaded": None,
                "time_last_sync": 333,
                "installed_version_time": 222,
                "latest_version_time": 444,
            }
        }

        res = api.workspace_get_all_domains()

        mod = res["data"]["self"][0]
        self.assertIsNone(mod["steam_status"]["time_downloaded"])
        self.assertEqual(mod["download_status"], {"download_time": 333, "source": "steam_sync_log"})

    def test_workspace_domains_uses_workshop_sync_time_as_download_time(self):
        ModAsset.create(
            path_hash="workshop-hash",
            package_id="author.workshopmod",
            name="Workshop Mod",
            path=str(Path(self.temp_dir.name) / "Workshop" / "456"),
            source="workshop",
            store="workshop",
            workshop_id="456",
        )
        api = self._api()
        api.steam_mgr.workshop_merged_data.return_value = {
            "456": {
                "workshop_id": "456",
                "time_downloaded": None,
                "time_last_sync": 555,
                "installed_version_time": 444,
                "latest_version_time": 666,
            }
        }

        res = api.workspace_get_all_domains()

        mod = res["data"]["workshop"][0]
        self.assertIsNone(mod["steam_status"]["time_downloaded"])
        self.assertEqual(mod["download_status"], {"download_time": 555, "source": "steam_sync_log"})


if __name__ == "__main__":
    unittest.main()
