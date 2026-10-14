import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.api import API
from backend.managers.mgr_github import GithubManager


class TestGithubApi(unittest.TestCase):
    def setUp(self):
        self.api = API.__new__(API)
        self.api._api_call_lock = threading.Lock()
        self.api._api_call_threads = {}
        self.api.github_mgr = GithubManager()
        self.api.github_mgr.record_timeline = Mock()
        self.api.github_mgr.fetch_repo_info = Mock(return_value={"source_status": "available", "latest_source_branch": "dev"})
        self.api.github_trigger_download = Mock(return_value={"status": "success", "data": {"task_id": "task-1"}})
        self.api.github_get_subscribed = Mock(return_value={"status": "success", "data": []})

    def test_github_subscribe_starts_download_after_record_is_saved(self):
        api = self.api
        record = SimpleNamespace(save=Mock())

        with patch("backend.api.GithubModRecord.get_or_create", return_value=(record, True)), \
             patch("backend.api.db.atomic"):
            result = api.github_subscribe({
                "url": "https://github.com/team/mod",
                "owner": "team",
                "repo": "mod",
                "default_branch": "dev",
                "install_type": "source",
            })

        api.github_trigger_download.assert_called_once_with("https://github.com/team/mod", "source", "dev")
        self.assertEqual(result["status"], "success")

    def test_switch_branch_keeps_installed_version_and_reports_download_start_failure(self):
        record = SimpleNamespace(owner="team", repo_name="mod", installed_version="master@old", save=Mock())
        self.api.github_trigger_download.return_value = {"status": "error", "message": "download failed"}
        with patch("backend.api.GithubModRecord.get_or_create", return_value=(record, False)), \
             patch("backend.api.db.atomic"):
            result = self.api.github_subscribe({
                "url": "https://gitgud.io/team/mod.git", "default_branch": "feature/1.7", "install_type": "source",
                "info": {"source_status": "available", "latest_source_branch": "feature/1.7"},
            })
        self.assertEqual(record.target_branch, "feature/1.7")
        self.assertEqual(record.installed_version, "master@old")
        self.api.github_trigger_download.assert_called_once_with("https://gitgud.io/team/mod", "source", "feature/1.7")
        self.assertEqual(result["status"], "error")
        self.api.github_get_subscribed.assert_not_called()

    def test_missing_source_branch_does_not_change_subscription_or_start_download(self):
        self.api.github_mgr.fetch_repo_info.return_value = {"source_status": "missing"}
        with patch("backend.api.GithubModRecord.get_or_create") as save:
            result = self.api.github_subscribe({
                "url": "https://github.com/team/mod", "default_branch": "missing", "install_type": "source",
                "info": {"source_status": "missing"},
            })
        self.assertEqual(result["status"], "error")
        save.assert_not_called()
        self.api.github_trigger_download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
