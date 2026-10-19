import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from zipfile import ZipFile

import pytest
from peewee import SqliteDatabase

from backend.database.models import GithubModRecord, GithubTimeline, SystemInfo
from backend.managers import mgr_github
from backend.managers.mgr_download import DownloadManager, DownloadTask, TaskStatus
from backend.managers.mgr_github import GithubArtifactRequest, GithubInstallPlan, GithubInstallRequest, GithubManager, GithubResolvedArtifact, GitSelectionRequired
from backend.settings import settings
from backend.utils.bundle_io import replace_dir_atomically


SHA = "a" * 40
URL = "https://github.com/team/mod"


@pytest.fixture
def git_env(tmp_path, monkeypatch):
    database = SqliteDatabase(tmp_path / "test.db")
    models = [GithubModRecord, GithubTimeline, SystemInfo]
    with database.bind_ctx(models):
        database.connect()
        database.create_tables(models)
        monkeypatch.setattr(mgr_github, "db", database)
        monkeypatch.setattr(settings.config, "self_mods_path", str(tmp_path / "mods"))
        GithubManager._response_cache.clear()
        yield GithubManager(), tmp_path
        database.close()


def make_install(manager, tmp_path, *, entries=None, callback=None):
    archive_path = tmp_path / "mod.zip"
    with ZipFile(archive_path, "w") as archive:
        for name, content in (entries or {"wrapper/About/About.xml": "<ModMetaData><packageId>test.mod</packageId></ModMetaData>", "wrapper/Defs/a.xml": "new"}).items():
            archive.writestr(name, content)
    request = GithubInstallRequest(repo_url=URL, owner="team", repo="mod",
        install=GithubInstallPlan(action="extract_then_move", move_target_dir=str(tmp_path / "mods"), final_name="_GH_mod", source_resolver="mod_root"), post_install=callback)
    task = DownloadTask(url="https://example.invalid/mod.zip", dest_path=str(archive_path), filename="mod.zip")
    resolved = GithubResolvedArtifact(repo_url=URL, owner="team", repo="mod", kind="source_archive", version="main@" + SHA,
        download_url=task.url, filename=task.filename, evidence={"ref": "main", "ref_type": "branch", "commit_sha": SHA})
    return request, task, resolved


@pytest.mark.parametrize("provider,host", [("github", "github.com"), ("gitlab", "gitgud.io")])
@pytest.mark.parametrize("kind", ["branch", "tag", "commit"])
def test_source_download_is_frozen_to_sha(git_env, provider, host, kind):
    manager, _ = git_env
    ref = SHA if kind == "commit" else "feature/1.7"
    request = GithubInstallRequest(repo_url=f"https://{host}/team/mod", provider=provider, host=host, owner="team", repo="mod",
        artifact=GithubArtifactRequest(source_ref=ref, source_ref_type=kind))
    with patch.object(manager, "fetch_ref_commit", return_value={"sha": SHA}) as fetch:
        resolved = manager._resolve_source_archive(request)
    assert SHA in resolved.download_url
    assert "feature" not in resolved.download_url
    assert resolved.evidence["ref_type"] == kind
    assert resolved.version == ref + "@" + SHA
    assert fetch.call_args.kwargs["force_refresh"] is True


def test_missing_branch_does_not_resolve_same_named_tag(git_env):
    manager, _ = git_env
    response = Mock(status_code=404)
    session = Mock()
    session.get.return_value = response
    with patch.object(manager, "fetch_commit") as commit, patch.object(mgr_github, "build_retry_session") as build:
        build.return_value.__enter__.return_value = session
        assert manager.fetch_ref_commit(manager.parse_git_repo_url(URL), "v1", "branch") is None
    commit.assert_not_called()
    assert session.get.call_args.args[0].endswith("/branches/v1")


def test_slash_ref_and_release_tag_are_encoded(git_env):
    manager, _ = git_env
    response = Mock(status_code=200)
    response.json.return_value = {"sha": SHA}
    session = Mock()
    session.get.return_value = response
    with patch.object(mgr_github, "build_retry_session") as build:
        build.return_value.__enter__.return_value = session
        manager.fetch_commit("team", "mod", ref="feature/1.7")
        assert session.get.call_args.args[0].endswith("/commits/feature%2F1.7")
        manager.fetch_release("team", "mod", tag="release/1.7")
        assert session.get.call_args.args[0].endswith("/releases/tags/release%2F1.7")


