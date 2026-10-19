import unittest
import os
import subprocess
import sys
import sysconfig
import threading
import json
import tempfile
import time
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
from unittest.mock import Mock, call, patch

from backend.settings import NetworkConfig, settings
from backend.utils.system_hosts import SystemHostsService

# 导入单例时不得应用个人配置或操作真实系统文件。
with patch.object(settings.config, "network", NetworkConfig(github_hosts_enabled=False)), patch.object(SystemHostsService, "submit"):
    from backend.managers.mgr_network import NetworkManager, PROXY_ENV_KEYS, RoutedSession, build_retry_session


class TestGithubHostsBackgroundRefresh(unittest.TestCase):
    def setUp(self):
        self.network = NetworkConfig(github_hosts_enabled=True, hosts_sources=[{"url": "https://raw.hellogithub.com/hosts", "enabled": True}])
        config_patch = patch.object(settings.config, "network", self.network)
        config_patch.start()
        self.addCleanup(config_patch.stop)
        cache_dir = tempfile.TemporaryDirectory()
        self.addCleanup(cache_dir.cleanup)
        self.cache_path = Path(cache_dir.name) / "github_hosts.json"
        cache_patch = patch("backend.managers.mgr_network.GITHUB_HOSTS_CACHE_PATH", self.cache_path)
        cache_patch.start()
        self.addCleanup(cache_patch.stop)
        with patch.object(NetworkManager, "apply"):
            self.manager = NetworkManager()
        self.addCleanup(self._wait_cache)
        self.addCleanup(self.manager.close)

    def _wait_cache(self):
        thread = self.manager._hosts_cache_thread
        if thread is not None:
            thread.join(2)

    def test_system_hosts_authorization_is_explicit_and_preview_never_applies(self):
        self.network.github_hosts_enabled = False
        self.network.write_to_system_hosts = True
        self.network.hosts = {"saved.example": "1.2.3.4"}
        with patch.object(self.manager._system_hosts, "submit") as submit:
            self.manager.apply(startup=True)
            submit.assert_called_with({"saved.example": "1.2.3.4"}, allow_elevation=False)
            self.manager.apply(allow_system_hosts_elevation=True)
            submit.assert_called_with({"saved.example": "1.2.3.4"}, allow_elevation=True)
            self.manager._github_hosts_preview_state = {"status": "ready", "source_url": "unsaved", "hosts": {"preview.example": "5.6.7.8"}, "updated_at": 1}
            state = self.manager.retry_system_hosts()
            submit.assert_called_with({"saved.example": "1.2.3.4"}, allow_elevation=True)
        self.assertNotIn("preview.example", state["effective_hosts"])

    def test_system_hosts_errors_have_persistent_localized_messages(self):
        for code, key in (("ELEVATION_CANCELLED", "authorization_cancelled"), ("AUTHORIZATION_TIMEOUT", "authorization_timeout"),
                           ("CONTENT_CHANGED", "content_changed"), ("TIMEOUT", "write_timeout")):
            with self.subTest(code=code), patch.object(self.manager._system_hosts, "status", return_value={
                "status": "error", "error_code": f"NETWORK.HOSTS.{code}", "removing": False,
            }):
                state = self.manager.get_github_hosts_status()["system_hosts"]
                self.assertEqual(state["message_key"], f"network.hosts.{key}")
                self.assertTrue(state["message"])
        message = self.manager._system_hosts_message({"status": "error", "removing": True})
        self.assertEqual(message.message_key, "network.hosts.system_remove_failed")

    def test_system_write_does_not_hold_network_lock_or_delay_save_apply(self):
        self.network.github_hosts_enabled = False
        self.network.write_to_system_hosts = True
        self.network.hosts = {"example.org": "1.2.3.4"}
        started, release = threading.Event(), threading.Event()

        def write(hosts, **kwargs):
            started.set()
            release.wait(2)
            return {"status": "success", "error_code": ""}

        with patch.object(self.manager._system_hosts, "_execute", side_effect=write):
            try:
                self.manager.apply()
                self.assertTrue(started.wait(1))
                before = time.perf_counter()
                state = self.manager.get_github_hosts_status()
                self.assertLess(time.perf_counter() - before, 0.2)
                self.assertEqual(state["system_hosts"]["status"], "applying")
                self.assertEqual(state["effective_hosts"], {"example.org": "1.2.3.4"})
            finally:
                release.set()
                self.manager.close()
        self.assertFalse(self.manager._system_hosts._thread.is_alive())

    def test_close_cancels_wait_for_dynamic_source_without_late_commit(self):
        started, release = threading.Event(), threading.Event()

        def fetch(*args, **kwargs):
            started.set()
            release.wait(2)
            return Mock(text="1.2.3.4 example.org")

        with patch("backend.managers.mgr_network.requests.Session.get", side_effect=fetch), patch.object(self.manager, "_apply_hosts") as apply:
            try:
                self.manager.refresh_github_hosts()
                self.assertTrue(started.wait(1))
                self.manager.close()
                self.manager._github_hosts_thread.join(0.5)
                self.assertFalse(self.manager._github_hosts_thread.is_alive())
                apply.assert_not_called()
                self.assertFalse(self.cache_path.exists())
            finally:
                release.set()

    def test_disabled_preview_hosts_ignore_stale_effective_hosts_payload(self):
        route = self.manager.request_route(
            "https://github.com/example/repo",
            network_override={
                "github_hosts_enabled": False,
                "effective_hosts": {"github.com": "1.2.3.4"},
                "hosts": {},
                "proxy": {"enabled": False},
            },
        )
        self.assertFalse(route["hosts_hit"])
        self.assertEqual(route["hosts_ip"], "")

    def test_hosts_preview_uses_snapshot_when_form_payload_changes(self):
        started, release = threading.Event(), threading.Event()
        payload = {
            "github_hosts_enabled": True,
            "hosts_sources": [{"url": "https://original.example/hosts", "enabled": True}],
            "proxy": {"enabled": False},
        }

        def fetch(url, **kwargs):
            started.set()
            release.wait(2)
            return Mock(text="1.2.3.4 example.org")

        with patch("backend.managers.mgr_network.requests.Session.get", side_effect=fetch) as request:
            try:
                self.manager.refresh_github_hosts(payload)
                self.assertTrue(started.wait(1))
                payload["hosts_sources"][0]["url"] = "https://mutated.example/hosts"
                payload["proxy"]["enabled"] = True
            finally:
                release.set()
                self.manager._github_hosts_preview_thread.join(2)

        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "https://original.example/hosts")
        self.assertEqual(request.call_args.kwargs["timeout"], (15, 60))
        self.assertEqual(request.call_args.kwargs["headers"]["Accept"], "text/plain, application/json")

    def test_multiple_sources_merge_in_order_despite_completion_order_and_partial_failure(self):
        first_ready = threading.Event()
        sources = ["https://first.example/hosts", "https://second.example/hosts.json", "https://failed.example/hosts"]
        self.network.hosts_sources = [{"url": url, "enabled": True} for url in [*sources, sources[0]]]
        self.network.hosts = {"other.example": "9.9.9.9"}

        def fetch(url, **kwargs):
            if url == sources[0]:
                self.assertTrue(first_ready.wait(1))
                return Mock(text="1.2.3.4 example.org")
            if url == sources[1]:
                first_ready.set()
                return Mock(text=json.dumps({"example.org": "2.3.4.5", "other.example": "3.4.5.6"}))
            raise requests.Timeout("slow")

        with patch("backend.managers.mgr_network.requests.Session.get", side_effect=fetch) as request, patch.object(self.manager, "_apply_hosts"):
            self.manager.refresh_github_hosts()
            self.manager._github_hosts_thread.join(2)
        self.assertEqual(request.call_count, 3)
        state = self.manager.get_github_hosts_status()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["source_errors"], [{"url": sources[2], "error": "timeout"}])
        self.assertEqual(state["hosts"], {"example.org": "1.2.3.4", "other.example": "3.4.5.6"})
        self.assertEqual(state["dynamic_hosts"], {"example.org": "1.2.3.4"})
        self.assertEqual(state["effective_hosts"]["other.example"], "9.9.9.9")

    def test_unsaved_source_does_not_replace_applied_cache_and_can_be_cancelled(self):
        response = Mock(text="1.2.3.4 example.org")
        with patch("backend.managers.mgr_network.requests.Session.get", return_value=response), patch.object(self.manager, "_apply_hosts"):
            self.manager.refresh_github_hosts()
            self.manager._github_hosts_thread.join(2)
            self._wait_cache()
            cache = self.cache_path.read_text(encoding="utf-8")
            self.manager.refresh_github_hosts({"github_hosts_enabled": True, "hosts_sources": [{"url": "https://other.example/hosts", "enabled": True}]})
            self.manager._github_hosts_preview_thread.join(2)
            self.assertEqual(self.cache_path.read_text(encoding="utf-8"), cache)
            state = self.manager.get_github_hosts_status()
            self.assertTrue(state["is_applied"])
            self.assertEqual(state["source_url"], "https://raw.hellogithub.com/hosts")
            self.assertEqual(state["preview"]["source_url"], "https://other.example/hosts")

        started, release = threading.Event(), threading.Event()

        def fetch(*args, **kwargs):
            started.set()
            release.wait(3)
            return Mock(text="2.3.4.5 example.org")

        with patch("backend.managers.mgr_network.requests.Session.get", side_effect=fetch), patch.object(self.manager, "_apply_hosts") as apply_hosts:
            try:
                self.manager.refresh_github_hosts({"github_hosts_enabled": True, "hosts_sources": [{"url": "https://other.example/hosts", "enabled": True}]})
                self.assertTrue(started.wait(1))
                self.manager.refresh_github_hosts({"github_hosts_enabled": False})
            finally:
                release.set()
                self.manager._github_hosts_preview_thread.join(2)
            apply_hosts.assert_not_called()
        self.assertEqual(self.manager.get_github_hosts_status()["preview"]["status"], "idle")
        self.assertEqual(self.manager.get_effective_hosts(), {"example.org": "1.2.3.4"})

    def test_timeout_preserves_old_mapping_and_retry_can_succeed(self):
        self.manager._dynamic_github_hosts = {"github.com": "140.82.112.4"}
        with patch("backend.managers.mgr_network.requests.Session.get", side_effect=requests.Timeout("slow")):
            self.manager.refresh_github_hosts()
            self.manager._github_hosts_thread.join(2)
        state = self.manager.get_github_hosts_status()
        self.assertEqual((state["status"], state["error"]), ("error", "timeout"))
        self.assertEqual(state["effective_hosts"], {"github.com": "140.82.112.4"})
        response = Mock(text="140.82.113.4 github.com")
        with patch("backend.managers.mgr_network.requests.Session.get", return_value=response), patch.object(self.manager, "_apply_hosts"):
            self.manager.refresh_github_hosts()
            self.manager._github_hosts_thread.join(2)
        self.assertEqual(self.manager.get_github_hosts_status()["status"], "ready")
        self.assertEqual(self.manager.get_effective_hosts(), {"github.com": "140.82.113.4"})

    def test_old_source_completion_does_not_replace_new_source(self):
        release = threading.Event()
        started = threading.Event()
        old_source = NetworkManager.split_hosts_sources(self.network.hosts_sources)[0]

        def fetch(url, **kwargs):
            if url == old_source:
                started.set()
                release.wait(3)
                return Mock(text="140.82.112.4 github.com")
            return Mock(text="140.82.113.4 github.com")

        with patch("backend.managers.mgr_network.requests.Session.get", side_effect=fetch), patch.object(self.manager, "_apply_hosts"):
            self.manager.refresh_github_hosts()
            old_task = self.manager._github_hosts_thread
            try:
                self.assertTrue(started.wait(1))
                self.network.hosts_sources = [{"url": "https://example.invalid/new-hosts", "enabled": True}]
                self.manager.refresh_github_hosts()
                self.manager._github_hosts_thread.join(2)
            finally:
                release.set()
                old_task.join(2)
        state = self.manager.get_github_hosts_status()
        self.assertEqual(state["source_url"], "https://example.invalid/new-hosts")
        self.assertEqual(state["hosts"], {"github.com": "140.82.113.4"})
        self.assertEqual(self.manager.get_effective_hosts(), {"github.com": "140.82.113.4"})

    def test_invalid_source_reports_error_without_request(self):
        with patch("backend.managers.mgr_network.requests.Session.get") as fetch:
            self.network.hosts_sources = [{"url": "http://example.invalid/hosts", "enabled": True}]
            self.manager.refresh_github_hosts()
            self.manager._github_hosts_thread.join(2)
        self.assertEqual(self.manager.get_github_hosts_status()["status"], "error")
        fetch.assert_not_called()

