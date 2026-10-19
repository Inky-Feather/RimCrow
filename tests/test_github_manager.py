import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from zipfile import ZipFile

import requests

from backend.api import API
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
        patcher = patch.object(self.manager, "fetch_ref_commit", side_effect=self._mock_ref_commit)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("backend.managers.mgr_github.GithubModRecord.get_or_none", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(self.manager, "fetch_release_assets_web", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _mock_ref_commit(self, identity, ref, ref_type="branch", **kwargs):
        if identity.provider == GIT_PROVIDER_GITLAB:
            return self.manager.fetch_gitlab_commit(identity, ref=ref, missing_ok=True)
        return self.manager.fetch_commit(identity.owner, identity.repo, ref=ref, missing_ok=True)

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

    def test_github_download_mirror_routes_release_and_keeps_direct_fallback(self):
        with patch.object(settings.config, "github_mirror_id", "custom:custom"), patch.object(
            settings.config,
            "github_mirrors",
            [{"id": "custom", "label": "测试镜像", "url_template": "https://mirror.example/{url}", "support": {"release_asset": {"status": "supported"}}}],
        ):
            request = GithubInstallRequest(owner="team", repo="mod", artifact=GithubArtifactRequest(kind=GITHUB_ARTIFACT_RELEASE_ASSET))
            resolved = self.manager._build_release_asset_from_payload(
                request,
                {"tag_name": "v1", "assets": [{"name": "mod.zip", "browser_download_url": "https://github.com/team/mod/releases/download/v1/mod.zip"}]},
            )

        self.assertEqual(resolved.download_url, "https://mirror.example/https://github.com/team/mod/releases/download/v1/mod.zip")
        self.assertEqual(resolved.fallback_urls, ["https://github.com/team/mod/releases/download/v1/mod.zip"])

    def test_github_download_mirror_does_not_route_gitlab(self):
        with patch.object(settings.config, "github_mirror_id", "custom:custom"), patch.object(
            settings.config,
            "github_mirrors",
            [{"id": "custom", "url_template": "https://mirror.example/{url}", "support": {"release_asset": {"status": "supported"}}}],
        ):
            candidates = self.manager._github_download_candidates("https://gitlab.com/team/mod/-/archive/v1/mod.zip", "release_asset")
        self.assertEqual(candidates, ["https://gitlab.com/team/mod/-/archive/v1/mod.zip"])

    def test_github_download_mirror_routes_source_archive(self):
        request = GithubInstallRequest(
            owner="team",
            repo="mod",
            artifact=GithubArtifactRequest(kind=GITHUB_ARTIFACT_SOURCE_ARCHIVE, source_ref="main"),
        )
        with patch.object(settings.config, "github_mirror_id", "custom:custom"), patch.object(
            settings.config,
            "github_mirrors",
            [{"id": "custom", "url_template": "https://mirror.example/{url}", "support": {"archive": {"status": "supported"}}}],
        ), patch.object(self.manager, "fetch_commit", return_value={"sha": "a" * 40}):
            resolved = self.manager._resolve_source_archive(request)

        self.assertEqual(resolved.download_url, "https://mirror.example/https://github.com/team/mod/archive/" + "a" * 40 + ".zip")
        self.assertEqual(resolved.fallback_urls, ["https://github.com/team/mod/archive/" + "a" * 40 + ".zip"])

    def test_install_from_github_records_resolved_artifact_capability(self):
        cases = [
            (GITHUB_ARTIFACT_SOURCE_ARCHIVE, "archive"),
            (GITHUB_ARTIFACT_RELEASE_ASSET, "release_asset"),
        ]
        for artifact_kind, capability in cases:
            with self.subTest(artifact_kind=artifact_kind):
                resolved = GithubResolvedArtifact(
                    repo_url="https://github.com/team/mod",
                    owner="team",
                    repo="mod",
                    kind=artifact_kind,
                    version="v1",
                    download_url="https://mirror.example/artifact.zip",
                    filename="artifact.zip",
                    fallback_urls=["https://github.com/team/mod/artifact.zip"],
                )
                download_mgr = MagicMock()
                download_mgr.add_task.return_value = "task-id"
                with patch.object(self.manager, "_resolve_artifact", return_value=resolved), patch.object(self.manager, "record_timeline"), patch.object(self.manager, "record_mirror_result") as record:
                    result = self.manager.install_from_github(
                        download_mgr,
                        GithubInstallRequest(
                            owner="team",
                            repo="mod",
                            install=GithubInstallPlan(download_dir=str(self.temp_root)),
                        ),
                    )
                    self.assertEqual(result, "task-id")
                    callback = download_mgr.add_task.call_args.kwargs["on_source_result"]
                    callback("https://mirror.example/artifact.zip", False)
                    record.assert_called_once_with("https://mirror.example/artifact.zip", success=False, capability=capability)

    def test_fetch_file_metadata_recomputes_mirror_after_cache_hit(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"sha": "b" * 40, "size": 12, "download_url": "https://raw.githubusercontent.com/team/mod/main/data.json"}
        with patch("backend.managers.mgr_github.build_retry_session") as build, patch.object(
            self.manager, "fetch_path_commit", return_value=None
        ), patch.object(settings.config, "github_mirror_id", "direct"):
            build.return_value.__enter__.return_value.get.return_value = response
            direct = self.manager.fetch_file_metadata("team", "mod", ref="main", remote_path="data.json")

        self.assertEqual(direct["download_url"], "https://raw.githubusercontent.com/team/mod/main/data.json")
        with patch.object(settings.config, "github_mirror_id", "custom:custom"), patch.object(
            settings.config,
            "github_mirrors",
            [{"id": "custom", "url_template": "https://mirror.example/{url}", "support": {"raw": {"status": "supported"}}}],
        ):
            mirrored = self.manager.fetch_file_metadata("team", "mod", ref="main", remote_path="data.json")

        self.assertEqual(mirrored["download_url"], "https://mirror.example/https://raw.githubusercontent.com/team/mod/main/data.json")
        self.assertEqual(mirrored["fallback_urls"], ["https://raw.githubusercontent.com/team/mod/main/data.json"])

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

    def test_resolve_repo_link_matches_complete_branches_and_subdirectories(self):
        cases = [
            ("https://github.com/user/repo/tree/feature/rimworld?tab=readme", "feature/rimworld"),
            ("https://github.com/user/repo/tree/feature%2Frimworld/About", "feature/rimworld"),
            ("https://github.com/tree/repo/tree/dev/About", "dev"),
            ("https://github.com/user/tree/tree/dev/About", "dev"),
            ("gitgud.io/group/subgroup/repo/-/tree/dev/About", "dev"),
            ("https://gitlab.com/group/subgroup/repo/-/tree/feature/rimworld/Defs", "feature/rimworld"),
        ]
        def refs(_url, ref_type="branch"):
            return ["dev", "feature/rimworld"] if ref_type == "branch" else []

        with patch.object(self.manager, "fetch_repo_branches", side_effect=refs):
            for url, expected in cases:
                with self.subTest(url=url):
                    identity, branch, _, _ = self.manager.resolve_repo_location(url)
                    self.assertEqual(branch, expected)
                    self.assertEqual(identity.url, f"https://{identity.host}/{identity.path}")

    def test_resolve_repo_link_keeps_explicit_branch_and_does_not_guess_ambiguous_paths(self):
        with patch.object(self.manager, "fetch_repo_branches", return_value=["dev", "dev/tools"]) as fetch:
            self.assertEqual(self.manager.resolve_repo_location("https://github.com/user/repo", "")[1], "")
            self.assertEqual(self.manager.resolve_repo_location("https://github.com/user/repo/tree/old", "release/1.7")[1], "release/1.7")
            fetch.assert_not_called()
            with self.assertRaises(ValueError):
                self.manager.resolve_repo_location("https://github.com/user/repo/tree/dev/tools")
            with self.assertRaises(ValueError):
                self.manager.resolve_repo_location("https://github.com/user/repo/tree/dev/tools/About")
            with self.assertRaises(ValueError):
                self.manager.resolve_repo_location("https://github.com/user/repo/tree/nonexistent")

    def test_fetch_repo_info_uses_link_branch_and_returns_canonical_url(self):
        with patch.object(self.manager, "fetch_repo_branches", side_effect=lambda _url, ref_type="branch": ["dev"] if ref_type == "branch" else []), \
             patch.object(self.manager, "fetch_gitlab_project", return_value={"default_branch": "master"}), \
             patch.object(self.manager, "fetch_gitlab_release", return_value=None), \
             patch.object(self.manager, "fetch_gitlab_commit", return_value={"id": "abc"}) as commit:
            info = self.manager.fetch_repo_info("https://gitgud.io/team/repo/-/tree/dev/About")
        self.assertEqual(info["repo_url"], "https://gitgud.io/team/repo")
        self.assertEqual(info["latest_source_branch"], "dev")
        self.assertEqual(commit.call_args.kwargs["ref"], "dev")
        self.assertEqual(info["release_status"], "missing")

    def test_fetch_repo_branches_reads_all_pages_for_both_providers(self):
        for url, endpoint in [
            ("https://github.com/user/repo", "https://api.github.com/repos/user/repo/branches"),
            ("https://gitgud.io/group/sub/repo", "https://gitgud.io/api/v4/projects/group%2Fsub%2Frepo/repository/branches"),
        ]:
            with self.subTest(url=url):
                responses = [MagicMock(status_code=200), MagicMock(status_code=200)]
                responses[0].json.return_value = [{"name": f"branch-{i}"} for i in range(100)]
                responses[1].json.return_value = [{"name": "feature/rimworld"}]
                with patch("backend.managers.mgr_github.build_retry_session") as build:
                    session = build.return_value.__enter__.return_value
                    session.get.side_effect = responses
                    branches = self.manager.fetch_repo_branches(url)
                self.assertEqual(len(branches), 101)
                self.assertEqual(branches[-1], "feature/rimworld")
                self.assertEqual(session.get.call_args.args[0], endpoint)
                self.assertEqual(session.get.call_args.kwargs["params"]["page"], 2)
                self.assertEqual(session.get.call_args.kwargs["timeout"], (5, 20))

    def test_fetch_repo_branches_does_not_return_partial_results_on_failure(self):
        response = MagicMock(status_code=200)
        response.json.return_value = [{"name": f"branch-{i}"} for i in range(100)]
        with patch("backend.managers.mgr_github.build_retry_session") as build:
            build.return_value.__enter__.return_value.get.side_effect = [response, requests.HTTPError("403")]
            with self.assertRaises(requests.HTTPError):
                self.manager.fetch_repo_branches("https://gitgud.io/team/repo")

    def test_web_metadata_parses_release_redirect_and_commit_feed(self):
        release_response = MagicMock(status_code=302, headers={"Location": "https://github.com/user/repo/releases/tag/v1.2.3"})
        commit_response = MagicMock(status_code=200, text=(
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            '<id>https://github.com/user/repo/commit/abcdef1</id>'
            '</entry></feed>'
        ))
        with patch("backend.managers.mgr_github.build_retry_session") as build:
            session = build.return_value.__enter__.return_value
            session.get.side_effect = [release_response, commit_response]
            release = self.manager.fetch_release_web("user", "repo")
            commit = self.manager.fetch_commit_web("user", "repo", ref="main")

        self.assertEqual(release["tag_name"], "v1.2.3")
        self.assertEqual(commit["sha"], "abcdef1")
        self.assertEqual([call.args[0] for call in session.get.call_args_list], [
            "https://github.com/user/repo/releases/latest",
            "https://github.com/user/repo/commits/main.atom",
        ])

    def test_release_failure_preserves_cached_release_and_refreshes_source(self):
        cached = {"has_release": True, "latest_release_tag": "v1", "latest_source_branch": "master", "latest_source_commit_sha": "old"}
        with patch.object(self.manager, "fetch_gitlab_project", return_value={"default_branch": "master"}), \
             patch.object(self.manager, "fetch_gitlab_release", side_effect=requests.HTTPError("403 Forbidden")), \
             patch.object(self.manager, "fetch_gitlab_commit", return_value={"id": "new", "committed_date": "2026-04-16T03:22:11Z"}), \
             patch("backend.managers.mgr_github.GithubModRecord.get_or_none", return_value=SimpleNamespace(online_info_cache=cached)):
            info = self.manager.fetch_repo_info("https://gitgud.io/team/repo")
        self.assertEqual(info["release_status"], "error")
        self.assertEqual(info["latest_release_tag"], "v1")
        self.assertEqual(info["source_status"], "available")
        self.assertEqual(info["latest_source_commit_sha"], "new")
        self.assertTrue(info["is_degraded"])

    def test_source_failure_does_not_block_release_or_inherit_another_branch_commit(self):
        cached = {"latest_source_branch": "old", "latest_source_commit_sha": "oldsha", "latest_source_version": "old@2026-04-01"}
        with patch.object(self.manager, "fetch_repo", return_value={"default_branch": "main"}), \
             patch.object(self.manager, "fetch_release", return_value={"tag_name": "v2"}), \
             patch.object(self.manager, "fetch_commit", side_effect=requests.Timeout("timeout")), \
             patch("backend.managers.mgr_github.GithubModRecord.get_or_none", return_value=SimpleNamespace(online_info_cache=cached)):
            info = self.manager.fetch_repo_info("https://github.com/user/repo", source_branch="new")
        self.assertEqual(info["release_status"], "available")
        self.assertEqual(info["latest_release_tag"], "v2")
        self.assertEqual(info["source_status"], "error")
        self.assertEqual(info["latest_source_branch"], "new")
        self.assertEqual(info["latest_source_commit_sha"], "")

    def test_missing_release_is_different_from_release_api_failure(self):
        with patch.object(self.manager, "fetch_repo", return_value={"default_branch": "dev"}), \
             patch.object(self.manager, "fetch_release", return_value=None), \
             patch.object(self.manager, "fetch_commit", return_value={"sha": "new"}), \
             patch("backend.managers.mgr_github.GithubModRecord.get_or_none") as cache:
            info = self.manager.fetch_repo_info("https://github.com/user/repo")
        self.assertEqual(info["release_status"], "missing")
        self.assertFalse(info["has_release"])
        cache.assert_not_called()


    def test_gitlab_release_api_failure_uses_existing_tag_archive_fallback(self):
        request = GithubInstallRequest(
            owner="user", repo="repo", provider=GIT_PROVIDER_GITLAB, host="gitgud.io", project_path="user/repo",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET, release_tag="v1",
                fallback_download_url="https://gitgud.io/api/v4/projects/user%2Frepo/repository/archive.zip?sha=v1",
                fallback_filename="repo_v1.zip", fallback_version="v1",
            ),
        )
        with patch.object(self.manager, "fetch_gitlab_release", side_effect=requests.HTTPError("403")), \
             patch.object(self.manager, "fetch_gitlab_commit", return_value={"id": "a" * 40}):
            resolved = self.manager._resolve_gitlab_release_asset(request)
        self.assertIn("a" * 40, resolved.download_url)
        self.assertEqual(resolved.version, "v1")

    def test_github_release_without_assets_uses_tag_archive(self):
        artifact = self.manager._build_repo_artifact_request("user", "repo", repo_url="https://github.com/user/repo", is_release_mode=True, target_version="release/1.7")
        self.assertIn("release%2F1.7", artifact.fallback_download_url)
        self.assertEqual(artifact.fallback_filename, "repo_release_1.7.zip")
        request = GithubInstallRequest(
            owner="user", repo="repo",
            artifact=GithubArtifactRequest(
                kind=GITHUB_ARTIFACT_RELEASE_ASSET, release_tag="v1",
                fallback_download_url="https://github.com/user/repo/archive/refs/tags/v1.zip",
                fallback_filename="repo_v1.zip", fallback_version="v1",
            ),
        )
        with patch.object(self.manager, "fetch_release", return_value={"tag_name": "v1", "assets": []}), \
             patch.object(self.manager, "fetch_commit", return_value={"sha": "a" * 40}):
            resolved = self.manager._resolve_release_asset(request)
        self.assertIn("a" * 40, resolved.download_url)
        self.assertEqual(resolved.version, "v1")

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
                 return_value={"sha": "a" * 40, "commit": {"author": {"date": "2026-04-16T03:22:11Z"}}},
             ):
            resolved = self.manager._resolve_source_archive(request)

        self.assertEqual(resolved.version, "dev@" + "a" * 40)
        self.assertTrue(resolved.download_url.endswith("/archive/" + "a" * 40 + ".zip"))
        self.assertEqual(resolved.filename, "repo_aaaaaaaaaaaa_source.zip")

    def test_fetch_repo_info_includes_source_version_for_target_branch(self):
        with patch.object(self.manager, "fetch_repo", return_value={"default_branch": "main"}), \
             patch.object(self.manager, "fetch_release", return_value={"tag_name": "v1.2.3", "name": "v1.2.3", "published_at": "2026-04-15T10:00:00Z"}), \
             patch.object(
                 self.manager,
                 "fetch_commit",
                 return_value={
                     "sha": "a" * 40,
                     "commit": {"author": {"date": "2026-04-16T03:22:11Z"}},
                 },
             ):
            info = self.manager.fetch_repo_info("https://github.com/user/repo", source_branch="dev")

        self.assertEqual(info["latest_source_branch"], "dev")
        self.assertEqual(info["latest_source_commit_sha"], "a" * 40)
        self.assertEqual(info["latest_source_commit_at"], "2026-04-16T03:22:11Z")
        self.assertEqual(info["latest_source_version"], "dev@" + "a" * 40)
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
                     "id": "a" * 40,
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
        self.assertEqual(info["latest_source_version"], "Dev@" + "a" * 40)

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

    def test_cached_provider_catalog_sources_by_package_id_skip_disabled_items(self):
        source = self.manager._parse_provider_json_sources("RJW|https://example.invalid/providers.json")[0]
        catalog_dir = self.temp_root / "git_catalogs"
        original_provider_catalog_url = settings.config.git_provider_catalog_url
        settings.config.git_provider_catalog_url = "RJW|https://example.invalid/providers.json"
        self.addCleanup(setattr, settings.config, "git_provider_catalog_url", original_provider_catalog_url)
        with patch("backend.managers.mgr_github.GIT_PROVIDER_CATALOG_DIR", catalog_dir):
            self.manager._save_provider_catalog_source_cache(source, {
                "source": {"id": source["id"], "label": "RJW", "type": "provider_json"},
                "items": [
                    {
                        "key": "active",
                        "source_id": source["id"],
                        "type": "git",
                        "name": "Active Git Mod",
                        "package_id": "author.gitmod",
                        "url": "https://gitgud.io/team/active",
                        "raw_url": "https://gitgud.io/team/active.git",
                        "workshop_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890",
                        "branch": "main",
                        "game_versions": ["1.5"],
                    },
                    {
                        "key": "disabled",
                        "source_id": source["id"],
                        "type": "git",
                        "name": "Disabled Git Mod",
                        "package_id": "author.disabled",
                        "url": "https://gitgud.io/team/disabled",
                        "not_recommended": True,
                    },
                ],
            })

            result = self.manager.get_cached_provider_catalog_install_sources_by_package_ids([
                "author.gitmod",
                "author.disabled",
            ])

        self.assertEqual(result["author.gitmod"][0]["source_kind"], "git")
        self.assertEqual(result["author.gitmod"][0]["install_type"], "source")
        self.assertEqual(result["author.gitmod"][0]["default_branch"], "main")
        self.assertEqual(result["author.gitmod"][0]["url"], "https://gitgud.io/team/active")
        self.assertEqual(result["author.gitmod"][0]["source_origin"], "git_catalog")
        self.assertNotIn("author.disabled", result)

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
        self.assertEqual({source["cache_id"] for source in sources}, {"rjw"})

    def test_provider_catalog_cache_path_uses_source_cache_id(self):
        source = self.manager._parse_provider_json_sources("RJW|https://example.invalid/providers.json")[0]

        with patch("backend.managers.mgr_github.GIT_PROVIDER_CATALOG_DIR", self.temp_root):
            cache_path = self.manager._provider_catalog_cache_path(source)

        self.assertEqual(cache_path, self.temp_root / "rjw.json")

    def test_provider_catalog_cache_load_migrates_legacy_source_id_file(self):
        source = self.manager._parse_provider_json_sources("RJW|https://example.invalid/providers.json")[0]
        stale_catalog = {
            "source": {"id": "rjw", "label": "RJW", "type": "provider_json", "count": 1},
            "items": [{"key": "old", "name": "Old"}],
        }
        current_catalog = {
            "source": {"id": source["id"], "label": "RJW", "type": "provider_json", "count": 1},
            "items": [{"key": "new", "name": "New"}],
        }

        with patch("backend.managers.mgr_github.GIT_PROVIDER_CATALOG_DIR", self.temp_root):
            self.manager._save_provider_catalog_source_cache(source, stale_catalog)
            self.manager._save_provider_catalog_source_cache(source["id"], current_catalog)
            loaded_catalog = self.manager._load_provider_catalog_source_cache(source)
            migrated_catalog = self.manager._load_provider_catalog_source_cache("rjw")

        self.assertEqual(loaded_catalog["items"], current_catalog["items"])
        self.assertEqual(migrated_catalog["source"]["id"], source["id"])

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
            self.manager._save_provider_catalog_source_cache(source, cached_catalog)
            with patch.object(self.manager, "_provider_catalog_sources", return_value=[source]), \
                 patch.object(self.manager, "_fetch_provider_catalog_source_remote", return_value=remote_catalog):
                result = self.manager.check_provider_catalog_updates()

            saved_catalog = self.manager._load_provider_catalog_source_cache(source)

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
            session=MagicMock(),
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
            session=MagicMock(),
            checked_about_count=0,
        )

        self.assertFalse(checked_about)
        self.assertNotIn("detected_by", repo_item)
        self.assertEqual(repo_item["workshop_url"], "https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890")

    def test_github_owner_catalog_reads_api_pages(self):
        repo_payload = {
            "name": "ExampleMod",
            "description": "RimWorld mod",
            "homepage": "",
            "topics": [],
            "html_url": "https://github.com/example/ExampleMod",
            "clone_url": "https://github.com/example/ExampleMod.git",
            "default_branch": "main",
            "owner": {"login": "example"},
            "fork": False,
            "archived": False,
        }
        first_page = MagicMock(status_code=200)
        first_page.json.return_value = [repo_payload]
        last_page = MagicMock(status_code=200)
        last_page.json.return_value = []
        with patch("backend.managers.mgr_github.build_retry_session") as build:
            request = build.return_value.__enter__.return_value.get
            request.side_effect = [first_page, last_page]
            items = self.manager._fetch_github_owner_catalog("example", {"id": "example", "label": "Example", "match": {"description": ["RimWorld"]}})

        self.assertEqual(items[0]["name"], "ExampleMod")
        self.assertEqual(request.call_count, 2)
        self.assertEqual([call.kwargs["params"]["page"] for call in request.call_args_list], [1, 2])
        self.assertEqual(request.call_args.args[0], "https://api.github.com/users/example/repos")

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
            session=MagicMock(),
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
                "repo-main/ExampleMod/About/About.xml": "<ModMetaData><packageId>test.mod</packageId></ModMetaData>",
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

        self.assertEqual(source, mod_root.resolve())

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
        ), patch.object(self.manager, "fetch_gitlab_commit", return_value={"id": "a" * 40}):
            resolved = self.manager._resolve_release_asset(request)

        self.assertEqual(resolved.version, "v2")
        self.assertEqual(resolved.filename, "repo_aaaaaaaaaaaa_source.zip")
        self.assertIn("repository/archive.zip?sha=" + "a" * 40, resolved.download_url)

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
                download_mgr, "https://github.com/user/repo", "release", "v1.2.3",
                install_options={"ref_type": GITHUB_SOURCE_TAG},
            )

        request = captured["request"]
        self.assertEqual(task_id, "task-1")
        self.assertEqual(request.artifact.kind, GITHUB_ARTIFACT_RELEASE_ASSET)
        self.assertEqual(request.artifact.release_tag, "v1.2.3")
        self.assertEqual(request.artifact.asset_name_prefix, "repo")
        self.assertEqual(request.artifact.asset_name_suffix, ".zip")
        self.assertIn("/archive/refs/tags/v1.2.3.zip", request.artifact.fallback_download_url)
        self.assertEqual(request.artifact.fallback_filename, "repo_v1.2.3.zip")
        self.assertTrue(request.install.final_name.startswith("_GH_repo_"))

    def test_fetch_repo_info_raises_when_no_fallback_source_available(self):
        with patch.object(self.manager, "_fetch_repo_info_via_api", side_effect=GithubRateLimitError("rate limited")), \
             patch.object(self.manager, "_fetch_repo_info_via_web", return_value=None), \
             patch.object(self.manager, "_fetch_repo_info_from_record_cache", return_value=None):
            with self.assertRaises(GithubRateLimitError):
                self.manager.fetch_repo_info("https://github.com/user/repo")

    def test_resolve_source_archive_blocks_unidentified_download_when_commit_lookup_fails(self):
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
            with self.assertRaises(GithubRateLimitError):
                self.manager._resolve_source_archive(request)


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

        api.github_trigger_download.assert_called_once_with(
            "https://github.com/team/mod", "source", "dev",
            {"ref_type": "branch", "asset_name": "", "source_subpath": ""},
        )
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
        self.api.github_trigger_download.assert_called_once_with(
            "https://gitgud.io/team/mod", "source", "feature/1.7",
            {"ref_type": "branch", "asset_name": "", "source_subpath": ""},
        )
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
