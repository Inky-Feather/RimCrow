import shutil
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

    def test_optimize_retries_group_once_after_batch_error(self):
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
                raise TextureOptError("todds 执行失败: batch contains invalid source")
            for source_path in paths:
                Path(source_path).with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_batch", side_effect=fake_encode_batch):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertTrue(good.with_suffix(".dds").exists())
        self.assertTrue(bad.with_suffix(".dds").exists())
        self.assertEqual(result["final_summary"]["current_output_count"], 2)
        self.assertEqual(result["final_summary"]["generate_required_count"], 0)
        self.assertEqual(result["failed_items"], [])
        self.assertTrue(any(len(item) > 1 for item in calls))
        self.assertEqual([sorted(item) for item in calls], [[str(bad), str(good)], [str(bad), str(good)]])

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
