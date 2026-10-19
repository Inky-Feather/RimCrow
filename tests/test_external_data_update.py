import gzip
import json
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
import requests
import time
import threading
import io
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from peewee import SqliteDatabase

from backend.api import API
from backend.database.models import SystemInfo, ModAsset
from backend.database.models_ext import ExtDatasetState, ModReplacement, WorkshopManifest
from backend.managers import mgr_download, mgr_workshop_db
from backend.managers.mgr_rules import RuleManager
from backend.managers.mgr_multiplayer_compat import MultiplayerCompatibilityManager
from backend.managers.mgr_download import DownloadManager, TaskStatus
from backend.managers.mgr_workshop_db import WorkshopDBManager
from backend.managers.mgr_github import GithubManager
from backend.managers.mgr_maintenance import MaintenanceManager
from backend.settings import settings
from backend.utils.event_bus import EventBus


@pytest.fixture
def external_env(tmp_path, monkeypatch):
    database = SqliteDatabase(tmp_path / "main.db")
    cache = SqliteDatabase(tmp_path / "cache.db")
    models = [ExtDatasetState, ModReplacement, WorkshopManifest]
    with database.bind_ctx([SystemInfo, ModAsset]), cache.bind_ctx(models):
        database.create_tables([SystemInfo, ModAsset])
        cache.create_tables(models)
        monkeypatch.setattr(mgr_workshop_db, "ext_db", cache)
        monkeypatch.setattr("backend.api.ext_db", cache)
        for kind, key in [("instead_db", "community_instead_db"), ("workshop_db", "community_workshop_db"),
                          ("community_rules", "community_rules"), ("multiplayer_compatibility", "multiplayer_compatibility"),
                          ("mp_compat_package_ids", "mp_compat_package_ids")]:
            monkeypatch.setattr(settings.config, key + "_path", str(tmp_path / (kind + ".json")))
            monkeypatch.setattr(settings.config, key + "_url", "https://example.invalid/" + kind)
        downloader = DownloadManager()
        monkeypatch.setattr(downloader, "tasks", {})
        monkeypatch.setattr(downloader, "executor", SimpleNamespace(submit=lambda *args: Future()))
        events = []
        monkeypatch.setattr(downloader, "_emit_progress", lambda task: events.append((task.status.value, dict(task.metadata))))
        monkeypatch.setattr(EventBus, "send_toast", Mock())
        monkeypatch.setattr(EventBus, "resume", Mock())
        api = API.__new__(API)
        api.download_mgr = downloader
        api.github_mgr = SimpleNamespace(
            github_url_capability=lambda url: "raw", _github_download_candidates=lambda url: [url],
            record_mirror_result=Mock(),
        )
        api.workshop_db_mgr = WorkshopDBManager.__new__(WorkshopDBManager)
        api.sorter = None
        api.multiplayer_compat_mgr = MultiplayerCompatibilityManager()
        yield api, events, tmp_path
        cache.close()
        database.close()


def run_update(env, monkeypatch, payload, kind="instead_db"):
    api, events, folder = env
    response = MagicMock(status_code=200, url="https://example.invalid/data")
    response.headers = requests.structures.CaseInsensitiveDict({"Content-Length": str(len(payload))})
    response.__enter__.return_value = response
    response.iter_content.side_effect = lambda chunk_size: iter([payload])
    session = Mock()
    session.get.return_value = response
    session._last_route = None
    monkeypatch.setattr(mgr_download, "build_retry_session", lambda **kwargs: session)
    result = api.update_external_db(kind)
    assert result["status"] == "success", result
    task = api.download_mgr.tasks[result["data"]["task_id"]]
    api.download_mgr._download_worker(task)
    return task, session


@pytest.mark.parametrize("compressed", [False, True])
def test_external_dataset_loads_before_reporting_completed(external_env, monkeypatch, compressed):
    api, events, folder = external_env
    payload = json.dumps({"version": "new", "rules": [{"oldPackageId": "old.mod", "newPackageId": "new.mod"}]}).encode()
    original_emit = api.download_mgr._emit_progress

    def emit(task):
        if task.status == TaskStatus.COMPLETED:
            assert ModReplacement.get().new_package_id == "new.mod"
            assert SystemInfo.get_by_id("instead_version").value == "new"
        original_emit(task)

    monkeypatch.setattr(api.download_mgr, "_emit_progress", emit)
    task, session = run_update(external_env, monkeypatch, gzip.compress(payload) if compressed else payload)
    assert task.status == TaskStatus.COMPLETED
    assert session.get.call_count == 1
    assert len([event for event in events if event[0] == "completed"]) == 1