def test_annotated_tag_is_resolved_to_commit(git_env):
    manager, _ = git_env
    ref, tag = Mock(status_code=200), Mock(status_code=200)
    ref.json.return_value = {"object": {"type": "tag", "sha": "b" * 40}}
    tag.json.return_value = {"object": {"type": "commit", "sha": SHA}}
    session = Mock()
    session.get.side_effect = [ref, tag]
    with patch.object(mgr_github, "build_retry_session") as build, patch.object(manager, "fetch_commit", return_value={"sha": SHA}) as commit:
        build.return_value.__enter__.return_value = session
        assert manager.fetch_ref_commit(manager.parse_git_repo_url(URL), "v1", "tag")["sha"] == SHA
    assert session.get.call_args.args[0].endswith("/git/tags/" + "b" * 40)
    assert commit.call_args.kwargs["ref"] == SHA


def test_same_named_repositories_do_not_share_install_folder(git_env):
    manager, _ = git_env
    folders = []
    with patch.object(manager, "install_from_github", side_effect=lambda _download, request: folders.append(request.install.final_name)):
        for url in (URL, "https://github.com/another/mod", "https://gitgud.io/team/mod"):
            manager.install_repo_mod(Mock(), url, "source", "dev", install_options={"ref_type": "branch"})
    assert len(set(folders)) == 3
    GithubModRecord.create(repo_url=URL, owner="team", repo_name="mod", local_folder="_GH_mod")
    GithubModRecord.create(repo_url="https://github.com/another/mod", owner="another", repo_name="mod", local_folder="_GH_mod")
    with pytest.raises(ValueError, match="同一个本地目录"):
        manager.install_repo_mod(Mock(), URL, "source", "dev", install_options={"ref_type": "branch"})


def test_explicit_checks_bypass_cache_and_return_independent_objects(git_env):
    manager, _ = git_env
    payload = {"default_branch": "main"}
    manager._store_cached_payload(("repo", "team", "mod"), payload)
    payload["default_branch"] = "changed"
    assert manager.fetch_repo("team", "mod")["default_branch"] == "main"
    cached = manager.fetch_repo("team", "mod")
    cached["default_branch"] = "changed"
    assert manager.fetch_repo("team", "mod")["default_branch"] == "main"
    response = Mock(status_code=200)
    response.json.return_value = {"default_branch": "dev"}
    with patch.object(mgr_github, "build_retry_session") as build:
        build.return_value.__enter__.return_value.get.return_value = response
        assert manager.fetch_repo("team", "mod", force_refresh=True)["default_branch"] == "dev"


def test_url_ref_ambiguity_and_subdirectory(git_env):
    manager, _ = git_env
    def refs(_url, ref_type="branch"):
        return ["feature/1.7"] if ref_type == "branch" else []
    with patch.object(manager, "fetch_repo_branches", side_effect=refs):
        assert manager.resolve_repo_location(URL + "/tree/feature/1.7/Mods/Example")[1:] == ("feature/1.7", "branch", "Mods/Example")
    with patch.object(manager, "fetch_repo_branches", return_value=["v1"]):
        with pytest.raises(ValueError, match="歧义"):
            manager.resolve_repo_location(URL + "/tree/v1")
    with pytest.raises(ValueError): manager.resolve_repo_location(URL + "/issues/1")
    assert manager.parse_git_repo_url("https://example.invalid/github.com/team/mod") is None


def test_cached_repository_does_not_reuse_another_mod_directory(git_env):
    manager, _ = git_env
    manager._store_cached_payload(("repo_info", "team", "mod", "branch", "dev"), {"source_subpath": "FirstMod"})
    info = manager.fetch_repo_info(URL + "/tree/dev/SecondMod", source_branch="dev")
    assert info["source_subpath"] == "SecondMod"
    assert manager.fetch_repo_info(URL, source_branch="dev")["source_subpath"] == ""


