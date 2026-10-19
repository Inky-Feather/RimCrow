import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.managers.mgr_github import GithubManager
from backend.settings import AppConfig, SettingsManager, normalize_github_mirrors, settings


@pytest.fixture(autouse=True)
def isolated_mirror_state(monkeypatch, tmp_path):
    # 镜像刷新会写缓存并修改类级状态，测试不得读写用户缓存或影响后续用例。
    monkeypatch.setattr("backend.managers.mgr_github.GITHUB_MIRROR_CATALOG_CACHE_PATH", tmp_path / "mirror_catalog.json")
    monkeypatch.setattr(GithubManager, "_mirror_catalog_loaded", True)
    monkeypatch.setattr(GithubManager, "_mirror_catalog", {"status": "idle", "mirrors": []})
    monkeypatch.setattr(GithubManager, "_mirror_catalog_stop", threading.Event())
    monkeypatch.setattr(GithubManager, "_mirror_cooldowns", {})
    monkeypatch.setattr(GithubManager, "_response_cache", {})
    monkeypatch.setattr(settings.config, "github_mirror_id", "direct")
    monkeypatch.setattr(settings.config, "github_dynamic_mirrors_enabled", False)
    monkeypatch.setattr(settings.config, "github_mirrors", [])


class TestGithubMirrorCatalog(unittest.TestCase):
    def test_refresh_filters_remote_failures_before_local_probe(self):
        groups = {
            "ghproxy_next": ([
                {"id": "good", "label": "Good", "url_template": "https://good.example/{url}", "url_mode": "full_url", "sources": ["ghproxy_next"], "remote_status": "unknown"},
            ], None),
            "hiwiki": ([
                {"id": "ok", "label": "OK", "url_template": "https://ok.example/{url}", "url_mode": "full_url", "sources": ["hiwiki"], "remote_status": "ok", "remote_latency_ms": 10},
            ], None),
        }

        def probe(template, target, url_mode="full_url"):
            return template, {"status": "supported", "http_status": 200}

        with patch.object(GithubManager, "_fetch_mirror_source", side_effect=lambda source: groups[source]), \
             patch.object(GithubManager, "_probe_mirror_url", side_effect=probe):
            payload = GithubManager.refresh_github_mirror_catalog(probe_limit=2)

        self.assertEqual(payload["status"], "ready")
        self.assertEqual({item["label"] for item in payload["mirrors"]}, {"Good", "OK"})
        self.assertTrue(all(item["health_status"] == "success" for item in payload["mirrors"]))

    def test_auto_mode_returns_multiple_dynamic_candidates_then_direct(self):
        old_id = settings.config.github_mirror_id
        old_dynamic_enabled = settings.config.github_dynamic_mirrors_enabled
        old_catalog = GithubManager._mirror_catalog
        self.addCleanup(setattr, settings.config, "github_mirror_id", old_id)
        self.addCleanup(setattr, settings.config, "github_dynamic_mirrors_enabled", old_dynamic_enabled)
        self.addCleanup(setattr, GithubManager, "_mirror_catalog", old_catalog)
        settings.config.github_mirror_id = "auto"
        settings.config.github_dynamic_mirrors_enabled = True
        GithubManager._mirror_catalog = {
            "status": "ready",
            "mirrors": [
                {"url_template": "https://fast.example/{url}", "url_mode": "full_url", "health_status": "success", "remote_latency_ms": 10, "support": {"archive": {"status": "supported"}}, "health": {"archive": {"status": "valid", "latency_ms": 10}}},
                {"url_template": "https://slow.example/{url}", "url_mode": "full_url", "health_status": "success", "remote_latency_ms": 20, "support": {"archive": {"status": "supported"}}, "health": {"archive": {"status": "valid", "latency_ms": 20}}},
            ],
        }
        self.assertEqual(
            GithubManager._github_download_candidates("https://github.com/a/b/archive/main.zip", "archive"),
            [
                "https://fast.example/https://github.com/a/b/archive/main.zip",
                "https://slow.example/https://github.com/a/b/archive/main.zip",
                "https://gh-proxy.org/https://github.com/a/b/archive/main.zip",
                "https://github.com/a/b/archive/main.zip",
            ],
        )

    def test_hiwiki_unknown_status_is_kept_for_local_probe(self):
        nodes = GithubManager._parse_hiwiki_nodes({"mirrors": [{
            "label": "Pending", "base": "https://pending.example", "pathPrefix": "https://github.com",
            "status": "pending", "latency": 20,
        }]})
        self.assertEqual(nodes[0]["remote_status"], "unknown")


