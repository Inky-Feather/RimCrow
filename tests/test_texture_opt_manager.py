import shutil
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.managers.mgr_texture_opt import _ToolProcessRunner, ToddsEncoder, TextureOptimizationManager, TextureTask


class TestTextureOptimizationManager(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        self.mod_root = self.temp_root / "ExampleMod"
        (self.mod_root / "Textures").mkdir(parents=True)
        self.manager = TextureOptimizationManager()
        self.options = {
            "texture_tools_path": str(self.temp_root / "tools"),
            "generate_mipmaps": False,
            "overwrite_existing": False,
            "clean_orphaned_dds": True,
            "skip_small_textures": True,
            "min_dimension": 16,
            "scale_factor": 1.0,
            "max_size": 0,
            "clean_generated_only": True,
        }

    def _write_png(self, relative_path: str, size=(32, 32), alpha=False, fully_transparent=False):
        path = self.mod_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "RGBA" if alpha else "RGB"
        color = (255, 0, 0, 0 if fully_transparent else 128) if alpha else (255, 0, 0)
        Image.new(mode, size, color).save(path)
        return path

    def _write_fake_png(self, relative_path: str, size=(32, 32)):
        path = self.mod_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (255, 0, 0)).save(path, format="JPEG")
        return path

    def _write_header_only_png(self, relative_path: str, size=(32, 32), alpha=True, use_trns=False, color_type=None):
        path = self.mod_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)

        def chunk(name: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + name + data + b"\x00\x00\x00\x00"

        png_color_type = color_type if color_type is not None else (6 if alpha else 2)
        ihdr = struct.pack(">IIBBBBB", size[0], size[1], 8, png_color_type, 0, 0, 0)
        payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
        if use_trns:
            if png_color_type == 3:
                trns = b"\x00"
            elif png_color_type == 0:
                trns = struct.pack(">H", 0)
            else:
                trns = struct.pack(">HHH", 65535, 0, 0)
            payload += chunk(b"tRNS", trns)
        payload += chunk(b"IDAT", b"broken") + chunk(b"IEND", b"")
        path.write_bytes(payload)
        return path

    def test_task_payload_exposes_task_id_alias(self):
        with patch("backend.managers.mgr_texture_opt.threading.Thread.start", return_value=None):
            task = self.manager.start_task([str(self.mod_root)], options=self.options)
        self.assertEqual(task["id"], task["task_id"])

    def test_inspect_png_treats_fully_transparent_rgba_as_alpha(self):
        source = self._write_png("Textures/transparent.png", size=(16, 16), alpha=True, fully_transparent=True)
        info = self.manager._inspect_source_image(source)
        self.assertTrue(info["has_alpha"])

    def test_cleanup_orphaned_outputs_only_deletes_manifest_tracked_files(self):
        source = self._write_png("Textures/source.png")
        tracked_dds = source.with_suffix(".dds")
        tracked_dds.write_bytes(b"dds")
        unmanaged_dds = self.mod_root / "Textures" / "unmanaged.dds"
        unmanaged_dds.write_bytes(b"dds")

        deleted = self.manager._cleanup_orphaned_outputs(
            str(self.mod_root),
            {"Textures/missing.png": {"output_rel_path": "Textures/source.dds"}},
            current_keys=set(),
        )

        self.assertEqual(deleted, 1)
        self.assertFalse(tracked_dds.exists())
        self.assertTrue(unmanaged_dds.exists())

    def test_clean_generated_managed_only_deletes_manifest_outputs(self):
        source = self._write_png("Textures/source.png")
        managed_dds = source.with_suffix(".dds")
        external_zstd = source.with_name("source.dds.zstd")
        managed_dds.write_bytes(b"dds")
        external_zstd.write_bytes(b"zstd")

        self.manager._write_manifest(
            str(self.mod_root),
            {"version": 2, "files": {"Textures/source.png": {"output_rel_path": "Textures/source.dds"}}},
        )
        task = TextureTask(
            id="clean-managed",
            action="clean_generated",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "clean_generated_only": True},
            status="running",
        )

        result = self.manager._clean_generated(task)

        self.assertEqual(result["orphan_deleted"], 1)
        self.assertFalse(managed_dds.exists())
        self.assertTrue(external_zstd.exists())
        self.assertTrue(result["refresh_after_analyze"])

    def test_clean_generated_with_source_deletes_external_outputs_and_refreshes_snapshot(self):
        source = self._write_png("Textures/source.png")
        external_dds = source.with_suffix(".dds")
        external_dds.write_bytes(b"dds")
        cached_snapshot = {
            "id": "stale",
            "schema_version": 2,
            "cache_key": self.manager._build_scan_cache_key([str(self.mod_root)], self.options),
            "signature": self.manager._build_signature(self.options),
            "generated_at": 1,
            "mod_paths": [str(self.mod_root)],
            "summary": self.manager._create_empty_stat(include_mod_count=True, mod_count=1),
            "mods": [],
        }
        self.manager._store_scan_snapshot(cached_snapshot)

        task = TextureTask(
            id="clean-with-source",
            action="clean_generated",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "clean_generated_only": False},
            status="running",
        )

        result = self.manager._clean_generated(task)
        refreshed = self.manager._get_cached_scan_snapshot([str(self.mod_root)], self.options)

        self.assertEqual(result["orphan_deleted"], 1)
        self.assertFalse(external_dds.exists())
        self.assertTrue(result["refresh_after_analyze"])
        self.assertIsNone(refreshed)

    def test_clean_generated_keeps_cached_snapshot_when_no_files_changed(self):
        snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], self.options)
        self.manager._store_scan_snapshot(snapshot)
        task = TextureTask(
            id="clean-no-change",
            action="clean_generated",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "clean_generated_only": True},
            status="running",
        )

        with patch.object(self.manager, "_scan_mods_snapshot", side_effect=AssertionError("should not full rescan")):
            result = self.manager._clean_generated(task)

        refreshed = self.manager._get_cached_scan_snapshot([str(self.mod_root)], self.options)
        self.assertEqual(result["orphan_deleted"], 0)
        self.assertFalse(result["refresh_after_analyze"])
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["summary"]["mod_count"], 1)

    def test_clean_generated_invalidates_only_changed_mod_snapshots(self):
        other_mod_root = self.temp_root / "OtherMod"
        (other_mod_root / "Textures").mkdir(parents=True)
        source_a = self._write_png("Textures/a.png")
        source_b = other_mod_root / "Textures" / "b.png"
        Image.new("RGB", (32, 32), (0, 255, 0)).save(source_b)
        source_a.with_suffix(".dds").write_bytes(b"dds-a")
        source_b.with_suffix(".dds").write_bytes(b"dds-b")

        options = self.manager._build_options(self.options)
        snapshot = self.manager._scan_mods_snapshot([str(self.mod_root), str(other_mod_root)], options)
        self.manager._store_scan_snapshot(snapshot)
        task = TextureTask(
            id="clean-partial-refresh",
            action="clean_generated",
            mod_paths=[str(self.mod_root), str(other_mod_root)],
            options={**self.options, "clean_generated_only": True},
            status="running",
        )
        self.manager._write_manifest(
            str(self.mod_root),
            {"version": 2, "files": {"Textures/a.png": {"output_rel_path": "Textures/a.dds"}}},
        )

        result = self.manager._clean_generated(task)

        self.assertEqual(result["orphan_deleted"], 1)
        self.assertTrue(result["refresh_after_analyze"])
        self.assertIsNone(self.manager._get_cached_scan_snapshot([str(self.mod_root)], options))
        self.assertIsNone(self.manager._get_cached_scan_snapshot([str(self.mod_root), str(other_mod_root)], options))

    def test_invalidate_scan_cache_removes_overlapping_snapshots(self):
        first_options = self.manager._build_options(self.options)
        second_options = self.manager._build_options({**self.options, "scale_factor": 0.5})
        first_snapshot = {
            "id": "snap-1",
            "schema_version": 2,
            "cache_key": self.manager._build_scan_cache_key([str(self.mod_root)], first_options),
            "signature": self.manager._build_signature(first_options),
            "generated_at": 1,
            "mod_paths": [str(self.mod_root)],
            "summary": self.manager._create_empty_stat(include_mod_count=True, mod_count=1),
            "mods": [],
        }
        second_snapshot = {
            "id": "snap-2",
            "schema_version": 2,
            "cache_key": self.manager._build_scan_cache_key([str(self.mod_root)], second_options),
            "signature": self.manager._build_signature(second_options),
            "generated_at": 2,
            "mod_paths": [str(self.mod_root)],
            "summary": self.manager._create_empty_stat(include_mod_count=True, mod_count=1),
            "mods": [],
        }
        self.manager._store_scan_snapshot(first_snapshot)
        self.manager._store_scan_snapshot(second_snapshot)

        removed = self.manager._invalidate_scan_cache([str(self.mod_root)])

        self.assertEqual(removed, 2)
        self.assertIsNone(self.manager._get_cached_scan_snapshot([str(self.mod_root)], first_options))
        self.assertIsNone(self.manager._get_cached_scan_snapshot([str(self.mod_root)], second_options))

    def test_resolve_output_source_returns_png_only(self):
        source = self._write_png("Textures/source.png")
        resolved = self.manager._resolve_output_source(source.with_suffix(".dds"))
        self.assertEqual(resolved, source)

    def test_calc_progress_never_stays_zero_after_work_starts(self):
        self.assertEqual(self.manager._calc_progress(0, 1000), 0)
        self.assertEqual(self.manager._calc_progress(1, 25245), 1)
        self.assertEqual(self.manager._calc_progress(252, 25245), 1)

    def test_build_options_normalizes_clean_generated_only_to_bool(self):
        options_true = self.manager._build_options({**self.options, "clean_generated_only": "true"})
        options_false = self.manager._build_options({**self.options, "clean_generated_only": "false"})

        self.assertIs(options_true["clean_generated_only"], True)
        self.assertIs(options_false["clean_generated_only"], False)

    def test_iter_texture_output_paths_only_returns_dds_outputs(self):
        self._write_png("Textures/source.png")
        (self.mod_root / "Textures" / "a.dds").write_bytes(b"a")
        (self.mod_root / "Textures" / "b.dds.zstd").write_bytes(b"b")
        (self.mod_root / "Textures" / "c.zstd").write_bytes(b"c")

        found = sorted(path.name for path in self.manager._iter_texture_output_paths(str(self.mod_root)))
        self.assertEqual(found, ["a.dds", "b.dds.zstd"])

    def test_scan_snapshot_tracks_external_orphan_dds_separately(self):
        self._write_png("Textures/source.png")
        orphan_dir = self.mod_root / "Textures" / "Loose"
        orphan_dir.mkdir(parents=True, exist_ok=True)
        (orphan_dir / "orphan.dds").write_bytes(b"dds")

        snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], self.options)
        summary = snapshot["summary"]
        row = snapshot["mods"][0]["stat"]

        self.assertEqual(summary["external_orphan_output_count"], 1)
        self.assertEqual(row["external_orphan_output_count"], 1)
        self.assertEqual(summary["output_total_count"], 1)

    def test_scan_summary_tracks_managed_outputs_and_action_required_separately(self):
        source = self._write_png("Textures/source.png")
        output = source.with_suffix(".dds")
        output.write_bytes(b"dds")
        signature = self.manager._build_signature(self.options)
        self.manager._write_manifest(
            str(self.mod_root),
            {
                "version": 2,
                "preset_signature": signature,
                "files": {
                    "Textures/source.png": {
                        "output_rel_path": "Textures/source.dds",
                        "source_size": source.stat().st_size,
                        "source_mtime_ns": source.stat().st_mtime_ns,
                        "output_size": output.stat().st_size,
                        "preset_signature": signature,
                    }
                },
            },
        )

        current_snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], self.options)
        current_row = current_snapshot["mods"][0]["stat"]
        regenerate_snapshot = self.manager._scan_mods_snapshot(
            [str(self.mod_root)],
            {**self.options, "overwrite_existing": True},
        )
        regenerate_row = regenerate_snapshot["mods"][0]["stat"]

        self.assertEqual(current_row["managed_output_count"], 1)
        self.assertEqual(current_row["action_required_count"], 0)
        self.assertEqual(regenerate_row["managed_output_count"], 1)
        self.assertEqual(regenerate_row["action_required_count"], 1)

    def test_scan_marks_fake_png_payload_as_engine_unsupported(self):
        source = self._write_fake_png("Textures/fake.png")

        entry = self.manager._build_scan_entry(
            str(self.mod_root),
            str(source),
            output_stats={},
            options=self.options,
        )

        self.assertTrue(entry["engine_unsupported"])
        self.assertEqual(entry["engine_unsupported_reason"], "文件扩展名为 PNG，但实际内容不是 PNG")
        self.assertFalse(entry["needs_action"])
        self.assertEqual(entry["action_status"], "unsupported")

    def test_scan_uses_png_header_fallback_for_pillow_unreadable_png(self):
        source = self._write_header_only_png("Textures/fallback.png", size=(20, 12), alpha=True)

        entry = self.manager._build_scan_entry(
            str(self.mod_root),
            str(source),
            output_stats={},
            options=self.options,
        )

        self.assertTrue(entry["source_readable"])
        self.assertEqual(entry["width"], 20)
        self.assertEqual(entry["height"], 12)
        self.assertTrue(entry["has_alpha"])
        self.assertFalse(entry["engine_unsupported"])

    def test_scan_png_header_fallback_treats_trns_truecolor_as_alpha(self):
        source = self._write_header_only_png(
            "Textures/trns_truecolor.png",
            size=(18, 10),
            alpha=False,
            use_trns=True,
            color_type=2,
        )

        entry = self.manager._build_scan_entry(
            str(self.mod_root),
            str(source),
            output_stats={},
            options=self.options,
        )

        self.assertTrue(entry["source_readable"])
        self.assertTrue(entry["has_alpha"])

    def test_unreadable_png_header_fallback_still_associates_existing_dds(self):
        source = self._write_header_only_png("Textures/fallback.png", size=(20, 12), alpha=False)
        source.with_suffix(".dds").write_bytes(b"dds")

        snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], self.options)
        row = snapshot["mods"][0]["stat"]

        self.assertEqual(row["source_total_count"], 1)
        self.assertEqual(row["output_total_count"], 1)
        self.assertEqual(row["external_orphan_output_count"], 0)

    def test_build_mod_plan_filters_small_mask_and_fake_png_sources(self):
        keep = self._write_png("Textures/keep.png", size=(64, 64))
        self._write_png("Textures/small.png", size=(8, 8))
        self._write_png("Textures/mask_m.png", size=(64, 64))
        self._write_fake_png("Textures/fake.png", size=(64, 64))
        keep.with_suffix(".dds").write_bytes(b"old")

        snapshot = self.manager._scan_single_mod_snapshot(str(self.mod_root), self.options)
        plan = self.manager._build_mod_plan(snapshot["entries"])

        self.assertEqual(plan["source_count"], 4)
        self.assertEqual(plan["up_to_date_count"], 1)
        self.assertEqual(plan["pending_count"], 0)
        self.assertEqual(plan["skipped_small_count"], 1)
        self.assertEqual(plan["skipped_mask_count"], 1)
        self.assertEqual(plan["unsupported_count"], 1)
        self.assertCountEqual(
            plan["current_keys"],
            ["Textures/keep.png", "Textures/mask_m.png", "Textures/fake.png"],
        )

    def test_optimize_uses_todds_fast_path_and_updates_manifest(self):
        source = self._write_png("Textures/fast.png", size=(32, 32))
        task = TextureTask(
            id="todds-fast",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options=self.options,
            status="running",
        )

        def fake_encode_mod(_cancel_event, overwrite_existing=None, source_paths=None):
            self.assertEqual(source_paths, [str(source)])
            source.with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_mod", side_effect=fake_encode_mod):
            result = self.manager._optimize(task)

        manifest = self.manager._load_manifest(str(self.mod_root))
        self.assertEqual(result["optimized"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertFalse(result["refresh_after_analyze"])
        self.assertTrue(source.with_suffix(".dds").exists())
        self.assertIn("Textures/fast.png", manifest["files"])

    def test_optimize_no_jobs_still_returns_final_snapshot_data(self):
        source = self._write_png("Textures/current.png", size=(32, 32))
        source.with_suffix(".dds").write_bytes(b"dds")
        signature = self.manager._build_signature(self.options)
        self.manager._write_manifest(
            str(self.mod_root),
            {
                "version": 2,
                "preset_signature": signature,
                "files": {
                    "Textures/current.png": {
                        "output_rel_path": "Textures/current.dds",
                        "source_size": source.stat().st_size,
                        "source_mtime_ns": source.stat().st_mtime_ns,
                        "output_size": source.with_suffix(".dds").stat().st_size,
                        "preset_signature": signature,
                    }
                },
            },
        )
        snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], self.options)
        self.manager._store_scan_snapshot(snapshot)

        task = TextureTask(
            id="no-jobs",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "clean_orphaned_dds": False},
            status="running",
        )

        result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 0)
        self.assertIn("final_summary", result)
        self.assertIn("final_mods", result)
        self.assertEqual(result["final_summary"]["mod_count"], 1)
        self.assertEqual(len(result["final_mods"]), 1)

    def test_scale_factor_above_one_updates_target_dimensions(self):
        self.assertEqual(
            self.manager._calculate_target_dimensions(64, 32, {**self.options, "scale_factor": 2.0}),
            (128, 64),
        )

    def test_cached_snapshot_without_current_schema_is_ignored(self):
        self.manager._store_scan_snapshot(
            {
                "id": "legacy",
                "cache_key": self.manager._build_scan_cache_key([str(self.mod_root)], self.options),
                "signature": self.manager._build_signature(self.options),
                "generated_at": 1,
                "mod_paths": [str(self.mod_root)],
                "summary": {"source_total_count": 1},
                "mods": [],
            }
        )

        self.assertIsNone(self.manager._get_cached_scan_snapshot([str(self.mod_root)], self.options))

    def test_read_process_log_returns_tail_segment(self):
        log_path = self.temp_root / "tool.log"
        log_path.write_bytes(b"a" * 4096 + b"TAIL-END")

        tail = _ToolProcessRunner.read_process_log(log_path, limit=16)

        self.assertEqual(tail, "aaaaaaaaTAIL-END")


