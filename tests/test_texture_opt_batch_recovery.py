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

    def test_optimize_recovers_single_file_failure_after_batch_error(self):
        good = self._write_png("Textures/good.png")
        bad = self._write_png("Textures/bad.png")
        task = self._make_task()
        calls: list[list[str]] = []

        def fake_encode_batch(_cancel_event, *, source_paths, overwrite_existing, scale_percent, output_callback=None):
            paths = list(source_paths or [])
            calls.append(paths)
            if len(paths) > 1:
                raise TextureOptError("todds 执行失败: batch contains invalid source")
            target = Path(paths[0])
            if target == bad:
                raise TextureOptError("todds 执行失败: invalid png payload")
            target.with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_batch", side_effect=fake_encode_batch):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertTrue(good.with_suffix(".dds").exists())
        self.assertFalse(bad.with_suffix(".dds").exists())
        self.assertEqual(result["final_summary"]["current_output_count"], 1)
        self.assertEqual(result["final_summary"]["generate_required_count"], 1)
        self.assertEqual(result["failed_items"][0]["rel_path"], "Textures/bad.png")
        self.assertTrue(any(len(item) > 1 for item in calls))
        self.assertIn([str(good)], calls)
        self.assertIn([str(bad)], calls)

    def test_run_task_keeps_partial_failure_as_success(self):
        good = self._write_png("Textures/good.png")
        bad = self._write_png("Textures/bad.png")
        task = self._make_task()

        def fake_encode_batch(_cancel_event, *, source_paths, overwrite_existing, scale_percent, output_callback=None):
            paths = list(source_paths or [])
            if len(paths) > 1:
                raise TextureOptError("todds 执行失败: batch contains invalid source")
            target = Path(paths[0])
            if target == bad:
                raise TextureOptError("todds 执行失败: invalid png payload")
            target.with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_batch", side_effect=fake_encode_batch):
            self.manager._run_task(task)

        self.assertEqual(task.status, "success")
        self.assertEqual(task.metrics["optimized"], 1)
        self.assertEqual(task.metrics["failed"], 1)
        self.assertEqual(task.metrics["failed_items"][0]["rel_path"], "Textures/bad.png")
        self.assertIn("失败 1 张", task.message)
        self.assertTrue(good.with_suffix(".dds").exists())

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