class TestGithubMirrorPool(unittest.TestCase):
    def setUp(self):
        settings.config.github_mirrors = [{
            "id": "custom", "label": "Custom", "url_template": "https://custom.example/{url}",
            "support": {"web": {"status": "supported"}},
            "health": {"web": {"status": "valid", "latency_ms": 80}},
        }]
        GithubManager._mirror_catalog = {"status": "ready", "mirrors": [{
            "id": "dynamic", "label": "Dynamic", "url_template": "https://dynamic.example/{url}",
            "origin": "dynamic", "support": {"web": {"status": "supported"}},
            "health": {"web": {"status": "valid", "latency_ms": 10}},
        }]}

    def test_selection_returns_one_node_or_auto_pool(self):
        settings.config.github_dynamic_mirrors_enabled = True
        self.assertEqual([n["origin"] for n in GithubManager.get_effective_mirrors("custom:custom", "web")], ["custom"])
        self.assertEqual([n["origin"] for n in GithubManager.get_effective_mirrors("dynamic:dynamic", "web")], ["dynamic"])
        self.assertEqual([n["origin"] for n in GithubManager.get_effective_mirrors("auto", "web")], ["dynamic", "custom"])

    def test_auto_uses_cached_health_and_never_refreshes(self):
        with patch.object(GithubManager, "start_mirror_catalog_refresh") as refresh:
            self.assertEqual(GithubManager._github_download_candidates("https://github.com/a/b", "web")[0], "https://github.com/a/b")
            refresh.assert_not_called()
        settings.config.github_mirror_id = "auto"
        settings.config.github_dynamic_mirrors_enabled = True
        candidates = GithubManager._github_download_candidates("https://github.com/a/b", "web")
        self.assertEqual(candidates[:2], [
            "https://dynamic.example/https://github.com/a/b",
            "https://custom.example/https://github.com/a/b",
        ])


class TestGithubMirrorProbe(unittest.TestCase):
    def test_builtin_defines_all_capabilities_and_only_gh_proxy(self):
        from backend.settings import GITHUB_MIRROR_CAPABILITIES
        nodes = GithubManager._builtin_mirrors()
        self.assertEqual([node["url_template"] for node in nodes], ["https://gh-proxy.org/{url}"])
        self.assertEqual(set(nodes[0]["support"]), set(GITHUB_MIRROR_CAPABILITIES))
        self.assertEqual(nodes[0]["support"]["api"]["status"], "supported")
        self.assertEqual(nodes[0]["support"]["web"]["status"], "unsupported")

    def test_probe_accepts_gist_raw_and_rejects_html_substitute(self):
        for body, content_type, expected in ((b"# Compiled source", "text/plain", "supported"), (b"<html>proxy home</html>", "text/html", "unsupported")):
            with self.subTest(expected=expected):
                response = MagicMock(status_code=200, url="https://mirror.example/gist")
                response.headers = {"Content-Type": content_type}
                response.iter_content.return_value = iter([body[:5], body[5:]])
                response.__enter__.return_value = response
                with patch("backend.managers.mgr_github.build_retry_session") as build:
                    build.return_value.__enter__.return_value.get.return_value = response
                    _, result = GithubManager._probe_mirror_url("https://mirror.example/{url}", "https://gist.githubusercontent.com/octocat/9257657/raw")
                self.assertEqual(result["status"], expected)

    def test_gist_pages_do_not_inherit_raw_content_support(self):
        for url in ("https://gist.github.com/octocat/9257657", "https://gist.github.com/octocat/raw"):
            self.assertEqual(GithubManager.github_url_capability(url), "web")
            with patch.object(settings.config, "github_mirror_id", "builtin:gh_proxy"):
                self.assertEqual(GithubManager._github_download_candidates(url), [url])
        for url in ("https://gist.github.com/octocat/9257657/raw", "https://gist.github.com/octocat/9257657/raw/file.txt", "https://gist.githubusercontent.com/octocat/9257657/raw"):
            self.assertEqual(GithubManager.github_url_capability(url), "gist")
            with patch.object(settings.config, "github_mirror_id", "builtin:gh_proxy"):
                self.assertEqual(GithubManager._github_download_candidates(url), [f"https://gh-proxy.org/{url}", url])

    def setUp(self):
        self.manager = GithubManager()

    def test_probe_records_each_capability_status(self):
        def probe(_template, target, _mode="full_url", **_kwargs):
            capability = self.manager.github_url_capability(target)
            return target, {"status": {"web": "supported", "raw": "unsupported"}.get(capability, "unknown"), "http_status": 200}

        with patch.object(GithubManager, "_probe_mirror_url", side_effect=probe):
            result = self.manager.probe_github_mirror({"url_template": "https://mirror.example/{url}"})

        self.assertEqual(result["support"]["web"]["status"], "supported")
        self.assertEqual(result["support"]["raw"]["status"], "unsupported")
        self.assertEqual(result["support"]["archive"]["status"], "unknown")
        self.assertEqual(result["support"]["release_asset"]["status"], "unknown")

    def test_unsupported_capability_uses_direct_only(self):
        with patch.object(settings.config, "github_mirror_id", "custom:custom"), patch.object(
            settings.config,
            "github_mirrors",
            [{"id": "custom", "url_template": "https://mirror.example/{url}", "support": {"web": {"status": "unsupported"}}}],
        ):
            self.assertEqual(
                self.manager._github_download_candidates("https://github.com/team/mod", "web"),
                ["https://github.com/team/mod"],
            )

    def test_repo_page_falls_back_after_mirror_404(self):
        mirror_response = MagicMock(status_code=404, text="")
        direct_response = MagicMock(status_code=200, text="<html>ok</html>")
        session = MagicMock()
        session.get.side_effect = [mirror_response, direct_response]
        manager = MagicMock()
        manager.__enter__.return_value = session
        manager.__exit__.return_value = None

        with patch.object(settings.config, "github_mirror_id", "custom:custom"), patch.object(
            settings.config,
            "github_mirrors",
            [{"id": "custom", "url_template": "https://mirror.example/{url}", "support": {"web": {"status": "supported"}}}],
        ), patch("backend.managers.mgr_github.build_retry_session", return_value=manager):
            payload = self.manager.fetch_repo_page("team", "mod", missing_ok=True)

        self.assertEqual(payload, "<html>ok</html>")
        self.assertEqual([call.args[0] for call in session.get.call_args_list], [
            "https://mirror.example/https://github.com/team/mod",
            "https://github.com/team/mod",
        ])