class TestToddsEncoder(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        (self.temp_root / "Textures").mkdir(parents=True, exist_ok=True)
        self.source = self.temp_root / "Textures" / "a.png"
        Image.new("RGBA", (16, 16), (255, 0, 0, 128)).save(self.source)

    def test_encode_mod_builds_filtered_source_list_command(self):
        encoder = ToddsEncoder(
            {
                "texture_tools_path": str(self.temp_root),
                "overwrite_existing": False,
                "generate_mipmaps": True,
                "scale_factor": 0.5,
                "max_size": 1024,
            }
        )

        def inspect_todds_command(command, _cancel_event, timeout_seconds=None, tool_name="todds"):
            self.assertEqual(command[0], str(self.temp_root / "todds.exe"))
            self.assertIn("-f", command)
            self.assertIn("BC1", command)
            self.assertIn("-af", command)
            self.assertIn("BC7", command)
            self.assertIn("-on", command)
            self.assertIn("-vf", command)
            self.assertNotIn("-fs", command)
            self.assertIn("-sc", command)
            self.assertIn("50", command)
            self.assertIn("-ms", command)
            self.assertIn("1024", command)
            self.assertNotIn("-ss", command)
            self.assertNotIn("-t", command)
            self.assertNotIn("-p", command)
            input_list = Path(command[-1])
            self.assertEqual(input_list.suffix.lower(), ".txt")
            self.assertTrue(input_list.exists())
            self.assertIn(str(self.source), input_list.read_text(encoding="utf-8"))

        with patch.object(ToddsEncoder, "resolve_executable", return_value=self.temp_root / "todds.exe"), \
             patch("backend.managers.mgr_texture_opt._ToolProcessRunner.run_command", side_effect=inspect_todds_command):
            encoder.encode_mod(threading.Event(), source_paths=[str(self.source)])


if __name__ == "__main__":
    unittest.main()