@pytest.mark.parametrize("changed,failed", [(False, False), (True, False), (False, True)])
def test_background_refresh_discards_changed_tracking_and_marks_failure(git_env, changed, failed):
    import threading
    from backend.api import API

    manager, _ = git_env
    record = GithubModRecord.create(repo_url=URL, owner="team", repo_name="mod", target_branch="main",
        installed_version="main@" + SHA, installed_info={"ref": "main", "commit_sha": SHA},
        online_info_cache={"source_status": "available", "latest_source_branch": "main", "latest_source_commit_sha": SHA})
    snapshot = record.__data__.copy()
    if changed:
        record.target_branch = "dev"
        record.save()
    api = API.__new__(API)
    api.github_mgr = manager
    api._github_subs_refresh_lock = threading.Lock()
    api._github_subs_refresh_running = True
    fresh = {"source_status": "available", "latest_source_branch": "main", "latest_source_commit_sha": "b" * 40}
    with patch.object(manager, "fetch_repo_info", side_effect=RuntimeError("network failure") if failed else None, return_value=fresh), \
         patch("backend.database.models.db", mgr_github.db), patch("backend.api.EventBus.emit") as emit:
        api._bg_refresh_github_subs([snapshot])
    updated = GithubModRecord.get_by_id(URL)
    pushed = emit.call_args.args[1]
    assert api._github_subs_refresh_running is False
    if changed:
        assert pushed == {} and updated.online_info_cache == snapshot["online_info_cache"]
    elif failed:
        assert updated.online_info_cache["latest_source_commit_sha"] == SHA
        assert pushed[URL]["subscription_status"] == "unknown"
    else:
        assert updated.online_info_cache["latest_source_commit_sha"] == "b" * 40
        assert pushed[URL]["subscription_status"] == "upgrade"


def test_ambiguous_release_requires_selection(git_env):
    manager, _ = git_env
    assets = [{"name": name, "browser_download_url": "https://example.invalid/" + name} for name in ("mod-win.zip", "mod-linux.zip")]
    with pytest.raises(GitSelectionRequired):
        manager._select_release_asset(assets, GithubArtifactRequest(asset_name_suffix=".zip"))
    selected = manager._select_release_asset(assets, GithubArtifactRequest(asset_name="mod-linux.zip", asset_name_prefix="other"))
    assert selected["name"] == "mod-linux.zip"


@pytest.mark.parametrize("subpath", ["../outside", "C:/outside", "/outside", "safe/../../outside"])
def test_subdirectory_cannot_escape_archive(git_env, subpath):
    manager, root = git_env
    with pytest.raises(ValueError): manager._resolve_install_source(root, GithubInstallPlan(source_subpath=subpath))


def test_multiple_mod_roots_require_selection(git_env):
    manager, root = git_env
    for name in ["one", "two"]:
        path = root / "wrapper" / name / "About"
        path.mkdir(parents=True)
        (path / "About.xml").write_text("<ModMetaData/>")
    with pytest.raises(GitSelectionRequired) as exc:
        manager._find_mod_root(root)
    assert set(exc.value.candidates) == {"one", "two"}


@pytest.mark.parametrize("entry,content", [("../outside", "x"), ("wrapper/About/About.xml", "<ModMetaData/>"),
    ("wrapper/Assemblies/mod.dll", "version https://git-lfs.github.com/spec/v1\noid sha256:x"), ("wrapper/Source/a.cs", "class X {}"),
    ("wrapper/.gitmodules", '[submodule "needed"]\npath=needed\nurl=https://example.invalid/needed')])
def test_invalid_or_incomplete_archive_preserves_old_install(git_env, entry, content):
    manager, root = git_env
    old = root / "mods" / "_GH_mod"
    old.mkdir(parents=True)
    (old / "original").write_text("old")
    entries = {"wrapper/About/About.xml": "<ModMetaData><packageId>test.mod</packageId></ModMetaData>", entry: content}
    request, task, resolved = make_install(manager, root, entries=entries)
    with pytest.raises((ValueError, FileNotFoundError)):
        manager._execute_install_plan(task, request, resolved)
    assert (old / "original").read_text() == "old"


def test_record_failure_rolls_back_files_and_keeps_archive(git_env):
    manager, root = git_env
    target = root / "mods" / "_GH_mod"
    target.mkdir(parents=True)
    (target / "old").write_text("old")
    request, task, resolved = make_install(manager, root, callback=Mock(side_effect=RuntimeError("database save failed")))
    with pytest.raises(RuntimeError): manager._execute_install_plan(task, request, resolved)
    assert (target / "old").read_text() == "old"
    assert Path(task.dest_path).exists()
    assert not list(target.parent.glob(".github-backup-*"))


def test_shared_atomic_replace_rolls_back_callback_failure(tmp_path):
    for had_target in (True, False):
        target, prepared = tmp_path / str(had_target), tmp_path / (str(had_target) + "-stage")
        prepared.mkdir()
        (prepared / "new").write_text("new")
        if had_target:
            target.mkdir()
            (target / "old").write_text("old")
        with pytest.raises(RuntimeError): replace_dir_atomically(target, prepared, Mock(side_effect=RuntimeError("failed")))
        assert (prepared / "new").exists()
        assert (target / "old").exists() if had_target else not target.exists()


