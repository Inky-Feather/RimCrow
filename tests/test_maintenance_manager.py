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


def test_external_dataset_prefers_github_signature_over_size(tmp_path):
    path = tmp_path / "communityRules.json"
    path.write_text('{"timestamp": 1777950016, "rules": {}}', encoding="utf-8")

    manager = MaintenanceManager.__new__(MaintenanceManager)
    local_signature = manager._compute_git_blob_sha(path)
    manager._resolve_local_dataset_version = lambda data_type: "1777950016000"
    manager._probe_remote_file = lambda url: {
        "supported": True,
        "available": True,
        "signature": local_signature,
        "size": path.stat().st_size + 100,
        "version": local_signature[:12],
    }

    result = manager._check_external_dataset(
        {
            "data_type": "community_rules",
            "name": "社区规则库",
            "path_key": "community_rules_path",
            "url_key": "community_rules_url",
        },
        {
            "community_rules_path": str(path),
            "community_rules_url": "https://github.com/example/repo/blob/main/communityRules.json",
        },
    )

    assert result["needs_update"] is False
    assert result["comparison_mode"] == "signature"
    assert result["local_signature_short"] == local_signature[:12]
    assert result["remote_signature_short"] == local_signature[:12]


def test_external_dataset_size_fallback_ignores_generic_etag(tmp_path):
    path = tmp_path / "external.json"
    path.write_text('{"version": "1"}', encoding="utf-8")

    manager = MaintenanceManager.__new__(MaintenanceManager)
    manager._resolve_local_dataset_version = lambda data_type: "1"
    manager._probe_remote_file = lambda url: {
        "supported": True,
        "available": True,
        "etag": "not-the-local-git-blob-sha",
        "size": path.stat().st_size,
    }

    result = manager._check_external_dataset(
        {
            "data_type": "workshop_db",
            "name": "社区工坊数据库",
            "path_key": "community_workshop_db_path",
            "url_key": "community_workshop_db_url",
        },
        {
            "community_workshop_db_path": str(path),
            "community_workshop_db_url": "https://example.invalid/external.json",
        },
    )

    assert result["needs_update"] is False
    assert result["comparison_mode"] == "size"
    assert result["remote_signature"] == ""
    assert result["remote_etag"] == "not-the-local-git-blob-sha"


def test_mp_compat_generated_cache_uses_source_etag(tmp_path):
    path = tmp_path / "mpCompatPackageIds.json"
    path.write_text(
        '{"package_ids": ["example.mod"], "source": {"etag": "source-etag", "updated_at": 1777950016000}}',
        encoding="utf-8",
    )

    manager = MaintenanceManager.__new__(MaintenanceManager)
    manager._probe_remote_file = lambda url: {
        "supported": True,
        "available": True,
        "etag": "source-etag",
        "size": path.stat().st_size + 1000,
        "updated_at": 1777950026000,
    }

    result = manager._check_external_dataset(
        {
            "data_type": "mp_compat_package_ids",
            "name": "Multiplayer Compatibility 适配缓存",
            "path_key": "mp_compat_package_ids_path",
            "url_key": "mp_compat_package_ids_url",
        },
        {
            "mp_compat_package_ids_path": str(path),
            "mp_compat_package_ids_url": "https://example.invalid/source.zip",
        },
    )

    assert result["needs_update"] is False
    assert result["comparison_mode"] == "source_etag"


def test_external_dataset_list_includes_multiplayer_sources():
    data_types = {spec["data_type"] for spec in MaintenanceManager.EXTERNAL_DATASETS}

    assert "multiplayer_compatibility" in data_types
    assert "mp_compat_package_ids" in data_types


def test_external_data_check_includes_git_provider_catalog():
    manager = MaintenanceManager.__new__(MaintenanceManager)
    manager.EXTERNAL_DATASETS = ()
    manager.github_mgr = type("FakeGithubManager", (), {
        "check_provider_catalog_updates": lambda self, url: {
            "sources": [
                {
                    "source_id": "rjw",
                    "label": "RJW",
                    "exists": True,
                    "remote_available": True,
                    "needs_update": True,
                }
            ],
            "local_signature": "local-signature",
            "remote_signature": "remote-signature",
            "local_count": 1,
            "remote_count": 2,
            "needs_update": True,
            "remote_available": True,
        }
    })()

    result = manager.check_external_data({"git_provider_catalog_url": "RJW|https://example.invalid/providers.json"})

    assert result["has_updates"] is True
    assert result["updates"][0]["data_type"] == "git_provider_catalog"
    assert result["updates"][0]["comparison_mode"] == "signature"
    assert result["updates"][0]["source_labels"] == ["RJW"]


def test_generic_external_probe_keeps_etag_separate(monkeypatch):
    class _FakeResponse:
        url = "https://example.invalid/external.json"
        headers = {
            "ETag": '"etag-value"',
            "Content-Length": "42",
            "Last-Modified": "Wed, 11 Jun 2025 12:00:00 GMT",
        }

        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def raise_for_status(self): return None

    class _FakeSession:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def head(self, *args, **kwargs): return _FakeResponse()

    monkeypatch.setattr(mgr_maintenance, "build_retry_session", lambda: _FakeSession())

    manager = MaintenanceManager.__new__(MaintenanceManager)
    result = manager._probe_generic_file("https://example.invalid/external.json")

    assert result["etag"] == "etag-value"
    assert "signature" not in result
    assert result["size"] == 42


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