class TestNetworkTransportStartup(unittest.TestCase):
    def test_routed_session_only_prepares_requested_url(self):
        route_manager = Mock()
        response = Mock(status_code=200)
        with patch.object(requests.Session, "request", return_value=response) as request, \
            patch("backend.managers.mgr_github.GithubManager._github_download_candidates") as candidates:
            session = RoutedSession(route_manager=route_manager)
            result = session.get("https://github.com/example/repo")

        self.assertIs(result, response)
        route_manager.prepare_session_for_url.assert_called_once_with(
            session, "https://github.com/example/repo", network_override=None,
        )
        candidates.assert_not_called()
        request.assert_called_once()

    def test_socks_proxy_adapter_is_available(self):
        from requests.adapters import SOCKSProxyManager
        self.assertIsNotNone(SOCKSProxyManager('socks5://127.0.0.1:9'))

    def test_system_certificates_are_enabled_without_site_startup(self):
        site_packages = sysconfig.get_path('purelib')
        code = f'import sys; sys.path.insert(0, {site_packages!r}); import ssl; assert ssl.SSLContext.__module__ == "ssl"; from unittest.mock import patch; from backend.settings import settings, NetworkConfig; settings.config.network = NetworkConfig(github_hosts_enabled=False); from backend.utils.system_hosts import SystemHostsService; p = patch.object(SystemHostsService, "submit"); p.start(); import backend.managers.mgr_network; assert "truststore" in ssl.SSLContext.__module__'
        result = subprocess.run([sys.executable, '-S', '-c', code], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


class TestNetworkManagerHostsCleanup(unittest.TestCase):
    def test_hosts_preview_is_thread_local_and_empty_mapping_disables_saved_hosts(self):
        manager = NetworkManager.__new__(NetworkManager)
        manager._is_socket_patched = False
        manager._original_getaddrinfo = Mock(side_effect=lambda host, *args: host)
        barrier, release = threading.Barrier(3), threading.Event()

        def resolve(hosts):
            with manager.hosts_override(hosts):
                barrier.wait(timeout=3)
                if not release.wait(3):
                    raise AssertionError("等待主线程验证超时")
                return socket.getaddrinfo("github.com", 443)

        with patch.object(manager, "_effective_hosts", return_value={"github.com": "1.1.1.1"}), \
            patch("backend.managers.mgr_network.socket.getaddrinfo"):
            manager.patch_socket_for_hosts()
            with ThreadPoolExecutor(max_workers=2) as executor:
                enabled = executor.submit(resolve, {"github.com": "2.2.2.2"})
                disabled = executor.submit(resolve, {})
                try:
                    barrier.wait(timeout=3)
                    self.assertEqual(socket.getaddrinfo("github.com", 443), "1.1.1.1")
                finally:
                    release.set()
                self.assertEqual(enabled.result(timeout=3), "2.2.2.2")
                self.assertEqual(disabled.result(timeout=3), "github.com")
            with manager.hosts_override({"github.com": "3.3.3.3"}):
                with self.assertRaises(ValueError):
                    with manager.hosts_override({}):
                        raise ValueError("test")
                self.assertEqual(socket.getaddrinfo("github.com", 443), "3.3.3.3")
            self.assertEqual(socket.getaddrinfo("github.com", 443), "1.1.1.1")

    def test_network_check_applies_form_hosts_inside_probe_threads(self):
        manager = NetworkManager.__new__(NetworkManager)
        manager._is_socket_patched = False
        manager._original_getaddrinfo = Mock(side_effect=lambda host, *args: host)
        observed = []

        def fake_get(url, **kwargs):
            observed.append(socket.getaddrinfo("github.com", 443))
            return Mock(status_code=200, url=url)

        with patch.object(manager, "_effective_hosts", return_value={"github.com": "1.1.1.1"}), \
            patch("backend.managers.mgr_network.socket.getaddrinfo"), \
            patch.object(requests.Session, "get", side_effect=fake_get):
            manager.patch_socket_for_hosts()
            manager.check_network_access({"github_mirror_id": "direct", "network": {
                "hosts": {"github.com": "2.2.2.2"}, "proxy": {"enabled": False},
            }})
            self.assertTrue(observed)
            self.assertEqual(set(observed), {"2.2.2.2"})
            self.assertEqual(socket.getaddrinfo("github.com", 443), "1.1.1.1")

    def test_network_access_check_reports_latency_and_failures(self):
        manager = NetworkManager.__new__(NetworkManager)
        config = settings.config
        previous_id = getattr(config, "github_mirror_id", "direct")
        previous_mirrors = getattr(config, "github_mirrors", [])
        self.addCleanup(setattr, config, "github_mirror_id", previous_id)
        self.addCleanup(setattr, config, "github_mirrors", previous_mirrors)
        config.github_mirror_id = "direct"
        config.github_mirrors = []

        def fake_get(url, **kwargs):
            if "sourceforge.net" in url:
                raise requests.Timeout("slow")
            if "gitee.com" in url:
                response = Mock(status_code=403)
                response.headers = {"Content-Type": "text/plain"}
                response.raw.read.side_effect = AssertionError("检测不得读取响应正文")
                response.close = Mock()
                return response
            response = Mock(status_code=200)
            response.close = Mock()
            return response

        with patch("backend.managers.mgr_network.requests.Session.get", side_effect=fake_get) as fetch, \
            patch("backend.managers.mgr_network.requests.Session.head", side_effect=fake_get) as head:
            result = manager.check_network_access()

        domains = {item["domain"] for item in result["targets"]}
        self.assertTrue({
            "api.github.com", "raw.githubusercontent.com", "codeload.github.com",
            "images.steamusercontent.com", "steamuserimages-a.akamaihd.net",
            "steamcommunity.com", "api.steampowered.com", "gitgud.io",
            "steamcdn-a.akamaihd.net", "client-update.steamstatic.com",
            "dl.steam.clngaa.com", "st.dl.eccdnx.com",
        }.issubset(domains))
        self.assertNotIn("xz.pphimalayanrt.com", domains)
        self.assertNotIn("wwbns.lanzouu.com", domains)
        self.assertTrue(domains.isdisjoint({
            "avatars.steamstatic.com", "avatars.fastly.steamstatic.com", "community.fastly.steamstatic.com",
            "shared.fastly.steamstatic.com",
        }))
        self.assertEqual(len(domains), len(result["targets"]))
        self.assertEqual(len({item["id"] for item in result["targets"]}), len(result["targets"]))
        steamcmd_urls = {item["id"]: item["url"] for item in result["targets"] if item["id"].startswith("steamcmd_")}
        self.assertEqual(steamcmd_urls, {
            "steamcmd_install": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip",
            "steamcmd_update": "https://client-update.steamstatic.com/steam_cmd_win32",
            "steamcmd_cdn_clngaa": "http://dl.steam.clngaa.com/",
            "steamcmd_cdn_eccdnx": "http://st.dl.eccdnx.com/",
        })
        sourceforge = next(item for item in result["targets"] if item["id"] == "sourceforge")
        gitee = next(item for item in result["targets"] if item["id"] == "gitee")
        github = next(item for item in result["targets"] if item["id"] == "github")
        self.assertEqual(sourceforge["status"], "timeout")
        self.assertFalse(sourceforge["reachable"])
        self.assertEqual(gitee["status"], "http_error")
        self.assertEqual(gitee["http_status"], 403)
        self.assertTrue(all("response_preview" not in item for item in result["targets"]))
        self.assertIn("拒绝", gitee["error"])
        self.assertEqual(github["status"], "ok")
        self.assertIsInstance(github["latency_ms"], float)
        self.assertTrue(all(call.kwargs["stream"] for call in fetch.call_args_list))
        self.assertEqual(head.call_count, 0)
        file_calls = [call for call in fetch.call_args_list if "codeload.github.com" in call.args[0] or "raw.githubusercontent.com" in call.args[0]]
        self.assertEqual(len(file_calls), 2)
        self.assertTrue(all(call.kwargs["headers"]["Range"] == "bytes=0-0" for call in file_calls))
        self.assertTrue(all(call.kwargs["headers"]["Accept-Encoding"] == "identity" for call in file_calls))
        self.assertTrue(any("sourceforge.net/projects/rimcrow/files/latest/download?format=json" in call.args[0] for call in fetch.call_args_list))
        self.assertFalse(any("/releases/download/" in call.args[0] for call in fetch.call_args_list))

    def test_file_probe_checks_range_headers_and_body(self):
        manager = NetworkManager.__new__(NetworkManager)
        cases = [
            (206, {"Content-Range": "bytes 0-0/4", "Content-Length": "1"}, [b"d"], True),
            (206, {"Content-Range": "bytes 1-1/4"}, [b"d"], False),
            (206, {"Content-Range": "bytes 0-0/4", "Content-Length": "2"}, [b"d"], False),
            (206, {"Content-Range": "bytes 0-0/4", "Content-Encoding": "gzip"}, [b"d"], False),
            (206, {"Content-Range": "bytes 0-0/4"}, [], False),
            (206, {"Content-Range": "bytes 0-0/4"}, [b"da"], False),
            (206, {"Content-Range": "bytes 0-0/4"}, [b"d", b"a"], False),
            (200, {"Content-Length": "4096"}, [], False),
        ]
        for status, headers, chunks, supports_range in cases:
            with self.subTest(status=status, headers=headers, chunks=chunks):
                responses = []

                def fake_get(url, **kwargs):
                    response = Mock(status_code=status, url=url)
                    response.headers = requests.structures.CaseInsensitiveDict(headers)
                    response.iter_content.return_value = iter(chunks)
                    responses.append(response)
                    return response

                with patch("backend.managers.mgr_network.requests.Session.get", side_effect=fake_get):
                    result = manager.check_network_access({"github_mirror_id": "direct", "network": {"proxy": {"enabled": False}}})
                files = [item for item in result["targets"] if item["id"] in {"github_archive", "github_raw"}]
                self.assertEqual(len(files), 2)
                for item in files:
                    self.assertEqual(item["range_supported"], supports_range)
                    self.assertEqual(item["status"], "ok" if status == 200 or supports_range else "failed")
                    if item["status"] == "failed":
                        self.assertEqual(item["error_code"], "NETWORK.INVALID_RESPONSE")
                for response in responses:
                    response.close.assert_called_once()
                    if status == 200:
                        response.iter_content.assert_not_called()

    def test_network_access_check_applies_selected_github_mirror_to_download_target(self):
        manager = NetworkManager.__new__(NetworkManager)
        config = settings.config
        previous_id = getattr(config, "github_mirror_id", "direct")
        previous_mirrors = getattr(config, "github_mirrors", [])
        self.addCleanup(setattr, config, "github_mirror_id", previous_id)
        self.addCleanup(setattr, config, "github_mirrors", previous_mirrors)
        config.github_mirror_id = "direct"
        config.github_mirrors = []
        response = Mock(status_code=204)
        response.close = Mock()
        with patch("backend.managers.mgr_network.requests.Session.get", return_value=response), \
            patch("backend.managers.mgr_network.requests.Session.head", return_value=response):
            result = manager.check_network_access({
                "github_mirror_id": "custom:mirror",
                "github_mirrors": [{
                    "id": "mirror", "label": "测试镜像",
                    "url_template": "https://mirror.example/{url}",
                    "support": {"archive": {"status": "supported"}},
                }],
                "network": {"proxy": {"enabled": False}},
            })
        self.assertFalse(any(item["id"] == "github_mirror" for item in result["targets"]))
        archive = next(item for item in result["targets"] if item["id"] == "github_archive")
        self.assertEqual(archive["source_url"], "https://codeload.github.com/Inky-Feather/RimCrow/zip/refs/heads/main")
        self.assertEqual(archive["url"], "https://mirror.example/https://codeload.github.com/Inky-Feather/RimCrow/zip/refs/heads/main")
        self.assertEqual(archive["mirror_label"], "测试镜像")
        github = next(item for item in result["targets"] if item["id"] == "github")
        self.assertEqual(github["url"], "https://github.com/Inky-Feather/RimCrow")
        self.assertNotIn("mirror_label", github)

    def test_network_access_plan_keeps_project_and_mirror_rows_separate(self):
        manager = NetworkManager.__new__(NetworkManager)
        plan = manager.check_network_access({
            "github_mirror_id": "custom:mirror",
            "github_mirrors": [{
                "id": "mirror", "label": "测试镜像",
                "url_template": "https://mirror.example/{url}",
                "support": {"web": {"status": "supported"}},
            }],
            "network": {"proxy": {"enabled": False}},
        }, plan_only=True)
        project_rows = [item for item in plan["targets"] if item["id"] == "github"]
        self.assertEqual(len(project_rows), 1)
        self.assertEqual(project_rows[0]["domain"], "mirror.example")
        self.assertEqual(project_rows[0]["status"], "loading")
        self.assertEqual(project_rows[0]["source_url"], "https://github.com/Inky-Feather/RimCrow")

    def test_network_access_plan_keeps_github_archive_and_raw_when_mirror_shares_origin(self):
        manager = NetworkManager.__new__(NetworkManager)
        plan = manager.check_network_access({
            "github_mirror_id": "custom:mirror",
            "github_mirrors": [{
                "id": "mirror", "label": "测试镜像",
                "url_template": "https://mirror.example/{url}",
                "support": {"web": {"status": "supported"}, "archive": {"status": "supported"}, "raw": {"status": "supported"}},
            }],
            "network": {"proxy": {"enabled": False}},
        }, plan_only=True)
        targets = {item["id"]: item for item in plan["targets"]}
        self.assertEqual(targets["github"]["domain"], "mirror.example")
        self.assertEqual(targets["github_archive"]["domain"], "mirror.example")
        self.assertEqual(targets["github_raw"]["domain"], "mirror.example")
        self.assertIn("github_api", targets)

    def test_network_access_deduplicates_github_config_source_before_mirroring(self):
        manager = NetworkManager.__new__(NetworkManager)
        config = settings.config
        with patch.object(config, "community_rules_url", "https://github.com/example/config.json"), \
            patch("backend.managers.mgr_update._load_project_meta", return_value={"update": {"sources": []}}):
            plan = manager.check_network_access({
                "github_mirror_id": "custom:mirror",
                "github_mirrors": [{
                    "id": "mirror", "label": "测试镜像",
                    "url_template": "https://mirror.example/{url}",
                    "support": {"web": {"status": "supported"}},
                }],
                "network": {"proxy": {"enabled": False}},
            }, plan_only=True)

        self.assertFalse(any(item["id"] == "community_rules" for item in plan["targets"]))
        github = next(item for item in plan["targets"] if item["id"] == "github")
        self.assertEqual(github["domain"], "mirror.example")
        self.assertFalse(any(item.get("source_url") == "https://github.com/example/config.json" for item in plan["targets"]))

    def test_network_access_target_filter_probes_only_requested_row(self):
        manager = NetworkManager.__new__(NetworkManager)
        response = Mock(status_code=204, url="https://github.com/Inky-Feather/RimCrow")
        response.close = Mock()
        response.headers = {}
        with patch("backend.managers.mgr_network.requests.Session.get", return_value=response) as fetch:
            result = manager.check_network_access({"network": {"proxy": {"enabled": False}}}, target_ids=["github"])
        self.assertEqual([item["id"] for item in result["targets"]], ["github"])
        self.assertEqual(fetch.call_count, 1)

    def test_network_access_check_uses_configured_sources_and_download_redirects(self):
        manager = NetworkManager.__new__(NetworkManager)
        config = settings.config
        response = Mock(status_code=200)
        response.url = "https://release-assets.githubusercontent.com/example/asset.zip"
        meta = {"update": {"sources": [
            {"type": "manifest", "url": "https://updates.example/manifest.json"},
            {"type": "manifest", "url": "file:///private/config.json"},
            {"type": "manifest", "url": "https://user:password@private.example/manifest.json"},
        ]}}
        with patch.object(config, "community_workshop_db_url", "https://database.example/data.json"), \
            patch.object(config, "community_rules_url", "https://DATABASE.example:443/rules.json"), \
            patch.object(config, "git_provider_catalog_url", "One|https://catalog.example/one.json,Two|https://catalog.example/two.json,Port|https://catalog.example:8443/three.json,Invalid|https://invalid.example:bad/data.json"), \
            patch("backend.managers.mgr_update._load_project_meta", return_value=meta), \
            patch("backend.managers.mgr_network.requests.Session.get", return_value=response) as fetch, \
            patch("backend.managers.mgr_network.requests.Session.head", return_value=response):
            result = manager.check_network_access({"network": {
                "proxy": {"enabled": False}, "github_hosts_enabled": True,
                "hosts_sources": [{"url": "https://hosts.example/hosts.json", "enabled": True}],
            }, "github_mirror_id": "direct"})
            urls = [item["url"] for item in result["targets"]]
            self.assertNotIn("https://database.example/data.json", urls)
            self.assertTrue({
                "https://hosts.example/hosts.json", "https://updates.example/manifest.json",
                "https://catalog.example/one.json", "https://catalog.example:8443/three.json",
            }.issubset(urls))
            self.assertNotIn("https://catalog.example/two.json", urls)
            self.assertIn("https://DATABASE.example:443/rules.json", urls)
            self.assertFalse(any("invalid.example" in url for url in urls))
            self.assertFalse(any("private" in url for url in urls))
            self.assertTrue(all(item["domain"] == "release-assets.githubusercontent.com" for item in result["targets"]))
            self.assertTrue(all(item["final_url"] == response.url for item in result["targets"]))
            fetch.reset_mock()
            manager.check_network_access({"network": {
                "proxy": {"enabled": False}, "github_hosts_enabled": False,
                "hosts_sources": [{"url": "https://hosts.example/hosts.json", "enabled": True}],
            }, "github_mirror_id": "direct"})
            self.assertNotIn("https://hosts.example/hosts.json", [call.args[0] for call in fetch.call_args_list])

    def test_public_effective_hosts_is_a_copy_with_manual_overrides(self):
        manager = NetworkManager.__new__(NetworkManager)
        manager._dynamic_github_hosts = {
            "github.com": "140.82.112.4",
            "api.github.com": "140.82.113.6",
        }
        network = settings.config.network
        with patch.object(network, "github_hosts_enabled", True), patch.object(
            network, "hosts", {" GitHub.COM. ": "140.82.114.4"}
        ):
            result = manager.get_effective_hosts()
            self.assertEqual(result, {
                "github.com": "140.82.114.4",
                "api.github.com": "140.82.113.6",
            })
            result.clear()
            self.assertEqual(len(manager.get_effective_hosts()), 2)
            self.assertEqual(manager._dynamic_github_hosts["github.com"], "140.82.112.4")
        with patch.object(network, "github_hosts_enabled", False), patch.object(network, "hosts", {}):
            self.assertEqual(manager.get_effective_hosts(), {})

    def test_parse_github_hosts_keeps_all_valid_domains(self):
        parsed = NetworkManager.parse_github_hosts(
            """
            # GitHub520 Host Start
            140.82.112.4 github.com api.github.com
            185.199.108.133 raw.githubusercontent.com
            1.2.3.4 evil.example
            not-an-ip codeload.github.com
            # GitHub520 Host End
            """
        )
        self.assertEqual(parsed, {
            "github.com": "140.82.112.4",
            "api.github.com": "140.82.112.4",
            "raw.githubusercontent.com": "185.199.108.133",
            "evil.example": "1.2.3.4",
        })

    def test_parse_github_hosts_json_and_text_have_identical_mappings(self):
        expected = {"alive.github.com": "140.82.112.25", "example.org": "2001:db8::1"}
        for text in (
            "\ufeff140.82.112.25 ALIVE.GITHUB.COM. # comment\n2001:db8::1 example.org",
            json.dumps([["140.82.112.25", "alive.github.com"], ["2001:db8::1", "example.org"]]),
            json.dumps(expected),
        ):
            with self.subTest(text=text):
                self.assertEqual(NetworkManager.parse_github_hosts(text), expected)
        self.assertEqual(NetworkManager.parse_github_hosts(json.dumps([
            ["invalid", "github.com"], ["1.2.3.4", "https://example.org", "bad_name", "-bad.org"],
            ["::1%bad\ninjection", "example.org"], None, ["1.2.3.4", {}],
        ])), {})
        self.assertEqual(NetworkManager.parse_github_hosts('[broken json'), {})
        self.assertEqual(NetworkManager.parse_github_hosts('1.2.3.4 example.org\n2.3.4.5 example.org'), {"example.org": "2.3.4.5"})

    def test_refresh_github_hosts_updates_runtime_map_without_system_hosts(self):
        with patch.object(NetworkManager, "apply"):
            manager = NetworkManager()
        self.addCleanup(manager.close)
        response = Mock(status_code=200, text="140.82.112.4 github.com\n")
        response.raise_for_status.return_value = None
        network = settings.config.network
        snapshot = {
            "github_hosts_enabled": network.github_hosts_enabled,
            "hosts_sources": network.hosts_sources,
            "github_hosts_updated_at": network.github_hosts_updated_at,
            "hosts": dict(network.hosts or {}),
            "write_to_system_hosts": network.write_to_system_hosts,
        }
        self.addCleanup(lambda: [setattr(network, key, value) for key, value in snapshot.items()])
        network.github_hosts_enabled = True
        network.hosts_sources = [{"url": "https://example.invalid/github520-hosts", "enabled": True}]
        network.github_hosts_updated_at = 0
        network.hosts = {}
        network.write_to_system_hosts = False
        with patch("backend.managers.mgr_network.requests.Session.get", return_value=response) as fetch, \
            patch.object(manager, "_apply_hosts"), patch("backend.managers.mgr_network.write_json_atomic"):
            manager.refresh_github_hosts()
            manager._github_hosts_thread.join(2)
            if manager._hosts_cache_thread is not None:
                manager._hosts_cache_thread.join(2)
        self.assertEqual(manager.get_github_hosts_status()["status"], "ready")
        self.assertEqual(fetch.call_args.kwargs["timeout"], (15, 60))
        response.close.assert_called_once()
        self.assertEqual(manager._effective_hosts(), {"github.com": "140.82.112.4"})

    def test_effective_hosts_normalizes_manual_host_names(self):
        manager = NetworkManager.__new__(NetworkManager)
        manager._dynamic_github_hosts = {}
        network = settings.config.network
        previous_enabled = network.github_hosts_enabled
        previous_hosts = dict(network.hosts or {})
        self.addCleanup(setattr, network, "github_hosts_enabled", previous_enabled)
        self.addCleanup(setattr, network, "hosts", previous_hosts)
        network.github_hosts_enabled = False
        network.hosts = {" GitHub.COM. ": "140.82.112.4", "": ""}

        self.assertEqual(manager._effective_hosts(), {"github.com": "140.82.112.4"})

class TestRoutedRetrySession(unittest.TestCase):
    def test_explicit_false_disables_global_routing(self):
        from backend.managers.mgr_network import network_mgr

        with patch.object(network_mgr, "prepare_session_for_url") as prepare, \
            patch.object(requests.Session, "request", return_value=Mock(status_code=200)):
            with build_retry_session(route_manager=False) as session:
                session.get("https://github.com/example")
        prepare.assert_not_called()

    def test_each_request_recomputes_url_route(self):
        manager = Mock()
        manager.prepare_session_for_url.side_effect = lambda session, url, **kwargs: session.proxies.clear()
        with patch.object(settings.config, "github_mirror_id", "direct"), \
            patch.object(requests.Session, "request", return_value=Mock(status_code=200)) as request:
            session = build_retry_session(route_manager=manager)
            try:
                session.get("https://github.com/example")
                session.get("https://sourceforge.net/projects/example/files/latest/download")
            finally:
                session.close()

        self.assertEqual(manager.prepare_session_for_url.call_count, 2)
        self.assertEqual(
            [call.args[1] for call in manager.prepare_session_for_url.call_args_list],
            ["https://github.com/example", "https://sourceforge.net/projects/example/files/latest/download"],
        )
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
