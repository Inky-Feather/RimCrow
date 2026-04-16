import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from backend.managers.mgr_download import DownloadTask
from backend.managers.mgr_github import (
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
             patch.object(self.manager, "fetch_latest_release", return_value={"tag_name": "v1.2.3", "name": "v1.2.3"}), \
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
        self.assertEqual(info["info_source"], "api")
        self.assertFalse(info["is_degraded"])

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
