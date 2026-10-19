import ast
import errno
import json
import io
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import backend.utils.system_hosts as system_hosts
from backend.utils.system_hosts import SystemHostsService, update_system_hosts


class TestSystemHostsFile(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "hosts"
        self.original = b"\xef\xbb\xbf# user comment\r\n127.0.0.1\tlocalhost\r\n# non-UTF8: \xff\r\n"
        self.path.write_bytes(self.original)

    def test_apply_and_remove_preserve_unrelated_bytes(self):
        self.assertTrue(update_system_hosts(self.path, {"example.org": "1.2.3.4"}))
        self.assertTrue(self.path.read_bytes().startswith(self.original))
        self.assertIn(b"1.2.3.4\texample.org\r\n", self.path.read_bytes())
        self.assertFalse(update_system_hosts(self.path, {"example.org": "1.2.3.4"}))
        self.assertTrue(update_system_hosts(self.path, {}))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob(".rimcrow-hosts-*")), [])

    def test_permission_denied_is_not_retried(self):
        with patch("backend.utils.system_hosts.os.open", side_effect=PermissionError(errno.EACCES, "denied")) as create:
            with self.assertRaises(PermissionError):
                update_system_hosts(self.path, {"example.org": "1.2.3.4"})
        self.assertEqual(create.call_count, 1)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_only_real_collisions_are_retried_with_a_limit(self):
        with patch("backend.utils.system_hosts.os.open", side_effect=FileExistsError()) as create:
            with self.assertRaises(FileExistsError):
                update_system_hosts(self.path, {"example.org": "1.2.3.4"})
        self.assertEqual(create.call_count, 3)

    def test_failed_flush_preserves_original_and_removes_temp_file(self):
        with patch("backend.utils.system_hosts.os.fsync", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                update_system_hosts(self.path, {"example.org": "1.2.3.4"})
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob(".rimcrow-hosts-*")), [])

    def test_concurrent_external_change_is_not_overwritten(self):
        external = self.original + b"# external change\n"
        with patch.object(Path, "read_bytes", side_effect=[self.original, external]):
            with self.assertRaisesRegex(OSError, "changed"):
                update_system_hosts(self.path, {"example.org": "1.2.3.4"})
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_invalid_mappings_and_broken_markers_do_not_write(self):
        for hosts in ({"example.org\nlocalhost": "1.2.3.4"}, {"example.org": "1.2.3.4\n"}, {"example.org": "fe80::1%eth0"}):
            with self.subTest(hosts=hosts), self.assertRaises(ValueError):
                update_system_hosts(self.path, hosts)
        broken = self.original + b"# --- RimCrow Hosts Start ---\n"
        self.path.write_bytes(broken)
        with self.assertRaises(ValueError):
            update_system_hosts(self.path, {})
        self.assertEqual(self.path.read_bytes(), broken)

    def test_cancelled_commit_preserves_original_and_removes_temporary_file(self):
        def cancel():
            raise ConnectionAbortedError("cancelled")

        with self.assertRaises(ConnectionAbortedError):
            update_system_hosts(self.path, {"example.org": "1.2.3.4"}, before_replace=cancel)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob(".rimcrow-hosts-*")), [])

    def test_external_change_while_awaiting_commit_is_not_overwritten(self):
        external = self.original + b"# another program\n"
        with self.assertRaises(system_hosts.HostsChangedError):
            update_system_hosts(self.path, {"example.org": "1.2.3.4"}, before_replace=lambda: self.path.write_bytes(external))
        self.assertEqual(self.path.read_bytes(), external)

    def test_identical_content_needs_no_commit_or_permission(self):
        update_system_hosts(self.path, {"example.org": "1.2.3.4"})
        confirm = Mock()
        self.assertFalse(update_system_hosts(self.path, {"example.org": "1.2.3.4"}, before_replace=confirm))
        confirm.assert_not_called()


