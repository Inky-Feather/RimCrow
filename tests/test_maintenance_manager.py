from backend.managers import mgr_maintenance
from backend.managers.mgr_maintenance import MaintenanceManager


class _FakeGithubQuery:
    def __init__(self, rows):
        self.rows = rows

    def dicts(self):
        return list(self.rows)


class _FakeGithubRecord:
    rows = []

    @classmethod
    def select(cls):
        return _FakeGithubQuery(cls.rows)


def test_tool_version_compare_is_conservative():
    assert MaintenanceManager._is_version_outdated("ripgrep 14.0.3", "14.1.1") is True
    assert MaintenanceManager._is_version_outdated("14.1.1", "v14.1.1") is False
    assert MaintenanceManager._is_version_outdated("", "v14.1.1") is False


def test_github_mod_update_check_uses_cached_versions(monkeypatch):
    # 启动期维护检查不能为了弹窗阻塞主界面，这里只读取订阅缓存来判断是否需要提示。
    _FakeGithubRecord.rows = [
        {
            "repo_url": "https://github.com/example/release-mod",
            "repo_name": "release-mod",
            "install_type": "release",
            "installed_version": "v1.0.0",
            "online_info_cache": {"latest_release_tag": "v1.1.0"},
        },
        {
            "repo_url": "https://github.com/example/source-mod",
            "repo_name": "source-mod",
            "install_type": "source",
            "target_branch": "main",
            "installed_version": "main@1000",
            "online_info_cache": {"latest_source_version": "main@2000", "latest_source_branch": "main"},
        },
        {
            "repo_url": "https://github.com/example/current-mod",
            "repo_name": "current-mod",
            "install_type": "release",
            "installed_version": "v1.0.0",
            "online_info_cache": {"latest_release_tag": "v1.0.0"},
        },
    ]
    monkeypatch.setattr(mgr_maintenance, "GithubModRecord", _FakeGithubRecord)

    manager = MaintenanceManager.__new__(MaintenanceManager)
    updates = manager._check_github_mod_updates()

    assert [item["repo_url"] for item in updates] == [
        "https://github.com/example/release-mod",
        "https://github.com/example/source-mod",
    ]
    assert updates[0]["target_version"] == "v1.1.0"
    assert updates[1]["target_version"] == "main"


def test_github_source_update_check_skips_when_local_is_newer(monkeypatch):
    _FakeGithubRecord.rows = [
        {
            "repo_url": "https://github.com/example/source-mod",
            "repo_name": "source-mod",
            "install_type": "source",
            "target_branch": "main",
            "installed_version": "main@2025-07-04T09:07:38Z",
            "online_info_cache": {"latest_source_version": "main@2025-06-27T04:22:57Z", "latest_source_branch": "main"},
        },
        {
            "repo_url": "https://github.com/example/outdated-source-mod",
            "repo_name": "outdated-source-mod",
            "install_type": "source",
            "target_branch": "main",
            "installed_version": "main@2025-06-27T04:22:57Z",
            "online_info_cache": {"latest_source_version": "main@2025-07-04T09:07:38Z", "latest_source_branch": "main"},
        },
    ]
    monkeypatch.setattr(mgr_maintenance, "GithubModRecord", _FakeGithubRecord)

    manager = MaintenanceManager.__new__(MaintenanceManager)
    updates = manager._check_github_mod_updates()

    assert [item["repo_url"] for item in updates] == ["https://github.com/example/outdated-source-mod"]


def test_managed_mod_update_check_combines_steamcmd_and_github(monkeypatch):
    _FakeGithubRecord.rows = [
        {
            "repo_url": "https://github.com/example/mod",
            "repo_name": "mod",
            "install_type": "release",
            "installed_version": "v1.0.0",
            "online_info_cache": {"latest_release_tag": "v1.2.0"},
        }
    ]
    monkeypatch.setattr(mgr_maintenance, "GithubModRecord", _FakeGithubRecord)

    manager = MaintenanceManager.__new__(MaintenanceManager)
    manager.check_steamcmd_mod_updates = lambda: {"updates": [{"workshop_id": "123", "title": "steam mod"}]}

    result = manager.check_managed_mod_updates()

    assert result["count"] == 2
    assert result["steamcmd_count"] == 1
    assert result["github_count"] == 1
    assert {item["source"] for item in result["updates"]} == {"steamcmd", "github"}