@pytest.mark.parametrize("payload", [b"{}", b'{"version":"new","rules":[null]}',
                                     b'{"version":true,"rules":[]}', b"<html>bad</html>", b"\x1f\x8bbroken"])
def test_invalid_dataset_keeps_old_file_and_cache(external_env, monkeypatch, payload):
    _, _, folder = external_env
    target = folder / "instead_db.json"
    target.write_bytes(b"old-good-file")
    ModReplacement.create(old_package_id="old.mod", new_package_id="old.replacement")
    task, _ = run_update(external_env, monkeypatch, payload)
    assert task.status == TaskStatus.ERROR
    assert target.read_bytes() == b"old-good-file"
    assert ModReplacement.get().new_package_id == "old.replacement"


def test_failed_cache_state_write_restores_file_rows_and_version(external_env, monkeypatch):
    api, events, folder = external_env
    target = folder / "instead_db.json"
    target.write_bytes(b"old-good-file")
    ModReplacement.create(old_package_id="old.mod", new_package_id="old.replacement")
    SystemInfo.create(key="instead_version", value="old")
    monkeypatch.setattr(api.workshop_db_mgr, "_save_dataset_state", Mock(side_effect=OSError("disk full")))
    task, session = run_update(external_env, monkeypatch, b'{"version":"new","rules":[]}')
    assert task.status == TaskStatus.ERROR
    assert target.read_bytes() == b"old-good-file"
    assert ModReplacement.get().new_package_id == "old.replacement"
    assert SystemInfo.get_by_id("instead_version").value == "old"
    assert session.get.call_count == 1
    assert not any(status == "completed" for status, _ in events)


def test_external_db_commit_failure_restores_main_version_and_file(external_env, monkeypatch):
    _, _, folder = external_env
    target = folder / "instead_db.json"
    target.write_bytes(b"old-good-file")
    ModReplacement.create(old_package_id="old.mod", new_package_id="old.replacement")
    SystemInfo.create(key="instead_version", value="old")
    cache = mgr_workshop_db.ext_db
    commit = cache.commit
    failed = False

    def fail_first_commit():
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("external database commit failed")
        return commit()

    monkeypatch.setattr(cache, "commit", fail_first_commit)
    task, _ = run_update(external_env, monkeypatch, b'{"version":"new","rules":[]}')
    assert task.status == TaskStatus.ERROR
    assert target.read_bytes() == b"old-good-file"
    assert ModReplacement.get().new_package_id == "old.replacement"
    assert SystemInfo.get_by_id("instead_version").value == "old"
    assert ExtDatasetState.select().count() == 0


def test_main_version_write_failure_rolls_back_cache_and_file(external_env, monkeypatch):
    _, events, folder = external_env
    target = folder / "instead_db.json"
    target.write_bytes(b"old-good-file")
    ModReplacement.create(old_package_id="old.mod", new_package_id="old.replacement")
    SystemInfo.create(key="instead_version", value="old")
    insert = SystemInfo.insert

    def fail_new_version(*args, **kwargs):
        if kwargs.get("value") == "new":
            raise OSError("version write failed")
        return insert(*args, **kwargs)

    monkeypatch.setattr(SystemInfo, "insert", fail_new_version)
    task, _ = run_update(external_env, monkeypatch, b'{"version":"new","rules":[]}')
    assert task.status == TaskStatus.ERROR
    assert target.read_bytes() == b"old-good-file"
    assert ModReplacement.get().new_package_id == "old.replacement"
    assert SystemInfo.get_by_id("instead_version").value == "old"
    assert ExtDatasetState.select().count() == 0


def test_workshop_rule_rebuild_failure_restores_all_prior_state(external_env, monkeypatch):
    api, events, folder = external_env
    target = folder / "workshop_db.json"
    target.write_bytes(b"old-good-file")
    WorkshopManifest.create(workshop_id="123", package_id="old.mod")
    SystemInfo.create(key="steamdb_version", value="old")
    rule_mgr = RuleManager.__new__(RuleManager)
    rule_mgr.workshop_rules_cache = {"old.mod": ["dependency"]}
    monkeypatch.setattr(rule_mgr, "build_workshop_rules", Mock(side_effect=RuntimeError("rule build failed")))
    api.sorter = SimpleNamespace(rule_mgr=rule_mgr)
    task, _ = run_update(external_env, monkeypatch, b'{"version":"new","database":{}}', "workshop_db")
    assert task.status == TaskStatus.ERROR
    assert target.read_bytes() == b"old-good-file"
    assert WorkshopManifest.get_by_id("123").package_id == "old.mod"
    assert rule_mgr.workshop_rules_cache == {"old.mod": ["dependency"]}
    assert SystemInfo.get_by_id("steamdb_version").value == "old"