class TestSystemHostsService(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows UAC API")
    def test_uac_cancel_uses_dedicated_code_and_balances_com(self):
        shell, kernel, ole = Mock(), Mock(), Mock()
        shell.ShellExecuteExW.return_value = 0
        with patch.object(system_hosts.ctypes, "WinDLL", side_effect=[shell, kernel]), \
                patch.object(system_hosts.ctypes, "OleDLL", return_value=ole), \
                patch.object(system_hosts.ctypes, "get_last_error", return_value=1223):
            result = system_hosts._launch_elevated_helper(Path("main.py"), 12345, "a" * 64)
        self.assertEqual(result["error_code"], "NETWORK.HOSTS.ELEVATION_CANCELLED")
        info = shell.ShellExecuteExW.call_args.args[0]._obj
        self.assertEqual(info.lpVerb, "runas")
        self.assertIn("--system-hosts-helper", info.lpParameters)
        self.assertNotIn("hosts.json", info.lpParameters)
        ole.CoUninitialize.assert_called_once()

    def test_worker_reports_fine_grained_failures_without_elevation(self):
        for error, code in ((PermissionError("denied"), "PERMISSION_DENIED"),
                            (system_hosts.HostsChangedError("changed"), "CONTENT_CHANGED"),
                            (TimeoutError("busy"), "TIMEOUT")):
            output = io.StringIO()
            with self.subTest(code=code), patch.object(sys, "stdin", io.StringIO('{"example.org": "1.2.3.4"}')), \
                    patch.object(sys, "stdout", output), patch.object(system_hosts, "update_system_hosts", side_effect=error):
                result = system_hosts.run_system_hosts_worker()
            self.assertEqual(result, 1)
            self.assertEqual(json.loads(output.getvalue())["error_code"], f"NETWORK.HOSTS.{code}")

    def test_untrusted_controller_never_reaches_hosts_io(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            errors = []

            def helper():
                try:
                    system_hosts.run_elevated_hosts_helper(server.getsockname()[1], "a" * 64)
                except ValueError as exc:
                    errors.append(exc)

            with patch.object(system_hosts, "update_system_hosts") as update:
                thread = threading.Thread(target=helper)
                thread.start()
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(1)
                    system_hosts._receive_message(connection)
                    system_hosts._send_message(connection, {"proof": "forged"})
                thread.join(2)
                self.assertFalse(thread.is_alive())
                update.assert_not_called()
            self.assertEqual(len(errors), 1)

    def test_only_explicit_permission_failure_can_request_elevation(self):
        service = SystemHostsService(Path("main.py"), Mock())
        for allow, code, expected in ((False, "PERMISSION_DENIED", False), (True, "WRITE_FAILED", False),
                                       (True, "PERMISSION_DENIED", os.name == "nt")):
            result = subprocess.CompletedProcess([], 1, json.dumps({"status": "error", "error_code": f"NETWORK.HOSTS.{code}"}))
            with self.subTest(allow=allow, code=code), patch.object(service, "_execute_elevated", return_value={"status": "success"}) as elevate, \
                    patch.object(system_hosts.subprocess, "run", return_value=result):
                service._execute({"example.org": "1.2.3.4"}, allow_elevation=allow)
                self.assertEqual(elevate.called, expected)

    def test_authorization_failure_is_returned_and_broker_is_reaped(self):
        service = SystemHostsService(Path("main.py"), Mock())
        service._desired = {"example.org": "1.2.3.4"}
        process = Mock()
        process.poll.return_value = 1
        process.communicate.return_value = (json.dumps({"status": "error", "error_code": "NETWORK.HOSTS.ELEVATION_CANCELLED"}).encode(), b"")
        with patch.object(system_hosts.subprocess, "Popen", return_value=process):
            result = service._execute_elevated(service._desired)
        self.assertEqual(result["error_code"], "NETWORK.HOSTS.ELEVATION_CANCELLED")
        self.assertEqual(service.status()["status"], "authorizing")
        process.communicate.assert_called()

    def test_authorization_timeout_closes_port_and_kills_broker(self):
        service = SystemHostsService(Path("main.py"), Mock())
        service._desired = {"example.org": "1.2.3.4"}
        process = Mock()
        process.poll.return_value = None
        with patch.object(system_hosts.subprocess, "Popen", return_value=process) as launch, \
                patch.object(system_hosts, "AUTHORIZATION_TIMEOUT", 0.02):
            result = service._execute_elevated(service._desired)
        self.assertEqual(result["error_code"], "NETWORK.HOSTS.AUTHORIZATION_TIMEOUT")
        process.kill.assert_called_once()
        port = int(launch.call_args.args[0][-2])
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=0.2)

    def test_authorization_channel_commits_only_current_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hosts"
            original = b"127.0.0.1 localhost\n"
            for cancel in (False, True):
                path.write_bytes(original)
                service = SystemHostsService(Path("main.py"), Mock())
                service._desired = {"example.org": "1.2.3.4"}
                helper_errors, helpers = [], []
                process = Mock()
                process.poll.return_value = None

                def launch(cmd, **kwargs):
                    def helper():
                        try:
                            system_hosts.run_elevated_hosts_helper(int(cmd[-2]), cmd[-1])
                        except OSError as exc:
                            helper_errors.append(exc)
                    thread = threading.Thread(target=helper)
                    helpers.append(thread)
                    thread.start()
                    return process

                real_update = update_system_hosts

                def update(target, hosts, *, before_replace):
                    def confirm():
                        if cancel:
                            with service._condition:
                                service._version += 1
                        before_replace()
                    return real_update(target, hosts, before_replace=confirm)

                with self.subTest(cancel=cancel), patch.object(system_hosts.subprocess, "Popen", side_effect=launch), \
                        patch.object(system_hosts, "_system_hosts_path", return_value=path), \
                        patch.object(system_hosts, "update_system_hosts", side_effect=update):
                    result = service._execute_elevated(service._desired)
                    for thread in helpers:
                        thread.join(2)
                        self.assertFalse(thread.is_alive())
                self.assertEqual(result["status"], "error" if cancel else "success")
                self.assertEqual(path.read_bytes() == original, cancel)
                self.assertEqual(helper_errors, [])

    def test_close_cancels_authorization_without_requesting_cleanup_elevation(self):
        service = SystemHostsService(Path("main.py"), Mock())
        authorizing = threading.Event()
        process = Mock()
        process.poll.return_value = None

        def launch(*args, **kwargs):
            authorizing.set()
            return process

        denied = subprocess.CompletedProcess([], 1, json.dumps({"status": "error", "error_code": "NETWORK.HOSTS.PERMISSION_DENIED"}))
        with patch.object(system_hosts.subprocess, "run", return_value=denied), \
                patch.object(system_hosts.subprocess, "Popen", side_effect=launch) as elevate:
            service.submit({"example.org": "1.2.3.4"}, allow_elevation=True)
            self.assertTrue(authorizing.wait(1))
            start = time.monotonic()
            service.close()
            self.assertLess(time.monotonic() - start, 1)
        self.assertFalse(service._thread.is_alive())
        self.assertEqual(elevate.call_count, 1)
        self.assertTrue(service.status()["removing"])

    def test_latest_target_wins_and_close_is_last_write(self):
        started, release, applied = threading.Event(), threading.Event(), threading.Event()
        writes = []

        def execute(hosts, **kwargs):
            writes.append(hosts)
            if len(writes) == 1:
                started.set()
                release.wait(2)
            return {"status": "success", "error_code": ""}

        service = SystemHostsService(Path("main.py"), lambda state: applied.set())
        with patch.object(service, "_execute", side_effect=execute):
            service.submit({"first.org": "1.1.1.1"})
            try:
                self.assertTrue(started.wait(1))
                self.assertEqual(service.status()["status"], "applying")
                service.submit({"obsolete.org": "2.2.2.2"})
                service.submit({"latest.org": "3.3.3.3"})
                release.set()
                self.assertTrue(applied.wait(2))
            finally:
                release.set()
                service.close()
            service.submit({"too-late.org": "4.4.4.4"})
            service.close()
        self.assertEqual(writes, [{"first.org": "1.1.1.1"}, {"latest.org": "3.3.3.3"}, {}])
        self.assertEqual(service.status()["status"], "removed")
        self.assertFalse(service._thread.is_alive())

    def test_worker_timeout_does_not_block_status_or_close(self):
        notified = threading.Event()
        service = SystemHostsService(Path("main.py"), lambda state: notified.set())
        with patch("backend.utils.system_hosts.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 3)):
            try:
                service.submit({"example.org": "1.2.3.4"})
                self.assertTrue(notified.wait(1))
                self.assertEqual(service.status()["error_code"], "NETWORK.HOSTS.TIMEOUT")
            finally:
                service.close()
        self.assertFalse(service._thread.is_alive())

    def test_actual_timeout_kills_and_reaps_child(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "worker.py"
            script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            service = SystemHostsService(script, Mock())
            started = time.perf_counter()
            with patch("backend.utils.system_hosts.WORKER_TIMEOUT", 0.2):
                result = service._execute({})
            self.assertEqual(result["error_code"], "NETWORK.HOSTS.TIMEOUT")
            self.assertLess(time.perf_counter() - started, 3)

    def test_worker_failure_is_reported_and_same_target_can_retry(self):
        notified = threading.Event()
        service = SystemHostsService(Path("main.py"), lambda state: notified.set())
        result = subprocess.CompletedProcess([], 1, json.dumps({"status": "error", "error_code": "NETWORK.HOSTS.PERMISSION_DENIED", "winerror": 5}))
        with patch("backend.utils.system_hosts.subprocess.run", return_value=result):
            try:
                service.submit({"example.org": "1.2.3.4"})
                self.assertTrue(notified.wait(1))
                self.assertEqual(service.status()["winerror"], 5)
                version = service.status()["version"]
                notified.clear()
                service.submit({"example.org": "1.2.3.4"})
                self.assertTrue(notified.wait(1))
                self.assertGreater(service.status()["version"], version)
            finally:
                service.close()

    def test_worker_command_matches_source_pyinstaller_and_nuitka(self):
        service = SystemHostsService(Path("main.py"), Mock())
        result = subprocess.CompletedProcess([], 0, json.dumps({"status": "success"}))
        for frozen, compiled in ((False, False), (True, False), (False, True)):
            with self.subTest(frozen=frozen, compiled=compiled), \
                patch.object(sys, "frozen", frozen, create=True), \
                patch.dict(system_hosts.__dict__, {"__compiled__": object()} if compiled else {}), \
                patch("backend.utils.system_hosts.subprocess.run", return_value=result) as run:
                self.assertEqual(service._execute({})["status"], "success")
                expected = [sys.executable] + ([] if frozen or compiled else ["main.py"]) + ["--system-hosts-worker"]
                self.assertEqual(run.call_args.args[0], expected)

    def test_worker_entry_does_not_load_application(self):
        root = Path(__file__).resolve().parents[1]
        # 无效输入在文件操作前拒绝；此测试绝不触碰真实 Hosts。
        result = subprocess.run([sys.executable, str(root / "main.py"), "--system-hosts-worker"],
                                input="[]", capture_output=True, text=True, timeout=5)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("日志系统", result.stdout + result.stderr)

    def test_application_entry_closes_loaded_network_on_every_exit(self):
        source = Path(__file__).resolve().parents[1] / "main.py"
        # 单独执行真实入口的退出段，避免测试创建窗口或初始化个人配置。
        entry = ast.parse(source.read_text(encoding="utf-8")).body[-1]
        code = compile(ast.Module(body=[entry], type_ignores=[]), str(source), "exec")
        for error in (None, SystemExit(0), RuntimeError("startup failed")):
            manager = Mock()
            namespace = {"__name__": "__main__", "main": Mock(side_effect=error),
                         "sys": SimpleNamespace(modules={"backend.managers.mgr_network": SimpleNamespace(network_mgr=manager)})}
            with self.subTest(error=error):
                if error is None:
                    exec(code, namespace)
                else:
                    with self.assertRaises(type(error)):
                        exec(code, namespace)
                manager.close.assert_called_once_with()

    @unittest.skipUnless(os.name == "nt", "Windows windowless worker")
    def test_worker_recovers_pipes_when_windowless_standard_streams_are_none(self):
        code = "import sys; from backend.utils.system_hosts import run_system_hosts_worker; saved = (sys.stdin, sys.stdout); sys.stdin = sys.stdout = None; raise SystemExit(run_system_hosts_worker())"
        result = subprocess.run([sys.executable, "-c", code], input="[]", capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["error_code"], "NETWORK.HOSTS.INVALID_CONTENT")


if __name__ == "__main__":
    unittest.main()
