import os
import shutil
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PIL import Image

import backend.managers.mgr_texture_opt as texture_opt_module
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
            "process_mode": "scaled_only_overwrite",
            "generate_mipmaps": True,
            "overwrite_existing": True,
            "clean_orphaned_dds": False,
            "skip_small_textures": True,
            "min_dimension": 128,
            "max_source_dimension": 2048,
            "scale_factor": 0.5,
            "max_size": 128,
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
        source = self._write_png("Textures/transparent.png", size=(128, 128), alpha=True, fully_transparent=True)
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
        managed_dds.write_bytes(b"dds")

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
        self.assertFalse(result["refresh_after_analyze"])

    def test_clean_generated_with_source_deletes_external_outputs_and_invalidates_snapshot(self):
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
        self.assertFalse(result["refresh_after_analyze"])
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
        self.assertFalse(result["refresh_after_analyze"])
        self.assertIsNone(self.manager._get_cached_scan_snapshot([str(self.mod_root)], options))
        self.assertIsNone(self.manager._get_cached_scan_snapshot([str(self.mod_root), str(other_mod_root)], options))

    def test_invalidate_scan_cache_removes_overlapping_snapshots(self):
        first_options = self.manager._build_options(self.options)
        second_options = self.manager._build_options({**self.options, "scale_factor": 0.25})
        first_snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], first_options)
        second_snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], second_options)
        self.manager._store_scan_snapshot(first_snapshot)
        self.manager._store_scan_snapshot(second_snapshot)

        removed = self.manager._invalidate_scan_cache([str(self.mod_root)])

        self.assertEqual(removed, 1)
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

    def test_build_options_derives_process_mode_flags(self):
        skip_existing = self.manager._build_options({**self.options, "process_mode": "all_skip_existing"})
        all_overwrite = self.manager._build_options({**self.options, "process_mode": "all_overwrite"})

        self.assertEqual(skip_existing["process_mode"], "all_skip_existing")
        self.assertEqual(all_overwrite["process_mode"], "all_overwrite")

    def test_build_encode_batches_splits_large_groups(self):
        total = texture_opt_module.TEXTURE_ENCODE_BATCH_SIZE + 1
        entries = [
            {
                "needs_action": True,
                "output_exists": False,
                "scale_percent": 50,
                "source_path": f"source-{index}.png",
            }
            for index in range(total)
        ]

        batches = self.manager._build_encode_batches(entries)

        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]["entries"]), texture_opt_module.TEXTURE_ENCODE_BATCH_SIZE)
        self.assertEqual(len(batches[1]["entries"]), 1)
        self.assertEqual(len(batches[0]["source_paths"]), texture_opt_module.TEXTURE_ENCODE_BATCH_SIZE)
        self.assertEqual(len(batches[1]["source_paths"]), 1)

    def test_iter_texture_output_paths_only_returns_dds_outputs(self):
        self._write_png("Textures/source.png")
        (self.mod_root / "Textures" / "a.dds").write_bytes(b"a")

        found = sorted(path.name for path in self.manager._iter_texture_output_paths(str(self.mod_root)))
        self.assertEqual(found, ["a.dds"])

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
        source = self._write_png("Textures/source.png", size=(128, 128))
        output = source.with_suffix(".dds")
        output.write_bytes(b"dds")
        source_stat = source.stat()
        os.utime(output, ns=(source_stat.st_mtime_ns + 1_000_000, source_stat.st_mtime_ns + 1_000_000))
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
            {**self.options, "process_mode": "all_overwrite"},
        )
        regenerate_row = regenerate_snapshot["mods"][0]["stat"]

        self.assertEqual(current_row["managed_output_count"], 1)
        self.assertEqual(current_row["action_required_count"], 0)
        self.assertEqual(regenerate_row["managed_output_count"], 1)
        self.assertEqual(regenerate_row["action_required_count"], 1)

    def test_scan_marks_fake_png_payload_as_engine_unsupported(self):
        source = self._write_fake_png("Textures/fake.png", size=(128, 128))

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

    def test_inspect_source_image_prefers_png_header_fast_path_when_precise_alpha_disabled(self):
        source = self._write_png("Textures/fast_header.png", size=(24, 12), alpha=True)

        with patch("backend.managers.mgr_texture_opt.Image.open", side_effect=AssertionError("should not open via Pillow")):
            info = self.manager._inspect_source_image(source, precise_alpha=False)

        self.assertEqual(info["width"], 24)
        self.assertEqual(info["height"], 12)
        self.assertTrue(info["has_alpha"])

    def test_unreadable_png_header_fallback_still_associates_existing_dds(self):
        source = self._write_header_only_png("Textures/fallback.png", size=(20, 12), alpha=False)
        source.with_suffix(".dds").write_bytes(b"dds")

        snapshot = self.manager._scan_mods_snapshot([str(self.mod_root)], self.options)
        row = snapshot["mods"][0]["stat"]

        self.assertEqual(row["source_total_count"], 1)
        self.assertEqual(row["output_total_count"], 1)
        self.assertEqual(row["external_orphan_output_count"], 0)

    def test_build_mod_plan_filters_small_mask_and_fake_png_sources(self):
        keep = self._write_png("Textures/keep.png", size=(128, 128))
        self._write_png("Textures/small.png", size=(8, 8))
        self._write_png("Textures/mask_m.png", size=(128, 128))
        self._write_fake_png("Textures/fake.png", size=(128, 128))
        keep_dds = keep.with_suffix(".dds")
        keep_dds.write_bytes(b"old")
        source_stat = keep.stat()
        os.utime(keep_dds, ns=(source_stat.st_mtime_ns + 1_000_000, source_stat.st_mtime_ns + 1_000_000))

        snapshot = self.manager._scan_single_mod_snapshot(
            str(self.mod_root),
            {**self.options, "min_dimension": 16, "scale_factor": 1.0, "max_size": 128},
        )
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
        source = self._write_png("Textures/fast.png", size=(128, 128))
        task = TextureTask(
            id="todds-fast",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "process_mode": "all_overwrite", "scale_factor": 1.0},
            status="running",
        )

        def fake_encode_mod(
            _cancel_event,
            overwrite_existing=None,
            source_paths=None,
            scale_percent=None,
            max_size=None,
            use_fix_size=None,
            output_callback=None,
        ):
            self.assertEqual(source_paths, [str(source)])
            self.assertIsNone(scale_percent)
            self.assertEqual(max_size, 0)
            self.assertTrue(use_fix_size)
            source.with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_mod", side_effect=fake_encode_mod):
            result = self.manager._optimize(task)

        manifest = self.manager._load_manifest(str(self.mod_root))
        self.assertEqual(result["optimized"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertFalse(result["refresh_after_analyze"])
        self.assertEqual(result["final_summary"]["managed_output_count"], 1)
        self.assertEqual(result["final_summary"]["external_output_count"], 0)
        self.assertEqual(result["final_mods"][0]["managed_output_count"], 1)
        self.assertTrue(source.with_suffix(".dds").exists())
        self.assertIn("Textures/fast.png", manifest["files"])

    def test_optimize_only_scans_each_mod_once(self):
        source = self._write_png("Textures/once.png", size=(128, 128))
        task = TextureTask(
            id="scan-once",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "process_mode": "all_overwrite", "scale_factor": 1.0},
            status="running",
        )
        original_build = self.manager._build_mod_base_index

        def fake_encode_mod(
            _cancel_event,
            overwrite_existing=None,
            source_paths=None,
            scale_percent=None,
            max_size=None,
            use_fix_size=None,
            output_callback=None,
        ):
            self.assertEqual(source_paths, [str(source)])
            source.with_suffix(".dds").write_bytes(b"dds")

        with patch.object(self.manager, "_build_mod_base_index", wraps=original_build) as build_mock, \
             patch.object(ToddsEncoder, "encode_mod", side_effect=fake_encode_mod):
            result = self.manager._optimize(task)

        self.assertEqual(build_mock.call_count, 1)
        self.assertEqual(result["optimized"], 1)
        self.assertEqual(result["failed"], 0)

    def test_optimize_prepare_uses_threaded_plan_builder(self):
        other_mod_root = self.temp_root / "OtherMod"
        (other_mod_root / "Textures").mkdir(parents=True)
        task = TextureTask(
            id="threaded-plan",
            action="optimize",
            mod_paths=[str(self.mod_root), str(other_mod_root)],
            options={**self.options, "process_mode": "all_overwrite"},
            status="running",
        )
        seen_threads: list[str] = []
        lock = threading.Lock()

        def fake_scan_single_target(target, _options, **_kwargs):
            mod_path = str(target.get("mod_path") or "")
            with lock:
                seen_threads.append(threading.current_thread().name)
            return {
                "mod_path": mod_path,
                "mod_name": Path(mod_path).name,
                "entries": [],
                "stat": self.manager._create_empty_stat(mod_path=mod_path, mod_name=Path(mod_path).name),
            }

        with patch.object(self.manager, "_resolve_scan_workers", return_value=2), \
             patch.object(self.manager, "_scan_single_target", side_effect=fake_scan_single_target):
            results = self.manager._scan_targets_for_optimize(task, task.options)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(name.startswith("TexturePlan") for name in seen_threads))

    def test_optimize_reuses_recent_analysis_cache_without_revalidating_signature(self):
        source = self._write_png("Textures/reuse.png", size=(128, 128))
        source.with_suffix(".dds").write_bytes(b"dds")
        options = {**self.options, "process_mode": "all_skip_existing"}
        self.manager._scan_mods([str(self.mod_root)], options, None)
        task = TextureTask(
            id="reuse-analysis-cache",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options=options,
            status="running",
        )

        with patch.object(self.manager, "_scan_single_target", side_effect=AssertionError("should use analysis plan cache")):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 0)
        self.assertEqual(result["failed"], 0)

    def test_optimize_rebuilds_base_scan_after_cache_ttl_expires(self):
        source = self._write_png("Textures/expired.png", size=(128, 128))
        source.with_suffix(".dds").write_bytes(b"dds")
        options = {**self.options, "process_mode": "all_skip_existing"}
        self.manager._scan_mods([str(self.mod_root)], options, None)
        cache_key = texture_opt_module.generate_path_hash(str(self.mod_root))
        self.manager._base_scan_cache[cache_key]["generated_at"] = (
            texture_opt_module.current_ms() - texture_opt_module.TEXTURE_BASE_SCAN_CACHE_TTL_MS - 1
        )
        for cached_plan in self.manager._projected_plan_cache.values():
            cached_plan["generated_at"] = (
                texture_opt_module.current_ms() - texture_opt_module.TEXTURE_BASE_SCAN_CACHE_TTL_MS - 1
            )
        task = TextureTask(
            id="expired-analysis-cache",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options=options,
            status="running",
        )

        with patch.object(self.manager, "_build_mod_base_index", wraps=self.manager._build_mod_base_index) as build_mock:
            result = self.manager._optimize(task)

        self.assertEqual(build_mock.call_count, 1)
        self.assertEqual(result["optimized"], 0)
        self.assertEqual(result["failed"], 0)

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

    def test_optimize_keeps_external_current_dds_unmanaged_when_not_overwriting(self):
        source = self._write_png("Textures/external.png", size=(128, 128))
        external_dds = source.with_suffix(".dds")
        external_dds.write_bytes(b"external-dds")
        task = TextureTask(
            id="external-current",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "process_mode": "all_skip_existing"},
            status="running",
        )

        with patch.object(ToddsEncoder, "encode_mod", side_effect=AssertionError("should not re-encode external current DDS")):
            result = self.manager._optimize(task)

        manifest = self.manager._load_manifest(str(self.mod_root))
        clean_task = TextureTask(
            id="external-current-clean",
            action="clean_generated",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "clean_generated_only": True},
            status="running",
        )
        clean_result = self.manager._clean_generated(clean_task)

        self.assertEqual(result["optimized"], 0)
        self.assertEqual(result["failed"], 0)
        self.assertNotIn("Textures/external.png", manifest["files"])
        self.assertTrue(external_dds.exists())
        self.assertEqual(clean_result["orphan_deleted"], 0)
        self.assertTrue(external_dds.exists())

    def test_optimize_force_overwrites_only_managed_signature_mismatch(self):
        source = self._write_png("Textures/managed.png", size=(128, 128))
        output = source.with_suffix(".dds")
        output.write_bytes(b"old")
        source_stat = source.stat()
        os.utime(output, ns=(source_stat.st_mtime_ns + 1_000_000, source_stat.st_mtime_ns + 1_000_000))
        old_signature = self.manager._build_signature({**self.options, "scale_factor": 0.5})
        self.manager._write_manifest(
            str(self.mod_root),
            {
                "version": 2,
                "preset_signature": old_signature,
                "files": {
                    "Textures/managed.png": {
                        "output_rel_path": "Textures/managed.dds",
                        "source_size": source.stat().st_size,
                        "source_mtime_ns": source.stat().st_mtime_ns,
                        "output_size": output.stat().st_size,
                        "preset_signature": old_signature,
                    }
                },
            },
        )
        task = TextureTask(
            id="managed-mismatch",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "process_mode": "all_overwrite", "scale_factor": 1.0},
            status="running",
        )
        calls = []

        def fake_encode_mod(
            _cancel_event,
            overwrite_existing=None,
            source_paths=None,
            scale_percent=None,
            max_size=None,
            use_fix_size=None,
            output_callback=None,
        ):
            calls.append((overwrite_existing, list(source_paths or [])))
            self.assertIsNone(scale_percent)
            self.assertEqual(max_size, 0)
            self.assertTrue(use_fix_size)
            output.write_bytes(b"new")

        with patch.object(ToddsEncoder, "encode_mod", side_effect=fake_encode_mod):
            result = self.manager._optimize(task)

        self.assertEqual(calls, [(True, [str(source)])])
        self.assertEqual(result["optimized"], 1)
        self.assertEqual(result["failed"], 0)

    def test_all_skip_existing_process_mode_keeps_existing_outputs(self):
        source = self._write_png("Textures/existing.png", size=(256, 256))
        output = source.with_suffix(".dds")
        output.write_bytes(b"old")
        task = TextureTask(
            id="skip-existing",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "process_mode": "all_skip_existing"},
            status="running",
        )

        with patch.object(ToddsEncoder, "encode_batch", side_effect=AssertionError("should skip existing dds")):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 0)

    def test_scale_strategy_falls_back_to_original_size_for_incompatible_dimensions(self):
        behavior = self.manager._resolve_encode_behavior(
            136,
            136,
            {**self.options, "scale_factor": 0.5, "max_size": 128},
        )

        self.assertEqual(behavior["mode"], "keep_original")
        self.assertTrue(behavior["use_fix_size"])
        self.assertIsNone(behavior["scale_percent"])
        self.assertEqual(
            self.manager._calculate_target_dimensions(136, 136, {**self.options, "scale_factor": 0.5, "max_size": 128}),
            (136, 136),
        )

    def test_scale_strategy_uses_larger_scale_when_needed(self):
        behavior = self.manager._resolve_encode_behavior(
            512,
            512,
            {**self.options, "scale_factor": 0.2, "max_size": 128},
        )

        self.assertEqual(behavior["mode"], "scale")
        self.assertEqual(behavior["scale_percent"], 25)
        self.assertEqual(
            self.manager._calculate_target_dimensions(512, 512, {**self.options, "scale_factor": 0.2, "max_size": 128}),
            (128, 128),
        )

    def test_optimize_scale_strategy_splits_scaled_and_original_size_batches(self):
        scaled_source = self._write_png("Textures/scaled.png", size=(256, 256))
        fallback_source = self._write_png("Textures/fallback.png", size=(136, 136))
        task = TextureTask(
            id="step-batches",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "process_mode": "all_overwrite", "scale_factor": 0.5, "max_size": 128},
            status="running",
        )
        calls = []

        def fake_encode_mod(
            _cancel_event,
            overwrite_existing=None,
            source_paths=None,
            scale_percent=None,
            max_size=None,
            use_fix_size=None,
            output_callback=None,
        ):
            calls.append(
                {
                    "overwrite_existing": overwrite_existing,
                    "source_paths": list(source_paths or []),
                    "scale_percent": scale_percent,
                    "max_size": max_size,
                    "use_fix_size": use_fix_size,
                }
            )
            for source_path in source_paths or []:
                Path(source_path).with_suffix(".dds").write_bytes(b"dds")

        with patch.object(ToddsEncoder, "encode_mod", side_effect=fake_encode_mod):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertIn("按当前档位缩放 1 张", result["message"])
        self.assertIn("保持原尺寸 1 张", result["message"])
        self.assertEqual(
            calls,
            [
                {
                    "overwrite_existing": True,
                    "source_paths": [str(scaled_source)],
                    "scale_percent": 50,
                    "max_size": 0,
                    "use_fix_size": False,
                },
                {
                    "overwrite_existing": True,
                    "source_paths": [str(fallback_source)],
                    "scale_percent": None,
                    "max_size": 0,
                    "use_fix_size": True,
                },
            ],
        )

    def test_optimize_streams_todds_progress_with_callback(self):
        source = self._write_png("Textures/progress.png", size=(128, 128))
        task = TextureTask(
            id="stream-progress",
            action="optimize",
            mod_paths=[str(self.mod_root)],
            options={**self.options, "process_mode": "all_overwrite", "scale_factor": 1.0},
            status="running",
        )
        emitted: list[dict[str, Any]] = []

        def fake_encode_mod(
            _cancel_event,
            overwrite_existing=None,
            source_paths=None,
            scale_percent=None,
            max_size=None,
            use_fix_size=None,
            output_callback=None,
        ):
            self.assertTrue(callable(output_callback))
            output_callback("Progress: 1 / 1")
            for source_path in source_paths or []:
                Path(source_path).with_suffix(".dds").write_bytes(b"dds")

        def capture_progress(_task_id, _task_type, **payload):
            emitted.append(payload)

        with patch.object(ToddsEncoder, "encode_mod", side_effect=fake_encode_mod), \
             patch("backend.managers.mgr_texture_opt.EventBus.emit_progress", side_effect=capture_progress):
            result = self.manager._optimize(task)

        self.assertEqual(result["optimized"], 1)
        self.assertTrue(source.with_suffix(".dds").exists())
        self.assertTrue(any(item.get("metrics", {}).get("current_batch_done") == 1 for item in emitted))

    def test_scan_summary_reports_scale_breakdown(self):
        self._write_png("Textures/scaled.png", size=(256, 256))
        self._write_png("Textures/fallback.png", size=(136, 136))

        snapshot = self.manager._scan_mods_snapshot(
            [str(self.mod_root)],
            {**self.options, "scale_factor": 0.5, "max_size": 128},
        )
        summary = snapshot["summary"]
        row = snapshot["mods"][0]["stat"]

        self.assertEqual(summary["scaled_count"], 1)
        self.assertEqual(summary["keep_original_count"], 1)
        self.assertEqual(row["scaled_count"], 1)
        self.assertEqual(row["keep_original_count"], 1)
        self.assertEqual(
            row["scale_breakdown"],
            [
                {"kind": "scaled", "label": "50%", "count": 1},
                {"kind": "keep_original", "label": "原尺寸", "count": 1},
            ],
        )

    def test_scaled_only_process_mode_skips_keep_original_jobs(self):
        scaled = self._write_png("Textures/scaled.png", size=(256, 256))
        fallback = self._write_png("Textures/fallback.png", size=(136, 136))
        scan_result = self.manager._scan_single_mod(
            str(self.mod_root),
            {**self.options, "process_mode": "scaled_only_overwrite"},
        )
        batches = self.manager._build_encode_batches(scan_result["entries"])

        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["source_paths"], [str(scaled)])
        self.assertNotIn(str(fallback), batches[0]["source_paths"])
        self.assertEqual(self.manager._count_skipped_entries(scan_result["entries"], {**self.options, "process_mode": "scaled_only_overwrite"}), 1)

    def test_should_skip_texture_matches_old_script_dimension_window(self):
        self.assertTrue(self.manager._should_skip_texture({"width": 127, "height": 256}, self.options))
        self.assertTrue(self.manager._should_skip_texture({"width": 4096, "height": 512}, self.options))
        self.assertFalse(self.manager._should_skip_texture({"width": 512, "height": 512}, self.options))

    def test_resolve_scan_workers_uses_auto_cap_and_manual_override(self):
        auto_workers = self.manager._resolve_scan_workers(12, self.options)
        manual_workers = self.manager._resolve_scan_workers(12, {**self.options, "scan_workers": 3})

        self.assertGreaterEqual(auto_workers, 1)
        self.assertLessEqual(auto_workers, 8)
        self.assertEqual(manual_workers, 3)

    def test_scale_factor_above_one_updates_target_dimensions(self):
        self.assertEqual(
            self.manager._calculate_target_dimensions(64, 32, {**self.options, "scale_factor": 2.0}),
            (128, 64),
        )

    def test_cached_snapshot_without_current_schema_is_ignored(self):
        self.manager._store_scan_snapshot(
            {
                "id": "snapshot-old",
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


class TestTextureOptimizationPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        self.results_dir = self.temp_root / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.exclusions_path = self.temp_root / "texture_opt_exclusions.json"
        self.results_patcher = patch.object(texture_opt_module, "TEXTURE_RESULTS_DIR", self.results_dir)
        self.exclusions_patcher = patch.object(texture_opt_module, "TEXTURE_EXCLUSIONS_PATH", self.exclusions_path)
        self.results_patcher.start()
        self.exclusions_patcher.start()
        self.addCleanup(self.results_patcher.stop)
        self.addCleanup(self.exclusions_patcher.stop)

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

    def test_mod_exclusion_removes_entries_from_generation_plan(self):
        self._write_png("Textures/excluded.png")
        self.manager.set_mod_exclusion("Example.Mod", True)

        projected = self.manager._scan_single_target(
            {
                "mod_path": str(self.mod_root),
                "mod_name": "ExampleMod",
                "package_id": "example.mod",
            },
            self.options,
            apply_exclusions=True,
        )

        self.assertEqual(projected["stat"]["package_id"], "example.mod")
        self.assertEqual(projected["stat"]["excluded_count"], 1)
        self.assertEqual(projected["stat"]["generate_required_count"], 0)
        self.assertEqual(projected["entries"][0]["action_status"], "excluded")
        self.assertTrue(projected["entries"][0]["excluded"])
        self.assertEqual(self.manager._build_encode_batches(projected["entries"]), [])

    def test_file_exclusion_removes_single_entry_from_generation_plan(self):
        self._write_png("Textures/keep.png")
        self._write_png("Textures/skip.png")
        self.manager.set_file_exclusion(str(self.mod_root), "Textures/skip.png", True)

        projected = self.manager._scan_single_mod(str(self.mod_root), self.options)
        entries = {entry["rel_path"]: entry for entry in projected["entries"]}

        self.assertEqual(projected["stat"]["excluded_count"], 1)
        self.assertEqual(projected["stat"]["generate_required_count"], 1)
        self.assertEqual(entries["Textures/skip.png"]["action_status"], "excluded")
        self.assertEqual(entries["Textures/keep.png"]["action_status"], "pending")

    def test_result_history_keeps_latest_three_files(self):
        for index in range(4):
            task = TextureTask(
                id=f"task-{index}",
                action="optimize",
                mod_paths=[str(self.mod_root)],
                options=dict(self.options),
                status="running",
                created_at=1000 + index,
                updated_at=1000 + index,
            )
            self.manager._write_task_result_file(
                task,
                self.options,
                self.manager._create_empty_stat(include_mod_count=True, mod_count=1),
                [],
                [],
            )
            time.sleep(0.01)

        history = self.manager.list_result_history(10)

        self.assertEqual([item["task_id"] for item in history], ["task-3", "task-2", "task-1"])
        self.assertEqual(len(list(self.results_dir.glob("*.json"))), 3)
        self.assertTrue(all(Path(item["result_path"]).exists() for item in history))


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
            self.assertIn("-r", command)
            self.assertIn("Textures", command)
            self.assertIn("-t", command)
            self.assertIn("-p", command)
            self.assertNotIn("-fs", command)
            self.assertIn("-sc", command)
            self.assertIn("50", command)
            self.assertIn("-ms", command)
            self.assertIn("1024", command)
            self.assertNotIn("-ss", command)
            input_list = Path(command[-1])
            self.assertEqual(input_list.suffix.lower(), ".txt")
            self.assertTrue(input_list.exists())
            self.assertIn(str(self.source), input_list.read_text(encoding="utf-8"))

        with patch.object(ToddsEncoder, "resolve_executable", return_value=self.temp_root / "todds.exe"), \
             patch("backend.managers.mgr_texture_opt._ToolProcessRunner.run_command", side_effect=inspect_todds_command):
            encoder.encode_mod(threading.Event(), source_paths=[str(self.source)])


if __name__ == "__main__":
    unittest.main()