@pytest.mark.parametrize("payload", [{}, {"rules": {}}, {"example.mod": {"loadAfter": {}}}])
def test_community_rules_keep_supported_formats(external_env, monkeypatch, payload):
    api, _, folder = external_env
    rule_mgr = RuleManager.__new__(RuleManager)
    rule_mgr.community_rules = {"old.mod": {}}
    rule_mgr.community_rules_update_time = 1
    api.sorter = SimpleNamespace(rule_mgr=rule_mgr)
    task, _ = run_update(external_env, monkeypatch, json.dumps(payload).encode(), "community_rules")
    assert task.status == TaskStatus.COMPLETED
    assert rule_mgr.community_rules == payload.get("rules", payload)


@pytest.mark.parametrize("payload", [[], {"mods": []}, {"mods": [{"name": "example", "status": 4}]}])
def test_multiplayer_schema_preserves_arrays_and_wrappers(external_env, monkeypatch, payload):
    _, _, folder = external_env
    task, _ = run_update(external_env, monkeypatch, json.dumps(payload).encode(), "multiplayer_compatibility")
    assert task.status == TaskStatus.COMPLETED
    assert json.loads((folder / "multiplayer_compatibility.json").read_text(encoding="utf-8")) == payload


def test_mp_compat_generation_uses_download_task_without_extra_network(external_env, monkeypatch):
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("repo/Source/Example.cs", '[MpCompatFor("Example.Mod")]')
        archive.comment = b"a" * 40
    _, _, folder = external_env
    task, session = run_update(external_env, monkeypatch, archive_bytes.getvalue(), "mp_compat_package_ids")
    assert task.status == TaskStatus.COMPLETED
    assert session.get.call_count == 1
    payload = json.loads((folder / "mp_compat_package_ids.json").read_text(encoding="utf-8"))
    assert payload["package_ids"] == ["example.mod"]
    assert payload["source"]["source_id"] == "a" * 40


def test_cancel_during_validation_keeps_old_file(external_env, monkeypatch):
    api, events, folder = external_env
    target = folder / "instead_db.json"
    target.write_bytes(b"old-good-file")
    prepare = api.workshop_db_mgr.prepare_dataset

    def cancel_after_parse(*args):
        result = prepare(*args)
        next(iter(api.download_mgr.tasks.values()))._cancel_event.set()
        return result

    monkeypatch.setattr(api.workshop_db_mgr, "prepare_dataset", cancel_after_parse)
    task, _ = run_update(external_env, monkeypatch, b'{"version":"new","rules":[]}')
    assert task.status == TaskStatus.CANCELLED
    assert target.read_bytes() == b"old-good-file"
    assert not any(status == "completed" for status, _ in events)


def test_external_updates_do_not_compete_for_same_target(external_env):
    api, _, _ = external_env
    first = api.update_external_db("instead_db")
    second = api.update_external_db("instead_db")
    assert first["data"]["task_id"] == second["data"]["task_id"]
    assert len(api.download_mgr.tasks) == 1


def test_cancel_after_backup_cleans_temporary_files(external_env, monkeypatch):
    api, _, folder = external_env
    target = folder / "instead_db.json"
    target.write_bytes(b"old-good-file")
    from backend import api as api_module
    copy_file = api_module.shutil.copy2

    def cancel_after_copy(*args):
        result = copy_file(*args)
        next(iter(api.download_mgr.tasks.values()))._cancel_event.set()
        return result

    monkeypatch.setattr(api_module.shutil, "copy2", cancel_after_copy)
    task, _ = run_update(external_env, monkeypatch, b'{"version":"new","rules":[]}')
    assert task.status == TaskStatus.CANCELLED
    assert target.read_bytes() == b"old-good-file"
    assert not list(folder.glob("*.previous"))
    assert not list(folder.glob("*.downloading"))