class TestGithubMirrorSettings(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.mirror_path = Path(directory.name) / "github_mirrors.json"
        self.config_path = Path(directory.name) / "config.json"
        for name, value in (("GITHUB_MIRRORS_PATH", self.mirror_path), ("CONFIG_PATH", self.config_path)):
            patcher = patch(f"backend.settings.{name}", value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.manager = object.__new__(SettingsManager)
        self.manager.config = AppConfig()
        self.manager._save_lock = threading.Lock()
        self.manager._sync_derived_paths = lambda: None
        self.manager.get_secret_status = lambda: {}
        self.custom = {"id": "custom", "label": "自定义", "url_template": "https://example.org/{url}", "support": {"raw": {"status": "supported"}}}

    def test_hosts_sources_defaults_and_legacy_migration(self):
        defaults = AppConfig().network.hosts_sources
        self.assertEqual([row["url"] for row in defaults], [
            "https://raw.hellogithub.com/hosts",
            "https://cdn.jsdelivr.net/gh/Clov614/SteamHostSync@main/Hosts_steam",
        ])
        self.assertTrue(all(row["enabled"] for row in defaults))
        for legacy, expected in (
            ("https://raw.hellogithub.com/hosts", defaults),
            ("https://custom.example/hosts\nhttps://second.example/hosts.json", [
                {"url": "https://custom.example/hosts", "enabled": True},
                {"url": "https://second.example/hosts.json", "enabled": True},
            ]),
        ):
            with self.subTest(legacy=legacy):
                fragment = self.manager._parse_config_fragment({"network": {"github_hosts_url": legacy}})
                self.manager._apply_config_fragment(fragment)
                self.assertEqual(self.manager.config.network.hosts_sources, expected)
                self.assertNotIn("github_hosts_url", self.manager.to_storage_dict()["network"])

    def test_empty_or_disabled_hosts_sources_survive_config_roundtrip(self):
        for sources in ([], [{"url": " https://custom.example/hosts ", "enabled": False}]):
            with self.subTest(sources=sources):
                fragment = self.manager._parse_config_fragment({"network": {"hosts_sources": sources, "github_hosts_url": "https://old.example/hosts"}})
                self.manager._apply_config_fragment(fragment)
                stored = self.manager.to_storage_dict()
                self.manager._apply_config_fragment(self.manager._parse_config_fragment(stored))
                self.assertEqual(self.manager.config.network.hosts_sources, [
                    {**row, "url": row["url"].strip()} for row in sources
                ])

    def test_legacy_migration_and_edit_persist_in_separate_file(self):
        self.manager.config.github_mirrors = [self.custom]
        self.manager.config.github_mirror_id = "custom:custom"
        self.manager._load_github_mirrors()
        self.assertEqual(json.loads(self.mirror_path.read_text("utf-8"))["mirrors"][0]["support"], self.custom["support"])
        self.manager.update_from_dict({"github_mirrors": [{**self.custom, "label": "新名称"}]})
        stored = json.loads(self.config_path.read_text("utf-8"))
        self.assertNotIn("github_mirrors", stored)
        self.assertEqual(stored["github_mirror_id"], "custom:custom")
        self.assertEqual(json.loads(self.mirror_path.read_text("utf-8"))["mirrors"][0]["label"], "新名称")
        public = self.manager.to_public_dict()
        self.assertEqual(public["_github_mirrors_path"], str(self.mirror_path))
        self.assertEqual(public["github_mirrors"][0]["label"], "新名称")

    def test_independent_file_wins_and_preserves_selection_on_startup(self):
        self.mirror_path.write_text(json.dumps({"mirrors": [self.custom]}), encoding="utf-8")
        self.manager.config.github_mirror_id = "custom:custom"
        self.manager._normalize_config()
        self.manager._load_github_mirrors()
        self.assertEqual(self.manager.config.github_mirror_id, "custom:custom")
        self.assertEqual(self.manager.config.github_mirrors[0]["support"], self.custom["support"])
        self.manager.update_from_dict({"github_mirrors": []})
        self.assertEqual(self.manager.config.github_mirror_id, "direct")
        self.manager._load_github_mirrors()
        self.assertEqual(self.manager.config.github_mirrors, [])

    def test_invalid_file_and_invalid_edits_do_not_destroy_saved_data(self):
        self.mirror_path.write_text("{broken", encoding="utf-8")
        self.manager._load_github_mirrors()
        self.manager.save()
        self.assertEqual(self.mirror_path.read_text("utf-8"), "{broken")
        self.assertIn("github_mirrors", self.manager.to_storage_dict())
        original = list(self.manager.config.github_mirrors)
        for override in (
            {"id": "direct"}, {"url_template": "http://example.org/{url}"},
            {"url_template": "https://example.org/{url}/{url}"}, {"support": {"unknown-capability": {"status": "supported"}}},
            {"url_template": "https://user@example.org/{url}"},
            {"url_template": "https://example.org:99999/{url}"},
            {"url_template": "https://{url}.example.org/"},
        ):
            with self.subTest(override=override), self.assertRaises((ValueError, TypeError)):
                self.manager.update_from_dict({"github_mirrors": [{**self.custom, **override}]})
            self.assertEqual(self.manager.config.github_mirrors, original)
            self.assertEqual(self.mirror_path.read_text("utf-8"), "{broken")
        with self.assertRaises(ValueError):
            normalize_github_mirrors([self.custom, self.custom], strict=True)

    def test_extended_capabilities_are_valid(self):
        mirror = {**self.custom, "support": {key: {"status": "supported"} for key in ("api", "git_clone", "gist", "lfs_media")}, "url_mode": "github_path"}
        self.assertEqual(set(normalize_github_mirrors([mirror], strict=True)[0]["support"]), {"api", "git_clone", "gist", "lfs_media"})

    def test_https_mirror_may_use_valid_nonstandard_port(self):
        mirror = {**self.custom, "url_template": "https://mirror.example:8443/{url}"}
        self.assertEqual(normalize_github_mirrors([mirror], strict=True)[0]["url_template"], mirror["url_template"])

    def test_failed_migration_keeps_legacy_list_in_main_config(self):
        self.manager.config.github_mirrors = [self.custom]
        with patch("backend.settings.write_json_atomic", side_effect=PermissionError("read only")):
            self.manager._load_github_mirrors()
        self.assertEqual(self.manager.to_storage_dict()["github_mirrors"][0]["support"], self.custom["support"])


if __name__ == "__main__":
    unittest.main()