def test_install_records_evidence_without_changing_online_cache(git_env):
    manager, root = git_env
    record = GithubModRecord.create(repo_url=URL, owner="team", repo_name="mod", target_branch="main", online_info_cache={"latest_source_commit_sha": "b" * 40})
    request, task, resolved = make_install(manager, root)
    request.post_install = lambda result: manager._update_mod_record(URL, result.version, "_GH_mod", installed_info=result.installed_info)
    result = manager._execute_install_plan(task, request, resolved)
    record = GithubModRecord.get_by_id(URL)
    assert record.installed_info["commit_sha"] == SHA
    assert record.installed_info["package_id"] == "test.mod"
    assert record.online_info_cache == {"latest_source_commit_sha": "b" * 40}
    assert Path(result.installed_path).exists()


@pytest.mark.parametrize("committed", [False, True])
def test_interrupted_install_recovery(git_env, committed):
    manager, root = git_env
    parent = root / "mods"
    parent.mkdir()
    token = "a" * 32
    target, backup, stage = parent / "_GH_mod", parent / (".github-backup-" + token), parent / ".github-stage-test"
    for path in (target, backup, stage): path.mkdir()
    (target / "new").write_text("new")
    (backup / "old").write_text("old")
    GithubModRecord.create(repo_url=URL, owner="team", repo_name="mod", installed_info={"install_id": token} if committed else {})
    journal = parent / f".github-pending-{token}.json"
    journal.write_text(json.dumps({"repo_url": URL, "install_id": token, "target": target.name, "backup": backup.name, "stage": stage.name, "had_target": True}))
    manager.recover_pending_installs()
    assert (target / ("new" if committed else "old")).exists()
    assert not journal.exists() and not stage.exists() and not backup.exists()


def test_tracking_change_and_cancel_do_not_replace_old_install(git_env):
    manager, root = git_env
    GithubModRecord.create(repo_url=URL, owner="team", repo_name="mod", target_branch="dev")
    request, task, resolved = make_install(manager, root)
    request.tracking = {"target_branch": "main"}
    with pytest.raises(InterruptedError): manager._execute_install_plan(task, request, resolved)
    assert not (root / "mods" / "_GH_mod").exists()
    task._cancel_event.set()
    with pytest.raises(InterruptedError): manager._execute_install_plan(task, request, resolved)


def test_unremoved_recovery_journal_blocks_later_overwrite(git_env):
    manager, root = git_env
    GithubModRecord.create(repo_url=URL, owner="team", repo_name="mod", target_branch="main")
    request, task, resolved = make_install(manager, root)
    request.tracking = {"target_branch": "main"}
    parent = root / "mods"
    parent.mkdir()
    (parent / (".github-pending-" + "b" * 32 + ".json")).write_text(json.dumps({"target": "_GH_mod"}))
    with pytest.raises(RuntimeError, match="恢复记录"):
        manager._execute_install_plan(task, request, resolved)
    assert not (parent / "_GH_mod").exists()


def test_migration_is_idempotent_and_does_not_forge_timestamp_sha(git_env):
    manager, _ = git_env
    GithubModRecord.create(repo_url=URL + ".git", owner="team", repo_name="mod", installed_version="main@2026-01-01", local_folder="_GH_mod")
    GithubModRecord.create(repo_url=URL, owner="team", repo_name="mod")
    manager.migrate_subscription_records()
    manager.migrate_subscription_records()
    record = GithubModRecord.get_by_id(URL)
    assert GithubModRecord.select().count() == 1
    assert record.local_folder == "_GH_mod"
    assert "commit_sha" not in record.installed_info


def test_status_uses_sha_including_force_pushes_and_errors():
    record = {"install_type": "source", "target_branch": "main", "installed_version": "main@" + SHA,
        "installed_info": {"ref": "main", "commit_sha": SHA},
        "online_info_cache": {"source_status": "available", "latest_source_branch": "main", "latest_source_commit_sha": SHA}}
    assert GithubManager.subscription_status(record) == "current"
    record["online_info_cache"]["latest_source_commit_sha"] = "b" * 40
    assert GithubManager.subscription_status(record) == "upgrade"
    record["online_info_cache"]["source_status"] = "error"
    assert GithubManager.subscription_status(record) == "unknown"
    record["installed_info"] = {"legacy_version": "main@2026-01-01"}
    assert GithubManager.subscription_status(record) == "unknown"