def test_failed_file_restore_retains_backup(external_env, monkeypatch):
    _, _, folder = external_env
    target = folder / "instead_db.json"
    target.write_bytes(b"old-good-file")
    from backend import api as api_module
    replace_file = api_module.os.replace

    def fail_restore(source, destination):
        if str(source).endswith(".previous"):
            raise OSError("restore blocked")
        return replace_file(source, destination)

    monkeypatch.setattr(api_module.os, "replace", fail_restore)
    monkeypatch.setattr(external_env[0].workshop_db_mgr, "import_prepared_dataset", Mock(side_effect=OSError("import failed")))
    task, _ = run_update(external_env, monkeypatch, b'{"version":"new","rules":[]}')
    assert task.status == TaskStatus.ERROR
    assert next(folder.glob("*.previous")).read_bytes() == b"old-good-file"


def test_path_change_does_not_allow_two_writers_for_same_dataset(external_env, monkeypatch):
    api, _, folder = external_env
    first = api.update_external_db("instead_db")["data"]["task_id"]
    monkeypatch.setattr(settings.config, "community_instead_db_path", str(folder / "new-target.json"))
    assert api.update_external_db("instead_db")["data"]["task_id"] == first
    assert len(api.download_mgr.tasks) == 1


def test_cancelled_external_update_can_restart(external_env):
    api, _, _ = external_env
    first = api.update_external_db("instead_db")["data"]["task_id"]
    api.download_mgr.tasks[first].status = TaskStatus.CANCELLED
    api.download_mgr.tasks[first]._future.set_result(None)
    second = api.update_external_db("instead_db")["data"]["task_id"]
    assert second != first


def test_external_task_freezes_application_proxy_and_target(external_env, monkeypatch):
    api, _, folder = external_env
    monkeypatch.setattr(settings.config.network.proxy, "enabled", True)
    monkeypatch.setattr(settings.config.network.proxy, "host", "old.proxy")
    monkeypatch.setattr(settings.config.network.proxy, "port", 1080)
    first = api.update_external_db("instead_db")["data"]["task_id"]
    old = api.download_mgr.tasks[first]
    monkeypatch.setattr(settings.config.network.proxy, "host", "new.proxy")
    monkeypatch.setattr(settings.config, "community_instead_db_path", str(folder / "new-target.json"))
    assert old.network_override["proxy"]["host"] == "old.proxy"
    old.status = TaskStatus.CANCELLED
    old._future.set_result(None)
    second = api.update_external_db("instead_db")["data"]["task_id"]
    new = api.download_mgr.tasks[second]
    assert new.network_override["proxy"]["host"] == "new.proxy"
    assert new.dest_path == str(folder / "new-target.json")


def test_dataset_reader_uses_content_not_suffix(tmp_path):
    path = tmp_path / "data.json.gz"
    path.write_bytes(b'{"version":"v1","rules":[]}')
    assert WorkshopDBManager.__new__(WorkshopDBManager)._read_dataset_payload(path)["version"] == "v1"


@pytest.mark.parametrize("bad_first", [False, True])
def test_local_http_gzip_update_and_schema_fallback(external_env, monkeypatch, bad_first):
    api, events, folder = external_env
    payload = gzip.compress(b'{"version":"new","rules":[]}')
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            body = b"{}" if self.path == "/invalid" else payload
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    session = requests.Session()
    session.trust_env = False
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        urls = [base + "/invalid", base + "/valid"] if bad_first else [base + "/valid"]
        monkeypatch.setattr(api.github_mgr, "_github_download_candidates", lambda url: urls)
        monkeypatch.setattr(mgr_download, "build_retry_session", lambda **kwargs: session)
        result = api.update_external_db("instead_db")
        task = api.download_mgr.tasks[result["data"]["task_id"]]
        api.download_mgr._download_worker(task)
        assert task.status == TaskStatus.COMPLETED
        assert (folder / "instead_db.json").read_bytes() == payload
        assert SystemInfo.get_by_id("instead_version").value == "new"
        assert paths == (["/invalid", "/valid"] if bad_first else ["/valid"])
        assert len([status for status, _ in events if status == "completed"]) == 1
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_metadata_uses_api_candidates_without_commit_date_lookup(monkeypatch):
    manager = GithubManager()
    manager._response_cache.clear()
    response = MagicMock(status_code=200)
    response.json.return_value = {"sha": "a" * 40, "size": 12}
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.side_effect = [requests.ConnectionError("origin unavailable"), response]
    monkeypatch.setattr("backend.managers.mgr_github.build_retry_session", lambda **kwargs: session)
    lookup = Mock(side_effect=AssertionError("unnecessary commit lookup"))
    monkeypatch.setattr(manager, "fetch_path_commit", lookup)
    result = manager.fetch_file_metadata("test", "data", ref="main", remote_path="rules.json",
        api_candidates=["https://api.github.com/data", "https://mirror.invalid/data"])
    assert result["signature"] == "a" * 40
    assert result["updated_at"] == 0
    assert session.get.call_count == 2
    lookup.assert_not_called()


