import gzip
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from backend.managers.mgr_download import DownloadManager, TaskStatus


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
        )

        task = self._wait_task(task_id)
        target_path = self.temp_dir / "steamDB.json"

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.total_size, len(_DownloadTestHandler.raw_blob_payload))
        self.assertEqual(task.downloaded_size, len(_DownloadTestHandler.raw_blob_payload))
        self.assertEqual(target_path.read_bytes(), _DownloadTestHandler.raw_blob_payload)

    def test_download_probes_total_size_when_stream_response_has_no_length(self):
        task_id = self.manager.add_task(
            f"{self.base_url}/chunked.zip",
            str(self.temp_dir),
            filename="archive.zip",
        )

        task = self._wait_task(task_id)
        target_path = self.temp_dir / "archive.zip"

        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.total_size, len(_DownloadTestHandler.chunked_payload))
        self.assertEqual(task.downloaded_size, len(_DownloadTestHandler.chunked_payload))
        self.assertEqual(target_path.read_bytes(), _DownloadTestHandler.chunked_payload)


if __name__ == "__main__":
    unittest.main()
