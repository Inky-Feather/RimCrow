import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.managers.mgr_texture_opt import TextureOptError, TextureOptimizationManager, TextureTask, ToddsEncoder


class TestTextureOptBatchRecovery(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        self.mod_root = self.temp_root / "ExampleMod"
        (self.mod_root / "Textures").mkdir(parents=True, exist_ok=True)
        self.manager = TextureOptimizationManager()
        self.options = {
            "texture_tools_path": str(self.temp_root / "tools"),
            "process_mode": "all_overwrite",
            "output_format": "dds",
            "generate_mipmaps": True,
            "overwrite_existing": True,
            "skip_small_textures": False,
            "min_dimension": 1,
            "max_source_dimension": 4096,
            "scale_factor": 1.0,
            "max_size": 128,
        }

    def _write_png(self, relative_path: str, size=(128, 128)) -> Path:
        path = self.mod_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", size, (255, 0, 0, 128)).save(path)
        return path

    def _make_task(self) -> TextureTask:
        return TextureTask(
            id="recover-batch",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options=dict(self.options),
            status="running",
        )

    def test_optimize_keeps_written_outputs_after_batch_error_and_retries_only_missing_items(self):
        good = self._write_png("Textures/good.png")
        bad = self._write_png("Textures/bad.png")
        task = self._make_task()
        calls: list[list[str]] = []
        first_batch = True

        def fake_encode_batch(_cancel_event, *, source_paths, overwrite_existing, scale_percent, max_size=None, output_callback=None):
            nonlocal first_batch
            paths = list(source_paths or [])
            calls.append(paths)
            if first_batch:
                first_batch = False
                good.with_suffix(".dds").write_bytes(b"good-dds")
                raise TextureOptError("todds 执行失败: batch contains invalid source")
            for source_path in paths:
                Path(source_path).with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_batch", side_effect=fake_encode_batch):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(sorted(calls[0]), [str(bad), str(good)])
        self.assertEqual(calls[1], [str(bad)])
        self.assertEqual(good.with_suffix(".dds").read_bytes(), b"good-dds")
        self.assertTrue(bad.with_suffix(".dds").exists())

    def test_optimize_records_missing_output_after_successful_todds_return(self):
        good = self._write_png("Textures/good.png")
        bad = self._write_png("Textures/bad.png")
        task = self._make_task()
        calls: list[list[str]] = []

        def fake_encode_batch(_cancel_event, *, source_paths, overwrite_existing, scale_percent, max_size=None, output_callback=None):
            paths = list(source_paths or [])
            calls.append(paths)
            for source_path in paths:
                if Path(source_path) == good:
                    Path(source_path).with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_batch", side_effect=fake_encode_batch):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["final_status"], "failed")
        self.assertEqual(sorted(calls[0]), [str(bad), str(good)])
        self.assertEqual(calls[1], [str(bad)])
        self.assertTrue(good.with_suffix(".dds").exists())
        self.assertFalse(bad.with_suffix(".dds").exists())
        self.assertEqual(result["failed_items"][0]["rel_path"], "Textures/bad.png")
        self.assertIn("生成结果未写出", result["failed_items"][0]["error"])

    def test_run_task_marks_group_retry_success_as_success(self):
        good = self._write_png("Textures/good.png")
        bad = self._write_png("Textures/bad.png")
        task = self._make_task()
        first_batch = True

        def fake_encode_batch(_cancel_event, *, source_paths, overwrite_existing, scale_percent, max_size=None, output_callback=None):
            nonlocal first_batch
            paths = list(source_paths or [])
            if first_batch:
                first_batch = False
                raise TextureOptError("todds 执行失败: batch contains invalid source")
            for source_path in paths:
                Path(source_path).with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_batch", side_effect=fake_encode_batch):
            self.manager._run_task(task)

        self.assertEqual(task.status, "success")
        self.assertEqual(task.metrics["optimized"], 2)
        self.assertEqual(task.metrics["failed"], 0)
        self.assertNotIn("failed_items", task.metrics)
        self.assertNotIn("失败", task.message)
        self.assertTrue(good.with_suffix(".dds").exists())
        self.assertTrue(bad.with_suffix(".dds").exists())

    def test_run_task_keeps_success_when_result_file_write_fails(self):
        source = self._write_png("Textures/result-write.png")
        task = self._make_task()

        def fake_encode_batch(_cancel_event, *, source_paths, overwrite_existing, scale_percent, max_size=None, output_callback=None):
            for source_path in source_paths or []:
                Path(source_path).with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_batch", side_effect=fake_encode_batch), \
             patch.object(self.manager, "_write_task_result_file", side_effect=OSError("disk full")):
            self.manager._run_task(task)

        self.assertEqual(task.status, "success")
        self.assertEqual(task.metrics["optimized"], 1)
        self.assertEqual(task.metrics["failed"], 0)
        self.assertNotIn("result_path", task.metrics)
        self.assertTrue(task.metrics["result_write_failed"])
        self.assertIn("结果记录写入失败", task.message)
        self.assertTrue(source.with_suffix(".dds").exists())

    def test_verify_generated_entries_accepts_existing_nonempty_output(self):
        source = self._write_png("Textures/existing.png")
        output = source.with_suffix(".dds")
        output.write_bytes(b"same-size")
        output_stat = output.stat()
        entry = {
            "output_path": str(output),
            "output_exists": True,
            "output_size": output_stat.st_size,
            "output_mtime_ns": output_stat.st_mtime_ns,
        }

        successful, failed = self.manager._verify_generated_entries([entry])

        self.assertEqual(successful, [entry])
        self.assertEqual(failed, [])

    def test_optimize_keeps_nonrecoverable_errors_fatal(self):
        self._write_png("Textures/good.png")
        task = self._make_task()

        with patch.object(ToddsEncoder, "encode_batch", side_effect=TextureOptError("未找到 todds.exe。请在贴图优化中心下载 todds。")):
            with self.assertRaises(TextureOptError):
                self.manager._optimize(task)

    def test_run_task_marks_all_failed_retries_as_failed(self):
        self._write_png("Textures/bad.png")
        task = self._make_task()

        with patch.object(ToddsEncoder, "encode_batch", side_effect=TextureOptError("todds 执行失败: invalid png payload")):
            self.manager._run_task(task)

        self.assertEqual(task.status, "failed")
        self.assertEqual(task.metrics["optimized"], 0)
        self.assertEqual(task.metrics["failed"], 1)


if __name__ == "__main__":
    unittest.main()
