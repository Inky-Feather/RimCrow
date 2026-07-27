import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.api import API


class TestGithubApi(unittest.TestCase):
    def test_github_subscribe_starts_download_after_record_is_saved(self):
        api = API.__new__(API)
        api._api_call_lock = threading.Lock()
        api._api_call_threads = {}
        api.github_mgr = SimpleNamespace(
            detect_repo_provider=Mock(return_value=("github", "github.com")),
            record_timeline=Mock(),
        )
        api.github_trigger_download = Mock(return_value={"status": "success", "data": {"task_id": "task-1"}})
        api.github_get_subscribed = Mock(return_value={"status": "success", "data": []})
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


if __name__ == "__main__":
    unittest.main()
