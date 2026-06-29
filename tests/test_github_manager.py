import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from backend.managers.mgr_download import DownloadTask
from backend.managers.mgr_github import (
    GIT_PROVIDER_GITHUB,
    GIT_PROVIDER_GITLAB,
    GITHUB_ARTIFACT_RELEASE_ASSET,
    GITHUB_ARTIFACT_SOURCE_ARCHIVE,
    GITHUB_INSTALL_EXTRACT,
    GITHUB_INSTALL_EXTRACT_THEN_MOVE,
    GITHUB_RESOLVER_MOD_ROOT,
    GITHUB_SOURCE_TAG,
    GithubArtifactRequest,
    GithubRateLimitError,
    GithubInstallPlan,
    GithubInstallRequest,
    GithubManager,
    GithubResolvedArtifact,
)
from backend.managers.mgr_texture_opt import TODDS_WINDOWS_ASSET_PREFIX, TextureOptimizationManager
from backend.settings import settings


class TestGithubManager(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        self.manager = GithubManager()
        GithubManager._response_cache.clear()

    def _create_zip(self, zip_path: Path, entries: dict[str, str]) -> None:
        with ZipFile(zip_path, "w") as archive:
            for relative_path, content in entries.items():
                archive.writestr(relative_path, content)

    def test_select_release_asset_matches_prefix_and_suffix(self):
        asset = self.manager._select_release_asset(
            [
                {"name": "todds_Linux_0.5.0.zip", "browser_download_url": "https://example.invalid/linux.zip"},
                {"name": "todds_Windows_0.5.0.zip", "browser_download_url": "https://example.invalid/windows.zip"},
            ],
            GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                asset_name_prefix=TODDS_WINDOWS_ASSET_PREFIX,
                asset_name_suffix=".zip",
            ),
        )

        self.assertIsNotNone(asset)
        self.assertEqual(asset["name"], "todds_Windows_0.5.0.zip")

    def test_select_release_asset_falls_back_to_single_zip_when_prefix_does_not_match(self):
        asset = self.manager._select_release_asset(
            [
                {"name": "modbundle-1.2.3.zip", "browser_download_url": "https://example.invalid/modbundle.zip"},
                {"name": "notes.txt", "browser_download_url": "https://example.invalid/notes.txt"},
            ],
            GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                asset_name_prefix="repo",
                asset_name_suffix=".zip",
            ),
        )

        self.assertIsNotNone(asset)
        self.assertEqual(asset["name"], "modbundle-1.2.3.zip")

    def test_parse_git_repo_url_supports_gitlab_multilevel_namespace(self):
        identity = self.manager.parse_git_repo_url("https://gitgud.io/group/subgroup/rjw/-/tree/Dev")

        self.assertIsNotNone(identity)
        self.assertEqual(identity.provider, GIT_PROVIDER_GITLAB)
        self.assertEqual(identity.host, "gitgud.io")
        self.assertEqual(identity.owner, "group/subgroup")
        self.assertEqual(identity.repo, "rjw")
        self.assertEqual(identity.path, "group/subgroup/rjw")

    def test_parse_git_repo_url_keeps_github_compatibility(self):
        identity = self.manager.parse_git_repo_url("https://github.com/user/repo.git")

        self.assertIsNotNone(identity)
        self.assertEqual(identity.provider, GIT_PROVIDER_GITHUB)
        self.assertEqual(identity.host, "github.com")
        self.assertEqual(identity.owner, "user")
        self.assertEqual(identity.repo, "repo")

    def test_resolve_source_archive_uses_default_branch_when_missing_ref(self):
        request = GithubInstallRequest(
            owner="user",
            repo="repo",
            artifact=GithubArtifactRequest(kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE),
        )

        with patch.object(self.manager, "fetch_repo", return_value={"default_branch": "dev"}), \
             patch.object(
                 self.manager,
                 "fetch_commit",
                 return_value={"commit": {"author": {"date": "2026-04-16T03:22:11Z"}}},
             ):
            resolved = self.manager._resolve_source_archive(request)

        self.assertEqual(resolved.version, "dev@2026-04-16T03:22:11Z")
        self.assertTrue(resolved.download_url.endswith("/archive/refs/heads/dev.zip"))
        self.assertEqual(resolved.filename, "repo_dev_source.zip")

    def test_fetch_repo_info_includes_source_version_for_target_branch(self):
        with patch.object(self.manager, "fetch_repo", return_value={"default_branch": "main"}), \
             patch.object(self.manager, "fetch_latest_release", return_value={"tag_name": "v1.2.3", "name": "v1.2.3", "published_at": "2026-04-15T10:00:00Z"}), \
             patch.object(
                 self.manager,
                 "fetch_commit",
                 return_value={
                     "sha": "abcdef123456",
                     "commit": {"author": {"date": "2026-04-16T03:22:11Z"}},
                 },
             ):
            info = self.manager.fetch_repo_info("https://github.com/user/repo", source_branch="dev")

        self.assertEqual(info["latest_source_branch"], "dev")
        self.assertEqual(info["latest_source_commit_sha"], "abcdef123456")
        self.assertEqual(info["latest_source_commit_at"], "2026-04-16T03:22:11Z")
        self.assertEqual(info["latest_source_version"], "dev@2026-04-16T03:22:11Z")
        self.assertEqual(info["latest_release_published_at"], "2026-04-15T10:00:00Z")
        self.assertEqual(info["info_source"], "api")
        self.assertFalse(info["is_degraded"])

    def test_extract_commit_timestamp_prefers_committer_date(self):
        timestamp = self.manager._extract_commit_timestamp({
            "commit": {
                "author": {"date": "2025-06-27T04:22:57Z"},
                "committer": {"date": "2025-07-04T09:07:38Z"},
            }
        })

        self.assertEqual(timestamp, "2025-07-04T09:07:38Z")

    def test_fetch_gitlab_repo_info_maps_to_common_payload(self):
        identity = self.manager.parse_git_repo_url("https://gitgud.io/Ed86/rjw")
        self.assertIsNotNone(identity)

        with patch.object(self.manager, "fetch_gitlab_project", return_value={"default_branch": "Dev"}), \
             patch.object(
                 self.manager,
                 "fetch_gitlab_release",
                 return_value={
                     "tag_name": "v1.2.3",
                     "name": "v1.2.3",
                     "released_at": "2026-04-15T10:00:00Z",
                     "assets": {
                         "sources": [
                             {"format": "zip", "url": "https://gitgud.io/Ed86/rjw/-/archive/v1.2.3/rjw-v1.2.3.zip"}
                         ],
                         "links": [],
                     },
                 },
             ), \
             patch.object(
                 self.manager,
                 "fetch_gitlab_commit",
                 return_value={
                     "id": "abcdef123456",
                     "committed_date": "2026-04-16T03:22:11Z",
                 },
             ):
            info = self.manager.fetch_repo_info("https://gitgud.io/Ed86/rjw", source_branch="Dev")

        self.assertEqual(info["provider"], GIT_PROVIDER_GITLAB)
        self.assertEqual(info["host"], "gitgud.io")
        self.assertEqual(info["owner"], "Ed86")
        self.assertEqual(info["repo"], "rjw")
        self.assertEqual(info["default_branch"], "Dev")
        self.assertEqual(info["latest_release_tag"], "v1.2.3")
        self.assertEqual(info["latest_release_published_at"], "2026-04-15T10:00:00Z")
        self.assertEqual(info["latest_source_version"], "Dev@2026-04-16T03:22:11Z")

    def test_provider_catalog_normalizes_rjw_git_and_zip_items(self):
        catalog = self.manager._normalize_provider_catalog_payload(
            {
                "version": 1,
                "authors": {
                    "author-a": {
                        "display_name": "Author A",
                        "donation_urls": [],
                        "extra_urls": [],
                    }
                },
                "providers": {
                    "root": {
                        "rjw": {
                            "type": "git",
                            "name": "rjw",
                            "display_name": "RJW",
                            "description": "Core mod",
                            "url": "https://gitgud.io/Ed86/rjw.git",
                            "branch": "Dev",
                            "mod_id": "rim.job.world",
                            "authors": ["author-a"],
                            "tags": ["core"],
                        }
                    },
                    "bodies": {
                        "rimnude": {
                            "type": "zip",
                            "name": "rimnude",
                            "description": "Zip package",
                            "url": "https://gitgud.io/api/v4/projects/1/packages/generic/rimnude/latest/rimnude.zip",
                            "subdir": "Rimnude-unofficial+",
                            "depends": ["rim.job.world"],
                            "disabled": True,
                        }
                    },
                },
            },
            source_url="https://example.invalid/providers.json",
        )

        items = {item["key"]: item for item in catalog["items"]}
        self.assertEqual(catalog["total"], 2)
        self.assertEqual(items["rjw"]["url"], "https://gitgud.io/Ed86/rjw")
        self.assertEqual(items["rjw"]["branch"], "Dev")
        self.assertEqual(items["rjw"]["name"], "RJW")
        self.assertEqual(items["rjw"]["package_id"], "rim.job.world")
        self.assertEqual(items["rjw"]["author"], ["Author A"])
        self.assertTrue(items["rimnude"]["not_recommended"])
        self.assertNotIn("is_installable", items["rimnude"])
        self.assertNotIn("availability", items["rimnude"])
        self.assertNotIn("availability_reason", items["rimnude"])
        self.assertNotIn("ecosystem", items["rimnude"])
        self.assertNotIn("catalog_source", items["rimnude"])
        self.assertNotIn("source_label", items["rimnude"])
        self.assertNotIn("display_name", items["rimnude"])
        self.assertNotIn("mod_id", items["rimnude"])
        self.assertNotIn("disabled", items["rimnude"])
        self.assertEqual(items["rimnude"]["subdir"], "Rimnude-unofficial+")
        self.assertEqual(items["rimnude"]["depends"], ["rim.job.world"])
        self.assertNotIn("dependency_items", items["rimnude"])

    def test_provider_catalog_sources_support_multiple_rows_and_builtin_owner(self):
        original_provider_catalog_url = settings.config.git_provider_catalog_url
        settings.config.git_provider_catalog_url = "RJW|https://example.invalid/rjw.json\nOther|https://example.invalid/other.json"
        self.addCleanup(setattr, settings.config, "git_provider_catalog_url", original_provider_catalog_url)

        sources = self.manager._provider_catalog_sources()

        self.assertEqual([source["label"] for source in sources], ["RJW", "Other", "Mlie"])
        self.assertEqual([source["type"] for source in sources], ["provider_json", "provider_json", "github_owner"])
        self.assertEqual(len({source["id"] for source in sources}), 3)
        self.assertEqual(sources[2]["owner"], "emipa606")

    def test_provider_catalog_source_ids_do_not_collide_for_same_label(self):
        sources = self.manager._parse_provider_json_sources(
            "RJW|https://example.invalid/first.json\nRJW|https://example.invalid/second.json"
        )

        self.assertEqual([source["label"] for source in sources], ["RJW", "RJW"])
        self.assertEqual(len({source["id"] for source in sources}), 2)

    def test_provider_catalog_update_check_compares_cache_with_remote_without_saving(self):
        source = self.manager._parse_provider_json_sources("RJW|https://example.invalid/providers.json")[0]
        cached_catalog = {
            "source": {"id": source["id"], "label": "RJW", "type": "provider_json", "count": 1},
            "items": [{"key": "old", "name": "Old"}],
        }
        remote_catalog = {
            "source": {"id": source["id"], "label": "RJW", "type": "provider_json", "count": 1},
            "items": [{"key": "new", "name": "New"}],
        }

        with patch("backend.managers.mgr_github.GIT_PROVIDER_CATALOG_DIR", self.temp_root):
            self.manager._save_provider_catalog_source_cache(source["id"], cached_catalog)
            with patch.object(self.manager, "_provider_catalog_sources", return_value=[source]), \
                 patch.object(self.manager, "_fetch_provider_catalog_source_remote", return_value=remote_catalog):
                result = self.manager.check_provider_catalog_updates()

            saved_catalog = self.manager._load_provider_catalog_source_cache(source["id"])

        self.assertTrue(result["needs_update"])
        self.assertTrue(result["remote_available"])
        self.assertEqual(result["sources"][0]["local_count"], 1)
        self.assertEqual(result["sources"][0]["remote_count"], 1)
        self.assertNotEqual(result["sources"][0]["local_signature"], result["sources"][0]["remote_signature"])
        self.assertEqual(saved_catalog["items"], cached_catalog["items"])

    def test_provider_catalog_update_check_marks_missing_cache_as_update(self):
        source = self.manager._parse_provider_json_sources("RJW|https://example.invalid/providers.json")[0]
        remote_catalog = {
            "source": {"id": source["id"], "label": "RJW", "type": "provider_json", "count": 1},
            "items": [{"key": "new", "name": "New"}],
        }

        with patch("backend.managers.mgr_github.GIT_PROVIDER_CATALOG_DIR", self.temp_root), \
             patch.object(self.manager, "_provider_catalog_sources", return_value=[source]), \
             patch.object(self.manager, "_fetch_provider_catalog_source_remote", return_value=remote_catalog):
            result = self.manager.check_provider_catalog_updates()

        self.assertTrue(result["needs_update"])
        self.assertFalse(result["sources"][0]["exists"])
        self.assertEqual(result["sources"][0]["remote_count"], 1)

    def test_github_owner_repo_detects_rimworld_mod_description(self):
        repo_item, checked_about = self.manager._normalize_github_owner_repo_item(
            {
                "name": "ExampleMod",
                "description": "Repository for the Rimworld mod ExampleMod",
                "homepage": "",
                "topics": [],
                "html_url": "https://github.com/emipa606/ExampleMod",
                "clone_url": "https://github.com/emipa606/ExampleMod.git",
                "default_branch": "main",
                "owner": {"login": "emipa606"},
                "fork": False,
                "archived": False,
            },
            session=object(),
            checked_about_count=0,
        )

        self.assertFalse(checked_about)
        self.assertIsNotNone(repo_item)
        self.assertNotIn("ecosystem", repo_item)
        self.assertNotIn("catalog_source", repo_item)
        self.assertNotIn("source_label", repo_item)
        self.assertEqual(repo_item["name"], "ExampleMod")
        self.assertEqual(repo_item["author"], ["emipa606"])
        self.assertNotIn("detected_by", repo_item)
        self.assertEqual(repo_item["url"], "https://github.com/emipa606/ExampleMod")

    def test_github_owner_repo_detects_steam_workshop_link(self):
        repo_item, checked_about = self.manager._normalize_github_owner_repo_item(
            {
                "name": "ExampleMod",
                "description": "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890",
                "homepage": "",
                "topics": [],
                "html_url": "https://github.com/emipa606/ExampleMod",
                "clone_url": "https://github.com/emipa606/ExampleMod.git",
                "default_branch": "main",
                "owner": {"login": "emipa606"},
                "fork": False,
                "archived": False,
            },
            session=object(),
            checked_about_count=0,
        )

        self.assertFalse(checked_about)
        self.assertNotIn("detected_by", repo_item)
        self.assertEqual(repo_item["workshop_url"], "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890")

    def test_fetch_github_readme_returns_empty_when_missing(self):
        class FakeResponse:
            status_code = 404

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def get(self, *_args, **_kwargs):
                return FakeResponse()

        identity = self.manager.parse_git_repo_url("https://github.com/example/NoReadme")
        self.assertIsNotNone(identity)
        with patch.object(self.manager, "fetch_repo", return_value={"default_branch": "main"}), \
             patch("backend.managers.mgr_github.build_retry_session", return_value=FakeSession()):
            result = self.manager._fetch_github_readme(identity, ref="", timeout=(1, 1))

        self.assertFalse(result["found"])
        self.assertEqual(result["content"], "")

    def test_builtin_github_owner_rule_supports_regex_fields(self):
        source = {
            "id": "custom",
            "label": "Custom",
            "match": {
                "description": [],
                "homepage": [],
                "name": [r"^RW_.+"],
                "topics": [r"rimworld-mod"],
                "about_xml": False,
            },
        }
        repo_item, checked_about = self.manager._normalize_github_owner_repo_item(
            {
                "name": "RW_Example",
                "description": "",
                "homepage": "",
                "topics": [],
                "html_url": "https://github.com/example/RW_Example",
                "clone_url": "https://github.com/example/RW_Example.git",
                "default_branch": "main",
                "owner": {"login": "example"},
                "fork": False,
                "archived": False,
            },
            session=object(),
            checked_about_count=0,
            source=source,
        )

        self.assertFalse(checked_about)
        self.assertIsNotNone(repo_item)
        self.assertNotIn("detected_by", repo_item)

    def test_fetch_repo_info_falls_back_to_web_sources_when_api_rate_limited(self):
        web_payload = {
            "owner": "user",
            "repo": "repo",
            "default_branch": "main",
            "has_release": True,
            "latest_release_tag": "v9.9.9",
            "latest_release_name": "v9.9.9",
            "release_zip_url": "https://github.com/user/repo/archive/refs/tags/v9.9.9.zip",
            "latest_source_branch": "main",
            "latest_source_commit_sha": "deadbeef",
            "latest_source_commit_at": "2026-04-16T08:00:00Z",
            "latest_source_version": "main@2026-04-16T08:00:00Z",
            "info_source": "web",
            "is_degraded": True,
        }

        with patch.object(self.manager, "_fetch_repo_info_via_api", side_effect=GithubRateLimitError("rate limited")), \
             patch.object(self.manager, "_fetch_repo_info_via_web", return_value=web_payload):
            info = self.manager.fetch_repo_info("https://github.com/user/repo")

        self.assertEqual(info["info_source"], "web")
        self.assertTrue(info["is_degraded"])
        self.assertEqual(info["latest_release_tag"], "v9.9.9")
        self.assertEqual(info["latest_source_version"], "main@2026-04-16T08:00:00Z")
        self.assertIn("rate limited", info["fetch_warning"])

    def test_execute_install_plan_extract_then_move_finds_mod_root(self):
        zip_path = self.temp_root / "repo_main_source.zip"
        self._create_zip(
            zip_path,
            {
                "repo-main/ExampleMod/About/About.xml": "<ModMetaData />",
                "repo-main/ExampleMod/Textures/a.png": "png",
            },
        )
        install_root = self.temp_root / "installed"
        request = GithubInstallRequest(
            repo_url="https://github.com/user/repo",
            owner="user",
            repo="repo",
            install=GithubInstallPlan(
                action=GITHUB_INSTALL_EXTRACT_THEN_MOVE,
                move_target_dir=str(install_root),
                final_name="_GH_repo",
                source_resolver=GITHUB_RESOLVER_MOD_ROOT,
                cleanup_archive=True,
            ),
        )
        task = DownloadTask(url="https://example.invalid/repo.zip", dest_path=str(zip_path), filename=zip_path.name)
        resolved = GithubResolvedArtifact(
            repo_url=request.repo_url,
            owner=request.owner,
            repo=request.repo,
            kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE,
            version="main",
            download_url=task.url,
            filename=zip_path.name,
        )

        result = self.manager._execute_install_plan(task, request, resolved)

        target = install_root / "_GH_repo"
        self.assertEqual(result.installed_path, str(target))
        self.assertTrue((target / "About" / "About.xml").exists())
        self.assertFalse(zip_path.exists())

    def test_resolve_install_source_accepts_subdir_below_archive_wrapper(self):
        temp_root = self.temp_root / "unzipped"
        mod_root = temp_root / "archive-wrapper" / "Rimnude-unofficial+"
        (mod_root / "About").mkdir(parents=True)
        (mod_root / "About" / "About.xml").write_text("<ModMetaData />", encoding="utf-8")

        source = self.manager._resolve_install_source(
            temp_root,
            GithubInstallPlan(
                source_resolver=GITHUB_RESOLVER_MOD_ROOT,
                source_subpath="Rimnude-unofficial+",
            ),
        )

        self.assertEqual(source, mod_root)

    def test_refresh_catalog_zip_signature_uses_remote_headers(self):
        class FakeResponse:
            status_code = 200
            headers = {
                "ETag": '"abc"',
                "Last-Modified": "Wed, 27 May 2026 01:00:00 GMT",
                "Content-Length": "123",
            }

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def head(self, *_args, **_kwargs):
                return FakeResponse()

        item = {
            "type": "zip",
            "name": "rimnude",
            "url": "https://example.invalid/rimnude.zip",
            "source_id": "rjw",
        }

        with patch("backend.managers.mgr_github.build_retry_session", return_value=FakeSession()):
            refreshed = self.manager._refresh_catalog_zip_signature(item)

        self.assertEqual(refreshed["remote_etag"], '"abc"')
        self.assertEqual(refreshed["remote_content_length"], "123")
        self.assertNotEqual(refreshed["catalog_signature"], self.manager._catalog_item_signature(item))

    def test_release_asset_resolution_uses_direct_fallback_when_api_fails(self):
        request = GithubInstallRequest(
            repo_url="https://github.com/todds-encoder/todds",
            owner="todds-encoder",
            repo="todds",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                asset_name_prefix="todds_Windows_",
                asset_name_suffix=".zip",
                fallback_download_url="https://github.com/todds-encoder/todds/releases/download/0.4.1/todds_Windows_0.4.1.zip",
                fallback_filename="todds_Windows_0.4.1.zip",
                fallback_version="0.4.1",
            ),
        )

        with patch.object(self.manager, "fetch_release", side_effect=GithubRateLimitError("rate limited")):
            resolved = self.manager._resolve_release_asset(request)

        self.assertEqual(resolved.version, "0.4.1")
        self.assertEqual(resolved.filename, "todds_Windows_0.4.1.zip")
        self.assertIn("/releases/download/0.4.1/", resolved.download_url)

    def test_parse_release_assets_from_html_extracts_download_links(self):
        html_text = """
        <section>
          <a href="/emipa606/XVIMECHFRAME/releases/download/1.6.3/XVIMECHFRAME_1.6.3.zip" class="Truncate">
            <span class="Truncate-text text-bold">XVIMECHFRAME_1.6.3.zip</span>
          </a>
        </section>
        """

        assets = self.manager._parse_release_assets_from_html(html_text)

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["name"], "XVIMECHFRAME_1.6.3.zip")
        self.assertEqual(
            assets[0]["browser_download_url"],
            "https://github.com/emipa606/XVIMECHFRAME/releases/download/1.6.3/XVIMECHFRAME_1.6.3.zip",
        )

    def test_resolve_release_asset_uses_web_assets_when_api_is_rate_limited(self):
        request = GithubInstallRequest(
            repo_url="https://github.com/emipa606/XVIMECHFRAME",
            owner="emipa606",
            repo="XVIMECHFRAME",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                release_tag="1.6.3",
                asset_name_prefix="XVIMECHFRAME",
                asset_name_suffix=".zip",
                fallback_download_url="https://github.com/emipa606/XVIMECHFRAME/archive/refs/tags/1.6.3.zip",
                fallback_filename="XVIMECHFRAME_1.6.3.zip",
                fallback_version="1.6.3",
            ),
        )

        with patch.object(self.manager, "fetch_release", side_effect=GithubRateLimitError("rate limited")), \
             patch.object(
                 self.manager,
                 "fetch_release_assets_web",
                 return_value={
                     "tag_name": "1.6.3",
                     "assets": [
                         {
                             "name": "XVIMECHFRAME_1.6.3.zip",
                             "browser_download_url": "https://github.com/emipa606/XVIMECHFRAME/releases/download/1.6.3/XVIMECHFRAME_1.6.3.zip",
                         }
                     ],
                 },
             ):
            resolved = self.manager._resolve_release_asset(request)

        self.assertEqual(resolved.version, "1.6.3")
        self.assertEqual(resolved.filename, "XVIMECHFRAME_1.6.3.zip")
        self.assertIn("/releases/download/1.6.3/", resolved.download_url)

    def test_resolve_gitlab_release_asset_prefers_matching_zip_link(self):
        request = GithubInstallRequest(
            repo_url="https://gitgud.io/Ed86/rjw",
            provider=GIT_PROVIDER_GITLAB,
            host="gitgud.io",
            project_path="Ed86/rjw",
            owner="Ed86",
            repo="rjw",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                release_tag="v1.2.3",
                asset_name_prefix="rjw",
                asset_name_suffix=".zip",
                fallback_download_url="https://gitgud.io/api/v4/projects/Ed86%2Frjw/repository/archive.zip?sha=v1.2.3",
                fallback_filename="rjw_v1.2.3.zip",
                fallback_version="v1.2.3",
            ),
        )

        with patch.object(
            self.manager,
            "fetch_gitlab_release",
            return_value={
                "tag_name": "v1.2.3",
                "assets": {
                    "links": [
                        {"name": "readme.txt", "url": "https://example.invalid/readme.txt"},
                        {"name": "rjw-v1.2.3.zip", "url": "https://example.invalid/rjw-v1.2.3.zip"},
                    ],
                    "sources": [
                        {"format": "zip", "url": "https://example.invalid/source.zip"},
                    ],
                },
            },
        ):
            resolved = self.manager._resolve_release_asset(request)

        self.assertEqual(resolved.version, "v1.2.3")
        self.assertEqual(resolved.filename, "rjw-v1.2.3.zip")
        self.assertEqual(resolved.download_url, "https://example.invalid/rjw-v1.2.3.zip")

    def test_resolve_gitlab_release_asset_falls_back_to_tag_source_zip(self):
        request = GithubInstallRequest(
            repo_url="https://gitlab.com/group/subgroup/repo",
            provider=GIT_PROVIDER_GITLAB,
            host="gitlab.com",
            project_path="group/subgroup/repo",
            owner="group/subgroup",
            repo="repo",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET,
                release_tag="v2",
                asset_name_prefix="repo",
                asset_name_suffix=".zip",
                fallback_download_url="https://gitlab.com/api/v4/projects/group%2Fsubgroup%2Frepo/repository/archive.zip?sha=v2",
                fallback_filename="repo_v2.zip",
                fallback_version="v2",
            ),
        )

        with patch.object(
            self.manager,
            "fetch_gitlab_release",
            return_value={
                "tag_name": "v2",
                "assets": {
                    "links": [{"name": "notes.txt", "url": "https://example.invalid/notes.txt"}],
                    "sources": [{"format": "zip", "url": "https://example.invalid/source.zip"}],
                },
            },
        ):
            resolved = self.manager._resolve_release_asset(request)

        self.assertEqual(resolved.version, "v2")
        self.assertEqual(resolved.filename, "repo_v2.zip")
        self.assertIn("repository/archive.zip?sha=v2", resolved.download_url)

    def test_install_repo_mod_builds_release_asset_request_for_release_mode(self):
        captured: dict[str, GithubInstallRequest] = {}
        download_mgr = object()
        original_self_mods_path = settings.config.self_mods_path
        settings.config.self_mods_path = str(self.temp_root / "self_mods")
        self.addCleanup(setattr, settings.config, "self_mods_path", original_self_mods_path)

        def fake_install(_download_mgr, request: GithubInstallRequest):
            captured["request"] = request
            return "task-1"

        with patch.object(self.manager, "install_from_github", side_effect=fake_install):
            task_id = self.manager.install_repo_mod(
                download_mgr, "https://github.com/user/repo", "release", "v1.2.3"
            )

        request = captured["request"]
        self.assertEqual(task_id, "task-1")
        self.assertEqual(request.artifact.kind, GITHUB_ARTIFACT_RELEASE_ASSET)
        self.assertEqual(request.artifact.release_tag, "v1.2.3")
        self.assertEqual(request.artifact.asset_name_prefix, "repo")
        self.assertEqual(request.artifact.asset_name_suffix, ".zip")
        self.assertIn("/archive/refs/tags/v1.2.3.zip", request.artifact.fallback_download_url)
        self.assertEqual(request.artifact.fallback_filename, "repo_v1.2.3.zip")
        self.assertEqual(request.install.final_name, "_GH_repo")

    def test_fetch_repo_info_raises_when_no_fallback_source_available(self):
        with patch.object(self.manager, "_fetch_repo_info_via_api", side_effect=GithubRateLimitError("rate limited")), \
             patch.object(self.manager, "_fetch_repo_info_via_web", return_value=None), \
             patch.object(self.manager, "_fetch_repo_info_from_record_cache", return_value=None):
            with self.assertRaises(GithubRateLimitError):
                self.manager.fetch_repo_info("https://github.com/user/repo")

    def test_resolve_source_archive_does_not_block_download_when_commit_lookup_fails(self):
        request = GithubInstallRequest(
            repo_url="https://github.com/user/repo",
            owner="user",
            repo="repo",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE,
                source_ref="dev",
            ),
        )

        with patch.object(self.manager, "fetch_commit", side_effect=GithubRateLimitError("rate limited")), \
             patch.object(self.manager, "fetch_commit_web", return_value=None), \
             patch.object(self.manager, "_fetch_repo_info_from_record_cache", return_value=None):
            resolved = self.manager._resolve_source_archive(request)

        self.assertEqual(resolved.version, "dev")
        self.assertTrue(resolved.download_url.endswith("/archive/refs/heads/dev.zip"))


class TestTextureOptGithubIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        self.manager = TextureOptimizationManager()

    def test_prepare_tool_download_delegates_to_github_install_plan(self):
        captured: dict[str, GithubInstallRequest] = {}
        download_mgr = object()

        def fake_install(_self, actual_download_mgr, request: GithubInstallRequest):
            captured["download_mgr"] = actual_download_mgr
            captured["request"] = request
            return "task-1"

        with patch("backend.managers.mgr_texture_opt.platform.system", return_value="Windows"), \
             patch.object(TextureOptimizationManager, "get_backend_status", return_value={"available": False}), \
             patch("backend.managers.mgr_github.GithubManager.install_from_github", new=fake_install):
            result = self.manager.prepare_tool_download(
                download_mgr,
                {"texture_tools_path": str(self.temp_root / "texture_tools")},
            )

        request = captured["request"]
        self.assertEqual(result, {"already_ready": False})
        self.assertIs(captured["download_mgr"], download_mgr)
        self.assertEqual(request.owner, "todds-encoder")
        self.assertEqual(request.repo, "todds")
        self.assertEqual(request.artifact.kind, GITHUB_ARTIFACT_RELEASE_ASSET)
        self.assertEqual(request.artifact.asset_name_prefix, TODDS_WINDOWS_ASSET_PREFIX)
        self.assertEqual(request.artifact.asset_name_suffix, ".zip")
        self.assertEqual(request.install.action, GITHUB_INSTALL_EXTRACT)
        self.assertEqual(request.install.extract_dir, str(self.temp_root / "texture_tools"))


if __name__ == "__main__":
    unittest.main()
