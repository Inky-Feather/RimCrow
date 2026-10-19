import gzip
import hashlib
import shutil
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from backend.managers.mgr_download import DownloadManager, DownloadTask, TaskStatus


def _make_response(payload=b"data", *, status=200, headers=None):
    response = MagicMock(status_code=status, url="https://files.example/archive.zip")
    response.headers = requests.structures.CaseInsensitiveDict(headers or {})
    response.__enter__.return_value = response
    response.iter_content.side_effect = lambda chunk_size: iter([payload] if payload else [])
    return response


class _DownloadTestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    raw_blob_payload = b""
    compressed_blob_payload = b""
    chunked_payload = b""

    def log_message(self, _format, *_args):
        return

    def do_HEAD(self):
        self._handle_request(send_body=False)

    def do_GET(self):
        self._handle_request(send_body=True)

    def _handle_request(self, *, send_body: bool):
        if self.path == "/compressed.json":
            self._handle_compressed(send_body=send_body)
            return
        if self.path == "/chunked.zip":
            self._handle_chunked(send_body=send_body)
            return
        self.send_error(404)

    def _handle_compressed(self, *, send_body: bool):
        if self.headers.get("Range") == "bytes=0-0":
            total = len(self.raw_blob_payload)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-0/{total}")
            self.send_header("Content-Length", "1")
            self.end_headers()
            if send_body:
                self.wfile.write(self.raw_blob_payload[:1])
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(self.compressed_blob_payload)))
        self.send_header("X-Goog-Stored-Content-Length", str(len(self.raw_blob_payload)))
        self.end_headers()
        if send_body:
            self.wfile.write(self.compressed_blob_payload)

    def _handle_chunked(self, *, send_body: bool):
        if self.headers.get("Range") == "bytes=0-0":
            total = len(self.chunked_payload)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes 0-0/{total}")
            self.send_header("Content-Length", "1")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            if send_body:
                self.wfile.write(self.chunked_payload[:1])
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.end_headers()
        if send_body:
            midpoint = len(self.chunked_payload) // 2
            self.wfile.write(self.chunked_payload[:midpoint])
            self.wfile.write(self.chunked_payload[midpoint:])


class DownloadManagerProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw_payload = b'{"mods":[' + b'{"id":1,"name":"demo"},' * 2048 + b'{"id":2049,"name":"end"}]}'
        chunked_payload = (b"PK\x03\x04" + b"rimmodmanager" * 4096)[:512 * 1024]

        _DownloadTestHandler.raw_blob_payload = raw_payload
        _DownloadTestHandler.compressed_blob_payload = gzip.compress(raw_payload)
        _DownloadTestHandler.chunked_payload = chunked_payload

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _DownloadTestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.manager = DownloadManager()
        self.manager.tasks.clear()

    def _wait_task(self, task_id: str):
        future = self.manager.get_task_future(task_id)
        self.assertIsNotNone(future)
        future.result(timeout=15)
        return self.manager.tasks[task_id]

    def test_download_uses_stored_content_length_for_compressed_response(self):
        task_id = self.manager.add_task(
            f"{self.base_url}/compressed.json",
            str(self.temp_dir),
            filename="steamDB.json",
            network_mode="direct",
        )

        task = self._wait_task(task_id)
        target_path = self.temp_dir / "steamDB.json"

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.total_size, len(_DownloadTestHandler.raw_blob_payload))
        self.assertEqual(task.downloaded_size, len(_DownloadTestHandler.raw_blob_payload))
        self.assertEqual(target_path.read_bytes(), _DownloadTestHandler.raw_blob_payload)

    def test_download_without_content_length_uses_received_size(self):
        task_id = self.manager.add_task(
            f"{self.base_url}/chunked.zip",
            str(self.temp_dir),
            filename="archive.zip",
            network_mode="direct",
        )

        task = self._wait_task(task_id)
        target_path = self.temp_dir / "archive.zip"

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.total_size, len(_DownloadTestHandler.chunked_payload))
        self.assertEqual(task.downloaded_size, len(_DownloadTestHandler.chunked_payload))
        self.assertEqual(target_path.read_bytes(), _DownloadTestHandler.chunked_payload)

    def test_download_falls_back_to_next_url_after_primary_failure(self):
        fallback_url = "https://github.com/team/mod/archive/v1.zip"
        task = self._run_download([
            requests.ConnectionError("mirror unavailable"),
            _make_response(headers={"Content-Length": "4"}),
        ], fallback_urls=[fallback_url])

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual([attempt["url"] for attempt in task.network_attempts], [task.url, fallback_url])
        self.assertEqual((self.temp_dir / "archive.zip").read_bytes(), b"data")
        self.assertNotIn("error_code", task.network_attempts[-1])

    def test_add_task_preserves_business_layer_urls(self):
        with patch.object(self.manager, "_download_worker"):
            task_id = self.manager.add_task(
                "https://github.com/team/mod/blob/main/data.json",
                str(self.temp_dir),
                filename="data.json",
            )

        task = self.manager.tasks[task_id]
        self.assertEqual(task.url, "https://github.com/team/mod/blob/main/data.json")
        self.assertEqual(task.source_urls, ["https://github.com/team/mod/blob/main/data.json"])

    def _run_download(self, responses, **task_options):
        fallback_urls = task_options.pop("fallback_urls", None)
        task = DownloadTask(
            url="https://mirror.example/archive.zip",
            source_urls=["https://mirror.example/archive.zip", *(fallback_urls or [])],
            dest_path=str(self.temp_dir / "archive.zip"), filename="archive.zip", **task_options,
        )
        session = Mock()
        session.get.side_effect = responses
        session._last_route = None
        with patch("backend.managers.mgr_download.build_retry_session", return_value=session), \
            patch.object(self.manager, "_emit_progress"):
            self.manager._download_worker(task)
        session.close.assert_called_once()
        return task

    def test_invalid_download_lengths_and_partial_responses_preserve_old_file(self):
        cases = [
            (200, {"Content-Length": "5"}, b"data"),
            (200, {"Content-Length": "3"}, b"data"),
            (200, {"Content-Length": "0"}, b"data"),
            (206, {"Content-Range": "bytes 1-4/5", "Content-Length": "4"}, b"data"),
            (206, {"Content-Range": "bytes 0-1/4", "Content-Length": "2"}, b"da"),
            (206, {"Content-Range": "bytes 0-3/4", "Content-Length": "5"}, b"data"),
            (206, {}, b"data"),
            (206, {"Content-Range": "bytes 0-3/4", "Content-Encoding": "gzip"}, b"data"),
        ]
        target = self.temp_dir / "archive.zip"
        for status, headers, payload in cases:
            with self.subTest(status=status, headers=headers):
                target.write_bytes(b"original")
                callback = Mock()
                task = self._run_download([_make_response(payload, status=status, headers=headers)], on_complete=callback)
                self.assertEqual(task.status, TaskStatus.ERROR)
                self.assertEqual(task.error_code, "NETWORK.INVALID_RESPONSE")
                self.assertEqual(target.read_bytes(), b"original")
                self.assertEqual(list(self.temp_dir.glob("*.downloading")), [])
                callback.assert_not_called()

    def test_complete_range_response_and_empty_file_are_accepted(self):
        for status, headers, payload in [
            (206, {"Content-Range": "bytes 0-3/4", "Content-Length": "4"}, b"data"),
            (200, {"Content-Length": "0"}, b""),
        ]:
            with self.subTest(status=status):
                task = self._run_download([_make_response(payload, status=status, headers=headers)])
                self.assertEqual(task.status, TaskStatus.COMPLETED)
                self.assertEqual(task.downloaded_size, len(payload))
                self.assertEqual(Path(task.dest_path).read_bytes(), payload)

    def test_truncated_file_retries_fallback_without_padding_progress(self):
        task = self._run_download([
            _make_response(b"bad", headers={"Content-Length": "4"}),
            _make_response(headers={"Content-Length": "4"}),
        ], fallback_urls=["https://files.example/archive.zip"])
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.downloaded_size, 4)
        self.assertEqual(Path(task.dest_path).read_bytes(), b"data")
        self.assertEqual(task.network_attempts[0]["error_code"], "NETWORK.INVALID_RESPONSE")

    def test_hash_failure_never_installs_and_can_retry_fallback(self):
        target = self.temp_dir / "archive.zip"
        target.write_bytes(b"original")
        expected_hash = hashlib.sha256(b"data").hexdigest()
        callback = Mock()
        task = self._run_download([_make_response(b"bad!", headers={"Content-Length": "4"})],
            expected_hash=expected_hash, hash_algorithm="sha256", on_complete=callback)
        self.assertEqual(task.status, TaskStatus.ERROR)
        self.assertEqual(task.error_code, "NETWORK.INVALID_RESPONSE")
        self.assertEqual(target.read_bytes(), b"original")
        callback.assert_not_called()
        task = self._run_download([
            _make_response(b"bad!", headers={"Content-Length": "4"}),
            _make_response(headers={"Content-Length": "4"}),
        ], expected_hash=expected_hash, hash_algorithm="sha256",
            fallback_urls=["https://files.example/archive.zip"])
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(target.read_bytes(), b"data")

    def test_hash_verification_observes_cancellation(self):
        target = self.temp_dir / "large.bin"
        target.write_bytes(b"x" * (8192 * 3))
        checks = 0

        def cancel_check():
            nonlocal checks
            checks += 1
            if checks == 2:
                raise InterruptedError("cancelled")

        with self.assertRaises(InterruptedError):
            self.manager._verify_hash(
                str(target), hashlib.sha256(b"x" * (8192 * 3)).hexdigest(),
                "sha256", cancel_check=cancel_check,
            )
        self.assertGreaterEqual(checks, 2)

    def test_business_validation_failure_retries_fallback_before_replacing_file(self):
        seen = []

        def validate(path):
            payload = Path(path).read_bytes()
            seen.append(payload)
            return payload == b"valid archive"

        task = self._run_download([
            _make_response(b"<!doctype html>", headers={"Content-Length": "15"}),
            _make_response(b"valid archive", headers={"Content-Length": "13"}),
        ], fallback_urls=["https://files.example/archive.zip"], validate_download=validate)

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(seen, [b"<!doctype html>", b"valid archive"])
        self.assertEqual(Path(task.dest_path).read_bytes(), b"valid archive")

    def test_failed_replace_keeps_original_file_and_skips_installation(self):
        target = self.temp_dir / "archive.zip"
        target.write_bytes(b"original")
        callback = Mock()
        with patch("backend.managers.mgr_download.os.replace", side_effect=PermissionError("file in use")):
            task = self._run_download([_make_response(headers={"Content-Length": "4"})], on_complete=callback)
        self.assertEqual(task.status, TaskStatus.ERROR)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(list(self.temp_dir.glob("*.downloading")), [])
        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