def test_release_source_status_uses_tag_sha_and_selected_directory(git_env):
    manager, _ = git_env
    with patch.object(manager, "fetch_repo", return_value={"default_branch": "main"}), \
         patch.object(manager, "fetch_release", return_value={"tag_name": "v1", "assets": []}), \
         patch.object(manager, "fetch_ref_commit", return_value={"sha": SHA}) as fetch:
        info = manager._fetch_repo_info_via_api("team", "mod", force_refresh=True)
    assert info["latest_release_commit_sha"] == SHA
    assert fetch.call_args.args[1:] == ("v1", "tag")
    record = {"install_type": "release", "installed_version": "v1", "online_info_cache": info,
        "installed_info": {"artifact_kind": "source_archive", "release_tag": "v1", "commit_sha": SHA, "source_subpath": ""}}
    assert manager.subscription_status(record) == "current"
    info["latest_release_commit_sha"] = "b" * 40
    assert manager.subscription_status(record) == "upgrade"
    record["install_options"] = {"source_subpath": "OtherMod"}
    assert manager.subscription_status(record) == "branch_changed"


def test_download_callback_failure_never_reports_completed(tmp_path):
    manager = object.__new__(DownloadManager)
    emitted = []
    manager._emit_progress = lambda task: emitted.append(task.status)
    task = DownloadTask(url="https://example.invalid/a.zip", dest_path=str(tmp_path / "a.zip"), filename="a.zip",
        on_post_download=Mock(side_effect=ValueError("invalid mod")))
    response = Mock(headers={"content-length": "3"}, url=task.url)
    response.iter_content.return_value = [b"zip"]
    session = MagicMock()
    session.get.return_value.__enter__.return_value = response
    with patch("backend.managers.mgr_download.build_retry_session", return_value=session): manager._download_worker(task)
    assert task.status == TaskStatus.ERROR
    assert TaskStatus.COMPLETED not in emitted
    session.close.assert_called_once()


def test_install_failure_records_only_one_git_timeline_error(git_env):
    manager, root = git_env
    request, task, resolved = make_install(manager, root)
    manager.record_timeline = Mock()

    with patch.object(manager, "_execute_install_plan", side_effect=ValueError("invalid mod")), pytest.raises(ValueError):
        manager._handle_install(task, request, resolved)

    manager._handle_download_error(task, request, resolved)
    errors = [call.args for call in manager.record_timeline.call_args_list if call.args[1] == "error"]
    assert len(errors) == 1
    assert errors[0][0] == URL
    assert errors[0][1] == "error"


@pytest.mark.parametrize("action,cleanup", [("download_only", True), ("extract", False), ("extract", True)])
def test_download_destination_and_retention(git_env, action, cleanup):
    manager, root = git_env
    request = GithubInstallRequest(repo_url=URL, install=GithubInstallPlan(action=action, download_dir=str(root / "downloads"), cleanup_archive=cleanup))
    resolved = GithubResolvedArtifact(URL, "team", "mod", "source_archive", SHA, "https://example.invalid/mod.zip", "mod.zip")
    download = Mock()
    with patch.object(manager, "_resolve_artifact", return_value=resolved): manager.install_from_github(download, request)
    kwargs = download.add_task.call_args.kwargs
    is_temporary = action != "download_only" and cleanup
    assert bool(kwargs["metadata"].get("temporary_dir")) == is_temporary
    assert (Path(kwargs["dest_dir"]).parent if is_temporary else Path(kwargs["dest_dir"])) == root / "downloads"
    if is_temporary:
        download.add_task.side_effect = ValueError("rejected")
        before = list((root / "downloads").iterdir())
        with patch.object(manager, "_resolve_artifact", return_value=resolved), pytest.raises(ValueError):
            manager.install_from_github(download, request)
        assert list((root / "downloads").iterdir()) == before


def test_cancel_before_download_cleans_only_task_directory(tmp_path):
    manager = object.__new__(DownloadManager)
    manager._emit_progress = Mock()
    temporary = tmp_path / "git-task-cancelled"
    temporary.mkdir()
    task = DownloadTask(url="https://example.invalid/a.zip", dest_path=str(temporary / "a.zip"), filename="a.zip", metadata={"temporary_dir": str(temporary)})
    task._cancel_event.set()
    manager._download_worker(task)
    assert task.status == TaskStatus.CANCELLED and not temporary.exists()
    retained = tmp_path / "a.zip"
    retained.write_bytes(b"zip")
    task.dest_path, task.metadata = str(retained), {}
    manager._download_worker(task)
    assert retained.read_bytes() == b"zip"