def test_check_budget_keeps_partial_results_without_starting_later_requests(monkeypatch):
    manager = MaintenanceManager.__new__(MaintenanceManager)
    manager.EXTERNAL_DATASETS = [{"data_type": str(i), "name": str(i), "path_key": "community_rules_path", "url_key": "community_rules_url"} for i in range(6)]
    manager.github_mgr = GithubManager()
    calls = []

    def check(spec, overrides, **kwargs):
        calls.append(spec["data_type"])
        time.sleep(0.07)
        return {"data_type": spec["data_type"], "exists": True, "remote_supported": True, "remote_available": True}

    monkeypatch.setattr(manager, "_check_external_dataset", check)
    monkeypatch.setattr(manager, "_check_provider_catalog", lambda *args, **kwargs: {"data_type": "git_provider_catalog", "exists": True})
    result = manager.check_external_data(budget_seconds=0.02)
    assert len(calls) <= 3
    assert len(result["items"]) == 7
    assert result["timed_out"] is True
    assert result["has_errors"] is True


def test_check_failure_reports_actual_local_file_presence(monkeypatch, tmp_path):
    manager = MaintenanceManager.__new__(MaintenanceManager)
    manager.EXTERNAL_DATASETS = [{
        "data_type": "community_rules",
        "name": "社区规则库",
        "path_key": "community_rules_path",
        "url_key": "community_rules_url",
    }]
    monkeypatch.setattr(manager, "_check_external_dataset", Mock(side_effect=RuntimeError("network unavailable")))
    monkeypatch.setattr(manager, "_check_provider_catalog", lambda *args, **kwargs: {
        "data_type": "git_provider_catalog", "exists": True,
        "remote_supported": False, "remote_available": False,
    })

    for local_path, expected in ((tmp_path / "cached.json", False), (tmp_path / "cached.json", True)):
        if expected:
            local_path.write_text("{}", encoding="utf-8")
        else:
            local_path.unlink(missing_ok=True)
        result = manager.check_external_data(overrides={
            "community_rules_path": str(local_path),
            "community_rules_url": "https://example.invalid/rules.json",
        })
        item = next(item for item in result["items"] if item["data_type"] == "community_rules")
        assert item["exists"] is expected
        assert item["remote_available"] is False


def test_cancelled_check_does_not_launch_network_requests(monkeypatch):
    manager = MaintenanceManager.__new__(MaintenanceManager)
    stop = threading.Event()
    stop.set()
    check = Mock(side_effect=AssertionError("cancelled check must not start"))
    monkeypatch.setattr(manager, "_check_external_dataset", check)
    result = manager.check_external_data(cancel_event=stop)
    assert result["cancelled"] is True
    check.assert_not_called()


def test_check_cancel_before_registration_is_not_lost(monkeypatch):
    api = API.__new__(API)
    monkeypatch.setattr(API, "_external_checks", {})

    def check(overrides, *, cancel_event, **kwargs):
        assert cancel_event.is_set()
        return {"cancelled": True, "items": [], "failed": [], "updates": []}

    api.maintenance_mgr = SimpleNamespace(check_external_data=check)
    api._log_maintenance_check = Mock()
    api.maintenance_cancel_external_data_check("early-cancel")
    result = api.maintenance_check_external_data({"check_id": "early-cancel"})
    assert result["data"]["cancelled"] is True
    assert API._external_checks == {}


def test_metadata_invalid_schema_tries_next_candidate(monkeypatch):
    manager = GithubManager()
    manager._response_cache.clear()
    bad, valid = MagicMock(status_code=200), MagicMock(status_code=200)
    bad.json.return_value = {}
    valid.json.return_value = {"sha": "a" * 40, "size": 12}
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.side_effect = [bad, valid]
    monkeypatch.setattr("backend.managers.mgr_github.build_retry_session", lambda **kwargs: session)
    result = manager.fetch_file_metadata("test", "data", ref="main", remote_path="rules.json", api_candidates=["https://bad.invalid", "https://valid.invalid"])
    assert result["size"] == 12
    assert session.get.call_count == 2
